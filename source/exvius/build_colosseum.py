"""Assemble Colosseum encounters through the established native battle assembler.

The shipped Global group labels identify each grade/rank/round and boss.
Original groups with complete monster, part, skill and AI data are retained.
The missing Advanced groups use user-approved local reconstructions.
Normal encounter weights are uniform local policy where the server lottery was
not preserved. Background 100103 is the original arena variant for ordinary battles.
"""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('FFBE_DATA', str(ROOT / 'data'))
sys.path.insert(0, str(ROOT / 'source/server'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from battle_content import IndexSource, Source, derive_mission


class EncounterSource(Source):
    def __init__(self, base, group_id, overrides=None):
        self.base, self.group_id = base, group_id
        self.overrides = overrides or {}

    def load(self, table):
        if table in self.overrides:
            return self.overrides[table]
        if table == 'F_MISSION_PHASE_MST':
            return [{'qo3PECw6': '99999999', '6v7y3QcJ': '1', 'gou39JeI': '2',
                     '6uIYE15X': self.group_id, 'DYTx1Is3': '100103'}]
        if table == 'F_BATTLE_LOTTERY_MST':
            return [{'c2gnh6Jd': self.group_id, 'ixDq7yJ8': '1', '2fY1IomW': self.group_id}]
        return self.base.load(table)


def main():
    base = IndexSource()
    groups = defaultdict(list)
    monsters = {r['xqartN26']: r for r in base.load('F_MONSTER_MST')}
    for row in base.load('F_BATTLE_GROUP_MST'):
        groups[row['2fY1IomW']].append(row)
    label_file = ROOT / 'data/text_decoded/F_TEXT_COLOSSEUM_MONSTER_GROUP_NAME.ndjson'
    labels = [json.loads(line) for line in label_file.read_text(encoding='utf8').splitlines() if line]
    progress_file = ROOT / 'data/mst_decoded/F_CLSM_PROGRESS_MST.ndjson'
    progresses = [json.loads(line) for line in progress_file.read_text(encoding='utf8').splitlines() if line]
    ranks = {'D': 1, 'C': 2, 'B': 3, 'A': 4, 'S': 5}
    occurrences = defaultdict(int)
    encounters, missing = {}, []
    for entry in labels:
        match = re.fullmatch(r'Class ([DCBAS])([1-5])( Boss)?', entry['v'][0])
        if match is None:
            raise ValueError('Unexpected original Colosseum group label: ' + entry['key'])
        rank, number, boss_text = match.groups()
        boss = bool(boss_text)
        marker = (rank, number, boss)
        grade = occurrences[marker] // (1 if boss else 5) + 1
        occurrences[marker] += 1
        source = next(p for p in progresses if int(p['3JuUWi4x']) == grade and
                      int(p['iI7ePy3B']) == ranks[rank] and p['LiQ36UFf'].endswith('0' + number))
        progress = source['i5pd8xr3']
        group_id = entry['key'].rsplit('_', 1)[-1]
        if not groups.get(group_id):
            missing.append({'progress': progress, 'group_id': group_id, 'boss': boss,
                            'reason': 'Global group is absent from the preserved battle corpus'})
            continue
        bundle = derive_mission(99999999, EncounterSource(base, group_id))
        # GL ClsmVsCpuEnemyInfo::setEnemyInfo parses graphic ID, order, position.
        # Reversing the first two fields loads monster_cgg_1.csv and crashes.
        enemy_info = '-'.join(monsters[row['xqartN26']]['V9j8wJcC'] + ':' +
                              str(row['Z0EN6jSh']) + ':' + row['MxLFKZ13']
                              for row in sorted(groups[group_id], key=lambda r: int(r['Z0EN6jSh'])))
        target = encounters.setdefault(progress, {'normal': [], 'boss': []})
        target['boss' if boss else 'normal'].append({
            'group_id': group_id, 'weight': 1, 'group_type': int(boss),
            'enemy_info': enemy_info, 'bgm': '0', 'background': '100103', 'bundle': bundle})
    from colosseum_reconstruction import Reconstructor, REFERENCE
    known = [groups[entry['key'].rsplit('_', 1)[-1]] for entry in labels
             if groups.get(entry['key'].rsplit('_', 1)[-1])]
    reconstructor = Reconstructor(base, known)
    wiki_file = ROOT / 'logs/reference/colosseum/colosseum-wiki.json'
    wiki = {row['round']: row for row in json.loads(wiki_file.read_text(encoding='utf8'))['rows']
            if row['grade'] == 'Advanced'}
    absent = defaultdict(list)
    for row in missing:
        absent[row['progress']].append(row)
    reconstructed, local_names = {}, {}
    for progress, originals in sorted(absent.items(), key=lambda pair: int(pair[0])):
        master = next(p for p in progresses if p['i5pd8xr3'] == progress)
        if master['3JuUWi4x'] != '3':
            raise ValueError('Unexpected missing non-Advanced round: ' + progress)
        rank = next(letter for letter, number in ranks.items() if number == int(master['iI7ePy3B']))
        round_name = rank + '-' + str(int(master['LiQ36UFf'][-2:]))
        local_groups, local_monsters, local_parts, provenance = reconstructor.round(progress, wiki[round_name], originals)
        target = encounters.setdefault(progress, {'normal': [], 'boss': []})
        local_by_id = {row['xqartN26']: row for row in local_monsters}
        local_names.update({row['xqartN26']: row['G4L0YIB2'] for row in local_monsters})
        local_names.update({row['xqartN26'] + chr(64 + int(row['6Yc4RkdM'])):
                            row['G4L0YIB2'] for row in local_parts})
        for original, slots in local_groups:
            group_id = original['group_id']
            bundle = derive_mission(99999999, EncounterSource(base, group_id, {
                'F_BATTLE_GROUP_MST': slots, 'F_MONSTER_MST': local_monsters,
                'F_MONSTER_PARTS_MST': local_parts}))
            enemy_info = '-'.join(local_by_id[row['xqartN26']]['V9j8wJcC'] + ':' +
                                  str(row['Z0EN6jSh']) + ':' + row['MxLFKZ13']
                                  for row in slots)
            target['boss' if original['boss'] else 'normal'].append({
                'group_id': group_id, 'weight': 1, 'group_type': int(original['boss']),
                'enemy_info': enemy_info, 'bgm': '0', 'background': '100103',
                'local_reconstruction': True, 'bundle': bundle})
        reconstructed[progress] = {'round': round_name, 'enemies': provenance}
    document = {'version': 1,
        'provenance': {'labels': str(label_file.relative_to(ROOT)).replace('\\', '/'),
                       'labels_sha256': hashlib.sha256(label_file.read_bytes()).hexdigest(),
                       'battles': 'source/server/content/battle original Memorial index',
                       'lottery': 'Uniform local normal weights; original server weights unavailable',
                       'background': '100103, original battle_bg_0010_03.jpg and its ordinary battle animation',
                       'advanced_reconstruction': 'User approved 2026-10-25. Original wiki species, body/limb HP, MP, level and resistances where published. Known model/AI and combat stats adapted locally. Normal pairs rotate through the wiki species; fifth group includes all species. Original encounter combinations and lottery weights were not preserved.',
                       'advanced_wiki_sha256': hashlib.sha256(REFERENCE.read_bytes()).hexdigest()},
        'rounds': encounters, 'missing_original_groups': missing,
        'reconstructed_rounds': reconstructed, 'local_monster_names': local_names}
    output = ROOT / 'source/server/colosseum_encounters.json'
    output.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    (ROOT / 'source/server/colosseum_names.json').write_text(
        json.dumps(local_names, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    print('Wrote', len(encounters), 'rounds;', len(reconstructed), 'local Advanced reconstructions')


if __name__ == '__main__':
    main()
