"""Recover canonical original JP icons and compare actual mapped native users.

The comparison never alters Global files or native masters. Its scoped plan
is consumed only after the final typed dependency mapping is available.
"""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from apply_jp_content import NativeCache
from recover_jp_unit_content import Inputs, json_bytes
from recover_jp_dependency_art import payload, rgba_equal, cpk
from recover_jp_assets import source_rows, decoded_member, inspect_member
from fill_content_from_memorial import global_cpk_header

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / 'Japan content/Earlier JP crossovers/Sources'
ARCHIVE = ROOT / 'Japan content/Shared sources/jp_andapp'
RECOVERED = ROOT / 'Japan content/Recovered assets/icons/canonical'
GEAR_IDS = ('304001600', '312001700', '404001800', '404001900', '404002000',
            '406002100', '406002300', '406002500', '407002100', '409012000', '409012100', '409012200')
KEYS = {'F_ITEM_MST': 'tL6G9egd', 'F_EQUIP_ITEM_MST': 'J1YX9kmM', 'F_MATERIA_MST': 'H5jBL0Vf',
        'F_ABILITY_MST': 'Ga5V42LZ', 'F_MAGIC_MST': 'QV1HE7Wq'}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')


def compare():
    inputs = Inputs()
    mapping_path = HOME / 'native-unit-id-map.json'
    mapping_raw = mapping_path.read_bytes()
    mappings = json.loads(mapping_raw)['mappings']
    originals = {r['0HUPxDf1']: r for r in inputs.original('F_ICON_MST')}
    current_icons = {r['0HUPxDf1']: r for r in inputs.current('F_ICON_MST')}
    initial = json.loads((HOME / 'original-jp-icon-bindings.json').read_text('utf8'))['bindings']
    bindings = {r['source_icon_id']: copy.deepcopy(r) for r in initial}
    for iid in GEAR_IDS:
        bindings[iid] = {'source_icon_id': iid, 'source_filename': originals[iid]['qtkvrS60'],
            'references': [{'table': 'F_EQUIP_ITEM_MST', 'identity_field': 'J1YX9kmM', 'source_id': iid}]}
    bindings['260000100'] = {'source_icon_id': '260000100', 'source_filename': originals['260000100']['qtkvrS60'],
        'references': [{'table': 'F_ITEM_MST', 'identity_field': 'tL6G9egd', 'source_id': '260000100'}]}
    required = {row['source_filename'] for row in bindings.values()}
    canonical, packages = {}, []
    RECOVERED.mkdir(parents=True, exist_ok=True)
    for stem in ('item1', 'item2'):
        path = ARCHIVE / (stem + '.cpk')
        data, rows, start = source_rows(path)
        package = {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(data), 'bytes': len(data)}
        packages.append(package)
        for row in rows:
            name = row['FileName']
            if name not in required: continue
            body = payload(path, data, row, start)
            validation = inspect_member(name, body)
            if name in canonical and canonical[name]['sha256'] != sha(body):
                raise ValueError('Canonical original packs disagree: ' + name)
            target = RECOVERED / name
            target.write_bytes(body)
            canonical[name] = {'body': body, 'sha256': sha(body), 'path': target.relative_to(ROOT).as_posix(),
                               'source_package': package, 'toc': row, 'validation': validation}
    missing = sorted(required - canonical.keys())
    if missing: raise ValueError('Canonical JP original icon missing:' + str(missing))
    current_rows = {table: {r[key]: r for r in inputs.current(table)} for table, key in KEYS.items()
                    if any(ref['table'] == table for b in bindings.values() for ref in b['references'])}
    names = set()
    for binding in bindings.values():
        for reference in binding['references']:
            table, source = reference['table'], reference['source_id']
            target = mappings.get(table, {}).get(source, source)
            row = current_rows[table].get(target)
            if row is None: raise ValueError('Final mapped icon consumer missing:' + table + ':' + target)
            icon = current_icons.get(row['0HUPxDf1'])
            if icon is None: raise ValueError('Native icon consumer points to missing F_ICON row:' + table + ':' + target)
            names.add(icon['qtkvrS60'])
    cache = NativeCache()
    try:
        versions = {}
        for _, _, members in cache.packs:
            for member in members:
                match = re.fullmatch(r'native/(common_lang/sd/item/Ver(\d+)_(item[12])_common\.cpk)', member)
                if match and (match[3] not in versions or int(match[2]) > versions[match[3]][0]):
                    versions[match[3]] = (int(match[2]), match[1])
        occurrences = {}
        for stem, (_, relative) in versions.items():
            raw, origin = cache.read(relative)
            archive = cpk.Cpk.load_bytes(raw)
            for index, entry in enumerate(archive.file_infos()):
                if entry.full_path not in names: continue
                body = decoded_member(archive.file_bytes(index), {'FileName': entry.full_path,
                    'ExtractSize': entry.extract_size, 'UserString': entry.user_string}, stem)
                inspect_member(entry.full_path, body)
                occurrences.setdefault(entry.full_path, []).append({'body': body, 'sha256': sha(body),
                    'native_path': relative, 'source': origin, 'package_sha256': sha(raw), 'member_id': entry.id})
        occupied = set(current_icons) | set(originals)
        planned, counts = [], Counter()
        for number, iid in enumerate(sorted(bindings, key=int), 1):
            binding = bindings[iid]; original = canonical[binding['source_filename']]
            references = []
            for reference in binding['references']:
                table, source = reference['table'], reference['source_id']
                target = mappings.get(table, {}).get(source, source)
                row = current_rows[table][target]; icon = current_icons[row['0HUPxDf1']]
                found = occurrences.get(icon['qtkvrS60'], [])
                matches = [{'native_path': f['native_path'], 'source': f['source'], 'member_id': f['member_id'],
                    'package_sha256': f['package_sha256'], 'sha256': f['sha256'],
                    'exact_bytes': f['body'] == original['body'], 'exact_RGBA_pixels': rgba_equal(f['body'], original['body'])}
                    for f in found]
                equivalent = bool(matches) and all(f['exact_RGBA_pixels'] for f in matches)
                references.append({'table': table, 'identity_field': KEYS[table], 'source_id': source, 'target_id': target,
                    'current_icon_id': row['0HUPxDf1'], 'current_filename': icon['qtkvrS60'],
                    'current_occurrences': matches, 'equivalent': equivalent,
                    'action': 'reuse_verified_original_pixels' if equivalent else
                              ('scoped_icon_patch' if target != source else 'requires_shared_consumer_identity_check')})
            different = [r for r in references if not r['equivalent']]
            icon_id = '872100001' if iid == '260000100' else str(874100000 + number)
            if different and icon_id in occupied:
                raise ValueError('Proposed JP icon identity already occupied:' + icon_id)
            source_record = {k: v for k, v in original.items() if k != 'body'}
            status = 'different_or_missing_pixels' if different else 'all_current_occurrences_exact_pixels'
            counts[status] += 1
            counts['references_' + ('different_or_missing_pixels' if different else 'equivalent_binding')] += len(references)
            planned.append({'source_icon_id': iid, 'source_filename': binding['source_filename'],
                'canonical_original': source_record, 'status': status, 'references': references,
                'proposed_icon_id': icon_id if different else None,
                'proposed_filename': 'jp_icon_' + icon_id + '.png' if different else None})
        result = {'schema': 1, 'status': 'CANONICAL_PIXELS_COMPARED_NO_NATIVE_WRITES',
            'primary_map_sha256': sha(mapping_raw), 'source_packages': packages, 'bindings': planned,
            'counts': dict(counts), 'binding_count': len(planned),
            'shared_consumer_review': [r for b in planned for r in b['references'] if r['action'] == 'requires_shared_consumer_identity_check'],
            'preservation': 'All current native files and masters unchanged. Current art is reused only after canonical byte/RGBA proof.',
            'native_master_sources': inputs.receipts}
        write(HOME / 'canonical-jp-icon-plan.json', result)
        print(json.dumps({'bindings': len(planned), 'counts': dict(counts),
                          'shared_consumer_review': len(result['shared_consumer_review'])}), flush=True)
        return result
    finally:
        cache.close(); inputs.close()


