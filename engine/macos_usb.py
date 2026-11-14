#!/usr/bin/env python3
"""macOS Bootable USB Creator: download/import Lion through Catalina and create USB media.

Installer assembly follows corpnewt/gibMacOS BuildmacOSInstallApp.py.
No disk is erased by the download or --check-only commands.
"""
import argparse
from contextlib import nullcontext
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import zipfile

if sys.version_info < (3, 9):
    raise SystemExit('Python 3.9 or newer is required. Install Python from https://www.python.org/downloads/macos/')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from releases import RELEASES, normalize_release
import legacy

ROOT = Path(__file__).resolve().parent.parent
VERSION = '0.1.0'
GIB_COMMIT = 'bf8f2abdadd56694519f1f04ff9c4b0cd89c6063'
RELEASE_KEY = 'catalina'
RELEASE = RELEASES[RELEASE_KEY]
WORK_ROOT = Path(os.environ.get('MACOS_USB_WORKDIR', str(ROOT / 'work'))).expanduser().resolve()
WORK = ROOT / 'catalina-installer' if (ROOT / 'catalina-installer').is_dir() else WORK_ROOT / RELEASE_KEY
APP = WORK / RELEASE['app']
_progress_times = {}
REQUIRED = ('BaseSystem.dmg', 'BaseSystem.chunklist', 'InstallESDDmg.pkg',
            'InstallInfo.plist', 'AppleDiagnostics.dmg', 'AppleDiagnostics.chunklist')


def fail(message):
    raise RuntimeError(message)


def configure_release(key):
    global RELEASE_KEY, RELEASE, WORK_ROOT, WORK, APP
    RELEASE_KEY = normalize_release(key)
    RELEASE = RELEASES[RELEASE_KEY]
    WORK_ROOT = Path(os.environ.get('MACOS_USB_WORKDIR', str(ROOT / 'work'))).expanduser().resolve()
    WORK = WORK_ROOT / RELEASE_KEY
    if RELEASE_KEY == 'catalina' and 'MACOS_USB_WORKDIR' not in os.environ:
        old = Path(os.environ.get('CATALINA_WORKDIR', str(ROOT / 'catalina-installer'))).expanduser().resolve()
        if old.is_dir():
            WORK = old
    APP = WORK / RELEASE['app']


def progress(stage, current=None, total=None, detail=''):
    key = (stage, detail)
    now = time.monotonic()
    done = total is not None and current is not None and current >= total
    if key in _progress_times and now - _progress_times[key] < 0.75 and not done:
        return
    _progress_times[key] = now
    event = {'stage': stage, 'detail': detail, 'current': current, 'total': total}
    if os.environ.get('MACOS_USB_EVENTS') == '1':
        print('::progress::' + json.dumps(event), flush=True)
    elif current is not None and total:
        text = '\r{}: {:.1f}%'.format(detail or stage, min(100, current / total * 100))
        if total > 100:
            text += ' ({:.1f}/{:.1f} MiB)'.format(current / 1024**2, total / 1024**2)
        print(text,
              end='\n' if done else '', flush=True)
    elif current is not None:
        print('\r{}: {:.1f} MiB processed'.format(detail or stage, current / 1024**2), end='', flush=True)
    else:
        print('\n' + (detail or stage) + '…', flush=True)


def terminal_prompt(message):
    # A tty is not seekable: buffered r+ streams can fail when switching from
    # writing to reading. Separate descriptors work in Terminal and over SSH.
    with open('/dev/tty', 'w') as output, open('/dev/tty', 'r') as input_stream:
        output.write(message)
        output.flush()
        return input_stream.readline().strip()


def run(args, progress_file=None, progress_size=None, progress_detail='', **kwargs):
    print('+ ' + ' '.join(map(str, args)), flush=True)
    if progress_file is not None:
        with subprocess.Popen(list(map(str, args)), **kwargs) as process:
            while process.poll() is None:
                current = progress_file.stat().st_size if progress_file.exists() else 0
                progress('download', current, progress_size, progress_detail)
                time.sleep(0.2)
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, args)
            progress('download', progress_file.stat().st_size, progress_size, progress_detail)
        return
    words = list(map(str, args))
    if words and words[0] == '/usr/bin/sudo':
        words = words[1:]
    if words[:2] == ['/usr/sbin/asr', 'restore']:
        progress('usb-restore', None, None, 'Restoring and verifying legacy image')
        with subprocess.Popen(list(map(str, args)), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                measured = re.search(r'(?:PERCENT|progress)\s*[:=]\s*(\d+(?:\.\d+)?)', line, re.IGNORECASE)
                if measured:
                    progress('usb-restore', float(measured.group(1)), 100, 'Restoring and verifying legacy image')
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, args)
        return
    action = Path(words[0]).name + (' ' + words[1] if len(words) > 1 else '')
    labels = {'hdiutil verify': 'Verifying disk image', 'hdiutil attach': 'Mounting original installer image',
              'hdiutil detach': 'Releasing temporary image', 'pkgutil --expand-full': 'Extracting installer package',
              'diskutil mount': 'Mounting USB', 'diskutil eraseDisk': 'Formatting the confirmed USB',
              'asr info': 'Checking legacy restore source'}
    label = labels.get(action, 'Copying installer files' if words and Path(words[0]).name == 'ditto'
                       else 'Checking installer signatures' if words and Path(words[0]).name == 'codesign' else action)
    progress('operation', None, None, label)
    result = subprocess.run(list(map(str, args)), check=True, **kwargs)
    progress('operation', 1, 1, label + ' finished')
    return result


