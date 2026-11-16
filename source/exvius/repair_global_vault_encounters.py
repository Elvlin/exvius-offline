"""Author stage-owned Global Vault encounters from retained guide fingerprints.

Native source profiles and capture identities are retained. Formation ownership,
equal lotteries and the allocation of documented run totals are explicitly
approved reconstructions, not recovered original server response rows.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))

from battle_content import IndexSource, derive_mission, EventSource, event_binding
from build_event_archive import rows
from restore_event_battles import ReconstructionSource


CONTRACT = ROOT / 'source/server/content/vault_encounter_sources.json'
CONTENT = ROOT / 'source/server/event_encounters.json'
SCOPE = 'global-vault-reconstruction'
TAGS = ('an6TB4WS', 'Bi6hVv34', 'wbet57nF', 'bV34YIJQ',
        'y35YvQjZ', 'Wp39QX52', 'BJ6A0KTt', '7KCkJd1E')


def _validated_contract(contract):
    if contract.get('scope') != SCOPE or contract.get('source_type') != 'documented-reconstruction':
        raise ValueError('Global Vault source contract identity changed')
    native = contract['native_source']
    if hashlib.sha256((ROOT / native['parts']).read_bytes()).hexdigest() != native['parts_sha256']:
        raise ValueError('Global Vault retained native monster-part source changed')
    return contract


def load_contract():
    return _validated_contract(json.loads(CONTRACT.read_text(encoding='utf-8')))


def _merge(fragments):
    merged = {tag: [] for tag in TAGS}
    for fragment in fragments:
        for tag in TAGS:
            for row in fragment.get(tag, []):
                if row not in merged[tag]:
                    merged[tag].append(copy.deepcopy(row))
    return merged


def _existing_ids(document, excluded):
    actors, groups = set(), set()

    def visit(value):
        if isinstance(value, dict):
            if 'xqartN26' in value:
                actors.add(str(value['xqartN26']))
            if '2fY1IomW' in value:
                groups.add(str(value['2fY1IomW']))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for mid, entry in document.get('missions', {}).items():
        if mid not in excluded:
            visit(entry)
    return actors, groups


def build(source=None, document=None, contract=None):
    """Return scoped entries and labels without writing any project file."""
    source = source or IndexSource()
    contract = load_contract() if contract is None else _validated_contract(contract)
    document = document or json.loads(CONTENT.read_text(encoding='utf-8'))
    definitions = contract['missions']
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    native_monsters = {r['xqartN26']: r for r in source.load('F_MONSTER_MST')}
    native_parts = {}
    for part in source.load('F_MONSTER_PARTS_MST'):
        native_parts.setdefault(part['xqartN26'], []).append(part)
    units = {r['3HriTp6B']: r for r in rows('F_UNIT_MST')}
    unit_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0]
                  for r in rows('F_TEXT_UNITS_NAME', text=True)}
    item_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0]
                  for r in rows('F_TEXT_ITEM_NAME', text=True)}
    item_ids = {r['tL6G9egd'] for r in rows('F_ITEM_MST')}
    blocked_actors, blocked_groups = _existing_ids(document, set(definitions))
    blocked_actors.update(native_monsters)
    blocked_groups.update(r['2fY1IomW'] for r in source.load('F_BATTLE_GROUP_MST'))
    for entry in contract['actors']:
        iid, uid = entry['source_actor'], entry['unit']
        original = native_parts[iid]
        if (len(original) != 1 or original[0]['6Yc4RkdM'] != '1'
                or original[0].get('Vf5DGw07') != '10:' + uid + ':1:100:1'
                or uid not in units or unit_names.get(uid) != entry['name']):
            raise ValueError('Vault native capturable identity changed: ' + iid)
    megacites = contract['megacites']
    tin = contract['tin']
    for item in megacites + [tin]:
        if item['id'] not in item_ids or item_names.get(item['id']) != item['name']:
            raise ValueError('Vault native item identity changed: ' + item['id'])
    output, labels = {}, {}
    for mid, definition in definitions.items():
        if not definition.get('source_records') or definition.get('mission') != mid:
            raise ValueError('Vault stage has no own guide fingerprint: ' + mid)
        mission = copy.deepcopy(missions[mid])
        expected_header = definition.get('original_mission_header', {
            '8xi6Xvyk': '2', '7UR4J2SE': '200000', 'B6H34Mea': '100', 'C2Hani5g': '0'})
        if any(mission.get(key) != value for key, value in expected_header.items()):
            raise ValueError('Vault original mission reward header changed: ' + mid)
        actor_ids = [str(1800000000 + int(mid) * 10 + i) for i in range(1, 9)]
        group_ids = [str(1900000000 + int(mid) * 10 + i) for i in range(1, 8)]
        if (any(int(i) > 2147483647 for i in actor_ids + group_ids)
                or set(actor_ids) & blocked_actors or set(group_ids) & blocked_groups):
            raise ValueError('Vault stage-owned native ID collision: ' + mid)
        blocked_actors.update(actor_ids)
        blocked_groups.update(group_ids)
        owned_monsters, owned_parts = [], []
        for number, entry in enumerate(contract['actors']):
            actor = actor_ids[number]
            monster = copy.deepcopy(native_monsters[entry['source_actor']])
            monster.update(xqartN26=actor, G4L0YIB2=entry['name'])
            part = copy.deepcopy(native_parts[entry['source_actor']][0])
            part.update(xqartN26=actor, G4L0YIB2=entry['name'])
            part['B6H34Mea'] = str(entry['served_unit_exp'])
            part['7UR4J2SE'] = str(entry['served_gil'])
            # Loot belongs to the explicit per-enemy carriers below. In
            # particular, the original KGS rare Tin must not become a third Tin.
            for channel in ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw'):
                part[channel] = ''
            owned_monsters.append(monster)
            owned_parts.append(part)
            labels[actor] = entry['name']

        def fragment(phase, option, indices):
            gid = group_ids[option]
            p = {'qo3PECw6': mid, '6v7y3QcJ': str(phase), 'gou39JeI': '2',
                 'i2ar9yXM': '0', '5LZN8C9I': '0', 'T03qgLWA': '1',
                 'YS9kfCX7': mission.get('6w4xiIsS', '400005'),
                 'DYTx1Is3': mission.get('DYTx1Is3', '100741'),
                 '6uIYE15X': gid, 'V2mCH5UR': '', 'J9gafF0t': '0',
                 'juA0Z4m7': '', '1C7GDEv4': '', 'Us0znif6': '0',
                 'k6Y8ysMA': '0', 'wTMK0x5p': '0:0:0:0'}
            slots = [{'2fY1IomW': gid, 'xqartN26': actor_ids[i],
                      'Z0EN6jSh': str(n + 1), 'MxLFKZ13': str(150 + 100 * n) + ',' + str(280 + 60 * n),
                      '3t7pZM5V': '0', 'WJdBp9f0': '1', 'm9BvFk2X': '1'}
                     for n, i in enumerate(indices)]
            view = ReconstructionSource(source, {
                'F_MISSION_PHASE_MST': [p],
                'F_BATTLE_LOTTERY_MST': [{'c2gnh6Jd': gid, '2fY1IomW': gid, 'ixDq7yJ8': '1'}],
                'F_BATTLE_GROUP_MST': slots, 'F_MONSTER_MST': owned_monsters,
                'F_MONSTER_PARTS_MST': owned_parts,
            })
            bundle = derive_mission(int(mid), view)
            template = bundle['y35YvQjZ'][0]
            rewards = []
            for slot, i in zip(slots, indices):
                row = copy.deepcopy(template)
                row.update(**{'2fY1IomW': gid, 'xqartN26': actor_ids[i],
                              'Z0EN6jSh': slot['Z0EN6jSh'], '6Yc4RkdM': '1',
                              '9BetM2Ds': '', 'MZn8LC6H': '', 'g4voc2Aw': '',
                              'Vf5DGw07': owned_parts[i]['Vf5DGw07']})
                if phase == 2:
                    row['_drop_choices'] = [
                        {'weight': 1, 'drop': '20:' + tin['id'] + ':1:100,20:' + item['id'] + ':1:100'}
                        for item in megacites]
                rewards.append(row)
            bundle['y35YvQjZ'] = rewards
            return bundle

        first = [{'group': group_ids[i], 'weight': 1,
                  'bundle': fragment(1, i, [i])} for i in range(6)]
        second = {'group': group_ids[6], 'weight': 1, 'bundle': fragment(2, 6, [6, 7])}
        canonical = _merge([first[0]['bundle'], second['bundle']])
        canonical['1IfDqR4n'] = [mission]
        metadata = {'mission': mid, 'source_type': 'documented-reconstruction',
                    'source_records': copy.deepcopy(definition['source_records']),
                    'matching_method': definition['matching_method'],
                    'original_challenge_rewards': copy.deepcopy(definition['original_challenge_rewards']),
                    'documented': copy.deepcopy(contract['documented']),
                    'reconstructed': copy.deepcopy(contract['reconstructed']),
                    'native_source': copy.deepcopy(contract['native_source'])}
        entry = {'bundle': canonical, 'identity_source': 'Own guide reward fingerprint and user-approved documented reconstruction',
                 'source_page': definition['source_records'][0]['page'],
                 'source_revision': definition['source_records'][0]['revision'],
                 'source_url': definition['source_records'][0]['url'],
                 'global_vault_reconstruction': metadata,
                 'global_vault_lottery': {'scope': SCOPE,
                    'phases': [{'phase': '1', 'candidates': first},
                               {'phase': '2', 'candidates': [second]}]}}
        previous = document.get('missions', {}).get(mid, {})
        legacy = previous.get('legacy_pending_bundle')
        if legacy is None and not previous.get('global_vault_reconstruction'):
            legacy = previous.get('bundle')
        if legacy is None and definition.get('legacy_explicit_binding'):
            binding = event_binding(mid)
            if not binding:
                raise ValueError('Original pending-compatible Vault binding missing: ' + mid)
            view = ReconstructionSource(EventSource(source, mid, binding), {'F_MISSION_MST': [mission]})
            legacy = derive_mission(int(mid), view)
        if legacy is not None:
            entry['legacy_pending_bundle'] = copy.deepcopy(legacy)
            for monster in legacy.get('wbet57nF', []):
                labels[monster['xqartN26']] = monster['G4L0YIB2']
        output[mid] = entry
    return output, labels
