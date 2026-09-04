#!/usr/bin/env python3
"""
riser.py - parametric fold-up riser nets for laser cutting.

Generates a 5-sided open-bottom riser ("cap") that sits over a placemat:
top face + 4 walls, no floor. Cut from one piece of sheet material,
score-folded, glued with internal tabs.

Output: layered SVG (CUT / SCORE / LABEL) in true 1:1 millimetres, plus
an optional nesting layout that packs many nets onto one sheet and
reports material yield.

GEOMETRY MODEL
--------------
Score on the INSIDE (underside) of the sheet, fold walls down 90 deg.
The fold pivots about the inside surface, so:

    top panel  = exterior footprint - 2 * thickness
    wall flap  = target height      - 1 * thickness

The top panel drops between the walls; the walls are proud of it by one
material thickness on each side. Exterior footprint therefore matches the
placemat exactly, and the top surface sits at exactly the target height.

Corners are closed by extending the E/W walls by one thickness at each
end, so they wrap and cover the N/S wall end grain. Glue tabs hang off
the N/S walls and land on the INSIDE face of the E/W walls, hidden.

All internal maths in millimetres. Public API takes inches or mm.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field, asdict

MM_PER_IN = 25.4


def inch(x: float) -> float:
    return x * MM_PER_IN


def to_in(x: float) -> float:
    return x / MM_PER_IN


# --------------------------------------------------------------------------
# material presets (thickness in mm, nominal sheet in mm)
# --------------------------------------------------------------------------

MATERIALS = {
    "matboard-4ply": dict(t=1.5, sheet=(inch(32), inch(40)), score_note="score 40-50% power on the back face"),
    "matboard-2ply": dict(t=1.0, sheet=(inch(32), inch(40)), score_note="score lightly; 2-ply folds easily"),
    "museum-8ply":   dict(t=3.0, sheet=(inch(32), inch(40)), score_note="v-groove or double-score; 8-ply resists folding"),
    "chipboard-2mm": dict(t=2.0, sheet=(inch(30), inch(40)), score_note="score deep, ~60% of thickness"),
    "ply-3mm":       dict(t=3.0, sheet=(inch(24), inch(48)), score_note="does not fold - use flat-pack/CNC mode"),
}


@dataclass
class RiserSpec:
    """Everything needed to draw one riser net. Dimensions in mm."""
    w_ext: float                 # exterior footprint width  (matches placemat)
    d_ext: float                 # exterior footprint depth
    height: float                # top surface height above the table
    t: float = 1.5               # material thickness
    kerf: float = 0.15           # laser kerf
    tab_w: float = 22.0          # glue tab reach
    tab_taper: float = 2.0       # trapezoid taper on the tab's free edge
    slit: float = 0.4            # gap between a tab and the wall beside it
    bottom_relief: float = 1.5   # keep tabs off the table
    close_corners: bool = True   # wrap E/W walls over N/S wall ends
    name: str = ""

    # ---- derived ----------------------------------------------------------
    @property
    def wp(self) -> float:
        """Top panel width."""
        return self.w_ext - 2 * self.t

    @property
    def dp(self) -> float:
        """Top panel depth."""
        return self.d_ext - 2 * self.t

    @property
    def hf(self) -> float:
        """Wall flap height (flat length of a wall)."""
        return self.height - self.t

    @property
    def cc(self) -> float:
        """Corner wrap extension on the E/W walls."""
        return self.t if self.close_corners else 0.0

    @property
    def tab(self) -> float:
        """Tab reach, clamped so it stays inside the corner void."""
        return max(0.0, min(self.tab_w, self.hf - self.slit - 1.0))

    @property
    def net_size(self) -> tuple[float, float]:
        """Bounding box of the flat net."""
        return (self.wp + 2 * self.hf, self.dp + 2 * self.hf)

    def validate(self) -> list[str]:
        errs = []
        if self.wp <= 0 or self.dp <= 0:
            errs.append(f"{self.name}: footprint {to_in(self.w_ext):.2f}x{to_in(self.d_ext):.2f}in is too small for {self.t}mm material")
        if self.hf <= self.t + self.slit + self.bottom_relief:
            errs.append(f"{self.name}: height {to_in(self.height):.2f}in is too short to fold - min ~{to_in(self.t*2+self.slit+self.bottom_relief+3):.2f}in")
        if self.tab < 6:
            errs.append(f"{self.name}: no room for a usable glue tab at this height (tab would be {self.tab:.1f}mm)")
        return errs


# --------------------------------------------------------------------------
# net construction
# --------------------------------------------------------------------------

def riser_net(s: RiserSpec) -> dict:
    """
    Build one riser net.

    Local coordinates: top panel occupies (0,0)-(wp,dp). Walls hang off it
    into negative / beyond-panel space. Returned geometry is translated so
    the net's bounding box starts at (0,0).

    Returns dict with:
      cut   : list of closed polygons (list of (x,y))
      score : list of polylines (fold lines)
      label : list of (x, y, text, size)
      voids : list of (x, y, w, h) free rectangles in the corners
      size  : (w, h) bounding box
    """
    wp, dp, hf, t = s.wp, s.dp, s.hf, s.t
    cc, tab, g = s.cc, s.tab, s.slit
    br, tp = s.bottom_relief, s.tab_taper

    # ---- outer boundary, walked clockwise in screen coords (y down) -------
    # Start top-left of the N wall.
    P: list[tuple[float, float]] = []
    P.append((0.0, -hf))                      # N wall top-left
    P.append((wp, -hf))                       # N wall top-right

    # NE corner: down the N wall's right edge, out around the glue tab,
    # back in, then out along the E wall's wrapped top edge.
    P.append((wp, -hf + br))
    P.append((wp + tab, -hf + br + tp))       # tab, tapered
    P.append((wp + tab, -t - g - tp))
    P.append((wp, -t - g))                    # back to the fold line
    P.append((wp, -cc))                       # slit between tab and E wall
    P.append((wp + hf, -cc))                  # E wall top edge (wrapped)

    # E wall
    P.append((wp + hf, dp + cc))
    P.append((wp, dp + cc))

    # SE corner: tab
    P.append((wp, dp + t + g))
    P.append((wp + tab, dp + t + g + tp))
    P.append((wp + tab, dp + hf - br - tp))
    P.append((wp, dp + hf - br))
    P.append((wp, dp + hf))                   # S wall bottom-right

    # S wall
    P.append((0.0, dp + hf))

    # SW corner (mirror of SE)
    P.append((0.0, dp + hf - br))
    P.append((-tab, dp + hf - br - tp))
    P.append((-tab, dp + t + g + tp))
    P.append((0.0, dp + t + g))
    P.append((0.0, dp + cc))
    P.append((-hf, dp + cc))

    # W wall
    P.append((-hf, -cc))
    P.append((0.0, -cc))

    # NW corner (mirror of NE)
    P.append((0.0, -t - g))
    P.append((-tab, -t - g - tp))
    P.append((-tab, -hf + br + tp))
    P.append((0.0, -hf + br))
    # closes back to (0, -hf)

    # ---- fold lines -------------------------------------------------------
    score: list[list[tuple[float, float]]] = [
        [(-cc, 0.0), (wp + cc, 0.0)],          # N wall fold (spans the wrap)
        [(-cc, dp), (wp + cc, dp)],            # S wall fold
        [(0.0, -cc), (0.0, dp + cc)],          # W wall fold
        [(wp, -cc), (wp, dp + cc)],            # E wall fold
        # tab folds
        [(0.0, -hf + br), (0.0, -t - g)],      # NW tab
        [(wp, -hf + br), (wp, -t - g)],        # NE tab
        [(0.0, dp + t + g), (0.0, dp + hf - br)],   # SW tab
        [(wp, dp + t + g), (wp, dp + hf - br)],     # SE tab
    ]

    # ---- free corner rectangles (usable for gussets) ----------------------
    void_w = hf - tab - g
    void_h = hf - t - g - br
    voids = []
    if void_w > 8 and void_h > 8:
        voids = [
            (-hf,        -hf + br,      void_w, void_h),   # NW
            (wp + tab + g, -hf + br,    void_w, void_h),   # NE
            (-hf,        dp + t + g,    void_w, void_h),   # SW
            (wp + tab + g, dp + t + g,  void_w, void_h),   # SE
        ]

    # ---- label, engraved on the inside of the top panel -------------------
    txt = s.name or f'{to_in(s.w_ext):.2f}x{to_in(s.d_ext):.2f}x{to_in(s.height):.2f}'
    labels = [(wp / 2, dp / 2, txt, min(14.0, max(5.0, min(wp, dp) / 9)))]

    # ---- normalise to a (0,0) origin --------------------------------------
    ox, oy = hf, hf
    shift = lambda pts: [(x + ox, y + oy) for x, y in pts]

    return dict(
        cut=[shift(P)],
        score=[shift(l) for l in score],
        label=[(x + ox, y + oy, txt, sz) for x, y, txt, sz in labels],
        voids=[(x + ox, y + oy, w, h) for x, y, w, h in voids],
        size=s.net_size,
        spec=s,
    )


def gusset(leg: float) -> dict:
    """Right-triangle corner brace. Glues into an inside corner."""
    return dict(
        cut=[[(0.0, 0.0), (leg, 0.0), (0.0, leg)]],
        score=[], label=[], voids=[], size=(leg, leg), spec=None,
    )


def rib_pair(s: RiserSpec, clearance: float = 0.6) -> list[dict]:
    """
    Two half-lapped ribs that cross under the top panel and carry load
    down to the table. Slot width is undersized by the kerf so the cut
    lands at exactly one material thickness.
    """
    h = s.hf - clearance                 # table to panel underside
    slot_w = max(0.2, s.t - s.kerf)
    parts = []
    for length, tag, slot_from_top in ((s.wp - clearance, "ribA", True),
                                       (s.dp - clearance, "ribB", False)):
        cx = length / 2
        depth = h / 2
        if slot_from_top:
            poly = [(0, 0), (cx - slot_w / 2, 0), (cx - slot_w / 2, depth),
                    (cx + slot_w / 2, depth), (cx + slot_w / 2, 0),
                    (length, 0), (length, h), (0, h)]
        else:
            poly = [(0, 0), (length, 0), (length, h),
                    (cx + slot_w / 2, h), (cx + slot_w / 2, h - depth),
                    (cx - slot_w / 2, h - depth), (cx - slot_w / 2, h), (0, h)]
        parts.append(dict(cut=[poly], score=[], label=[(cx, h / 2, tag, 6)],
                          voids=[], size=(length, h), spec=None))
    return parts


# --------------------------------------------------------------------------
# nesting
# --------------------------------------------------------------------------

@dataclass
class Placement:
    part: dict
    x: float
    y: float
    rotated: bool
    w: float
    h: float


EPS = 1e-7


def _split_free(fr, used):
    """Guillotine-split a free rect around a used rect. MaxRects style."""
    fx, fy, fw, fh = fr
    ux, uy, uw, uh = used
    if ux >= fx + fw - EPS or ux + uw <= fx + EPS or \
       uy >= fy + fh - EPS or uy + uh <= fy + EPS:
        return [fr]                                  # no overlap
    out = []
    if uy > fy + EPS:                                # above
        out.append((fx, fy, fw, uy - fy))
    if uy + uh < fy + fh - EPS:                      # below
        out.append((fx, uy + uh, fw, fy + fh - (uy + uh)))
    if ux > fx + EPS:                                # left
        out.append((fx, fy, ux - fx, fh))
    if ux + uw < fx + fw - EPS:                      # right
        out.append((ux + uw, fy, fx + fw - (ux + uw), fh))
    return [r for r in out if r[2] > EPS and r[3] > EPS]


def _prune(rects):
    """Drop free rects fully contained in another."""
    keep = []
    for i, a in enumerate(rects):
        ax, ay, aw, ah = a
        if aw <= EPS or ah <= EPS:
            continue
        buried = False
        for j, b in enumerate(rects):
            if i == j:
                continue
            bx, by, bw, bh = b
            if (bx <= ax + EPS and by <= ay + EPS and
                    bx + bw >= ax + aw - EPS and by + bh >= ay + ah - EPS):
                if (bw > aw + EPS or bh > ah + EPS) or j < i:
                    buried = True
                    break
        if not buried:
            keep.append(a)
    return keep


def pack(parts: list[dict], sheet_w: float, sheet_h: float,
         margin: float = 6.0, gap: float = 3.0) -> tuple[list[Placement], list[dict]]:
    """
    MaxRects packer, best-short-side-fit, 90-degree rotation allowed.
    Handles mixed long strips and large panels far better than a shelf
    packer. Deterministic. Returns (placements, leftovers).
    """
    free = [(margin, margin, sheet_w - 2 * margin, sheet_h - 2 * margin)]
    placed: list[Placement] = []
    left: list[dict] = []

    # biggest first, by longest side then area
    order = sorted(range(len(parts)),
                   key=lambda i: (-max(parts[i]["size"]),
                                  -parts[i]["size"][0] * parts[i]["size"][1]))

    for i in order:
        p = parts[i]
        pw, ph = p["size"]
        options = [(pw, ph, False)]
        if abs(pw - ph) > EPS:
            options.append((ph, pw, True))

        best = None
        for fx, fy, fw, fh in free:
            for w, h, rot in options:
                aw, ah = w + gap, h + gap
                if aw <= fw + EPS and ah <= fh + EPS:
                    dw, dh = fw - aw, fh - ah
                    key = (min(dw, dh), max(dw, dh), fy, fx)
                    if best is None or key < best[0]:
                        best = (key, fx, fy, w, h, rot)
        if best is None:
            left.append(p)
            continue

        _, x, y, w, h, rot = best
        placed.append(Placement(p, x, y, rot, w, h))
        used = (x, y, w + gap, h + gap)
        nxt = []
        for fr in free:
            nxt.extend(_split_free(fr, used))
        free = _prune(nxt)

    return placed, left


def part_area(p: dict) -> float:
    """True cut area of a part (shoelace over its polygons)."""
    tot = 0.0
    for poly in p["cut"]:
        a = 0.0
        n = len(poly)
        for j in range(n):
            x1, y1 = poly[j]
            x2, y2 = poly[(j + 1) % n]
            a += x1 * y2 - x2 * y1
        tot += abs(a) / 2
    return tot


# --------------------------------------------------------------------------
# SVG output
# --------------------------------------------------------------------------

LAYERS = [
    ("CUT",   "#FF0000"),
    ("SCORE", "#0000FF"),
    ("LABEL", "#00A000"),
]


def _xf(pts, dx, dy, rot, w, h):
    """Translate, and rotate 90deg CW inside the placed w x h box."""
    out = []
    for x, y in pts:
        if rot:
            x, y = w - y, x
        out.append((x + dx, y + dy))
    return out


def svg(placements: list[Placement], sheet_w: float, sheet_h: float,
        title: str = "risers", show_sheet: bool = True) -> str:
    head = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'version="1.1" width="{sheet_w:.3f}mm" height="{sheet_h:.3f}mm" '
        f'viewBox="0 0 {sheet_w:.3f} {sheet_h:.3f}">',
        f'<title>{title}</title>',
        '<desc>1:1 millimetres. Layers: CUT (red), SCORE (blue, fold lines), LABEL (green, engrave). '
        'Score on the INSIDE face, then fold walls down.</desc>',
    ]
    body: dict[str, list[str]] = {n: [] for n, _ in LAYERS}

    if show_sheet:
        body["LABEL"].append(
            f'<rect x="0" y="0" width="{sheet_w:.3f}" height="{sheet_h:.3f}" '
            f'fill="none" stroke="#CCCCCC" stroke-width="0.2" stroke-dasharray="4 4"/>')

    for pl in placements:
        p = pl.part
        for poly in p["cut"]:
            pts = _xf(poly, pl.x, pl.y, pl.rotated, pl.w, pl.h)
            d = " ".join(f'{x:.3f},{y:.3f}' for x, y in pts)
            body["CUT"].append(f'<polygon points="{d}" fill="none" stroke="#FF0000" stroke-width="0.1"/>')
        for line in p["score"]:
            pts = _xf(line, pl.x, pl.y, pl.rotated, pl.w, pl.h)
            d = " ".join(f'{x:.3f},{y:.3f}' for x, y in pts)
            body["SCORE"].append(f'<polyline points="{d}" fill="none" stroke="#0000FF" stroke-width="0.1"/>')
        for x, y, txt, sz in p["label"]:
            (tx, ty), = _xf([(x, y)], pl.x, pl.y, pl.rotated, pl.w, pl.h)
            rot = ' transform="rotate(90 %.3f %.3f)"' % (tx, ty) if pl.rotated else ''
            body["LABEL"].append(
                f'<text x="{tx:.3f}" y="{ty:.3f}" font-family="Helvetica,Arial,sans-serif" '
                f'font-size="{sz:.2f}" fill="none" stroke="#00A000" stroke-width="0.1" '
                f'text-anchor="middle" dominant-baseline="middle"{rot}>{txt}</text>')

    out = head
    for name, _ in LAYERS:
        out.append(f'<g id="{name}" inkscape:groupmode="layer" inkscape:label="{name}">')
        out.extend(body[name])
        out.append('</g>')
    out.append('</svg>')
    return "\n".join(out)


# --------------------------------------------------------------------------
# high-level job
# --------------------------------------------------------------------------

def build_job(specs: list[RiserSpec], sheet: tuple[float, float],
              gussets_per_riser: int = 0, ribs: bool = False,
              margin: float = 6.0, gap: float = 3.0) -> dict:
    """Build nets for every spec, nest them, and report yield."""
    errs = []
    parts: list[dict] = []
    for s in specs:
        e = s.validate()
        if e:
            errs.extend(e)
            continue
        net = riser_net(s)
        parts.append(net)
        if ribs:
            parts.extend(rib_pair(s))
        if gussets_per_riser and net["voids"]:
            leg = min(net["voids"][0][2], net["voids"][0][3]) * 0.95
            for _ in range(gussets_per_riser):
                parts.append(gusset(leg))

    placed, left = pack(parts, sheet[0], sheet[1], margin, gap)
    used = sum(part_area(pl.part) for pl in placed)
    sheet_area = sheet[0] * sheet[1]
    bbox_used = sum(pl.w * pl.h for pl in placed)

    return dict(
        placements=placed,
        leftovers=left,
        errors=errs,
        sheet=sheet,
        yield_true=used / sheet_area,
        yield_bbox=bbox_used / sheet_area,
        n_placed=len(placed),
        n_left=len(left),
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Parametric fold-up riser nets for laser cutting.")
    ap.add_argument("--size", action="append", default=[], metavar="WxDxH",
                    help="riser exterior size in inches, repeatable, e.g. 14.33x13.25x3")
    ap.add_argument("--qty", action="append", type=int, default=[],
                    help="quantity for the matching --size (default 1)")
    ap.add_argument("--material", default="matboard-4ply", choices=list(MATERIALS))
    ap.add_argument("--thickness", type=float, default=None, help="override thickness, mm")
    ap.add_argument("--kerf", type=float, default=0.15, help="laser kerf, mm")
    ap.add_argument("--sheet", default=None, metavar="WxH", help="sheet size in inches, e.g. 32x40")
    ap.add_argument("--bed", default=None, metavar="WxH", help="clamp sheet to laser bed, inches")
    ap.add_argument("--tab", type=float, default=22.0, help="glue tab reach, mm")
    ap.add_argument("--gussets", type=int, default=0, help="corner gussets per riser")
    ap.add_argument("--ribs", action="store_true", help="add crossed load ribs per riser")
    ap.add_argument("--out", default="risers.svg")
    ap.add_argument("--json", default=None, help="also write a machine-readable report")
    args = ap.parse_args()

    mat = MATERIALS[args.material]
    t = args.thickness if args.thickness else mat["t"]

    sheet = mat["sheet"]
    if args.sheet:
        w, h = (float(v) for v in args.sheet.lower().split("x"))
        sheet = (inch(w), inch(h))
    if args.bed:
        bw, bh = (float(v) for v in args.bed.lower().split("x"))
        sheet = (min(sheet[0], inch(bw)), min(sheet[1], inch(bh)))

    if not args.size:
        args.size = ["14.33x13.25x3"]

    specs: list[RiserSpec] = []
    for i, sz in enumerate(args.size):
        w, d, h = (float(v) for v in sz.lower().split("x"))
        n = args.qty[i] if i < len(args.qty) else 1
        for k in range(n):
            specs.append(RiserSpec(
                w_ext=inch(w), d_ext=inch(d), height=inch(h),
                t=t, kerf=args.kerf, tab_w=args.tab,
                name=f'{w:g}x{d:g}x{h:g}'))

    job = build_job(specs, sheet, args.gussets, args.ribs)

    for e in job["errors"]:
        print("!!", e)

    with open(args.out, "w") as f:
        f.write(svg(job["placements"], sheet[0], sheet[1], title=args.out))

    print(f'sheet          {to_in(sheet[0]):.2f} x {to_in(sheet[1]):.2f} in')
    print(f'material       {args.material}  t={t}mm  kerf={args.kerf}mm')
    print(f'parts nested   {job["n_placed"]}   not fitted: {job["n_left"]}')
    print(f'yield (cut)    {job["yield_true"]*100:.1f}%   (bounding boxes {job["yield_bbox"]*100:.1f}%)')
    print(f'wrote          {args.out}')
    print(f'note           {mat["score_note"]}')

    if args.json:
        rep = dict(sheet_in=[to_in(sheet[0]), to_in(sheet[1])], material=args.material,
                   thickness_mm=t, n_placed=job["n_placed"], n_left=job["n_left"],
                   yield_true=job["yield_true"], errors=job["errors"])
        with open(args.json, "w") as f:
            json.dump(rep, f, indent=2)


if __name__ == "__main__":
    main()
