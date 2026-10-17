#!/usr/bin/env python3
"""The Empire State BBS desktop launcher. Standard-library Tkinter GUI."""
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
DATA = Path.home() / ".empire-state-bbs"
CONFIG = DATA / "launcher.json"
THEME = {"background": "#061018", "panel": "#101D29", "primary": "#B88A35",
         "connected": "#1CC86A", "text": "#F5EAD4", "highlight": "#F2BE51"}
COMMANDS = [
    ("/empire", "Main menu"), ("/help", "Quick help"),
    ("/mail", "Check your mail"), ("/boards", "The Bulletin Board"),
    ("/fortune", "New York wisdom"), ("/tools", "Utilities"),
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
        self.attitude = tk.StringVar(value="clean")
        self.connection = tk.StringVar(value="serial")
        self.address = tk.StringVar()
        self.community = tk.StringVar(value="The Empire State BBS")
        self.welcome = tk.StringVar(value="AYO, welcome to the Empire State. One state. One network.")
        self.status = tk.StringVar(value="Stopped")
        self.colors = THEME
        self.root.title("THE EMPIRE STATE BBS | New York State Communications Network")
        self.root.geometry("1220x830")
        self.root.minsize(1040, 720)
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
                self.community.set(data.get("community", "The Empire State BBS"))
                self.welcome.set(data.get("welcome", self.welcome.get()))
                self.attitude.set(data.get("attitude", "clean") if data.get("attitude") in ("clean", "spicy", "unfiltered") else "clean")
            except (ValueError, OSError):
                pass

    def save(self):
        DATA.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps({
            "connection": self.connection.get(), "address": self.address.get(),
            "community": self.community.get(), "welcome": self.welcome.get(),
            "attitude": self.attitude.get()
        }, indent=2), encoding="utf-8")
        self.log("Control Room: settings saved.")

    def build(self):
        c = self.colors
        bg, panel, gold, cream = c["background"], c["panel"], c["highlight"], c["text"]
        header = tk.Frame(self.root, bg=panel, padx=22, pady=14)
        header.pack(fill="x", padx=14, pady=(12, 5))
        tk.Label(header, text="THE EMPIRE STATE BBS", font=("Helvetica", 30, "bold"),
                 fg=gold, bg=panel).pack(anchor="w")
        tk.Label(header, text="FROM THE FIVE BOROUGHS TO THE NORTH COUNTRY  •  ALL 62 COUNTIES",
                 font=("Menlo", 11, "bold"), fg=cream, bg=panel).pack(anchor="w")
        nav = tk.Frame(self.root, bg=bg)
        nav.pack(fill="x", padx=14, pady=6)
        for name, action in [
            ("EMPIRE HQ", self.show_home), ("THE GRAPEVINE", self.commands),
            ("THE BULLETIN", self.show_bulletin), ("THE LOCALS", self.show_locals),
            ("THE EMPIRE CONNECTION", self.show_radio), ("SETTINGS", self.settings),
            ("ABOUT", self.show_about)
        ]:
            self.styled_button(nav, name, action, panel).pack(side="left", padx=(0, 5))
        cards = tk.Frame(self.root, bg=bg)
        cards.pack(fill="x", padx=14, pady=6)
        left = tk.Frame(cards, bg=panel, padx=13, pady=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.panel_heading(left, "THE EMPIRE CONNECTION")
        tk.Label(left, textvariable=self.status, bg=panel, fg=c["connected"],
                 font=("Menlo", 12, "bold")).pack(anchor="w", pady=6)
        tk.Label(left, textvariable=self.node_count, bg=panel, fg=cream).pack(anchor="w")
        tk.Label(left, textvariable=self.uptime, bg=panel, fg=cream).pack(anchor="w")
        for name, value in [("USB / Serial radio", "serial"), ("Network / TCP radio", "tcp")]:
            tk.Radiobutton(left, text=name, variable=self.connection, value=value,
                           bg=panel, fg=cream, selectcolor=bg).pack(anchor="w")
        tk.Label(left, text="Serial port / TCP host", bg=panel, fg=gold).pack(anchor="w")
        tk.Entry(left, textvariable=self.address, bg=bg, fg=cream,
                 insertbackground=cream, relief="flat").pack(fill="x", ipady=6, pady=4)
        self.styled_button(left, "FIND USB PORTS", self.list_ports, bg).pack(fill="x", pady=5)
        center = tk.Frame(cards, bg=panel, padx=13, pady=12)
        center.pack(side="left", fill="both", expand=True, padx=5)
        self.panel_heading(center, "BBS SERVER")
        tk.Label(center, text="Actual server status is shown at left.",
                 bg=panel, fg=cream).pack(anchor="w", pady=7)
        tk.Checkbutton(center, text="DEMO MODE (NO RADIO)", variable=self.demo,
                       bg=panel, fg=gold, selectcolor=bg).pack(anchor="w")
        tk.Checkbutton(center, text="Restart on crash", variable=self.auto_restart,
                       bg=panel, fg=cream, selectcolor=bg).pack(anchor="w")
        self.styled_button(center, "START BBS SERVER", self.start, "#166F43").pack(fill="x", pady=(14, 5))
        self.styled_button(center, "STOP SERVER", self.stop, "#9A302A").pack(fill="x", pady=5)
        self.styled_button(center, "THE ARCHIVES", self.backup, bg).pack(fill="x", pady=5)
        right = tk.Frame(cards, bg=panel, padx=13, pady=12)
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.panel_heading(right, "EMPIRE STATE ATTITUDE")
        tk.Label(right, text="Turn up the New York. Clean by default.",
                 bg=panel, fg=cream).pack(anchor="w", pady=7)
        for value, name in [("clean", "CLEAN"), ("spicy", "SPICY"), ("unfiltered", "UNCENSORED")]:
            tk.Radiobutton(right, text=name, variable=self.attitude, value=value,
                           command=lambda v=value: self.set_attitude(v),
                           bg=panel, fg=gold, selectcolor=bg).pack(anchor="w")
        tk.Label(right, text="LOCAL PREVIEW • NOT TRANSMITTED", bg=panel,
                 fg=gold, font=("Menlo", 9)).pack(anchor="w", pady=(8, 0))
        self.preview = tk.Label(right, text=self.attitude_message(), bg=bg,
                                fg=cream, font=("Menlo", 10), wraplength=290,
                                justify="left", padx=8, pady=8)
        self.preview.pack(fill="x", pady=5)
        logpanel = tk.Frame(self.root, bg=panel, padx=13, pady=11)
        logpanel.pack(fill="both", expand=True, padx=14, pady=(5, 10))
        loghead = tk.Frame(logpanel, bg=panel)
        loghead.pack(fill="x")
        tk.Label(loghead, text="UNDER THE HOOD  /  SERVER LOG", bg=panel,
                 fg=gold, font=("Menlo", 12, "bold")).pack(side="left")
        self.styled_button(loghead, "CLEAR LOG", self.clear_log, bg).pack(side="right")
        self.output = tk.Text(logpanel, bg="#030A10", fg="#8BE0A0",
                              insertbackground=cream, wrap="word", relief="flat",
                              state="disabled", height=14, font=("Menlo", 11), padx=10, pady=8)
        self.output.pack(fill="both", expand=True, pady=(7, 0))
        self.log(self.attitude_message())
        self.log("EMPIRE HQ • Demo is clearly labeled. No simulated connections.")
        tk.Label(self.root, text="NEW YORK  •  62 COUNTIES  •  ONE NETWORK",
                 bg=bg, fg=gold, font=("Menlo", 10, "bold")).pack(pady=(0, 8))

    def panel_heading(self, parent, title):
        tk.Label(parent, text=title, bg=self.colors["panel"],
                 fg=self.colors["highlight"], font=("Menlo", 12, "bold")).pack(anchor="w")

    def clear_log(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def show_home(self):
        self.log("EMPIRE HQ: You're already on the dashboard.")

    def command_panel(self, title, subtitle, commands):
        """Read-only command browser: actual BBS content stays on the radio."""
        win = tk.Toplevel(self.root)
        win.title(title + " | The Empire State BBS")
        win.geometry("560x420")
        win.configure(bg=THEME["background"])
        tk.Label(win, text=title.upper(), bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 20, "bold")).pack(
                     anchor="w", padx=20, pady=(20, 4))
        tk.Label(win, text=subtitle, bg=THEME["background"], fg=THEME["text"],
                 justify="left", wraplength=510).pack(anchor="w", padx=20, pady=(0, 15))
        for command, description in commands:
            line = tk.Frame(win, bg=THEME["panel"], padx=12, pady=9)
            line.pack(fill="x", padx=20, pady=4)
            tk.Label(line, text=command, bg=THEME["panel"],
                     fg=THEME["highlight"], font=("Menlo", 12, "bold")).pack(side="left")
            tk.Label(line, text=description, bg=THEME["panel"],
                     fg=THEME["text"]).pack(side="left", padx=14)
            def copy(value=command):
                win.clipboard_clear()
                win.clipboard_append(value)
                win.update()
                self.log("Copied radio command: " + value)
            self.styled_button(line, "COPY", copy, THEME["background"]).pack(side="right")

    def show_bulletin(self):
        self.command_panel("The Bulletin", "Bulletin boards live on your Meshtastic BBS. "
                           "DM these commands to your BBS node; this window does not "
                           "download, create, or invent posts.", [
                               ("/boards", "Browse bulletin boards"),
                               ("/empire", "Return to the main menu"),
                               ("/help", "View available commands")])

    def show_locals(self):
        win = tk.Toplevel(self.root)
        win.title("The Locals | Observed Radio Nodes")
        win.geometry("610x430")
        win.configure(bg=THEME["background"])
        tk.Label(win, text="THE LOCALS", bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 22, "bold")).pack(
                     anchor="w", padx=20, pady=(20, 4))
        tk.Label(win, text="Nodes observed in this BBS process's logs only. "
                 "Not a full mesh directory or proof of current connectivity.",
                 bg=THEME["background"], fg=THEME["text"],
                 wraplength=550, justify="left").pack(anchor="w", padx=20, pady=(0, 12))
        listing = tk.Text(win, bg=THEME["panel"], fg=THEME["text"],
                          font=("Menlo", 11), relief="flat", height=12)
        listing.pack(fill="both", expand=True, padx=20, pady=6)
        def refresh():
            listing.delete("1.0", "end")
            nodes = self.supervisor.nodes if self.supervisor else {}
            if not nodes:
                listing.insert("end", "No nodes observed in this session.\\n"
                               "Start a real BBS radio connection to collect activity.")
            else:
                for node_id, (name, last_seen) in sorted(nodes.items()):
                    listing.insert("end", f"{name}  |  {node_id}  |  "
                                   f"Last log: {time.strftime('%H:%M:%S', time.localtime(last_seen))}\\n")
            listing.configure(state="disabled")
        def update_listing():
            listing.configure(state="normal")
            refresh()
        self.styled_button(win, "REFRESH OBSERVED NODES", update_listing,
                           THEME["primary"]).pack(pady=10)
        refresh()

    def show_radio(self):
        self.log("THE EMPIRE CONNECTION: Choose USB or TCP and start the BBS.")
        self.list_ports()

    def show_about(self):
        messagebox.showinfo("The Empire State BBS",
                            "New York statewide Meshtastic BBS.\\n"
                            "From the Five Boroughs to the North Country.\\n"
                            "Demo mode never connects or transmits.")

    def attitude_message(self):
        return {
            "clean": "AYO! Welcome to the Empire State. Whaddya wanna do, boss?",
            "spicy": "AYO! Welcome to New York. Pick a damn command already, we\u0027re busy over here!",
            "unfiltered": "AYO! Welcome to the Empire State. Pick a fuckin\u0027 command, boss!",
        }.get(self.attitude.get(), "AYO! Welcome to the Empire State.")

    def set_attitude(self, value):
        self.attitude.set(value)
        self.save()
        if hasattr(self, "preview"):
            self.preview.configure(text=self.attitude_message())
        self.log(self.attitude_message())

    def styled_button(self, parent, text, command, color=None):
        # macOS Aqua ignores custom backgrounds on native Tk buttons,
        # producing white-on-white labels. Use a keyboard-accessible Label.
        background = color or self.colors["primary"]
        control = tk.Label(parent, text=text, bg=background, fg="#F5EAD4",
                           padx=9, pady=9, cursor="hand2",
                           font=("Helvetica", 10, "bold"), relief="flat",
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
            self.log(self.attitude_message())
            self.retry_count = 0
            return
        DATA.mkdir(parents=True, exist_ok=True)
        config = DATA / "config.ini" if getattr(sys, "frozen", False) else ROOT / "config.ini"
        if not config.exists() and getattr(sys, "frozen", False) and (ROOT / "example_config.ini").exists():
            shutil.copy2(ROOT / "example_config.ini", config)
            self.log("Created config.ini in ~/.empire-state-bbs. Review it before connecting a radio.")
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
            self.log("Starting The Empire State BBS...")
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
        win.title("Control Room")
        win.configure(bg=THEME["background"])
        for name, var in [("Community name", self.community), ("Welcome message (local setting)", self.welcome)]:
            tk.Label(win, text=name, bg=THEME["background"], fg=THEME["text"]).pack(anchor="w", padx=20, pady=(12, 0))
            tk.Entry(win, textvariable=var, width=55, bg=THEME["panel"], fg=THEME["text"],
                     insertbackground=THEME["text"]).pack(padx=20)
        tk.Label(win, text="EMPIRE STATE ATTITUDE — applies only to local interface and demo text",
                 bg=THEME["background"], fg=THEME["highlight"]).pack(padx=20, pady=(12, 4))
        for value, title in [("clean", "Clean — Classic New York (default)"),
                             ("spicy", "Spicy — A Little Mouthy"),
                             ("unfiltered", "Unfiltered — Full New York Attitude")]:
            tk.Radiobutton(win, text=title, variable=self.attitude, value=value,
                           command=lambda v=value: self.set_attitude(v),
                           bg=THEME["background"], fg=THEME["text"],
                           selectcolor=THEME["panel"], anchor="w").pack(anchor="w", padx=20)
        tk.Label(win, text="Custom welcome is saved locally; radio reply integration is pending.",
                 bg=THEME["background"], fg=THEME["highlight"]).pack(padx=20, pady=10)
        self.styled_button(win, "Save", self.save, THEME["connected"]).pack(pady=12)

    def backup(self):
        DATA.mkdir(parents=True, exist_ok=True)
        destination = filedialog.asksaveasfilename(defaultextension=".zip",
                     initialfile="empire-state-backup.zip", filetypes=[("Zip archive", "*.zip")])
        if not destination:
            return
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in [CONFIG, ROOT / "config.ini", *ROOT.glob("*.db")]:
                if path.exists() and path.is_file():
                    archive.write(path, path.name)
        self.log("The Archives: backup saved. Treat backups as sensitive; they may contain messages and keys.")

    def close(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        # Launch the *packaged* GUI in CI, not just the source Python module.
        root = tk.Tk()
        root.withdraw()
        app = SitdownApp(root)
        root.update_idletasks()
        if not app.output.winfo_exists():
            raise RuntimeError("Dashboard failed to initialize")
        print("EMPIRE_GUI_SMOKE_OK", flush=True)
        root.destroy()
        sys.exit(0)
    if "--sitdown-server" in sys.argv:
        sys.argv.remove("--sitdown-server")
        import server  # Ensures PyInstaller includes the server and its dependencies.
        runpy.run_module("server", run_name="__main__")
        sys.exit(0)
    root = tk.Tk()
    SitdownApp(root)
    root.mainloop()
