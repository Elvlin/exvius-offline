"""Expose the28 verified original earlier JP quest sets in the event catalogue."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'Japan content/Earlier JP crossovers'
KINDS={
 '702':'Challenge event','738':'Raid event','742':'Raid event','771':'Raid event','772':'Challenge quest',
 '3037':'Exploration','3038':'Exploration','3147':'Character Battle','4082':'Collaboration event',
 '4480':'Collaboration event','4481':'Azure Awakening Quest','4482':'Weapon Quest',
 '4483':'True Weapon Quest','4484':'Character Battle','6410':'Raid event',
 '6411':'Extreme Weapon Quest','6412':'Azure Awakening Quest','6413':'Character Battle',
 '6210':'Raid event','6212':'Weapon Quest','6213':'True Weapon Quest','6214':'Character Battle',
 '6215':'True Crown Quest','6216':'Character Battle','6217':'Azure Awakening Quest',
 '4500':'Collaboration event','4501':'Extreme Weapon Quest','4502':'Character Battle',
}


def rows(path):
    return [json.loads(line)for line in path.read_text(encoding='utf8').splitlines()if line.strip()]


def main():
    path=ROOT/'source/server/event_archive.json'
    before=path.read_bytes();document=json.loads(before)
    old={str(r['area']):r for r in document['events']}
    source=list(csv.DictReader((BASE/'earlier-crossovers.csv').open(encoding='utf-8-sig')))
    scope={r['entry_id']for r in csv.DictReader((BASE/'stage-counts-and-gaps.csv').open(encoding='utf-8-sig'))}
    source=[r for r in source if r['entry_id']in scope]
    if len(source)!=28:raise ValueError('Earlier JP original scope changed')
    graph=BASE/'Sources/Event graph'
    dungeons={r['U9iHsau3']:r for r in rows(graph/'F_DUNGEON_MST.ndjson')}
    missions=rows(graph/'F_MISSION_MST.ndjson')
    labels={r['key'].rsplit('_',1)[-1]:r['v'][0]for r in rows(ROOT/'data/text_decoded/F_TEXT_AREA_NAME.ndjson')}
    art=json.loads((ROOT/'source/server/event_art.json').read_text(encoding='utf8'))['events']
    added=[]
    for row in source:
        dids=row['jp_dungeon_ids'].split(';')
        areas={dungeons[did]['uv60hgDW']for did in dids}
        if len(areas)!=1:raise ValueError('Unexpected multi-area source quest set')
        area=next(iter(areas));image=art.get(area)
        name=image['name']if image else labels[area]
        own=sorted((r for r in missions if r['U9iHsau3']in dids),key=lambda r:(int(r['U9iHsau3']),int(r['Z0EN6jSh'])))
        if len(own)!=int(row['source_mission_count']):raise ValueError('Source stage membership changed: '+area)
        entry={'area':area,'name':name,'group':'collaborations','release':row['release_date_jst'],
               'kind':KINDS[area],'collaboration':row['family'],
               'dungeons':dids,'missions':[r['qo3PECw6']for r in own],
               'first_dungeon':dids[0],'first_mission':own[0]['qo3PECw6'],
               'banner_title':name,'source_page':row['source'],
               'date_source':row['source'],'jp_original_scope':'earlier-jp-28'}
        if image:
            runtime=ROOT/image['runtime_file']
            if hashlib.sha256(runtime.read_bytes()).hexdigest()!=image['runtime_sha256']:
                raise ValueError('Reviewed original banner translation changed: '+area)
            entry['filename']=image['filename']
        else:
            if area!='3038':raise ValueError('Unexpected missing original event banner: '+area)
            entry['original_art_status']='Original SINoALICE Part2 banner not recovered; deliberately unfilled'
        if area in old:
            prior=old[area]
            if prior.get('jp_original_scope')!='earlier-jp-28'and prior!=entry:
                raise ValueError('Existing Global catalogue identity collision: '+area)
        added.append(entry)
    ids={r['area']for r in added}
    # Existing rows keep both their data and relative order. New JP entries are
    # chronological; dates and native route membership come from owned sources.
    retained=[r for r in document['events']if str(r['area'])not in ids]
    document['events']=retained+sorted(added,key=lambda r:(r['release'],int(r['area'])))
    if any(r not in document['events']for r in retained):raise ValueError('Unrelated catalogue row lost')
    path.write_text(json.dumps(document,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
    receipt={'status':'APPLIED','quest_sets':len(added),'stages':sum(len(r['missions'])for r in added),
             'original_banner_translations':sum('filename'in r for r in added),'unfilled_original_banner_areas':['3038'],
             'preserved_existing_rows':len(retained),'output':path.relative_to(ROOT).as_posix(),
             'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'area_ids':[r['area']for r in added],'invented_artwork':False}
    (BASE/'Sources/Event graph/catalogue-integration.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:receipt[k]for k in ['status','quest_sets','stages','original_banner_translations','preserved_existing_rows']}))


if __name__=='__main__':main()
