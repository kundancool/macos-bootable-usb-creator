# macOS Bootable USB Creator

Download or import a macOS installer and create a bootable USB for a compatible
Intel Mac. Target releases range from **Lion 10.7 through Catalina 10.15**.

Choose the interface you prefer:

| Interface | Best for | Start |
| --- | --- | --- |
| Bash CLI | Terminal users and repeatable preparation | `./macos-usb.command --help` |
| Native Swift app | Guided setup, version/source selection, USB picker, and visible progress | Build/open `macOS Bootable USB Creator.app` |

Both interfaces use one Python engine. **Python 3.9+ is required by both**;
the Bash launcher is not a standalone pure-Bash implementation and the Swift
app is not a Python-free rewrite.

**USB creation erases the selected drive.** The tool never chooses a disk for
you and requires its identifier to be typed before writing. Repair is a separate
operation that restores installer code without erasing the USB payload.

## Versions and download options

| Release | Automatic source | USB creation method |
| --- | --- | --- |
| Lion 10.7 | Apple's installer DMG | Native `asr` image restore |
| Mountain Lion 10.8 | Apple's installer DMG | Native `asr` image restore |
| Mavericks 10.9 | **Local original installer required** | `createinstallmedia` |
| Yosemite 10.10 | Apple's installer DMG | `createinstallmedia` |
| El Capitan 10.11 | Apple's installer DMG | `createinstallmedia` |
| Sierra 10.12 | Apple's installer DMG | `createinstallmedia` |
| High Sierra 10.13 | Apple's full-installer catalog | `createinstallmedia` |
| Mojave 10.14 | Apple's full-installer catalog | `createinstallmedia` |
| Catalina 10.15 | Apple's full-installer catalog | `createinstallmedia` |

Automatic downloads use Apple's published links or catalog. Apple controls
availability. Mavericks is not linked on Apple's current download page, so
there is no automatic unofficial-mirror fallback. Every release also accepts
an **original full `.app`**, an Apple installer-distribution **`.dmg`**, or its
**`.pkg`**. A bare `InstallESD.dmg` alone is not enough for the import workflow.

**Implementation support is not hardware certification.** The original Catalina
workflow and USB signature repair were reported working with an M1 preparation
Mac and a 2012 MacBook Pro. The other releases, particularly Lion/Mountain Lion
restoration on modern macOS, require wider hardware testing. Legacy utilities
may not execute on every preparation Mac; failures stop and retain downloads.
Use a compatible Intel preparation Mac if a legacy operation is unsupported.
This project does not patch incompatible target hardware.

## Requirements

- Preparation host: macOS 11+ for the CLI; macOS 13+ for the app.
- Target: an Intel Mac compatible with the chosen OS. Check Apple's model and
  OS requirements; the host's ability to download does not prove target compatibility.
