# Whale in a Teacup — entry for make.fun competition ai-excited-01.
#
# A single-file, pure standard-library Python program. It paints one
# 1024x1024 picture with a small software rasterizer and saves it as a
# PNG to $MAKEFUN_OUTPUT_DIR/entry.png (falling back to /output/entry.png).
#
# The scene, in one glance: a colossal blue whale breaches out of a giant
# teacup that towers over a tiny night city, while the spray bursting from
# the cup climbs into the sky and turns into gold stars under a huge dusk
# moon. Impossible scale, a body in full motion, water becoming starlight.
# There is no text anywhere in the picture.
#
# The output is fully deterministic. One fixed RNG seed drives every
# random choice, every colour and coordinate is a literal, and the PNG
# encoder always uses zlib level 9 with no filtering and no ancillary
# chunks, so repeated runs produce byte-identical files. This file was
# restructured in the recorded session (renamed rasterizer and painters,
# extracted helpers) without changing any rendered pixel.
#
# Run locally:  mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py

import binascii
import hashlib
import math
import os
import random
import struct
import sys
import zlib

W = 1024
H = 1024
SEED = 20261116


# ---------------------------------------------------------------------------
# Palette
#
# Dusk sky, hazy city, cream cup with a teal band, cold water and spray,
# the whale in three blues, and the gold the spray turns into.
# ---------------------------------------------------------------------------

SKY_TOP = (11, 16, 53)
SKY_MID = (43, 32, 94)
SKY_LOW = (122, 48, 110)
SKY_HORIZON = (255, 126, 74)
CITY_FAR = (32, 24, 64)
CITY_NEAR = (16, 12, 38)
WINDOW = (255, 196, 110)
MOON = (255, 244, 214)
CRATER = (232, 214, 172)
CUP = (247, 234, 210)
CUP_SHADE = (222, 205, 175)
CUP_BAND = (18, 148, 164)
CUP_STRIPE = (255, 110, 90)
SAUCER = (232, 214, 184)
WATER = (127, 231, 255)
SPLASH = (255, 255, 255)
SPRAY = (190, 235, 255)
WHALE = (24, 84, 160)
WHALE_DARK = (16, 64, 130)
WHALE_LIGHT = (90, 170, 225)
BELLY = (191, 227, 255)
GOLD = (255, 214, 120)


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------

def blend(a, b, t):
    """Linear blend of two RGB triples, channel by channel."""
    return tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))


def quadratic_bezier(p0, c, p1, t):
    """Point on a quadratic Bezier curve at parameter t."""
    u = 1.0 - t
    x = u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0]
    y = u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]
    return x, y


# ---------------------------------------------------------------------------
# Framebuffer
#
# The picture lives as one bytearray per row. A horizontal fill is a single
# slice assignment, which keeps a 1024x1024 scene fast in pure Python.
# ---------------------------------------------------------------------------

