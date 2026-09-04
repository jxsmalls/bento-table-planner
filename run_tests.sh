#!/usr/bin/env bash
# Every check, in dependency order. Exits non-zero on the first failure.
set -euo pipefail
cd "$(dirname "$0")"

echo "== reference geometry =="
python3 tools/make_ref.py

echo
echo "== python: net geometry, ribs, nesting, svg =="
python3 tests/verify.py

echo
echo "== python: construction comparison and material crossover =="
python3 tests/compare.py

echo
echo "== js: planner geometry vs the python reference =="
node tests/xcheck.js

echo
echo "== js: table grid, tiles, rollup, multi-sheet nesting =="
node tests/layoutcheck.js

echo
echo "== build =="
python3 tools/make_site.py

echo
echo "all checks passed"
