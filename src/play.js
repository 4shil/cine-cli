/**
 * play.js — open the resolved URL in the platform-native browser.
 *
 * No emoji progress bars, no subprocess noise. Just clean open + report.
 */

import { theme, sym, kv } from './ui/theme.js';

function openUrl(url) {
  const cmd = process.platform === 'darwin' ? 'open'
    : process.platform === 'win32' ? 'cmd' : 'xdg-open';
  const args = process.platform === 'win32'
    ? ['/c', 'start', '', url] : [url];
  try {
    const child = spawn(cmd, args, { detached: true, stdio: 'ignore', windowsHide: true });
    child.unref();
  } catch (_err) { /* best-effort */ }
}

export async function playInBrowser({ url, title, providerName }) {
  console.log('');
  console.log(`  ${theme.cold('┌──')}`);
  console.log(`  ${theme.cold('│')}  ${theme.cold(sym.play)} ${theme.brand.bold(title || 'Now playing')}`);
  console.log(`  ${theme.cold('│')}`);
  console.log(`  ${theme.cold('│')}  ${kv('source', providerName)}`);
  console.log(`  ${theme.cold('│')}`);
  console.log(`  ${theme.cold('│')}  ${theme.dim('url')}`);
  console.log(`  ${theme.cold('│')}    ${theme.dim(url)}`);
  console.log(`  ${theme.cold('└──')}`);
  console.log('');

  openUrl(url);
  return true;
}
