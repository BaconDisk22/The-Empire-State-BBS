# The Sitdown BBS desktop preview

This is an **initial functional desktop launcher**, not a completed macOS app release.

## Run locally

Install Python 3 with Tkinter and dependencies from `requirements.txt`.
Copy `example_config.ini` to `config.ini`, configure your BBS, then run:

```sh
python sitdown_desktop.py
```

Use **Demo mode** to explore the UI without connecting a radio. The radio Start/Stop buttons launch and terminate the existing `server.py` process with serial or TCP arguments. This does not modify upstream BBS behavior.

**Current limitations:** Server output is not streamed into the GUI; 'Server running' means the process is alive, **not** that the radio is connected. Custom welcome text is saved locally but not yet served over radio. Backup creates a ZIP; restore is not implemented. The desktop launcher is not yet packaged as a signed, click-to-open Mac app.

Radio commands supported by this fork are in `SITDOWN_COMMANDS.md`. UI colors are charcoal, Italian red and green, off-white, and diner gold—not the Joker palette.

Do not share `config.ini` or backups publicly. Preserve upstream GPLv3 licensing and acknowledgements.
