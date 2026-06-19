/**
 * Banner — the new welcome screen.
 *
 * Clean monochrome logo with a brand-gradient "cine" wordmark,
 * a status row, no greetings, no tips, no vibes.
 */

import { theme, sym, hr } from './theme.js';

const LOGO_LINES = [
  '   ▄████▄ ',
  '  ██▀  ▀██',
  '  ██    ██',
  '  ██    ██',
  '  ██▄  ▄██',
  '   ▀████▀ ',
];

/**
 * Renders the compact logo alongside a graceful wordmark,
 * strictly inside width columns.
 */
function wordmark(gradient) {
  // "cine" styled with the brand gradient
  return gradient('cine');
}

function tagline(msg) {
  // clean subtitle: just version + a flat feature tag
  return [theme.mute('stream') + theme.dim(' · '), theme.mute('scrape') + theme.dim(' · '), theme.mute('play')]
    .map((tag, i, arr) => (i === arr.length - 1 ? tag : tag))
    .map((tag, i) => (i === 2 ? theme.cold(tag) : tag))
    .join('');
}

/**
 * Show banner.
 * @param {object} opts
 * @param {string} opts.version
 * @param {string|null} opts.platform        - 'Linux' | 'Darwin' | ...
 * @param {boolean} opts.interactive         - are we in a tty?
 */
export function showBanner({ version, platform, interactive }) {
  const lines = [];

  // Top bar
  lines.push('');
  lines.push(`  ${theme.cold(sym.bracketL)} ${wordmark(theme.gradient)} ${theme.cold(sym.pipe)} ${theme.dim('v' + version)} ${theme.mute(sym.pipe)} ${theme.mute('node')} ${theme.dim(process.versions.node)} ${theme.cold(sym.bracketR)}`);

  // Compact logo on the left, padding wordmark on the right
  for (const line of LOGO_LINES) {
    lines.push(`  ${theme.cold(line)}`);
  }

  // Status row — flat, one line
  const statusParts = [
    `${theme.dim('platform')}  ${theme.cold(platform ?? 'unknown')}`,
    `${theme.dim('player')}     ${theme.cold('browser')}`,
    `${theme.dim('sources')}    ${theme.cold('TMDB + 6 providers')}`,
    interactive ? `${theme.ok(sym.check)} ${theme.dim('interactive')}` : `${theme.warn(sym.bullet)} ${theme.dim('non-interactive')}`,
  ];
  lines.push('');
  lines.push(`  ${hr(72, '─')}`);
  for (const sp of statusParts) {
    lines.push(`  ${sp}`);
  }
  lines.push(`  ${hr(72, '─')}`);

  // Tiny hint row — commands
  lines.push('');
  lines.push(`  ${theme.cold(sym.arrow)} ${theme.fg('Search')}    ${theme.mute('cine')} ${theme.dim('"inception"')}`);
  lines.push(`  ${theme.cold(sym.arrow)} ${theme.fg('TV show')}   ${theme.mute('cine')} ${theme.dim('"breaking bad" -e 5:1')}`);
  lines.push(`  ${theme.cold(sym.arrow)} ${theme.fg('Torrent')}   ${theme.mute('cine')} ${theme.dim('"matrix" --download')}`);
  lines.push('');

  // eslint-disable-next-line no-console
  console.log(lines.join('\n'));
}

/**
 * showSearchHeader — minimal hero shown while typing.
 */
export function showSearchHeader(query) {
  const trimmed = query.trim() || '...';
  const padded = trimmed.length > 40 ? trimmed.slice(0, 37) + '...' : trimmed;
  return `  ${theme.cold(sym.arrow)} ${theme.dim('searching')} ${theme.fg.bold(padded)}`;
}

/**
 * showResultCount — small one-liner above the result list.
 */
export function showResultCount(n) {
  const word = n === 1 ? 'result' : 'results';
  return `  ${theme.cold(sym.dot)} ${theme.dim(n)} ${theme.mute(word)}`;
}
