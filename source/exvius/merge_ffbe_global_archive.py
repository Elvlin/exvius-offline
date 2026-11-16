"""Merge the completed Global RAR without replacing any existing source file.

One-off local recovery helper. Listing/plan first, then --apply after reviewing
conflicts and unmapped source candidates. This never changes runtime overlays.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / 'repository snapshots/ffbe_gl_contentserver_archive.rar'
EXPECTED_BYTES = 31344666514
EXPECTED_MD5 = 'fdf8e48ebe0626a8fadfd76a3510fc2c'
SEVEN = Path('C:/Program Files/7-Zip/7z.exe')
RAW = ROOT / 'data/client/files'
STAGE = ROOT / 'build/scratch/ffbe-global-archive-merge'
VARIANTS = ROOT / 'data/web_sources/global_archive_variants'
PLAN = ROOT / 'logs/ffbe-global-archive-merge-plan.json'
INTEGRITY = ROOT / 'logs/ffbe-global-archive-integrity.json'
RECEIPT = ROOT / 'logs/ffbe-global-archive-merge-20261110.jsonl'
FAMILIES = {'common_lang', 'en', 'mst', 'localized_texts', 'homeMarquee'}


def checked_child(base, relative):
    normalized = relative.replace('\\', '/')
    parts = PurePosixPath(normalized).parts
    if not parts or any(p in ('..', '.') or ':' in p for p in parts) or normalized.startswith('/'):
        raise ValueError('Unsafe archive path: ' + relative)
    path = base.joinpath(*parts).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError('Archive path escaped destination: ' + relative)
    return path


def crc(path):
    value = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value = zlib.crc32(chunk, value)
    return f'{value & 0xffffffff:08X}'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive():
    """One completed-download MD5 pass, cached only for the same local file."""
    stat = ARCHIVE.stat()
    if stat.st_size != EXPECTED_BYTES:
        raise RuntimeError('Archive is incomplete; leave the active downloader alone.')
    identity = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                'md5': EXPECTED_MD5}
    if INTEGRITY.exists() and json.loads(INTEGRITY.read_text(encoding='utf8')) == identity:
        return
    print('CHECKPOINT checking completed download MD5 once', flush=True)
    digest = hashlib.md5()
    with ARCHIVE.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != EXPECTED_MD5:
        raise ValueError('Completed archive MD5 does not match the published source. No import permitted.')
    INTEGRITY.write_text(json.dumps(identity) + '\n', encoding='utf8')
    print('CHECKPOINT published archive MD5 matched', flush=True)


def entries():
    """Read archive metadata only after the exact authorized download finishes."""
    if ARCHIVE.stat().st_size != EXPECTED_BYTES:
        raise RuntimeError('Archive is incomplete; leave the active downloader alone.')
    proc = subprocess.Popen([str(SEVEN), 'l', '-slt', '-ba', '-sccUTF-8', str(ARCHIVE)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf8', errors='strict')
    record = {}
    for line in proc.stdout:
        if line.strip():
            key, sep, value = line.rstrip('\r\n').partition(' = ')
            if sep:
                record[key] = value
        elif record:
            yield record
            record = {}
    if record:
        yield record
    error = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError('RAR listing failed: ' + error[-1500:])


def relative_native(member):
    parts = member.replace('\\', '/').split('/')
    if 'dlc_assets_prod' not in parts:
        return None
    pos = parts.index('dlc_assets_prod') + 1
    relative = '/'.join(parts[pos:])
    if pos >= len(parts) or parts[pos] not in FAMILIES:
        return None
    checked_child(RAW, relative)
    return relative


def candidate(member):
    name = member.lower()
    return (any(word in name for word in ('4f1zpy7v', 'brjd06sm', 'wje09yxd',
            'monster', 'encount', 'battle', 'response', 'sqlite'))
            or Path(name).suffix in ('.json', '.jsonl', '.ndjson', '.db', '.sqlite', '.sqlite3', '.dat', '.i'))


def plan():
    result = {'archive': ARCHIVE.relative_to(ROOT).as_posix(), 'bytes': EXPECTED_BYTES,
              'missing': [], 'conflicts': [], 'unmapped_candidates': [],
              'unmapped_extensions': {}, 'unmapped_examples': [], 'identical': 0}
    extensions = collections.Counter()
    destinations = {}
    for i, record in enumerate(entries(), 1):
        if record.get('Folder') == '+' or record.get('Attributes', '').startswith('D'):
            continue
        member = record.get('Path', '')
        if not member or 'Size' not in record:
            continue
        checked_child(STAGE, member)
        row = {'member': member, 'bytes': int(record['Size']), 'crc32': record.get('CRC', '').upper()}
        relative = relative_native(member)
        if relative is None:
            extensions[Path(member).suffix.lower() or '(none)'] += 1
            if candidate(member):
                result['unmapped_candidates'].append(row)
            elif len(result['unmapped_examples']) < 20:
                result['unmapped_examples'].append(member)
            continue
        row['relative'] = relative
        previous = destinations.get(relative)
        if previous:
            if previous != (row['bytes'], row['crc32']):
                raise ValueError('Two different archive members map to the same native path: ' + relative)
            continue
        destinations[relative] = row['bytes'], row['crc32']
        target = checked_child(RAW, relative)
        if not target.exists():
            result['missing'].append(row)
        elif (target.is_file() and target.stat().st_size == row['bytes']
              and row['crc32'] and crc(target) == row['crc32']):
            result['identical'] += 1
        else:
            row['existing_bytes'] = target.stat().st_size
            result['conflicts'].append(row)
        if i % 5000 == 0:
            print('CHECKPOINT listed', i, 'members', flush=True)
    result['unmapped_extensions'] = dict(extensions)
    PLAN.write_text(json.dumps(result, ensure_ascii=True, indent=2) + '\n', encoding='utf8')
    print('CHECKPOINT plan', {k: len(result[k]) for k in
          ('missing', 'conflicts', 'unmapped_candidates')}, 'identical', result['identical'], flush=True)
    return result


def batches(rows):
    batch, size = [], 0
    for row in rows:
        if batch and (len(batch) >= 256 or size + row['bytes'] > 512 * 1024 * 1024):
            yield batch
            batch, size = [], 0
        batch.append(row)
        size += row['bytes']
    if batch:
        yield batch


def apply(document, selected_variants, selected_native=None):
    """Only missing native files plus explicitly selected differing source rows."""
    available = {row['relative'].replace('\\', '/'): row for row in document['missing']}
    if selected_native is not None:
        unknown = selected_native - available.keys()
        if unknown:
            raise ValueError('Native selection is not in the missing-file plan: ' + ', '.join(sorted(unknown)))
    rows = [dict(row, destination='native') for relative, row in available.items()
            if selected_native is None or relative in selected_native]
    known = {row['member']: row for key in ('conflicts', 'unmapped_candidates') for row in document[key]}
    for member in selected_variants:
        if member not in known:
            raise ValueError('Variant was not a reviewed conflict/source candidate: ' + member)
        rows.append(dict(known[member], destination='variant'))
    STAGE.mkdir(parents=True, exist_ok=True)
    include = STAGE / 'selected-members.txt'
    with RECEIPT.open('a', encoding='utf8') as log:
        for number, batch in enumerate(batches(rows), 1):
            include.write_text(''.join(row['member'] + '\n' for row in batch), encoding='utf8')
            print('CHECKPOINT extracting batch', number, 'files', len(batch), flush=True)
            proc = subprocess.run([str(SEVEN), 'x', str(ARCHIVE), '-y', '-aos', '-spd',
                                   '-scsUTF-8', '-sccUTF-8', '-bso0', '-bsp0',
                                   '-o' + str(STAGE), '-i@' + str(include)],
                                  capture_output=True, text=True, encoding='utf8')
            if proc.returncode != 0:
                raise RuntimeError('RAR extraction failed: ' + proc.stderr[-1500:])
            for row in batch:
                source = checked_child(STAGE, row['member'])
                if (not source.is_file() or source.stat().st_size != row['bytes']
                        or (row['crc32'] and crc(source) != row['crc32'])):
                    raise ValueError('Extracted member differs from archive metadata: ' + row['member'])
                digest = sha(source)
                if row['destination'] == 'native':
                    target = checked_child(RAW, row['relative'])
                else:
                    # Preserve only reviewed differing sources, without a second corpus.
                    target = checked_child(VARIANTS, row.get('relative') or row['member'])
                if target.exists():
                    if not target.is_file() or sha(target) != digest:
                        raise FileExistsError('Preserved current file; do not overwrite: ' + str(target))
                    source.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                log.write(json.dumps({'member': row['member'], 'path': target.relative_to(ROOT).as_posix(),
                                      'bytes': row['bytes'], 'sha256': digest}, ensure_ascii=True) + '\n')
                log.flush()
            print('CHECKPOINT merged batch', number, flush=True)
    include.unlink(missing_ok=True)
    # Only empty directories made by this helper are disposable here.
    for folder in sorted((p for p in STAGE.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    if not any(STAGE.iterdir()):
        STAGE.rmdir()
    print('CHECKPOINT selected merge complete. Keep the compressed archive until all conflicts and unmapped candidates are reviewed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reuse-plan', action='store_true')
    parser.add_argument('--variant-list', type=Path,
                        help='UTF-8 exact archive member names, one reviewed differing source per line.')
    parser.add_argument('--native-list', type=Path,
                        help='UTF-8 exact missing native relative paths, one per line. Only these native files are extracted.')
    args = parser.parse_args()
    if ARCHIVE.stat().st_size != EXPECTED_BYTES:
        raise RuntimeError('Download incomplete. No listing, extraction or source change performed.')
    verify_archive()
    document = json.loads(PLAN.read_text(encoding='utf8')) if args.reuse_plan else plan()
    if document['bytes'] != EXPECTED_BYTES or document['archive'].replace('\\', '/') != ARCHIVE.relative_to(ROOT).as_posix():
        raise ValueError('Plan belongs to another archive.')
    if args.apply:
        selected = args.variant_list.read_text(encoding='utf-8-sig').splitlines() if args.variant_list else []
        native = ({line.strip().replace('\\', '/') for line in
                args.native_list.read_text(encoding='utf-8-sig').splitlines() if line.strip()}
                  if args.native_list else None)
        apply(document, {line for line in selected if line.strip()}, native)


if __name__ == '__main__':
    main()
