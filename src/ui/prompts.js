/**
 * Prompt helpers — search input, select pickers.
 *
 * Prefers @clack/prompts for selects: it handles raw-mode, term escape codes,
 * partial-line redrawing, and cancellation uniformly. fzf is great for
 * power users but only safe in real PTYs (xterm.js-backed panes can cause
 * it to die immediately with no selection), so we use it as an optional
 * enhancement via `FZF_PICKER=1` or when an explicit `--fzf` flag passes.
 */

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import * as p from '@clack/prompts';

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
 * Whether to use fzf for selects. Default: NEVER — clack.prompts is more
 * reliable across terminal panes (Hermes's embedded xterm.js, VSCode
 * terminal, etc.). fzf is great in real PTYs but its pipe-mode runtime
 * often exits with no selection when the host terminal is shimmed, which
 * is what produced the false "cancelled" loop in the screenshot.
 *
 * Opt-in: set `FZF_PICKER=1` or pass `--fzf`. Even then we still fall back
 * to clack if fzf dies without selecting.
 */
function preferFzf() {
  return process.env.FZF_PICKER === '1' && hasFzf() && !!process.stdin.isTTY;
}

/**
 * textSearch — prompt for a free-form search string.
 */
export async function textSearch({ message, defaultValue = '', placeholder } = {}) {
  const value = await p.text({
    message,
    defaultValue,
    placeholder,
  });
  if (p.isCancel(value)) return null;
  return String(value || '').trim();
}

/**
 * confirm — yes/no confirm.
 */
export async function confirm({ message, initialValue = true }) {
  const value = await p.confirm({ message, initialValue });
  if (p.isCancel(value)) return null;
  return !!value;
}

/**
 * Unwrap a clack select. If the user cancels, returns the default value
 * (first item). If they actually chose something, returns the choice.
 */
async function runSelect({ message, items, defaultIndex = 0 }) {
  const choice = await p.select({
    message,
    options: items.map((it) => ({
      label: it.label,
      value: it.value,
      hint: it.hint,
    })),
    initialValue: items[defaultIndex]?.value,
  });
  if (p.isCancel(choice)) return items[defaultIndex]?.value ?? null;
  return choice;
}

/**
 * Provider picker. Falls back to the default if cancelled — Cancelling
 * a provider picker is rarely what the user wanted; they probably hit Esc
 * instinctively.
 */
export async function selectProvider({ message, items, defaultIndex = 0 }) {
  if (!items.length) return null;
  if (preferFzf()) {
    const value = pickWithFzf(message, items, defaultIndex);
    if (value !== null) return value;
  }
  return runSelect({ message, items, defaultIndex });
}

/**
 * Search-result picker. Same cancel-falls-back-to-default behaviour.
 */
export async function pickResult({ message, items, defaultIndex = 0 }) {
  if (!items.length) return null;
  if (preferFzf()) {
    const value = pickWithFzf(message, items, defaultIndex);
    if (value !== null) return value;
  }
  return runSelect({ message, items, defaultIndex });
}

/**
 * pickNumber — small numeric picker (season/episode).
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
 * pickWithFzf — runs fzf in pipe mode with our candidates fed on stdin,
 * and reads the highlighted line from stdout.
 *
 * fzf assumes real PTY semantics for both the parent process and its own
 * child; CR-based cursor redrawing from xterm.js-shimmed panes can cause
 * fzf to void the selection. We don't expose this by default — `FZF_PICKER=1`
 * opts in.
 */
function pickWithFzf(message, items) {
  return new Promise((resolve) => {
    const lines = items.map((it) => it.hint ? `${it.label} — ${it.hint}` : it.label);

    const proc = spawn('fzf', [
      '--reverse',
      '--no-sort',
      '--height', '40%',
      '--prompt', `${message} › `,
      '--header', `${items.length} options · enter accept · esc cancel`,
      '--bind', 'start:up',           // start on the highlighted (top) line
      '--bind', 'enter:accept-non-empty',
      '--print0',                       // null-separated output to avoid trailing-newline issues
    ], { stdio: ['pipe', 'pipe', 'pipe'] });

    let out = '';
    proc.stdout.on('data', (chunk) => { out += chunk.toString(); });
    proc.stderr.on('data', () => {}); // swallow fzf's terminal noise
    proc.on('error', () => resolve(null));
    proc.on('close', (code) => {
      if (code !== 0) return resolve(null);
      const picked = out.toString().replace(/\0+$/, '').trim();
      if (!picked) return resolve(null);
      // match prefix-tolerant in case of chop
      const idx = lines.findIndex((l) => l === picked || l.startsWith(picked));
      if (idx === -1) return resolve(null);
      resolve(items[idx].value);
    });

    proc.stdin.on('error', () => {});
    proc.stdin.write(lines.join('\n') + '\n');
    proc.stdin.end();
  });
}
