#!/usr/bin/env node
/**
 * ciné — main entry.
 *
 * commander parses argv; the orchestrator below does the heavy lifting:
 *   search  →  pick result  →  episode (if tv)  →  pick provider  →  play | torrent
 */

import { Command } from 'commander';
import process from 'node:process';
import os from 'node:os';

import { showBanner, showSearchHeader } from './ui/banner.js';
import { theme, sym } from './ui/theme.js';
import { makeSpinner } from './ui/spinner.js';
import { textSearch, selectProvider, pickResult, pickNumber, hasFzf } from './ui/prompts.js';
import { searchAll, resolveProviders } from './scraper.js';
import { playInBrowser } from './play.js';
import { fetchStreams, startTorrentWebServerAndOpen } from './torrent/index.js';
import { ensureImdbId } from './tmdb.js';

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(resolve(__dirname, '..', 'package.json'), 'utf-8'));
const VERSION = pkg.version;

const program = new Command();

program
  .name('cine')
  .description('Watch anything from your terminal. Browser-first. Multi-provider. Torrent web.')
  .version(VERSION);

program
  .argument('[query...]', 'Search query — title of a movie or TV show')
  .option('-e, --episode <ep>', 'Format `episode:season` or just `episode` (TV only)', null)
  .option('-c, --choice <n>', 'Auto-select result index (1-based) and skip prompt')
  .option('-d, --download', 'Open torrent web downloader instead of streaming in browser')
  .option('-p, --player <name>', 'Override player (browser default)')
  .option('--port <n>', 'Override the torrent web server port (default 3737)', (v) => parseInt(v, 10), 3737)
  .option('--no-banner', 'Skip the welcome banner')
  .option('--no-color', 'Disable colour output')
  .option('--provider <id>', 'Skip provider picker, use this provider id directly')
  .option('--list-providers', 'Print known providers and exit')
  .option('--smoke', 'Run full flow in non-interactive mode without spawning a browser (verification)')
  .option('--fzf', 'Use fzf for picker UIs (off by default — @clack/prompts is more reliable)')
  .action(async (queryParts, opts) => {
    // Honour --fzf flag by setting the opt-in env var.
    if (opts.fzf) process.env.FZF_PICKER = '1';
    if (opts.color === false) {
      theme.chalk.level = 0;
    }

    // Auto-pick everything when non-interactive (fzf path already handles this
    // cleanly, but we also need to skip the result picker, episode picker, and
    // provider spinner if there's no TTY).
    const isTTY = !!process.stdin.isTTY;

    if (opts.listProviders) {
      const { PROVIDERS } = await import('./providers.js');
      console.log('');
      for (const p of PROVIDERS) {
        console.log(`  ${theme.hot('·')}  ${theme.fg.bold(p.id.padEnd(10))} ${theme.dim('→')} ${theme.cold(p.name)}  ${theme.dim('priority ' + p.priority)}`);
      }
      console.log('');
      return;
    }

    if (isTTY && opts.banner !== false) {
      showBanner({ version: VERSION, platform: os.platform(), interactive: true });
    } else {
      console.log('');
    }

    let query = (queryParts || []).join(' ').trim();
    if (!query) {
      const out = await textSearch({
        message: 'What are you looking for',
        placeholder: 'e.g. inception',
      });
      if (!out) return gracefulExit('cancelled');
      query = out;
    }

    await runFlow(query, opts, { isTTY });
  });

program.parseAsync(process.argv).catch((err) => {
  console.error(`\n  ${theme.error(sym.cross)} ${theme.fg(err.message || err)}\n`);
  process.exit(1);
});

/**
 * The actual flow — single source of truth for streaming + torrent paths.
 */
