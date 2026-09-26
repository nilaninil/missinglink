/* MissingLink core: API wrapper, app state, router, small helpers. No external libraries. */
"use strict";

const ML = {
  state: {
    role: "investigator",
    online: true,
    simulated: false,
    status: null,
    cases: [],
    localities: [],
    orgs: [],
    lastResults: {},      // case_id -> latest match payload
    currentCase: null,
  },
  routes: [],
};

/* ---------- storage (best effort; never required) */
const store = {
  get(k, d) { try { const v = localStorage.getItem("ml." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("ml." + k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
};

/* ---------- local auth / sessions */
const ML_AUTH_KEY = "ml_user_session";

function getActiveSession() {
  try {
    const raw = localStorage.getItem(ML_AUTH_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  // Default session for smooth first run
  return {
    name: "Officer Sharma",
    email: "sharma@police.gov.in",
    role: "Investigator" // "Investigator" | "Field Officer"
  };
}

function setActiveSession(session) {
  try {
    localStorage.setItem(ML_AUTH_KEY, JSON.stringify(session));
  } catch (e) {}
  ML.state.user = session;
  const mappedRole = session.role === "Field Officer" ? "volunteer" : "investigator";
  ML.state.role = mappedRole;
  store.set("role", mappedRole);
  if ($("#roleSelect")) $("#roleSelect").value = mappedRole;
  if (typeof updateUserBadge === "function") updateUserBadge();
}

function clearSession() {
  try {
    localStorage.removeItem(ML_AUTH_KEY);
  } catch (e) {}
  ML.state.user = null;
  if (typeof updateUserBadge === "function") updateUserBadge();
}

/* ---------- API */
class ApiFailure extends Error {
  constructor(message, code, status, detail) { super(message); this.code = code; this.status = status; this.detail = detail; }
}

async function api(path, { method = "GET", json, form, timeout = 15000, quiet = false } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const headers = { "X-Role": ML.state.role };
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  try {
    const res = await fetch("/api" + path, { method, headers, body, signal: ctrl.signal });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const e = (data && data.error) || {};
      throw new ApiFailure(e.message || `Request failed (${res.status}).`, e.code || "http_" + res.status, res.status, e.detail);
    }
    return data;
  } catch (err) {
    let f = err;
    if (err.name === "AbortError") f = new ApiFailure("The request took too long. Your previous data is safe — please try again.", "timeout", 0);
    else if (!(err instanceof ApiFailure)) f = new ApiFailure("Backend unavailable — your previous data is safe. Retrying may help.", "network", 0);
    if (!quiet) toast(f.message + (f.detail && typeof f.detail === "string" ? " " + f.detail : ""), "error");
    throw f;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(v) {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function pct(v, cap = 0.99) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Math.round(Math.min(v, cap) * 100) + "%";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmtDT(iso, withDate = true) {
  if (!iso) return "Unknown time";
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  const hm = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  return withDate ? `${d.getDate()} ${MONTHS[d.getMonth()]}, ${hm}` : hm;
}

function toLocalInput(iso) {
  if (!iso) return "";
  return iso.slice(0, 16);
}

function ageText(r) {
  if (r.age_min == null && r.age_max == null) return "Age unknown";
  if (r.age_min === r.age_max) return `Age ~${r.age_min}`;
  return `Age ${r.age_min ?? "?"}–${r.age_max ?? "?"}`;
}

const RECORD_TYPES = { found: "Found person", unidentified_patient: "Unidentified patient", shelter_resident: "Shelter resident", sighting: "Sighting" };

function bandChip(band, text) {
  const cls = { high_priority: "hp", possible: "possible", low: "low", conflict: "conflict" }[band] || "neutral";
  const label = text || { high_priority: "High-Priority Potential Match", possible: "Potential Match", low: "Low Evidence", conflict: "Possible Match — Conflict Detected" }[band] || band;
  return `<span class="chip ${cls}">${esc(label)}</span>`;
}

function syncChip(s) {
  return s === "pending_sync" ? `<span class="chip pending" title="Created while offline">Pending Sync</span>` : "";
}

function toast(msg, kind = "info", ms = 5200) {
  const el = h(`<div class="toast ${kind}" role="status">${esc(msg)}</div>`);
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function loading(text = "Loading…") {
  return `<div class="loading"><span class="spin"></span>${esc(text)}</div>`;
}

function bust(url) {
  if (!url) return url;
  return url + (url.includes("?") ? "&" : "?") + "v=" + (ML.bustKey || 1);
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

/* ---------- icons (inline SVG paths, 24x24, stroke) */
const ICONS = {
  dash: "M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 8h6V4h-6z",
  cases: "M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 7h16v12H4zM4 12h16",
  plus: "M12 5v14M5 12h14",
  scan: "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M12 8a2 2 0 1 0 0 .01M9 17v-3a3 3 0 0 1 6 0v3",
  records: "M5 4h10l4 4v12H5zM15 4v4h4M8 12h8M8 16h6",
  cctv: "M3 7l12-3 2 6-12 3zM9 12l1 4h4M15 9l5 2M4 20h6",
  doc: "M6 3h9l3 3v15H6zM9 9h6M9 13h6M9 17h4",
  timeline: "M12 3v18M12 7h6M12 12H6M12 17h6",
  sync: "M4 12a8 8 0 0 1 14-5l2 2M20 12a8 8 0 0 1-14 5l-2-2M20 4v5h-5M4 20v-5h5",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19 12l2-1-2-4-2 1-2-1V5h-4v2l-2 1-2-1-2 4 2 1v2l-2 1 2 4 2-1 2 1v2h4v-2l2-1 2 1 2-4-2-1z",
  play: "M7 4l12 8-12 8z",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  check: "M5 12l5 5 9-10",
  flag: "M5 21V4h11l-2 4 2 4H5",
  x: "M6 6l12 12M18 6L6 18",
  hospital: "M4 20V6h16v14M9 20v-5h6v5M12 8v5M9.5 10.5h5",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  rank: "M4 18l5-6 4 3 7-9",
  person: "M12 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 20v-4a6 6 0 0 1 12 0v4",
  flip: "M4 10a8 8 0 0 1 14-3M20 14a8 8 0 0 1-14 3M18 3v4h-4M6 21v-4h4",
};
function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[name] || ""}"/></svg>`;
}

/* ---------- router */
function route(pattern, render) {
  const keys = [];
  const re = new RegExp("^" + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return "([^/]+)"; }) + "$");
  ML.routes.push({ re, keys, render, pattern });
}

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/dashboard";
  const [path, qs] = raw.split("?");
  const query = Object.fromEntries(new URLSearchParams(qs || ""));
  return { path, query };
}

let routeToken = 0;
async function renderRoute() {
  const { path, query } = parseHash();
  const view = $("#view");
  const token = ++routeToken;
  for (const r of ML.routes) {
    const m = path.match(r.re);
    if (!m) continue;
    const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
    $$("#nav a").forEach((a) => a.classList.toggle("active", path.startsWith(a.dataset.match)));
    $("#sidebar").classList.remove("open");
    view.innerHTML = loading();
    try {
      await r.render(view, params, query, () => token === routeToken);
    } catch (e) {
      if (token !== routeToken) return;
      console.error(e);
      view.innerHTML = `<div class="panel empty"><h3>This page could not be loaded</h3><p>${esc(e.message || "Unknown error")}</p>
        <button class="btn" onclick="renderRoute()">Try again</button></div>`;
    }
    window.scrollTo(0, 0);
    return;
  }
  view.innerHTML = `<div class="panel empty"><h3>Page not found</h3><a class="btn" href="#/dashboard">Go to dashboard</a></div>`;
}

function go(hash) { if (location.hash === hash) renderRoute(); else location.hash = hash; }