def apple_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not (parsed.hostname or '').endswith(('.apple.com', '.cdn-apple.com')):
        fail('Unexpected non-Apple installer URL: ' + url)
    return parsed._replace(scheme='https').geturl()


def verify_chunks(path, manifest):
    data = Path(manifest).read_bytes()
    if len(data) < 36:
        fail('Truncated Apple chunk manifest')
    magic, header, version, method, signature, unused, count, offset, sig_offset = struct.unpack_from('<4sIBBBBQQQ', data)
    if (magic, header, version, method) != (b'CNKL', 36, 1, 1) or offset != 36:
        fail('Unsupported Apple chunk manifest format')
    if not count or offset + count * 36 != sig_offset or sig_offset > len(data):
        fail('Invalid Apple chunk manifest bounds')
    with Path(path).open('rb') as stream:
        completed = 0
        total_bytes = Path(path).stat().st_size
        for number in range(count):
            length, expected = struct.unpack_from('<I32s', data, offset + number * 36)
            if not 0 < length <= 64 * 1024**2:
                fail('Invalid Apple chunk length')
            block = stream.read(length)
            if len(block) != length or hashlib.sha256(block).digest() != expected:
                return False
            completed += length
            progress('validation', completed, total_bytes, 'Checking SHA-256 chunks: ' + Path(path).name)
        return not stream.read(1)


def fetch(url, destination, size=None, digest=None, integrity_url=None, integrity_size=None):
    destination = Path(destination)

    def valid(path):
        if not path.is_file() or (size is not None and path.stat().st_size != size):
            return False
        if digest:
            h = hashlib.sha1()
            completed = 0
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    h.update(block)
                    completed += len(block)
                    progress('validation', completed, path.stat().st_size, 'Checking checksum: ' + path.name)
            expected = digest.hex() if isinstance(digest, bytes) else digest
            actual = h.hexdigest().lower()
            if actual == expected.lower():
                return True
            print('Catalog SHA-1 differs for {}: expected {}, got {}'.format(path.name, expected, actual), flush=True)
            if integrity_url:
                # Apple can retain a stale catalog SHA-1 for a reissued package.
                # Require every byte to match Apple's HTTPS chunk manifest.
                manifest = destination.with_name(destination.name + '.integrityDataV1')
                fetch(apple_url(integrity_url), manifest, integrity_size)
                if verify_chunks(path, manifest):
                    print('Verified every SHA-256 chunk against Apple integrity manifest:', path.name, flush=True)
                    return True
            return False
        return True

    if valid(destination):
        print('Using validated download:', destination, flush=True)
        return
    partial = destination.with_name(destination.name + '.part')
    if valid(partial):
        print('Recovering complete, validated .part file:', partial, flush=True)
        partial.replace(destination)
        return
    resume = (size is not None and partial.is_file() and 0 < partial.stat().st_size < size)
    command = ['/usr/bin/curl', '--fail', '--location', '--retry', '3',
               '--connect-timeout', '30', '--silent', '--show-error', '--output', partial]
    try:
        run(command + (['--continue-at', '-'] if resume else []) + [url],
            progress_file=partial, progress_size=size, progress_detail='Downloading ' + destination.name)
    except subprocess.CalledProcessError as error:
        if resume and error.returncode in (33, 36):
            print('Server cannot resume; restarting this download.', flush=True)
            run(command + [url], progress_file=partial, progress_size=size, progress_detail='Downloading ' + destination.name)
        else:
            raise
    if not valid(partial):
        fail('Downloaded file failed size/digest validation: ' + str(partial))
    partial.replace(destination)


