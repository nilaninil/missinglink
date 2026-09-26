/* CCTV evidence, document scanner (OCR), evidence timeline, offline/sync, settings. */
"use strict";

function caseSelectRow(id, selected, label = "Case") {
  return `<label class="field" style="min-width:280px"><span>${esc(label)}</span><select id="${id}">${caseOptions(selected)}</select></label>`;
}
function pickCase(q) {
  return q.case || ML.state.currentCase || store.get("currentCase") || (ML.state.cases[0] || {}).id || "";
}

/* ---------------- CCTV */
route("/cctv", async (view, p, q, alive) => {
  await refreshCases();
  if (!alive()) return;
  const caseId = pickCase(q);
  view.innerHTML = `
    <div class="page-head"><div><h1>CCTV evidence</h1>
      <p>Frames are sampled once per second, people are detected, and each person is compared with the case photo — locally, on this device.</p></div></div>
    <section class="panel">
      <div class="row" style="align-items:flex-end">${caseSelectRow("cvCase", caseId)}
        <button class="btn primary" id="cvSample">${icon("play")} Use sample video</button></div>
      <details style="margin-top:14px"><summary class="link-btn">Upload a video instead</summary>
        <form id="cvForm" style="margin-top:10px"><div class="fields">
          <label class="field"><span>Video (MP4 or AVI, up to 50 MB)</span><input type="file" name="video" accept="video/mp4,video/x-msvideo,.avi,.mp4" required></label>
          <label class="field"><span>Camera name</span><input name="camera_name" value="Camera 1"></label>
          <label class="field"><span>Camera locality</span><input name="locality" list="localities">${localityOptions()}</label>
          <label class="field"><span>Recording start</span><input name="start_datetime" type="datetime-local"></label>
        </div><div class="row" style="margin-top:10px"><button class="btn">${icon("upload")} Process video</button></div></form></details>
      <p class="disclaimer">This is a potential visual similarity for authorized investigation, not automatic identification.</p>
    </section>
    <div id="cvOut" style="margin-top:16px"></div>`;

  const show = (res, cid) => {
    const out = $("#cvOut", view);
    if (!res.sightings.length) { out.innerHTML = `<div class="panel empty"><h3>No potential sightings</h3><p>${esc(res.message || "")} ${res.frames_analysed || 0} frames analysed.</p></div>`; return; }
    out.innerHTML = `<section class="panel"><div class="panel-head"><h2>${res.sightings.length} potential sighting${res.sightings.length > 1 ? "s" : ""}</h2>
      <span class="small muted">${res.frames_analysed} frames analysed</span></div>
      <div class="cands">${res.sightings.map((s) => `<article class="cand" style="grid-template-columns:120px 1fr 200px">
        <img class="pic" style="width:120px" src="${bust(s.crop_url)}" alt="Detected person crop">
        <div class="meta"><h3>${esc(s.camera_name)} <span class="chip verify">Potential Sighting — Requires Human Verification</span></h3>
          <div class="line">${esc(s.locality || "Unknown locality")}, ${fmtDT(s.frame_datetime)} (video +${s.video_offset_s}s)</div>
          <div class="line">Visual similarity to case photo: <b>${pct(s.visual_similarity)}</b>${s.location_compatibility != null ? ` · Location compatibility with last known place: <b>${pct(s.location_compatibility)}</b>` : ""}</div>
          <a class="link-btn small" href="${bust(s.frame_url)}" target="_blank" rel="noopener">View full frame</a></div>
        <div class="side"><button class="btn primary" data-att="${s.id}">${icon("plus")} Add to evidence timeline</button></div></article>`).join("")}</div></section>
      <div id="cvRank"></div>`;
    $$("[data-att]", out).forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const r = await api(`/cctv/${b.dataset.att}/attach`, { method: "POST" });
        ML.state.lastResults[cid] = r;
        b.textContent = "Added to timeline";
        $("#cvRank", view).innerHTML = `<div style="margin-top:14px">${rerankBanner(r) || `<div class="note">Sighting added. Ranking recomputed.</div>`}
          <a class="btn" href="#/cases/${encodeURIComponent(cid)}">Open case ranking</a></div>`;
      } catch (e) { b.disabled = false; }
    }));
  };
  $("#cvSample", view).addEventListener("click", async () => {
    const cid = $("#cvCase", view).value;
    const out = $("#cvOut", view);
    try {
      const res = await withPhases(out, ["Sampling one frame per second…", "Detecting people in each frame…", "Comparing people with the case photo…"],
        api("/cctv/sample", { method: "POST", json: { case_id: cid }, timeout: 120000 }));
      show(res, cid);
    } catch (e) { out.innerHTML = ""; }
  });
  $("#cvForm", view).addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    fd.append("case_id", $("#cvCase", view).value);
    const out = $("#cvOut", view);
    try {
      const res = await withPhases(out, ["Uploading video…", "Detecting people in each frame…", "Comparing people with the case photo…"],
        api("/cctv/process", { method: "POST", form: fd, timeout: 180000 }));
      show(res, $("#cvCase", view).value);
    } catch (err) { out.innerHTML = ""; }
  });
});

