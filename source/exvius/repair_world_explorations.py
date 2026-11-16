"""Restore finite random fights in the initial world explorations.

Original server formation draws were not retained. These explicit local runs
match the published species, fight, EXP and Gil totals using unchanged native
monster profiles. They do not claim to recover retail formation order or loot.
"""
from collections import Counter
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server')]
import battle_content

# mission, source page, random battles, EXP, Gil, native actor/count pairs.
STAGES = (
    ('1110104', 'Earth_Shrine', 13, 130, 63,
     (('101001000', 12), ('102001000', 11), ('109011000', 2))),
    ('1110204', 'Latius_Woods', 15, 536, 81,
     (('103001000', 3), ('105001000', 3), ('109001000', 9),
      ('111001000', 4), ('209001000', 1), ('111031000', 5),
      ('101011000', 6), ('111011000', 4))),
    ('1110304', 'Dalnakya_Cavern', 18, 1788, 181,
     (('103021000', 4), ('109012000', 2), ('108001000', 4),
      ('105001001', 22), ('103011000', 6), ('112001000', 5),
      ('102001001', 5), ('101025000', 5))),
    ('1110604', 'Grandshelt_Catacombs', 21, 5400, 148,
     (('112011000', 11), ('101006000', 16), ('103012000', 14),
      ('112021000', 9))),
    ('1110804', 'Fulan_Pass', 22, 10816, 402,
     (('206011000', 2), ('201021000', 6), ('105051000', 10),
      ('111002000', 6), ('206001001', 9), ('111012000', 7),
      ('101013000', 5), ('202011000', 1), ('106001000', 8))),
)


def build(source=None):
    source = source or battle_content.IndexSource()
    groups = source.load('F_BATTLE_GROUP_MST')
    parts = {}
    for row in source.load('F_MONSTER_PARTS_MST'):
        parts.setdefault(row['xqartN26'], []).append(row)
    existing_ids = {r['2fY1IomW'] for r in groups}
    output = {}
    for mid, page, fights, experience, gil, allocations in STAGES:
        wanted = dict(allocations)
        # Each profile must occur in this dungeon's original native groups.
        # Explicit IDs avoid selecting a later same-name quest enemy.
        area = mid[:-2]
        own_groups = {r['2fY1IomW'] for r in groups
                      if r['2fY1IomW'].startswith(area)
                      and r['xqartN26'] in wanted}
        own_actors = {r['xqartN26'] for r in groups
                      if r['2fY1IomW'] in own_groups}
        if not wanted.keys() <= own_actors:
            raise ValueError('Missing original world profiles: ' + mid)
        totals = [sum(int(p[token]) * count for iid, count in allocations
                      for p in parts[iid])
                  for token in ('B6H34Mea', '7UR4J2SE')]
        if totals != [experience, gil]:
            raise ValueError('Published world totals disagree: ' + mid)
        dependencies = battle_content.derive_mission(int(mid), source,
                                                       field_groups=own_groups)
        bundle = {tag: copy.deepcopy(dependencies.get(tag, []))
                  for tag in ('wbet57nF', 'bV34YIJQ', 'Wp39QX52',
                              'BJ6A0KTt', '7KCkJd1E')}
        bundle['wbet57nF'] = [r for r in bundle['wbet57nF']
                              if r['xqartN26'] in wanted]
        bundle['bV34YIJQ'] = [r for r in bundle['bV34YIJQ']
                              if r['xqartN26'] in wanted]
        bundle['Bi6hVv34'], bundle['6v0LPiRe'] = [], []
        # Balanced authored formations cover the exact published finite run.
        # IDs 70 onward are checked against every original group before use.
        remaining = Counter(wanted)
        for index in range(fights):
            gid = mid + str(70 + index)
            if gid in existing_ids:
                raise ValueError('World encounter group collision: ' + gid)
            size = (sum(remaining.values()) + fights - index - 1) // (fights - index)
            if not 1 <= size <= 5:
                raise ValueError('Invalid world formation size: ' + mid)
            for slot in range(1, size + 1):
                iid = max(remaining, key=lambda key: (remaining[key], key))
                remaining[iid] -= 1
                if not remaining[iid]:
                    del remaining[iid]
                bundle['Bi6hVv34'].append({
                    '2fY1IomW': gid, 'xqartN26': iid,
                    'MxLFKZ13': str(110 + 70 * ((slot - 1) % 2)) + ',' + str(210 + 85 * (slot - 1)),
                    'Z0EN6jSh': str(slot), '3t7pZM5V': '2',
                    'WJdBp9f0': '1', 'm9BvFk2X': '1'})
                for part in parts[iid]:
                    bundle['6v0LPiRe'].append({
                        'qo3PECw6': mid, 'YzGa63QM': '10', '2fY1IomW': gid,
                        'h4Sjf96p': '0', 'Z0EN6jSh': str(slot),
                        'xqartN26': iid, '6Yc4RkdM': part['6Yc4RkdM'],
                        '9BetM2Ds': part.get('9BetM2Ds', ''),
                        'MZn8LC6H': '', 'g4voc2Aw': '',
                        'Vf5DGw07': '', '4K8t5dVh': '0', 'V2mCH5UR': '',
                        '14FMQseU': '0'})
        if remaining:
            raise ValueError('Unallocated world enemies: ' + mid)
        output[mid] = (bundle, {
            'campaign': page.replace('_', ' ') + ' - Exploration',
            'sources': ['https://exvius.fandom.com/wiki/' + page + '/Exploration',
                        'logs/reference/world-exploration-wiki-20261110.json'],
            'recovered': 'Original own-dungeon actor identities, combat profiles, AI, skills, '
                         'published regular species totals and random battle/EXP/Gil totals. '
                         'Original scripted bosses and quest encounters remain separate.',
            'reconstructed': 'Local finite formations partition the published enemy counts '
                             'across the documented number of fights. Formation composition, '
                             'positions and draw order are not recovered retail allocations. '
                             'Each original native occurrence key starts at zero and exhausts. '
                             'No refill, foreign actor, changed encounter rate or invented loot roll.',
            'published_random_totals': {'battles': fights, 'experience': experience,
                                        'gil': gil, 'actors': wanted},
            'item_drops': {
                'source': 'Retained native Japanese F_MONSTER_PARTS_MST battle index, '
                          'the exact original own-dungeon actor ID and part number.',
                'recovered': 'Each occurrence carries its own actor drop list in '
                             '6v0LPiRe. Original item IDs, quantities and rates are '
                             'retained; no shared world-material list is substituted.',
                'actor_pools': {iid + ':' + p['6Yc4RkdM']: p.get('9BetM2Ds', '')
                               for iid in wanted for p in parts[iid]},
                'regional_limit': 'These are preserved Japanese native drop records '
                                  'for the directly referenced story actors. A separate '
                                  'original Global per-encounter allocation is not retained.',
            },
        })
    return output


def main():
    path = ROOT / 'source/server/event_encounters.json'
    document = json.loads(path.read_text(encoding='utf8'))
    for mid, (bundle, provenance) in build().items():
        entry = document['missions'].setdefault(mid, {})
        entry.setdefault('bundle', {}).update(bundle)
        entry['world_exploration_reconstruction'] = provenance
    pending = ROOT / 'build/scratch/world-encounter-write.json'
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    pending.replace(path)
    print('Restored random encounters in', len(STAGES), 'world explorations')


if __name__ == '__main__':
    main()
