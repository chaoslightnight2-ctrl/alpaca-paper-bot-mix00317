from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from tkinter import BOTH, Button, Frame, Label, Tk, messagebox


ROOT = Path(__file__).resolve().parent
DASHBOARD_URL = "http://127.0.0.1:8765"


class BotApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Alpaca Paper Bot Kontrol")
        self.root.geometry("520x310")
        self.root.minsize(460, 290)
        self.root.configure(bg="#070a12")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.dashboard: subprocess.Popen | None = None
        self.bot: subprocess.Popen | None = None
        self.started_at = time.time()
        self._build()
        self.start_all()
        self.root.after(1000, self.tick)

    def _build(self) -> None:
        wrap = Frame(self.root, bg="#070a12", padx=22, pady=20)
        wrap.pack(fill=BOTH, expand=True)
        Label(
            wrap,
            text="ALPACA PAPER BOT",
            fg="#20e8ff",
            bg="#070a12",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        Label(
            wrap,
            text="Kontrol Merkezi",
            fg="#edf7ff",
            bg="#070a12",
            font=("Segoe UI", 25, "bold"),
        ).pack(anchor="w", pady=(2, 8))
        Label(
            wrap,
            text="Bu pencere ana uygulamadır. Kapatınca paper bot ve dashboard birlikte kapanır.",
            fg="#8ca2b7",
            bg="#070a12",
            wraplength=460,
            justify="left",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 18))

        self.status = Label(
            wrap,
            text="Başlatılıyor...",
            fg="#37f29a",
            bg="#101827",
            padx=12,
            pady=12,
            font=("Consolas", 11),
            anchor="w",
            justify="left",
        )
        self.status.pack(fill=BOTH, pady=(0, 16))

        buttons = Frame(wrap, bg="#070a12")
        buttons.pack(fill=BOTH)
        Button(
            buttons,
            text="Dashboard'u Aç",
            command=lambda: webbrowser.open(DASHBOARD_URL),
            bg="#12243a",
            fg="#edf7ff",
            activebackground="#173452",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=10,
        ).pack(side="left", padx=(0, 8))
        Button(
            buttons,
            text="Botu Durdur ve Kapat",
            command=self.close,
            bg="#351327",
            fg="#fff0fb",
            activebackground="#4b1a38",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=10,
        ).pack(side="left")

    def start_process(self, script: str, *args: str) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, script, *args],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    def start_all(self) -> None:
        self.dashboard = self.start_process("dashboard.py")
        time.sleep(1.0)
        self.bot = self.start_process("paper_bot.py", "--execute", "--loop")
        time.sleep(0.8)
        webbrowser.open(DASHBOARD_URL)

    def proc_alive(self, proc: subprocess.Popen | None) -> bool:
        return proc is not None and proc.poll() is None

    def tick(self) -> None:
        dash = "AÇIK" if self.proc_alive(self.dashboard) else "KAPALI"
        bot = "AÇIK" if self.proc_alive(self.bot) else "KAPALI"
        mins = int((time.time() - self.started_at) // 60)
        self.status.configure(text=f"Dashboard: {dash}\nPaper bot: {bot}\nÇalışma süresi: {mins} dk\nPanel: {DASHBOARD_URL}")
        self.root.after(1000, self.tick)

    def stop_process(self, proc: subprocess.Popen | None) -> None:
        if not self.proc_alive(proc):
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def close(self) -> None:
        if messagebox.askokcancel("Kapat", "Paper bot ve dashboard kapatılsın mı?"):
            self.stop_process(self.bot)
            self.stop_process(self.dashboard)
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    BotApp().run()
