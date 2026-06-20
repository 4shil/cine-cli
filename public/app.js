// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  cine :: torrent runtime — app.js
//
//  - GSAP-driven springs/tweens for every UI motion (≥ 0.18s, ≥ power2.out)
//  - Socket.io real-time status + torrent update stream
//  - Theme: dark | light | system   (persists in localStorage)
//  - URL/queue magnet ingestion (URL params, hash, or POST /api/queue/incoming)
//
//  Loaded as a classic <script> after socket.io.js and gsap.min.js, so
//  `io` and `gsap` are globals here.
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/* global io, gsap */

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const fmtBytes = (b) => {
  if (!b || b < 0) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let n = b, i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 2 : 1)} ${u[i]}`;
};
const fmtRate = (bps) => `${fmtBytes(bps || 0)}/s`;
const fmtEta  = (ms) => {
  if (!ms || ms === Infinity || ms < 0) return "—";
  const s = Math.round(ms / 1000);
  if (s > 3600) return `${Math.floor(s / 3600)}h${Math.floor((s % 3600) / 60)}m`;
  if (s > 60)   return `${Math.floor(s / 60)}m${s % 60}s`;
  return `${s}s`;
};
const fmtInt = (n) => (n | 0).toString();
const fmtHash = (h) => h ? `${h.slice(0, 8)}…${h.slice(-4)}` : "—";
const host = location.host;

// ─────────────────────────────────────────────────────────────────────
//  theme
// ─────────────────────────────────────────────────────────────────────
const THEME_KEY = "cine:theme";
const theme = { current: "dark" };

function applyTheme(t) {
  theme.current = t;
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch {}
}

function resolveInitialTheme() {
  let saved;
  try { saved = localStorage.getItem(THEME_KEY); } catch {}
  if (saved === "dark" || saved === "light") return saved;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

applyTheme(resolveInitialTheme());

$("#theme-toggle").addEventListener("click", () => {
  const next = theme.current === "dark" ? "light" : "dark";
  // Smooth bg transition
  document.body.style.transition = "background 0.22s ease, color 0.22s ease";
  applyTheme(next);
  setTimeout(() => { document.body.style.transition = ""; }, 260);
});

// ─────────────────────────────────────────────────────────────────────
//  feed log
// ─────────────────────────────────────────────────────────────────────
const feed = {
  el: $("#feed-list"),
  list: [],              // ring buffer
  max: 80,
  push(kind, glyph, msg) {
    const time = new Date();
    const hh = String(time.getHours()).padStart(2, "0");
    const mm = String(time.getMinutes()).padStart(2, "0");
    const ss = String(time.getSeconds()).padStart(2, "0");
    this.list.push({ kind, glyph, msg, t: `${hh}:${mm}:${ss}` });
    if (this.list.length > this.max) this.list.shift();
    this.render();
  },
  render() {
    const html = this.list.map((it) => `
      <li class="feed-line" data-kind="${it.kind}">
        <span class="g">${it.glyph}</span>
        <span class="t">${it.t}</span>
        <span class="m">${escapeHtml(it.msg)}</span>
      </li>
    `).join("");
    this.el.innerHTML = html;
    this.el.scrollTo({ top: this.el.scrollHeight, behavior: "smooth" });
  }
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&", "<": "<", ">": ">", "\"": "\"", "'": "'"
  }[c]));
}

// ─────────────────────────────────────────────────────────────────────
//  status pills + wire
// ─────────────────────────────────────────────────────────────────────
const status = {
  pillsEl: $("#status-pills"),
  uptimeEl: $("#uptime"),
  totalsEl: $("#totals"),
  dlEl: $("#dl-path"),
  wire: $("#wire-dot")?.closest(".wire"),
  amount: $("#wire-amount"),
  startedAt: Date.now(),
  setPills(items) {
    const html = items.map((it) => `
      <span class="pill" data-state="${it.state ?? "ok"}">
        <span class="label">${escapeHtml(it.label)}</span>
        ${it.value ? `<span>${escapeHtml(it.value)}</span>` : ""}
      </span>
    `).join("");
    this.pillsEl.innerHTML = html;
  },
  setWire(busy, amount) {
    if (!this.wire) return;
    this.wire.dataset.state = busy ? (amount > 0 ? "busy" : "active") : "idle";
    this.amount.textContent = amount > 0 ? formatBytesRate(amount) : (busy ? "rendezvous…" : "idle");
  },
  tickUptime() {
    const s = Math.floor((Date.now() - this.startedAt) / 1000);
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    this.uptimeEl.textContent = hh > 0
      ? `${hh}h${String(mm).padStart(2, "0")}m${String(ss).padStart(2, "0")}s`
      : `${mm}m${String(ss).padStart(2, "0")}s`;
  }
};

const formatBytesRate = (bps) => fmtRate(bps);

setInterval(() => status.tickUptime(), 1000);

// initial pill set
status.setPills([
  { state: "warn", label: "loading", value: "…" },
]);

// ─────────────────────────────────────────────────────────────────────
//  sockets
// ─────────────────────────────────────────────────────────────────────
const socket = io({ transports: ["websocket", "polling"], reconnection: true });

socket.on("connect", () => {
  status.setPills([
    { state: "ok",   label: "socket.io",   value: "live" },
    { state: "ok",   label: "webrtc",      value: "•" },
    { state: "warn", label: "dht",         value: "bootstrap…" },
  ]);
  status.setWire(true, 0);
  const transport = (socket.io && socket.io.engine && socket.io.engine.transport) || "?";
  const tName = typeof transport === "string" ? transport : (transport && transport.name) || "socket";
  feed.push("ok", "+", "socket.io  ·  connected  ·  transport=" + tName);
});

socket.on("disconnect", () => {
  status.setPills([
    { state: "bad",  label: "socket.io",   value: "offline" },
    { state: "bad",  label: "webrtc",      value: "—" },
    { state: "bad",  label: "dht",         value: "—" },
  ]);
  status.setWire(false, 0);
  feed.push("bad", "!", "socket.io  ·  disconnected");
});

socket.on("connect_error", (err) => {
  feed.push("warn", "?", "socket.io  ·  " + escapeHtml(err.message || String(err)));
});

// server emits runtime events
socket.on("runtime", (e) => {
  if (!e || !e.kind) return;
  feed.push(e.kind === "bad" ? "bad" : e.kind === "warn" ? "warn" : "ok", "+", e.msg);
});

let bandwidth = 0;
socket.on("torrent-update", (items) => {
  // Aggregate total wire bandwidth (sum of speed across active torrents)
  bandwidth = (items || []).reduce((a, t) => a + (t.downloadSpeed || 0) + (t.uploadSpeed || 0), 0);
  status.setWire(true, bandwidth);
  for (const t of items || []) upsertRow(t);
  recomputeHeadMeta();
});

socket.on("torrent-list", (items) => {
  for (const t of items || []) upsertRow(t);
  recomputeHeadMeta();
});

// ─────────────────────────────────────────────────────────────────────
//  torrent rows
// ─────────────────────────────────────────────────────────────────────
const rowsEl = $("#rows");
const empty = $("#empty");
const rows = new Map(); // infoHash -> { el, data, sparkline }

function recomputeHeadMeta() {
  const n = rows.size;
  let bytes = 0;
  for (const v of rows.values()) bytes += (v.data.size || 0) * (v.data.progress || 0);
  $("#head-meta").textContent = `${n} active · ${fmtBytes(bytes)}`;
  status.totalsEl.textContent = `${n} active · ${fmtBytes(bytes)}`;
  empty.hidden = n > 0;
}

function statusStateFor(t) {
  if (t.error) return "err";
  if (t.done || t.progress >= 1) return "complete";
  if (t.paused) return "paused";
  if ((t.uploadSpeed || 0) > (t.downloadSpeed || 0) && (t.uploadSpeed || 0) > 0) return "seeding";
  return "downloading";
}

function buildRow(t) {
  const el = document.createElement("article");
  el.className = "row";
  el.dataset.hash = t.infoHash || "";
  el.dataset.state = statusStateFor(t);
  el.innerHTML = `
    <div class="row-main">
      <div class="row-top">
        <div class="row-name" data-role="name"></div>
        <span class="row-state-tag" data-role="tag">…</span>
      </div>
      <div class="row-meta">
        <span>size  <b data-role="size">0 B</b></span>
        <span>done  <b data-role="done">0 B</b></span>
        <span>ratio <b data-role="ratio">0.00</b></span>
        <span>peers <b data-role="peers">0</b></span>
        <span>eta   <b data-role="eta">—</b></span>
        <span class="hash"><span class="g">hash</span> <b data-role="hash">—</b></span>
      </div>
      <div class="row-progress">
        <div class="bar" data-role="bar">
          <div class="bar-fill" data-role="fill" style="width:0%"></div>
          <div class="bar-ticks">
            ${Array.from({ length: 20 }).map(() => `<span></span>`).join("")}
          </div>
        </div>
      </div>
    </div>

    <div class="row-right">
      <div class="spark" data-role="spark">
        <svg viewBox="0 0 240 36" preserveAspectRatio="none" aria-hidden="true">
          <path data-role="dline" d="" />
          <path data-role="uline" d="" />
        </svg>
      </div>
      <div class="row-stats">
        <div>
          <span>dl</span> <b data-role="dl">0 B/s</b>
        </div>
        <div>
          <span class="uplink">ul </span>
          <span class="uplink" data-role="ul">0 B/s</span>
        </div>
      </div>
      <div class="row-actions">
        <button class="ra-btn" data-role="pause"   type="button">pause</button>
        <button class="ra-btn" data-role="resume"  type="button">resume</button>
        <button class="ra-btn" data-role="copy"    type="button">copy</button>
        <button class="ra-btn danger" data-role="remove" type="button">remove</button>
      </div>
    </div>
  `;
  rowsEl.appendChild(el);

  // enter animation
  gsap.from(el, {
    y: -8,
    opacity: 0,
    duration: 0.32,
    ease: "expo.out",
  });

  // bindings
  el.$ = (role) => el.querySelector('[data-role="' + role + '"]');
  el.$.pause?.addEventListener("click",  () => socket.emit("pause",  t.infoHash));
  el.$.resume?.addEventListener("click", () => socket.emit("resume", t.infoHash));
  el.$.copy?.addEventListener("click",    () => copyMagnet(t.infoHash));
  el.$.remove?.addEventListener("click", () => removeRow(t.infoHash));

  const entry = {
    el,
    data: t,
    spark: { d: [], u: [], max: 60, lastDl: 0, lastUl: 0 },
    tweens: {},
  };
  rows.set(t.infoHash, entry);
  return entry;
}

function removeRow(hash) {
  const entry = rows.get(hash);
  if (!entry) return;
  socket.emit("remove", hash);
  rows.delete(hash);
  gsap.to(entry.el, {
    y: -8,
    opacity: 0,
    height: 0,
    marginBottom: -8,
    paddingTop: 0,
    paddingBottom: 0,
    duration: 0.28,
    ease: "power2.in",
    onComplete: () => { entry.el.remove(); recomputeHeadMeta(); },
  });
}

function copyMagnet(hash) {
  fetch(`/api/info/${hash}`)
    .then((r) => r.ok ? r.json() : null)
    .then((j) => {
      if (!j || !j.magnet) toast("warn", "no magnet recorded");
      else {
        navigator.clipboard?.writeText(j.magnet).then(
          () => toast("ok",  "magnet copied"),
          () => toast("warn", "copy blocked by browser"),
        );
      }
    }).catch(() => toast("bad", "copy failed"));
}

function upsertRow(t) {
  if (!t || !t.infoHash) return;
  const hash = t.infoHash;
  let entry = rows.get(hash);
  if (!entry) entry = buildRow(t);

  // Update sparkline buffer
  const sp = entry.spark;
  sp.d.push(t.downloadSpeed || 0);
  sp.u.push(t.uploadSpeed   || 0);
  if (sp.d.length > sp.max) { sp.d.shift(); sp.u.shift(); }

  // === GSAP-tweened numeric readouts ===
  const setOrTween = (sel, val, opts = {}) => {
    const node = entry.el.$(sel);
    if (!node) return;
    gsap.to(node, {
      duration: opts.dur ?? 0.45,
      ease: opts.ease ?? "power2.out",
      ...opts.props,
      onUpdate: opts.onUpdate,
    });
    if (typeof val === "function") {
      node.textContent = val();
    } else {
      node.textContent = val;
    }
  };

  // bar fill animation
  const targetPct = Math.max(0, Math.min(100, (t.progress || 0) * 100));
  gsap.to(entry.el.$("fill"), {
    width: targetPct + "%",
    duration: 0.5,
    ease: "power3.out",
  });

  // state stripe
  const st = statusStateFor(t);
  if (entry.el.dataset.state !== st) {
    entry.el.dataset.state = st;
    gsap.fromTo(entry.el, { boxShadow: "inset 0 0 0 1px transparent" }, { boxShadow: "inset 0 0 0 1px transparent", duration: 0.4 });
  }
  entry.el.$("tag").dataset.state = st;
  entry.el.$("tag").textContent = ({
    downloading: "downloading",
    seeding:     "seeding",
    complete:    "complete",
    paused:      "paused",
    err:         "error",
  })[st];

  // text
  entry.el.$("name").textContent  = t.name || "loading…";
  entry.el.$("name").title        = t.name || "";
  entry.el.$("size").textContent  = fmtBytes(t.size || 0);
  entry.el.$("done").textContent  = fmtBytes((t.size || 0) * (t.progress || 0));
  entry.el.$("ratio").textContent = (t.size ? ((t.uploaded || 0) / t.size).toFixed(2) : "0.00");
  entry.el.$("peers").textContent = String(t.numPeers || 0);
  entry.el.$("eta").textContent   = st === "complete" ? "—" : fmtEta(t.timeRemaining);
  entry.el.$("hash").textContent  = fmtHash(hash);

  // numeric readout: tween number-with-commas
  const dlEl = entry.el.$("dl");
  const ulEl = entry.el.$("ul");
  tweenNumber(dlEl, t.downloadSpeed || 0, (v) => fmtRate(v));
  tweenNumber(ulEl, t.uploadSpeed   || 0, (v) => fmtRate(v));

  // sparkline
  drawSparkline(entry);

  // buttons
  entry.el.$("pause").disabled  = st === "complete" || st === "paused" || st === "seeding";
  entry.el.$("resume").disabled = st !== "paused";

  entry.data = t;
}

function tweenNumber(el, target, fmt) {
  if (!el) return;
  const current = parseFloat(el.dataset.num || "0") || 0;
  // rate-based smoothing
  const dur = 0.4;
  const obj = { v: current };
  gsap.killTweensOf(obj);
  gsap.to(obj, {
    v: target,
    duration: dur,
    ease: "power2.out",
    onUpdate: () => {
      el.dataset.num = String(obj.v);
      el.textContent = fmt(obj.v);
    },
    onComplete: () => { el.dataset.num = String(target); el.textContent = fmt(target); },
  });
}

// Draw a gentle SVG sparkline for download + upload over the last 60 ticks.
function drawSparkline(entry) {
  const svg  = entry.el.$("spark").querySelector("svg");
  const dln  = svg.querySelector('[data-role="dline"]');
  const uln  = svg.querySelector('[data-role="uline"]');
  const W = 240, H = 36;
  const sp = entry.spark;
  const max = Math.max(1, ...sp.d, ...sp.u);
  const x = (i) => (i / Math.max(1, sp.max - 1)) * W;
  const y = (v) => H - (v / max) * (H - 4) - 2;
  const path = (arr) => arr
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");
  dln.setAttribute("d", path(sp.d));
  uln.setAttribute("d", path(sp.u));
}

// ─────────────────────────────────────────────────────────────────────
//  add magnet form
// ─────────────────────────────────────────────────────────────────────
const addHint = $("#add-hint");
const addBtn  = $("#add-btn");

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#magnet");
  const v = (input.value || "").trim();
  if (!v) { toast("warn", "magnet link required"); return; }
  if (addBtn.disabled) return;
  addBtn.disabled = true;
  addBtn.textContent = "sending…";
  try {
    const r = await fetch("/api/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnet: v, name: v.slice(0, 80) }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `failed (${r.status})`);
    input.value = "";
    toast("ok", "added · " + (j.name || v.slice(0, 28)));
  } catch (err) {
    const m = (err && err.message) || String(err);
    toast("err", m.length > 80 ? m.slice(0, 80) + "…" : m);
  } finally {
    addBtn.disabled = false;
    addBtn.textContent = "enqueue";
  }
});

$("#magnet").addEventListener("input", (e) => {
  const has = (e.target.value || "").trim().length > 0;
  addHint.textContent = has ? "enter ↵" : "";
});

// ─────────────────────────────────────────────────────────────────────
//  toast
// ─────────────────────────────────────────────────────────────────────
const toastEl = $("#toast");
let toastTimer = null;
function toast(kind, msg) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  toastEl.className = "toast show kind-" + (kind || "info");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    gsap.to(toastEl, {
      opacity: 0,
      y: 8,
      duration: 0.18,
      ease: "power2.in",
      onComplete: () => { toastEl.hidden = true; toastEl.classList.remove("kind-" + kind); },
    });
  }, 2200);
}

// ─────────────────────────────────────────────────────────────────────
//  magnet ingestion (URL params / hash / server queue)
// ─────────────────────────────────────────────────────────────────────
async function ingestMagnet() {
  const params = new URLSearchParams(location.search);
  const hash   = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
  const h     = new URLSearchParams(hash);
  const fromUrl =
    params.get("magnet") || h.get("magnet") ||
    params.get("m")     || h.get("m");

  // Always wait for the input to be in the DOM (we're at the bottom of body).
  for (let i = 0; i < 50; i += 1) {
    if ($("#magnet")) break;
    await new Promise((r) => setTimeout(r, 20));
  }
  const input = $("#magnet");
  if (!input) return;

  let magnet = fromUrl;
  if (magnet) {
    input.value = magnet;
    // tidy the URL
    try {
      const u = new URL(location.href);
      u.searchParams.delete("magnet");
      u.searchParams.delete("m");
      u.hash = "";
      history.replaceState({}, "", u.pathname + (u.search || ""));
    } catch {}
  } else {
    // queue fallback
    try {
      const r = await fetch("/api/queue/incoming");
      if (r.ok) {
        const j = await r.json();
        if (j && j.magnet && j.magnet.magnet) {
          magnet = j.magnet.magnet;
          input.value = magnet;
          toast("info", "queued magnet loaded");
        }
      }
    } catch {}
  }

  if (magnet) {
    // dispatch add event via the form submit
    $("#add-form").dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", ingestMagnet, { once: true });
} else {
  ingestMagnet();
}

// show the download path on the rail
fetch("/api/info").then((r) => r.json()).then((j) => {
  if (j && j.downloadDir) status.dlEl.textContent = j.downloadDir;
}).catch(() => {});

// boot message
feed.push("info", "$", "runtime  ·  cine-cli torrent runtime ui  ·  v1");
console.info("%ccine-cli %s", "color:#a8a8ff;font-weight:700", "torrent runtime · v1");
