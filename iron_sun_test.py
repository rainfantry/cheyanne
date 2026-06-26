import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__) if "__file__" in dir() else ".", "shell"))

# --- IRON-SUN BANNER TEST ---
CY = "\033[36m"
BL = "\033[38;2;0;56;184m"
GD = "\033[38;2;255;215;0m"
WH = "\033[38;2;255;255;255m"
RS = "\033[0m"
print()
print(f"  {CY}╔══════════════════════════════════════════════════════╗")
print(f"  ║{BL}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{CY}║")
print(f"  ║{GD}╲ ╲  ╲  │ ╲ │ ╲ │  │ ╱ │ ╱ │  ╱  ╱ ╱{RS}             {CY}║")
print(f"  ║ {GD}╲  ╲──╲──╲──╲─╲─│─╱─╱──╱──╱──╱  ╱{RS}               {CY}║")
print(f"  ║{BL}━━━━━━━━━━━━━━━━━━━━{WH}✡{BL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{CY}║")
print(f"  ║   {WH}THE  IRON-SUN  ·  AUSTRALIAN  ARMY{RS}              {CY}║")
print(f"  ║{BL}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{CY}║")
print(f"  ╚══════════════════════════════════════════════════════╝{RS}")
print()
print(f"  {CY}│{RS}  iron-sun v1.0.0 — RADON — 2026-06-26")
print(f"  {CY}│{RS}  vader_shell.c  → gcc 15.2 → 319KB → Defender CLEAN")
print(f"  {CY}│{RS}  Python 3.14.6  via Scoop (no admin)")
print(f"  {CY}│{RS}  SSH push to rainfantry/iron-sun: OK")
print(f"  {CY}│{RS}  Tag: v1.0.0")
print()
print("  DESIGNATE CALLSIGN:")
import socket, hashlib
_IDF=["kfir","tavor","golan","hermon","carmel","negev","galil","gibbor","tzuk","ofek","keshet","ariel","gilad","gideon","dagan","nimrod","samal","tzabar","sinai","shaked"]
_AUS=["digger","anzac","kokoda","tobruk","gallipoli","slouch","bushranger","cobber","wren","rats","lance","swagman","brumby","boomerang","dingo","dundee","eureka","anzio","mateship","outback"]
from datetime import datetime
fp=f"{socket.gethostname()}:{datetime.now().strftime('%Y%m%d%H')}"
h=hashlib.sha256(fp.encode()).hexdigest()
cs=f"{_IDF[int(h[0:4],16)%20]}-{_AUS[int(h[4:8],16)%20]}"
print(f"  {CY}╔══════════════════════════════════════════════════════╗")
print(f"  ║  CALLSIGN: {WH}{cs:<41}{CY}║")
print(f"  ║  REPO:     rainfantry/{cs:<34}{CY}║")
print(f"  ╚══════════════════════════════════════════════════════╝{RS}")
print()
print("  [i] gh auth login required to --create | all other ops ready")
print()
input("  [PRESS ENTER TO CLOSE]")
