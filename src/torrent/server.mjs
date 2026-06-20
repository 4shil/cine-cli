/**
 * Embedded WebTorrent web server.
 *
 * Spawned by `cine --download` after the user picks a torrent.
 * Serves the public/ directory, exposes a Socket.io bus for live updates,
 * and accepts new torrents via POST /api/add.
 *
 * Note: when cine-cli is installed globally the server's __dirname
 * resolves to *inside* the package's lib/ tree (e.g.
 * .../node_modules/cine-cli/lib/torrent/), while public/ ships directly
 * under the package root. We climb the right number of levels AND
 * tolerate via a few fallback roots so layout quirks (npm/i/pnpm) don't
 * 404 the UI.
 */

import express from 'express';
import { createServer } from 'node:http';
import { Server as SocketIOServer } from 'socket.io';
import WebTorrent from 'webtorrent';
import { mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const arg = (name, fallback) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
};

const PORT = parseInt(arg('--port', '3737'), 10);
const HOST = arg('--host', '127.0.0.1');
const DOWNLOAD_DIR = arg('--dir', path.join(os.homedir(), 'Downloads', 'cine-cli'));
const MAX_CONCURRENT = 5;

/**
 * Resolve the public directory.
 *
 * Order:
 *   1. <src>/../../public                       (typical src/ layout)
 *   2. <src>/../public                          (lib/ layout, e.g. global npm)
 *   3. <cwd>/public                             (dev convenience)
 *   4. <src>/public                             (alt layout)
 * Reject anything outside the package tree bounds if both root options miss.
 */
function resolvePublicDir() {
  const candidates = [
    path.resolve(__dirname, '..', '..', 'public'), // src/torrent → package root/public
    path.resolve(__dirname, '..', 'public'),       // lib/torrent → package root/public (alt)
    path.resolve(process.cwd(), 'public'),
    path.resolve(__dirname, 'public'),
  ];
  for (const p of candidates) {
    if (existsSync(path.join(p, 'index.html'))) return p;
  }
  // Return the first candidate for diagnostic purposes — give the caller a chance
  // to log if it failed and then fall through to the inline fallback page.
  return candidates[0];
}

const PUBLIC_DIR = resolvePublicDir();
const HAS_INDEX = existsSync(path.join(PUBLIC_DIR, 'index.html'));
mkdirSync(DOWNLOAD_DIR, { recursive: true });

