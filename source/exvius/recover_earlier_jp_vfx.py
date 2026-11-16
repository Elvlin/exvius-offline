"""Recover the exact JP effects required by the tracked crossover units.

Existing Global members stay untouched. Conflicting JP files use separately
bound names; binary string-table replacements retain every original offset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from apply_jp_content import NativeCache
from decode_client_data import decode
from recover_jp_assets import source_rows, decoded_member
from fill_content_from_memorial import global_cpk_header

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'
RETAIL=ROOT/'data/memorial/external/files/assetpacks/on_demand_asset2/199/199/assets'
OUT=ROOT/'Japan content/Recovered assets'
sys.path.insert(0,str(ROOT/'tools/vendor/python'))
from cricodecs import cpk

def sha(raw):return hashlib.sha256(raw).hexdigest()

def source_content():
    original=json.loads((BASE/'original-unit-content.json').read_text(encoding='utf8'))
    extra=json.loads((BASE/'original-monster-vfx-content.json').read_text(encoding='utf8'))
    for table,selection in extra['tables'].items():
        target=original['tables'][table];key=selection['key']
        indexed={r[key]:r for r in target['rows']}
        for row in selection['rows']:
            if row[key]in indexed and indexed[row[key]]!=row:
                raise ValueError('Original unit and monster VFX source disagreement: '+table+':'+row[key])
            if row[key]not in indexed:target['rows'].append(row);indexed[row[key]]=row
    return original

class BytesSource:
    def __init__(self,raw):self.raw=raw
    def read_bytes(self):return self.raw

def payload(raw,row,start):
    attribute=row.get('UserString') or ''
    stem=attribute.split(':',1)[1].rsplit('-',1)[0] if attribute.startswith('CRI_CFATTR:') else ''
    return decoded_member(raw[start+row['FileOffset']:start+row['FileOffset']+row['FileSize']],row,stem)

def read_original(pattern,wanted=None,lazy=False):
    files={};packs=[]
    archive=ROOT/'Japan content/Shared sources/jp_andapp'
    metadata={r['name']:r for r in json.loads((ROOT/'Japan content/Shared sources/original-jp-archive-index.json').read_text(encoding='utf8'))['files']}
    candidates={p.name:p for p in RETAIL.glob(pattern)}
    candidates.update({p.name:p for p in archive.glob(pattern)})
    for path in sorted(candidates.values(),key=lambda p:p.name):
        raw,rows,start=source_rows(path);digest=sha(raw)
        original=metadata.get(path.name)
        if original is None or hashlib.md5(raw).hexdigest()!=original['md5']:
            continue
        packs.append({'path':path.relative_to(ROOT).as_posix(),'sha256':digest})
        for row in rows:
            name=row['FileName']
            if wanted is not None and name not in wanted:continue
            record={'path':path.relative_to(ROOT).as_posix(),'package_sha256':digest,
                    'member':name,'_raw':raw,'_row':row,'_start':start}
            files.setdefault(name,[]).append(record)
    if not lazy:
        files={name:materialize(name,records)for name,records in files.items()}
    return files,packs

def materialize(name,records):
    decoded=[]
    for record in records:
        data=payload(record['_raw'],record['_row'],record['_start'])
        decoded.append({k:v for k,v in record.items()if not k.startswith('_')}|{'sha256':sha(data),'data':data})
    if len({r['sha256']for r in decoded})!=1:
        receipt=BASE/'original-effect-resource-precedence.json'
        rule=json.loads(receipt.read_text(encoding='utf8'))if receipt.is_file()else{}
        winner=rule.get('duplicate_winners',{}).get(name)
        allowed={r['filename']:r['sha256']for r in rule.get('duplicates',{}).get(name,{}).get('variants',[])}
        if rule.get('status')!='VERIFIED_NATIVE_BIND_ORDER' or not winner or any(
                allowed.get(Path(r['path']).name)!=r['sha256']for r in decoded):
            raise ValueError('Ambiguous original JP member versions: '+name+' '+str([r['path']for r in decoded]))
        selected=next(r for r in decoded if Path(r['path']).name==winner)
        selected['duplicate_resolution']={'receipt':receipt.relative_to(ROOT).as_posix(),
            'sha256':sha(receipt.read_bytes()),'rule':rule['rule'],'variants':allowed}
        return selected
    return decoded[0]

def active_resources(cache,group):
    token,key=cache.tables['F_RESOURCE_MST'];_,rows=decode(cache.read('mst/Ver329_'+token+'.dat')[0],key)
    token,key=cache.tables['F_RESOURCE_VERSION_MST_LOCALIZE'];_,versions=decode(cache.read('mst/Ver735_'+token+'.dat')[0],key)
    versions={r['9ZCEWn0z']:r for r in versions};result=[]
    for row in rows:
        if row.get('drE35YcF')!=group:continue
        folder='common_lang' if '_common.' in row['pJ56sAEo'] else 'en'
        version=versions[row['9ZCEWn0z']]['OzT5lSz3' if folder=='common_lang' else '86SWOBTb']
        relative=folder+'/sd/'+row['3LHdc6Qa']+'/Ver'+version+'_'+row['pJ56sAEo']
        try:raw,origin=cache.read(relative)
        except FileNotFoundError:continue
        result.append({'relative':relative,'raw':raw,'origin':origin})
    return result

def index_current(packages):
    result={}
    for package in packages:
        raw,rows,start=source_rows(BytesSource(package['raw']))
        for row in rows:
            name=row['FileName']
            result.setdefault(name,[]).append({'sha256':sha(payload(raw,row,start)),
                'path':package['relative']})
    return result

def strings(raw):
    # IBMB/IM3R resources store names in a NUL-separated string table. Only
    # whole known filenames or stems are considered resource references.
    return {m.group().decode('ascii') for m in re.finditer(rb'(?<![^\x00])[A-Za-z_][A-Za-z0-9_. /\-]{2,}(?=\x00)',raw)}

def references(raw,by_stem):
    return set().union(*(by_stem.get(s,set()) for s in strings(raw)))

def replacement(raw,aliases):
    names={}
    for old,new in aliases.items():
        for old_text,new_text in [(old,new),(Path(old).stem,Path(new).stem)]:
            if len(old_text)!=len(new_text):raise ValueError('Binary resource rename must retain length')
            if old_text in names and names[old_text]!=new_text:raise ValueError('Ambiguous resource stem alias')
            names[old_text]=new_text
    edits=[];output=bytearray(raw)
    for match in re.finditer(rb'(?<![^\x00])[A-Za-z_][A-Za-z0-9_. /\-]{2,}(?=\x00)',raw):
        old=match.group().decode('ascii');new=names.get(old)
        if new is None:continue
        start,end=match.span();value=new.encode('ascii')
        output[start:end]=value;edits.append((start,end,value,old))
    if len(output)!=len(raw):raise ValueError('Native resource offsets changed')
    return bytes(output),[{'offset':s,'length':e-s,'source':old,'target':new.decode('ascii')}for s,e,new,old in edits]

def alias(name,digest,occupied):
    path=Path(name);length=len(path.stem)
    if length<5:raise ValueError('No safe scoped same-length alias for '+name)
    for salt in range(100):
        value=sha((name+digest+str(salt)).encode('ascii'));stem='j'+(value*3)[:length-1]
        candidate=stem+path.suffix
        if candidate not in occupied:occupied.add(candidate);return candidate
    raise ValueError('Unable to allocate distinct JP effect filename')

def main(apply=False):
    original=source_content()
    required=set()
    for row in original['tables']['F_EFFECT_MST']['rows']:
        for value in row.values():
            if isinstance(value,str):required.update(re.findall(r'[A-Za-z0-9_./-]+\.bmb',value,re.I))
    effects,effect_packs=read_original('battleEffect*.cpk',required)
    resource_index,resource_packs=read_original('effectResource*.cpk',lazy=True)
    if required-effects.keys():raise ValueError('Original JP BMB missing: '+str(sorted(required-effects.keys())))
    stems={}
    for name in resource_index:
        stems.setdefault(name,set()).add(name);stems.setdefault(Path(name).stem,set()).add(name)
    resources={};needed=set();pending=set().union(*(references(effects[n]['data'],stems)for n in required))
    while pending:
        item=pending.pop()
        if item in needed:continue
        resources[item]=materialize(item,resource_index[item])
        needed.add(item);pending.update(references(resources[item]['data'],stems)-needed)
    cache=NativeCache()
    try:
        packages={'effects':active_resources(cache,'battleEffect'),'effect-resources':active_resources(cache,'effectResource')}
        current={kind:index_current(values)for kind,values in packages.items()}
        occupied=set(effects)|set(resources)|set(current['effects'])|set(current['effect-resources'])
        prior_path=BASE/'original-unit-vfx-import.json'
        prior=json.loads(prior_path.read_text(encoding='utf8')) if prior_path.is_file() else {}
        resource_aliases={}
        for name in sorted(needed):
            entries=current['effect-resources'].get(name,[])
            if entries and not all(r['sha256']==resources[name]['sha256']for r in entries):
                resource_aliases[name]=prior.get('resource_aliases',{}).get(name) or alias(name,resources[name]['sha256'],occupied)
        # A model referencing a renamed texture also needs its own unchanged-
        # length binding copy, even when its original bytes match Global.
        while True:
            changed=False
            for name in sorted(needed):
                if name in resource_aliases:continue
                if references(resources[name]['data'],stems)&resource_aliases.keys():
                    resource_aliases[name]=prior.get('resource_aliases',{}).get(name) or alias(name,resources[name]['sha256'],occupied);changed=True
            if not changed:break
        effect_aliases={}
        for name in sorted(required):
            entries=current['effects'].get(name,[])
            if (entries and not all(r['sha256']==effects[name]['sha256']for r in entries)) or references(effects[name]['data'],stems)&resource_aliases.keys():
                effect_aliases[name]=prior.get('bmb_aliases',{}).get(name) or alias(name,effects[name]['sha256'],occupied)
        outputs={'effects':{},'effect-resources':{}};files=[]
        for kind,required_names,source,aliases in [('effects',required,effects,effect_aliases),('effect-resources',needed,resources,resource_aliases)]:
            for name in sorted(required_names):
                target=aliases.get(name,name);raw,edits=replacement(source[name]['data'],resource_aliases)
                existing=current[kind].get(target,[])
                if existing and not all(r['sha256']==sha(raw)for r in existing):raise ValueError('Scoped resource collision: '+target)
                record={k:v for k,v in source[name].items()if k!='data'}
                record.update(kind=kind,source_member=name,target_member=target,
                    runtime_sha256=sha(raw),resource_string_edits=edits,
                    current_byte_equivalent=bool(existing),runtime_source='Original JP bytes with scoped same-length resource binding names' if edits else 'Exact original JP member bytes')
                files.append(record)
                if not existing:outputs[kind][target]=raw
        prepared={};receipts=[]
        for kind,additions in outputs.items():
            if not additions:continue
            package=packages[kind][0];archive=cpk.Cpk.load_bytes(package['raw'])
            before={e.full_path:(e.id,sha(archive.file_bytes(i)))for i,e in enumerate(archive.file_infos())}
            next_id=max(e.id for e in archive.file_infos())+1
            for name,raw in sorted(additions.items()):archive.add_bytes(raw,name,id=next_id);next_id+=1
            body=archive.save_bytes();end=16+struct.unpack_from('<Q',body,8)[0];body=global_cpk_header(body[:end])+body[end:]
            check=cpk.Cpk.load_bytes(body);after={e.full_path:(e.id,sha(check.file_bytes(i)))for i,e in enumerate(check.file_infos())}
            if any(after.get(k)!=v for k,v in before.items()):raise ValueError('An existing Global effect member changed')
            if any(after[n][1]!=sha(raw)for n,raw in additions.items()):raise ValueError('Original JP effect append did not roundtrip')
            prepared[package['relative']]=body
            receipts.append({'output':'data/overlay/'+package['relative'],'before_origin':package['origin'],'before_sha256':sha(package['raw']),'output_sha256':sha(body),'added_members':len(additions),'existing_members_preserved':len(before)})
        report={'schema':1,'status':'APPLIED_ASSETS_NATIVE_BINDINGS_PENDING' if apply else 'VALIDATED_PREVIEW',
            'required_bmb_files':len(required),'required_resource_files':len(needed),
            'bmb_aliases':effect_aliases,'resource_aliases':resource_aliases,'files':files,
            'original_packages':effect_packs+resource_packs,'packages':receipts,
            'existing_Global_members_untouched':True,'resource_versions_changed':False}
        if apply:
            for relative,raw in prepared.items():
                p=ROOT/'data/overlay'/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                if p.read_bytes()!=raw:raise ValueError('Native effect resource write/readback failed')
            for kind,additions in outputs.items():
                for name,raw in additions.items():
                    p=OUT/kind/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        (BASE/'original-unit-vfx-import.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':report['status'],'bmb_files':len(required),'resource_files':len(needed),
            'new_BMB_bindings':len(effect_aliases),'new_resource_bindings':len(resource_aliases),
            'appended_files':sum(map(len,outputs.values())),'Global_existing_preserved':True}))
    finally:cache.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
