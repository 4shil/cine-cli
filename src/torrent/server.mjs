/**
 * Embedded WebTorrent web server.
 *
 * Spawned by `cine --download` after the user picks a torrent.
 * Serves the public/ directory, exposes a Socket.io bus for live updates,
 * and accepts new torrents via POST /api/add.
 */

import express from 'express';
import { createServer } from 'node:http';
import { Server as SocketIOServer } from 'socket.io';
import WebTorrent from 'webtorrent';
import { mkdirSync } from 'node:fs';
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
const DOWNLOAD_DIR = arg('--dir', path.join(os.homedir(), 'Downloads', 'cine-cli'));
const MAX_CONCURRENT = 5;

mkdirSync(DOWNLOAD_DIR, { recursive: true });

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));
// Fallback to public root at the package level too:
app.use(express.static(path.resolve(process.cwd(), 'public')));

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
    torrents.set(t.infoHash, {
      torrent: t,
      meta: { name: name || 'Loading...', infoHash: t.infoHash, addedAt: Date.now() },
    });
    await new Promise((resolve) => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      t.on('metadata', finish);
      t.on('ready', finish);
      setTimeout(finish, 10000);
    });
    const meta = torrents.get(t.infoHash).meta;
    meta.name = t.name || name || 'Unknown';
    meta.size = t.length || 0;
    res.json({
      success: true,
      infoHash: t.infoHash,
      name: meta.name,
      size: meta.size,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/torrents', (_req, res) => {
  const list = [];
  for (const [, { torrent, meta }] of torrents) list.push(payload(torrent, meta));
  res.json(list);
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
});

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

httpServer.listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`\n  ╭─────────────────────────────────────────────────╮\n`);
  process.stdout.write(`  │  cine-cli  ·  torrent web ui                     │\n`);
  process.stdout.write(`  │  url: http://127.0.0.1:${PORT}                      │\n`);
  process.stdout.write(`  │  dir: ${DOWNLOAD_DIR}\n`);
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
