"""Empire State BBS design system: tokens, theme and reusable Tk components.

Every colour, font, spacing value and widget recipe used by the desktop app
lives here so screens never hard-code styling. Standard library only.

Design notes
------------
* Two hand-tuned palettes (dark "after hours" and light "daylight") share one
  set of semantic slot names. Text colours meet WCAG AA (4.5:1) on the
  surfaces they are used on.
* State is never communicated by colour alone: every status carries an icon
  glyph and a word as well as a tone.
* Buttons are keyboard-focusable Labels because macOS Aqua ignores custom
  backgrounds on native Tk buttons (white-on-white text).
* Motion is limited to hover feedback and a gentle status pulse, and is
  switched off when macOS "Reduce motion" is enabled.
"""
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- tokens ---

# Primitive palette, named by what it is. Screens use the semantic slots below.
_DARK = {
    "bg": "#0E1015",            # window background
    "surface": "#171A21",       # cards, sidebar
    "surface_alt": "#1F232C",   # inputs, table rows, hover
    "surface_sunken": "#0A0C10",  # log, previews
    "border": "#2B303B",
    "border_strong": "#3A4150",
    "text": "#F2EFE9",
    "text_muted": "#A9ADB8",    # 7.6:1 on surface
    "text_faint": "#8A8F9D",    # captions only, >=4.5:1 on all surfaces
    "accent": "#FF8A3D",        # Empire State crown orange
    "accent_hover": "#FFA266",
    "accent_text": "#1A0D04",   # text placed on accent
    "accent_soft": "#3A2416",   # selected sidebar row / selection
    "success": "#4ADE80",
    "success_soft": "#13301F",
    "warning": "#FBBF24",
    "warning_soft": "#33280C",
    "danger": "#F87171",
    "danger_soft": "#3A1717",
    "danger_fill": "#B4362F",
    "info": "#7CB7FF",
    "info_soft": "#14263D",
    "focus": "#FFB27A",
    "log_text": "#9FE7B4",
    "sky_top": "#141826",
    "sky_bottom": "#2A1C22",
    "building": "#0B0D13",
    "window_light": "#B85A26",
}

_LIGHT = {
    "bg": "#F4F2EE",
    "surface": "#FFFFFF",
    "surface_alt": "#F0EDE8",
    "surface_sunken": "#F7F5F1",
    "border": "#DEDAD2",
    "border_strong": "#C6C0B5",
    "text": "#1B1D22",
    "text_muted": "#555A65",    # 7.0:1 on surface
    "text_faint": "#5F636D",    # >=4.5:1 on all surfaces
    "accent": "#A8440A",        # >=4.5:1 on all light surfaces
    "accent_hover": "#8F3907",
    "accent_text": "#FFFFFF",
    "accent_soft": "#FBE6D7",
    "success": "#126B33",
    "success_soft": "#DCF3E4",
    "warning": "#855000",
    "warning_soft": "#FBF0D3",
    "danger": "#B91C1C",
    "danger_soft": "#FBE1E1",
    "danger_fill": "#B91C1C",
    "info": "#1D5FB8",
    "info_soft": "#DFEAF9",
    "focus": "#A8440A",
    "log_text": "#1F5133",
    "sky_top": "#1A2033",
    "sky_bottom": "#3A2630",
    "building": "#0F121A",
    "window_light": "#D8752F",
}

