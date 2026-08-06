"""Desktop shell: runs the engine web service on localhost and shows it in a
native window. No data leaves the machine. Package with PyInstaller into a
Mac .app / Windows .exe (see docs/DEPLOY.md)."""
from __future__ import annotations

import socket
import threading
import time


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    import uvicorn
    import webview  # pywebview
    from app.server import app

    port = _free_port()
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning"),
        daemon=True,
    ).start()
    time.sleep(1.0)
    webview.create_window("1864 Prep", f"http://127.0.0.1:{port}/1864_prep_app.html",
                          width=1200, height=820)
    webview.start()


if __name__ == "__main__":
    main()
