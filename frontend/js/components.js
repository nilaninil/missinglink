/* Reusable UI pieces: evidence dial, candidate card, factor breakdown, timeline, charts, modals. */
"use strict";

const FACTOR_COLORS = {
  photo: "#0d7a70", age: "#3b5bb5", gender: "#7a5bb5", clothing: "#c07a12", location: "#2f8f4e",
  time: "#8a5a44", corroboration: "#1a4f6e", occupation: "#6b7785",
  appearance: "#0d7a70", upper: "#c07a12", lower: "#3b5bb5", face_head: "#7a5bb5", silhouette: "#2f8f4e",
};

/* Segmented evidence dial: each coloured arc is one factor's share of the combined score. */
function dial(score, factors, { size = "", label = "evidence score" } = {}) {
  const R = 44, C = 2 * Math.PI * R;
  const avail = (factors || []).filter((f) => f.status !== "unavailable" && f.score != null);
  const wsum = avail.reduce((a, f) => a + (f.effective_weight ?? f.weight ?? 0), 0) || 1;
  let offset = 0;
  const shown = Math.min(score ?? 0, 0.99);
  let arcs = "";
  if (avail.length) {
    const raw = avail.map((f) => (f.score * (f.effective_weight ?? f.weight)) / wsum);
    const tot = raw.reduce((a, b) => a + b, 0) || 1;
    raw.forEach((v, i) => {
      const len = (v / tot) * shown * C;
      if (len <= 0.5) return;
      const f = avail[i];
      arcs += `<circle cx="50" cy="50" r="${R}" fill="none" stroke="${FACTOR_COLORS[f.name] || "#0d7a70"}" stroke-width="9"
        stroke-dasharray="${Math.max(0, len - 1.2)} ${C}" stroke-dashoffset="${-offset}"><title>${esc(f.label || f.name)}: ${pct(f.score)}</title></circle>`;
      offset += len;
    });
  } else {
    arcs = `<circle cx="50" cy="50" r="${R}" fill="none" stroke="#0d7a70" stroke-width="9" stroke-dasharray="${shown * C} ${C}"/>`;
  }
  return `<div class="dial ${size}" role="img" aria-label="${pct(score)} ${esc(label)}">
    <svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="${R}" fill="none" stroke="#e5eaee" stroke-width="9"/>${arcs}</svg>
    <div class="val"><div><b>${pct(score)}</b><small>${esc(label)}</small></div></div></div>`;
}

function miniFactors(factors) {
  return `<div class="mini-factors">${factors.map((f) => {
    const w = f.status === "available" ? Math.round((f.score || 0) * 100) : 0;
    const val = f.status === "unavailable" ? "n/a" : f.status === "conflict" ? "conflict" : pct(f.score, 1);
    return `<div class="mf ${f.status}" title="${esc(f.reason)}">${esc(f.label)} <b>${val}</b><div class="bar"><i style="width:${w}%"></i></div></div>`;
  }).join("")}</div>`;
}

function rankDelta(c) {
  if (c.previous_rank == null || c.previous_rank === c.rank) return c.previous_rank == null ? "" : `<small class="down">no change</small>`;
  const up = c.previous_rank > c.rank;
  return `<small class="${up ? "up" : "down"}">${up ? "▲" : "▼"} was #${c.previous_rank}</small>`;
}

