#!/usr/bin/env bash
#
# Push this repo to GitHub and print the Pages setup steps.
# Run it from macOS Terminal, where your GitHub credentials already live.
#
#   ./push.sh <github-username> [repo-name]
#
# Two routes. If you have the gh CLI on your Mac, this one line does
# everything including creating the repo:
#
#   gh repo create bento-table-planner --public --source=. --push
#
# Otherwise create an empty repo on github.com first (no README, no
# .gitignore, no licence — an empty one, or the first push will conflict),
# then run this script.

set -euo pipefail
cd "$(dirname "$0")"

USER="${1:-}"
REPO="${2:-bento-table-planner}"

if [ -z "$USER" ]; then
  echo "usage: ./push.sh <github-username> [repo-name]" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "! working tree is dirty — commit or stash first:" >&2
  git status --short >&2
  exit 1
fi

# SSH if you have keys set up, HTTPS otherwise. Change if you prefer.
if ssh -T -o StrictHostKeyChecking=accept-new -o ConnectTimeout=6 \
     git@github.com 2>&1 | grep -q "successfully authenticated"; then
  URL="git@github.com:$USER/$REPO.git"
  echo "using SSH: $URL"
else
  URL="https://github.com/$USER/$REPO.git"
  echo "using HTTPS: $URL  (you'll be asked for a token, not a password)"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$URL"
else
  git remote add origin "$URL"
fi

git push -u origin main

cat <<DONE

Pushed. Now turn on Pages:

  1. https://github.com/$USER/$REPO/settings/pages
  2. Source: "Deploy from a branch"
  3. Branch: main    Folder: /docs
  4. Save, then wait ~1 minute

The tool will be at:

  https://$USER.github.io/$REPO/

Then put that URL in README.md where it says "Live tool", and:

  git commit -am "Add the live Pages URL" && git push

HEADS UP: GitHub only serves Pages from a PRIVATE repo on paid plans
(Pro / Team / Enterprise). If this repo is private and Pages stays dark,
either make the repo public — the tool contains no IDEO client material,
just geometry — or use the Claude artifact share link instead.
DONE
