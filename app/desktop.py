"""Desktop shell for 1864 Prep.

Runs the engine web service on localhost and shows it in a native window, so the
whole product is a single offline app - no cloud, data never leaves the machine.
If the native window library isn't available, it falls back to the default
browser so the app still works. Package into a Mac .app / Windows .exe with the
bundled 1864Prep.spec (see docs/DEPLOY.md).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


PREFERRED_PORT = 18640   # same address every launch, so the window's saved data is found again


def _free_port() -> int:
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", PREFERRED_PORT))
        s.close()
        return PREFERRED_PORT
    except OSError:
        pass   # already in use (e.g. a second copy is open) -> any free port
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _resource_base() -> str:
    """Where bundled files live: the PyInstaller temp dir when frozen, else the
    repo root. Kept so data (prototype/ui, reference/) resolves either way."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _wait_until_up(port: int, timeout: float = 15.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    # make bundled top-level modules (regions.py) and data importable when frozen
    base = _resource_base()
    if base not in sys.path:
        sys.path.insert(0, base)
    os.chdir(base)

    import uvicorn
    os.environ.setdefault("PREP_DESKTOP", "1")   # desktop: save downloads straight to disk
    from app.server import app

    port = _free_port()
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning"),
        daemon=True,
    ).start()

    up = _wait_until_up(port)
    url = f"http://127.0.0.1:{port}/"
    if not up:
        print("Engine did not start in time; opening anyway:", url)

    try:
        import webview  # pywebview - native window
        import urllib.request as _u, json as _json

        class _Api:
            """Exposed to the page as window.pywebview.api — lets the user pick where
            to save a produced file via a native Save dialog."""
            def save_file(self, rid, fmt, suggested):
                ext = {"excel": "xlsx"}.get(fmt, fmt)
                win = webview.windows[0] if webview.windows else None
                target = win.create_file_dialog(webview.SAVE_DIALOG,
                            save_filename=f"{suggested}.{ext}") if win else None
                if not target:
                    return {"cancelled": True}
                path = target if isinstance(target, str) else target[0]
                # ask the local engine for the bytes, write them where the user chose
                req = _u.Request(f"http://127.0.0.1:{port}/api/tool/download/{rid}?fmt={fmt}")
                with _u.urlopen(req, timeout=60) as r:
                    data = r.read()
                with open(path, "wb") as f:
                    f.write(data)
                return {"saved": path}

        webview.create_window("1864 Prep", url, width=1200, height=820, js_api=_Api())
        # keep the window's storage between launches (pywebview defaults to a
        # private, throwaway session, which wiped AI keys and setup on every start)
        _store = os.path.join(os.path.expanduser("~"), ".1864prep", "webview")
        os.makedirs(_store, exist_ok=True)
        try:
            webview.start(private_mode=False, storage_path=_store)
        except TypeError:          # older pywebview without these options
            webview.start()
    except Exception:
        # no native window available - use the browser, keep the server alive
        print("Native window unavailable; opening in your browser:", url)
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
