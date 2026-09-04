#!/usr/bin/env python3
"""Wrap src/planner.html into a standalone docs/index.html for static
hosting (GitHub Pages, Netlify, an S3 bucket, a shared drive).

src/planner.html is authored as Artifact body content - no doctype, html,
head or body tags, because the Artifact runtime supplies that skeleton.
This adds an equivalent one so the same file works as a plain web page.
"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "planner.html")
OUT = os.path.join(ROOT, "docs", "index.html")

body = open(SRC).read()
title = (re.search(r"<title>(.*?)</title>", body) or [None, "Bento Table Planner"])[1]

SKELETON = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Plan a bento placemat layout for an exhibition table, set elevations, and generate laser-ready fold-up riser templates.">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  html, body {{ margin: 0; }}
  body {{ font: 14px system-ui, -apple-system, sans-serif; }}
  img {{ max-width: 100%; }}
  [hidden] {{ display: none !important; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write(SKELETON)
print(f"wrote {OUT}  ({len(SKELETON)/1024:.0f} KB)")
