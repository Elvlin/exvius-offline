"""Bind original JP-only effects without changing shared Global skill records."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from recover_jp_unit_content import Inputs, IDENTITIES, rewrite_row, text_specs
from apply_jp_unit_tables import apply_contract
from recover_earlier_jp_vfx import source_content

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'
DOMAINS={'F_ABILITY_MST':830000000,'F_MAGIC_MST':835000000,
    'F_LIMITBURST_MST':840000000,'F_EFFECT_GROUP_MST':850000000,
    'F_EFFECT_MST':860000000,'F_EQUIP_ITEM_MST':870000000,
    'F_MATERIA_MST':871000000,'F_ITEM_MST':872000000,'F_VISION_CARD_MST':873000000}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def main(apply=False):
    source=source_content()
    prior=json.loads((BASE/'native-unit-id-map.json').read_text(encoding='utf8'))
    art=json.loads((BASE/'original-unit-vfx-import.json').read_text(encoding='utf8'))
    aliases=dict(art['bmb_aliases'])
    # Native effect filenames may include a rotation clause. Keep every
    # original operand and rewrite only the filename before its first colon.
    for row in source['tables']['F_EFFECT_MST']['rows']:
        value=row.get('2HjxCGo6','');name,separator,operands=value.partition(':')
        if separator and name in aliases:aliases[value]=aliases[name]+separator+operands
    plan=copy.deepcopy(prior);maps=plan['mappings'];inputs=Inputs()
    legacy_frames=not prior.get('vfx_frame_groups',False)
    current={};occupied=set();source_tables=source['tables'];unresolved=[]
    try:
        for table,selection in source_tables.items():
            if not selection['rows']:continue
            current[table]=inputs.current(table)
            key=selection['key']
            if key:
                occupied.update(r[key]for r in current[table]);occupied.update(r[key]for r in selection['rows'])
        for mapping in maps.values():occupied.update(mapping.values())
        occupied.add('872100001') # Other task-owned JP event currency reservation.
        allocated={table:{}for table in DOMAINS}
        numeric={int(i)for i in occupied if i.isdecimal()}
        next_values={t:max([i for i in numeric if base<i<base+1000000]+[base])+1
            for t,base in DOMAINS.items()}
        def allocate(table,source_id):
            value=next_values[table]
            while str(value)in occupied:value+=1
            next_values[table]=value+1
            target=str(value);occupied.add(target);maps[table][source_id]=target;allocated[table][source_id]=target
        for row in source_tables['F_EFFECT_MST']['rows']:
            if row.get('2HjxCGo6')in aliases and row['h5t4yBm2']not in maps['F_EFFECT_MST']:
                allocate('F_EFFECT_MST',row['h5t4yBm2'])
        # Existing owned JP forks can change in place. A shared original
        # parent gets its own fork before any changed child reference is used.
        while True:
            count=0
            for table in DOMAINS:
                key=source_tables[table]['key']
                for row in source_tables[table]['rows']:
                    if row[key]in maps[table]:continue
                    old,_=rewrite_row(table,row,prior['mappings'],source_tables,prior.get('vfx_file_aliases'),legacy_frames)
                    new,_=rewrite_row(table,row,maps,source_tables,aliases)
                    if old!=new:allocate(table,row[key]);count+=1
            if not count:break
        additional={table:{}for table in maps}
        for table,mapping in maps.items():
            for original,target in mapping.items():
                old=prior['mappings'].get(table,{}).get(original,original)
                if old!=target:additional[table][old]=target
        patches=[];old_selected={};current_indices={}
        for table,selection in source_tables.items():
            if not selection['rows']:continue
            key=selection['key'];fields=[key]if key else IDENTITIES[table]
            if table=='F_UNIT_SERIES_LV_ACQUIRE_MST':
                old_selected[table]={'key':key,'rows':[]}
                continue
            old_selected[table]={'key':key,'rows':[]}
            current_indices[table]={tuple(r[f]for f in fields):r for r in current[table]}
            for row in selection['rows']:
                old,_=rewrite_row(table,row,prior['mappings'],source_tables,prior.get('vfx_file_aliases'),legacy_frames)
                identity=tuple(old[f]for f in fields);actual=current_indices[table].get(identity)
                if actual is None:raise ValueError('Current scoped JP dependency is missing: '+table+':'+str(identity))
                old_selected[table]['rows'].append(actual)
        for table,selection in source_tables.items():
            if not selection['rows']:continue
            key=selection['key'];fields=[key]if key else IDENTITIES[table];updates=[]
            if table=='F_UNIT_SERIES_LV_ACQUIRE_MST':
                roots={prior['mappings']['F_UNIT_MST'].get(r['woghJa61'],r['woghJa61'])for r in selection['rows']}
                groups={}
                for row in current[table]:
                    if row['woghJa61']in roots:groups.setdefault(row['woghJa61'],[]).append(row)
                for root,rows in groups.items():
                    rewritten=[rewrite_row(table,row,additional,old_selected)[0]for row in rows]
                    if rows!=rewritten:updates.extend(rewritten)
                operation='replace_groups'
            else:
                operation='replace'
                for row in selection['rows']:
                    old,_=rewrite_row(table,row,prior['mappings'],source_tables,prior.get('vfx_file_aliases'),legacy_frames)
                    new,pending= rewrite_row(table,row,maps,source_tables,aliases)
                    if old==new:continue
                    unresolved.extend(dict(p,table=table,source_identity=[row[f]for f in fields])for p in pending)
                    actual=current_indices[table][tuple(old[f]for f in fields)]
                    result=dict(actual)
                    for field,value in new.items():
                        if value!=old.get(field):
                            if actual.get(field)!=old.get(field):
                                self_default=(field=='6ZEyK95f' and key and old.get(field)==old.get(key)
                                    and actual.get(field)in ('','0',None))
                                if not self_default:
                                    raise ValueError('A scoped reference changed outside this VFX addendum: '+
                                        str((table,tuple(old[f]for f in fields),field,old.get(field),actual.get(field))))
                            result[field]=value
                    updates.append(result)
            if not updates:continue
            receipt=inputs.receipts['current:'+table];native=receipt['active_native_source']
            if not native:raise ValueError('No effective native baseline for '+table)
            filename=(native.get('member')or native['path']).rsplit('/',1)[-1]
            decoded=ROOT/'data/mst_decoded'/(table+'.ndjson')
            patches.append({'table':table,'identity_fields':fields,'operation':operation,
                'active_native_path':'mst/'+filename,'active_native_source':native,
                'active_native_sha256':native['sha256'],
                'decoded_baseline_sha256':sha(decoded.read_bytes()),'rows':updates})
        if unresolved:
            write(ROOT/'logs/jp-vfx-operand-review.json',{'references':unresolved})
            raise ValueError('Unresolved typed VFX references: '+str(unresolved[:5]))
        if not patches:
            print(json.dumps({'status':'VERIFIED_ALREADY_APPLIED','tables':0,'rows':0,
                'existing_import_receipts_preserved':True}))
            return
        english={}
        for master,_,table,prefix,_ in text_specs():
            reference='F_ABILITY_MST'if master=='F_ABILITY_EXPLAIN_MST'else master
            mapping=additional.get(reference,{})
            if not mapping:continue
            labels=inputs.text(table)
            for old,new in mapping.items():
                if prefix+old not in labels or not labels[prefix+old]:
                    raise ValueError('Missing existing reviewed English label for new VFX fork: '+table+':'+old)
                english.setdefault(table,{})[prefix+new]=labels[prefix+old]
        contract={'schema':1,'status':'VALIDATED_READY_TO_APPLY','scope':'Original JP VFX only; typed parent forks; existing Global rows untouched',
            'tables':patches,'additional_current_id_map':additional,'counts':{e['table']:len(e['rows'])for e in patches}}
        plan['vfx_file_aliases']=aliases;plan['vfx_import']='Japan content/Earlier JP crossovers/Sources/original-unit-vfx-import.json'
        plan['vfx_frame_groups']=True
        plan['vfx_additional_id_map']=additional
        write(BASE/'native-unit-vfx-import.json',contract);write(BASE/'native-unit-vfx-id-map.json',plan)
        write(BASE/'unit-vfx-english.json',english)
        if apply:
            if not art['status'].startswith('APPLIED'):raise ValueError('Install the original JP asset overlays before binding their names')
            apply_contract(BASE/'native-unit-vfx-import.json',True,ROOT/'logs/jp-unit-vfx-native-integration.json')
            write(BASE/'native-unit-id-map.json',plan)
            # Keep the reviewed translation inventory aware of the new typed
            # fork labels. Existing English corrections remain authoritative.
            path=BASE/'unit-text-mapped-en.json';labels=json.loads(path.read_text(encoding='utf8'))
            for table,values in english.items():labels.setdefault(table,{}).update(values)
            write(path,labels)
        print(json.dumps({'status':'APPLIED'if apply else 'VALIDATED_PREVIEW','tables':len(patches),
            'rows':sum(len(e['rows'])for e in patches),'new_forks':{t:len(v)for t,v in allocated.items()if v},
            'new_English_keys':sum(map(len,english.values()))}))
    finally:inputs.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
