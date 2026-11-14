#!/usr/bin/env python3
"""Create source/app archives from allowlisted files, never local installer data."""
import argparse
import hashlib
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ('README.md', 'LICENSE', 'CREDITS.md', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md',
         'CONTRIBUTING.md', 'SECURITY.md', '.gitignore', 'Makefile',
         'macos-usb.command', 'App/Package.swift', 'App/Info.plist')
DIRECTORIES = ('cli', 'engine', 'docs', 'App/Assets', 'App/Sources', 'App/Tests', 'scripts', 'tests')


def source_files():
    files = [ROOT / name for name in FILES]
    for name in DIRECTORIES:
        files.extend(p for p in (ROOT / name).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('Missing or symlinked source file: ' + str(path))
    return sorted(set(files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-app', action='store_true', help='Also zip the already-built local app')
    args = parser.parse_args()
    version = re.search(r"^VERSION = '([^']+)'", (ROOT / 'engine/macos_usb.py').read_text(), re.MULTILINE).group(1)
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    archive = dist / ('macos-bootable-usb-creator-' + version + '-source.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in source_files():
            bundle.write(path, 'macos-bootable-usb-creator/' + path.relative_to(ROOT).as_posix())
    artifacts = [archive]
    if args.include_app:
        app = dist / 'macOS Bootable USB Creator.app'
        if not (app / 'Contents/MacOS/MacOSBootableUSBCreator').is_file():
            raise RuntimeError('Build the app first: ./scripts/build-app.sh')
        archive = dist / ('macos-bootable-usb-creator-' + version + '-macos.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(app.rglob('*')):
                if path.is_file():
                    bundle.write(path, path.relative_to(dist).as_posix())
        artifacts.append(archive)
    lines = [hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name for path in artifacts]
    (dist / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(str(path) for path in artifacts))
    print(dist / 'SHA256SUMS.txt')


if __name__ == '__main__':
    main()
