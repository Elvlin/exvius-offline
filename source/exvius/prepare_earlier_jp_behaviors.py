"""Recover same-JP-unit training profiles and retained native skill behaviors.

Original enemy part pointers remain absent. These explicitly authored bindings
use owned original actions and same-identity JP unit records, never Global
same-name substitutes or an invented enemy skill.
"""
import hashlib
import csv
import copy
import json
from pathlib import Path
import re
import zipfile

from decode_client_data import decode
from recover_jp_event_art import original_tables

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources/Battle recovery'
UNITS={
 '9990977':'346000107','9990987':'346000307','9990997':'346000407',
 '10003608':'348000107','10003609':'349000107','10003610':'309000507',
 '10003611':'350000107','10003612':'351000107','10003613':'346000507','10003614':'346000607',
 '10003615':'346000707','10003707':'346000907','10003807':'346000807',
 '9992605':'312000805','9992705':'312000905','9992805':'312000705','9992905':'312000505',
 '9993005':'312000605','9993105':'312000105','9993205':'312000205','9993305':'312000305','9993404':'312000404',
}
# These eleven actors previously had no retained enemy skillset. Additional
# numeric profiles must not accidentally acquire an authored behavior binding.
ORIGINALLY_NORMAL_ONLY=(
 '9990977','10003608','10003609','10003610','10003611','10003612',
 '10003613','10003614','10003615','10003707','10003807',
)
PRESERVE_RETAINED_BEHAVIOR={'9990987','9990997'}
# Child abilities are linked by the exact native cooldown wrapper owned by this
# same unit form. Player-only cooldown commands are not sent to enemy AI.
SIGNATURES={
 '9990977':('1189040',None,'physical'),
 '10003608':('1423070',None,'physical'),
 '10003609':('1424080',None,'magic'),
 '10003610':('1425070',None,'physical'),
 '10003611':('1428090',None,'physical'),
 '10003612':('1429221','1429220','physical'),
 '10003613':('1436190',None,'drain'),
 '10003614':('1311141','1311140','ally_heal'),
 '10003615':('1438080',None,'physical'),
 '10003707':('1443080',None,'physical'),
 '10003807':('1444231','1444230','magic'),
}


def nd(path):
    return [json.loads(line)for line in path.read_text(encoding='utf8').splitlines()if line]


