#!/usr/bin/env python3
"""Capture every page of the desktop app with clearly labelled sample data.

Runs in Demo mode against a temporary data folder: it never touches
~/.empire-state-bbs, never starts the server and never transmits.

    python scripts/capture_ui_tour.py [--theme dark|light|both] [--out docs/images/tour]
"""
import argparse
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sitdown_desktop  # noqa: E402
from desktop_session import DesktopStore  # noqa: E402

PAGES = ["home", "messages", "bulletin", "locals", "connection", "commands", "settings", "about"]


def seed(store, now):
    """Sample records, labelled as samples, for screenshots only."""
    store.create("mail", "Net check-in tonight", "SAMPLE DATA — Weekly net at 8 PM on LongFast. "
                 "Reply with your call sign and grid.", "!a1b2c3d4")
    store.create("bulletin", "Hudson Valley repeater maintenance", "SAMPLE DATA — The Beacon node "
                 "will be down Saturday morning for an antenna swap.", "")
    store.create("bulletin", "Welcome to the Empire State BBS", "SAMPLE DATA — Post local news here.", "")
    with store.connect() as db:
        db.execute("INSERT INTO received VALUES (?,?,?,?)",
                   ("s1", "!9c3e11aa", "SAMPLE DATA — Anyone copy from Albany?", now - 240))
        db.execute("UPDATE posts SET state='sent', detail='Submitted to local radio; RF delivery unverified' "
                   "WHERE subject='Net check-in tonight'")
        for node in [("!9c3e11aa", "Albany Rooftop (sample)", now - 240, 6.5, -92),
                     ("!4f20bb01", "Beacon Ridge (sample)", now - 600, -3.0, -111),
                     ("!77e1c0de", "Queens Mobile (sample)", now - 7200, None, None),
                     ("!0a0b0c0d", "Buffalo Base (sample)", now - 60, 9.25, -78)]:
            db.execute("INSERT INTO nodes VALUES (?,?,?,?,?)", node)


def capture(root, path):
    """Capture just the app window. macOS screencapture handles Retina scaling."""
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    if sys.platform == "darwin":
        subprocess.run(["screencapture", "-x", "-o", f"-R{x},{y},{w},{h}", str(path)], check=True)
    else:
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
    return w, h


def run(theme, out):
    with tempfile.TemporaryDirectory() as temp:
        data = Path(temp)
        sitdown_desktop.DATA = data
        sitdown_desktop.CONFIG = data / "launcher.json"
        sitdown_desktop.CONFIG.write_text('{"appearance": "%s", "connection": "tcp", '
                                          '"address": "meshtastic.local"}' % theme)
        root = tk.Tk()
        root.geometry("1280x840+40+40")
        app = sitdown_desktop.SitdownApp(root)
        app.store = DesktopStore(data / "desktop-state.db", data / "bulletins.db")
        seed(app.store, time.time())
        app.demo.set(True)
        app.start()
        app.node_count.set("Observed nodes: 4")
        app.log("SAMPLE DATA — screenshot tour; no radio connected, nothing transmitted")
        root.lift()
        root.attributes("-topmost", True)
        root.focus_force()
        for page in PAGES:
            app.navigate(page)
            if page == "messages":
                page_obj = app.page_objects["messages"]
                children = page_obj.listing.get_children()
                if children:
                    page_obj.listing.selection_set(children[0])
            for _ in range(8):
                root.update()
                time.sleep(0.08)
            size = capture(root, out / f"{page}-{theme}.png")
            print(f"{page}-{theme}.png {size[0]}x{size[1]}")
        root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", choices=["dark", "light", "both"], default="both")
    parser.add_argument("--out", default="docs/images/tour")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for theme in (["dark", "light"] if args.theme == "both" else [args.theme]):
        run(theme, out)


if __name__ == "__main__":
    main()
