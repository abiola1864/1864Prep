#!/bin/bash
# 1864 Prep — run locally with no build step.
# Double-click this file (macOS) or run ./launch.command in a terminal.
# It sets up a private environment on first run, then starts the offline app.
cd "$(dirname "$0")"

PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "Python 3 is required. Install it from python.org, then try again."; read -r; exit 1; }

if [ ! -d ".venv" ]; then
  echo "First run: setting up (about a minute)…"
  "$PY" -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  if [ -f pyproject.toml ]; then ./.venv/bin/pip install --quiet -e ".[web,desktop]" || ./.venv/bin/pip install --quiet -e .; fi
  # core runtime deps in case extras are unavailable offline
  ./.venv/bin/pip install --quiet fastapi uvicorn python-multipart pandas openpyxl xlrd 2>/dev/null
fi

echo "Starting 1864 Prep…  (leave this window open; close it to quit)"
exec ./.venv/bin/python -m app.desktop
