# App icon

The original master artwork is `App/Assets/AppIcon.png`. It was generated for
this project with the built-in OpenAI image-generation tool, then copied into
the repository. It is not an Apple wallpaper, Apple logo, or third-party icon.
The project distributes this artwork alongside its own MIT-licensed assets;
it does not claim Apple endorsement or trademark rights over macOS names.

Design prompt used: a single polished macOS rounded-square app icon with a
transparent exterior, deep Pacific blue/turquoise ocean and an original island
ridge, and a large ivory/brushed-silver USB drive angled up-right. Restrained
dimension, crisp silhouette readable at small sizes, generous safe margins,
no lettering, Apple logo, text, watermark, grid, or mockup background. Palette:
ocean #18576B, teal #247D88, fog #F3F7F8, silver, and ivory.

The original prompt used the initial Catalina project name to describe the
island motif; the artwork contains no version-specific text and is used for
the generic macOS Bootable USB Creator app.

`scripts/make-icon.sh` uses Apple's `sips` to make standard 16–1024 pixel PNG
representations and `iconutil` to produce `App/.build/AppIcon.icns`. The app
build bundles that file and references it via `CFBundleIconFile`. Generated
representations are build artifacts; the PNG master and script are source.
