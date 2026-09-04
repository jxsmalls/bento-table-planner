#!/usr/bin/env python3
"""
build.py - turn a cut list into a laser-ready build package.

  python3 build.py --list cutlist.txt --out out/

cutlist.txt lines:   QTY  WxDxH   [mode]
  4   14.33x13.25x3
  6   14.33x6.5x1.5   one-piece
  2   19.25x13.25x4.5 band

mode defaults to whichever construction gets more risers per sheet.
Writes sheet-01.svg, sheet-02.svg ... plus BUILD.md.
"""

from __future__ import annotations

import argparse
import os
import sys

from riser import (RiserSpec, riser_net, rib_pair, gusset, pack, part_area,
                   svg, inch, to_in, MATERIALS, Placement)
from band import band_parts, band_geometry, choose_scheme, sq_in


def parse_list(path: str):
    items = []
    with open(path) as f:
        for ln, raw in enumerate(f, 1):
            line = raw.split("#")[0].strip()
            if not line:
                continue
            bits = line.split()
            if len(bits) < 2:
                sys.exit(f"{path}:{ln}: expected 'QTY WxDxH [mode]'")
            qty = int(bits[0])
            try:
                w, d, h = (float(v) for v in bits[1].lower().split("x"))
            except ValueError:
                sys.exit(f"{path}:{ln}: bad size '{bits[1]}'")
            mode = bits[2] if len(bits) > 2 else "auto"
            if mode not in ("auto", "band", "one-piece"):
                sys.exit(f"{path}:{ln}: mode must be auto|band|one-piece")
            items.append((qty, w, d, h, mode))
    return items


def per_sheet(make_parts, spec, sheet, cap=40):
    best, parts = 0, []
    for _ in range(cap):
        parts = parts + make_parts(spec)
        if pack(parts, sheet[0], sheet[1])[1]:
            break
        best += 1
    return best


def pick_mode(spec, sheet):
    n1 = per_sheet(lambda s: [riser_net(s)], spec, sheet)
    nb = per_sheet(lambda s: band_parts(s, sheet), spec, sheet)
    return ("band", nb, n1) if nb > n1 else ("one-piece", n1, nb)


