#!/bin/bash
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
REPO="$HOME/Downloads/1864Prep"
echo "Source: $SRC"; echo "Repo:   $REPO"
[ -d "$REPO" ] || { echo "Repo not found at $REPO (edit REPO= in this file)"; read -r; exit 1; }
[ "$SRC" = "$REPO" ] && { echo "This folder IS the repo; nothing to copy."; read -r; exit 1; }
cp -R "$SRC"/. "$REPO"/
echo "Copied latest code into the repo."
cd "$REPO"
grep -q "build 2026" prototype/ui/1864_prep_app.html && echo "Build stamp present." || echo "Warning: build stamp not found."
if [ -d .git ]; then git add -u; git add engine/regions_fallback.py 2>/dev/null || true
  git commit -m "Sync latest 1864 Prep build" || echo "(nothing new to commit)"
  read -r -p "Push to GitHub now? [y/N] " a; [ "$a" = y ] && git push && echo "Pushed."; fi
read -r -p "Rebuild the desktop app now? [y/N] " r
if [ "$r" = y ]; then rm -rf build dist; [ -d .venv ] && source .venv/bin/activate
  pyinstaller --clean --noconfirm 1864Prep.spec && open dist/1864Prep.app; fi
echo "Done. Press Enter to close."; read -r
