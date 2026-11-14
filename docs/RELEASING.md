# Prepare a release locally

No step in these scripts publishes, creates a hosted repository, or contacts
a Git hosting service. Source dependencies are fetched only when preparing
an installer through the catalog route, not when building the Swift app or running tests.

## Check and build

```bash
./scripts/check.sh
./scripts/build-app.sh --universal
python3 scripts/package-release.py --include-app
```

Generated files are in `dist/`:

- `macOS Bootable USB Creator.app`: native app with the backend and user guide bundled.
- `macos-bootable-usb-creator-0.1.0-source.zip`: allowlisted source, including both interfaces.
- `macos-bootable-usb-creator-0.1.0-macos.zip`: the app built by the preceding command.
- `SHA256SUMS.txt`: checksums for the generated release archives.

The version is defined in `engine/macos_usb.py`; keep Swift UI version labels,
App/Info.plist, CHANGELOG.md, and release documentation synchronized when bumping.
The source packager does not zip the workspace blindly. Installer payloads,
logs, `.git`, dependency downloads, and build caches are excluded even if present
locally. Never upload `work/` or legacy `catalina-installer/` as part of this project's source or
app release. You can produce just the source archive without building:

```bash
python3 scripts/package-release.py
```

## Local Git repository

The prepared local repository uses the `main` branch. Inspect changes and
ignored files before committing:

```bash
git status --short
git status --ignored --short
git diff --cached --stat
```

Commit using your own configured author identity. Choose your hosting service,
repository visibility, and remote yourself when ready. No remote or hosted
repository is created by the project scripts.

## Signing and notarization

The default app is ad hoc signed for local builds. This is not sufficient to
claim an Apple-notarized public app. For a distributable binary, use your own
Developer ID Application certificate, unique bundle identifier, hardened-runtime
configuration, and notarization credentials. Review Apple's current distribution
requirements before publishing. Never commit signing secrets or Apple credentials.

`CODESIGN_IDENTITY` can select a signing identity during the build, but setting
it alone does not perform notarization or establish a complete release-signing
pipeline. The maintainer must configure, notarize, staple, and verify their own
release. Repackage and regenerate checksums after signing/stapling.

The app's signing identity is separate from local legacy host-tool signing
workaround and from the original Apple installer signatures restored to USB media.

## Release review

1. Review MIT attribution and CREDITS.md; add a private security contact to
   SECURITY.md before accepting public reports.
2. Run offline tests and inspect source/app archive manifests and checksums.
3. Record actual host OS, architecture, target model, and hardware test results.
4. Test creation and repair on disposable USB media and boot a compatible Intel
   Mac. Do not describe an offline test or `--help` check as hardware validation.
5. Publish the interface choices and limitations clearly: both use Python; USB
   creation opens Terminal for privilege confirmation; current app signing status
   must be stated accurately.
