#!/usr/bin/env python3
"""
compare.py - cut every riser SKU both ways, report which gets more
risers out of a sheet, and verify the band geometry actually closes.
"""

import itertools
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riser import (RiserSpec, riser_net, pack, part_area, inch, to_in)
from band import band_parts, band_geometry, choose_scheme, sq_in

SHEET = (inch(32), inch(40))          # standard matboard
FAILS = []


def check(c, m):
    if not c:
        FAILS.append(m)


def risers_per_sheet(make_parts, spec, sheet, cap=40):
    """Add one riser's worth of parts at a time until something won't nest."""
    best, parts = 0, []
    for _ in range(cap):
        parts = parts + make_parts(spec)
        _, left = pack(parts, sheet[0], sheet[1])
        if left:
            break
        best += 1
    return best


def cut_area(make_parts, spec):
    return sum(part_area(p) for p in make_parts(spec))


ONE = lambda sp: [riser_net(sp)]
BAND = lambda sp: band_parts(sp, SHEET)

SKUS = [
    # from the bento grid: 4-col cell 14.33 x 13.25, 3-col cell 19.25 x 13.25,
    # half-height rows ~6.5
    ("4col full",    14.33, 13.25),
    ("4col half",    14.33, 6.50),
    ("3col full",    19.25, 13.25),
    ("3col half",    19.25, 6.50),
    ("4col double",  29.41, 13.25),
    ("small square",  6.50, 6.50),
]
HEIGHTS = [1.5, 3.0, 4.5, 6.0]

print(f"sheet {to_in(SHEET[0]):.0f} x {to_in(SHEET[1]):.0f} in, 4-ply matboard (1.5mm)\n")
hdr = (f'{"SKU":<14}{"footprint":>14}{"H":>5}  '
       f'{"one-piece net":>14}{"/sh":>5}{"sq.in":>7}  '
       f'{"band":>5}{"/sh":>5}{"sq.in":>7}{"joints":>7}  {"best":>10}{"gain":>7}')
print(hdr)
print("-" * len(hdr))

rows = []
for name, w, d in SKUS:
    for h in HEIGHTS:
        s = RiserSpec(w_ext=inch(w), d_ext=inch(d), height=inch(h), t=1.5,
                      name=f"{name.replace(' ', '-')}-{h:g}")
        if s.validate():
            continue

        # --- the walls must close the outer perimeter exactly ------------
        g = band_geometry(s, SHEET)
        check(abs(g["closed_perimeter"] - g["target_perimeter"]) < 1e-9,
              f"{s.name}: wall perimeter {g['closed_perimeter']:.3f} != "
              f"needed {g['target_perimeter']:.3f}")
        # --- the finished height must be exact in both modes -------------
        check(abs((s.hf + s.t) - s.height) < 1e-9, f"{s.name}: band height off")
        # --- the chosen scheme's longest part must fit the sheet ---------
        longest = max(max(p["size"]) for p in band_parts(s, SHEET))
        check(longest <= max(SHEET) - 12 + 1e-6,
              f"{s.name}: scheme {g['scheme']} longest part {to_in(longest):.1f}in "
              f"exceeds the sheet")

        n1 = risers_per_sheet(ONE, s, SHEET)
        nb = risers_per_sheet(BAND, s, SHEET)
        a1, ab = cut_area(ONE, s), cut_area(BAND, s)
        nw, nh = riser_net(s)["size"]

        best = max(n1, nb)
        win = "band" if nb > n1 else ("one-piece" if n1 > nb else "tie")
        gain = f"{nb/n1:.2f}x" if n1 else ("--" if not nb else "1pc fails")
        flag = "" if best else "   NEITHER FITS"

        print(f'{name:<14}{w:>7.2f}x{d:<6.2f}{h:>5.1f}  '
              f'{to_in(nw):>6.1f}x{to_in(nh):<7.1f}{n1:>5}{sq_in(a1):>7.0f}  '
              f'{g["scheme"]:>5}{nb:>5}{sq_in(ab):>7.0f}{g["joints"]:>7}  '
              f'{win:>10}{gain:>7}{flag}')
        rows.append(dict(name=name, w=w, d=d, h=h, n1=n1, nb=nb, a1=a1, ab=ab,
                         scheme=g["scheme"], joints=g["joints"]))

# ---- invariants ----------------------------------------------------------
for r in rows:
    # every SKU must be buildable somehow
    check(max(r["n1"], r["nb"]) > 0,
          f'{r["name"]} {r["h"]}in: no scheme fits the sheet')
    r["best_mode"] = "band" if r["nb"] > r["n1"] else "one-piece"
    r["best_n"] = max(r["n1"], r["nb"])

# NOT asserted: that the band always wins. It does not. Below about 3in of
# height the one-piece cross wastes almost nothing in its corners, while the
# band pays for a full-size top panel plus glue tabs - so the cross is both
# leaner and (being one compact part) sometimes better-packing. The band wins
# as height grows, because the cross's corner waste scales with height^2.
tall = [r for r in rows if r["h"] >= 4.5]
check(sum(r["nb"] for r in tall) >= sum(r["n1"] for r in tall),
      "band should win in aggregate at 4.5in and above")
short = [r for r in rows if r["h"] <= 1.5]
check(sum(r["a1"] for r in short) <= sum(r["ab"] for r in short),
      "one-piece should use less material in aggregate at 1.5in")

# the band's material overhead over the one-piece cross is a full-size top
# panel plus glue tabs, minus the cross's corner voids. Corner voids grow
# as height^2, so the band should win on material above a crossover height
# and lose slightly below it. Check that story holds.
crossovers = []
for name, w, d in SKUS:
    prev = None
    for h in HEIGHTS:
        rs = [r for r in rows if r["name"] == name and r["h"] == h]
        if not rs:
            continue
        r = rs[0]
        band_leaner = r["ab"] <= r["a1"]
        if prev is not None:
            check(not (prev and not band_leaner),
                  f'{name}: band goes from leaner to heavier as height grows '
                  f'(at {h}in) - corner-void model is wrong')
        if band_leaner and prev is False:
            crossovers.append((name, h))
        prev = band_leaner

print()
print("material crossover (height at which the band starts using less board):")
for name, h in crossovers:
    print(f'  {name:<14} at {h}in')
if not crossovers:
    print("  none within the tested heights")

tot1 = sum(r["n1"] for r in rows)
totb = sum(r["nb"] for r in rows)
print()
print(f'across {len(rows)} SKUs: one-piece {tot1/len(rows):.1f} risers/sheet avg, '
      f'band {totb/len(rows):.1f} risers/sheet avg '
      f'({totb/tot1:.2f}x more risers per sheet)')

# ---- no overlaps in an actual winning layout ----------------------------
s = RiserSpec(w_ext=inch(14.33), d_ext=inch(13.25), height=inch(3.0), t=1.5,
              name="check")
parts = []
for _ in range(risers_per_sheet(BAND, s, SHEET)):
    parts += band_parts(s, SHEET)
placed, left = pack(parts, *SHEET)
check(not left, "winning layout failed to nest on recheck")
for a, b in itertools.combinations(placed, 2):
    ov = (a.x < b.x + b.w - 1e-6 and b.x < a.x + a.w - 1e-6 and
          a.y < b.y + b.h - 1e-6 and b.y < a.y + a.h - 1e-6)
    check(not ov, "overlap in the winning layout")

print()
if FAILS:
    print(f"FAILED ({len(FAILS)}):")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("wall perimeters close, every part fits, no overlaps")
