"""Assemble earlier JP encounters with explicit, source-tagged reconstruction.

Original phase, lottery and group rows remain authoritative. Missing server
body records use original JP dictionary/model identities, published observed
statistics where available and difficulty-matched native numeric profiles for
the remaining fields. Those fields are authored adaptations, never originals.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import IndexSource, derive_mission, resolve_pool
from restore_event_battles import ReconstructionSource
from decode_client_data import decode
from earlier_jp_enemy_profiles import build_profiles

BASE = ROOT / 'Japan content/Earlier JP crossovers'
GRAPH = BASE / 'Sources/Event graph'
OUT = BASE / 'Sources/Battle recovery'
ORIGINAL = ROOT / 'Japan content/Shared sources/memorial_battle_decoded'
NAMES = {
 '1054610':'Eliminator', '1060411':'Killing Machine', '1083410':'Fire Phantom',
 '2014010':'Hound','2015810':'Polar Drake','2034510':'Peg Powler','2045810':'Ifrit',
 '2081910':'Sylph','2082010':'Fire Spirit','2100511':'Golem','2121710':'Ghost',
 '2251610':'Orc','3014310':'Beast King Gnon','3014311':'Beast King Gnon (True Form)',
 '3015210':'Megalith Beast','3032110':'Devil Tentacler','3032210':'Armored Beast Dafora',
 '3044810':'Kzinssie','3045010':'Byunei','3082410':'Flame Tyrant','3091810':'Dark King Gorgona',
 '3121511':'Restless Armour','3254410':'Demon King Jagan','3259310':'Golden Lion Princess',
 '4030310':'Charybdis','4030410':'Arlan Weld','4040110':'Four Sinistrals',
 '4041210':'Nightmare (Bondage)','5050010':'Wagnas','5050110':'Noel','5050210':'Dantarg',
 '5050310':'Kzinssie','5050410':'Bokhohn','5050510':'Subier','5050610':'Rocbouquet',
 '5050810':'Seven Heroes','5070010':'Nef-Garmud','9990977':'Arus','9990987':'Yao',
 '9990997':'Poron','9992605':'Divine Fist Kevin','9992705':'Evil Shaman Charlotte',
 '9992805':'Fenrir Knight Riesz','9992905':'Duran','9993005':'Angela','9993105':'Riesz',
 '9993205':'Hawkeye','9993305':'Kevin','9993404':'Charlotte',
 '10003608':'Albert','10003609':'Rocbouquet','10003610':'Ellen','10003611':'Asellus',
 '10003612':'Gustave XIII','10003613':'Hero Alan','10003614':'Hero Astea',
 '10003615':'Sea King II Cesarion','10003707':'Hero Arus','10003807':'Imagin',
}
STATS = ('9NBV1XCS','Pn5w9dfh','84FJM3PD','T8xMDAZ4')


def nd(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def indexed(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def reference_profiles():
    ref = {}
    document = json.loads((OUT / 'saga-roto-published-reference.json').read_text(encoding='utf8'))
    for row in document['profiles']:
        ref[row['enemy_id']] = dict(row, basis='Published original in-game Libra screenshot')
    other = json.loads((OUT / 'imperial-mh-bravely-reference.json').read_text(encoding='utf8'))
    for row in other['imperial_saga']['bosses']:
        vector = [row.get('element_resists_percent', {}).get(k, 0)
                  for k in ('fire','ice','lightning','water','wind','earth','light','dark')]
        ref[row['enemy_id']] = {'hp': row['HP'], 'mp': row['MP'], 'race': row['race'],
            'element_resists_percent': vector, 'ailment_resists_percent':[100,100,100,100,50,100,100,100],
            'guide_url': other['imperial_saga']['source'], 'basis':'Published Awakening encounter table'}
    for row in other['monster_hunter']['tiers']:
        body = row['parts'][0]
        ref[row['enemy_id']] = {'hp':body['HP'],'mp':body['MP'],'level':row['level'],
            'element_resists_percent':[-50,-50,0,0,0,0,0,0],
            'ailment_resists_percent':[100,0,100,100,100,100,100,100],
            'guide_url':other['sources']['mh_event']['url'], 'basis':'Published exact raid tier and original Libra screenshot',
            'tail':row['parts'][1] if len(row['parts'])>1 else None}
    for row, vector, url in (
        (other['bravely']['charybdis']['awakening'],[0,0,0,100,0,-50,0,0],other['bravely']['charybdis']['source']),
        (other['bravely']['arlan_weld'],[0,0,0,0,200,0,0,0],other['bravely']['arlan_weld']['source'])):
        ref[row['enemy_id']] = {'hp':row['HP'],'mp':row['MP'],'level':row['level'],
            'element_resists_percent':vector,'ailment_resists_percent':[100]*8,
            'guide_url':url,'basis':'Published original encounter table and Libra screenshot'}
    rewards=json.loads((BASE/'Sources/Event rewards/published-event-rewards.json').read_text(encoding='utf8'))
    for row in rewards['events']['742']['boss_HP_MP']:
        index=int(row['mission_id'][-2:])-1
        ref['40401100'+str(index)]={'hp':row['HP'],'mp':row['MP'],'level':row['level'],
            'element_resists_percent':[0]*8,'ailment_resists_percent':[100]*8,
            'guide_url':'https://ffbe.gorillawiki.jp/entry/11038',
            'basis':'Published exact difficulty table; allfour original sections reviewed'}
    return ref, other


def stage_daily_skillsets(behavior, apply=False):
    """Use the established same-version native importer for new skillsets."""
    rows=behavior.get('authored_skillsets', [])
    if not rows:
        return None
    from recover_jp_unit_content import Inputs
    from recover_earlier_jp_event_rewards import contract_table
    from apply_jp_unit_tables import apply_contract
    inputs=Inputs()
    try:
        current={r['A5x02C6a']:r for r in inputs.current('F_MONSTER_SKILL_SET_MST')}
        for row in rows:
            previous=current.get(row['A5x02C6a'])
            if previous is not None and previous != row:
                raise ValueError('Authored daily skillset identity is already used: '+row['A5x02C6a'])
        contract={'schema':1,'status':'VALIDATED_READY_TO_APPLY',
            'scope':'Eleven explicitly authored earlier-JP daily-character signature skillsets',
            'tables':[contract_table(inputs,'F_MONSTER_SKILL_SET_MST','A5x02C6a',rows,'replace')],
            'authorship':'Enemy-side skill selection and calibrated potency are reconstructed; original player ability sources are retained separately.',
            'resource_versions_changed':False,'saves_changed':False,'apk_built':False}
        path=OUT/'authored-daily-skillset-import.json'
        path.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    finally:
        inputs.close()
    if apply:
        apply_contract(path,apply=True,receipt_path=ROOT/'logs/jp-daily-enemy-skillset-integration.json')
    return path.relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--effect-map',type=Path,help='Final original JP typed effect-group mapping supplied by the VFX importer.')
    args = parser.parse_args()
    effect_map={};effect_source=None
    prior_path=OUT/'earlier-battle-reconstruction.json'
    if not args.effect_map and prior_path.is_file():
        prior=json.loads(prior_path.read_text(encoding='utf8'))
        if prior.get('effect_group_map_source'):args.effect_map=ROOT/prior['effect_group_map_source']
    if args.effect_map:
        effect_source=args.effect_map.resolve()
        if not effect_source.is_relative_to(ROOT):raise ValueError('Effect map must be a permanent project source')
        effect_document=json.loads(effect_source.read_text(encoding='utf8'))
        effect_map=effect_document['mappings']['F_EFFECT_GROUP_MST']
    def effect_frames(row):
        result=dict(row);clauses=[]
        for clause in re.split('([&@])',row.get('5A8SmwyC','')):
            if clause in ('&','@'):
                clauses.append(clause)
                continue
            fields=clause.split(':')
            if len(fields)>=2:fields[1]=effect_map.get(fields[1],fields[1])
            clauses.append(':'.join(fields))
        if '5A8SmwyC'in row:result['5A8SmwyC']=''.join(clauses)
        return result
    evidence = json.loads((BASE / 'stage-gap-evidence.json').read_text(encoding='utf8'))
    source_tables = {p.stem: nd(p) for p in GRAPH.glob('F_*.ndjson')}
    missions = {r['qo3PECw6']: r for r in source_tables['F_MISSION_MST']}
    phases = indexed(source_tables['F_MISSION_PHASE_MST'], 'qo3PECw6')
    pools = indexed(source_tables['F_BATTLE_LOTTERY_MST'], 'c2gnh6Jd')
    groups = indexed(source_tables['F_BATTLE_GROUP_MST'], '2fY1IomW')
    _, dictionary_rows = decode((ROOT / 'Japan content/Shared sources/jp_andapp/Ver906_1r6jb9wB.dat').read_bytes(), 'wL4N16V3')
    dictionary = {r['V9j8wJcC']: r for r in dictionary_rows}
    original_monsters = {r['xqartN26']: r for r in nd(ORIGINAL / 'F_MONSTER_MST.ndjson')}
    original_parts = indexed(nd(ORIGINAL / 'F_MONSTER_PARTS_MST.ndjson'), 'xqartN26')
    original_missions = {r['qo3PECw6']: r for r in nd(ORIGINAL / 'F_MISSION_MST.ndjson')}
    original_phases = indexed(nd(ORIGINAL / 'F_MISSION_PHASE_MST.ndjson'), 'qo3PECw6')
    original_pools = indexed(nd(ORIGINAL / 'F_BATTLE_LOTTERY_MST.ndjson'), 'c2gnh6Jd')
    original_groups = indexed(nd(ORIGINAL / 'F_BATTLE_GROUP_MST.ndjson'), '2fY1IomW')
    templates = []
    for mid, mission in original_missions.items():
        if not str(mission.get('52KBR9qV','')).isdigit():
            continue
        for phase in original_phases.get(mid, []):
            if phase.get('gou39JeI') != '2':
                continue
            for lottery in original_pools.get(phase['6uIYE15X'], []):
                for slot in original_groups.get(lottery['2fY1IomW'], []):
                    iid = slot['xqartN26']
                    for part in original_parts.get(iid, []):
                        if (part['6Yc4RkdM']=='1' and iid in original_monsters and
                            int(iid)<800000000 and all(str(part.get(k,'')).isdigit() and int(part[k])>0 for k in ('fh31sk7B','PC97pWQj',*STATS))):
                            templates.append((int(mission['52KBR9qV']), mid, part))
    if not templates:
        raise ValueError('No original native numeric reconstruction templates')
    references, other = reference_profiles()
    behavior=json.loads((OUT/'same-jp-unit-behaviors.json').read_text(encoding='utf8'))
    unit_profiles={r['graphic_id']:r for r in behavior['profiles']}
    numeric_profiles=build_profiles(references, unit_graphics=unit_profiles)
    override_path=OUT/'enemy-behavior-overrides.json'
    override_document=json.loads(override_path.read_text(encoding='utf8'))
    role_overrides={(r['enemy_id'],r['part_num']):r for r in override_document['overrides']}
    contexts = defaultdict(set)
    for mid in missions:
        for phase in phases.get(mid, []):
            if phase.get('gou39JeI') != '2':
                continue
            for lottery in pools[phase['6uIYE15X']]:
                for slot in groups[lottery['2fY1IomW']]:
                    contexts[slot['xqartN26']].add(mid)
    native_ai = nd(OUT / 'F_AI_MST.ndjson')
    ai_ids = {r['8a6gAwN9'] for r in native_ai}
    sets = {r['A5x02C6a']: r for r in nd(OUT / 'F_MONSTER_SKILL_SET_MST.ndjson')}
    skill_rows = nd(OUT / 'F_MONSTER_SKILL_MST.ndjson')
    for row in behavior.get('authored_skillsets', []):
        if row['A5x02C6a'] in sets:
            raise ValueError('Authored daily skillset collides with retained original')
        sets[row['A5x02C6a']]=row
    original_skill_ids={r['6E5u1xrs'] for r in skill_rows}
    for row in behavior.get('authored_skill_rows', []):
        if row['6E5u1xrs'] in original_skill_ids:
            raise ValueError('Authored daily skill collides with retained original')
        skill_rows.append(row)
    reviewed=json.loads((OUT/'monster-skill-english.json').read_text(encoding='utf8'))
    english={r['skill_id']:r for r in reviewed['rows']}
    for row in skill_rows:
        translation=english.get(row['6E5u1xrs'])
        if translation:
            if row['G4L0YIB2']!=translation['source']:
                raise ValueError('Reviewed monster move source differs: '+row['6E5u1xrs'])
            row['G4L0YIB2']=translation['english']
    monsters, parts, provenance = [], [], []
    missing = set(evidence['summary']['missing_monster_ids'])
    if set(contexts) - missing != set(original_monsters) & set(contexts):
        raise ValueError('Original owned enemy identities changed')
    for iid in sorted(missing, key=int):
        candidate = evidence['missing_body_dictionary_candidates'][iid]
        graphic = candidate['candidate_graphic_id']
        if dictionary[graphic]['G4L0YIB2'] != candidate['dictionary_row']['G4L0YIB2']:
            raise ValueError('Original JP graphic dictionary identity mismatch: '+iid)
        model = ROOT / 'Japan content/Recovered assets/monsters' / graphic
        if not model.is_dir():
            raise ValueError('Original JP recovered model missing: '+graphic)
        mids = sorted(contexts[iid], key=int)
        target = max(int(missions[mid]['52KBR9qV']) for mid in mids)
        # Keep a complete native schema. Combat values below come from a
        # calibrated cohort or the exact same JP unit, not this schema donor.
        diff, donor_mid, template = min(templates, key=lambda t:(abs(t[0]-target), abs(int(t[2].get('7wV3QZ80') or 1)-99), int(t[1]), int(t[2]['xqartN26'])))
        name = NAMES[graphic]
        part = copy.deepcopy(template)
        part.update({'xqartN26':iid,'G4L0YIB2':name,'6Yc4RkdM':'1',
            'a9qg8vnP':dictionary[graphic]['a9qg8vnP'],'3HriTp6B':'',
            'e56NZY42':'0','B6H34Mea':'0','7UR4J2SE':'0','ATM35pjf':'0',
            '9BetM2Ds':'','MZn8LC6H':'','3frn4ILX':'','IRf10dwx':'','e5xoiC84':'',
            'm28pD1GM':'','hn42BL3Q':'0,0,0,0,0,0,0,0,0',
            'D9Nb7jgd':'0,0,0,0,0,0,0,0','Rcqa1Zt7':'0,0,0,0,0,0,0',
            '4Y2DGP7m':'1,1','rtw4F6hn':'0','rB70Ls63':'0'})
        exact = references.get(iid)
        numeric_profile=numeric_profiles.get(iid)
        if graphic not in unit_profiles:
            if numeric_profile is None:
                raise ValueError('Missing calibrated numeric profile: '+iid)
            part.update(numeric_profile['native_fields'])
        hp_basis = 'Authored era/race/encounter-role cohort estimate; exact published values override estimates'
        if exact:
            part.update(fh31sk7B=str(exact['hp']),PC97pWQj=str(exact['mp']))
            if 'level' in exact: part['7wV3QZ80']=str(exact['level'])
            part['hn42BL3Q']=','.join(map(str,exact['element_resists_percent']+[0]))
            part['D9Nb7jgd']=','.join(map(str,exact['ailment_resists_percent']))
            hp_basis=exact['basis']
        elif numeric_profile and numeric_profile['trace'].get('published_anchor'):
            hp_basis = 'Authored same-model published-anchor adaptation using empirical comparable-enemy tier ratios; not original tier values'
        set_candidates = [k for k in sets if k[:-2] == iid[:-2]]
        set_id = iid if iid in sets else (min(set_candidates,key=lambda k:abs(int(k)-int(iid))) if set_candidates else '0')
        ai_candidates = [k for k in ai_ids if k[:-2] == iid[:-2]]
        ai_id = iid if iid in ai_ids else (min(ai_candidates,key=lambda k:abs(int(k)-int(iid))) if ai_candidates else '1')
        generic = False
        if ai_id=='1' and set_id!='0' and len(sets[set_id]['7qxLC5hP'].split(','))==101:
            # These are owned generic native interpreters, not a newly invented
            # AI grammar. Gnon's first six five-slot blocks match the published
            # preemptive and five-turn sequence exactly; Flame Tyrant likewise
            # has a published preemptive block. Other sets start on turn one.
            ai_id = '117' if set_id in ('301431103','308241000') else '116'
            generic = True
        behavior_binding=behavior['bindings'].get(graphic)
        unit_profile=unit_profiles.get(graphic)
        if behavior_binding:
            ai_id=behavior_binding['native_ai']
            set_id=behavior_binding.get('authored_skillset_id',set_id)
            generic=False
        if unit_profile:
            part.update(unit_profile['native_attack_fields'])
            for stat,token in zip(('ATK','DEF','MAG','SPR'),STATS):
                part[token]=str(unit_profile['stats'][stat])
            if not exact:
                part['fh31sk7B']=str(unit_profile['stats']['HP'])
                part['PC97pWQj']=str(unit_profile['stats']['MP'])
                part['hn42BL3Q']=','.join(map(str,unit_profile['element_resist']+[0]))
                part['D9Nb7jgd']=','.join(map(str,unit_profile['status_resist']))
                hp_basis='Authored training profile using exact same-JP-unit maximum-level base HP/MP, not unrelated enemy scaffolding or original server enemy values.'
        role_override=role_overrides.get((iid,'1'))
        if role_override:
            ai_id=role_override['target_fields']['8a6gAwN9']
            set_id=role_override['target_fields']['A5x02C6a']
        part['8a6gAwN9'], part['A5x02C6a'] = ai_id, set_id
        skillset_basis=('Preserved native same-model set with reconstructed part pointer'
                        if set_id!='0' else 'No original skillset owned')
        if behavior_binding and behavior_binding.get('authored_skillset_id'):
            skillset_basis='Authored enemy-side adaptation of this exact JP unit form signature ability; calibrated potency and selection are not original enemy behavior'
        if role_override:
            skillset_basis='Retained same-model set selected by documented battle role, tier labels and native skill-slot contract; original body/part pointer remains inferred'
        monsters.append({'xqartN26':iid,'G4L0YIB2':name,'V9j8wJcC':graphic})
        parts.append(part)
        if exact and exact.get('tail'):
            tail=copy.deepcopy(part)
            tail.update({'6Yc4RkdM':'2','G4L0YIB2':name+' Tail',
                         'fh31sk7B':str(exact['tail']['HP']),'PC97pWQj':str(exact['tail']['MP'])})
            tail_override=role_overrides.get((iid,'2'))
            if tail_override:
                tail.update(tail_override['target_fields'])
            parts.append(tail)
        provenance.append({'enemy_id':iid,'name':name,'original_graphic_id':graphic,
            'graphic_binding':'Reconstructed missing body field from original body-ID prefix and independently verified live JP dictionary. Original JP model bytes recovered.',
            'missions':mids,'hp_mp_basis':hp_basis,'published_reference':exact,
            'numeric_template':{'same_JP_source_unit':unit_profile['source_unit_id'],'basis':unit_profile['authorship']}if unit_profile else numeric_profile['trace'],
            'authored_fields':'Same-JP-unit base stats/resistances and native normal-attack presentation; enemy role and any adapted signature-skill selection explicitly authored.'if unit_profile else 'Era/race/encounter-role comparable native cohorts estimate missing combat stats. Schema/presentation defaults and absent enemy pointers are authored; resistances stay neutral unless independently observed. Not original server values.',
            'multipart': 'Published MH tail attached as authored PartsNum2 under original one-slot monster identity; original native part index/presentation unknown' if exact and exact.get('tail') else None,
            'ai_id':ai_id,'ai_basis':('Retained native AI with battle-role/tier/slot-derived pointer; see enemy-behavior-overrides.json. Original body/part pointers remain inferred.'if role_override else behavior_binding['basis']if behavior_binding else (('Reconstructed pointer to original generic five-action native interpreter with owned101-slot native skillset; published preemptive/turn block comparison where available' if generic else 'Preserved original same-model JP AI with reconstructed part pointer') if ai_id!='1' else 'Authored normal-attack fallback using verified original native AI1; original boss behavior not recovered')),
            'part_behaviors':[{'part_num':r['part_num'],'ai_id':r['target_fields']['8a6gAwN9'],
                               'skillset_id':r['target_fields']['A5x02C6a'],'classification':r['classification'],
                               'evidence_file':override_path.relative_to(ROOT).as_posix()}
                              for key,r in role_overrides.items()if key[0]==iid],
            'skillset_id':set_id,'skillset_basis':skillset_basis})
    output_tables = dict(source_tables)
    output_tables['F_MONSTER_MST'] = source_tables['F_MONSTER_MST'] + monsters
    if effect_map:
        parts=[effect_frames(row)for row in parts]
        skill_rows=[effect_frames(row)for row in skill_rows]
    output_tables['F_MONSTER_PARTS_MST'] = [effect_frames(row)for row in source_tables['F_MONSTER_PARTS_MST']] + parts
    output_tables['F_MONSTER_SKILL_SET_MST'] = list(sets.values())
    output_tables['F_MONSTER_SKILL_MST'] = skill_rows
    source = ReconstructionSource(IndexSource(), output_tables)
    bundles, nonbattle = {}, []
    for mid, mission in sorted(missions.items(), key=lambda p:int(p[0])):
        if not any(r.get('gou39JeI')=='2' for r in phases.get(mid, [])):
            nonbattle.append(mid)
            continue
        bundle = derive_mission(mid, source)
        bundle['1IfDqR4n']=[mission]
        bundles[mid]={'bundle':bundle,'basis':'Original JP phase/lottery/group graph with source-tagged reconstructed missing body records',
                      'reconstruction_source':'Japan content/Earlier JP crossovers/Sources/Battle recovery/earlier-battle-reconstruction.json'}
        combat=sorted((r for r in phases[mid]if r.get('gou39JeI')=='2'),key=lambda r:int(r['6v7y3QcJ']))
        if any(len([r for r in pools[p['6uIYE15X']]if int(r['ixDq7yJ8'])>0])>1 for p in combat):
            weighted=[]
            for phase in combat:
                alternatives=[]
                for row in pools[phase['6uIYE15X']]:
                    weight=int(row['ixDq7yJ8'])
                    if weight<=0:continue
                    fragment_tables=dict(output_tables)
                    fragment_tables['F_MISSION_PHASE_MST']=[phase]
                    fragment_tables['F_BATTLE_LOTTERY_MST']=[row]
                    fragment=derive_mission(mid,ReconstructionSource(IndexSource(),fragment_tables))
                    alternatives.append({'weight':weight,'group':row['2fY1IomW'],'bundle':fragment})
                weighted.append({'phase':phase['6v7y3QcJ'],'pool':phase['6uIYE15X'],'candidates':alternatives})
            bundles[mid]['jp_weighted_lottery']={'schema':1,'scope':'earlier-jp-28',
                'authority':'Original retained JP F_MISSION_PHASE_MST -> F_BATTLE_LOTTERY_MST -> F_BATTLE_GROUP_MST rows. No invented weights.',
                'phases':weighted}
    if len(bundles)!=117 or len(nonbattle)!=13:
        raise ValueError('Earlier stage coverage changed')
    skillset_import=stage_daily_skillsets(behavior,apply=args.apply)
    for table, rows in [('F_MONSTER_MST',monsters),('F_MONSTER_PARTS_MST',parts)]:
        (OUT / ('reconstructed-'+table+'.ndjson')).write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows),encoding='utf8')
    receipt={'schema':1,'status':'AUTHORED_RECONSTRUCTION_STAGED','battle_stages':len(bundles),'field_stages':nonbattle,
        'missing_original_bodies_recovered':0,'reconstructed_bodies':len(monsters),'reconstructed_parts':len(parts),
        'original_phase_rows':len(source_tables['F_MISSION_PHASE_MST']),'original_lottery_rows':len(source_tables['F_BATTLE_LOTTERY_MST']),
        'original_group_rows':len(source_tables['F_BATTLE_GROUP_MST']),'enemy_provenance':provenance,
        'numeric_method':'Comparable native enemy cohorts matched by release era, encounter role, race, difficulty and observed level/HP. Published values and exact same-JP-unit training profiles take precedence. Donor identities and calculations are recorded per enemy.',
        'numeric_cohort_profiles':len(numeric_profiles),'same_JP_unit_numeric_profiles':len(unit_profiles),
        'published_HP_MP_profiles':len(references),
        'behavior_role_overrides':{'source':override_path.relative_to(ROOT).as_posix(),
                                   'reviewed_part_bindings':len(role_overrides),
                                   'corrected_part_bindings':sum(r['changes_current_binding']for r in role_overrides.values())},
        'authored_daily_skillset_import':skillset_import,
        'authored_daily_signature_skills':len(behavior.get('authored_skill_rows',[])),
        'caveat':'Calibrated authored offline reconstruction is not original server battle fidelity. Original phases, lotteries, groups, retained enemy AI/skillsets and published profiles remain. Missing stats and pointers, plus daily signature-skill balancing/selection, are explicitly reconstructed. MH tails use published HP/MP and authored PartsNum2. Phone battle/field playback remains unverified.',
        'bundle_file':'Japan content/Earlier JP crossovers/Sources/Battle recovery/reconstructed-event-encounters.json'}
    if effect_source:
        receipt['effect_group_map_source']=effect_source.relative_to(ROOT).as_posix()
        receipt['effect_group_map_sha256']=sha(effect_source.read_bytes())
        receipt['effect_group_domain_sha256']=sha(json.dumps(effect_map,sort_keys=True,separators=(',',':')).encode('utf8'))
    (OUT / 'reconstructed-event-encounters.json').write_text(json.dumps({'missions':bundles,'local_monster_names':{r['enemy_id']:r['name']for r in provenance}},ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    if args.apply:
        target=ROOT/'source/server/event_encounters.json'
        document=json.loads(target.read_text(encoding='utf8'))
        before=dict(document['missions'])
        for mid,value in bundles.items():
            if mid in before and before[mid]!=value and before[mid].get('reconstruction_source')!=value['reconstruction_source']:
                raise ValueError('Existing encounter collision: '+mid)
            document['missions'][mid]=value
        document['local_monster_names'].update({r['enemy_id']:r['name']for r in provenance})
        if any(document['missions'][mid]!=value for mid,value in before.items() if mid not in bundles):
            raise ValueError('Unrelated encounter changed')
        target.write_text(json.dumps(document,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
        receipt['status']='APPLIED_WITH_DOCUMENTED_AUTHORED_FALLBACKS'
    (OUT/'earlier-battle-reconstruction.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'battle_stages':len(bundles),'field_stages':len(nonbattle),'bodies':len(monsters),'published_profiles':len(references)}))


if __name__=='__main__':
    main()
