"""Merge exact recovered original JP monsters into the active native group."""
from collections import defaultdict, Counter
import json
from pathlib import Path
import struct

from restore_jp_art import cpk, digest, global_cpk_header, NativeCache
from decode_client_data import decode
from fill_content_from_memorial import device_dir

ROOT=Path(__file__).resolve().parents[2]


def main():
    manifest_path=ROOT/'Japan content/Recovered assets/recovery-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    records=[r for r in manifest['files']if r['kind']=='monsters']
    if len({r['source_identity']for r in records})!=61:
        raise ValueError('All61 original JP monster models are required')
    cache=NativeCache()
    try:
        raw,resource_origin=cache.read('mst/Ver329_ZQqB38Ns.dat')
        _,resource_rows=decode(raw,cache.tables['F_RESOURCE_MST'][1])
        raw_versions,version_origin=cache.read('mst/Ver735_A1L1GlaQ.dat')
        _,versions=decode(raw_versions,cache.tables['F_RESOURCE_VERSION_MST_LOCALIZE'][1])
        versions={r['9ZCEWn0z']:r['OzT5lSz3']for r in versions}
        resource_rows=[r for r in resource_rows if r['drE35YcF']=='monster'and r['pJ56sAEo'].endswith('.cpk')]
        if not resource_rows:raise ValueError('No actual native monster resource group')
        archives,originals,origins,membership={},{},{},defaultdict(list)
        for row in resource_rows:
            relative='common_lang/'+device_dir(row['3LHdc6Qa'])+'/Ver'+versions[row['9ZCEWn0z']]+'_'+row['pJ56sAEo']
            body,origin=cache.read(relative)
            archive=cpk.Cpk.load_bytes(body)
            archives[relative]=archive
            entries=[(entry.full_path,entry.id,digest(archive.file_bytes(i)))for i,entry in enumerate(archive.file_infos())]
            originals[relative]=entries
            origins[relative]={'origin':origin,'sha256':digest(body),'resource_id':row['9ZCEWn0z']}
            for i,(name,_,_)in enumerate(entries):membership[name].append((relative,i))
        default=sorted(archives)[-1]
        requested=defaultdict(dict)
        bindings=[]
        for row in records:
            name=row['source_member']
            payload=(ROOT/row['path']).read_bytes()
            if digest(payload)!=row['sha256']:raise ValueError('Original monster source changed: '+name)
            # Existing native compact spellings are accepted aliases of these
            # exact model members. Patch them too so bind priority cannot pick
            # an older texture or animation. Never create an unproven alias.
            alias=name.replace('monster_','monster',1)
            names=[name]+([alias]if alias!=name and alias in membership else [])
            for target_name in names:
                destinations=membership.get(target_name)
                if destinations:
                    for relative,index in destinations:
                        archives[relative].replace_bytes(index,payload)
                        requested[relative][target_name]=row['sha256']
                else:
                    archive=archives[default]
                    archive.add_bytes(payload,target_name,id=max(e.id for e in archive.file_infos())+1)
                    membership[target_name]=[(default,len(list(archive.file_infos()))-1)]
                    requested[default][target_name]=row['sha256']
            bindings.append({'model_id':row['source_identity'],'member':name,'sha256':row['sha256'],
                             'original_source':row['source_package'],'native_member_names':names,
                             'native_packages':sorted({v[0]for target_name in names for v in membership[target_name]})})
        outputs,receipts={},[]
        for relative,wanted in requested.items():
            body=archives[relative].save_bytes()
            end=16+struct.unpack_from('<Q',body,8)[0]
            body=global_cpk_header(body[:end])+body[end:]
            check=cpk.Cpk.load_bytes(body)
            after=[(e.full_path,e.id,digest(check.file_bytes(i)))for i,e in enumerate(check.file_infos())]
            # CRI may reorder its directory when saving. Preserve identity and
            # payload multiplicities rather than imposing a new directory order.
            expected_original=Counter((name,iid,wanted.get(name,previous))for name,iid,previous in originals[relative])
            after_counts=Counter(after)
            if expected_original-after_counts:
                raise ValueError('Original unrelated member or CRI ID changed: '+relative+':'+str(next(iter(expected_original-after_counts))))
            for name,expected in wanted.items():
                found=[v for v in after if v[0]==name]
                if not found or any(v[2]!=expected for v in found):
                    raise ValueError('Exact original JP monster bytes not retained in every occurrence: '+name)
            outputs[relative]=body
            receipts.append({'output':'data/overlay/'+relative,'source':origins[relative],
                             'output_sha256':digest(body),'bytes':len(body),'original_members':len(originals[relative]),
                             'requested_unique_members':len(wanted),'appended_members':len(after)-len(originals[relative])})
        for relative,body in outputs.items():
            target=ROOT/'data/overlay'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(body)
            if digest(target.read_bytes())!=digest(body):raise ValueError('Monster CPK write/readback mismatch')
        result={'status':'Original JP monster native cache overlays applied; phone animation playback pending',
                'manifest':manifest_path.relative_to(ROOT).as_posix(),'manifest_sha256':digest(manifest_path.read_bytes()),
                'models':61,'members':len(records),'bindings':bindings,'packages':receipts,
                'native_group_authority':{'resource_master':resource_origin,'resource_master_sha256':digest(raw),
                                          'version_master':version_origin,'version_master_sha256':digest(raw_versions),
                                          'group_field':'F_RESOURCE_MST.drE35YcF=monster','packages_bound':len(resource_rows)},
                'unrelated_payloads_and_existing_CRI_IDs_preserved':True,'resource_versions_changed':False}
        (ROOT/'logs/jp-monster-art-integration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'models':61,'original_members':len(records),'modified_packages':len(outputs),'all_original_bytes_verified':True}))
    finally:cache.close()


if __name__=='__main__':main()
