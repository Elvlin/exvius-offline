"""Recover original JP reward icons and vision cards into native cache packs."""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json
import re
import struct
import sys
from collections import Counter

from apply_jp_content import NativeCache
from fill_content_from_memorial import global_cpk_header
from recover_jp_assets import decoded_member, inspect_member, source_rows
from decode_client_data import decode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
from cricodecs import cpk
from PIL import Image

RECOVERED = ROOT / 'Japan content/Recovered assets'
SOURCES = ROOT / 'Japan content/Earlier JP crossovers/Sources'
ARCHIVE = ROOT / 'Japan content/Shared sources/jp_andapp'
RETAIL = ROOT / 'data/memorial/external/files/assetpacks/on_demand_asset2/199/199/assets'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def payload(path, data, row, start):
    offset = start + row['FileOffset']
    return decoded_member(data[offset:offset + row['FileSize']], row, path.stem)


def rgba_equal(left, right):
    with Image.open(io.BytesIO(left)) as a, Image.open(io.BytesIO(right)) as b:
        return a.size == b.size and a.convert('RGBA').tobytes() == b.convert('RGBA').tobytes()


def animation_check(identity, files):
    def records(name):
        result = []
        for row in csv.reader(io.StringIO(files[name].decode('ascii'))):
            while row and not row[-1]:
                row.pop()
            if row:
                result.append(row)
        return result
    groups = records('vc_cgg_' + identity + '.csv')
    frames = records('vc_cgs_' + identity + '.csv')
    with Image.open(io.BytesIO(files['vc_vignette_anime_' + identity + '.png'])) as image:
        width, height = image.size
    anomalies, pages, parts = [], set(), 0
    for index, row in enumerate(groups):
        count = int(row[1])
        if len(row) < 2 + 11 * count:
            raise ValueError('Incomplete original VC CGG part list: ' + identity)
        for offset in range(count):
            fields = row[2 + 11 * offset:2 + 11 * (offset + 1)]
            x, y, w, h, page = map(int, fields[6:11])
            pages.add(page)
            parts += 1
            if page == 0 and (x < 0 or y < 0 or x + w > width or y + h > height):
                anomalies.append({'group': index, 'part': offset, 'rectangle': [x, y, w, h]})
    used = set()
    for row in frames:
        if len(row) != 4 or not 0 <= int(row[0]) < len(groups):
            raise ValueError('Original VC CGS points outside CGG groups: ' + identity)
        used.add(int(row[0]))
    if pages - {0}:
        raise ValueError('Unresolved original VC texture pages: ' + identity)
    return {'cgg_groups': len(groups), 'cgs_frames': len(frames), 'parts': parts,
            'texture_pages': sorted(pages), 'source_rectangle_anomalies': anomalies,
            'referenced_rectangle_anomalies': [a for a in anomalies if a['group'] in used]}


