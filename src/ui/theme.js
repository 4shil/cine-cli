/**
 * Theme — clean modern palette using chalk + gradient-string.
 *
 * No "good morning", no random_tips. Just a coherent color system.
 */

import chalk from 'chalk';
import gradient from 'gradient-string';

const palette = {
  brand: '#7C3AED',     // violet
  brandHot: '#EC4899',  // pink
  brandCold: '#22D3EE', // cyan
  fg: '#E4E4F1',
  dim: '#8B8BA7',
  mute: '#4B4B66',
  warn: '#F59E0B',
  error: '#EF4444',
  success: '#22C55E',
  border: '#3A3A55',
  bg: '#11111A',
  surface: '#181826',
};

chalk.level = 3; // 24-bit colors

const brand = gradient(['#7C3AED', '#EC4899', '#22D3EE']);

export const theme = {
  ...palette,
  chalk,
  gradient: brand,

  // Semantic helpers
  brand: chalk.hex(palette.brand),
  hot: chalk.hex(palette.brandHot),
  cold: chalk.hex(palette.brandCold),
  fg: chalk.hex(palette.fg),
  dim: chalk.hex(palette.dim),
  mute: chalk.hex(palette.mute),
  warn: chalk.hex(palette.warn),
  error: chalk.hex(palette.error),
  ok: chalk.hex(palette.success),
  border: chalk.hex(palette.border),
  surface: chalk.hex(palette.surface),
  bg: chalk.hex(palette.bg),
};

export const c = theme;

/**
 * Symbols — thin, line-drawn. No emojis that render unpredictably across terminals.
 */
export const sym = {
  bullet: '•',
  arrow: '›',
  check: '✓',
  cross: '✗',
  play: '▶',
  bracketL: '╭',
  bracketR: '╰',
  pipe: '│',
  dash: '─',
  dot: '·',
  star: '★',
  down: '▼',
  up: '▲',
};

/**
 * Box drawing — single line, rounded. Width-aware.
 */
export function hr(width = 60, char = '─') {
  return theme.mute(char.repeat(width));
}

export function heading(text, options = {}) {
  const { width = 60 } = options;
  const textWidth = text.length;
  const sideWidth = Math.max(1, Math.floor((width - textWidth - 4) / 2));
  const line = '─'.repeat(sideWidth);
  const left = `${line}  `;
  const right = `  ${line}`;
  if (textWidth + left.length + right.length > width) {
    return `${theme.cold(left)}${brand(text)}${theme.cold(right)}`;
  }
  return `${theme.cold(left)}${brand.bold(text)}${theme.cold(right)}`;
}

/**
 * panel — thin rounded box with brand gradient border + dimmed body.
 * body can be a string (single line) or an array (multi-line).
 */
export function panel(label, body, options = {}) {
  const { width = 60 } = options;
  const top = `${theme.cold('╭')} ${brand(label)} ${theme.cold('─'.repeat(Math.max(1, width - label.length - 4)))}╮`;
  const bottom = theme.cold(`╰${'─'.repeat(width - 2)}╯`);
  const lines = (Array.isArray(body) ? body : [body]).map((line) =>
    `${theme.cold('│')}  ${theme.fg(line)}  ${theme.cold('│')}`,
  );
  return [top, ...lines, bottom].join('\n');
}

/**
 * kv — render a key: value pair aligned with subtle dimming on the key.
 */
export function kv(key, value, options = {}) {
  const { keyWidth = 14 } = options;
  const padded = String(key).padEnd(keyWidth, ' ');
  return `  ${theme.dim(padded)} ${theme.cold(sym.arrow)}  ${theme.fg(value)}`;
}

/**
 * list — minimal bullet list with brand-colored bullets.
 */
export function list(items, options = {}) {
  const { bullet = sym.bullet, indent = '  ' } = options;
  return items
    .map((text, i) => {
      const tag = theme.hot(`${indent}${bullet}`);
      const sep = theme.mute(sym.arrow);
      return `${tag} ${theme.fg(text)}`;
    })
    .join('\n');
}
