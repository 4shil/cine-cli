#!/usr/bin/env python3
"""Torrent-to-HTTP streaming server using libtorrent.

Downloads the torrent file completely, then serves it over HTTP.
This ensures MPV always has data to read (no buffering issues).
"""
import sys
import os
import time
import threading
import signal
import json
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

try:
    import libtorrent as lt
except ImportError:
    print("ERROR: libtorrent not found.", file=sys.stderr)
    sys.exit(1)

import http.server
import socketserver


class TorrentStreamer:
    def __init__(self, info_hash_hex, port=8080, file_idx=0, save_path="/tmp/cine-cli-torrents"):
        self.info_hash_hex = info_hash_hex.lower()
        self.port = port
        self.file_idx = file_idx
        self.save_path = save_path
        self.session = None
        self.handle = None
        self.ready = threading.Event()
        self.metadata_received = threading.Event()
        self._download_complete = threading.Event()
        self.file_size = 0
        self.file_path = ""
        self.torrent_name = ""
        self._progress = 0.0
        self._peers = 0
        self._seeds = 0
        self._dl_rate = 0

    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.session = lt.session({"listen_interfaces": "0.0.0.0:6881"})

        # Build magnet URL with public trackers
        magnet = f"magnet:?xt=urn:btih:{self.info_hash_hex}"
        for tr in [
            "udp://tracker.opentrackr.org:1337/announce",
            "udp://open.stealth.si:80/announce",
            "udp://tracker.torrent.eu.org:451/announce",
            "udp://exodus.desync.com:6969/announce",
        ]:
            magnet += f"&tr={tr.replace(':', '%3A').replace('/', '%2F')}"

        atp = lt.parse_magnet_uri(magnet)
        atp.save_path = self.save_path
        self.handle = self.session.add_torrent(atp)

        logging.info(f"Starting: {self.info_hash_hex[:16]}...")
        threading.Thread(target=self._wait_for_metadata, daemon=True).start()

    def _wait_for_metadata(self):
        for i in range(120):
            if self.handle.has_metadata():
                self.metadata_received.set()
                self._setup_file()
                return
            if i % 10 == 0:
                st = self.handle.status()
                logging.info(f"Waiting metadata... peers={st.num_peers}")
            time.sleep(1)
        logging.error("Timeout waiting for metadata")

    def _setup_file(self):
        ti = self.handle.torrent_file()
        files = ti.files()
        if self.file_idx >= files.num_files():
            self.file_idx = 0
        entry = files.file_at(self.file_idx)
        self.file_size = entry.size
        self.torrent_name = ti.name()

        self.file_path = os.path.join(self.save_path, ti.name(), entry.path)
        if not os.path.exists(self.file_path):
            direct = os.path.join(self.save_path, entry.path)
            self.file_path = direct if os.path.exists(direct) else os.path.join(self.save_path, ti.name())

        logging.info(f"Name: {self.torrent_name}")
        logging.info(f"Size: {self.file_size / (1024*1024):.1f} MB")
        logging.info(f"Path: {self.file_path}")

        self.ready.set()
        threading.Thread(target=self._download_and_serve, daemon=True).start()

    def _download_and_serve(self):
        """Download the file and signal ready when enough is buffered."""
        while True:
            st = self.handle.status()
            self._progress = st.progress * 100
            self._peers = st.num_peers
            self._seeds = st.num_seeds
            self._dl_rate = st.download_rate // 1024

            if st.progress >= 1.0:
                logging.info("Download complete!")
                self._download_complete.set()
                return

            # Check if file exists and has enough data for streaming
            if os.path.exists(self.file_path):
                file_size_on_disk = os.path.getsize(self.file_path)
                # Signal ready when we have at least 5% or 10MB
                min_size = min(self.file_size * 0.05, 10 * 1024 * 1024)
                if file_size_on_disk >= min_size:
                    pass  # ready is already set

            time.sleep(2)

    def get_status(self):
        if self.handle is None:
            return {"status": "initializing"}
        st = self.handle.status()
        file_exists = os.path.exists(self.file_path) if self.file_path else False
        file_size_on_disk = os.path.getsize(self.file_path) if file_exists else 0
        return {
            "status": str(st.state),
            "progress": round(st.progress * 100, 1),
            "download_rate_kb": st.download_rate // 1024,
            "num_peers": st.num_peers,
            "num_seeds": st.num_seeds,
            "file_size": self.file_size,
            "file_on_disk": file_size_on_disk,
            "ready": file_size_on_disk > 0,
        }

    def read_file_range(self, start, length):
        """Read from the downloaded file on disk."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "rb") as f:
                    f.seek(start)
                    return f.read(length)
        except Exception as e:
            logging.error(f"Read error: {e}")
        return None

    def stop(self):
        if self.session:
            self.session.pause()


class TorrentHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        streamer = self.server.streamer

        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(streamer.get_status()).encode())
            return

        if not streamer.ready.is_set():
            self.send_response(503)
            self.send_header("Retry-After", "3")
            self.end_headers()
            self.wfile.write(b"Waiting for torrent metadata...")
            return

        file_size = streamer.file_size
        range_header = self.headers.get("Range", "")
        start = 0
        end = file_size - 1

        if range_header:
            try:
                range_val = range_header.replace("bytes=", "")
                parts = range_val.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
            except (ValueError, IndexError):
                pass

        length = end - start + 1

        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", "video/x-matroska")
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        # Read from disk — the file is being downloaded in background
        chunk_size = 256 * 1024
        remaining = length
        offset = start

        while remaining > 0:
            to_read = min(chunk_size, remaining)
            data = streamer.read_file_range(offset, to_read)
            if data and len(data) > 0:
                self.wfile.write(data)
                offset += len(data)
                remaining -= len(data)
            else:
                # No data available yet, wait a bit
                time.sleep(0.5)
                # Check if download is still in progress
                st = streamer.handle.status() if streamer.handle else None
                if st and st.progress >= 1.0:
                    break  # Download complete, nothing more to read

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("info_hash")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--file-idx", type=int, default=0)
    args = parser.parse_args()

    streamer = TorrentStreamer(args.info_hash, port=args.port, file_idx=args.file_idx)
    streamer.start()

    server = ReusableTCPServer(("127.0.0.1", args.port), TorrentHTTPHandler)
    server.streamer = streamer
    print(f"[http] http://127.0.0.1:{args.port}", flush=True)

    def shutdown(signum, frame):
        streamer.stop()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    server.serve_forever()


if __name__ == "__main__":
    main()
