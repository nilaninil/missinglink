/* Boot: navigation, status pill, role switcher, offline toggle. */
"use strict";

const NAV = [
  ["Overview", [["dash", "Dashboard", "#/dashboard", "/dashboard"], ["play", "Demo investigation", "#/demo", "/demo"]]],
  ["Investigate", [["cases", "Missing cases", "#/cases", "/cases"], ["scan", "Live body scan", "#/scan", "/scan"],
    ["records", "Found records", "#/records", "/records"]]],
  ["Evidence", [["cctv", "CCTV evidence", "#/cctv", "/cctv"], ["doc", "Document scanner", "#/documents", "/documents"],
    ["timeline", "Evidence timeline", "#/timeline", "/timeline"]]],
  ["System", [["sync", "Offline and sync", "#/sync", "/sync"], ["settings", "Settings", "#/settings", "/settings"]]],
];

function buildNav() {
  $("#nav").innerHTML = NAV.map(([g, items]) => `<div class="group">${esc(g)}</div>` +
    items.map(([ic, label, href, match]) => `<a href="${href}" data-match="${match}">${icon(ic)}<span>${esc(label)}</span>${match === "/sync" ? `<span class="count" id="syncCount" hidden></span>` : ""}</a>`).join("")).join("");
}

function paintStatus() {
  const s = ML.state;
  const pill = $("#modePill");
  pill.className = "mode-pill " + (s.online ? "online" : "offline");
  pill.textContent = s.online ? "ONLINE MODE" : "OFFLINE MODE";
  pill.title = (s.simulated ? "Simulated. " : "") + "Click to " + (s.online ? "simulate going offline" : "simulate reconnecting");
  $("#offlineBanner").hidden = s.online;
  if (s.status) {
    const enc = s.status.encoder || "";
    $("#encoderName").textContent = enc.toLowerCase().includes("fallback") ? "Fallback visual encoder active" : enc;
    const n = s.status.pending_sync || 0;
    const c = $("#syncCount");
    if (c) { c.hidden = !n; c.textContent = n; }
  }
}

async function pollStatus() {
  try {
    const st = await api("/system/status", { quiet: true, timeout: 5000 });
    ML.state.status = st;
    ML.state.simulated = st.simulated;
    ML.state.online = st.mode === "online" && navigator.onLine !== false;
  } catch (e) {
    ML.state.status = null;
  }
  paintStatus();
}

async function setOffline(offline) {
  try {
    const st = await api("/system/offline", { method: "POST", json: { offline } });
    ML.state.online = st.mode === "online"; ML.state.simulated = st.simulated;
    paintStatus();
    await pollStatus();
  } catch (e) { /* toast */ }
}

function updateUserBadge() {
  const area = $("#userBadgeArea");
  if (!area) return;
  const user = getActiveSession();
  if (user) {
    area.innerHTML = `
      <div class="user-badge" id="userBadgeBtn" title="Click to view session or switch user">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
        <span class="user-name">${esc(user.name)}</span>
        <span class="role-tag">${esc(user.role)}</span>
      </div>
    `;
    const btn = $("#userBadgeBtn", area);
    if (btn) btn.addEventListener("click", () => authModal());
  } else {
    area.innerHTML = `
      <button class="btn sm auth-btn" id="signInBtn">
        ${icon("person")} Sign In
      </button>
    `;
    const btn = $("#signInBtn", area);
    if (btn) btn.addEventListener("click", () => authModal());
  }
}

async function boot() {
  buildNav();
  const session = getActiveSession();
  ML.state.user = session;
  if (session) {
    const mappedRole = session.role === "Field Officer" ? "volunteer" : "investigator";
    ML.state.role = mappedRole;
    store.set("role", mappedRole);
  } else {
    ML.state.role = store.get("role", "investigator");
  }
  ML.state.currentCase = store.get("currentCase", null);
  ML.bustKey = Date.now();
  $("#roleSelect").value = ML.state.role;
  updateUserBadge();
  $("#roleSelect").addEventListener("change", (e) => {
    ML.state.role = e.target.value; store.set("role", ML.state.role);
    // sync session role if user exists
    if (ML.state.user) {
      ML.state.user.role = e.target.value === "volunteer" ? "Field Officer" : "Investigator";
      localStorage.setItem(ML_AUTH_KEY, JSON.stringify(ML.state.user));
      updateUserBadge();
    }
    toast(ML.state.role === "volunteer" ? "Field volunteer view: exact care locations are hidden." : `Viewing as ${e.target.selectedOptions[0].text}.`);
    renderRoute();
  });
  $("#modePill").addEventListener("click", () => setOffline(ML.state.online));
  $("#menuBtn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  $("#sideDemo").addEventListener("click", () => go("#/demo"));
  window.addEventListener("online", pollStatus);
  window.addEventListener("offline", pollStatus);
  window.addEventListener("hashchange", renderRoute);

  await pollStatus();
  const [loc, orgs] = await Promise.allSettled([api("/localities", { quiet: true }), api("/organizations", { quiet: true })]);
  if (loc.status === "fulfilled") ML.state.localities = loc.value;
  if (orgs.status === "fulfilled") ML.state.orgs = orgs.value;
  await refreshCases();
  setInterval(pollStatus, 10000);
  renderRoute();
}

boot();

