"""Offline safety and regression tests. No real disk operations are executed."""
import hashlib
import importlib.util
from pathlib import Path
import plistlib
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('engine', ROOT / 'engine/macos_usb.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class DiskSafety(unittest.TestCase):
    def setUp(self):
        self.disk = {'DeviceNode': '/dev/disk4', 'Internal': False, 'WholeDisk': True,
                     'VirtualOrPhysical': 'Physical', 'TotalSize': 64_000_000_000,
                     'WritableMedia': True}

    def test_external_disk_accepted(self):
        with patch.object(engine, 'disk_info', return_value=self.disk):
            self.assertEqual(engine.external_disk('/dev/disk4'), self.disk)

    def test_unsafe_and_unknown_disks_rejected(self):
        for change in ({'Internal': True}, {'Internal': None}, {'WholeDisk': False},
                       {'WholeDisk': None}, {'VirtualOrPhysical': 'Virtual'},
                       {'TotalSize': 1}, {'WritableMedia': False},
                       {'DeviceNode': '/dev/disk0'}):
            with self.subTest(change=change), patch.object(engine, 'disk_info', return_value=dict(self.disk, **change)):
                with self.assertRaises(RuntimeError):
                    engine.external_disk('/dev/disk4')

    def test_legacy_whole_key(self):
        self.disk['Whole'] = self.disk.pop('WholeDisk')
        with patch.object(engine, 'disk_info', return_value=self.disk):
            engine.external_disk('/dev/disk4')

    def test_reuse_requires_single_hfs_partition_on_same_disk(self):
        layout = {'Content': 'GUID_partition_scheme', 'Partitions': [
            {'Content': 'EFI', 'DeviceIdentifier': 'disk4s1'},
            {'Content': 'Apple_HFS', 'DeviceIdentifier': 'disk4s2'}]}
        def result(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=plistlib.dumps({'AllDisksAndPartitions': [layout]}))
        with patch.object(engine.subprocess, 'run', side_effect=result):
            self.assertEqual(engine.reusable_partition('/dev/disk4'), '/dev/disk4s2')
            self.assertIsNone(engine.reusable_partition('/dev/disk8'))
            layout['Partitions'].append({'Content': 'Apple_HFS', 'DeviceIdentifier': 'disk4s3'})
            self.assertIsNone(engine.reusable_partition('/dev/disk4'))

    def test_malformed_repair_identifiers_do_not_execute_commands(self):
        for disk in (None, '/dev/disk4s2', 'disk4', '/dev/disk4;bad'):
            class Args:
                pass
            args = Args()
            args.disk = disk
            with patch.object(engine, 'original_image'), patch.object(engine.subprocess, 'run') as run:
                with self.assertRaises(RuntimeError):
                    engine.repair_usb(args)
                run.assert_not_called()


class Downloads(unittest.TestCase):
    def test_apple_url_validation(self):
        self.assertEqual(engine.apple_url('http://swcdn.apple.com/file'), 'https://swcdn.apple.com/file')
        for url in ('file:///etc/passwd', 'https://apple.com.evil.example/file', 'https://example.com/file'):
            with self.assertRaises(RuntimeError):
                engine.apple_url(url)

    def test_complete_part_recovered_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'file'
            part = Path(directory) / 'file.part'
            part.write_bytes(b'valid')
            with patch.object(engine, 'run') as run:
                engine.fetch('https://example.test', dest, 5, hashlib.sha1(b'valid').digest())
                run.assert_not_called()
            self.assertEqual(dest.read_bytes(), b'valid')
            self.assertFalse(part.exists())

    def test_partial_download_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'file'
            part = Path(directory) / 'file.part'
            part.write_bytes(b'ab')
            def download(args, **kwargs):
                self.assertIn('--continue-at', args)
                part.write_bytes(b'abcd')
            with patch.object(engine, 'run', side_effect=download):
                engine.fetch('https://example.test', dest, 4, hashlib.sha1(b'abcd').digest())
            self.assertEqual(dest.read_bytes(), b'abcd')

    def test_failed_validation_never_replaces_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'file'
            dest.write_bytes(b'old')
            def download(args, **kwargs):
                (Path(directory) / 'file.part').write_bytes(b'bad')
            with patch.object(engine, 'run', side_effect=download):
                with self.assertRaises(RuntimeError):
                    engine.fetch('https://example.test', dest, 3, hashlib.sha1(b'new').digest())
            self.assertEqual(dest.read_bytes(), b'old')

    def test_chunk_verification_and_trailing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / 'payload'
            manifest = Path(directory) / 'manifest'
            manifest.write_bytes(struct.pack('<4sIBBBBQQQ', b'CNKL', 36, 1, 1, 2, 0, 1, 36, 72)
                                 + struct.pack('<I32s', 4, hashlib.sha256(b'good').digest()) + b'signature')
            for content, valid in ((b'good', True), (b'bad!', False), (b'goodextra', False), (b'goo', False)):
                payload.write_bytes(content)
                self.assertEqual(engine.verify_chunks(payload, manifest), valid)
            manifest.write_bytes(b'broken')
            with self.assertRaises(RuntimeError):
                engine.verify_chunks(payload, manifest)

    def test_stale_catalog_digest_requires_matching_apple_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'file'
            dest.write_bytes(b'good')
            manifest = Path(directory) / 'file.integrityDataV1'
            manifest.write_bytes(struct.pack('<4sIBBBBQQQ', b'CNKL', 36, 1, 1, 2, 0, 1, 36, 72)
                                 + struct.pack('<I32s', 4, hashlib.sha256(b'good').digest()) + b'signature')
            with patch.object(engine, 'run') as run:
                engine.fetch('https://swcdn.apple.com/file', dest, 4, '0' * 40,
                             'https://swcdn.apple.com/file.integrityDataV1', manifest.stat().st_size)
                run.assert_not_called()


class Restoration(unittest.TestCase):
    def test_original_code_restored_without_replacing_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'work'; work.mkdir()
            product = work / 'product'; product.mkdir()
            (product / 'BaseSystem.dmg').write_bytes(b'image')
            (product / 'download-manifest.plist').write_bytes(plistlib.dumps({
                'packages': [{'URL': 'https://swcdn.apple.com/BaseSystem.dmg', 'Size': 5}]}))
            original = root / 'original' / engine.APP.name
            for folder in ('Resources', 'MacOS'):
                (original / 'Contents' / folder).mkdir(parents=True, exist_ok=True)
            (original / 'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': 'com.apple.InstallAssistant.Catalina', 'CFBundleVersion': '15703'}))
            for relative in ('Resources/createinstallmedia', 'MacOS/InstallAssistant', 'MacOS/InstallAssistant_springboard'):
                path = original / 'Contents' / relative
                path.write_bytes(b'original signed code'); path.chmod(0o755)
            volume = root / 'volume'; volume.mkdir()
            import shutil
            destination = volume / engine.APP.name
            shutil.copytree(original, destination)
            shared = destination / 'Contents/SharedSupport'; shared.mkdir()
            for name in engine.REQUIRED:
                (shared / ('InstallESD.dmg' if name == 'InstallESDDmg.pkg' else name)).write_bytes(b'payload')
            (shared / 'InstallInfo.plist').write_bytes(plistlib.dumps({'System Image Info': {'version': '10.15.7'}}))
            (destination / 'Contents/MacOS/InstallAssistant').write_bytes(b'host modified code')
            def run(args, **kwargs):
                args = list(map(str, args))
                if args[:2] == ['/usr/bin/hdiutil', 'attach']:
                    mount = Path(args[args.index('-mountpoint') + 1])
                    shutil.copytree(original, mount / engine.APP.name)
                elif args[:2] == ['/usr/bin/sudo', '/usr/bin/ditto']:
                    shutil.copytree(args[2], args[3], dirs_exist_ok=True)
            def codesign(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, stdout='CDHash=original\nSignature size=4628\n')
            with patch.object(engine, 'WORK', work), patch.object(engine, 'run', side_effect=run), \
                    patch.object(engine.subprocess, 'run', side_effect=codesign):
                engine.restore_original_installer(volume)
            self.assertEqual((shared / 'InstallESD.dmg').read_bytes(), b'payload')
            self.assertEqual((destination / 'Contents/MacOS/InstallAssistant').read_bytes(), b'original signed code')

    def test_missing_original_fails_before_repair(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(engine, 'WORK', Path(directory)):
            with self.assertRaises(RuntimeError):
                engine.original_image()

    def test_manifest_image_size_checked(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(engine, 'WORK', Path(directory)):
            folder = Path(directory) / 'product'
            folder.mkdir()
            image = folder / 'BaseSystem.dmg'
            image.write_bytes(b'image')
            manifest = {'packages': [{'URL': 'https://swcdn.apple.com/BaseSystem.dmg', 'Size': 5}]}
            (folder / 'download-manifest.plist').write_bytes(plistlib.dumps(manifest))
            self.assertEqual(engine.original_image(), image)
            image.write_bytes(b'bad')
            with self.assertRaises(RuntimeError):
                engine.original_image()

    def test_redirected_installer_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            volume = root / 'volume'; volume.mkdir()
            outside = root / 'outside'; outside.mkdir()
            (volume / engine.APP.name).symlink_to(outside, target_is_directory=True)
            with patch.object(engine, 'run') as run:
                with self.assertRaises(RuntimeError):
                    engine.restore_original_installer(volume)
                run.assert_not_called()


class Release(unittest.TestCase):
    def test_legacy_import_rejects_incomplete_app_without_running_installer(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'Install OS X Mavericks.app'
            (source / 'Contents').mkdir(parents=True)
            work = root / 'work'; work.mkdir()
            import shutil
            calls = []
            def run(args, **kwargs):
                calls.append(list(map(str, args)))
                if str(args[0]) == '/usr/bin/ditto':
                    shutil.copytree(args[1], args[2])
            with patch.object(engine.legacy.shutil, 'disk_usage', return_value=SimpleNamespace(free=50 * 1024**3)):
                with self.assertRaisesRegex(RuntimeError, 'not a full installer'):
                    engine.legacy.prepare(source, work, engine.RELEASES['mavericks'], run, lambda *args: None)
            self.assertTrue(source.exists())
            self.assertFalse((work / source.name).exists())
            self.assertTrue(all(call[0] == '/usr/bin/ditto' for call in calls))

    def test_all_nine_releases_have_correct_routes(self):
        self.assertEqual(len(engine.RELEASES), 9)
        self.assertEqual(engine.RELEASES['lion']['method'], 'restore')
        self.assertEqual(engine.RELEASES['mountain-lion']['method'], 'restore')
        self.assertNotIn('url', engine.RELEASES['mavericks'])
        for key in ('high-sierra', 'mojave', 'catalina'):
            self.assertTrue(engine.RELEASES[key]['catalog'])
        for release in engine.RELEASES.values():
            if release.get('url'):
                self.assertTrue(engine.apple_url(release['url']).startswith('https://'))

    def test_release_aliases(self):
        self.assertEqual(engine.normalize_release('10.13'), 'high-sierra')
        self.assertEqual(engine.normalize_release('Mountain Lion'), 'mountain-lion')
        self.assertEqual(engine.normalize_release('elcapitan'), 'el-capitan')
        with self.assertRaises(ValueError):
            engine.normalize_release('big-sur')

    def test_machine_readable_progress_contains_measured_values(self):
        import io, json
        from contextlib import redirect_stdout
        stream = io.StringIO()
        with patch.dict(engine.os.environ, {'MACOS_USB_EVENTS': '1'}), redirect_stdout(stream):
            engine.progress('download', 50, 100, 'test-file')
        line = stream.getvalue().strip()
        self.assertTrue(line.startswith('::progress::'))
        event = json.loads(line.removeprefix('::progress::'))
        self.assertEqual(event['current'], 50)
        self.assertEqual(event['total'], 100)

    def test_source_archive_allowlist_excludes_local_data(self):
        spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts/package-release.py')
        release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
        for path in release.source_files():
            relative = path.relative_to(ROOT)
            self.assertNotIn('catalina-installer', relative.parts)
            self.assertNotIn('.git', relative.parts)
            self.assertNotIn('.build', relative.parts)
            self.assertNotIn('dist', relative.parts)
            self.assertNotIn(path.suffix, ('.dmg', '.pkg', '.part', '.log'))


if __name__ == '__main__':
    unittest.main()
