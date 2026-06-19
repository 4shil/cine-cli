/**
 * TMDB client — search + external_ids lookup.
 *
 * Uses undici's fetch (Node 18+ has native, but undici is faster + cooler
 * headers API). Falls back to the built-in fetch if undici isn't available.
 */

import { fetch } from 'undici';

export const TMDB_API_KEY = '1f54bd990f1cdfb230adb312546d765d';
export const TMDB_BASE = 'https://api.themoviedb.org/3';

const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

/**
 * Low-level GET against TMDB.
 */
export async function tmdbGet(path, params = {}) {
  const url = new URL(`${TMDB_BASE}/${path}`);
  url.searchParams.set('api_key', TMDB_API_KEY);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, { headers: { 'User-Agent': ua } });
  if (!res.ok) {
    throw new Error(`TMDB ${path} → ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Multi search — returns a flattened list of normalized items:
 *   { tmdbId, imdbId, type: 'movie' | 'tv', title, year?, imageUrl? }
 */
export async function multiSearch(query, { limit = 12 } = {}) {
  if (!query) return [];
  const data = await tmdbGet('search/multi', {
    query,
    page: 1,
    language: 'en-US',
    include_adult: 'false',
  });

  const items = [];
  for (const r of data.results || []) {
    if (r.media_type !== 'movie' && r.media_type !== 'tv') continue;
    const tmdbId = String(r.id || '');
    if (!tmdbId) continue;
    let title, year, imdbId;
    if (r.media_type === 'movie') {
      title = r.title || r.original_title || 'Unknown';
      year = (r.release_date || '').slice(0, 4);
    } else {
      title = r.name || r.original_name || 'Unknown';
      year = (r.first_air_date || '').slice(0, 4);
    }
    if (r.imdb_id) {
      imdbId = r.imdb_id;
    } else {
      try {
        const ext = await tmdbGet(`${r.media_type}/${tmdbId}/external_ids`, {});
        imdbId = ext.imdb_id || '';
      } catch {
        imdbId = '';
      }
    }
    const poster = r.poster_path || r.profile_path || '';
    items.push({
      tmdbId,
      imdbId,
      type: r.media_type,
      title,
      year,
      imageUrl: poster ? `https://image.tmdb.org/t/p/w500${poster}` : null,
    });
    if (items.length >= limit) break;
  }
  return items;
}

/**
 * externalIds — fetch IMDb ID for a TMDB ID + media type.
 */
export async function externalIds(tmdbId, mediaType = 'movie') {
  try {
    const d = await tmdbGet(`${mediaType}/${tmdbId}/external_ids`, {});
    return d || {};
  } catch {
    return {};
  }
}

/**
 * Pull an IMDb ID from a normalized item, fetching external_ids if missing.
 */
export async function ensureImdbId(item) {
  if (item.imdbId) return item.imdbId;
  const ext = await externalIds(item.tmdbId, item.type);
  return ext.imdb_id || '';
}
