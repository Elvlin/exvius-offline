"""Apply approved typed reward forks to original earlier JP objectives."""
import hashlib
import json
from pathlib import Path
from apply_jp_content import NativeCache
from decode_client_data import decode

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'


def main():
    mapping_path=BASE/'native-unit-import.json'
    mapping=json.loads(mapping_path.read_text(encoding='utf8'))['mappings']
    native_path='mst/Ver373_GL9t6cMF.dat'
    table='F_CHALLENGE_MST'
    cache=NativeCache()
    try:
        raw,origin=cache.read(native_path)
        _,current=decode(raw,cache.tables[table][1])
        active={r['V36ygRYs']:r for r in current}
        authoring_path=ROOT/'data/mst_decoded/F_CHALLENGE_MST.ndjson'
        authoring_bytes=authoring_path.read_bytes()
        authoring=[json.loads(l)for l in authoring_bytes.splitlines()if l.strip()]
        local={r['V36ygRYs']:r for r in authoring}
        kind={'20':'F_ITEM_MST','21':'F_EQUIP_ITEM_MST','22':'F_MATERIA_MST','10':'F_UNIT_MST','27':'F_VISION_CARD_MST'}
        updates=[]
        for line in (BASE/'Event graph/F_CHALLENGE_MST.ndjson').read_text(encoding='utf8').splitlines():
            row=json.loads(line)
            original=row.get('dX6cor8j','')
            values=[]
            for value in original.split(','):
                fields=value.split(':')
                if len(fields)>=3 and fields[0]in kind:
                    fields[1]=mapping.get(kind[fields[0]],{}).get(fields[1],fields[1])
                values.append(':'.join(fields))
            reward=','.join(values)
            if reward==original:continue
            cid=row['V36ygRYs']
            for label,record in [('active native',active.get(cid)),('local authoring',local.get(cid))]:
                if record is None or any(record.get(k)!=row.get(k)for k in ('qo3PECw6','Z0EN6jSh')):
                    raise ValueError('Challenge owner/order identity mismatch: '+label+':'+cid)
                if record.get('dX6cor8j')not in (original,reward):
                    raise ValueError('Challenge reward differs from original or approved mapping: '+label+':'+cid)
            updates.append({'qo3PECw6':row['qo3PECw6'],'V36ygRYs':cid,'Z0EN6jSh':row['Z0EN6jSh'],'dX6cor8j':reward})
        digest=lambda body:hashlib.sha256(body).hexdigest()
        contract={'schema':1,'status':'VALIDATED_READY_TO_APPLY',
            'classification':'Typed objective reward references only. Owner/order and exact prior reward verified in active native and authoring tables. Existing IDs, objectives, text and unrelated rows preserved.',
            'approved_mapping_source':mapping_path.relative_to(ROOT).as_posix(),'mapping_sha256':digest(mapping_path.read_bytes()),
            'tables':[{'table':table,'identity_fields':['qo3PECw6','V36ygRYs','Z0EN6jSh'],'operation':'merge_fields',
                       'active_native_path':native_path,'active_native_sha256':digest(raw),
                       'decoded_baseline_sha256':digest(authoring_bytes),
                       'expected_decoded_canonical_sha256':digest(json.dumps(authoring,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')),
                       'rows':updates}]}
        out=BASE/'native-event-reward-import.json'
        out.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'contract':out.relative_to(ROOT).as_posix(),'objectives':len(updates),'active_source':origin}))
    finally:cache.close()


if __name__=='__main__':main()