- Python **3.9+** from [python.org](https://www.python.org/downloads/macos/).
  No pip packages are required.
- Apple Command Line Tools: `xcode-select --install`. App builds need Swift 5.9+.
- Rosetta on Apple Silicon when using Intel `createinstallmedia`:
  `softwareupdate --install-rosetta` (review Apple's license when prompted).
- A **16 GB or larger** external, physical, writable USB drive.
- Internet access for Apple downloads and the pinned gibMacOS source when using
  the catalog route. Local imports can be prepared without catalog access.
- Free internal storage for downloads, extraction, and assembly. Catalog
  preparation typically needs roughly **18–20 GiB** for a fresh download; Apple
  legacy DMG extraction can need more. The tool checks the selected operation's
  budget, accounting for complete cached catalog files. Keep normal macOS free
  space in addition to that budget.
- Keep the tool and its working folder on the **internal drive**.

## Quick start: Bash CLI

Extract this source folder onto the internal drive, then open Terminal:

```bash
cd /path/to/macos-bootable-usb-creator
chmod +x macos-usb.command cli/*.command scripts/*.sh
./macos-usb.command --list-releases
./macos-usb.command --macos catalina --doctor
./macos-usb.command --macos catalina
```

The guided workflow prepares the selected installer, lists USB disks, and asks
which to use. Use the **whole disk** such as `/dev/disk4`, not `/dev/disk4s2`.
Check its name and capacity. Identifiers can change when drives are reconnected.

Run as your normal user. **Do not prefix the entire command with sudo.** Specific
USB operations request an administrator password after disk confirmation; password
characters are not displayed. No unattended erase flag is provided.

### Download and preparation choices

```bash
# Download and assemble the selected release without writing a USB.
./macos-usb.command --macos mojave --download-only

# Download Apple's files only; defer package extraction/app assembly.
./macos-usb.command --macos lion --download-files-only

# Import an existing full original installer; do not contact Apple's catalog.
./macos-usb.command --macos mavericks \
  --source "/Applications/Install OS X Mavericks.app" --download-only

# Import Apple's installer-distribution DMG or PKG.
./macos-usb.command --macos el-capitan \
  --source "$HOME/Downloads/InstallMacOSX.dmg" --download-only
```

Names such as `high-sierra` and version numbers such as `10.13` are accepted.
The default target is Catalina if `--macos` is omitted. Existing prepared apps
and validated downloads are reused. Download-only operations never erase a USB.
Packages are expanded using `pkgutil`; their installation scripts are not run.

### Create the USB

```bash
./cli/create-usb.command --list
./macos-usb.command --macos catalina --disk /dev/diskN --check-only
./macos-usb.command --macos catalina --disk /dev/diskN
```

Replace `/dev/diskN` with the USB's actual identifier. `--check-only` does not
erase the USB; it can prepare host files and apply the local host-signing fix.

Progress is shown for downloads, checksums, assembly, and USB copying. Steps
without reliable numeric progress show their current action. Percentages are
**per step/file**, not an invented overall completion estimate.

Wait for **`USB installer created successfully`**. A volume name, a completed
copy step, or an installer app existing on disk is not proof of a complete USB.
For Mavericks through Catalina the tool restores original installer code after
media creation; this restoration must also finish. Lion/Mountain Lion use image
restoration and a basic boot-file check instead of app signature repair.

## Quick start: native Swift app

```bash
./scripts/build-app.sh
```

Open **`dist/macOS Bootable USB Creator.app`** in Finder. The default build is
for the preparation Mac's CPU. Use `./scripts/build-app.sh --universal` for both
arm64 and x86_64.

1. Review setup requirements; install Python/Command Line Tools if requested.
2. Select the macOS version and choose **Download from Apple** or **Use a local
   installer**. Mavericks explains that a local source is needed.
3. Choose an internal working folder. The default is
   `~/Library/Application Support/MacOSBootableUSBCreator`.
4. Use **Prepare installer**, or **Download files only** to defer preparation.
   The current action, measured percentages, and activity log remain visible.
5. Connect a USB, refresh the drive list, and choose it by name, size, and ID.
6. Use **Check USB**, then **Create installer** when ready.
7. Continue in **Terminal** for the typed disk confirmation and `sudo` password.
   Keep Terminal open until it finishes. The app follows its progress and result.

The app never reads or stores your administrator password. Creation is deliberately
performed through the shared terminal workflow so privilege confirmation and disk
safety checks remain the same in both interfaces. A cancelled/failed operation
does not automatically retry erasure. Logs are available in the activity panel
and under the work folder. Redact usernames, paths, and volume names before sharing.

The app is **ad hoc signed for local development by default**, not Apple-notarized.
Public binary distribution requires the publisher's own signing/notarization
setup; see [docs/RELEASING.md](docs/RELEASING.md).

## Boot and install on the target Mac

1. Eject the completed USB with `diskutil eject /dev/diskN`.
2. Connect it directly to the compatible Intel Mac and connect power.
3. Start while holding **Option (Alt)**; select the installer and press Return.
4. Choose a language if prompted, select **Install macOS/OS X**, and continue.
5. Choose the intended installation destination and follow Apple's instructions.

Erasing the target Mac's internal disk is a separate choice in Disk Utility.
This project prepares USB media; it does not automatically erase that internal
disk or install the OS on the preparation Mac. Keep important files backed up.
Apple notes that internet access may still be needed for model-specific firmware
and other information. See [Apple's bootable-installer guide](https://support.apple.com/en-us/101578).

## Repair original installer signatures

On Apple Silicon, older installer tools or frameworks may need a local ad hoc
signature to execute. That host workaround must not be left as the installer
code used on the target. Normal media creation restores original code from the
verified BaseSystem image or the preserved original imported app automatically.

For an already-created USB with a damaged-installer alert, retain the matching
downloads and reconnect it to the preparation Mac:

```bash
./cli/create-usb.command --list
./macos-usb.command --macos catalina --disk /dev/diskN --repair-usb
```

Repair restores original code and signing metadata while preserving SharedSupport.
It does not erase the USB or fix a missing/incomplete payload. Signature repair
applies to **Mavericks through Catalina**, not Lion/Mountain Lion image restores.
A damaged alert can also have other causes: check the target's clock and obtain
a fresh installer log if repair does not resolve it. Do not disable validation.

## Troubleshooting

| Problem | Next step |
| --- | --- |
| Missing/old Python | Install Python 3.9+, then reopen the app/terminal. |
| Missing Command Line Tools | Run `xcode-select --install` and wait for completion. |
| Rosetta required | Run `softwareupdate --install-rosetta` and review the license. |
| Storage check fails | Free the reported space; keep completed downloads and retry. |
| Checksum/manifest mismatch | Retry over a reliable connection. Never skip integrity checks. |
| Apple download/catalog unavailable | Retry later or import a legitimate original full installer; no unofficial mirror is used. |
| Mavericks automatic download unavailable | Select a local original full installer. |
| Bare InstallESD.dmg rejected | Use the full app or Apple's outer installer-distribution DMG/PKG. |
| Signal 9/framework signature failure | A local signing workaround is attempted before erasure. If unsupported, use a compatible Intel preparation Mac. |
| Legacy ASR restore fails | Retain downloads; use a compatible Intel host. This path is not certified on every modern macOS version. |
| Cocoa 513/Operation not permitted | Enable **Removable Volumes** for the actual app/terminal in **System Settings → Privacy & Security → Files and Folders**, then quit/reopen it. `sudo` does not override macOS privacy controls. |
| USB rejected | Refresh its ID; choose an external physical writable whole disk of at least 16 GB. |
| Missing original source for repair | Use the same release and working folder used for preparation. |
| Another operation running | Wait; do not bypass the active workspace lock. A stale file alone does not hold the lock. |
| Copy failed after erasure | USB is incomplete. Resolve the error and rerun creation; local downloads are retained. |
| Damaged/no installer window | Try signature repair for a completed modern installer; collect a fresh installer log if unresolved. |
| hdiutil deprecation warning | A warning is not failure; use exit status and the final completion message. |

## Files, diagnostics, and developer usage

```bash
./macos-usb.command --version
./macos-usb.command --help
./cli/download-macos.command --macos high-sierra
python3 engine/macos_usb.py doctor --macos catalina --json
```

CLI work files default to **`work/<release>/`**. The app uses its selected folder
with the same per-release layout. To share that folder with the CLI:

```bash
export MACOS_USB_WORKDIR="$HOME/Library/Application Support/MacOSBootableUSBCreator"
./macos-usb.command --macos catalina --download-only
```

Existing `catalina-installer/` data from this project's earlier Catalina-only
prototype is recognized automatically for Catalina when no new work root is set.
Keep original images/manifests or imported app skeletons until creation and any
repair are complete. After testing the USB, remove old work data manually if no
longer needed. Do not delete work data or eject an image during an active task.
Forced termination can leave temporary mounts; eject them with Disk Utility
before removing their scratch folders.

Set `MACOS_USB_EVENTS=1` for newline-delimited `::progress::` JSON records in
stdout alongside human logs. Events include stage, detail, current, and total;
null values mean indeterminate progress. See [architecture](docs/ARCHITECTURE.md).
Exit codes: **0** success, **1** operational failure, **2** invalid arguments,
**130** interruption. There is no unattended erase flag.

```text
macos-bootable-usb-creator/
├── macos-usb.command       # Main Bash entry
├── cli/                   # Separate download/create launchers
├── engine/                # Shared engine, release definitions, import logic
├── App/                   # SwiftUI app, original icon, metadata, Swift checks
├── tests/                 # Offline backend safety and regression checks
├── scripts/               # Checks, icon/app builds, allowlisted release packaging
├── docs/                  # Architecture, icon provenance, and release guide
└── README.md, CREDITS.md, LICENSE, THIRD_PARTY_NOTICES.md
```

Generated `work/`, legacy `catalina-installer/`, app builds, locks, logs, images,
packages, archives, and scratch folders are ignored by Git. Release packaging
uses a source allowlist rather than zipping the working folder.

```bash
make check              # Offline Python + standalone Swift checks; no USB operations
make app                # Build native-CPU app
make app-universal      # Build arm64 + x86_64 app
make release            # Source/app ZIPs and SHA256SUMS; build app first
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[release instructions](docs/RELEASING.md). No repository hosting or publishing
is performed by these scripts.

## Credits and license

[CREDITS.md](CREDITS.md) identifies the specific roles of CorpNewt/gibMacOS,
Dortania, Apple documentation/tools, project testing, and AI-assisted development
and icon artwork. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) preserves
gibMacOS's MIT notice. Project code is [MIT licensed](LICENSE); Apple's installer
binaries and SDKs retain Apple's terms and are not bundled in releases.
This project is not affiliated with or endorsed by Apple, CorpNewt, or Dortania.
