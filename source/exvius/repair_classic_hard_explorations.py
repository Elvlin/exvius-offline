"""Stage-owned classic Gapra and Pandemonium combat reconstructions.

Published facts override a documented numeric calibration. Original graphics,
AI, skills, animations, drops and scripted encounter identities are retained.
The later shared profiles are never edited or used as classic numeric values.
"""
import copy
import json
import math
from pathlib import Path

from battle_content import PARTS_DEFAULTS, PARTS_TOKENS
from player_state import mission_row
from repair_glaive_castle import median_profile

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'logs/ffbe-field-channel-audit-20261109.json'
CHALLENGE_CONTRACT = ROOT / 'source/server/content/battle/classic_hard_challenge_repair.json'
NUMERIC = ('fh31sk7B', 'PC97pWQj', '9NBV1XCS', 'Pn5w9dfh',
           '84FJM3PD', 'T8xMDAZ4')
STAT_NAMES = ('hp', 'mp', 'atk', 'def', 'mag', 'spr')
FIELD_NAMES = dict(zip(NUMERIC, STAT_NAMES))
FIELD_NAMES['7wV3QZ80'] = 'level'

# Source IDs remain explicit aliases. These are new actors, not replacements
# for the same IDs in the updated explorations or any other original content.
ACTORS = {
    '8540101': (
        ('209111010', '1820000001', 75, ('209111005', '209111006'), False),
        ('201341008', '1820000002', 75, ('201341003', '201341004'), False),
        ('206201009', '1820000003', 75, ('206201001', '206201002'), False),
        ('306121008', '1820000004', 75, ('306121000',), False),
        ('306141000', '1820000005', 99, (), True),
        ('401141008', '1820000006', 85, ('401141000',), True),
    ),
    '30060101': (
        ('305631000', '1820000007', 99, (), True),
        ('204341001', '1820000008', 75, (), False),
        ('309081001', '1820000009', 75, (), False),
        ('211005101', '1820000010', 99, (), True),
    ),
}
STAGES = {
    '8540101': {
        'title': 'The Gapra Whitewood - Exploration',
        'prefix': '8540101', 'local_prefix': '18200001',
        'regular_suffixes': (2, 3, 5, 6, 7, 8, 9, 10),
        'scripted': {'8540101': '854010111', '8540102': '854010101'},
        'excluded': {'854010104': 'Actor204301009 is not included in the documented classic roster; its original group remains unchanged outside this authored stage.'},
        'reference': 'logs/reference/late-exploration-wiki-20261110.json',
    },
    '30060101': {
        'title': 'Pandemonium - Exploration',
        'prefix': '3060101', 'local_prefix': '18200002',
        'regular_suffixes': (2, 3, 4, 5),
        'scripted': {'30060101': '306010101', '30060102': '306010107'},
        'excluded': {'306010106': 'Golden Bomb is not included in the documented classic roster; its original group remains unchanged outside this authored stage.'},
        'reference': 'logs/reference/modern-exploration-wiki-20261110.json',
    },
}
PUBLISHED = {
    '306141000': {'7wV3QZ80': '99', 'fh31sk7B': '9180000', 'PC97pWQj': '5000',
                  'hn42BL3Q': '0,0,0,0,0,0,-50,0,0',
                  'D9Nb7jgd': '100,100,100,100,100,100,100,100',
                  'Rcqa1Zt7': '100,0,100,0,100,100,100'},
    '305631000': {'7wV3QZ80': '99', 'fh31sk7B': '30250000', 'PC97pWQj': '5000',
                  'hn42BL3Q': '0,0,0,0,0,0,0,0,0',
                  'D9Nb7jgd': '100,100,100,100,100,100,100,100',
                  'Rcqa1Zt7': '100,0,100,0,100,100,100'},
}
PUBLISHED_SOURCES = {
    '306141000': (
        'https://exvius.fandom.com/wiki/The_Gapra_Whitewood_-_Exploration',
        'https://www.reddit.com/r/FFBraveExvius/comments/9t7gmk/',
        'https://i.imgur.com/4agbdVf.png',
    ),
    '305631000': (
        'https://exvius.fandom.com/wiki/Pandemonium_-_Exploration',
        'https://exvius.fandom.com/wiki/Garland_(Pandemonium)',
    ),
}