class Framebuffer:
    """An RGB framebuffer with span fills and scanline shapes."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.rows = [bytearray(3 * width) for _ in range(height)]

    def fill_span(self, y, x0, x1, rgb):
        """Paint pixels x0..x1-1 of row y in one colour, clipped."""
        if y < 0 or y >= self.h:
            return
        left = max(0, int(x0))
        right = min(self.w, int(x1))
        if right <= left:
            return
        row = self.rows[y]
        row[3 * left:3 * right] = bytes(rgb) * (right - left)

    def _gradient_row(self, y, stops):
        """Colour of row y for a vertical gradient through `stops`."""
        for i in range(len(stops) - 1):
            y0, c0 = stops[i]
            y1, c1 = stops[i + 1]
            if y0 <= y <= y1:
                t = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
                return blend(c0, c1, t)
        if y > stops[-1][0]:
            return stops[-1][1]
        return stops[0][1]

    def vertical_gradient(self, stops):
        """Paint the whole frame with a vertical gradient.

        `stops` is a list of (y, (r, g, b)) sorted by y.
        """
        for y in range(self.h):
            self.rows[y] = bytearray(bytes(self._gradient_row(y, stops)) * self.w)

    def fill_ellipse(self, cx, cy, rx, ry, rgb):
        """Paint a filled axis-aligned ellipse."""
        rx = float(rx)
        ry = float(ry)
        if rx <= 0 or ry <= 0:
            return
        first = max(0, int(math.ceil(cy - ry)))
        last = min(self.h - 1, int(math.floor(cy + ry)))
        for y in range(first, last + 1):
            dy = (y - cy) / ry
            q = 1.0 - dy * dy
            if q < 0:
                continue
            dx = rx * math.sqrt(q)
            self.fill_span(y, math.ceil(cx - dx), math.floor(cx + dx) + 1, rgb)

    def fill_disc(self, cx, cy, r, rgb):
        self.fill_ellipse(cx, cy, r, r, rgb)

    def fill_polygon(self, points, rgb):
        """Paint a filled polygon (scanline, even-odd rule)."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        first = max(0, int(math.ceil(min(ys))))
        last = min(self.h - 1, int(math.floor(max(ys))))
        count = len(points)
        for y in range(first, last + 1):
            # Sample at the row centre, then fill between crossing pairs.
            scan_y = y + 0.5
            crossings = []
            for i in range(count):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % count]
                if (y1 <= scan_y < y2) or (y2 <= scan_y < y1):
                    t = (scan_y - y1) / (y2 - y1)
                    crossings.append(x1 + t * (x2 - x1))
            crossings.sort()
            for i in range(0, len(crossings) - 1, 2):
                self.fill_span(y, math.ceil(crossings[i]),
                               math.floor(crossings[i + 1]) + 1, rgb)

    def stroke_polyline(self, points, radius, rgb):
        """Paint a thick polyline as a chain of overlapping discs."""
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dist = max(1.0, math.hypot(x2 - x1, y2 - y1))
            steps = int(dist / max(1.0, radius * 0.6)) + 1
            for s in range(steps + 1):
                t = s / steps
                self.fill_disc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t,
                               radius, rgb)

    def star(self, cx, cy, r, rgb):
        """Paint a four-point star: a droplet that has become a star."""
        pts = []
        for i in range(8):
            ang = math.pi / 2 * i - math.pi / 2
            rr = r if i % 2 == 0 else r * 0.22
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        self.fill_polygon(pts, rgb)


# ---------------------------------------------------------------------------
# Sky, stars, moon
# ---------------------------------------------------------------------------

def paint_sky(fb):
    fb.vertical_gradient([
        (0, SKY_TOP),
        (260, SKY_MID),
        (480, SKY_LOW),
        (660, (214, 82, 92)),
        (730, SKY_HORIZON),
        (790, (48, 26, 72)),
        (H - 1, (20, 14, 44)),
    ])


def _milky_way(fb, rng):
    # A denser diagonal band of faint stars behind the whale.
    for _ in range(170):
        t = rng.random()
        x = t * W
        y = 60 + t * 330 + rng.gauss(0, 70)
        if 0 <= y < 660:
            b = rng.choice([150, 180, 210])
            fb.fill_disc(x, y, rng.choice([1, 1, 1, 2]), (b, b, min(255, b + 25)))


def _scattered_stars(fb, rng):
    # Stars scattered over the upper two thirds of the sky.
    for _ in range(240):
        x = rng.random() * W
        y = rng.random() * 660
        b = rng.choice([200, 220, 235, 255])
        r = rng.choice([1, 1, 1, 2, 2, 3])
        fb.fill_disc(x, y, r, (b, b, min(255, b + 15)))


def _bright_sparkles(fb, rng):
    # A few bright four-point sparkles.
    for _ in range(12):
        x = rng.random() * W
        y = rng.random() * 520
        fb.star(x, y, rng.choice([5, 6, 7, 9]), (255, 255, 255))


def paint_stars(fb, rng):
    _milky_way(fb, rng)
    _scattered_stars(fb, rng)
    _bright_sparkles(fb, rng)


def paint_moon(fb):
    cx, cy = 795, 175
    # Soft glow rings, then the disc itself.
    fb.fill_ellipse(cx, cy, 235, 235, (30, 28, 80))
    fb.fill_ellipse(cx, cy, 168, 168, (52, 46, 110))
    fb.fill_ellipse(cx, cy, 126, 126, (110, 96, 160))
    fb.fill_ellipse(cx, cy, 104, 104, (140, 125, 180))
    fb.fill_disc(cx, cy, 92, MOON)
    for dx, dy, r in [(-30, -18, 14), (22, 12, 18), (-8, 34, 11),
                      (38, -32, 9), (-48, 28, 8)]:
        fb.fill_disc(cx + dx, cy + dy, r, CRATER)


# ---------------------------------------------------------------------------
# City
# ---------------------------------------------------------------------------

def _far_skyline(fb, rng):
    # Low, hazy silhouettes.
    x = -20
    while x < W + 20:
        bw = rng.randint(50, 110)
        bh = rng.randint(40, 110)
        fb.fill_polygon([(x, H), (x, 830 - bh), (x + bw, 830 - bh), (x + bw, H)],
                        CITY_FAR)
        x += bw + rng.randint(4, 18)