/* ---------------- documents / OCR */
const OCR_LABELS = { name: "Name", age: "Age", gender: "Gender", location: "Location", destination: "Destination / admitted to",
  pickup_location: "Pickup location", pickup_time: "Pickup time", admitted: "Admitted at", time: "Time", date: "Date",
  clothing: "Clothing", record_ref: "Linked record reference" };

route("/documents", async (view, p, q, alive) => {
  await refreshCases();
  const samples = await api("/ocr/samples");
  if (!alive()) return;
  const caseId = pickCase(q);
  let current = null;
  view.innerHTML = `
    <div class="page-head"><div><h1>Document scanner</h1>
      <p>Read hospital logs, shelter intake forms and police reports on this device. Check any field highlighted in amber before adding it as evidence.</p></div></div>
    <section class="panel"><div class="row" style="align-items:flex-end">
      ${samples.map((s) => `<button class="btn" data-sample="${esc(s.key)}">${icon("doc")} ${esc(s.label)}</button>`).join("")}
      <span class="spacer"></span>
      <label class="btn dark">${icon("upload")} Upload or photograph a document<input type="file" id="docFile" accept="image/*" capture="environment" hidden></label></div></section>
    <div id="docOut" style="margin-top:16px"></div>`;

  const paint = (res, imgUrl) => {
    current = res;
    const keys = Object.keys(OCR_LABELS).filter((k) => res.fields[k]).concat(Object.keys(res.fields).filter((k) => !OCR_LABELS[k]));
    const needs = keys.some((k) => res.fields[k].needs_verification);
    $("#docOut", view).innerHTML = `<div class="grid g2">
      <section class="panel"><h3>Scanned document</h3>${imgUrl ? `<img class="doc-img" src="${bust(imgUrl)}" alt="Scanned document">` : ""}
        <p class="small muted" style="margin-top:8px">Engine: ${esc(res.engine || "unavailable")}</p></section>
      <section class="panel"><div class="panel-head"><h3>Extracted fields</h3>${needs ? `<span class="chip verify">Some fields require verification.</span>` : `<span class="chip possible">Read with good confidence</span>`}</div>
        ${res.message ? `<p class="small">${esc(res.message)}</p>` : ""}
        <form id="docForm"><div class="fields">
          ${keys.map((k) => { const f = res.fields[k]; return `<label class="field ${f.needs_verification ? "needs" : ""}"><span>${esc(OCR_LABELS[k] || k)}</span>
            <input data-key="${esc(k)}" value="${esc(f.value)}"><span class="hint">Confidence ${pct(f.confidence, 1)}${f.needs_verification ? " — please check" : ""}</span></label>`; }).join("")}
          <label class="field"><span>Document type</span><select id="docType">
            ${["hospital_record", "shelter_record", "investigator_note", "ocr_document"].map((t) => `<option value="${t}" ${t === res.document_type ? "selected" : ""}>${esc({ hospital_record: "Hospital record", shelter_record: "Shelter record", investigator_note: "Police / investigator note", ocr_document: "Other document" }[t])}</option>`).join("")}</select></label>
          <label class="field"><span>Source organisation</span><select id="docOrg">${orgOptions(res.source_org_id)}</select></label>
          ${caseSelectRow("docCase", caseId, "Attach to case")}
        </div><div class="row" style="margin-top:12px"><button class="btn primary">${icon("plus")} Add as evidence and re-rank</button></div></form>
        <div id="docRank"></div></section></div>
      ${res.raw_text ? `<details class="panel" style="margin-top:16px"><summary class="link-btn">Raw text read from the image</summary><pre style="white-space:pre-wrap;font-size:.85rem">${esc(res.raw_text)}</pre></details>` : ""}`;
    $$("input[data-key]", view).forEach((inp) => inp.addEventListener("input", () => {
      const f = current.fields[inp.dataset.key]; f.value = inp.value; f.edited = true; inp.closest(".field").classList.remove("needs");
    }));
    $("#docForm", view).addEventListener("submit", async (e) => {
      e.preventDefault();
      const cid = $("#docCase", view).value;
      const btn = $("button.primary", e.target); btn.disabled = true;
      try {
        const r = await api("/ocr/attach", { method: "POST", json: { case_id: cid, fields: current.fields, document_type: $("#docType", view).value,
          source_org_id: $("#docOrg", view).value || null } });
        ML.state.lastResults[cid] = r;
        $("#docRank", view).innerHTML = `<div style="margin-top:14px">${rerankBanner(r) || `<div class="note">Document added. Ranking recomputed.</div>`}
          <a class="btn" href="#/cases/${encodeURIComponent(cid)}">Open case ranking</a></div>`;
        toast("Document added as evidence.");
      } catch (err) { btn.disabled = false; }
    });
  };

  $$("[data-sample]", view).forEach((b) => b.addEventListener("click", async () => {
    $("#docOut", view).innerHTML = loading("Reading document locally…");
    try { const r = await api(`/ocr/sample/${b.dataset.sample}`, { method: "POST", timeout: 60000 }); paint(r, r.image_url); }
    catch (e) { $("#docOut", view).innerHTML = ""; }
  }));
  $("#docFile", view).addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("image", f);
    $("#docOut", view).innerHTML = loading("Reading document locally…");
    try { const r = await api("/ocr/extract", { method: "POST", form: fd, timeout: 60000 }); paint(r, URL.createObjectURL(f)); }
    catch (err) { $("#docOut", view).innerHTML = ""; }
  });
});

