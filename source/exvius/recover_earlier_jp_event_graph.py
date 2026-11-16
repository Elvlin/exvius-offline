"""Stage original Japanese event metadata and exact native resource bindings.

Uses the established native getter and master decoder. Source records and IDs
are preserved. Existing identities must agree before an ID can be reused.
This tool never enables a catalogue entry or a battle and never builds an APK.
"""
import csv
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

from decode_client_data import TRIPLET, decode, getter_manifest

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / 'Japan content'
EARLIER = CONTENT / 'Earlier JP crossovers'
PACKS = CONTENT / 'Shared sources/jp_andapp'
OUT = EARLIER / 'Sources/Event graph'
NATIVE_SHA = '6c7e501c98939581528df3d712ff1f58afcfd392160f1e71ef1f903d49926b77'
TOKENS = ('Fvix6V0n', '1Bj4oy5Q', '24Eka6wL', 'GL9t6cMF', '2Jtkc4Ar',
          '91vNbdxg', 'En90A5BC', 'B7LnP2TH', 'ZQqB38Ns')
KEYS = {'F_AREA_MST': 'uv60hgDW', 'F_DUNGEON_MST': 'U9iHsau3',
        'F_MISSION_MST': 'qo3PECw6', 'F_CHALLENGE_MST': 'V36ygRYs',
        'F_RESOURCE_MAP_MST': 'Nnb20keZ', 'F_RESOURCE_MST': '9ZCEWn0z',
        'F_MAP_EVENT_MST': 'Lxj5u3WB', 'F_MAP_EXT_RESOURCE_MST': 'Lxj5u3WB'}
# Identity columns have established owner/type meanings in the retained native
# graph. Costs, rewards and versioned behavior are intentionally not identities.
IDENTITY = {'F_AREA_MST': ('uv60hgDW', '9Pb24aSy', 'Esxe71j3'),
            'F_DUNGEON_MST': ('U9iHsau3', 'uv60hgDW', '9Pb24aSy', 'Esxe71j3'),
            'F_MISSION_MST': ('qo3PECw6', 'U9iHsau3', 'uv60hgDW', '9Pb24aSy',
                              'Esxe71j3', 'gQR24kST', 'Y4VoF8yu'),
            'F_CHALLENGE_MST': ('V36ygRYs', 'qo3PECw6', 'Z0EN6jSh', 'Pzn5h0Ga'),
            'F_RESOURCE_MAP_MST': ('Nnb20keZ', 'drE35YcF', 'pJ56sAEo'),
            'F_RESOURCE_MST': ('9ZCEWn0z', 'drE35YcF', 'pJ56sAEo')}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8-sig').splitlines() if s.strip()]


def normal(value):
    return unicodedata.normalize('NFKC', str(value or '')).replace(' ', '').replace('\u3000', '')


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_tables():
    native_path = ROOT / 'repository snapshots/FFBE-Memorial-EN-Global-Events-v208.apk'
    with zipfile.ZipFile(native_path) as archive:
        native = archive.read('lib/arm64-v8a/libgame.so')
    if sha(native) != NATIVE_SHA:
        raise ValueError('Original Japanese native getter authority changed.')
    manifest = getter_manifest(native)
    for match in TRIPLET.finditer(native):
        name, token, key = (s.decode() for s in match.groups())
        entry = {'table': name, 'token': token, 'key': key}
        if token in manifest and manifest[token] != entry:
            raise ValueError('Native getter and literal triplet disagree.')
        manifest[token] = entry
    metadata = json.loads((CONTENT / 'Shared sources/original-jp-master-download-sources.json').read_text())
    metadata = {r['name']: r for r in metadata['files']}
    tables, receipts = {}, []
    for token in TOKENS:
        candidates = list(PACKS.glob('Ver*_' + token + '.dat'))
        if len(candidates) != 1:
            raise ValueError('Expected one acquired original master: ' + token)
        path = candidates[0]
        raw, expected = path.read_bytes(), metadata[path.name]
        if len(raw) != int(expected['size']) or hashlib.md5(raw).hexdigest() != expected['md5'] or hashlib.sha1(raw).hexdigest() != expected['sha1']:
            raise ValueError('Original archive source checksum failed: ' + path.name)
        mode, decoded = decode(raw, manifest[token]['key'])
        table = manifest[token]['table']
        tables[table] = decoded
        receipts.append({'table': table, 'path': relative(path), 'token': token,
                         'sha256': sha(raw), 'mode': mode, 'decoded_rows': len(decoded),
                         'native_library_sha256': NATIVE_SHA})
    return tables, receipts


