#!/usr/bin/env python3
"""Convert CHEYANNE ASCII banner into pixel-perfect SVG rectangles."""

ASCII_ART = r"""
  ██████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ███╗   ██╗███╗   ██╗███████╗
 ██╔════╝██║  ██║██╔════╝╚██╗ ██╔╝██╔══██╗████╗  ██║████╗  ██║██╔════╝
 ██║     ███████║█████╗   ╚████╔╝ ███████║██╔██╗ ██║██╔██╗ ██║█████╗  
 ██║     ██╔══██║██╔══╝    ╚██╔╝  ██╔══██║██║╚██╗██║██║╚██╗██║██╔══╝  
 ╚██████╗██║  ██║███████╗   ██║   ██║  ██║██║ ╚████║██║ ╚████║███████╗
  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝
""".strip("\n")

CELL_W = 4
CELL_H = 8
MARGIN_X = 20
MARGIN_Y = 42
GAP_X = 3
GAP_Y = 4

def art_to_rects(art):
    rects = []
    for row_idx, line in enumerate(art.splitlines()):
        y = MARGIN_Y + row_idx * (CELL_H + GAP_Y)
        for col_idx, ch in enumerate(line):
            if ch != " ":
                x = MARGIN_X + col_idx * (CELL_W + GAP_X)
                rects.append(f'    <rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}"/>')
    return "\n".join(rects)

lines = ASCII_ART.splitlines()
banner_w = max(len(line) for line in lines) * (CELL_W + GAP_X)
banner_h = len(lines) * (CELL_H + GAP_Y)
view_w = max(820, banner_w + MARGIN_X * 2)
view_h = 280

svg = f"""<svg viewBox="0 0 {view_w} {view_h}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      .glow  {{ animation: glow-pulse 3s ease-in-out infinite; }}
      .sub   {{ font-family: 'Courier New', Courier, monospace; font-size: 13px; fill: #93c5fd; }}
      .tag   {{ font-family: 'Courier New', Courier, monospace; font-size: 12px; fill: #3b82f6; font-style: italic; }}
      .stat  {{ font-family: 'Courier New', Courier, monospace; font-size: 11px; fill: #94a3b8; }}
      .dot   {{ fill: #22c55e; animation: blink 1.4s step-end infinite; }}
      @keyframes glow-pulse {{
        0%,100% {{ filter: drop-shadow(0 0 1px #2563eb); }}
        50%     {{ filter: drop-shadow(0 0 4px #3b82f6) drop-shadow(0 0 8px #2563eb); }}
      }}
      @keyframes blink {{
        0%,100% {{ opacity: 1; }}
        50%     {{ opacity: 0; }}
      }}
    </style>
  </defs>

  <rect width="{view_w}" height="{view_h}" fill="#0d1117" rx="8"/>
  <line x1="0"   y1="2"   x2="{view_w}" y2="2"   stroke="#2563eb" stroke-width="2" opacity="0.3"/>
  <line x1="0"   y1="{view_h-2}" x2="{view_w}" y2="{view_h-2}" stroke="#2563eb" stroke-width="2" opacity="0.3"/>

  <g class="glow" fill="#60a5fa">
{art_to_rects(ASCII_ART)}
  </g>

  <line x1="14" y1="136" x2="{view_w-14}" y2="136" stroke="#1e293b" stroke-width="1"/>

  <text x="14" y="158" class="sub">W I N D O W S   S E C U R I T Y   R E S E A R C H   P R O J E C T</text>
  <text x="14" y="180" class="tag">"Named after someone worth protecting. Built so defenders can see what attackers see."</text>

  <line x1="14" y1="196" x2="{view_w-14}" y2="196" stroke="#1e293b" stroke-width="1"/>

  <text x="14" y="216" class="stat">MSRC  VULN-195458   ·   CERT IV CYBER SECURITY   ·   RESPONSIBLE DISCLOSURE</text>
  <text x="14" y="234" class="stat">OWN HARDWARE   ·   DEFENDER RTP ENABLED   ·   DOCUMENTED FINDINGS ONLY</text>

  <circle cx="{view_w-24}" cy="216" r="4" class="dot"/>
</svg>
"""

with open("cheyanne_header.svg", "w", encoding="utf-8") as f:
    f.write(svg)

print(f"Wrote cheyanne_header.svg ({view_w}x{view_h}, {len(ASCII_ART.splitlines())} lines)")
