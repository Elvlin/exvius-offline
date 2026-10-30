"""Map the recovered Global wiki raid rewards to the shipped Global item IDs."""
import hashlib
import json
from pathlib import Path
import re

PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT / 'logs/reference/raids/one-year-anniversary-kupo-wiki.json'
OUT = PROJECT / 'source/server/raid_rewards.json'


def names(table):
    result = {}
    for line in (PROJECT / 'data/text_decoded' / (table + '.ndjson')).open(encoding='utf-8'):
        row = json.loads(line)
        result.setdefault(row['v'][0], []).append(int(row['key'].rsplit('_', 1)[1]))
    return result


def main():
    wiki = json.loads(SOURCE.read_text(encoding='utf-8'))
    tables = {kind: names(table) for kind, table in (
        (20, 'F_TEXT_ITEM_NAME'), (22, 'F_TEXT_MATERIA_NAME'),
        (60, 'F_TEXT_RECIPE_BOOK_NAME'), (10, 'F_TEXT_UNITS_NAME'))}
    milestones = []
    for row in wiki['rows'][1:]:
        threshold = int(re.sub(r'[^0-9]', '', row[0]['text']))
        label = row[1]['text']
        match = re.search(r' \((\d+)\)$', label)
        count = int(match[1]) if match else 1
        name = label[:match.start()] if match else label
        if name.startswith('Recipe for '):
            kind, name = 60, name[len('Recipe for '):]
        elif 'Trust Moogle (ALL ' in name:
            kind = 10
            iid = {1: 904000101, 4: 904000104, 5: 904000105}[int(name[0])]
        elif re.match(r'\d-star ', name):
            kind, name = 10, re.sub(r'^\d-star ', '', name)
        elif name == 'Moogle':
            kind, iid = 10, 100008804
        elif name in ('Rare Summon Ticket', '4★+ Guaranteed Ticket'):
            kind, iid = 23, 50 if name == 'Rare Summon Ticket' else 70
        else:
            kind = 22 if row[2]['text'] == 'Ability' and name.startswith('Mog ') else 20
        if name in tables.get(kind, {}):
            ids = tables[kind][name]
            if len(ids) != 1:
                if name != 'Moogle':
                    raise ValueError('ambiguous reward: ' + name)
            else:
                iid = ids[0]
        elif name not in ('Moogle', 'Rare Summon Ticket', '4★+ Guaranteed Ticket') and 'Trust Moogle (ALL ' not in name:
            raise ValueError('unmapped reward: ' + name)
        milestones.append({'points': threshold, 'label': label,
                           'reward': {'kind': kind, 'id': iid, 'count': count}})
    assert len(milestones) == 55 and milestones[-1]['points'] == 3750000
    document = {'version': 1, 'events': [{
        'event_id': '734', 'dungeon_id': '73401', 'name': 'One Year Anniversary, Kupo!',
        'menu_background': 'raid_king_mog.png',
        'reward_banner_id': '900073401',
        'special_unlock': {'mission_id': '7340104', 'switch_id': '18334401',
                           'abilities': [501560, 501580]},
        'source_url': wiki['url'], 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'mission_points': dict(zip(map(str, range(7340101, 7340106)), [1200, 2200, 3400, 7000, 9800])),
        'raid_coin': {'kind': 20, 'id': 106301500},
        'points_per_coin': 10, 'level_bonus_percent': 16,
        'solo_pacing': {'shared_hp_per_level': 40000000, 'authored': True,
                        'basis': 'Ten full King Mog Counterattack boss HP bars per local level. Battle HP is unchanged.'},
        'personal_milestones': milestones,
        'status': 'Original personal rewards. Shared HP per level is an authored solo setting; battle HP and personal thresholds are unchanged.'
    }]}
    OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('wrote', len(milestones), 'original personal milestones:', OUT)


if __name__ == '__main__':
    main()
