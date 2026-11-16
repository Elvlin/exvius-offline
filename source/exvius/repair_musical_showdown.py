"""Reconstruct the missing Musical Showdown field boss dependency graphs.

Original Global identities, AI, skills and published statistics are retained.
Unpreserved combat statistics and formations are explicitly derived here.
The existing field response assembler consumes these dependency-only bundles.
"""
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import IndexSource, PARTS_TOKENS, PARTS_DEFAULTS
from build_event_archive import rows
from reconstruct_event_battles import Reconstruction

STATS = ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')
BARD = ((10, 3000, 50, 1000, 50), (15, 8000, 75, 3000, 150),
        (20, 32000, 100, 5000, 250), (30, 63500, 150, 7000, 350),
        (50, 753000, 200, 10000, 500))
TUNE = ((5, 300, 20, 50, 5), (10, 2500, 40, 200, 10),
        (15, 10000, 60, 500, 25))
SOURCES = ['https://exvius.fandom.com/wiki/A_Musical_Showdown',
           'https://exvius.fandom.com/wiki/Bard_Spirit',
           'https://exvius.fandom.com/wiki/Tune_of_Hatred']

# Published regular-enemy totals and random battles (published total minus Bard).
# Wiki total battles are 8/9/7/7/8. These documented runs are not retail caps.
RANDOM_SAMPLES = ((7, 6, (3, 0, 0)), (8, 8, (1, 1, 0)),
                  (6, 6, (0, 2, 0)), (6, 4, (0, 1, 2)),
                  (7, 8, (0, 0, 2)))
METALS = ('111051000', '111061000', '211011000')
METAL_NAMES = ('Metal Minituar', 'Metal Cactuar', 'Metal Gigantuar')
METAL_UNITS = ('900020101', '900020201', '900020301')


