"""Restore sourced field scenario graphs through the existing encounter path."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/exvius'))
sys.path.insert(0, str(ROOT / 'source/server'))
from reconstruct_event_battles import Reconstruction, key
from build_event_archive import rows
from battle_content import PARTS_TOKENS, PARTS_DEFAULTS

REFERENCE = ROOT / 'logs/reference/field-scenario-wiki-20261109.json'
ELEMENTS = ('fire', 'ice', 'lightning', 'water', 'wind', 'earth', 'light', 'dark')
AILMENTS = ('poison', 'blind', 'sleep', 'silence', 'paralyze', 'confuse', 'disease', 'petrify')
STAT_TOKENS = ('9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')
NIAN = ((80, 64000, 285, 4000, 400), (85, 160000, 380, 4000, 400),
        (90, 360000, 450, 4000, 400))
# Species order is the original Global900010181..198 name table. Each row
# preserves the event's published INT/ADV/PRO level, HP, MP, EXP and gil.
NIAN_REGULAR = (
    ('Wolf', '101025', '1', '0', 6, ((57,5230,54,30,3),(67,9300,68,30,3),(77,32330,75,30,3))),
    ('Purusa', '201013', '5', '201013000', 8, ((57,5360,90,400,30),(67,10280,113,400,30),(77,36100,125,400,30))),
    ('Coeurl', '201021', '311001000', '201021000', 8, ((57,4940,72,192,6),(67,9470,90,192,6),(77,33070,100,192,6))),
    ('Wild Rat', '101006', '5', '101001000', 6, ((57,4730,76,108,4),(67,9050,95,108,4),(77,31800,105,108,4))),
    ('Poison Toad', '103002', '5', '103011000', 6, ((55,4940,54,80,4),(65,9460,68,80,4),(75,28630,76,80,4))),
    ('Adamantoise', '203012', '203012000', '203012000', 4, ((60,6160,142,401,48),(70,11640,177,401,48),(80,40105,197,401,48))))
NIAN_BONUS = (('111051000','103041000'),('111061000','103051000'),('211011000','103061000'))
NIAN_CAPTURE = {'111051000':'900020101','111061000':'900020201','211011000':'900020301',
                '103041000':'900010101','103051000':'900010201','103061000':'900010301'}
# Exact original formations plus finite counts determined jointly by the
# campaign's published species totals and battle/EXP/gil totals.
CRYSTAL_ALLOCATIONS = (
    ((1,7),(2,8)),
    ((1,6),(2,6),(3,6)),
    ((1,5),(2,5),(3,5),(4,5)),
    ((1,5),(2,5),(3,5),(4,5),(5,5),(80,2)),
    ((1,6),(2,6),(3,6),(4,5),(5,5),(6,5),(8,2),(9,2),(10,1)))
MACALANIA_ALLOCATIONS = (((1,6),(2,6)),((1,5),(2,4),(3,6)),((1,6),(2,6),(3,6)),
                        tuple((i,4)for i in range(1,6)),tuple((i,4)for i in range(1,7)))
BABIL_ALLOCATIONS = (tuple((i,3)for i in range(1,6)),tuple((i,6)for i in range(1,4)),
    tuple(enumerate((3,4,3,3,4,3),1)),tuple(enumerate((3,3,3,3,3,3,3,4),1)),
    tuple(enumerate((3,3,4,4,4,4,4,4),1)))
PAIRED_EXPLORATIONS = (
    ('7030101','Orbonne Monastery Vaults','10',None,
     ((1,2),(2,3),(3,3),(4,3),(5,3)),15,2750,142),
    ('7030102','Orbonne Monastery Vaults','10',None,
     tuple((i,5)for i in range(1,6)),26,13600,1461),
    ('7030103','Orbonne Monastery Vaults','10',None,
     tuple(enumerate((4,4,4,5,6,6),1)),30,52250,6855),
    ('7450101','Destroy the Reactor - Exploration','10',None,
     tuple(enumerate((4,4,4,4,4,5,5),1)),31,112600,11887),
    ('7450102','Destroy the Reactor - Exploration','10','7450101',
     ((9,4),(10,3),(11,3)),11,590,79),
    ('7490102','The Web-Weaving Princess','10','7490101',
     tuple((i,4 if i in (8,9) else 3)for i in range(1,10)),30,8090,829),
    ('7540101','Escape from Alexandria Castle','12',None,
     tuple(enumerate((4,4,6,4,4,1,4),1))+((14,2),),31,165900,17447),
    ('7540102','Escape from Alexandria Castle','12','7540101',
     ((9,6),(10,6),(11,6)),19,920,112),
    ('7590101','Mt. Gagazet - Exploration','11',None,
     tuple(enumerate((3,4,3,3,3,4,4,4,2),2)),31,175600,18550),
    ('7590102','Mt. Gagazet - Exploration','11',None,
     tuple((i,3)for i in range(2,7)),16,920,112),
    ('7690101','Nam-Yensa Sandsea - Exploration','11',None,
     tuple(enumerate((3,3,3,3,4,4,3,4,3),2)),31,175600,18600),
    ('7690102','Nam-Yensa Sandsea - Exploration','11',None,
     tuple((i,3)for i in range(2,7)),16,920,112),
    ('7790101','Mt. Nibel - Exploration','10',None,
     tuple((i,3 if i==10 else 2)for i in range(2,11))+((11,1),),21,118100,12600),
    ('7790102','Mt. Nibel - Exploration','10',None,
     ((2,3),(3,3),(4,4)),11,950,115),
    ('8000101','Fodina Caestino - Exploration','11',None,
     tuple((i,3)for i in range(2,11)),None,156700,16620),
    ('8000102','Fodina Caestino - Exploration','11',None,
     tuple((i,3)for i in range(2,5)),None,830,103),
    ('7950102',"Shrine of Ru'Avitau - Exploration",'11',None,
     tuple((i,3)for i in range(2,5)),None,830,103))
DREAD_FIRST = ((1,2),)+tuple((i,1)for i in range(2,9))
DREAD_SECOND = tuple((i,1)for i in range(9,15))+((8,2),)
DREAD_THIRD = tuple((i,1)for i in (7,13,15,16,17,18,19))
DREAD_ALLOCATIONS = (
    (('110',tuple((i,1 if i<=5 else 2)for i in range(1,9))),
     ('120',tuple((i,1 if i<=12 else 2)for i in range(9,15))+((8,1),))),
    (('110',DREAD_FIRST),('120',DREAD_SECOND),('130',DREAD_THIRD+((20,1),))),
    (('110',DREAD_FIRST),('120',DREAD_SECOND),('130',DREAD_THIRD),
     ('140',tuple((i,1)for i in (3,14,19,20,21,22)))),
    (('110',DREAD_FIRST),('120',DREAD_SECOND),
     ('130',tuple((i,2 if i==7 else 1)for i in (7,13,15,16,17,18,19))),
     ('140',((14,2),)+tuple((i,1)for i in (19,20,21,22))),
     ('150',tuple((i,1)for i in (21,22,23)))))
MERMAID = ((39, 375000, 125, 343, 70), (59, 750000, 250, 490, 100),
           (79, 1500000, 500, 700, 144), (99, 3000000, 1000, 1000, 205))
MERMAID_LANTERNS = (130, 220, 400, 600)
LANDS = (
    ('610010100', 'Goblin', (1, 304, 15, 36, 4), 4, 'story comparison, not an explicit Lands stat row'),
    ('610010100', 'Goblin Guard', (1, 1950, 40, 180, 12), 1, 'story comparison, not an explicit Lands stat row'),
    ('610010101', 'Chocobo Eater', (11, 6700, 40, 520, 30), 1, 'story comparison, not an explicit Lands stat row'),
    ('610010102', 'Wyvern', (19, 24300, 45, 1300, 100), 1, 'published Lands ADV profile'),
    ('610010103', 'Hill Gigas', (24, 21000, 30, 650, 90), 1, 'published Lands ADV profile'),
    ('610010104', 'Amoebozoa', (68, 50000, 250, 1000, 35), 1, 'published Lands PRO profile'),
    ('610010105', 'Hill Gigas', (70, 88000, 250, 182, 5), 1, 'published Lands PRO profile'),
    ('610010106', 'Ogre', (72, 98000, 250, 786, 102), 1, 'published Lands PRO profile'))



def script_scenarios(data):
    spec = importlib.util.spec_from_file_location('field_native_pages', ROOT / 'source/build/inspect-map-chests-20261027.py')
    native = importlib.util.module_from_spec(spec)
    previous_args = sys.argv
    try:
        sys.argv = ['inspect-map-chests']
        spec.loader.exec_module(native)
    finally:
        sys.argv = previous_args
    r = native.Reader(data)
    size,version = r.integer(),r.integer()
    if size != len(data):
        raise ValueError('Original field container length mismatch')
    r.take(12 if version >= 1009 else 0)
    r.take(4 if version >= 1022 else 0)
    for _ in range(r.integer()):
        r.short();r.string()
    output = set()
    for _ in range(r.short()):
        start = r.pos
        length = r.integer();r.short()
        if version >= 1015:
            width,height = r.integer(),r.integer()
            r.take(width*height)
        for _ in range(r.short()):
            r.integer() if version >= 1024 else r.short()
            kind = r.byte()
            r.take(22+2*(version>=1046))
            for _ in range(r.byte()):
                _,commands = native.page(r,kind,version)
                for op,payload,_ in commands:
                    if op == 0x47:
                        if len(payload) != 4:
                            raise ValueError('Original scenario opcode payload mismatch')
                        output.add(str(int.from_bytes(payload,'big')))
        if r.pos != start+length:
            raise ValueError('Original field block coverage mismatch')
    if r.pos != len(data):
        raise ValueError('Original field container coverage mismatch')
    return output


def source():
    result = Reconstruction()
    for title, text in json.loads(REFERENCE.read_text(encoding='utf8'))['pages'].items():
        result.pages[key(title)] = {'title': title, 'revisions': [{'slots': {'main': {'*': text}}}]}
    # A deterministic local ID range, separate from the existing reconstructed
    # actors. These are explicit local identities, not invented original IDs.
    result.counter = 19000000
    # These are decrypted original Global master rows, recovered from the full
    # content archive using the pinned native Memorial table's literal key.
    # Apply them after template recovery to this generator's owned stage bundles.
    # Shared profiles, unrelated stages and authored counters stay outside this repair.
    original = ROOT / 'data/web_sources/global_archive_mst_decoded/F_MONSTER_SKILL_MST.ndjson'
    native_skills = {row['6E5u1xrs']: row for row in map(json.loads,
        original.read_text(encoding='utf8').splitlines())}
    result.original_global_skills = native_skills
    result.original_global_skill_ids = set(native_skills)
    return result


def actor(recovery, name, campaign, tier, values, native=None, resistance=None):
    level, hp, mp, experience, gil = values
    spec = dict(level=str(level), hp=str(hp), mp=str(mp))
    if resistance:
        spec.update({k: str(v) for k, v in resistance.items()})
    page = recovery.page(campaign) or {'title':campaign,'revisions':[{'slots':{'main':{'*':''}}}]}
    record = {'page': page, 'heading': campaign + ' - ' + tier, 'fields': {},
              'season_scoped': True, 'published_profiles': {key(name): spec}}
    if native:
        record['native_enemy_overrides'] = {name: {'part_id': native[0], 'ai': native[1]}}
    if name == 'Nian Beast':
        candidates = ['401081000','401081001','401081002','401081003']
        assert all(recovery.names[iid] == name and len(recovery.parts[iid]) == 1 for iid in candidates)
        record['native_donor_by_name'] = {name: min(candidates,
            key=lambda iid:(abs(int(recovery.parts[iid][0]['fh31sk7B'])-hp),int(iid)))}
    monster, parts, provenance = recovery.enemy(name, name, record,
        [campaign + ' - ' + tier], campaign, native[0] if native else '')
    for part in parts:
        part['B6H34Mea'], part['7UR4J2SE'] = str(experience), str(gil)
        if name == 'Nian Beast':
            part['zPu2iUK8'] = ''
            part['Rcqa1Zt7'] = '0,0,0,0,0,0,0'
            anchors = [recovery.parts[iid][0] for iid in candidates]
            lower, upper = next((a,b) for a,b in zip(anchors,anchors[1:])
                                if int(a['fh31sk7B']) <= hp <= int(b['fh31sk7B']))
            ratio = (hp-int(lower['fh31sk7B']))/(int(upper['fh31sk7B'])-int(lower['fh31sk7B']))
            for token in STAT_TOKENS:
                part[token] = str(math.ceil(int(lower[token]) + ratio*(int(upper[token])-int(lower[token]))))
            provenance['unpublished_values'] = ('2017 combat stats reconstructed by bounded HP interpolation '
                'between preserved Nian Beast profiles401081000/1/2/3. Original2017 identity/graphic/AI retained; '
                'these are not recovered2017 server statistics.')
    return monster, parts, provenance


def append_graph(bundle, sid, gid, actors, reward=''):
    bundle['rqxw0p9k'].append({'ja07xgLF': sid, '6w4xiIsS': '400007'})
    bundle['YjHhvN65'].append({'ja07xgLF': sid, '2fY1IomW': gid, 'T03qgLWA': '1',
                              '14FMQseU': '0', 'V2mCH5UR': '', '4K8t5dVh': '0'})
    for slot, (monster, parts) in enumerate(actors, 1):
        iid = monster['xqartN26']
        bundle['Bi6hVv34'].append({'2fY1IomW': gid, 'xqartN26': iid,
            'MxLFKZ13': '170,340' if len(actors) == 1 else str(90 + 65 * (slot % 2)) + ',' + str(150 + 85 * slot),
            'Z0EN6jSh': str(slot), '3t7pZM5V': '2', 'WJdBp9f0': '1', 'm9BvFk2X': '1'})
        for part in parts:
            bundle['JR7jZci2'].append({'ja07xgLF': sid, '2fY1IomW': gid,
                'xqartN26': iid, 'Z0EN6jSh': str(slot), '6Yc4RkdM': part['6Yc4RkdM'],
                '9BetM2Ds': reward if slot == 1 else '', 'MZn8LC6H': '',
                'g4voc2Aw': '', 'Vf5DGw07': ''})
        if not any(r['xqartN26'] == iid for r in bundle['wbet57nF']):
            bundle['wbet57nF'].append(monster)
            bundle['bV34YIJQ'].extend(parts)


def empty_bundle():
    return {tag: [] for tag in ('rqxw0p9k', 'YjHhvN65', 'JR7jZci2',
                               'Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'Wp39QX52')}


def skill_dependencies(recovery, bundle):
    wanted = set()
    indexed_sets = {r['A5x02C6a']: r for r in recovery.base.load('F_MONSTER_SKILL_SET_MST')}
    for part in bundle['bV34YIJQ']:
        sid = part.get('A5x02C6a')
        if sid in ('', '0', None):
            continue
        skillset = recovery.global_sets.get(sid) or indexed_sets.get(sid)
        if skillset is None:
            raise ValueError('Original monster skill set missing: ' + str(sid))
        if sid in recovery.global_sets:
            recovery.recover_skills(sid)
        wanted.update(s for s in skillset['7qxLC5hP'].split(',') if s)
    bundle['Wp39QX52'] = [recovery.skill_rows[s] for s in sorted(wanted, key=int)]


def nian_regular_actors(recovery, tier):
    actors, provenance = [], []
    for species, (name, prefix, ai, skillset, _, profiles) in enumerate(NIAN_REGULAR):
        values = profiles[tier]
        hp = values[1]
        # Restrict reconstruction to preserved normal profiles of this exact
        # species and its normal AI/skill set. Boss and other-model variants
        # cannot become stat anchors just because their level is close.
        pool = [iid for iid in recovery.by_name[key(name)] if iid.startswith(prefix)
                and len(recovery.parts.get(iid, [])) == 1
                and recovery.parts[iid][0]['8a6gAwN9'] == ai
                and recovery.parts[iid][0]['A5x02C6a'] == skillset]
        pool.sort(key=lambda iid: (int(recovery.parts[iid][0]['fh31sk7B']), int(iid)))
        lower = max((iid for iid in pool if int(recovery.parts[iid][0]['fh31sk7B']) <= hp),
                    key=lambda iid:(int(recovery.parts[iid][0]['fh31sk7B']),-int(iid)))
        upper = min((iid for iid in pool if int(recovery.parts[iid][0]['fh31sk7B']) >= hp),
                    key=lambda iid:(int(recovery.parts[iid][0]['fh31sk7B']),int(iid)), default=lower)
        iid = str(900010181 + tier * 6 + species)
        monster, parts, basis = actor(recovery, name, 'Lunar New Year', ('INT','ADV','PRO')[tier],
                                      values, (iid, ai))
        a, b = recovery.parts[lower][0], recovery.parts[upper][0]
        denominator = int(b['fh31sk7B']) - int(a['fh31sk7B'])
        ratio = (hp - int(a['fh31sk7B'])) / denominator if denominator else 0
        # Retain the exact original species model and normal action/skill
        # contract, then replace only the unavailable numeric combat profile.
        monster['V9j8wJcC'] = recovery.monsters[lower]['V9j8wJcC']
        for part in parts:
            for token in ('4Y2DGP7m','hn42BL3Q','D9Nb7jgd','Rcqa1Zt7','zPu2iUK8','a9qg8vnP'):
                part[token] = a[token]
            part['8a6gAwN9'], part['A5x02C6a'] = ai, skillset
            for token in STAT_TOKENS:
                value = (int(a[token]) * hp / int(a['fh31sk7B']) if not denominator
                         else int(a[token]) + ratio * (int(b[token])-int(a[token])))
                part[token] = str(math.ceil(value))
        basis['dictionary'] = monster['V9j8wJcC']
        basis['combat_anchors'] = [lower, upper]
        basis['unpublished_values'] = ('ATK/DEF/MAG/SPR reconstructed by bounded HP interpolation '
            'between preserved normal profiles of this exact species, rounded up. Original event '
            'identity and species model retained. Normal species AI/skillset/resists reused; '
            'not recovered2017 server values.')
        if not denominator:
            basis['unpublished_values'] = ('ATK/DEF/MAG/SPR reconstructed proportionally to HP from '
                'the highest preserved normal profile of this exact species, rounded up. '
                'Published Wild Rat PRO31800HP is1500HP above normal anchor101006013 at30300HP. '
                'Original event identity/model and normal species AI/skillset/resists retained; '
                'not recovered2017 server values.')
        actors.append((monster, parts))
        provenance.append(basis)
    return actors, provenance


def nian_random_stage(recovery, mid, tier, bundle, actors):
    """Finite own-event38-enemy sample, never a global or prefix encounter pool."""
    allocations = []
    for (_, _, _, _, total, _), (monster, parts) in zip(NIAN_REGULAR, actors):
        bundle['wbet57nF'].append(monster)
        bundle['bV34YIJQ'].extend(parts)
        # Ten triples and four pairs form14 ordinary battles. This grouping
        # is reconstructed; published evidence supplies the species totals.
        triples, pairs = (2, 0) if total == 6 else (2, 1) if total == 8 else (0, 2)
        allocations.extend((monster['xqartN26'], size, count)
                           for size, count in ((3, triples),(2, pairs)) if count)
    for iid in NIAN_BONUS[tier]:
        bundle['wbet57nF'].append(dict(recovery.monsters[iid], G4L0YIB2=recovery.names[iid]))
        bundle['bV34YIJQ'].extend(dict(p, G4L0YIB2=recovery.names[iid]) for p in recovery.parts[iid])
        allocations.append((iid, 1, 1))
    bundle['6v0LPiRe'] = []
    for offset, (iid, size, count) in enumerate(allocations, 11):
        gid = str(int(mid) * 100 + offset)
        for slot in range(1, size + 1):
            bundle['Bi6hVv34'].append({'2fY1IomW':gid,'xqartN26':iid,
                'MxLFKZ13':'170,340' if size == 1 else '100,'+str(170+100*slot),
                'Z0EN6jSh':str(slot),'3t7pZM5V':'2','WJdBp9f0':'1','m9BvFk2X':'1'})
            for counter in range(count):
                bundle['6v0LPiRe'].append({'qo3PECw6':mid,'YzGa63QM':'10','2fY1IomW':gid,
                    'h4Sjf96p':str(counter),'Z0EN6jSh':str(slot),'xqartN26':iid,'6Yc4RkdM':'1',
                    '9BetM2Ds':'','MZn8LC6H':'','g4voc2Aw':'',
                    'Vf5DGw07':'10:'+NIAN_CAPTURE[iid]+':1' if iid in NIAN_CAPTURE else '',
                    '4K8t5dVh':'0','V2mCH5UR':'','14FMQseU':'0'})
    skill_dependencies(recovery, bundle)


def crystal_tower_stages(recovery):
    stages = {}
    original_groups = recovery.base.load('F_BATTLE_GROUP_MST')
    for tier, allocations in enumerate(CRYSTAL_ALLOCATIONS):
        mid = str(7070101+tier)
        bundle = empty_bundle()
        groups = [copy.deepcopy(r) for r in original_groups
                  if r['2fY1IomW'].startswith(mid) and len(r['2fY1IomW']) == len(mid)+2]
        if tier == 3:
            # The campaign explicitly includes two Green Dragons in PRO.
            # This same campaign's preserved dragon profile exactly matches
            # the published350000HP/3000EXP/300gil; no other enemy is used.
            groups.append({'2fY1IomW':mid+'80','xqartN26':'407043000','MxLFKZ13':'170,340',
                'Z0EN6jSh':'1','3t7pZM5V':'2','WJdBp9f0':'1','m9BvFk2X':'1'})
        bundle['Bi6hVv34'] = groups
        used = {r['xqartN26'] for r in groups}
        for iid in sorted(used,key=int):
            bundle['wbet57nF'].append(copy.deepcopy(recovery.monsters[iid]))
            bundle['bV34YIJQ'].extend({t:p.get(t,PARTS_DEFAULTS.get(t,'')) for t in PARTS_TOKENS}
                                     for p in recovery.parts[iid])
        bundle['6v0LPiRe'] = []
        for suffix, count in allocations:
            gid = mid+str(suffix).zfill(2)
            formation = [r for r in groups if r['2fY1IomW']==gid and r['WJdBp9f0']=='1']
            if not formation:
                raise ValueError('Missing exact Crystal Tower formation '+gid)
            for counter in range(count):
                for row in formation:
                    for part in recovery.parts[row['xqartN26']]:
                        bundle['6v0LPiRe'].append({'qo3PECw6':mid,'YzGa63QM':'10','2fY1IomW':gid,
                            'h4Sjf96p':str(counter),'Z0EN6jSh':row['Z0EN6jSh'],
                            'xqartN26':row['xqartN26'],'6Yc4RkdM':part['6Yc4RkdM'],
                            '9BetM2Ds':'','MZn8LC6H':'','g4voc2Aw':'','Vf5DGw07':'',
                            '4K8t5dVh':'0','V2mCH5UR':'','14FMQseU':'0'})
        skill_dependencies(recovery,bundle)
        stages[mid] = (bundle, {'campaign':'The Crystal Tower',
            'sources':['https://exvius.fandom.com/wiki/The_Crystal_Tower'],
            'recovered':'Classic2016 five-tier event, not the2023 exploration. Original own field10, original formations/slots/positions, unchanged monster identities, stats, AI, skillsets and skill effects. Exact published species, battle, EXP and gil totals reconcile against the preserved profiles and original flat mission gil.',
            'reconstructed':'Finite per-group occurrence counts solve the original formation equations for the documented run. This is a sourced run reconstruction, not a claim of original server quota, draw order or rare-dragon frequency. PRO Green Dragon formation is local suffix80 with the exact same-event preserved407043000 profile; no other original formation is changed. The typed original boss group is excluded from random allocations and remains solely script-triggered. Zero-based native counters exhaust without refill.',
            'published_totals':{'battles':(16,19,21,28,39)[tier],
                                'experience':(2600,6680,11900,41000,75500)[tier],
                                'gil':(99,359,753,2560,5097)[tier]},
            'item_drop_limit':'Published possible dragon drops include Green/Yellow Megacites, Elixir and awakening materials, but the source does not preserve per-allocation probabilities or exact red material identities. No foreign item or invented random probability is inserted.'})
    return stages


def indexed_random_allocations(recovery, mid, allocations, field='10', group_prefix=None):
    """Serialize only the explicitly sourced finite group/count pairs."""
    groups = recovery.base.load('F_BATTLE_GROUP_MST')
    bundle = {'6v0LPiRe':[]}
    for suffix,count in allocations:
        gid = (group_prefix or mid)+str(suffix).zfill(2)
        formation = [r for r in groups if r['2fY1IomW']==gid and r['WJdBp9f0']=='1']
        if not formation:
            raise ValueError('Missing exact finite field formation '+gid)
        for counter in range(count):
            for row in formation:
                for part in recovery.parts[row['xqartN26']]:
                    bundle['6v0LPiRe'].append({'qo3PECw6':mid,'YzGa63QM':field,'2fY1IomW':gid,
                        'h4Sjf96p':str(counter),'Z0EN6jSh':row['Z0EN6jSh'],
                        'xqartN26':row['xqartN26'],'6Yc4RkdM':part['6Yc4RkdM'],
                        '9BetM2Ds':'','MZn8LC6H':'','g4voc2Aw':'','Vf5DGw07':'',
                        '4K8t5dVh':'0','V2mCH5UR':'','14FMQseU':'0'})
    if group_prefix and group_prefix != mid:
        # Explicit same-event cross-stage group namespace. This is bounded by
        # the supplied original group IDs, not all groups matching a prefix.
        wanted = {r['2fY1IomW']for r in bundle['6v0LPiRe']}
        bundle['Bi6hVv34'] = [copy.deepcopy(r)for r in groups if r['2fY1IomW'] in wanted]
        used = {r['xqartN26']for r in bundle['Bi6hVv34']}
        bundle['wbet57nF'] = [copy.deepcopy(recovery.monsters[i])for i in sorted(used,key=int)]
        bundle['bV34YIJQ'] = [{t:p.get(t,PARTS_DEFAULTS.get(t,''))for t in PARTS_TOKENS}
                             for i in sorted(used,key=int)for p in recovery.parts[i]]
        skill_dependencies(recovery,bundle)
    return bundle


def macalania_stages(recovery):
    stages = {}
    for tier, allocations in enumerate(MACALANIA_ALLOCATIONS):
        mid = str(7260101+tier)
        bundle = indexed_random_allocations(recovery,mid,allocations)
        stages[mid] = (bundle,{'campaign':'Macalania Woods',
            'sources':['https://exvius.fandom.com/wiki/Macalania_Woods'],
            'recovered':'Original own field10, exact native regular formation/actor/slot IDs and unchanged monster profiles, AI and skills. Published regular species counts and all five-tier battle/EXP/gil totals. All original boss and butterfly scenario groups remain script-triggered and are excluded from random allocations.',
            'reconstructed':'Finite occurrence counts solve the documented species and battle totals using original formations. BGN12random plus boss and one scripted Iguion; INT15random plus boss; ADV18random plus boss and two scripted Iguions; PRO20random plus boss and three scripted Iguions; ELT24random plus boss, five scripted Iguions and two scripted large Chimeras. Equal four occurrences of each original PRO/ELT regular formation reproduce the published totals. This is a balanced sourced run reconstruction, not recovered retail quota, draw order or loot probability. Native counters start at0 and exhaust without refill. No original actor, skill, formation or butterfly logic is modified.',
            'published_totals':{'battles':(14,16,21,24,32)[tier],'experience':(910,4600,18600,33200,95000)[tier],
                                'gil':(123,272,973,1830,6367)[tier]},
            'loot':'Blue/Red Butterfly Powder remains on the original butterfly script/reward path. No random encounter is substituted for a scripted butterfly and no invented random powder roll is added.'})
    return stages


def babil_stages(recovery):
    stages = {}
    for tier,allocations in enumerate(BABIL_ALLOCATIONS):
        mid = str(7050101+tier)
        stages[mid] = (indexed_random_allocations(recovery,mid,allocations),{
            'campaign':'The Giant of Babel','sources':['https://exvius.fandom.com/wiki/The_Giant_of_Babel'],
            'recovered':'Exact original field10 and native own-event formations, identities, positions, monster stats, skills and AI. Primary classic2016 event guide preserves all five-tier regular species totals and battle/EXP/gil totals. Scripted Fiend/Golbez groups remain exclusively in the original event script path.',
            'reconstructed':'Balanced finite per-formation counts satisfy every published regular species and battle total. Native original groups are reused unchanged. Formation quotas are source-constrained representative runs, not recovered retail draw order, unique solutions or rarity probabilities. Boss counts1/2/3/4/5 remain original scripted encounters; random counts15/18/20/25/30 exhaust on zero-based native occurrence keys without refill.',
            'published_totals':{'battles':(16,20,23,29,35)[tier],
                                'experience':(2700,8202,19500,34400,64000)[tier],
                                'gil':(102,442,1373,2970,5917)[tier]},
            'loot':'No unpublished random item-drop probabilities are invented. Original script/treasure/first-clear rewards remain on their original paths.'})
    return stages


def paired_exploration_stages(recovery):
    stages = {}
    for mid,campaign,field,prefix,allocations,battles,experience,gil in PAIRED_EXPLORATIONS:
        stages[mid] = (indexed_random_allocations(recovery,mid,allocations,field,prefix),{
            'campaign':campaign,'sources':['https://exvius.fandom.com/wiki/'+campaign.replace(' ','_')],
            'recovered':'Original own encounter field, exact native formations/identities/slots/positions, monster statistics, AI and skills. Published EXP/gil and available species/battle counts all reconcile with unchanged original profiles and original mission flat gil. Original boss fights remain script-triggered.',
            'reconstructed':'Balanced finite counts of exact original regular formations reproduce the documented run, not proven retail quotas, draw order or rarity probabilities. Native occurrence keys start at0 and exhaust without refill. No actor statistics or skills are modified. Where original EASY groups share the HARD namespace, only explicitly listed same-event groups and their unchanged profiles are supplied, without scanning unrelated prefixes.',
            'field':field,'published_totals':{'battles':battles,'experience':experience,'gil':gil},
            'loot':'No unpublished per-encounter item probabilities are invented. Original script/treasure/first-clear reward paths remain separate.'})
        if prefix:
            stages[mid][1]['original_group_namespace'] = {'prefix':prefix,
                'groups':[prefix+str(s).zfill(2)for s,_ in allocations]}
        if mid == '7030101':
            stages[mid][1]['recovered'] = ('Original own field10 and unchanged native formations/profiles/AI/skills. '
                'The published15battles and2750EXP constrain23regular actors plus the scripted three-enemy boss. '
                'Original native gil totals139, while the wiki reports142; this3gil discrepancy remains explicit '
                'and is not resolved by changing original mission or monster rewards.')
            stages[mid][1]['native_reward_difference'] = {'native_original_gil':139,'published_gil':142,
                'unexplained_difference':3,'policy':'Preserve original reward records; no invented correction.'}
        if mid in ('7030101', '7030102', '7030103'):
            graph, evidence = orbonne_script_dependencies(recovery.base, mid)
            stages[mid][0].update(graph)
            stages[mid][1]['original_script_dependencies'] = evidence
        if mid == '7540101':
            stages[mid][0]['JR7jZci2'] = [{'ja07xgLF':'7540105','2fY1IomW':'754010113',
                'xqartN26':'204171001','Z0EN6jSh':'1','6Yc4RkdM':'1',
                '9BetM2Ds':'20:106303100:200:100','MZn8LC6H':'','g4voc2Aw':'','Vf5DGw07':''}]
            # Preserve the optional boss's exact Global skill definitions even
            # though its original event-specific AI conditions remain absent.
            skillset = recovery.global_sets['204171001']
            stages[mid][0]['Wp39QX52'] = [recovery.skill_rows[sid]
                for sid in skillset['7qxLC5hP'].split(',') if sid]
            stages[mid][1]['scripted_reward_reconciliation'] = ('The published31battles explicitly include '
                'optional original Tantarian group754010113 as well as final Ralvuimago group754010108. '
                'Their5500+5000EXP and550+500gil remain on those original script groups, not random allocations.')
            stages[mid][1]['tantarian_reward'] = {'scenario':'7540105','group':'754010113','monster':'204171001',
                'guaranteed_drop':'20:106303100:200:100',
                'ownership':'Original Ticket item106303100, Japanese play-ticket name, original currency in70F_MEDAL_EXCHANGE rows. Native F_STORE_ITEM links that stock to original King Mog900125; stock includes Tin Helm (FFIX) and Mog\'s Ribbon, corroborating the same Alexandria owner. Wiki Ticket page lists Alexandria Castle acquisition.',
                'script_proof':'Original own75401010101_event.bin map10/event200001/page0 starts scenario7540105 then changes event/switch state; it has no item grant command. Original29J group row has empty reward fields and noJR7reward row. Restore guaranteed200 only on the native side-boss drop row, not mission entry or random encounters.',
                'settlement':'Native field drop collection reports the earned category20 item; existing durable mission-attempt settlement handles save reload and request retries. No mission-wide pre-award.'}
        if battles is None:
            stages[mid][1]['budget_derivation'] = ('The guide does not publish battle or individual species counts. '
                'Published total EXP and gil independently constrain the regular actor budget: '
                + ('(156700-5500)/2100 = (16620-600-180)/220 =72.' if mid=='8000101' else
                   '(830-200)/30 = (103-20-20)/3 =21.')
                + ' Three occurrences of each exact own-event native regular formation reproduce that finite budget. '
                'The resulting '+str(sum(c for _,c in allocations))+' random fights and per-species distribution '
                'are explicitly reconstructed, not published encounter counts or recovered retail quotas.')
    return stages


def orbonne_script_dependencies(base, mid):
    """Supply the exact boss graph referenced by the retained Orbonne scripts."""
    import hashlib
    sys.path.insert(0, str(ROOT / 'tools/vendor/python'))
    from cricodecs import cpk
    from battle_content import derive_mission

    package_name = {'7030101': 'Ver23_70301010101.cpk',
                    '7030102': 'Ver24_70301010201.cpk',
                    '7030103': 'Ver24_70301010301.cpk'}[mid]
    archive = ROOT / 'data/client/files/common_lang/sd/event/SP' / package_name
    package = cpk.load(str(archive))
    wanted, scripts = set(), []
    for index, member in enumerate(package.file_infos()):
        if not member.full_path.startswith('7030101') or not member.full_path.endswith('_event.bin'):
            continue
        data = package.file_bytes(index)
        ids = script_scenarios(data)
        if not ids or not ids <= {'7030101', mid}:
            raise ValueError('Unexpected original Orbonne script battle references: ' + mid)
        wanted.update(ids)
        scripts.append({'member': member.full_path, 'sha256': hashlib.sha256(data).hexdigest(),
                        'scenario_ids': sorted(ids, key=int)})
    if mid not in wanted:
        raise ValueError('Missing original Orbonne boss script: ' + mid)
    original = ROOT / 'data/web_sources/global_archive_mst_decoded'
    masters = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_MST.ndjson').read_text(encoding='utf8').splitlines())}
    links = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_GROUP_MST.ndjson').read_text(encoding='utf8').splitlines())}
    groups = {links[sid]['2fY1IomW'] for sid in wanted}
    dependencies = derive_mission(int(mid), base, field_groups=groups)
    graph = {tag: copy.deepcopy(dependencies.get(tag, [])) for tag in
             ('Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'Wp39QX52', 'BJ6A0KTt', '7KCkJd1E')}
    graph['rqxw0p9k'] = [copy.deepcopy(masters[sid]) for sid in sorted(wanted, key=int)]
    graph['YjHhvN65'] = [copy.deepcopy(links[sid]) for sid in sorted(wanted, key=int)]
    graph['JR7jZci2'] = []
    parts = {}
    for row in base.load('F_MONSTER_PARTS_MST'):
        parts.setdefault(row['xqartN26'], []).append(row)
    for sid in sorted(wanted, key=int):
        gid = links[sid]['2fY1IomW']
        for slot in graph['Bi6hVv34']:
            if slot['2fY1IomW'] != gid or slot['WJdBp9f0'] != '1':
                continue
            for part in parts[slot['xqartN26']]:
                graph['JR7jZci2'].append({'ja07xgLF': sid, '2fY1IomW': gid,
                    'xqartN26': slot['xqartN26'], 'Z0EN6jSh': slot['Z0EN6jSh'],
                    '6Yc4RkdM': part['6Yc4RkdM'],
                    **{channel: part.get(channel, '') for channel in
                       ('9BetM2Ds', 'MZn8LC6H', 'g4voc2Aw', 'Vf5DGw07')}})
    return graph, {
        'archive': archive.relative_to(ROOT).as_posix(), 'scripts': scripts,
        'global_scenario_source': 'data/web_sources/global_archive_mst_decoded/'
            'F_SCENARIO_BATTLE_MST.ndjson and F_SCENARIO_BATTLE_GROUP_MST.ndjson',
        'group_ids': {sid: links[sid]['2fY1IomW'] for sid in sorted(wanted, key=int)},
        'recovered': 'Exact original Global scenario metadata and links, and the '
            'explicitly referenced native formations, actors, slots, positions, '
            'unchanged profiles, skills and per-actor/part reward records. '
            'The own-event auxiliary BGN script is retained in INT and ADV packages.',
        'regional_limit': 'Referenced formation/profile/reward records are from '
            'the retained Japanese native battle index. Separate original Global '
            'server reward allocations are not retained. Existing finite random '
            'encounter counts and mission rewards remain separate and unchanged.'}


def shrine_hard_stage(recovery):
    mid = '7950101'
    allocations = tuple((i, 3) for i in range(2, 11))
    return {mid: (indexed_random_allocations(recovery, mid, allocations, '11'), {
        'campaign': "Shrine of Ru'Avitau - Exploration",
        'sources': ['https://exvius.fandom.com/wiki/Shrine_of_Ru%27Avitau_-_Exploration'],
        'recovered': 'Own original map encounter field11 and nine explicit original '
            'regular formations795010102..110. Their five species exactly match the '
            'HARD guide: EvilWeapon, Faust, MotherGlobe, OllaGrande andUllikummi. '
            'Original Kirin group795010101 remains solely script-triggered. '
            'All original actor statistics, skills, positions and rewards are retained.',
        'reconstructed': 'Three finite occurrences per original regular formation '
            'provide a balanced27-battle route. HARD retail counters, species totals '
            'and random loot probabilities are unpreserved; this explicit own-roster '
            'reconstruction is not claimed as recovered retail quota or draw order. '
            'Zero-based counters exhaust without refill and do not grant boss rewards.',
        'field': '11', 'random_battles': 27})}


def glaive_random_allocations(recovery, stages):
    for mid, suffixes in (('7640101', range(2, 11)), ('7640102', range(2, 7))):
        bundle, provenance = stages[mid]
        # These actors were absent from the indexed source and were reconstructed
        # by the existing Glaive repair. Allocate their actual served part rows.
        view = copy.copy(recovery)
        view.parts = dict(recovery.parts)
        for part in bundle['bV34YIJQ']:
            view.parts[part['xqartN26']] = [part]
        bundle['6v0LPiRe'] = indexed_random_allocations(
            view, mid, tuple((i, 3) for i in suffixes), '11')['6v0LPiRe']
        provenance['random_encounters'] = {
            'field': '11', 'groups': [mid + str(i).zfill(2) for i in suffixes],
            'recovered': 'Own external encounter field11 and explicit native '
                'regular formations. Original DarkLord, Chimera and five-Imp '
                'script groups remain excluded from random allocations.',
            'reconstructed': 'Three finite occurrences of each retained own regular '
                'formation. The exact retail counters and random loot probabilities '
                'are unpreserved. Served actors use the same documented Glaive '
                'profile reconstructions already used for scenario dependencies; '
                'no second profile or foreign actor is substituted.'}
        provenance['loot'] = ('Original mission/chest/first-clear rewards remain '
            'separate. Finite regular allocations have no invented item roll; '
            'native actor EXP/gil is earned through actual combat.')
    return stages


def restore_original_seasonal_scenario_ids(stages):
    """Use recovered Global scenario identities without guessing formations."""
    original = ROOT / 'data/web_sources/global_archive_mst_decoded'
    masters = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_MST.ndjson').read_text(encoding='utf8').splitlines())}
    links = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_GROUP_MST.ndjson').read_text(encoding='utf8').splitlines())}
    own = {str(i) for start, stop in ((9000701,9000703),(9002001,9002004))
           for i in range(start,stop+1)}
    for bundle, provenance in stages.values():
        present = {r['ja07xgLF'] for r in bundle.get('rqxw0p9k',[])} & own
        if not present:
            continue
        mapping = {}
        for row in bundle['YjHhvN65']:
            sid = row['ja07xgLF']
            if sid in present:
                mapping[row['2fY1IomW']] = links[sid]['2fY1IomW']
        bundle['rqxw0p9k'] = [copy.deepcopy(masters[r['ja07xgLF']])
            if r['ja07xgLF'] in present else r for r in bundle['rqxw0p9k']]
        bundle['YjHhvN65'] = [copy.deepcopy(links[r['ja07xgLF']])
            if r['ja07xgLF'] in present else r for r in bundle['YjHhvN65']]
        for tag in ('Bi6hVv34','JR7jZci2'):
            for row in bundle.get(tag,[]):
                row['2fY1IomW'] = mapping.get(row['2fY1IomW'],row['2fY1IomW'])
        provenance['original_global_scenarios'] = {
            'source': 'Original Global JS1Yuw4I and3h5KWXLz masters, '
                'decoded by their pinned native Memorial keys.',
            'scenario_ids': sorted(present,key=int),
            'group_ids': {sid:links[sid]['2fY1IomW'] for sid in sorted(present,key=int)},
            'recovered': 'Exact original Global scenario names/backgrounds and full '
                'scenario-to-group records replace the previously authored local '
                'boss group identities. All recovered backgrounds are400006.',
            'limits': 'Original formation coordinates, missing actor statistics and '
                'reward allocations are not present in these two tables. Their '
                'existing separately labeled reconstruction is retained; a recovered '
                'group reference is not claimed to recover its absent formation.'}
        if provenance.get('campaign') == 'The Misty Bamboo Forest':
            provenance['reconstructed'] = provenance['reconstructed'].replace(
                'Positions/groupIDs and standard scenario presentation reconstructed.',
                'Formation positions remain reconstructed. Exact original scenario '
                'metadata and group IDs are restored from the Global masters below.')


def dreadnought_stages(recovery):
    stages = {}
    for tier,zones in enumerate(DREAD_ALLOCATIONS,1):
        mid = str(7130101+tier)
        bundle = {'6v0LPiRe':[]}
        for field,allocations in zones:
            bundle['6v0LPiRe'].extend(indexed_random_allocations(recovery,mid,allocations,field)['6v0LPiRe'])
        stages[mid] = (bundle,{'campaign':'The Dreadnought',
            'sources':['https://exvius.fandom.com/wiki/The_Dreadnought'],
            'recovered':'Original native regular formations, all monster identities, combat values, AI, skills and optional Captain/chest/boss formations remain unchanged. Primary guide preserves per-species columns for the progressively unlocked2/3/4/5 areas, battle ranges and EXP/gil ranges. Exact original own fields110/120/130/140/150 map to successive original maps0/1/2/3/4..5.',
            'reconstructed':'Published species columns are assigned in order to those original successive map areas, explicitly an evidence-constrained reconstruction. Finite native group/counter rows reproduce every column exactly, including reuse of some original formations in more than one zone. Only unlocked tier areas are allocated. No optional Captain, chest trap or final boss becomes random. Original BGN remains the documented one-battle boss-only flow with no random allocation.',
            'sample':{'random_battles':(20,25,30,34)[tier-1],
                      'normal_actors':(69,86,105,119)[tier-1],
                      'experience_with_initial_visible_boss':(6230,11300,29750,49350)[tier-1],
                      'gil_with_initial_visible_boss_and_mission':(822,2933,4650,6867)[tier-1]},
            'reward_reconciliation':'INT optional six-enemy chest trap and Captain explain6230..6720EXP/822..892gil exactly. ADV optional Captain explains11300..11400/2933..2963. PRO optional Captain, three-enemy chest trap and two summoned Soldiers explain29750..31250/4650..4890. ELT original hidden Sergeant slots4/5/6/7 and exact CallAllies skills156960/970/980/990 remain unchanged. Normal plus initial visible boss gives49350EXP/6867gil; two actually summoned Sergeants give the published50050/6967 minimum, four give50750/7067 and optional Captain reaches51100/7117 maximum. Summoned rewards are not pre-granted and hidden actors are not made visible.',
            'limits':'These are sourced finite samples, not recovered retail draw order, maximum quotas or loot probabilities. The area-column assignment is derived and is not described as an original retained allocation table. No unpublished random item rates are invented.'})
    return stages


def field_ai_definition():
    # Reuse the original unconditional attack encoding, never a pointer to a
    # different enemy's AI. Original Tantarian parts retain their6,6 actions.
    grammar = next(r for r in rows('F_AI_MST')
                   if r['8a6gAwN9']=='1' and r['w7VR6ypY']=='1')
    rule = dict(grammar, **{'8a6gAwN9':'204171001','w7VR6ypY':'1',
                'WhQL5ev9':'Tantarian exploration documented physical attacks'})
    return {'version':1,'tables':{'F_AI_MST':{
        'identity_fields':['8a6gAwN9','w7VR6ypY'],'rows':[rule]}},
        'provenance':{'mission':'7540101','scenario_group':'754010113','monster':'204171001',
            'source_urls':['https://exvius.fandom.com/wiki/Escape_from_Alexandria_Castle',
                           'https://exvius.fandom.com/wiki/Tantarian',
                           'https://www.youtube.com/watch?v=nd7ypfez1XU&t=175s',
                           'https://www.youtube.com/watch?v=nd7ypfez1XU&t=280s'],
            'observed':'Own-event guide documents up to six physical attacks per turn. Muted2017 own-event footage shows normal physical attacks at175s; the280..292s sequence retains the same enemy near15%HP and returns to command selection without an observed special-skill banner.',
            'reconstructed':'Missing ownAI204171001 is authored as an unconditional normal attack using original native action grammar. Original parts6,6 determine six actions. This is evidence-constrained behavior reconstruction, not recovered retail AI. No other AI ID is substituted.',
            'retained':'Original HP5000000, MP10000, ATK650, DEF100, MAG500, SPR80, resistances, six actions and skillset204171001 with170520/162200/170530/170540 remain unchanged. Original optional side boss stays outside random encounter quotas.',
            'limits':'The preserved skill definitions include Edge, Death, Poison and Paper Storm, but their original event-specific trigger conditions were not recovered. They remain unchanged in the original skill master and skillset; this reconstruction does not claim exact retail activation rules.'}}


def write_field_ai():
    import hashlib
    from decode_client_data import client_manifest, decode
    from apply_jp_unit_tables import patch_native
    from native_master_index import build_index
    definition = field_ai_definition()
    info = next(v for v in client_manifest(ROOT/'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()
                if v['table']=='F_AI_MST')
    source = ROOT/'data/client/files/mst/Ver335_PCm9K3no.dat'
    original = source.read_bytes()
    original_index = source.with_name('PCm9K3no.i').read_bytes()
    content = ROOT/'source/server/content/battle/ai_repairs.json'
    if content.exists():
        prior = json.loads(content.read_text(encoding='utf8'))
        files = prior.get('native_overlay',{}).get('files',[])
        checked = prior.get('validation',{})
        if (prior.get('tables')==definition['tables'] and prior.get('provenance')==definition['provenance']
                and checked.get('source_master_sha256')==hashlib.sha256(original).hexdigest()
                and checked.get('original_index_sha256')==hashlib.sha256(original_index).hexdigest()
                and {r['path']for r in files}=={'mst/Ver335_PCm9K3no.dat','mst/PCm9K3no.i'}
                and all((ROOT/'data/overlay'/r['path']).is_file() and
                    hashlib.sha256((ROOT/'data/overlay'/r['path']).read_bytes()).hexdigest()==r['sha256']for r in files)):
            print('CHECKPOINT preserved verified own Tantarian AI ciphertext and paired index')
            return
    if build_index('F_AI_MST',original,info['key'],335) != original_index:
        raise ValueError('Original native AI pair-key index did not reproduce byte for byte')
    _, original_rows = decode(original,info['key'])
    if any(r['8a6gAwN9']=='204171001'for r in original_rows):
        raise ValueError('Original Tantarian AI unexpectedly exists; do not replace preserved behavior')
    target = ROOT/'data/overlay/mst'/source.name
    raw = target.read_bytes() if target.exists() else original
    if not raw.startswith(original):
        raise ValueError('Native AI overlay changed an unrelated original ciphertext line')
    _, active_rows = decode(raw,info['key'])
    if any(r['8a6gAwN9']!='204171001'for r in active_rows[len(original_rows):]):
        raise ValueError('Native AI overlay has another task addition; coordinate before changing it')
    output, stats = patch_native(raw,info['key'],['8a6gAwN9'],
        definition['tables']['F_AI_MST']['rows'],operation='replace_groups')
    if not output.startswith(original):
        raise ValueError('Field AI repair modified original ciphertext')
    _, decoded = decode(output,info['key'])
    if decoded[:len(original_rows)] != original_rows or decoded[len(original_rows):] != definition['tables']['F_AI_MST']['rows']:
        raise ValueError('Native AI repair round-trip differs from the selected own-AI group')
    index = build_index('F_AI_MST',output,info['key'],335)
    target.parent.mkdir(parents=True, exist_ok=True)
    if raw != output or not target.exists():target.write_bytes(output)
    index_target = target.with_name('PCm9K3no.i')
    if not index_target.exists() or index_target.read_bytes()!=index:index_target.write_bytes(index)
    if target.read_bytes()!=output or index_target.read_bytes()!=index:
        raise ValueError('Native AI overlay read-back differs')
    definition['native_overlay'] = {'files':[{'path':p.relative_to(ROOT/'data/overlay').as_posix(),
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in (target,index_target)]}
    definition['validation'] = {'original_ciphertext_lines_unchanged':len(original_rows),
        'own_ai_rules':len(definition['tables']['F_AI_MST']['rows']),
        'original_index_sha256':hashlib.sha256(original_index).hexdigest(),
        'pair_key':'8a6gAwN9,w7VR6ypY','group_key':'8a6gAwN9',
        'source_master_sha256':hashlib.sha256(original).hexdigest(),
        'writer':'apply_jp_unit_tables.patch_native replace_groups with original AI identity',
        'native_rows':len(decoded)}
    serialized = json.dumps(definition,ensure_ascii=False,indent=2)+'\n'
    if not content.exists() or content.read_text(encoding='utf8')!=serialized:
        content.write_text(serialized,encoding='utf8')
    print('CHECKPOINT restored own Tantarian AI rule and original-proven paired native index')


def build():
    recovery = source()
    output = {}
    nian = empty_bundle()
    provenance = []
    for i, values in enumerate(NIAN):
        resistance = dict(zip(ELEMENTS, (-75 if i == 0 else -20 if i == 1 else -25, 0, 0, 0, 0, 0, 0, 0)))
        resistance.update(dict(zip(AILMENTS, (100, 100, (10, 70, 30)[i], 100, 100, 100, 100, 100))))
        monster, parts, basis = actor(recovery, 'Nian Beast', 'Lunar New Year', ('INT','ADV','PRO')[i], values,
                                     (str(900010178 + i), '900000009'), resistance)
        append_graph(nian, str(9000701 + i), str(1719000101 + i), [(monster, parts)])
        provenance.append(basis)
    skill_dependencies(recovery, nian)
    regular = [nian_regular_actors(recovery, tier) for tier in range(3)]
    for index in range(21):
        mid = str(9000701 + index)
        tier = index % 3
        bundle = copy.deepcopy(nian)
        actors, ordinary_basis = regular[tier]
        nian_random_stage(recovery, mid, tier, bundle, actors)
        output[mid] = (bundle, {'campaign': 'Lunar New Year',
            'sources': ['https://exvius.fandom.com/wiki/'+name.replace(' ','_') for name in
                        ('Lunar New Year','Nian Beast',*[r[0] for r in NIAN_REGULAR])],
            'actors': provenance + ordinary_basis,
            'recovered': 'Original three Nian identities/graphic, AI900000009, skillset900000009 and archived exact skill effects. Original ordinary identities900010181..198 and own encounter zone10. Published per-tier HP/MP/level/EXP/gil, six-species counts6/8/8/6/6/4, and tier-specific Cactuar/Gil Snapper captures. Preserved bonus monster profiles and native capture unit IDs.',
            'reconstructed': 'Unpreserved boss ATK/DEF/MAG/SPR use bounded HP interpolation between preserved Nian401081000..3; ordinary combat values use same-species normal-profile HP anchors, documented per actor. Wild Rat PRO uses proportional31800/30300 scaling above its own highest normal anchor; other ordinary values interpolate within preserved anchors. Original identities, models and original boss counts retained. Local positions/groupIDs and standard presentation fields reconstructed. Ten triple and four pair formations partition38 ordinary enemies into14 fights; one of each documented tier bonus gives16 random fights plus the sole scripted boss, matching the published15..17-battle envelope. This is a finite documented upper-sample reconstruction, not recovered retail formation order, cap or bonus probability. Bonus probability is unrecovered, and the two local finite bonus allocations are not claimed to reproduce retail rarity. Native counters remain zero-based and exhaust without refill. All three boss scenarios remain available for the original daily conditional scripts.',
            'reward_checks': {'ordinary_exp':7648,'boss_exp':4000,'bonus_exp':(60,70,80)[tier],
                              'ordinary_gil':546,'boss_gil':400,'original_mission_gil':(32,70,117)[tier],
                              'bonus_gil':(9,11,14)[tier]},
            'unit_rewards': 'One level1 capture per allocated bonus monster. Native category10:originalUnitID:level tuples are attached to that encounter, with existing result settlement and durable attempt guard. No pre-granted mission-wide captures or invented regular item-drop probabilities.'})
    for i, values in enumerate(MERMAID):
        bundle = empty_bundle()
        resistance = dict(zip(ELEMENTS, (0,0,-50,100,0,0,-50,50)))
        resistance.update(dict(zip(AILMENTS, (100,0,100,100,100,100,0,100))))
        monster, parts, basis = actor(recovery, 'Mermaid', 'The Misty Bamboo Forest', ('INT','ADV','PRO','ELT')[i],
                                      values, (str(900010319 + 5*i), '900000021'), resistance)
        for part in parts:
            part['A5x02C6a'] = '900000030'
            part['zPu2iUK8'] = '1,2'
            for token, anchor in zip(STAT_TOKENS, (350,50,430,70)):
                part[token] = str(math.ceil(anchor * values[0] / 99))
        mid = str(9002001 + i)
        # Published repeatable drops are separate from first-clear rewards.
        # ELT's documented600-640 range supports the base600; the unpreserved
        # extra-drop probability is not invented.
        append_graph(bundle, mid, str(1719000201 + i), [(monster, parts)],
                     '20:1209000836:' + str(MERMAID_LANTERNS[i]) + ':100')
        skill_dependencies(recovery, bundle)
        output[mid] = (bundle, {'campaign': 'The Misty Bamboo Forest',
            'sources': ['https://exvius.fandom.com/wiki/The_Misty_Bamboo_Forest','https://exvius.fandom.com/wiki/Mermaid'],
            'actors': [basis], 'recovered': 'Original Mermaid identity/graphic, AI900000021, skillset900000030, exact archived effects and published tier level/HP/MP/EXP/gil, resists and ELT combat stats.',
            'reconstructed': 'Lower ATK/DEF/MAG/SPR = ceil(published ELT stat * published level /99). One Mermaid as documented. Positions/groupIDs and standard scenario presentation reconstructed. Published Lantern130/220/400 and ELT minimum600 selected native item tuples; first-clear rewards remain separate. ELT published range600-640 and rare extra-drop probability are not converted to a guessed random roll.'})
    lands = empty_bundle()
    provenance = []
    grouped = {}
    for sid, name, values, count, evidence in LANDS:
        tier = 'BGN' if sid.endswith('100') else 'INT' if sid.endswith('101') else 'ADV' if sid.endswith(('102','103')) else 'PRO'
        monster, parts, basis = actor(recovery, name, 'Lands of Plenty', tier, values)
        basis['profile_evidence'] = evidence
        basis['scenario_id'] = sid
        # The source's special PRO resistances supersede generic species rows.
        if tier == 'PRO':
            for part in parts:
                part['hn42BL3Q'] = '20,20,20,20,20,20,0,0,0' if name == 'Amoebozoa' else '0,0,50,0,0,50,0,0,0'
                part['D9Nb7jgd'] = '100,100,100,100,100,100,100,100' if name == 'Amoebozoa' else ('100,0,100,100,100,100,100,100' if name == 'Hill Gigas' else '100,20,100,100,100,100,100,100')
        grouped.setdefault(sid, []).extend([(monster, parts)] * count)
        provenance.append(basis)
    for index, (sid, actors) in enumerate(grouped.items()):
        append_graph(lands, sid, str(1719000301 + index), actors)
    # Preserve the existing allocation sequence above so PRO and later local
    # actor IDs remain stable. Replace the four recovered formations together
    # with their linked actors, profiles and scenario information below.
    original = ROOT / 'data/web_sources/global_archive_mst_decoded'
    scenario_ids = set(grouped)
    masters = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_MST.ndjson').read_text(encoding='utf8').splitlines())
        if r['ja07xgLF'] in scenario_ids}
    links = {r['ja07xgLF']: r for r in map(json.loads,
        (original / 'F_SCENARIO_BATTLE_GROUP_MST.ndjson').read_text(encoding='utf8').splitlines())
        if r['ja07xgLF'] in scenario_ids}
    if masters.keys() != scenario_ids or links.keys() != scenario_ids:
        raise ValueError('Original Lands of Plenty scenario metadata is incomplete')
    mapping = {r['2fY1IomW']: links[r['ja07xgLF']]['2fY1IomW']
               for r in lands['YjHhvN65']}
    exact_scenarios = {str(610010100 + i) for i in range(4)}
    replaced_groups = {r['2fY1IomW'] for r in lands['YjHhvN65']
                       if r['ja07xgLF'] in exact_scenarios}
    lands['Bi6hVv34'] = [r for r in lands['Bi6hVv34']
                        if r['2fY1IomW'] not in replaced_groups]
    lands['JR7jZci2'] = [r for r in lands['JR7jZci2']
                        if r['ja07xgLF'] not in exact_scenarios]
    provenance = [r for r in provenance if r['scenario_id'] not in exact_scenarios]
    original_groups = recovery.base.load('F_BATTLE_GROUP_MST')
    exact_actors = set()
    for sid in sorted(exact_scenarios, key=int):
        gid = links[sid]['2fY1IomW']
        formation = [copy.deepcopy(r) for r in original_groups if r['2fY1IomW'] == gid]
        expected_names = sorted(name for source_sid, name, _, count, _ in LANDS
                                if source_sid == sid for _ in range(count))
        if sorted(recovery.names.get(r['xqartN26'], '') for r in formation) != expected_names:
            raise ValueError('Original Lands of Plenty formation differs from its documented roster: ' + sid)
        lands['Bi6hVv34'].extend(formation)
        for row in formation:
            iid = row['xqartN26']
            if iid not in recovery.monsters or not recovery.parts.get(iid):
                raise ValueError('Original Lands of Plenty actor is incomplete: ' + iid)
            for part in recovery.parts[iid]:
                lands['JR7jZci2'].append({'ja07xgLF': sid, '2fY1IomW': gid,
                    'xqartN26': iid, 'Z0EN6jSh': row['Z0EN6jSh'],
                    '6Yc4RkdM': part['6Yc4RkdM'],
                    '9BetM2Ds': part.get('9BetM2Ds', ''),
                    'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': ''})
            if iid not in exact_actors:
                exact_actors.add(iid)
                lands['wbet57nF'].append(copy.deepcopy(recovery.monsters[iid]))
                name = recovery.names[iid]
                values = next(values for source_sid, source_name, values, _, _ in LANDS
                              if source_sid == sid and source_name == name)
                published_tokens = ('7wV3QZ80', 'fh31sk7B', 'PC97pWQj', 'B6H34Mea', '7UR4J2SE')
                applied = dict(zip(published_tokens, map(str, values)))
                original_values = []
                for part in recovery.parts[iid]:
                    projected = {token: part.get(token, PARTS_DEFAULTS.get(token, ''))
                                 for token in PARTS_TOKENS}
                    original_values.append({'part': part['6Yc4RkdM'],
                        'item_drop_pool': part.get('9BetM2Ds', ''),
                        'values': {token: part[token] for token in published_tokens + STAT_TOKENS}})
                    projected.update(applied)
                    lands['bV34YIJQ'].append(projected)
                provenance.append({'scenario_id': sid, 'group_id': gid, 'part_id': iid,
                    'enemy': name,
                    'profile_evidence': 'The original Global scenario explicitly names this group. '
                        'Its preserved Japanese formation and actor identities match the documented '
                        'Global roster. Regional numeric equality is not assumed.',
                    'original_jp_values': original_values,
                    'applied_global_values': applied,
                    'field_provenance': {
                        'scenario_metadata_and_group_id': 'Recovered original Global scenario masters.',
                        'formation_and_actor_identity': 'Preserved Japanese battle index for the exact '
                            'group ID referenced by the original Global scenario.',
                        'hp_mp_level_exp_gil': 'Retained English wiki ' + name + ' Stats table: ' +
                            ('Lands of Plenty ADV event row.' if sid in ('610010102', '610010103') else
                             'documented story profile for the directly referenced native actor. '
                             'A separate Lands BGN/INT numeric row is not preserved.'),
                        'atk_def_mag_spr': 'Original Japanese values retained unchanged as a regional '
                            'reconstruction. No original Global values recovered; no interpolation applied.',
                        'item_drops': 'Original Japanese drop list for the exact actor and part from '
                            'the group explicitly referenced by the original Global scenario. '
                            'Copy quantities and rates into JR7jZci2, not the unsupported '
                            'MonsterParts response field. Regional server-allocation equality is unproven.',
                        'other_profile_fields': 'Original Japanese indexed fields retained, including '
                            'resistances, AI and skill-set assignments. Available original Global skill '
                            'records replace generated skill rows later in this generator.'}})
    used = {r['xqartN26'] for r in lands['Bi6hVv34']}
    lands['wbet57nF'] = [r for r in lands['wbet57nF'] if r['xqartN26'] in used]
    lands['bV34YIJQ'] = [r for r in lands['bV34YIJQ'] if r['xqartN26'] in used]
    lands['rqxw0p9k'] = [copy.deepcopy(masters[sid]) for sid in grouped]
    lands['YjHhvN65'] = [copy.deepcopy(links[sid]) for sid in grouped]
    for tag in ('Bi6hVv34', 'JR7jZci2'):
        for row in lands[tag]:
            row['2fY1IomW'] = mapping.get(row['2fY1IomW'], row['2fY1IomW'])
    skill_dependencies(recovery, lands)
    for i in range(4):
        output[str(610010100 + i)] = (copy.deepcopy(lands), {'campaign':'Lands of Plenty',
            'sources':['https://exvius.fandom.com/wiki/Lands_of_Plenty'] + ['https://exvius.fandom.com/wiki/' + name.replace(' ','_') for name in dict.fromkeys(r[1] for r in LANDS)],
            'actors':provenance,
            'original_global_scenarios': {
                'source': 'Original Global F_SCENARIO_BATTLE_MST and F_SCENARIO_BATTLE_GROUP_MST, '
                    'decoded from the recovered content archive with pinned native keys.',
                'scenario_ids': sorted(scenario_ids, key=int),
                'group_ids': {sid: links[sid]['2fY1IomW'] for sid in sorted(scenario_ids, key=int)},
                'recovered': 'All seven original Global scenario names, backgrounds and complete group-link '
                    'records. BGN, INT and ADV use the four directly referenced groups and their preserved '
                    'Japanese formations, slot order, positions and actor identities, with documented Global '
                    'HP/MP/level/EXP/gil applied by field as recorded for each actor.',
                'limits': 'PRO group references are recovered, but their formation and actor records remain '
                    'unpreserved. Their existing separately labeled reconstruction is retained. BGN/INT/ADV '
                    'four combat statistics and other unverified regional fields retain Japanese source values, '
                    'not recovered Global values. BGN/INT numeric wiki rows describe the referenced story actors.'},
            'recovered':'Original Global bindings for BGN four Goblins plus Goblin Guard, INT Chocobo Eater and '
                'ADV Wyvern then Hill Gigas. These explicitly reuse preserved group identities. PRO retains published '
                'Amoebozoa, Hill Gigas and Ogre HP/MP/level/EXP/gil and special resistances.',
            'reconstructed':'BGN/INT/ADV use Japanese native formations and unmodified Japanese combat statistics '
                'where no Global values survive. Published Global HP/MP/level/EXP/gil supersede their Japanese '
                'counterparts, including Goblin 304 HP, Goblin Guard 1950 HP and ADV Wyvern 100 gil. PRO retains local '
                'actor IDs, authored coordinates and unpublished same-model combat values/AI. Its three group '
                'IDs and scenario metadata are now original. BGN/INT/ADV use the retained Japanese '
                'drop pools of their directly referenced native actors, including original quantities '
                'and rates. Separate original Global loot allocations and PRO drop pools remain '
                'unpreserved; no new loot probabilities are invented. Existing local '
                'actor allocation order and all four missions\' script scenario IDs are preserved.'})
    output.update(crystal_tower_stages(recovery))
    output.update(macalania_stages(recovery))
    output.update(babil_stages(recovery))
    output.update(paired_exploration_stages(recovery))
    output.update(dreadnought_stages(recovery))
    output.update(shrine_hard_stage(recovery))
    from repair_route_explorations import build as build_route_explorations
    output.update(build_route_explorations(recovery, indexed_random_allocations))
    from repair_updated_explorations import build as build_updated_explorations
    output.update(build_updated_explorations(recovery, indexed_random_allocations))
    from repair_modern_explorations import build as build_modern_explorations
    output.update(build_modern_explorations(recovery, indexed_random_allocations))
    from repair_late_explorations import build as build_late_explorations
    output.update(build_late_explorations(recovery, indexed_random_allocations))
    from repair_web_princess import build as build_web_princess
    output.update(build_web_princess(recovery, indexed_random_allocations, skill_dependencies))
    from repair_glaive_castle import build_glaive
    output.update(glaive_random_allocations(recovery, build_glaive(recovery)))
    from repair_bamboo_encounters import augment as augment_bamboo_encounters
    augment_bamboo_encounters(recovery, output, actor, skill_dependencies)
    from repair_world_explorations import build as build_world_explorations
    output.update(build_world_explorations(recovery.base))
    from repair_classic_hard_explorations import build as build_classic_hard_explorations
    output.update(build_classic_hard_explorations(recovery, indexed_random_allocations,
                                               skill_dependencies))
    from repair_lost_map_rewards import build as build_lost_map_rewards
    output.update(build_lost_map_rewards(recovery.base))
    from repair_enchanted_maze import build as build_enchanted_maze
    output.update(build_enchanted_maze(recovery.base))
    restore_original_seasonal_scenario_ids(output)
    for mid, (bundle, provenance) in output.items():
        served = {r['6E5u1xrs'] for r in bundle.get('Wp39QX52',[])}
        exact = served & recovery.original_global_skill_ids
        if exact:
            bundle['Wp39QX52'] = [copy.deepcopy(recovery.original_global_skills[r['6E5u1xrs']])
                if r['6E5u1xrs'] in exact else r for r in bundle['Wp39QX52']]
            provenance['original_global_skills'] = {
                'source': 'Original Global Ver367_wJE09yxD.dat, '
                    'F_MONSTER_SKILL_MST, decoded by its pinned native Memorial key.',
                'skill_ids': sorted(exact,key=int),
                'recovered': 'Complete original native rows, including effects, '
                    'targeting, element flags, action flags, damage frames and '
                    'visual references. These replace generated skill templates. '
                    'AI assignments and unavailable monster statistics are separate '
                    'and retain their existing explicit reconstruction provenance.'}
    return output


def main():
    path = ROOT / 'source/server/event_encounters.json'
    document = json.loads(path.read_text(encoding='utf8'))
    entries = build()
    original_names = {r['key'].rsplit('_',1)[-1]:r['v'][0]
                      for r in rows('F_TEXT_MONSTER_NAME',text=True)}
    local_ids = {row['xqartN26'] for bundle, _ in entries.values()
                 for row in bundle.get('wbet57nF',[]) if int(row['xqartN26']) >= 1800000000}
    for mid, entry in document['missions'].items():
        if mid in entries:
            continue
        conflicts = local_ids.intersection(row['xqartN26']
            for row in entry.get('bundle', {}).get('wbet57nF', []))
        if conflicts:
            raise ValueError('Local field actor IDs already owned by mission ' + mid + ': ' + ','.join(sorted(conflicts)))
    for mid, (bundle, provenance) in entries.items():
        document['missions'].setdefault(mid,{})['bundle'] = bundle
        provenance = copy.deepcopy(provenance)
        lottery = provenance.pop('original_weighted_lottery', None)
        if lottery is not None:
            document['missions'][mid]['original_weighted_lottery'] = lottery
        document['missions'][mid]['field_scenario_reconstruction'] = provenance
        for row in bundle.get('wbet57nF',[]):
            iid = row['xqartN26']
            name = original_names.get(iid,row['G4L0YIB2'])
            document['local_monster_names'][iid] = name
            document['local_monster_names'][iid+'A'] = name
    from restore_native_loot_channels import restore_encounter_channels
    restored_loot = restore_encounter_channels(document)
    print('CHECKPOINT exact-actor omitted loot channels', json.dumps(restored_loot))
    # Reuse the existing save path's write-then-replace contract. A failed write
    # must not truncate the accepted encounter document on this nearly full drive.
    pending = ROOT / 'build/scratch/field-encounter-write.json'
    pending.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pending.open('w', encoding='utf8') as stream:
            json.dump(document, stream, ensure_ascii=False, separators=(',',':'))
            stream.write('\n')
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    write_field_ai()
    print('CHECKPOINT reconstructed',len(entries),'explicit field content entries')
    restored = [p['original_global_skills']['skill_ids'] for _,p in entries.values()
                if p.get('original_global_skills')]
    print('CHECKPOINT original Global skill records',len(set(s for group in restored for s in group)),
          'unique,',sum(map(len,restored)),'served rows across',len(restored),'owned stage entries')
    exact_scenarios = {sid:gid for _,p in entries.values()
        for sid,gid in p.get('original_global_scenarios',{}).get('group_ids',{}).items()}
    print('CHECKPOINT original Global scenario bindings',json.dumps(exact_scenarios,sort_keys=True))


if __name__ == '__main__':
    main()
