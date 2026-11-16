"""Stage original JP Reberta art in the existing native unit resource package."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
from cricodecs import cpk
from fill_content_from_memorial import global_cpk_header
from apply_jp_content import NativeCache

RELATIVE = 'common_lang/sd/unit/Ver20_unit6_common.cpk'
BASE_SHA256 = '05ad9df98dd324f37d471d220131497f90f42e364a7d282c76491fd6d13678ec'
FORMS = {'100014405', '100014406'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def restore_reberta():
    source = ROOT / 'data/client/files' / RELATIVE
    target = ROOT / 'data/overlay' / RELATIVE
    receipt = ROOT / 'logs/jp-native-art-integration.json'
    if (ROOT / 'logs/jp-unit-art-integration.json').exists():
        raise ValueError('The full JP unit import is already staged; reuse --unit-map to preserve it')
    baseline = source.read_bytes()
    if digest(baseline) != BASE_SHA256:
        raise ValueError('Pinned published native unit6 baseline changed')
    manifest = json.loads((ROOT / 'Japan content/Recovered assets/recovery-manifest.json').read_text(encoding='utf-8'))
    records = [r for r in manifest['files'] if r['kind'] == 'units' and r['source_identity'] in FORMS]
    if len(records) != 32 or {r['source_identity'] for r in records} != FORMS:
        raise ValueError('Both complete original Reberta JP forms are required')
    archive = cpk.Cpk.load_bytes(baseline)
    originals = {entry.full_path: (entry.id, digest(archive.file_bytes(i)))
                 for i, entry in enumerate(archive.file_infos())}
    next_id = max(entry.id for entry in archive.file_infos()) + 1
    for record in sorted(records, key=lambda r: r['source_member']):
        name = record['source_member']
        if name in originals:
            raise ValueError('Unexpected existing Reberta source identity: ' + name)
        payload = (ROOT / record['path']).read_bytes()
        if digest(payload) != record['sha256']:
            raise ValueError('Recovered original art hash changed: ' + name)
        archive.add_bytes(payload, name, id=next_id)
        next_id += 1
    body = archive.save_bytes()
    end = 16 + struct.unpack_from('<Q', body, 8)[0]
    body = global_cpk_header(body[:end]) + body[end:]
    check = cpk.Cpk.load_bytes(body)
    members = {entry.full_path: (entry.id, digest(check.file_bytes(i)))
               for i, entry in enumerate(check.file_infos())}
    if len(members) != len(originals) + len(records):
        raise ValueError('Native art merge changed the expected member count')
    if any(members[name] != value for name, value in originals.items()):
        raise ValueError('Native art merge changed an existing member or CRI ID')
    if any(members[r['source_member']][1] != r['sha256'] for r in records):
        raise ValueError('Native package did not retain exact original JP asset bytes')
    if target.exists() and target.read_bytes() != body:
        if not receipt.exists():
            raise ValueError('Refusing to overwrite an unowned native art overlay')
        prior = json.loads(receipt.read_text(encoding='utf-8'))
        if digest(target.read_bytes()) != prior['output_sha256']:
            raise ValueError('Native art overlay changed outside this importer')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    result = {'status': 'native cache overlay staged; phone playback not verified',
              'resource_id': '101006', 'resource_version': '20',
              'baseline': source.relative_to(ROOT).as_posix(), 'baseline_sha256': BASE_SHA256,
              'output': target.relative_to(ROOT).as_posix(), 'output_sha256': digest(body),
              'bytes': len(body), 'preserved_original_members': len(originals),
              'added_original_jp_members': len(records), 'unit_forms': sorted(FORMS),
              'added_files': [{k: r[k] for k in ('source_member', 'sha256', 'source_package', 'source_package_sha256')}
                              for r in records],
              'remaining': 'Use the existing data-only cache installer. Verify native icon, portrait and battle animations on the phone. No new APK or resource-version bump.'}
    receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('output', 'preserved_original_members', 'added_original_jp_members', 'output_sha256')}), flush=True)
    return result


def restore_unit_art(mapping_path):
    """Replace exact existing JP identities; add renamed collision forks once."""
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    if not (mapping.get('artwork_mapping_ready') or mapping.get('ready_for_native_merge')):
        raise ValueError('The unit mapping is not finalized for native integration')
    unit_map = mapping['mappings'].get('F_UNIT_MST', {})
    manifest = json.loads((ROOT / 'Japan content/Recovered assets/recovery-manifest.json').read_text(encoding='utf-8'))
    records = [r for r in manifest['files'] if r['kind'] == 'units']
    cache = NativeCache()
    try:
        packages = {}
        for _, _, names in cache.packs:
            for name in names:
                match = re.fullmatch(r'native/(common_lang/sd/unit/Ver(\d+)_(unit\d+_common\.cpk))', name)
                if match and (match[3] not in packages or int(match[2]) > packages[match[3]][0]):
                    packages[match[3]] = (int(match[2]), match[1])
        if 'unit6_common.cpk' not in packages:
            raise ValueError('The published unit resource group has no unit6 package')
        archives, originals, origins, memberships = {}, {}, {}, {}
        for _, relative in packages.values():
            body, origin = cache.read(relative)
            archive = cpk.Cpk.load_bytes(body)
            archives[relative] = archive
            originals[relative] = {e.full_path: (e.id, digest(archive.file_bytes(i)))
                                   for i, e in enumerate(archive.file_infos())}
            origins[relative] = {'path': origin, 'sha256': digest(body)}
            for name in originals[relative]:
                memberships.setdefault(name, []).append(relative)
        default = packages['unit6_common.cpk'][1]
        modified, expected, bindings = set(), {}, []
        for record in records:
            old_id = record['source_identity']
            target_id = unit_map.get(old_id, old_id)
            old_name = record['source_member']
            suffix = '_' + old_id + '.'
            if old_name.count(suffix) != 1:
                raise ValueError('Unexpected source member identity: ' + old_name)
            name = old_name.replace(suffix, '_' + target_id + '.')
            payload = (ROOT / record['path']).read_bytes()
            if digest(payload) != record['sha256']:
                raise ValueError('Original JP asset changed: ' + old_name)
            # Patch every effective existing occurrence so CRI bind priority cannot
            # select an older same-name sprite. New IDs exist in one package only.
            destinations = memberships.get(name) or [default]
            for relative in destinations:
                archive = archives[relative]
                entries = {e.full_path: i for i, e in enumerate(archive.file_infos())}
                if name in entries:
                    archive.replace_bytes(entries[name], payload)
                else:
                    next_id = max(e.id for e in archive.file_infos()) + 1
                    archive.add_bytes(payload, name, id=next_id)
                    memberships[name] = [relative]
                modified.add(relative)
                expected.setdefault(relative, {})[name] = digest(payload)
            bindings.append({'source_form': old_id, 'target_form': target_id,
                             'source_member': old_name, 'target_member': name,
                             'sha256': digest(payload), 'native_packages': destinations})
        prepared, receipts = {}, []
        for relative in sorted(modified):
            body = archives[relative].save_bytes()
            end = 16 + struct.unpack_from('<Q', body, 8)[0]
            body = global_cpk_header(body[:end]) + body[end:]
            check = cpk.Cpk.load_bytes(body)
            found = {e.full_path: (e.id, digest(check.file_bytes(i)))
                     for i, e in enumerate(check.file_infos())}
            for name, value in originals[relative].items():
                if name not in expected[relative] and found.get(name) != value:
                    raise ValueError('An unrelated native unit member changed: ' + name)
                if name in expected[relative] and found[name][0] != value[0]:
                    raise ValueError('An existing native CRI member ID changed: ' + name)
            if any(found[name][1] != value for name, value in expected[relative].items()):
                raise ValueError('Native JP art round-trip changed original decoded bytes')
            prepared[relative] = body
            receipts.append({'output': 'data/overlay/' + relative, 'source': origins[relative],
                             'output_sha256': digest(body), 'bytes': len(body),
                             'requested_members': len(expected[relative]),
                             'existing_members_preserved_or_explicitly_replaced': len(originals[relative])})
        for relative, body in prepared.items():
            target = ROOT / 'data/overlay' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        result = {'status': 'JP unit art native overlays applied; phone playback pending',
                  'mapping': mapping_path.relative_to(ROOT).as_posix(),
                  'mapping_sha256': digest(mapping_path.read_bytes()),
                  'unit_forms': len({r['source_identity'] for r in records}),
                  'members': len(records), 'packages': receipts, 'bindings': bindings,
                  'native_binding': {'original_gl9_lib_sha256': 'a127654037f2f28a70cce7c64ff0a9d291770ea904cdf5bcba59a7af9a6937e4',
                                     'library_unit_group_getter': '0x22f0fe0 -> unit',
                                     'cgs_filename_uses_unit_id': 'GameUtils::setUnitCgsFileName at 0x19e6dc4',
                                     'group_binding': 'CriUtils::groupBindCpkAsync(const char*, bool) at 0x1efaa18'},
                  'resource_versions_changed': False}
        (ROOT / 'logs/jp-unit-art-integration.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'unit_forms': result['unit_forms'], 'original_jp_members': len(records),
                          'native_packages': len(prepared), 'unrelated_members_preserved': True}), flush=True)
        return result
    finally:
        cache.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit-map', type=Path)
    args = parser.parse_args()
    if args.unit_map:
        restore_unit_art(args.unit_map.resolve())
    else:
        restore_reberta()
