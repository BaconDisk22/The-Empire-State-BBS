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
from radio_health import radio_health_label
from radio_diagnostics import available_serial_ports, check_serial_target, check_tcp_target
import zipfile
from desktop_session import DesktopStore
from desktop_views import open_posts, open_nodes

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA = Path.home() / ".empire-state-bbs"
CONFIG = DATA / "launcher.json"
THEME = {"background": "#090B10", "panel": "#171A22", "primary": "#342319",
         "connected": "#44DF79", "text": "#F5F1E9", "highlight": "#FF791F"}
COMMANDS = [
    ("/empire", "Main menu"), ("/help", "Quick help"),
    ("/mail", "Check your mail"), ("/boards", "The Bulletin Board"),
    ("/fortune", "New York wisdom"), ("/tools", "Utilities"),
    ("/cancel", "Return to main menu"),
]


class SitdownApp:
    def __init__(self, root):
        self.root = root
        self.store = DesktopStore(DATA / "desktop-state.db",
                                  (DATA if getattr(sys, "frozen", False) else ROOT) / "bulletins.db")
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
        self.radio_health = tk.StringVar(value="Radio health: unverified")
        self.last_serial_scan = 0.0
        self.last_serial_ports = None
        self.waiting_for_usb = False
        self.colors = THEME
        self.root.title("THE EMPIRE STATE BBS | New York State Communications Network")
        self.root.geometry("1360x870")
        self.root.minsize(1100, 740)
        self.root.configure(bg=THEME["background"])
        self.load()
        self.build()
        # Command shortcuts do not transmit or start/stop the server.
        for sequence, action in [
            ("<Command-1>", self.show_home), ("<Command-2>", self.show_messages),
            ("<Command-3>", self.show_bulletin), ("<Command-4>", self.show_locals),
            ("<Command-5>", self.show_radio), ("<Command-comma>", self.settings),
        ]:
            self.root.bind(sequence, lambda _event, callback=action: callback())
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
        nav.pack(fill="x", padx=14, pady=(3, 12))
        for name, action in [
            ("EMPIRE HQ", self.show_home), ("THE GRAPEVINE", self.show_messages),
            ("THE BULLETIN", self.show_bulletin), ("THE LOCALS", self.show_locals),
            ("THE EMPIRE CONNECTION", self.show_radio), ("SETTINGS", self.settings),
            ("ABOUT", self.show_about)
        ]:
            self.styled_button(nav, name, action, "#9C3D0B" if name == "EMPIRE HQ" else panel).pack(side="left", padx=(0, 7))
        cards = tk.Frame(self.root, bg=bg)
        cards.pack(fill="x", padx=14, pady=6)
        left = tk.Frame(cards, bg=panel, padx=19, pady=18,
                        highlightthickness=2, highlightbackground=panel)
        self.connection_panel = left
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.panel_heading(left, "01  /  THE EMPIRE CONNECTION")
        self.status_label = tk.Label(left, textvariable=self.status, bg=panel,
                                     fg=c["highlight"], font=("Menlo", 12, "bold"))
        self.status_label.pack(anchor="w", pady=6)
        self.status.trace_add("write", self.update_status_color)
        self.update_status_color()
        tk.Label(left, textvariable=self.radio_health, bg=panel, fg=gold,
                 wraplength=300, justify="left").pack(anchor="w")
        tk.Label(left, textvariable=self.node_count, bg=panel, fg=cream).pack(anchor="w")
        tk.Label(left, textvariable=self.uptime, bg=panel, fg=cream).pack(anchor="w")
        for name, value in [("USB / Serial radio", "serial"), ("Network / TCP radio", "tcp")]:
            tk.Radiobutton(left, text=name, variable=self.connection, value=value,
                           bg=panel, fg=cream, selectcolor=bg).pack(anchor="w")
        tk.Label(left, text="Serial port / TCP host", bg=panel, fg=gold).pack(anchor="w")
        self.connection_address = tk.Entry(
            left, textvariable=self.address, bg=bg, fg=cream,
            insertbackground=cream, relief="flat")
        self.connection_address.pack(fill="x", ipady=6, pady=4)
        self.styled_button(left, "⌕  FIND USB PORTS", self.list_ports, bg).pack(fill="x", pady=5)
        self.styled_button(left, "◎  CHECK RADIO TARGET", self.check_radio_target, bg).pack(fill="x", pady=5)
        center = tk.Frame(cards, bg=panel, padx=19, pady=18)
        center.pack(side="left", fill="both", expand=True, padx=5)
        self.panel_heading(center, "02  /  BBS SERVER")
        tk.Label(center, text="Actual server status is shown at left.",
                 bg=panel, fg=cream).pack(anchor="w", pady=7)
        tk.Checkbutton(center, text="DEMO MODE (NO RADIO)", variable=self.demo,
                       bg=panel, fg=gold, selectcolor=bg).pack(anchor="w")
        tk.Checkbutton(center, text="Auto recovery (crash / radio loss)", variable=self.auto_restart,
                       bg=panel, fg=cream, selectcolor=bg).pack(anchor="w")
        self.styled_button(center, "▶  START BBS SERVER", self.start, "#166F43").pack(fill="x", pady=(14, 5))
        self.styled_button(center, "■  STOP SERVER", self.stop, "#9A302A").pack(fill="x", pady=5)
        self.styled_button(center, "THE ARCHIVES", self.backup, bg).pack(fill="x", pady=5)
        right = tk.Frame(cards, bg=panel, padx=19, pady=18)
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.panel_heading(right, "03  /  EMPIRE STATE ATTITUDE")
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
        logpanel = tk.Frame(self.root, bg=panel, padx=18, pady=14)
        logpanel.pack(fill="both", expand=True, padx=14, pady=(5, 10))
        loghead = tk.Frame(logpanel, bg=panel)
        loghead.pack(fill="x")
        tk.Label(loghead, text="UNDER THE HOOD  /  SERVER LOG", bg=panel,
                 fg=gold, font=("Helvetica", 13, "bold")).pack(side="left")
        self.styled_button(loghead, "CLEAR LOG", self.clear_log, bg).pack(side="right")
        self.output = tk.Text(logpanel, bg="#080C12", fg="#8CE9A3",
                              insertbackground=cream, wrap="word", relief="flat",
                              state="disabled", height=14, font=("Menlo", 11), padx=10, pady=8)
        self.output.pack(fill="both", expand=True, pady=(7, 0))
        self.log(self.attitude_message())
        self.log("EMPIRE HQ • Demo is clearly labeled. No simulated connections.")
        self.log("Navigation: ⌘1 HQ • ⌘2 Grapevine • ⌘3 Bulletin • ⌘4 Locals • ⌘5 Connection • ⌘, Settings")
        tk.Label(self.root, text="NEW YORK  •  62 COUNTIES  •  ONE NETWORK",
                 bg=bg, fg=gold, font=("Menlo", 10, "bold")).pack(pady=(0, 8))

    def update_status_color(self, *_args):
        """Green only when running, not for stopped or unverified states."""
        state = self.status.get().lower()
        if state.startswith("demo"):
            color = self.colors["highlight"]
        elif state.startswith("running") or state.startswith("ready") or state.startswith("connected"):
            color = self.colors["connected"]
        elif state.startswith("starting") or "recovery" in state:
            color = self.colors["highlight"]
        else:
            color = "#F28B82"
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.configure(fg=color)

    def draw_skyline_header(self, event=None):
        """New York after dark: vector-only, resize-safe command-center masthead."""
        canvas = self.header_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1000)
        height = 165
        orange = self.colors["highlight"]
        canvas.create_rectangle(0, 0, width, height, fill="#0D1018", outline="")
        # A dusk horizon and layered NYC silhouette, without external image assets.
        for y, shade in [(0, "#14111E"), (42, "#1F1623"), (84, "#2D1A20"),
                         (122, "#17151B")]:
            canvas.create_rectangle(0, y, width, y + 42, fill=shade, outline="")
        for n in range(42):
            x = (n * 89 + 17) % max(width, 1)
            top = 72 + (n * 37) % 55
            bw = 20 + (n * 11) % 23
            canvas.create_rectangle(x, top, x + bw, 155, fill="#090C13", outline="")
            for wy in range(top + 9, 148, 16):
                if (n + wy) % 3:
                    canvas.create_rectangle(x + 7, wy, x + 10, wy + 5,
                                            fill="#A85024", outline="")
        # Empire State Building silhouette and illuminated crown.
        tower = int(width * 0.73)
        canvas.create_rectangle(tower - 24, 48, tower + 24, 155,
                                fill="#0A0C12", outline="")
        canvas.create_polygon(tower - 30, 50, tower + 30, 50,
                              tower + 16, 33, tower - 16, 33, fill="#F28B32")
        canvas.create_rectangle(tower - 8, 15, tower + 8, 34,
                                fill="#F28B32", outline="")
        canvas.create_line(tower, 3, tower, 15, fill="#FFD49C", width=3)
        canvas.create_text(28, 22, anchor="nw", text="THE EMPIRE STATE",
                           fill="#F7F3ED", font=("Helvetica", 30, "bold"))
        canvas.create_text(29, 68, anchor="nw", text="B B S   /   COMMAND CENTER",
                           fill=orange, font=("Helvetica", 23, "bold"))
        canvas.create_text(30, 117, anchor="nw",
                           text="FROM THE FIVE BOROUGHS TO THE NORTH COUNTRY",
                           fill="#F4D7BF", font=("Menlo", 10, "bold"))
        canvas.create_text(width - 24, 120, anchor="ne",
                           text="62 COUNTIES  /  ONE NETWORK",
                           fill=orange, font=("Menlo", 10, "bold"))
        canvas.create_rectangle(0, 157, width, 162, fill=orange, outline="")

    def panel_heading(self, parent, title):
        tk.Label(parent, text=title, bg=self.colors["panel"],
                 fg=self.colors["highlight"], font=("Helvetica", 13, "bold")).pack(anchor="w", pady=(0, 8))

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
        search = tk.StringVar()
        search_row = tk.Frame(win, bg=THEME["background"])
        search_row.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(search_row, text="SEARCH LOCAL RECORDS", bg=THEME["background"],
                 fg=THEME["highlight"]).pack(side="left", padx=(0, 10))
        tk.Entry(search_row, textvariable=search, bg=THEME["panel"],
                 fg=THEME["text"], insertbackground=THEME["text"],
                 relief="flat").pack(side="left", fill="x", expand=True)
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
                            needle = search.get().strip().casefold()
                            if needle:
                                records = [record for record in records if any(
                                    needle in str(value).casefold() for value in record)]
                            if not records:
                                content.insert("end", "No matching local records among the latest 100.\\n")
                            for record in records:
                                for col, value in zip(columns, record):
                                    content.insert("end", f"{col}: {value}\\n")
                                content.insert("end", "─" * 55 + "\\n")
                except sqlite3.Error as exc:
                    content.insert("end", "Could not read local BBS data: " + str(exc))
            content.configure(state="disabled")
        search_row.bind("<Return>", lambda _event: refresh())
        self.styled_button(win, "SEARCH / REFRESH LOCAL RECORDS", refresh,
                           THEME["primary"]).pack(pady=10)
        refresh()

    def compose_local_mail_draft(self, draft_path=None):
        """Save an operator draft locally, never to the BBS mail database."""
        win = tk.Toplevel(self.root)
        win.title("The Grapevine | Local Draft")
        win.geometry("650x520")
        win.configure(bg=THEME["background"])
        tk.Label(win, text="NEW LOCAL MAIL DRAFT", bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 19, "bold")).pack(
                     anchor="w", padx=18, pady=(16, 6))
        tk.Label(win, text="Saved only on this Mac. Not sent over the mesh.",
                 bg=THEME["background"], fg=THEME["text"]).pack(
                     anchor="w", padx=18)
        fields = {}
        for name in ("Recipient node ID", "Subject"):
            tk.Label(win, text=name, bg=THEME["background"],
                     fg=THEME["highlight"]).pack(anchor="w", padx=18, pady=(12, 2))
            value = tk.StringVar()
            tk.Entry(win, textvariable=value, bg=THEME["panel"],
                     fg=THEME["text"], insertbackground=THEME["text"]).pack(
                         fill="x", padx=18)
            fields[name] = value
        tk.Label(win, text="Message", bg=THEME["background"],
                 fg=THEME["highlight"]).pack(anchor="w", padx=18, pady=(12, 2))
        body = tk.Text(win, height=9, bg=THEME["panel"], fg=THEME["text"],
                       insertbackground=THEME["text"], wrap="word")
        body.pack(fill="both", expand=True, padx=18)
        if draft_path is not None:
            try:
                saved = json.loads(draft_path.read_text(encoding="utf-8"))
                fields["Recipient node ID"].set(str(saved.get("recipient", "")))
                fields["Subject"].set(str(saved.get("subject", "")))
                body.insert("1.0", str(saved.get("message", "")))
            except (OSError, ValueError) as exc:
                messagebox.showerror("Draft error", str(exc), parent=win)
                win.destroy()
                return
        def save_draft():
            recipient = fields["Recipient node ID"].get().strip()
            subject = fields["Subject"].get().strip()
            message = body.get("1.0", "end-1c").strip()
            if not recipient or not subject or not message:
                messagebox.showerror("Draft incomplete",
                                     "Recipient, subject and message are required.",
                                     parent=win)
                return
            if not (recipient.startswith("!") and len(recipient) == 9
                    and all(c in "0123456789abcdefABCDEF" for c in recipient[1:])):
                messagebox.showerror("Invalid recipient",
                                     "Use a Meshtastic node ID such as !a1b2c3d4.",
                                     parent=win)
                return
            drafts = DATA / "drafts"
            drafts.mkdir(parents=True, exist_ok=True)
            import uuid
            draft = draft_path if draft_path is not None else drafts / (uuid.uuid4().hex + ".json")
            draft.write_text(json.dumps({"recipient": recipient,
                                         "subject": subject, "message": message},
                                        indent=2), encoding="utf-8")
            self.log("Saved a local mail draft; nothing was transmitted.")
            messagebox.showinfo("Draft saved", "Saved locally. No radio message sent.",
                                parent=win)
            win.destroy()
        self.styled_button(win, "SAVE LOCAL DRAFT (DO NOT SEND)", save_draft,
                           THEME["primary"]).pack(pady=12)

    def list_local_mail_drafts(self):
        """Browse and reopen local drafts without sending over the mesh."""
        folder = DATA / "drafts"
        win = tk.Toplevel(self.root)
        win.title("The Grapevine | Saved Drafts")
        win.geometry("630x400")
        win.configure(bg=THEME["background"])
        tk.Label(win, text="SAVED LOCAL DRAFTS", bg=THEME["background"],
                 fg=THEME["highlight"], font=("Helvetica", 18, "bold")).pack(
                     anchor="w", padx=18, pady=14)
        items = tk.Listbox(win, bg=THEME["panel"], fg=THEME["text"],
                           selectbackground=THEME["primary"])
        items.pack(fill="both", expand=True, padx=18, pady=6)
        paths = []
        def refresh():
            items.delete(0, "end")
            paths.clear()
            for path in sorted(folder.glob("*.json"), reverse=True) if folder.exists() else []:
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    label = "{} — {}".format(record.get("recipient", "?"),
                                             record.get("subject", "(no subject)"))
                except (OSError, ValueError):
                    continue
                paths.append(path)
                items.insert("end", label)
        def edit_selected():
            selected = items.curselection()
            if not selected:
                messagebox.showinfo("Select draft", "Choose a draft to edit.", parent=win)
                return
            self.compose_local_mail_draft(paths[selected[0]])
        def delete_selected():
            selected = items.curselection()
            if not selected:
                messagebox.showinfo("Select draft", "Choose a draft to delete.", parent=win)
                return
            path = paths[selected[0]]
            if not messagebox.askyesno("Delete local draft",
                                       "Permanently delete this local draft?\\n"
                                       "No mesh or BBS messages will be affected.",
                                       parent=win):
                return
            try:
                path.unlink()
            except OSError as exc:
                messagebox.showerror("Delete failed", str(exc), parent=win)
                return
            self.log("Deleted a local draft; no mesh message was changed.")
            refresh()
        def copy_selected():
            selected = items.curselection()
            if not selected:
                messagebox.showinfo("Select draft", "Choose a draft to copy.", parent=win)
                return
            try:
                record = json.loads(paths[selected[0]].read_text(encoding="utf-8"))
                payload = "Recipient: {}\\nSubject: {}\\n\\n{}".format(
                    record.get("recipient", ""), record.get("subject", ""),
                    record.get("message", ""))
                win.clipboard_clear()
                win.clipboard_append(payload)
                win.update()
            except (OSError, ValueError, tk.TclError) as exc:
                messagebox.showerror("Copy failed", str(exc), parent=win)
                return
            messagebox.showinfo("Copied locally",
                                "Draft copied to clipboard. Nothing was sent.",
                                parent=win)
        self.styled_button(win, "EDIT SELECTED DRAFT", edit_selected,
                           THEME["primary"]).pack(pady=8)
        self.styled_button(win, "COPY SELECTED DRAFT", copy_selected,
                           THEME["primary"]).pack(pady=(0, 8))
        self.styled_button(win, "DELETE SELECTED LOCAL DRAFT", delete_selected,
                           THEME["primary"]).pack(pady=(0, 8))
        self.styled_button(win, "REFRESH DRAFT LIST", refresh,
                           THEME["primary"]).pack(pady=(0, 10))
        refresh()

    def show_messages(self):
        open_posts(self, "mail")

    def show_bulletin(self):
        open_posts(self, "bulletin")

    def show_locals(self):
        open_nodes(self)

    def show_radio(self):
        """Navigate to existing controls without touching the active radio session."""
        self.root.deiconify()
        self.root.lift()
        self.connection_panel.configure(highlightbackground=self.colors["highlight"])
        self.connection_address.focus_set()
        self.refresh_radio_health()

    def refresh_radio_health(self):
        """Display only the state already observed by the running supervisor."""
        monitor = self.supervisor
        present = None
        if self.connection.get() == "serial" and self.address.get().strip() and self.last_serial_ports is not None:
            present = self.address.get().strip() in self.last_serial_ports
        self.radio_health.set(radio_health_label(self.demo.get(),
            bool(monitor and monitor.running), bool(monitor and monitor.ready),
            present, self.waiting_for_usb, monitor.radio_state if monitor else None))

    def show_about(self):
        messagebox.showinfo(
            "The Empire State BBS",
            "New York statewide Meshtastic BBS.\n"
            "From the Five Boroughs to the North Country.\n"
            "Demo mode never connects or transmits.\n\n"
            "Credits: Based on TC²-BBS by TheCommsChannel,\n"
            "with adaptations through The Sitdown BBS.\n"
            "Original contributors retain their credits.\n"
            "Licensed under GNU GPLv3. See README and LICENSE."
        )

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
        control = tk.Label(parent, text=text, bg=background, fg="#F5F1E9",
                           padx=12, pady=11, cursor="hand2",
                           font=("Helvetica", 10, "bold"), relief="flat",
                           highlightthickness=2, highlightbackground=self.colors["background"],
                           takefocus=True)
        control.bind("<Enter>", lambda _event: control.configure(bg=self.colors["highlight"], fg="#090B10"))
        control.bind("<Leave>", lambda _event: control.configure(bg=background, fg="#F5F1E9"))
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
        elif any(ord(c) < 32 or ord(c) == 127 for c in addr):
            return "Serial port contains invalid characters."
        return None

    def list_ports(self):
        try:
            ports = available_serial_ports()
            self.log("USB ports: " + (", ".join(ports) if ports else "None detected"))
            if len(ports) == 1 and self.connection.get() == "serial" and not self.address.get().strip():
                self.address.set(ports[0])
                self.log("Automatically selected the only available USB port.")
        except ImportError:
            self.log("pyserial is missing. Install requirements.txt.")
        except OSError as exc:
            self.log(f"USB enumeration failed: {exc}")

    def watch_serial_ports(self):
        """Observe USB changes without opening a port or interrupting a session."""
        if self.demo.get() or self.connection.get() != "serial":
            return
        try:
            ports = available_serial_ports()
        except (ImportError, OSError) as exc:
            if self.last_serial_ports is not None:
                self.log(f"USB scan unavailable: {exc}")
                self.last_serial_ports = None
            return
        previous = self.last_serial_ports
        self.last_serial_ports = tuple(ports)
        if previous is None:
            return
        added = sorted(set(ports) - set(previous))
        removed = sorted(set(previous) - set(ports))
        if added:
            self.log("USB attached: " + ", ".join(added))
        if removed:
            self.log("USB disconnected: " + ", ".join(removed))
        selected = self.address.get().strip()
        if selected and selected in removed:
            self.status.set("USB device removed — radio connection unverified")
            self.log("Selected USB radio disappeared; waiting for reconnect.")
            if self.auto_restart.get() and self.supervisor and self.supervisor.running:
                self.supervisor.stop()
                self.supervisor = None
                self.waiting_for_usb = True
                self.restart_at = None
                self.log("Stopped BBS; waiting for the same USB port to return.")
        if (self.waiting_for_usb and selected in added and
                self.auto_restart.get() and not self.demo.get() and
                not (self.supervisor and self.supervisor.running)):
            self.waiting_for_usb = False
            self.restart_at = time.monotonic() + 2
            self.log("USB port returned; scheduling restart in 2 seconds.")
        if (not selected and len(ports) == 1 and
                not (self.supervisor and self.supervisor.running)):
            self.address.set(ports[0])
            self.log("Auto-selected newly detected USB port: " + ports[0])

    def check_radio_target(self):
        """Non-transmitting preflight; does not prove a Meshtastic session."""
        if self.demo.get():
            messagebox.showinfo("Radio preflight", "Demo mode: no radio checks or transmissions.")
            return
        if self.supervisor and self.supervisor.running:
            messagebox.showinfo("Radio preflight", "Stop the BBS before preflight; a second TCP connection may disrupt the radio session.")
            return
        error = self.validate_radio_target()
        if error:
            messagebox.showerror("Radio preflight", error)
            return
        mode, address = self.connection.get(), self.address.get().strip()
        try:
            if mode == "serial":
                result = check_serial_target(address)
            else:
                result = check_tcp_target(address)
        except (OSError, ImportError) as exc:
            result = f"Radio preflight failed: {exc}"
        self.log(result)
        messagebox.showinfo("Radio preflight", result)

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
            self.supervisor = ServerSupervisor(cmd, DATA if getattr(sys, "frozen", False) else ROOT,
                                               env_overrides={"EMPIRE_ATTITUDE": self.attitude.get(),
                                                              "EMPIRE_DESKTOP_STORE": str(DATA / "desktop-state.db")})
            self.supervisor.start()
            self.status.set("Starting...")
            self.log("Starting The Empire State BBS...")
        except OSError as exc:
            self.supervisor = None
            self.status.set("Start failed")
            self.log(f"Start failed: {exc}")

    def poll(self):
        now = time.monotonic()
        if now - self.last_serial_scan >= 5.0:
            self.last_serial_scan = now
            self.watch_serial_ports()
        monitor = self.supervisor
        self.refresh_radio_health()
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
                if self.auto_restart.get() and not self.demo.get() and not self.waiting_for_usb:
                    self.retry_count += 1
                    delay = min(60, 2 ** min(self.retry_count, 6))
                    self.restart_at = time.monotonic() + delay
                    self.status.set(f"Radio unavailable — recovery in {delay}s (attempt {self.retry_count})")
                    self.log(f"Retrying process in {delay}s (attempt {self.retry_count}).")
                self.supervisor = None
        if self.restart_at is not None:
            if not self.auto_restart.get() or self.demo.get():
                self.restart_at = None
            elif time.monotonic() >= self.restart_at and not self.waiting_for_usb:
                self.restart_at = None
                self.start()
        if self.root.winfo_exists():
            self.root.after(500, self.poll)

    def stop(self):
        self.waiting_for_usb = False
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
        """Local-only preferences in a readable NYC command-center window."""
        win = tk.Toplevel(self.root)
        win.title("Control Room | Empire State BBS")
        win.geometry("680x540")
        win.minsize(560, 480)
        win.configure(bg=THEME["background"])
        tk.Label(win, text="CONTROL ROOM  /  SETTINGS",
                 bg=THEME["background"], fg=THEME["highlight"],
                 font=("Helvetica", 23, "bold")).pack(anchor="w", padx=24, pady=(24, 4))
        tk.Label(win, text="LOCAL PREFERENCES  •  CHANGES DO NOT TRANSMIT",
                 bg=THEME["background"], fg=THEME["text"],
                 font=("Menlo", 10)).pack(anchor="w", padx=24, pady=(0, 20))
        for name, var in [("COMMUNITY NAME", self.community),
                          ("WELCOME MESSAGE  /  LOCAL SETTING", self.welcome)]:
            tk.Label(win, text=name, bg=THEME["background"],
                     fg=THEME["highlight"], font=("Helvetica", 11, "bold")).pack(
                         anchor="w", padx=24, pady=(12, 5))
            tk.Entry(win, textvariable=var, width=55, bg=THEME["panel"],
                     fg=THEME["text"], insertbackground=THEME["text"],
                     relief="flat", font=("Helvetica", 12)).pack(
                         fill="x", padx=24, ipady=10)
        tk.Label(win, text="EMPIRE STATE ATTITUDE",
                 bg=THEME["background"], fg=THEME["highlight"],
                 font=("Helvetica", 12, "bold")).pack(anchor="w", padx=24, pady=(22, 8))
        for value, title in [("clean", "CLEAN  /  Classic New York (default)"),
                             ("spicy", "SPICY  /  A Little Mouthy"),
                             ("unfiltered", "UNCENSORED  /  Full New York Attitude")]:
            tk.Radiobutton(win, text=title, variable=self.attitude, value=value,
                           command=lambda v=value: self.set_attitude(v),
                           bg=THEME["background"], fg=THEME["text"],
                           selectcolor=THEME["panel"], anchor="w",
                           font=("Helvetica", 11)).pack(anchor="w", padx=24, pady=3)
        tk.Label(win, text="Local preview only. Radio reply integration is pending.",
                 bg=THEME["background"], fg=THEME["text"],
                 font=("Helvetica", 10)).pack(anchor="w", padx=24, pady=(12, 6))
        self.styled_button(win, "SAVE LOCAL SETTINGS", self.save,
                           THEME["primary"]).pack(anchor="w", padx=24, pady=12)

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
        app.show_messages()
        app.show_bulletin()
        app.show_locals()
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
