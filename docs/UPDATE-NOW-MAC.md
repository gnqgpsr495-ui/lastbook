# Update now on a Mac (Sparkle 2)

About shows **Update now** only on a Mac build that carries a pinned `Sparkle.framework` and the update public key. On every
other build (Windows, Linux, a default Mac build, or a Mac build whose Sparkle setup is incomplete or fails to start), About shows
**Open download page** instead. That button only opens `https://lastbook.org/download/` in the browser.

## How it works

| Step | Where | What happens |
|---|---|---|
| Launch | `app/shell_macos.py` `_configure_update_now` | Reads `Info.plist` and looks for the framework file. Loads no Sparkle code and makes no request. |
| Check | `engine/update.py` (unchanged) | The person's own check, or the opt-in daily notice, decides whether a newer version exists. |
| Click | `POST /api/update/now` → `update_macos.Native.begin` | Takes nothing from the request. It refuses unless the build is trusted and a newer version is known. |
| Sparkle | `update_macos._start`, main thread | Loads the framework from inside the app, starts one updater and makes one user-initiated check. |
| Install | Sparkle | Sparkle asks the person to confirm in its own window. It verifies the signed appcast and the EdDSA signature on the archive (before extraction), replaces `Lastbook.app` only, and relaunches. |

The Lastbook > Check for Updates… menu item still opens About and runs the same website check as before. It never starts Sparkle.

### Fails closed

`update_macos.problem` and `scan_package_macos.py` (which runs at build time) enforce the same rules:

- These `Info.plist` values must be exactly:
  - `SUFeedURL = https://downloads.lastbook.org/mac/appcast.xml`
  - `SUEnableAutomaticChecks`, `SUAllowsAutomaticUpdates`, `SUAutomaticallyUpdate`, `SUEnableSystemProfiling` and `SUShowReleaseNotes` all `NO`
  - `SUVerifyUpdateBeforeExtraction` and `SURequireSignedFeed` both `YES`
  - `SUSignedFeedFailureExpirationInterval = 0` (integer). Sparkle's default accepts a feed that fails validation after 20 days; 0 never does.
  - `CFBundleVersion` equal to `CFBundleShortVersionString` (Sparkle compares `CFBundleVersion`)
  - `CFBundleIdentifier = local.lastbook.desktop`
- `SUPublicEDKey` must be a 32-byte Ed25519 public key.
- None of `SUScheduledCheckInterval`, `SUEnableInstallerLauncherService` or `SUEnableDownloaderService` may be set.
- The framework's XPC services must be absent.
- Sparkle's MIT license must ship as `Contents/Resources/LICENSE-Sparkle.txt`.

The Sparkle delegate refuses:

- every check except a user-initiated one (`SPUUpdateCheckUpdates`)
- installer packages and information-only items
- an archive whose URL is not exactly `https://downloads.lastbook.org/...` (no other scheme, host, port, or credentials). The GitHub pin is for the source dependency only; no update is fetched from GitHub.
- release-notes downloads
- feed parameters, and `_start` also calls `setSendsSystemProfile_(False)` so an old `SUSendProfileInfo` user default cannot turn profiling on
- any feed URL other than the one above

## Build

The default build has no Sparkle. Set both of these variables, or neither:

```
LASTBOOK_SPARKLE_ARCHIVE=/path/to/Sparkle-<version>.tar.xz \
LASTBOOK_SPARKLE_PUBLIC_ED_KEY=<base64 public key from generate_keys> \
bash packaging/build_app_macos.sh
```

`packaging/sparkle_framework.py` handles the framework:

1. Checks the archive name and SHA-256 against `packaging/sparkle.lock.json`.
2. Takes only `Sparkle.framework` out of the archive (tar `data` filter) and removes its XPC services.
3. Thins it to arm64.
4. Copies Sparkle's `LICENSE` to `Contents/Resources/LICENSE-Sparkle.txt` and sets `CFBundleVersion` from the spec's single `version=` (`CFBundleShortVersionString`), so the version bump step stays one literal.
5. Ad-hoc re-signs `Autoupdate`, then `Updater.app`, then the framework, then the app.

It never downloads. Fetch the official archive by hand and pin it first.

## Release dependencies (not done here)

1. **Sparkle 2.10.1 is pinned** in `sparkle.lock.json` (SHA-256 `1a856d2a…4cf27`, checked against the GitHub asset metadata and the downloaded bytes). Its LICENSE ships in the app.
2. **Update key**: run Sparkle's `generate_keys` on the release machine. The private key stays in that Keychain. Only the public key goes into the build.
3. **Developer ID signing and notarization** of the whole app. The existing production signing script signs Mach-O leaves and then the top-level app only. That is not enough for Sparkle: after the leaves, re-sign bottom-up, each with the Developer ID identity, `--options runtime` and a timestamp: `Sparkle.framework/Versions/B/Autoupdate`, then `Sparkle.framework/Versions/B/Updater.app`, then `Sparkle.framework`, then `Lastbook.app` last. Do not use `--deep`. Check with `codesign --verify --deep --strict` and `spctl -a -vv`. This task did not touch production keys, and no signed release or install has been proven. Today's builds are ad-hoc only. Sparkle's code-signing continuity checks and Gatekeeper are only meaningful with a real identity. Do not ship Update now from ad-hoc builds.
4. **Appcast**: a signed appcast at `https://downloads.lastbook.org/mac/appcast.xml`, made by `generate_appcast`. It must have no `sparkle:releaseNotesLink`, no `.pkg`, and no `sparkle:informationalUpdate`. Each archive must be a signed `.zip`, `.tar.*` or `.dmg` of `Lastbook.app` with the same bundle ID.
5. Keep `app-v1.json` in step with the appcast. Update now appears only after that check finds a newer version.
6. Optional, once Sparkle 2.11 is stable: `SURequireFeedBundleIdentifier`.

## Staging (test-only artifacts, disposable macOS VM)

Do this only in a throwaway VM, never on a machine with a real Lastbook install or library. The feed address is fixed in the
product, so the VM points `downloads.lastbook.org` at a local server instead.

1. **Keys.** In the VM, run `generate_keys --account lastbook-staging` and note the public key. This staging key is never used for release.
2. **Two builds.** Build 1.1.15 and 1.1.16. Change `version=` in the spec in a scratch copy, and set the staging key and the pinned archive on both.
3. **Archive and appcast.** Zip 1.1.16 with `ditto -c -k --keepParent Lastbook.app Lastbook-1.1.16.zip`. Then run `generate_appcast --account lastbook-staging <dir>` and confirm the appcast is signed.
4. **Server.** Serve the appcast as `/mac/appcast.xml`, the zip, and an `app-v1.json` announcing `1.1.16` over HTTPS. Use a test CA trusted only in the VM, and map `downloads.lastbook.org` to the server in the VM's `/etc/hosts`.
5. **Expected results.** Open 1.1.15 and check:
   - No request reaches the server until About → Check for updates → Update now (watch the server log).
   - Sparkle asks before installing, then relaunches into 1.1.16.
   - The library and settings are unchanged.
6. **Negative cases.** Each of these must end in a Sparkle error and no install:
   - Flip one byte in the zip.
   - Re-sign the appcast with another key.
   - Serve an unsigned appcast.
   - Serve a `.pkg`.

   Separately, a build without the key or the framework must show only **Open download page**.

## Tests

```
python3 app/tests/test_update.py
derived/app-build/mac-venv-3.11.18/bin/python -B app/tests/test_update_macos.py
node app/tests/update_view_test.cjs
```
