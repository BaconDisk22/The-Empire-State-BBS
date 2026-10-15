#!/usr/bin/env python3
"""Capture the actual Tk dashboard in safe demo mode on a macOS GUI runner."""
import sys
from pathlib import Path
import tkinter as tk
from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sitdown_desktop import SitdownApp

root = tk.Tk()
app = SitdownApp(root)
app.demo.set(True)
app.start()
app.log("DEMONSTRATION DATA — no radio connected")
app.log("The Social Club: example bulletin board")
app.log("A Word With You: sample mail")
app.log("The Backroom: example activity; no radio traffic transmitted")
root.update_idletasks()
root.lift()
root.focus_force()
root.update()
root.after(1800, root.quit)
root.mainloop()
root.update()
x, y = root.winfo_rootx(), root.winfo_rooty()
w, h = root.winfo_width(), root.winfo_height()
if w < 700 or h < 500:
    raise RuntimeError(f"Unexpected window size: {w}x{h}")
destination = Path("docs/images/desktop-preview-demo.png")
destination.parent.mkdir(parents=True, exist_ok=True)
image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
if image.width < 700:
    raise RuntimeError("Screenshot capture failed")
image.save(destination)
print(f"Saved real demo-mode screenshot: {destination}")
root.destroy()