def random_stage(index, bundle, monsters, parts):
    """Restore finite native field/group/counter allocations from a sourced run."""
    mid = str(9001701 + index)
    battles, tunes, metals = RANDOM_SAMPLES[index]
    # PRO's published 9480 EXP resolves the overlapping wiki location labels:
    # Bard7000 + four regular Tunes500 + two boss Tunes200 + metals20+30+30.
    tune = str(900010278 + (0 if index < 2 else 1 if index == 2 else 2))
    metal_battles = sum(metals)
    tune_battles = battles - metal_battles
    pairs = tunes - tune_battles
    singles = tune_battles - pairs
    assert min(pairs, singles) >= 0
    allocations = [(tune, 1, singles), (tune, 2, pairs)]
    allocations += [(iid, 1, count) for iid, count in zip(METALS, metals)]
    source = IndexSource()
    source_monsters = {r['xqartN26']: r for r in source.load('F_MONSTER_MST')}
    source_parts = {r['xqartN26']: r for r in source.load('F_MONSTER_PARTS_MST')}
    used = {tune}
    encount = []
    for offset, (iid, size, count) in enumerate(allocations, 11):
        if not count:
            continue
        gid = str(int(mid) * 100 + offset)
        used.add(iid)
        for slot in range(1, size + 1):
            bundle['Bi6hVv34'].append({'2fY1IomW': gid, 'xqartN26': iid,
                'MxLFKZ13': '170,340' if size == 1 else ('100,240' if slot == 1 else '100,440'),
                'Z0EN6jSh': str(slot), '3t7pZM5V': '2', 'WJdBp9f0': '1', 'm9BvFk2X': '1'})
            for counter in range(count):
                encount.append({'qo3PECw6': mid, 'YzGa63QM': '10', '2fY1IomW': gid,
                    'h4Sjf96p': str(counter), 'Z0EN6jSh': str(slot),
                    'xqartN26': iid, '6Yc4RkdM': '1', '9BetM2Ds': '',
                    'MZn8LC6H': '', 'g4voc2Aw': '',
                    # Native field 2 is unit level, not a capture quantity.
                    'Vf5DGw07': '10:' + METAL_UNITS[METALS.index(iid)] + ':1' if iid in METALS else '',
                    '4K8t5dVh': '0', 'V2mCH5UR': '', '14FMQseU': '0'})
    bundle['6v0LPiRe'] = encount
    present = {r['xqartN26'] for r in bundle['wbet57nF']}
    for iid in sorted(used - present):
        if iid in METALS:
            name = METAL_NAMES[METALS.index(iid)]
            monster = dict(source_monsters[iid], G4L0YIB2=name)
            part = {t: source_parts[iid].get(t, PARTS_DEFAULTS.get(t, '')) for t in PARTS_TOKENS}
            part['G4L0YIB2'] = name
            assert part['8a6gAwN9'] == '1' and part['A5x02C6a'] == '0'
        else:
            monster, part = monsters[iid], parts[iid]
        bundle['wbet57nF'].append(monster)
        bundle['bV34YIJQ'].append(part)
    return {'source_urls': SOURCES,
        'published_sample': {'random_battles': battles, 'regular_tunes': tunes,
                             'metal_minituars': metals[0], 'metal_cactuars': metals[1],
                             'metal_gigantuars': metals[2]},
        'recovered': 'Original map900004 encounter plane maps traversable encounter tiles to field10, whose original rate/safe-step profile remains unchanged. Existing original metal monster identities, graphics, stats and AI retained.',
        'reconstructed': 'Finite allocation reproduces the wiki documented run, not a proven retail maximum. Single metal fights and single/pair Tune fights partition the published monster and battle totals. Local group IDs/coordinates and the assignment of repeated formations to consecutive zero-based native counters are reconstructed. Original client still draws uniformly among distinct groups and consumes their finite counters; no refill or arbitrary extra quota.',
        'pro_tune_profile': 'Published EXP9480 = Bard7000 + regular4*500 + boss2*200 + metals20+30+30; random Tunes level15, boss Tunes level10.',
        'unit_rewards': 'Each Metal Cactuar drops one unit of its own type, documented by the Cactuar Dunes guide and corroborated by Musical stage/monster drop tables. Original English unit master IDs900020101/201/301. Native Vf5DGw07 is MissionDropInfo unitDropInfo; comma list of category:unitID:unitLevel tuples. Each allocated metal row carries one level1 tuple, not a pre-granted stage total.',
        'unit_reward_sources': ['https://exvius.fandom.com/wiki/Cactuar_Dunes',
            'https://exvius.fandom.com/wiki/Metal_Minituar_(Monster)',
            'https://exvius.fandom.com/wiki/Metal_Cactuar_(Monster)',
            'https://exvius.fandom.com/wiki/Metal_Gigantuar_(Monster)'],
        'loot_limit': 'Original per-encounter random-item reward records did not survive. Musical Gem1209000835 is restored separately on the scripted Bard row from observed result-screen amounts; no extra random Tune gem awards or unrelated materials are inserted.'}


