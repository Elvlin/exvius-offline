"""Compile all bound exploration collection points from retained maps and guides."""
import hashlib,json,re,struct,sys,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/vendor/python'))
from cricodecs import cpk

def rows(name,folder='mst_decoded'):
 return [json.loads(s) for s in (ROOT/'data'/folder/(name+'.ndjson')).read_text(encoding='utf8').splitlines()]
def norm(s):return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s.split('/')[0].replace('(2)','')).lower())
def inventory():
 paths={}
 for directory in ('memorial_fill','client/files'):
  for path in sorted((ROOT/'data'/directory/'common_lang/sd').glob('map*/**/*.cpk')):
   paths[re.sub(r'^Ver\d+_','',path.name)]=path
 resources={r['Nnb20keZ']:r for r in rows('F_RESOURCE_MAP_MST')}
 dungeons={r['U9iHsau3']:r for r in rows('F_DUNGEON_MST')}
 names={r['key'].rsplit('_',1)[-1]:r['v'][0] for r in rows('F_TEXT_DUNGEON_NAME','text_decoded') if r['v']}
 scanned,output,missing={},[],[]
 for m in rows('F_MISSION_MST'):
  if m['Y4VoF8yu']!='2':continue
  did=m['U9iHsau3'];ids=m['q4f9IdMs'] or dungeons.get(did,{}).get('q4f9IdMs','')
  maps=[resources[r]['pJ56sAEo'] for r in ids.split(',') if r in resources and resources[r]['dX0SkK3j']=='200']
  points,sources=set(),[]
  for name in maps:
   path=paths.get(re.sub(r'^Ver\d+_','',name))
   if not path:missing.append((m['qo3PECw6'],name));continue
   if path not in scanned:
    a=cpk.load(str(path));raw=next(a.file_bytes(i) for i,e in enumerate(a.file_infos()) if e.full_path=='map.bin')
    found={struct.unpack('>I',x[1])[0] for x in re.finditer(rb'\x00\x00\x00\x07\x50\x00\x04(.{4})',raw,re.S)}
    # Small placeholder IDs appear in inactive NPC pages, not real gathering nodes.
    scanned[path]=(sorted(p for p in found if p>=10000),hashlib.sha256(raw).hexdigest())
   points.update(scanned[path][0]);sources.append({'path':path.relative_to(ROOT).as_posix(),'map_bin_sha256':scanned[path][1]})
  output.append({'mission':m['qo3PECw6'],'name':names.get(did,''),'points':sorted(points),'sources':sources})
 if missing:raise ValueError('Unrecovered exploration bindings: '+str(missing))
 return output

def build():
 labels={int(r['key'].rsplit('_',1)[-1]):r['v'][0] for r in rows('F_TEXT_ITEM_NAME','text_decoded') if r['v']}
 names={}
 for iid,label in sorted(labels.items()):names.setdefault(label,iid)
 items={int(r['tL6G9egd']) for r in rows('F_ITEM_MST')}
 guides=json.loads((ROOT/'logs/reference/all-exploration-collection-wiki-20261110.json').read_text())['pages']
 guides+=json.loads((ROOT/'logs/reference/later-field-collection-guides-20261110.json').read_text())['pages']
 for p in json.loads((ROOT/'logs/reference/extra-field-collection-guides-20261110.json').read_text())['pages']:
  s=p.get('wikitext','');n=s.find('Collection Points')
  if n>=0:guides.append({'title':p['title'],'collection_wikitext':s[n:s.index('\n|}',n)+3]})
 by={norm(p['title']):p for p in guides if p.get('collection_wikitext')};missions={}
 for m in inventory():
  if not m['points']:continue
  mid=m['mission'];g=by.get(norm(m['name']))
  if mid=='22010101':g=by['fulanpass']
  if mid.startswith('210101'):g=by[norm('The Sealed Tower - Level '+mid[-1])]
  text=re.split(r'\n\s*\|\}',g['collection_wikitext'].split('Collection Points',1)[1],maxsplit=1)[0] if g else ''
  entries=[(x[1].split('|')[0],float(x[2]) if x[2] else None,1) for x in re.finditer(r'\[\[([^\]]+)\]\](?:\s*\((\d+(?:\.\d+)?)%\))?',text)]
  entries += [(x[1],100,int(x[2])) for x in re.finditer(r'\{\{Currency\|([^|]+)\|(\d+)\}\}',text)]
  draws=3;provenance='Published item membership. Equal item weights are local estimates; original server probabilities were not recovered.'
  if mid=='8180102':
   entries=[(e+' Megacryst',None,1) for e in ('Fire','Ice','Lightning','Water','Wind','Earth','Light','Dark')];draws=5
   provenance='King Mog Lost Maps: all eight megacrysts, 25-30 per run. Five items per point; equal element weights reconstructed.'
  elif mid=='8180104':
   awakening=set()
   unit_mst={r['3HriTp6B']:r for r in rows('F_UNIT_MST')}
   for r in rows('F_UNIT_CLASS_UP_MST'):
    target=unit_mst.get(r['t74crqAL'],{})
    if not 3<=int(target.get('9fW0TePj','0'))<=6:continue
    for part in r['KCk8u0am'].split(','):
     fields=part.split(':')
     if len(fields)==3 and fields[0]=='20' and 290010000<=int(fields[1])<290070000:awakening.add(int(fields[1]))
   entries=[(labels[i],None,1,i) for i in sorted(awakening)]
   provenance='King Mog Lost Maps: 3-6 star unit awakening materials. IDs from original unit awakening recipes; equal weights reconstructed.'
  elif mid in ('8600101','8600102'):
   entries=[('Dragon Grass',100,100)];draws=1
   provenance='Original Castle Exdeath event currency. Point allocation reconstructed; the reused map carries newer Warlock Castle identities.'
  elif mid=='32830101':
   entries=[(e+' Megacryst',None,1) for e in ('Fire','Ice','Lightning','Water','Wind','Earth','Light','Dark')]
   provenance='Original underwater exploration point identities. Later-tier megacryst membership reconstructed; original pool unverified.'
  elif '{{Currency|' in text:draws=1;provenance='Published event currency and quantity per point.'
  elif entries and all(entry[1] is not None for entry in entries):provenance='Published item percentages used as relative weights.'
  if not entries:raise ValueError('Missing pool: '+mid+' '+m['name'])
  pool=[]
  for entry in entries:
   name,weight,count=entry[:3]
   name=' '.join(name.split())
   iid=entry[3] if len(entry)>3 else names.get(name)
   if iid not in items:raise ValueError('Unresolved collection item: '+name)
   pool.append({'kind':20,'id':iid,'count':count,'weight':round(weight*100) if weight is not None else 100,'name':name})
  missions[mid]={'name':m['name'],'points':m['points'],'draws':draws,'pool':pool,'map_sources':m['sources'],
   'source':'https://exvius.fandom.com/wiki/'+(g['title'] if g else "King Mog's Lost Maps" if mid.startswith('818') else 'Castle Exdeath - Exploration' if mid.startswith('860') else 'Esper of Destruction').replace(' ','_'),'provenance':provenance}
 return {'note':'Original collection identities for every bound exploration. Selection persists per attempt; items are credited only from reported collection results. Unless documented otherwise, three draws per point are reconstructed. Estimates are stated per mission.','missions':missions}
if __name__=='__main__':
 result=build();(ROOT/'source/server/content/field_harvests.json').write_text(json.dumps(result,indent=1)+'\n',encoding='utf8');print('Restored collection definitions:',len(result['missions']))
