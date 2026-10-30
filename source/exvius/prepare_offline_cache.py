"""Preseed the server's existing cache versions so local startup needs no fetch."""
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / 'data'
os.environ.setdefault('FFBE_DATA', str(DATA))
sys.path.insert(0, str(PROJECT / 'source/server'))
from ffbe_config import FORCE_TABLE_VERSIONS
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16
from decode_client_data import client_manifest, decode, json_record
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from android_offline import OFFLINE_TEXT

def raid_reward_banners(source, target, key):
    """Append local personal-reward links without changing original banner rows."""
    lines = [line for line in source.read_text(encoding='ascii').splitlines() if line]
    rows = [json_record(cbc_decrypt(key16(key), line)) for line in lines]
    existing = {str(row['fSxqkF10']) for row in rows}
    plain = cbc_decrypt(key16(key), lines[0])
    pad = plain[-1]
    double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
    events = json.loads((PROJECT / 'source/server/raid_rewards.json').read_text(encoding='utf8'))['events']
    archive = PROJECT / 'source/server/raid_archive.json'
    if archive.exists():
        events += json.loads(archive.read_text(encoding='utf8'))['events']
    for event in events:
        banner_id = event['reward_banner_id']
        if banner_id in existing:
            raise ValueError('Local raid reward banner ID collides with original data: ' + banner_id)
        row = {'fSxqkF10': banner_id, 'w2A76noc': '3',
               'G4L0YIB2': event['name'] + ' Personal Rewards',
               'T4o9heqC': '1,2,3,101,102,103', 'Z0EN6jSh': '61100',
               '6Dgaqir0': 'home_icon',
               '1X65WPLU': 'http://127.0.0.1/exvius/raid-rewards/' + event['dungeon_id'] + '.html',
               'xHZj7Va5': '', '2odVXyT8': '0', 'rUP3Gix0': '1'}
        lines.append(cbc_encrypt(key16(key), json.dumps(row, ensure_ascii=False,
                     separators=(',', ':')).encode('utf8'), double_pad=double))
        existing.add(banner_id)
    target.write_text('\n'.join(lines) + '\n', encoding='ascii')


def arena_entry_events(source, target, key):
    """Use the client's normal direct entry when the optional foyer is absent."""
    roots = [DATA / folder for folder in ('client/files', 'overlay', 'memorial_fill')]
    if any(any(root.rglob('Ver*_211020200.cpk')) for root in roots):
        shutil.copyfile(source, target)
        return
    output, removed = [], 0
    for line in source.read_text(encoding='ascii').splitlines():
        if not line:
            continue
        row = json_record(cbc_decrypt(key16(key), line))
        if row.get('4SWuwc0M') == '1003005' and row.get('q4f9IdMs') == '290002':
            removed += 1
        else:
            output.append(line)
    if removed != 1:
        raise ValueError('Expected the single original Arena foyer event')
    target.write_text('\n'.join(output) + '\n', encoding='ascii')


