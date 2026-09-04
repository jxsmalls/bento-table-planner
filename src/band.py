#!/usr/bin/env python3
"""
band.py - the second construction mode: a separate flat top panel plus
folded wall pieces.

WHY THIS EXISTS
---------------
A one-piece fold-up net is a cross, so its flat footprint is

    (footprint width + 2 x height)  by  (footprint depth + 2 x height)

For placemat-sized risers that overruns a matboard sheet fast: a
14.33 x 13.25 x 4.5in riser needs a 23 x 22in net, so exactly one fits on
a 32 x 40in sheet. Splitting the riser into a flat top panel plus wall
strips keeps every part small and rectangular, which packs far tighter.

WALL SCHEMES, cheapest assembly first
-------------------------------------
  L2  two L-shaped pieces, one score fold each, 2 glue joints.
      Flat length per piece = t + (W-2t) + (D-2t) + t + tab.
  W4  four separate walls, 4 glue joints. N/S walls are plain
      rectangles the full exterior width; E/W walls are (D-2t) long with
      a fold-over glue tab at each end.
  W4S as W4, but any wall longer than the sheet is split in half and
      rejoined with an internal splice plate.

The scheme is chosen automatically from the sheet size: fewest joints
that actually fit. Band height is (target height - thickness) so the
finished top surface still lands exactly on target.

Fold allowance: score on the inside, so the flat run between fold lines
equals the INSIDE dimension, and each end of a wrapping piece extends by
one thickness to close the outer corner.
"""

from __future__ import annotations

from riser import RiserSpec, inch, to_in

SQ_MM_PER_SQ_IN = 645.16


def sq_in(mm2: float) -> float:
    return mm2 / SQ_MM_PER_SQ_IN


def _rect(w: float, h: float, label: str, spec=None, size_label: float = 6.0) -> dict:
    return dict(
        cut=[[(0, 0), (w, 0), (w, h), (0, h)]],
        score=[], voids=[], size=(w, h), spec=spec,
        label=[(w / 2, h / 2, label, min(14.0, max(4.0, min(w, h) / 6)))],
    )


def _top_panel(s: RiserSpec) -> dict:
    return _rect(s.w_ext, s.d_ext, f"{s.name} top", s)


def _l_piece(s: RiserSpec, i: int) -> dict:
    """One L: wraps a long and a short side with a single corner fold."""
    t, h, tab, br = s.t, s.hf, s.tab, s.bottom_relief
    run_a, run_b = s.w_ext - 2 * t, s.d_ext - 2 * t
    fold_at = t + run_a
    x0 = t + run_a + run_b + t          # start of the glue tab
    length = x0 + tab
    poly = [(0, 0), (x0, 0), (length, br), (length, h - br), (x0, h), (0, h)]
    return dict(
        cut=[poly],
        score=[[(fold_at, 0), (fold_at, h)], [(x0, 0), (x0, h)]],
        label=[(x0 * 0.3, h / 2, f"{s.name} L{i}", min(8.0, max(4.0, h / 4)))],
        voids=[], size=(length, h), spec=s,
    )


def _long_wall(s: RiserSpec, i: int) -> dict:
    """N or S wall: a plain rectangle the full exterior width."""
    return _rect(s.w_ext, s.hf, f"{s.name} wall{i}", s)


def _short_wall(s: RiserSpec, i: int) -> dict:
    """E or W wall: (D-2t) long, with a fold-over glue tab at each end."""
    t, h, tab, br = s.t, s.hf, s.tab, s.bottom_relief
    run_b = s.d_ext - 2 * t
    length = run_b + 2 * tab
    a, b = tab, tab + run_b
    poly = [(a, 0), (b, 0), (length, br), (length, h - br), (b, h), (a, h),
            (0, h - br), (0, br)]
    return dict(
        cut=[poly],
        score=[[(a, 0), (a, h)], [(b, 0), (b, h)]],
        label=[((a + b) / 2, h / 2, f"{s.name} end{i}", min(8.0, max(4.0, h / 4)))],
        voids=[], size=(length, h), spec=s,
    )


def _splice(s: RiserSpec) -> dict:
    """Internal backing plate that rejoins a split wall."""
    return _rect(min(80.0, s.hf * 2), s.hf - 2 * s.bottom_relief, f"{s.name} splice", s)


def choose_scheme(s: RiserSpec, sheet: tuple[float, float],
                  margin: float = 6.0) -> str:
    """Fewest-joint wall scheme whose longest part fits the sheet."""
    t = s.t
    run_a, run_b = s.w_ext - 2 * t, s.d_ext - 2 * t
    limit = max(sheet) - 2 * margin

    l2 = t + run_a + run_b + t + s.tab
    if l2 <= limit:
        return "L2"
    w4 = max(s.w_ext, run_b + 2 * s.tab)
    if w4 <= limit:
        return "W4"
    return "W4S"


def band_parts(s: RiserSpec, sheet: tuple[float, float] = (inch(32), inch(40)),
               scheme: str | None = None) -> list[dict]:
    """All flat parts for one banded riser."""
    sch = scheme or choose_scheme(s, sheet)
    parts = [_top_panel(s)]

    if sch == "L2":
        parts += [_l_piece(s, 1), _l_piece(s, 2)]
    elif sch == "W4":
        parts += [_long_wall(s, 1), _long_wall(s, 2),
                  _short_wall(s, 1), _short_wall(s, 2)]
    else:  # W4S - halve the long walls and splice them
        half = _rect(s.w_ext / 2, s.hf, f"{s.name} wallA", s)
        parts += [half, dict(half), dict(half), dict(half),
                  _short_wall(s, 1), _short_wall(s, 2),
                  _splice(s), _splice(s)]
    return parts


def band_geometry(s: RiserSpec, sheet=(inch(32), inch(40))) -> dict:
    """Key numbers, for verification and for the build sheet."""
    t = s.t
    run_a, run_b = s.w_ext - 2 * t, s.d_ext - 2 * t
    sch = choose_scheme(s, sheet)
    return dict(
        scheme=sch,
        panel=(s.w_ext, s.d_ext),
        wall_height=s.hf,
        run_a=run_a, run_b=run_b, tab=s.tab,
        l_length=t + run_a + run_b + t + s.tab,
        long_wall=s.w_ext,
        short_wall=run_b + 2 * s.tab,
        joints={"L2": 2, "W4": 4, "W4S": 6}[sch],
        # the walls must close the outer perimeter exactly
        closed_perimeter=2 * (run_a + run_b + 2 * t),
        target_perimeter=2 * (s.w_ext + s.d_ext) - 4 * t,
        # material actually consumed by the walls (excludes glue tabs)
        wall_area=s.hf * 2 * (run_a + run_b + 2 * t),
    )