def _records():
    document = json.loads(AUDIT.read_text(encoding='utf8'))
    return {str(row['mission']): row for values in document.values()
            if isinstance(values, list) for row in values
            if isinstance(row, dict) and str(row.get('mission')) in STAGES}


def _numeric_profile(recovery, original, level, anchors, boss):
    own = recovery.parts[original][0]
    if not anchors:
        values, _, cohort = median_profile(recovery, own['a9qg8vnP'], level, boss)
        return {token: values[token] for token in NUMERIC}, {
            'method': 'Existing repair_glaive_castle.median_profile: same-race original single-body profiles in the nearest level band, scaled linearly to the authored level; regular HP100..500000 and boss HP1000000..8000000 cohorts. Only numeric fields are borrowed.',
            'source_profile_ids': cohort,
        }
    graphic = recovery.monsters[original]['V9j8wJcC']
    rows = []
    for iid in anchors:
        if (len(recovery.parts[iid]) != 1 or
                recovery.monsters[iid]['V9j8wJcC'] != graphic):
            raise ValueError('Classic calibration must use the exact same graphic species: ' + iid)
        rows.append(recovery.parts[iid][0])
    rows.sort(key=lambda row: int(row['7wV3QZ80']))
    if len(rows) == 2:
        low, high = rows
        lower, upper = int(low['7wV3QZ80']), int(high['7wV3QZ80'])
        if not lower <= level <= upper or lower == upper:
            raise ValueError('Classic same-species interpolation is not bounded: ' + original)
        values = {token: str(math.ceil(int(low[token]) +
                  (int(high[token]) - int(low[token])) * (level - lower) / (upper - lower)))
                  for token in NUMERIC}
        method = 'Bounded linear interpolation between preserved older same-species wave profiles at the stated levels. These are numeric calibration inputs, not claimed original exploration records.'
    else:
        anchor = rows[0]
        values = {token: str(max(1, math.ceil(int(anchor[token]) * level /
                                            int(anchor['7wV3QZ80'])))) for token in NUMERIC}
        method = 'Preserved older same-species wave numeric profile, scaled linearly by authored level / source level. An equal level retains its exact values as a reconstruction basis, not proof of the exploration values.'
    return values, {'method': method, 'source_profile_ids': list(anchors),
                    'source_levels': [int(row['7wV3QZ80']) for row in rows]}


def _actors(recovery, mid):
    monsters, parts, evidence, aliases = [], [], {}, {}
    for original, local, level, anchors, boss in ACTORS[mid]:
        if len(recovery.parts[original]) != 1:
            raise ValueError('Classic actor multipart contract changed: ' + original)
        own = recovery.parts[original][0]
        values, basis = _numeric_profile(recovery, original, level, anchors, boss)
        basis['source_table'] = 'source/server/content/battle/F_MONSTER_PARTS_MST.tsv'
        basis['source_region'] = 'Preserved Japanese battle index. These calibration values are not recovered Global exploration statistics.'
        values['7wV3QZ80'] = str(level)
        published = PUBLISHED.get(original, {})
        values.update(published)
        part = {token: own.get(token, PARTS_DEFAULTS.get(token, '')) for token in PARTS_TOKENS}
        part.update(values)
        name = recovery.names.get(original) or recovery.monsters[original]['G4L0YIB2']
        part['xqartN26'], part['G4L0YIB2'] = local, name
        monster = copy.deepcopy(recovery.monsters[original])
        monster['xqartN26'], monster['G4L0YIB2'] = local, name
        monsters.append(monster)
        parts.append(part)
        aliases[original] = local
        evidence[local] = {
            'original_actor_id': original, 'name': name,
            'graphic': monster['V9j8wJcC'], 'race': own['a9qg8vnP'],
            'original_ai': own['8a6gAwN9'], 'original_skill_set': own['A5x02C6a'],
            'published_fields': {FIELD_NAMES.get(token, token): value for token, value in published.items()},
            'published_field_sources': list(PUBLISHED_SOURCES.get(original, ())),
            'reconstructed_fields': {FIELD_NAMES[token]: values[token]
                                     for token in (*NUMERIC, '7wV3QZ80') if token not in published},
            'calibration': basis,
            'level_basis': ('Published classic exploration boss level.' if '7wV3QZ80' in published else
                            'Older own Alpha Behemoth wave level85 used explicitly as a reconstruction basis.' if original == '401141008' else
                            'Authored classic regular level75 matches intact adjacent classic HARD explorations.' if not boss else
                            'Retained own scripted monster level99; classic numeric profile is reconstructed.'),
            'preserved_non_numeric': 'Original own graphic/dictionary identity, AI, skill set, action/animation parameters, passives, resistances except documented boss overrides, capture/unit references, EXP, gil and drop fields. No foreign actor behavior is copied.',
            'fidelity_limit': 'Missing classic numeric fields are reconstructed, not recovered retail values. Nonpublished retained resistance and reward fields have not been independently recovered from a classic server response.',
        }
    return monsters, parts, evidence, aliases


