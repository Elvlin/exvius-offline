"""Recover native treasure definitions and map ownership from the preserved database."""
import hashlib
from array import array
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
from cricodecs import cpk


def main():
    database = ROOT / 'data/web_sources/ffbe-data.db'
    output = ROOT / 'source/server/content/field_treasures.json'
    previous = json.loads(output.read_text(encoding='utf8'))
    override_path = output.with_name('field_treasure_overrides.json')
    overrides = json.loads(override_path.read_text(encoding='utf8'))
    retained = {str(row['id']): row for row in overrides['treasures']}
    connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    rows = {str(row['treasureId']): dict(row)
            for row in connection.execute('select * from field_treasure')}
    resources = {str(row['resourceId']): dict(row)
                 for row in connection.execute('select * from resource_map')}
    towns = [dict(row) for row in connection.execute('select * from town')]
    missions = [dict(row) for row in connection.execute('select * from mission')]
    dungeons = {str(row['dungeonId']): dict(row)
                for row in connection.execute('select * from dungeon')}

    owners = {}
    for kind, definitions in (('towns', towns), ('missions', missions)):
        for row in definitions:
            identity = str(row['townId' if kind == 'towns' else 'missionId'])
            files = row.get('fileInfo')
            if not files and kind == 'missions':
                files = dungeons.get(str(row.get('dungeonId')), {}).get('fileInfo')
            for rid in str(files or '').split(','):
                resource = resources.get(rid)
                if resource and resource.get('drE35YcF') == 'map':
                    key = Path(resource['fileName']).stem
                    owners.setdefault(key, {'towns': set(), 'missions': set()})[kind].add(identity)

    buffers = {path.parent.name: path.read_bytes()
               for path in (ROOT / 'data/web_sources/field_maps').glob('*/map.bin')}
    wanted = {Path(row['fileName']).stem for row in resources.values()
              if row.get('drE35YcF') == 'map'}
    for folder in ('data/overlay', 'data/client/files', 'data/memorial_fill'):
        for path in (ROOT / folder).rglob('*.cpk'):
            match = re.fullmatch(r'Ver\d+_(.+)\.cpk', path.name)
            if not match or match[1] not in wanted or match[1] in buffers:
                continue
            archive = cpk.load(str(path))
            for index, member in enumerate(archive.file_infos()):
                if member.full_path == 'map.bin' or member.full_path.endswith('/map.bin'):
                    buffers[match[1]] = archive.file_bytes(index)
                    break

    bindings = {}
    for resource, data in buffers.items():
        for match in re.finditer(rb'[HM]\x00\x05(.{4})\x01', data, re.DOTALL):
            iid = str(struct.unpack('>I', match[1])[0])
            if iid not in rows:
                continue
            switch = struct.pack('>I', int(rows[iid]['openSwitch'] or 0))
            nearby = data[max(0, match.start() - 256):match.end() + 256]
            if rows[iid]['openSwitch'] and switch not in nearby:
                continue
            binding = bindings.setdefault(iid, {'resources': set(), 'towns': set(), 'missions': set()})
            binding['resources'].add(resource)
            for kind in ('towns', 'missions'):
                binding[kind].update(owners.get(resource, {}).get(kind, set()))

    treasures = []
    for iid, source in rows.items():
        rewards = []
        for entry in source['reward'].split(','):
            fields = entry.split(':')
            if len(fields) == 4 and fields[3] == '100':
                fields = fields[:3]
            if len(fields) != 3 or not all(field.isdigit() for field in fields):
                raise ValueError('Unresolved reward tuple: ' + iid + ' ' + entry)
            rewards.append(':'.join(fields))
        row = {'id': int(iid), 'switch': int(source['openSwitch'] or 0),
               'rewards': ','.join(rewards), 'database': True}
        for key, values in bindings.get(iid, {}).items():
            if values:
                row[key] = sorted(values, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))
        # Preserve the already documented Global rewards where JP differs.
        # In particular Egg Seekers' staff quest pays 5,000 in Global, 8,000
        # in the preserved database. Map identity and switch still agree.
        if iid in retained:
            row.update(retained[iid])
            row['database'] = True
        replacements = overrides.get('legacy_reward_replacements', {})
        if row['rewards'] in replacements:
            row['original_rewards'] = row['rewards']
            row['rewards'] = replacements[row['rewards']]['reward']
            row['recovery_note'] = replacements[row['original_rewards']]['note']
        treasures.append(row)
    previous['sources'] = list(dict.fromkeys(previous['sources'] + [
        'https://drive.google.com/file/d/1DCw_qFpe03-rCnMiKMWAS5EV56XYO-GA/view']))
    previous['database_sha256'] = hashlib.sha256(database.read_bytes()).hexdigest()
    previous['note'] = ('All 2,667 preserved native treasure definitions. Rewards and opening switches '
                        'come from field_treasure; typed treasure references in original map binaries '
                        'supply location ownership where available. Documented Global overrides are retained.')
    previous['treasures'] = treasures
    output.write_text(json.dumps(previous, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    # Map scripts can name shared groups whose IDs do not start with the
    # mission ID. Include existing group IDs referenced by either byte order
    # in their original map binaries, then let the normal dependency loader
    # provide the monsters, parts and skills. No synthetic phase is created.
    sys.path.insert(0, str(ROOT / 'source/server'))
    from battle_content import IndexSource
    source = IndexSource()
    groups = source.load('F_BATTLE_GROUP_MST')
    monster_ids = {str(row['xqartN26']) for row in source.load('F_MONSTER_MST')}
    part_ids = {str(row['xqartN26']) for row in source.load('F_MONSTER_PARTS_MST')}
    complete_monsters = monster_ids & part_ids
    valid_groups, invalid = set(), set()
    for row in groups:
        group = int(row['2fY1IomW'])
        valid_groups.add(group)
        if str(row['xqartN26']) not in complete_monsters:
            invalid.add(group)
    valid_groups -= invalid
    field_missions = {str(row['missionId']) for row in missions
                      if not int(row.get('waveCount') or 0) or int(row.get('type') or 0) == 2}
    mission_groups = {}
    for resource, data in buffers.items():
        group_ids = set()
        for offset in range(4):
            length = (len(data) - offset) // 4 * 4
            values = array('I')
            values.frombytes(data[offset:offset + length])
            group_ids.update(valid_groups.intersection(values))
            values.byteswap()
            group_ids.update(valid_groups.intersection(values))
        for mid in owners.get(resource, {}).get('missions', set()) & field_missions:
            mission_groups.setdefault(mid, set()).update(group_ids)
    # A scripted field boss names a scenario, not a battle group. Its group
    # can belong to an earlier story mission (Earth Shrine uses 111010306),
    # so neither a map integer scan nor a mission-prefix search finds it.
    scenario_groups = {}
    for row in connection.execute('select * from scenario_battle_group'):
        scenario_groups.setdefault(str(row['scenarioBattleId']), []).append(int(row['battleGroupId']))
    scenario_links = {}
    for row in connection.execute('select * from location_scenario_battle'):
        mid = str(row['targetId'])
        if int(row['locationType']) != 1 or mid not in field_missions:
            continue
        for sid in re.findall(r'\d+', str(row['scenarioBattleInfo'] or '')):
            for group in scenario_groups.get(sid, []):
                if group not in valid_groups:
                    raise ValueError(f'Field scenario {mid}/{sid}: incomplete group {group}')
                mission_groups.setdefault(mid, set()).add(group)
                scenario_links.setdefault(mid, []).append({'scenario': sid, 'group': str(group)})
    field_output = output.with_name('field_group_bindings.json')
    field_output.write_text(json.dumps({
        'database_sha256': previous['database_sha256'],
        'note': 'Existing native group IDs referenced in original field map binaries, plus '
                'the original location_scenario_battle -> scenario_battle_group relationships. '
                'This is a dependency set, not an opening battle timeline.',
        'scenario_links': scenario_links,
        'missions': {mid: list(map(str, sorted(values))) for mid, values in mission_groups.items()}
    }, indent=1) + '\n', encoding='utf8')
    print(json.dumps({'treasures': len(treasures), 'map_binaries': len(buffers),
                      'bound_treasures': len(bindings), 'global_overrides': len(retained),
                      'field_missions': len(mission_groups)}))


if __name__ == '__main__':
    main()
