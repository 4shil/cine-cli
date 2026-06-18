#!/usr/bin/env python3
"""Torrent-to-HTTP streaming server.

Downloads a torrent using libtorrent, then serves the file over HTTP
with proper range request support for MPV/VLC streaming.
"""
import sys
import os
import time
import threading
import signal
import json
import argparse
import logging
import mimetypes

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

try:
    import libtorrent as lt
except ImportError:
    print("ERROR: libtorrent not found.", file=sys.stderr)
    sys.exit(1)

import http.server
import socketserver
import urllib.parse


class RangeFileHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that serves a single file with range request support."""

    video_file: str | None = None  # Class variable set by server

    def do_GET(self):
        if self.path == "/status":
            self.send_status()
            return

        if not self.video_file or not os.path.exists(self.video_file):
            self.send_response(503)
            self.send_header("Retry-After", "2")
            self.end_headers()
            self.wfile.write(b"Waiting for download...")
            return

        file_size = os.path.getsize(self.video_file)
        content_type = mimetypes.guess_type(self.video_file)[0] or "video/x-matroska"

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
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        # Stream from file
        with open(self.video_file, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def send_status(self):
        if not self.video_file:
            status = {"status": "initializing"}
        elif not os.path.exists(self.video_file):
            status = {"status": "downloading_metadata"}
        else:
            file_size = os.path.getsize(self.video_file)
            status = {
                "status": "ready",
                "progress": 100.0 if file_size > 0 else 0,
                "file_size": file_size,
                "ready": file_size > (5 * 1024 * 1024),
            }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def download_and_serve(info_hash_hex, port):
    """Download torrent and serve the file."""
    save_path = "/tmp/cine-cli-torrents"
    os.makedirs(save_path, exist_ok=True)

    session = lt.session({"listen_interfaces": "0.0.0.0:6881"})

    # Build magnet URL with public trackers
    magnet = f"magnet:?xt=urn:btih:{info_hash_hex}"
    for tr in [
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://open.stealth.si:80/announce",
        "udp://tracker.torrent.eu.org:451/announce",
        "udp://exodus.desync.com:6969/announce",
    ]:
        magnet += f"&tr={tr.replace(':', '%3A').replace('/', '%2F')}"

    atp = lt.parse_magnet_uri(magnet)
    atp.save_path = save_path
    handle = session.add_torrent(atp)

    logging.info(f"Starting: {info_hash_hex[:16]}...")

    # Wait for metadata
    for i in range(120):
        if handle.has_metadata():
            break
        if i % 10 == 0:
            st = handle.status()
            logging.info(f"Waiting metadata... peers={st.num_peers}")
        time.sleep(1)
    else:
        logging.error("Timeout waiting for metadata")
        return None

    ti = handle.torrent_file()
    logging.info(f"Name: {ti.name()}")
    logging.info(f"Size: {ti.total_size() / (1024*1024):.1f} MB")

    # Find the video file
    video_file = None
    for i in range(ti.num_files()):
        entry = ti.files().file_at(i)
        if entry.path.endswith((".mp4", ".mkv", ".avi", ".webm", ".mov")):
            vf = os.path.join(save_path, ti.name(), entry.path)
            if not os.path.exists(vf):
                vf = os.path.join(save_path, entry.path)
            video_file = vf
            break

    if not video_file:
        for root, dirs, fs in os.walk(save_path):
            for f in fs:
                fp = os.path.join(root, f)
                if os.path.getsize(fp) > 10 * 1024 * 1024:
                    video_file = fp
                    break

    logging.info(f"Video file: {video_file}")

    # Set up HTTP server
    RangeFileHandler.video_file = video_file
    server = ReusableTCPServer(("127.0.0.1", port), RangeFileHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logging.info(f"HTTP server: http://127.0.0.1:{port}")

    print(f"[http] http://127.0.0.1:{port}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("info_hash")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    download_and_serve(args.info_hash, args.port)

    # Keep running
    signal.pause()


if __name__ == "__main__":
    main()
