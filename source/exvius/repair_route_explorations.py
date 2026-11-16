"""Finite own-formation reconstructions for the three retained exploration routes.

This source helper does not write shared encounter data. Original formations,
actors, slots and combat profiles stay intact. Missing occurrence counts are
explicit reconstructions, not recovered retail maximum encounter quotas.
"""
import copy
import json
from pathlib import Path

from battle_content import PARTS_DEFAULTS, PARTS_TOKENS


STAGES = (
    ('7840101', 'Latius Woods - Past',
     ((2, 2), (3, 2), (4, 2), (5, 1), (6, 1), (7, 2), (8, 1), (9, 1), (10, 1)),
     ('311001014',), {'experience': 79000, 'gil': 8480, 'rank_experience': 820},
     'https://www.youtube.com/watch?v=r0oraxlwH7A&t=630s', 630.4),
    ('7840102', 'Latius Woods - Past', ((2, 1), (3, 1), (4, 1)),
     ('311001013',), None, None, None),
    ('7900101', 'Dollet - Exploration', ((2, 1), (3, 1), (4, 1), (5, 1), (8, 1), (9, 1), (10, 1)),
     ('506002001', '506002002'), {'experience': 30400, 'gil': 3460, 'rank_experience': 820},
     'https://www.youtube.com/watch?v=iNU3cZZtvV4&t=955s', 955),
    ('7900102', 'Dollet - Exploration', ((2, 1), (3, 1), (4, 1)),
     ('506002000',), None, None, None),
    ('8050101', "Gaea's Cliff - Exploration", tuple((suffix, 1) for suffix in range(2, 12)),
     ('407211001',), {'experience': 45400, 'gil': 4960, 'rank_experience': 820},
     'https://www.youtube.com/watch?v=azkl1WjhVKk&t=977s', 977.5),
    ('8050102', "Gaea's Cliff - Exploration", ((2, 1), (3, 1), (4, 1)),
     ('407211000',), None, None, None),
)

# Exact native group membership, in ascending original slot order. This is an
# explicit identity list, never a selection of every group sharing a prefix.
FORMATIONS = {
    '7840101': {
        2: ('101006008',) * 3, 3: ('101027001',) * 3,
        4: ('102015010',) * 2, 5: ('109014004',) * 2,
        6: ('204093001',) * 2, 7: ('109034001',) * 3,
        8: ('101006008', '101027001'), 9: ('101027001',) * 4,
        10: ('101006008', '101006008', '109014004'),
    },
    '7840102': {2: ('101006007',), 3: ('101027000',) * 2,
                4: ('101006007', '101027000', '101027000', '101006007')},
    '7900101': {
        2: ('205861008',) * 3, 3: ('205871006',) * 3,
        4: ('201191004',) * 2, 5: ('201201003',) * 2,
        8: ('205861008', '205871006'),
        9: ('205861008', '205861008', '205871006', '205871006'),
        10: ('205861008', '205861008', '201201003'),
    },
    '7900102': {2: ('205861007',), 3: ('205871005',) * 2,
                4: ('205861007', '205871005', '205871005', '205861007')},
    '8050101': {
        2: ('102081008',) * 3, 3: ('209091006',) * 3,
        4: ('201211004',) * 2, 5: ('201221003',) * 2,
        6: ('201211004', '309031001'),
        7: ('201211004', '209091006', '201221003'),
        8: ('102081008', '209091006'),
        9: ('102081008', '102081008', '209091006', '209091006'),
        10: ('102081008', '102081008', '201221003'), 11: ('307091002',),
    },
    '8050102': {2: ('102081007',), 3: ('209091005',) * 2,
                4: ('102081007', '209091005', '209091005', '102081007')},
}


