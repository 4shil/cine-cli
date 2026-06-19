/**
 * cine-cli WebTorrent Server (ESM)
 * 
 * A local web server for downloading torrents via WebTorrent.
 * Integrates with cine-cli's download command.
 */

import express from 'express';
import { Server } from 'socket.io';
import { createServer } from 'http';
import WebTorrent from 'webtorrent';
import path from 'path';
import fs from 'fs';
import os from 'os';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Configuration ──────────────────────────────────────────────────────────
const PORT = parseInt(process.argv.find((_, i, a) => a[i - 1] === '--port')) || 3737;
const DOWNLOAD_DIR = process.argv.find((_, i, a) => a[i - 1] === '--dir') || path.join(os.homedir(), 'Downloads', 'cine-cli');
const MAX_CONCURRENT = 5;

// ── App Setup ──────────────────────────────────────────────────────────────
const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, { cors: { origin: '*' } });
const client = new WebTorrent();
const torrents = new Map();

fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });

// ── Middleware ──────────────────────────────────────────────────────────────
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ── Routes ─────────────────────────────────────────────────────────────────
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.post('/api/add', async (req, res) => {
  const { magnet, name } = req.body;
  if (!magnet || typeof magnet !== 'string') {
    return res.status(400).json({ error: 'Missing or invalid magnet link' });
  }
  const magnetRegex = /magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}/;
  if (!magnetRegex.test(magnet)) {
    return res.status(400).json({ error: 'Invalid magnet link format' });
  }
  const infoHash = magnet.match(/btih:([a-fA-F0-9]{32,40})/)?.[1]?.toLowerCase();
  if (infoHash && torrents.has(infoHash)) {
    return res.status(409).json({ error: 'Torrent already added', infoHash });
  }
  if (torrents.size >= MAX_CONCURRENT) {
    return res.status(429).json({ error: `Max ${MAX_CONCURRENT} concurrent downloads` });
  }
  try {
    const torrent = client.add(magnet, { path: DOWNLOAD_DIR });
    torrents.set(torrent.infoHash, {
      torrent,
      meta: { name: name || torrent.name || 'Loading...', infoHash: torrent.infoHash, addedAt: Date.now() },
    });
    const metaPromise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Metadata timeout')), 30000);
      torrent.on('metadata', () => { clearTimeout(timeout); resolve(); });
      torrent.on('error', (err) => { clearTimeout(timeout); reject(err); });
    });
    try { await metaPromise; } catch { /* metadata might come later */ }
    const meta = torrents.get(torrent.infoHash)?.meta;
    if (meta) { meta.name = torrent.name || name || 'Unknown'; meta.size = torrent.length; }
    console.log(`[ADD] ${torrent.name || infoHash} (${torrent.infoHash})`);
    res.json({ success: true, infoHash: torrent.infoHash, name: torrent.name || name || 'Loading...' });
  } catch (err) {
    console.error(`[ERROR] Failed to add torrent: ${err.message}`);
    res.status(500).json({ error: `Failed to add torrent: ${err.message}` });
  }
});

app.get('/api/torrents', (req, res) => {
  const list = [];
  for (const [infoHash, { torrent, meta }] of torrents) {
    list.push(buildPayload(torrent, meta));
  }
  res.json(list);
});

app.post('/api/pause/:infoHash', (req, res) => {
  const entry = torrents.get(req.params.infoHash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'Torrent not found' });
  entry.torrent.pause();
  res.json({ success: true });
});

app.post('/api/resume/:infoHash', (req, res) => {
  const entry = torrents.get(req.params.infoHash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'Torrent not found' });
  entry.torrent.resume();
  res.json({ success: true });
});

app.post('/api/remove/:infoHash', (req, res) => {
  const entry = torrents.get(req.params.infoHash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'Torrent not found' });
  entry.torrent.destroy();
  torrents.delete(req.params.infoHash.toLowerCase());
  res.json({ success: true });
});

// ── Socket.io ──────────────────────────────────────────────────────────────
io.on('connection', (socket) => {
  console.log(`[SOCKET] Client connected: ${socket.id}`);
  const list = [];
  for (const [infoHash, { torrent, meta }] of torrents) list.push(buildPayload(torrent, meta));
  socket.emit('torrent-list', list);
  socket.on('disconnect', () => console.log(`[SOCKET] Client disconnected: ${socket.id}`));
});

function buildPayload(torrent, meta) {
  return {
    infoHash: torrent.infoHash,
    name: meta.name || torrent.name || 'Unknown',
    size: torrent.length || 0,
    progress: Math.round(torrent.progress * 10000) / 10000,
    downloadSpeed: torrent.downloadSpeed || 0,
    uploadSpeed: torrent.uploadSpeed || 0,
    numPeers: torrent.numPeers || 0,
    timeRemaining: torrent.timeRemaining || 0,
    done: torrent.done || false,
    paused: torrent.paused || false,
  };
}

setInterval(() => {
  if (torrents.size === 0) return;
  const updates = [];
  for (const [infoHash, { torrent, meta }] of torrents) {
    if (torrent.name && meta.name !== torrent.name) meta.name = torrent.name;
    updates.push(buildPayload(torrent, meta));
    if (torrent.done && Date.now() - meta.addedAt > 300000) torrents.delete(infoHash);
  }
  io.emit('torrent-update', updates);
}, 1000);

function shutdown() {
  console.log('\n[SHUTDOWN] Destroying torrents...');
  for (const [infoHash, { torrent }] of torrents) torrent.destroy();
  httpServer.close(() => { console.log('[SHUTDOWN] Server closed'); process.exit(0); });
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

httpServer.listen(PORT, '127.0.0.1', () => {
  console.log(`\n  ╔══════════════════════════════════════════════════╗`);
  console.log(`  ║       cine-cli Torrent Web Downloader            ║`);
  console.log(`  ╠══════════════════════════════════════════════════╣`);
  console.log(`  ║  URL:    http://localhost:${PORT}                   ║`);
  console.log(`  ║  Dir:    ${DOWNLOAD_DIR}`);
  console.log(`  ╚══════════════════════════════════════════════════╝\n`);
});