def loading_text(source, target, key, replacements=None, append_missing=False):
    replacements = OFFLINE_TEXT if replacements is None else replacements
    changed, output = set(), []
    sample_layers, sample_columns = None, None
    for encrypted in source.read_text(encoding='ascii').splitlines():
        if not encrypted:
            continue
        cipher = Cipher(algorithms.AES(key16(key)), modes.ECB())
        decryptor = cipher.decryptor()
        plain = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
        layers = 0
        while plain and 1 <= plain[-1] <= 16 and plain[-plain[-1]:] == bytes([plain[-1]]) * plain[-1]:
            plain = plain[:-plain[-1]]
            layers += 1
        lines = plain.decode('utf-8').splitlines(keepends=True)
        for index, line in enumerate(lines):
            fields = line.rstrip('\r\n').split('^')
            if sample_columns is None and len(fields) > 1:
                sample_columns, sample_layers = len(fields) - 1, layers
            if fields[0] in replacements:
                changed.add(fields[0])
                ending = line[len(line.rstrip('\r\n')):]
                lines[index] = '^'.join([fields[0]] + [replacements[fields[0]]] * (len(fields) - 1)) + ending
        plain = ''.join(lines).encode('utf-8')
        for _ in range(layers):
            pad = 16 - len(plain) % 16
            plain += bytes([pad]) * pad
        encryptor = cipher.encryptor()
        output.append(base64.b64encode(encryptor.update(plain) + encryptor.finalize()).decode('ascii'))
    if append_missing:
        if not sample_columns or sample_layers is None:
            raise ValueError('Original localized-text record shape is missing.')
        for text_key in sorted(set(replacements) - changed):
            plain = '^'.join([text_key] + [replacements[text_key]] * sample_columns).encode('utf8') + b'\n'
            for _ in range(sample_layers):
                pad = 16 - len(plain) % 16
                plain += bytes([pad]) * pad
            encryptor = Cipher(algorithms.AES(key16(key)), modes.ECB()).encryptor()
            output.append(base64.b64encode(encryptor.update(plain) + encryptor.finalize()).decode('ascii'))
            changed.add(text_key)
    if changed != set(replacements):
        raise ValueError('Expected localized labels were not found: ' + ','.join(sorted(set(replacements) - changed)))
    target.write_text('\n'.join(output) + '\n', encoding='ascii')
    _, records = decode(target.read_bytes(), key, localized=True)
    assert all(all(value == replacements[row['key']] for value in row['v'])
               for row in records if row['key'] in replacements)


def event_skill_sets(source, target, key):
    """Add preserved encounter skill sets missing from the Global client cache."""
    additions = json.loads((PROJECT / 'source/server/event_battles.json').read_text(
        encoding='utf8'))['native_master_additions']['F_MONSTER_SKILL_SET_MST']
    encounters = json.loads((PROJECT / 'source/server/event_encounters.json').read_text(encoding='utf8'))['missions']
    needed = {row['A5x02C6a'] for entry in encounters.values() for row in entry['bundle']['bV34YIJQ']}
    additions += [row for row in map(json.loads,
        (DATA / 'memorial_battle_decoded/F_MONSTER_SKILL_SET_MST.ndjson').read_text(encoding='utf8').splitlines())
                  if row['A5x02C6a'] in needed]
    lines = [line for line in source.read_text(encoding='ascii').splitlines() if line]
    existing = {json_record(cbc_decrypt(key16(key), line))['A5x02C6a'] for line in lines}
    plain = cbc_decrypt(key16(key), lines[0])
    pad = plain[-1]
    double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
    for row in additions:
        if row['A5x02C6a'] not in existing:
            lines.append(cbc_encrypt(key16(key), json.dumps(row, ensure_ascii=False,
                separators=(',', ':')).encode('utf8'), double_pad=double))
            existing.add(row['A5x02C6a'])
    target.write_text('\n'.join(lines) + '\n', encoding='ascii')


