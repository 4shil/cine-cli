<p align="center">
  <a href="https://github.com/4shil/cine-cli"><img src="https://img.shields.io/badge/project-cine--cli-magenta?style=for-the-badge&logo=github" alt="Project"></a>
  <a href="https://nodejs.org"><img src="https://img.shields.io/badge/node-%E2%89%A5%2018-green?style=for-the-badge&logo=node.js" alt="Node Version"></a>
  <a href="https://github.com/4shil/cine-cli/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License"></a>
</p>

<h1 align="center">cine-cli</h1>

<p align="center">
  <strong>Watch anything from your terminal. Browser-first, multi-provider, torrent web UI — one shot.</strong>
</p>

```
cine "inception"
cine "breaking bad" -e 5:1
cine "matrix" --download
```

Browser-first. Finds via TMDB, streams via 6 embed providers. Torrent mode boots a self-hosted WebTorrent web UI on `localhost:3737` and opens it in your browser.

## Install

```bash
npm install -g cine-cli
```

> Requires **Node ≥ 18** and a modern browser. `xdg-open` (Linux), `open` (macOS), or `cmd /c start` (Windows) for handoff.

## Usage

```
cine [query] [options]

  -e, --episode <ep>     Format `episode:season` or just `episode` (TV only)  e.g. 5:1 or 5
  -c, --choice <n>       Auto-select a search result (1-based) and skip the picker
  -d, --download         Open the embedded torrent web UI instead of streaming
  -p, --player <name>    Override the auto-detected browser (xdg-open/open/cmd)
      --provider <id>    Skip the provider picker, use this provider id directly
      --list-providers   Print every provider and exit
      --no-banner        Skip the welcome screen
      --no-color         Disable colour output
      --smoke            Run full flow in non-interactive mode (no browser open)
  -U, --update           Update cine-cli to the latest version
  -V, --version
```

### Examples

```bash
# Movie
cine inception

# TV series, specific episode (S05E01)
cine "breaking bad" -e 1:5

# Auto-pick first result and first provider (for scripts)
cine "inception" -c 1 --provider vidsrc

# Torrent flow — opens web UI, prefilled with the magnet
cine "matrix" --download
```

## How it works

```
query ── TMDB (multi-search) ── imdb_id ── providers ── pick ── xdg-open ──▶  browser

                                                    └─── --download ──▶  torrent web ui (localhost:3737)
```

Six providers ship out of the box:

| id         | upstream         |
| ---------- | ---------------- |
| vidsrc     | vidsrc.to        |
| vidking    | vidking.net      |
| vidlink    | vidlink.pro      |
| vidsync    | vidsync.live     |
| cinesrc    | cinesrc.st       |
| lordflix   | lordflix.org     |

Providers are pure URL templates over IMDb IDs — adding a new one is a one-line append in `src/providers.js`.

### Torrent mode

`--download` flips the terminal output into the torrent flow. We hit the public torrentio API, sort by seeders, and the highest-quality torrent is picked. A Node.js WebTorrent server is spawned (no telnet, no subprocess weirdness — same process tree), listening on `127.0.0.1:3737`, and your default browser is opened with the magnet preloaded.

The web UI supports multiple concurrent downloads (`MAX_CONCURRENT = 5` by default), pause/resume/remove, and live Socket.io updates. No login, no tracking.

## Architecture

```
src/
├── cli.js               commander parser + flow orchestration
├── tmdb.js              thin TMDB client (multi-search + external_ids)
├── providers.js         provider templates → URL builder
├── scraper.js           search formatting + provider resolution
├── play.js              xdg-open handoff
├── torrent/
│   ├── index.js         torrentio fetch + sort by seeders
│   └── server.mjs       embedded WebTorrent server (subservice)
└── ui/
    ├── theme.js         color palette, gradients, panels
    ├── banner.js        welcome screen
    ├── spinner.js       @clack spinner (TTY-only, no-op elsewhere)
    └── prompts.js       search input + provider picker (fzf when available, clack fallback)

public/
└── index.html           torrent runtime UI shell
└── styles.css           terminal-style themes + tokens (dark / light)
└── app.js               GSAP-driven UI + socket.io realtime stream
```

Pure Node.js + native `fetch` from undici. No bundler, no transpilation, single `package.json`.

## Dependencies

Runtime:
- [`@clack/prompts`](https://github.com/bombshell-dev/clack) — modern input prompts
- [`chalk`](https://github.com/chalk/chalk) — terminal colour (level-3 24-bit)
- [`commander`](https://github.com/tj/commander) — argv parser
- [`express`](https://expressjs.com), [`socket.io`](https://socket.io) — torrent web server
- [`webtorrent`](https://webtorrent.io) — peer-to-peer torrent client (browser-side, ships in the page)
- [`gradient-string`](https://github.com/bokub/gradient-string) — banner brand gradient
- [`open`](https://github.com/sindresorhus/open) — cross-platform browser launcher
- [`undici`](https://github.com/nodejs/undici) — fast HTTP client for the TMDB API

External tools (peer):
- `fzf` (optional) — uses it for every picker when present, falls back to `@clack/prompts` otherwise
- `xdg-open` / `open` / `cmd /c start` — for the browser handoff
- Web browser — any modern browser, since torrent streaming runs in-browser

## Inspiration & Credits

This project is heavily inspired by:
- [ani-cli](https://github.com/pystardust/ani-cli) — the ultimate CLI tool to browse and stream anime.
- [mov-cli](https://github.com/mov-cli/mov-cli) — the modular movie scraper CLI.

## License

MIT