async function runFlow(query, opts, { isTTY }) {
  console.log('');
  console.log(showSearchHeader(query));
  console.log('');

  const spin = makeSpinner(theme.dim('searching TMDB'));
  let results;
  try {
    results = await searchAll(query, { limit: 12 });
    spin.stop(theme.dim(`${results.length} matches`));
  } catch (err) {
    spin.cancel(theme.error('search failed'));
    console.error(`  ${theme.dim(err.message)}`);
    process.exit(1);
  }
  if (!results.length) {
    console.log(`  ${theme.warn(sym.bullet)} ${theme.fg('no matches.')}  ${theme.dim('try a different query.')}`);
    return;
  }
  // No second "X results" line — the spinner already subtitled that.

  // Pick a result.
  let pickedIdx = null;
  if (opts.choice) {
    const n = Number(opts.choice);
    if (Number.isInteger(n) && n >= 1 && n <= results.length) {
      pickedIdx = n - 1;
    }
  }
  if (pickedIdx === null && !isTTY) {
    // Non-interactive: auto-pick first result.
    pickedIdx = 0;
  }
  if (pickedIdx === null) {
    const items = results.map((r, i) => ({
      label: `${(i + 1).toString().padStart(2, ' ')}. ${r.label}`,
      value: i,
      hint: r.hint,
    }));
    const chosen = await pickResult({ message: 'pick a result', items, defaultIndex: 0 });
    if (chosen === null) return gracefulExit('cancelled');
    pickedIdx = Number(chosen);
  }

  const result = results[pickedIdx];
  const item = result.item;

  // Episode (TV only).
  let season = 1, episode = 1;
  if (item.type === 'tv') {
    const ep = parseEpisodeArg(opts.episode);
    if (ep) {
      season = ep.season; episode = ep.episode;
    } else if (!isTTY) {
      // Non-interactive: season 1 episode 1.
      season = 1; episode = 1;
    } else {
      console.log('');
      const s = await pickNumber({ message: 'season',  min: 1, max: 99, defaultValue: 1 });
      if (s === null) return gracefulExit('cancelled');
      const e = await pickNumber({ message: 'episode', min: 1, max: 999, defaultValue: 1 });
      if (e === null) return gracefulExit('cancelled');
      season = s; episode = e;
    }
  }

  // Resolve IMDb ID + provider URLs.
  const spin2 = makeSpinner(theme.dim('resolving providers'));
  let resolved;
  try {
    resolved = await resolveProviders(item, { type: item.type, season, episode });
    spin2.stop(theme.ok(`${resolved?.providers?.length || 0} providers`));
  } catch (err) {
    spin2.cancel(theme.error('resolve failed'));
    console.error(`  ${theme.dim(err.message)}`);
    process.exit(1);
  }
  if (!resolved || !resolved.providers.length) {
    console.log(`  ${theme.error(sym.cross)} ${theme.fg('no providers available for this title')}`);
    return;
  }

  // Pick a provider.
  let pick = null;
  if (opts.provider) {
    pick = resolved.providers.find((p) => p.id === opts.provider) || resolved.providers[0];
  } else if (resolved.providers.length > 1 && process.stdin.isTTY && !opts.choice) {
    const items = resolved.providers.map((p, i) => ({
      label: theme.fg(`${(i + 1).toString().padStart(2, ' ')}. ${p.name}`),
      value: p,
      hint: theme.dim(safeHost(p.url)),
    }));
    pick = await selectProvider({ message: 'choose a server', items, defaultIndex: 0 });
  } else {
    pick = resolved.providers[0];
  }
  if (!pick) return gracefulExit('cancelled');

  // Branch on --download.
  if (opts.download) {
    return runTorrentFlow({ item, resolved, pick }, opts);
  }

  console.log('');
  if (opts.smoke) {
    console.log(`  ${theme.ok(sym.check)} ${theme.fg(`would open ${pick.name} · ${pick.url}`)}`);
    return;
  }
  await playInBrowser({
    url: pick.url,
    title: item.title,
    providerName: pick.name,
  });
  if (process.stdin.isTTY) {
    console.log(`  ${theme.dim(sym.dot)} ${theme.dim('press Ctrl+C to exit')}\n`);
  } else {
    console.log(`  ${theme.dim(sym.dot)} ${theme.dim('url above — non-interactive smoke test')}\n`);
  }
}

