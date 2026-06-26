"""
deploy_evc.py -- Upload evc.html to 22div.com.au/evc/
Usage: python deploy_evc.py
"""
import paramiko
import os
import sys

HOST = "S06ee.syd5.hostingplatform.net.au"
PORT = 2683
USER = "divcom22"
PASS = "DTCE1mpVPd"
LOCAL = os.path.join(os.path.dirname(__file__), "evc.html")
REMOTE_DIR = "public_html/evc"
REMOTE_FILE = f"{REMOTE_DIR}/index.html"

if not os.path.exists(LOCAL):
    print(f"ERROR: {LOCAL} not found")
    sys.exit(1)

print(f"Connecting to {HOST}:{PORT}...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

ssh.exec_command(f"mkdir -p {REMOTE_DIR}")
sftp = ssh.open_sftp()
sftp.put(LOCAL, REMOTE_FILE)
sftp.close()

ssh.exec_command(f"chmod 644 {REMOTE_FILE}")
print(f"Deployed: https://22div.com.au/evc/")
ssh.close()
