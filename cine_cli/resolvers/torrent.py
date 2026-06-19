"""Torrent resolver and downloader using Torrentio API + libtorrent.

Features:
- Fetches torrents from Torrentio (aggregates YTS, EZTV, RARBG, 1337x, TPB)
- Shows ALL torrents sorted by seeders (highest first)
- Downloads via libtorrent (Python bindings) with progress bar
- Auto-retry on failure
- Auto-select highest seeder per quality
"""
from __future__ import annotations
from typing import Optional, Callable, List, Dict
import os
import re
import sys
import time
import threading
import json
import urllib.request
import subprocess

try:
    import libtorrent as lt
    LIBTORRENT_AVAILABLE = True
except ImportError:
    LIBTORRENT_AVAILABLE = False

from ..logger import cine_cli_logger


class TorrentStream:
    """Represents a single torrent stream from Torrentio."""

    def __init__(self, data: dict):
        self.name: str = data.get("name", "")
        self.title: str = data.get("title", "")
        self.info_hash: Optional[str] = data.get("infoHash")
        self.file_idx: int = data.get("fileIdx", 0)
        self.url: Optional[str] = data.get("url")
        self.filename: str = data.get("behaviorHints", {}).get("filename", "")
        self.size: Optional[int] = None
        self.seeders: Optional[int] = None
        self._parse_title()

    def _parse_title(self):
        title = self.title or self.name
        q_match = re.search(r"(4K|2160p|1080p|720p|480p|360p|HDR|DV|HEVC)", title, re.IGNORECASE)
        self.quality = q_match.group(1).lower() if q_match else "unknown"
        s_match = re.search(r"👤\s*(\d+)", title)
        self.seeders = int(s_match.group(1)) if s_match else 0
        size_match = re.search(r"([\d.]+)\s*(GB|MB|KB)", title, re.IGNORECASE)
        if size_match:
            size_val = float(size_match.group(1))
            unit = size_match.group(2).upper()
            if unit == "GB":
                self.size = int(size_val * 1024)
            elif unit == "MB":
                self.size = int(size_val)
            elif unit == "KB":
                self.size = int(size_val / 1024)
        else:
            self.size = 0

    @property
    def display_label(self) -> str:
        if self.size and self.size > 1024:
            size_str = f"{self.size / 1024:.1f}GB"
        elif self.size:
            size_str = f"{self.size}MB"
        else:
            size_str = "??"
        seed_str = f"👤{self.seeders}" if self.seeders else "👤0"
        fname = self.filename[:45] if self.filename else "?"
        return f"{self.quality:>6}  {size_str:>7}  {seed_str:>5}  {fname}"

    @property
    def magnet_url(self) -> str:
        if self.info_hash:
            return f"magnet:?xt=urn:btih:{self.info_hash}"
        return ""


class TorrentResolver:
    """Fetches torrent streams from Torrentio."""

    def __init__(self):
        self.base_url = "https://torrentio.strem.fun"
        self.config = "providers=yts,eztv,rarbg,1337x,thepiratebay|qualityfilter=480p,720p,1080p|sort=qualitysize"
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def _api_url(self, imdb_id: str, media_type: str = "movie",
                 season: str = "1", episode: str = "1") -> str:
        base = f"{self.base_url}/{self.config}"
        if media_type == "tv":
            return f"{base}/stream/series/{imdb_id}:{season}:{episode}.json"
        return f"{base}/stream/movie/{imdb_id}.json"

    def fetch_streams(self, imdb_id: str, media_type: str = "movie",
                      season: str = "1", episode: str = "1") -> List[TorrentStream]:
        url = self._api_url(imdb_id, media_type, season, episode)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.ua})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
            streams = [TorrentStream(s) for s in data.get("streams", [])]
            streams = [s for s in streams if s.info_hash and (s.seeders or 0) > 0]
            return streams
        except Exception as e:
            cine_cli_logger.error(f"[torrent] Fetch failed: {e}")
            return []

    def group_by_quality(self, streams: List[TorrentStream]) -> Dict[str, List[TorrentStream]]:
        groups: Dict[str, List[TorrentStream]] = {}
        for s in streams:
            q = s.quality
            if q not in groups:
                groups[q] = []
            groups[q].append(s)
        for q in groups:
            groups[q].sort(key=lambda s: s.seeders or 0, reverse=True)
        return groups

    def pick_best_for_quality(self, streams: List[TorrentStream],
                               prefer_quality: str = "1080p") -> Optional[TorrentStream]:
        groups = self.group_by_quality(streams)
        if prefer_quality in groups and groups[prefer_quality]:
            return groups[prefer_quality][0]
        q_order = ["4k", "2160p", "1080p", "720p", "480p", "360p"]
        for q in q_order:
            if q in groups and groups[q]:
                return groups[q][0]
        for s in sorted(streams, key=lambda x: x.seeders or 0, reverse=True):
            if s.seeders and s.seeders > 0:
                return s
        return streams[0] if streams else None


