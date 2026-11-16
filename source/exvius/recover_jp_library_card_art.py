"""Recover the original SINoALICE Library reward card without shared replacements."""
import argparse
import json
import struct
from recover_jp_dependency_art import animation_check, inspect_member
from recover_earlier_jp_vfx import (ROOT, BASE, OUT, NativeCache, read_original,
    active_resources, index_current, source_rows, BytesSource, payload, sha, cpk,
    global_cpk_header)


def main(apply=False):
    identity='336000101'
    target_identity='873100001'
    names={'vc_cgg_'+identity+'.csv','vc_cgs_'+identity+'.csv',
        'vc_vignette_anime_'+identity+'.png','vc_vignette_icon_s_'+identity+'.png',
        'vc_vignette_item_icon_'+identity+'.png'}
    originals,packs=read_original('visioncard[123].cpk',names)
    if names-originals.keys():raise ValueError('Original Library card assets missing')
    files={n:r['data']for n,r in originals.items()}
    validation=animation_check(identity,files)
    if validation['referenced_rectangle_anomalies']:raise ValueError('Invalid Library animation texture bounds')
    cache=NativeCache()
    try:
        packages=active_resources(cache,'visioncard');current=index_current(packages)
        additions={};records=[]
        for name in sorted(names):
            target_name=name.replace(identity,target_identity)
            raw=files[name];existing=current.get(target_name,[])
            if any(r['sha256']!=sha(raw)for r in existing):
                raise ValueError('Isolated Library card art collision: '+target_name)
            records.append({k:v for k,v in originals[name].items()if k!='data'}|
                {'target_member':target_name,'present_exact':bool(existing),'validation':inspect_member(name,raw)})
            if not existing:additions[target_name]=raw
        updates=[]
        if additions:
            package=packages[0];archive=cpk.Cpk.load_bytes(package['raw'])
            before={e.full_path:(e.id,sha(archive.file_bytes(i)))for i,e in enumerate(archive.file_infos())}
            next_id=max(e.id for e in archive.file_infos())+1
            for name,raw in sorted(additions.items()):archive.add_bytes(raw,name,id=next_id);next_id+=1
            body=archive.save_bytes();end=16+struct.unpack_from('<Q',body,8)[0]
            body=global_cpk_header(body[:end])+body[end:]
            check=cpk.Cpk.load_bytes(body)
            after={e.full_path:(e.id,sha(check.file_bytes(i)))for i,e in enumerate(check.file_infos())}
            if any(after.get(n)!=v for n,v in before.items()):raise ValueError('An unrelated card member changed')
            if any(after[n][1]!=sha(raw)for n,raw in additions.items()):raise ValueError('Library art append failed')
            updates.append({'path':'data/overlay/'+package['relative'],'before_sha256':sha(package['raw']),
                'after_sha256':sha(body),'added_members':len(additions),'existing_members_preserved':len(before)})
            if apply:
                target=ROOT/'data/overlay'/package['relative'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
                if target.read_bytes()!=body:raise ValueError('Library native pack readback failed')
        if apply:
            for name,raw in files.items():
                target=OUT/'visioncards'/identity/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        report={'schema':1,'status':'APPLIED'if apply else 'VALIDATED_PREVIEW','original_card':identity,
            'target_card':target_identity,'target_graphic':target_identity,
            'files':records,'original_packages':packs,'animation':validation,'packages':updates,
            'all_original_members_exact':True,'unrelated_Global_assets_untouched':True}
        path=BASE/'Event rewards/library-card-art.json';path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':report['status'],'original_files':len(names),'added_files':len(additions),
            'animation_frames':validation['cgs_frames'],'unrelated_Global_preserved':True}))
    finally:cache.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)