function candidateCard(c, caseId) {
  const r = c.record;
  const img = r.photo_url
    ? `<img class="pic" src="${bust(r.photo_url)}" alt="Photo on record ${esc(r.id)}">`
    : `<div class="pic none">No photo on record</div>`;
  const warn = (c.warnings || []).length ? `<div class="line" style="color:var(--amber)">⚠ ${esc(c.warnings.join(" "))}</div>` : "";
  const conflicts = (c.conflicts_list || []).length ? `<div class="line" style="color:var(--red)">Conflict: ${esc(c.conflicts_list.join(", "))}</div>` : "";
  return `<article class="cand ${c.rank === 1 ? "top" : ""} ${c.critical_conflict ? "conflicted" : ""}" data-record="${esc(r.id)}">
    <div class="rank">#${c.rank}${rankDelta(c)}</div>
    ${img}
    <div class="meta">
      <h3><span class="id">${esc(r.id)}</span> ${bandChip(c.band, c.band_text)} ${syncChip(r.sync_status)}</h3>
      <div class="line">${esc(RECORD_TYPES[r.record_type] || r.record_type)} · ${esc(r.source_org || "Unknown source")}</div>
      <div class="line">${esc(r.locality || "Locality unknown")}, ${fmtDT(r.found_datetime)} · ${ageText(r)} · ${esc(r.gender || "Gender unknown")}</div>
      <div class="line">${esc(r.clothing_text || "No clothing description")}</div>
      ${conflicts}${warn}
      ${miniFactors(c.factors)}
      <div class="coverage">${esc(c.coverage_text)} · ${esc(c.status_text)}</div>
    </div>
    <div class="side">
      ${dial(c.overall_score, c.factors)}
      <div class="btns">
        <a class="btn sm primary" href="#/cases/${encodeURIComponent(caseId)}/candidate/${encodeURIComponent(r.id)}">${icon("eye")} View evidence</a>
        <button class="btn sm" data-act="evidence" data-record="${esc(r.id)}">${icon("plus")} Add evidence</button>
        <button class="btn sm warn" data-act="flag" data-record="${esc(r.id)}">${icon("flag")} Mark for review</button>
      </div>
    </div>
  </article>`;
}

function factorBreakdown(factors) {
  return `<div class="factors">${factors.map((f) => {
    const w = f.status === "unavailable" ? 0 : f.status === "conflict" ? 100 : Math.round((f.score || 0) * 100);
    const val = f.status === "unavailable" ? "n/a" : f.status === "conflict" ? "0%" : pct(f.score, 1);
    const reason = f.status === "unavailable" ? `Evidence unavailable — excluded from this score. ${f.reason || ""}` : f.reason;
    const wtxt = f.status === "unavailable" ? "excluded" : `weight ${Number(f.effective_weight ?? f.weight).toFixed(2)}`;
    return `<div class="factor ${f.status}">
      <div class="name">${esc(f.label)}<small>${wtxt}</small></div>
      <div class="track"><i style="width:${w}%"></i></div>
      <div class="pct">${val}</div>
      <div class="why">${esc(reason)}</div></div>`;
  }).join("")}</div>`;
}

function whyList(reasons) {
  const ic = { support: "✓", weak: "~", conflict: "⚠", missing: "○", warning: "⚠", enrich: "+" };
  return `<ul class="why-list">${(reasons || []).map((r) =>
    `<li class="${esc(r.kind)}"><span class="ic">${ic[r.kind] || "•"}</span><span>${esc(r.text)}</span></li>`).join("")}</ul>`;
}

const TL_ICON = { report: "person", rank_update: "rank", ranking: "rank", hospital_record: "hospital", body_scan: "scan",
  cctv_sighting: "cctv", ocr_document: "doc", shelter_record: "records", investigator_note: "doc", review: "flag", sync: "sync" };
function timelineList(events) {
  if (!events || !events.length) return `<div class="empty small">No events yet.</div>`;
  return `<ol class="tl">${events.map((e) => {
    const t = e.event_type && e.event_type.includes("rank") ? "rank" : e.event_type;
    return `<li class="t-${esc(t)}"><span class="dot">${icon(TL_ICON[e.event_type] || (t === "rank" ? "rank" : "timeline"))}</span>
      <div><div class="when">${fmtDT(e.occurred_at)}</div><div class="what">${esc(e.title)}</div>
      ${e.detail ? `<div class="detail">${esc(e.detail)}</div>` : ""}
      <div class="where">${[e.locality, e.org].filter(Boolean).map(esc).join(" · ")}</div></div></li>`;
  }).join("")}</ol>`;
}

function rerankBanner(res) {
  if (!res || !res.rank_changes || !res.rank_changes.length) {
    if (res && res.explanation) return `<div class="rerank"><span>${icon("rank")}</span><div><h3>Ranking updated</h3><p>${esc(res.explanation)}</p></div></div>`;
    return "";
  }
  const moves = res.rank_changes.slice(0, 6).map((m) => {
    const up = m.old_rank == null || m.new_rank < m.old_rank;
    const from = m.old_rank == null ? "new" : "#" + m.old_rank;
    return `<span class="move"><b class="id">${esc(m.record_id)}</b> ${from} → <span class="${up ? "up" : "down"}">#${m.new_rank}</span></span>`;
  }).join("");
  return `<div class="rerank" role="status"><span style="color:var(--teal)">${icon("rank")}</span><div>
    <h3>Ranking updated — ${esc(res.trigger || "new evidence")}</h3>
    ${res.explanation ? `<p>${esc(res.explanation)}</p>` : ""}
    <div class="moves">${moves}</div></div></div>`;
}

