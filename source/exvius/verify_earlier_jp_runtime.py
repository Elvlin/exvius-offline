"""Verify actual server assembly and original exploration resource routing."""
import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
os.environ['FFBE_DATA']=str(ROOT/'data')
sys.path.insert(0,str(ROOT/'source/server'))
import battle_content as battle


def main():
    base=ROOT/'Japan content/Earlier JP crossovers/Sources'
    rows=[json.loads(l)for l in (base/'Event graph/F_MISSION_MST.ndjson').read_text(encoding='utf8').splitlines()]
    evidence=json.loads((base/'Battle recovery/earlier-battle-reconstruction.json').read_text(encoding='utf8'))
    fields=set(evidence['field_stages'])
    document=json.loads((ROOT/'source/server/event_encounters.json').read_text(encoding='utf8'))
    catalogue=json.loads((ROOT/'source/server/event_archive.json').read_text(encoding='utf8'))
    with zipfile.ZipFile(ROOT/'release/exvius-offline-v0.1.25.apk')as archive:
        original=json.loads(archive.read('assets/rules/event_archive.json'))
    now={str(r['area']):r for r in catalogue['events']}
    # The authoring catalogue already contains30 date/source/group corrections
    # newer than the public APK. Preserve those existing changes; compare every
    # original gameplay identity, route and art binding independently.
    historical_metadata={'release','date_source','source_page','group'}
    # A separate authorized category task appends these UI classification
    # fields. Report them independently from this crossover import's gameplay
    # identity, mission, route and artwork preservation comparison.
    category_metadata={'vortex_tab','vortex_category','category_source'}
    unchanged=[r for r in original['events']if r=={
        k:v for k,v in now.get(str(r['area']),{}).items()if k not in category_metadata}]
    category_rows=sum(any(k in now.get(str(r['area']),{})for k in category_metadata)
                      for r in original['events'])
    excluded_metadata=historical_metadata|category_metadata
    for row in original['events']:
        current=now.get(str(row['area']))
        assert current is not None,'An existing Global area disappeared'
        assert {k:v for k,v in row.items()if k not in excluded_metadata}=={k:v for k,v in current.items()if k not in excluded_metadata},'Existing Global gameplay binding changed'
    jp=[r for r in catalogue['events']if r.get('jp_original_scope')=='earlier-jp-28']
    assert len(jp)==28 and sum(len(r['missions'])for r in jp)==130
    checks=[]
    for mission in rows:
        mid=mission['qo3PECw6']
        if mid in fields:
            assert battle.resource_kind(mid)=='exploration',mid
            out=battle.field_mission_bundle({},mission)
            resources=battle.story_mission_resources(mission)
            assert not out.get('an6TB4WS')and not out.get('Bi6hVv34'),mid
            names=[r['pJ56sAEo']for r in resources]
            assert any(n.endswith('0100.cpk')for n in names),mid
            assert any(n.endswith('.cpk')and not n.endswith('0100.cpk')for n in names),mid
            checks.append({'mission':mid,'kind':'field','native_resources':names})
        else:
            out=battle.assemble(mid,authored={},mode='on')
            assert out and out.get('an6TB4WS'),mid
            assert out['1IfDqR4n'][0]['qo3PECw6']==mid,mid
            enemies={r['xqartN26']for r in out['wbet57nF']}
            parts={r['xqartN26']for r in out['bV34YIJQ']}
            assert all(r['xqartN26']in enemies&parts for r in out['Bi6hVv34']),mid
            assert all(int(r['fh31sk7B'])>0 and all(int(r[k])>0 for k in ('9NBV1XCS','Pn5w9dfh','84FJM3PD','T8xMDAZ4'))for r in out['bV34YIJQ']),mid
            assert all(not re.search('[\u3040-\u30ff\u3400-\u9fff]',r['G4L0YIB2'])for r in out['Wp39QX52']),mid
            checks.append({'mission':mid,'kind':'battle','phases':len(out['an6TB4WS']),'enemies':len(enemies)})
    summary={'battles':sum(r['kind']=='battle'for r in checks),'fields':len(fields),
             'canonical_encounters':len(document['missions']),'previous_encounters_preserved':len(document['missions'])-117,
             'unchanged_public_Global_catalogue_rows':len(unchanged),'preserved_public_Global_gameplay_bindings':len(original['events']),
             'preexisting_historical_metadata_differences':len(original['events'])-len(unchanged),'JP_catalogue_sets':len(jp)}
    summary['separate_category_metadata_rows']=category_rows
    assert summary['battles']==117 and summary['fields']==13,summary
    result={'schema':1,'checks':checks,'summary':summary,'phone_verified':False}
    (base/'Battle recovery/runtime-contract-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary))


if __name__=='__main__':main()
