# Desktop UI design system

The Intel Mac desktop app uses one window with a sidebar, built from a
single design system in [`empire_ui.py`](../empire_ui.py). The design loosely
follows Apple's Human Interface Guidelines (source-list sidebar, native menu
bar, sheets, native confirmation alerts) while keeping the Empire State
identity: charcoal surfaces, crown-orange accent and the skyline masthead.

Screenshots of every page, with labelled sample data, are in
[`docs/images/tour`](images/tour). To regenerate them on a Mac (Demo mode,
temporary data folder, nothing transmitted):

```sh
python scripts/capture_ui_tour.py --theme both --out docs/images/tour
```

## Structure

| Sidebar item | NYC name | Shortcut | What it does |
| --- | --- | --- | --- |
| Dashboard | Empire HQ | ⌘1 | Server status, start/stop, key metrics, activity log, quick links |
| Messages | The Grapevine | ⌘2 | Received messages and local drafts; compose, reply, send once |
| Bulletin | The Bulletin | ⌘3 | Local General-board posts and replies |
| Locals | Nodes heard | ⌘4 | Every node this Mac knows about, beyond the radio's ~100-node list, with search, time-range and source filters |
| Connection | The Empire Connection | ⌘5 | USB or network radio, test, server start/stop, demo and recovery options, troubleshooting |
| Radio commands | The Playbook | ⌘6 | Commands mesh users can DM the BBS, with copy buttons |
| Settings | Control Room | ⌘, | Community, personality, appearance, data and backups |
| About | — | — | Version, safety notes, credits, license |

The sidebar footer always shows the server state. ⌘N writes a new message or
post on the Messages and Bulletin pages; ⌘F focuses the Locals filter. The menu
bar has View, Server and Help menus. Keyboard shortcuts only navigate: they
never start or stop the server and never transmit.

## Tokens

* **Colour.** Two palettes (`_DARK`, `_LIGHT`) share the same semantic slots:
  `bg`, `surface`, `surface_alt`, `surface_sunken`, `border`, `text`,
  `text_muted`, `text_faint`, `accent`, and the tones `success`, `warning`,
  `danger` and `info`, each with a `*_soft` background. Every text colour
  meets WCAG AA (4.5:1) on every surface it is used on.
* **Type.** Roles `display`, `title`, `headline`, `body`, `body_strong`,
  `label`, `caption`, `overline` and `mono`, based on the system font. Settings
  › Appearance › Text size scales the whole ramp (90–130%).
* **Spacing.** A 4-pt scale: `xxs 2`, `xs 4`, `sm 8`, `md 12`, `lg 16`,
  `xl 24`, `xxl 32`.
* **Icons.** One glyph vocabulary in `ICON`. No image assets.
* **Tones.** `TONES` maps each state to a foreground, a soft background and an
  icon, so colour is never the only signal.

## Components

`Card`, `Button` (primary, secondary, ghost, danger, subtle_danger; hover,
pressed, focus ring, disabled), `Field` (label, help, inline error),
`text_area`, `Segmented`, `Toggle`, `StatusPill`, `Banner`, `Collapsible`,
`EmptyState`, `treeview`, `sheet`, `Toast` and `Tooltip`.

Buttons are focusable Labels because macOS Aqua ignores custom backgrounds on
native Tk buttons. ttk widgets use the `clam` theme so colours apply
consistently.

## Behaviour rules

* Pages are built once and swapped in place. Data pages poll the database only
  while visible: Messages every 1.5 s, Locals every 2 s.
* Tables update rows in place, which keeps selection and scroll position. The
  message detail pane redraws only when the record changes.
* Status is green only when the server is running. Stopped is neutral, and
  problems are red.
* Starting and recovery pulse the status dot, unless macOS Reduce Motion is on.
* Theme and text size apply immediately. The window is rebuilt, and the
  server, the log and the current page are preserved.
* Destructive or outward actions always confirm: sending, creating a retry
  draft, deleting a draft, and quitting while the server runs.
* The connection test runs off the UI thread, so a slow network never freezes
  the window.
