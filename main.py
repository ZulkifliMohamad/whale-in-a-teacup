# Whale in a Teacup — make.fun ai-excited-01 entry.
#
# One file, Python 3 standard library only. It renders a single
# 1024x1024 image with a tiny software rasterizer and writes it as a
# PNG to $MAKEFUN_OUTPUT_DIR/entry.png (or /output/entry.png).
#
# What the picture shows: a giant blue whale breaching out of an
# oversized teacup that looms over a miniature night city. Spray flies
# out of the cup, climbs the sky and turns to gold stars below a big
# dusk moon. No text appears anywhere in the image.
#
# The render is fully deterministic: a single fixed seed feeds every
# random draw, all colours and coordinates are literals, and the PNG
# writer uses zlib level 9, no filtering and no extra chunks, so every
# run writes a byte-identical file.
#
# This file was restructured a second time inside a sealed recording
# (new canvas and painter names, reorganised sections) without changing
# a single rendered pixel: the output hash is unchanged.
#
# Run it:  mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py

import binascii
import hashlib
import math
import os
import random
import struct
import sys
import zlib

SIZE = 1024
SEED = 20261116

# --- palette: dusk sky, hazy city, cream cup, cold spray, blue whale, gold
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


def mix(a, b, t):
    """Blend two RGB colours channel by channel."""
    return tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))


def quad(p0, c, p1, t):
    """A point on a quadratic Bezier curve at parameter t."""
    u = 1.0 - t
    x = u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0]
    y = u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]
    return x, y


class Canvas:
    """An RGB canvas stored as one bytearray per row.

    Horizontal fills are single slice assignments, which keeps a
    1024x1024 scene fast in pure Python.
    """

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.rows = [bytearray(3 * width) for _ in range(height)]

    def hline(self, y, x0, x1, rgb):
        """Fill pixels x0..x1-1 of row y with one colour, clipped."""
        if y < 0 or y >= self.h:
            return
        left = max(0, int(x0))
        right = min(self.w, int(x1))
        if right <= left:
            return
        row = self.rows[y]
        row[3 * left:3 * right] = bytes(rgb) * (right - left)

    def _row_colour(self, y, stops):
        """Colour of row y for a vertical gradient through `stops`."""
        for i in range(len(stops) - 1):
            y0, c0 = stops[i]
            y1, c1 = stops[i + 1]
            if y0 <= y <= y1:
                t = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
                return mix(c0, c1, t)
        if y > stops[-1][0]:
            return stops[-1][1]
        return stops[0][1]

    def vgrad(self, stops):
        """Fill the whole canvas with a vertical gradient.

        `stops` is a list of (y, (r, g, b)) sorted by y.
        """
        for y in range(self.h):
            self.rows[y] = bytearray(bytes(self._row_colour(y, stops)) * self.w)

    def ellipse(self, cx, cy, rx, ry, rgb):
        """Fill an axis-aligned ellipse."""
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
            self.hline(y, math.ceil(cx - dx), math.floor(cx + dx) + 1, rgb)

    def disc(self, cx, cy, r, rgb):
        self.ellipse(cx, cy, r, r, rgb)

    def poly(self, points, rgb):
        """Fill a polygon with the scanline even-odd rule."""
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
                self.hline(y, math.ceil(crossings[i]),
                           math.floor(crossings[i + 1]) + 1, rgb)

    def thick_path(self, points, radius, rgb):
        """Draw a thick polyline as a chain of overlapping discs."""
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dist = max(1.0, math.hypot(x2 - x1, y2 - y1))
            steps = int(dist / max(1.0, radius * 0.6)) + 1
            for s in range(steps + 1):
                t = s / steps
                self.disc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t,
                          radius, rgb)

    def starburst(self, cx, cy, r, rgb):
        """Draw a four-point star: a droplet that has become a star."""
        pts = []
        for i in range(8):
            ang = math.pi / 2 * i - math.pi / 2
            rr = r if i % 2 == 0 else r * 0.22
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        self.poly(pts, rgb)


# --- sky, stars, moon -------------------------------------------------------

def draw_sky(cv):
    cv.vgrad([
        (0, SKY_TOP),
        (260, SKY_MID),
        (480, SKY_LOW),
        (660, (214, 82, 92)),
        (730, SKY_HORIZON),
        (790, (48, 26, 72)),
        (SIZE - 1, (20, 14, 44)),
    ])


def _band_stars(cv, rng):
    # A denser diagonal band of faint stars behind the whale.
    for _ in range(170):
        t = rng.random()
        x = t * SIZE
        y = 60 + t * 330 + rng.gauss(0, 70)
        if 0 <= y < 660:
            b = rng.choice([150, 180, 210])
            cv.disc(x, y, rng.choice([1, 1, 1, 2]), (b, b, min(255, b + 25)))


