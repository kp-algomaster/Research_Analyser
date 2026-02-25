#!/usr/bin/env python3
"""
Generate Research Analyser macOS app icon (.icns).

Design concept:
  • Deep navy-to-indigo radial gradient background
  • White paper/document card (slight tilt) with subtle text-rule lines
  • Amber/gold knowledge-graph overlay: nodes + edges representing diagram generation
  • Small circular review-badge bottom-right (magnifying glass glyph)

Run:  python3 packaging/make_icon.py
Output: packaging/icon.icns   (and packaging/icon.iconset/ for inspection)
"""

import math
import os
import subprocess
import sys

# ── Require Pillow ─────────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw, ImageFilter

# ── Palette ────────────────────────────────────────────────────────────────────
BG_CENTER   = (18,  40,  80)   # deep navy (center of radial gradient)
BG_EDGE     = ( 6,  14,  36)   # very dark navy (edges)
PAPER_FILL  = (245, 248, 252)  # near-white card
PAPER_EDGE  = (210, 220, 235)  # subtle card shadow
LINE_CLR    = (190, 200, 218)  # rule lines on paper
NODE_CLR    = (255, 168,  40)  # amber/gold nodes
EDGE_CLR    = (255, 168,  40)  # graph edges (same amber)
EDGE_ALPHA  = 160              # edge opacity (0-255)
BADGE_BG    = (255, 168,  40)  # badge circle — amber
BADGE_FG    = (255, 255, 255)  # badge glyph — white


def _radial_gradient(size: int) -> Image.Image:
    """Create a dark navy radial gradient background."""
    img = Image.new("RGBA", (size, size))
    cx = cy = size / 2
    max_r = size * 0.72  # gradient reaches edges

    pixels = img.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            t = min(d / max_r, 1.0)
            t = t ** 1.6  # darken edges faster
            r = round(BG_CENTER[0] * (1 - t) + BG_EDGE[0] * t)
            g = round(BG_CENTER[1] * (1 - t) + BG_EDGE[1] * t)
            b = round(BG_CENTER[2] * (1 - t) + BG_EDGE[2] * t)
            pixels[x, y] = (r, g, b, 255)
    return img


def _rounded_rect_mask(size: int, radius: int) -> Image.Image:
    """Alpha mask for a rounded-square icon."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _draw_paper(draw: ImageDraw.ImageDraw, cx: float, cy: float,
                w: float, h: float, angle_deg: float, size: int) -> None:
    """Draw the tilted white paper card with a subtle drop shadow and rule lines."""

    def _rot(px, py):
        a = math.radians(angle_deg)
        rx = (px - cx) * math.cos(a) - (py - cy) * math.sin(a) + cx
        ry = (px - cx) * math.sin(a) + (py - cy) * math.cos(a) + cy
        return rx, ry

    hw, hh = w / 2, h / 2
    corners = [
        _rot(cx - hw, cy - hh),
        _rot(cx + hw, cy - hh),
        _rot(cx + hw, cy + hh),
        _rot(cx - hw, cy + hh),
    ]

    # Drop shadow (offset + blurred via a separate layer)
    shadow_off = size * 0.018
    shadow_pts = [(x + shadow_off, y + shadow_off) for x, y in corners]
    draw.polygon(shadow_pts, fill=(0, 0, 0, 60))

    # Paper fill
    draw.polygon(corners, fill=PAPER_FILL + (255,))

    # Subtle rule lines across the card
    num_lines = 8
    a = math.radians(angle_deg)
    for i in range(num_lines):
        t = (i + 1) / (num_lines + 1)
        fy = cy - hh + h * t          # y along card height (un-rotated)
        # Left & right endpoints on this rule line
        lx, ly = _rot(cx - hw * 0.82, fy)
        rx_, ry = _rot(cx + hw * 0.82, fy)
        draw.line([(lx, ly), (rx_, ry)], fill=LINE_CLR + (255,), width=max(1, round(size * 0.004)))


def _draw_graph(draw: ImageDraw.ImageDraw, cx: float, cy: float,
                size: int) -> None:
    """Draw an amber knowledge-graph overlay (nodes + edges)."""
    s = size
    # Node positions (relative to icon centre, as fractions of size)
    # Nodes are arranged in a loose network pattern — lower-left quadrant of icon
    nodes = [
        (cx - s * 0.04,  cy + s * 0.06),   # 0 — hub (large)
        (cx - s * 0.21,  cy - s * 0.04),   # 1
        (cx - s * 0.19,  cy + s * 0.22),   # 2
        (cx + s * 0.14,  cy + s * 0.20),   # 3
        (cx + s * 0.22,  cy - s * 0.04),   # 4
        (cx + s * 0.02,  cy - s * 0.22),   # 5
    ]
    # Edges
    edges = [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 5), (3, 4)]

    nr = [s * 0.060, s * 0.038, s * 0.038, s * 0.038, s * 0.038, s * 0.038]

    # Draw edges first (behind nodes)
    edge_w = max(2, round(s * 0.013))
    for a_idx, b_idx in edges:
        ax, ay = nodes[a_idx]
        bx, by = nodes[b_idx]
        draw.line([(ax, ay), (bx, by)], fill=EDGE_CLR + (EDGE_ALPHA,), width=edge_w)

    # Draw nodes
    for i, (nx, ny) in enumerate(nodes):
        r = nr[i]
        # Outer glow ring
        glow_r = r * 1.45
        draw.ellipse(
            [(nx - glow_r, ny - glow_r), (nx + glow_r, ny + glow_r)],
            fill=NODE_CLR + (50,),
        )
        # Node fill
        draw.ellipse(
            [(nx - r, ny - r), (nx + r, ny + r)],
            fill=NODE_CLR + (255,),
        )
        # White inner highlight
        hr = r * 0.38
        draw.ellipse(
            [(nx - hr, ny - hr + r * 0.06), (nx + hr, ny - hr * 0.4 + r * 0.06)],
            fill=(255, 255, 255, 160),
        )


def _draw_badge(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Draw a circular amber badge with a magnifying-glass glyph (bottom-right)."""
    br = size * 0.118          # badge radius
    bx = size * 0.755          # centre-x
    by = size * 0.750          # centre-y

    # Badge shadow
    draw.ellipse(
        [(bx - br + size * 0.015, by - br + size * 0.015),
         (bx + br + size * 0.015, by + br + size * 0.015)],
        fill=(0, 0, 0, 70),
    )
    # Badge circle
    draw.ellipse(
        [(bx - br, by - br), (bx + br, by + br)],
        fill=BADGE_BG + (255,),
    )
    # White border ring
    ring_w = max(2, round(size * 0.008))
    draw.ellipse(
        [(bx - br, by - br), (bx + br, by + br)],
        outline=(255, 255, 255, 200), width=ring_w,
    )

    # Magnifying glass glyph in white
    mg_r = br * 0.42           # lens circle radius
    mg_cx = bx - br * 0.10    # lens centre x
    mg_cy = by - br * 0.10    # lens centre y
    lw = max(2, round(size * 0.013))

    # Lens ring
    draw.ellipse(
        [(mg_cx - mg_r, mg_cy - mg_r), (mg_cx + mg_r, mg_cy + mg_r)],
        outline=BADGE_FG + (255,), width=lw,
    )
    # Handle — starts at ~SE of lens ring, goes SE
    angle_handle = math.radians(45)
    hx0 = mg_cx + mg_r * math.cos(angle_handle)
    hy0 = mg_cy + mg_r * math.sin(angle_handle)
    hx1 = mg_cx + (mg_r + br * 0.50) * math.cos(angle_handle)
    hy1 = mg_cy + (mg_r + br * 0.50) * math.sin(angle_handle)
    draw.line([(hx0, hy0), (hx1, hy1)], fill=BADGE_FG + (255,), width=lw + 1)


