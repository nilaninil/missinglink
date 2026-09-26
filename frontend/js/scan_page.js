/* Live body scan: reference photo of the missing person + camera scan of a person in the field,
   analysed region by region, then attached to the case as evidence (which re-ranks candidates). */
"use strict";

route("/scan", async (view, p, q, alive) => {
  await refreshCases();
  let records = [];
  try { records = await api("/records", { quiet: true }); } catch (e) { /* optional */ }
  if (!alive()) return;
  const firstWithPhoto = (ML.state.cases.find((c) => c.photo_url) || {}).id;
  let caseId = q.case || ML.state.currentCase || store.get("currentCase") || firstWithPhoto || "";
  let refMode = "case";          // "case" | "upload"
  let scanBlob = null;
  let lastScan = null;

  view.innerHTML = `
    <div class="page-head"><div><h1>Live body scan</h1>
      <p>Compare a person in front of the camera with the missing person's photo. The analysis checks overall appearance, upper and lower clothing,
        the face or head region, and build — and shows how far each agrees.</p></div></div>

    <div class="scan-grid">
      <section class="panel">
        <div class="panel-head"><h2>Missing person's photo</h2></div>
        <div class="row" style="margin-bottom:10px">
          <label class="field" style="flex:1"><span>Compare against case</span><select id="scCase"><option value="">No case — upload a photo</option>${caseOptions(caseId)}</select></label>
        </div>
        <div class="row small" style="margin-bottom:10px">
          <label><input type="radio" name="refMode" value="case" checked> Use the photo on the case</label>
          <label><input type="radio" name="refMode" value="upload"> Upload a different photo</label>
        </div>
        <div id="refCase"></div>
        <div id="refUpload" hidden></div>
      </section>

      <section class="panel">
        <div class="panel-head"><h2>Person in the field</h2></div>
        <div class="dropzone" id="scanZone">
          <div class="scan-cta" id="scanEmpty">
            <svg class="empty-ill" viewBox="0 0 60 100" aria-hidden="true"><circle cx="30" cy="14" r="10" fill="none" stroke="#5d6b78" stroke-width="3"/>
              <path d="M12 30h36l5 30h-9l-2 36H34l-4-28-4 28h-8l-2-36H7z" fill="none" stroke="#5d6b78" stroke-width="3" stroke-linejoin="round"/></svg>
            <button class="scan-btn" id="scanBtn">${icon("scan")} Scan the body</button>
            <p class="small muted">Opens the camera with a head-to-toe guide frame.</p>
            <div class="row" style="justify-content:center">
              <label class="btn sm">${icon("upload")} Upload a photo<input type="file" id="scanFile" accept="image/*" capture="environment" hidden></label>
              <button class="btn sm" id="scanSample">Use sample field capture</button>
            </div>
          </div>
          <div id="scanFull" hidden><img class="preview" id="scanPreview" alt="Captured scan">
            <div class="row" style="justify-content:center;margin-top:10px"><button class="btn sm" id="rescan">${icon("camera")} Scan again</button>
            <button class="btn sm" id="scanClear">${icon("x")} Remove</button></div></div>
        </div>
      </section>
    </div>

    <div class="row" style="margin:16px 0;justify-content:center">
      <button class="btn primary big" id="analyseBtn" disabled>${icon("eye")} Analyse match</button>
    </div>
    <div id="scanResult"></div>`;

  const refPicker = photoPicker($("#refUpload", view), { label: "Reference photo of the missing person", onChange: () => checkReady() });

  const paintRefCase = () => {
    const c = ML.state.cases.find((x) => x.id === caseId);
    const box = $("#refCase", view);
    if (!c) { box.innerHTML = `<div class="dropzone"><p class="muted">Choose a case, or upload a reference photo.</p></div>`; return; }
    box.innerHTML = c.photo_url
      ? `<div class="dropzone"><div><img class="preview" src="${bust(c.photo_url)}" alt="Case photo"><p class="small" style="margin-top:8px">
          <b>${esc(c.name || c.id)}</b> — ${ageText(c)}, ${esc(c.gender || "gender unknown")}, ${esc(c.clothing_text || "")}</p></div></div>`
      : `<div class="dropzone"><div><p><b>${esc(c.name || c.id)}</b> has no photo on file.</p><p class="small muted">Choose "Upload a different photo" to add one for this scan.</p></div></div>`;
  };
  const setRefMode = (m) => {
    refMode = m;
    $("#refCase", view).hidden = m !== "case";
    $("#refUpload", view).hidden = m !== "upload";
    $$("input[name=refMode]", view).forEach((r) => (r.checked = r.value === m));
    checkReady();
  };
  const refReady = () => (refMode === "upload" ? !!refPicker.get() : !!(ML.state.cases.find((x) => x.id === caseId) || {}).photo_url);
  const checkReady = () => { $("#analyseBtn", view).disabled = !(scanBlob && refReady()); };
  const setScan = (b) => {
    scanBlob = b;
    $("#scanEmpty", view).hidden = !!b; $("#scanFull", view).hidden = !b;
    if (b) $("#scanPreview", view).src = URL.createObjectURL(b);
    checkReady();
  };

  paintRefCase();
  if (!caseId) setRefMode("upload");
  $("#scCase", view).addEventListener("change", (e) => {
    caseId = e.target.value;
    if (caseId) { ML.state.currentCase = caseId; store.set("currentCase", caseId); }
    paintRefCase();
    setRefMode(caseId ? "case" : "upload");
  });
  $$("input[name=refMode]", view).forEach((r) => r.addEventListener("change", () => setRefMode(r.value)));

  const openCam = async () => { const b = await Camera.capture({ title: "Scan the body", guide: true }); if (b) setScan(b); };
  $("#scanBtn", view).addEventListener("click", openCam);
  $("#rescan", view).addEventListener("click", openCam);
  $("#scanClear", view).addEventListener("click", () => setScan(null));
  $("#scanFile", view).addEventListener("change", (e) => { if (e.target.files[0]) setScan(e.target.files[0]); });
  $("#scanSample", view).addEventListener("click", async () => {
    try {
      const r = await fetch("/samples/scans/field_capture.png");
      if (!r.ok) throw new Error();
      setScan(await r.blob());
      toast("Loaded a synthetic field capture from a dim hospital ward.");
    } catch (e) { toast("Sample capture not found. Reset the demo data in Settings.", "error"); }
  });

  $("#analyseBtn", view).addEventListener("click", async () => {
    const fd = new FormData();
    fd.append("scan", scanBlob, "scan.jpg");
    if (refMode === "upload") fd.append("reference", refPicker.get(), "reference.jpg");
    else if (caseId) fd.append("case_id", caseId);
    if (refMode === "upload" && caseId) fd.append("case_id", caseId);
    const out = $("#scanResult", view);
    const btn = $("#analyseBtn", view); btn.disabled = true;
    try {
      lastScan = await withPhases(out, ["Finding the person in each image…", "Comparing upper and lower clothing…",
        "Comparing face / head region…", "Comparing overall appearance and build…"], api("/scan/analyze", { method: "POST", form: fd, timeout: 60000 }));
      paintResult(lastScan);
    } catch (e) { /* toast */ }
    btn.disabled = false; checkReady();
  });

  function paintResult(r) {
    const out = $("#scanResult", view);
    out.innerHTML = `
      <section class="panel">
        <div class="result-hero">
          ${dial(r.overall_score, r.components, { size: "lg", label: "visual agreement" })}
          <div>
            <div class="row" style="margin-bottom:8px">${bandChip(r.band, r.band_text)} <span class="chip verify">${esc(r.status_text)}</span></div>
            <p class="summary">${esc(r.summary)}</p>
            <p class="small muted">${esc(r.coverage_text)}. Person found by: reference — ${esc(r.reference.detection)}; scan — ${esc(r.scan.detection)}. Encoder: ${esc(r.encoder)}.</p>
            ${r.warnings.length ? `<div class="warnings"><b>Check before relying on this</b><ul>${r.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}
            <p class="disclaimer">${esc(r.disclaimer)}</p>
          </div>
        </div>
      </section>
      <div class="grid g2" style="margin-top:16px">
        <section class="panel"><h3>What was compared</h3>${factorBreakdown(r.components)}</section>
        <section class="panel"><h3>Regions analysed</h3>
          <div class="crops"><figure><img src="${bust(r.reference.crop_url)}" alt="Reference crop"><figcaption>Missing person's photo</figcaption></figure>
            <figure><img src="${bust(r.scan.crop_url)}" alt="Scan crop"><figcaption>Field scan</figcaption></figure></div>
          <div class="legend" style="margin-top:10px"><span><i style="border-color:#f2a900"></i>Head / face</span><span><i style="border-color:#009688"></i>Upper body</span><span><i style="border-color:#5a6ec8"></i>Lower body</span></div>
        </section>
      </div>
      ${r.similar_records && r.similar_records.length ? `<section class="panel" style="margin-top:16px"><h3>Visually similar found records on this device</h3>
        <p class="small muted">From the local FAISS index. Linking the scan to one of them adds corroborating evidence to that record.</p>
        <div class="similar">${r.similar_records.map((s) => `<div class="s">${s.record.photo_url ? `<img src="${bust(s.record.photo_url)}" alt="">` : ""}
          <b class="id">${esc(s.record.id)}</b><br>${esc(s.record.locality || "")}<br>${pct(s.visual_similarity)} visual</div>`).join("")}</div></section>` : ""}
      <section class="panel" style="margin-top:16px" id="attachPanel">
        <h2>Add this scan to the case</h2>
        <p class="small muted">The scan becomes evidence on the case timeline and every candidate is re-scored. It is flagged as requiring human verification.</p>
        <form id="attachForm"><div class="fields">
          <label class="field"><span>Case</span><select name="case_id" required><option value="">Choose a case</option>${caseOptions(r.case_id || caseId)}</select></label>
          <label class="field"><span>Where was this scan taken?</span><input name="locality" list="localities" placeholder="e.g. Kilpauk">${localityOptions()}</label>
          <label class="field full"><span>This person is</span>
            <div class="stack small" style="margin-top:4px">
              <label><input type="radio" name="linkMode" value="link" ${r.similar_records && r.similar_records.length ? "checked" : ""}> Already on a found record:
                <select name="linked_record_id">${records.map((x) => `<option value="${esc(x.id)}" ${r.similar_records && r.similar_records[0] && r.similar_records[0].record.id === x.id ? "selected" : ""}>
                  ${esc(x.id)} — ${esc(RECORD_TYPES[x.record_type] || x.record_type)}, ${esc(x.locality || "")}</option>`).join("")}</select></label>
              <label><input type="radio" name="linkMode" value="new" ${r.similar_records && r.similar_records.length ? "" : "checked"}> Not on any record yet — create a new sighting record with this photo</label>
            </div></label>
          <label class="field"><span>Date and time of scan</span><input name="observed_datetime" type="datetime-local"></label>
          <label class="field"><span>Gender</span><select name="gender"><option value="">Unknown</option><option>Male</option><option>Female</option><option>Other</option></select></label>
          <label class="field"><span>Approx. age range</span><div class="row"><input name="age_min" type="number" placeholder="min" style="width:48%"><input name="age_max" type="number" placeholder="max" style="width:48%"></div></label>
          <label class="field"><span>Clothing seen</span><input name="clothing_text" placeholder="e.g. blue shirt, black trousers"></label>
          <label class="field full"><span>Notes</span><textarea name="notes"></textarea></label>
        </div><div class="row" style="margin-top:12px"><button class="btn primary">${icon("plus")} Add scan as evidence and re-rank</button></div></form>
        <div id="attachOut"></div>
      </section>`;
    const now = new Date(); now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    $("[name=observed_datetime]", out).value = now.toISOString().slice(0, 16);
    $("#attachForm", out).addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      if (!f.case_id) { toast("Choose the case this scan relates to.", "warn"); return; }
      const body = { ...f };
      if (f.linkMode !== "link") delete body.linked_record_id;
      delete body.linkMode;
      Object.keys(body).forEach((k) => { if (body[k] === "") delete body[k]; });
      const btn = $("button.primary", e.target); btn.disabled = true;
      try {
        const res = await api(`/scan/${r.scan_id}/attach`, { method: "POST", json: body });
        ML.state.lastResults[f.case_id] = res;
        const top = res.candidates.slice(0, 3);
        $("#attachOut", out).innerHTML = `<div style="margin-top:14px">${rerankBanner(res) || `<div class="note">Evidence added. Ranking recomputed.</div>`}
          ${res.created_record_id ? `<p>New sighting record <span class="id">${esc(res.created_record_id)}</span> created from this scan ${syncChip(res.evidence_sync_status)}.</p>` : ""}
          <p><b>Top candidates now:</b> ${top.map((c) => `#${c.rank} <span class="id">${esc(c.record_id)}</span> ${pct(c.overall_score)}`).join(" · ")}</p>
          <a class="btn primary" href="#/cases/${encodeURIComponent(f.case_id)}">${icon("rank")} Open updated ranking</a></div>`;
        toast("Scan added as evidence. Candidates re-ranked.");
      } catch (err) { btn.disabled = false; }
    });
    out.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