def pack_source(filename, file_index, metadata):
    candidates = [PACKS / filename]
    candidates += [ROOT / r['project_path'] for r in file_index if r['filename'] == filename]
    found = []
    expected = metadata.get(filename)
    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        exact = bool(expected and len(raw) == int(expected['size']) and hashlib.md5(raw).hexdigest() == expected.get('md5') and hashlib.sha1(raw).hexdigest() == expected.get('sha1'))
        found.append({'path': relative(path), 'bytes': len(raw), 'sha256': sha(raw),
                      'matches_original_archive_bytes': exact})
    return found


def retained_battle_graph(selected, receipts):
    """Preserve every original lottery alternative, including unplayable gaps."""
    base = CONTENT / 'Shared sources/memorial_battle_decoded'
    mission_ids = {r['qo3PECw6'] for r in selected['F_MISSION_MST']}

    def read(table, folder=base):
        path = folder / (table + '.ndjson')
        raw = path.read_bytes()
        values = rows(path)
        receipts.append({'table': table, 'path': relative(path), 'sha256': sha(raw),
                         'decoded_rows': len(values),
                         'source_class': 'retained native source; live JP source-version comparison unavailable'})
        return values

    phases = [r for r in read('F_MISSION_PHASE_MST') if r['qo3PECw6'] in mission_ids]
    pools = {r['6uIYE15X'] for r in phases if r['gou39JeI'] == '2'}
    lotteries = [r for r in read('F_BATTLE_LOTTERY_MST') if r['c2gnh6Jd'] in pools]
    group_ids = {r['2fY1IomW'] for r in lotteries}
    groups = [r for r in read('F_BATTLE_GROUP_MST') if r['2fY1IomW'] in group_ids]
    enemies = {r['xqartN26'] for r in groups}
    positive_groups = {r['2fY1IomW'] for r in lotteries if int(r.get('ixDq7yJ8') or 0) > 0}
    positive_enemies = {r['xqartN26'] for r in groups if r['2fY1IomW'] in positive_groups}
    monsters = [r for r in read('F_MONSTER_MST') if r['xqartN26'] in enemies]
    parts = [r for r in read('F_MONSTER_PARTS_MST') if r['xqartN26'] in enemies]
    skillset_ids = {r['A5x02C6a'] for r in parts if r.get('A5x02C6a') not in (None, '', '0')}
    ai_ids = {r['8a6gAwN9'] for r in parts if r.get('8a6gAwN9') not in (None, '', '0')}
    skillsets = [r for r in read('F_MONSTER_SKILL_SET_MST') if r['A5x02C6a'] in skillset_ids]
    skills_wanted = {s.strip() for r in skillsets for s in r['7qxLC5hP'].split(',') if s.strip()}
    skills = [r for r in read('F_MONSTER_SKILL_MST') if r['6E5u1xrs'] in skills_wanted]
    ai = [r for r in read('F_AI_MST', ROOT / 'data/mst_decoded') if r['8a6gAwN9'] in ai_ids]
    for table, values in [('F_MISSION_PHASE_MST', phases), ('F_BATTLE_LOTTERY_MST', lotteries),
                          ('F_BATTLE_GROUP_MST', groups), ('F_MONSTER_MST', monsters),
                          ('F_MONSTER_PARTS_MST', parts), ('F_MONSTER_SKILL_SET_MST', skillsets),
                          ('F_MONSTER_SKILL_MST', skills), ('F_AI_MST', ai)]:
        selected[table] = values
    missing_monsters = sorted(enemies - {r['xqartN26'] for r in monsters}, key=int)
    missing_parts = sorted(enemies - {r['xqartN26'] for r in parts}, key=int)
    return {'phase_rows': len(phases), 'lottery_rows': len(lotteries), 'group_rows': len(groups),
            'weighted_pool_count': len(pools), 'group_count': len(group_ids),
            'enemy_identities': len(enemies), 'owned_body_rows': len(monsters), 'owned_part_rows': len(parts),
            'positive_weight_group_count': len(positive_groups),
            'positive_weight_enemy_identities': len(positive_enemies),
            'positive_weight_owned_body_rows': sum(r['xqartN26'] in positive_enemies for r in monsters),
            'positive_weight_owned_part_rows': sum(r['xqartN26'] in positive_enemies for r in parts),
            'nonpositive_weight_lottery_rows': sum(int(r.get('ixDq7yJ8') or 0) <= 0 for r in lotteries),
            'missing_pool_ids': sorted(pools - {r['c2gnh6Jd'] for r in lotteries}, key=int),
            'missing_group_ids': sorted(group_ids - {r['2fY1IomW'] for r in groups}, key=int),
            'missing_original_body_ids': missing_monsters, 'missing_original_part_ids': missing_parts,
            'bound_AI_ids': sorted(ai_ids, key=int),
            'bound_AI_ids_absent_from_retained_source': sorted(ai_ids - {r['8a6gAwN9'] for r in ai}, key=int),
            'bound_skillset_ids_absent_from_retained_source': sorted(skillset_ids - {r['A5x02C6a'] for r in skillsets}, key=int),
            'bound_skill_ids_absent_from_retained_source': sorted(skills_wanted - {r['6E5u1xrs'] for r in skills}, key=int),
            'missing_part_binding_limit': 'Original body/part gaps prevent recovering their actual AI, skill-set, drop and model pointers. Same-ID support candidates remain in the separate Battle recovery bundle.'}