def build(recovery, indexed_random_allocations, skill_dependencies):
    """Return two complete field bundles for the existing authoring generator."""
    audit = _records()
    groups = recovery.base.load('F_BATTLE_GROUP_MST')
    carrier = json.loads((ROOT / 'source/server/responses.json').read_text(encoding='utf8'))['29JRaDbd']
    challenge_contract = json.loads(CHALLENGE_CONTRACT.read_text(encoding='utf8'))
    local_ids = {local for actors in ACTORS.values() for _, local, *_ in actors}
    local_groups = {stage['local_prefix'] + str(suffix).zfill(2)
                    for stage in STAGES.values() for suffix in stage['regular_suffixes']}
    if local_ids.intersection(recovery.monsters) or local_ids.intersection(recovery.parts):
        raise ValueError('Classic local actor namespace collides with original data.')
    if local_groups.intersection(row['2fY1IomW'] for row in groups):
        raise ValueError('Classic local group namespace collides with original data.')
    output = {}
    for mid, stage in STAGES.items():
        record = audit[mid]
        fields = record.get('own_external_positive_fields', {})
        mission = mission_row(mid)
        roots = {row['scenario'] for row in record['script_scenarios']
                 if row.get('own_event_member') and not row.get('conditional_resource')}
        expected = {(sid, gid) for sid, gid in stage['scripted'].items()}
        actual = {(row['scenario'], gid) for row in record['script_scenarios']
                  if row.get('own_event_member') and not row.get('conditional_resource')
                  for gid in row.get('groups', [])}
        if set(fields) != {'11'} or not mission or mission['B6kyCQ9M'] != '20' or actual != expected:
            raise ValueError('Classic field, script or version ownership changed: ' + mid)
        monsters, parts, actors, aliases = _actors(recovery, mid)
        challenge_dependencies = {'300601012': {
            'condition': '77:306010101:15',
            'policy': 'Unchanged: the original scripted group identity is retained.'}}
        if mid == '8540101':
            original = challenge_contract['original']
            condition = original['Pzn5h0Ga'].split(':')
            if (challenge_contract['table'] != 'F_CHALLENGE_MST'
                    or challenge_contract['mission_id'] != mid
                    or original['qo3PECw6'] != mid
                    or original['V36ygRYs'] != '85401017'
                    or len(condition) != 4 or condition[1] not in stage['scripted'].values()
                    or condition[2] not in aliases):
                raise ValueError('Classic challenge contract does not match its scoped encounter')
            replacement = ':'.join((condition[0], condition[1], aliases[condition[2]], condition[3]))
            if challenge_contract['rows'] != [{'qo3PECw6': mid, 'V36ygRYs': original['V36ygRYs'],
                                               'Pzn5h0Ga': replacement}]:
                raise ValueError('Classic challenge target differs from the served local actor')
            challenge_dependencies = {original['V36ygRYs']: {
                'table': challenge_contract['table'], 'field': 'Pzn5h0Ga',
                'original': original['Pzn5h0Ga'], 'replacement': replacement,
                'contract': CHALLENGE_CONTRACT.relative_to(ROOT).as_posix(),
                'delivery': 'Scoped original challenge master and matching native index; preserve the original condition, reward and challenge identity.'}}
        regular = {stage['prefix'] + str(suffix).zfill(2):
                   stage['local_prefix'] + str(suffix).zfill(2)
                   for suffix in stage['regular_suffixes']}
        scripted = set(stage['scripted'].values())
        if scripted.intersection(regular):
            raise ValueError('A scripted boss entered a classic random pool: ' + mid)
        formation = [copy.deepcopy(row) for row in groups
                     if row['2fY1IomW'] in set(regular) | scripted]
        if {row['2fY1IomW'] for row in formation} != set(regular) | scripted:
            raise ValueError('A classic source formation is missing: ' + mid)
        if {row['xqartN26'] for row in formation} != set(aliases):
            raise ValueError('Classic formation species roster changed: ' + mid)
        for row in formation:
            row['xqartN26'] = aliases[row['xqartN26']]
            row['2fY1IomW'] = regular.get(row['2fY1IomW'], row['2fY1IomW'])
        bundle = indexed_random_allocations(recovery, mid,
            tuple((suffix, 1) for suffix in stage['regular_suffixes']), '11', stage['prefix'])
        for row in bundle['6v0LPiRe']:
            row['xqartN26'] = aliases[row['xqartN26']]
            row['2fY1IomW'] = regular[row['2fY1IomW']]
        bundle.update({'Bi6hVv34': formation, 'wbet57nF': monsters, 'bV34YIJQ': parts,
                       'rqxw0p9k': [copy.deepcopy(row) for row in carrier['rqxw0p9k']
                                    if row['ja07xgLF'] in roots],
                       'YjHhvN65': [copy.deepcopy(row) for row in carrier['YjHhvN65']
                                    if (row['ja07xgLF'], row['2fY1IomW']) in expected],
                       'JR7jZci2': []})
        by_actor = {row['xqartN26']: row for row in parts}
        for sid, gid in stage['scripted'].items():
            for row in formation:
                if row['2fY1IomW'] != gid or row['WJdBp9f0'] != '1':
                    continue
                part = by_actor[row['xqartN26']]
                reward = next((r for r in carrier.get('JR7jZci2', [])
                               if r['ja07xgLF'] == sid and r['2fY1IomW'] == gid
                               and aliases.get(r['xqartN26']) == row['xqartN26']), None)
                copied = copy.deepcopy(reward) if reward else {
                    'ja07xgLF': sid, '2fY1IomW': gid, 'Z0EN6jSh': row['Z0EN6jSh'],
                    '6Yc4RkdM': part['6Yc4RkdM'], '9BetM2Ds': part.get('9BetM2Ds', ''),
                    'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': ''}
                copied['xqartN26'] = row['xqartN26']
                bundle['JR7jZci2'].append(copied)
        skill_dependencies(recovery, bundle)
        output[mid] = bundle, {
            'campaign': stage['title'], 'classic_reconstruction': True,
            'sources': ['https://exvius.fandom.com/wiki/' + stage['title'].replace(' ', '_')],
            'reference': stage['reference'],
            'typed_source': {'audit': AUDIT.relative_to(ROOT).as_posix(),
                             'resources': record['base_resources'], 'field': '11',
                             'sources': fields['11']['sources']},
            'actors': actors, 'original_to_local_actor_ids': aliases,
            'original_to_local_regular_group_ids': regular,
            'scripted_scenario_groups': stage['scripted'],
            'regular_groups_outside_documented_roster': stage['excluded'],
            'recovered': 'Published classic boss HP/MP/level and resistances, own original script/scenario/background/group links, matching regular formation layouts, actor graphics/dictionary identity, own AI and skill sets. Scripted groups remain outside random allocations; updated shared profiles and their actors remain unchanged.',
            'reconstructed': 'Classic missing numeric values use preserved older same-species wave inputs or the established same-race/level median calibration. These are authored playable reconstructions, not recovered original server rows. New local actors and regular groups isolate these values from later updated content. Each explicitly retained own regular formation has one finite occurrence, not a claimed retail quota, draw order or rarity distribution.',
            'allocation_policy': {'occurrences_per_authored_group': 1,
                                  'random_battles': len(regular), 'retail_quota_recovered': False,
                                  'refill': False},
            'challenge_dependencies': challenge_dependencies,
            'loot': 'Retain own actor EXP/gil/capture/drop fields and exact existing scripted reward rows. No entry award, mission-wide boss grant, bonus roll probability or repeated counter refill is introduced.',
        }
    return output