class LibtorrentDownloader:
    """Download torrents using libtorrent Python bindings."""

    def __init__(self, download_dir: str):
        if not LIBTORRENT_AVAILABLE:
            raise RuntimeError("libtorrent not available. Install libtorrent or use aria2c.")
        self.download_dir = download_dir
        self.session = lt.session()
        self.session.listen_on(6881, 6891)
        self.session.add_dht_router("router.bittorrent.com", 6881)
        self.session.add_dht_router("router.utorrent.com", 6881)
        self.session.add_dht_router("dht.transmissionbt.com", 6881)
        self.session.start_dht()
        self.session.start_lsd()
        self.session.start_upnp()
        self.session.start_natpmp()
        self.handle: Optional[lt.torrent_handle] = None
        self.status = "idle"
        self.progress = 0.0
        self._stop_event = threading.Event()

    def add_torrent(self, info_hash: str, title: str) -> bool:
        os.makedirs(self.download_dir, exist_ok=True)
        params = {
            "save_path": self.download_dir,
            "storage_mode": lt.storage_mode_t.storage_mode_sparse,
        }
        try:
            magnet = f"magnet:?xt=urn:btih:{info_hash}"
            self.handle = lt.add_magnet_uri(self.session, magnet, params)
            self.status = "downloading"
            cine_cli_logger.info(f"Added torrent: {title} ({info_hash[:16]}...)")
            return True
        except Exception as e:
            cine_cli_logger.error(f"Failed to add torrent: {e}")
            return False

    def wait_with_progress(self, timeout: int = 600) -> bool:
        if not self.handle:
            return False

        start_time = time.time()
        last_print = 0

        print(f"\n  {'─' * 56}")
        print(f"  ⚠ Download runs in background. Check {self.download_dir}")
        print(f"  {'─' * 56}\n")

        while not self._stop_event.is_set():
            if time.time() - start_time > timeout:
                cine_cli_logger.warning("Download timeout reached")
                break

            s = self.handle.status()
            self.progress = s.progress * 100

            now = time.time()
            if now - last_print >= 0.5:
                self._print_progress(s)
                last_print = now

            if s.is_seeding or s.progress >= 1.0:
                self.status = "completed"
                self.progress = 100.0
                self._print_progress(s, final=True)
                print(f"\n  ✓ Download complete!")
                return True

            if s.error:
                self.status = "error"
                cine_cli_logger.error(f"Torrent error: {s.error}")
                return False

            time.sleep(0.1)

        return False

    def _print_progress(self, s: lt.torrent_status, final: bool = False):
        bar_width = 40
        filled = int(bar_width * s.progress)
        bar = "█" * filled + "░" * (bar_width - filled) if not final else "█" * bar_width

        total_mb = s.total_wanted / (1024 * 1024)
        done_mb = s.total_wanted_done / (1024 * 1024)

        speed_kb = s.download_rate / 1024
        if speed_kb >= 1024:
            speed_str = f"{speed_kb / 1024:.1f}MB/s"
        elif speed_kb > 0:
            speed_str = f"{speed_kb:.0f}KB/s"
        else:
            speed_str = "connecting..."

        if s.download_rate > 0 and s.total_wanted > s.total_wanted_done:
            eta_sec = (s.total_wanted - s.total_wanted_done) / s.download_rate
            if eta_sec > 3600:
                eta_str = f"{eta_sec / 3600:.0f}h"
            elif eta_sec > 60:
                eta_str = f"{eta_sec / 60:.0f}m"
            else:
                eta_str = f"{eta_sec:.0f}s"
        else:
            eta_str = "..."

        status_icon = {"downloading": "⬇", "paused": "⏸", "completed": "✓", "error": "✗"}.get(self.status, " ")

        line = (
            f"\r  {status_icon} [{bar}] {self.progress:.1f}% "
            f"| {done_mb:.0f}/{total_mb:.0f}MB "
            f"| {speed_str} | 🌱{s.num_seeds} 🔗{s.num_peers} "
            f"| ETA: {eta_str}"
        )
        sys.stdout.write(line.ljust(90))
        sys.stdout.flush()

    def auto_retry(self, info_hash: str, title: str, max_retries: int = 3) -> bool:
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                wait = min(30, 5 * attempt)
                print(f"\n  Retry {attempt}/{max_retries} in {wait}s...")
                time.sleep(wait)

            if self.add_torrent(info_hash, title):
                if self.wait_with_progress(timeout=600):
                    return True

            if self.handle:
                try:
                    self.session.remove_torrent(self.handle)
                except Exception:
                    pass
            self.handle = None

        cine_cli_logger.error(f"Download failed after {max_retries} attempts")
        return False