def render_icon(size: int) -> Image.Image:
    """Render the icon at `size` × `size` pixels (RGBA)."""

    # ── Background ──────────────────────────────────────────────────────────
    img = _radial_gradient(size)
    draw = ImageDraw.Draw(img, "RGBA")

    # ── Paper card ──────────────────────────────────────────────────────────
    paper_w = size * 0.56
    paper_h = size * 0.64
    # Centre the card slightly upper-left so graph extends to lower-right
    _draw_paper(draw, size * 0.45, size * 0.44, paper_w, paper_h, angle_deg=-7, size=size)

    # ── Knowledge graph ──────────────────────────────────────────────────────
    _draw_graph(draw, size * 0.50, size * 0.50, size)

    # ── Review badge ─────────────────────────────────────────────────────────
    _draw_badge(draw, size)

    # ── Apply rounded-square mask ────────────────────────────────────────────
    # macOS icon corner radius ~ 22.4% of size
    corner_r = round(size * 0.224)
    mask = _rounded_rect_mask(size, corner_r)
    img.putalpha(mask)

    return img


# ── macOS iconset sizes ────────────────────────────────────────────────────────
ICONSET_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def build_icns(out_dir: str = "packaging") -> str:
    iconset_dir = os.path.join(out_dir, "icon.iconset")
    icns_path   = os.path.join(out_dir, "icon.icns")
    os.makedirs(iconset_dir, exist_ok=True)

    print("Rendering icon sizes…")
    for s in ICONSET_SIZES:
        img = render_icon(s)

        # 1× name
        name_1x = f"icon_{s}x{s}.png"
        img.save(os.path.join(iconset_dir, name_1x), format="PNG")
        print(f"  {name_1x}")

        # 2× name (half the logical size, same pixel count = @2x)
        if s >= 32:
            half = s // 2
            name_2x = f"icon_{half}x{half}@2x.png"
            img.save(os.path.join(iconset_dir, name_2x), format="PNG")
            print(f"  {name_2x}")

    # iconutil (macOS built-in) converts iconset → .icns
    print("Packaging .icns via iconutil…")
    result = subprocess.run(
        ["iconutil", "-c", "icns", "-o", icns_path, iconset_dir],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("iconutil error:", result.stderr)
        sys.exit(1)

    size_kb = os.path.getsize(icns_path) // 1024
    print(f"Created: {icns_path}  ({size_kb} KB)")
    return icns_path


if __name__ == "__main__":
    build_icns()
