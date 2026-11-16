"""Recover exact original JP unit dependencies without changing the live dataset.

The selected source rows are retained with their original identities first. The
import material is produced separately after checking the effective public
dataset, never by reconstructing gameplay values from community descriptions.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re
import zipfile

from decode_client_data import client_manifest, decode

PROJECT = Path(__file__).resolve().parents[2]
SHARED = PROJECT / 'Japan content/Shared sources'
HOME = PROJECT / 'Japan content/Earlier JP crossovers'
SOURCE = SHARED / 'jp_andapp'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def numbers(value):
    """Conservative source dependency discovery, not a parameter rewrite rule."""
    return set(re.findall(r'(?<![0-9])[0-9]+(?![0-9])', str(value)))


class Inputs:
    def __init__(self):
        original = PROJECT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk'
        self.manifest = {v['table']: dict(v, token=k)
                         for k, v in client_manifest(original).items()}
        self.receipts = {}
        self.rows = {}
        self.current_rows = {}
        self.public_manifest = json.loads((PROJECT /
            'source/build/distribution/repository/data/latest.json').read_text('utf-8'))
        self.packs = []
        for pack in self.public_manifest['packs']:
            path = PROJECT / 'source/build/distribution/assets' / pack['url'].rsplit('/', 1)[-1]
            if path.is_file():
                archive = zipfile.ZipFile(path)
                self.packs.append((path, archive, set(archive.namelist())))

    def original(self, table, required=True):
        if table in self.rows:
            return self.rows[table]
        entry = self.manifest.get(table)
        if entry is None:
            if required:
                raise ValueError('Original client has no getter: ' + table)
            return []
        files = list(SOURCE.glob('Ver*_' + entry['token'] + '.dat'))
        if not files:
            if required:
                raise FileNotFoundError(table + ' original source token ' + entry['token'])
            return []
        path = max(files, key=lambda p: int(p.name.split('_')[0][3:]))
        raw = path.read_bytes()
        _, rows = decode(raw, entry['key'])
        self.rows[table] = rows
        self.receipts[table] = {'path': path.relative_to(PROJECT).as_posix(),
            'sha256': digest(raw), 'bytes': len(raw), 'rows': len(rows)}
        return rows

    def current(self, table):
        if table in self.current_rows:
            return self.current_rows[table]
        relative = 'static/mst_decoded/' + table + '.ndjson'
        raw = None
        location = None
        for path, archive, names in self.packs:
            if relative in names:
                raw = archive.read(relative)
                location = str(path.relative_to(PROJECT)) + ':' + relative
        if raw is None:
            path = PROJECT / 'data/mst_decoded' / (table + '.ndjson')
            if path.is_file():
                raw = path.read_bytes()
                location = path.relative_to(PROJECT).as_posix()
        rows = [json.loads(line) for line in (raw or b'').splitlines() if line.strip()]
        entry = self.manifest.get(table)
        native_path = None
        if entry:
            suffix = '_' + entry['token'] + '.dat'
            for pack_path, _, names in self.packs:
                members = [n for n in names if n.startswith('native/mst/') and n.endswith(suffix)]
                if members:
                    member = max(members, key=lambda n: int(n.rsplit('/', 1)[-1].split('_')[0][3:]))
                    native_path = {'container': pack_path.relative_to(PROJECT).as_posix(), 'member': member}
            overlay = list((PROJECT / 'data/overlay/mst').glob('Ver*' + suffix))
            if overlay:
                path = max(overlay, key=lambda p: int(p.name.split('_')[0][3:]))
                native = path.read_bytes()
                _, rows = decode(native, entry['key'])
                location = path.relative_to(PROJECT).as_posix()
                raw = b'\n'.join(json_bytes(r) for r in rows) + b'\n'
                native_path = {'path': location, 'sha256': digest(native)}
            if native_path is None:
                local = list((PROJECT / 'data/client/files/mst').glob('Ver*' + suffix))
                if local:
                    path = max(local, key=lambda p: int(p.name.split('_')[0][3:]))
                    native_path = {'path': path.relative_to(PROJECT).as_posix()}
            if native_path:
                if 'container' in native_path:
                    archive = next(z for p, z, _ in self.packs
                                   if p.relative_to(PROJECT).as_posix() == native_path['container'])
                    native = archive.read(native_path['member'])
                else:
                    native = (PROJECT / native_path['path']).read_bytes()
                _, rows = decode(native, entry['key'])
                native_path['sha256'] = digest(native)
        self.current_rows[table] = rows
        self.receipts['current:' + table] = {'path': location,
            'decoded_sha256': digest(raw or b''), 'decoded_canonical_sha256': digest(json_bytes(rows)),
            'active_native_source': native_path, 'rows': len(rows)}
        return rows

    def text(self, table):
        relative = 'static/text_decoded/' + table + '.ndjson'
        raw = None
        for _, archive, names in self.packs:
            if relative in names:
                raw = archive.read(relative)
        if raw is None:
            path = PROJECT / 'data/text_decoded' / (table + '.ndjson')
            if path.is_file():
                raw = path.read_bytes()
        result = {r['key']: r['v'][0] for r in
                  (json.loads(line) for line in (raw or b'').splitlines() if line.strip())}
        local = PROJECT / 'data/text_decoded' / (table + '.ndjson')
        if local.is_file():
            result.update({r['key']: r['v'][0] for r in
                           (json.loads(line) for line in local.read_bytes().splitlines() if line.strip())})
        return result

    def close(self):
        for _, archive, _ in self.packs:
            archive.close()


def community():
    path = SHARED / 'ffbe-jp-ea7d9fa82659.zip'
    with zipfile.ZipFile(path) as archive:
        documents = {}
        for name in ('units', 'skills_ability', 'skills_passive', 'skills_magic', 'limitbursts'):
            member = next(x for x in archive.namelist() if x.endswith('/' + name + '.json'))
            documents[name] = json.loads(archive.read(member))
    return documents


def text_specs():
    return [('F_UNIT_MST', '3HriTp6B', 'F_TEXT_UNITS_NAME', 'MST_UNIT_NAME_', 'G4L0YIB2'),
                ('F_ABILITY_MST', 'Ga5V42LZ', 'F_TEXT_ABILITY_NAME', 'MST_ABILITY_NAME_', 'G4L0YIB2'),
                ('F_LIMITBURST_MST', 'PR2HIc71', 'F_TEXT_LIMIT_BURST_NAME', 'MST_LIMITBURST_NAME_', 'G4L0YIB2'),
                ('F_ABILITY_EXPLAIN_MST', 'Ga5V42LZ', 'F_TEXT_ABILITY_EXPLAIN_SHORT', 'MST_ABILITY_SHORTDESCRIPTION_', 'T7aEx3Mj'),
                ('F_LIMITBURST_MST', 'PR2HIc71', 'F_TEXT_LIMIT_BURST_DES', 'MST_LIMITBURST_DESCRIPTION_', '6uvHX2JG'),
                ('F_MAGIC_MST', 'QV1HE7Wq', 'F_TEXT_MAGIC_NAME', 'MST_MAGIC_NAME_', 'G4L0YIB2'),
                ('F_UNIT_EXPLAIN_MST', '3HriTp6B', 'F_TEXT_UNIT_DESCRIPTION', 'MST_UNIT_EXPLAIN_DESCRIPTION_', 'fYhnz5N9'),
                ('F_UNIT_EXPLAIN_MST', '3HriTp6B', 'F_TEXT_UNIT_SUMMON', 'MST_UNIT_EXPLAIN_SUMMON_', 'BGWpF0i2'),
                ('F_UNIT_EXPLAIN_MST', '3HriTp6B', 'F_TEXT_UNIT_FUSION', 'MST_UNIT_EXPLAIN_FUSION_', 'J5QKLzW7'),
                ('F_UNIT_EXPLAIN_MST', '3HriTp6B', 'F_TEXT_UNIT_EVO', 'MST_UNIT_EXPLAIN_EVOLUTION_', 'SAh4cnW2'),
                ('F_UNIT_EXPLAIN_MST', '3HriTp6B', 'F_TEXT_UNIT_AFFINITY', 'MST_UNIT_EXPLAIN_AFFINITY_', 'Q1d8m7yt'),
                ('F_EQUIP_ITEM_MST', 'J1YX9kmM', 'F_TEXT_ITEM_EQUIP_NAME', 'MST_EQUIP_ITEM_NAME_', 'G4L0YIB2'),
                ('F_MATERIA_MST', 'H5jBL0Vf', 'F_TEXT_MATERIA_NAME', 'MST_MATERIA_NAME_', 'G4L0YIB2'),
                ('F_ITEM_MST', 'tL6G9egd', 'F_TEXT_ITEM_NAME', 'MST_ITEM_NAME_', 'G4L0YIB2'),
                ('F_VISION_CARD_MST', '5giCMUd2', 'F_TEXT_VISION_CARD_NAME', 'MST_VISION_CARD_NAME_', 'G4L0YIB2')]


def export_text_requests(inputs, source, destination):
    requests = []
    plan_path = HOME / 'Sources/native-unit-id-map.json'
    remaps = json.loads(plan_path.read_text('utf-8')).get('mappings', {}) if plan_path.is_file() else {}
    mappings = text_specs()
    documents = community()
    community_skills = dict(documents['skills_ability'], **documents['skills_passive'])
    association = {}
    for ident, unit in documents['units'].items():
        if set(unit.get('entries', {})) & {r['3HriTp6B'] for r in source['tables']['F_UNIT_MST']['rows']}:
            for skill in unit.get('skills', []):
                association.setdefault(str(skill['id']), []).append(ident)
    for table, key, text_table, prefix, field in mappings:
        current = {r[key]: r for r in inputs.current(table)}
        english = inputs.text(text_table)
        for row in source['tables'][table]['rows']:
            ident = row[key]
            jp = row.get(field, '')
            candidate = english.get(prefix + ident) or current.get(ident, {}).get(field, '')
            if not jp:
                continue
            reference_table = 'F_ABILITY_MST' if table == 'F_ABILITY_EXPLAIN_MST' else ('F_UNIT_MST' if table == 'F_UNIT_EXPLAIN_MST' else table)
            changed = ident in remaps.get(reference_table, {})
            if candidate and not changed and not re.search('[\u3040-\u30ff\u3400-\u9fff]', candidate):
                continue
            requests.append({'table': text_table, 'native_key': prefix + ident,
                'source_id': ident, 'jp': jp, 'existing_english_candidate': candidate,
                'unit_dictionary_ids': association.get(ident, []),
                'community_effects': community_skills.get(ident, {}).get('effects', [])})
    english_ex = inputs.text('F_TEXT_NV_UNIT_CLASS_UP')
    for row in source['tables'].get('F_NV_EX_CLASS_UP_MST', {}).get('rows', []):
        ident = row['JPW8Vs40']
        key = 'MST_NV_CLASS_UP_' + ident + '_' + row['f8vk4JrD']
        jp = row.get('q4mpoKz2', '')
        candidate = english_ex.get(key, '')
        if jp and (ident in remaps.get('F_UNIT_MST', {}) or not candidate or re.search('[\u3040-\u30ff\u3400-\u9fff]', candidate)):
            requests.append({'table': 'F_TEXT_NV_UNIT_CLASS_UP', 'native_key': key,
                'source_id': ident, 'jp': jp, 'existing_english_candidate': candidate,
                'unit_dictionary_ids': [ident], 'community_effects': []})
    destination.write_bytes(json_bytes({'schema': 1, 'bindings': requests}) + b'\n')
    print('Translation requests: ' + str(len(requests)) + ' at ' + str(destination))


def english_value(value):
    return bool(value and value.strip() not in ('<blank>', 'Test data') and
                not re.search('[\u3040-\u30ff\u3400-\u9fff]', value))


def export_english(inputs, source):
    authored = json.loads((HOME / 'Sources/unit-text-en.json').read_text('utf-8'))
    plan = json.loads((HOME / 'Sources/native-unit-id-map.json').read_text('utf-8'))
    mappings = plan['mappings']
    output, missing, embedded = {}, [], {}
    bindings = []
    for table, key, text_table, prefix, field in text_specs():
        current = {r[key]: r for r in inputs.current(table)}
        english = inputs.text(text_table)
        reference = 'F_ABILITY_MST' if table == 'F_ABILITY_EXPLAIN_MST' else ('F_UNIT_MST' if table == 'F_UNIT_EXPLAIN_MST' else table)
        for row in source['tables'][table]['rows']:
            if not row.get(field):
                continue
            ident = row[key]
            source_key = prefix + ident
            candidate = english.get(source_key) or current.get(ident, {}).get(field, '')
            target = mappings.get(reference, {}).get(ident, ident)
            value = authored.get(text_table, {}).get(source_key)
            if not english_value(value):
                value = candidate if english_value(candidate) else row[field]
            if not english_value(value):
                missing.append({'table': text_table, 'native_key': source_key, 'jp': row[field]})
                continue
            value = value.replace('\u2014', ' - ').replace('\r', '').replace('\n', '<br>')
            if text_table == 'F_TEXT_UNITS_NAME':
                if target != ident and not value.endswith(' JP'):
                    value += ' JP'
                elif target == ident and english_value(candidate) and candidate.endswith(' JP'):
                    value = candidate
            output.setdefault(text_table, {})[prefix + target] = value
            embedded.setdefault(table, {}).setdefault(target, {key: target})[field] = value
            bindings.append({'table': text_table, 'source_key': source_key,
                             'target_key': prefix + target, 'source_master': table, 'field': field})
    text_table = 'F_TEXT_NV_UNIT_CLASS_UP'
    english = inputs.text(text_table)
    for row in source['tables']['F_NV_EX_CLASS_UP_MST']['rows']:
        if not row.get('q4mpoKz2'):
            continue
        ident, level = row['JPW8Vs40'], row['f8vk4JrD']
        source_key = 'MST_NV_CLASS_UP_' + ident + '_' + level
        target = mappings['F_UNIT_MST'].get(ident, ident)
        value = authored.get(text_table, {}).get(source_key) or english.get(source_key)
        if not english_value(value):
            missing.append({'table': text_table, 'native_key': source_key, 'jp': row['q4mpoKz2']})
            continue
        value = value.replace('\u2014', ' - ').replace('\r', '').replace('\n', '<br>')
        output.setdefault(text_table, {})['MST_NV_CLASS_UP_' + target + '_' + level] = value
        embedded.setdefault('F_NV_EX_CLASS_UP_MST', {})[target + '_' + level] = {
            'JPW8Vs40': target, 'f8vk4JrD': level, 'q4mpoKz2': value}
    path = HOME / 'Sources/unit-text-mapped-en.json'
    path.write_bytes(json_bytes(output) + b'\n')
    coverage = {'schema': 1, 'status': 'COMPLETE' if not missing else 'MISSING_TRANSLATIONS',
        'source_sha256': digest(json_bytes(source) + b'\n'), 'mappings': mappings,
        'counts': {t: len(v) for t, v in output.items()}, 'total_bindings': sum(map(len, output.values())),
        'missing': missing, 'bindings': bindings,
        'embedded_master_patches': {t: list(values.values()) for t, values in embedded.items()}}
    (HOME / 'Sources/unit-text-mapped-coverage.json').write_bytes(json_bytes(coverage) + b'\n')
    print(json.dumps({'english': str(path), 'status': coverage['status'], 'counts': coverage['counts'],
                      'missing': missing[:8], 'missing_count': len(missing)}))
    return coverage


def embedded_english_contract(inputs):
    coverage_path = HOME / 'Sources/unit-text-mapped-coverage.json'
    coverage = json.loads(coverage_path.read_text('utf-8'))
    if coverage['status'] != 'COMPLETE' or coverage['missing']:
        raise ValueError('Complete mapped English is required before embedding')
    source = json.loads((HOME / 'Sources/original-unit-content.json').read_text('utf-8'))
    entries = []
    for table, patches in coverage['embedded_master_patches'].items():
        selection = source['tables'][table]
        keys = [selection['key']] if selection['key'] else IDENTITIES[table]
        rows = inputs.current(table)
        existing = {tuple(r[k] for k in keys) for r in rows}
        if any(tuple(r[k] for k in keys) not in existing for r in patches):
            raise ValueError('Gameplay import must exist before English embedding: ' + table)
        for row in patches:
            for field, value in row.items():
                if field not in keys and (not english_value(value) or '\u2014' in value):
                    raise ValueError('Non-English native text patch')
        receipt = inputs.receipts['current:' + table]
        native = receipt['active_native_source']
        filename = (native.get('member') or native.get('path')).rsplit('/', 1)[-1]
        decoded = PROJECT / 'data/mst_decoded' / (table + '.ndjson')
        raw = decoded.read_bytes() if decoded.is_file() else b''
        entries.append({'table': table, 'identity_fields': keys, 'rows': patches,
            'operation': 'merge_fields', 'active_native_path': 'mst/' + filename,
            'active_native_source': native, 'active_native_sha256': native.get('sha256'),
            'decoded_baseline_sha256': digest(raw),
            'expected_decoded_canonical_sha256': digest(json_bytes([json.loads(line) for line in raw.splitlines() if line.strip()]))})
    result = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY',
        'scope': 'English names, bios, quotes and descriptions only. Gameplay fields preserved.',
        'source_file': coverage_path.relative_to(PROJECT).as_posix(),
        'source_sha256': digest(coverage_path.read_bytes()), 'tables': entries}
    path = HOME / 'Sources/native-unit-english-import.json'
    path.write_bytes(json_bytes(result) + b'\n')
    print(json.dumps({'contract': str(path), 'tables': len(entries),
                      'rows': sum(len(t['rows']) for t in entries)}))
    return result


def icon_contract(inputs, bindings_only=False):
    source = json.loads((HOME / 'Sources/original-unit-content.json').read_text('utf-8'))
    mappings = json.loads((HOME / 'Sources/native-unit-id-map.json').read_text('utf-8'))['mappings']
    original = {r['0HUPxDf1']: r for r in inputs.original('F_ICON_MST')}
    current = {r['0HUPxDf1']: r for r in inputs.current('F_ICON_MST')}
    tables = ('F_ABILITY_MST', 'F_MAGIC_MST', 'F_EQUIP_ITEM_MST', 'F_MATERIA_MST', 'F_ITEM_MST')
    references = {}
    for table in tables:
        key = source['tables'][table]['key']
        for row in source['tables'][table]['rows']:
            icon = row.get('0HUPxDf1')
            if icon not in (None, '', '0'):
                references.setdefault(icon, []).append({'table': table, 'identity_field': key,
                    'source_id': row[key], 'target_id': mappings[table].get(row[key], row[key])})
    missing = sorted(references.keys() - original.keys(), key=int)
    if missing:
        raise ValueError('Original JP icon bindings absent: ' + str(missing))
    occupied = current.keys() | original.keys()
    icon_map, icon_rows, patches, assets = {}, [], {}, []
    for source_id in sorted(references, key=int):
        row = dict(original[source_id])
        filename = row['qtkvrS60']
        # Only typed native unit graphic basenames use the unit fork map.
        match = re.fullmatch(r'(unit_(?:icon|ills|anime)_)([0-9]+)(\.png|\.cgg|_[A-Za-z0-9_]+\.cgs)', filename)
        target_filename = filename
        if match and match[2] in mappings['F_UNIT_MST']:
            target_filename = match[1] + mappings['F_UNIT_MST'][match[2]] + match[3]
        old = current.get(source_id)
        target_id = source_id
        if old is not None and old['qtkvrS60'] != target_filename:
            target_id = str(880000000 + len(icon_map) + 1)
            if target_id in occupied:
                raise ValueError('Icon namespace is occupied: ' + target_id)
            icon_map[source_id] = target_id
        row['0HUPxDf1'] = target_id
        row['qtkvrS60'] = target_filename
        if old is None or target_id != source_id:
            icon_rows.append(row)
        for ref in references[source_id]:
            if target_id != source_id:
                patches.setdefault(ref['table'], []).append({ref['identity_field']: ref['target_id'], '0HUPxDf1': target_id})
        assets.append({'source_icon_id': source_id, 'target_icon_id': target_id,
            'source_filename': filename, 'target_filename': target_filename,
            'current_filename': old['qtkvrS60'] if old else None,
            'status': 'shared_binding' if old and target_id == source_id else 'original_JP_binding_required',
            'references': references[source_id]})
    binding_path = HOME / 'Sources/original-jp-icon-bindings.json'
    binding_path.write_bytes(json_bytes({'source': inputs.receipts['F_ICON_MST'],
        'bindings': assets, 'icon_mapping': icon_map}) + b'\n')
    if bindings_only:
        print(json.dumps({'binding_map': str(binding_path), 'bindings': len(assets),
                          'references': sum(map(len, references.values())), 'icon_forks': len(icon_map)}))
        return
    updates = {'F_ICON_MST': (['0HUPxDf1'], icon_rows, 'replace')}
    updates.update({table: ([source['tables'][table]['key']], rows, 'merge_fields')
                    for table, rows in patches.items()})
    entries = []
    for table, (keys, rows, operation) in updates.items():
        if not rows:
            continue
        inputs.current(table)
        receipt = inputs.receipts['current:' + table]
        native = receipt['active_native_source']
        filename = (native.get('member') or native.get('path')).rsplit('/', 1)[-1]
        authoring = PROJECT / 'data/mst_decoded' / (table + '.ndjson')
        raw = authoring.read_bytes() if authoring.is_file() else b''
        entries.append({'table': table, 'identity_fields': keys, 'rows': rows, 'operation': operation,
            'active_native_path': 'mst/' + filename, 'active_native_source': native,
            'active_native_sha256': native.get('sha256'), 'decoded_baseline_sha256': digest(raw)})
    result = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY' if entries else 'VERIFIED_NO_NATIVE_CHANGES', 'tables': entries,
        'icon_mapping': icon_map, 'binding_source': inputs.receipts['F_ICON_MST'],
        'binding_count': len(assets), 'binding_reference_count': sum(map(len, references.values())),
        'asset_verification': 'Parent must verify original JP payloads separately from these exact native filename bindings.'}
    path = HOME / 'Sources/native-unit-icon-import.json'
    path.write_bytes(json_bytes(result) + b'\n')
    (HOME / 'Sources/original-jp-icon-bindings.json').write_bytes(json_bytes({'source': result['binding_source'],
        'bindings': assets, 'icon_mapping': icon_map}) + b'\n')
    print(json.dumps({'contract': str(path), 'bindings': len(assets), 'references': result['binding_reference_count'],
        'icon_forks': len(icon_map), 'table_rows': {t['table']: len(t['rows']) for t in entries}}))
    return result


def comparable(row, identity=None, unit=False):
    ignored = {'G4L0YIB2', '6uvHX2JG', 'Z0EN6jSh', 'QLfe23bu', 'cnLF6Cz1', 'A86KwrGh'}
    if unit:
        ignored.add('A86KwrGh')
    result = {k: v for k, v in row.items() if k not in ignored and v not in ('', '0', None)}
    # Native source uses an explicit self display-group where Global leaves
    # the default empty. This alone is not a distinct skill implementation.
    if identity and result.get('6ZEyK95f') == row.get(identity):
        result.pop('6ZEyK95f')
    return result


def different(left, right, identity=None, unit=False):
    """Compare fields implemented by both native client schemas."""
    fields = left.keys() & right.keys()
    a = comparable({k: v for k, v in left.items() if k in fields}, identity, unit)
    b = comparable({k: v for k, v in right.items() if k in fields}, identity, unit)
    return a != b


# Native child-ability operand positions, observed in the selected original
# records and cross-checked against their community decoded effect clauses.
# These are operand positions, not a numeric search-and-replace across stats.
SKILL_OPERANDS = {'103': (0,), '52': (2,), '98': (1, 3), '49': (2,),
    '50': (2,), '100': (1,), '66': (0,), '73': (0,), '130': (0,),
    '53': (1, 3), '56': (0,), '136': (0,), '102': (1, 2, 4), '157': (0,), '97': (2,),
    '35': (0,), '165': (0,), '168': (1, 4)}
LB_OPERANDS = {'72': (0,), '171': (0,)}


def substitute(value, mapping):
    return re.sub(r'(?<![0-9])[0-9]+(?![0-9])',
                  lambda hit: mapping.get(hit.group(), hit.group()), value)


def rewrite_rewards(value, mappings):
    domains = {'10': 'F_UNIT_MST', '20': 'F_ITEM_MST', '21': 'F_EQUIP_ITEM_MST',
               '22': 'F_MATERIA_MST', '27': 'F_VISION_CARD_MST'}
    clauses = []
    unit_map = mappings.get('F_UNIT_MST', {})
    for clause in value.split(','):
        fields = clause.split(':')
        if len(fields) >= 3:
            fields[1] = mappings.get(domains.get(fields[0]), {}).get(fields[1], fields[1])
            if fields[0] == '10' and len(fields) >= 9:
                bound = fields[8]
                for source, target in unit_map.items():
                    if bound == str(1000000000 + int(source)):
                        fields[8] = str(1000000000 + int(target))
                        break
        clauses.append(':'.join(fields))
    return ','.join(clauses)


def effect_parameters(row, skill_map, lb_map, opcodes=None):
    commands = (opcodes if opcodes is not None else row.get('2kq0BpnD', '')).split('@')
    parameters = row.get('Ha9G5sCS', '').split('@')
    if len(commands) != len(parameters):
        raise ValueError('Native effect/parameter cardinality differs')
    output = []
    unresolved = []
    for opcode, params in zip(commands, parameters):
        fields = params.split(',')
        if opcode == '29':
            # Each random-cast operand is skillID&chance.
            for index, field in enumerate(fields):
                parts = field.split('&')
                if parts:
                    parts[0] = skill_map.get(parts[0], parts[0])
                fields[index] = '&'.join(parts)
        elif opcode == '99':
            for index in range(1, len(fields), 2):
                fields[index] = substitute(fields[index], skill_map)
        elif opcode == '100':
            # Passive normal-attack replacement has four operands and its
            # child at0; active autocast has five and its child list at1.
            index = 0 if len(fields) == 4 else 1
            fields[index] = substitute(fields[index], skill_map)
        else:
            for index in SKILL_OPERANDS.get(opcode, ()):
                if index < len(fields):
                    fields[index] = substitute(fields[index], skill_map)
        for index in LB_OPERANDS.get(opcode, ()):
            if index < len(fields):
                fields[index] = substitute(fields[index], lb_map)
        rewritten = ','.join(fields)
        # Any remaining collision could be an ordinary numeric effect value.
        # Retain it and expose it for investigation rather than changing it.
        # Native40 is hybrid damage. Its ATK/MAG coefficients can happen
        # to equal a magic ID, for example10400, without referring to it.
        remaining = set() if opcode=='40' else numbers(rewritten) & (skill_map.keys() | lb_map.keys())
        if remaining:
            unresolved.append({'opcode': opcode, 'params': params, 'ids': sorted(remaining)})
        output.append(rewritten)
    return '@'.join(output), unresolved


def rewrite_effect_frames(value, group_map, legacy=False):
    phases=[value]if legacy else value.split('@')
    result=[]
    for phase in phases:
        frames=[]
        for clause in phase.split('&'):
            parts=clause.split(':')
            if len(parts)>=2:parts[1]=group_map.get(parts[1],parts[1])
            frames.append(':'.join(parts))
        result.append('&'.join(frames))
    return '@'.join(result)


def rewrite_row(table, row, mappings, selected, file_aliases=None, legacy_effect_frames=False):
    result = dict(row)
    unit_map = mappings.get('F_UNIT_MST', {})
    skill_map = dict(mappings['F_ABILITY_MST'], **mappings['F_MAGIC_MST'])
    lb_map = mappings['F_LIMITBURST_MST']
    group_map = mappings['F_EFFECT_GROUP_MST']
    identity = selected[table]['key']
    own_map = mappings.get(table, {})
    if identity:
        result[identity] = own_map.get(row[identity], row[identity])
    unresolved = []
    if table in ('F_ABILITY_MST', 'F_MAGIC_MST', 'F_LIMITBURST_MST'):
        result['Ha9G5sCS'], unresolved = effect_parameters(row, skill_map, lb_map)
        result['5A8SmwyC'] = rewrite_effect_frames(row.get('5A8SmwyC',''),group_map,legacy_effect_frames)
        if row.get('6ZEyK95f') in own_map:
            result['6ZEyK95f'] = own_map[row['6ZEyK95f']]
    elif table == 'F_LIMITBURST_LV_MST':
        ident = row['PR2HIc71']
        result['PR2HIc71'] = lb_map.get(ident, ident)
        parent = next(r for r in selected['F_LIMITBURST_MST']['rows'] if r['PR2HIc71'] == ident)
        result['Ha9G5sCS'], unresolved = effect_parameters(row, skill_map, lb_map, parent['2kq0BpnD'])
    elif table == 'F_UNIT_MST':
        for field in ('3HriTp6B', 'woghJa61', 'JPW8Vs40'):
            result[field] = unit_map.get(row[field], row[field])
        result['PR2HIc71'] = lb_map.get(row['PR2HIc71'], row['PR2HIc71'])
        for field in ('9mu4boy7', 'C74EmZ1I'):
            result[field] = rewrite_rewards(row.get(field, ''), mappings)
        result['Ew8e6BAc'] = mappings.get('F_ITEM_MST', {}).get(row['Ew8e6BAc'], row['Ew8e6BAc'])
        result['5A8SmwyC'] = rewrite_effect_frames(row.get('5A8SmwyC',''),group_map,legacy_effect_frames)
    elif table == 'F_UNIT_SERIES_LV_ACQUIRE_MST':
        result['woghJa61'] = unit_map.get(row['woghJa61'], row['woghJa61'])
        for field in ('i6kc1jN0', '1Zsh27mS', 'eAM5B1qt'):
            result[field] = substitute(row[field], skill_map)
    elif table == 'F_EFFECT_GROUP_MST':
        clauses = []
        for clause in row.get('5A8SmwyC', '').split(','):
            parts = clause.split(':')
            if len(parts) == 8:
                parts[1] = mappings['F_EFFECT_MST'].get(parts[1], parts[1])
            clauses.append(':'.join(parts))
        result['5A8SmwyC'] = ','.join(clauses)
    elif table == 'F_EFFECT_MST':
        filename = row.get('2HjxCGo6')
        if filename in (file_aliases or {}):
            result['2HjxCGo6'] = file_aliases[filename]
    elif table == 'F_UNIT_EXPLAIN_MST':
        result['3HriTp6B'] = unit_map.get(row['3HriTp6B'], row['3HriTp6B'])
    elif table == 'F_ABILITY_EXPLAIN_MST':
        result['Ga5V42LZ'] = skill_map.get(row['Ga5V42LZ'], row['Ga5V42LZ'])
    elif table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST'):
        for field in ('GiBvPK84', 't42Xb3jV', '5Sx0haBw', '82PrpZU6'):
            if field in row:
                result[field] = substitute(row[field], skill_map)
    elif table == 'F_NV_EX_CLASS_UP_MST':
        result['JPW8Vs40'] = unit_map.get(row['JPW8Vs40'], row['JPW8Vs40'])
        for field in ('KCk8u0am', 'dX6cor8j'):
            result[field] = rewrite_rewards(row[field], mappings)
    elif table.startswith('F_VISION_CARD_') and table != 'F_VISION_CARD_EXP_PATTERN_MST':
        if '5giCMUd2' in row:
            result['5giCMUd2'] = mappings.get('F_VISION_CARD_MST', {}).get(row['5giCMUd2'], row['5giCMUd2'])
        if table == 'F_VISION_CARD_MST' and row.get('efb6J8AZ') == row.get('5giCMUd2'):
            result['efb6J8AZ'] = result['5giCMUd2']
        for field in ('i6kc1jN0', '1Zsh27mS', 'a4hXTIm0'):
            if field in row:
                result[field] = substitute(row[field], skill_map)
    elif table == 'F_LEADER_SKILL_MST':
        result['Ga5V42LZ'] = skill_map.get(row['Ga5V42LZ'], row['Ga5V42LZ'])
    elif table.startswith('F_UNIT_') and table not in ('F_UNIT_GROW_MST', 'F_UNIT_EXP_PATTERN_MST', 'F_UNIT_ROLE_MST', 'F_UNIT_SUB_CATEGORY_MST', 'F_UNIT_CHARACTER_MST'):
        for field, value in row.items():
            result[field] = substitute(value, unit_map)
    return result, unresolved


IDENTITIES = {
    'F_UNIT_SERIES_LV_ACQUIRE_MST': ['woghJa61', '2EusAP6T', '7wV3QZ80'],
    'F_LIMITBURST_LV_MST': ['PR2HIc71', '7wV3QZ80'],
    'F_UNIT_CLASS_UP_MST': ['3HriTp6B'],
    'F_NV_EX_CLASS_UP_MST': ['JPW8Vs40', 'f8vk4JrD'],
    'F_UNIT_GROW_MST': ['aU3o2D4t', 'uk6Wh8mw', '7wV3QZ80'],
    'F_UNIT_EXP_PATTERN_MST': ['0W7g6YXS', '7wV3QZ80'],
    'F_VISION_CARD_EXP_PATTERN_MST': ['0W7g6YXS', '7wV3QZ80'],
    'F_VISION_CARD_LV_ACQUIRE_MST': ['5giCMUd2', '7wV3QZ80'],
    'F_VISION_CARD_ABILITY_ACT_COND_MST': ['5giCMUd2', '9qQg2zjH'],
    'F_LEADER_SKILL_MST': ['Uv6Rj1b0', 'SVT5aU9n'],
    'F_UNIT_EX_BONUS_MST': ['L3Nx1Jpb'],
    'F_UNIT_SERIES_NV_PIECE_MST': ['woghJa61'],
    'F_UNIT_SERIES_POWER_UP_POINT_MST': ['RvN2W9Qx'],
    'F_UNIT_EXPLAIN_MST': ['3HriTp6B'],
}


def emit_contract(inputs, source, plan):
    tables = []
    unresolved = []
    for table, selection in source['tables'].items():
        if not selection['rows']:
            continue
        keys = [selection['key']] if selection['key'] else IDENTITIES.get(table)
        if not keys:
            raise ValueError('No proven native identity fields for ' + table)
        original_current = inputs.current(table)
        grouped = table == 'F_UNIT_SERIES_LV_ACQUIRE_MST'
        current = {tuple(r[k] for k in keys): r for r in original_current}
        rewritten = []
        seen = set()
        for row in selection['rows']:
            result, pending = rewrite_row(table, row, plan['mappings'], source['tables'], plan.get('vfx_file_aliases'))
            unresolved.extend(dict(p, table=table, source_identity={k: row[k] for k in keys}) for p in pending)
            identity = tuple(result[k] for k in keys)
            if identity in seen and not grouped:
                raise ValueError('Duplicate logical source identity in ' + table + ': ' + str(identity))
            seen.add(identity)
            old = current.get(identity)
            if table=='F_ITEM_MST' and row[selection['key']]in plan.get('shared_common_item_ids',[]):
                # These exact common wallets were separately verified. Keep
                # the client's existing stack cap and translated metadata.
                left={k:v for k,v in result.items()if k!='9J6uRe8f'}
                right={k:v for k,v in (old or {}).items()if k!='9J6uRe8f'}
                if old is None or different(left,right,selection['key']):
                    raise ValueError('Verified shared common item changed: '+str(identity))
                continue
            # Identical shared records stay byte-for-byte in the live dataset.
            if grouped or old is None or different(result, old, selection['key'], table == 'F_UNIT_MST'):
                rewritten.append(result)
        if not rewritten:
            continue
        receipt = inputs.receipts['current:' + table]
        native = receipt['active_native_source']
        if native is None:
            raise ValueError('No existing native version path for ' + table)
        filename = (native.get('member') or native.get('path')).rsplit('/', 1)[-1]
        tables.append({'table': table, 'identity_fields': keys,
            'active_native_path': 'mst/' + filename, 'active_native_source': native,
            'active_native_sha256': native.get('sha256'),
            'expected_native_decoded_canonical_sha256': receipt['decoded_canonical_sha256'],
            'operation': 'replace_groups' if grouped else 'replace', 'replace_existing': True,
            'preserve_unselected_rows': True, 'rows': rewritten})
        authoring = PROJECT / 'data/mst_decoded' / (table + '.ndjson')
        authoring_bytes = authoring.read_bytes() if authoring.is_file() else b''
        authoring_rows = [json.loads(line) for line in authoring_bytes.splitlines() if line.strip()]
        tables[-1]['decoded_baseline_sha256'] = digest(authoring_bytes)
        tables[-1]['expected_decoded_canonical_sha256'] = digest(json_bytes(authoring_rows))
    report = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY' if not unresolved else 'BLOCKED_UNRESOLVED_TYPED_REFERENCES',
        'source_file': 'Japan content/Earlier JP crossovers/Sources/original-unit-content.json',
        'source_sha256': digest(json_bytes(source) + b'\n'),
        'mappings': plan['mappings'], 'tables': tables, 'unresolved_references': unresolved,
        'counts': {t['table']: len(t['rows']) for t in tables},
        'scope': '145 earlier crossover forms plus two existing JP Reberta forms',
        'preservation': 'Existing distinct Global Duran/Angela versions and unselected native records preserved.'}
    missing = source['missing']
    if missing.get('skills') or missing.get('effect_groups') or missing.get('effects') or any(missing.get('reward_master_ids', {}).values()):
        report['status'] = 'BLOCKED_MISSING_ORIGINAL_DEPENDENCIES'
    path = HOME / 'Sources/native-unit-import.json'
    path.write_bytes(json_bytes(report) + b'\n')
    plan['status'] = report['status']
    plan['import_contract'] = path.relative_to(PROJECT).as_posix()
    (HOME / 'Sources/native-unit-id-map.json').write_bytes(json_bytes(plan) + b'\n')
    print(json.dumps({'contract': str(path), 'status': report['status'], 'counts': report['counts'],
                      'unresolved_references': unresolved[:8], 'unresolved_count': len(unresolved)}))
    return report


def prepare_import(inputs, source):
    """Append-only fork material. Preserve every effective Global source row."""
    selected = source['tables']
    prior_path = HOME / 'Sources/native-unit-id-map.json'
    if prior_path.is_file():
        prior = json.loads(prior_path.read_text('utf-8'))
        if prior.get('artwork_mapping_ready') and prior.get('source_sha256') == digest(json_bytes(source) + b'\n'):
            for table, mapping in prior.get('mappings', {}).items():
                if table not in selected:continue
                key = selected[table]['key']
                current = {r[key]: r for r in inputs.current(table)}
                originals = {r[key]: r for r in selected[table]['rows']}
                for original, target in mapping.items():
                    if original not in originals:continue
                    if target in current:
                        expected, pending = rewrite_row(table, originals[original], prior['mappings'], selected, prior.get('vfx_file_aliases'))
                        if pending or different(expected, current[target], key, table == 'F_UNIT_MST'):
                            raise ValueError('Owned reserved import target changed: ' + table + ':' + target)
            emit_contract(inputs, source, prior)
            print('Reused validated owned import reservations without allocating new identities.')
            return prior
    scopes = json.loads((HOME / 'unit-banner-visual-count-evidence.json').read_text('utf-8'))['unit_versions']
    families = [(v['canonical_unit_version_id'], set(v['native_form_ids'])) for v in scopes]
    families.append(('100014405', {'100014405', '100014406'}))
    originals = {r['3HriTp6B']: r for r in selected['F_UNIT_MST']['rows']}
    current_units = {r['3HriTp6B']: r for r in inputs.current('F_UNIT_MST')}
    occupied = set()
    for table, selection in selected.items():
        key = selection['key']
        if key:
            occupied.update(r[key] for r in inputs.current(table) if key in r)
            occupied.update(r[key] for r in inputs.original(table, required=False) if key in r)
            authoring = PROJECT / 'data/mst_decoded' / (table + '.ndjson')
            if authoring.is_file():
                occupied.update(r[key] for r in (json.loads(line) for line in authoring.read_bytes().splitlines()
                    if line.strip()) if key in r)
    for row in community()['units'].values():
        occupied.update(row.get('entries', {}))
    reserved = PROJECT / 'Japan content/Banners/new-unit-id-plan.csv'
    if reserved.is_file():
        with reserved.open(encoding='utf-8-sig', newline='') as handle:
            occupied.update(value for row in csv.DictReader(handle) for value in row.values()
                            if value and value.isdecimal())
    mappings = {}
    domains = [('F_ABILITY_MST', 830000000), ('F_MAGIC_MST', 835000000),
               ('F_LIMITBURST_MST', 840000000), ('F_EFFECT_GROUP_MST', 850000000),
               ('F_EFFECT_MST', 860000000), ('F_EQUIP_ITEM_MST', 870000000),
               ('F_MATERIA_MST', 871000000), ('F_ITEM_MST', 872000000),
               ('F_VISION_CARD_MST', 873000000)]
    for table, start in domains:
        key = selected[table]['key']
        current = {r[key]: r for r in inputs.current(table)}
        changes = []
        for row in selected[table]['rows']:
            old = current.get(row[key])
            if old is not None and different(row, old, key):
                changes.append(row[key])
        mapping = {}
        for index, ident in enumerate(sorted(changes, key=int), 1):
            target = str(start + index)
            if target in occupied:
                raise ValueError('Reserved native identity is occupied: ' + target)
            occupied.add(target)
            mapping[ident] = target
        mappings[table] = mapping
    mappings['F_UNIT_MST'] = {}
    # Effect group and parent-skill forks must propagate. A shared Global
    # parent cannot be edited merely to reference a separately imported child.
    effect_mapping = mappings['F_EFFECT_MST']
    group_mapping = mappings['F_EFFECT_GROUP_MST']
    for row in selected['F_EFFECT_GROUP_MST']['rows']:
        if numbers(row.get('5A8SmwyC', '')) & effect_mapping.keys() and row['qIy86WvJ'] not in group_mapping:
            target = str(850000000 + len(group_mapping) + 1)
            if target in occupied:
                raise ValueError('Effect group identity occupied')
            occupied.add(target)
            group_mapping[row['qIy86WvJ']] = target
    # Propagate typed child references until no shared parent would be edited.
    while True:
        added = 0
        for table, start in domains:
            key = selected[table]['key']
            current = {r[key]: r for r in inputs.current(table)}
            for row in selected[table]['rows']:
                if row[key] in mappings[table] or row[key] not in current:
                    continue
                rewritten, _ = rewrite_row(table, row, mappings, selected)
                if different(rewritten, row, key):
                    target = str(start + len(mappings[table]) + 1)
                    if target in occupied:
                        raise ValueError('Propagated identity occupied: ' + target)
                    occupied.add(target)
                    mappings[table][row[key]] = target
                    added += 1
        if not added:
            break
    skill_mapping = dict(mappings['F_ABILITY_MST'], **mappings['F_MAGIC_MST'])
    for table in ('F_ABILITY_MST', 'F_MAGIC_MST', 'F_LIMITBURST_MST'):
        key = selected[table]['key']
        mapping = mappings[table]
        for row in selected[table]['rows']:
            if numbers(row.get('5A8SmwyC', '')) & group_mapping.keys() and row[key] not in mapping:
                base = dict(domains)[table]
                target = str(base + len(mapping) + 1)
                if target in occupied:
                    raise ValueError('Parent native identity occupied')
                occupied.add(target)
                mapping[row[key]] = target
    skill_mapping = dict(mappings['F_ABILITY_MST'], **mappings['F_MAGIC_MST'])
    current_acquire = inputs.current('F_UNIT_SERIES_LV_ACQUIRE_MST')
    source_acquire = selected['F_UNIT_SERIES_LV_ACQUIRE_MST']['rows']
    unit_mapping = {}
    decisions = []
    for index, (canonical, forms) in enumerate(families, 1):
        roots = {originals[f]['woghJa61'] for f in forms}
        reasons = []
        for ident in sorted(forms):
            if ident in current_units and different(originals[ident], current_units[ident], unit=True):
                reasons.append('native_unit_gameplay:' + ident)
            if originals[ident].get('PR2HIc71') in mappings['F_LIMITBURST_MST']:
                reasons.append('distinct_JP_limit_burst:' + ident)
        src = [r for r in source_acquire if r['woghJa61'] in roots]
        old = [r for r in current_acquire if r['woghJa61'] in roots]
        if {json_bytes(comparable(r)) for r in src} != {json_bytes(comparable(r)) for r in old}:
            reasons.append('distinct_JP_acquisition')
        if any(set().union(*(numbers(v) for v in r.values())) & skill_mapping.keys() for r in src):
            reasons.append('distinct_JP_acquired_ability')
        # Material balance changes do not establish a different character
        # version. The confirmed regional-version collisions change the
        # native family root: Global's new NV Duran/Angela overlap JP's NVA
        # forms of the older five-star families. Existing separate JP forms,
        # including Reberta, retain save ownership and their existing IDs.
        root_conflicts = [ident for ident in forms & current_units.keys()
            if originals[ident]['woghJa61'] != current_units[ident]['woghJa61']]
        fork = bool(root_conflicts)
        if fork:
            reasons.append('confirmed_native_family_root_collision:' + ','.join(sorted(root_conflicts)))
        if fork:
            for ident in sorted(forms):
                target = str(820000000 + index * 1000 + int(ident) % 1000)
                if target in occupied:
                    raise ValueError('Unit fork identity is occupied: ' + target)
                occupied.add(target)
                unit_mapping[ident] = target
        decisions.append({'canonical_source_id': canonical, 'form_ids': sorted(forms),
            'fork': fork, 'reasons': sorted(set(reasons))})
    mappings['F_UNIT_MST'] = unit_mapping
    result = {'schema': 1, 'status': 'SOURCE_RECOVERED_REFERENCE_REWRITE_PENDING',
              'mappings': mappings, 'family_decisions': decisions,
              'preserve_global': True, 'source_sha256': digest(json_bytes(source) + b'\n'),
              'identity_policy': 'Fork only confirmed distinct family-root versions. Existing JP identities retain IDs.'}
    result['artwork_mapping_ready'] = True
    path = HOME / 'Sources/native-unit-id-map.json'
    path.write_bytes(json_bytes(result) + b'\n')
    print(json.dumps({'mapping_output': str(path), 'domain_counts': {k: len(v) for k, v in mappings.items()}}))
    emit_contract(inputs, source, result)
    return result


def recover(inputs):
    scope = json.loads((HOME / 'unit-banner-visual-count-evidence.json').read_text('utf-8'))
    versions = scope['unit_versions']
    form_ids = {f for v in versions for f in v['native_form_ids']} | {'100014405', '100014406'}
    documents = community()
    units = [r for r in inputs.original('F_UNIT_MST') if r['3HriTp6B'] in form_ids]
    if {r['3HriTp6B'] for r in units} != form_ids:
        raise ValueError('Original native unit source is incomplete')
    roots = {r['woghJa61'] for r in units}
    acquired = [r for r in inputs.original('F_UNIT_SERIES_LV_ACQUIRE_MST')
                if r['woghJa61'] in roots]
    ex_keys = {r['JPW8Vs40'] for r in units} - {'0', ''}
    ex_rows = [r for r in inputs.original('F_NV_EX_CLASS_UP_MST') if r['JPW8Vs40'] in ex_keys]
    shift_keys = {r['rZhG3M4b'] for r in units} - {'0', ''}
    shift_rows = [r for r in inputs.original('F_NV_SHIFT_MST') if r['rZhG3M4b'] in shift_keys]
    rewards = {'EQUIP': set(), 'MATERIA': set(), 'ITEM': set(), 'VISIONCARD': set(), 'UNIT': set()}
    scoped_community_units = [u for u in documents['units'].values() if form_ids.intersection(u.get('entries', {}))]
    for unit in scoped_community_units:
        for field in ('TMR', 'sTMR'):
            reward = unit.get(field)
            if reward:
                rewards[reward[0]].add(str(reward[1]))
        for entry in unit.get('entries', {}).values():
            upgrades = ([entry['awakening']] if entry.get('awakening') else []) + (entry.get('nv_upgrade') or [])
            for upgrade in upgrades:
                rewards['ITEM'].update(str(i) for i in (upgrade.get('materials') or {}))
                for reward in upgrade.get('reward') or []:
                    if reward[0] in rewards:
                        rewards[reward[0]].add(str(reward[1]))
    for row in units:
        if row.get('Ew8e6BAc') not in (None, '', '0'):
            rewards['ITEM'].add(row['Ew8e6BAc'])
    for row in ex_rows:
        for field in ('KCk8u0am', 'dX6cor8j'):
            for clause in row.get(field, '').split(','):
                fields = clause.split(':')
                if len(fields) >= 3:
                    kind = {'10': 'UNIT', '20': 'ITEM', '21': 'EQUIP', '22': 'MATERIA', '27': 'VISIONCARD'}.get(fields[0])
                    if kind:
                        rewards[kind].add(fields[1])
    reward_selected = {}
    for kind, table, key in [('EQUIP', 'F_EQUIP_ITEM_MST', 'J1YX9kmM'),
                             ('MATERIA', 'F_MATERIA_MST', 'H5jBL0Vf'),
                             ('ITEM', 'F_ITEM_MST', 'tL6G9egd'),
                             ('VISIONCARD', 'F_VISION_CARD_MST', '5giCMUd2')]:
        available = {r[key]: r for r in inputs.original(table)}
        reward_selected[table] = {'key': key, 'rows': [available[i] for i in sorted(rewards[kind] & available.keys(), key=int)]}
    vc_acquired = [r for r in inputs.original('F_VISION_CARD_LV_ACQUIRE_MST') if r['5giCMUd2'] in rewards['VISIONCARD']]
    reward_selected['F_VISION_CARD_LV_ACQUIRE_MST'] = {'key': None, 'rows': vc_acquired}
    vc_conditions = [r for r in inputs.original('F_VISION_CARD_ABILITY_ACT_COND_MST') if r['5giCMUd2'] in rewards['VISIONCARD']]
    reward_selected['F_VISION_CARD_ABILITY_ACT_COND_MST'] = {'key': None, 'rows': vc_conditions}
    vc_group_ids = {r['4JZgSr3A'] for r in vc_acquired} - {'0', ''}
    reward_selected['F_VISION_CARD_ABILITY_GROUP_MST'] = {'key': '4JZgSr3A', 'rows': [r for r in
        inputs.original('F_VISION_CARD_ABILITY_GROUP_MST') if r['4JZgSr3A'] in vc_group_ids]}
    leader_ids = {r['Uv6Rj1b0'] for r in units} - {'0', ''}
    leaders = [r for r in inputs.original('F_LEADER_SKILL_MST') if r['Uv6Rj1b0'] in leader_ids]
    skills = {}
    for name in ('skills_ability', 'skills_passive', 'skills_magic'):
        skills.update(documents[name])
    skill_ids = set()
    skill_ids.update(r['Ga5V42LZ'] for r in leaders)
    for table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST'):
        for record in reward_selected[table]['rows']:
            for field in ('GiBvPK84', 't42Xb3jV', '5Sx0haBw', '82PrpZU6'):
                skill_ids.update(numbers(record.get(field, '')) & skills.keys())
    for record in vc_acquired:
        for field in ('i6kc1jN0', '1Zsh27mS'):
            skill_ids.update(numbers(record.get(field, '')) & skills.keys())
    for record in vc_conditions:
        skill_ids.update(numbers(record.get('a4hXTIm0', '')) & skills.keys())
    for record in acquired:
        for field in ('i6kc1jN0', '1Zsh27mS', 'eAM5B1qt'):
            skill_ids.update(numbers(record.get(field, '')) & skills.keys())
    for unit in documents['units'].values():
        if form_ids.intersection(unit.get('entries', {})):
            skill_ids.update(str(s['id']) for s in unit.get('skills', []))
    abilities = {r['Ga5V42LZ']: r for r in inputs.original('F_ABILITY_MST')}
    magic = {r['QV1HE7Wq']: r for r in inputs.original('F_MAGIC_MST')}
    # Include every ability-like numeric dependency mentioned by native source
    # parameters or community decoded effects. This over-includes occasional
    # numeric coincidences; it never changes or interprets the source opcodes.
    available_skills = abilities.keys() | magic.keys()
    queue = list(skill_ids)
    while queue:
        sid = queue.pop()
        native = abilities.get(sid, magic.get(sid, {}))
        child = numbers(native.get('Ha9G5sCS', '')) & available_skills
        for text in skills.get(sid, {}).get('effects', []):
            child.update(re.findall(r'\(([0-9]+)\)', str(text)))
        child &= available_skills
        for ident in child - skill_ids:
            skill_ids.add(ident)
            queue.append(ident)
    missing = sorted(skill_ids - abilities.keys() - magic.keys(), key=int)
    lb_ids = {r['PR2HIc71'] for r in units if r.get('PR2HIc71') not in ('', '0')}
    all_lbs = {r['PR2HIc71']: r for r in inputs.original('F_LIMITBURST_MST')}
    for sid in skill_ids:
        native = abilities.get(sid, magic.get(sid, {}))
        for opcode, params in zip(native.get('2kq0BpnD', '').split('@'),
                                  native.get('Ha9G5sCS', '').split('@')):
            if opcode == '72':
                lb_ids.update(numbers(params) & all_lbs.keys())
    selected = {
        'F_UNIT_MST': {'key': '3HriTp6B', 'rows': units},
        'F_UNIT_SERIES_LV_ACQUIRE_MST': {'key': None, 'rows': acquired},
        'F_ABILITY_MST': {'key': 'Ga5V42LZ', 'rows': [abilities[s] for s in sorted(skill_ids & abilities.keys(), key=int)]},
        'F_MAGIC_MST': {'key': 'QV1HE7Wq', 'rows': [magic[s] for s in sorted(skill_ids & magic.keys(), key=int)]},
        'F_LIMITBURST_MST': {'key': 'PR2HIc71', 'rows': [r for r in all_lbs.values() if r['PR2HIc71'] in lb_ids]},
        'F_LIMITBURST_LV_MST': {'key': None, 'rows': [r for r in inputs.original('F_LIMITBURST_LV_MST') if r['PR2HIc71'] in lb_ids]},
    }
    selected.update(reward_selected)
    selected['F_LEADER_SKILL_MST'] = {'key': None, 'rows': leaders}
    selected['F_NV_EX_CLASS_UP_MST'] = {'key': None, 'rows': ex_rows}
    selected['F_NV_SHIFT_MST'] = {'key': 'rZhG3M4b', 'rows': shift_rows}
    # Source effect groups are precisely referenced by the native animation
    # clauses. Keep their native opcodes and complete parameter strings intact.
    group_ids = set()
    for change in selected.values():
        for row in change['rows']:
            for clause in row.get('5A8SmwyC', '').split('&'):
                fields = clause.split(':')
                if len(fields) >= 2:
                    group_ids.add(fields[1])
    groups = {r['qIy86WvJ']: r for r in inputs.original('F_EFFECT_GROUP_MST')}
    absent_groups = sorted(group_ids - groups.keys())
    selected['F_EFFECT_GROUP_MST'] = {'key': 'qIy86WvJ', 'rows': [groups[g] for g in sorted(group_ids & groups.keys(), key=int)]}
    effect_ids = set()
    for row in selected['F_EFFECT_GROUP_MST']['rows']:
        for clause in row['5A8SmwyC'].split(','):
            fields = clause.split(':')
            if clause and len(fields) == 8:
                effect_ids.add(fields[1])
    effects = {r['h5t4yBm2']: r for r in inputs.original('F_EFFECT_MST')}
    absent_effects = sorted(effect_ids - effects.keys())
    selected['F_EFFECT_MST'] = {'key': 'h5t4yBm2', 'rows': [effects[e] for e in sorted(effect_ids & effects.keys(), key=int)]}
    # Exact original unit-related records. Their schemas contain source unit
    # family references, so scope by exact form/root numeric token membership.
    for table in ('F_UNIT_CLASS_UP_MST', 'F_UNIT_EX_BONUS_MST',
                  'F_UNIT_SERIES_NV_PIECE_MST', 'F_UNIT_SERIES_HIDDEN_SKILL_MST',
                  'F_UNIT_SERIES_POWER_UP_POINT_MST', 'F_UNIT_SUB_CATEGORY_MST',
                  'F_UNIT_ROLE_MST', 'F_UNIT_CHARACTER_MST', 'F_UNIT_EXPLAIN_MST'):
        rows = inputs.original(table, required=False)
        selected[table] = {'key': None, 'rows': [r for r in rows
            if any(str(value) in form_ids | roots for value in r.values())]}
    selected['F_ABILITY_EXPLAIN_MST'] = {'key': 'Ga5V42LZ', 'rows': [r for r in
        inputs.original('F_ABILITY_EXPLAIN_MST', required=False) if r['Ga5V42LZ'] in skill_ids]}
    growth_keys = {(r['aU3o2D4t'], r['uk6Wh8mw']) for r in units + reward_selected['F_VISION_CARD_MST']['rows']}
    selected['F_UNIT_GROW_MST'] = {'key': None, 'rows': [r for r in
        inputs.original('F_UNIT_GROW_MST') if (r['aU3o2D4t'], r['uk6Wh8mw']) in growth_keys]}
    exp_keys = {r['0W7g6YXS'] for r in units}
    selected['F_UNIT_EXP_PATTERN_MST'] = {'key': None, 'rows': [r for r in
        inputs.original('F_UNIT_EXP_PATTERN_MST') if r['0W7g6YXS'] in exp_keys]}
    vc_exp_keys = {r['0W7g6YXS'] for r in reward_selected['F_VISION_CARD_MST']['rows']}
    selected['F_VISION_CARD_EXP_PATTERN_MST'] = {'key': None, 'rows': [r for r in
        inputs.original('F_VISION_CARD_EXP_PATTERN_MST', required=False) if r['0W7g6YXS'] in vc_exp_keys]}
    category_ids = set().union(*(numbers(r.get('GPUkhv72', '')) for r in units))
    selected['F_UNIT_SUB_CATEGORY_MST'] = {'key': 'SVT5aU9n', 'rows': [r for r in
        inputs.original('F_UNIT_SUB_CATEGORY_MST') if r['SVT5aU9n'] in category_ids]}
    character_ids = {r.get('p7esQ2y3') for r in units} - {None, '', '0'}
    selected['F_UNIT_CHARACTER_MST'] = {'key': 'p7esQ2y3', 'rows': [r for r in
        inputs.original('F_UNIT_CHARACTER_MST') if r['p7esQ2y3'] in character_ids]}
    current_units = {r['3HriTp6B']: r for r in inputs.current('F_UNIT_MST')}
    comparison = []
    for row in units:
        ident = row['3HriTp6B']
        old = current_units.get(ident)
        differences = [] if old is None else sorted(k for k in old.keys() | row.keys()
            if k != 'G4L0YIB2' and row.get(k) != old.get(k))
        comparison.append({'source_form_id': ident, 'name_jp': row['G4L0YIB2'],
            'current_name': old.get('G4L0YIB2') if old else None,
            'status': 'absent' if old is None else ('native_fields_differ' if differences else 'equivalent_except_name'),
            'differing_fields': differences})
    return {'schema': 1, 'source_kind': 'original_JP_native_archive',
        'counts': {k: len(v['rows']) for k, v in selected.items()},
        'source_inputs': inputs.receipts, 'tables': selected,
        'unit_comparison': comparison, 'dependency_discovery': 'Conservative numeric closure, source records unmodified',
        'missing': {'skills': missing, 'effect_groups': absent_groups, 'effects': absent_effects,
            'reward_master_ids': {kind: sorted(rewards[kind] - {r[key] for r in reward_selected[table]['rows']})
                for kind, table, key in [('EQUIP', 'F_EQUIP_ITEM_MST', 'J1YX9kmM'),
                    ('MATERIA', 'F_MATERIA_MST', 'H5jBL0Vf'), ('ITEM', 'F_ITEM_MST', 'tL6G9egd'),
                    ('VISIONCARD', 'F_VISION_CARD_MST', '5giCMUd2')]}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HOME / 'Sources/original-unit-content.json')
    parser.add_argument('--export-texts', action='store_true')
    parser.add_argument('--prepare-import', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--export-contract', action='store_true')
    parser.add_argument('--export-english', action='store_true')
    parser.add_argument('--embedded-english-contract', action='store_true')
    parser.add_argument('--icon-contract', action='store_true')
    parser.add_argument('--icon-bindings', action='store_true')
    args = parser.parse_args()
    inputs = Inputs()
    try:
        if args.export_texts:
            source = json.loads(args.output.read_text('utf-8'))
            export_text_requests(inputs, source, HOME / 'Sources/unit-text-translation-requests.json')
            return
        if args.export_contract:
            if (PROJECT / 'logs/jp-unit-native-english-integration.json').is_file():
                raise ValueError('English is embedded. Do not regenerate the raw Japanese gameplay contract over it.')
            source = json.loads(args.output.read_text('utf-8'))
            plan = json.loads((HOME / 'Sources/native-unit-id-map.json').read_text('utf-8'))
            emit_contract(inputs, source, plan)
            return
        if args.export_english:
            export_english(inputs, json.loads(args.output.read_text('utf-8')))
            return
        if args.embedded_english_contract:
            embedded_english_contract(inputs)
            return
        if args.icon_contract:
            icon_contract(inputs)
            return
        if args.icon_bindings:
            icon_contract(inputs, bindings_only=True)
            return
        if args.prepare_import:
            if (PROJECT / 'logs/jp-unit-native-english-integration.json').is_file():
                raise ValueError('English is embedded. Owned IDs remain reserved; do not regenerate raw Japanese gameplay rows.')
            if args.refresh:
                refreshed = recover(inputs)
                args.output.write_bytes(json_bytes(refreshed) + b'\n')
            prepare_import(inputs, json.loads(args.output.read_text('utf-8')))
            return
        result = recover(inputs)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(json_bytes(result) + b'\n')
        print(json.dumps({'output': str(args.output), 'sha256': digest(args.output.read_bytes()),
            'counts': result['counts'], 'missing': result['missing'],
            'unit_status': {s: sum(r['status'] == s for r in result['unit_comparison'])
                for s in ('absent', 'native_fields_differ', 'equivalent_except_name')}}))
    finally:
        inputs.close()


if __name__ == '__main__':
    main()
