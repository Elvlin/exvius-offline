"""Bounded allocations for nine updated explorations, retaining native profiles."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'logs/ffbe-field-channel-audit-20261109.json'

# Explicit native namespaces, regular group suffixes and owned active zones.
# The namespace differences are source bindings, not actor substitutions.
PLANS = (
    ('31770101', 'Mystic Den HARD', '3177010', (10, 11, 12, 13), ('12',)),
    ('32380101', "Patron's Palace", '323801', (1, 2, 3, 4), ('12',)),
    ('42340101', "Dark Mage's Castle", '4234010', (11, 12, 13, 14, 15, 16), ('11',)),
    ('61520101', "Isaaru's Aeons", '6152010', (11, 12, 13, 14, 15), ('12',)),
    ('62630101', 'Pandemonium updated exploration', '3060101', (2, 3, 4, 5, 6), ('13',)),
    ('62750101', 'Gapra Whitewood updated exploration', '8540101', (2, 3, 4, 5, 6, 7, 8, 9, 10), ('13',)),
    ('62850101', 'The Crystal Tower updated EASY', '6285010', (11, 12, 13, 14, 15, 16), ('10',)),
    ('62850102', 'The Crystal Tower updated HARD', '6285010', (21, 22, 23, 24, 25, 26), ('10', '70', '71', '72')),
    ('62850103', 'The Crystal Tower updated EX', '6285010', (31, 32, 33, 34, 35, 36), ('10', '73', '74', '75')),
)

SCRIPTED = {
    '31770101': ('317701014',),
    '32380101': ('32380100',),
    '42340101': ('423401017',),
    '61520101': ('615201016', '615201017', '615201018'),
    '62630101': ('306010101', '306010107'),
    '62750101': ('854010101', '854010111'),
    '62850101': ('628501017',),
    '62850102': ('628501020', '628501027', '628501028', '628501029'),
    '62850103': ('628501030', '628501037', '628501038', '628501039'),
}

# Actor tuples are in ascending original slot order. Every selected group is
# explicitly named and contains only its original visible actors.
FORMATIONS = {
    '317701010': ('207007006', '107008009'),
    '317701011': ('107008009', '107008009'),
    '317701012': ('107008009',),
    '317701013': ('207007006', '207048002'),
    '32380101': ('206271002', '206271002'),
    '32380102': ('106121003', '106121003'),
    '32380103': ('101172002', '101172002'),
    '32380104': ('206271002', '106121003', '101172002'),
    '423401011': ('207111010',),
    '423401012': ('307102010',),
    '423401013': ('307161009',),
    '423401014': ('225021001', '201351011', '225021001'),
    '423401015': ('201351011', '201351011', '201351011'),
    '423401016': ('201351011', '201351011', '225021001', '225021001'),
    '615201011': ('203351002',),
    '615201012': ('203391000',),
    '615201013': ('203351002', '203391000'),
    '615201014': ('203351002', '203351002', '203351002'),
    '615201015': ('203391000', '203391000', '203391000'),
    '306010102': ('204341001', '204341001', '204341001'),
    '306010103': ('204341001', '309081001'),
    '306010104': ('204341001', '204341001'),
    '306010105': ('204341001',),
    '306010106': ('104028049',),
    '854010102': ('209111010', '209111010', '209111010'),
    '854010103': ('201341008', '201341008', '201341008'),
    '854010104': ('204301009', '204301009'),
    '854010105': ('206201009', '206201009'),
    '854010106': ('306121008',),
    '854010107': ('209111010', '201341008', '201341008'),
    '854010108': ('201341008', '206201009'),
    '854010109': ('209111010', '209111010', '201341008', '201341008'),
    '854010110': ('206201009', '306121008', '209111010'),
}

CRYSTAL_PROFILES = (
    ('62850101', ('105063011', '312021012', '205231013', '205221014', '204034115')),
    ('62850102', ('105063012', '312021013', '205231014', '205221015', '204034116')),
    ('62850103', ('105063013', '312021014', '205231015', '205221016', '204034117')),
)
for _mission, (_kum, _platinal, _azer, _general, _gomory) in CRYSTAL_PROFILES:
    FORMATIONS.update({
        _mission + '1': (_kum, _kum, _kum),
        _mission + '2': (_platinal, _kum),
        _mission + '3': (_azer, _kum),
        _mission + '4': (_azer, _azer),
        _mission + '5': (_general, _kum),
        _mission + '6': (_gomory, _gomory),
    })


def restore_crystal_loot(bundle, source, mission):
    """Project exact own-tier native drop pools onto their encounter carriers."""
    actors = dict(CRYSTAL_PROFILES).get(str(mission))
    if actors is None:
        raise ValueError('Not an owned updated Crystal Tower tier: ' + str(mission))
    original = {(r['xqartN26'], r['6Yc4RkdM']): r
                for r in source.load('F_MONSTER_PARTS_MST') if r['xqartN26'] in actors}
    pools = {}
    for row in bundle['6v0LPiRe']:
        identity = (row['xqartN26'], row['6Yc4RkdM'])
        if identity not in original:
            raise ValueError('Updated Crystal Tower loot actor changed: ' + str(identity))
        value = original[identity].get('9BetM2Ds', '')
        row['9BetM2Ds'] = value
        pools[':'.join(identity)] = value
    return {
        'source': 'Retained native Japanese F_MONSTER_PARTS_MST battle index, '
                  'exact updated Crystal Tower tier actor IDs and part numbers.',
        'actor_pools': pools,
        'recovered': 'Original Onion Seed235053600 quantities and rates copied '
                     'unchanged into each own-actor 6v0LPiRe occurrence. '
                     'No shared generic materials or other tier actor is substituted.',
        'regional_limit': 'Preserved Japanese records for these updated native actors; '
                          'not a claim of recovered original Global server allocations.',
    }


def build(recovery, indexed_random_allocations):
    """Return source-only bundles for one integration into the shared generator."""
    audit = {row['mission']: row for row in json.loads(AUDIT.read_text(encoding='utf-8'))['missions']}
    original = {}
    for row in recovery.base.load('F_BATTLE_GROUP_MST'):
        original.setdefault(row['2fY1IomW'], []).append(row)
    stages = {}
    for mid, campaign, namespace, suffixes, fields in PLANS:
        own = audit[mid]['own_external_positive_fields']
        if any(field not in own for field in fields):
            raise ValueError('Updated exploration lost its original owned zone: ' + mid)
        typed_groups = {gid for script in audit[mid]['script_scenarios']
                        if script.get('own_event_member') for gid in script.get('groups', [])}
        if typed_groups != set(SCRIPTED[mid]):
            raise ValueError('Updated exploration scripted ownership changed: ' + mid)
        visible_actors = 0
        identities, records = set(), []
        for suffix in suffixes:
            gid = namespace + str(suffix).zfill(2)
            if gid in typed_groups:
                raise ValueError('Scripted boss or dragon entered random allocations: ' + gid)
            formation = sorted(original.get(gid, []), key=lambda row: int(row['Z0EN6jSh']))
            if (tuple(row['xqartN26'] for row in formation) != FORMATIONS[gid]
                    or any(row['WJdBp9f0'] != '1' for row in formation)):
                raise ValueError('Updated original regular formation changed: ' + gid)
            for row in formation:
                iid = row['xqartN26']
                if not recovery.parts.get(iid) or iid not in recovery.monsters:
                    raise ValueError('Missing updated own actor profile: ' + iid)
                identities.add(iid)
            visible_actors += len(formation)
            records.append({'group': gid, 'occurrences_per_zone': 1, 'actors': list(FORMATIONS[gid])})
        # Each occurrence count is an explicit bounded reconstruction. Serialize
        # the dependency graph once; additional owned zones need counter rows,
        # not duplicate monster/group/skill definitions in the same response.
        allocations = tuple((suffix, 1) for suffix in suffixes)
        bundle = indexed_random_allocations(recovery, mid, allocations, fields[0], namespace)
        first_zone = list(bundle['6v0LPiRe'])
        for field in fields[1:]:
            bundle['6v0LPiRe'].extend(dict(row, YzGa63QM=field) for row in first_zone)
        provenance = {
            'campaign': campaign,
            'sources': ['logs/ffbe-field-channel-audit-20261109.json',
                        'Original GL 9.0.0 F_BATTLE_GROUP_MST and F_MONSTER_PARTS_MST'],
            'recovered': ('Exact native updated-stage mission/field/resource ownership and explicit regular '
                          'group identities, visible actor slots and all current native combat profiles. '
                          'The typed original scripts identify the excluded boss and dragon groups.'),
            'reconstructed': ('One finite occurrence of each explicitly named original regular formation '
                              'per owned active zone. These are authored minimal complete formation budgets, '
                              'not recovered retail maximum quotas, draw order, rarity or loot probabilities. '
                              'Original counters start at zero and exhaust. No foreign actor, automatic '
                              'numeric-prefix pool, old combat profile or stat scaling is introduced.'),
            'native_group_namespace': namespace,
            'native_formations': records,
            'scripted_groups_excluded': list(SCRIPTED[mid]),
            'own_zones': {
                field: {'maps': sorted({source['map'] for source in own[field]['sources']}),
                        'resources': sorted({source['resource'] for source in own[field]['sources']}),
                        'members': sorted({source['member'] for source in own[field]['sources']})}
                for field in fields
            },
            'finite_budget': {'random_fights_per_zone': len(suffixes),
                              'random_actors_per_zone': visible_actors,
                              'zone_count': len(fields),
                              'total_random_fights': len(suffixes) * len(fields)},
            'preserved_actor_ids': sorted(identities, key=int),
            'combat': ('The original current HP, MP, ATK/DEF/MAG/SPR, resists, AI, skill sets, '
                       'skills, reward definitions and capture contracts are unchanged. '
                       'No reconstructed early-event stats are applied to these updated stages.'),
        }
        if mid in ('62630101', '62750101'):
            provenance['version_binding'] = (
                'The updated owned resource explicitly references this retained native group namespace. '
                'These are the current native profiles, including hundreds of millions of regular HP; '
                'the stage-specific historical boss alias handling remains on its separate script path. '
                'No legacy exploration profile is copied over an updated actor.')
        if mid in ('62850102', '62850103'):
            provenance['zone_distribution'] = (
                'The retained planes prove field 10 plus three additional floor-specific positive zones. '
                'No original ordinary-monster allocation by floor survives. Sharing only this exact '
                'updated tier\'s six original regular formations across its four zones is an explicit '
                'distribution reconstruction. Each field has independent finite group counters. '
                'Typed Red/Yellow/Green Dragon encounters and Xande stay script-triggered and never '
                'enter these pools. No assumption of zero random encounters on field 10 is made.')
        if mid in dict(CRYSTAL_PROFILES):
            provenance['item_drops'] = restore_crystal_loot(bundle, recovery.base, mid)
        stages[mid] = (bundle, provenance)
    return stages
