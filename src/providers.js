/**
 * Provider definitions — all use IMDb IDs, just template-fill the URL.
 *
 * To add a provider, append an entry. Order matters: vidsrc first (default),
 * then by priority.
 */

export const PROVIDERS = [
  {
    id: 'vidsrc',
    name: 'VidSrc',
    url: 'https://vidsrc.to/embed',
    movie: 'https://vidsrc.to/embed/movie/{imdb}',
    tv: 'https://vidsrc.to/embed/tv/{imdb}/{season}/{episode}',
    priority: 1,
  },
  {
    id: 'vidking',
    name: 'VidKing',
    url: 'https://www.vidking.net',
    movie: 'https://www.vidking.net/embed/movie/{imdb}',
    tv: 'https://www.vidking.net/embed/tv/{imdb}/{season}/{episode}',
    priority: 2,
  },
  {
    id: 'vidlink',
    name: 'VidLink',
    url: 'https://vidlink.pro',
    movie: 'https://vidlink.pro/movie/{imdb}',
    tv: 'https://vidlink.pro/tv/{imdb}/{season}/{episode}',
    priority: 3,
  },
  {
    id: 'vidsync',
    name: 'VidSync',
    url: 'https://vidsync.live',
    movie: 'https://vidsync.live/embed/movie/{imdb}',
    tv: 'https://vidsync.live/embed/tv/{imdb}/{season}/{episode}',
    priority: 4,
  },
  {
    id: 'cinesrc',
    name: 'CineSrc',
    url: 'https://cinesrc.st',
    movie: 'https://cinesrc.st/embed/movie/{imdb}',
    tv: 'https://cinesrc.st/embed/tv/{imdb}/{season}/{episode}',
    priority: 5,
  },
  {
    id: 'lordflix',
    name: 'LordFlix',
    url: 'https://lordflix.org',
    movie: 'https://lordflix.org/movie/{imdb}',
    tv: 'https://lordflix.org/tv/{imdb}/{season}/{episode}',
    priority: 6,
  },
];

/**
 * Build the URL for one (providerId, imdb, type, [season, episode]) tuple.
 */
export function buildUrl({ providerId, imdbId, type, season, episode }) {
  const p = PROVIDERS.find((x) => x.id === providerId);
  if (!p) return null;
  const tpl = type === 'tv' ? p.tv : p.movie;
  if (!tpl) return null;
  return tpl
    .replace('{imdb}', imdbId)
    .replace('{season}', String(season ?? 1))
    .replace('{episode}', String(episode ?? 1));
}

/**
 * Build a sorted list of {id, name, url} for every provider, dedup on URL.
 */
export function buildAllProviders({ imdbId, type, season = 1, episode = 1 }) {
  const seen = new Set();
  const out = [];
  for (const p of PROVIDERS) {
    if (seen.has(p.id)) continue;
    const url = buildUrl({ providerId: p.id, imdbId, type, season, episode });
    if (!url) continue;
    out.push({ id: p.id, name: p.name, url });
    seen.add(p.id);
  }
  return out;
}