def build(recovery, indexed_random_allocations):
    """Return six bundles using the shared native allocation serializer."""
    groups = {}
    for row in recovery.base.load('F_BATTLE_GROUP_MST'):
        groups.setdefault(row['2fY1IomW'], []).append(row)
    result = {}
    for mid, campaign, allocations, bosses, observed, video, seconds in STAGES:
        actors, experience, gil, formation_records = 0, 0, 0, []
        for suffix, count in allocations:
            gid = mid + str(suffix).zfill(2)
            source = sorted(groups.get(gid, []), key=lambda row: int(row['Z0EN6jSh']))
            if (tuple(row['xqartN26'] for row in source) != FORMATIONS[mid][suffix]
                    or any(row['WJdBp9f0'] != '1' for row in source)):
                raise ValueError('Original exploration formation changed: ' + gid)
            if any(row['xqartN26'] in bosses for row in source):
                raise ValueError('Scripted exploration boss entered random allocations: ' + gid)
            for row in source:
                parts = recovery.parts[row['xqartN26']]
                if len(parts) != 1:
                    raise ValueError('Original regular actor gained extra parts: ' + row['xqartN26'])
                part = parts[0]
                actors += count
                experience += count * int(part['B6H34Mea'])
                gil += count * int(part['7UR4J2SE'])
            formation_records.append({'group': gid, 'occurrences': count,
                                      'actors': list(FORMATIONS[mid][suffix])})
        provenance = {
            'campaign': campaign,
            'sources': ['https://exvius.fandom.com/wiki/' + campaign.replace(' ', '_')],
            'recovered': ('Original own encounter zone 11, exact explicitly listed formations and visible slots, '
                          'actor identities, tier-specific statistics, AI, skills and rewards. '
                          'Own map and external-plane ownership are retained in the typed field channel audit. '
                          'Boss and hidden summon slots are not random encounters.'),
            'reconstructed': ('Finite per-formation occurrence counts are authored below. They are not recovered '
                              'retail quotas, random draw order or loot probabilities. Counters start at zero '
                              'and exhaust without refill. No foreign actor, level scaling or generic prefix '
                              'pool is used. Original scripted encounters remain separate.'),
            'native_formations': formation_records,
            'finite_budget': {'random_fights': sum(count for _, count in allocations),
                              'random_actors': actors, 'random_experience': experience, 'random_gil': gil},
            'retained_combat': 'No monster, parts, AI, skill, resistance, formation or boss rows are altered.',
        }
        if observed:
            provenance['sources'].append(video)
            provenance['observed_route'] = dict(observed, video=video, seconds=seconds,
                muted_verified=True, encounter_exhaustion_demonstrated=False)
        if mid == '7840101':
            if actors != 35 or experience != 73500 or gil != 7700:
                raise ValueError('Latius original reward calibration changed')
            provenance['budget_derivation'] = (
                'Recorded HARD route at 630.4s gives 79000 EXP and 8480 gil. Own Ochu gives 5500 EXP/600 gil; '
                'Microchu gives zero, including hidden summoned copies. The observed regular actor budget is '
                '(79000-5500)/2100=35. Gil independently gives 8480-600-35*220=180 remaining flat mission gil. '
                'The selected 13 original regular formations total exactly 35 actors. Each original eligible '
                'formation appears once or twice. The particular per-species distribution and occurrence '
                'counts are nonunique inferred values, not recovered retail allocation records. '
                'The source visibly shows the original three-Wild-Rat formation at 250s. '
                'Original actor 102015010 is localized Fledgling Rudra; the guide labels its species Fledgling Rukh.')
        elif mid == '8050101':
            provenance['budget_derivation'] = (
                'Recorded HARD route at 977.5s gives 45400 EXP and 4960 gil. Own Schizo gives 5500 EXP/600 gil. '
                'The observed route therefore contains 19 ordinary 2100-EXP/220-gil actors and no 2200-EXP '
                'Blue Dragon, leaving 180 flat mission gil. This does not demonstrate exhausted encounters. '
                'One occurrence of each of the nine explicit ordinary formations plus the original Blue Dragon '
                'formation is the bounded reconstruction: 10 random fights, 24 ordinary actors and one Blue '
                'Dragon. The guide positively lists Blue Dragon as a regular monster. Its single occurrence '
                'is inferred coverage, not a recovered rarity or a reward added to the recorded route.')
        elif mid == '7900101':
            provenance['budget_derivation'] = (
                'Recorded HARD route at 955s gives 30400 EXP and 3460 gil. The four original scripted '
                'X-ATM092 ambushes each give5500EXP/600gil. Thus30400-4*5500=8400EXP, or four ordinary '
                '2100-EXP actors. Gil independently gives3460-4*600-4*220=180flat missiongil. '
                'This observed run does not demonstrate encounter exhaustion. The finite own-roster '
                'reconstruction uses each of the seven explicit '
                'guide-matched native regular formations once: 7 random fights and 19 actors. '
                'Original groups 790010106/107 contain Biggs 205872002, absent from the published regular '
                'roster; their random-channel ownership is unconfirmed. They are retained unchanged and '
                'are not declared unused. Both original X-ATM092 groups 790010101/111 remain excluded from '
                'random allocations. Original mission 7900101 is named Dollet Exploration HARD, dungeon '
                '79001, energy 20, rank EXP 820 and flat gil 180; EASY 7900102 costs 3 energy and gives '
                'rank EXP 50/flat gil 20. These original values match the 2018 recorded stage selection. '
                'The current typed event resource references scenarios42920101..4. The separate scoped '
                'script restoration below binds its first three ambushes and final boss to the two '
                'exact original2018 X-ATM092 profiles, preserving the documented four-fight order.')
        else:
            provenance['budget_derivation'] = (
                'No EASY quota or complete-run reward total was recovered. Each of this exact EASY stage\'s '
                'three explicit native regular formations occurs once, yielding 3 finite fights and 7 actors. '
                'This is a minimal complete own-formation reconstruction, not a HARD count copied into EASY. '
                'The original EASY actors retain their own 30 EXP/3 gil profiles and original combat stats; '
                'the boss remains on its existing scripted path.')
        result[mid] = (indexed_random_allocations(recovery, mid, allocations, '11'), provenance)
    restore_dollet_graph(recovery, result['7900101'])
    return result


