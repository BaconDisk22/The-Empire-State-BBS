# Intel Mac test builds

Every push to `main`, pull request, or manual workflow dispatch runs **Intel Mac test build** on GitHub's `macos-15-intel` runner.

1. Open **Actions** → **Intel Mac test build**.
2. Select a **successful** run.
3. Under **Artifacts**, download **The-Sitdown-BBS-Intel-Mac-Test**.
4. Unzip the artifact and open `The-Sitdown-BBS-Intel-Test.dmg`.
5. Drag the app to Applications.

The DMG is an **unsigned, unnotarized development test build**, not a stable release. macOS Gatekeeper may block it; only approve a build you trust through System Settings → Privacy & Security. Do not disable Gatekeeper globally.

The bundled app creates a user-editable radio configuration at `~/.sitdown-bbs/config.ini` on first non-demo launch. Review it before connecting a radio. Demo mode does not require a radio. Radio connectivity and macOS Tahoe compatibility must still be tested on physical hardware.

Build artifacts expire after **14 days**. This workflow does not publish GitHub Releases and does not require an Apple Developer signing certificate.