function retrievalBox(res) {
  if (!res || !res.retrieval) return "";
  const r = res.retrieval;
  const t = res.timings_ms || {};
  const funnel = r.mode === "faiss"
    ? `<div class="funnel"><b>${r.total_records}</b><i>records</i> → <b>${r.visual_count + (r.attribute_count || 0)}</b><i>compared in detail</i></div>`
    : `<div class="funnel"><b>${r.total_records}</b><i>records</i> → <b>${r.attribute_count ?? "?"}</b><i>after attribute filters</i></div>`;
  return `<div class="retrieval">${funnel}
    <p><b>${esc(r.text)}</b><br>${esc(res.retrieval_note || "")}
    ${t.total != null ? `<br><span class="muted">Search took ${t.search} ms; full ranking ${t.total} ms on this device · ${esc(res.encoder || "")}</span>` : ""}</p></div>`;
}

/* Rank-over-runs line chart (simple SVG). */
function historyChart(history, highlight = []) {
  if (!history || history.length < 1) return `<div class="empty small">Run matching to build ranking history.</div>`;
  const last = history[history.length - 1];
  const ids = Object.entries(last.ranks).sort((a, b) => a[1] - b[1]).slice(0, 5).map((x) => x[0]);
  highlight.forEach((id) => { if (!ids.includes(id)) ids.push(id); });
  const W = 560, H = 200, pl = 36, pr = 80, pt = 14, pb = 34;
  const maxRank = Math.max(5, ...history.flatMap((r) => ids.map((id) => r.ranks[id] || 0)));
  const n = history.length;
  const x = (i) => pl + (n === 1 ? (W - pl - pr) / 2 : (i * (W - pl - pr)) / (n - 1));
  const y = (rk) => pt + ((rk - 1) * (H - pt - pb)) / Math.max(1, maxRank - 1);
  const palette = ["#0d7a70", "#c07a12", "#3b5bb5", "#7a5bb5", "#8a5a44", "#2f8f4e", "#b3261e"];
  let grid = "";
  for (let k = 1; k <= maxRank; k++) grid += `<line x1="${pl}" x2="${W - pr}" y1="${y(k)}" y2="${y(k)}" stroke="#eef1f4"/><text x="${pl - 8}" y="${y(k) + 4}" text-anchor="end">#${k}</text>`;
  history.forEach((r, i) => { grid += `<text x="${x(i)}" y="${H - 12}" text-anchor="middle">Run ${r.run_id}</text>`; });
  const lines = ids.map((id, j) => {
    const pts = history.map((r, i) => (r.ranks[id] ? [x(i), y(r.ranks[id])] : null)).filter(Boolean);
    if (!pts.length) return "";
    const col = palette[j % palette.length];
    const lastPt = pts[pts.length - 1];
    return `<polyline fill="none" stroke="${col}" stroke-width="2.5" points="${pts.map((p) => p.join(",")).join(" ")}"/>
      ${pts.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="#fff" stroke="${col}" stroke-width="2"/>`).join("")}
      <text x="${lastPt[0] + 10}" y="${lastPt[1] + 4}" style="fill:${col};font-weight:600">${esc(id)}</text>`;
  }).join("");
  const triggers = history.map((r) => `Run ${r.run_id}: ${esc(r.trigger || "")}`).join(" · ");
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Rank of top candidates across matching runs">${grid}${lines}</svg>
    <div class="small muted">${triggers}</div></div>`;
}