# 4-pt spacing scale.
SPACE = {"xxs": 2, "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}

# Type ramp (role -> size, weight). Scaled by the user's text-size preference.
TYPE = {
    "display": (26, "bold"),
    "title": (20, "bold"),
    "headline": (15, "bold"),
    "body": (13, "normal"),
    "body_strong": (13, "bold"),
    "label": (12, "bold"),
    "caption": (11, "normal"),
    "overline": (10, "bold"),
    "mono": (12, "normal"),
    "mono_small": (11, "normal"),
}

TEXT_SCALES = {"small": 0.9, "default": 1.0, "large": 1.15, "xlarge": 1.3}
TEXT_SCALE_LABELS = [("small", "Small"), ("default", "Default"),
                     ("large", "Large"), ("xlarge", "Extra large")]
APPEARANCES = [("system", "Match macOS"), ("light", "Light"), ("dark", "Dark")]

# One icon vocabulary for the whole app (text glyphs; no image assets).
ICON = {
    "home": "⌂", "messages": "✉", "bulletin": "▤", "locals": "◉",
    "connection": "⇄", "commands": "⌘", "settings": "⚙", "about": "ⓘ",
    "start": "▶", "stop": "■", "search": "⌕", "check": "✓", "copy": "⧉",
    "warning": "▲", "error": "✕", "info": "ⓘ", "success": "✓", "dot": "●",
    "send": "➤", "reply": "↩", "new": "+", "more": "…", "refresh": "↻",
    "archive": "⬇", "folder": "▸", "back": "‹", "chevron": "›",
}

# Semantic tones -> (foreground slot, soft background slot, icon).
TONES = {
    "neutral": ("text_muted", "surface_alt", "dot"),
    "info": ("info", "info_soft", "info"),
    "success": ("success", "success_soft", "success"),
    "warning": ("warning", "warning_soft", "warning"),
    "danger": ("danger", "danger_soft", "error"),
    "accent": ("accent", "accent_soft", "dot"),
}


# ------------------------------------------------------------- platform ---

def _defaults_read(domain, key):
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(["defaults", "read", domain, key],
                                capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def system_prefers_dark():
    """macOS reports AppleInterfaceStyle=Dark only when dark mode is on."""
    if sys.platform != "darwin":
        return True  # the brand's native look; Linux CI and others
    return (_defaults_read("-g", "AppleInterfaceStyle") or "").lower() == "dark"


def system_reduce_motion():
    value = _defaults_read("com.apple.universalaccess", "reduceMotion")
    return value in ("1", "true", "YES")


# ---------------------------------------------------------------- theme ---

class Theme:
    """Resolved palette + fonts. Rebuild the UI after calling configure()."""

    def __init__(self, root, appearance="system", text_scale="default"):
        self.root = root
        self.reduce_motion = system_reduce_motion()
        self.fonts = {}
        self.configure(appearance, text_scale)

    def configure(self, appearance="system", text_scale="default"):
        self.appearance = appearance if appearance in dict(APPEARANCES) else "system"
        self.text_scale = text_scale if text_scale in TEXT_SCALES else "default"
        dark = (self.appearance == "dark" or
                (self.appearance == "system" and system_prefers_dark()))
        self.is_dark = dark
        self.c = dict(_DARK if dark else _LIGHT)
        self._build_fonts()
        self._style_ttk()

    def __getitem__(self, slot):
        return self.c[slot]

    def _build_fonts(self):
        try:
            family = tkfont.nametofont("TkDefaultFont").actual("family")
        except tk.TclError:
            family = "Helvetica"
        mono = "Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono"
        scale = TEXT_SCALES[self.text_scale]
        for role, (size, weight) in TYPE.items():
            fam = mono if role.startswith("mono") else family
            px = max(9, round(size * scale))
            if role in self.fonts:
                self.fonts[role].configure(family=fam, size=px, weight=weight)
            else:
                self.fonts[role] = tkfont.Font(root=self.root, family=fam,
                                               size=px, weight=weight)

    def font(self, role):
        return self.fonts[role]

    def row_height(self):
        return int(self.fonts["body"].metrics("linespace") * 2.1)

    def _style_ttk(self):
        c = self.c
        style = ttk.Style(self.root)
        try:
            # 'clam' honours custom colours on every platform (Aqua does not).
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Empire.Treeview", background=c["surface"],
                        fieldbackground=c["surface"], foreground=c["text"],
                        bordercolor=c["border"], lightcolor=c["surface"],
                        darkcolor=c["surface"], rowheight=self.row_height(),
                        font=self.fonts["body"], borderwidth=0)
        style.configure("Empire.Treeview.Heading", background=c["surface_alt"],
                        foreground=c["text_muted"], relief="flat",
                        bordercolor=c["border"], lightcolor=c["surface_alt"],
                        darkcolor=c["surface_alt"], font=self.fonts["label"],
                        padding=(SPACE["sm"], SPACE["sm"]))
        style.map("Empire.Treeview.Heading",
                  background=[("active", c["border"])])
        style.map("Empire.Treeview",
                  background=[("selected", c["accent_soft"])],
                  foreground=[("selected", c["text"])])
        style.layout("Empire.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"Empire.{orient}.TScrollbar", background=c["surface_alt"],
                            troughcolor=c["surface"], bordercolor=c["surface"],
                            arrowcolor=c["text_muted"], lightcolor=c["surface_alt"],
                            darkcolor=c["surface_alt"], gripcount=0)
            style.map(f"Empire.{orient}.TScrollbar",
                      background=[("active", c["border_strong"])])


# ----------------------------------------------------------- components ---

def frame(parent, theme, bg="bg", **kw):
    return tk.Frame(parent, bg=theme[bg], **kw)


def text(parent, theme, value="", role="body", fg="text", bg="bg", **kw):
    """Themed label. Pass textvariable= instead of value for live text."""
    if "textvariable" not in kw:
        kw["text"] = value
    kw.setdefault("anchor", "w")
    kw.setdefault("justify", "left")
    return tk.Label(parent, font=theme.font(role), fg=theme[fg], bg=theme[bg], **kw)


class Card(tk.Frame):
    """Surface with a 1-px border and consistent inner padding."""

    def __init__(self, parent, theme, padding="lg", bg="surface", **kw):
        super().__init__(parent, bg=theme[bg], highlightthickness=1,
                         highlightbackground=theme["border"],
                         highlightcolor=theme["border"], **kw)
        self.theme = theme
        self.body = tk.Frame(self, bg=theme[bg])
        self.body.pack(fill="both", expand=True, padx=SPACE[padding], pady=SPACE[padding])

    def emphasize(self, on=True):
        color = self.theme["accent"] if on else self.theme["border"]
        self.configure(highlightbackground=color, highlightcolor=color,
                       highlightthickness=2 if on else 1)


def section_header(parent, theme, title, subtitle=None, bg="surface", overline=None):
    box = tk.Frame(parent, bg=theme[bg])
    if overline:
        text(box, theme, overline.upper(), "overline", "accent", bg).pack(anchor="w")
    text(box, theme, title, "headline", "text", bg).pack(anchor="w")
    if subtitle:
        lbl = text(box, theme, subtitle, "caption", "text_muted", bg)
        lbl.pack(anchor="w", pady=(SPACE["xxs"], 0), fill="x")
        wrap_to_width(lbl)
    return box


def wrap_to_width(label, margin=4):
    """Re-wrap a label to its allocated width so text never clips."""
    if not int(label.cget("wraplength") or 0):
        label.configure(wraplength=360)  # modest request; grows to fit on <Configure>
    def on_configure(event):
        width = max(event.width - margin, 80)
        if abs(int(label.cget("wraplength") or 0) - width) > 8:
            label.configure(wraplength=width)
    label.bind("<Configure>", on_configure, add="+")
    return label


class Button(tk.Label):
    """Accessible button: hover, pressed, focus ring, disabled, keyboard."""

    VARIANTS = {
        # variant: (bg, fg, hover bg, hover fg)
        "primary": ("accent", "accent_text", "accent_hover", "accent_text"),
        "secondary": ("surface_alt", "text", "border", "text"),
        "ghost": (None, "text_muted", "surface_alt", "text"),
        "danger": ("danger_fill", "#FFFFFF", "danger", "#FFFFFF"),
        "subtle_danger": ("surface_alt", "danger", "danger_soft", "danger"),
    }

    def __init__(self, parent, theme, label, command, variant="secondary",
                 icon=None, size="md", bg="surface", tooltip=None, **kw):
        self.theme, self.command, self.variant = theme, command, variant
        self.parent_bg = theme[bg]
        self._enabled = True
        pad = {"sm": (SPACE["sm"], SPACE["xs"]), "md": (SPACE["md"], SPACE["sm"]),
               "lg": (SPACE["lg"], SPACE["md"])}[size]
        content = f"{ICON.get(icon, icon)}  {label}" if icon else label
        super().__init__(parent, text=content, cursor="hand2", takefocus=True,
                         padx=pad[0], pady=pad[1],
                         font=theme.font("label" if size != "lg" else "body_strong"),
                         highlightthickness=2, bd=0, **kw)
        self._paint(False)
        self.bind("<Enter>", lambda _e: self._paint(True))
        self.bind("<Leave>", lambda _e: self._paint(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", self._invoke)
        self.bind("<KP_Enter>", self._invoke)
        self.bind("<space>", self._invoke)
        self.bind("<FocusIn>", lambda _e: self.configure(highlightbackground=theme["focus"],
                                                         highlightcolor=theme["focus"]))
        self.bind("<FocusOut>", lambda _e: self._ring_off())
        self._ring_off()
        if tooltip:
            Tooltip(self, theme, tooltip)

    def _colors(self, hover):
        bg, fg, hbg, hfg = self.VARIANTS[self.variant]
        if hover:
            bg, fg = hbg, hfg
        resolve = (lambda v: self.parent_bg if v is None else
                   (self.theme[v] if v in self.theme.c else v))
        return resolve(bg), resolve(fg)

    def _paint(self, hover):
        if not self._enabled:
            self.configure(bg=self.theme["surface_alt"], fg=self.theme["text_faint"], cursor="arrow")
            return
        bg, fg = self._colors(hover)
        self.configure(bg=bg, fg=fg, cursor="hand2")

    def _ring_off(self):
        self.configure(highlightbackground=self.parent_bg, highlightcolor=self.parent_bg)

    def _press(self, _event):
        if self._enabled:
            bg, _fg = self._colors(True)
            self.configure(bg=self.theme["border_strong"] if self.variant in ("secondary", "ghost") else bg)

    def _release(self, event):
        if not self._enabled:
            return
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._paint(inside)
        if inside:
            self.command()

    def _invoke(self, _event=None):
        if self._enabled:
            self.command()
        return "break"

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.configure(takefocus=self._enabled)
        self._paint(False)

    def set_label(self, label, icon=None, variant=None):
        if variant:
            self.variant = variant
        self.configure(text=f"{ICON.get(icon, icon)}  {label}" if icon else label)
        self._paint(False)


class Tooltip:
    """Small delayed hint for icon-only or terse controls."""

    def __init__(self, widget, theme, message, delay=600):
        self.widget, self.theme, self.message, self.delay = widget, theme, message, delay
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self.job = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def _show(self):
        if self.tip or not self.widget.winfo_viewable():
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.message, bg=self.theme["text"], fg=self.theme["bg"],
                 font=self.theme.font("caption"), padx=8, pady=4,
                 wraplength=280, justify="left").pack()

    def _hide(self, _event=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


class StatusPill(tk.Frame):
    """Dot + word, coloured by tone. Never colour alone."""

    def __init__(self, parent, theme, label="", tone="neutral", bg="surface"):
        super().__init__(parent, bg=theme[bg])
        self.theme = theme
        self.dot = tk.Label(self, text=ICON["dot"], bg=theme[bg], font=theme.font("caption"))
        self.dot.pack(side="left")
        self.label = tk.Label(self, bg=theme[bg], font=theme.font("label"))
        self.label.pack(side="left", padx=(SPACE["xs"], 0))
        self._pulse_job = None
        self._pulse_on = True
        self.set(label, tone)

    def set(self, label, tone="neutral", pulse=False):
        fg = self.theme[TONES.get(tone, TONES["neutral"])[0]]
        self._fg = fg
        self.dot.configure(fg=fg)
        self.label.configure(text=label, fg=fg)
        self._stop_pulse()
        if pulse and not self.theme.reduce_motion:
            self._pulse()

    def _pulse(self):
        if not self.winfo_exists():
            return
        self._pulse_on = not self._pulse_on
        self.dot.configure(fg=self._fg if self._pulse_on else self.theme["border_strong"])
        self._pulse_job = self.after(650, self._pulse)

    def _stop_pulse(self):
        if self._pulse_job:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.dot.configure(fg=self._fg)


class Banner(tk.Frame):
    """Inline message with icon. Hidden when empty."""

    def __init__(self, parent, theme, bg="bg"):
        super().__init__(parent, bg=theme[bg])
        self.theme = theme
        self.inner = tk.Frame(self)
        self.inner.pack(fill="x")
        self.icon = tk.Label(self.inner, font=theme.font("body_strong"))
        self.icon.pack(side="left", padx=(SPACE["md"], SPACE["sm"]), pady=SPACE["sm"], anchor="n")
        self.msg = tk.Label(self.inner, font=theme.font("body"), justify="left", anchor="w")
        self.msg.pack(side="left", fill="x", expand=True, pady=SPACE["sm"], padx=(0, SPACE["md"]))
        wrap_to_width(self.msg)
        self._packed_kw = None
        self.tone = None

    def show(self, message, tone="info"):
        if not message:
            return self.clear()
        fg_slot, bg_slot, icon = TONES.get(tone, TONES["info"])
        bg, fg = self.theme[bg_slot], self.theme[fg_slot]
        self.tone = tone
        self.inner.configure(bg=bg)
        self.icon.configure(text=ICON[icon], bg=bg, fg=fg)
        self.msg.configure(text=message, bg=bg, fg=self.theme["text"])
        if self._packed_kw is not None and not self.winfo_ismapped():
            self.pack(**self._packed_kw)

    def clear(self):
        self.tone = None
        self.msg.configure(text="")
        if self.winfo_ismapped():
            self.pack_forget()

    def place_with(self, **pack_kw):
        """Remember pack options; the banner packs itself only when shown."""
        self._packed_kw = pack_kw

    def message(self):
        return self.msg.cget("text")


class Field(tk.Frame):
    """Label + input + help text + inline error."""

    def __init__(self, parent, theme, label, variable=None, help_text=None,
                 bg="surface", width=None):
        super().__init__(parent, bg=theme[bg])
        self.theme = theme
        text(self, theme, label, "label", "text", bg).pack(anchor="w")
        self.border = tk.Frame(self, bg=theme["border_strong"], padx=1, pady=1)
        self.border.pack(fill="x", pady=(SPACE["xs"], 0))
        self.variable = variable if variable is not None else tk.StringVar()
        well = tk.Frame(self.border, bg=theme["surface_alt"])
        well.pack(fill="x")
        self.entry = tk.Entry(well, textvariable=self.variable, relief="flat", bd=0,
                              bg=theme["surface_alt"], fg=theme["text"],
                              insertbackground=theme["text"], font=theme.font("body"),
                              highlightthickness=0, selectbackground=theme["accent_soft"],
                              selectforeground=theme["text"], **({"width": width} if width else {}))
        self.entry.pack(fill="x", ipady=SPACE["sm"], padx=SPACE["sm"])
        self.entry.bind("<FocusIn>", lambda _e: self._ring(True), add="+")
        self.entry.bind("<FocusOut>", lambda _e: self._ring(False), add="+")
        self.help = text(self, theme, help_text or "", "caption", "text_muted", bg)
        if help_text:
            self.help.pack(anchor="w", pady=(SPACE["xs"], 0), fill="x")
            wrap_to_width(self.help)
        self.error = text(self, theme, "", "caption", "danger", bg)
        self._error_on = False

    def _ring(self, focused):
        if self._error_on:
            return
        self.border.configure(bg=self.theme["focus"] if focused else self.theme["border_strong"])

    def value(self):
        return self.variable.get()

    def set_help(self, message):
        self.help.configure(text=message)

    def set_error(self, message):
        self._error_on = bool(message)
        self.error.configure(text=(ICON["error"] + "  " + message) if message else "")
        if message:
            self.border.configure(bg=self.theme["danger"])
            if not self.error.winfo_ismapped():
                self.error.pack(anchor="w", pady=(SPACE["xs"], 0))
        else:
            try:
                focused = self.focus_get() is self.entry
            except (KeyError, tk.TclError):
                focused = False
            self._ring(focused)
            self.error.pack_forget()


def text_area(parent, theme, height=8, bg_slot="surface_alt", role="body", **kw):
    """Bordered multi-line Text with a themed scrollbar."""
    border = tk.Frame(parent, bg=theme["border_strong"], padx=1, pady=1)
    inner = tk.Frame(border, bg=theme[bg_slot])
    inner.pack(fill="both", expand=True)
    widget = tk.Text(inner, height=height, wrap="word", relief="flat", bd=0,
                     bg=theme[bg_slot], fg=theme["text"], insertbackground=theme["text"],
                     font=theme.font(role), padx=SPACE["md"], pady=SPACE["sm"],
                     highlightthickness=0, selectbackground=theme["accent_soft"],
                     selectforeground=theme["text"], **kw)
    bar = ttk.Scrollbar(inner, orient="vertical", command=widget.yview,
                        style="Empire.Vertical.TScrollbar")
    widget.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    widget.pack(side="left", fill="both", expand=True)
    widget.bind("<FocusIn>", lambda _e: border.configure(bg=theme["focus"]), add="+")
    widget.bind("<FocusOut>", lambda _e: border.configure(bg=theme["border_strong"]), add="+")
    return border, widget


class Segmented(tk.Frame):
    """Segmented control bound to a StringVar; arrow keys move selection."""

    def __init__(self, parent, theme, variable, options, command=None, bg="surface"):
        super().__init__(parent, bg=theme["border"], padx=1, pady=1, takefocus=True,
                         highlightthickness=2, highlightbackground=theme[bg],
                         highlightcolor=theme["focus"])
        self.theme, self.variable, self.command = theme, variable, command
        self.options = options
        self.cells = {}
        for index, (value, label) in enumerate(options):
            cell = tk.Label(self, text=label, font=theme.font("label"), cursor="hand2",
                            padx=SPACE["md"], pady=SPACE["sm"])
            cell.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 1, 0))
            self.columnconfigure(index, weight=1)
            cell.bind("<Button-1>", lambda _e, v=value: self.choose(v))
            self.cells[value] = cell
        self.bind("<Left>", lambda _e: self._step(-1))
        self.bind("<Right>", lambda _e: self._step(1))
        self.bind("<FocusIn>", lambda _e: self.configure(highlightbackground=theme["focus"]))
        self.bind("<FocusOut>", lambda _e: self.configure(highlightbackground=theme[bg]))
        self._trace = variable.trace_add("write", lambda *_a: self.paint())
        self.bind("<Destroy>", self._untrace, add="+")
        self.paint()

    def _untrace(self, event):
        if event.widget is self:
            try:
                self.variable.trace_remove("write", self._trace)
            except tk.TclError:
                pass

    def _step(self, delta):
        values = [v for v, _ in self.options]
        current = self.variable.get()
        index = values.index(current) if current in values else 0
        self.choose(values[(index + delta) % len(values)])

    def choose(self, value):
        if self.variable.get() != value:
            self.variable.set(value)
            if self.command:
                self.command(value)
        self.paint()

    def paint(self):
        if not self.winfo_exists():
            return
        current = self.variable.get()
        for value, cell in self.cells.items():
            on = value == current
            cell.configure(bg=self.theme["accent"] if on else self.theme["surface_alt"],
                           fg=self.theme["accent_text"] if on else self.theme["text_muted"])


class Toggle(tk.Frame):
    """Switch row: title, description, on/off switch drawn on a Canvas."""

    def __init__(self, parent, theme, title, variable, description=None,
                 command=None, bg="surface"):
        super().__init__(parent, bg=theme[bg], takefocus=True, highlightthickness=2,
                         highlightbackground=theme[bg], highlightcolor=theme["focus"])
        self.theme, self.variable, self.command, self.bg = theme, variable, command, bg
        # Pack the switch first so a long description can never push it out of view.
        self.switch = tk.Canvas(self, width=44, height=26, bg=theme[bg],
                                highlightthickness=0, cursor="hand2")
        self.switch.pack(side="right", padx=SPACE["xs"], pady=SPACE["xs"], anchor="n")
        self.state_word = tk.Label(self, font=theme.font("caption"), bg=theme[bg], width=3)
        self.state_word.pack(side="right", anchor="n", pady=SPACE["xs"])
        words = tk.Frame(self, bg=theme[bg])
        words.pack(side="left", fill="x", expand=True, padx=(SPACE["xs"], SPACE["md"]))
        text(words, theme, title, "body_strong", "text", bg).pack(anchor="w")
        if description:
            desc = text(words, theme, description, "caption", "text_muted", bg, wraplength=320)
            wrap_to_width(desc).pack(anchor="w", fill="x", pady=(SPACE["xxs"], 0))
        for widget in (self, self.switch):
            widget.bind("<Button-1>", lambda _e: self.toggle())
        self.bind("<space>", lambda _e: self.toggle())
        self.bind("<Return>", lambda _e: self.toggle())
        self.bind("<FocusIn>", lambda _e: self.configure(highlightbackground=theme["focus"]))
        self.bind("<FocusOut>", lambda _e: self.configure(highlightbackground=theme[bg]))
        self._trace = variable.trace_add("write", lambda *_a: self.paint())
        self.bind("<Destroy>", self._untrace, add="+")
        self.paint()

    def _untrace(self, event):
        if event.widget is self:
            try:
                self.variable.trace_remove("write", self._trace)
            except tk.TclError:
                pass

    def toggle(self):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command(self.variable.get())

    def paint(self):
        if not self.winfo_exists():
            return
        on = bool(self.variable.get())
        c = self.switch
        c.delete("all")
        track = self.theme["accent"] if on else self.theme["border_strong"]
        c.create_oval(1, 1, 25, 25, fill=track, outline=track)
        c.create_oval(19, 1, 43, 25, fill=track, outline=track)
        c.create_rectangle(13, 1, 31, 25, fill=track, outline=track)
        knob_x = 21 if on else 3
        c.create_oval(knob_x, 3, knob_x + 20, 23, fill="#FFFFFF", outline="")
        self.state_word.configure(text="On" if on else "Off",
                                  fg=self.theme["text"] if on else self.theme["text_faint"])


class Collapsible(tk.Frame):
    """Progressive disclosure: a header button that reveals a body frame."""

    def __init__(self, parent, theme, title, bg="surface", opened=False):
        super().__init__(parent, bg=theme[bg])
        self.theme = theme
        self.title = title
        self.opened = opened
        self.header = tk.Label(self, font=theme.font("label"), fg=theme["accent"],
                               bg=theme[bg], cursor="hand2", takefocus=True, anchor="w",
                               highlightthickness=2, highlightbackground=theme[bg],
                               highlightcolor=theme["focus"])
        self.header.pack(anchor="w", fill="x")
        self.body = tk.Frame(self, bg=theme[bg])
        for seq in ("<Button-1>", "<Return>", "<space>"):
            self.header.bind(seq, lambda _e: self.set(not self.opened))
        self.header.bind("<FocusIn>", lambda _e: self.header.configure(highlightbackground=theme["focus"]))
        self.header.bind("<FocusOut>", lambda _e: self.header.configure(highlightbackground=theme[bg]))
        self.set(opened)

    def set(self, opened):
        self.opened = opened
        self.header.configure(text=("▾  " if opened else "▸  ") + self.title)
        if opened:
            self.body.pack(fill="x", pady=(SPACE["sm"], 0))
        else:
            self.body.pack_forget()


class EmptyState(tk.Frame):
    """Centred icon, headline, explanation and optional action."""

    def __init__(self, parent, theme, icon, title, message, action=None, bg="surface"):
        super().__init__(parent, bg=theme[bg])
        inner = tk.Frame(self, bg=theme[bg])
        inner.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(inner, text=ICON.get(icon, icon), font=theme.font("display"),
                 fg=theme["text_faint"], bg=theme[bg]).pack()
        tk.Label(inner, text=title, font=theme.font("headline"), fg=theme["text"],
                 bg=theme[bg]).pack(pady=(SPACE["sm"], SPACE["xs"]))
        tk.Label(inner, text=message, font=theme.font("body"), fg=theme["text_muted"],
                 bg=theme[bg], wraplength=420, justify="center").pack()
        if action:
            label, command, icon_name = action
            Button(inner, theme, label, command, "primary", icon_name, bg=bg).pack(pady=(SPACE["lg"], 0))


def treeview(parent, theme, columns, height=10):
    """Themed table with scrollbar inside a bordered surface. Returns (frame, tree)."""
    box = tk.Frame(parent, bg=theme["border"], padx=1, pady=1)
    inner = tk.Frame(box, bg=theme["surface"])
    inner.pack(fill="both", expand=True)
    tree = ttk.Treeview(inner, columns=[c[0] for c in columns], show="headings",
                        height=height, style="Empire.Treeview", selectmode="browse")
    for key, label, width, stretch in columns:
        tree.heading(key, text=label, anchor="w")
        tree.column(key, width=width, minwidth=70, stretch=stretch, anchor="w")
    bar = ttk.Scrollbar(inner, orient="vertical", command=tree.yview,
                        style="Empire.Vertical.TScrollbar")
    tree.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)
    tree.tag_configure("odd", background=theme["surface"])
    tree.tag_configure("even", background=theme["surface_sunken"] if theme.is_dark else theme["surface_alt"])
    for tone, (fg, _bg, _icon) in TONES.items():
        tree.tag_configure("tone-" + tone, foreground=theme[fg])
    return box, tree


