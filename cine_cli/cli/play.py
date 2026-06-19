from __future__ import annotations
from typing import TYPE_CHECKING, Type, cast
import subprocess
import time

from ..media import Media, Metadata, Multi, Single, MultiSourceMedia
from ..scraper import Scraper, ScrapeEpisodesT, ScrapeResultT
from ..players import Player
from ..utils.platform import SUPPORTED_PLATFORMS
from ..utils.episode_selector import EpisodeSelector

from typing import Optional, Literal

if TYPE_CHECKING:
    from ..config import Config

from devgoldyutils import Colours

from .scraper import scrape
from .episode import handle_episode
from .watch_options import watch_options

from ..media import MetadataType
from ..logger import cine_cli_logger
from ..cache import Cache
from ..utils import what_platform, hide_ip
from ..players import PLAYER_TABLE, CustomPlayer

def play(media: Media, metadata: Metadata, scraper: Scraper, episode: EpisodeSelector, config: Config) -> Optional[Literal["search"]]:
    platform = what_platform()
    cache = Cache(platform)

    cache.set_cache(str(metadata.id), episode.__dict__)

    chosen_player = __get_player(config, platform)

    # Quality selection for MultiSourceMedia
    if isinstance(media, MultiSourceMedia):
        selected = __select_quality(media, config.quality)
        if selected is None:
            return None
        media = selected

    quality_string = ""
    episode_details_string = ""

    if metadata.type == MetadataType.MULTI:
        season_string = Colours.CLAY.apply(str(episode.season))
        episode_string = Colours.ORANGE.apply(str(episode.episode))

        episode_details_string = f"episode {episode_string} in season {season_string} of " if episode.season > 1 else f"episode {episode_string} of "

    if config.display_quality:
        quality = media.get_quality()

        if quality is not None:
            quality_string = f"in {Colours.GREEN.apply(quality.name)} "

    try:
        popen = chosen_player.play(media)

        actual_player = chosen_player.display_name
        popen_args = popen.args if popen is not None else []
        if isinstance(popen_args, (list, tuple)) and len(popen_args) > 0:
            command = str(popen_args[0])
            if command.endswith("xdg-open") or "zen-browser" in command or "firefox" in command or "brave" in command:
                actual_player = Colours.PURPLE.apply("Browser")

        cine_cli_logger.info(
            f"Playing {episode_details_string}'{Colours.BLUE.apply(media.title)}' " \
                f"{quality_string}with {actual_player}..."
        )
        cine_cli_logger.debug(f"Called player with these args -> '{hide_ip(' '.join(popen.args), config.hide_ip)}'")
    except FileNotFoundError as e:
        cine_cli_logger.error(
            f"The player '{chosen_player.display_name}' was not found! " \
                f"Are you sure you have it installed? Are you sure it's in path? \\nError: {e}"
        )
        return None

    if popen is None and platform != "iOS":
        cine_cli_logger.error(
            f"The player '{chosen_player.display_name}' is not supported on this platform ({platform}). " \
                "We recommend VLC for iOS, IINA for MacOS and MPV for every other platform."
        )

        return None

    if config.watch_options:
        option = watch_options(popen, chosen_player, platform, media, config.fzf_enabled)

        if option == "next" or option == "previous":
            popen.kill()

            media_episodes = scraper.scrape_episodes(metadata)

            if option == "next":
                episode.episode += 1
            else:
                episode.episode -= 1

            season_episode_count = media_episodes.get(episode.season)

            if season_episode_count is None:
                cine_cli_logger.info("No more episodes :(")
                return None

            result = __handle_next_season(episode, season_episode_count, media_episodes)

            if result is False:
                cine_cli_logger.info("No more episodes :(")
                return None

            media = scrape(metadata, episode, scraper)

            return play(media, metadata, scraper, episode, config)

        elif option == "select":
            popen.kill()

            episode = handle_episode(None, scraper, metadata, config.fzf_enabled, False)

            if episode is None:
                return None

            media = scrape(metadata, episode, scraper)

            return play(media, metadata, scraper, episode, config)

    # For torrent streams, poll progress and show live stats
    if popen is not None and "127.0.0.1" in media.url:
        cine_cli_logger.info("Torrent stream started. Showing download progress...")
        try:
            import urllib.request as _urlreq
            import json as _json
            status_url = media.url.rstrip("/") + "/status"
            start_time = time.time()
            last_progress = -1
            while popen.poll() is None:
                time.sleep(3)
                try:
                    r = _urlreq.urlopen(status_url, timeout=2)
                    s = _json.loads(r.read())
                    progress = s.get("progress", 0)
                    dl_rate = s.get("download_rate_kb", 0)
                    peers = s.get("num_peers", 0)
                    seeds = s.get("num_seeds", 0)
                    buffered = s.get("buffered_bytes", 0) // 1024
                    is_ready = s.get("ready", False)
                    if progress != last_progress or True:
                        bar_len = 30
                        filled = int(bar_len * progress / 100) if progress > 0 else 0
                        bar = "█" * filled + "░" * (bar_len - filled)
                        elapsed = int(time.time() - start_time)
                        status_icon = "▶" if is_ready else "⏳"
                        print(
                            f"\r  {status_icon} [{bar}] {progress:5.1f}%  "
                            f"⬇ {dl_rate} KB/s  "
                            f"💾 {buffered}KB  "
                            f"👤 {peers}  🌱 {seeds}  "
                            f"⏱ {elapsed}s",
                            end="", flush=True,
                        )
                        last_progress = progress
                except Exception:
                    pass
            print()
        except subprocess.TimeoutExpired:
            print()
            cine_cli_logger.info("Player still running after timeout. Detaching...")
    elif popen is not None:
        popen.wait()

    return None

