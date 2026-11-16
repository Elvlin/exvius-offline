"""Reconstruct absent Glaive profiles while retaining original identities/groups."""
import copy
import math
import statistics

from battle_content import PARTS_DEFAULTS, PARTS_TOKENS

SOURCES = ('https://ffbe.gorillawiki.jp/entry/10712',
           'https://altema.jp/ffbe/glancecastletansaku-49915',
           'https://ffbe.gorillawiki.jp/entry/539',
           'https://img.altema.jp/ffbe/uploads/2017/06/7955d21624aa34e38e9bc44e808a0415.jpg',
           'https://img.altema.jp/ffbe/uploads/2017/06/cc2bc706e46e07908f0be44b3e89adb0.jpg')
STATS = ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')
GROUPS = {'7640101': ('764010101', '764010111', '764010112'),
          '7640102': ('764010201', '764010207', '764010208')}
BOSSES = {'301141000': ('Chimera', False), '301141001': ('Chimera', True),
          '305241000': ('Dark Lord', False), '305241001': ('Dark Lord', True)}
# These are original same-species sets, not foreign monster replacements.
# Where the exact later profile's AI/set assignment is absent, the choice is
# explicitly reconstructed and recorded for that actor.
COMBAT = {'104061000': ('1', '0'), '104061001': ('1', '0'),
          '108231006': ('2', '108231000'), '108231007': ('2', '108231001'),
          '205711006': ('2', '205711000'), '205711007': ('2', '205711001'),
          '205731000': ('2', '205731000'), '212101000': ('2', '212101000'),
          '301141000': ('301141000', '301141000'),
          '301141001': ('301141000', '301141001'),
          '302031003': ('302031000', '302031001'),
          '303041005': ('303041000', '303041001'),
          '305241000': ('305241000', '305241000'),
          '305241001': ('305241000', '305241001'),
          '310001004': ('310001001', '310001001')}


def median_profile(recovery, race, level, boss):
    """Derive unknown values from an explicit comparable original cohort."""
    candidates = []
    for iid, values in recovery.parts.items():
        if len(values) != 1:
            continue
        row = values[0]
        hp, native_level = int(row['fh31sk7B']), int(row['7wV3QZ80'])
        if row.get('a9qg8vnP') != race or native_level <= 0 or row.get('e56NZY42', '0') not in ('', '0'):
            continue
        if boss:
            if not 1000000 <= hp <= 8000000:
                continue
        elif not 100 <= hp <= 500000 or int(iid) >= 300000000:
            continue
        if any(int(row.get(t) or 0) <= 0 for t in STATS):
            continue
        candidates.append((abs(native_level-level), iid, row))
    if not candidates:
        raise ValueError('No original same-race calibration profiles: ' + race)
    candidates.sort(key=lambda row: (row[0], int(row[1])))
    # Use the nearest available level band, rather than one selected foreign
    # boss's combat behavior or identity. Every source ID remains reviewable.
    radius = max(candidates[0][0], 5)
    selected = [entry for entry in candidates if entry[0] <= radius]
    tokens = ('fh31sk7B', 'PC97pWQj', *STATS, 'B6H34Mea', '7UR4J2SE')
    values = {}
    for token in tokens:
        scaled = [int(row.get(token) or 0) * level / int(row['7wV3QZ80']) for _, _, row in selected]
        values[token] = str(max(0, math.ceil(statistics.median(scaled))))
    for token in STATS:
        values[token] = str(max(1, int(values[token])))
    return values, selected[0][2], [iid for _, iid, _ in selected]


