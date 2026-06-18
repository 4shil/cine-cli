#!/usr/bin/env python3
"""Torrent-to-HTTP streaming server using libtorrent.

Usage:
    python3 torrent_stream_server.py <info_hash> [--port 8080] [--file-idx 0]
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

MIN_READY_PROGRESS = 0.5  # Very low threshold — just need metadata + some peers
MIN_BUFFER_BYTES = 0       # Don't require disk buffer — serve from piece cache

PUBLIC_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
]


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
        self.file_offset = 0
        self.piece_length = 0
        self.first_piece = 0
        self.file_piece_count = 0
        self.torrent_name = ""
        self.file_path = ""
        self._buffered_bytes = 0

    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.session = lt.session({"listen_interfaces": "0.0.0.0:6881"})

        # Build magnet URL with public trackers for better peer discovery
        magnet = f"magnet:?xt=urn:btih:{self.info_hash_hex}"
        for tr in PUBLIC_TRACKERS:
            magnet += f"&tr={tr.replace(':', '%3A').replace('/', '%2F')}"

        atp = lt.parse_magnet_uri(magnet)
        atp.save_path = self.save_path
        self.handle = self.session.add_torrent(atp)

        logging.info(f"Starting: {self.info_hash_hex[:16]}...")
        t = threading.Thread(target=self._wait_for_metadata, daemon=True)
        t.start()

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
        self.file_offset = entry.offset
        self.piece_length = ti.piece_length()
        self.first_piece = self.file_offset // self.piece_length
        last_piece = (self.file_offset + self.file_size - 1) // self.piece_length
        self.file_piece_count = last_piece - self.first_piece + 1
        self.torrent_name = ti.name()

        self.file_path = os.path.join(self.save_path, ti.name(), entry.path)
        if not os.path.exists(self.file_path):
            direct = os.path.join(self.save_path, entry.path)
            self.file_path = direct if os.path.exists(direct) else os.path.join(self.save_path, ti.name())

        logging.info(f"Name: {self.torrent_name}")
        logging.info(f"Size: {self.file_size / (1024*1024):.1f} MB")

        for i in range(self.first_piece, min(self.first_piece + 50, self.first_piece + self.file_piece_count)):
            self.handle.piece_priority(i, 7)

        self.ready.set()
        threading.Thread(target=self._monitor_download, daemon=True).start()

    def _monitor_download(self):
        while True:
            st = self.handle.status()
            if st.progress >= 1.0:
                logging.info("Download complete!")
                self._download_complete.set()
                return
            time.sleep(2)

    def _calculate_buffered(self):
        """Calculate how many bytes of the file are available in piece cache."""
        if not self.handle.has_metadata():
            return 0
        buffered = 0
        for i in range(self.first_piece, self.first_piece + self.file_piece_count):
            if self.handle.have_piece(i):
                buffered += min(self.piece_length, self.file_size - (i - self.first_piece) * self.piece_length)
        return buffered

    def get_status(self):
        if self.handle is None:
            return {"status": "initializing"}
        s = self.handle.status()
        buffered = self._calculate_buffered() if self.metadata_received.is_set() else 0
        ready = s.progress * 100 >= MIN_READY_PROGRESS and buffered >= MIN_BUFFER_BYTES
        return {
            "status": str(s.state),
            "progress": round(s.progress * 100, 1),
            "download_rate_kb": s.download_rate // 1024,
            "num_peers": s.num_peers,
            "num_seeds": s.num_seeds,
            "file_size": self.file_size,
            "buffered_bytes": buffered,
            "ready": ready,
        }

    def read_file_range(self, start, length):
        if not self.metadata_received.is_set():
            return None
        if self._download_complete.is_set():
            return self._read_from_disk(start, length)
        return self._read_from_libtorrent(start, length)

    def _read_from_disk(self, start, length):
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "rb") as f:
                    f.seek(start)
                    return f.read(length)
        except Exception as e:
            logging.error(f"Disk read error: {e}")
        return None

    def _read_from_libtorrent(self, start, length):
        piece_length = self.piece_length
        abs_start = self.file_offset + start
        abs_end = abs_start + length
        first_piece = abs_start // piece_length
        last_piece = (abs_end - 1) // piece_length
        max_wait = 60
        for piece in range(first_piece, min(last_piece + 1, first_piece + 10)):
            waited = 0.0
            while not self.handle.have_piece(piece) and waited < max_wait:
                time.sleep(0.5)
                waited += 0.5
            if not self.handle.have_piece(piece):
                return self._read_from_disk(start, length)
        result = bytearray()
        for piece in range(first_piece, last_piece + 1):
            data = self.handle.read_piece(piece)
            if data is None:
                return None
            result.extend(data)
        piece_start_offset = first_piece * piece_length
        start_in_result = abs_start - piece_start_offset
        end_in_result = start_in_result + length
        return bytes(result[start_in_result:end_in_result])

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
        status = streamer.get_status()
        if not status.get("ready", False):
            self.send_response(503)
            self.send_header("Retry-After", "2")
            self.end_headers()
            self.wfile.write(f"Buffering... {status.get('progress', 0):.1f}%".encode())
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
        chunk_size = 512 * 1024
        remaining = length
        offset = start
        while remaining > 0:
            to_read = min(chunk_size, remaining)
            data = streamer.read_file_range(offset, to_read)
            if data is None:
                break
            self.wfile.write(data)
            offset += len(data)
            remaining -= len(data)

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
