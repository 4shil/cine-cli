"""Media classes for cine-cli.

Media represents any piece of media that can be played.
Single = one stream URL. Multi = multiple quality options (choose one).
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, List

    from ..utils import EpisodeSelector

import json
import shutil
import subprocess

from .quality import Quality

from abc import abstractmethod

__all__ = (
    "Media",
    "Multi",
    "Single",
    "MultiSourceMedia",
)


class Media():
    """Represents any piece of media in cine-cli that can be streamed or downloaded."""

    def __init__(
        self,
        url: str,
        title: str,
        audio_url: Optional[str],
        referrer: Optional[str],
        subtitles: Optional[List[str]],
    ) -> None:
        self.url = url
        """The stream-able url of the media (Can also be a path to a file)."""
        self.title = title
        """A title to represent this stream-able media."""
        self.audio_url = audio_url
        """The stream-able url that provides audio for the media if the main url doesn't stream with audio."""
        self.referrer = referrer
        """The required referrer for streaming the content."""
        self.subtitles = subtitles
        """A tuple of urls or file paths to subtitles."""

        self.__stream_quality: Optional[Quality] = None

    @property
    @abstractmethod
    def display_name(self) -> str:
        """The title that should be displayed by the player."""
        ...

    def get_quality(self) -> Optional[Quality]:
        """Uses ffprobe to grab the quality of the stream."""

        if self.__stream_quality is None:

            if shutil.which("ffprobe") is None:
                return None

            args = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v",
                "-show_entries", "stream=width,height",
                "-of", "json",
                self.url
            ]

            try:
                out = str(subprocess.check_output(args), "utf-8")

                stream = json.loads(out).get("streams", [])

                if not stream == []:
                    width = stream[0]["width"]
                    height = stream[0]["height"]

                    target_dimension_px = height

                    if height > width:
                        target_dimension_px = width

                    heights_lower_than_target_height = [
                        quality_height for quality_height in Quality._value2member_map_ if target_dimension_px >= quality_height
                    ]

                    closest_quality_height = min(heights_lower_than_target_height, key = lambda x: abs(x - target_dimension_px))

                    self.__stream_quality = Quality(closest_quality_height)

            except Exception:
                pass

        return self.__stream_quality


class Multi(Media):
    """Represents a media that has multiple episodes like a TV Series, Anime or Cartoon."""

    def __init__(
        self,
        url: str,
        title: str,
        episode: EpisodeSelector,
        audio_url: Optional[str] = None,
        referrer: Optional[str] = None,
        subtitles: Optional[List[str]] = None
    ):
        self.episode = episode
        """The episode and season of this series."""

        super().__init__(
            url,
            title = title,
            audio_url = audio_url,
            referrer = referrer,
            subtitles = subtitles
        )

    @property
    def display_name(self) -> str:
        return f"{self.title} - S{self.episode.season} EP{self.episode.episode}"


class Single(Media):
    """Represents a media with a single episode, like a Film/Movie or a YouTube video."""

    def __init__(
        self,
        url: str,
        title: str,
        audio_url: Optional[str] = None,
        referrer: Optional[str] = None,
        year: Optional[str] = None,
        subtitles: Optional[List[str]] = None
    ):
        self.year = year
        """The year this film was released."""

        super().__init__(
            url,
            title = title,
            audio_url = audio_url,
            referrer = referrer,
            subtitles = subtitles
        )

    @property
    def display_name(self) -> str:
        return f"{self.title} ({self.year})" if self.year is not None else self.title


class MultiSourceMedia(Media):
    """Represents media with multiple quality options.

    Used when a scraper returns multiple stream URLs (e.g., Videasy returns 360p, 720p, 1080p).
    The user picks one quality before playback.
    """

    def __init__(
        self,
        sources: List[dict],
        title: str,
        audio_url: Optional[str] = None,
        referrer: Optional[str] = None,
        year: Optional[str] = None,
        subtitles: Optional[List[str]] = None,
    ):
        """
        sources: list of {"quality": "720p", "url": "...", "type": "m3u8"}
        """
        self.sources = sources
        self._selected_url: Optional[str] = None
        self.year = year

        # Use the best quality as default for the base Media
        best_url = self._best_url()

        super().__init__(
            url = best_url,
            title = title,
            audio_url = audio_url,
            referrer = referrer,
            subtitles = subtitles,
        )

    def _best_url(self) -> str:
        """Get the highest quality URL."""
        quality_order = {"4k": 2160, "2160p": 2160, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360, "unknown": 0}

        if not self.sources:
            return ""

        sorted_sources = sorted(
            self.sources,
            key=lambda s: quality_order.get(s.get("quality", "unknown").lower(), 0),
            reverse=True,
        )
        return sorted_sources[0]["url"]

    def select_quality(self, quality: str) -> bool:
        """Select a specific quality. Returns True if found."""
        quality_lower = quality.lower()
        for source in self.sources:
            if source.get("quality", "").lower() == quality_lower:
                self._selected_url = source["url"]
                self.url = source["url"]
                return True
        return False

    def set_url(self, url: str):
        """Set the active URL (after quality selection)."""
        self._selected_url = url
        self.url = url

    @property
    def display_name(self) -> str:
        return f"{self.title} ({self.year})" if self.year is not None else self.title
