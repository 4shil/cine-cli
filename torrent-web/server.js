/**
 * cine-cli WebTorrent Server
 * 
 * A local web server for downloading torrents via WebTorrent.
 * Integrates with cine-cli's download command.
 * 
 * Usage:
 *   node server.js              # Start on port 3737
 *   node server.js --port 8080  # Custom port
 *   node server.js --dir /path  # Custom download directory
 */

const express = require('express');
const { Server } = require('socket.io');
const { createServer } = require('http');
const WebTorrent = require('webtorrent');
const path = require('path');
const fs = require('fs');
const os = require('os');

// ── Configuration ──────────────────────────────────────────────────────────
const PORT = parseInt(process.argv.find((_, i, a) => a[i - 1] === '--port')) || 3737;
const DOWNLOAD_DIR = process.argv.find((_, i, a) => a[i - 1] === '--dir') || path.join(os.homedir(), 'Downloads', 'cine-cli');
const MAX_CONCURRENT = 5;

// ── App Setup ──────────────────────────────────────────────────────────────
const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: { origin: '*' },
});

const client = new WebTorrent();
const torrents = new Map(); // infoHash -> { torrent, meta }

// Ensure download directory exists
fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });

// ── Middleware ──────────────────────────────────────────────────────────────
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ── API Routes ─────────────────────────────────────────────────────────────

// Serve the main page
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Add a torrent via magnet link
app.post('/api/add', async (req, res) => {
  const { magnet } = req.body;

  if (!magnet || typeof magnet !== 'string') {
    return res.status(400).json({ error: 'Missing or invalid magnet link' });
  }

  // Validate magnet link format
  const magnetRegex = /magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}/;
  if (!magnetRegex.test(magnet)) {
    return res.status(400).json({ error: 'Invalid magnet link format' });
  }

  // Check if already downloading
  const infoHash = magnet.match(/btih:([a-fA-F0-9]{32,40})/)?.[1]?.toLowerCase();
  if (infoHash && torrents.has(infoHash)) {
    return res.status(409).json({ error: 'Torrent already added', infoHash });
  }

  // Check concurrent limit
  if (torrents.size >= MAX_CONCURRENT) {
    return res.status(429).json({ error: `Max ${MAX_CONCURRENT} concurrent downloads` });
  }

  try {
    const torrent = client.add(magnet, { path: DOWNLOAD_DIR });

    torrents.set(torrent.infoHash, {
      torrent,
      meta: {
        name: torrent.name || 'Loading...',
        infoHash: torrent.infoHash,
        addedAt: Date.now(),
      },
    });

    // Wait for metadata or timeout
    const metaPromise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Metadata timeout')), 30000);
      torrent.on('metadata', () => {
        clearTimeout(timeout);
        resolve();
      });
      torrent.on('error', (err) => {
        clearTimeout(timeout);
        reject(err);
      });
    });

    try {
      await metaPromise;
    } catch {
      // Still return success — metadata might come later
    }

    const meta = torrents.get(torrent.infoHash)?.meta;
    if (meta) {
      meta.name = torrent.name || 'Unknown';
      meta.size = torrent.length;
    }

    console.log(`[ADD] ${torrent.name || infoHash} (${torrent.infoHash})`);

    res.json({
      success: true,
      infoHash: torrent.infoHash,
      name: torrent.name || 'Loading...',
    });
  } catch (err) {
    console.error(`[ERROR] Failed to add torrent: ${err.message}`);
    res.status(500).json({ error: `Failed to add torrent: ${err.message}` });
  }
});

// List all torrents
app.get('/api/torrents', (req, res) => {
  const list = [];
  for (const [infoHash, { torrent, meta }] of torrents) {
    list.push({
      infoHash,
      name: meta.name,
      size: torrent.length,
      progress: torrent.progress,
      downloadSpeed: torrent.downloadSpeed,
      uploadSpeed: torrent.uploadSpeed,
      numPeers: torrent.numPeers,
      timeRemaining: torrent.timeRemaining,
      done: torrent.done,
      paused: torrent.paused,
    });
  }
  res.json(list);
});

// Pause a torrent
app.post('/api/pause/:infoHash', (req, res) => {
  const { infoHash } = req.params;
  const entry = torrents.get(infoHash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'Torrent not found' });
  entry.torrent.pause();
  res.json({ success: true });
});

// Resume a torrent
app.post('/api/resume/:infoHash', (req, res) => {
  const { infoHash } = req.params;
  const entry = torrents.get(infoHash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'Torrent not found' });
  entry.torrent.resume();
  res.json({ success: true });
});

// Remove a torrent
app.post('/api/remove/:infoHash', (req, res) => {
  const { infoHash } = req.params;
  const entry = torrents.get(infoHash.toLowerCase());
  if (!entry) return res.status(404).json({ error: 'Torrent not found' });
  entry.torrent.destroy();
  torrents.delete(infoHash.toLowerCase());
  res.json({ success: true });
});

// ── Socket.io ──────────────────────────────────────────────────────────────

io.on('connection', (socket) => {
  console.log(`[SOCKET] Client connected: ${socket.id}`);

  // Send current state on connect
  const list = [];
  for (const [infoHash, { torrent, meta }] of torrents) {
    list.push(buildTorrentPayload(torrent, meta));
  }
  socket.emit('torrent-list', list);

  socket.on('disconnect', () => {
    console.log(`[SOCKET] Client disconnected: ${socket.id}`);
  });
});

function buildTorrentPayload(torrent, meta) {
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

// Broadcast updates every second
setInterval(() => {
  if (torrents.size === 0) return;

  const updates = [];
  for (const [infoHash, { torrent, meta }] of torrents) {
    // Update meta
    if (torrent.name && meta.name !== torrent.name) {
      meta.name = torrent.name;
    }
    updates.push(buildTorrentPayload(torrent, meta));

    // Clean up completed torrents after 5 minutes
    if (torrent.done && Date.now() - meta.addedAt > 300000) {
      torrents.delete(infoHash);
    }
  }

  io.emit('torrent-update', updates);
}, 1000);

// ── Graceful Shutdown ──────────────────────────────────────────────────────
function shutdown() {
  console.log('\n[SHUTDOWN] Destroying torrents...');
  for (const [infoHash, { torrent }] of torrents) {
    torrent.destroy();
  }
  httpServer.close(() => {
    console.log('[SHUTDOWN] Server closed');
    process.exit(0);
  });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// ── Start Server ───────────────────────────────────────────────────────────
httpServer.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('  ╔══════════════════════════════════════════════════╗');
  console.log('  ║       cine-cli Torrent Web Downloader            ║');
  console.log('  ╠══════════════════════════════════════════════════╣');
  console.log(`  ║  URL:    http://localhost:${PORT}                   ║`);
  console.log(`  ║  Dir:    ${DOWNLOAD_DIR}`);
  console.log('  ╚══════════════════════════════════════════════════╝');
  console.log('');
  console.log('  Open the URL in your browser to start downloading.');
  console.log('  Press Ctrl+C to stop.');
  console.log('');
});

module.exports = { app, httpServer, io, client, torrents };
