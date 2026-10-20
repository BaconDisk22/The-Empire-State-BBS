# Intel Mac beta release process

The repository has two GitHub Actions workflows:

- **Intel Mac test build** runs on pushes to `main` and produces a test artifact.
- **Publish Intel Mac Release** builds an x86_64 Mac app and versioned DMG, generates `SHA256SUMS.txt`, and publishes both to GitHub Releases on a version tag (`v*`) or manual workflow dispatch.

## Publish beta.3

1. Merge only reviewed pull requests with successful CI.
2. Open **Actions → Publish Intel Mac Release → Run workflow**.
3. Select `main`, enter `v0.1.0-beta.3`, and run the workflow. Do not reuse a published tag.
4. Confirm the workflow **succeeded** and the GitHub release contains both `The-Empire-State-BBS-Intel-Mac-v0.1.0-beta.3.dmg` and `SHA256SUMS.txt`.
5. Verify the DMG's SHA256 matches `SHA256SUMS.txt` before distributing it. Check the downloadable application launches from Finder on an Intel Mac.

## Hardware smoke-test checklist

- Launch and quit the desktop app.
- Configure TCP connection to the user's own Meshtastic host (do not embed a private IP in releases).
- Start BBS and verify a local protocol response; do not interpret this as RF message delivery.
- Disconnect and reconnect TCP; verify status transitions and recovery without automatic mail retransmission.
- Open The Empire Connection (no modal), Grapevine, Bulletin and The Locals.
- Create a local draft and local Bulletin post/reply. Check persisted state after restart.
- Explicitly send a message only if the operator intentionally chooses a valid individual recipient and accepts that actual RF delivery may remain unverified.

## Safety and release limits

Builds are **unsigned and unnotarized**. If macOS Gatekeeper blocks launch, use the normal **System Settings → Privacy & Security** per-app approval. Never disable Gatekeeper globally.

Mock tests and successful local TCP checks do **not** demonstrate remote RF receipt, delivery acknowledgements, or successful testing with a second radio. Record those as unverified until actual hardware testing is completed. The release workflow requires a token with `contents: write` permission.
