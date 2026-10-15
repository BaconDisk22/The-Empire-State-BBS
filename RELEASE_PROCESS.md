# Phase 4: Automated Intel Mac Releases

GitHub Actions now has two paths:

- **Intel Mac test build**: every push to `main` creates a downloadable workflow artifact for testing.
- **Publish Intel Mac Release**: on version tags matching `v*` or manual dispatch, builds an Intel x86_64 `.app`, wraps it in a versioned `.dmg`, computes `SHA256SUMS.txt`, and publishes both under **GitHub → Releases**.

## Publishing the first beta

1. Merge the Phase 4 pull request after CI checks pass.
2. Open **Actions → Publish Intel Mac Release → Run workflow**.
3. Select the **main** branch, enter `v0.1.0-beta.1` and click **Run workflow**.
4. Wait for the run to succeed, then open **Releases** and download `The-Sitdown-BBS-Intel-Mac-v0.1.0-beta.1.dmg`.

Alternatively push an annotated version tag to `main`; a matching tag automatically triggers the workflow. Use new versions for each new release.

**Warning:** Builds are unsigned and unnotarized. macOS Gatekeeper may ask for approval via System Settings → Privacy & Security. Never disable Gatekeeper globally. This pipeline does not verify physical Meshtastic radio behavior or provide an Apple Developer signature. The workflow uses `GITHUB_TOKEN` with `contents: write` and requires GitHub Actions to have permission to publish releases.