/* ---------------- timeline */
route("/timeline", async (view, p, q, alive) => {
  await refreshCases();
  const caseId = q.case || "";
  const events = caseId ? await api(`/cases/${encodeURIComponent(caseId)}/timeline`) : (await api("/timeline?limit=80")).slice().reverse();
  if (!alive()) return;
  view.innerHTML = `
    <div class="page-head"><div><h1>Evidence timeline</h1><p>Every report, piece of evidence, re-ranking and review decision, in time order.</p></div>
      <label class="field" style="min-width:280px"><span>Show</span><select id="tlCase"><option value="">All cases</option>${caseOptions(caseId)}</select></label></div>
    <section class="panel">${timelineList(events)}</section>`;
  $("#tlCase", view).addEventListener("change", (e) => go(e.target.value ? `#/timeline?case=${encodeURIComponent(e.target.value)}` : "#/timeline"));
});

/* ---------------- offline / sync */
route("/sync", async (view, p, q, alive) => {
  const s = await api("/sync/status");
  if (!alive()) return;
  view.innerHTML = `
    <div class="page-head"><div><h1>Offline and sync</h1><p>Everything in the core — photo comparison, search, scoring, OCR and CCTV — runs on this device.
      Records created while offline are kept locally and copied to the regional coordination hub when the connection returns.</p></div></div>
    <div class="grid g2">
      <section class="panel"><h2>${esc(s.message)}</h2>
        <dl class="kv" style="margin-top:12px">
          <dt>Connection</dt><dd>${s.online ? "Online" : "Offline"} ${ML.state.simulated ? "(simulated)" : ""}</dd>
          <dt>Pending cases</dt><dd>${s.pending.missing_cases || 0}</dd>
          <dt>Pending records</dt><dd>${s.pending.found_records || 0}</dd>
          <dt>Pending evidence</dt><dd>${s.pending.evidence || 0}</dd>
          <dt>Rows in hub</dt><dd>${s.hub_rows}</dd></dl>
        <div class="row" style="margin-top:14px"><button class="btn primary" id="syncRun" ${s.online && s.pending_total ? "" : "disabled"}>${icon("sync")} Sync now</button>
          <button class="btn" id="syncToggle">${ML.state.online ? "Simulate going offline" : "Simulate reconnecting"}</button></div>
        <div id="syncOut"></div></section>
      <section class="panel"><h3>Test it yourself</h3><ol class="small">
        <li>Turn off Wi-Fi, or use the ONLINE / OFFLINE pill at the top to simulate it.</li>
        <li>Create a case or a found record, run matching, attach evidence. Everything keeps working.</li>
        <li>New rows show a Pending Sync badge.</li>
        <li>Reconnect, then press Sync now. Rows are copied into <span class="kbd">data/hub.db</span>, the simulated regional hub.</li></ol></section>
    </div>`;
  $("#syncRun", view).addEventListener("click", async () => {
    try { const r = await api("/sync/run", { method: "POST" }); toast(`${r.synced} rows synced to the hub.`); renderRoute(); } catch (e) { /* toast */ }
  });
  $("#syncToggle", view).addEventListener("click", async () => { await setOffline(ML.state.online); renderRoute(); });
});

