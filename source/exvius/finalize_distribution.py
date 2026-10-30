"""Verify a release APK and finalize its static update metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from build_release_data import sha256

ROOT = Path(__file__).resolve().parents[2]


def finalize(version, client_version, version_code):
    apk = ROOT / f'source/build/distribution/assets/exvius-offline-v{version}.apk'
    manifest_path = ROOT / 'data/latest.json'
    manifest = json.loads(manifest_path.read_text())
    with zipfile.ZipFile(apk) as archive:
        assert not any(name.startswith('assets/chaquopy/exvius_pack') for name in archive.namelist())
        with zipfile.ZipFile(ROOT / 'source/build/android/client/assets/chaquopy/app.imy') as python:
            assert not any(name.startswith('exvius_pack/') for name in python.namelist()), 'Game data is still inside the APK'
        game_hash = hashlib.sha256(archive.read('lib/arm64-v8a/libgame.so')).hexdigest()
        with zipfile.ZipFile(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk') as original:
            assert game_hash == hashlib.sha256(original.read('lib/arm64-v8a/libgame.so')).hexdigest()
        assert archive.read('lib/arm64-v8a/libexviustest.js.so') == (ROOT / 'source/build/android/android_test.bundle.js').read_bytes()
    for pack in manifest['packs']:
        path = ROOT / 'source/build/distribution/assets' / pack['url'].rsplit('/', 1)[-1]
        assert path.stat().st_size == pack['size']
        with zipfile.ZipFile(path) as archive:
            assert sum(row.file_size for row in archive.infolist()) == pack['unpackedSize']
            assert all(row.filename.startswith(('native/', 'static/', 'metadata/')) for row in archive.infolist())
            assert not any('/state/' in row.filename or '.jks' in row.filename for row in archive.infolist())
    app = {'version': version, 'versionName': client_version, 'versionCode': version_code,
           'url': f'https://github.com/Elvlin/exvius-offline/releases/download/v{version}/{apk.name}',
           'size': apk.stat().st_size, 'sha256': sha256(apk)}
    manifest['minAppVersionCode'] = version_code
    manifest['app'] = app
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    (ROOT / 'release/app.json').write_text(json.dumps(app, indent=2) + '\n')
    proof = {'apk': app, 'original_game_library_sha256': game_hash,
             'bundled_data_removed': True, 'data_parts': len(manifest['packs']),
             'download_bytes': manifest['downloadBytes'], 'installed_bytes': manifest['installedBytes']}
    (ROOT / 'logs/distribution-package-proof-20261030.json').write_text(json.dumps(proof, indent=2))
    print(f'Release ready: APK {app["size"] / 1e6:.1f} MB; game data {manifest["downloadBytes"] / 1e9:.2f} GB in {len(manifest["packs"])} parts.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='0.1.0')
    parser.add_argument('--client-version', default='9.0.0-offline.1')
    parser.add_argument('--version-code', type=int, default=9001)
    args = parser.parse_args()
    finalize(args.version, args.client_version, args.version_code)
