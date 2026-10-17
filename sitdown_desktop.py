#!/usr/bin/env python3
"""The Empire State BBS desktop launcher. Standard-library Tkinter GUI."""
import json
import ipaddress
import sqlite3
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
        header = tk.Canvas(self.root, height=165, bg=panel, highlightthickness=0)
        header.pack(fill="x", padx=14, pady=(12, 5))
        self.header_canvas = header
        header.bind("<Configure>", self.draw_skyline_header)

        nav = tk.Frame(self.root, bg=bg)
        nav.pack(fill="x", padx=14, pady=6)
        for name, action in [
            ("EMPIRE HQ", self.show_home), ("THE GRAPEVINE", self.show_messages),
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

    def draw_skyline_header(self, event=None):
        """Vector skyline banner, responsive to window size; no external image files."""
        canvas = self.header_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1000)
        height = 165
        bg, gold = self.colors["panel"], self.colors["highlight"]
        canvas.create_rectangle(0, 0, width, height, fill=bg, outline="")
        # Midnight skyline silhouette and illuminated windows.
        buildings = [(0, 104, 65, 155), (69, 79, 120, 155), (126, 100, 174, 155),
                     (181, 62, 225, 155), (233, 91, 288, 155), (298, 73, 351, 155),
                     (359, 102, 418, 155), (428, 84, 481, 155)]
        right_start = width - 490
        for x1, y1, x2, y2 in buildings:
            for offset in (0, right_start):
                x1o, x2o = x1 + offset, x2 + offset
                canvas.create_rectangle(x1o, y1, x2o, y2, fill="#203A4B", outline="")
                for wx in range(x1o + 9, x2o - 5, 16):
                    for wy in range(y1 + 10, y2 - 7, 19):
                        canvas.create_rectangle(wx, wy, wx + 4, wy + 7,
                                                fill="#987B45", outline="")
        # Empire State Building at the right, drawn as scalable vector art.
        center = width - 185
        canvas.create_rectangle(center - 32, 49, center + 32, 155,
                                fill="#B58C48", outline="")
        canvas.create_polygon(center - 42, 52, center + 42, 52,
                              center + 26, 35, center - 26, 35, fill=gold)
        canvas.create_rectangle(center - 12, 17, center + 12, 35, fill=gold, outline="")
        canvas.create_line(center, 3, center, 17, fill="#FFE7A4", width=4)
        for wy in range(65, 145, 17):
            for wx in (center - 19, center, center + 19):
                canvas.create_rectangle(wx - 3, wy, wx + 3, wy + 9,
                                        fill="#172330", outline="")
        canvas.create_rectangle(0, 154, width, 160, fill=gold, outline="")
        canvas.create_text(25, 24, anchor="nw", text="THE EMPIRE STATE BBS",
                           fill=gold, font=("Helvetica", 29, "bold"))
        canvas.create_text(27, 79, anchor="nw",
                           text="FROM THE FIVE BOROUGHS TO THE NORTH COUNTRY",
                           fill="#F5EAD4", font=("Menlo", 12, "bold"))
        canvas.create_text(27, 108, anchor="nw",
                           text="NEW YORK STATEWIDE MESH  •  62 COUNTIES  •  ONE NETWORK",
                           fill=gold, font=("Menlo", 10, "bold"))

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

    def local_database(self):
        """Locate the BBS SQLite store without creating an empty database."""
        for path in (DATA / "bulletins.db", ROOT / "bulletins.db"):
            if path.is_file():
                return path
        return None

    def browse_local_records(self, title, table, columns):
        """Read-only browser of the local BBS database, never a radio inbox."""
        win = tk.Toplevel(self.root)
        win.title(title + " | Empire State BBS")
        win.geometry("800x530")
        win.configure(bg=THEME["background"])
        tk.Label(win, text=title.upper(), bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 22, "bold")).pack(
                     anchor="w", padx=18, pady=(15, 5))
        tk.Label(win, text="LOCAL BBS DATABASE ONLY • not a synced mesh feed. "
                 "Mail may contain private messages. No radio transmission occurs here.",
                 bg=THEME["background"], fg=THEME["text"], wraplength=760,
                 justify="left").pack(anchor="w", padx=18, pady=(0, 10))
        content = tk.Text(win, bg=THEME["panel"], fg=THEME["text"],
                          insertbackground=THEME["text"], wrap="word",
                          font=("Menlo", 11), padx=12, pady=12)
        content.pack(fill="both", expand=True, padx=18, pady=5)
        def refresh():
            content.configure(state="normal")
            content.delete("1.0", "end")
            path = self.local_database()
            if not path:
                content.insert("end", "No local BBS database found. Start the BBS "
                               "to create records, then refresh.\\n")
            else:
                try:
                    # Read-only URI prevents accidental writes and creation.
                    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                         timeout=2) as conn:
                        names = {row[0] for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'")}
                        if table not in names:
                            content.insert("end", "The database has no " + table + " table.\\n")
                        else:
                            selected = ", ".join('"' + col + '"' for col in columns)
                            query = "SELECT " + selected + " FROM " + table + " ORDER BY id DESC LIMIT 100"
                            records = conn.execute(query).fetchall()
                            if not records:
                                content.insert("end", "No saved records yet.\\n")
                            for record in records:
                                for col, value in zip(columns, record):
                                    content.insert("end", f"{col}: {value}\\n")
                                content.insert("end", "─" * 55 + "\\n")
                except sqlite3.Error as exc:
                    content.insert("end", "Could not read local BBS data: " + str(exc))
            content.configure(state="disabled")
        self.styled_button(win, "REFRESH LOCAL RECORDS", refresh,
                           THEME["primary"]).pack(pady=10)
        refresh()

    def show_messages(self):
        self.browse_local_records("The Grapevine / Local Mail", "mail",
                                  ("id", "sender_short_name", "recipient",
                                   "date", "subject", "content"))

    def show_bulletin(self):
        self.browse_local_records("The Bulletin / Local Posts", "bulletins",
                                  ("id", "board", "sender_short_name",
                                   "date", "subject", "content"))

    def show_locals(self):
        """Display only nodes actually observed in BBS process logs."""
        from tkinter import ttk
        win = tk.Toplevel(self.root)
        win.title("The Locals | Observed Meshtastic Nodes")
        win.geometry("800x510")
        win.configure(bg=THEME["background"])
        tk.Label(win, text="THE LOCALS", bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 22, "bold")).pack(
                     anchor="w", padx=20, pady=(18, 4))
        tk.Label(win, text="Observed messages in the current BBS session. "
                 "Last seen means a log event, not a verified online status. "
                 "Signal and battery telemetry are unavailable in these logs.",
                 bg=THEME["background"], fg=THEME["text"], wraplength=740,
                 justify="left").pack(anchor="w", padx=20, pady=(0, 12))
        summary = tk.StringVar(value="Loading observed nodes...")
        tk.Label(win, textvariable=summary, bg=THEME["background"],
                 fg=THEME["highlight"], font=("Menlo", 11, "bold")).pack(
                     anchor="w", padx=20, pady=(0, 8))
        columns = ("node", "name", "seen", "age")
        listing = ttk.Treeview(win, columns=columns, show="headings", height=13)
        for key, label, width in (("node", "Node ID", 150),
                                  ("name", "Observed Name", 210),
                                  ("seen", "Last Log Event", 175),
                                  ("age", "Elapsed", 110)):
            listing.heading(key, text=label)
            listing.column(key, width=width, stretch=True)
        listing.pack(fill="both", expand=True, padx=20, pady=5)
        def refresh():
            for item in listing.get_children():
                listing.delete(item)
            nodes = dict(self.supervisor.nodes) if self.supervisor else {}
            now = time.time()
            for node_id, (name, last_seen) in sorted(
                    nodes.items(), key=lambda item: item[1][1], reverse=True):
                elapsed = max(0, int(now - last_seen))
                age = f"{elapsed}s" if elapsed < 60 else (
                    f"{elapsed // 60}m" if elapsed < 3600 else f"{elapsed // 3600}h")
                listing.insert("", "end", values=(
                    node_id, name, time.strftime("%Y-%m-%d %H:%M:%S",
                                                  time.localtime(last_seen)), age))
            summary.set(f"Observed this session: {len(nodes)} node(s)"
                        if nodes else "No nodes observed in the current session")
        self.styled_button(win, "REFRESH NODE ACTIVITY", refresh,
                           THEME["primary"]).pack(pady=12)
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

    def validate_radio_target(self):
        """Validate connection input before launching the BBS process."""
        mode = self.connection.get()
        addr = self.address.get().strip()
        if mode not in ("serial", "tcp"):
            return "Choose USB/Serial or TCP."
        if mode == "tcp":
            if not addr:
                return "Enter a radio hostname or IP address."
            if any(c.isspace() for c in addr) or "/" in addr or "://" in addr:
                return "Enter a hostname or IP address, not a URL."
            try:
                ipaddress.ip_address(addr)
            except ValueError:
                labels = addr.split(".")
                if len(addr) > 253 or not all(
                    label and len(label) <= 63 and label[0].isalnum()
                    and label[-1].isalnum()
                    and all(c.isalnum() or c == "-" for c in label)
                    for label in labels
                ):
                    return "Invalid TCP hostname or IP address."
        elif any(c in addr for c in ("\\x00", "\\r", "\\n")):
            return "Serial port contains invalid characters."
        return None

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
        error = self.validate_radio_target()
        if error:
            self.status.set("Connection settings invalid")
            self.log("Connection validation: " + error)
            messagebox.showerror("Radio connection", error)
            return
        if self.connection.get() == "serial" and not addr:
            self.log("No USB port selected; Meshtastic will try automatic discovery.")
        self.save()
        cmd = ([sys.executable, "--sitdown-server"] if getattr(sys, "frozen", False)
               else [sys.executable, "-u", str(ROOT / "server.py")]) + ["--config", str(config),
               "--interface-type", self.connection.get()]
        if addr:
            cmd += ["--host" if self.connection.get() == "tcp" else "--port", addr]
        try:
            self.supervisor = ServerSupervisor(cmd, DATA if getattr(sys, "frozen", False) else ROOT,\n                                               env_overrides={"EMPIRE_ATTITUDE": self.attitude.get()})
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
        tk.Label(win, text="EMPIRE STATE ATTITUDE — applies to local preview and radio main-menu heading",
                 bg=THEME["background"], fg=THEME["highlight"]).pack(padx=20, pady=(12, 4))
        for value, title in [("clean", "Clean — Classic New York (default)"),
                             ("spicy", "Spicy — A Little Mouthy"),
                             ("unfiltered", "Unfiltered — Full New York Attitude")]:
            tk.Radiobutton(win, text=title, variable=self.attitude, value=value,
                           command=lambda v=value: self.set_attitude(v),
                           bg=THEME["background"], fg=THEME["text"],
                           selectcolor=THEME["panel"], anchor="w").pack(anchor="w", padx=20)
        tk.Label(win, text="Custom welcome is saved locally; only the radio main-menu heading uses attitude.",
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