def sheet(app_root, theme, title, width=620, height=560, parent=None):
    """A dialog window attached to its parent (macOS sheet-like behaviour)."""
    owner = parent or app_root
    win = tk.Toplevel(owner)
    win.withdraw()
    win.title(title)
    win.configure(bg=theme["bg"])
    win.minsize(min(width, 480), min(height, 360))
    try:
        win.transient(owner.winfo_toplevel())
    except tk.TclError:
        pass
    owner.update_idletasks()
    try:
        x = owner.winfo_rootx() + max((owner.winfo_width() - width) // 2, 20)
        y = owner.winfo_rooty() + 60
        win.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError:
        win.geometry(f"{width}x{height}")
    win.bind("<Escape>", lambda _e: win.destroy())
    win.bind("<Command-w>", lambda _e: win.destroy())
    win.deiconify()
    return win


class Toast:
    """Transient confirmation anchored to the bottom of a window."""

    def __init__(self, root, theme):
        self.root, self.theme = root, theme
        self.frame = None
        self.job = None

    def show(self, message, tone="success", duration=3200):
        self.hide()
        fg_slot, _bg_slot, icon = TONES.get(tone, TONES["success"])
        c = self.theme
        self.frame = tk.Frame(self.root, bg=c["text"] if c.is_dark else "#1B1D22",
                              padx=SPACE["lg"], pady=SPACE["sm"])
        bg = self.frame.cget("bg")
        tk.Label(self.frame, text=ICON[icon], bg=bg, fg=_toast_fg(c, fg_slot),
                 font=c.font("body_strong")).pack(side="left", padx=(0, SPACE["sm"]))
        tk.Label(self.frame, text=message, bg=bg, fg=c["bg"] if c.is_dark else "#FFFFFF",
                 font=c.font("body"), wraplength=520, justify="left").pack(side="left")
        self.frame.place(relx=0.5, rely=1.0, y=-SPACE["xl"], anchor="s")
        self.frame.lift()
        self.job = self.root.after(duration, self.hide)

    def hide(self):
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.frame is not None:
            try:
                self.frame.destroy()
            except tk.TclError:
                pass
            self.frame = None


def _toast_fg(theme, slot):
    # Toast surface inverts the theme, so use the opposite palette's tone colour.
    other = _LIGHT if theme.is_dark else _DARK
    return other[slot]


def humanize_seconds(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"
