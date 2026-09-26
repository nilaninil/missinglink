"""FAISS index: IndexIDMap2(IndexHNSWFlat(512, 32, INNER_PRODUCT)) on L2-normalised vectors."""
import logging
import threading
import numpy as np
import faiss
from app.config.settings import FAISS_PATH, EMB_DIR, EMBED_DIM

log = logging.getLogger("missinglink.faiss")
_lock = threading.Lock()
_index = None


def _new_index():
    base = faiss.IndexHNSWFlat(EMBED_DIM, 32, faiss.METRIC_INNER_PRODUCT)
    base.hnsw.efSearch = 64
    return faiss.IndexIDMap2(base)


def save_vector(emb_id: int, vec: np.ndarray):
    np.save(EMB_DIR / f"{emb_id}.npy", vec.astype(np.float32))


def load_vector(emb_id):
    if emb_id is None:
        return None
    p = EMB_DIR / f"{emb_id}.npy"
    return np.load(p) if p.exists() else None


def get_index():
    global _index
    with _lock:
        if _index is None:
            _index = load()
        return _index


def load():
    if FAISS_PATH.exists():
        try:
            idx = faiss.read_index(str(FAISS_PATH))
            if idx.d == EMBED_DIM:
                return idx
        except Exception as e:
            log.warning("FAISS index corrupt (%s); rebuilding from stored embeddings", e)
    return rebuild_from_db()


def rebuild_from_db():
    global _index
    from app.database.db import SessionLocal
    from app.models.orm import FaissMap
    idx = _new_index()
    with SessionLocal() as s:
        rows = s.query(FaissMap).filter(FaissMap.entity_type == "found_record").all()
        ids, vecs = [], []
        for r in rows:
            v = load_vector(r.embedding_id)
            if v is not None and v.shape[0] == EMBED_DIM:
                ids.append(r.embedding_id); vecs.append(v)
    if ids:
        idx.add_with_ids(np.stack(vecs).astype(np.float32), np.array(ids, dtype=np.int64))
    faiss.write_index(idx, str(FAISS_PATH))
    _index = idx
    log.info("FAISS rebuilt with %d vectors", len(ids))
    return idx


def add(emb_id: int, vec: np.ndarray):
    idx = get_index()
    with _lock:
        idx.add_with_ids(vec.reshape(1, -1).astype(np.float32), np.array([emb_id], dtype=np.int64))
        faiss.write_index(idx, str(FAISS_PATH))


def search(vec: np.ndarray, k: int):
    idx = get_index()
    if idx.ntotal == 0:
        return []
    D, I = idx.search(vec.reshape(1, -1).astype(np.float32), min(k, idx.ntotal))
    return [(int(i), float(d)) for i, d in zip(I[0], D[0]) if i != -1]


def count():
    return get_index().ntotal


def reset():
    global _index
    with _lock:
        _index = _new_index()
        faiss.write_index(_index, str(FAISS_PATH))
