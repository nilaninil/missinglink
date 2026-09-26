/* Guided demo: each step calls a real backend step and waits for it. */
"use strict";

const DEMO_STEPS = [
  { t: "Load the missing-person case", d: "Reset the synthetic scenario and open MC-2026-0001, Aarav Kumar, 22, last seen in Anna Nagar at 18:30 in a blue shirt and black trousers." },
  { t: "Local visual matching", d: "The case photo is embedded on this device and FAISS retrieves visually similar found records first." },
  { t: "Ranked candidates", d: "Every retrieved record is scored on photo, age, gender, clothing, location, time and corroboration." },
  { t: "Why this match?", d: "Open the evidence breakdown for the current #1 candidate." },
  { t: "Read a scanned ambulance log", d: "OCR runs locally on the Kilpauk hospital ambulance log." },
  { t: "Attach it and re-rank", d: "The log becomes evidence. The working profile updates and every candidate is re-scored." },
  { t: "Check CCTV", d: "The Anna Nagar checkpoint clip is scanned for people resembling the case photo." },
  { t: "Field body-scan at the hospital", d: "A volunteer's camera capture in the Kilpauk ward is compared with the missing person's photo, then linked to the hospital record." },
  { t: "Timeline and ranking history", d: "Review everything that happened and how the ranking moved." },
];

function demoOut(n, r) {
  const top3 = (res) => res.candidates.slice(0, 3).map((c) => `<span class="move"><b class="id">${esc(c.record_id)}</b> #${c.rank} · ${pct(c.overall_score)}</span>`).join(" ");
  switch (n) {
    case 1: return `<div class="row"><img src="${bust(r.case.photo_url)}" alt="" style="height:120px;border-radius:3px"><div>
      <b>${esc(r.case.name)}</b> <span class="id">${esc(r.case.id)}</span><br>${ageText(r.case)}, ${esc(r.case.gender)} · ${esc(r.case.clothing_text)}<br>
      Last seen ${esc(r.case.last_seen_locality)}, ${fmtDT(r.case.last_seen_datetime)}</div></div>`;
    case 2: return `<p><b>${esc(r.retrieval.text)}</b></p><p class="small muted">${esc(r.note)} Search took ${r.timings_ms.search} ms; full ranking ${r.timings_ms.total} ms on this device.</p>`;
    case 3: return `<div class="moves row">${top3(r.result)}</div><p class="small muted">Initial order comes from the evidence available so far. The hospital patient's photo is low-light and their age is unknown, so their score is limited.</p>`;
    case 4: return `<div class="row" style="align-items:flex-start;flex-wrap:nowrap;gap:18px">${dial(r.candidate.overall_score, r.candidate.factors)}
      <div style="flex:1"><b class="id">${esc(r.candidate.record_id)}</b> ${bandChip(r.candidate.band, r.candidate.band_text)}${whyList(r.candidate.reasons.slice(0, 7))}</div></div>`;
    case 5: {
      const f = r.ocr.fields;
      return `<div class="row" style="align-items:flex-start;flex-wrap:nowrap;gap:16px"><img src="${bust(r.ocr.image_url)}" alt="" style="max-height:170px">
        <dl class="kv" style="flex:1">${Object.entries(f).map(([k, v]) => `<dt>${esc(OCR_LABELS[k] || k)}</dt><dd>${esc(v.value)} <span class="small muted">${pct(v.confidence, 1)}</span></dd>`).join("")}</dl></div>
        <p class="small muted">${esc(r.ocr.message || "")} Engine: ${esc(r.ocr.engine || "unavailable")}</p>`;
    }
    case 6: return rerankBanner(r.result) + `<div class="moves row">${top3(r.result)}</div>`;
    case 7: {
      const s = r.cctv.sightings;
      if (!s.length) return `<p>${esc(r.cctv.message || "No potential sightings.")}</p>`;
      const best = s.reduce((a, b) => (b.visual_similarity > a.visual_similarity ? b : a));
      return `<div class="row" style="align-items:flex-start"><img src="${bust(best.crop_url)}" alt="" style="height:130px"><div>
        <b>${esc(best.camera_name)}</b>, ${fmtDT(best.frame_datetime)}<br>Visual similarity ${pct(best.visual_similarity)}<br>
        <span class="chip verify">Potential Sighting — Requires Human Verification</span><br><span class="small muted">Added to the evidence timeline. ${s.length} sighting(s) in ${r.cctv.frames_analysed} frames.</span></div></div>
        ${r.result ? `<div class="moves row" style="margin-top:8px">${top3(r.result)}</div>` : ""}`;
    }
    case 8: return `<div class="row" style="align-items:center;flex-wrap:nowrap;gap:16px">
        <img src="${bust(r.scan.scan_url)}" alt="" style="height:150px;border-radius:3px">${dial(r.scan.overall_score, r.scan.components, { label: "visual agreement" })}
        <div style="flex:1">${bandChip(r.scan.band, r.scan.band_text)} <span class="chip verify">Requires Human Verification</span><p class="small" style="margin-top:6px">${esc(r.scan.summary)}</p></div></div>
        ${rerankBanner(r.result)}<div class="moves row">${top3(r.result)}</div>`;
    case 9: return `<div class="grid g2"><div>${historyChart(r.history, ["FR-0003"])}</div><div style="max-height:320px;overflow:auto">${timelineList(r.timeline)}</div></div>`;
    default: return "";
  }
}