def main():
    tables, receipts = source_tables()
    stage_rows = list(csv.DictReader((EARLIER / 'stage-details.csv').open(encoding='utf-8-sig', newline='')))
    mission_ids = {r['mission_id'] for r in stage_rows}
    selected = {'F_MISSION_MST': [r for r in tables['F_MISSION_MST'] if r['qo3PECw6'] in mission_ids]}
    if {r['qo3PECw6'] for r in selected['F_MISSION_MST']} != mission_ids or len(mission_ids) != 130:
        raise ValueError('The original Japanese master does not cover the exact 130 stage scope.')
    dungeon_ids = {r['U9iHsau3'] for r in selected['F_MISSION_MST']}
    area_ids = {r['uv60hgDW'] for r in selected['F_MISSION_MST']}
    selected['F_DUNGEON_MST'] = [r for r in tables['F_DUNGEON_MST'] if r['U9iHsau3'] in dungeon_ids]
    selected['F_AREA_MST'] = [r for r in tables['F_AREA_MST'] if r['uv60hgDW'] in area_ids]
    selected['F_CHALLENGE_MST'] = [r for r in tables['F_CHALLENGE_MST'] if r['qo3PECw6'] in mission_ids]
    if len(dungeon_ids) != 28 or len(area_ids) != 28:
        raise ValueError('Expected 28 native event area/dungeon sets.')
    all_owners = mission_ids | dungeon_ids | area_ids
    for table in ('F_MAP_EVENT_MST', 'F_MAP_EXT_RESOURCE_MST'):
        selected[table] = [r for r in tables[table] if r.get('6uIYE15X') in all_owners]
    resource_ids = {ident for table in ('F_AREA_MST', 'F_DUNGEON_MST', 'F_MISSION_MST')
                    for r in selected[table] for ident in r.get('q4f9IdMs', '').split(',') if ident}
    resource_ids.update(r[k] for r in selected['F_MISSION_MST'] for k in ('bs60p4LC', '6w4xiIsS') if r.get(k) not in ('', '0', None))
    selected['F_RESOURCE_MAP_MST'] = [r for r in tables['F_RESOURCE_MAP_MST'] if r['Nnb20keZ'] in resource_ids]
    # q4f9IdMs is the map-resource selector namespace. Retain an ordinary
    # resource record only for a selector not provided by the map table.
    mapped = {r['Nnb20keZ'] for r in selected['F_RESOURCE_MAP_MST']}
    selected['F_RESOURCE_MST'] = [r for r in tables['F_RESOURCE_MST'] if r['9ZCEWn0z'] in resource_ids - mapped]
    missing_resources = sorted(resource_ids - mapped - {r['9ZCEWn0z'] for r in selected['F_RESOURCE_MST']}, key=int)
    current = {}
    id_map, conflicts, route_differences, version_changes = [], [], [], []
    for table, key in KEYS.items():
        current[table] = {r[key]: r for r in rows(ROOT / 'data/mst_decoded' / (table + '.ndjson'))}
        for r in selected[table]:
            ident = r[key]
            previous = current[table].get(ident)
            fields = IDENTITY.get(table, (key,))
            changed = [k for k in fields if previous and normal(r.get(k)) != normal(previous.get(k))]
            if previous and 'G4L0YIB2' in r and normal(r['G4L0YIB2']) != normal(previous.get('G4L0YIB2')):
                changed.append('G4L0YIB2')
            if changed:
                conflicts.append({'table': table, 'id': ident, 'fields': changed})
            if previous:
                diffs = [k for k in r if normal(r.get(k)) != normal(previous.get(k))]
                if diffs:
                    version_changes.append({'table': table, 'id': ident, 'fields': diffs})
                route_fields = ('juA0Z4m7', 'U9hr20s7', '0HUPxDf1', 'DutE7B3F') if table in ('F_AREA_MST', 'F_DUNGEON_MST') else ('juA0Z4m7', 'U9hr20s7', '1C7GDEv4', 'dIPkNn61') if table == 'F_MISSION_MST' else ()
                route_diff = [k for k in route_fields if normal(r.get(k)) != normal(previous.get(k))]
                if route_diff:
                    route_differences.append({'table': table, 'id': ident, 'fields': route_diff,
                                              'policy': 'Keep original JP route fields in staged source; no gate removal.'})
            id_map.append({'table': table, 'source_id': ident, 'target_id': ident,
                           'identity_status': 'CONFLICT' if changed else 'SAME_NATIVE_IDENTITY' if previous else 'UNUSED_TYPED_ID',
                           'identity_fields': ';'.join(fields), 'source_name': r.get('G4L0YIB2', '')})
    if conflicts:
        raise ValueError('Distinct identities require explicit unused typed ID remapping: ' + json.dumps(conflicts))
    combat = retained_battle_graph(selected, receipts)
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = []
    for table, values in selected.items():
        if not values:
            continue
        data = ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n' for r in values).encode('utf-8')
        path = OUT / (table + '.ndjson')
        path.write_bytes(data)
        if rows(path) != values:
            raise ValueError('Original record readback changed.')
        outputs.append({'table': table, 'file': relative(path), 'rows': len(values), 'sha256': sha(data)})
    with (OUT / 'native-id-map.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(id_map[0]))
        writer.writeheader(); writer.writerows(id_map)
    localization = json.loads((EARLIER / 'Sources/earlier-event-english-localization.json').read_text(encoding='utf-8'))
    text_tables = {'F_TEXT_AREA_NAME': ('F_AREA_MST', 'uv60hgDW'),
                   'F_TEXT_DUNGEON_NAME': ('F_DUNGEON_MST', 'U9iHsau3'),
                   'F_TEXT_MISSION': ('F_MISSION_MST', 'qo3PECw6'),
                   'F_TEXT_CHALLENGE_NAME': ('F_CHALLENGE_MST', 'V36ygRYs'),
                   'F_TEXT_ITEM_NAME': ('F_ITEM_MST', 'tL6G9egd'),
                   'F_TEXT_ITEM_EQUIP_NAME': ('F_EQUIP_ITEM_MST', 'J1YX9kmM')}
    native_lookup = {table: {r[key]: r for r in tables[table]}
                     for table, key in text_tables.values() if table in tables}
    item_lookup = {}
    for item_table, item_key in (('F_ITEM_MST', 'tL6G9egd'), ('F_EQUIP_ITEM_MST', 'J1YX9kmM')):
        for item in rows(ROOT / 'data/mst_decoded' / (item_table + '.ndjson')):
            item_lookup[item[item_key]] = (item_table, item_key, item)
    bindings, text_sources = [], []
    for text_table, (table, key) in text_tables.items():
        text_path = EARLIER / 'Sources' / ('earlier-' + text_table + '.en.ndjson')
        english = {r['key']: r for r in rows(text_path)}
        expected_rows = [r for r in localization['rows'] if r['table'] == text_table]
        for r in expected_rows:
            ident = r['source_id']
            bound_table, bound_key = table, key
            if text_table in ('F_TEXT_ITEM_NAME', 'F_TEXT_ITEM_EQUIP_NAME'):
                bound_table, bound_key, native = item_lookup.get(ident, (table, key, None))
                if bound_table != table:
                    raise ValueError('Item and equipment English table namespaces differ: ' + r['key'])
            else:
                native = native_lookup[table].get(ident)
            if native is None or r['key'] not in english or english[r['key']]['v'] != r['v']:
                raise ValueError('Unbound English native identity: ' + r['key'])
            if text_table in ('F_TEXT_ITEM_NAME', 'F_TEXT_ITEM_EQUIP_NAME', 'F_TEXT_CHALLENGE_NAME') and normal(native.get('G4L0YIB2')) != normal(r['source_jp']):
                raise ValueError('English source describes another native identity: ' + r['key'])
            bindings.append({'table': text_table, 'key': r['key'], 'source_id': ident,
                             'target_id': ident, 'native_table': bound_table, 'native_key': bound_key,
                             'native_name': native.get('G4L0YIB2', ''),
                             'native_owner': native.get('qo3PECw6') if table == 'F_CHALLENGE_MST' else native.get('U9iHsau3') if table == 'F_MISSION_MST' else native.get('uv60hgDW') if table == 'F_DUNGEON_MST' else None,
                             'scope': 'existing Vow event, not a new event import' if ident in ('6211', '621101') else 'earlier JP source translation',
                             'authority': 'retained native item/equipment master; original live version still needs comparison' if table in ('F_ITEM_MST', 'F_EQUIP_ITEM_MST') else 'original live Japanese archive master'})
        text_sources.append({'table': text_table, 'file': relative(text_path), 'rows': len(english), 'sha256': sha(text_path.read_bytes())})
    if len(bindings) != 654:
        raise ValueError('Expected all 654 authored English rows to bind native identities.')
    write_json('english-import.json', {'schema': 1, 'activation': 'staged, not applied',
              'text_tables': text_sources, 'bindings': bindings, 'id_replacements': {},
              'merge_contract': 'Merge exact keys into the existing native English F_TEXT tables using loading_text. Both existing v columns are retained. Do not change unrelated text rows or activate event menus.',
              'item_version_limit': '18 item labels bind retained native identities. Their live JP source version is not certified by these nine acquired tables.'})
    with (CONTENT / 'Shared sources/memorial-file-index.csv').open(encoding='utf-8-sig', newline='') as handle:
        file_index = list(csv.DictReader(handle))
    metadata = {r['name']: r for r in json.loads((CONTENT / 'Shared sources/original-jp-archive-index.json').read_text())['files']}
    resource_map = {r['Nnb20keZ']: r for r in selected['F_RESOURCE_MAP_MST']}
    asset_ownership = {r['pJ56sAEo']: pack_source(r['pJ56sAEo'], file_index, metadata) for r in selected['F_RESOURCE_MAP_MST']}
    sys.path.insert(0, str(ROOT / 'custom-engine/tools'))
    from cpk import Cpk
    field_bindings = []
    for stage in stage_rows:
        if stage['jp_high_level_type'] != 'EXPLORATION':
            continue
        mission = next(r for r in selected['F_MISSION_MST'] if r['qo3PECw6'] == stage['mission_id'])
        native_resources = []
        for rid in mission['q4f9IdMs'].split(','):
            resource = resource_map[rid]
            entry = {'resource_id': rid, 'directory': resource['3LHdc6Qa'],
                     'type': resource['drE35YcF'], 'filename': resource['pJ56sAEo'],
                     'original_source_paths': asset_ownership[resource['pJ56sAEo']]}
            if resource['pJ56sAEo'].endswith('.cpk'):
                pack = PACKS / resource['pJ56sAEo']
                archive = Cpk(pack.read_bytes())
                entry['original_members'] = [{'name': n, 'stored_bytes': archive.files[n][1],
                                             'extracted_bytes': len(archive.read(n)), 'sha256': sha(archive.read(n))}
                                            for n in archive.files]
            native_resources.append(entry)
        field_bindings.append({'mission_id': mission['qo3PECw6'], 'dungeon_id': mission['U9iHsau3'],
                               'area_id': mission['uv60hgDW'], 'native_type': mission['gQR24kST'],
                               'native_resources': native_resources,
                               'script_policy': 'Preserve original map.bin and event.bin, native mission resource order and IDs. Use the native field engine; no synthetic opening phases or inferred command operands.',
                               'native_script_semantics_verified': False})
    write_json('field-resource-bindings.json', {'schema': 1, 'missions': field_bindings,
              'map_event_master_rows': len(selected['F_MAP_EVENT_MST']),
              'map_ext_resource_master_rows': len(selected['F_MAP_EXT_RESOURCE_MST']),
              'limits': 'Exact native mission-to-map/script binding and original package bytes are recovered. No demonstrated parser or device run has established field-script behavior or completion callbacks.'})
    status = {'schema': 1, 'activation': 'inactive original source graph; no catalogue or production changes',
              'native_authority_sha256': NATIVE_SHA, 'sources': receipts, 'outputs': outputs,
              'event_sets': len(dungeon_ids), 'unique_stages': len(mission_ids),
              'native_challenge_rows': len(selected['F_CHALLENGE_MST']), 'english_rows_bound': len(bindings),
              'identity_conflicts': conflicts, 'id_replacements': {}, 'id_policy': 'Preserve IDs only after native owner/type/name comparison. No conflicting source identity was encountered, so no new IDs were assigned.',
              'route_comparisons': route_differences, 'versioned_record_differences': version_changes,
              'missing_native_resource_selectors': missing_resources,
              'asset_sources': asset_ownership, 'exploration_bindings': len(field_bindings),
              'retained_battle_graph': combat,
              'zero_matching_auxiliary_rows': ['F_MAP_EVENT_MST', 'F_MAP_EXT_RESOURCE_MST'],
              'battles_enabled': 0, 'remaining_battle_source_blocker': str(len(combat['missing_original_body_ids'])) + ' original monster body and part identities are absent from inspected sources. Phase/lottery/group originals survive in retained Memorial source, but their exact live JP source version is not in the live archive.',
              'shared_encounter_profiles': 'F_ENCOUNT_FIELD_MST source is decoded and checksum verified; no proven native field-rate selector for these scripts was inferred.'}
    write_json('graph-status.json', status)
    print(json.dumps({k: status[k] for k in ('event_sets', 'unique_stages', 'native_challenge_rows', 'english_rows_bound', 'identity_conflicts', 'exploration_bindings', 'missing_native_resource_selectors', 'battles_enabled')}))


if __name__ == '__main__':
    main()
