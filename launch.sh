#!/bin/bash
# 1864 Prep: run locally with no build step.
# Double-click launch.command (macOS) or run "bash launch.sh" in a terminal.
# It keeps its own private set of components, and updates them whenever a new
# version of the app needs something new, so this copy matches the online demo.
cd "$(dirname "$0")"

ok311() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }

# 1) Python 3.11 or newer (many Macs ship 3.9, which is too old)
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && ok311 "$c"; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "1864 Prep needs Python 3.11 or newer."
  echo "Install it from https://www.python.org/downloads/ then open 1864 Prep again."
  read -r; exit 1
fi

# 2) a setup made with an older Python is replaced
if [ -d ".venv" ] && ! ok311 ./.venv/bin/python; then
  echo "Updating the setup to a newer Python…"; rm -rf .venv
fi
if [ ! -d ".venv" ]; then
  echo "First run: setting up (about a minute)…"
  "$PY" -m venv .venv || { echo "Could not create the setup folder."; read -r; exit 1; }
fi

# 3) install or update components whenever the app's requirements change
hashof() { (shasum "$1" 2>/dev/null || sha1sum "$1" 2>/dev/null) | cut -d' ' -f1; }
STAMP=".venv/.prep-components"
WANT="$(hashof pyproject.toml)"
if [ "$(cat "$STAMP" 2>/dev/null)" != "$WANT" ]; then
  echo "Getting 1864 Prep's components (needs internet once)…"
  ./.venv/bin/python -m pip install --quiet --upgrade pip
  if ! ./.venv/bin/python -m pip install --quiet -e ".[web]"; then
    echo "Setup did not finish. Check your internet connection and open 1864 Prep again."
    read -r; exit 1
  fi
  ./.venv/bin/python -m pip install --quiet "pywebview>=5.0" >/dev/null 2>&1 \
    || echo "(The app window component is unavailable here; 1864 Prep will open in your browser.)"
  echo "$WANT" > "$STAMP"
fi

# 4) make sure the engine's parts are really there
if ! ./.venv/bin/python -c "import pandas, dateparser, rapidfuzz, phonenumbers, jellyfish, fastapi, uvicorn" >/dev/null 2>&1; then
  echo "Some of 1864 Prep's components are missing."
  echo "Delete the hidden .venv folder in this folder, then open 1864 Prep again."
  read -r; exit 1
fi

echo "Starting 1864 Prep…  (leave this window open; close it to quit)"
exec ./.venv/bin/python -m app.desktop
