/**
 * scraper.js — orchestrates search → episode → provider → play.
 */

import { multiSearch, ensureImdbId } from './tmdb.js';
import { buildAllProviders } from './providers.js';
import { theme, sym } from './ui/theme.js';

/**
 * Search & format the result list for UI consumption.
 */
export async function searchAll(query, { limit = 12 } = {}) {
  const items = await multiSearch(query, { limit });
  return items.map((it) => {
    const year = it.year ? theme.dim(`(${it.year})`) : '';
    const type = it.type === 'movie' ? theme.cold('movie') : theme.hot('series');
    const imdb = it.imdbId ? theme.dim(`${sym.dot} ${it.imdbId}`) : '';
    const label = `${it.title}  ${year}`;
    const hint = `${type}  ${imdb}`.trim();
    return { item: it, label, hint };
  });
}

/**
 * Resolve IMDb ID, return provider list for the chosen media.
 */
export async function resolveProviders(item, { type, season, episode }) {
  const imdbId = item.imdbId || (await ensureImdbId(item));
  if (!imdbId) return null;
  const providers = buildAllProviders({
    imdbId,
    type,
    season,
    episode,
  });
  return { imdbId, providers };
}
