"""
test_listener.py — Simulated session client for listener.py proof test
Connects to localhost:4443, responds to whoami/hostname like a real implant.
Run AFTER listener.py is running.
"""
import socket, time, sys

HOST = "127.0.0.1"
PORT = 4443

print(f"[*] Connecting to {HOST}:{PORT} ...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
print("[+] Connected")

# send greeting (what ghost_loader sends on connect)
s.sendall(b"OK> \n")
time.sleep(0.3)

def respond(sock, expected_cmd, response):
    """Wait for a command and send a fake response."""
    buf = b""
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            sock.settimeout(1.0)
            chunk = sock.recv(4096)
            if chunk:
                buf += chunk
                if expected_cmd.encode() in buf:
                    sock.sendall((response + "\n").encode())
                    print(f"  >> {expected_cmd!r} -> replied: {response!r}")
                    return
        except socket.timeout:
            pass

respond(s, "whoami", "LAPTOP-R32M8MLI\\gwu07")
respond(s, "hostname", "LAPTOP-R32M8MLI")

print("[+] Session handshake complete — staying alive for 30s")
print("[*] Listener should now show: [+] NEW SESSION ...")
s.settimeout(30)
try:
    while True:
        data = s.recv(4096)
        if not data:
            break
        cmd = data.decode(errors="replace").strip()
        print(f"  [CMD] {cmd!r}")
        # echo a fake response
        s.sendall((f"[simulated output for: {cmd}]\n").encode())
except Exception as e:
    print(f"[*] Done: {e}")
finally:
    s.close()
    print("[*] Test client disconnected")