def validate_app(app):
    if app.name != RELEASE['app']:
        fail('Installer app does not match selected release: ' + RELEASE['title'])
    esd = app / 'Contents/SharedSupport/InstallESD.dmg'
    if not esd.is_file() or not esd.stat().st_size:
        fail('Missing full installer payload: ' + str(esd))
    if RELEASE['method'] == 'restore':
        return esd
    tool = app / 'Contents/Resources/createinstallmedia'
    if not tool.is_file() or not os.access(tool, os.X_OK):
        fail('Missing executable createinstallmedia. Run download-macos-usb.command first.')
    shared = app / 'Contents/SharedSupport'
    for name in REQUIRED if RELEASE.get('catalog') else ('InstallESDDmg.pkg',):
        name = 'InstallESD.dmg' if name == 'InstallESDDmg.pkg' else name
        path = shared / name
        if not path.is_file() or not path.stat().st_size:
            fail('Installer support file missing or empty: ' + str(path))
    if (shared / 'InstallInfo.plist').is_file():
        with (shared / 'InstallInfo.plist').open('rb') as stream:
            info = plistlib.load(stream)
        version = str(info.get('System Image Info', {}).get('version', ''))
        if version and not (version == RELEASE['version'] or version.startswith(RELEASE['version'] + '.')):
            fail('Installer version does not match ' + RELEASE['title'] + ': ' + repr(version))
    return tool