def _field_stars(cv, rng):
    # Stars scattered over the upper two thirds of the sky.
    for _ in range(240):
        x = rng.random() * SIZE
        y = rng.random() * 660
        b = rng.choice([200, 220, 235, 255])
        r = rng.choice([1, 1, 1, 2, 2, 3])
        cv.disc(x, y, r, (b, b, min(255, b + 15)))


def _sparkle_stars(cv, rng):
    # A few bright four-point sparkles.
    for _ in range(12):
        x = rng.random() * SIZE
        y = rng.random() * 520
        cv.starburst(x, y, rng.choice([5, 6, 7, 9]), (255, 255, 255))


def draw_stars(cv, rng):
    _band_stars(cv, rng)
    _field_stars(cv, rng)
    _sparkle_stars(cv, rng)


def draw_moon(cv):
    cx, cy = 795, 175
    # Soft glow rings, then the disc itself.
    cv.ellipse(cx, cy, 235, 235, (30, 28, 80))
    cv.ellipse(cx, cy, 168, 168, (52, 46, 110))
    cv.ellipse(cx, cy, 126, 126, (110, 96, 160))
    cv.ellipse(cx, cy, 104, 104, (140, 125, 180))
    cv.disc(cx, cy, 92, MOON)
    for dx, dy, r in [(-30, -18, 14), (22, 12, 18), (-8, 34, 11),
                      (38, -32, 9), (-48, 28, 8)]:
        cv.disc(cx + dx, cy + dy, r, CRATER)


# --- city -------------------------------------------------------------------

def _distant_blocks(cv, rng):
    # Low, hazy silhouettes.
    x = -20
    while x < SIZE + 20:
        bw = rng.randint(50, 110)
        bh = rng.randint(40, 110)
        cv.poly([(x, SIZE), (x, 830 - bh), (x + bw, 830 - bh), (x + bw, SIZE)],
                CITY_FAR)
        x += bw + rng.randint(4, 18)


