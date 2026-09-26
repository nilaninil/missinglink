/* Case detail (match results) and the candidate / investigator view. */
"use strict";

async function loadCaseBundle(caseId) {
  const [detail, history, timeline] = await Promise.all([
    api(`/cases/${encodeURIComponent(caseId)}`),
    api(`/match/${encodeURIComponent(caseId)}/history`),
    api(`/cases/${encodeURIComponent(caseId)}/timeline`),
  ]);
  return { detail, history, timeline };
}

function profileBlock(p) {
  if (!p) return "";
  const age = p.age_range && p.age_range[0] != null ? `${p.age_range[0]}–${p.age_range[1]}` : "Unknown";
  return `<dl class="kv">
    <dt>Age range</dt><dd>${esc(age)}</dd>
    <dt>Gender</dt><dd>${esc(p.gender || "Unknown")}</dd>
    <dt>Clothing</dt><dd>${esc(p.clothing || "Unknown")}</dd>
    <dt>Last known</dt><dd>${esc(p.last_known_locality || "Unknown")}, ${fmtDT(p.last_known_time)}<div class="small muted">from ${esc(p.last_known_source || "report")}</div></dd>
    <dt>Linked records</dt><dd>${(p.linked_records || []).length ? p.linked_records.map((r) => `<span class="id">${esc(r)}</span>`).join(", ") : "None yet"}</dd>
  </dl>${(p.notes || []).length ? `<div class="warnings" style="margin-top:10px">${p.notes.map(esc).join("<br>")}</div>` : ""}`;
}

function evidenceList(evs) {
  if (!evs.length) return `<p class="small muted">No evidence attached yet. Add a hospital record, scanned document, CCTV sighting or body scan to update the ranking.</p>`;
  return `<ul class="why-list">${evs.map((e) => `<li class="${e.needs_verification ? "warning" : "support"}"><span class="ic">${e.needs_verification ? "⚠" : "✓"}</span>
    <span><b>${esc(e.label)}</b> ${syncChip(e.sync_status)}${e.needs_verification ? ` <span class="chip verify">Requires Human Verification</span>` : ""}
    <div class="small muted">${esc(e.source_org || "Unknown source")} · ${esc(e.locality || "")} ${e.observed_datetime ? fmtDT(e.observed_datetime) : ""}
    ${e.linked_record_id ? ` · links to <span class="id">${esc(e.linked_record_id)}</span>` : ""}</div></span></li>`).join("")}</ul>`;
}