def download(args):
    if os.geteuid() == 0:
        fail('Run the download script as your normal user, without sudo.')
    WORK.mkdir(exist_ok=True)
    if APP.exists():
        validate_app(APP)
        print('Installer already assembled:', APP)
        return
    if getattr(args, 'source', None):
        legacy.prepare(args.source, WORK, RELEASE, run, progress)
        validate_app(APP)
        return
    if not RELEASE.get('catalog'):
        url = RELEASE.get('url')
        if not url:
            fail(RELEASE['title'] + ' has no direct public Apple download configured. Supply your original full installer with --source /path/to/' + RELEASE['app'] + '. No unofficial mirror is used.')
        destination = WORK / 'AppleInstaller.dmg'
        progress('download', None, None, 'Getting Apple download size')
        header = subprocess.run(['/usr/bin/curl', '--fail', '--location', '--head', '--silent', '--show-error', '--connect-timeout', '30', apple_url(url)],
                                check=True, stdout=subprocess.PIPE, text=True)
        sizes = re.findall(r'^content-length:\s*(\d+)', header.stdout, re.IGNORECASE | re.MULTILINE)
        size = int(sizes[-1]) if sizes else None
        needed = (size or 0) + 512 * 1024**2 if getattr(args, 'download_files_only', False) else (size or 0) * 3 + 2 * 1024**3
        if size and shutil.disk_usage(WORK).free < needed:
            fail('Need {:.1f} GiB free for the requested Apple download/preparation.'.format(needed / 1024**3))
        fetch(apple_url(url), destination, size)
        run(['/usr/bin/hdiutil', 'verify', destination])
        if getattr(args, 'download_files_only', False):
            print('Apple download saved:', destination)
            return
        legacy.prepare(destination, WORK, RELEASE, run, progress)
        validate_app(APP)
        return
    if shutil.disk_usage(WORK).free < 100 * 1024**2:
        fail('At least 100 MiB free space is required to load the download tools and catalog.')
    archive = WORK / ('gibMacOS-' + GIB_COMMIT + '.zip')
    source = WORK / ('gibMacOS-' + GIB_COMMIT)
    if not (source / 'gibMacOS.py').is_file():
        legacy = WORK / 'gibMacOS-master.zip'
        if not archive.exists() and legacy.is_file():
            with zipfile.ZipFile(legacy) as bundle:
                if bundle.comment.decode('ascii') == GIB_COMMIT:
                    shutil.copy2(legacy, archive)
        fetch('https://codeload.github.com/corpnewt/gibMacOS/zip/' + GIB_COMMIT, archive)
        with zipfile.ZipFile(archive) as bundle:
            if bundle.comment.decode('ascii') != GIB_COMMIT:
                fail('gibMacOS archive does not identify the pinned source commit.')
            roots = {Path(item.filename).parts[0] for item in bundle.infolist()}
            if len(roots) != 1:
                fail('Unexpected gibMacOS archive structure.')
            for item in bundle.infolist():
                target = (WORK / item.filename).resolve()
                if not target.is_relative_to(WORK.resolve()):
                    fail('Unsafe path in gibMacOS archive')
            bundle.extractall(WORK)
            extracted = WORK / roots.pop()
            if extracted != source:
                extracted.rename(source)
    sys.path.insert(0, str(source))
    gib = importlib.import_module('gibMacOS').gibMacOS(interactive=False)
    gib.current_catalog = 'publicrelease'
    gib.current_macos = 15
    gib.find_recovery = False
    progress('catalog', None, None, 'Reading Apple installer catalog')
    gib.set_prods()
    products = [p for p in gib.mac_prods if p['version'] == RELEASE['version'] or p['version'].startswith(RELEASE['version'] + '.')]
    if not products:
        fail('Apple catalog contains no full installer for ' + RELEASE['title'] + '. Supply an original full installer with --source instead.')
    product = max(products, key=lambda p: p['time'])
    product_id = product['product']
    print('Selected installer:', RELEASE['title'], product_id, product['version'], product['build'], flush=True)
    packages = gib.catalog_data['Products'][product_id]['Packages']
    files = {Path(urlparse(p['URL']).path).name: p for p in packages}
    missing = set(REQUIRED) - files.keys()
    if missing:
        fail('Apple product is missing components: ' + ', '.join(sorted(missing)))
    downloads = WORK / product_id
    downloads.mkdir(exist_ok=True)
    # Count complete downloads, including .part files, toward the disk budget.
    pending = sum(files[name]['Size'] for name in REQUIRED if not any(
        path.is_file() and path.stat().st_size == files[name]['Size']
        for path in (downloads / name, downloads / (name + '.part'))))
    needed = pending + (512 * 1024**2 if getattr(args, 'download_files_only', False)
                        else sum(files[name]['Size'] for name in REQUIRED) + 2 * 1024**3)
    available = shutil.disk_usage(WORK).free
    print('Disk budget: {:.2f} GiB needed, {:.2f} GiB available'.format(needed / 1024**3, available / 1024**3), flush=True)
    if available < needed:
        fail('Need {:.2f} GiB additional free space for remaining downloads and assembly.'.format((needed-available) / 1024**3))
    for name in REQUIRED:
        package = files[name]
        fetch(apple_url(package['URL']), downloads / name,
              package['Size'], package.get('Digest'),
              package.get('IntegrityDataURL'), package.get('IntegrityDataSize'))
    manifest = {'product': product_id, 'version': product['version'],
                'build': product['build'], 'packages': [files[n] for n in REQUIRED]}
    with (downloads / 'download-manifest.plist').open('wb') as stream:
        plistlib.dump(manifest, stream)
    if getattr(args, 'download_files_only', False):
        print('Matching Apple components downloaded:', downloads)
        return
    progress('validation', None, None, 'Verifying original BaseSystem disk image')
    run(['/usr/bin/hdiutil', 'verify', downloads / 'BaseSystem.dmg'])
    # Use a private staging folder so interruption never leaves a completed app.
    with tempfile.TemporaryDirectory(prefix='assemble-', dir=WORK) as staging:
        mount = Path(staging) / 'base'
        mount.mkdir()
        attached = False
        try:
            run(['/usr/bin/hdiutil', 'attach', downloads / 'BaseSystem.dmg',
                 '-readonly', '-nobrowse', '-mountpoint', mount])
            attached = True
            candidates = list(mount.glob('*.app'))
            if len(candidates) != 1:
                fail('Could not uniquely locate installer app in BaseSystem.dmg')
            assembled = Path(staging) / APP.name
            run(['/usr/bin/ditto', candidates[0], assembled])
            shared = assembled / 'Contents/SharedSupport'
            shared.mkdir(parents=True, exist_ok=True)
            for name in REQUIRED:
                dest = 'InstallESD.dmg' if name == 'InstallESDDmg.pkg' else name
                source = downloads / name
                total = source.stat().st_size
                copied = 0
                with source.open('rb') as input_stream, (shared / dest).open('wb') as output:
                    for block in iter(lambda: input_stream.read(8 * 1024**2), b''):
                        output.write(block)
                        copied += len(block)
                        progress('assembly', copied, total, 'Assembling ' + dest)
                shutil.copystat(source, shared / dest)
            with (shared / 'InstallInfo.plist').open('rb') as stream:
                info = plistlib.load(stream)
            payload = info.get('Payload Image Info', {})
            for key, old, new in [('URL', 'InstallESDDmg.pkg', 'InstallESD.dmg'),
                                  ('id', 'com.apple.pkg.InstallESDDmg', 'com.apple.dmg.InstallESD')]:
                if key in payload:
                    payload[key] = payload[key].replace(old, new)
            payload.pop('chunklistURL', None)
            payload.pop('chunklistid', None)
            with (shared / 'InstallInfo.plist').open('wb') as stream:
                plistlib.dump(info, stream)
            validate_app(assembled)
            assembled.rename(APP)
        finally:
            if attached:
                run(['/usr/bin/hdiutil', 'detach', mount])
    print('\nComplete installer:', APP)
    print('Next: ./cli/create-usb.command --list')


def disk_info(disk):
    result = subprocess.run(['/usr/sbin/diskutil', 'info', '-plist', disk],
                            check=True, stdout=subprocess.PIPE)
    return plistlib.loads(result.stdout)


