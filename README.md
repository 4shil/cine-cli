# cine-cli

Watch anything from your terminal. Browser-first, multi-provider, torrent web UI — one shot.

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

## Security

**Known advisory: [CVE-2024-29415](https://github.com/advisories/GHSA-2p57-rm9w-gvfp) (HIGH) — `ip` SSRF in `isPublic`**

The vulnerable package is `ip@2.0.1`, pulled in transitively via:
`webtorrent → torrent-discovery → bittorrent-tracker → ip@^2.0.0`

cine-cli v5.1.0+ mitigates this by overriding `ip` to `^1.1.9` (pre-CVE, no breakage in the IP-range APIs used by the tracker). The advisory database may still list the advisory for the declared upstream range; the actual installed `ip` version is safe.

`npm audit fix --force` would roll `webtorrent` back to the 0.x API line (a different, deprecated package), which breaks cine-cli's API surface. That suggestion is incorrect for this project and should be ignored.

If you find another issue, please file it at [github.com/4shil/cine-cli/issues](https://github.com/4shil/cine-cli/issues).

## License

MIT
