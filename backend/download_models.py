"""One-time, online step: download CLIP weights into backend/models so the app can run fully offline later.
Safe to skip — the app falls back to its built-in visual encoder."""
import os
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
try:
    from app.services.embedding_service import ClipEncoder  # noqa
except Exception:
    ClipEncoder = None
try:
    import open_clip
    from app.config.settings import MODELS_DIR
    open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k", cache_dir=str(MODELS_DIR))
    print("CLIP weights downloaded to", MODELS_DIR)
except Exception as e:
    print("CLIP not available (", e.__class__.__name__, ") — MissingLink will use the fallback visual encoder.")
