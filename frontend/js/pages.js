/* Dashboard, missing cases, create case, found records. */
"use strict";

async function refreshCases() {
  try { ML.state.cases = await api("/cases", { quiet: true }); } catch (e) { /* keep previous */ }
  return ML.state.cases;
}

/* ---------------- dashboard */
route("/dashboard", async (view, p, q, alive) => {
  const [stats, feed] = await Promise.all([api("/dashboard/stats"), api("/timeline?limit=12")]);
  if (!alive()) return;
  const maxOrg = Math.max(1, ...stats.org_breakdown.map((o) => o.records));
  view.innerHTML = `
    <section class="hero">
      <div class="hero-l">
        <h1>Connect fragmented records into a short, explainable review queue.</h1>
        <p>Police, hospital, shelter and NGO records are compared locally — photo, age, clothing, place and time — and
          every ranking says why. New evidence re-ranks candidates. People are never identified by software; an authorized investigator verifies.</p>
        <div class="row">
          <a class="btn big primary" href="#/demo">${icon("play")} Run demo investigation</a>
          <a class="btn big" href="#/scan">${icon("scan")} Live body scan</a>
          <a class="btn big" href="#/cases/new">${icon("plus")} Report missing person</a>
        </div>
      </div>
      <div class="hero-r">
        <h3>How a case moves</h3>
        <ol class="flow">
          <li>Missing report: photo, age, gender, clothing, last place and time</li>
          <li>Case built with a unique ID</li>
          <li>Police, hospital, shelter and other found records gathered</li>
          <li>Photo, attribute and location-time matching</li>
          <li>Combined evidence score and ranked candidates</li>
          <li>Why this match — support, conflicts, missing evidence</li>
          <li>Investigator verifies, rejects or asks for more</li>
        </ol>
      </div>
    </section>

    <div class="stats">
      <div class="stat"><b>${stats.active_cases}</b><span>Active missing cases</span></div>
      <div class="stat"><b>${stats.potential_matches}</b><span>Potential matches in latest rankings</span></div>
      <div class="stat"><b>${stats.new_evidence_24h}</b><span>New evidence, last 24 h</span></div>
      <div class="stat ${stats.pending_verification ? "attn" : ""}"><b>${stats.pending_verification}</b><span>Pending human verification</span></div>
      <div class="stat ${stats.pending_sync ? "attn" : ""}"><b>${stats.pending_sync}</b><span>Offline records pending sync</span></div>
    </div>

    <div class="grid g-main">
      <section class="panel">
        <div class="panel-head"><h2>Recent activity</h2><a class="link-btn" href="#/timeline">Full evidence timeline</a></div>
        ${timelineList(feed)}
      </section>
      <div class="stack">
        <section class="panel">
          <h3>Where records come from</h3>
          <p class="small muted">Organizations can contribute records they already collect.</p>
          <ul class="orgs">${stats.org_breakdown.map((o) => `<li><span>${esc(o.name)}</span><b>${o.records}</b>
            <span class="bar"><i style="width:${(o.records / maxOrg) * 100}%"></i></span></li>`).join("")}</ul>
        </section>
        <section class="panel">
          <h3>About this prototype</h3>
          <p class="small">We are not replacing investigators or the organizations that already collect missing-person information.
            MissingLink is an AI-assisted matching layer that connects fragmented records, retrieves visually similar candidates locally,
            combines multiple pieces of evidence, explains why candidates are ranked, and updates those rankings as new evidence arrives.
            The core system runs without internet, handles incomplete information, and is built to accept new evidence sources.
            Final identification always rests with an authorized investigator.</p>
        </section>
      </div>
    </div>`;
});

/* ---------------- cases list */
route("/cases", async (view, p, q, alive) => {
  const cases = await refreshCases();
  if (!alive()) return;
  view.innerHTML = `
    <div class="page-head"><div><h1>Missing cases</h1><p>${cases.length} cases on this device.</p></div>
      <a class="btn primary" href="#/cases/new">${icon("plus")} Report missing person</a></div>
    <section class="panel table-wrap">
      <table class="t"><thead><tr><th></th><th>Case</th><th>Name</th><th>Last seen</th><th>Status</th><th>Evidence</th><th>Top candidate</th></tr></thead>
      <tbody>${cases.map((c) => `<tr class="click" data-href="#/cases/${encodeURIComponent(c.id)}">
        <td>${c.photo_url ? `<img class="thumb" src="${bust(c.photo_url)}" alt="">` : `<div class="thumb none">No photo</div>`}</td>
        <td class="id">${esc(c.id)} ${syncChip(c.sync_status)}</td>
        <td>${esc(c.name || "Unnamed")}<div class="small muted">${ageText(c)} · ${esc(c.gender || "gender unknown")}</div></td>
        <td>${esc(c.last_seen_locality || "Unknown place")}<div class="small muted">${fmtDT(c.last_seen_datetime)}</div></td>
        <td><span class="chip status-${esc(c.status)}">${esc(c.status.replace("_", " "))}</span></td>
        <td>${c.evidence_count}</td>
        <td>${c.top_candidate ? `<span class="id">${esc(c.top_candidate.record_id)}</span> ${bandChip(c.top_candidate.band)}
          <div class="small muted">${pct(c.top_candidate.score)} · ${c.top_candidate.coverage} factors</div>` : `<span class="muted small">Not matched yet</span>`}</td>
      </tr>`).join("")}</tbody></table>
    </section>`;
  $$("tr[data-href]", view).forEach((tr) => tr.addEventListener("click", () => go(tr.dataset.href)));
});

