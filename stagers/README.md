# PHASE 5 — STAGERS AND DROPPERS

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Status: PENDING — Operational tooling, build when needed

---

## Objective

Small binary that downloads and executes the full payload.
Minimizes on-disk footprint. Evasion through size and simplicity.

## Architecture

```
STAGER (tiny, ~5KB)
    → Connect to C2
    → Download full payload to memory
    → Execute in-memory (no disk write)
    → Payload takes over (reverse shell, rootkit modules)
```

## Techniques

### HTTP Stager
- WinHTTP/WinInet to download payload from C2 web server
- Execute from memory via VirtualAlloc + CreateThread
- No file written to disk → no Defender file scan

### DNS Stager
- Encode payload in DNS TXT records
- Standard user can make DNS queries
- Exfiltrate data via DNS queries (low bandwidth but stealthy)

### SMB Stager
- Load payload from SMB share on attacker's machine
- Works on LAN without internet access

## Implementation Plan

Build when Phases 1-4 produce tools worth staging.
The reverse shell (Phase 0) is currently self-contained — no stager needed yet.

## Files (when built)

```
stagers/
+-- http_stager_annotated.c  # HTTP download + execute
+-- stager.c                 # Deployment variant
+-- README.md                # This file
```