def _near_towers(fb, rng):
    # Tall dark towers with lit windows.
    x = -30
    while x < W + 30:
        bw = rng.randint(45, 105)
        bh = rng.randint(70, 200)
        top = 1000 - bh
        fb.fill_polygon([(x, H), (x, top), (x + bw, top), (x + bw, H)], CITY_NEAR)
        if rng.random() < 0.3:
            fb.fill_span(top - 26, x + bw // 2 - 2, x + bw // 2 + 2, CITY_NEAR)
            fb.fill_disc(x + bw // 2, top - 30, 3, (255, 80, 70))
        for wy in range(top + 16, 985, 22):
            for wx in range(x + 10, x + bw - 8, 16):
                if rng.random() < 0.5:
                    fb.fill_span(wy, wx, wx + 5, WINDOW)
                    fb.fill_span(wy + 1, wx, wx + 5, WINDOW)
                    fb.fill_span(wy + 2, wx, wx + 5, WINDOW)
        x += bw + rng.randint(6, 22)


def paint_city(fb, rng):
    _far_skyline(fb, rng)
    _near_towers(fb, rng)


# ---------------------------------------------------------------------------
# Teacup
# ---------------------------------------------------------------------------

def paint_teacup(fb):
    # Saucer.
    fb.fill_ellipse(400, 922, 235, 30, (208, 188, 156))
    fb.fill_ellipse(400, 914, 235, 30, SAUCER)
    fb.fill_ellipse(400, 912, 200, 22, (244, 228, 200))
    # Handle: thick cream arc on the right, dark hole showing the city.
    arc = [(578, 742), (622, 748), (656, 782), (662, 826),
           (640, 866), (596, 884), (566, 872)]
    fb.stroke_polyline(arc, 17, CUP)
    fb.stroke_polyline(arc, 8, CITY_NEAR)
    # Cup body.
    fb.fill_polygon([(222, 706), (578, 706), (532, 908), (268, 908)], CUP)
    # Left-side shading and right-edge highlight.
    fb.fill_polygon([(222, 706), (300, 706), (292, 908), (268, 908)], CUP_SHADE)
    fb.fill_polygon([(548, 706), (578, 706), (532, 908), (516, 908)], (255, 246, 226))
    # Bold teal band and coral stripe.
    fb.fill_polygon([(232, 762), (568, 762), (560, 800), (240, 800)], CUP_BAND)
    fb.fill_polygon([(238, 808), (562, 808), (559, 820), (241, 820)], CUP_STRIPE)
    # Rim and water.
    fb.fill_ellipse(400, 706, 192, 44, (214, 196, 168))
    fb.fill_ellipse(400, 704, 178, 36, WATER)
    fb.fill_ellipse(360, 698, 90, 14, (210, 248, 255))
    # Splash crown where the whale bursts out of the cup.
    for dx, r in [(-150, 16), (-110, 22), (-66, 26), (-20, 20), (28, 26),
                  (74, 22), (118, 18), (152, 13)]:
        fb.fill_disc(400 + dx, 692 - abs(dx) // 9, r, SPLASH)
    for dx, r in [(-130, 10), (-88, 13), (-44, 11), (4, 13), (52, 11),
                  (96, 10), (136, 8)]:
        fb.fill_disc(400 + dx, 678 - abs(dx) // 10, r, SPRAY)


# ---------------------------------------------------------------------------
# Whale
# ---------------------------------------------------------------------------

def _body_half_width(t, half_width):
    """Half-width of the whale body at fraction t along its axis.

    Blunt at the head, fullest about a third of the way back, narrow at
    the tail stock.
    """
    base = math.sin(math.pi * (0.12 + 0.88 * t)) ** 0.65
    taper = 1.0 - 0.86 * max(0.0, (t - 0.5) / 0.5) ** 1.6
    return half_width * base * taper


def whale_outline(head, tail, half_width, perp_offset=0.0):
    """Outline of a whale body as a polygon.

    A blunt rounded head, widest a third of the way back, tapering to a
    narrow tail stock, with a rounded head cap closing the snout.
    """
    hx, hy = head
    tx, ty = tail
    dx, dy = tx - hx, ty - hy
    length = math.hypot(dx, dy)
    dx, dy = dx / length, dy / length
    # Perpendicular; +p is the dorsal (upper-left) side here.
    px, py = -dy, dx
    ox, oy = px * perp_offset, py * perp_offset

    top, bottom = [], []
    steps = 40
    for i in range(steps + 1):
        t = i / steps
        ax = hx + dx * length * t + ox
        ay = hy + dy * length * t + oy
        w = _body_half_width(t, half_width)
        top.append((ax + px * w, ay + py * w))
        bottom.append((ax - px * w, ay - py * w))
    # Rounded head cap: a half-arc from the bottom edge start (B) around
    # the snout tip (head minus the axis direction) to the top edge start.
    cap = []
    w0 = _body_half_width(0.0, half_width)
    for i in range(1, 12):
        phi = math.pi * (1 - i / 12)
        cap.append((hx + ox + px * w0 * math.cos(phi)
                    - dx * w0 * 0.9 * math.sin(phi),
                    hy + oy + py * w0 * math.cos(phi)
                    - dy * w0 * 0.9 * math.sin(phi)))
    return top + list(reversed(bottom)) + cap


def paint_whale(fb):
    head = (762, 358)
    tail = (455, 600)
    # Tail flukes first (behind the body): two broad lobes fanning out
    # from the tail tip, clearly forked, clear of the cup rim. Each is a
    # wide triangle with its base across the tail tip, so it merges with
    # the body instead of floating beside it.
    fb.fill_polygon([(470, 579), (330, 505), (395, 560), (440, 621)], WHALE_DARK)
    fb.fill_polygon([(437, 581), (350, 700), (405, 645), (473, 619)], WHALE_DARK)
    # Top sheen, belly, then the body itself: each later layer leaves a
    # crescent of the one beneath it showing along one edge.
    fb.fill_polygon(whale_outline(head, tail, 80, perp_offset=-16), WHALE_LIGHT)
    fb.fill_polygon(whale_outline(head, tail, 82, perp_offset=15), BELLY)
    fb.fill_polygon(whale_outline(head, tail, 95), WHALE)
    # No pectoral fin: in this breach pose it read as a detached slab,
    # and the whale reads cleanly without it.
    # Eye and the long curved mouth of the head (upper-right end).
    fb.fill_disc(738, 332, 7, SPLASH)
    fb.fill_disc(740, 332, 3, (8, 20, 40))
    mouth = [(698, 438), (724, 422), (754, 402), (776, 376), (790, 352)]
    fb.stroke_polyline(mouth, 2, (12, 48, 96))


# ---------------------------------------------------------------------------
# Spray
# ---------------------------------------------------------------------------

def paint_spray(fb, rng):
    # Parabolic arcs of droplets bursting from the cup and arcing through
    # the open sky beside the whale, never across its body. The highest
    # droplets turn gold: water becoming stars, rising toward the moon.
    arcs = [
        ((470, 685), (430, 420), (640, 290), 26),
        ((420, 690), (330, 480), (470, 330), 22),
        ((505, 690), (520, 560), (560, 470), 14),
    ]
    for p0, c, p1, count in arcs:
        for i in range(count):
            t = i / max(1, count - 1)
            x, y = quadratic_bezier(p0, c, p1, t)
            x += rng.gauss(0, 12)
            y += rng.gauss(0, 10)
            r = rng.choice([2, 2, 3, 3, 4])
            if t > 0.7 and rng.random() < 0.6:
                fb.star(x, y, r + 4, GOLD)
            else:
                fb.fill_disc(x, y, r, rng.choice([SPLASH, SPRAY, SPRAY]))
    # A rising trail of gold stars from the whale's head up past the moon.
    for i in range(6):
        t = i / 5
        x = 745 + (665 - 745) * t + rng.gauss(0, 8)
        y = 295 - (295 - 185) * t + rng.gauss(0, 7)
        fb.star(x, y, 12 - i, GOLD)


def render():
    rng = random.Random(SEED)
    fb = Framebuffer(W, H)
    paint_sky(fb)
    paint_stars(fb, rng)
    paint_moon(fb)
    paint_city(fb, rng)
    paint_teacup(fb)
    paint_whale(fb)
    paint_spray(fb, rng)
    return fb


# ---------------------------------------------------------------------------
# PNG encoding
# ---------------------------------------------------------------------------

def _png_chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    return out


def encode_png(fb):
    raw = bytearray()
    for row in fb.rows:
        raw.append(0)  # filter: None
        raw += row
    compressed = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", compressed) + _png_chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    data = encode_png(render())
    with open(path, "wb") as f:
        f.write(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"Wrote {path}: {W}x{H}, {len(data)} bytes, sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
