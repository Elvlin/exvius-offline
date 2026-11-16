"""Recover exact original JP unit/model members without replacing game assets.

Reuses the preserved native filename transform before CRILAYLA decompression.
Sources are retained native packs and checksum-verified original JP archive packs.
Fan overlays and current Global assets are never fallback sources.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'custom-engine/tools'))
from cpk import crilayla, utf_table
from decode_gl9_member import decode
from PIL import Image

NATIVE = ROOT / 'data/memorial/external/files/assetpacks/on_demand_asset3/199/199/assets'
RECOVERED = ROOT / 'Japan content/Recovered assets'
INVENTORY = ROOT / 'Japan content/Earlier JP crossovers'
ARCHIVE = ROOT / 'Japan content/Shared sources/jp_andapp'
ARCHIVE_METADATA = ROOT / 'Japan content/Shared sources/original-jp-pack-download-sources.json'
DECODER_SHA256 = '9241df3ca40468a31bc17dc22918b623f528eee16581cb1cc9665029e925f1af'
DECODER_SOURCE = {
    'archive': 'G:/My Drive/Exvius/Exvius-Private-1.26-higher-Esper-source-evidence.zip',
    'member': 'workspace/private126-esper-menu-assets-candidate/decode_gl9_member.py',
    'sha256': DECODER_SHA256,
    'native_reference': '0x1ef4250 -> 0x19b5e90; native trimmed basename',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_rows(path: Path):
    data = path.read_bytes()
    if data[:4] != b'CPK ':
        raise ValueError(f'Not an original CPK: {path}')
    size = struct.unpack_from('<Q', data, 8)[0]
    header = utf_table(data[16:16 + size])[0]
    offset = header['TocOffset']
    size = struct.unpack_from('<Q', data, offset + 8)[0]
    rows = utf_table(data[offset + 16:offset + 16 + size])
    start = min(offset, header.get('ContentOffset') or offset)
    return data, rows, start


def decoded_member(raw: bytes, row: dict, stem: str) -> bytes:
    name = row['FileName']
    if Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Source member must have its exact native basename')
    attribute = row.get('UserString')
    if attribute == f'CRI_CFATTR:{stem}-1':
        raw = decode(raw, name)
    elif attribute not in (None, '', '<NULL>', f'CRI_CFATTR:{stem}-0'):
        raise ValueError(f'Unsupported original member attribute: {attribute}')
    if raw[:8] == b'CRILAYLA':
        raw = crilayla(raw)
    if len(raw) != int(row['ExtractSize']):
        raise ValueError(f'Original extracted length mismatch: {name}')
    return raw


def inspect_member(name: str, payload: bytes) -> dict:
    if name.endswith('.png'):
        with Image.open(io.BytesIO(payload)) as im:
            im.verify()
        with Image.open(io.BytesIO(payload)) as im:
            rgba = im.convert('RGBA')
            if not rgba.getchannel('A').getbbox():
                raise ValueError(f'Empty required original image: {name}')
            colors = rgba.getcolors(2)
            if colors and len(colors) == 1:
                raise ValueError(f'Solid placeholder image: {name}')
            return {'format': 'PNG', 'width': im.width, 'height': im.height,
                    'alpha_bounds': rgba.getchannel('A').getbbox(),
                    'rgba_sha256': sha(rgba.tobytes())}
    if name.endswith('.csv'):
        text = payload.decode('ascii')
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise ValueError(f'Empty original animation definition: {name}')
        return {'format': 'ASCII CSV', 'rows': len(rows),
                'column_counts': sorted({len(r) for r in rows})}
    raise ValueError(f'Unreviewed asset type: {name}')


def validate_unit_animation(identity: str, directory: Path) -> dict:
    """Check native CGS group references and CGG page-zero texture rectangles."""
    import math

    def rows(path: Path) -> list[list[str]]:
        result = []
        for row in csv.reader(io.StringIO(path.read_text(encoding='ascii'))):
            if not row:
                continue
            # Native strtok ignores the original files' trailing delimiter.
            while row and row[-1] == '':
                row.pop()
            if row:
                result.append(row)
        return result

    texture = directory / f'unit_anime_{identity}.png'
    with Image.open(texture) as image:
        width, height = image.size
    groups = rows(directory / f'unit_cgg_{identity}.csv')
    if not groups:
        raise ValueError(f'No native CGG groups: {identity}')
    parts_checked = 0
    unresolved_pages = set()
    rectangle_anomalies = []
    for group_index, row in enumerate(groups):
        if len(row) < 2:
            raise ValueError(f'Incomplete CGG group: {identity}:{group_index}')
        part_count = int(row[1])
        # EdgeAnimeCgg::read at 0x1ee98d4 consumes eleven fields per part.
        if part_count < 0 or len(row) < 2 + 11 * part_count:
            raise ValueError(f'Incomplete CGG parts: {identity}:{group_index}')
        for part_index in range(part_count):
            part = row[2 + 11 * part_index:2 + 11 * (part_index + 1)]
            x, y, part_width, part_height = map(float, part[6:10])
            page = int(part[10])
            if not all(math.isfinite(v) for v in (x, y, part_width, part_height)):
                raise ValueError(f'Nonfinite CGG rectangle: {identity}:{group_index}')
            if page != 0:
                # The native array-texture overload uses PageIdx. Do not invent
                # another page's filename or reject an original multipage asset.
                unresolved_pages.add(page)
                continue
            if (x < 0 or y < 0 or part_width < 0 or part_height < 0 or
                    x + part_width > width or y + part_height > height):
                # Genuine source data can contain unused out-of-bounds groups.
                # Preserve the original bytes and report the anomaly rather
                # than rewriting it or treating it as decoder corruption.
                rectangle_anomalies.append(
                    {'group_index': group_index, 'part_index': part_index,
                     'rectangle': [x, y, part_width, part_height],
                     'texture_size': [width, height]})
            parts_checked += 1

    actions = sorted(directory.glob(f'unit_*_cgs_{identity}.csv'))
    if not actions:
        raise ValueError(f'No native CGS actions: {identity}')
    frames_checked = 0
    group_actions = {}
    for action in actions:
        for frame_index, row in enumerate(rows(action)):
            if len(row) < 4:
                raise ValueError(f'Incomplete native CGS frame: {action.name}:{frame_index}')
            group_index = int(row[0])
            # EdgeAnimeCgs::read sets CggIndex from column zero. The original
            # EdgeAnimeCgg::getGroup at 0x1ee9cc8 indexes without a bounds check.
            if group_index < 0 or group_index >= len(groups):
                raise ValueError(
                    f'CGS references missing CGG group: '
                    f'{action.name}:{frame_index}:{group_index}')
            group_actions.setdefault(group_index, set()).add(action.name)
            if not all(math.isfinite(float(v)) for v in row[1:3]):
                raise ValueError(f'Nonfinite native CGS position: {action.name}:{frame_index}')
            int(row[3])  # Native Delay is an integer; no invented duration range.
            frames_checked += 1
    for anomaly in rectangle_anomalies:
        actions_using_group = sorted(group_actions.get(anomaly['group_index'], set()))
        anomaly['referenced_by_cgs'] = bool(actions_using_group)
        anomaly['actions_using_group'] = actions_using_group
    status = 'cross-file references and page-zero bounds checked'
    if rectangle_anomalies or unresolved_pages:
        status = 'group references checked; original texture anomalies/pages require review'
    return {'identity': identity, 'cgg_groups': len(groups), 'cgs_actions': len(actions),
            'cgs_frames_checked': frames_checked, 'page_zero_parts_checked': parts_checked,
            'unresolved_texture_pages': sorted(unresolved_pages),
            'source_rectangle_anomalies': rectangle_anomalies, 'status': status}


def write_exact(path: Path, payload: bytes) -> None:
    if not path.resolve().is_relative_to(RECOVERED.resolve()):
        raise ValueError('Recovery output escaped the designated folder')
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f'Refusing to replace different recovered bytes: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def requested_ids():
    document = json.loads((INVENTORY / 'unit-banner-visual-count-evidence.json').read_text(encoding='utf-8-sig'))
    unit_ids = {str(mid) for row in document['unit_versions'] for mid in row['native_form_ids']}
    unit_ids.update(('100014405', '100014406'))
    with (INVENTORY / 'original-jp-monster-source-map.csv').open(encoding='utf-8-sig', newline='') as stream:
        model_ids = {row['graphic_id'] for row in csv.DictReader(stream)}
    return unit_ids, model_ids


def verified_archive_packs():
    metadata = json.loads(ARCHIVE_METADATA.read_text(encoding='utf-8-sig'))
    for record in metadata['packages']:
        path = ARCHIVE / record['name']
        if not path.exists():
            continue
        payload = path.read_bytes()
        if (len(payload) != int(record['size']) or
                hashlib.md5(payload).hexdigest() != record['md5'] or
                hashlib.sha1(payload).hexdigest() != record['sha1']):
            raise ValueError(f'Original JP archive checksum mismatch: {path}')
        yield path


def ingest_archive_download(path: Path):
    metadata = json.loads(ARCHIVE_METADATA.read_text(encoding='utf-8-sig'))
    record = next(r for r in metadata['packages'] if r['name'] == path.name)
    payload = path.read_bytes()
    if (len(payload) != int(record['size']) or
            hashlib.md5(payload).hexdigest() != record['md5'] or
            hashlib.sha1(payload).hexdigest() != record['sha1']):
        raise ValueError(f'Download checksum mismatch: {path.name}')
    destination = ARCHIVE / path.name
    if destination.exists() and destination.read_bytes() != payload:
        raise ValueError(f'Refusing to replace another source version: {destination}')
    if not destination.exists():
        destination.write_bytes(payload)
    if sha(destination.read_bytes()) != sha(payload):
        raise ValueError('Source transfer verification failed')
    manifest_path = ARCHIVE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    manifest[path.name] = {'size': len(payload), 'md5': record['md5'],
                           'sha1': record['sha1'], 'sha256': sha(payload),
                           'source': record['download_url']}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if path.resolve() != destination.resolve():
        if path.parent.resolve() != (Path.home() / 'Downloads').resolve():
            raise ValueError('Only the verified task download may be removed')
        path.unlink()
    print(f'Verified original JP package: {destination.name} ({len(payload)} bytes)', flush=True)


def recover(only_reberta=False):
    decoder_path = Path(__file__).with_name('decode_gl9_member.py')
    if sha(decoder_path.read_bytes()) != DECODER_SHA256:
        raise ValueError('Proven decoder changed; review its native-source contract first')
    unit_ids, model_ids = requested_ids()
    if only_reberta:
        unit_ids, model_ids = {'100014405', '100014406'}, set()
    records, packages, seen = [], [], {}
    for path in [*sorted(NATIVE.glob('*.cpk')), *verified_archive_packs()]:
        kind = ('units' if re.fullmatch(r'unit\d+\.cpk', path.name) else
                'monsters' if re.fullmatch(r'monster[^/]*\.cpk', path.name) else '')
        if not kind or (kind == 'monsters' and not model_ids):
            continue
        wanted = unit_ids if kind == 'units' else model_ids
        # Preserve the already recovered native version. Older archive packs fill gaps.
        if path.parent == ARCHIVE:
            wanted = wanted - {r['source_identity'] for r in records if r['kind'] == kind}
        data, rows, start = source_rows(path)
        selected = []
        for row in rows:
            name = row.get('FileName') or ''
            match = re.search(r'_(\d+)\.(?:png|csv)$', name)
            if not match or match.group(1) not in wanted:
                continue
            if not name.startswith('unit_' if kind == 'units' else 'monster_'):
                continue
            selected.append((row, match.group(1)))
        if not selected:
            continue
        package_hash = sha(data)
        for row, identity in selected:
            name = row['FileName']
            offset = start + int(row['FileOffset'])
            stored = data[offset:offset + int(row['FileSize'])]
            payload = decoded_member(stored, row, path.stem)
            checked = inspect_member(name, payload)
            destination = RECOVERED / kind / identity / name
            member_hash = sha(payload)
            key = kind, identity, name
            if key in seen and seen[key] != member_hash:
                raise ValueError(f'Conflicting original source versions: {name}')
            seen[key] = member_hash
            write_exact(destination, payload)
            records.append({'kind': kind, 'source_identity': identity,
                            'path': destination.relative_to(ROOT).as_posix(),
                            'bytes': len(payload), 'sha256': member_hash,
                            'source_package': path.relative_to(ROOT).as_posix(),
                            'source_package_sha256': package_hash,
                            'source_member': name, 'source_member_ID': row.get('ID'),
                            'source_stored_bytes': len(stored),
                            'source_stored_sha256': sha(stored),
                            'source_attribute': row.get('UserString'),
                            'validation': checked})
        packages.append({'path': path.relative_to(ROOT).as_posix(),
                         'sha256': package_hash, 'selected_members': len(selected)})
        print(f'Recovered {path.name}: {len(selected)} original members', flush=True)
    found_units = {r['source_identity'] for r in records if r['kind'] == 'units'}
    found_models = {r['source_identity'] for r in records if r['kind'] == 'monsters'}
    for identity in found_models:
        names = {r['source_member'] for r in records if r['kind'] == 'monsters' and r['source_identity'] == identity}
        required = {f'monster_anime_{identity}.png', f'monster_icon_{identity}.png',
                    f'monster_cgg_{identity}.csv'}
        if not required <= names or not any('_cgs_' in n for n in names):
            raise ValueError(f'Incomplete original monster core: {identity}')
    animation_checks = []
    for identity in found_units:
        names = {r['source_member'] for r in records if r['kind'] == 'units' and r['source_identity'] == identity}
        required = {f'unit_{prefix}_{identity}.png' for prefix in ('icon', 'ills', 'anime')}
        required.add(f'unit_cgg_{identity}.csv')
        if not required <= names or not any('_cgs_' in n for n in names):
            raise ValueError(f'Incomplete original unit core: {identity}')
        animation_checks.append(validate_unit_animation(identity, RECOVERED / 'units' / identity))
    print('Native animation references: '
          f'{len(animation_checks)} forms, '
          f'{sum(r["cgs_actions"] for r in animation_checks)} actions, '
          f'{sum(r["cgs_frames_checked"] for r in animation_checks)} frames, '
          f'{sum(r["page_zero_parts_checked"] for r in animation_checks)} texture parts; '
          f'{sum(bool(r["unresolved_texture_pages"]) for r in animation_checks)} '
          'forms with unresolved additional pages; '
          f'{sum(len(r["source_rectangle_anomalies"]) for r in animation_checks)} '
          'original rectangle anomalies retained', flush=True)
    for check in animation_checks:
        if check['source_rectangle_anomalies']:
            print(json.dumps({'identity': check['identity'],
                              'source_rectangle_anomalies': check['source_rectangle_anomalies']},
                             ensure_ascii=True), flush=True)
    manifest = {'schema': 1, 'status': 'Decoded original JP sources; not installed or gameplay verified',
                'source_policy': 'Retained native JP packs, then checksum-verified original JP archive packs for missing identities; no Global or fan-overlay fallback',
                'decoder': DECODER_SOURCE, 'scope': 'Reberta JP only' if only_reberta else 'Earlier JP units/models plus Reberta JP',
                'requested_unit_forms': len(unit_ids), 'recovered_unit_forms': len(found_units),
                'missing_unit_forms_in_inspected_sources': sorted(unit_ids - found_units),
                'requested_model_ids': len(model_ids), 'recovered_model_ids': len(found_models),
                'missing_model_ids_in_inspected_sources': sorted(model_ids - found_models),
                'unique_files': len(seen), 'bytes': sum(r['bytes'] for r in records),
                'source_packages': packages, 'files': records,
                'unit_animation_validation': sorted(animation_checks, key=lambda check: check['identity']),
                'remaining': 'Source/package availability is separate from complete provenance, original body/model bindings, native metadata/index installation and gameplay acceptance.'}
    RECOVERED.mkdir(parents=True, exist_ok=True)
    name = 'reberta-jp-manifest.json' if only_reberta else 'recovery-manifest.json'
    (RECOVERED / name).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: manifest[k] for k in ('scope', 'recovered_unit_forms', 'recovered_model_ids', 'unique_files', 'bytes')}, ensure_ascii=True))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reberta-only', action='store_true', help='Recover only the two exact original JP Reberta forms.')
    parser.add_argument('--ingest-download', type=Path, action='append', default=[], help='Verify an original archive download, store it in the canonical source home, then remove its Downloads copy.')
    args = parser.parse_args()
    if args.ingest_download:
        for download in args.ingest_download:
            ingest_archive_download(download)
    else:
        recover(args.reberta_only)