def __select_quality(media: MultiSourceMedia, preferred_quality: Optional[str] = None) -> Optional[Single]:
    """Prompt user to select quality for multi-source media.

    Returns a Single media object with the selected URL, or None if cancelled.
    If preferred_quality is provided and matches an option, auto-selects it.
    """
    sources = media.sources
    if not sources:
        return None

    if len(sources) == 1:
        return Single(
            url=sources[0]["url"],
            title=media.title,
            referrer=media.referrer,
            year=media.year,
            subtitles=media.subtitles,
        )

    # Sort by quality (highest first)
    quality_order = {"4k": 2160, "2160p": 2160, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360, "unknown": 0}
    sorted_sources = sorted(
        sources,
        key=lambda s: quality_order.get(s.get("quality", "unknown").lower(), 0),
        reverse=True,
    )

    # Auto-select if preferred quality matches
    if preferred_quality:
        pq = preferred_quality.lower()
        for s in sorted_sources:
            if s.get("quality", "").lower() == pq:
                cine_cli_logger.info(f"  Quality: {Colours.GREEN.apply(s['quality'])} (preferred)")
                return Single(
                    url=s["url"],
                    title=media.title,
                    referrer=media.referrer,
                    year=media.year,
                    subtitles=media.subtitles,
                )

    print(f"\n  {Colours.BLUE.apply(media.display_name)} — {len(sorted_sources)} qualities available:\n")

    for i, source in enumerate(sorted_sources, 1):
        quality = source.get("quality", "unknown")
        url = source["url"]
        # Show URL domain for clarity
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        marker = " ◄" if preferred_quality and quality.lower() == preferred_quality.lower() else ""
        print(f"    {Colours.GREEN.apply(str(i))}. {quality:>8}  —  {domain}{marker}")

    print()

    # Auto-select best quality (stdin not available in non-interactive terminals)
    best = sorted_sources[0]
    print(f"  → {Colours.GREEN.apply(best.get('quality', 'unknown'))} selected (best)\n")
    return Single(
        url=best["url"],
        title=media.title,
        referrer=media.referrer,
        year=media.year,
        subtitles=media.subtitles,
    )


def __get_player(config: Config, platform: SUPPORTED_PLATFORMS) -> Player:
    player = PLAYER_TABLE.get(config.player, CustomPlayer)

    if player == CustomPlayer:
        player = cast(Type[CustomPlayer], player)

        return player(
            binary = config.player, 
            args = config.player_args
        )

    return player(
        platform = platform, 
        args = config.player_args, 
        debug = config.debug_player, 
        args_override = config.player_args_override
    )

def __handle_next_season(episode: EpisodeSelector, season_episode_count: int, media_episodes: ScrapeEpisodesT) -> bool:

    if episode.episode > season_episode_count:
        next_season = episode.season + 1

        if media_episodes.get(next_season) is None:
            return False

        episode._next_season()

    elif episode.episode <= 1:

        if episode.season <= 1:
            return False

        episode._previous_season(media_episodes)

    return True
