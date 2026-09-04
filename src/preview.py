#!/usr/bin/env python3
"""
preview.py - dependency-free raster preview of a nested sheet, so the
geometry can actually be looked at rather than trusted.

Writes a PPM (converted to PNG by the caller). Cut lines black, score
lines dashed red, part fills light grey, sheet edge grey.
"""
from __future__ import annotations
import sys

from riser import Placement, _xf


class Canvas:
    def __init__(self, w: int, h: int, bg=(255, 255, 255)):
        self.w, self.h = w, h
        self.px = bytearray(bg * (w * h))

    def set(self, x: int, y: int, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def line(self, x0, y0, x1, y1, c, dash=0):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        n = 0
        while True:
            if not dash or (n // dash) % 2 == 0:
                self.set(x0, y0, c)
            n += 1
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def fill_poly(self, pts, c):
        ys = [p[1] for p in pts]
        for y in range(int(min(ys)), int(max(ys)) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for a, b in zip(xs[0::2], xs[1::2]):
                for x in range(int(a), int(b) + 1):
                    self.set(x, y, c)

    def write_ppm(self, path):
        with open(path, "wb") as f:
            f.write(f"P6\n{self.w} {self.h}\n255\n".encode())
            f.write(self.px)


def render(placements, sheet_w, sheet_h, path, px_per_mm=1.4):
    W = int(sheet_w * px_per_mm) + 20
    H = int(sheet_h * px_per_mm) + 20
    cv = Canvas(W, H)
    s = lambda p: (p[0] * px_per_mm + 10, p[1] * px_per_mm + 10)

    # sheet edge
    for a, b in (((0, 0), (sheet_w, 0)), ((sheet_w, 0), (sheet_w, sheet_h)),
                 ((sheet_w, sheet_h), (0, sheet_h)), ((0, sheet_h), (0, 0))):
        cv.line(*s(a), *s(b), (170, 170, 170))

    for pl in placements:
        for poly in pl.part["cut"]:
            pts = [s(p) for p in _xf(poly, pl.x, pl.y, pl.rotated, pl.w, pl.h)]
            cv.fill_poly(pts, (232, 236, 232))
        for poly in pl.part["cut"]:
            pts = [s(p) for p in _xf(poly, pl.x, pl.y, pl.rotated, pl.w, pl.h)]
            for i in range(len(pts)):
                cv.line(*pts[i], *pts[(i + 1) % len(pts)], (20, 20, 20))
        for line in pl.part["score"]:
            pts = [s(p) for p in _xf(line, pl.x, pl.y, pl.rotated, pl.w, pl.h)]
            for i in range(len(pts) - 1):
                cv.line(*pts[i], *pts[i + 1], (215, 40, 40), dash=3)
    cv.write_ppm(path)
    return W, H