def profiles():
    """Return all eight original enemy identities and their sourced skills."""
    base = IndexSource()
    native_parts = {r['xqartN26']: r for r in base.load('F_MONSTER_PARTS_MST')}
    donors = ('108001016', '108002012', '108003008', '108004020')
    # Four independently preserved level-10 normal spirit families agree.
    # This is a minion comparison, not a replacement boss or original Tune row.
    assert all(tuple(native_parts[i][t] for t in STATS) == ('70', '25', '40', '20')
               and native_parts[i]['7wV3QZ80'] == '10' and native_parts[i]['a9qg8vnP'] == '8'
               for i in donors)
    template = native_parts[donors[0]]
    monsters, parts = {}, {}
    for bard, values in ((True, BARD), (False, TUNE)):
        for i, (level, hp, mp, experience, gil) in enumerate(values):
            iid = str((900010273 if bard else 900010278) + i)
            name = 'Bard Spirit' if bard else 'Tune of Hatred'
            monsters[iid] = {'xqartN26': iid, 'G4L0YIB2': name,
                             'V9j8wJcC': '10000011' if bard else '10000012'}
            part = {t: template.get(t, PARTS_DEFAULTS.get(t, '')) for t in PARTS_TOKENS}
            part.update(xqartN26=iid, G4L0YIB2=name, fh31sk7B=str(hp), PC97pWQj=str(mp),
                        **{'7wV3QZ80': str(level), 'B6H34Mea': str(experience), '7UR4J2SE': str(gil),
                           '8a6gAwN9': '10000011' if bard else '1',
                           'A5x02C6a': '900000024' if bard else '0',
                           'ATM35pjf': '0', '3HriTp6B': '', 'e56NZY42': '0',
                           'hn42BL3Q': '0,0,0,0,0,0,0,0,0',
                           'D9Nb7jgd': '0,0,0,0,0,0,0,0',
                           'Rcqa1Zt7': '0,0,0,0,0,0,0', 'zPu2iUK8': ''})
            anchor, denominator = ((240, 180, 170, 110), 50) if bard else ((70, 25, 40, 20), 10)
            for token, value in zip(STATS, anchor):
                part[token] = str(max(1, math.ceil(value * level / denominator)))
            if bard:
                resistance = 75 if i >= 3 else 50
                part['hn42BL3Q'] = ','.join(map(str, (resistance, 0, resistance, resistance,
                                                     resistance, 0, resistance, resistance, 0)))
                part['D9Nb7jgd'] = '100,100,100,100,100,100,100,100'
                # Rcqa1Zt7 is the debuff vector, not the special-resist list.
                part['Rcqa1Zt7'] = ','.join(map(str, (0, 100 if i >= 3 else 0, 0,
                                                     100 if i >= 3 else 0,
                                                     0, 0, 0)))
                if i == 4:
                    part['zPu2iUK8'] = '1,2'
            parts[iid] = part
    skills = {r['6E5u1xrs']: r for r in base.load('F_MONSTER_SKILL_MST')}
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as archive:
        raw = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/monster_skills.json'))))
    recovery = SimpleNamespace(global_sets={r['A5x02C6a']: r for r in rows('F_MONSTER_SKILL_SET_MST')},
        raw_skills=raw, recovered_skills=set(), skill_rows=skills,
        skill_templates={kind: next(r for r in skills.values() if r['Isb1GDe2'] == kind and r.get('5w1o9DPV') == '0')
                         for kind in ('1', '2', '3', '4')})
    Reconstruction.recover_skills(recovery, '900000024')
    return monsters, parts, [recovery.skill_rows[str(i)] for i in range(900086, 900091)]