def exbonus_master(source, target, key, table):
    restored = json.loads((PROJECT / 'source/server/content/exbonus_masters.json').read_text(encoding='utf8'))['tables'][table]
    lines = [line for line in source.read_text(encoding='ascii').splitlines() if line]
    mode, original = decode(source.read_bytes(), key)
    identity = lambda row: row[restored['key']] if restored['key'] else json.dumps(row, sort_keys=True)
    existing = {identity(row) for row in original}
    if mode == 'cbc':
        plain = cbc_decrypt(key16(key), lines[0])
        pad = plain[-1]
        double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
    else:
        decryptor = Cipher(algorithms.AES(key16(key)), modes.ECB()).decryptor()
        plain = decryptor.update(base64.b64decode(lines[0])) + decryptor.finalize()
        layers = 0
        while plain and 1 <= plain[-1] <= 16 and plain[-plain[-1]:] == bytes([plain[-1]]) * plain[-1]:
            plain = plain[:-plain[-1]]
            layers += 1
        assert layers > 0 and isinstance(json.loads(plain), dict)
    def encode(row):
        body = json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf8')
        if mode == 'cbc':
            return cbc_encrypt(key16(key), body, double_pad=double)
        for _ in range(layers):
            pad = 16 - len(body) % 16
            body += bytes([pad]) * pad
        encryptor = Cipher(algorithms.AES(key16(key)), modes.ECB()).encryptor()
        return base64.b64encode(encryptor.update(body) + encryptor.finalize()).decode('ascii')
    if table == 'F_ABILITY_EXPLAIN_MST':
        descriptions = {identity(r): r['T7aEx3Mj'] for r in restored['rows']}
        for index, row in enumerate(original):
            text = str(row.get('T7aEx3Mj', ''))
            if identity(row) in descriptions and (not text or text == 'Test data'
                    or re.search(r'[\u3040-\u30ff\u3400-\u9fff]', text)):
                row['T7aEx3Mj'] = descriptions[identity(row)]
                lines[index] = encode(row)
    for row in restored['rows']:
        if identity(row) not in existing:
            lines.append(encode(row))
            existing.add(identity(row))
    target.write_text('\n'.join(lines) + '\n', encoding='ascii')


def localized_text_versions(source, target, key, replacements):
    """The localized-text index, not the general version table, selects this file."""
    output, changed = [], set()
    for line in source.read_text(encoding='ascii').splitlines():
        if not line:
            continue
        plain = cbc_decrypt(key16(key), line)
        row = json_record(plain)
        table = row.get('a4hXTIm0')
        if table in replacements:
            version, path = replacements[table]
            content = path.read_bytes()
            # These are the English version/hash/size columns. The original
            # English Ver84 file is 32512 bytes, matching MLOSu5E0 exactly.
            row.update({'00zAYGYS': str(version), 'zptmZGqa': hashlib.md5(content).hexdigest(),
                        'MLOSu5E0': str(len(content))})
            pad = plain[-1]
            double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
            line = cbc_encrypt(key16(key), json.dumps(row, ensure_ascii=False,
                               separators=(',', ':')).encode('utf8'), double_pad=double)
            if table in changed:
                raise ValueError('Duplicate English localized-text index entry: ' + table)
            changed.add(table)
        output.append(line)
    if changed != set(replacements):
        raise ValueError('Missing English localized-text index entries: ' + str(set(replacements) - changed))
    target.write_text('\n'.join(output) + '\n', encoding='ascii')


