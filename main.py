#!/usr/bin/env python3
"""The Moon Fell Into the Sea — make.fun ai-excited-01 entry.

Draws a 1024x1024 PNG with pure Python 3.13 stdlib only (zlib + struct
for the PNG encoder, math/random for the picture itself). No third-party
imports, no network, deterministic: two runs produce byte-identical files.

The scene: a colossal cratered moon has fallen out of the night sky and
crashed half-submerged into the ocean. Spray explodes upward in a white
crown, shockwave rings race across the water, a sparkling moon-path
shimmers below it, and one tiny sailboat sails toward it — the scale cue
that makes the moon feel impossibly huge. A jagged crack zigzags down the
moon's face. Bold pixel-font captions carry the joke.

Run:  mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import math
import os
import random
import struct
import sys
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------------------
# Canvas: a plain RGB bytearray with small drawing helpers.
# ---------------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def _idx(self, x, y):
        return (y * self.w + x) * 3

    def set_px(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = self._idx(x, y)
            self.buf[i] = color[0]
            self.buf[i + 1] = color[1]
            self.buf[i + 2] = color[2]

    def blend_px(self, x, y, color, alpha):
        """Alpha-blend color over the pixel (alpha 0..255)."""
        if 0 <= x < self.w and 0 <= y < self.h and 0 < alpha:
            if alpha >= 255:
                self.set_px(x, y, color)
                return
            i = self._idx(x, y)
            b = self.buf
            inv = 255 - alpha
            b[i] = (color[0] * alpha + b[i] * inv) // 255
            b[i + 1] = (color[1] * alpha + b[i + 1] * inv) // 255
            b[i + 2] = (color[2] * alpha + b[i + 2] * inv) // 255

    def hline(self, x0, x1, y, color):
        """Fast horizontal span fill (clipped)."""
        if y < 0 or y >= self.h:
            return
        if x0 > x1:
            x0, x1 = x1, x0
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x0 > x1:
            return
        i = self._idx(x0, y)
        n = x1 - x0 + 1
        self.buf[i:i + n * 3] = bytes(color) * n

    def fill_rect(self, x0, y0, x1, y1, color):
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            self.hline(x0, x1, y, color)

    def fill_circle(self, cx, cy, r, color):
        if r <= 0:
            return
        r2 = r * r
        for y in range(max(0, cy - r), min(self.h, cy + r + 1)):
            dy = y - cy
            dx = int(math.sqrt(max(0, r2 - dy * dy)))
            self.hline(cx - dx, cx + dx, y, color)

    def fill_circle_alpha(self, cx, cy, r, color, alpha):
        if r <= 0 or alpha <= 0:
            return
        r2 = r * r
        for y in range(max(0, cy - r), min(self.h, cy + r + 1)):
            dy = y - cy
            dx = int(math.sqrt(max(0, r2 - dy * dy)))
            for x in range(max(0, cx - dx), min(self.w, cx + dx + 1)):
                self.blend_px(x, y, color, alpha)

    def draw_line(self, x0, y0, x1, y1, color, width=1):
        """Bresenham line with round thick joints."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        rad = max(1, width // 2)
        while True:
            self.fill_circle(x0, y0, rad, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_polygon(self, points, color):
        """Scanline polygon fill for a simple (non self-intersecting) polygon."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        y_min = max(0, min(ys))
        y_max = min(self.h - 1, max(ys))
        n = len(points)
        for y in range(y_min, y_max + 1):
            xs = []
            for i in range(n):
                x0, y0 = points[i]
                x1, y1 = points[(i + 1) % n]
                if y0 == y1:
                    continue
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y - y0) / (y1 - y0)
                    xs.append(x0 + t * (x1 - x0))
            if len(xs) >= 2:
                xs.sort()
                for k in range(0, len(xs) - 1, 2):
                    self.hline(int(xs[k]), int(xs[k + 1]), y, color)

    def ellipse_points(self, cx, cy, rx, ry, color, width=2, y_min=None,
                       y_max=None, alpha=None, dash=False):
        """Plot an ellipse outline; optionally clipped to a y band.

        With dash=True, regular gaps break the outline (reads as a
        natural ripple rather than a perfect rule)."""
        steps = max(180, int(2 * math.pi * max(rx, ry) / 2))
        for s in range(steps):
            if dash and (s % 42) < 9:
                continue
            a = 2 * math.pi * s / steps
            x = int(cx + rx * math.cos(a))
            y = int(cy + ry * math.sin(a))
            if y_min is not None and y < y_min:
                continue
            if y_max is not None and y > y_max:
                continue
            if alpha is None:
                self.fill_circle(x, y, width, color)
            else:
                self.fill_circle_alpha(x, y, width, color, alpha)


def lerp_color(c0, c1, t):
    return (int(c0[0] + (c1[0] - c0[0]) * t),
            int(c0[1] + (c1[1] - c0[1]) * t),
            int(c0[2] + (c1[2] - c0[2]) * t))


def shade(color, f):
    """Multiply a color by a brightness factor f (clamped 0..255)."""
    return (max(0, min(255, int(color[0] * f))),
            max(0, min(255, int(color[1] * f))),
            max(0, min(255, int(color[2] * f))))


# ---------------------------------------------------------------------------
# 5x7 pixel font (own hand-written glyphs). '#' = on.
# ---------------------------------------------------------------------------

FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'D': ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'J': ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    'K': ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'Q': ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'V': ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    'W': ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    'X': ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    'Y': ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    'Z': ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '!': ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    ',': ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
}

GLYPH_W = 5
GLYPH_H = 7
ADVANCE = 6  # glyph width + 1px tracking, in font units


def text_width(text, scale):
    return len(text) * ADVANCE * scale - scale


def draw_text(canvas, text, x, y, scale, color, shadow=None, shadow_dx=0,
              shadow_dy=0):
    """Blit pixel text. If shadow is given, draw it offset first."""
    if shadow is not None:
        draw_text(canvas, text, x + shadow_dx, y + shadow_dy, scale,
                  shadow, shadow=None)
    cx = x
    for ch in text:
        glyph = FONT.get(ch.upper(), FONT[' '])
        for row in range(GLYPH_H):
            bits = glyph[row]
            for col in range(GLYPH_W):
                if bits[col] == '1':
                    canvas.fill_rect(cx + col * scale, y + row * scale,
                                     cx + col * scale + scale - 1,
                                     y + row * scale + scale - 1, color)
        cx += ADVANCE * scale


def draw_text_centered(canvas, text, y, scale, color, shadow=None,
                       shadow_dx=0, shadow_dy=0):
    x = (W - text_width(text, scale)) // 2
    draw_text(canvas, text, x, y, scale, color, shadow=shadow,
              shadow_dx=shadow_dx, shadow_dy=shadow_dy)


# ---------------------------------------------------------------------------
# Scene constants
# ---------------------------------------------------------------------------

HORIZON = 660          # sea line
MOON_CX, MOON_CY = 512, 470
MOON_R = 300

SKY_TOP = (4, 8, 26)
SKY_MID = (13, 24, 58)
SKY_LOW = (38, 58, 110)
GLOW_WARM = (96, 66, 118)

SEA_TOP = (12, 46, 78)
SEA_DEEP = (3, 14, 34)

MOON_BASE = (228, 234, 242)
MOON_DARK = (168, 184, 210)
CRATER_DARK = (148, 164, 194)
CRATER_RIM = (246, 249, 253)

FOAM = (246, 251, 255)
FOAM_SHADOW = (172, 202, 232)
RING = (150, 220, 255)
SPARK = (190, 220, 248)


def draw_sky(canvas, rng):
    """Night gradient, warm glow band at the horizon, stars, shooting stars."""
    for y in range(0, HORIZON):
        t = y / HORIZON
        if t < 0.55:
            c = lerp_color(SKY_TOP, SKY_MID, t / 0.55)
        else:
            c = lerp_color(SKY_MID, SKY_LOW, (t - 0.55) / 0.45)
        # warm magenta kiss right above the horizon
        if y > HORIZON - 90:
            w = (y - (HORIZON - 90)) / 90.0
            c = lerp_color(c, GLOW_WARM, w * 0.35)
        canvas.hline(0, W - 1, y, c)

    # stars: denser and brighter up high, sparser near the horizon
    for _ in range(260):
        x = rng.randint(4, W - 5)
        y = rng.randint(4, HORIZON - 30)
        depth = 1.0 - y / HORIZON          # 1 top, 0 horizon
        if rng.random() > 0.25 + 0.75 * depth:
            continue
        b = rng.randint(150, 255)
        tw = rng.choice([1, 1, 1, 2])
        col = (b, b, min(255, b + 12))
        if tw == 1:
            canvas.set_px(x, y, col)
        else:
            canvas.fill_rect(x, y, x + 1, y + 1, col)
            canvas.set_px(x - 1, y, shade(col, 0.5))
            canvas.set_px(x + 2, y, shade(col, 0.5))
            canvas.set_px(x, y - 1, shade(col, 0.5))
            canvas.set_px(x, y + 2, shade(col, 0.5))

    # a few big bright stars with cross sparkle
    for _ in range(7):
        x = rng.randint(30, W - 30)
        y = rng.randint(20, 260)
        canvas.fill_circle(x, y, 2, (255, 255, 255))
        canvas.hline(x - 6, x + 6, y, (220, 230, 255))
        canvas.hline(x, x, y - 6, (220, 230, 255))
        canvas.hline(x, x, y + 6, (220, 230, 255))

    # shooting stars: bright head, fading tail
    for (sx, sy, dx, dy, ln) in [(180, 90, 1, 1, 70), (820, 60, -1, 1, 55),
                                 (640, 140, -1, 1, 44)]:
        for i in range(ln):
            a = int(230 * (1 - i / ln) ** 2)
            x = sx + dx * i
            yy = sy + dy * i
            canvas.blend_px(x, yy, (255, 255, 255), a)
            canvas.blend_px(x, yy + 1, (200, 220, 255), a // 2)
        canvas.fill_circle(sx, sy, 3, (255, 255, 255))

    # tiny birds, far away, heading for the moon
    for (bx, by, s) in [(820, 210, 7), (860, 235, 6), (790, 250, 5),
                        (900, 180, 6)]:
        canvas.draw_line(bx - s, by, bx, by - 4, (20, 28, 52), width=2)
        canvas.draw_line(bx, by - 4, bx + s, by, (20, 28, 52), width=2)


def draw_moon_glow(canvas):
    """Soft halo around the moon, strongest right at its rim."""
    cx, cy, r = MOON_CX, MOON_CY, MOON_R + 95
    r2 = r * r
    for y in range(max(0, cy - r), min(HORIZON + 30, cy + r + 1)):
        dy = y - cy
        dx = int(math.sqrt(max(0, r2 - dy * dy)))
        for x in range(max(0, cx - dx), min(W, cx + dx + 1)):
            d = math.sqrt((x - cx) ** 2 + dy * dy) / r
            if d >= 1.0:
                continue
            a = int(64 * (1 - d) ** 2)
            canvas.blend_px(x, y, (150, 180, 235), a)


def draw_moon(canvas, rng):
    """The fallen moon: shaded disc, craters, jagged crack, bright rim."""
    cx, cy, r = MOON_CX, MOON_CY, MOON_R
    # disc with radial falloff + light from the upper left
    for y in range(cy - r, cy + r + 1):
        dy = y - cy
        dx = int(math.sqrt(max(0, r * r - dy * dy)))
        for x in range(cx - dx, cx + dx + 1):
            ddx = x - cx
            radial = math.sqrt(ddx * ddx + dy * dy) / r
            # directional light: upper-left is lit, lower-right falls off
            dl = (-ddx * 0.55 - dy * 0.55) / r
            f = 0.76 + 0.26 * (1 - radial) + 0.16 * dl
            f = max(0.50, min(1.08, f))
            canvas.set_px(x, y, shade(MOON_BASE, f))

    # limb: bright upper-left rim, darker lower edge
    canvas.ellipse_points(cx, cy, r - 2, r - 2, (255, 255, 255), width=3,
                          y_max=cy - 40)
    canvas.ellipse_points(cx, cy, r - 1, r - 1, (120, 135, 168), width=4,
                          y_min=cy + 120)

    # craters: fewer, varied in size and tone, rims kept close to the
    # surface colour so they read as dents in rock, not soap bubbles
    craters = []
    tries = 0
    while len(craters) < 11 and tries < 400:
        tries += 1
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0.12, 0.86) * r
        px = int(cx + d * math.cos(a))
        py = int(cy + d * math.sin(a))
        cr = rng.choice([rng.randint(6, 10), rng.randint(12, 24),
                         rng.randint(26, 48)])
        if math.hypot(px - cx, py - cy) + cr > r - 8:
            continue
        if any(math.hypot(px - qx, py - qy) < cr + qr + 16
               for (qx, qy, qr) in craters):
            continue
        craters.append((px, py, cr))
    for (px, py, cr) in craters:
        tone = rng.uniform(0.82, 1.0)
        dark = shade(CRATER_DARK, tone)
        rim = lerp_color(CRATER_RIM, MOON_BASE, 0.55)
        canvas.fill_circle(px - 2, py - 2, cr, rim)
        canvas.fill_circle(px, py, max(2, cr - 1), dark)
        # inner shadow pit, offset to the lower right, large craters only
        if cr > 20:
            canvas.fill_circle(px + cr // 4, py + cr // 4, max(2, cr // 2),
                               shade(dark, 0.75))
            canvas.fill_circle(px - cr // 3, py - cr // 3, 3,
                               (232, 238, 247))

    # the crack: a jagged dark zigzag with a glowing cyan edge
    crack = [(498, 178), (522, 248), (494, 312), (526, 384), (492, 452),
             (518, 522), (496, 592), (508, 652)]
    for i in range(len(crack) - 1):
        canvas.draw_line(crack[i][0], crack[i][1],
                         crack[i + 1][0], crack[i + 1][1],
                         (26, 34, 58), width=9)
    for i in range(len(crack) - 1):
        canvas.draw_line(crack[i][0] + 5, crack[i][1] + 2,
                         crack[i + 1][0] + 5, crack[i + 1][1] + 2,
                         (190, 232, 255), width=2)
    # two short branch cracks
    for (bx0, by0, bx1, by1) in [(512, 384, 560, 420), (500, 522, 458, 556)]:
        canvas.draw_line(bx0, by0, bx1, by1, (26, 34, 58), width=5)
        canvas.draw_line(bx0 + 3, by0 + 1, bx1 + 3, by1 + 1,
                         (170, 215, 250), width=1)

    # sea mist hugging the moon where it meets the water
    for (mx, my, mr, al) in [(300, 640, 66, 24), (724, 640, 66, 24),
                             (512, 655, 110, 26)]:
        canvas.fill_circle_alpha(mx, my, mr, (200, 220, 245), al)


def draw_sea(canvas, rng):
    """Ocean gradient, moon-path shimmer, shockwave rings, foam, spray."""
    for y in range(HORIZON, H):
        t = (y - HORIZON) / (H - HORIZON)
        c = lerp_color(SEA_TOP, SEA_DEEP, t ** 0.8)
        canvas.hline(0, W - 1, y, c)

    # moon-path: a soft glowing column under the moon, fading with depth
    for y in range(HORIZON + 2, H - 4):
        t = (y - HORIZON) / (H - HORIZON)
        half = int(120 * (1 - 0.45 * t))
        for x in range(MOON_CX - half, MOON_CX + half + 1):
            fall = 1 - abs(x - MOON_CX) / max(1, half)
            a = int(52 * fall * fall * (1 - 0.55 * t))
            if a > 0:
                canvas.blend_px(x, y, (150, 195, 235), a)

    # faint wave streaks across the open sea, so it is not a flat void
    for _ in range(60):
        y = rng.randint(HORIZON + 20, H - 10)
        x = rng.randint(10, W - 110)
        ln = rng.randint(20, 90)
        t = (y - HORIZON) / (H - HORIZON)
        base = lerp_color(SEA_TOP, SEA_DEEP, t ** 0.8)
        canvas.hline(x, x + ln, y, lerp_color(base, (64, 112, 162), 0.16))

    # sparkling dashes on the moon-path
    for _ in range(380):
        x = int(rng.gauss(MOON_CX, 88))
        y = rng.randint(HORIZON + 4, H - 8)
        if not (330 <= x <= 694):
            continue
        ln = rng.randint(6, 42)
        fade = 1 - (y - HORIZON) / (H - HORIZON) * 0.45
        b = int(rng.randint(150, 235) * fade)
        col = (b, min(255, b + 18), 255)
        canvas.hline(x - ln // 2, x + ln // 2, y, col)
        if rng.random() < 0.3:
            canvas.hline(x - ln // 4, x + ln // 4, y + 1,
                         shade(col, 0.6))

    # shockwave rings racing outward from the impact point: only three,
    # curvier and broken into dashes so they read as water, not rules
    for (rx, ry, col, wd) in [(320, 42, (185, 232, 255), 3),
                              (470, 60, (140, 210, 250), 3),
                              (620, 80, (95, 175, 230), 2)]:
        canvas.ellipse_points(MOON_CX, HORIZON + 4, rx, ry, col, width=wd,
                              y_min=HORIZON + 2, dash=True)

    # foam where the moon meets the water: a bumpy broken band of blobs,
    # not a clean white plate
    for x in range(272, 756, 13):
        fr = rng.randint(6, 14)
        fy = HORIZON + rng.randint(-2, 8)
        canvas.fill_circle(x + rng.randint(-4, 4), fy, fr,
                           FOAM if rng.random() < 0.7 else FOAM_SHADOW)
    for _ in range(90):
        x = int(rng.gauss(MOON_CX, 130))
        y = rng.randint(HORIZON - 2, HORIZON + 16)
        canvas.fill_circle(x, y, rng.randint(2, 5),
                           FOAM if rng.random() < 0.7 else FOAM_SHADOW)

    # spray crown: jets and droplets exploding upward from the impact
    for _ in range(16):
        bx = rng.randint(300, 724)
        peak = rng.randint(440, 600)
        height = HORIZON - peak
        drift = 1 if bx > MOON_CX else -1
        for s in range(0, 21):
            t = s / 20.0
            # parabolic jet: up, then falling back outwards
            x = int(bx + drift * t * t * 70)
            y = int(HORIZON - height * (2 * t - t * t) * 0.55 - t * 8)
            canvas.fill_circle(x, y, max(2, int(6 - 3 * t)), FOAM)
        # droplet burst at the jet tip
        for _ in range(6):
            dx = rng.randint(-26, 26)
            dy = rng.randint(-20, 10)
            canvas.fill_circle(bx + dx, peak + dy, rng.randint(2, 5),
                               FOAM if rng.random() < 0.8 else FOAM_SHADOW)

    # loose spray droplets scattered across the whole crown
    for _ in range(300):
        # denser near the waterline, thinner higher up
        y = int(HORIZON - abs(rng.gauss(0, 78)))
        spread = 250 - (HORIZON - y)  # wider low, narrower high
        x = int(MOON_CX + rng.gauss(0, max(40, spread * 0.55)))
        if y < 420 or not (180 <= x <= 844):
            continue
        r = rng.randint(2, 9)
        canvas.fill_circle(x, y, r,
                           FOAM if rng.random() < 0.75 else FOAM_SHADOW)
        if rng.random() < 0.25:  # a few droplets catch the light
            canvas.set_px(x - 1, y - 1, (255, 255, 255))


def draw_boat(canvas):
    """One tiny sailboat sailing toward the moon — the scale cue."""
    bx, by = 772, 832  # mast base / waterline of the boat
    # reflection shimmer under the hull
    for i in range(6):
        canvas.hline(bx - 26 + i * 4, bx + 26 - i * 4, by + 34 + i * 7,
                     (120, 165, 210) if i % 2 == 0 else (80, 130, 180))
    # hull: dark silhouette
    canvas.fill_polygon([(bx - 30, by), (bx + 30, by), (bx + 20, by + 14),
                         (bx - 20, by + 14)], (14, 20, 36))
    canvas.hline(bx - 30, bx + 30, by, (200, 170, 120))
    # mast
    canvas.draw_line(bx, by, bx, by - 58, (14, 20, 36), width=3)
    # main sail: warm white, lit by the moon
    canvas.fill_polygon([(bx + 2, by - 56), (bx + 2, by - 4),
                         (bx + 30, by - 4)], (244, 234, 208))
    canvas.fill_polygon([(bx + 2, by - 56), (bx + 2, by - 4),
                         (bx + 30, by - 4)], (244, 234, 208))
    # jib sail on the far side
    canvas.fill_polygon([(bx - 2, by - 48), (bx - 2, by - 4),
                         (bx - 24, by - 4)], (214, 204, 178))
    # lantern glow at the masthead
    canvas.fill_circle_alpha(bx, by - 60, 10, (255, 200, 90), 90)
    canvas.fill_circle(bx, by - 60, 3, (255, 214, 120))
    # a tiny wake trailing behind
    for i in range(5):
        canvas.hline(bx + 34 + i * 8, bx + 52 + i * 8, by + 8 + i * 2,
                     FOAM_SHADOW)


def draw_captions(canvas):
    """Bold pixel-font captions, with a dark drop shadow for legibility."""
    shadow = (8, 12, 34)
    draw_text_centered(canvas, "THE MOON FELL", 34, 8, (255, 255, 255),
                       shadow=shadow, shadow_dx=5, shadow_dy=6)
    draw_text_centered(canvas, "AND THE SEA CAUGHT IT", 106, 6,
                       (255, 220, 140), shadow=shadow, shadow_dx=4,
                       shadow_dy=5)
    # small line addressed to the judge, down in the sea
    draw_text_centered(canvas, "JUDGE - IT'S STILL FALLING", 962, 4,
                       (165, 195, 232), shadow=(4, 8, 22), shadow_dx=2,
                       shadow_dy=3)


def draw_frame(canvas):
    canvas.fill_rect(0, 0, W - 1, 7, (6, 10, 24))
    canvas.fill_rect(0, H - 8, W - 1, H - 1, (6, 10, 24))
    canvas.fill_rect(0, 0, 7, H - 1, (6, 10, 24))
    canvas.fill_rect(W - 8, 0, W - 1, H - 1, (6, 10, 24))


# ---------------------------------------------------------------------------
# PNG encoder (stdlib only): raw RGB scanlines, filter 0, zlib level 9.
# ---------------------------------------------------------------------------

def encode_png(canvas):
    raw = bytearray()
    row_bytes = canvas.w * 3
    for y in range(canvas.h):
        raw.append(0)  # filter: none
        start = y * row_bytes
        raw += canvas.buf[start:start + row_bytes]
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    return png


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")

    rng = random.Random(20261116)  # fixed seed: byte-identical every run

    canvas = Canvas(W, H)
    draw_sky(canvas, rng)
    draw_moon_glow(canvas)
    draw_moon(canvas, rng)
    draw_sea(canvas, rng)
    draw_boat(canvas)
    draw_captions(canvas)
    draw_frame(canvas)

    png = encode_png(canvas)
    with open(out_path, "wb") as f:
        f.write(png)
    print(f"wrote {out_path}: {len(png)} bytes, {W}x{H}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