class DownloadManager:
    """Fallback download manager using aria2c."""

    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        self.process: Optional[subprocess.Popen] = None
        self.status = "idle"
        self.progress = 0.0
        self.speed = ""
        self.eta = ""
        self.downloaded = 0
        self.total = 0
        self.connections = 0
        self.seeds = 0
        self._stop_event = threading.Event()

    def start(self, stream: TorrentStream, title: str) -> bool:
        os.makedirs(self.download_dir, exist_ok=True)
        safe_title = re.sub(r'[<>:"/\\|?*\'`]', '', title)[:80]
        magnet = stream.magnet_url
        if not magnet:
            cine_cli_logger.error("No magnet URL available")
            return False
        cmd = [
            "aria2c", "--dir", self.download_dir, "--out", f"{safe_title}.mp4",
            "--seed-time=0", "--bt-stop-timeout=600", "--summary-interval=1",
            "--console-log-level=notice", "--download-result=full",
            "--file-allocation=none", "--max-connection-per-server=16",
            "--bt-max-peers=100", "--listen-port=6881", "--enable-dht=true",
            "--dht-listen-port=6882", magnet
        ]
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.status = "downloading"
            return True
        except FileNotFoundError:
            cine_cli_logger.error("aria2c not found!")
            return False

    def wait_with_progress(self, stream: TorrentStream):
        if not self.process:
            return
        self.total = stream.size or 0
        print(f"\n  {'─' * 56}")
        print(f"  Filename: {stream.filename[:50]}")
        print(f"  Quality:  {stream.quality} | Size: {stream.size}MB | Seeds: {stream.seeders}")
        print(f"  {'─' * 56}")
        print(f"  ⚠ Download runs in background. Check {self.download_dir}\n")
        try:
            for line in iter(self.process.stdout.readline, ''):
                if self._stop_event.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                self._parse_progress(line)
                self._print_progress_bar(line)
                if "DOWNLOAD COMPLETE" in line.upper():
                    self.status = "completed"
                    self.progress = 100.0
                    self._print_progress_bar("", final=True)
                    print(f"\n  ✓ Download complete!")
                    break
        except (KeyboardInterrupt, EOFError):
            print(f"\n  Interrupted. Download continues in background.")
        finally:
            self._stop_event.set()
            if self.process.poll() is None:
                self.process.wait(timeout=5)

    def _parse_progress(self, line: str):
        progress_match = re.search(r'\[#\w+\s+([\d.]+)([KMGTiB]+)/([\d.]+)([KMGTiB]+)(?:\((\d+)%\)|\s)', line)
        if progress_match:
            dl_val = float(progress_match.group(1))
            dl_unit = progress_match.group(2)
            total_val = float(progress_match.group(3))
            total_unit = progress_match.group(4)
            pct = progress_match.group(5)
            if pct:
                self.progress = float(pct)
            else:
                total_mb = self._to_mb(total_val, total_unit)
                dl_mb = self._to_mb(dl_val, dl_unit)
                self.progress = (dl_mb / total_mb * 100) if total_mb > 0 else 0
            self.downloaded = self._to_mb(dl_val, dl_unit)
            self.total = self._to_mb(total_val, total_unit)
        speed_match = re.search(r'DL:([\d.]+)([KMGTiB]+)', line)
        if speed_match:
            sv = float(speed_match.group(1))
            su = speed_match.group(2)
            self.speed = f"{sv}{su}/s" if sv > 0 else "connecting..."
        eta_match = re.search(r'ETA:(\S+)', line)
        if eta_match:
            self.eta = eta_match.group(1) if eta_match.group(1) != "--" else "..."

    def _to_mb(self, val: float, unit: str) -> float:
        u = unit.upper()
        if "G" in u: return val * 1024
        if "M" in u: return val
        if "K" in u: return val / 1024
        return val

    def _print_progress_bar(self, line: str = "", final: bool = False):
        bar_width = 40
        filled = int(bar_width * self.progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled) if not final else "█" * bar_width
        size_info = f"{self.downloaded:.0f}/{self.total:.0f}MB" if self.total > 0 else f"{self.downloaded:.0f}MB"
        icon = {"downloading": "⬇", "paused": "⏸", "completed": "✓", "error": "✗"}.get(self.status, " ")
        sys.stdout.write(f"\r  {icon} [{bar}] {self.progress:.1f}% | {size_info} | {self.speed} | ETA: {self.eta}".ljust(80))
        sys.stdout.flush()

    def auto_retry(self, stream: TorrentStream, title: str, max_retries: int = 3) -> bool:
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                print(f"\n  Retry {attempt}/{max_retries} in {min(30, 5 * attempt)}s...")
                time.sleep(min(30, 5 * attempt))
            if self.start(stream, title):
                self.wait_with_progress(stream)
                if self.status == "completed":
                    return True
            if self.process:
                try: self.process.terminate()
                except: pass
                self.process = None
        return False
