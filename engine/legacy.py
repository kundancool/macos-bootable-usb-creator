"""Prepare an original full installer app from a local app/DMG/PKG or Apple DMG.

Packages are expanded without running their installer scripts. This module
never erases disks; USB creation remains in the shared engine.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import plistlib
import shutil
import subprocess
import tempfile


@contextmanager
def mounted(image, work, run):
    with tempfile.TemporaryDirectory(prefix='mount-', dir=work) as directory:
        mount = Path(directory) / 'image'; mount.mkdir()
        attached = False
        try:
            run(['/usr/bin/hdiutil', 'verify', image])
            run(['/usr/bin/hdiutil', 'attach', image, '-readonly', '-nobrowse', '-mountpoint', mount])
            attached = True
            yield mount
        finally:
            if attached:
                run(['/usr/bin/hdiutil', 'detach', mount])


def app_candidates(folder, name):
    return sorted((p for p in Path(folder).rglob(name) if p.is_dir()), key=lambda p: len(p.parts))


def preserve_original(app, work, run):
    original = Path(work) / 'original' / app.name
    if original.exists():
        return original
    original.parent.mkdir(exist_ok=True)
    # Copy only code/resources, not another multi-gigabyte payload.
    shutil.copytree(app, original, symlinks=True,
                    ignore=lambda directory, names: ['SharedSupport'] if Path(directory) == app / 'Contents' else [])
    return original


def prepare(source, work, release, run, progress):
    source = Path(source).expanduser().resolve()
    work = Path(work)
    final = work / release['app']
    if not source.exists():
        raise RuntimeError('Installer source does not exist: ' + str(source))
    free = shutil.disk_usage(work).free
    # Package expansion can temporarily require both extracted and staged data.
    required = (source.stat().st_size * 2 + 2 * 1024**3) if source.is_file() else 12 * 1024**3
    if free < required:
        raise RuntimeError('Need {:.1f} GiB free for this installer import/extraction; {:.1f} GiB available.'.format(required / 1024**3, free / 1024**3))

    def copy_app(app, staging, search_root=None):
        if app.name != release['app']:
            raise RuntimeError('Installer name does not match the selected release: ' + app.name)
        progress('assembly', None, None, 'Copying original installer app')
        destination = staging / release['app']
        if search_root and Path(app).is_relative_to(Path(search_root)):
            shutil.move(str(app), destination)
        else:
            run(['/usr/bin/ditto', app, destination])
        shared = destination / 'Contents/SharedSupport'
        shared.mkdir(exist_ok=True)
        esd = shared / 'InstallESD.dmg'
        if not esd.is_file() and search_root:
            images = list(Path(search_root).rglob('InstallESD.dmg'))
            if len(images) != 1:
                raise RuntimeError('Could not uniquely locate the full InstallESD.dmg in this package.')
            if Path(images[0]).is_relative_to(staging):
                shutil.move(str(images[0]), esd)
            else:
                run(['/usr/bin/ditto', images[0], esd])
        if not esd.is_file() or esd.stat().st_size < 100 * 1024**2:
            raise RuntimeError('This is not a full installer: missing the full SharedSupport/InstallESD.dmg payload.')
        if release['method'] != 'restore':
            tool = destination / 'Contents/Resources/createinstallmedia'
            if not tool.is_file() or not os.access(tool, os.X_OK):
                raise RuntimeError('This installer lacks createinstallmedia. Use an original full installer for the selected release.')
        return destination

    def expand_pkg(package, staging):
        progress('extraction', None, None, 'Expanding package; installer scripts are not executed')
        expanded = staging / 'expanded'
        run(['/usr/sbin/pkgutil', '--expand-full', package, expanded])
        apps = app_candidates(expanded, release['app'])
        if len(apps) != 1:
            raise RuntimeError('Package did not contain one matching full installer app for ' + release['title'])
        return copy_app(apps[0], staging, expanded)

    with tempfile.TemporaryDirectory(prefix='import-', dir=work) as directory:
        staging = Path(directory)
        if source.is_dir() and source.suffix.lower() == '.app':
            app = copy_app(source, staging)
        elif source.suffix.lower() == '.pkg':
            app = expand_pkg(source, staging)
        elif source.suffix.lower() == '.dmg':
            with mounted(source, work, run) as mount:
                apps = list(mount.glob(release['app']))
                packages = list(mount.glob('*.pkg'))
                if len(apps) == 1:
                    app = copy_app(apps[0], staging)
                elif len(packages) == 1:
                    app = expand_pkg(packages[0], staging)
                else:
                    raise RuntimeError('Expected an Apple installer-distribution DMG containing a full app or one installer PKG. A bare InstallESD.dmg alone is insufficient for this import.')
        else:
            raise RuntimeError('Choose a full .app, an Apple installer-distribution .dmg, or its .pkg.')
        if release['method'] != 'restore':
            signature = subprocess.run(['/usr/bin/codesign', '-dv', str(app)], stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
            if signature.returncode or 'Signature=adhoc' in signature.stdout:
                raise RuntimeError('The supplied installer app has no original signing metadata or was already re-signed. Obtain an original full installer; this import cannot recover missing Apple signatures.')
        preserve_original(app, work, run)
        (work / 'prepared.plist').write_bytes(plistlib.dumps({'release': release['version'], 'app': release['app'], 'source': str(source)}))
        app.rename(final)
    progress('assembly', 1, 1, 'Installer prepared')
    return final
