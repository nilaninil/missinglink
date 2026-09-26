/* Camera capture modal. Uses getUserMedia (needs http://localhost or HTTPS). Falls back to the
   device's native camera through <input type="file" capture="environment"> on phones. */
"use strict";

const Camera = (() => {
  let stream = null;
  let facing = "environment";

  function stop() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }

  function guideRect(vw, vh) {
    const portrait = vh > vw;
    const gw = portrait ? vw * 0.72 : vw * 0.42;
    const gh = portrait ? vh * 0.86 : vh * 0.92;
    return { x: (vw - gw) / 2, y: (vh - gh) / 2, w: gw, h: gh };
  }

  function guideSvg(vw, vh) {
    const g = guideRect(vw, vh);
    const cx = g.x + g.w / 2, s = g.h / 100;       // silhouette scaled to guide height
    const L = Math.min(g.w, g.h) * 0.12;
    const corner = (x, y, dx, dy) => `M${x + dx * L} ${y} L${x} ${y} L${x} ${y + dy * L}`;
    const body = `M${cx - 7 * s} ${g.y + 13 * s} a${7 * s} ${7.5 * s} 0 1 1 ${14 * s} 0 a${7 * s} ${7.5 * s} 0 1 1 ${-14 * s} 0
      M${cx - 17 * s} ${g.y + 25 * s} L${cx + 17 * s} ${g.y + 25 * s} L${cx + 21 * s} ${g.y + 55 * s} L${cx + 14 * s} ${g.y + 55 * s}
      L${cx + 12 * s} ${g.y + 97 * s} L${cx + 2 * s} ${g.y + 97 * s} L${cx} ${g.y + 62 * s} L${cx - 2 * s} ${g.y + 97 * s}
      L${cx - 12 * s} ${g.y + 97 * s} L${cx - 14 * s} ${g.y + 55 * s} L${cx - 21 * s} ${g.y + 55 * s} Z`;
    return `<svg class="guide" viewBox="0 0 ${vw} ${vh}" preserveAspectRatio="xMidYMid slice">
      <path d="M0 0H${vw}V${vh}H0Z M${g.x} ${g.y}v${g.h}h${g.w}v${-g.h}Z" fill="rgba(8,12,16,.45)" fill-rule="evenodd"/>
      <path d="${corner(g.x, g.y, 1, 1)} ${corner(g.x + g.w, g.y, -1, 1)} ${corner(g.x, g.y + g.h, 1, -1)} ${corner(g.x + g.w, g.y + g.h, -1, -1)}"
        stroke="#50c2b5" stroke-width="${Math.max(3, vw / 180)}" fill="none"/>
      <path d="${body}" stroke="rgba(255,255,255,.55)" stroke-width="${Math.max(2, vw / 320)}" stroke-dasharray="${vw / 80} ${vw / 120}" fill="none"/>
    </svg>`;
  }

  async function start(video) {
    stop();
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false, video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 960 } },
    });
    video.srcObject = stream;
    await video.play();
    await new Promise((r) => (video.videoWidth ? r() : video.addEventListener("loadedmetadata", r, { once: true })));
  }

  function grab(video, cropToGuide) {
    const vw = video.videoWidth, vh = video.videoHeight;
    let r = { x: 0, y: 0, w: vw, h: vh };
    if (cropToGuide) {
      const g = guideRect(vw, vh);
      const mx = g.w * 0.12, my = g.h * 0.04;       // small margin so arms/feet are not cut
      r = { x: Math.max(0, g.x - mx), y: Math.max(0, g.y - my), w: Math.min(vw, g.w + 2 * mx), h: Math.min(vh, g.h + 2 * my) };
    }
    const c = document.createElement("canvas");
    c.width = Math.round(r.w); c.height = Math.round(r.h);
    c.getContext("2d").drawImage(video, r.x, r.y, r.w, r.h, 0, 0, c.width, c.height);
    return new Promise((res) => c.toBlob((b) => res(b), "image/jpeg", 0.92));
  }

  /* Opens the camera. Resolves with a Blob (JPEG) or null if cancelled. */
  function capture({ title = "Scan the body", guide = true } = {}) {
    return new Promise((resolve) => {
      const canCam = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && window.isSecureContext;
      const m = openModal(title, `
        <div class="cam" id="camBox">
          ${canCam ? `<video id="camVideo" playsinline muted></video>` : ""}
          <div id="camOverlay"></div>
          <div class="status" id="camStatus">${canCam ? "Starting camera…" : ""}</div>
        </div>
        ${guide ? `<p class="small muted" style="margin-top:10px">Stand the person inside the frame, head to feet, facing the camera, in the best light available.
          Only the area inside the frame is sent for analysis.</p>` : ""}
        <label class="row small" style="margin-top:6px" ${guide ? "" : "hidden"}><input type="checkbox" id="camCrop" ${guide ? "checked" : ""}> Crop to the guide frame</label>
        <div id="camFallback" hidden></div>`,
        `<label class="btn">${icon("upload")} Use phone camera / file<input id="camFile" type="file" accept="image/*" capture="environment" hidden></label>
         <span class="spacer"></span>
         <button class="btn" id="camFlip" ${canCam ? "" : "disabled"}>${icon("flip")} Switch camera</button>
         <button class="btn" id="camTimer" ${canCam ? "" : "disabled"}>Capture in 3 s</button>
         <button class="btn primary" id="camShot" ${canCam ? "" : "disabled"}>${icon("camera")} Capture</button>`, { wide: true });

      let settled = false;
      const finish = (b) => { if (settled) return; settled = true; stop(); m.close(); resolve(b); };
      $("#modalRoot").addEventListener("modalclose", () => { stop(); if (!settled) { settled = true; resolve(null); } }, { once: true });

      const video = $("#camVideo", m.el);
      const statusEl = $("#camStatus", m.el);
      const showError = (msg) => {
        $("#camBox", m.el).innerHTML = `<div class="cam-error"><h3>Camera not available here</h3><p>${esc(msg)}</p>
          <p>Use <b>Use phone camera / file</b> below — on a phone it opens the camera app directly.</p></div>`;
        ["#camFlip", "#camTimer", "#camShot"].forEach((s) => ($(s, m.el).disabled = true));
      };

      if (!canCam) {
        showError(window.isSecureContext ? "This browser does not support live camera capture."
          : "Live camera needs the app to be opened at http://localhost:8000 (or over HTTPS).");
      } else {
        start(video).then(() => {
          statusEl.textContent = "Align the person with the guide";
          if (guide) {
            $("#camOverlay", m.el).innerHTML = guideSvg(video.videoWidth, video.videoHeight) + `<div class="scanline"></div>`;
          }
        }).catch((e) => {
          showError(e && e.name === "NotAllowedError" ? "Camera permission was denied. Allow camera access in the browser's address bar and try again."
            : e && e.name === "NotFoundError" ? "No camera was found on this device." : "The camera could not be started (" + (e && e.name || "error") + ").");
        });
      }

      $("#camFile", m.el).addEventListener("change", (e) => { if (e.target.files[0]) finish(e.target.files[0]); });
      $("#camFlip", m.el).addEventListener("click", async () => {
        facing = facing === "environment" ? "user" : "environment";
        try { await start(video); } catch (e) { toast("Could not switch camera.", "warn"); }
      });
      const shoot = async () => {
        const b = await grab(video, $("#camCrop", m.el).checked && guide);
        finish(b);
      };
      $("#camShot", m.el).addEventListener("click", shoot);
      $("#camTimer", m.el).addEventListener("click", async () => {
        const box = $("#camBox", m.el);
        const cd = h(`<div class="countdown">3</div>`); box.appendChild(cd);
        for (const n of [3, 2, 1]) { cd.textContent = n; await sleep(1000); if (settled) return; }
        cd.remove(); shoot();
      });
    });
  }

  return { capture, stop };
})();