route("/demo", async (view) => {
  let next = 1, busy = false;
  view.innerHTML = `
    <div class="page-head"><div><h1>Demo investigation</h1>
      <p>A guided walk through one case. Every step calls the real local services and waits for the result — nothing is pre-recorded.</p></div>
      <div class="row"><button class="btn primary" id="dNext">${icon("play")} Run step 1</button><button class="btn" id="dAll">Run all steps</button>
        <button class="btn warn" id="dOffline">Toggle offline and replay</button></div></div>
    <section class="panel"><ol class="steps">${DEMO_STEPS.map((s, i) => `<li class="step" id="st${i + 1}"><span class="n">${i + 1}</span>
      <div><h3>${esc(s.t)}</h3><p class="small muted" style="margin:2px 0 0">${esc(s.d)}</p><div class="out"></div></div><span class="state small muted"></span></li>`).join("")}</ol>
      <div class="row" style="margin-top:14px"><a class="btn" href="#/cases/MC-2026-0001?fresh=0">Open the case</a>
        <a class="btn dark" href="#/scan?case=MC-2026-0001">${icon("scan")} Try a live body scan yourself</a></div></section>`;

  const setBtn = () => { $("#dNext", view).innerHTML = next <= 9 ? `${icon("play")} Run step ${next}` : "Demo complete"; $("#dNext", view).disabled = next > 9 || busy; };
  async function run(n) {
    const li = $("#st" + n, view);
    li.className = "step running"; $(".state", li).textContent = "Running…";
    try {
      const r = await api(`/demo/step/${n}`, { method: "POST", timeout: 150000 });
      if (n === 1) { ML.bustKey = Date.now(); ML.state.lastResults = {}; $$(".step", view).forEach((x) => { if (x !== li) { x.className = "step"; $(".out", x).innerHTML = ""; $(".state", x).textContent = ""; } }); }
      if (r.result && r.result.candidates) ML.state.lastResults["MC-2026-0001"] = r.result;
      li.className = "step done"; $(".state", li).textContent = "Done";
      $(".out", li).innerHTML = demoOut(n, r);
      li.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return true;
    } catch (e) {
      li.className = "step failed"; $(".state", li).textContent = "Failed — try again";
      return false;
    }
  }
  const runNext = async () => { if (busy || next > 9) return; busy = true; setBtn(); const ok = await run(next); busy = false; if (ok) next++; setBtn(); };
  $("#dNext", view).addEventListener("click", runNext);
  $("#dAll", view).addEventListener("click", async () => {
    if (busy) return;
    if (next > 9) next = 1;
    busy = true; setBtn();
    while (next <= 9) { const ok = await run(next); if (!ok) break; next++; }
    busy = false; setBtn();
  });
  $("#dOffline", view).addEventListener("click", async () => {
    if (busy) return;
    await setOffline(true);
    toast("Offline mode on. Replaying steps 1–6 using only local services.", "warn");
    busy = true; next = 1; setBtn();
    for (let n = 1; n <= 6; n++) { const ok = await run(n); if (!ok) break; next = n + 1; }
    busy = false; setBtn();
  });
  setBtn();
});
