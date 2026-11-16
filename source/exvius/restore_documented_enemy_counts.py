"""Restore source-proven simultaneous boss counts without multiplying totals."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/exvius'), str(ROOT / 'source/server')]
from build_event_archive import rows

STAGES = {
    '99160101': {'count': 3, 'gil': 130000, 'unit_exp': 1500000, 'drop': 800},
    '99160102': {'count': 5, 'gil': 400000, 'unit_exp': 4400000, 'drop': 1350},
}


def proposals(document):
    names = {r['v'][0]: r['key'].rsplit('_', 1)[-1] for r in rows('F_TEXT_ITEM_NAME', True)}
    insignia = names['Brave Insignia (Joined Forces)']
    result = {}
    for mid, source in STAGES.items():
        entry = deepcopy(document['missions'][mid])
        bundle = entry['bundle']
        if len(bundle['an6TB4WS']) != 1:
            raise ValueError('Own Luon Highway battle count changed')
        group = bundle['an6TB4WS'][0]['2fY1IomW']
        original_slot = next(r for r in bundle['Bi6hVv34'] if r['2fY1IomW'] == group)
        original_actor = next(r for r in bundle['wbet57nF'] if r['xqartN26'] == original_slot['xqartN26'])
        if original_actor['G4L0YIB2'] != 'Rabite':
            raise ValueError('Own Luon Highway species changed')
        original_part = next(r for r in bundle['bV34YIJQ'] if r['xqartN26'] == original_actor['xqartN26'])
        profiles, actors, slots = [], [], []
        for index in range(source['count']):
            pid = str(1889900100 + (0 if mid == '99160101' else 10) + index)
            profile = deepcopy(original_part)
            profile['xqartN26'] = pid
            for token, total in (('7UR4J2SE', source['gil']), ('B6H34Mea', source['unit_exp'])):
                share, remainder = divmod(total, source['count'])
                profile[token] = str(share + (remainder if index == source['count'] - 1 else 0))
            profiles.append(profile)
            actor = deepcopy(original_actor)
            actor['xqartN26'] = pid
            actors.append(actor)
            slot = deepcopy(original_slot)
            slot.update({'xqartN26': pid, 'Z0EN6jSh': str(index + 1),
                         'MxLFKZ13': str(170 if index % 2 == 0 else 100) + ',' + str(220 + 45 * index)})
            slots.append(slot)
        bundle.update({'Bi6hVv34': slots, 'wbet57nF': actors, 'bV34YIJQ': profiles})
        # The guide gives one stage total. Keep one existing native carrier,
        # with explicit reconstructed ownership instead of copying it per slot.
        carrier = deepcopy(bundle['y35YvQjZ'][0])
        carrier.update({'2fY1IomW': group, 'xqartN26': actors[0]['xqartN26'], 'Z0EN6jSh': '1',
                        '9BetM2Ds': '20:' + insignia + ':' + str(source['drop']) + ':100'})
        bundle['y35YvQjZ'] = [carrier]
        entry['documented_enemy_count_source'] = {
            'page': 'Business Unusual on the Luon Highway?', 'revision': 349603,
            'url': 'https://exvius.fandom.com/wiki/Business_Unusual_on_the_Luon_Highway%3F',
            'boss_field': '[[Rabite (Monster)|Rabite]] (' + str(source['count']) + ')',
            'gil_total': source['gil'], 'unit_exp_total': source['unit_exp'], 'drop_total': source['drop'],
            'documented': 'One wave containing the stated number of Rabites and the stated stage reward totals.',
            'reconstructed': 'Individual Rabite server stats were not recovered. Existing combat fields are preserved. '
                             'Per-enemy gil/EXP shares and first-carrier ownership of the stage-total insignia are explicit native projections.'}
        result[mid] = entry
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    doc = json.loads((ROOT / 'source/server/event_encounters.json').read_text(encoding='utf-8'))
    args.output.write_text(json.dumps({'missions': proposals(doc)}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Prepared two own-source Rabite count corrections')