def _towers(cv, rng):
    # Tall dark towers with lit windows.
    x = -30
    while x < SIZE + 30:
        bw = rng.randint(45, 105)
        bh = rng.randint(70, 200)
        top = 1000 - bh
        cv.poly([(x, SIZE), (x, top), (x + bw, top), (x + bw, SIZE)], CITY_NEAR)
        if rng.random() < 0.3:
            cv.hline(top - 26, x + bw // 2 - 2, x + bw // 2 + 2, CITY_NEAR)
            cv.disc(x + bw // 2, top - 30, 3, (255, 80, 70))
        for wy in range(top + 16, 985, 22):
            for wx in range(x + 10, x + bw - 8, 16):
                if rng.random() < 0.5:
                    cv.hline(wy, wx, wx + 5, WINDOW)
                    cv.hline(wy + 1, wx, wx + 5, WINDOW)
                    cv.hline(wy + 2, wx, wx + 5, WINDOW)
        x += bw + rng.randint(6, 22)


def draw_city(cv, rng):
    _distant_blocks(cv, rng)
    _towers(cv, rng)


# --- teacup -----------------------------------------------------------------

def draw_cup(cv):
    # Saucer.
    cv.ellipse(400, 922, 235, 30, (208, 188, 156))
    cv.ellipse(400, 914, 235, 30, SAUCER)
    cv.ellipse(400, 912, 200, 22, (244, 228, 200))
    # Handle: thick cream arc on the right, dark hole showing the city.
    arc = [(578, 742), (622, 748), (656, 782), (662, 826),
           (640, 866), (596, 884), (566, 872)]
    cv.thick_path(arc, 17, CUP)
    cv.thick_path(arc, 8, CITY_NEAR)
    # Cup body.
    cv.poly([(222, 706), (578, 706), (532, 908), (268, 908)], CUP)
    # Left-side shading and right-edge highlight.
    cv.poly([(222, 706), (300, 706), (292, 908), (268, 908)], CUP_SHADE)
    cv.poly([(548, 706), (578, 706), (532, 908), (516, 908)], (255, 246, 226))
    # Bold teal band and coral stripe.
    cv.poly([(232, 762), (568, 762), (560, 800), (240, 800)], CUP_BAND)
    cv.poly([(238, 808), (562, 808), (559, 820), (241, 820)], CUP_STRIPE)
    # Rim and water.
    cv.ellipse(400, 706, 192, 44, (214, 196, 168))
    cv.ellipse(400, 704, 178, 36, WATER)
    cv.ellipse(360, 698, 90, 14, (210, 248, 255))
    # Splash crown where the whale bursts out of the cup.
    for dx, r in [(-150, 16), (-110, 22), (-66, 26), (-20, 20), (28, 26),
                  (74, 22), (118, 18), (152, 13)]:
        cv.disc(400 + dx, 692 - abs(dx) // 9, r, SPLASH)
    for dx, r in [(-130, 10), (-88, 13), (-44, 11), (4, 13), (52, 11),
                  (96, 10), (136, 8)]:
        cv.disc(400 + dx, 678 - abs(dx) // 10, r, SPRAY)


# --- whale ------------------------------------------------------------------

def _profile(t, half_width):
    """Half-width of the whale body at fraction t along its axis.

    Blunt at the head, fullest about a third of the way back, narrow at
    the tail stock.
    """
    base = math.sin(math.pi * (0.12 + 0.88 * t)) ** 0.65
    taper = 1.0 - 0.86 * max(0.0, (t - 0.5) / 0.5) ** 1.6
    return half_width * base * taper


def body_polygon(head, tail, half_width, perp_offset=0.0):
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
    segments = 40
    for i in range(segments + 1):
        t = i / segments
        ax = hx + dx * length * t + ox
        ay = hy + dy * length * t + oy
        w = _profile(t, half_width)
        top.append((ax + px * w, ay + py * w))
        bottom.append((ax - px * w, ay - py * w))
    # Rounded head cap: a half-arc from the bottom edge start (B) around
    # the snout tip (head minus the axis direction) to the top edge start.
    cap = []
    w0 = _profile(0.0, half_width)
    for i in range(1, 12):
        phi = math.pi * (1 - i / 12)
        cap.append((hx + ox + px * w0 * math.cos(phi)
                    - dx * w0 * 0.9 * math.sin(phi),
                    hy + oy + py * w0 * math.cos(phi)
                    - dy * w0 * 0.9 * math.sin(phi)))
    return top + list(reversed(bottom)) + cap


def draw_whale(cv):
    head = (762, 358)
    tail = (455, 600)
    # Tail flukes first (behind the body): two broad lobes fanning out
    # from the tail tip, clearly forked, clear of the cup rim. Each is a
    # wide triangle with its base across the tail tip, so it merges with
    # the body instead of floating beside it.
    cv.poly([(470, 579), (330, 505), (395, 560), (440, 621)], WHALE_DARK)
    cv.poly([(437, 581), (350, 700), (405, 645), (473, 619)], WHALE_DARK)
    # Top sheen, belly, then the body itself: each later layer leaves a
    # crescent of the one beneath it showing along one edge.
    cv.poly(body_polygon(head, tail, 80, perp_offset=-16), WHALE_LIGHT)
    cv.poly(body_polygon(head, tail, 82, perp_offset=15), BELLY)
    cv.poly(body_polygon(head, tail, 95), WHALE)
    # No pectoral fin: in this breach pose it read as a detached slab,
    # and the whale reads cleanly without it.
    # Eye and the long curved mouth of the head (upper-right end).
    cv.disc(738, 332, 7, SPLASH)
    cv.disc(740, 332, 3, (8, 20, 40))
    mouth = [(698, 438), (724, 422), (754, 402), (776, 376), (790, 352)]
    cv.thick_path(mouth, 2, (12, 48, 96))


# --- spray ------------------------------------------------------------------

def draw_spray(cv, rng):
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
            x, y = quad(p0, c, p1, t)
            x += rng.gauss(0, 12)
            y += rng.gauss(0, 10)
            r = rng.choice([2, 2, 3, 3, 4])
            if t > 0.7 and rng.random() < 0.6:
                cv.starburst(x, y, r + 4, GOLD)
            else:
                cv.disc(x, y, r, rng.choice([SPLASH, SPRAY, SPRAY]))
    # A rising trail of gold stars from the whale's head up past the moon.
    for i in range(6):
        t = i / 5
        x = 745 + (665 - 745) * t + rng.gauss(0, 8)
        y = 295 - (295 - 185) * t + rng.gauss(0, 7)
        cv.starburst(x, y, 12 - i, GOLD)


def build_image():
    rng = random.Random(SEED)
    cv = Canvas(SIZE, SIZE)
    draw_sky(cv)
    draw_stars(cv, rng)
    draw_moon(cv)
    draw_city(cv, rng)
    draw_cup(cv)
    draw_whale(cv)
    draw_spray(cv, rng)
    return cv


# --- PNG encoding -----------------------------------------------------------

def chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    return out


def to_png(cv):
    raw = bytearray()
    for row in cv.rows:
        raw.append(0)  # filter: None
        raw += row
    compressed = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed) + chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    data = to_png(build_image())
    with open(path, "wb") as f:
        f.write(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"Wrote {path}: {SIZE}x{SIZE}, {len(data)} bytes, sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
