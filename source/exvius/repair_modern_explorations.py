"""Restore finite counters for the original 2020 exploration definitions.

Enemy IDs, formations, combat profiles and script exclusions come from the
retained native tables and typed maps. Missing finite counts are reconstructed
explicitly. No combat statistic is estimated by this module.
"""
from collections import Counter
from urllib.parse import quote


# Explicit namespace bindings are essential: several fields do not use their
# mission ID as their original formation prefix. All these maps use zone 11.
# Each row is mission, original guide, original prefix, suffix/count pairs,
# exact regular actor IDs. Scripted boss groups are outside these lists.
STAGES = (
    ('30060102', 'Pandemonium - Exploration', '3060102',
     ((2, 3), (3, 3), (4, 3)), ('204341000', '309081000')),
    ('30420101', "Siren's Tower - Exploration", '3042010',
     tuple((i, 3) for i in range(11, 16)), ('108021043', '110001019', '112014020')),
    ('30420102', "Siren's Tower - Exploration", '3042010',
     tuple((i, 3) for i in range(21, 26)), ('108021044', '110001020', '112014021')),
    ('30420103', "Siren's Tower - Exploration", '3042010',
     tuple((i, 3) for i in range(31, 36)), ('108021045', '110001021', '112014022')),
    ('30420104', "Siren's Tower - Exploration", '3042010',
     tuple((i, 3) for i in range(41, 46)), ('108021046', '110001022', '112014023')),
    ('30420105', "Siren's Tower - Exploration", '3042010',
     tuple((i, 3) for i in range(51, 56)), ('108021047', '110001023', '112014024')),
    ('30610101', 'The Forgotten City - Exploration', '3061011',
     ((2, 3), (3, 3), (4, 3), (5, 3)),
     ('103171012', '204251011', '205971010', '301211011')),
    ('30610102', 'The Forgotten City - Exploration', '3061012',
     ((2, 3), (3, 3), (4, 3)),
     ('103171011', '204251010', '205971009', '301211010')),
    ('30700101', 'Academia -400 AF- Exploration', '3070010',
     ((12, 7), (13, 6), (14, 6), (15, 7), (16, 6)),
     ('206231001', '212181001', '212191001')),
    ('30700102', 'Academia -400 AF- Exploration', '3070010',
     ((22, 3), (23, 3), (24, 3), (25, 3)),
     ('206231000', '212181000', '212191000')),
    ('30870101', 'Lunatic Pandora - Exploration', '3087010',
     ((12, 3), (13, 3), (14, 3), (15, 3), (16, 3)),
     ('104211004', '201022104', '204192002', '301241001')),
    ('30870102', 'Lunatic Pandora - Exploration', '3087010',
     ((22, 3), (23, 3), (24, 3), (25, 3)),
     ('104211003', '201022103', '204192001', '301241000')),
    ('31080101', 'Pandæmonium - Exploration', '3108010',
     ((12, 7), (13, 6), (14, 6), (15, 7), (16, 6)),
     ('203301001', '210111001', '225201001', '225202001')),
    ('31080102', 'Pandæmonium - Exploration', '3108010',
     ((22, 3), (23, 3), (24, 3), (25, 3)),
     ('203301000', '210111000', '225201000', '225202000')),
    ('31210101', 'The Phon Coast - Exploration', '3121010',
     ((12, 7), (13, 6), (14, 6), (15, 7), (16, 6)),
     ('111021101', '202073001', '203311001')),
    ('31210102', 'The Phon Coast - Exploration', '3121010',
     ((22, 3), (23, 3), (24, 3), (25, 3)),
     ('111021100', '202073000', '203311000')),
    ('31340101', 'Memoria - Exploration', '3134010',
     ((12, 8), (13, 7), (14, 7), (15, 7)), ('204361001', '309031101')),
    ('31340102', 'Memoria - Exploration', '3134010',
     ((22, 3), (23, 3), (24, 3)), ('204361000', '309031100')),
)

PUBLISHED_APPROXIMATE_TOTALS = {
    mid: {'experience': 112600, 'gil': 933, 'ordinary_actors': 51,
          'scripted_boss_experience': 5500, 'scripted_boss_gil': 600,
          'flat_mission_gil': 180}
    for mid in ('30700101', '31080101', '31210101', '31340101')
}


def build(recovery, indexed_random_allocations):
    """Return stage-scoped native bundles without changing master data."""
    stages = {}
    original = recovery.base.load('F_BATTLE_GROUP_MST')
    for mid, title, prefix, allocations, actor_ids in STAGES:
        wanted = {prefix + str(suffix).zfill(2) for suffix, _ in allocations}
        formation = [row for row in original if row['2fY1IomW'] in wanted]
        if {row['2fY1IomW'] for row in formation} != wanted:
            raise ValueError('Missing exact original exploration formation: ' + mid)
        if any(row['WJdBp9f0'] != '1' for row in formation):
            raise ValueError('Hidden original slot cannot become a random encounter: ' + mid)
        if {row['xqartN26'] for row in formation} != set(actor_ids):
            raise ValueError('Original exploration regular roster changed: ' + mid)
        bundle = indexed_random_allocations(recovery, mid, allocations, '11', prefix)
        counts = Counter()
        quantities = {prefix + str(suffix).zfill(2): count for suffix, count in allocations}
        for row in formation:
            counts[row['xqartN26']] += quantities[row['2fY1IomW']]
        provenance = {
            'campaign': title,
            'sources': ['https://exvius.fandom.com/wiki/' + quote(title.replace(' ', '_'), safe='_-')],
            'recovered': (
                'Original 2020 mission and own encounter zone11, exact native regular '
                'formation/actor/slot identities and unchanged combat profiles, AI, skills '
                'and rewards. Original guide confirms this event regular species roster. '
                'Siren, Mage, Imp and Sorcerer scripted fights, MobileType8 probes, '
                'Garland, both Malboro fights and every other scripted boss are excluded '
                'from random allocation. Only the explicitly listed formation IDs are used.'),
            'reconstructed': (
                'Missing finite per-formation counts are authored representative runs. '
                'Where the guide publishes approximate112600EXP/933gil, the allocation '
                'contains51 original2100EXP/3gil ordinary actors; the existing5500EXP/'
                '600gil boss and180flat missiongil produce the published approximate '
                'totals. These counts are nonunique and are not recovered retail maximum '
                'quotas, draw order or rarity probabilities. Other stages use three finite '
                'occurrences per explicit original regular formation as a balanced local '
                'reconstruction. Native counters start at0 and exhaust without refill. '
                'No combat statistic is inferred or changed.'),
            'finite_random_battles': sum(count for _, count in allocations),
            'ordinary_actor_counts': dict(sorted(counts.items())),
            'combat_profile_policy': 'Retain exact existing original-version profiles; no stat estimation.',
        }
        if mid in PUBLISHED_APPROXIMATE_TOTALS:
            provenance['published_approximate_totals'] = PUBLISHED_APPROXIMATE_TOTALS[mid]
        if mid == '31080102':
            provenance['source_roster_difference'] = (
                'The wiki EASY roster omits Golem, but the original native EASY '
                'formation310801025 contains its exact400HP own actor210111000. '
                'This valid own regular formation is retained, not silently discarded '
                'because of the shorter secondary-source list.')
        stages[mid] = bundle, provenance
    return stages
