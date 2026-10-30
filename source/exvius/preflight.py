"""Read-only offline-data preflight. Never imports downloaded code or launches apps.
Supports a source ZIP (--bundle) or extracted root. Reports readiness, not playability.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
try:
    from exvius_events import event_facts, load_policy
except ModuleNotFoundError:
    sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'server')]
    from exvius_events import event_facts, load_policy

class Bundle:
    def __init__(self,path):
        self.path=Path(path)
        self.zip=zipfile.ZipFile(self.path) if self.path.is_file() else None
        self.names=self.zip.namelist() if self.zip else []
    def read(self,name):
        if not self.zip:return (self.path/name).read_bytes()
        hits=[n for n in self.names if n==name or n.endswith('/'+name)]
        if len(hits)!=1:raise ValueError('expected exactly one bundled '+name)
        if self.zip.getinfo(hits[0]).file_size>16*1024*1024:raise ValueError('oversized input '+name)
        return self.zip.read(hits[0])
    def close(self):
        if self.zip:self.zip.close()


def read_rows(path):
    rows=[]
    with Path(path).open(encoding='utf-8') as f:
        for line in f:
            if line.strip():
                value=json.loads(line)
                if not isinstance(value,dict):raise ValueError('master row must be object')
                rows.append(value)
    return rows


def audit(bundle_path,data_root,profile):
    root=Path(data_root);bundle=Bundle(bundle_path)
    issues=[];hashes={}
    def doc(name):
        data=bundle.read(name);hashes[name]=hashlib.sha256(data).hexdigest()
        return json.loads(data)
    try:
        banner_map={}
        for name in ['gacha_catalogue.json','gacha_community.json','gacha_authored.json']:
            for banner in doc('server/'+name).get('banners',[]):
                if 'id' in banner:banner_map[str(banner['id'])]=banner
        selection=profile.get('banners',{'mode':'all'})
        mode=selection.get('mode');missing=[]
        if mode=='all':selected=set(banner_map)
        elif mode=='ids':
            selected=set(map(str,selection.get('ids',[])))
            missing=sorted(selected-set(banner_map))
            if not selected:issues.append('no banner IDs selected')
        elif mode=='campaign':
            campaigns=doc('server/gacha_campaigns.json')
            key=selection.get('campaign')
            row=campaigns.get('campaigns',{}).get(key)
            if row is None:issues.append('unknown campaign '+str(key));selected=set()
            else:selected={str(r['id']) for r in row.get('banners',[])+campaigns.get('standard',[]) if 'id' in r}
            missing=sorted(selected-set(banner_map))
        else:issues.append('unsupported banner selection mode');selected=set()
        # Upstream single-ID mode returns before optional standard-family merging.
        if profile.get('standard_banners') and mode!='ids':
            for banner in doc('server/gacha_standard.json').get('banners',[]):
                if 'id' in banner:banner_map[str(banner['id'])]=banner;selected.add(str(banner['id']))
        if missing:issues.append('unknown selected banner IDs: '+','.join(missing))
        dependency_results=[]
        for entry in doc('server_app/deps.json')['entries']:
            paths=[root/p for p in entry['paths']]
            found=all(p.exists() for p in paths)
            count=sum(sum(1 for f in p.rglob('*') if f.is_file()) if p.is_dir() else int(p.is_file()) for p in paths)
            okay=found and count>=entry.get('min_files',0)
            dependency_results.append({'label':entry['label'],'paths':entry['paths'],'required':entry.get('required',False),'present':okay,'file_count':count})
            if entry.get('required') and not okay:issues.append('missing/incomplete '+entry['label'])
        facts=[];missing_events=[]
        try:
            policy=load_policy(root,profile.get('event_areas',[]))
            dungeons=read_rows(root/'mst_decoded/F_DUNGEON_MST.ndjson')
            missions=read_rows(root/'mst_decoded/F_MISSION_MST.ndjson')
            facts,missing_events=event_facts(policy['areas'],dungeons,missions)
            if missing_events:issues.append('selected event area chains unresolved')
        except (OSError,ValueError) as exc:
            policy=None;issues.append('event chain not verified: '+str(exc))
        raw=bundle.read('server/content/battle/F_MISSION_MST.tsv')
        hashes['server/content/battle/F_MISSION_MST.tsv']=hashlib.sha256(raw).hexdigest()
        lines=raw.decode().splitlines()
        header=json.loads(lines[0][2:]) if lines and lines[0].startswith('# {') else {}
        index_rows=list(csv.DictReader((line for line in lines if not line.startswith('#')),fieldnames=header.get('fields'),delimiter='\t'))
        indexed_ids={str(r.get('qo3PECw6')) for r in index_rows if r.get('qo3PECw6')}
        for fact in facts:fact['first_mission_in_battle_index']=fact['first_mission'] in indexed_ids
        return {'ready_for_runtime_setup':not issues,'playable_verified':False,
                'banner_catalog_count':len(banner_map),'selected_banner_count':len(selected-set(missing)),
                'unknown_banner_ids':missing,'battle_index_mission_count':len(indexed_ids),
                'event_policy':policy,'resolved_event_chains':facts,'unresolved_event_chains':missing_events,
                'dependencies':dependency_results,'issues':issues,'input_sha256':hashes,
                'limits':['A table/index entry is not proof of working combat or story coverage.',
                          'Banner pool/rate/art validation and UI selection are not executed.',
                          'Version registry presence is checked, not GL/JP semantic compatibility.',
                          'No certificate, host, network, server or client changes are made.']}
    finally:bundle.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--data',required=True);p.add_argument('--profile',required=True)
    a=p.parse_args()
    report=audit(a.bundle,a.data,json.loads(Path(a.profile).read_text()))
    print(json.dumps(report,indent=2));sys.exit(0 if report['ready_for_runtime_setup'] else 2)