def stage(index, monsters, parts, skills):
    mid = str(9001701 + index)
    # The preserved INT event has the legacy filename and invokes 9001701.
    sid = '9001701' if index == 1 else mid
    gid = str(int(mid) * 100 + 1)
    bard = str(900010273 + index)
    tune = str(900010278 + (0 if index < 2 else 1 if index < 4 else 2))
    selected = (bard, tune)
    # The wiki documents two starting adds; original skills 900086/7 summon
    # slots 4/5. Their AI branches are limited_act:1. A callMax of one permits
    # each one-time summon and is not an arbitrary repeat-summon cap.
    formation = [{'2fY1IomW': gid, 'xqartN26': bard if slot == 1 else tune,
                  'MxLFKZ13': position, 'Z0EN6jSh': str(slot), '3t7pZM5V': '2',
                  'WJdBp9f0': '1' if slot <= 3 else '0', 'm9BvFk2X': '1'}
                 for slot, position in enumerate(('170,340', '90,230', '90,450', '260,230', '260,450'), 1)]
    bundle = {'rqxw0p9k': [{'ja07xgLF': sid, '6w4xiIsS': '400007'}],
              'YjHhvN65': [{'ja07xgLF': sid, '2fY1IomW': gid, 'T03qgLWA': '1',
                            '14FMQseU': '0', 'V2mCH5UR': '', '4K8t5dVh': '0'}],
              'JR7jZci2': [dict({k: r[k] for k in ('2fY1IomW', 'Z0EN6jSh', 'xqartN26')},
                               ja07xgLF=sid, **{'6Yc4RkdM': '1', '9BetM2Ds': '',
                                               'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': ''})
                            for r in formation],
              'Bi6hVv34': formation, 'wbet57nF': [monsters[i] for i in selected],
              'bV34YIJQ': [parts[i] for i in selected], 'Wp39QX52': skills}
    # This is a selected native reward tuple, not a newly guessed drop chance.
    # ScenarioBattleInfo's parser requires all four item fields and discards
    # the fourth field. The result is attached only to the Bard's own slot.
    bundle['JR7jZci2'][0]['9BetM2Ds'] = '20:1209000835:' + str(index + 1) + ':100'
    provenance = {'source_urls': SOURCES,
        'recovered': 'Original Global enemy IDs/graphics, Bard AI10000011 and skillset900000024; archived exact skill effects. Published level/HP/MP/EXP/gil/resists and ELT Bard combat stats.',
        'derived_stats': 'Bard lower ATK/DEF/MAG/SPR = ceil(published ELT stat * published level / 50). Tune = ceil(shared normal-spirit level-10 stat * published level / 10), four agreeing profiles108001016/108002012/108003008/108004020. These are reconstructed values, not original server rows.',
        'derived_presentation': 'Single-body native presentation fields from normal spirit108001016; generic attack AI1 for Tune; local coordinates and group ID; standard battle BGM400007; no unverified item drops.',
        'formation': 'Published Bard plus two starting Tunes; original skills target hidden slots4/5 and AI limits each to one summon. Group initial-display/callMax verified against pinned GL9 native reader.',
        'musical_gem_reward': {'item': '1209000835', 'observed_count': index + 1,
            'source_url': 'https://www.youtube.com/watch?v=GYXMMXlj-DI',
            'result_timestamp_seconds': (215, 526, 680, 919.8, 1183)[index],
            'attribution_source': 'https://exvius.fandom.com/wiki/Bard_Spirit',
            'reconstruction': 'Muted original-game walkthrough Items Obtained screens show1/2/3/4/5 Musical Gems by tier; Bard wiki lists Musical Gem, Tune wiki lists no loot. Reproduce those observed selected amounts on the Bard ScenarioBattleInfo row. Retail probability/variation is not recovered. The tuple fourth field100 satisfies the native four-field parser and is not rolled by the client. No opening loot or direct mission-end grant.'},
        'scenario': sid, 'original_script_member': '9000401_event.bin' if index == 1 else '9000040' + str(index + 1) + '_event.bin'}
    return mid, bundle, provenance


def main():
    path = ROOT / 'source/server/event_encounters.json'
    document = json.loads(path.read_text(encoding='utf8'))
    monsters, parts, skills = profiles()
    for index in range(5):
        mid, bundle, provenance = stage(index, monsters, parts, skills)
        random_provenance = random_stage(index, bundle, monsters, parts)
        entry = document['missions'].setdefault(mid, {})
        # Preserve the independently authored field random-encounter channel.
        previous = entry.setdefault('bundle', {})
        for tag, values in bundle.items():
            if tag in ('Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'Wp39QX52'):
                keys = {'Bi6hVv34': ('2fY1IomW', 'Z0EN6jSh'), 'wbet57nF': ('xqartN26',),
                        'bV34YIJQ': ('xqartN26', '6Yc4RkdM'), 'Wp39QX52': ('6E5u1xrs',)}[tag]
                identities = {tuple(r[k] for k in keys) for r in values}
                previous[tag] = [r for r in previous.get(tag, []) if tuple(r[k] for k in keys) not in identities] + values
            else:
                previous[tag] = values
        entry['scripted_boss_reconstruction'] = provenance
        entry['random_encounter_reconstruction'] = random_provenance
    for iid, monster in monsters.items():
        document['local_monster_names'][iid] = monster['G4L0YIB2']
        document['local_monster_names'][iid + 'A'] = monster['G4L0YIB2']
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    print('CHECKPOINT: reconstructed five Musical field scenario graphs, eight original enemy identities, five original skills')


if __name__ == '__main__':
    main()