route("/cases/:id", async (view, { id }, q, alive) => {
  let { detail, history, timeline } = await loadCaseBundle(id);
  if (!alive()) return;
  const c = detail.case;
  ML.state.currentCase = c.id;
  store.set("currentCase", c.id);
  let res = ML.state.lastResults[c.id] || detail.last_result;

  view.innerHTML = `
    <div class="page-head"><div><div class="crumb"><a href="#/cases">Missing cases</a></div>
      <h1>${esc(c.name || "Unnamed person")} <span class="id muted" style="font-size:1.1rem">${esc(c.id)}</span></h1></div>
      <span class="chip status-${esc(c.status)}">${esc(c.status.replace("_", " "))}</span></div>
    <section class="panel case-head">
      ${c.photo_url ? `<img class="case-photo" src="${bust(c.photo_url)}" alt="Reference photo for ${esc(c.id)}">` : `<div class="case-photo thumb none" style="width:150px">No photo</div>`}
      <div>
        <p style="margin:0">${esc(c.description || "")}</p>
        <div class="facts">
          <div><span>Age</span><b>${ageText(c)}</b></div>
          <div><span>Gender</span><b>${esc(c.gender || "Unknown")}</b></div>
          <div><span>Last seen</span><b>${esc(c.last_seen_locality || "Unknown")}</b> ${fmtDT(c.last_seen_datetime)}</div>
          <div><span>Clothing</span><b>${esc(c.clothing_text || "Unknown")}</b></div>
          <div><span>Reported by</span><b>${esc(c.reporting_org || "Unknown")}</b></div>
          <div><span>Photo</span><b>${esc(c.photo_quality || "none")}</b> ${(c.photo_warnings || []).map(esc).join(" ")}</div>
        </div>
      </div>
      <div class="case-actions">
        <button class="btn primary" id="runMatch">${icon("rank")} Find potential matches</button>
        <button class="btn" id="addEv">${icon("plus")} Add evidence</button>
        <a class="btn dark" href="#/scan?case=${encodeURIComponent(c.id)}">${icon("scan")} Body scan for this case</a>
        <a class="btn" href="#/documents?case=${encodeURIComponent(c.id)}">${icon("doc")} Scan a document</a>
        <a class="btn" href="#/cctv?case=${encodeURIComponent(c.id)}">${icon("cctv")} Check CCTV</a>
      </div>
    </section>
    <div class="grid g-main" style="margin-top:16px">
      <section><div id="bannerBox"></div><div id="resultsBox"></div></section>
      <aside class="stack">
        <section class="panel"><h3>Working profile</h3><p class="small muted">Built from the report plus every attached piece of evidence. Matching always runs on this.</p><div id="profileBox"></div></section>
        <section class="panel"><h3>Ranking history</h3><div id="histBox"></div></section>
        <section class="panel"><h3>Evidence</h3><div id="evBox"></div></section>
        <section class="panel"><div class="panel-head"><h3>Evidence timeline</h3><a class="link-btn" href="#/timeline?case=${encodeURIComponent(c.id)}">Open</a></div><div id="tlBox"></div></section>
      </aside>
    </div>`;

  const paint = (showBanner) => {
    $("#bannerBox", view).innerHTML = showBanner ? rerankBanner(res) : "";
    $("#profileBox", view).innerHTML = profileBlock(res ? res.profile : detail.profile);
    $("#histBox", view).innerHTML = historyChart(history);
    $("#evBox", view).innerHTML = evidenceList(detail.evidence);
    $("#tlBox", view).innerHTML = timelineList(timeline.slice(-8));
    const box = $("#resultsBox", view);
    if (!res) {
      box.innerHTML = `<div class="panel empty"><h3>No ranking yet</h3><p>Run matching to compare this case with every found record on this device.</p></div>`;
      return;
    }
    const partial = res.candidates.length && res.candidates.every((x) => x.coverage < 4);
    box.innerHTML = retrievalBox(res) +
      (partial ? `<div class="warnings" style="margin-bottom:12px">Partial information received. Candidates are ranked on the evidence that is available.</div>` : "") +
      `<div class="cands">${res.candidates.map((x) => candidateCard(x, c.id)).join("")}</div>`;
  };
  paint(!!(res && res.rank_changes && res.rank_changes.length && q.fresh !== "0"));

  const refresh = async (newRes, banner = true) => {
    res = newRes;
    const b = await loadCaseBundle(id);
    detail = b.detail; history = b.history; timeline = b.timeline;
    paint(banner);
  };

  $("#runMatch", view).addEventListener("click", async () => {
    const box = $("#resultsBox", view);
    try {
      const r = await withPhases(box, ["Generating visual representation…", "Searching local index…", "Combining available evidence…", "Ranking candidates…"],
        api(`/match/${encodeURIComponent(id)}`, { method: "POST" }));
      ML.state.lastResults[id] = r;
      await refresh(r, false);
    } catch (e) { paint(false); }
  });
  $("#addEv", view).addEventListener("click", async () => { const r = await evidenceModal(id); if (r) await refresh(r); });
  $("#resultsBox", view).addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    if (b.dataset.act === "evidence") { const r = await evidenceModal(id, b.dataset.record); if (r) await refresh(r); }
    if (b.dataset.act === "flag") { const r = await reviewModal(id, b.dataset.record); if (r) await refresh(res, false); }
  });

  if (!res && q.run !== "0") $("#runMatch", view).click();
});