// Tiny inline UI used as a hard fallback if public/index.html is missing.
const INLINE_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>cine-cli · torrent web ui</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter,
                 system-ui, sans-serif;
    background: #11111A; color: #E4E4F1;
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    padding: 24px;
  }
  main {
    max-width: 640px; width: 100%;
    background: #181826; border: 1px solid #2D2D44;
    border-radius: 14px; padding: 28px 26px;
  }
  h1 {
    background: linear-gradient(120deg, #7C3AED, #EC4899, #22D3EE);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    font-size: 20px; font-weight: 600; margin-bottom: 6px;
  }
  p { color: #8B8BA7; font-size: 14px; line-height: 1.55; margin-bottom: 16px; }
  form { display: flex; gap: 10px; margin-bottom: 18px; }
  input {
    flex: 1; background: #11111A; color: #E4E4F1;
    border: 1px solid #2D2D44; border-radius: 9px;
    padding: 12px 14px; font-size: 14px;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    outline: none;
  }
  input:focus { border-color: #7C3AED; }
  button {
    background: linear-gradient(135deg, #7C3AED, #EC4899);
    color: #fff; border: none; border-radius: 9px;
    padding: 12px 22px; font-size: 14px; font-weight: 600;
    cursor: pointer;
  }
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  ul { list-style: none; display: flex; flex-direction: column; gap: 10px; }
  li {
    background: #11111A; border: 1px solid #2D2D44;
    border-radius: 10px; padding: 12px 14px;
    font-size: 13px;
  }
  .bar { height: 6px; background: #1F1F2F; border-radius: 3px; margin: 8px 0; overflow: hidden; }
  .bar > div { height: 100%; background: linear-gradient(90deg, #7C3AED, #EC4899); }
  .meta { color: #8B8BA7; font-size: 11px; display: flex; gap: 12px; flex-wrap: wrap; }
  button.danger {
    background: transparent; color: #8B8BA7;
    border: 1px solid #2D2D44; border-radius: 7px;
    padding: 4px 10px; font-size: 11px; margin-left: 8px;
  }
  button.danger:hover { color: #EF4444; border-color: #EF4444; }
  button.action {
    background: transparent; color: #8B8BA7;
    border: 1px solid #2D2D44; border-radius: 7px;
    padding: 4px 10px; font-size: 11px; margin-left: 4px;
  }
  .net { color: #8B8BA7; font-size: 11px; margin-top: 14px; }
  .net .ok { color: #22C55E; }
  .net .bad { color: #EF4444; }
  code { color: #22D3EE; font-size: 11px; }
</style>
</head>
<body>
<main>
  <h1>cine-cli · torrent web</h1>
  <p>Inline fallback UI — the bundled <code>public/index.html</code> was not found at
     <code>__dirname/public</code>. The page below still uses the real API + Socket.io,
     so downloads work normally.</p>
  <form id="form">
    <input id="magnet" type="text" placeholder="magnet:?xt=urn:btih:…"
           autocomplete="off" spellcheck="false"/>
    <button id="add-btn" type="submit">add torrent</button>
  </form>
  <ul id="list"></ul>
  <div class="net" id="net">connecting…</div>
</main>
<script src="/socket.io/socket.io.js"></script>
<script>
const socket = io();
const item = (h, t) => {
  const li = document.createElement('li');
  const pctEl = document.createElement('div'); pctEl.id = 'pct-' + h;
  const bar = document.createElement('div');
  bar.className = 'bar'; const fill = document.createElement('div'); fill.id = 'fill-' + h; fill.style.width = '0%'; bar.appendChild(fill);
  const meta = document.createElement('div'); meta.className = 'meta'; meta.id = 'meta-' + h;
  const title = document.createElement('div'); title.id = 'name-' + h; title.textContent = t.name || 'Loading…';
  li.appendChild(title); li.appendChild(bar); li.appendChild(pctEl); li.appendChild(meta);
  const actions = document.createElement('div'); actions.style.marginTop = '8px';
  const pause = document.createElement('button'); pause.className = 'action';
  pause.textContent = 'pause'; pause.onclick = () => fetch('/api/pause/' + h, {method: 'POST'});
  const resume = document.createElement('button'); resume.className = 'action';
  resume.textContent = 'resume'; resume.onclick = () => fetch('/api/resume/' + h, {method: 'POST'});
  const remove = document.createElement('button'); remove.className = 'danger';
  remove.textContent = 'remove'; remove.onclick = async () => {
    await fetch('/api/remove/' + h, {method: 'POST'}); li.remove();
  };
  actions.appendChild(pause); actions.appendChild(resume); actions.appendChild(remove);
  li.appendChild(actions);
  return li;
};
const fmt = (b) => { if(!b) return '0 B'; const u=['B','KB','MB','GB','TB']; let i=0,n=b; while(n>=1024 && i<u.length-1){n/=1024;i++;} return n.toFixed(n<10 && i>0?2:1)+' ' +u[i]; };
const fmtRate = (b) => b ? fmt(b)+'/s' : '0 B/s';

document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const m = document.getElementById('magnet').value.trim();
  if (!m) return;
  document.getElementById('add-btn').disabled = true;
  try {
    const res = await fetch('/api/add', {method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({magnet: m})});
    document.getElementById('magnet').value = '';
  } catch {}
  document.getElementById('add-btn').disabled = false;
});

socket.on('connect', () => document.getElementById('net').innerHTML = '<span class="ok">live</span> · socket.io');
socket.on('disconnect', () => document.getElementById('net').innerHTML = '<span class="bad">disconnected</span>');
socket.on('torrent-list', (list) => {
  const root = document.getElementById('list');
  for (const t of list) if (!document.getElementById('pct-' + t.infoHash)) root.appendChild(item(t.infoHash, t));
});
socket.on('torrent-update', (list) => {
  const root = document.getElementById('list');
  for (const t of list) {
    if (!document.getElementById('pct-' + t.infoHash)) root.appendChild(item(t.infoHash, t));
    const pct = Math.round((t.progress || 0) * 100);
    const fm = document.getElementById('fill-' + t.infoHash);
    if (fm) fm.style.width = pct + '%';
    const pctEl = document.getElementById('pct-' + t.infoHash);
    if (pctEl) pctEl.textContent = pct + '%';
    const nm = document.getElementById('name-' + t.infoHash);
    if (nm) nm.textContent = t.name;
    const meta = document.getElementById('meta-' + t.infoHash);
    if (meta) meta.innerHTML = '<span>↓ ' + fmtRate(t.downloadSpeed) + '</span>'
      + '<span>↑ ' + fmtRate(t.uploadSpeed) + '</span>'
      + '<span>' + (t.numPeers||0) + ' peers</span>'
      + '<span>' + fmt(t.size||0) + '</span>';
  }
});
</script>
</body>
</html>`;

const app = express();
app.use(express.json());

/**
 * LOG every request with a tiny prefix. Critical when debugging 404s from
 * upstream cli's "open the browser" hand-off landing on the wrong path.
 */
app.use((req, _res, next) => {
  if (req.url.includes('/socket.io/') && req.url.includes('?EIO=')) {
    // socket.io poll/upgrade cycles every few seconds — too noisy to log.
  } else {
    process.stdout.write(`[req] ${req.method} ${req.url}\n`);
  }
  next();
});

/**
 * Hard root → index.html. We always answer GET / ourselves so that
 * layout variations in the installation tree don't shadow this path.
 */
// One-shot queue of the magnet the CLI wants the user to start watching.
// The page GETs it on load — sidesteps any URL-parameter fragility.
let pendingMagnet = null;

app.post('/api/queue/incoming', (req, res) => {
  const { magnet, name } = req.body || {};
  if (typeof magnet !== 'string' || !magnet.startsWith('magnet:')) {
    return res.status(400).json({ error: 'invalid magnet' });
  }
  pendingMagnet = { magnet, name: name || '' };
  res.json({ ok: true });
});

app.get('/api/queue/incoming', (_req, res) => {
  if (!pendingMagnet) return res.json({ magnet: null });
  const m = pendingMagnet;
  pendingMagnet = null;
  return res.json({ magnet: m });
});

app.get('/', (_req, res) => {
  res.set('Content-Type', 'text/html; charset=utf-8');
  if (HAS_INDEX) {
    res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
  } else {
    process.stdout.write(`[warn] public/index.html missing at ${PUBLIC_DIR}\n`);
    res.send(INLINE_HTML);
  }
});

/**
 * Static assets from public/ *after* the explicit `/` route. This keeps
 * other assets (served at /socket.io/... by socket.io itself, /style.css,
 * future assets) working but doesn't break / routing.
 */
if (HAS_INDEX) {
  app.use(express.static(PUBLIC_DIR, { index: false, fallthrough: true }));
}

const httpServer = createServer(app);
const io = new SocketIOServer(httpServer, { cors: { origin: '*' } });
const client = new WebTorrent();

const torrents = new Map();

function payload(torrent, meta) {
  return {
    infoHash: torrent.infoHash,
    name: meta?.name || torrent.name || 'Unknown',
    size: torrent.length || 0,
    progress: torrent.progress || 0,
    downloadSpeed: torrent.downloadSpeed || 0,
    uploadSpeed: torrent.uploadSpeed || 0,
    numPeers: torrent.numPeers || 0,
    timeRemaining: torrent.timeRemaining || 0,
    done: torrent.done || false,
    paused: torrent.paused || false,
  };
}

app.post('/api/add', async (req, res) => {
  const { magnet, name } = req.body || {};
  if (typeof magnet !== 'string' || !magnet.startsWith('magnet:')) {
    return res.status(400).json({ error: 'Invalid magnet link' });
  }
  if (torrents.size >= MAX_CONCURRENT) {
    return res.status(429).json({ error: `Max ${MAX_CONCURRENT} concurrent downloads` });
  }
  const hashMatch = magnet.match(/btih:([a-fA-F0-9]{32,40})/);
  const hash = hashMatch ? hashMatch[1].toLowerCase() : null;
  if (hash && torrents.has(hash)) {
    return res.status(409).json({ error: 'Already added', infoHash: hash });
  }
  try {
  const t = client.add(magnet, { path: DOWNLOAD_DIR, announce: torrentAnnounces() });
  t.on('error', (e) => process.stdout.write(`[torrent-error] ${e.message}\n`));

  // Wait for metadata first so `t.infoHash` is populated. WebTorrent v2
  // returns the Torrent synchronously but `infoHash` is undefined until
  // the `metadata` (or `ready`) event fires. Without this we register
  // the entry under key "undefined" and lose the ability to look it up.
  const resolvedHash = await new Promise((resolve) => {
    let done = false;
    const finish = (h) => {
      if (done) return;
      done = true;
      resolve((t.infoHash || h || '').toLowerCase());
    };
    t.on('infoHash', finish);
    t.on('metadata', () => finish());
    t.on('ready',      () => finish());
    setTimeout(() => finish(t.infoHash), 10000);
  });

  if (!resolvedHash) {
    try { t.destroy(); } catch {}
    return res.status(400).json({ error: 'Could not resolve info-hash from magnet' });
  }

  // Register under the now-known infoHash.
  if (torrents.has(resolvedHash)) {
    try { t.destroy(); } catch {}
    return res.status(409).json({ error: 'Already added', infoHash: resolvedHash });
  }
  torrents.set(resolvedHash, {
    torrent: t,
    meta: {
      name: name || t.name || 'Loading...',
      infoHash: resolvedHash,
      magnet,                     // remember original magnet for "copy"
      addedAt: Date.now(),
    },
  });

  // Backfill name/size once they're known.
  t.once('metadata', () => {
    const entry = torrents.get(resolvedHash);
    if (!entry) return;
    entry.meta.name = t.name || entry.meta.name;
    if (t.length) entry.meta.size = t.length;
  });

  return res.json({
    success: true,
    infoHash: resolvedHash,
    name: t.name || name || 'Loading...',
  });
  } catch (err) {
  process.stdout.write(`[catch] ${err.message}\n`);
  if (!res.headersSent) {
    return res.status(500).json({ error: err.message });
  }
  }
  });

app.get('/api/torrents', (_req, res) => {
  const list = [];
  for (const [, { torrent, meta }] of torrents) list.push(payload(torrent, meta));
  res.json(list);
});

/**
 * /api/info     → server/runtime info (download dir, version, count).
 * /api/info/:h  → per-torrent info incl. magnet URI for the copy button.
 */
app.get('/api/info', (_req, res) => {
  res.json({
    downloadDir: DOWNLOAD_DIR,
    version: '1',
    port: PORT,
    torrents: torrents.size,
  });
});

app.get('/api/info/:hash', (req, res) => {
  const h = String(req.params.hash || '').toLowerCase();
  const e = torrents.get(h);
  if (!e) return res.status(404).json({ error: 'not found' });
  res.json({
    infoHash: h,
    name: e.meta.name,
    magnet: e.meta.magnet || ('magnet:?xt=urn:btih:' + h),
    size:   e.torrent.length || e.meta.size || 0,
    peers:  e.torrent.numPeers || 0,
  });
});

app.post('/api/pause/:hash', (req, res) => {
  const entry = torrents.get(req.params.hash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'not found' });
  entry.torrent.pause();
  res.json({ ok: true });
});
app.post('/api/resume/:hash', (req, res) => {
  const entry = torrents.get(req.params.hash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'not found' });
  entry.torrent.resume();
  res.json({ ok: true });
});
app.post('/api/remove/:hash', (req, res) => {
  const entry = torrents.get(req.params.hash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'not found' });
  entry.torrent.destroy();
  torrents.delete(req.params.hash.toLowerCase());
  res.json({ ok: true });
});

io.on('connection', (socket) => {
  socket.emit('torrent-list', Array.from(torrents.values()).map(({ torrent, meta }) => payload(torrent, meta)));
  socket.emit('runtime', { kind: 'info', msg: 'client connected  ·  ' + (socket.id || '?').slice(0, 8) });

  // Socket.io-driven pause / resume / remove (the UI uses these now).
  socket.on('pause',  (hash) => {
    const e = lookUp(hash);
    if (!e) return socket.emit('runtime', { kind: 'warn', msg: 'pause: not found  ·  ' + (hash || '').slice(0, 8) });
    e.torrent.pause();
    socket.emit('runtime', { kind: 'info', msg: 'paused  ·  ' + (e.meta.name || hash).slice(0, 32) });
  });
  socket.on('resume', (hash) => {
    const e = lookUp(hash);
    if (!e) return socket.emit('runtime', { kind: 'warn', msg: 'resume: not found  ·  ' + (hash || '').slice(0, 8) });
    e.torrent.resume();
    socket.emit('runtime', { kind: 'info', msg: 'resumed  ·  ' + (e.meta.name || hash).slice(0, 32) });
  });
  socket.on('remove', (hash) => {
    const e = lookUp(hash);
    if (!e) return socket.emit('runtime', { kind: 'warn', msg: 'remove: not found  ·  ' + (hash || '').slice(0, 8) });
    try { e.torrent.destroy(); } catch {}
    torrents.delete((e.meta.infoHash || hash || '').toLowerCase());
    io.emit('torrent-update', []); // wake up the page
    io.emit('runtime', { kind: 'info', msg: 'removed  ·  ' + (e.meta.name || hash).slice(0, 32) });
  });

  socket.on('disconnect', () => {
    io.emit('runtime', { kind: 'warn', msg: 'client disconnected  ·  ' + (socket.id || '?').slice(0, 8) });
  });
});

function lookUp(hash) {
  if (typeof hash !== 'string') return null;
  const e = torrents.get(hash.toLowerCase());
  return e || null;
}

setInterval(() => {
  if (!torrents.size) return;
  const updates = [];
  for (const [hash, { torrent, meta }] of torrents) {
    if (torrent.name && meta.name !== torrent.name) meta.name = torrent.name;
    if (torrent.length && meta.size !== torrent.length) meta.size = torrent.length;
    updates.push(payload(torrent, meta));
    if (torrent.done && Date.now() - meta.addedAt > 5 * 60 * 1000) {
      torrents.delete(hash);
    }
  }
  io.emit('torrent-update', updates);
}, 1000);

function shutdown() {
  process.stdout.write('\n[shutdown] tearing down\n');
  for (const [, { torrent }] of torrents) {
    try { torrent.destroy(); } catch {}
  }
  httpServer.close(() => process.exit(0));
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

httpServer.listen(PORT, HOST, () => {
  process.stdout.write(`\n  ╭─────────────────────────────────────────────────╮\n`);
  process.stdout.write(`  │  cine-cli  ·  torrent web ui                     │\n`);
  process.stdout.write(`  │  url: http://${HOST}:${PORT}                        │\n`);
  process.stdout.write(`  │  dir: ${DOWNLOAD_DIR}\n`);
  process.stdout.write(`  │  ui:  ${HAS_INDEX ? PUBLIC_DIR : 'inline (no public/)'}\n`);
  process.stdout.write(`  ╰─────────────────────────────────────────────────╯\n\n`);
});

function torrentAnnounces() {
  return [
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://open.stealth.si:80/announce',
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://exodus.desync.com:6969/announce',
    'udp://tracker.tiny-vps.com:6969/announce',
    'udp://tracker.zerobytes.xyz:1337/announce',
    'udp://explodie.org:6969/announce',
  ];
}
