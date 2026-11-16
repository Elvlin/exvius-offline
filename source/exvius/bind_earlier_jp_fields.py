"""Bind original SINoALICE field-script treasures to their exact missions."""
import argparse
import hashlib
import json
import re
import sqlite3
import struct
from pathlib import Path

from recover_jp_assets import source_rows, decoded_member

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    bindings=json.loads((BASE/'Event graph/field-resource-bindings.json').read_text(encoding='utf8'))
    path=ROOT/'source/server/content/field_treasures.json'
    before=path.read_bytes()
    document=json.loads(before)
    catalogue={str(r['id']):r for r in document['treasures']}
    database=ROOT/'data/web_sources/ffbe-data.db'
    conn=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    source_treasures={str(r['treasureId']):dict(r)for r in conn.execute('select * from field_treasure')}
    switches={r['8vAYn3IX'] for r in map(json.loads,(ROOT/'data/mst_decoded/F_SWITCH_MST.ndjson').read_text(encoding='utf8').splitlines())}
    receipts=[]
    found={}
    for mission in bindings['missions']:
        mid=mission['mission_id']
        entry={'mission_id':mid,'map':None,'scene':None,'treasures':[],'binary_sources':[]}
        for resource in mission['native_resources']:
            if not resource['filename'].endswith('.cpk'):continue
            source=next(ROOT/r['path']for r in resource['original_source_paths']if r.get('matches_original_archive_bytes'))
            raw,toc,start=source_rows(source)
            if resource['type']=='map':entry['map']=resource['filename']
            else:entry['scene']=resource['filename']
            for row in toc:
                name=row['FileName']
                if not name.endswith('.bin'):continue
                offset=start+row['FileOffset']
                data=decoded_member(raw[offset:offset+row['FileSize']],row,source.stem)
                entry['binary_sources'].append({'file':resource['filename'],'member':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'external_url_bytes_present':b'http://'in data or b'https://'in data})
                for match in re.finditer(rb'[HM]\x00\x05(.{4})\x01',data,re.DOTALL):
                    iid=str(struct.unpack('>I',match[1])[0])
                    if iid not in source_treasures:continue
                    original=source_treasures[iid]
                    switch=str(original['openSwitch'] or '0')
                    nearby=data[max(0,match.start()-256):match.end()+256]
                    if switch!='0'and struct.pack('>I',int(switch))not in nearby:continue
                    expected=','.join(':'.join(v.split(':')[:3]) for v in original['reward'].split(','))
                    target=catalogue.get(iid)
                    if target is None or target['rewards']!=expected or str(target['switch'])!=switch:
                        raise ValueError('Original treasure/runtime definition mismatch: '+iid)
                    if switch not in switches:raise ValueError('Original treasure opening switch missing: '+switch)
                    target['missions']=sorted(set(map(str,target.get('missions',[])))|{mid},key=int)
                    target['resources']=sorted(set(target.get('resources',[]))|{source.stem})
                    found[iid]={'id':iid,'rewards':expected,'switch':switch,'missions':target['missions']}
                    entry['treasures'].append(iid)
        if not entry['map'] or not entry['scene']:
            raise ValueError('Original field map/scene dependency missing: '+mid)
        entry['treasures']=sorted(set(entry['treasures']),key=int)
        receipts.append(entry)
    if len(receipts)!=13 or len(found)!=19:
        raise ValueError('Original SINoALICE field dependency coverage changed')
    if args.apply:
        path.write_text(json.dumps(document,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
    result={'schema':1,'status':'APPLIED'if args.apply else'PREVIEW','field_stages':len(receipts),'unique_original_treasures':len(found),
            'original_treasure_database_sha256':hashlib.sha256(database.read_bytes()).hexdigest(),
            'before_sha256':hashlib.sha256(before).hexdigest(),'output':path.relative_to(ROOT).as_posix(),
            'original_binary_policy':'Original map and event binaries unchanged. Only original typed treasure references with adjacent original opening switches authorize mission ownership. No opening battles or invented script operands.',
            'historical_raffle':'Localized closed-raffle notice; no real-world prize draw is provided offline.',
            'treasures':list(found.values()),'missions':receipts,'phone_flow_verified':False}
    (BASE/'Event graph/field-runtime-bindings.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':result['status'],'field_stages':13,'original_treasures':19}))


if __name__=='__main__':main()