/* ---------------- candidate / investigator view */
route("/cases/:id/candidate/:rid", async (view, { id, rid }, q, alive) => {
  const { detail, history, timeline } = await loadCaseBundle(id);
  let res = ML.state.lastResults[id] || detail.last_result;
  if (!res) res = await api(`/match/${encodeURIComponent(id)}`, { method: "POST" });
  if (!alive()) return;
  ML.state.lastResults[id] = res;
  const c = detail.case;
  const cand = res.candidates.find((x) => x.record.id === rid);
  if (!cand) {
    view.innerHTML = `<div class="panel empty"><h3>${esc(rid)} is not in the current ranking</h3><p>It was not retrieved for this case in the latest run.</p>
      <a class="btn" href="#/cases/${encodeURIComponent(id)}">Back to case</a></div>`;
    return;
  }
  const r = cand.record;
  const linkedEv = detail.evidence.filter((e) => e.linked_record_id === rid);
  const flags = detail.flags.filter((f) => f.record_id === rid);
  const decisionText = { needs_review: "Marked for human review", verified_by_investigator: "Investigator verification recorded",
    rejected: "Rejected by investigator", more_information: "More information requested" };
  const careLoc = ML.state.role === "volunteer"
    ? `<span class="masked">Hidden for field volunteers — locality only</span>`
    : esc(r.care_location_detail || "Not recorded");

  view.innerHTML = `
    <div class="page-head"><div><div class="crumb"><a href="#/cases">Missing cases</a> / <a href="#/cases/${encodeURIComponent(id)}?fresh=0">${esc(id)}</a></div>
      <h1>Candidate <span class="id">${esc(rid)}</span> for ${esc(c.name || id)}</h1>
      <p>Rank #${cand.rank} of ${res.candidates.length} · ${esc(cand.coverage_text)}</p></div>
      <div class="row">${bandChip(cand.band, cand.band_text)} <span class="chip verify">Requires Human Verification</span></div></div>

    <div class="grid g-main">
      <div class="stack">
        <section class="panel">
          <div class="compare">
            <figure>${c.photo_url ? `<img src="${bust(c.photo_url)}" alt="Missing person reference photo">` : `<div class="noimg">No reference photo</div>`}
              <figcaption><b>Missing report ${esc(c.id)}</b><br>${ageText(c)}, ${esc(c.gender || "gender unknown")}<br>${esc(c.clothing_text || "")}<br>
              Last seen ${esc(c.last_seen_locality || "unknown")}, ${fmtDT(c.last_seen_datetime)}</figcaption></figure>
            <figure>${r.photo_url ? `<img src="${bust(r.photo_url)}" alt="Photo on found record">` : `<div class="noimg">No photo on this record — photo factor excluded</div>`}
              <figcaption><b>${esc(RECORD_TYPES[r.record_type] || r.record_type)} ${esc(r.id)}</b> — ${esc(r.source_org || "")}<br>${ageText(r)}, ${esc(r.gender || "gender unknown")}<br>
              ${esc(r.clothing_text || "")}<br>${esc(r.locality || "Unknown")}, ${fmtDT(r.found_datetime)}</figcaption></figure>
          </div>
        </section>
        <section class="panel"><div class="panel-head"><h2>Evidence breakdown</h2><span class="small muted">Weights renormalise over available evidence only</span></div>
          <div class="row" style="align-items:flex-start;gap:24px;flex-wrap:nowrap">
            ${dial(cand.overall_score, cand.factors, { size: "lg" })}
            <div style="flex:1;min-width:0">${factorBreakdown(cand.factors)}</div>
          </div></section>
        <section class="panel"><h2>Why this match?</h2>${whyList(cand.reasons)}
          ${(cand.enrichments || []).length ? `<p class="small muted" style="margin-top:8px">Linked evidence added: ${cand.enrichments.map(esc).join("; ")}</p>` : ""}
          <p class="disclaimer">A high evidence score means "review now". It is never proof of identity.</p></section>
      </div>
      <aside class="stack">
        <section class="panel"><h3>Investigator verification</h3>
          <p class="small muted">Check with the source organisation and the family through protected questions before any disclosure.</p>
          <div class="stack" style="margin-top:10px">
            <button class="btn warn" data-dec="needs_review" style="width:100%">${icon("flag")} Mark for human review</button>
            <button class="btn" data-dec="more_information" style="width:100%">Request more information</button>
            <button class="btn primary" data-dec="verified_by_investigator" style="width:100%" ${ML.state.role === "volunteer" ? "disabled title='Investigators and supervisors only'" : ""}>${icon("check")} Record verification</button>
            <button class="btn danger" data-dec="rejected" style="width:100%" ${ML.state.role === "volunteer" ? "disabled" : ""}>${icon("x")} Reject / investigate further</button>
          </div>
          ${flags.length ? `<ul class="why-list" style="margin-top:10px">${flags.map((f) => `<li class="support"><span class="ic">•</span><span>${esc(decisionText[f.decision] || f.decision)}
            <div class="small muted">${esc(f.role)} · ${fmtDT(f.created_at)} ${f.note ? "· " + esc(f.note) : ""}</div></span></li>`).join("")}</ul>` : ""}
        </section>
        <section class="panel"><h3>Source record</h3><dl class="kv">
          <dt>Source</dt><dd>${esc(r.source_org || "Unknown")}</dd>
          <dt>Type</dt><dd>${esc(RECORD_TYPES[r.record_type] || r.record_type)}</dd>
          <dt>Locality</dt><dd>${esc(r.locality || "Unknown")}</dd>
          <dt>Care location</dt><dd>${careLoc}</dd>
          <dt>Recorded</dt><dd>${fmtDT(r.found_datetime)}</dd>
          <dt>Description</dt><dd>${esc(r.description || "—")}</dd>
          <dt>Photo quality</dt><dd>${esc(r.photo_quality || "no photo")} ${(r.photo_warnings || []).map(esc).join(" ")}</dd>
          <dt>Sync</dt><dd>${r.sync_status === "pending_sync" ? syncChip(r.sync_status) : "Synced"}</dd></dl></section>
        <section class="panel"><h3>Evidence linked to this record</h3>${evidenceList(linkedEv)}</section>
        <section class="panel"><h3>Ranking history</h3>${historyChart(history, [rid])}</section>
        ${detail.cctv_sightings.length ? `<section class="panel"><h3>CCTV potential sightings for this case</h3><div class="similar">${detail.cctv_sightings.map((s) =>
          `<div class="s">${s.crop_url ? `<img src="${bust(s.crop_url)}" alt="">` : ""}<b>${fmtDT(s.frame_datetime, false)}</b><br>${esc(s.camera_name)}<br>${pct(s.visual_similarity)} visual</div>`).join("")}</div></section>` : ""}
        ${detail.body_scans.length ? `<section class="panel"><h3>Field body-scans</h3><div class="similar">${detail.body_scans.map((s) =>
          `<div class="s"><img src="${bust(s.scan_url)}" alt=""><b>${pct(s.overall_score)}</b> visual agreement${s.attached_record_id ? `<br>→ <span class="id">${esc(s.attached_record_id)}</span>` : ""}</div>`).join("")}</div></section>` : ""}
        <section class="panel"><h3>Case timeline</h3>${timelineList(timeline.slice(-6))}</section>
      </aside>
    </div>`;

  $$("[data-dec]", view).forEach((b) => b.addEventListener("click", async () => {
    const r2 = await reviewModal(id, rid, b.dataset.dec);
    if (r2) renderRoute();
  }));
});
