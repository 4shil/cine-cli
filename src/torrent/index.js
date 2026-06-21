/**
 * torrent/index.js — fetch torrents from Torrentio + sort by seeders.
 *
 * Plus the embedded server lifecycle:
 *   startTorrentWebServerAndOpen() spawns the server, picks a free port if
 *   the requested one is busy, waits for / to respond 200, opens the
 *   browser with the magnet preloaded, and returns status for the caller.
 */

import { fetch } from 'undici';
import open from 'open';
import { createServer } from 'node:net';

const BASE = 'https://torrentio.strem.fun';
const CONFIG = 'providers=yts,eztv,rarbg,1337x,thepiratebay|qualityfilter=480p,720p,1080p|sort=qualitysize';

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';

function apiUrl({ imdbId, type, season, episode }) {
  const path = type === 'tv'
    ? `stream/series/${imdbId}:${season}:${episode}.json`
    : `stream/movie/${imdbId}.json`;
  return `${BASE}/${CONFIG}/${path}`;
}

const QUALITY_RX = /(4K|2160p|1080p|720p|480p|360p|HDR|DV|HEVC)/i;
const SEEDERS_RX = /👤\s*(\d+)/;
const SIZE_RX = /([\d.]+)\s*(GB|MB|KB)/i;

export class TorrentStream {
  constructor(data) {
    this.title = data.title || data.name || '';
    this.infoHash = (data.infoHash || '').toLowerCase();
    this.fileIdx = data.fileIdx || 0;
    this.url = data.url;
    this.filename = data.behaviorHints?.filename || '';

    const q = this.title.match(QUALITY_RX);
    this.quality = q ? q[1].toLowerCase() : 'unknown';

    const s = this.title.match(SEEDERS_RX);
    this.seeders = s ? Number(s[1]) : 0;

    const m = this.title.match(SIZE_RX);
    if (m) {
      const v = parseFloat(m[1]);
      const u = m[2].toUpperCase();
      this.size = u === 'GB' ? Math.round(v * 1024) : u === 'KB' ? Math.round(v / 1024) : Math.round(v);
    } else {
      this.size = 0;
    }
    this.magnet = this.infoHash ? `magnet:?xt=urn:btih:${this.infoHash}` : '';
    this.name = this.filename || this.quality || 'torrent';
  }
}

TorrentStream.prototype.fileSizeLabel = function () {
  if (!this.size) return '—';
  if (this.size >= 1024) return `${(this.size / 1024).toFixed(1)} GB`;
  return `${this.size} MB`;
};

export async function fetchStreams({ imdbId, type = 'movie', season = 1, episode = 1 } = {}) {
  if (!imdbId) return [];
  const url = apiUrl({ imdbId, type, season, episode });
  try {
    const res = await fetch(url, { headers: { 'User-Agent': UA } });
    if (!res.ok) return [];
    const data = await res.json();
    const list = (data.streams || [])
      .map((s) => new TorrentStream(s))
      .filter((s) => s.infoHash && s.seeders > 0);
    list.sort((a, b) => (b.seeders || 0) - (a.seeders || 0));
    return list;
  } catch (err) {
    return [];
  }
}

/**
 * probePort(host, port) — return true if `port` on `host` answers a TCP
 * connect within `timeoutMs`. We use it twice:
 *   1. before spawning the server, to see if *something* is already
 *      serving on it (we then pick a fresh port)
 *   2. after spawn-returns-OK, to detect that the *child* actually bound.
 */
function probePort(host, port, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (taken) => {
      if (done) return;
      done = true;
      resolve(taken);
    };
    const sock = createServer();
    const timer = setTimeout(() => finish(true), timeoutMs);
    sock.once('error', () => { clearTimeout(timer); finish(true); });
    sock.once('listening', () => {
      sock.close(() => { clearTimeout(timer); finish(false); });
    });
    sock.listen(port, host);
  });
}