def signature_behaviors(profiles,units):
    """Author easy training adaptations of each exact JP form's own action."""
    source_path=BASE.parent/'original-unit-content.json'
    document=json.loads(source_path.read_text(encoding='utf8'))
    abilities={r['Ga5V42LZ']:r for r in document['tables']['F_ABILITY_MST']['rows']}
    labels_path=BASE.parent/'unit-text-mapped-en.json'
    labels=json.loads(labels_path.read_text(encoding='utf8'))['F_TEXT_ABILITY_NAME']
    mapping_path=BASE.parent/'native-unit-id-map.json'
    mapping=json.loads(mapping_path.read_text(encoding='utf8'))['mappings']['F_ABILITY_MST']
    native_path=ROOT/'Japan content/Shared sources/memorial_battle_decoded/F_MONSTER_SKILL_MST.ndjson'
    native={r['6E5u1xrs']:r for r in nd(native_path)}
    native_sets={r['A5x02C6a']:r for r in nd(ROOT/'data/mst_decoded/F_MONSTER_SKILL_SET_MST.ndjson')}
    # Only these monster-only schema defaults are borrowed. No donor name,
    # identity, effects, element, targets or visual resources are copied.
    templates={'physical':'175410','magic':'110060','drain':'175410','ally_heal':'173800'}
    calibration={'physical':'219016','magic':'219017','ally_heal':'173800'}
    ai=[r for r in nd(ROOT/'data/mst_decoded/F_AI_MST.ndjson')if r['8a6gAwN9']=='3']
    if len(ai)!=2 or ai[0]['ixDq7yJ8']!='30.00' or not ai[0]['z5hB3P01'].startswith('skill@') or not ai[1]['z5hB3P01'].startswith('attack@'):
        raise ValueError('Original generic native AI3 changed')
    original_parts_path=native_path.with_name('F_MONSTER_PARTS_MST.ndjson')
    original_parts={r['xqartN26']:r for r in nd(original_parts_path)}
    original_sets={r['A5x02C6a']:r for r in nd(native_path.with_name('F_MONSTER_SKILL_SET_MST.ndjson'))}
    friendly_precedents=[]
    for enemy,set_id,skill_id in (('105037101','105037101','219698'),('105031400','105031400','220697')):
        part=original_parts[enemy];skill=native[skill_id]
        if part['8a6gAwN9']!='3'or part['A5x02C6a']!=set_id or skill_id not in original_sets[set_id]['7qxLC5hP'].split(','):
            raise ValueError('Original native AI3 friendly-heal binding changed')
        if (skill['2kq0BpnD'],skill['a4hXTIm0'],skill['oPD4yL58'])!=('26','2','1'):
            raise ValueError('Original native friendly percent-heal grammar changed')
        friendly_precedents.append({'original_enemy_id':enemy,'original_skillset_id':set_id,'original_skill_id':skill_id,'original_skill_name':skill['G4L0YIB2'],'native_ai':'3','native_ai_skill_action_target_selector':ai[0]['piK07TV4'],'native_friend_target':'2','native_single_target':'1','native_effect':'26','native_parameters':skill['Ha9G5sCS'],'basis':'Retained original enemy part, original skillset and original friendly healing skill use the same generic AI3. No dedicated AI clone is required.'})
    by_graphic={p['graphic_id']:p for p in profiles}
    skill_rows=[];skillsets=[];bindings={}
    for index,graphic in enumerate(ORIGINALLY_NORMAL_ONLY,1):
        profile=by_graphic[graphic];sid,parent,role=SIGNATURES[graphic]
        owner=parent or sid
        acquired={str(s['id'])for s in units[profile['source_unit_id']]['skills']if isinstance(s['rarity'],int)and s['rarity']<=7}
        if owner not in acquired:
            raise ValueError('Signature not owned by this exact JP form: '+graphic)
        if parent and (abilities[parent]['2kq0BpnD']!='130' or abilities[parent]['Ha9G5sCS'].split(',')[0]!=sid):
            raise ValueError('Original cooldown child linkage changed: '+sid)
        original=abilities[sid]
        name=labels.get('MST_ABILITY_NAME_'+mapping.get(sid,sid))
        if not name or name in ('NA','N/A')or re.search('[\u3040-\u30ff\u3400-\u9fff]',name):
            raise ValueError('Missing existing reviewed English signature name: '+sid)
        template=native[templates[role]]
        common={k:v for k,v in original.items()if k in template}
        row=copy.deepcopy(template);row.update(common)
        new_id=str(879510000+index);set_id=str(879520000+index)
        expected_set={'A5x02C6a':set_id,'G4L0YIB2':name,'7qxLC5hP':','.join([new_id]+['']*60)}
        if new_id in native or (set_id in native_sets and native_sets[set_id]!=expected_set):
            raise ValueError('Authored daily skill identity collides: '+graphic)
        row.update({'6E5u1xrs':new_id,'G4L0YIB2':name,'8cY9hejo':'0'})
        changes={'8cY9hejo':{'source':original['8cY9hejo'],'authored':'0','basis':'Retained daily enemy skills219016/219017 have no MP cost; enemy training action does not import a player cost/cooldown wrapper.'}}
        if role in ('physical','magic'):
            opcode='1'if role=='physical'else'15'
            if original['2kq0BpnD']!=opcode:
                raise ValueError('Only direct damage is selected for this training signature')
            position=6 if role=='physical'else 5
            values=original['Ha9G5sCS'].split(',')
            target=native[calibration[role]]['Ha9G5sCS'].split(',')[position]
            before=values[position];values[position]=target
            row['Ha9G5sCS']=','.join(values)
            changes['damage_coefficient']={'source_percent':int(before),'authored_percent':int(target),'original_native_baseline_skill':calibration[role],'basis':'Same-event retained daily character battle120% enemy potency. Type, element, targets, hit frames/weights and original signature VFX remain source-derived; not player NV damage.'}
        elif role=='drain':
            if original['2kq0BpnD']!='25'or original['Ha9G5sCS']!='30,100,100':
                raise ValueError('Original easy physical HP-drain signature changed')
            changes['damage_coefficient']={'source_percent':100,'authored_percent':100,'hp_drain_percent':30,'basis':'Exact original same-unit physical1x HP-drain action is already at the retained daily enemy potency.'}
        else:
            # Fullheal's player row has a zero-value buff clause followed by a
            # 100000-flat heal. Native Healing Light173800 supplies the proven
            # single-ally10% HP grammar, without changing friendly targeting.
            heal=native[calibration[role]]
            if original['2kq0BpnD']!='3@2'or original['Ha9G5sCS'].split('@')[0]!='0,0,0,0,0,0,0':
                raise ValueError('Original Fullheal action shape changed')
            for field in ('a4hXTIm0','oPD4yL58','PI18xnkD','a9DvZ70c'):
                row[field]=original[field].split('@')[-1]
            if (row['a4hXTIm0'],row['oPD4yL58'])!=('2','1')or(heal['a4hXTIm0'],heal['oPD4yL58'])!=('2','1'):
                raise ValueError('Healing must remain one ally, not a hostile player target or caster-only substitute')
            row['2kq0BpnD']=heal['2kq0BpnD'];row['Ha9G5sCS']=heal['Ha9G5sCS']
            changes['healing']={'source_effects':original['2kq0BpnD'],'source_parameters':original['Ha9G5sCS'],'authored_effect':'26','authored_parameters':heal['Ha9G5sCS'],'original_native_baseline_skill':'173800','basis':'Explicit easy-training adaptation:10%HP to one enemy-side ally using original native Healing Light grammar. Source Fullheal English name, friendly target, own VFX and heal timing retained. Zero-only buff removed; no invented flat amount or player100000 heal.'}
            changes['healing']['native_AI3_friendly_heal_precedents']=friendly_precedents
            changes['healing']['native_precedent_parts_source']=original_parts_path.relative_to(ROOT).as_posix()
        # Raw source effect IDs are intentional. The existing battle importer
        # performs typed F_EFFECT_GROUP_MST remapping together with other JP FX.
        profile['signature_behavior']={
            'source_unit_id':profile['source_unit_id'],'source_ability_id':sid,
            'source_owner_ability_id':owner,'source_cooldown_wrapper':parent,
            'source_name':original['G4L0YIB2'],'english_name':name,'role':role,
            'source_native_row_sha256':hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')).hexdigest(),
            'native_monster_only_template_id':templates[role],
            'copied_original_common_fields':sorted(common),
            'authored_monster_only_fields':{k:row[k]for k in row if k not in original},
            'source_hit_frames_and_weights':original['a9DvZ70c'],
            'source_effect_frame_groups':original['5A8SmwyC'],
            'effect_group_domain':'Original JP IDs; apply the existing typed effect-group map on import.',
            'calibration':changes,'authored_skill_id':new_id,'authored_skillset_id':set_id,
            'native_ai':'3','ai_choice':'Original generic native AI3:30% signature skill and otherwise normal attack. One selected skill; no new AI rows or boss turn script.',
            'authorship':'Same-form JP signature with explicitly calibrated daily-training potency and authored selection. Not a recovered original enemy behavior.',
        }
        skill_rows.append(row)
        skillsets.append(expected_set)
        bindings[graphic]={'native_ai':'3','authored_skillset_id':set_id,'basis':profile['signature_behavior']['authorship']+' '+profile['signature_behavior']['ai_choice']}
    return skill_rows,skillsets,bindings,{'native_unit_content':source_path.relative_to(ROOT).as_posix(),'native_unit_content_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),'english_labels':labels_path.relative_to(ROOT).as_posix(),'native_enemy_templates':native_path.relative_to(ROOT).as_posix(),'native_enemy_templates_sha256':hashlib.sha256(native_path.read_bytes()).hexdigest(),'authored_daily_actor_count':len(skill_rows),'calibration_enemy_skill_ids':calibration,'static_dependency':'Import authored_skillsets into native F_MONSTER_SKILL_SET_MST; AI3 is already native. Add authored_skill_rows to the battle bundles; do not replace immutable recovered F_* rows.'}


def normalized(value):
    return str(value).replace(' ','').replace('\u3000','')


def main():
    source=ROOT/'Japan content/Shared sources/ffbe-jp-ea7d9fa82659.zip'
    with zipfile.ZipFile(source)as archive:
        member=next(n for n in archive.namelist()if n.endswith('/units.json'))
        raw=archive.read(member);units=json.loads(raw)
    _,_,manifest=original_tables()
    unit_source=ROOT/'Japan content/Shared sources/jp_andapp/Ver1355_SsidX62G.dat'
    unit_raw=unit_source.read_bytes()
    _,native_rows=decode(unit_raw,manifest['SsidX62G']['key'])
    native={r['3HriTp6B']:r for r in native_rows}
    dictionary_source=ROOT/'Japan content/Shared sources/jp_andapp/Ver906_1r6jb9wB.dat'
    _,ds=decode(dictionary_source.read_bytes(),'wL4N16V3')
    dictionary={r['V9j8wJcC']:r for r in ds}
    profiles=[]
    for graphic,uid in UNITS.items():
        unit=units[uid];row=native[uid]
        if normalized(unit['name'])!=normalized(dictionary[graphic]['G4L0YIB2'])or normalized(row['G4L0YIB2'])!=normalized(unit['name']):
            raise ValueError('Same-JP-unit identity mismatch: '+graphic+':'+uid)
        entry=unit['entries'][uid]
        stats={k:int(entry['stats'][k][1])for k in ('HP','MP','ATK','DEF','MAG','SPR')}
        if not all(v>0 for v in stats.values()):raise ValueError('Incomplete original maximum-level stats')
        motion=ROOT/'Japan content/Recovered assets/monsters'/graphic/('monster_atk_cgs_'+graphic+'.csv')
        motion_raw=motion.read_bytes()
        duration=sum(int(r[3])for r in csv.reader(motion_raw.decode('utf8').splitlines())if r)
        if max(entry['attack_frames'])>duration:raise ValueError('JP-unit normal-hit frame outside original monster motion: '+graphic)
        form_art_proof=[]
        if graphic in PRESERVE_RETAINED_BEHAVIOR:
            for kind in ('anime','cgg','atk_cgs','idle_cgs','magic_atk_cgs','limit_atk_cgs'):
                extension='png'if kind=='anime'else'csv'
                monster=ROOT/'Japan content/Recovered assets/monsters'/graphic/('monster_'+kind+'_'+graphic+'.'+extension)
                player=ROOT/'Japan content/Recovered assets/units'/uid/('unit_'+kind+'_'+uid+'.'+extension)
                if monster.read_bytes()!=player.read_bytes():
                    raise ValueError('Daily profile must match this exact original JP form artwork/motion: '+graphic+':'+kind)
                form_art_proof.append({'kind':kind,'monster_file':monster.relative_to(ROOT).as_posix(),'unit_file':player.relative_to(ROOT).as_posix(),'same_bytes_sha256':hashlib.sha256(monster.read_bytes()).hexdigest()})
        profiles.append({'graphic_id':graphic,'source_unit_id':uid,'source_name':unit['name'],
            'stats':stats,'element_resist':entry['element_resist'],'status_resist':entry['status_resist'],
            'native_attack_fields':{key:row[key]for key in ('5A8SmwyC','a9DvZ70c','7KYufEd5','w04FtZqB','rtw4F6hn','rB70Ls63')},
            'attack_count':entry['attack_count'],'attack_frames':entry['attack_frames'],
            'original_monster_attack_cgs_sha256':hashlib.sha256(motion_raw).hexdigest(),
            'original_monster_attack_delay_total':duration,
            'same_form_asset_proof':form_art_proof,
            'authorship':'Daily training enemy uses this exact JP unit form maximum-level base stats and original normal-attack presentation. This is an authored training profile, not recovered original enemy stats.'})
    authored_skills,authored_sets,authored_bindings,signature_sources=signature_behaviors(profiles,units)
    result={'schema':1,'source_archive':source.relative_to(ROOT).as_posix(),'source_member':member,
            'source_member_sha256':hashlib.sha256(raw).hexdigest(),
            'original_native_unit_master':unit_source.relative_to(ROOT).as_posix(),'original_native_unit_sha256':hashlib.sha256(unit_raw).hexdigest(),
            'source_search':'Exact original body/part IDs absent from retained native tables and original archive. Eleven daily actors lack retained enemy skillsets; their own same-form JP signatures are now explicitly calibrated easy-training adaptations. Additional Yao/Poron profiles have six exact monster/unit artwork and motion byte matches and leave retained101-slot sets and current AI pointers unchanged.',
            'profiles':profiles,
            'originally_normal_attack_only_graphic_ids':list(ORIGINALLY_NORMAL_ONLY),
            'normal_attack_only_graphic_ids':[],
            'preserve_retained_behavior_graphic_ids':sorted(PRESERVE_RETAINED_BEHAVIOR),
            'authored_skill_rows':authored_skills,'authored_skillsets':authored_sets,'authored_ai_rows':[],
            'signature_sources':signature_sources,
            'bindings':{'2014010':{'native_ai':'3','basis':'Authored minor-enemy mix using original AI3 and retained Bite skill217156.'},
                        '2121710':{'native_ai':'3','basis':'Authored minor-enemy mix using original AI3, retained BlueFlame217154 and original caster-targeted Heal217155. Original raw Heal effect restores10%HP to caster.'},
                        '2251610':{'native_ai':'3','basis':'Authored minor-enemy mix using original AI3 and both retained native physical attacks217157/217158.'},
                        **{g:{'native_ai':'2','basis':'Authored daily opponent uses original native skill-only AI2 and its retained exact character special-move skillset.'}for g in UNITS if g.startswith('999')and g!='9990977'and g not in PRESERVE_RETAINED_BEHAVIOR},
                        **authored_bindings}}
    (BASE/'same-jp-unit-behaviors.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'same_JP_unit_profiles':len(profiles),'retained_skill_behavior_versions':19,'authored_same_form_training_signatures':len(authored_skills),'explicit_training_normal_attack_versions':0,'Yao_Poron_retained_behavior_preserved':True}))


if __name__=='__main__':main()
