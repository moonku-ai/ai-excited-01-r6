#!/usr/bin/env python3
"""THE MOON FELL INTO THE SEA -- make.fun ai-excited-01 (r6).

A pure-stdlib Python program that procedurally draws one 1024x1024 PNG:
a colossal glowing moon has fallen out of the sky and crashed into the
ocean. It sits half-submerged on the horizon, spray exploding outward in
a crown, shockwave rings racing across the water, and a tiny sailboat
sailing toward it -- the scale twist that makes the moon feel enormous.
A bold headline crowns the scene. No image files, no network, no
third-party code: every pixel is computed here, deterministically, with
a hand-rolled PNG encoder (zlib + struct only).

Run:  mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import os
import struct
import zlib
from math import sqrt, sin, pi

W = 1024
H = 1024

# ---------------------------------------------------------------- PNG ----

def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def write_png(path, buf):
    """buf is a bytearray of W*H*3 RGB bytes, top row first."""
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)  # filter: none
        raw += buf[y * stride:(y + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


# ------------------------------------------------------- deterministic RNG ----

class Rng:
    """Tiny LCG with a fixed seed: same picture on every run."""

    def __init__(self, seed=987654321):
        self.s = seed

    def next(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s

    def frac(self):
        return self.next() / 0x7FFFFFFF

    def irange(self, a, b):
        return a + self.next() % (b - a + 1)

    def pick(self, items):
        return items[self.next() % len(items)]


# -------------------------------------------------------------- canvas ----

def _lerp(a, b, t):
    return int(a + (b - a) * t + 0.5)


def lerp_rgb(c0, c1, t):
    return (_lerp(c0[0], c1[0], t), _lerp(c0[1], c1[1], t), _lerp(c0[2], c1[2], t))


class Canvas:
    def __init__(self):
        self.buf = bytearray(W * H * 3)

    # -- low level spans ------------------------------------------------
    def span(self, y, x0, x1, r, g, b):
        if y < 0 or y >= H:
            return
        if x0 < 0:
            x0 = 0
        if x1 > W - 1:
            x1 = W - 1
        if x1 < x0:
            return
        n = x1 - x0 + 1
        px = bytes((r, g, b)) * n
        i = (y * W + x0) * 3
        self.buf[i:i + len(px)] = px

    def span_alpha(self, y, x0, x1, r, g, b, a):
        if a <= 0:
            return
        if a >= 255:
            self.span(y, x0, x1, r, g, b)
            return
        if y < 0 or y >= H:
            return
        if x0 < 0:
            x0 = 0
        if x1 > W - 1:
            x1 = W - 1
        if x1 < x0:
            return
        inv = 255 - a
        buf = self.buf
        for x in range(x0, x1 + 1):
            i = (y * W + x) * 3
            buf[i] = (r * a + buf[i] * inv) // 255
            buf[i + 1] = (g * a + buf[i + 1] * inv) // 255
            buf[i + 2] = (b * a + buf[i + 2] * inv) // 255

    def rect(self, x, y, w, h, r, g, b):
        for yy in range(y, y + h):
            self.span(yy, x, x + w - 1, r, g, b)

    # -- gradients ------------------------------------------------------
    def vgrad(self, y0, y1, top, bottom):
        span = max(1, y1 - y0)
        for y in range(y0, y1 + 1):
            c = lerp_rgb(top, bottom, (y - y0) / span)
            self.span(y, 0, W - 1, *c)

    # -- discs / ellipses / rings ---------------------------------------
    def disc(self, cx, cy, rad, rgb, alpha=255):
        r, g, b = rgb
        for y in range(cy - rad, cy + rad + 1):
            dy = y - cy
            d2 = rad * rad - dy * dy
            if d2 < 0:
                continue
            dx = int(sqrt(d2))
            if alpha >= 255:
                self.span(y, cx - dx, cx + dx, r, g, b)
            else:
                self.span_alpha(y, cx - dx, cx + dx, r, g, b, alpha)

    def ellipse(self, cx, cy, rx, ry, rgb, alpha=255):
        r, g, b = rgb
        for y in range(cy - ry, cy + ry + 1):
            dy = y - cy
            t = 1.0 - (dy * dy) / float(ry * ry)
            if t < 0:
                continue
            dx = int(rx * sqrt(t))
            if alpha >= 255:
                self.span(y, cx - dx, cx + dx, r, g, b)
            else:
                self.span_alpha(y, cx - dx, cx + dx, r, g, b, alpha)

    def ring(self, cx, cy, rad, thick, rgb, alpha=255):
        """Circular outline of the given thickness."""
        r, g, b = rgb
        for y in range(cy - rad, cy + rad + 1):
            dy = y - cy
            d2 = rad * rad - dy * dy
            if d2 < 0:
                continue
            dx = int(sqrt(d2))
            inner = rad - thick
            d2i = inner * inner - dy * dy
            if d2i > 0:
                dxi = int(sqrt(d2i))
                if alpha >= 255:
                    self.span(y, cx - dx, cx - dxi - 1, r, g, b)
                    self.span(y, cx + dxi + 1, cx + dx, r, g, b)
                else:
                    self.span_alpha(y, cx - dx, cx - dxi - 1, r, g, b, alpha)
                    self.span_alpha(y, cx + dxi + 1, cx + dx, r, g, b, alpha)
            else:
                if alpha >= 255:
                    self.span(y, cx - dx, cx + dx, r, g, b)
                else:
                    self.span_alpha(y, cx - dx, cx + dx, r, g, b, alpha)

    def ellipse_ring(self, cx, cy, rx, ry, thick, rgb, alpha=255):
        r, g, b = rgb
        for y in range(cy - ry, cy + ry + 1):
            dy = y - cy
            t = 1.0 - (dy * dy) / float(ry * ry)
            if t < 0:
                continue
            dx = int(rx * sqrt(t))
            ti = 1.0 - (dy * dy) / float((ry - thick) * (ry - thick)) \
                if ry > thick else -1.0
            if ti > 0:
                dxi = int((rx - thick) * sqrt(ti))
                if alpha >= 255:
                    self.span(y, cx - dx, cx - dxi - 1, r, g, b)
                    self.span(y, cx + dxi + 1, cx + dx, r, g, b)
                else:
                    self.span_alpha(y, cx - dx, cx - dxi - 1, r, g, b, alpha)
                    self.span_alpha(y, cx + dxi + 1, cx + dx, r, g, b, alpha)
            else:
                if alpha >= 255:
                    self.span(y, cx - dx, cx + dx, r, g, b)
                else:
                    self.span_alpha(y, cx - dx, cx + dx, r, g, b, alpha)

    # -- polygons and lines ---------------------------------------------
    def poly(self, pts, rgb):
        r, g, b = rgb
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(H - 1, int(max(ys)))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, yy0 = pts[i]
                x1, yy1 = pts[(i + 1) % n]
                if (yy0 <= y < yy1) or (yy1 <= y < yy0):
                    t = (y - yy0) / float(yy1 - yy0)
                    xs.append(x0 + t * (x1 - x0))
            if len(xs) >= 2:
                xs.sort()
                self.span(y, int(xs[0]), int(xs[-1]), r, g, b)

    def thick_line(self, x0, y0, x1, y1, w, rgb):
        dx, dy = x1 - x0, y1 - y0
        leng = sqrt(dx * dx + dy * dy) or 1.0
        nx, ny = -dy / leng * w / 2.0, dx / leng * w / 2.0
        self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                   (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], rgb)


# ------------------------------------------------------------ bitmap font ----
# 5x7 glyphs, '#' = ink. Only the letters the two captions need, plus
# space, period and exclamation mark.

FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".....", "..#.."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
}


def text_width(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(cv, s, cx, y, scale, rgb, shadow=None):
    """Draw s centred on cx, top edge at y. Optional shadow offset colour."""
    w = text_width(s, scale)
    x = cx - w // 2
    if shadow is not None:
        _draw_text_at(cv, s, x + scale // 2, y + scale // 2, scale, shadow)
    _draw_text_at(cv, s, x, y, scale, rgb)


def _draw_text_at(cv, s, x0, y0, scale, rgb):
    r, g, b = rgb
    x = x0
    for ch in s:
        glyph = FONT.get(ch, FONT[" "])
        for row in range(7):
            line = glyph[row]
            for col in range(5):
                if line[col] == "#":
                    cv.rect(x + col * scale, y0 + row * scale,
                            scale, scale, r, g, b)
        x += 6 * scale

# ---------------------------------------------------------------- scene ----

MOON_CX, MOON_CY, MOON_R = 512, 640, 300
HORIZON = 660

SKY_TOP = (4, 7, 34)
SKY_MID = (14, 30, 82)
SKY_LOW = (36, 72, 140)
SEA_TOP = (7, 48, 66)
SEA_BOT = (2, 13, 25)
SPRAY = (236, 246, 255)
SPRAY_BLUE = (198, 224, 246)
GOLD = (255, 214, 120)
CREAM = (255, 247, 214)


def draw_sky(cv, rng):
    # Three-stop vertical gradient: deep indigo up top, brighter near sea.
    for y in range(0, HORIZON + 1):
        if y < 380:
            c = lerp_rgb(SKY_TOP, SKY_MID, y / 380.0)
        else:
            c = lerp_rgb(SKY_MID, SKY_LOW, (y - 380) / 280.0)
        cv.span(y, 0, W - 1, *c)
    # Stars: fixed-seed scatter, brightest ones get a tiny cross flare.
    for _ in range(210):
        x = rng.irange(4, W - 5)
        y = rng.irange(4, HORIZON - 40)
        roll = rng.frac()
        if roll < 0.55:
            cv.span(y, x, x, 200, 210, 240)
        elif roll < 0.85:
            cv.span(y, x - 1, x + 1, 225, 232, 250)
            cv.span(y - 1, x, x, 225, 232, 250)
            cv.span(y + 1, x, x, 225, 232, 250)
        else:
            cv.span(y, x - 2, x + 2, 255, 244, 200)
            cv.span(y - 2, x, x, 255, 244, 200)
            cv.span(y + 2, x, x, 255, 244, 200)
            cv.span(y - 1, x, x, 255, 244, 200)
            cv.span(y + 1, x, x, 255, 244, 200)
    # Three shooting stars streaking down toward the fallen moon.
    for (x0, y0, x1, y1) in ((120, 96, 268, 168), (760, 60, 884, 128),
                             (880, 210, 978, 262)):
        cv.thick_line(x0, y0, x1, y1, 3, (207, 228, 255))
        cv.thick_line(x0, y0, (x0 + x1) // 2, (y0 + y1) // 2, 5,
                      (160, 190, 240))
        cv.disc(x1, y1, 4, (255, 255, 255))


def draw_moon(cv):
    # Warm halo in five faint layers, so the glow fades out gradually
    # instead of leaving a hard grey ring against the night sky.
    for rad, alpha in ((430, 10), (400, 12), (370, 14), (340, 18),
                       (315, 22)):
        cv.disc(MOON_CX, MOON_CY, rad, (255, 206, 110), alpha=alpha)
    # Body: pale-gold disc with a darker limb band for roundness.
    cv.disc(MOON_CX, MOON_CY, MOON_R, (255, 238, 196))
    cv.ring(MOON_CX, MOON_CY, MOON_R, 30, (240, 200, 110))
    cv.ring(MOON_CX, MOON_CY, MOON_R - 30, 14, (250, 222, 150))
    # Soft highlight high on the disc, like light catching its curve.
    cv.ellipse(MOON_CX - 30, MOON_CY - 165, 190, 78, (255, 246, 210),
               alpha=70)
    # Craters: darker gold discs, a few with a bright lower rim.
    craters = [
        (-120, -80, 22), (60, -140, 16), (140, -40, 26), (-40, 40, 18),
        (90, 90, 12), (-170, 30, 14), (180, 60, 10), (0, -180, 20),
        (-90, -160, 12), (200, -110, 14), (-200, -90, 9), (40, -60, 8),
        (-150, -130, 11), (120, 130, 15), (-60, 150, 10), (230, 10, 8),
    ]
    for dx, dy, rad in craters:
        cv.disc(MOON_CX + dx, MOON_CY + dy, rad, (214, 162, 82))
        cv.disc(MOON_CX + dx + 2, MOON_CY + dy + 3, max(2, rad - 5),
                (196, 140, 66))
    # The fall cracked it: a thin jagged fissure zigzagging down the upper
    # face. Kept thin and dark-gold so it reads as a crack, not a branch.
    crack = [(470, 375), (452, 410), (478, 445), (458, 480), (486, 515),
             (462, 550), (490, 585), (470, 612)]
    for (x0, y0), (x1, y1) in zip(crack, crack[1:]):
        cv.thick_line(x0, y0, x1, y1, 3, (146, 104, 58))
    # One thin night cloud drifting across the moon's upper face.
    cv.ellipse(330, 470, 250, 13, (26, 38, 88), alpha=42)


def draw_sea(cv, rng):
    # Sea gradient, darker with depth.
    for y in range(HORIZON, H):
        c = lerp_rgb(SEA_TOP, SEA_BOT, (y - HORIZON) / float(H - HORIZON))
        cv.span(y, 0, W - 1, *c)
    # A bright gold band where moonlight hits the horizon line.
    for k in range(7):
        cv.span_alpha(HORIZON - 4 + k, 0, W - 1, 255, 210, 120, 96 - k * 12)
    # Small wave bumps along the horizon, in front of the moon base.
    x = 0
    while x < W:
        r = rng.irange(4, 8)
        cv.disc(x, HORIZON - 1, r, SEA_TOP)
        x += rng.irange(38, 64)
    # Moonlight reflection: a narrow column of short bright dashes --
    # the classic sparkling moon-path -- instead of a solid smear.
    for y in range(HORIZON + 8, H - 12, 6):
        depth = (y - HORIZON) / float(H - HORIZON)
        half = int(95 * (1.0 - depth * 0.45))
        for _ in range(2):
            cx = MOON_CX + rng.irange(-half, half)
            w = rng.irange(12, 52)
            alpha = rng.irange(70, 150)
            cv.span_alpha(y, cx - w // 2, cx + w // 2, 255, 214, 130,
                          alpha)


def draw_spray(cv, rng):
    """The explosion of water where the moon hit: a crown of spikes,
    flying droplets and foam, plus shockwave rings racing outward."""
    cx, cy = MOON_CX, HORIZON + 6
    # Shockwave rings on the water, widest first so near rings overlap.
    for rx, ry, thick, alpha in ((470, 78, 7, 46), (392, 62, 6, 62),
                                 (316, 48, 6, 84), (244, 36, 5, 110)):
        cv.ellipse_ring(cx, cy + 18, rx, ry, thick, SPRAY, alpha=alpha)
    # Foam collar hugging the moon where it meets the sea.
    cv.ellipse_ring(cx, cy, 292, 44, 16, SPRAY, alpha=150)
    cv.ellipse_ring(cx, cy, 292, 44, 8, (255, 255, 255), alpha=200)
    # Radial spikes: tall in the middle, shorter toward the edges, and
    # leaning outward at the flanks so the crown fans instead of standing
    # in parallel ranks.
    for k in range(22):
        frac = k / 21.0
        lean = (frac - 0.5) * 2.0  # -1 left .. +1 right
        base_r = rng.irange(215, 265)
        tip_r = base_r + rng.irange(40, 150) * (1.0 - abs(lean) * 0.55)
        bx = cx + int(base_r * lean * 0.92)
        by = cy - int(30 * (1.0 - abs(lean)))
        tx = cx + int(tip_r * lean * 1.18)
        ty = cy - int(tip_r * 0.5) - rng.irange(0, 30)
        half = rng.irange(5, 13)
        perp_x, perp_y = -(ty - by), (tx - bx)
        pl = sqrt(perp_x * perp_x + perp_y * perp_y) or 1.0
        px, py = perp_x / pl * half, perp_y / pl * half
        col = SPRAY if rng.frac() < 0.6 else SPRAY_BLUE
        cv.poly([(bx + px, by + py), (tx, ty), (bx - px, by - py)], col)
    # Droplets flung just above the spray crown, kept close to it so the
    # open sea stays clean instead of looking snowed on.
    for _ in range(58):
        x = cx + int(rng.irange(-330, 330))
        y = cy - int(rng.irange(40, 230) * (1.0 - abs(x - cx) / 800.0))
        r = rng.irange(2, 7)
        col = SPRAY if rng.frac() < 0.7 else SPRAY_BLUE
        cv.disc(x, y, r, col)
    # Low foam flecks scattered across the near water.
    for _ in range(34):
        x = rng.irange(60, W - 60)
        y = rng.irange(HORIZON + 30, HORIZON + 170)
        r = rng.irange(2, 5)
        cv.disc(x, y, r, SPRAY_BLUE)


def draw_boat(cv):
    """One tiny sailboat sailing toward the fallen moon -- the scale cue
    that makes the moon feel impossibly huge."""
    hx, hy = 168, 838
    # Hull and mast, near-black silhouette.
    cv.poly([(hx - 52, hy), (hx + 58, hy), (hx + 40, hy + 24),
             (hx - 34, hy + 24)], (7, 14, 28))
    cv.thick_line(hx + 4, hy, hx + 4, hy - 78, 4, (7, 14, 28))
    # Sail lit gold by the moon, plus a small jib.
    cv.poly([(hx + 8, hy - 74), (hx + 8, hy - 4), (hx + 52, hy - 4)],
            (255, 228, 164))
    cv.poly([(hx, hy - 66), (hx, hy - 4), (hx - 38, hy - 4)],
            (240, 205, 140))
    # Warm lantern at the stern and a faint reflection below.
    cv.disc(hx - 44, hy - 6, 4, (255, 190, 80))
    cv.disc(hx - 44, hy - 6, 2, (255, 240, 180))
    cv.ellipse(hx + 3, hy + 34, 52, 5, (255, 200, 100), alpha=48)


def draw_birds(cv):
    """Small gull chevrons fleeing the impact, high in the sky."""
    for (x, y, s) in ((210, 250, 14), (262, 226, 10), (790, 300, 12),
                      (838, 268, 9), (150, 330, 9), (905, 380, 11)):
        col = (18, 28, 58)
        cv.thick_line(x - s, y, x, y - s // 2, 3, col)
        cv.thick_line(x, y - s // 2, x + s, y, 3, col)


def draw_captions(cv):
    # Headline across the top, gold on deep night with a dark shadow.
    draw_text(cv, "THE MOON FELL", 512, 46, 10, CREAM,
              shadow=(8, 14, 54))
    # Gold rule under the headline.
    cv.rect(512 - 150, 46 + 72 + 12, 300, 6, *GOLD)
    cv.disc(512 - 168, 46 + 72 + 15, 5, GOLD)
    cv.disc(512 + 168, 46 + 72 + 15, 5, GOLD)
    # Subline low over the sea.
    draw_text(cv, "AND THE SEA CAUGHT IT", 512, 946, 4, (255, 220, 140),
              shadow=(4, 10, 30))


def draw():
    rng = Rng()
    cv = Canvas()
    draw_sky(cv, rng)
    draw_moon(cv)
    draw_sea(cv, rng)
    draw_spray(cv, rng)
    draw_boat(cv)
    draw_birds(cv)
    draw_captions(cv)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    cv = draw()
    size = write_png(path, cv.buf)
    print("wrote %s (%d bytes)" % (path, size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