def card_binding_contract(cache):
    core = json.loads((SOURCES / 'native-unit-import.json').read_text('utf-8'))
    entry = next(t for t in core['tables'] if t['table'] == 'F_VISION_CARD_MST')
    relative = entry['active_native_path']
    raw, origin = cache.read(relative)
    _, rows = decode(raw, cache.tables['F_VISION_CARD_MST'][1])
    target = next(r for r in rows if r['5giCMUd2'] == '873000001')
    if any(r['efb6J8AZ'] == '873000001' and r['5giCMUd2'] != '873000001' for r in rows):
        raise ValueError('Proposed JP graphic identity is already used by another card')
    name = target['G4L0YIB2']
    if re.search('[\u3040-\u30ff\u3400-\u9fff]', name):
        raise ValueError('English master embedding must precede the card art addendum')
    if not name.endswith(' JP'):
        name += ' JP'
    native_source = {'container': origin.split('::')[0], 'member': origin.split('::')[1]} if '::' in origin else {'path': origin, 'sha256': sha(raw)}
    decoded = ROOT / 'data/mst_decoded/F_VISION_CARD_MST.ndjson'
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY',
        'scope': 'Owned JP Mana card873000001 only. Original Global312000101 and unrelated cards preserved.',
        'tables': [{'table': 'F_VISION_CARD_MST', 'identity_fields': ['5giCMUd2'],
            'active_native_path': relative, 'active_native_source': native_source,
            'active_native_sha256': sha(raw), 'decoded_baseline_sha256': sha(decoded.read_bytes()),
            'operation': 'merge_fields', 'rows': [{'5giCMUd2': '873000001',
                'efb6J8AZ': '873000001', 'G4L0YIB2': name}]}]}
    (SOURCES / 'native-jp-card-art-import.json').write_bytes((json.dumps(contract, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    (SOURCES / 'dependency-art-labels-en.json').write_bytes((json.dumps({'F_TEXT_VISION_CARD_NAME': {
        'MST_VISION_CARD_NAME_873000001': name}}, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))


def recover(apply=False):
    icon_bindings = json.loads((SOURCES / 'original-jp-icon-bindings.json').read_text('utf-8'))['bindings']
    icons = {r['source_filename'] for r in icon_bindings}
    master = json.loads((SOURCES / 'original-unit-content.json').read_text('utf-8'))
    cards = {r['efb6J8AZ'] for r in master['tables']['F_VISION_CARD_MST']['rows']}
    mana_graphic = '873000001'
    records, contents, packages = [], {}, {}
    source_paths = [RETAIL / 'item1.cpk', RETAIL / 'item2.cpk'] + [ARCHIVE / ('visioncard' + str(n) + '.cpk') for n in range(1, 4)]
    for path in source_paths:
        data, rows, start = source_rows(path)
        packages[path.name] = {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(data)}
        for row in rows:
            name = row['FileName']
            match = re.search(r'_([0-9]{9})(?:_|\.)', name)
            identity = match[1] if match else None
            selected_icon = path.name.startswith('item') and name in icons
            selected_card = path.name.startswith('visioncard') and identity in cards
            selected_common = path.name.startswith('visioncard') and re.fullmatch(r'vc_(?:bg|frame)_[0-9]+_(?:s|m|ll)\.png', name)
            if not (selected_icon or selected_card or selected_common):
                continue
            body = payload(path, data, row, start)
            validation = inspect_member(name, body)
            if name in contents and contents[name] != body:
                raise ValueError('Original source members disagree: ' + name)
            contents[name] = body
            kind = 'icons' if selected_icon else 'visioncards'
            directory = RECOVERED / kind / (identity if selected_card else ('common' if selected_common else ''))
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / name
            if target.exists() and target.read_bytes() != body:
                raise ValueError('Recovered original dependency asset changed: ' + name)
            target.write_bytes(body)
            records.append({'kind': kind, 'identity': identity, 'member': name,
                'path': target.relative_to(ROOT).as_posix(), 'sha256': sha(body),
                'source_package': path.relative_to(ROOT).as_posix(), 'source_package_sha256': sha(data),
                'source_toc': row, 'validation': validation})
    if icons - contents.keys():
        raise ValueError('Missing original JP icon PNGs: ' + str(sorted(icons - contents.keys())))
    animation = {}
    for identity in sorted(cards):
        expected = {'vc_cgg_' + identity + '.csv', 'vc_cgs_' + identity + '.csv',
                    'vc_vignette_anime_' + identity + '.png', 'vc_vignette_icon_s_' + identity + '.png',
                    'vc_vignette_item_icon_' + identity + '.png'}
        if expected - contents.keys():
            raise ValueError('Missing original VC graphics: ' + identity)
        animation[identity] = animation_check(identity, contents)
    cache = NativeCache()
    try:
        versions = {}
        for _, _, names in cache.packs:
            for name in names:
                match = re.fullmatch(r'native/(common_lang/sd/(?:item|visioncard)/Ver(\d+)_((?:item|visioncard)\d+)_common\.cpk)', name)
                if match and (match[3] not in versions or int(match[2]) > versions[match[3]][0]):
                    versions[match[3]] = (int(match[2]), match[1])
        archives, before, full_before, origins, membership = {}, {}, {}, {}, {}
        target_names = set(contents) | {name.replace('_312000101.', '_' + mana_graphic + '.')
                                      for name in contents if '_312000101.' in name}
        for stem, (_, relative) in versions.items():
            raw, origin = cache.read(relative)
            archive = cpk.Cpk.load_bytes(raw)
            archives[relative] = archive
            origins[relative] = {'source': origin, 'sha256': sha(raw)}
            before[relative] = {e.full_path: (e.id, sha(archive.file_bytes(i))) for i, e in enumerate(archive.file_infos())}
            full_before[relative] = Counter((e.full_path, e.id, sha(archive.file_bytes(i)))
                                           for i, e in enumerate(archive.file_infos()))
            for index, entry in enumerate(archive.file_infos()):
                if entry.full_path in target_names:
                    membership.setdefault(entry.full_path, []).append((relative, index, entry))
        modified, desired, comparisons = set(), {}, []
        for record in records:
            name, original = record['member'], contents[record['member']]
            isolated_mana = record['kind'] == 'visioncards' and record['identity'] == '312000101'
            target_name = name.replace('_312000101.', '_' + mana_graphic + '.') if isolated_mana else name
            destinations = membership.get(name)
            if not destinations:
                source_stem = Path(record['source_package']).stem
                relative = versions[source_stem][1]
                destinations = [(relative, None, None)]
            for relative, index, entry in destinations:
                archive = archives[relative]
                old = None
                if index is not None:
                    native_stem = Path(relative).stem.split('_', 1)[1].removesuffix('_common')
                    old = decoded_member(archive.file_bytes(index), {'FileName': name, 'ExtractSize': entry.extract_size,
                        'UserString': entry.user_string}, native_stem)
                exact = old == original
                equal_pixels = bool(old is not None and name.endswith('.png') and rgba_equal(original, old))
                comparison = 'shared_exact_payload' if exact else ('shared_exact_RGBA_pixels' if equal_pixels else 'original_payload_differs_or_missing')
                if isolated_mana:
                    action = 'isolated_original_JP_card'
                elif record['kind'] == 'visioncards' and (record['identity'] is None or record['identity'] == '900020101'):
                    action = 'retained_English_client_UI_or_generic_EXP'
                elif old is not None and not exact and not equal_pixels:
                    action = 'retained_semantically_equivalent_English_UI'
                else:
                    action = comparison if old is not None else 'added_missing_original_JP_asset'
                comparisons.append({'member': name, 'target_member': target_name, 'native_package': relative,
                    'action': action, 'payload_comparison': comparison,
                    'original_sha256': sha(original), 'current_decoded_sha256': sha(old) if old is not None else None})
                if not isolated_mana and (old is not None or action.startswith('retained')):
                    continue
                if isolated_mana:
                    target_members = membership.get(target_name, [])
                    existing_target = next((p for p in target_members if p[0] == relative), None)
                    name = target_name
                    if existing_target:
                        _, index, entry = existing_target
                        if archive.file_bytes(index) == original:
                            continue
                    else:
                        index, entry = None, None
                if entry is not None:
                    if entry.user_string not in (None, '', '<NULL>', 'CRI_CFATTR:' + native_stem + '-0'):
                        raise ValueError('Native target requires a proven encoding transform: ' + name)
                    archive.replace_bytes(index, original)
                else:
                    archive.add_bytes(original, name, id=max(e.id for e in archive.file_infos()) + 1)
                desired.setdefault(relative, {})[name] = sha(original)
                modified.add(relative)
        prepared, integration = {}, []
        for relative in sorted(modified):
            body = archives[relative].save_bytes()
            end = 16 + struct.unpack_from('<Q', body, 8)[0]
            body = global_cpk_header(body[:end]) + body[end:]
            check = cpk.Cpk.load_bytes(body)
            after = {e.full_path: (e.id, sha(check.file_bytes(i))) for i, e in enumerate(check.file_infos())}
            full_after = Counter((e.full_path, e.id, sha(check.file_bytes(i))) for i, e in enumerate(check.file_infos()))
            if full_before[relative] - full_after:
                raise ValueError('An existing native member/ID/payload changed, including duplicate names')
            for name, value in before[relative].items():
                if name not in desired[relative] and after.get(name) != value:
                    raise ValueError('Unrelated native member changed: ' + name)
                if name in desired[relative] and after[name][0] != value[0]:
                    raise ValueError('Existing native CRI ID changed: ' + name)
            if any(after[name][1] != digest for name, digest in desired[relative].items()):
                raise ValueError('Native dependency payload readback differs')
            prepared[relative] = body
            integration.append({'output': 'data/overlay/' + relative, 'sha256': sha(body),
                'source': origins[relative], 'source_members': len(before[relative]),
                'changed_or_added_members': len(desired[relative]), 'bytes': len(body)})
        if apply:
            for relative, body in prepared.items():
                target = ROOT / 'data/overlay' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                if sha(target.read_bytes()) != sha(body):
                    raise ValueError('Native dependency overlay write differs')
        card_binding_contract(cache)
        result = {'status': 'APPLIED' if apply else 'VERIFIED_PREVIEW_NO_NATIVE_WRITES',
            'source_packages': packages, 'icons': len(icons), 'vision_cards': sorted(cards),
            'original_asset_members': len(records), 'files': records, 'animation_validation': animation,
            'comparisons': comparisons, 'native_integration': integration,
            'policy': 'Preserve English-client shared UI and generic EXP. All37 differing weapon/portrait pairs visually show the same identity/version. Isolate original Mana JP card artwork in graphic873000001. Add missing original assets without replacing existing Global members.',
            'limitations': 'Native payload and animation references verified. Phone rendering/playback not exercised here.'}
        (RECOVERED / 'dependency-art-manifest.json').write_bytes((json.dumps(result, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
        (ROOT / 'logs/jp-dependency-art-integration.json').write_bytes((json.dumps(result, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
        counts = {action: sum(r['action'] == action for r in comparisons) for action in {r['action'] for r in comparisons}}
        print(json.dumps({'status': result['status'], 'icons': len(icons), 'vision_cards': len(cards),
            'original_members': len(records), 'comparison_counts': counts, 'native_packages': integration}))
        return result
    finally:
        cache.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    recover(parser.parse_args().apply)
