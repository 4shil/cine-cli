/**
 * torrent/index.js — fetch torrents from Torrentio + sort by seeders.
 */

import { fetch } from 'undici';
import open from 'open';

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
 * Pretty label for the torrent UI: "1.4 GB" / "640 MB" / "—".
 */
TorrentStream.prototype.fileSizeLabel = function () {
  if (!this.size) return '—';
  if (this.size >= 1024) return `${(this.size / 1024).toFixed(1)} GB`;
  return `${this.size} MB`;
};

/**
 * Start the embedded WebTorrent web server, wait for it to be ready,
 * open the browser with the magnet URL prefilled.
 *
 * Health-check loop uses an HTTP GET to / (returns 200 once listening).
 */
export async function startTorrentWebServerAndOpen({ magnet, name, port = 3737, host = '127.0.0.1' }) {
  const { spawn } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const { dirname, resolve } = await import('node:path');
  const here = dirname(fileURLToPath(import.meta.url));

  const serverPath = resolve(here, 'server.mjs');
  const proc = spawn(process.execPath, [serverPath, '--port', String(port), '--host', host], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    env: { ...process.env, FORCE_COLOR: '0' },
  });

  proc.stdout.on('data', (chunk) => process.stdout.write(`  ${chunk}`));
  proc.stderr.on('data', (chunk) => process.stderr.write(`  ${chunk}`));

  const ready = await waitForServer(`http://${host}:${port}/`, { timeoutMs: 8000 });
  if (!ready) {
    process.stderr.write(`\n  web torrent server did not become ready on http://${host}:${port} within 8s\n`);
    return { url: null, proc, ready: false };
  }

  const params = new URLSearchParams({ magnet, name });
  const url = `http://${host}:${port}/?${params.toString()}`;
  await open(url, { wait: false });
  return { url, proc, ready: true };
}

async function waitForServer(url, { timeoutMs = 8000 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 304) return true;
    } catch {
      // not yet
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}
