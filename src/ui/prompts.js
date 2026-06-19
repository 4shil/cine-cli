/**
 * Prompt helpers — search input, select pickers.
 *
 * Uses @clack/prompts for inputs/text, and prefers fzf for selects
 * (visual maturity) with a clack fallback when fzf is missing or the
 * process is non-interactive.
 */

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import * as p from '@clack/prompts';

import { theme } from './theme.js';

let _hasFzf = null;
export function hasFzf() {
  if (_hasFzf !== null) return _hasFzf;
  try {
    _hasFzf = existsSync(execFileSync('which', ['fzf']).toString().trim());
  } catch {
    _hasFzf = false;
  }
  return _hasFzf;
}

/**
 * textSearch — prompt for a free-form search string with a default value.
 */
export async function textSearch({ message, defaultValue = '', placeholder } = {}) {
  const value = await p.text({
    message,
    defaultValue,
    placeholder,
  });
  if (p.isCancel(value)) {
    return null;
  }
  return String(value || '').trim();
}

/**
 * confirm — yes/no confirm with cool default.
 */
export async function confirm({ message, initialValue = true }) {
  const value = await p.confirm({ message, initialValue });
  if (p.isCancel(value)) return null;
  return !!value;
}

/**
 * selectServer — provider picker with highlighting.
 * items: [{ label, hint?, value }]
 */
export async function selectProvider({ message, items, defaultIndex = 0 }) {
  if (!items.length) return null;

  if (hasFzf() && process.stdin.isTTY) {
    const value = pickWithFzf(message, items, defaultIndex);
    if (value !== null) return value;
    // fall through to clack if user cancelled
  }

  const choice = await p.select({
    message,
    options: items.map((it) => ({
      label: it.label,
      value: it.value,
      hint: it.hint,
    })),
    initialValue: items[defaultIndex]?.value,
  });

  if (p.isCancel(choice)) return null;
  return choice;
}

/**
 * pickResult — search-result picker with type hints.
 */
export async function pickResult({ message, items, defaultIndex = 0 }) {
  if (!items.length) return null;

  if (hasFzf() && process.stdin.isTTY) {
    const value = pickWithFzf(message, items, defaultIndex);
    if (value !== null) return value;
  }

  const choice = await p.select({
    message,
    options: items.map((it) => ({
      label: it.label,
      value: it.value,
      hint: it.hint,
    })),
    initialValue: items[defaultIndex]?.value,
  });
  if (p.isCancel(choice)) return null;
  return choice;
}

/**
 * pickNumber — small numeric picker (e.g. season/episode).
 */
export async function pickNumber({ message, min, max, defaultValue }) {
  const def = clamp(defaultValue ?? min, min, max);
  const v = await p.text({
    message,
    defaultValue: String(def),
    validate: (s) => {
      const n = Number(s);
      if (!Number.isInteger(n) || n < min || n > max) {
        return `Enter an integer in [${min}, ${max}].`;
      }
      return undefined;
    },
  });
  if (p.isCancel(v)) return null;
  return Number(v);
}

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n));
}

/**
 * pickWithFzf — runs fzf with formatted lines and returns the matched value.
 * items need { label, value, hint? }.
 *
 * Returns null when fzf is cancelled (Esc) or no match.
 */
function pickWithFzf(message, items, defaultIndex = 0) {
  return new Promise((resolve) => {
    const lines = items.map((it, i) => it.hint ? `${it.label} — ${it.hint}` : it.label);
    const proc = spawn('fzf', [
      '--reverse',
      '--cycle',
      '--prompt', `${message} › `,
      '--no-sort',
      '--height', '40%',
      '--info', 'inline',
      '--header', `[ ${items.length} options · Enter to select · Esc to cancel ]`,
    ], { stdio: ['pipe', 'pipe', 'inherit'] });

    let out = '';
    proc.stdout.on('data', (chunk) => { out += chunk.toString(); });
    proc.on('error', () => resolve(null));
    proc.on('close', (code) => {
      if (code !== 0) return resolve(null);
      const picked = out.toString().trim();
      if (!picked) return resolve(null);
      const idx = lines.findIndex((l) => l === picked);
      if (idx === -1) return resolve(null);
      resolve(items[idx].value);
    });

    proc.stdin.write(lines.join('\n') + '\n');
    proc.stdin.end();
  });
}
