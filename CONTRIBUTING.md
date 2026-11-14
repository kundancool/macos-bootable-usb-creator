# Contributing

Use Python 3.9+, macOS 13+, Swift 5.9+ and Apple Command Line Tools. There are
no pip, npm, or Swift package dependencies to install for this repository.

```bash
./scripts/check.sh
./scripts/build-app.sh --debug
```

Backend logic belongs in `engine/macos_usb.py`; Bash launchers and the Swift app
must call that engine. Keep user-visible operations and exit statuses consistent.
Keep requirements and flags synchronized with README.md and the app's guide.
Use `CATALINA_WORKDIR` to isolate scratch downloads from personal installer data.

Tests must never erase, partition, bless, or write to an actual USB. Mock disk
metadata, process execution, and privileged operations. Disk validation must
reject internal disks, partitions, virtual devices, and unknown metadata.
Keep explicit disk confirmation; never add automatic first-disk selection.
Do not accept an installer just because its filename or byte count matches.

Manual hardware checks, using a disposable USB, are separate: download, repeat
without redownloading, preflight, cancel confirmation, create media, verify
signature restoration, then boot on a compatible Intel Mac. Record host OS,
CPU architecture, target model, and results. Never claim success from `--help`
or filesystem checks alone.

Before a release, run `make check`, build both architectures if distributing a
universal app, and create archives with `scripts/package-release.py`. Inspect
the archive manifest and SHA256SUMS.txt. Installer binaries, local logs,
credentials, dependency downloads, `.git`, and build caches must not be included
in source archives. Publishing is a separate manual operation.
