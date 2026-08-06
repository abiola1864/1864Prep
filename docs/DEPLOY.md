# From repo to installable app

The end product is a **desktop app** (offline, data never leaves the machine).
Along the way we can demo cheaply on the web — but the web demo is for
**synthetic data only**, because hosting means data goes to a server.

## Step 1 — the engine web service (done)

`app/server.py` is a small FastAPI service around the engine:

- `POST /api/profile` — read a file (CSV/Excel/JSON/PDF), report what was
  detected and each column's type.
- `POST /api/clean` — read + auto-clean, return the before/after overview and a
  random spot-check sample.
- `/` serves the prototype UI.

Run locally:
```bash
pip install -e ".[web]"
uvicorn app.server:app --reload      # open http://127.0.0.1:8000
```

## Step 2 — free UX demo on GitHub Pages ($0)

The prototype is static HTML, so GitHub Pages can host it with no server:
repo **Settings → Pages → Deploy from branch → main → /prototype/ui**. Good for
showing the flow to partners. (No engine runs here — it's the mockup.)

## Step 3 — live engine demo on Render (free tier)

`render.yaml` is a blueprint. In Render: **New → Blueprint → pick this repo**.
It installs `.[web]` and starts uvicorn. You get a public URL where the real
engine cleans uploaded files. The free instance sleeps when idle (fine for
demos). **Put only synthetic/sample data through it.**

## Step 4 — the desktop app (Mac + Windows)

`app/desktop.py` runs the same service on localhost and shows it in a native
window via **pywebview** — so the desktop app and the web demo share one
codebase. Package it with **PyInstaller**:

```bash
pip install -e ".[web,desktop]" pyinstaller
# macOS:
pyinstaller --noconfirm --windowed --name 1864Prep \
  --add-data "prototype/ui:prototype/ui" app/desktop.py
# Windows (note the ';' instead of ':'):
pyinstaller --noconfirm --windowed --name 1864Prep ^
  --add-data "prototype/ui;prototype/ui" app/desktop.py
```

Output lands in `dist/` — a `.app` on Mac, a `.exe`/folder on Windows.

**You build on the OS you target.** You have a Mac, so you can build the Mac app
directly. For the Windows `.exe` without a Windows PC, the included GitHub Action
(`.github/workflows/build-desktop.yml`) builds **both** on GitHub's free runners
— trigger it from the **Actions** tab (or push a `v*` tag) and download the
installers from the run's artifacts. This is a starting point and will need
tuning (icons, a `.spec` file for reliable data bundling).

## Step 5 — signing & notarisation (costs money — do last)

Unsigned apps run fine for testing:
- **Mac:** right-click the app → **Open** → confirm once.
- **Windows:** "More info" → **Run anyway**.

To remove the warnings for wide distribution you need paid certificates:
- **Apple Developer Program** — US$99/year (Developer ID signing + notarisation).
- **Windows code-signing certificate** — roughly US$100–300/year.

Nothing before this step costs money. Sign only when you're distributing beyond
your own testers.

## What runs where

| Stage | Cost | Data leaves machine? | Use |
|-------|------|----------------------|-----|
| GitHub Pages (mockup) | free | n/a (no engine) | show the flow |
| Render (live engine)  | free tier | **yes** — synthetic only | test the engine |
| Desktop app           | free to build | **no** | the real product |
| Signed desktop app    | ~$99–400/yr | no | wide distribution |
