"""Restore the archived 2017 Princess stage without changing its 2023 profiles."""
import copy
import math

from battle_content import PARTS_DEFAULTS, PARTS_TOKENS


def build(recovery, indexed_random_allocations, skill_dependencies):
    mid = '7490101'
    # All thirteen ordinary formations belong to this exact original stage.
    # The two bonus formations remain finite and use their original identities.
    allocations = tuple((i, 2) for i in range(11, 24)) + ((25, 1), (26, 1))
    bundle = indexed_random_allocations(recovery, mid, allocations, '10')
    for row in bundle['6v0LPiRe']:
        amount = (500 if row['xqartN26'] in ('201151001', '201151002')
                  else 800 if row['xqartN26'] == '205621001' else 0)
        if amount:
            row['9BetM2Ds'] = '20:106302900:' + str(amount) + ':100'
    groups = recovery.base.load('F_BATTLE_GROUP_MST')
    selected = {mid + str(i).zfill(2) for i in range(11, 27)}
    bundle['Bi6hVv34'] = [copy.deepcopy(r) for r in groups if r['2fY1IomW'] in selected]
    identities = {r['xqartN26'] for r in bundle['Bi6hVv34']}
    bundle['wbet57nF'] = [copy.deepcopy(recovery.monsters[i]) for i in sorted(identities, key=int)]
    # These preserved earlier identities are the exact published 2017 profiles,
    # not a same-name monster from another game or an estimated stat multiplier.
    exact = {'203091007': '203091005', '104051007': '104051005',
             '205611006': '205611004', '209061010': '209061003',
             '304131003': '304131002', '412021000': '412021001'}
    profiles = []
    for iid, original in exact.items():
        row = copy.deepcopy(recovery.parts[original][0])
        row['xqartN26'] = iid
        profiles.append(row)
    # Their own-species old combat rows were overwritten by the 2023 update.
    # Published event HP/MP/level/rewards are exact. Unpublished four combat
    # values use a transparent level projection from the retained same species.
    # This is an explicit reconstruction, not recovered retail statistics.
    inferred = [('201151001', '201151000', 80, 1200000, 1000),
                ('201151002', '201151000', 80, 1200000, 1000),
                ('205621001', '205621000', 99, 5000000, 10000)]
    inferred += [(str(209061004 + i), '209061003', (80, 90, 99)[i // 2],
                  (500000, 750000, 1000000)[i // 2], 1000) for i in range(6)]
    derived = []
    for iid, anchor, level, hp, mp in inferred:
        row = copy.deepcopy(recovery.parts[iid][0])
        old = recovery.parts[anchor][0]
        for token in ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4'):
            row[token] = str(math.ceil(int(old[token]) * level / int(old['7wV3QZ80'])))
        row.update({'fh31sk7B': str(hp), 'PC97pWQj': str(mp), '7wV3QZ80': str(level)})
        if iid.startswith('209061'):
            row['hn42BL3Q'] = '-50,50,0,0,0,0,-50,0,0'
            row['D9Nb7jgd'] = '0,0,0,0,0,0,0,100'
        elif iid.startswith('201151'):
            row['hn42BL3Q'] = '-50,100,0,0,0,0,50,0,0'
            row['D9Nb7jgd'] = '0,0,100,0,100,100,0,100'
        else:
            row['hn42BL3Q'] = '100,0,-50,0,0,0,-50,0,0'
            row['D9Nb7jgd'] = '100,0,100,100,100,100,100,100'
        profiles.append(row)
        derived.append({'identity': iid, 'own_species_anchor': anchor,
                        'published': {'level': level, 'hp': hp, 'mp': mp},
                        'combat_stat_derivation': 'ceil(anchor stat * event level / anchor level)'})
    bundle['bV34YIJQ'] = [{t: p.get(t, PARTS_DEFAULTS.get(t, '')) for t in PARTS_TOKENS}
                           for p in profiles]
    skill_dependencies(recovery, bundle)
    return {mid: (bundle, {
        'campaign': 'The Web-Weaving Princess',
        'sources': ['https://exvius.fandom.com/wiki/' + n for n in
                    ('The_Web-Weaving_Princess', 'Flan', 'Imp_(Monster)', 'Ronin',
                     'Tarantula_(Monster)', 'Arachne_(FFXV)', 'Elder_Coeurl',
                     'Yojimbo', 'Ariadne')],
        'version_identity': 'Original mission7490101 costs20NRG and awards4starTrustMoogle, '
            'DebasedCoin10000, FireResistance15percent andIronDuke for the original2017 '
            'challenges. The2023Update costs30NRG and has different unit/turn restrictions '
            'and rewards. Only this2017 stage response is restored; indexed2023 profiles '
            'and other stages remain unchanged.',
        'recovered': 'Own field10, all original formation/slot identities and script-only '
            'Ariadne group749010124 with six initially hidden summoned Tarantulas. Exact '
            '2017 native profiles for five ordinary species and Ariadne match published '
            'level/HP/MP/EXP/gil and boss combat statistics. Published other species '
            'HP/MP/levels/resists and original rewards remain separate from counters.',
        'exact_native_profile_bindings': exact,
        'derived_profiles': derived,
        'reconstructed': 'Two finite occurrences of each of13 original ordinary formations '
            'plus one of each original ElderCoeurl/Yojimbo bonus formation gives28random '
            'fights. This bounded representative route stays below the same-event EASY '
            'documented29random fights; HARD retail quotas and bonus rarity are not '
            'preserved and are not claimed exact. Six Tarantula slots are paired in '
            'native action tiers2/3/4 to the published80/90/99 variants. Their four '
            'combat stats and ElderCoeurl/Yojimbo combat stats use only retained '
            'own-species level projections, explicitly reconstructed rather than exact '
            'retail values. Boss/add visibility and original summon AI remain intact.',
        'field': '10', 'random_battles': 28,
        'loot': 'The original DebasedCoin item106302900 is used for the published '
            '500-per-ElderCoeurl and800-per-Yojimbo drops, attached only to those '
            'actual encounter actors through the native reward channel. No entry '
            'award or invented ordinary-species random probability is added. '
            'Original quest and chest rewards remain separate.'})}