def external_disk(disk):
    info = disk_info(disk)
    if info.get('DeviceNode') != disk:
        fail('Disk metadata does not match the selected device.')
    if info.get('Internal') is not False or info.get('WholeDisk', info.get('Whole')) is not True:
        fail('Refusing disk: target must be a confirmed external whole disk.')
    if info.get('VirtualOrPhysical') != 'Physical':
        fail('Refusing disk: target must be physical.')
    if info.get('TotalSize', 0) < 16_000_000_000:
        fail('USB must have at least 16 GB capacity.')
    if info.get('WritableMedia') is not True:
        fail('The selected USB is read-only or its write capability could not be confirmed.')
    return info


def prepare_media_tool(tool):
    def probe():
        return subprocess.run([str(tool), '--help'], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)

    result = probe()
    if result.returncode == -9 and platform.machine() == 'arm64':
        print('macOS killed createinstallmedia (signal 9); attempting the Apple Silicon signature workaround.', flush=True)
        print('Preserving the Apple executable and applying a local ad hoc signature to this utility.', flush=True)
        backup = tool.with_name(tool.name + '.apple-original')
        if not backup.exists():
            shutil.copy2(tool, backup)
        run(['/usr/bin/codesign', '--force', '--sign', '-', tool])
        run(['/usr/bin/codesign', '--verify', '--verbose', tool])
        result = probe()
    if platform.machine() == 'arm64' and (
            result.returncode == -9 or 'code signature invalid' in result.stdout):
        print('Installer frameworks also require local signatures; signing the local installer bundle.', flush=True)
        run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', tool.parents[2]])
        result = probe()
    if result.returncode < 0 or '--volume' not in result.stdout:
        fail('createinstallmedia preflight failed (exit {}).\n{}\n'
             'No disk was erased. If the utility still cannot run, use this installer on a compatible Intel Mac.'
             .format(result.returncode, result.stdout))
    print('Installer utility execution check passed.', flush=True)


def reusable_partition(disk):
    result = subprocess.run(['/usr/sbin/diskutil', 'list', '-plist', disk],
                            check=True, stdout=subprocess.PIPE)
    layouts = plistlib.loads(result.stdout).get('AllDisksAndPartitions', [])
    if len(layouts) != 1 or layouts[0].get('Content') != 'GUID_partition_scheme':
        return None
    partitions = layouts[0].get('Partitions', [])
    data = [p for p in partitions if p.get('Content') != 'EFI']
    if len(data) != 1 or data[0].get('Content') != 'Apple_HFS':
        return None
    identifier = data[0].get('DeviceIdentifier', '')
    if not re.fullmatch(re.escape(disk.removeprefix('/dev/')) + r's[0-9]+', identifier):
        return None
    return '/dev/' + identifier


def usb_permission_help():
    return ('macOS denied terminal access to the USB. In System Settings > Privacy & Security > '
            'Files and Folders, enable Removable Volumes for iTerm (or the terminal app running this script). '
            'Quit and reopen that terminal, then rerun the command. '
            'sudo does not override this macOS privacy permission.')


def write_installer(tool, volume, app=None):
    command = ['/usr/bin/sudo', str(tool), '--volume', volume, '--nointeraction']
    if int(RELEASE['version'].split('.')[1]) <= 12:
        command += ['--applicationpath', str(app or APP)]
    print('+ ' + ' '.join(command), flush=True)
    recent = ''
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1) as process:
        for line in process.stdout:
            print(line, end='', flush=True)
            recent = (recent + line)[-65536:]
            percentages = re.findall(r'(\d+(?:\.\d+)?)%', line)
            if percentages:
                stage = 'Erasing USB' if 'Erasing' in line else 'Copying installer to USB'
                progress('usb', float(percentages[-1]), 100, stage)
            elif line.strip():
                progress('usb', None, None, line.strip()[:160])
        status = process.wait()
    if status:
        if 'Operation not permitted' in recent or ('Code=513' in recent):
            fail(usb_permission_help() + '\nThe USB was already erased by createinstallmedia, '
                 'but installer creation did not complete. The downloaded installer remains available.')
        fail('createinstallmedia failed (exit {}). The USB is incomplete; the installer download is preserved.'.format(status))


def original_image():
    original = WORK / 'original' / APP.name
    if original.is_dir():
        return original
    manifests = list(WORK.glob('*/download-manifest.plist'))
    if len(manifests) != 1:
        fail('Keep exactly one matching product download in this release work folder for signature restoration.')
    image = manifests[0].parent / 'BaseSystem.dmg'
    if not image.is_file():
        fail('Original BaseSystem image is missing: ' + str(image))
    with manifests[0].open('rb') as stream:
        manifest = plistlib.load(stream)
    package = next((p for p in manifest.get('packages', [])
                    if Path(urlparse(p.get('URL', '')).path).name == 'BaseSystem.dmg'), None)
    if not package or image.stat().st_size != package.get('Size'):
        fail('Original BaseSystem image does not match its download manifest. Rerun download preparation.')
    return image


