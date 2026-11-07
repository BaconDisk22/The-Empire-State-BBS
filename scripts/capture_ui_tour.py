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



def seed_nodes(directory, now):
    """Sample node list, labelled as samples; one node is 'dropped' from the radio's list."""
    def node(num, short, long, ago, snr=None, **extra):
        return {'num': num, 'user': {'id': f'!{num:08x}', 'shortName': short, 'longName': long + ' (sample)',
                                     'hwModel': extra.pop('hw', '')}, 'lastHeard': int(now - ago), 'snr': snr, **extra}
    clock = directory.clock
    directory.clock = lambda: now - 3600
    directory.record_radio([node(0x77e1c0de, 'QNS', 'Queens Mobile', 7200, None, hw='T_ECHO')])
    directory.clock = lambda: now
    directory.record_radio([
        node(0x9c3e11aa, 'ALB', 'Albany Rooftop', 240, 6.5, hw='HELTEC_V3', hopsAway=0,
             deviceMetrics={'batteryLevel': 100}),
        node(0x4f20bb01, 'BCN', 'Beacon Ridge', 600, -3.0, hw='RAK4631', hopsAway=2),
        node(0x0a0b0c0d, 'BUF', 'Buffalo Base', 60, 9.25, hw='STATION_G2', hopsAway=1,
             deviceMetrics={'batteryLevel': 76}),
    ])
    directory.record_packet({'from': 0x9c3e11aa, 'rxSnr': 6.5, 'rxRssi': -92, 'hopStart': 3, 'hopLimit': 3})
    directory.clock = clock


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
        seed_nodes(app.node_directory, time.time())
        app.radio_node_count = 3
        app.refresh_node_count()
        app.demo.set(True)
        app.start()
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
