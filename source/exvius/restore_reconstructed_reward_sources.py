"""Restore explicitly source-verified rewards on their actual enemy carriers.

This returns scoped encounter edits to the single content-data writer. It does
not modify profiles, first-clear/challenge rewards or unverified campaigns.
"""
import copy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/exvius'), str(ROOT / 'source/server')]


def build(document=None):
    from build_event_archive import rows
    from reconstruct_event_battles import key, linked_enemies
    from repair_additional_global_combat import source_reader
    definitions = json.loads((ROOT / 'source/server/content/reconstructed_reward_sources.json')
                             .read_text(encoding='utf8'))['fixed_single_enemy_drops']
    document = document or json.loads((ROOT / 'source/server/event_encounters.json').read_text(encoding='utf8'))
    reader = source_reader()
    items = {r['tL6G9egd'] for r in rows('F_ITEM_MST')}
    names = {r['v'][0]: r['key'].rsplit('_', 1)[-1]
             for r in rows('F_TEXT_ITEM_NAME', True)}
    output = {}
    for mid, contract in definitions.items():
        if names.get(contract['item']) != contract['item_id'] or contract['item_id'] not in items:
            raise ValueError('Own original reward identity differs: ' + mid)
        records = [r for r in reader.records(contract['source_page'])
                   if r['heading'] == contract['source_heading']]
        if len(records) != 1:
            raise ValueError('Own original reward stage is ambiguous: ' + mid)
        record = records[0]
        expected_macro = '{{Currency|' + contract['item'] + '|' + str(contract['quantity']) + '}}'
        if re.sub(r'\s+', '', record['fields'].get('drop', '')) != re.sub(r'\s+', '', expected_macro):
            raise ValueError('Own fixed published reward amount differs: ' + mid)
        if record['fields'].get('boss') != '[[' + contract['enemy'] + ']]':
            raise ValueError('Own published enemy count/identity differs: ' + mid)
        entry = copy.deepcopy(document['missions'][mid])
        bundle = entry['bundle']
        phases = [p for p in bundle.get('an6TB4WS', []) if p.get('gou39JeI') == '2']
        if len(phases) != 1:
            raise ValueError('Own fixed reward must have one actual wave: ' + mid)
        group = phases[0]['2fY1IomW']
        slots = [s for s in bundle.get('Bi6hVv34', [])
                 if s['2fY1IomW'] == group and s.get('WJdBp9f0') == '1']
        if len(slots) != 1:
            raise ValueError('Own fixed reward has an unverified enemy count: ' + mid)
        slot = slots[0]
        monster = next(r for r in bundle['wbet57nF'] if r['xqartN26'] == slot['xqartN26'])
        if key(monster['G4L0YIB2']) != key(contract['enemy']):
            raise ValueError('Own fixed reward is bound to another enemy: ' + mid)
        body = next(r for r in bundle['bV34YIJQ']
                    if r['xqartN26'] == slot['xqartN26'] and r['6Yc4RkdM'] == '1')
        carriers = bundle.setdefault('y35YvQjZ', [])
        owned = [r for r in carriers if r.get('xqartN26') == body['xqartN26']
                 and r.get('6Yc4RkdM') == '1']
        if len(owned) > 1:
            raise ValueError('Duplicate own body reward carriers: ' + mid)
        if owned:
            carrier = owned[0]
        else:
            carrier = {'qo3PECw6': mid, 'pIHCrf40': '1',
                       **{k: '' for k in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07',
                                         '3frn4ILX', 'IRf10dwx', 'ATM35pjf', 'e5xoiC84')}}
            carriers.append(carrier)
        drop = '20:' + contract['item_id'] + ':' + str(contract['quantity']) + ':100'
        if carrier.get('9BetM2Ds', '') not in ('', drop) or carrier.get('_drop_choices'):
            raise ValueError('Own normal reward already conflicts with primary source: ' + mid)
        carrier.update({'6v7y3QcJ': phases[0]['6v7y3QcJ'], '2fY1IomW': group,
                        'xqartN26': body['xqartN26'], 'Z0EN6jSh': slot['Z0EN6jSh'],
                        '6Yc4RkdM': '1', '9BetM2Ds': drop})
        entry['source_verified_reward'] = {
            **contract, 'source_field': 'Own Battle Infobox drop, separate from clear-bonus and challenges.',
            'native_drop': drop,
            'projection': 'Published fixed per-clear quantity on the only own enemy body. '
                'The original server wire tuple is not retained; no random distribution '
                'or cross-enemy ownership is introduced.'}
        output[mid] = entry
    return output, {}