def main():
    manifest = client_manifest(PROJECT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
    by_table = {entry['table']: (token, entry['key']) for token, entry in manifest.items()}
    registry = ET.parse(DATA / 'client/shared_prefs/gamedata.xml')
    count = 0
    overrides = dict(part.split('=', 1) for part in FORCE_TABLE_VERSIONS.split(','))
    localized_updates = {}
    index_update = None
    for table, version in overrides.items():
        token, key = by_table[table]
        sources = list((DATA / 'client/files').rglob('Ver*_' + token + '.dat'))
        if len(sources) != 1:
            raise ValueError('Expected one content source for ' + table)
        source = sources[0]
        relative = source.relative_to(DATA / 'client/files')
        target = DATA / 'overlay' / relative.parent / ('Ver' + version + '_' + token + '.dat')
        target.parent.mkdir(parents=True, exist_ok=True)
        if table in ('F_TEXT_TOWN_STORE_OWNER_NAME', 'F_TEXT_MONSTER_NAME', 'F_TEXT_NPC_NAME', 'F_TEXT_MISSION'):
            localized_updates[table] = (version, target)
        if table == 'F_DEFINE_MST':
            lines, changed = [], 0
            for line in source.read_text(encoding='ascii').splitlines():
                if not line:
                    continue
                plain = cbc_decrypt(key16(key), line)
                row = json_record(plain)
                if row.get('AK8Nn7ta') == 'TNC_SWITCH_ID':
                    if 'YjIUDJ97' not in row:
                        raise ValueError('Terms switch value column is missing.')
                    row['YjIUDJ97'] = '0'
                    pad = plain[-1]
                    double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
                    line = cbc_encrypt(key16(key), json.dumps(row, ensure_ascii=False,
                        separators=(',', ':')).encode('utf-8'), double_pad=double)
                    changed += 1
                lines.append(line)
            if changed != 1:
                raise ValueError('Expected one original terms notice switch.')
            target.write_text('\n'.join(lines) + '\n', encoding='ascii')
            _, decoded = decode(target.read_bytes(), key)
            assert next(r for r in decoded if r.get('AK8Nn7ta') == 'TNC_SWITCH_ID')['YjIUDJ97'] == '0'
        elif table == 'F_BANNER_MST':
            raid_reward_banners(source, target, key)
        elif table == 'F_MAP_EVENT_MST':
            arena_entry_events(source, target, key)
        elif table == 'F_TEXT_TEXT_EN':
            loading_text(source, target, key, append_missing=True)
        elif table == 'F_TEXT_NPC_NAME':
            captions = json.loads((PROJECT / 'source/server/content/dialogue_en.json').read_text(encoding='utf8'))
            loading_text(source, target, key,
                         {'MST_NPC_NAME_' + iid: row['english']
                          for iid, row in captions['npc_names'].items()}, append_missing=True)
        elif table == 'F_TEXT_TOWN_STORE_OWNER_NAME':
            loading_text(source, target, key,
                         {'MST_TOWN_STORE_OWNER_NAME_' + iid: 'King Mog'
                          for iid in ('7000456', '7000457', '7000458')}, append_missing=True)
        elif table == 'F_LOCALIZED_TEXT_MST':
            index_update = source, target, key
        elif table == 'F_TEXT_MONSTER_NAME':
            bindings = json.loads((PROJECT / 'source/server/event_battles.json').read_text(encoding='utf8'))
            names = {'MST_MONSTER_NAME_' + iid: name
                     for iid, name in bindings['local_monster_names'].items()}
            encounters = json.loads((PROJECT / 'source/server/colosseum_encounters.json').read_text(encoding='utf8'))
            names.update({'MST_MONSTER_NAME_' + iid: name
                          for iid, name in encounters['local_monster_names'].items()})
            events = json.loads((PROJECT / 'source/server/event_encounters.json').read_text(encoding='utf8'))
            names.update({'MST_MONSTER_NAME_' + iid: name
                          for iid, name in events['local_monster_names'].items()})
            loading_text(source, target, key, names, append_missing=True)
        elif table == 'F_MONSTER_SKILL_SET_MST':
            event_skill_sets(source, target, key)
        elif table in ('F_UNIT_EX_BONUS_MST', 'F_UNIT_SERIES_NV_PIECE_MST',
                       'F_SUBLIMATION_RECIPE_MST', 'F_ABILITY_MST', 'F_ABILITY_EXPLAIN_MST',
                       'F_UNIT_SERIES_LV_ACQUIRE_MST'):
            exbonus_master(source, target, key, table)
        else:
            shutil.copyfile(source, target)
        entry = registry.find("string[@name='key" + table + "']")
        if entry is None:
            raise ValueError('Original cache registry is missing ' + table)
        entry.text = version
        count += 1
    if index_update is None:
        raise ValueError('The local English text index must be included in cache versions.')
    localized_text_versions(*index_update, localized_updates)
    output = DATA / 'overlay/shared_prefs/gamedata.xml'
    output.parent.mkdir(exist_ok=True)
    registry.write(output, encoding='utf-8', xml_declaration=True)
    print(f'Prepared {count} local cache versions. Original content preserved; online terms notice disabled.')


if __name__ == '__main__':
    main()
