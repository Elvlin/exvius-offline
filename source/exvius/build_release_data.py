"""Build the complete static data download from the same sources as the native cache installer."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CONTENT = {'mst', 'en', 'common_lang', 'localized_texts', 'homeMarquee'}
ASSETS = 'https://github.com/Elvlin/exvius-offline/releases/download'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inputs():
    files = {}
    # Keep the established precedence: preserved originals override recovered
    # files, and accepted repairs override both. Never include a player save.
    for folder in ('memorial_fill', 'client/files', 'overlay'):
        base = ROOT / 'data' / folder
        for path in sorted(base.rglob('*')):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(base)
                if relative.parts[0] in CONTENT:
                    files['native/' + relative.as_posix()] = path
    for folder in ('mst_decoded', 'text_decoded', 'cpk_extract', 'gacha_community/art'):
        base = ROOT / 'data' / folder
        for path in sorted(base.rglob('*')):
            if path.is_file() and not path.is_symlink():
                files['static/' + path.relative_to(ROOT / 'data').as_posix()] = path
    version_source = ROOT / 'data/overlay/shared_prefs/gamedata.xml'
    if not version_source.is_file():
        version_source = ROOT / 'data/client/shared_prefs/gamedata.xml'
    version_root = ET.parse(version_source).getroot()
    clean = ET.Element('map')
    registry = {}
    for row in version_root:
        name = row.get('name', '')
        if name.startswith('keyF_'):
            if row.tag != 'string':
                raise ValueError('Unexpected native resource version type: ' + name)
            registry[name] = row.text or ''
            ET.SubElement(clean, 'string', {'name': name}).text = row.text
    files['static/client/shared_prefs/gamedata.xml'] = ET.tostring(clean, encoding='utf-8', xml_declaration=True)
    files['metadata/registry.json'] = json.dumps(registry, sort_keys=True).encode()
    return files


def build(output, tag, revision, limit):
    output.mkdir(parents=True, exist_ok=True)
    files = inputs()
    manifest = {'schema': 1, 'revision': revision, 'version': '2026.10.30.' + str(revision),
                'minAppVersionCode': 9001, 'packs': []}
    archive = None
    raw = 0
    number = 0

    def finish():
        archive.close()
        size = target.stat().st_size
        if size >= 2 * 1024 ** 3:
            raise ValueError('GitHub release file exceeds its size limit: ' + target.name)
        manifest['packs'].append({'id': 'data-' + str(number).zfill(3),
            'url': ASSETS + '/' + tag + '/' + target.name,
            'size': size, 'unpackedSize': raw, 'sha256': sha256(target)})
        print(f'Finished {target.name}: {size / 1e6:.1f} MB, expanded {raw / 1e6:.1f} MB', flush=True)

    # Put runtime tables and version metadata first, followed by native assets.
    ordered = sorted(files, key=lambda key: (key.startswith('native/'), key))
    for name in ordered:
        source = files[name]
        size = source.stat().st_size if isinstance(source, Path) else len(source)
        if size > limit - 4 * 1024 * 1024:
            raise ValueError('A single resource exceeds the pack size: ' + name)
        if archive is None or raw + size > limit - 4 * 1024 * 1024:
            if archive is not None:
                finish()
            number += 1
            target = output / f'exvius-data-{number:03}.zip'
            archive = zipfile.ZipFile(target, 'w', allowZip64=True)
            raw = 0
        info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED if name.endswith(('.json', '.ndjson', '.xml', '.csv', '.txt')) else zipfile.ZIP_STORED
        info.external_attr = 0o100644 << 16
        with archive.open(info, 'w', force_zip64=True) as destination:
            if isinstance(source, Path):
                with source.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        destination.write(block)
            else:
                destination.write(source)
        raw += size
    if archive is not None:
        finish()
    manifest['downloadBytes'] = sum(p['size'] for p in manifest['packs'])
    manifest['installedBytes'] = sum(p['unpackedSize'] for p in manifest['packs'])
    manifest['files'] = len(files)
    destination = ROOT / 'data/latest.json'
    destination.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Complete: {len(files)} files, {len(manifest["packs"])} parts, {manifest["downloadBytes"] / 1e9:.2f} GB', flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'source/build/distribution/assets')
    parser.add_argument('--tag', default='v0.1.0')
    parser.add_argument('--revision', type=int, default=1)
    parser.add_argument('--pack-mib', type=int, default=1400)
    args = parser.parse_args()
    build(args.output, args.tag, args.revision, args.pack_mib * 1024 * 1024)