/* ---------- modals */
function openModal(title, bodyHtml, footHtml = "", { wide = false } = {}) {
  const root = $("#modalRoot");
  root.innerHTML = `<div class="modal-back"><div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}" style="${wide ? "width:min(980px,100%)" : ""}">
    <div class="modal-head"><h2>${esc(title)}</h2><button class="btn sm" data-close aria-label="Close">${icon("x")}</button></div>
    <div class="modal-body">${bodyHtml}</div>${footHtml ? `<div class="modal-foot">${footHtml}</div>` : ""}</div></div>`;
  const back = root.firstElementChild;
  const close = () => { root.dispatchEvent(new Event("modalclose")); root.innerHTML = ""; document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  $$("[data-close]", back).forEach((b) => b.addEventListener("click", close));
  back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
  setTimeout(() => { const f = $("input,select,textarea,button:not([data-close])", back); if (f) f.focus(); }, 30);
  return { el: back, close };
}

function localityOptions() {
  return `<datalist id="localities">${ML.state.localities.map((l) => `<option value="${esc(l)}">`).join("")}</datalist>`;
}

function caseOptions(selected) {
  return ML.state.cases.map((c) => `<option value="${esc(c.id)}" ${c.id === selected ? "selected" : ""}>${esc(c.id)} — ${esc(c.name || "Unnamed")}</option>`).join("");
}

function orgOptions(selected, types) {
  return `<option value="">Unknown / not listed</option>` + ML.state.orgs.filter((o) => !types || types.includes(o.type))
    .map((o) => `<option value="${o.id}" ${String(o.id) === String(selected) ? "selected" : ""}>${esc(o.name)}</option>`).join("");
}

/* Evidence form modal: manual evidence. Resolves with the new match payload. */
function evidenceModal(caseId, linkedRecordId) {
  return new Promise((resolve) => {
    const m = openModal("Add evidence", `
      <form id="evForm"><div class="fields">
        <label class="field"><span>Evidence type</span><select name="evidence_type">
          <option value="investigator_note">Investigator note</option><option value="hospital_record">Hospital record</option>
          <option value="shelter_record">Shelter record</option><option value="cctv_sighting">CCTV sighting (manual)</option></select></label>
        <label class="field"><span>Source organisation</span><select name="source_org_id">${orgOptions()}</select></label>
        <label class="field"><span>Observed at (locality)</span><input name="locality" list="localities" placeholder="e.g. Kilpauk">${localityOptions()}</label>
        <label class="field"><span>Observed date and time</span><input name="observed_datetime" type="datetime-local"></label>
        <label class="field"><span>Age (approx.)</span><input name="age" type="number" min="0" max="110"></label>
        <label class="field"><span>Gender</span><select name="gender"><option value="">Unknown</option><option>Male</option><option>Female</option><option>Other</option></select></label>
        <label class="field full"><span>Clothing</span><input name="clothing_text" placeholder="e.g. blue shirt, dark trousers"></label>
        <label class="field full"><span>Links to found record (optional)</span><input name="linked_record_id" value="${esc(linkedRecordId || "")}" placeholder="e.g. FR-0003">
          <span class="hint">Linking evidence to a record makes the corroboration factor available for that candidate.</span></label>
        <label class="field full"><span>Notes</span><textarea name="notes"></textarea></label>
      </div></form>`,
      `<button class="btn" data-close>Cancel</button><button class="btn primary" id="evSave">${icon("plus")} Add evidence and re-rank</button>`);
    m.el.addEventListener("click", async (e) => {
      if (!e.target.closest("#evSave")) return;
      const fd = Object.fromEntries(new FormData($("#evForm", m.el)));
      Object.keys(fd).forEach((k) => { if (fd[k] === "") delete fd[k]; });
      const btn = $("#evSave", m.el); btn.disabled = true; btn.textContent = "Re-ranking…";
      try {
        const res = await api(`/cases/${encodeURIComponent(caseId)}/evidence`, { method: "POST", json: fd });
        ML.state.lastResults[caseId] = res;
        m.close();
        toast("Evidence added. Ranking recomputed.");
        resolve(res);
      } catch (err) { btn.disabled = false; btn.textContent = "Add evidence and re-rank"; }
    });
    $("#modalRoot").addEventListener("modalclose", () => resolve(null), { once: true });
  });
}

function reviewModal(caseId, recordId, preset = "needs_review") {
  return new Promise((resolve) => {
    const m = openModal(`Review decision — ${recordId}`, `
      <p class="muted">Recording a decision does not identify anyone. It logs the investigator's review step on the evidence timeline.</p>
      <div class="fields" style="display:grid;gap:12px">
        <label class="field"><span>Decision</span><select id="rvDecision">
          <option value="needs_review" ${preset === "needs_review" ? "selected" : ""}>Mark for human review</option>
          <option value="more_information" ${preset === "more_information" ? "selected" : ""}>Request more information</option>
          <option value="verified_by_investigator" ${preset === "verified_by_investigator" ? "selected" : ""}>Investigator has verified in person with partner</option>
          <option value="rejected" ${preset === "rejected" ? "selected" : ""}>Reject — not the missing person</option></select></label>
        <label class="field"><span>Note</span><textarea id="rvNote" placeholder="What was checked, with whom"></textarea></label>
      </div>`, `<button class="btn" data-close>Cancel</button><button class="btn primary" id="rvSave">Save decision</button>`);
    m.el.addEventListener("click", async (e) => {
      if (!e.target.closest("#rvSave")) return;
      try {
        const r = await api("/review/flag", { method: "POST", json: { case_id: caseId, record_id: recordId, decision: $("#rvDecision", m.el).value,
          note: $("#rvNote", m.el).value, role: ML.state.role } });
        m.close(); toast("Review decision logged on the timeline."); resolve(r);
      } catch (err) { /* toast shown */ }
    });
    $("#modalRoot").addEventListener("modalclose", () => resolve(null), { once: true });
  });
}

/* Staged loading driven by real backend phases (the request runs while phases advance; the list settles when it returns). */
async function withPhases(container, phases, promise) {
  container.innerHTML = `<ul class="phases">${phases.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
  const lis = $$("li", container);
  let i = 0, done = false;
  promise.finally(() => { done = true; });
  while (!done && i < lis.length - 1) {
    lis[i].className = "doing";
    await sleep(380);
    if (!done) { lis[i].className = "done"; i++; }
  }
  lis.forEach((li, k) => { if (k >= i) li.className = "doing"; });
  try { const r = await promise; lis.forEach((li) => (li.className = "done")); return r; }
  catch (e) { container.innerHTML = ""; throw e; }
}

/* Attach a photo input with preview + optional camera button. Returns getter for the current Blob. */
function photoPicker(root, { label = "Photo", allowCamera = true, onChange = null } = {}) {
  let blob = null;
  root.innerHTML = `<div class="dropzone" tabindex="0">
      <div class="pp-empty scan-cta"><p class="muted">${esc(label)}: drop an image here, or</p>
        <div class="row" style="justify-content:center">
          <label class="btn">${icon("upload")} Choose file<input type="file" accept="image/png,image/jpeg,image/webp" hidden></label>
          ${allowCamera ? `<button type="button" class="btn dark" data-cam>${icon("camera")} Use camera</button>` : ""}
        </div><p class="small muted">JPG, PNG or WebP, up to 10 MB.</p></div>
      <div class="pp-full" hidden><img class="preview" alt="Selected photo preview"><div class="row" style="justify-content:center;margin-top:8px">
        <button type="button" class="btn sm" data-clear>${icon("x")} Remove</button></div></div></div>`;
  const dz = $(".dropzone", root);
  const set = (b) => {
    blob = b;
    $(".pp-empty", root).hidden = !!b; $(".pp-full", root).hidden = !b;
    if (b) $(".preview", root).src = URL.createObjectURL(b);
    if (onChange) onChange(b);
  };
  $("input[type=file]", root).addEventListener("change", (e) => { if (e.target.files[0]) set(e.target.files[0]); });
  const cam = $("[data-cam]", root);
  if (cam) cam.addEventListener("click", async () => { const b = await Camera.capture({ title: "Take a photo", guide: false }); if (b) set(b); });
  $("[data-clear]", root).addEventListener("click", () => set(null));
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); const f = e.dataTransfer.files[0]; if (f) set(f); });
  return { get: () => blob, set };
}

/* ---------- Local Auth / Sign-In / Sign-Up Modal */
function authModal(initialMode = "signin") {
  return new Promise((resolve) => {
    let mode = initialMode;
    const currentSession = getActiveSession();

    const renderBody = () => `
      <div class="auth-container" style="display:flex;flex-direction:column;gap:14px;">
        <div class="auth-tabs" style="display:flex;border-bottom:1px solid var(--line);margin-bottom:6px;">
          <button type="button" class="btn sm tab-btn ${mode === "signin" ? "active primary" : ""}" id="tabSignIn" style="flex:1;justify-content:center;border-bottom:2px solid ${mode === "signin" ? "var(--teal)" : "transparent"};">Sign In</button>
          <button type="button" class="btn sm tab-btn ${mode === "signup" ? "active primary" : ""}" id="tabSignUp" style="flex:1;justify-content:center;border-bottom:2px solid ${mode === "signup" ? "var(--teal)" : "transparent"};">Sign Up</button>
        </div>

        <form id="authForm" style="display:flex;flex-direction:column;gap:12px;">
          <div class="field" id="nameField" style="${mode === "signin" ? "display:none;" : ""}">
            <span>Full Name / Call Sign</span>
            <input type="text" id="authName" name="name" placeholder="e.g. Officer Sharma" value="${esc(mode === "signup" ? "" : (currentSession ? currentSession.name : ""))}">
          </div>

          <div class="field">
            <span>Email Address</span>
            <input type="email" id="authEmail" name="email" required placeholder="investigator@agency.gov" value="${esc(currentSession ? currentSession.email : "")}">
          </div>

          <div class="field">
            <span>Password</span>
            <input type="password" id="authPassword" name="password" placeholder="••••••••">
          </div>

          <div class="field">
            <span>Role</span>
            <select id="authRole" name="role">
              <option value="Investigator" ${currentSession && currentSession.role === "Investigator" ? "selected" : ""}>Investigator (Full decision support & match access)</option>
              <option value="Field Officer" ${currentSession && currentSession.role === "Field Officer" ? "selected" : ""}>Field Officer (Field scans & triage view)</option>
            </select>
          </div>

          <div class="auth-error" id="authError" style="color:var(--red);font-size:0.86rem;display:none;"></div>
        </form>

        ${currentSession ? `
          <div style="border-top:1px dashed var(--line);padding-top:10px;display:flex;justify-content:space-between;align-items:center;">
            <span class="small muted">Active: <b>${esc(currentSession.name)}</b> (${esc(currentSession.role)})</span>
            <button type="button" class="btn sm danger" id="authSignOut">Sign Out</button>
          </div>
        ` : ""}
      </div>
    `;

    const m = openModal(
      mode === "signin" ? "Sign In — Investigator Session" : "Create Investigator Account",
      renderBody(),
      `<button class="btn" data-close>Cancel</button>
       <button class="btn primary" id="authSubmit">${mode === "signin" ? "Sign In" : "Create Account"}</button>`
    );

    const updateForm = () => {
      $(".modal-head h2", m.el).textContent = mode === "signin" ? "Sign In — Investigator Session" : "Create Investigator Account";
      $(".modal-body", m.el).innerHTML = renderBody();
      $("#authSubmit", m.el).textContent = mode === "signin" ? "Sign In" : "Create Account";
      attachEvents();
    };

    const attachEvents = () => {
      const tIn = $("#tabSignIn", m.el);
      const tUp = $("#tabSignUp", m.el);
      if (tIn) tIn.addEventListener("click", () => { mode = "signin"; updateForm(); });
      if (tUp) tUp.addEventListener("click", () => { mode = "signup"; updateForm(); });

      const so = $("#authSignOut", m.el);
      if (so) {
        so.addEventListener("click", () => {
          clearSession();
          toast("Signed out.");
          m.close();
          renderRoute();
          resolve(null);
        });
      }
    };

    attachEvents();

    m.el.addEventListener("click", (e) => {
      if (!e.target.closest("#authSubmit")) return;
      const email = ($("#authEmail", m.el).value || "").trim();
      const role = $("#authRole", m.el).value || "Investigator";
      let name = ($("#authName", m.el) ? $("#authName", m.el).value : "").trim();

      if (!email) {
        const err = $("#authError", m.el);
        if (err) {
          err.textContent = "Please enter an email address.";
          err.style.display = "block";
        }
        return;
      }

      if (mode === "signup" && !name) {
        name = email.split("@")[0];
      } else if (!name) {
        name = currentSession ? currentSession.name : email.split("@")[0];
      }

      const session = {
        name: name || "Investigator",
        email: email,
        role: role,
        signedInAt: new Date().toISOString()
      };

      setActiveSession(session);
      m.close();
      toast(`Signed in as ${session.name} (${session.role})`);
      renderRoute();
      resolve(session);
    });

    $("#modalRoot").addEventListener("modalclose", () => resolve(null), { once: true });
  });
}

