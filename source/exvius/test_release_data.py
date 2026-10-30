"""Check release path safety, save preservation, hashing and resource precedence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'source/build/distribution/tests'
BUILD.mkdir(parents=True, exist_ok=True)
JAVA = Path(os.environ.get('JAVA_HOME', 'C:/Program Files/Microsoft/jdk-11.0.12.7-hotspot')) / 'bin'
DRIVER = '''
import java.io.File;
import com.exvius.local.DataPack;
public class DataPackDriver {
    public static void main(String[] args) throws Exception {
        if (args[0].equals("hash")) System.out.println(DataPack.sha256(new File(args[1])));
        else DataPack.extract(new File(args[1]), new File(args[2]), Long.parseLong(args[3]));
    }
}
'''


class ReleaseData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (BUILD / 'DataPackDriver.java').write_text(DRIVER)
        # Model Android's POSIX atomic rename with the host's atomic move API.
        system = BUILD / 'android/system'
        system.mkdir(parents=True, exist_ok=True)
        (system / 'ErrnoException.java').write_text('package android.system; public class ErrnoException extends Exception {}')
        (system / 'Os.java').write_text('''package android.system;
public class Os {
 public static void rename(String from, String to) throws ErrnoException {
  try { java.nio.file.Files.move(java.nio.file.Paths.get(from), java.nio.file.Paths.get(to),
    java.nio.file.StandardCopyOption.REPLACE_EXISTING, java.nio.file.StandardCopyOption.ATOMIC_MOVE); }
  catch (java.io.IOException error) { throw new ErrnoException(); }
 }
}''')
        subprocess.run([str(JAVA / 'javac.exe'), '-d', str(BUILD),
            str(system / 'ErrnoException.java'), str(system / 'Os.java'),
            str(ROOT / 'source/memorial/android/src/main/java/com/exvius/local/DataPack.java'),
            str(BUILD / 'DataPackDriver.java')], check=True, capture_output=True)
        spec = importlib.util.spec_from_file_location('release_data', ROOT / 'source/exvius/build_release_data.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=BUILD)
        self.folder = Path(self.temporary.name).resolve()
        assert self.folder.is_relative_to(BUILD.resolve())
        self.files = self.folder / 'files'
        self.files.mkdir()
        self.save = self.files / 'exvius/state/campaign.json'
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b'keep this campaign')

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, entries):
        path = self.folder / 'data.zip'
        with zipfile.ZipFile(path, 'w') as output:
            for name, body in entries.items():
                info = zipfile.ZipInfo('entry')
                info.filename = name
                output.writestr(info, body)
        return path

    def java(self, *args):
        return subprocess.run([str(JAVA / 'java.exe'), '-cp', str(BUILD), 'DataPackDriver', *map(str, args)],
                              capture_output=True, text=True)

    def test_install_preserves_save_and_replaces_partial_file(self):
        entries = {'native/en/test.dat': b'game bytes', 'static/mst_decoded/F_UNIT_MST.ndjson': b'{}',
                   'metadata/registry.json': b'{"keyF_TEST":"1"}'}
        target = self.files / 'en/test.dat'
        target.parent.mkdir()
        target.write_bytes(b'old')
        (target.parent / 'test.dat.installing').write_bytes(b'interrupted')
        result = self.java('extract', self.archive(entries), self.files, sum(map(len, entries.values())))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), b'game bytes')
        self.assertFalse((target.parent / 'test.dat.installing').exists())
        self.assertEqual(self.save.read_bytes(), b'keep this campaign')

    def test_unsafe_paths_are_rejected_before_writing(self):
        for name in ['../campaign.json', '/absolute.dat', 'static/../../state/campaign.json',
                     'native/exvius/state/campaign.json', 'native/en/../../exvius/state/campaign.json',
                     'native\\en\\escape.dat']:
            with self.subTest(name=name):
                result = self.java('extract', self.archive({'native/en/safe.dat': b'good', name: b'bad'}), self.files, 7)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.files / 'en/safe.dat').exists())
                self.assertEqual(self.save.read_bytes(), b'keep this campaign')

    def test_wrong_expanded_size_is_rejected(self):
        result = self.java('extract', self.archive({'native/mst/test.dat': b'abc'}), self.files, 4)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.files / 'mst/test.dat').exists())

    def test_archive_hash_matches_independent_digest(self):
        path = self.archive({'native/en/test.dat': b'example'})
        result = self.java('hash', path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_downloaded_original_assets_keep_repairs_and_preserve_save(self):
        project = self.folder / 'project'
        original = project / 'repository snapshots/FFBE-Global-v9.0.0-original.apk'
        original.parent.mkdir(parents=True)
        with zipfile.ZipFile(original, 'w') as archive:
            archive.writestr('assets/cpk/en/boot.cpk', b'original art')
            archive.writestr('assets/font/font.ttf', b'original font')
            archive.writestr('assets/audience_network.dex', b'obsolete advertising')
        repair = project / 'data/apk_overlay/assets/cpk/en/boot.cpk'
        repair.parent.mkdir(parents=True)
        repair.write_bytes(b'accepted repair')
        with patch.object(self.builder, 'ROOT', project):
            pack, count = self.builder.client_assets(self.folder / 'packs', 'v0.1.1')
        self.assertEqual(count, 2)
        path = self.folder / 'packs/exvius-client-assets.zip'
        result = self.java('extract', path, self.files, pack['unpackedSize'])
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.files / 'exvius/data/static/client/game-assets.apk') as archive:
            self.assertEqual(archive.read('assets/cpk/en/boot.cpk'), b'accepted repair')
            self.assertEqual(archive.read('assets/font/font.ttf'), b'original font')
            self.assertNotIn('assets/audience_network.dex', archive.namelist())
        self.assertEqual(self.save.read_bytes(), b'keep this campaign')

    def test_builder_uses_accepted_override_and_excludes_private_data(self):
        project = self.folder / 'project'
        for directory, body in [('memorial_fill', 'recovered'), ('client/files', 'original'), ('overlay', 'repaired')]:
            p = project / 'data' / directory / 'en/test.dat'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        private = project / 'data/client/files/exvius/state/campaign.json'
        private.parent.mkdir(parents=True)
        private.write_text('private save')
        prefs = project / 'data/overlay/shared_prefs/gamedata.xml'
        prefs.parent.mkdir(parents=True)
        prefs.write_text('<map><string name="keyF_TEST">7</string><string name="private_login">secret</string></map>')
        with patch.object(self.builder, 'ROOT', project):
            files = self.builder.inputs()
        self.assertEqual(files['native/en/test.dat'].read_text(), 'repaired')
        self.assertFalse(any('state' in name for name in files))
        self.assertEqual(json.loads(files['metadata/registry.json']), {'keyF_TEST': '7'})
        self.assertNotIn(b'secret', files['static/client/shared_prefs/gamedata.xml'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
