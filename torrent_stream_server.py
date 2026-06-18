#!/usr/bin/env python3
"""Torrent-to-HTTP streaming server using libtorrent."""
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
        self.file_size = 0
        self.file_offset = 0
        self.piece_length = 0
        self.first_piece = 0
        self.file_piece_count = 0
        self.torrent_name = ""
        self._download_complete = threading.Event()

    def start(self):
        os.makedirs(self.save_path, exist_ok=True)
        self.session = lt.session({"listen_interfaces": "0.0.0.0:6881"})

        atp = lt.add_torrent_params()
        atp.save_path = self.save_path
        atp.info_hash = lt.sha1_hash(bytes.fromhex(self.info_hash_hex))
        self.handle = self.session.add_torrent(atp)
        self.handle.set_sequential_download(True)

        logging.info(f"Starting torrent: {self.info_hash_hex}")

        t = threading.Thread(target=self._wait_for_metadata, daemon=True)
        t.start()

    def _wait_for_metadata(self):
        count = 0
        while not self.handle.has_metadata():
            time.sleep(0.5)
            count += 1
            if count % 10 == 0:
                s = self.handle.status()
                logging.info(f"Waiting metadata... peers={s.num_peers}")
            if count > 120:
                logging.error("Timeout waiting for metadata")
                return
        self.metadata_received.set()
        self._setup_file()

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

        # Build the full file path
        self.file_path = os.path.join(self.save_path, ti.name(), entry.path)
        # Handle case where file is directly in save_path (single-file torrent)
        if not os.path.exists(self.file_path):
            direct = os.path.join(self.save_path, entry.path)
            if os.path.exists(direct):
                self.file_path = direct
            else:
                # Try without subdir
                self.file_path = os.path.join(self.save_path, ti.name())

        logging.info(f"Name: {self.torrent_name}")
        logging.info(f"File: {entry.path}")
        logging.info(f"Size: {self.file_size / (1024*1024):.1f} MB")
        logging.info(f"Path: {self.file_path}")

        for i in range(self.first_piece, min(self.first_piece + 30, self.first_piece + self.file_piece_count)):
            self.handle.piece_priority(i, 7)

        self.ready.set()

        # Monitor download completion
        t = threading.Thread(target=self._monitor_download, daemon=True)
        t.start()

    def _monitor_download(self):
        while True:
            s = self.handle.status()
            if s.progress >= 1.0:
                logging.info("Download complete!")
                self._download_complete.set()
                break
            if s.num_peers == 0 and s.num_seeds == 0:
                time.sleep(2)
                continue
            if int(s.progress * 100) % 10 == 0:
                logging.info(f"Progress: {s.progress*100:.0f}% DL={s.download_rate//1024}KB/s peers={s.num_peers}")
            time.sleep(2)

    def get_status(self):
        if self.handle is None:
            return {"status": "initializing"}
        s = self.handle.status()
        return {
            "status": str(s.state),
            "progress": round(s.progress * 100, 1),
            "download_rate_kb": s.download_rate // 1024,
            "num_peers": s.num_peers,
            "num_seeds": s.num_seeds,
            "file_size": self.file_size,
        }

    def read_file_range(self, start, length):
        """Read a byte range from the torrent file — from disk or from libtorrent."""
        if not self.metadata_received.is_set():
            return None

        # If download is complete, just read from disk
        if self._download_complete.is_set():
            return self._read_from_disk(start, length)

        # For streaming while downloading, try libtorrent read_piece first
        # Fall back to disk read for completed pieces
        return self._read_from_libtorrent(start, length)

    def _read_from_disk(self, start, length):
        """Read from the downloaded file on disk."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "rb") as f:
                    f.seek(start)
                    return f.read(length)
        except Exception as e:
            logging.error(f"Disk read error: {e}")
        return None

    def _read_from_libtorrent(self, start, length):
        """Read from libtorrent's piece cache."""
        piece_length = self.piece_length
        abs_start = self.file_offset + start
        abs_end = abs_start + length
        first_piece = abs_start // piece_length
        last_piece = (abs_end - 1) // piece_length

        result = bytearray()
        for piece in range(first_piece, last_piece + 1):
            # Wait for piece to be available
            max_wait = 30
            waited = 0.0
            while not self.handle.have_piece(piece) and waited < max_wait:
                time.sleep(0.2)
                waited += 0.2

            if not self.handle.have_piece(piece):
                # Try reading from disk as fallback
                disk_data = self._read_from_disk(start, length)
                if disk_data:
                    return disk_data
                return None

            data = self.handle.read_piece(piece)
            if data is None:
                return None
            result.extend(data)

        # Extract the requested byte range
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(streamer.get_status()).encode())
            return

        if not streamer.ready.is_set():
            self.send_response(503)
            self.send_header("Retry-After", "2")
            self.send_header("Access-Control-Allow-Origin", "*")
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        chunk_size = 512 * 1024  # 512KB chunks for smoother streaming
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