/* ---------------- settings */
const WEIGHT_LABELS = { photo: "Photo similarity", age: "Age compatibility", gender: "Gender", clothing: "Clothing", location: "Location",
  time: "Time plausibility", corroboration: "Corroborating record", occupation: "Occupation (example factor)" };

route("/settings", async (view, p, q, alive) => {
  await refreshCases();
  const cfg = await api("/config/weights");
  if (!alive()) return;
  const caseId = pickCase(q);
  view.innerHTML = `
    <div class="page-head"><div><h1>Settings</h1><p>Scoring weights live in one configuration file. Changing them re-runs matching immediately, so the effect is visible.</p></div></div>
    <div class="grid g-main">
      <section class="panel"><h2>Evidence weights</h2>
        <p class="small muted">Weights do not need to sum to 1 — the engine normalises over the evidence that is available for each candidate. Set a weight to 0 to switch a factor off.</p>
        <div id="sliders">${Object.entries(cfg.weights).map(([k, v]) => `<div class="slider"><label for="w_${k}">${esc(WEIGHT_LABELS[k] || k)}</label>
          <input id="w_${k}" type="range" min="0" max="1" step="0.05" value="${v}" data-k="${esc(k)}"><b>${Number(v).toFixed(2)}</b></div>`).join("")}</div>
        <div class="row" style="margin-top:14px;align-items:flex-end">${caseSelectRow("setCase", caseId, "Re-run for case")}
          <button class="btn primary" id="applyW">${icon("rank")} Apply and re-rank</button><button class="btn" id="resetW">Restore defaults</button></div>
        <div id="setOut"></div></section>
      <aside class="stack">
        <section class="panel"><h3>Bands and retrieval</h3><dl class="kv">
          <dt>High-priority</dt><dd>${pct(cfg.bands.high_priority)} or more, 3+ factors, no critical conflict</dd>
          <dt>Potential match</dt><dd>${pct(cfg.bands.possible)} or more</dd>
          <dt>FAISS top-K</dt><dd>${cfg.top_k}</dd><dt>Score cap</dt><dd>99%</dd></dl></section>
        <section class="panel"><h3>Demo data</h3><p class="small muted">Wipe this device's database and regenerate the synthetic scenario.</p>
          <button class="btn danger" id="resetDemo">Reset demo data</button></section>
      </aside>
    </div>`;
  $$("#sliders input", view).forEach((i) => i.addEventListener("input", () => { i.nextElementSibling.textContent = Number(i.value).toFixed(2); }));
  $("#applyW", view).addEventListener("click", async () => {
    const weights = Object.fromEntries($$("#sliders input", view).map((i) => [i.dataset.k, Number(i.value)]));
    const cid = $("#setCase", view).value;
    try {
      const r = await api("/config/weights", { method: "PUT", json: { weights, rerun_case_id: cid } });
      if (r.result) {
        ML.state.lastResults[cid] = r.result;
        $("#setOut", view).innerHTML = `<div style="margin-top:14px">${rerankBanner(r.result) || `<div class="note">Weights saved. Ranking unchanged.</div>`}
          <p class="small">Top 3 now: ${r.result.candidates.slice(0, 3).map((c) => `#${c.rank} <span class="id">${esc(c.record_id)}</span> ${pct(c.overall_score)}`).join(" · ")}</p>
          <a class="btn" href="#/cases/${encodeURIComponent(cid)}">Open case ranking</a></div>`;
      }
      toast("Weights saved.");
    } catch (e) { /* toast */ }
  });
  $("#resetW", view).addEventListener("click", async () => { await api("/config/weights/reset", { method: "POST" }); toast("Default weights restored."); renderRoute(); });
  $("#resetDemo", view).addEventListener("click", async () => {
    if (!confirm("Reset all demo data on this device?")) return;
    try { await api("/demo/reset", { method: "POST", timeout: 120000 }); ML.state.lastResults = {}; ML.bustKey = Date.now(); await refreshCases(); toast("Demo data reset."); go("#/dashboard"); }
    catch (e) { /* toast */ }
  });
});