def build_glaive(recovery):
    base = recovery.base
    original_groups = base.load('F_BATTLE_GROUP_MST')
    dictionaries = {row['V9j8wJcC']: row for row in recovery.dictionary.values()}
    stages = {}
    all_ids = {row['xqartN26'] for row in original_groups
               if row['2fY1IomW'].startswith(('7640101', '7640102'))}
    if all_ids != COMBAT.keys():
        raise ValueError('Original Glaive formation identities changed')
    profiles, monsters, provenance = {}, {}, {}
    easy_level = math.ceil(99 * 15 / 95)
    for iid in sorted(all_ids, key=int):
        graphic = str(int(iid) // 100)
        dictionary = dictionaries[graphic]
        name = recovery.names[iid]
        race = dictionary['a9qg8vnP']
        # Group membership identifies the tier for regular shared profiles;
        # some original actors occur in both tiers and keep a single identity.
        easy = iid in {'104061000', '108231006', '205711006', '301141000', '305241000'}
        level = easy_level if easy else 99
        boss = iid in BOSSES
        values, template, cohort = median_profile(recovery, race, level, boss)
        part = {token: template.get(token, PARTS_DEFAULTS.get(token, '')) for token in PARTS_TOKENS}
        part.update(values)
        ai, skillset = COMBAT[iid]
        part.update(xqartN26=iid, G4L0YIB2=name, **{
            '6Yc4RkdM': '1', 'a9qg8vnP': race, '7wV3QZ80': str(level),
            '8a6gAwN9': ai, 'A5x02C6a': skillset,
            'hn42BL3Q': '0,0,0,0,0,0,0,0,0', 'D9Nb7jgd': '0,0,0,0,0,0,0,0',
            'Rcqa1Zt7': '0,0,0,0,0,0,0', 'zPu2iUK8': '', 'Y9Vz8WNH': '0',
            'f67khsQZ': '0', 'Q1qLbx93': '0', 'n0UEb71s': '10,100',
            '4Y2DGP7m': '1,1', 'LBye01Wi': '0:0', 'e56NZY42': '0',
            '3HriTp6B': '', 'rB70Ls63': '0', 'rtw4F6hn': '0',
            'ATM35pjf': '0', '3frn4ILX': '', 'IRf10dwx': '', 'e5xoiC84': '',
            'tPh7ue1c': '', 'm28pD1GM': ''})
        published = {}
        if boss:
            chimera = BOSSES[iid][0] == 'Chimera'
            hard_hp, hard_mp = (3600000, 2500) if chimera else (4000000, 5000)
            if not easy:
                part['fh31sk7B'], part['PC97pWQj'] = str(hard_hp), str(hard_mp)
                published = {'level': 99, 'hp': hard_hp, 'mp': hard_mp,
                             'elements': 'all neutral', 'ailments': 'all immune'}
            else:
                # The source retains difficulty15/95, but no EASY boss stats.
                # Scale the published HARD HP by the original same-race
                # low/high-level HP medians; do not label this a retail row.
                low, _, _ = median_profile(recovery, race, easy_level, False)
                high, _, _ = median_profile(recovery, race, 99, True)
                part['fh31sk7B'] = str(max(1, math.ceil(hard_hp * int(low['fh31sk7B']) / max(1, int(high['fh31sk7B'])))))
                part['PC97pWQj'] = str(max(1, math.ceil(hard_mp * easy_level / 99)))
            part['D9Nb7jgd'] = '100,100,100,100,100,100,100,100' if not easy else '0,0,0,0,0,0,0,0'
            if not chimera and not easy:
                part['Rcqa1Zt7'] = '0,100,100,100,100,0,0'
                published['stat_breaks'] = 'immune to ATK/DEF/MAG/SPR debuffs'
        elif graphic == '1040610':
            # The guide calls these unusually durable; the original formation
            # has five. Constrain their aggregate HP to the stage's own first
            # boss budget instead of borrowing another Imp variant's profile.
            # EASY is generated later in numeric order; derive its same budget
            # directly from the identical documented calibration formula.
            if easy:
                low, _, _ = median_profile(recovery, '1', easy_level, False)
                high, _, _ = median_profile(recovery, '1', 99, True)
                budget = math.ceil(3600000 * int(low['fh31sk7B']) / max(1, int(high['fh31sk7B'])))
            else:
                budget = 3600000
            part['fh31sk7B'] = str(max(1, math.ceil(budget / 5)))
        monsters[iid] = {'xqartN26': iid, 'G4L0YIB2': name, 'V9j8wJcC': graphic}
        profiles[iid] = part
        provenance[iid] = {'name': name, 'japanese_dictionary_name': dictionary['G4L0YIB2'],
            'dictionary_number': dictionary['Z0EN6jSh'], 'graphic': graphic, 'race': race,
            'original_identity': True, 'published_fields': published,
            'combat_source': {'AI': ai, 'skill_set': skillset,
                'assignment': 'Original boss AI and exact weak/strong set' if boss else
                    ('Reconstructed basic attack using original generic AI1; no own-species spell data preserved' if skillset == '0' else
                     'Original same-species skill set; AI assignment reconstructed where exact profile is absent')},
            'derived_stats': {'method': 'Median original single-body same-race profiles in nearest level band, scaled linearly to reconstructed level. Boss calibration restricted to HP1M..8M; regular calibration to original normal actors with HP100..500K. Published HARD HP/MP/level override this model.',
                'source_profile_ids': cohort, 'technical_presentation_profile': template['xqartN26'],
                'easy_level': 'ceil(published HARD level99 * original mission difficulty15 /95)',
                'easy_boss_hp': 'Published HARD HP scaled by original same-race low-level/high-level median HP ratio.',
                'imp_hp': 'Five-member aggregate HP equals this tier Chimera budget. This is a constrained reconstruction, not recovered retail HP.' if graphic == '1040610' else None},
            'unknown_original_fields': 'Unpublished combat stats, EXP/gil, regular levels/HP/MP/resists, EASY profile values and missing regular AI assignments are reconstructed, not original server records.'}
    for mid in ('7640101', '7640102'):
        formation = [copy.deepcopy(row) for row in original_groups
                     if row['2fY1IomW'].startswith(mid) and len(row['2fY1IomW']) == len(mid)+2]
        used = {row['xqartN26'] for row in formation}
        bundle = {'Bi6hVv34': formation, 'wbet57nF': [monsters[i] for i in sorted(used,key=int)],
                  'bV34YIJQ': [profiles[i] for i in sorted(used,key=int)],
                  'Wp39QX52': [], 'rqxw0p9k': [], 'YjHhvN65': [], 'JR7jZci2': []}
        # Original MissionStart masters bind every active script root. Retain
        # those exact rows and presentation fields, not a synthetic scenario.
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        carrier = json.loads((root/'source/server/responses.json').read_text(encoding='utf8'))['29JRaDbd']
        links = [row for row in carrier['YjHhvN65'] if row['2fY1IomW'] in GROUPS[mid]]
        wanted = {row['ja07xgLF'] for row in links}
        bundle['YjHhvN65'] = copy.deepcopy(links)
        bundle['rqxw0p9k'] = [copy.deepcopy(row) for row in carrier['rqxw0p9k'] if row['ja07xgLF'] in wanted]
        for link in links:
            for row in formation:
                if row['2fY1IomW'] == link['2fY1IomW']:
                    bundle['JR7jZci2'].append(dict(ja07xgLF=link['ja07xgLF'],
                        **{key:row[key] for key in ('2fY1IomW','xqartN26','Z0EN6jSh')},
                        **{'6Yc4RkdM':'1','9BetM2Ds':'','MZn8LC6H':'','g4voc2Aw':'','Vf5DGw07':''}))
        sets = {profiles[i]['A5x02C6a'] for i in used} - {'0'}
        skills = set()
        for skillset in sets:
            recovery.recover_skills(skillset)
            skills.update(s for s in recovery.global_sets[skillset]['7qxLC5hP'].split(',') if s)
        bundle['Wp39QX52'] = [recovery.skill_rows[i] for i in sorted(skills,key=int)]
        stages[mid] = (bundle, {'campaign':'Glaive Castle', 'sources':list(SOURCES),
            'actors':{i:provenance[i] for i in sorted(used,key=int)},
            'formations':'All original native group/position/slot/display rows preserved, including the five-Imp groups and six proven scenario-group roots. Additional regular groups are retained because the active loader selects them; no random allocation is inferred from the prefix.',
            'ownership':'Primary guide independently names Harcypete, Genoa, Evil Shaman, Magician, Chimera and Imp. Its list does not establish that the other preserved groups are unused; they are retained for dependency closure.',
            'loot':'No unpublished drop rates or items invented. Original mission/chest/first-clear rewards remain separate; random allocation rows are not supplied by this repair.'})
    return stages