def restore_original_installer(volume):
    """Restore Apple's signed code on media after using host-signed tools."""
    destination = Path(volume) / APP.name
    if destination.is_symlink() or not destination.resolve().is_relative_to(Path(volume).resolve()):
        fail('Refusing a redirected USB installer app path.')
    for folder, directories, filenames in os.walk(destination, followlinks=False):
        for name in directories + filenames:
            entry = Path(folder) / name
            if entry.is_symlink() and not entry.resolve().is_relative_to(destination.resolve()):
                fail('Installer contains a symlink outside its app bundle: ' + str(entry))
    validate_app(destination)
    image = original_image()
    progress('repair', None, None, 'Restoring original installer signatures')
    manager = nullcontext(image.parent) if image.is_dir() else legacy.mounted(image, WORK, run)
    with manager as mount:
        originals = list(mount.glob('*.app'))
        if len(originals) != 1 or originals[0].name != destination.name:
            fail('Original installer app could not be uniquely identified.')
        source = originals[0]
        # Refuse a differently versioned destination before overwriting code.
        def app_info(app):
            with (app / 'Contents/Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            return tuple(info.get(k) for k in ('CFBundleIdentifier', 'CFBundleVersion'))
        if app_info(source) != app_info(destination):
            fail('USB installer does not match the original BaseSystem app version.')
        if (source / 'Contents/SharedSupport').exists():
            fail('Unexpected SharedSupport in original app; refusing to overwrite USB payload.')
        print('Restoring original Apple installer code and signatures; retaining USB SharedSupport payload.', flush=True)
        # ditto merges the app skeleton; SharedSupport is absent in the source.
        run(['/usr/bin/sudo', '/usr/bin/ditto', source, destination])
        backup = destination / 'Contents/Resources/createinstallmedia.apple-original'
        if backup.is_file():
            run(['/usr/bin/sudo', '/bin/rm', backup])
        # Compare the original executable bytes, including embedded signatures.
        for relative in ('Contents/MacOS/InstallAssistant',
                         'Contents/MacOS/InstallAssistant_springboard',
                         'Contents/Resources/createinstallmedia'):
            original = source / relative
            if original.is_file() and original.read_bytes() != (destination / relative).read_bytes():
                fail('Original executable restoration check failed: ' + relative)
        signatures = []
        for bundle in (source, destination):
            display = subprocess.run(['/usr/bin/codesign', '-dv', '--verbose=4', str(bundle)],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
            match = re.search(r'^CDHash=(\S+)', display.stdout, re.MULTILINE)
            if 'Signature=adhoc' in display.stdout or not match:
                fail('Expected original signed installer metadata.\n' + display.stdout)
            signatures.append(match.group(1))
        if signatures[0] != signatures[1]:
            fail('Restored app signature metadata differs from original BaseSystem app.')
        print('Original installer executables and signature metadata match the verified BaseSystem app.', flush=True)
    progress('repair', 1, 1, 'Original installer code restored and checked')


def repair_usb(args):
    if RELEASE['method'] == 'restore':
        fail('Lion and Mountain Lion use image restoration, not app signature repair. Recreate their USB if its payload is incomplete.')
    original_image()
    if not args.disk or not re.fullmatch(r'/dev/disk[0-9]+', args.disk):
        fail('Specify the USB whole disk with --disk /dev/diskN.')
    info = external_disk(args.disk)
    target = reusable_partition(args.disk)
    if not target:
        fail('Expected an existing GUID/HFS+ installer USB. No disk was changed.')
    partition = disk_info(target)
    volume = partition.get('MountPoint')
    if not volume:
        run(['/usr/sbin/diskutil', 'mount', target])
        volume = disk_info(target).get('MountPoint')
    if not volume:
        fail('Cannot find the USB mount point.')
    validate_app(Path(volume) / APP.name)
    print('Repair installer code on {} ({}) without erasing the USB.'.format(args.disk, volume), flush=True)
    if terminal_prompt('Type {} to confirm repair: '.format(args.disk)) != args.disk:
        fail('Repair cancelled.')
    run(['/usr/bin/sudo', '-v'])
    if external_disk(args.disk) != info or disk_info(target).get('MountPoint') != volume:
        fail('USB information changed; rerun repair.')
    restore_original_installer(volume)
    print('USB installer code repaired. Eject the USB before reconnecting to the Intel Mac.')


def usb(args):
    if args.list:
        run(['/usr/sbin/diskutil', 'list', 'external', 'physical'])
        return
    if not args.disk or not re.fullmatch(r'/dev/disk[0-9]+', args.disk):
        fail('Specify a whole disk: --disk /dev/diskN. Use --list to find it.')
    app = (args.app or APP).resolve()
    use_restore = RELEASE['method'] == 'restore'
    # Fail before erasure if signature restoration cannot be completed.
    if not use_restore:
        original_image()
    tool = validate_app(app)
    # --help runs the actual Intel utility, without touching the target disk.
    if not use_restore and platform.machine() == 'arm64':
        result = subprocess.run(['/usr/bin/arch', '-x86_64', '/usr/bin/true'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            fail('Rosetta is required. Run: softwareupdate --install-rosetta\nThen rerun this script.')
    if use_restore:
        progress('validation', None, None, 'Checking legacy InstallESD image before erasure')
        run(['/usr/bin/hdiutil', 'verify', tool])
        run(['/usr/sbin/asr', 'info', '--source', tool])
    else:
        progress('preflight', None, None, 'Checking installer utility on this Mac')
        prepare_media_tool(tool)
    info = external_disk(args.disk)
    # Protect the installer and running scripts if someone selects their disk.
    for protected in (app, ROOT):
        mount = protected
        while not os.path.ismount(mount):
            mount = mount.parent
        protected_info = disk_info(str(mount))
        if protected_info.get('Internal') is not True:
            fail('Keep the installer and these scripts on the internal drive before creating USB media.')
        parent = protected_info.get('ParentWholeDisk', protected_info.get('DeviceIdentifier'))
        if parent == args.disk.removeprefix('/dev/'):
            fail('Target disk contains the installer or these scripts. Move them to the internal disk first.')
    print('\nTarget: {} | {} | {:.1f} GB'.format(args.disk,
          info.get('MediaName', info.get('IORegistryEntryName', 'Unknown')),
          info['TotalSize'] / 1e9), flush=True)
    run(['/usr/sbin/diskutil', 'list', args.disk])
    existing = reusable_partition(args.disk)
    if existing:
        mounted = disk_info(existing).get('MountPoint')
        if mounted:
            try:
                with os.scandir(mounted) as entries:
                    next(entries, None)
            except PermissionError:
                fail(usb_permission_help() + '\nNo disk was erased by this run.')
    if args.check_only:
        print('Preflight passed. No disk was erased.')
        return
    print('\nALL DATA ON THIS DISK WILL BE ERASED.', flush=True)
    if terminal_prompt('Type {} to confirm: '.format(args.disk)) != args.disk:
        fail('Cancelled. No disk was erased.')
    run(['/usr/bin/sudo', '-v'])
    # Reject a changed disk after the password/confirmation delay.
    if external_disk(args.disk) != info:
        fail('Disk information changed. Rerun and confirm the disk again.')
    target = reusable_partition(args.disk)
    if target:
        print('Reusing existing GUID/HFS+ USB partition; skipping eraseDisk.', flush=True)
        run(['/usr/sbin/diskutil', 'mount', target])
    else:
        run(['/usr/bin/sudo', '/usr/sbin/diskutil', 'eraseDisk', 'JHFS+',
             'MacOSBootableUSBCreator', 'GPT', args.disk])
        target = args.disk + 's2'
    partition = disk_info(target)
    volume = partition.get('MountPoint')
    if not volume or partition.get('ParentWholeDisk') != args.disk.removeprefix('/dev/'):
        fail('Could not verify the new USB partition mount point. Stopping.')
    if use_restore:
        progress('usb', None, None, 'Restoring original bootable InstallESD image; keep the USB connected')
        run(['/usr/bin/sudo', '/usr/sbin/asr', 'restore', '--source', tool,
             '--target', volume, '--erase', '--noprompt', '--puppetstrings'])
        run(['/usr/sbin/diskutil', 'mount', target])
    else:
        write_installer(tool, volume, app)
    # createinstallmedia may rename the volume, so resolve its mount point again.
    created_volume = disk_info(target).get('MountPoint')
    if not created_volume:
        fail('Installer utility finished, but its USB mount point could not be resolved for signature restoration.')
    if use_restore:
        markers = [Path(created_volume) / name for name in
                   ('System/Library/CoreServices/boot.efi', '.IABootFiles/boot.efi', '.boot.efi', 'boot.efi')]
        if not any(path.is_file() for path in markers):
            fail('Image restoration finished but no expected Intel boot file was found. Do not treat this USB as verified bootable; use a compatible Intel preparation Mac.')
    else:
        restore_original_installer(created_volume)
    progress('complete', 1, 1, 'USB creation completed')
    print('\nUSB installer created successfully. Eject with: diskutil eject ' + args.disk)
    print('On a compatible Intel Mac: start while holding Option, then select the ' + RELEASE['title'] + ' installer.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    commands = parser.add_subparsers(dest='command', required=True)
    doctor = commands.add_parser('doctor', help='Report requirements without downloading or writing USB media')
    doctor.add_argument('--json', action='store_true', help='Output machine-readable diagnostic information')
    prepare = commands.add_parser('download', help='Download matching Apple files and prepare selected macOS')
    prepare.add_argument('--version', action='version', version=VERSION)
    create = commands.add_parser('usb', help='Create USB; erases only after explicit confirmation')
    create.add_argument('--version', action='version', version=VERSION)
    create.add_argument('--list', action='store_true', help='List external physical disks and exit')
    create.add_argument('--disk', help='Whole external physical disk, e.g. /dev/disk4')
    create.add_argument('--app', type=Path, help='Complete original installer app for selected macOS')
    create.add_argument('--check-only', action='store_true', help='Check installer and target without erasing')
    combined = commands.add_parser('all', help='Download or reuse installer, then guide USB creation')
    combined.add_argument('--version', action='version', version=VERSION)
    combined.add_argument('--disk', help='Whole external USB disk; otherwise prompt after listing disks')
    combined.add_argument('--download-only', action='store_true', help='Prepare installer and exit')
    combined.add_argument('--check-only', action='store_true', help='Prepare installer and check USB without erasing')
    combined.add_argument('--repair-usb', action='store_true', help='Restore original Apple installer code on existing USB without erasing')
    combined.add_argument('--doctor', action='store_true', help='Report requirements and exit')
    combined.add_argument('--list-releases', action='store_true', help='Show supported releases and available download methods')
    for command in (doctor, prepare, create, combined):
        command.add_argument('--macos', type=normalize_release, choices=list(RELEASES), default='catalina',
                             help='Target macOS name or version; default catalina')
    for command in (prepare, combined):
        command.add_argument('--source', type=Path, help='Import an original full .app, Apple installer .dmg, or .pkg')
        command.add_argument('--download-files-only', action='store_true', help='Download Apple files without assembling or writing USB')
    args = parser.parse_args()
    configure_release(args.macos)
    if getattr(args, 'source', None) and getattr(args, 'download_files_only', False):
        parser.error('--source imports a local installer; it cannot be combined with --download-files-only.')
    if sys.platform != 'darwin':
        fail('These scripts require macOS.')
    if args.command == 'all' and args.list_releases:
        for key, release in RELEASES.items():
            source = 'Apple catalog download' if release.get('catalog') else 'Apple DMG download' if release.get('url') else 'Local original installer required'
            print('{} ({}) — {} — {}'.format(key, release['version'], source, release['method']))
        return
    if args.command == 'doctor' or (args.command == 'all' and args.doctor):
        report = {
            'version': VERSION, 'macos': platform.mac_ver()[0], 'architecture': platform.machine(),
            'python': platform.python_version(), 'work_directory': str(WORK),
            'selected_release': RELEASE_KEY, 'selected_version': RELEASE['version'],
            'installer_present': APP.is_dir(),
            'tools': {name: Path(path).is_file() for name, path in {
                'curl': '/usr/bin/curl', 'diskutil': '/usr/sbin/diskutil',
                'codesign': '/usr/bin/codesign', 'hdiutil': '/usr/bin/hdiutil',
                'ditto': '/usr/bin/ditto'}.items()}}
        for key, command in [('command_line_tools', ['/usr/bin/xcode-select', '-p']),
                             ('intel_execution', ['/usr/bin/arch', '-x86_64', '/usr/bin/true'])]:
            report[key] = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        print(json.dumps(report, indent=2))
        return
    # A second invocation must not race assembly or erasure in another terminal.
    WORK.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with (WORK_ROOT / '.macos-usb.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('Another macOS USB operation is already running in this workspace. Wait for it to finish.')
        if args.command == 'all':
            if args.repair_usb:
                if args.download_only or args.check_only or args.download_files_only or args.source:
                    fail('--repair-usb cannot be combined with --download-only or --check-only.')
                repair_usb(args)
                return
            if args.disk and not re.fullmatch(r'/dev/disk[0-9]+', args.disk):
                fail('Specify a whole disk such as /dev/disk4, not a partition.')
            download(args)
            if args.download_only or args.download_files_only:
                return
            if not args.disk:
                run(['/usr/sbin/diskutil', 'list', 'external', 'physical'])
                args.disk = terminal_prompt('Enter the USB whole disk (e.g. /dev/disk4), or press Enter to stop: ')
                if not args.disk:
                    print('Installer ready. USB creation cancelled; no disk erased.')
                    return
            args.app = APP
            args.list = False
            usb(args)
        else:
            (download if args.command == 'download' else usb)(args)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print('\nERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        sys.exit(130)
