"""Restore evidenced story awards and free event-unit mailbox definitions."""
import json,re
from pathlib import Path
from audit_summon_pools import approved_unit_baseline
ROOT=Path(__file__).resolve().parents[2]

def strings(x):
 if isinstance(x,str):yield x
 elif isinstance(x,dict):
  for v in x.values():yield from strings(v)
 elif isinstance(x,list):
  for v in x:yield from strings(v)
def build():
 mst,_=approved_unit_baseline()
 raw=json.loads((ROOT/'logs/reference/summons/unit-list-wiki.json').read_text(encoding='utf8'))
 table=max(strings(raw),key=len);units={}
 for line in table.split('|-'):
  cols=line.split('||');m=re.search(r'unit_icon_(\d+)\.png',line)
  if not m or len(cols)<8:continue
  uid=m[1];acquisition=cols[7]
  if not any(s in acquisition for s in ('Reward Units','Raid Summon','Star Quartz Units')):continue
  row=mst[uid]
  if row.get('I3SKJ4q0')=='1':continue
  name=re.search(r'\[\[([^\]]+)\]\]',cols[2])[1].split('|')[-1]
  root=row['woghJa61'];units[root]={'unit':uid,'root':root,'name':name,'mail_id':str(9800000000000+int(root)),
    'acquisition':re.sub(r'<[^>]+>|\[\[|\]\]','',acquisition).strip(),'source':'https://exvius.fandom.com/wiki/Unit_List'}
 mailbox={'note':'One claimable copy per verified free reward, raid or event exchange unit, including historical login gifts. Brave Shift forms and summon-only units are excluded. Stable issuance receipts survive claims and deletion.','units':list(units.values())}
 (ROOT/'source/server/content/free_event_units.json').write_text(json.dumps(mailbox,indent=1)+'\n',encoding='utf8')
 path=ROOT/'source/server/content/story_reward_repairs.json';story=json.loads(path.read_text(encoding='utf8'))
 story['rewards']=[r for r in story['rewards'] if r['reward'].startswith('60:') or r['mission']=='1120704']
 for name,uid,mid,town,later,acquisition in (
  ('Lid','100000503','1220505',None,None,'Clear Galebreak in Dirnado'),
  ('Nichol','100000403','1320905','3101','1410101','Visit Aquapolis Olderion after Water Shrine'),
  ('Jake','100000703','1420606','4202','1510101','Visit Downtown Zoldaad after Invincible Interior'),
  ('Sakura','100000603','1510506','5101','1610101','Visit Magi Nation Mysidia after Magic Library - Showdown of Destiny'),
  ('Blue Mage Fina','100025705','11810702',None,None,'Watch Starting on a New Journey after Season 2'),
  ('Runda','100037407','14010503',None,None,'Heroic Quest: clear Trail to Yorte - Underground Nest')):
  assert uid in mst
  row={'mission':mid,'reward':'10:'+uid+':1','evidence':{'unit':uid,'acquisition':acquisition,
   'source':'https://exvius.fandom.com/wiki/'+('General_Quests#Heroic_Quests' if name=='Runda' else name.replace(' ','_'))}}
  if town:row.update(town=town,later_mission=later)
  if name=='Blue Mage Fina':row['alternate_missions']=['11810703']
  story['rewards'].append(row)
 (path).write_text(json.dumps(story,indent=1,ensure_ascii=False)+'\n',encoding='utf8')
 print('Free event-unit mail:',len(units),'Story-unit acquisition repairs:',len(story['rewards'])-1)
if __name__=='__main__':build()
