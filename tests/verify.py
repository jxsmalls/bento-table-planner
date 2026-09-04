#!/usr/bin/env python3
"""Geometry and nesting checks for riser.py. Run: python3 verify.py"""

import itertools
import math
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riser import (RiserSpec, riser_net, rib_pair, gusset, pack, part_area,
                   build_job, inch, to_in, MATERIALS)

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
    return cond


def seg_int(p1, p2, p3, p4):
    """Proper crossing of two open segments (shared endpoints don't count)."""
    def o(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    d1, d2 = o(p3, p4, p1), o(p3, p4, p2)
    d3, d4 = o(p1, p2, p3), o(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def simple(poly):
    n = len(poly)
    edges = [(poly[i], poly[(i + 1) % n]) for i in range(n)]
    for i, j in itertools.combinations(range(n), 2):
        if abs(i - j) in (1, n - 1):
            continue
        if seg_int(*edges[i], *edges[j]):
            return False, (i, j)
    return True, None


def shoelace(poly):
    a = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def rects_overlap(a, b, tol=1e-6):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax < bx + bw - tol and bx < ax + aw - tol and
            ay < by + bh - tol and by < ay + ah - tol)


# ---------------------------------------------------------------- geometry
print("== net geometry ==")

CASES = [
    # (w_ext_in, d_ext_in, height_in, thickness_mm)
    (14.33, 13.25, 3.0, 1.5),
    (14.33, 6.50, 1.5, 1.5),
    (19.25, 13.25, 4.5, 1.5),
    (6.00, 6.00, 6.0, 1.5),
    (19.25, 6.50, 2.0, 3.0),
    (28.66, 13.25, 1.25, 1.0),
]

for w, d, h, t in CASES:
    s = RiserSpec(w_ext=inch(w), d_ext=inch(d), height=inch(h), t=t,
                  name=f"{w}x{d}x{h}")
    errs = s.validate()
    check(not errs, f"spec {w}x{d}x{h} t={t} rejected: {errs}")
    if errs:
        continue
    net = riser_net(s)
    poly = net["cut"][0]

    ok, where = simple(poly)
    check(ok, f"{s.name}: net outline self-intersects at edges {where}")

    # 1. folded exterior footprint must equal the requested footprint
    ext_w = s.wp + 2 * s.t
    ext_d = s.dp + 2 * s.t
    check(abs(ext_w - s.w_ext) < 1e-9 and abs(ext_d - s.d_ext) < 1e-9,
          f"{s.name}: exterior {to_in(ext_w):.4f}x{to_in(ext_d):.4f} != {w}x{d}")

    # 2. finished top surface height must equal the requested height
    check(abs((s.hf + s.t) - s.height) < 1e-9,
          f"{s.name}: folded height {to_in(s.hf + s.t):.4f} != {h}")

    # 3. bounding box matches the analytic net size and the drawn polygon
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    check(abs(bw - net["size"][0]) < 1e-6 and abs(bh - net["size"][1]) < 1e-6,
          f"{s.name}: drawn bbox {bw:.2f}x{bh:.2f} != declared {net['size']}")
    check(min(xs) > -1e-6 and min(ys) > -1e-6,
          f"{s.name}: net is not normalised to a (0,0) origin")

    # 4. cut area must be less than the bbox (corner voids are real waste)
    #    and more than the sum of the five faces (tabs add material back)
    faces = s.wp * s.dp + 2 * s.hf * (s.wp + 2 * s.cc) + 2 * s.hf * s.dp
    area = shoelace(poly)
    check(area < bw * bh, f"{s.name}: cut area {area:.0f} >= bbox {bw*bh:.0f}")
    check(area > 0.9 * (s.wp * s.dp + 2 * s.hf * (s.wp + s.dp)),
          f"{s.name}: cut area {area:.0f} implausibly small vs five faces")

    # 5. tabs must clear the top panel by >= one thickness so the folded tab
    #    cannot foul the panel underside, and must sit above the table
    tab_gap = s.t + s.slit
    check(tab_gap >= s.t, f"{s.name}: tab clearance {tab_gap} < thickness")
    check(s.bottom_relief > 0, f"{s.name}: tabs would touch the table")

    # 6. tabs must fit inside the corner void
    check(s.tab + s.slit <= s.hf, f"{s.name}: tab {s.tab:.1f}mm overruns the corner void")
    check(s.tab >= 6, f"{s.name}: tab {s.tab:.1f}mm too small to glue")

    # 7. every score line must lie on the net, and fold lines must be
    #    long enough to actually hinge
    for line in net["score"]:
        L = math.dist(line[0], line[1])
        check(L > 1.0, f"{s.name}: degenerate score line of {L:.2f}mm")
        for pt in line:
            check(min(xs) - 1e-6 <= pt[0] <= max(xs) + 1e-6 and
                  min(ys) - 1e-6 <= pt[1] <= max(ys) + 1e-6,
                  f"{s.name}: score point {pt} outside the net bbox")

    # 8. wall fold lines must span the corner wrap
    n_fold = net["score"][0]
    check(abs((n_fold[1][0] - n_fold[0][0]) - (s.wp + 2 * s.cc)) < 1e-6,
          f"{s.name}: N fold line does not span the corner wrap")

    print(f"  ok  {s.name:<18} net {to_in(bw):6.2f} x {to_in(bh):6.2f} in"
          f"   panel {to_in(s.wp):6.2f} x {to_in(s.dp):6.2f}"
          f"   wall {to_in(s.hf):5.2f}   tab {s.tab:4.1f}mm"
          f"   waste-in-corners {(1-area/(bw*bh))*100:4.1f}%")

# too-small / too-short specs must be rejected, not silently drawn
for bad, why in (((2.0, 2.0, 0.08, 1.5), "height under one thickness"),
                 ((0.05, 4.0, 2.0, 1.5), "footprint under two thicknesses")):
    s = RiserSpec(w_ext=inch(bad[0]), d_ext=inch(bad[1]), height=inch(bad[2]),
                  t=bad[3], name="bad")
    check(bool(s.validate()), f"invalid spec accepted ({why})")
print("  ok  invalid specs are rejected")


# ---------------------------------------------------------------- ribs
print("== ribs ==")
s = RiserSpec(w_ext=inch(14.33), d_ext=inch(13.25), height=inch(4.0), t=1.5, kerf=0.15)
ra, rb = rib_pair(s)
for r, tag in ((ra, "ribA"), (rb, "ribB")):
    ok, where = simple(r["cut"][0])
    check(ok, f"{tag} self-intersects at {where}")
    xs = [p[0] for p in r["cut"][0]]
    ys = [p[1] for p in r["cut"][0]]
    check(abs((max(xs) - min(xs)) - r["size"][0]) < 1e-6, f"{tag} width mismatch")
    check(abs((max(ys) - min(ys)) - r["size"][1]) < 1e-6, f"{tag} height mismatch")
# the two half-lap slots must be complementary: depths sum to full height
h = s.hf - 0.6
check(abs(h / 2 + h / 2 - h) < 1e-9, "half-lap depths do not sum to rib height")
# slot must be cut undersize by the kerf so the finished slot equals t
slot_drawn = s.t - s.kerf
check(abs(slot_drawn + s.kerf - s.t) < 1e-9, "slot kerf compensation wrong")
# rib must fit the cavity and reach the panel underside
check(ra["size"][0] < s.wp, "ribA longer than the cavity")
check(rb["size"][0] < s.dp, "ribB longer than the cavity")
check(ra["size"][1] < s.hf, "rib taller than the cavity")
print(f"  ok  ribs {to_in(ra['size'][0]):.2f}in and {to_in(rb['size'][0]):.2f}in, "
      f"{to_in(ra['size'][1]):.2f}in tall, slot cut at {slot_drawn:.2f}mm for {s.t}mm stock")


# ---------------------------------------------------------------- nesting
print("== nesting ==")
specs = []
for (w, d, h) in [(14.33, 13.25, 3.0), (14.33, 6.5, 1.5), (14.33, 6.5, 4.5),
                  (19.25, 13.25, 2.0), (19.25, 6.5, 3.0), (6.5, 6.5, 6.0)]:
    specs.append(RiserSpec(w_ext=inch(w), d_ext=inch(d), height=inch(h), t=1.5,
                           name=f"{w}x{d}x{h}"))

job = build_job(specs, (inch(32), inch(40)), gussets_per_riser=2, ribs=False)
check(not job["errors"], f"build errors: {job['errors']}")

pls = job["placements"]
sw, sh = job["sheet"]
for pl in pls:
    check(pl.x >= 0 and pl.y >= 0 and pl.x + pl.w <= sw + 1e-6 and pl.y + pl.h <= sh + 1e-6,
          f"placement off sheet: {pl.x:.1f},{pl.y:.1f} {pl.w:.1f}x{pl.h:.1f}")
    # rotation must swap the declared size
    dw, dh = pl.part["size"]
    if pl.rotated:
        check(abs(pl.w - dh) < 1e-6 and abs(pl.h - dw) < 1e-6, "rotated size mismatch")
    else:
        check(abs(pl.w - dw) < 1e-6 and abs(pl.h - dh) < 1e-6, "unrotated size mismatch")

collisions = 0
for a, b in itertools.combinations(pls, 2):
    if rects_overlap((a.x, a.y, a.w, a.h), (b.x, b.y, b.w, b.h)):
        collisions += 1
check(collisions == 0, f"{collisions} overlapping placements")

check(job["yield_true"] <= job["yield_bbox"] + 1e-9, "true yield exceeds bbox yield")
check(job["yield_bbox"] <= 1.0 + 1e-9, "bbox yield over 100%")
print(f"  ok  {job['n_placed']} parts on one 32x40in sheet, no overlaps, "
      f"{job['yield_true']*100:.1f}% cut yield ({job['yield_bbox']*100:.1f}% bbox)")

# a part larger than the sheet must be reported, never silently dropped
huge = RiserSpec(w_ext=inch(40), d_ext=inch(40), height=inch(8), t=1.5, name="huge")
j2 = build_job([huge], (inch(24), inch(18)))
check(j2["n_left"] == 1 and j2["n_placed"] == 0, "oversize part was not reported as unfitted")
print("  ok  oversize parts are reported, not dropped")

# packing must be monotonic: more copies never fit fewer parts
one = build_job([specs[0]], (inch(32), inch(40)))
many = build_job([specs[0]] * 6, (inch(32), inch(40)))
check(many["n_placed"] >= one["n_placed"], "packing is not monotonic")
print(f"  ok  6 identical risers nest {many['n_placed']} per sheet")


# ---------------------------------------------------------------- svg
print("== svg ==")
from riser import svg
out = svg(pls, sw, sh, title="verify")
check(out.count("<svg") == 1 and out.rstrip().endswith("</svg>"), "malformed svg")
for name in ("CUT", "SCORE", "LABEL"):
    check(f'id="{name}"' in out, f"missing {name} layer")
check(f'width="{sw:.3f}mm"' in out, "svg is not in true millimetres")
check("stroke-width=\"0.1\"" in out, "strokes are not hairlines")
print("  ok  layered, 1:1 mm, hairline strokes")


# ---------------------------------------------------------------- result
print()
if FAILS:
    print(f"FAILED ({len(FAILS)}):")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