/**
 * Torrent flow — resolve streams from Torrentio, fzf-pick, start embedded web server.
 */
async function runTorrentFlow({ item, resolved, pick }, opts) {
  const spin = makeSpinner(theme.dim('fetching torrents from torrentio'));
  const imdbId = resolved.imdbId || (await ensureImdbId(item));
  if (!imdbId) {
    spin.cancel(theme.error('no IMDb id'));
    process.exit(1);
  }
  const streams = await fetchStreams({
    imdbId,
    type: item.type,
    season: 1,
    episode: 1,
  });
  spin.stop(theme.ok(`${streams.length} torrents`));

  if (!streams.length) {
    console.log(`  ${theme.warn(sym.bullet)} ${theme.fg('no torrents found for this title')}`);
    return;
  }

  let chosen = null;
  if (process.stdin.isTTY && hasFzf()) {
    const items = streams.map((s, i) => ({
      label: `${(i + 1).toString().padStart(2, ' ')}. ${theme.fg(s.quality.padEnd(6))} ${theme.dim(s.fileSizeLabel().padEnd(8))} ${theme.cold('seeds ' + s.seeders).padEnd(16)} ${theme.dim(s.name.slice(0, 48))}`,
      value: s,
      hint: '',
    }));
    chosen = await selectProvider({ message: 'pick a torrent', items, defaultIndex: 0 });
  } else {
    chosen = streams[0];
  }
  if (!chosen) return gracefulExit('cancelled');

  console.log('');
  console.log(`  ${theme.cold('┌──')}`);
  console.log(`  ${theme.cold('│')}  ${theme.brand.bold(item.title)} ${theme.dim('· torrent web')}`);
  console.log(`  ${theme.cold('│')}  ${theme.dim(String(chosen.quality))} ${theme.dim(sym.dot)} ${theme.dim(String(chosen.fileSizeLabel()))} ${theme.dim(sym.dot)} ${theme.cold('seeds ' + String(chosen.seeders))}`);
  console.log(`  ${theme.cold('└──')}`);
  console.log('');

  if (opts.smoke) {
    console.log(`  ${theme.ok(sym.check)} ${theme.fg(`would start web ui + open magnet for ${chosen.name}`)}`);
    return;
  }

  const { url, port, ready } = await startTorrentWebServerAndOpen({
    magnet: chosen.magnet,
    name: chosen.name,
    port: opts.port ?? 3737,
  });

  if (!ready) {
    console.log('');
    console.log(`  ${theme.error(sym.cross)} ${theme.fg('web ui could not start — all the usual ports are busy.')}`);
    console.log(`  ${theme.dim(sym.dot)} ${theme.dim('try: cine "title" --download --port 4800')}`);
    console.log('');
    return;
  }

  console.log('');
  console.log(`  ${theme.dim(sym.dot)} web ui:    ${theme.cold(`http://127.0.0.1:${port}`)}`);
  console.log(`  ${theme.dim(sym.dot)} downloads: ${theme.dim(process.env.HOME + '/Downloads/cine-cli')}`);
  if (url) console.log(`  ${theme.dim(sym.dot)} magnet:    ${theme.dim(url)}`);
  console.log('');
  console.log(`  ${theme.dim(sym.arrow)} ${theme.dim('press Ctrl+C to stop the server')}`);
  console.log('');

  setInterval(() => {}, 1 << 30); // park the event loop until SIGINT
}

/**
 * Helpers.
 */
function parseEpisodeArg(arg) {
  if (!arg) return null;
  const m = String(arg).match(/^(\d+)(?::(\d+))?$/);
  if (!m) return null;
  if (m[2]) return { episode: Number(m[1]), season: Number(m[2]) };
  return { episode: Number(m[1]), season: 1 };
}

function safeHost(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function gracefulExit(reason) {
  console.log('');
  console.log(`  ${theme.dim(sym.dot)} ${theme.dim(reason)}`);
  console.log('');
  process.exit(0);
}
