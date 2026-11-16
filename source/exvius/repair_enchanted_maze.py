"""Restore Enchanted Maze script battle dependencies through the field path."""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'tools/vendor/python')]
from battle_content import IndexSource, derive_mission

# Each resource is the stage's original event script, not an inferred mission
# prefix. Script scenario IDs and mission IDs use separate namespaces.
STAGES = (
    ('2210101', 'common_lang/sd/event/SP/Ver8_22101010101.cpk',
     '22101010101_event.bin', tuple(str(i) for i in range(2210101, 2210108))),
    ('2210102', 'common_lang/sd/event/SP/Ver8_22101021101.cpk',
     '22101021101_event.bin', tuple(str(i) for i in range(2210111, 2210124))),
)
TAGS = ('Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'Wp39QX52', 'BJ6A0KTt', '7KCkJd1E')
CHANNELS = ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07')


def build(source=None):
    from cricodecs import cpk
    from repair_field_scenarios import script_scenarios

    source = source or IndexSource()
    original = ROOT / 'data/web_sources/global_archive_mst_decoded'
    masters = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_MST.ndjson').read_text(encoding='utf8').splitlines())}
    links = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_GROUP_MST.ndjson').read_text(encoding='utf8').splitlines())}
    parts = {}
    for row in source.load('F_MONSTER_PARTS_MST'):
        parts.setdefault(row['xqartN26'], []).append(row)
    result = {}
    for mid, relative, member, expected in STAGES:
        archive = ROOT / 'data/client/files' / relative
        package = cpk.load(str(archive))
        script = next(package.file_bytes(i) for i, entry in enumerate(package.file_infos())
                      if entry.full_path == member)
        if script_scenarios(script) != set(expected):
            raise ValueError('Original Enchanted Maze scenario references changed: ' + mid)
        required = list(expected)
        map_source = None
        if mid == '2210102':
            # These two original map NPC pages still call Beginner scenarios,
            # independently of the Intermediate external event script.
            relative_map = 'common_lang/sd/map/SP/Ver32_221010210.cpk'
            map_archive = ROOT / 'data/overlay' / relative_map
            package = cpk.load(str(map_archive))
            map_data = next(package.file_bytes(i) for i, entry in enumerate(package.file_infos())
                            if entry.full_path == 'map.bin')
            commands = ((29975, '2210107'), (117390, '2210101'))
            for offset, sid in commands:
                if map_data[offset:offset + 7] != b'\x47\x00\x04' + int(sid).to_bytes(4, 'big'):
                    raise ValueError('Enchanted Maze map NPC battle command changed: ' + sid)
                required.append(sid)
            map_source = {'archive': str(map_archive.relative_to(ROOT)).replace('\\', '/'),
                          'member': 'map.bin', 'sha256': hashlib.sha256(map_data).hexdigest(),
                          'battle_commands': [{'offset': offset, 'scenario': sid}
                                              for offset, sid in commands]}
        if not set(required) <= masters.keys() or not set(required) <= links.keys():
            raise ValueError('Missing original Enchanted Maze scenario metadata: ' + mid)
        groups = {links[sid]['2fY1IomW'] for sid in required}
        dependencies = derive_mission(int(mid), source, field_groups=groups)
        bundle = {tag: copy.deepcopy(dependencies.get(tag, [])) for tag in TAGS}
        bundle['rqxw0p9k'] = [copy.deepcopy(masters[sid]) for sid in required]
        bundle['YjHhvN65'] = [copy.deepcopy(links[sid]) for sid in required]
        bundle['JR7jZci2'] = []
        for sid in required:
            gid = links[sid]['2fY1IomW']
            for slot in bundle['Bi6hVv34']:
                if slot['2fY1IomW'] != gid or slot['WJdBp9f0'] != '1':
                    continue
                for part in parts[slot['xqartN26']]:
                    bundle['JR7jZci2'].append({
                        'ja07xgLF': sid, '2fY1IomW': gid,
                        'xqartN26': slot['xqartN26'], 'Z0EN6jSh': slot['Z0EN6jSh'],
                        '6Yc4RkdM': part['6Yc4RkdM'],
                        **{channel: part.get(channel, '') for channel in CHANNELS}})
        result[mid] = bundle, {
            'campaign': 'The Enchanted Maze',
            'script': {'archive': str(archive.relative_to(ROOT)).replace('\\', '/'),
                       'member': member, 'sha256': hashlib.sha256(script).hexdigest(),
                       'scenario_ids': list(expected)},
            'original_global_scenarios': {
                'source': 'data/web_sources/global_archive_mst_decoded/'
                    'F_SCENARIO_BATTLE_MST.ndjson and F_SCENARIO_BATTLE_GROUP_MST.ndjson',
                'group_ids': {sid: links[sid]['2fY1IomW'] for sid in required}},
            'recovered': 'Original script references and complete Global scenario metadata '
                'and group links. Exact referenced native formations, positions, slots, '
                'actor profiles, AI, skills and each actor/part reward tuple retained. '
                'Only dependency records are loaded; original maze door conditions, '
                'routing and battle selection remain in the original scripts.',
            'regional_limit': 'Formations and actor profiles/reward tuples are the retained '
                'Japanese native records for the exact group IDs explicitly linked by '
                'the Global scenarios. Separate original Global per-encounter reward '
                'allocations are not retained. No opening combat phase, random field '
                'battle allocation, substitute group or invented drop rate is added.'}
        if map_source:
            result[mid][1]['map_npc_scripts'] = map_source
    return result


def main():
    path = ROOT / 'source/server/event_encounters.json'
    document = json.loads(path.read_text(encoding='utf8'))
    entries = build()
    for mid, (bundle, provenance) in entries.items():
        entry = document['missions'].setdefault(mid, {})
        entry.setdefault('bundle', {}).update(bundle)
        entry['enchanted_maze_script_dependencies'] = provenance
    pending = ROOT / 'build/scratch/enchanted-maze-encounter-write.json'
    pending.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pending.open('w', encoding='utf8') as stream:
            json.dump(document, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    print('CHECKPOINT restored Enchanted Maze script dependencies', ','.join(entries))


if __name__ == '__main__':
    main()
