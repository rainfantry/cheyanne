#!/usr/bin/env python3
"""Generate an animated neon GIF header for GitHub README."""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageColor
import os

W, H = 820, 280
BG = "#0d1117"
BLUE = "#3b82f6"
LIGHT_BLUE = "#60a5fa"
WHITE = "#ffffff"
CYAN = "#93c5fd"
DIM = "#94a3b8"
GREEN = "#22c55e"

# Try to find a monospace font on Windows
FONT_PATHS = [
    r"C:\Windows\Fonts\courbd.ttf",
    r"C:\Windows\Fonts\cour.ttf",
    r"C:\Windows\Fonts\consolab.ttf",
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\lucon.ttf",
]

def get_font(size, bold=False):
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

TITLE_FONT = get_font(72, bold=True)
SUB_FONT = get_font(14)
TAG_FONT = get_font(12)
STAT_FONT = get_font(11)

def draw_text_with_glow(draw, img, text, x, y, font, color, glow_color, glow_radius):
    """Draw text with a gaussian-blur glow behind it."""
    # Create a temporary image for the glow
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.text((x, y), text, font=font, fill=glow_color, anchor="mm")
    # Blur it
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    # Composite glow onto main image
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, glow_layer)
    # Draw main text
    final_draw = ImageDraw.Draw(img_rgba)
    final_draw.text((x, y), text, font=font, fill=color, anchor="mm")
    return img_rgba

def make_frame(glow_radius, dot_alpha):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Border lines
    draw.line([(0, 2), (W, 2)], fill="#1a3a6a", width=2)
    draw.line([(0, H - 2), (W, H - 2)], fill="#1a3a6a", width=2)

    # Horizontal divider lines
    draw.line([(60, 130), (760, 130)], fill="#1e293b", width=1)
    draw.line([(60, 202), (760, 202)], fill="#1e293b", width=1)

    # Title with glow
    img = draw_text_with_glow(
        draw, img, "CHEYANNE", W // 2, 100, TITLE_FONT, WHITE,
        (*ImageColor.getrgb(LIGHT_BLUE), 180), glow_radius
    )
    draw = ImageDraw.Draw(img)

    # Subtitle
    draw.text((W // 2, 158), "WINDOWS SECURITY RESEARCH PROJECT",
              font=SUB_FONT, fill=CYAN, anchor="mm")

    # Tagline
    draw.text((W // 2, 184),
              '"Named after someone worth protecting. Built so defenders can see what attackers see."',
              font=TAG_FONT, fill=BLUE, anchor="mm")

    # Stats
    draw.text((W // 2, 228),
              "MSRC VULN-195458  ·  CERT IV CYBER SECURITY  ·  RESPONSIBLE DISCLOSURE",
              font=STAT_FONT, fill=DIM, anchor="mm")
    draw.text((W // 2, 248),
              "OWN HARDWARE  ·  DEFENDER RTP ENABLED  ·  DOCUMENTED FINDINGS ONLY",
              font=STAT_FONT, fill=DIM, anchor="mm")

    # Blinking dot
    draw.ellipse([(W - 32, 220), (W - 24, 228)], fill=(*ImageColor.getrgb(GREEN), int(dot_alpha)))

    return img.convert("RGB")

# Build frames for pulse animation
frames = []
for i in range(20):
    # Pulse glow from radius 5 to 25 and back
    t = i / 20.0
    pulse = abs((t * 2) - 1)  # 1 -> 0 -> 1
    glow_radius = 8 + (1 - pulse) * 18
    dot_alpha = 255 if i % 14 < 7 else 60
    frames.append(make_frame(glow_radius, dot_alpha))

# Save as GIF
frames[0].save(
    "cheyanne_header.gif",
    save_all=True,
    append_images=frames[1:],
    duration=80,
    loop=0,
    optimize=True
)

print("Wrote cheyanne_header.gif")
