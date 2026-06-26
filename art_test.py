#!/usr/bin/env python3
"""
Iron-Sun banner art test — run this, screenshot, iterate.
Uses mathematical ray convergence to the Star of David.
"""
import sys, os
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except: os.environ.setdefault("PYTHONIOENCODING","utf-8")

_IDF  = "\033[38;2;0;56;184m"
_GOLD = "\033[38;2;255;215;0m"
_WH   = "\033[38;2;255;255;255m"
_CY   = "\033[38;2;0;229;255m"
_DIM  = "\033[38;2;100;140;100m"
_RST  = "\033[0m"

# ── Ray engine ──────────────────────────────────────────────────────────────
# 13 rays spread across 180° arc converging to ✡ at the bottom.
# Each row: rays occupy computed columns, narrowing each row until ✡.
# Uses integer rounding + gap fill to keep rays looking solid.

def build_ray_section(num_rays=13, rows=12, inner_w=58):
    CENTER = inner_w // 2
    canvas = []

    for r in range(rows + 1):
        # Half-span: full width at top, zero at convergence row
        half = int(round(CENTER * (rows - r) / rows))
        if half == 0:
            # Convergence row
            line = list(' ' * inner_w)
            if CENTER < inner_w:
                line[CENTER] = '✡'
            canvas.append(''.join(line))
            break

        line = list(' ' * inner_w)

        # Compute position of each ray in this row
        prev_positions = []
        if r > 0 and canvas:
            # positions from previous row (for gap filling)
            pass

        positions = []
        for i in range(num_rays):
            if num_rays == 1:
                frac = 0.0
            else:
                frac = -1.0 + i * (2.0 / (num_rays - 1))
            col = int(round(CENTER + frac * half))
            positions.append(max(0, min(inner_w - 1, col)))

        for pos in positions:
            rel = pos - CENTER
            if abs(rel) <= 1:
                ch = '│'
            elif rel < -half * 0.6:
                ch = '╲'
            elif rel > half * 0.6:
                ch = '╱'
            elif rel < 0:
                ch = '╲'
            else:
                ch = '╱'
            if 0 <= pos < inner_w:
                line[pos] = ch

        canvas.append(''.join(line))

    return canvas


# ── Banner designs to compare ─────────────────────────────────────────────

def design_a():
    """Converging rays, tall, thin box"""
    W = 58
    rays = build_ray_section(num_rays=13, rows=11, inner_w=W)
    out = []
    out.append(f"  {_CY}╔{'═'*W}╗{_RST}")
    out.append(f"  {_CY}║{_IDF}{'▓'*W}{_CY}║{_RST}")
    for row in rays:
        padded = row.ljust(W)[:W]
        out.append(f"  {_CY}║{_GOLD}{padded}{_CY}║{_RST}")
    out.append(f"  {_CY}║{_IDF}{'▓'*W}{_CY}║{_RST}")
    out.append(f"  {_CY}║{_WH}{'  T H E   I R O N - S U N   ·   A U S T R A L I A N   A R M Y  '.center(W)}{_CY}║{_RST}")
    out.append(f"  {_CY}║{_IDF}{'▓'*W}{_CY}║{_RST}")
    out.append(f"  {_CY}╚{'═'*W}╝{_RST}")
    return '\n'.join(out)


def design_b():
    """Wider rays + decorative center ring + spaced title"""
    W = 58
    rays = build_ray_section(num_rays=15, rows=13, inner_w=W)
    out = []
    out.append(f"  {_CY}╔{'═'*W}╗{_RST}")
    out.append(f"  {_CY}║{_IDF}{'█'*W}{_CY}║{_RST}")
    for i, row in enumerate(rays):
        padded = row.ljust(W)[:W]
        # Color: outermost chars dimmer, center brighter
        out.append(f"  {_CY}║{_GOLD}{padded}{_CY}║{_RST}")
    # Decorative separator above title
    sep = ('─' * 8 + '◆' + '─' * 18 + '◆' + '─' * 8).center(W)
    out.append(f"  {_CY}║{_DIM}{sep}{_CY}║{_RST}")
    out.append(f"  {_CY}║{_IDF}{'▓'*W}{_CY}║{_RST}")
    title = 'T H E   I R O N - S U N   ·   A U S T R A L I A N   A R M Y'
    out.append(f"  {_CY}║{_WH}{title.center(W)}{_CY}║{_RST}")
    out.append(f"  {_CY}║{_IDF}{'▓'*W}{_CY}║{_RST}")
    out.append(f"  {_CY}╚{'═'*W}╝{_RST}")
    return '\n'.join(out)


def design_c():
    """Minimalist — rays only in upper half, bold ✡ ring, clean title"""
    W = 58
    C = W // 2
    out = []

    # Top IDF stripe
    out.append(f"\n  {_CY}╔{'═'*W}╗")
    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")

    # Ray section: 9 rows, 11 rays
    rays = build_ray_section(num_rays=11, rows=9, inner_w=W)
    for row in rays[:-1]:  # skip convergence row
        padded = row.ljust(W)[:W]
        out.append(f"  ║{_GOLD}{padded}{_CY}║")

    # ✡ center row with flanking lines
    star_line = ('━' * ((W//2)-1) + _WH + ' ✡ ' + _CY + '━' * ((W//2)-2))
    out.append(f"  ║{_IDF}{star_line}{_CY}║")

    # Title rows
    out.append(f"  ║{_WH}{'IRON-SUN  ·  AUSTRALIAN ARMY  ·  22DIV'.center(W)}{_CY}║")

    # Bottom IDF stripe
    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")
    out.append(f"  ╚{'═'*W}╝{_RST}\n")
    return '\n'.join(out)


def design_d():
    """Art approach: wide rays + double IDF stripe + large title"""
    W = 66
    rays = build_ray_section(num_rays=17, rows=14, inner_w=W)

    out = []
    out.append(f"\n  {_CY}╔{'═'*W}╗")
    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")
    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")

    for row in rays:
        padded = row.ljust(W)[:W]
        out.append(f"  ║{_GOLD}{padded}{_CY}║")

    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")
    title1 = 'T H E   I R O N ─ S U N'
    title2 = 'A U S T R A L I A N   A R M Y   ·   2 2 D I V'
    out.append(f"  ║{_WH}{title1.center(W)}{_CY}║")
    out.append(f"  ║{_WH}{title2.center(W)}{_CY}║")
    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")
    out.append(f"  ║{_IDF}{'▓'*W}{_CY}║")
    out.append(f"  ╚{'═'*W}╝{_RST}\n")
    return '\n'.join(out)


# ── Print all designs ────────────────────────────────────────────────────────
print(f"\n{'═'*70}")
print(f"  {_WH}DESIGN A — 13 rays, 11 rows, single stripe{_RST}")
print(f"{'═'*70}")
print(design_a())

print(f"\n{'═'*70}")
print(f"  {_WH}DESIGN B — 15 rays, 13 rows, decorative sep{_RST}")
print(f"{'═'*70}")
print(design_b())

print(f"\n{'═'*70}")
print(f"  {_WH}DESIGN C — 11 rays, 9 rows, star center bar{_RST}")
print(f"{'═'*70}")
print(design_c())

print(f"\n{'═'*70}")
print(f"  {_WH}DESIGN D — 17 rays, 14 rows, double stripe, wide{_RST}")
print(f"{'═'*70}")
print(design_d())

input(f"\n  {_CY}[PRESS ENTER TO CLOSE]{_RST}")