/**
 * Pick a free port on host. Tries the requested port first, then walks up
 * to +N. Caps so we don't pin forever on a saturated host.
 */
async function pickFreePort(host, basePort, maxTries = 10) {
  for (let i = 0; i < maxTries; i += 1) {
    const candidate = basePort + i;
    const taken = await probePort(host, candidate);
    if (!taken) return candidate;
  }
  throw new Error(`could not find a free port on ${host} near ${basePort}`);
}

/**
 * Start the embedded WebTorrent web server, wait for it to be ready,
 * open the browser with the magnet URL prefilled.
 *
 * Behaviour:
 *   - If `port` is busy, picks the next free one immediately
 *   - If the child process fails to bind (e.g. race condition where
 *     another process grabs the port after our probe but before our
 *     spawn), we surface that as `ready: false` *and* attach a
 *     non-fatal error handler to the child so Node won't crash.
 *   - Returns `{url, port, proc, ready}`. Callers MUST check `ready`
 *     before advertising a URL.
 */
export async function startTorrentWebServerAndOpen({ magnet, name, port = 3737, host = '127.0.0.1' } = {}) {
  const { spawn } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const { dirname, resolve } = await import('node:path');
  const here = dirname(fileURLToPath(import.meta.url));

  const serverPath = resolve(here, 'server.mjs');

  // Probe & pick a free port BEFORE spawning anything. If the default port
  // is busy (some previous cine still holding it), immediately try 3738,
  // 3739, etc. — transparent.
  const freePort = await pickFreePort(host, port);
  if (freePort !== port) {
    process.stdout.write(`\n  port ${port} busy — switched to ${freePort}\n`);
  }

  const proc = spawn(process.execPath, [serverPath, '--port', String(freePort), '--host', host], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    env: { ...process.env, FORCE_COLOR: '0' },
  });

  // Don't let the spawned child's own errors crash our parent.
  proc.on('error', (err) => {
    process.stderr.write(`\n  spawn failed: ${err.message}\n`);
  });

  let childExited = false;
  let childExitInfo = null;
  proc.on('exit', (code, signal) => {
    childExited = true;
    childExitInfo = { code, signal };
  });

  proc.stdout.on('data', (chunk) => process.stdout.write(`  ${chunk}`));
  proc.stderr.on('data', (chunk) => process.stderr.write(`  ${chunk}`));

  const ready = await waitForServer(`http://${host}:${freePort}/`, {
    timeoutMs: 30000,
    intervalMs: 150,
    onPoll: () => childExited,
  });

  if (!ready) {
    let why = `web torrent server did not become ready on http://${host}:${freePort} within 30s`;
    if (childExited) {
      why += ` (child exited: ${JSON.stringify(childExitInfo)})`;
    }
    process.stderr.write(`\n  ${why}\n`);
    return { url: null, port: freePort, proc, ready: false };
  }

  // Push the magnet into the server's one-shot queue so the page can
  // pick it up on load. Belt-and-braces alongside the URL query params:
  // if the browser opens the magnet-free URL (no ?magnet=… in the bar),
  // the page still finds the magnet via /api/queue/incoming.
  try {
    await fetch(`http://${host}:${freePort}/api/queue/incoming`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ magnet, name }),
    });
  } catch (err) {
    process.stderr.write(`  (warn) queue prefill failed: ${err.message}\n`);
  }

  // Open with URL params too (most browsers handle them cleanly, and the
  // page falls back to the queue if params fail).
  const params = new URLSearchParams({ magnet, name });
  const url = `http://${host}:${freePort}/?${params.toString()}`;
  await open(url, { wait: false });
  return { url, port: freePort, proc, ready: true };
}

async function waitForServer(url, { timeoutMs = 30000, intervalMs = 200, onPoll } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (typeof onPoll === 'function' && onPoll()) return false;
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 304) return true;
    } catch {
      // not yet
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}