/* ---------------- create case */
route("/cases/new", async (view) => {
  view.innerHTML = `
    <div class="page-head"><div><div class="crumb"><a href="#/cases">Missing cases</a></div><h1>Report a missing person</h1>
      <p>Every field is optional, but give at least a photo, a name or a clothing description. Missing details are excluded from scoring, never counted against a candidate.</p></div></div>
    <div class="grid g-main">
      <form class="panel" id="caseForm">
        <div class="fields">
          <label class="field"><span>Name</span><input name="name" autocomplete="off"></label>
          <label class="field"><span>Reporting organisation</span><select name="reporting_org_id">${orgOptions(null, ["police", "investigator", "ngo", "public"])}</select></label>
          <label class="field"><span>Age</span><input name="age" type="number" min="0" max="110"><span class="hint">Or leave blank and give a range below.</span></label>
          <label class="field"><span>Age range</span><div class="row"><input name="age_min" type="number" min="0" max="110" placeholder="min" style="width:48%"><input name="age_max" type="number" min="0" max="110" placeholder="max" style="width:48%"></div></label>
          <label class="field"><span>Gender</span><select name="gender"><option value="">Unknown</option><option>Male</option><option>Female</option><option>Other</option></select></label>
          <label class="field"><span>Last seen at</span><input name="last_seen_locality" list="localities" placeholder="e.g. Anna Nagar">${localityOptions()}</label>
          <label class="field"><span>Last seen date and time</span><input name="last_seen_datetime" type="datetime-local"></label>
          <label class="field"><span>Occupation</span><input name="occupation"></label>
          <label class="field full"><span>Clothing when last seen</span><input name="clothing_text" placeholder="e.g. blue shirt, black trousers"></label>
          <label class="field full"><span>Description</span><textarea name="description" placeholder="Build, marks, belongings, circumstances"></textarea></label>
        </div>
        <div class="row" style="margin-top:16px"><button class="btn primary big" id="createBtn">${icon("check")} Create case and find potential matches</button></div>
        <div id="createOut"></div>
      </form>
      <aside class="panel"><h3>Photo of the missing person</h3>
        <p class="small muted">A recent full-body photo gives the best visual comparison. Blurry or dark photos are accepted with reduced weight.</p>
        <div id="casePhoto"></div></aside>
    </div>`;
  const picker = photoPicker($("#casePhoto", view), { label: "Reference photo" });
  $("#caseForm", view).addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    [...fd.keys()].forEach((k) => { if (fd.get(k) === "") fd.delete(k); });
    if (picker.get()) fd.append("photo", picker.get(), "photo.jpg");
    const out = $("#createOut", view);
    const btn = $("#createBtn", view); btn.disabled = true;
    try {
      const created = await api("/cases", { method: "POST", form: fd });
      const cid = created.case.id;
      out.innerHTML = `<div class="note" style="margin-top:14px"><b>${esc(created.message)}</b> Case <span class="id">${esc(cid)}</span> created.
        ${created.warnings.length ? `<div class="warnings" style="margin-top:8px">${created.warnings.map(esc).join("<br>")}</div>` : ""}<div id="phaseBox"></div></div>`;
      const res = await withPhases($("#phaseBox", out), ["Generating visual representation…", "Searching local index…", "Combining available evidence…", "Ranking candidates…"],
        api(`/match/${encodeURIComponent(cid)}`, { method: "POST" }));
      ML.state.lastResults[cid] = res;
      await refreshCases();
      go(`#/cases/${encodeURIComponent(cid)}`);
    } catch (err) { btn.disabled = false; }
  });
});

