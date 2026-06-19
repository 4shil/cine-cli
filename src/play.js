/**
 * play.js — open the resolved URL in the platform-native browser.
 *
 * No emoji progress bars, no subprocess noise. Just clean open + report.
 */

import open from 'open';
import { theme, sym, kv } from './ui/theme.js';

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

  try {
    await open(url, { wait: false });
    return true;
  } catch (err) {
    console.error(`  ${theme.error(sym.cross)} ${theme.fg('failed to open browser')}`);
    console.error(`  ${theme.dim(err.message)}`);
    return false;
  }
}
