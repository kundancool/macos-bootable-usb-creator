# Changelog

## 0.1.0

- Bash CLI and SwiftUI macOS app in one repository with a shared Python engine.
- Release profiles from Lion through Catalina, direct Apple DMG/catalog
  downloads where published, and local app/DMG/PKG import. Mavericks requires
  a local original installer; no unofficial download mirror is used.
- Download retry/resume, catalog size/checksum verification including Apple's
  chunk-manifest fallback, and stage/byte progress in CLI and app.
- Lion/Mountain Lion image restoration and Mavericks–Catalina createinstallmedia
  routes, with original-code preservation/restoration for the latter.
- Guided external USB selection and confirmation, existing HFS+ layout reuse,
  and clear macOS removable-volume permission errors.
- Apple Silicon host signature workaround, followed by restoration of original
  installer code on the USB; repair mode for previously created media.
- Source-only release packaging, offline checks, and app build scripts.
- Original USB/ocean app artwork, macOS icon generation, and per-release work folders.

The original command-line workflow and subsequent USB signature repair were
reported working on an M1 host for a 2012 MacBook Pro. Other configurations
and the Swift app need wider hardware validation; this release does not claim
that every compatible Mac has been tested.
