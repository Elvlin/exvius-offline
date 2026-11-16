"""Export exact original effect records required by earlier JP monster frames."""
import hashlib
import json
from pathlib import Path

from recover_jp_unit_content import Inputs

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers/Sources'


def main():
    requirement_path=BASE/'Battle recovery/monster-vfx-required-groups.json'
    requirement_bytes=requirement_path.read_bytes();requirements=json.loads(requirement_bytes)
    wanted=set(requirements['additional_original_group_ids'])
    inputs=Inputs()
    try:
        groups={r['qIy86WvJ']:r for r in inputs.original('F_EFFECT_GROUP_MST')}
        effects={r['h5t4yBm2']:r for r in inputs.original('F_EFFECT_MST')}
        if wanted-groups.keys():raise ValueError('Original monster effect groups absent: '+str(sorted(wanted-groups.keys(),key=int)))
        selected_groups={g:groups[g]for g in wanted}
        selected_effects={}
        pending=set(wanted)
        while pending:
            gid=pending.pop()
            for clause in groups[gid].get('5A8SmwyC','').split(','):
                if not clause:continue
                fields=clause.split(':')
                if len(fields)!=8:raise ValueError('Unresolved original effect-group clause: '+gid+':'+clause)
                eid=fields[1]
                if eid not in effects:raise ValueError('Original effect dependency absent: '+gid+':'+eid)
                effect=effects[eid]
                selected_effects[eid]=effect
                # Current native effects are leaf BMB records. Retain the same
                # typed frame traversal if a preserved effect carries a group
                # frame field; never treat arbitrary numbers as references.
                for frame in effect.get('5A8SmwyC','').split('&'):
                    parts=frame.split(':')
                    if len(parts)<2 or parts[1]not in groups:continue
                    nested=parts[1]
                    if nested not in selected_groups:
                        selected_groups[nested]=groups[nested];pending.add(nested)
        tables={'F_EFFECT_GROUP_MST':{'key':'qIy86WvJ','rows':[selected_groups[k]for k in sorted(selected_groups,key=int)]},
                'F_EFFECT_MST':{'key':'h5t4yBm2','rows':[selected_effects[k]for k in sorted(selected_effects,key=int)]}}
        output={'schema':1,'source_kind':'Exact original native JP effect group and leaf records; source-only, no native writes',
                'source_inputs':inputs.receipts,'requirement_source':requirement_path.relative_to(ROOT).as_posix(),
                'requirement_sha256':hashlib.sha256(requirement_bytes).hexdigest(),
                'tables':tables,'counts':{k:len(v['rows'])for k,v in tables.items()},
                'missing':{'effect_groups':[],'effects':[]},
                'dependency_discovery':{'requested_additional_groups':len(wanted),'recursive_groups':len(selected_groups),
                                        'original_BMB_filenames':sorted({r['2HjxCGo6']for r in selected_effects.values()if r.get('2HjxCGo6')})}}
        path=BASE/'original-monster-vfx-content.json'
        path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'output':path.relative_to(ROOT).as_posix(),'groups':len(selected_groups),'effects':len(selected_effects),'missing':0,'native_writes':False}))
    finally:inputs.close()


if __name__=='__main__':main()
