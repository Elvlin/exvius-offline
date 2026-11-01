"""Compare the Android table reader with the recovered CBC decoder on real tables."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'source/exvius')]
from decode_client_data import getter_manifest, TRIPLET
from ffbe_crypto import IV, cbc_decrypt, key16


class GameTableReader(unittest.TestCase):
    def test_large_original_tables_decode_identically(self):
        source = ROOT / 'source/memorial/android/src/main/java/com/exvius/local/LocalGameBridge.java'
        method = re.search(r'public static String decodeGameTable\(.*?return result.toString\(\);\n    }',
                           source.read_text(), re.S)[0]
        # Android's Base64 API and the JDK API accept the same canonical input.
        method = method.replace('android.util.Base64.decode(line, android.util.Base64.DEFAULT)',
                                'java.util.Base64.getDecoder().decode(line)')
        main = '''public static void main(String[] a) throws Exception {
            byte[] result = decodeGameTable(a[0], a[1], a[2]).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            byte[] hash = java.security.MessageDigest.getInstance("SHA-256").digest(result);
            for (byte b : hash) System.out.printf("%02x", b);
        }'''
        java = Path(os.environ.get('JAVA_HOME', 'C:/Program Files/Microsoft/jdk-11.0.12.7-hotspot')) / 'bin'
        native = (ROOT / 'source/build/android/client/lib/arm64-v8a/libgame.so').read_bytes()
        manifest = getter_manifest(native)
        for match in TRIPLET.finditer(native):
            table, token, key = (v.decode() for v in match.groups())
            manifest[token] = {'table': table, 'token': token, 'key': key}
        with tempfile.TemporaryDirectory(prefix='table-reader-', dir=ROOT / 'source/build') as temporary:
            folder = Path(temporary)
            harness = folder / 'TableReader.java'
            harness.write_text('import java.io.File; public class TableReader {' + method + main + '}')
            subprocess.run([str(java / 'javac'), str(harness)], check=True, capture_output=True)
            for table in ('F_UNIT_MST', 'F_MISSION_MST', 'F_MAGIC_MST'):
                entry = next(v for v in manifest.values() if v['table'] == table)
                candidates = list((ROOT / 'data/client/files/mst').glob('Ver*_' + entry['token'] + '.dat'))
                path = max(candidates, key=lambda p: int(p.stem.split('_')[0][3:]))
                overlay = ROOT / 'data/overlay/mst' / path.name
                if overlay.is_file():
                    path = overlay
                digest = hashlib.sha256()
                for index, line in enumerate(path.read_text().splitlines()):
                    plain = cbc_decrypt(key16(entry['key']), line)
                    padding = plain[-1]
                    self.assertTrue(1 <= padding <= 16 and plain[-padding:] == bytes([padding]) * padding)
                    if index:
                        digest.update(b'\n')
                    digest.update(plain[:-padding])
                result = subprocess.check_output([str(java / 'java'), '-cp', str(folder), 'TableReader',
                                                  str(path), entry['key'], IV.decode()], text=True)
                self.assertEqual(result, digest.hexdigest(), table)


if __name__ == '__main__':
    unittest.main()
