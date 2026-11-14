# Credits and sources

This file identifies implementation sources, workaround references, and
documentation consulted. A link is not an endorsement by its author. MIT
copyright and license notices are preserved in THIRD_PARTY_NOTICES.md.

## CorpNewt and gibMacOS

- **Author:** CorpNewt and gibMacOS contributors.
- **Project:** https://github.com/corpnewt/gibMacOS
- **Source revision:** `bf8f2abdadd56694519f1f04ff9c4b0cd89c6063`.
- **Catalog discovery:** `gibMacOS.py` is imported at runtime to discover
  Apple's full Catalina installer products and their metadata.
- **Assembly source:** `BuildmacOSInstallApp.py` supplies the assembly approach:
  use the BaseSystem installer app, copy the six matching support components,
  rename the ESD package, and adjust the payload URL/identifier in InstallInfo.
- **License:** MIT, copyright © 2018 CorpNewt; full notice included in
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Links to the pinned source:
- https://github.com/corpnewt/gibMacOS/blob/bf8f2abdadd56694519f1f04ff9c4b0cd89c6063/gibMacOS.py
- https://github.com/corpnewt/gibMacOS/blob/bf8f2abdadd56694519f1f04ff9c4b0cd89c6063/BuildmacOSInstallApp.py

gibMacOS itself credits FoxletFox, the Munki project, Tim Sutton, and
wolfmannight for earlier work. Those acknowledgments belong to gibMacOS;
this project has not separately incorporated or audited all of their tools.

## Dortania and OpenCore Install Guide contributors

- **Reference:** https://github.com/dortania/OpenCore-Install-Guide/blob/master/installer-guide/mac-install.md
- **Role:** The Apple Silicon note documents that older `createinstallmedia`
  utilities may be killed because of signatures and describes ad hoc signing
  as a workaround. It informed the host-only execution workaround here.
- **Attribution boundary:** No OpenCore bootloader or OpenCore configuration
  is used or distributed. The original-signature restoration and repair flow
  in this repository is project logic added after testing this workflow.
  The guide is linked as a technical reference; its prose is not reproduced.

## Apple

Apple supplies macOS, the original installer images and code signatures,
the software-update catalog/CDN, `createinstallmedia`, `diskutil`, `hdiutil`,
`ditto`, `codesign`, Rosetta, and the macOS SDK frameworks used by the app.
The installer is downloaded from Apple's servers at runtime; it is not
redistributed in the project's release archives.

Documentation used:
- Bootable installer procedure and Intel startup steps:
  https://support.apple.com/en-us/101578
- Catalina compatibility and requirements:
  https://support.apple.com/en-us/118458
- Download/install methods:
  https://support.apple.com/en-us/102662
- Recovery procedures, considered before the USB workflow:
  https://support.apple.com/en-us/102655
- Installation errors and damaged-installer guidance:
  https://support.apple.com/en-us/102531
- File access and macOS privacy protections:
  https://support.apple.com/en-am/guide/security/secddd1d86a6/web
- Privacy and Security settings reference:
  https://support.apple.com/en-bn/guide/mac-help/mchl211c911f/mac
- Foundation process launching and completion:
  https://developer.apple.com/documentation/foundation/process
  and https://developer.apple.com/documentation/foundation/process/terminationhandler
- Foundation streaming output:
  https://developer.apple.com/documentation/foundation/filehandle/readabilityhandler
- AppKit folder selection:
  https://developer.apple.com/documentation/appkit/nsopenpanel

The SwiftUI app uses system-provided SF Symbols through Apple's frameworks;
it does not bundle a separate third-party icon set. Apple trademarks, software,
SDKs, and system assets retain their applicable terms.

## Diagnostic references

This first-hand VMware community report was consulted while investigating
duplicate Objective-C class warnings in an installer log. It was not used as
a source of code or as proof of the cause on this user's hardware:
https://community.broadcom.com/vmware-cloud-foundation/communities/community-home/digestviewer/viewthread?CommunityKey=0c3a2021-5113-4ad1-af9e-018f5da40bc0&GroupId=7165&MessageKey=e53a284e-c0b7-4419-86ca-24f97e2d342d

## Project development and validation

Kundan supplied the original use case, tested the M1-to-2012-MacBook-Pro
workflow, reported errors, and confirmed that restoring original installer
signatures resolved the reported damaged-installer problem. That report is
not a claim of a completed OS installation on every supported model.

Initial project code, documentation, and debugging were developed with
OpenAI Codex assistance. Maintainers remain responsible for reviewing,
testing, signing, and distributing their release. No Apple, CorpNewt,
Dortania, or OpenAI endorsement is implied.

The original ocean/island/USB app icon was generated for this project using
OpenAI's built-in image-generation tool. Its master file, provenance, design
prompt, and deterministic macOS icon-build instructions are documented in
[docs/ICON.md](docs/ICON.md). It is original project artwork, not an Apple asset.

Apple's published direct links for Lion, Mountain Lion, Yosemite, El Capitan,
and Sierra are recorded in `engine/releases.py`. Native `pkgutil --expand-full`
and `asr` interfaces were checked against the tools' built-in help on the
development Mac. Their use here does not imply all legacy paths have been
hardware-validated.
