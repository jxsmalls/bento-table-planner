#!/usr/bin/env python3
"""Write tests/ref.json: reference geometry from the Python, which the
browser tool's JavaScript is then checked against."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from riser import RiserSpec, riser_net, rib_pair, pack, part_area, inch
from band import band_parts, choose_scheme

SHEET = (inch(32), inch(40))

def per_sheet(mk, s, cap=24):
    n, parts = 0, []
    for _ in range(cap):
        parts = parts + mk(s)
        if pack(parts, SHEET[0], SHEET[1], 6, 3)[1]:
            break
        n += 1
    return n

CASES = [(14.33, 13.25, 3.0, 1.5, 22), (14.33, 6.5, 1.5, 1.5, 22),
         (19.25, 13.25, 4.5, 1.5, 22), (6.5, 6.5, 6.0, 1.5, 22),
         (29.41, 13.25, 2.0, 2.0, 18), (19.25, 6.5, 1.0, 1.0, 22)]

cases = []
for w, d, h, t, tab in CASES:
    s = RiserSpec(w_ext=inch(w), d_ext=inch(d), height=inch(h), t=t,
                  kerf=0.15, tab_w=tab, name="x")
    if s.validate():
        continue
    n = riser_net(s); bp = band_parts(s, SHEET); ra, _ = rib_pair(s)
    cases.append(dict(
        w=w, d=d, h=h, t=t, kerf=0.15, tab=tab,
        wp=s.wp, dp=s.dp, hf=s.hf, tab_eff=s.tab,
        net_w=n["size"][0], net_h=n["size"][1], net_area=part_area(n),
        net_points=len(n["cut"][0]), net_scores=len(n["score"]),
        scheme=choose_scheme(s, SHEET), band_parts=len(bp),
        band_area=sum(part_area(p) for p in bp),
        ribA_len=ra["size"][0], rib_h=ra["size"][1],
        per_sheet_one=per_sheet(lambda x: [riser_net(x)], s),
        per_sheet_band=per_sheet(lambda x: band_parts(x, SHEET), s)))

out = os.path.join(ROOT, "tests", "ref.json")
with open(out, "w") as f:
    json.dump(dict(cases=cases), f, indent=1)
print(f"wrote {out}: {len(cases)} reference cases")
