from __future__ import annotations

import subprocess
import sys
import threading
import time
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

import dashboard


ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765"


def creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def start_bot() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "paper_bot.py", "--execute", "--loop"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags(),
    )


def cleanup_old_processes() -> None:
    if sys.platform != "win32":
        return
    current = os.getpid()
    script = f"""
    Get-CimInstance Win32_Process |
      Where-Object {{
        ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and
        ($_.CommandLine -like '*paper_bot.py*' -or $_.CommandLine -like '*dashboard.py*' -or $_.CommandLine -like '*integrated_app.py*') -and
        $_.ProcessId -ne {current}
      }} |
      ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}
    """
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags(),
    )


def find_browser() -> Path | None:
    candidates = [
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def start_browser() -> subprocess.Popen | None:
    browser = find_browser()
    if browser is None:
        subprocess.Popen(["cmd", "/c", "start", URL], cwd=ROOT, creationflags=creationflags())
        return None
    profile = ROOT / "app_profile"
    profile.mkdir(exist_ok=True)
    return subprocess.Popen(
        [
            str(browser),
            f"--app={URL}",
            "--new-window",
            f"--user-data-dir={profile}",
            "--disable-features=Translate",
        ],
        cwd=ROOT,
    )


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    cleanup_old_processes()
    shutdown = threading.Event()
    dashboard.SHUTDOWN_EVENT = shutdown
    server = ThreadingHTTPServer(("127.0.0.1", 8765), dashboard.Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    bot = start_bot()
    time.sleep(1.0)
    browser = start_browser()
    try:
        while not shutdown.is_set():
            if browser is not None and browser.poll() is not None:
                break
            if bot.poll() is not None:
                shutdown.set()
                break
            time.sleep(0.8)
    finally:
        stop(bot)
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