/* ---------------- found records */
route("/records", async (view, p, q, alive) => {
  const recs = await api("/records");
  if (!alive()) return;
  view.innerHTML = `
    <div class="page-head"><div><h1>Found records</h1><p>${recs.length} records from hospitals, shelters, police and NGO teams.</p></div>
      <a class="btn primary" href="#/records/new">${icon("plus")} Add found record</a></div>
    <section class="panel table-wrap"><table class="t"><thead><tr><th></th><th>Record</th><th>Type and source</th><th>Where and when</th><th>Person</th><th>Photo quality</th></tr></thead>
    <tbody>${recs.map((r) => `<tr>
      <td>${r.photo_url ? `<img class="thumb" src="${bust(r.photo_url)}" alt="">` : `<div class="thumb none">No photo</div>`}</td>
      <td class="id">${esc(r.id)} ${syncChip(r.sync_status)}</td>
      <td>${esc(RECORD_TYPES[r.record_type] || r.record_type)}<div class="small muted">${esc(r.source_org || "Unknown source")}</div></td>
      <td>${esc(r.locality || "Unknown")}${r.care_location_detail ? `<div class="small">${esc(r.care_location_detail)}</div>` : (ML.state.role === "volunteer" ? `<div class="small masked">Care location hidden for this role</div>` : "")}
        <div class="small muted">${fmtDT(r.found_datetime)}</div></td>
      <td>${ageText(r)} · ${esc(r.gender || "gender unknown")}<div class="small muted">${esc(r.clothing_text || "")}</div></td>
      <td>${r.photo_quality ? `<span class="chip ${r.photo_quality === "good" ? "neutral" : "verify"}">${esc(r.photo_quality)}</span>` : "—"}
        ${(r.photo_warnings || []).length ? `<div class="small muted">${esc(r.photo_warnings.join(" "))}</div>` : ""}</td></tr>`).join("")}</tbody></table></section>`;
});

route("/records/new", async (view) => {
  view.innerHTML = `
    <div class="page-head"><div><div class="crumb"><a href="#/records">Found records</a></div><h1>Add a found record</h1>
      <p>Hospitals, shelters and field teams can enter what they already know. Records with only a few fields are still searchable.</p></div></div>
    <div class="grid g-main">
      <form class="panel" id="recForm"><div class="fields">
        <label class="field"><span>Record type</span><select name="record_type"><option value="found">Found person</option><option value="unidentified_patient">Unidentified patient</option>
          <option value="shelter_resident">Shelter resident</option><option value="sighting">Sighting</option></select></label>
        <label class="field"><span>Source organisation</span><select name="source_org_id">${orgOptions()}</select></label>
        <label class="field"><span>Age (approx.)</span><input name="age" type="number" min="0" max="110"></label>
        <label class="field"><span>Gender</span><select name="gender"><option value="">Unknown</option><option>Male</option><option>Female</option><option>Other</option></select></label>
        <label class="field"><span>Found at</span><input name="locality" list="localities">${localityOptions()}</label>
        <label class="field"><span>Found date and time</span><input name="found_datetime" type="datetime-local"></label>
        <label class="field full"><span>Clothing</span><input name="clothing_text"></label>
        <label class="field full"><span>Exact care location (restricted)</span><input name="care_location_detail" placeholder="Ward / bed / shelter hall"><span class="hint">Hidden from field volunteers.</span></label>
        <label class="field full"><span>Description</span><textarea name="description"></textarea></label>
      </div><div class="row" style="margin-top:14px"><button class="btn primary">${icon("check")} Save record</button></div><div id="recOut"></div></form>
      <aside class="panel"><h3>Photo</h3><div id="recPhoto"></div></aside>
    </div>`;
  const picker = photoPicker($("#recPhoto", view), { label: "Photo of the found person" });
  $("#recForm", view).addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    [...fd.keys()].forEach((k) => { if (fd.get(k) === "") fd.delete(k); });
    if (picker.get()) fd.append("photo", picker.get(), "photo.jpg");
    try {
      const r = await api("/records", { method: "POST", form: fd });
      $("#recOut", view).innerHTML = `<div class="note" style="margin-top:12px"><b>${esc(r.message)}</b> Saved as <span class="id">${esc(r.record.id)}</span> ${syncChip(r.record.sync_status)}
        ${r.warnings.length ? `<div class="warnings" style="margin-top:8px">${r.warnings.map(esc).join("<br>")}</div>` : ""}
        <p class="small" style="margin-top:6px">Re-run matching on a case to include this record.</p></div>`;
      toast(`Record ${r.record.id} saved.`);
      e.target.reset(); picker.set(null);
    } catch (err) { /* toast */ }
  });
});
