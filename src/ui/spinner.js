/**
 * Spinner — thin wrapper around @clack/prompts spinner.
 *
 * In a non-TTY, we silently just print a one-shot message and finish.
 */

import { spinner as clackSpinner } from '@clack/prompts';

/** No-op fallback for non-TTY. */
const NullSp = {
  update() {},
  stop() {},
  cancel() {},
};

export function makeSpinner(startMessage) {
  if (!process.stdout.isTTY) {
    process.stdout.write(`  ${startMessage}\n`);
    return NullSp;
  }
  const s = clackSpinner({ indicator: 'dots' });
  s.start(startMessage);
  return {
    update(msg) {
      s.message = msg;
    },
    stop(msg, code = 0) {
      if (msg) process.stdout.write(`  ${msg}\n`);
      s.stop(msg, code);
    },
    cancel(msg) {
      if (msg) process.stdout.write(`  ${msg}\n`);
      s.cancel(msg);
    },
  };
}

