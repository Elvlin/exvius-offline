"""Import completed native-browser downloads from preserved Global and JP archives.

The browser owns network retrieval. This importer never overwrites originals or
accepts an HTML error page as a game resource. The recovery queue records the
original archive URL for each requested catalogue path. Its stable location is
data/web_sources/global-content-recovery.json.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
from cricodecs import cpk


def valid(path):
    head = path.open('rb').read(8)
    if path.suffix == '.cpk':
        try:
            archive = cpk.load(str(path))
            return bool(archive.file_infos())
        except Exception:
            return False
    return head[:4] in (b'@UTF', b'AFS2', b'CRID', b'OggS', b'RIFF', b'\x89PNG')


def import_jp_archive(metadata, downloads):
    """Retain checksum-verified original packages from the preserved JP archive."""
    records = json.loads(metadata.read_text(encoding='utf8'))['files']
    folder = ROOT / 'data/jp_andapp'
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    imported, pending = 0, 0
    for row in records:
        name = row['name']
        if Path(name).name != name or not name.endswith('.cpk'):
            continue
        target = folder / name
        source = target if target.is_file() else downloads / name
        if not source.is_file():
            pending += 1
            continue
        data = source.read_bytes()
        if (len(data) != row['size'] or
                hashlib.sha1(data).hexdigest() != row['sha1'] or
                hashlib.md5(data).hexdigest() != row['md5'] or not valid(source)):
            raise ValueError('Original archive checksum or CPK validation failed: ' + name)
        if source != target:
            shutil.move(str(source), str(target))
            imported += 1
        manifest[name] = {**manifest.get(name, {}), **row,
                          'source': row['url'],
                          'sha256': hashlib.sha256(data).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding='utf8')
    print(json.dumps({'jp_imported': imported, 'jp_pending': pending}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, default=ROOT / 'data/web_sources/global-content-recovery.json')
    parser.add_argument('--downloads', type=Path, default=Path.home() / 'Downloads')
    parser.add_argument('--first', type=int, default=0)
    parser.add_argument('--count', type=int, default=676)
    parser.add_argument('--pending', action='store_true')
    parser.add_argument('--jp-archive', type=Path,
                        help='Import native browser downloads using preserved JP archive checksums.')
    args = parser.parse_args()
    if args.jp_archive:
        import_jp_archive(args.jp_archive, args.downloads)
        return
    rows = json.loads(args.queue.read_text(encoding='utf8'))
    imported, rejected, pending = [], [], []
    stage = ROOT / 'data/memorial_fill'
    manifest_path = stage / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf8')) if manifest_path.exists() else []
    staged = {row['path']: row for row in manifest}
    manifest_changed = False
    for row in rows:
        language = row['url'].split('dlc_assets_prod%2F', 1)[1].split('%2F', 1)[0]
        target = ROOT / 'data/client/files' / language / row['dir'] / row['file']
        alias = stage / language / row['dir'] / row['file']
        if target.exists() or alias.exists() or row.get('builtin') and (ROOT / row['builtin']).is_file():
            continue
        actual_file = row.get('actual_file', row['file'])
        original = (ROOT / 'data/client/files' / row.get('actual_lang', language)
                    / row.get('actual_dir', row['dir']) / actual_file)
        source = args.downloads / actual_file
        if not source.exists() and not original.exists():
            pending.append([row['dir'], row['file'], language])
            continue
        if not valid(source if source.exists() else original):
            rejected.append(row['file'])
            continue
        if not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(original))
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        if original != target:
            alias.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, alias)
            key = alias.relative_to(stage).as_posix()
            staged[key] = {'path': key, 'source': original.relative_to(ROOT / 'data').as_posix(),
                           'source_url': row.get('actual_url', row['url']),
                           'source_sha256': digest, 'sg_members_added': 0,
                           'bytes': alias.stat().st_size, 'sha256': digest,
                           'original_global_alias': True}
            manifest_changed = True
        else:
            alias = target
        imported.append({'path': alias.relative_to(ROOT).as_posix(), 'sha256': digest,
                         'original': original.relative_to(ROOT).as_posix(),
                         'url': row.get('actual_url', row['url']), 'bytes': alias.stat().st_size})
    if manifest_changed:
        manifest_path.write_text(json.dumps(list(staged.values()), indent=1), encoding='utf8')
    if imported:
        with (ROOT / 'logs/catalogue-recovery-20261028.jsonl').open('a', encoding='utf8') as log:
            for row in imported:
                log.write(json.dumps(row) + '\n')
    if args.pending:
        print(json.dumps(pending[args.first:args.first + args.count]))
    else:
        print(json.dumps({'imported': len(imported), 'pending': len(pending), 'rejected': rejected}))


if __name__ == '__main__':
    main()