def restore_dollet_graph(recovery, entry):
    """Bind the reused field calls to the matching 2018 X-ATM092 phases."""
    bundle, provenance = entry
    root = Path(__file__).resolve().parents[2]
    carrier = json.loads((root / 'source/server/responses.json').read_text(encoding='utf8'))['29JRaDbd']
    masters = {r['ja07xgLF']: r for r in carrier['rqxw0p9k']}
    links = {r['ja07xgLF']: r for r in carrier['YjHhvN65']}
    bindings = {'42920101': '7900102', '42920102': '7900102',
                '42920103': '7900102', '42920104': '7900101'}
    bundle['rqxw0p9k'], bundle['YjHhvN65'], bundle['JR7jZci2'] = [], [], []
    groups = set()
    for called, old in bindings.items():
        master, link = copy.deepcopy(masters[old]), copy.deepcopy(links[old])
        master['ja07xgLF'] = link['ja07xgLF'] = called
        bundle['rqxw0p9k'].append(master)
        bundle['YjHhvN65'].append(link)
        groups.add(link['2fY1IomW'])
        for formation in recovery.source_groups[link['2fY1IomW']]:
            for part in recovery.parts[formation['xqartN26']]:
                bundle['JR7jZci2'].append({'ja07xgLF': called,
                    '2fY1IomW': link['2fY1IomW'], 'xqartN26': formation['xqartN26'],
                    'Z0EN6jSh': formation['Z0EN6jSh'], '6Yc4RkdM': part['6Yc4RkdM'],
                    '9BetM2Ds': part.get('9BetM2Ds',''), 'MZn8LC6H': '',
                    'g4voc2Aw': '', 'Vf5DGw07': ''})
    bundle['Bi6hVv34'] = [copy.deepcopy(r) for gid in sorted(groups)
                            for r in recovery.source_groups[gid]]
    actors = {r['xqartN26'] for r in bundle['Bi6hVv34']}
    bundle['wbet57nF'] = [copy.deepcopy(recovery.monsters[i]) for i in sorted(actors)]
    bundle['bV34YIJQ'] = [{t: p.get(t, PARTS_DEFAULTS.get(t,'')) for t in PARTS_TOKENS}
                           for i in sorted(actors) for p in recovery.parts[i]]
    sets = {p['A5x02C6a'] for p in bundle['bV34YIJQ']} - {'', '0'}
    native_sets = {r['A5x02C6a']: r for r in recovery.base.load('F_MONSTER_SKILL_SET_MST')}
    skills = set()
    for sid in sets:
        if sid in recovery.global_sets:
            recovery.recover_skills(sid)
        skills.update((recovery.global_sets.get(sid) or native_sets[sid])['7qxLC5hP'].split(','))
    bundle['Wp39QX52'] = [recovery.skill_rows[i] for i in sorted(skills - {''}, key=int)]
    provenance['scoped_script_restoration'] = {
        'typed_source': 'Own resource397900101/member79001010101_event.bin calls '
            '42920101/02/03 in maps2/4/7 and42920104 in map8. These calls are '
            'retained unchanged; only this original2018 mission response is corrected.',
        'native_scenario_bindings': bindings,
        'recovered': 'The old guide explicitly documents four X-ATM092 ambushes, '
            'with the limit-burst challenge applying only to the fourth. First three '
            'calls use original group790010111, exact506002002 at1.2MHP/three actions '
            'and normal-attack AI. Final call uses original790010101, exact506002001 '
            'at4.2MHP/seven actions with original506001002AI/506001003skillset. '
            'Both full original stat rows, background400006, original scenario '
            'parameters and actual-defeat reward contracts are preserved.',
        'scope': 'New4292 mission content, global scenarios, CPKs, saves and original '
            'quest criteria are unchanged. The final original group identity also '
            'preserves the original2018 limit-burst mission target. No guessed '
            'statistics, generic AI or skipped intermediate encounters are used.'}
    provenance['retained_combat'] = ('All original2018 monster/parts/AI/skill/resistance '
        'records are retained. Only the reused typed scenario call bindings and '
        'matching original dependency rows are restored within mission7900101.')