def nest_all(parts, sheet, margin=6.0, gap=3.0, max_sheets=200):
    """Fill sheet after sheet until everything is placed."""
    sheets = []
    remaining = list(parts)
    while remaining and len(sheets) < max_sheets:
        placed, left = pack(remaining, sheet[0], sheet[1], margin, gap)
        if not placed:
            return sheets, left
        sheets.append(placed)
        keep = [id(pl.part) for pl in placed]
        out, seen = [], {}
        for p in remaining:
            if id(p) in keep and not seen.get(id(p)):
                seen[id(p)] = True
                continue
            out.append(p)
        remaining = out
    return sheets, remaining


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--material", default="matboard-4ply", choices=list(MATERIALS))
    ap.add_argument("--thickness", type=float, default=None)
    ap.add_argument("--kerf", type=float, default=0.15)
    ap.add_argument("--sheet", default="32x40", help="inches, WxH")
    ap.add_argument("--bed", default=None, help="clamp to laser bed, inches WxH")
    ap.add_argument("--tab", type=float, default=22.0)
    ap.add_argument("--gussets", type=int, default=0, help="corner gussets per riser")
    ap.add_argument("--ribs", action="store_true")
    args = ap.parse_args()

    mat = MATERIALS[args.material]
    t = args.thickness or mat["t"]
    sw, sh = (float(v) for v in args.sheet.lower().split("x"))
    sheet = (inch(sw), inch(sh))
    if args.bed:
        bw, bh = (float(v) for v in args.bed.lower().split("x"))
        sheet = (min(sheet[0], inch(bw)), min(sheet[1], inch(bh)))

    os.makedirs(args.out, exist_ok=True)
    items = parse_list(args.list)

    parts, report, problems = [], [], []
    for qty, w, d, h, mode in items:
        spec = RiserSpec(w_ext=inch(w), d_ext=inch(d), height=inch(h), t=t,
                         kerf=args.kerf, tab_w=args.tab,
                         name=f"{w:g}x{d:g}x{h:g}")
        errs = spec.validate()
        if errs:
            problems.extend(errs)
            continue

        if mode == "auto":
            mode, n_best, n_other = pick_mode(spec, sheet)
        else:
            n_best = per_sheet(
                (lambda s: band_parts(s, sheet)) if mode == "band"
                else (lambda s: [riser_net(s)]), spec, sheet)
            n_other = None

        if n_best == 0:
            problems.append(f"{spec.name}: does not fit a {sw:g}x{sh:g}in sheet in {mode} mode")
            continue

        mk = (lambda s: band_parts(s, sheet)) if mode == "band" else (lambda s: [riser_net(s)])
        for _ in range(qty):
            these = mk(spec)
            if args.ribs:
                these += rib_pair(spec)
            if args.gussets:
                net = riser_net(spec)
                if net["voids"]:
                    leg = min(net["voids"][0][2], net["voids"][0][3]) * 0.95
                    these += [gusset(leg) for _ in range(args.gussets)]
            parts += these

        g = band_geometry(spec, sheet)
        report.append(dict(qty=qty, spec=spec, mode=mode, per_sheet=n_best,
                           alt=n_other, scheme=g["scheme"], joints=g["joints"],
                           parts_each=len(mk(spec)), geo=g))

    if not parts:
        for p in problems:
            print("!!", p)
        sys.exit("nothing to cut")

    sheets, unplaced = nest_all(parts, sheet)

    for i, placed in enumerate(sheets, 1):
        path = os.path.join(args.out, f"sheet-{i:02d}.svg")
        with open(path, "w") as f:
            f.write(svg(placed, sheet[0], sheet[1], title=f"sheet {i}"))

    total_cut = sum(part_area(pl.part) for s in sheets for pl in s)
    sheet_area = sheet[0] * sheet[1]
    total_parts = sum(len(s) for s in sheets)

    # ---- build sheet -----------------------------------------------------
    L = []
    L.append("# Riser build package\n")
    L.append(f"- **Material** {args.material}, {t} mm thick")
    L.append(f"- **Sheet** {sw:g} x {sh:g} in")
    L.append(f"- **Kerf assumed** {args.kerf} mm")
    L.append(f"- **Sheets needed** {len(sheets)}")
    L.append(f"- **Parts** {total_parts}")
    L.append(f"- **Board used** {total_cut/sheet_area/len(sheets)*100:.0f}% of each sheet, "
             f"{sq_in(total_cut)/144:.1f} sq ft of cut parts")
    L.append(f"- **Score note** {mat['score_note']}\n")

    L.append("## Cut list\n")
    L.append("| Qty | Footprint | Height | Mode | Parts each | Glue joints | Per sheet |")
    L.append("|---:|---|---:|---|---:|---:|---:|")
    for r in report:
        s = r["spec"]
        alt = f' (other mode: {r["alt"]})' if r["alt"] is not None else ""
        joints = r["joints"] if r["mode"] == "band" else 4
        L.append(f'| {r["qty"]} | {to_in(s.w_ext):.2f} x {to_in(s.d_ext):.2f} in '
                 f'| {to_in(s.height):.2f} in | {r["mode"]}'
                 f'{"/" + r["scheme"] if r["mode"] == "band" else ""} '
                 f'| {r["parts_each"]} | {joints} | {r["per_sheet"]}{alt} |')

    L.append("\n## Key dimensions per SKU\n")
    for r in report:
        s, g = r["spec"], r["geo"]
        L.append(f'### {to_in(s.w_ext):.2f} x {to_in(s.d_ext):.2f} x {to_in(s.height):.2f} in'
                 f'  ({r["mode"]})')
        L.append(f'- Top panel: **{to_in(s.wp if r["mode"] == "one-piece" else s.w_ext):.3f} x '
                 f'{to_in(s.dp if r["mode"] == "one-piece" else s.d_ext):.3f} in**'
                 + ("  (drops between the walls)" if r["mode"] == "one-piece"
                    else "  (caps the walls, edges flush)"))
        L.append(f'- Wall flat height: **{to_in(s.hf):.3f} in**  '
                 f'(target {to_in(s.height):.2f} minus one thickness)')
        if r["mode"] == "one-piece":
            nw, nh = riser_net(s)["size"]
            L.append(f'- Flat net: **{to_in(nw):.2f} x {to_in(nh):.2f} in**')
            L.append(f'- Glue tabs: 4, {s.tab:.0f} mm reach, land inside the E/W walls')
        else:
            if g["scheme"] == "L2":
                L.append(f'- 2 L walls, flat length **{to_in(g["l_length"]):.3f} in**, '
                         f'fold at **{to_in(g["fold_at"]):.3f} in** from the left edge')
            else:
                L.append(f'- 2 long walls **{to_in(g["long_wall"]):.3f} in**, '
                         f'2 end walls **{to_in(g["short_wall"]):.3f} in** overall '
                         f'(fold {s.tab:.0f} mm in from each end)')
        L.append("")

    L.append("## Assembly\n")
    L.append("1. Cut. Red = through, blue = score, green = engraved labels. "
             "Run the score pass **first**, with the board face-down, so the "
             "score lands on the inside and the show face stays clean.")
    L.append("2. Fold every scored line to 90 degrees against a straight edge. "
             "Matboard wants a firm, single, decisive fold - creeping up on it "
             "crushes the core and the corner goes soft.")
    L.append("3. Glue the tabs. PVA and low-tack tape while it sets, or double-sided "
             "tape if you need them same-day. Tabs land on the **inside**, hidden.")
    L.append("4. Prime before paint. Raw matboard drinks paint and the panel will "
             "cup - a coat of shellac or spray primer on both faces first, then colour.")
    L.append("5. Optional gussets glue into the inside corners; optional ribs "
             "half-lap into a cross under the top panel and carry load to the table.\n")

    L.append("## Notes and cautions\n")
    L.append(f"- Every dimension already accounts for material thickness: the folded "
             f"exterior footprint equals the placemat exactly, and the top surface "
             f"lands at the stated height.")
    L.append(f"- Kerf is compensated on **slots only** ({args.kerf} mm undersize). "
             f"On outside contours {args.kerf} mm across a 14 in part is under "
             f"0.05% - below the accuracy of a folded matboard box.")
    L.append("- 4-ply matboard walls are stiff in-plane but a 1.5 mm panel spanning "
             "more than about 10 in will visibly deflect under any real weight. "
             "Add ribs, or laminate a second panel underneath, before trusting it "
             "with anything heavy.")
    if problems:
        L.append("\n## Problems\n")
        for p in problems:
            L.append(f"- {p}")
    if unplaced:
        L.append(f"\n- **{len(unplaced)} parts could not be nested** on any sheet.")

    with open(os.path.join(args.out, "BUILD.md"), "w") as f:
        f.write("\n".join(L) + "\n")

    for p in problems:
        print("!!", p)
    print(f'{total_parts} parts on {len(sheets)} sheet(s) of {sw:g}x{sh:g}in '
          f'{args.material}; {total_cut/sheet_area/len(sheets)*100:.0f}% board used')
    for r in report:
        print(f'  {r["qty"]:>3} x {to_in(r["spec"].w_ext):.2f}x{to_in(r["spec"].d_ext):.2f}'
              f'x{to_in(r["spec"].height):.2f}  {r["mode"]:<10} {r["per_sheet"]}/sheet')
    print(f'wrote {args.out}/sheet-*.svg and {args.out}/BUILD.md')
    if unplaced:
        print(f'!! {len(unplaced)} parts unplaced')


if __name__ == "__main__":
    main()
