"""
CHEYANNE — Shared Configuration
Auto-detects build environment. Import from any module.
"""
import os
import glob


def find_vcvars():
    """Auto-detect vcvars64.bat across Visual Studio versions."""
    search_paths = [
        r"C:\Program Files\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat",
    ]
    for pattern in search_paths:
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    return None


VCVARS = find_vcvars() or r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
C2_PORT = 4443
RECV_PORT = 8891
VIEW_PORT = 8892
UI_PORT = 8666
AGENT_PORT = 8667
SERVE_PORT = 8890
