#!/usr/bin/env python3
"""The Sitdown BBS desktop launcher. Standard-library Tkinter GUI."""
import json
import runpy
import shutil
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, filedialog
from sitdown_monitor import ServerSupervisor
import zipfile

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA = Path.home() / ".sitdown-bbs"
CONFIG = DATA / "launcher.json"
THEME = {"background": "#121212", "panel": "#242424", "primary": "#C62828",
         "connected": "#008C45", "text": "#F5F5F0", "highlight": "#F4B942"}
COMMANDS = [
    ("/sitdown", "Main menu"), ("/help", "Quick help"),
    ("/mail", "Check your mail"), ("/boards", "The Social Club"),
    ("/fortune", "Jersey wisdom"), ("/tools", "Utilities"),
    ("/cancel", "Return to main menu"),
]


class SitdownApp:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.supervisor = None
        self.restart_at = None
        self.retry_count = 0
        self.auto_restart = tk.BooleanVar(value=False)
        self.node_count = tk.StringVar(value='Observed nodes: 0')
        self.uptime = tk.StringVar(value='Uptime: 0s')
        self.demo = tk.BooleanVar(value=False)
        self.connection = tk.StringVar(value="serial")
        self.address = tk.StringVar()
        self.community = tk.StringVar(value="The Sitdown BBS")
        self.welcome = tk.StringVar(value="Ayyy, pull up a chair. We gotta talk.")
        self.status = tk.StringVar(value="Stopped")
        self.colors = THEME
        self.root.title("THE SITDOWN BBS | North Jersey Communications Division")
        self.root.geometry("1080x800")
        self.root.minsize(900, 670)
        self.root.configure(bg=THEME["background"])
        self.load()
        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.poll)

    def load(self):
        if CONFIG.exists():
            try:
                data = json.loads(CONFIG.read_text(encoding="utf-8"))
                self.connection.set(data.get("connection", "serial"))
                self.address.set(data.get("address", ""))
                self.community.set(data.get("community", "The Sitdown BBS"))
                self.welcome.set(data.get("welcome", self.welcome.get()))
            except (ValueError, OSError):
                pass

    def save(self):
        DATA.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps({
            "connection": self.connection.get(), "address": self.address.get(),
            "community": self.community.get(), "welcome": self.welcome.get()
        }, indent=2), encoding="utf-8")
        self.log("The Family Business: settings saved.")

    def build(self):
        c = self.colors
        def label(parent, text, size=11, color=None):
            return tk.Label(parent, text=text, font=("Helvetica", size, "bold"),
                            fg=color or c["text"], bg=c["background"])
        button = self.styled_button
        header = tk.Frame(self.root, bg=c["panel"], padx=22, pady=16)
        header.pack(fill="x", padx=18, pady=(14, 10))
        tk.Label(header, text="THE SITDOWN BBS", font=("Helvetica", 26, "bold"),
                 fg=c["highlight"], bg=c["panel"]).pack(anchor="w")
        tk.Label(header, text="NORTH JERSEY  •  COMMUNICATIONS DIVISION",
                 font=("Helvetica", 11, "bold"), fg=c["text"], bg=c["panel"]).pack(anchor="w")
        tk.Frame(self.root, bg=c["connected"], height=4).pack(fill="x", padx=18)
        tk.Frame(self.root, bg=c["primary"], height=4).pack(fill="x", padx=18, pady=(3, 0))
        label(self.root, "Ayyy, pull up a chair. We gotta talk.", 12, c["highlight"]).pack(pady=(2, 12))
        panel = tk.Frame(self.root, bg=c["background"])
        panel.pack(fill="x", padx=20)
        tk.Radiobutton(panel, text="USB / Serial radio", variable=self.connection,
                       value="serial", bg=c["background"], fg=c["text"], selectcolor=c["panel"]).pack(side="left")
        tk.Radiobutton(panel, text="Network radio", variable=self.connection,
                       value="tcp", bg=c["background"], fg=c["text"], selectcolor=c["panel"]).pack(side="left")
        tk.Checkbutton(panel, text="Demo mode (no radio)", variable=self.demo,
                       bg=c["background"], fg=c["highlight"], selectcolor=c["panel"]).pack(side="right")
        tk.Checkbutton(panel, text="Restart on crash", variable=self.auto_restart,
                       bg=c["background"], fg=c["highlight"], selectcolor=c["panel"]).pack(side="right")
        label(self.root, "Serial port (optional) or radio IP / hostname", 10).pack(anchor="w", padx=20, pady=(8, 2))
        tk.Entry(self.root, textvariable=self.address, bg=c["panel"], fg=c["text"],
                 insertbackground=c["text"], relief="flat", font=("Helvetica", 12)).pack(fill="x", padx=20, ipady=8)
        actions = tk.Frame(self.root, bg=c["background"])
        actions.pack(fill="x", padx=20, pady=12)
        for title, fn, color in [
            ("Start the Sitdown", self.start, c["connected"]),
            ("Fuggedaboutit (Stop)", self.stop, c["primary"]),
            ("The Playbook", self.commands, c["panel"]),
            ("The Family Business", self.settings, c["panel"]),
            ("The Books", self.backup, c["panel"])
        ]:
            button(actions, title, fn, color).pack(side="left", padx=(0, 8), pady=4)
        button(self.root, "Refresh USB Ports", self.list_ports, c["panel"]).pack(anchor="w", padx=20)
        label(self.root, "THE WIRE  •  LIVE STATUS", 12, c["highlight"]).pack(anchor="w", padx=20)
        tk.Label(self.root, textvariable=self.status, bg=c["background"],
                 fg=c["connected"], font=("Helvetica", 12, "bold")).pack(anchor="w", padx=20)
        label(self.root, "NODES OBSERVED IN RADIO TRAFFIC", 10, c["highlight"]).pack(anchor="w", padx=20)
        tk.Label(self.root, textvariable=self.node_count, bg=c["background"], fg=c["text"]).pack(anchor="w", padx=20)
        tk.Label(self.root, textvariable=self.uptime, bg=c["background"], fg=c["text"]).pack(anchor="w", padx=20)
        label(self.root, "THE BACKROOM  •  SERVER ACTIVITY", 12, c["highlight"]).pack(anchor="w", padx=20, pady=(10, 0))
        self.output = tk.Text(self.root, bg=c["panel"], fg=c["text"], insertbackground=c["text"],
                              wrap="word", relief="flat", state="disabled", height=17,
                              font=("Menlo", 12), padx=12, pady=10)
        self.output.pack(fill="both", expand=True, padx=20, pady=(12, 20))
        self.log("Ready, pal. Pick a radio, or check Demo mode.")

    def styled_button(self, parent, text, command, color=None):
        # macOS Aqua ignores custom backgrounds on native Tk buttons,
        # producing white-on-white labels. Use a keyboard-accessible Label.
        background = color or self.colors["primary"]
        control = tk.Label(parent, text=text, bg=background, fg="#FFFFFF",
                           padx=13, pady=10, cursor="hand2",
                           font=("Helvetica", 12, "bold"), relief="flat",
                           highlightthickness=2, highlightbackground=self.colors["background"],
                           takefocus=True)
        control.bind("<Button-1>", lambda _event: command())
        control.bind("<Return>", lambda _event: command())
        control.bind("<space>", lambda _event: command())
        control.bind("<FocusIn>", lambda _event: control.configure(
            highlightbackground=self.colors["highlight"]))
        control.bind("<FocusOut>", lambda _event: control.configure(
            highlightbackground=self.colors["background"]))
        return control

    def log(self, message):
        self.output.configure(state="normal")
        self.output.insert("end", message + "\n")
        if int(self.output.index("end-1c").split(".")[0]) > 2000:
            self.output.delete("1.0", "300.0")
        self.output.see("end")
        self.output.configure(state="disabled")

    def list_ports(self):
        try:
            from serial.tools import list_ports
            ports = [p.device for p in list_ports.comports()]
            self.log("USB ports: " + (", ".join(ports) if ports else "None detected"))
            if len(ports) == 1 and self.connection.get() == "serial":
                self.address.set(ports[0])
        except ImportError:
            self.log("pyserial is missing. Install requirements.txt.")

    def start(self):
        if self.supervisor and self.supervisor.running:
            return
        if self.demo.get():
            self.status.set("Demo running — no radio")
            self.log("DEMO: No radio messages are sent.")
            self.retry_count = 0
            return
        DATA.mkdir(parents=True, exist_ok=True)
        config = DATA / "config.ini" if getattr(sys, "frozen", False) else ROOT / "config.ini"
        if not config.exists() and getattr(sys, "frozen", False) and (ROOT / "example_config.ini").exists():
            shutil.copy2(ROOT / "example_config.ini", config)
            self.log("Created config.ini in ~/.sitdown-bbs. Review it before connecting a radio.")
        if not config.exists():
            messagebox.showerror("Need a Guy?", "Missing config.ini. Copy example_config.ini to config.ini and configure it first.")
            return
        addr = self.address.get().strip()
        if self.connection.get() == "tcp" and not addr:
            messagebox.showerror("Need a Guy?", "Enter the radio IP or hostname for TCP.")
            return
        self.save()
        cmd = ([sys.executable, "--sitdown-server"] if getattr(sys, "frozen", False)
               else [sys.executable, "-u", str(ROOT / "server.py")]) + ["--config", str(config),
               "--interface-type", self.connection.get()]
        if addr:
            cmd += ["--host" if self.connection.get() == "tcp" else "--port", addr]
        try:
            self.supervisor = ServerSupervisor(cmd, DATA if getattr(sys, "frozen", False) else ROOT)
            self.supervisor.start()
            self.status.set("Starting...")
            self.log("Starting The Sitdown BBS...")
        except OSError as exc:
            self.supervisor = None
            self.status.set("Start failed")
            self.log(f"Start failed: {exc}")

    def poll(self):
        monitor = self.supervisor
        if monitor:
            for kind, value in monitor.poll_events():
                if kind == "log":
                    self.log(value)
                elif kind == "state":
                    self.status.set(value)
                elif kind == "node":
                    self.node_count.set(f"Observed nodes: {len(monitor.nodes)}")
            if monitor.running:
                self.uptime.set(f"Uptime: {monitor.uptime_seconds()}s")
            elif not monitor.stopping and self.restart_at is None:
                code = monitor.process.poll() if monitor.process else "unknown"
                self.log(f"BBS process exited ({code}).")
                self.status.set("Disconnected / process stopped")
                if self.auto_restart.get() and not self.demo.get():
                    self.retry_count += 1
                    delay = min(60, 2 ** min(self.retry_count, 6))
                    self.restart_at = time.monotonic() + delay
                    self.log(f"Retrying process in {delay}s (attempt {self.retry_count}).")
                self.supervisor = None
        if self.restart_at is not None and time.monotonic() >= self.restart_at:
            self.restart_at = None
            self.start()
        if self.root.winfo_exists():
            self.root.after(500, self.poll)

    def stop(self):
        self.restart_at = None
        self.retry_count = 0
        if self.supervisor:
            self.supervisor.stop()
            self.supervisor = None
        self.status.set("Stopped")
        self.uptime.set("Uptime: 0s")
        self.log("Fuggedaboutit. Server stopped.")

    def commands(self):
        win = tk.Toplevel(self.root)
        win.title("The Playbook | Radio Commands")
        win.configure(bg=THEME["background"])
        tk.Label(win, text="DM these commands to your BBS radio", bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 14, "bold")).pack(padx=20, pady=12)
        selected = tk.StringVar(value=COMMANDS[0][0])
        for cmd, desc in COMMANDS:
            tk.Radiobutton(win, text=f"{cmd} — {desc}", value=cmd, variable=selected,
                           bg=THEME["background"], fg=THEME["text"],
                           selectcolor=THEME["panel"], anchor="w").pack(fill="x", padx=20)
        def copy():
            win.clipboard_clear()
            win.clipboard_append(selected.get())
            win.update()
        self.styled_button(win, "Copy selected command", copy, THEME["primary"]).pack(pady=15)

    def settings(self):
        win = tk.Toplevel(self.root)
        win.title("The Family Business")
        win.configure(bg=THEME["background"])
        for name, var in [("Community name", self.community), ("Welcome message (local setting)", self.welcome)]:
            tk.Label(win, text=name, bg=THEME["background"], fg=THEME["text"]).pack(anchor="w", padx=20, pady=(12, 0))
            tk.Entry(win, textvariable=var, width=55, bg=THEME["panel"], fg=THEME["text"],
                     insertbackground=THEME["text"]).pack(padx=20)
        tk.Label(win, text="Custom welcome is saved locally; radio reply integration is pending.",
                 bg=THEME["background"], fg=THEME["highlight"]).pack(padx=20, pady=10)
        self.styled_button(win, "Save", self.save, THEME["connected"]).pack(pady=12)

    def backup(self):
        DATA.mkdir(parents=True, exist_ok=True)
        destination = filedialog.asksaveasfilename(defaultextension=".zip",
                     initialfile="sitdown-backup.zip", filetypes=[("Zip archive", "*.zip")])
        if not destination:
            return
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in [CONFIG, ROOT / "config.ini", *ROOT.glob("*.db")]:
                if path.exists() and path.is_file():
                    archive.write(path, path.name)
        self.log("The Books: backup saved. Treat backups as sensitive; they may contain messages and keys.")

    def close(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    if "--sitdown-server" in sys.argv:
        sys.argv.remove("--sitdown-server")
        import server  # Ensures PyInstaller includes the server and its dependencies.
        runpy.run_module("server", run_name="__main__")
        sys.exit(0)
    root = tk.Tk()
    SitdownApp(root)
    root.mainloop()
