# THE EMPIRE STATE BBS

**New York State Communications Division**

*From the Adirondacks to the Atlantic. Everybody's connected.*

A statewide, old-school New York-themed edition of the Meshtastic bulletin board project, inspired by [THE SITDOWN BBS](https://github.com/BaconDisk22/The-Sitdown-BBS).

> **Project status:** A working Meshtastic BBS codebase and Intel Mac beta build workflows are present. The gold desktop dashboard and original skyline icon are implemented. Real-radio functionality and launch behavior on individual Macs still require device testing. [Releases](https://github.com/BaconDisk22/The-Empire-State-BBS/releases).

## Statewide identity

This project represents **all of New York State**, not just New York City: Western New York, the Finger Lakes, Central New York, the Southern Tier, the Capital Region, the North Country, the Mohawk Valley, the Hudson Valley, Long Island, and New York City.

### Visual direction

| Color | Hex |
| --- | --- |
| Empire navy | `#172C46` |
| Antique gold | `#C5A46D` |
| Vintage cream | `#F2E8D5` |
| Brick red | `#9C302C` |
| Adirondack green | `#36513D` |

## Implementation and next steps

- Preserve existing radio BBS behavior and compatibility.
- Replace New Jersey-specific names, messages, menus, and assets with statewide New York branding.
- Preserve Intel Mac x86_64 desktop build and DMG workflows, adapting app and artifact names.
- Preserve optional radio-free demo mode and automated README screenshot capture.
- Configure independent GitHub Actions, testing, and releases for this repository.
- Retain upstream attribution and GPLv3 licensing when source code is imported.


## Opening the app on macOS

After downloading the Intel Mac `.dmg` from [GitHub Releases](https://github.com/BaconDisk22/The-Empire-State-BBS/releases), install **The Empire State BBS** in Applications.

1. Open **Applications** in Finder.
2. **Control-click** **The Empire State BBS**.
3. Select **Open**, then **Open** again if prompted.
4. If macOS blocks it, check **System Settings → Privacy & Security → Open Anyway**.

These steps address macOS security prompts for an unsigned app. If the icon bounces in the Dock but no window appears, that may indicate a startup failure rather than a security block; report the issue instead of repeatedly overriding security warnings.

## Source and licensing

**The Empire State BBS** is an independently branded New York adaptation of [The Sitdown BBS](https://github.com/BaconDisk22/The-Sitdown-BBS), which is based on **TC²-BBS by TheCommsChannel**. Thank you to TheCommsChannel and the original contributors for the BBS foundation. Their work made this edition possible.\n\nThe original source credits and copyright notices remain in the source files. This project continues to be distributed under the **GNU General Public License v3.0**; see [LICENSE](LICENSE). New York-themed names, menus, artwork and desktop presentation are specific to this edition.

**The Sitdown BBS remains an independent New Jersey project.**

## Empire State gold dashboard

The Mac launcher uses a black-and-antique-gold statewide New York dashboard inspired by the approved design concept, with a matching original skyline app icon. Panels show actual process status, observed nodes, server logs, radio configuration and local attitude controls. The Grapevine and Bulletin shortcuts open the supported radio command guide; they are not separate message browsers yet. Demo mode never claims a live connection. The visual concept is not a screenshot of a working radio session.

## Build verification

The Intel Mac CI packages the app, checks x86_64 architecture and launches the **actual bundled executable** with `--smoke-test` to confirm Tk and the dashboard initialize. This catches packaging-related startup errors, but it does not replace testing a normal Finder launch on macOS Tahoe or a real Meshtastic device.
