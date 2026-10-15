# THE EMPIRE STATE BBS

**New York State Communications Division**

*From the Adirondacks to the Atlantic. Everybody's connected.*

A statewide, old-school New York-themed edition of the Meshtastic bulletin board project, inspired by [THE SITDOWN BBS](https://github.com/BaconDisk22/The-Sitdown-BBS).

> **Project status:** Initial repository setup. The functioning BBS and Intel Mac desktop application have **not yet been migrated**. Do not treat this repository as a working release yet.

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

## Planned migration

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

The working implementation will be adapted from [BaconDisk22/The-Sitdown-BBS](https://github.com/BaconDisk22/The-Sitdown-BBS), itself based on TC²-BBS. Preserve original copyright notices and GPLv3 license during migration.

**The Sitdown BBS remains an independent New Jersey project.**