def apply_otherworld():
    """Fix the one reviewed genuinely wrong item image, without Global edits."""
    from recover_earlier_jp_event_rewards import contract_table
    plan_path = HOME / 'canonical-jp-icon-plan.json'
    plan = json.loads(plan_path.read_text('utf8'))
    primary_path = HOME / 'native-unit-id-map.json'
    primary_raw = primary_path.read_bytes()
    if sha(primary_raw) != plan['primary_map_sha256']:
        raise ValueError('Typed primary mapping changed after icon comparison')
    primary = json.loads(primary_raw)
    if primary['mappings']['F_ITEM_MST'].get('260000100') != '872100001':
        raise ValueError('Otherworld Brave source item mapping changed')
    original = next(b for b in plan['bindings'] if b['source_icon_id'] == '260000100')['canonical_original']
    png = (ROOT / original['path']).read_bytes()
    if sha(png) != original['sha256']: raise ValueError('Canonical source PNG changed')
    inspect_member('jp_icon_872100001.png', png)
    inputs = Inputs()
    icons = {r['0HUPxDf1']: r for r in inputs.current('F_ICON_MST')}
    items = {r['tL6G9egd']: r for r in inputs.current('F_ITEM_MST')}
    if '872100001' in icons: raise ValueError('Otherworld icon target occupied; compare before reuse')
    if items['872100001']['0HUPxDf1'] != '260000100': raise ValueError('Otherworld current item icon changed')
    icon = {'0HUPxDf1': '872100001', 'G4L0YIB2': 'Otherworld Brave', 'qtkvrS60': 'jp_icon_872100001.png'}
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY',
        'scope': 'One genuine Otherworld Brave icon collision; Global item/icon260000100 untouched',
        'tables': [contract_table(inputs, 'F_ICON_MST', '0HUPxDf1', [icon], 'replace'),
                   contract_table(inputs, 'F_ITEM_MST', 'tL6G9egd', [{'tL6G9egd': '872100001', '0HUPxDf1': '872100001'}])]}
    contract_path = HOME / 'Event rewards/native-otherworld-icon-import.json'
    write(contract_path, contract)
    cache = NativeCache()
    try:
        source_stem = Path(original['source_package']['path']).stem
        candidates = []
        for _, _, members in cache.packs:
            for member in members:
                match = re.fullmatch(r'native/(common_lang/sd/item/Ver(\d+)_' + source_stem + r'_common\.cpk)', member)
                if match: candidates.append((int(match[2]), match[1]))
        relative = max(candidates)[1]
        raw, origin = cache.read(relative)
        archive = cpk.Cpk.load_bytes(raw)
        old = Counter((e.full_path, e.id, sha(archive.file_bytes(i)), e.extract_size, str(e.user_string))
                      for i, e in enumerate(archive.file_infos()))
        if any(e.full_path == icon['qtkvrS60'] for e in archive.file_infos()):
            raise ValueError('Namespaced JP source PNG already present; compare before reuse')
        archive.add_bytes(png, icon['qtkvrS60'], id=max(e.id for e in archive.file_infos()) + 1)
        body = archive.save_bytes(); end = 16 + struct.unpack_from('<Q', body, 8)[0]
        body = global_cpk_header(body[:end]) + body[end:]
        check = cpk.Cpk.load_bytes(body)
        after = Counter((e.full_path, e.id, sha(check.file_bytes(i)), e.extract_size, str(e.user_string))
                        for i, e in enumerate(check.file_infos()))
        if old - after: raise ValueError('Existing Global CPK member, ID or metadata changed')
        added = [(i, e) for i, e in enumerate(check.file_infos()) if e.full_path == icon['qtkvrS60']]
        if len(added) != 1 or check.file_bytes(added[0][0]) != png:
            raise ValueError('Namespaced canonical original PNG readback differs')
        command = [sys.executable, str(ROOT / 'source/exvius/apply_jp_unit_tables.py'),
                   '--contract', str(contract_path), '--receipt', str(ROOT / 'logs/jp-otherworld-icon-native-integration.json')]
        subprocess.run(command, check=True)
        target = ROOT / 'data/overlay' / relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(body)
        if target.read_bytes() != body: raise ValueError('Native icon cache write differs')
        subprocess.run(command + ['--apply'], check=True)
        primary['mappings'].setdefault('F_ICON_MST', {})['260000100'] = '872100001'
        write(primary_path, primary)
        receipt = {'status': 'APPLIED_EXACT_ORIGINAL_JP_ICON', 'source': original,
            'target_icon': icon, 'item_id': '872100001', 'native_cpk': relative,
            'source_native_cpk': origin, 'before_sha256': sha(raw), 'output_sha256': sha(body),
            'preserved_members': sum(old.values()), 'added_members': 1,
            'all_prior_member_ids_payloads_and_metadata_preserved': True,
            'primary_map_before_sha256': sha(primary_raw), 'primary_map_after_sha256': sha(primary_path.read_bytes()),
            'Global_item_and_icon260000100_preserved': True}
        write(HOME / 'Event rewards/otherworld-brave-icon-integration.json', receipt)
        print(json.dumps({'status': receipt['status'], 'preserved_members': receipt['preserved_members'],
                          'added_original_PNG': 1, 'native_rows': 2}), flush=True)
    finally:
        cache.close(); inputs.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--compare', action='store_true')
    mode.add_argument('--apply-otherworld', action='store_true')
    args = parser.parse_args()
    compare() if args.compare else apply_otherworld()
