import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'server')]
from exvius_raid_progress import record_completion,claim_shared_milestone,save_state,validate_config,local_threshold,credit_configured_raid
# Explicit synthetic schema fixture IDs and goal, not claimed original game values.
CONFIG={'version':1,'events':[{'event_id':'123','mission_ids':['456'], 'source':'synthetic fixture only',
 'original_shared_goal':1000,'target_solo_clears':10,'shared_milestones':[
 {'id':'half','scope':'shared','threshold':500,'rewards':[{'kind':20,'id':789,'count':3}]},
 {'id':'full','scope':'shared','threshold':1000,'rewards':[{'kind':50,'id':1,'count':100}]}]}]}
class RaidProgress(unittest.TestCase):
 def test_local_progress_original_rewards(self):
  state={'personal_points':99,'boss_hp':500000}; original=copy.deepcopy(CONFIG)
  for n in range(5):out=record_completion(state,CONFIG,'456',str(n),True)
  self.assertEqual(out['equivalent_shared_progress'],500);self.assertEqual(out['eligible_shared_milestones'],['half'])
  self.assertEqual(claim_shared_milestone(state,CONFIG,'123','half'),CONFIG['events'][0]['shared_milestones'][0]['rewards'])
  self.assertEqual(state['personal_points'],99);self.assertEqual(state['boss_hp'],500000);self.assertEqual(CONFIG,original)
 def test_retry_and_reload(self):
  state={};record_completion(state,CONFIG,'456','attempt1',True)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state.json';save_state(p,state);loaded=json.loads(p.read_text())
   self.assertFalse(record_completion(loaded,CONFIG,'456','attempt1',True)['credited'])
   self.assertEqual(record_completion(loaded,CONFIG,'456','attempt2',True)['clears'],2)
 def test_failed_unknown_mission_do_not_change(self):
  for mid,success in [('456',False),('456',None),('999',True)]:
   s={};self.assertFalse(record_completion(s,CONFIG,mid,'a',success)['credited']);self.assertEqual(s,{})
 def test_claim_not_early_or_twice(self):
  s={};record_completion(s,CONFIG,'456','1',True)
  self.assertEqual(claim_shared_milestone(s,CONFIG,'123','half'),[])
  for n in range(2,6):record_completion(s,CONFIG,'456',str(n),True)
  self.assertTrue(claim_shared_milestone(s,CONFIG,'123','half'))
  self.assertEqual(claim_shared_milestone(s,CONFIG,'123','half'),[])
 def test_personal_milestone_rejected(self):
  c=copy.deepcopy(CONFIG);c['events'][0]['shared_milestones'][0]['scope']='personal'
  with self.assertRaises(ValueError):validate_config(c)
 def test_no_silent_config_change(self):
  s={};record_completion(s,CONFIG,'456','1',True);before=copy.deepcopy(s)
  c=copy.deepcopy(CONFIG);c['events'][0]['target_solo_clears']=2
  with self.assertRaises(ValueError):record_completion(s,c,'456','2',True)
  self.assertEqual(s,before)
 def test_ceil_milestone(self):
  self.assertEqual(local_threshold(CONFIG['events'][0],501),6)
 def test_invalid_targets_and_event_ids(self):
  for v in [0,-1,True,1000001]:
   c=copy.deepcopy(CONFIG);c['events'][0]['target_solo_clears']=v
   with self.assertRaises(ValueError):validate_config(c)
 def test_disabled_without_config(self):
  class Player:
   mode='live';data={};dirty=False
  with tempfile.TemporaryDirectory() as d:
   self.assertFalse(credit_configured_raid(Player(),'456','1',True,d))
 def test_configured_runtime_seam(self):
  class Player:
   mode='live';dirty=False
   def __init__(self):self.data={}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state/exvius_raids.json';p.parent.mkdir();p.write_text(json.dumps(CONFIG))
   player=Player();self.assertTrue(credit_configured_raid(player,'456','1',True,d));self.assertTrue(player.dirty)
   self.assertFalse(credit_configured_raid(player,'456','1',True,d))
if __name__=='__main__':unittest.main()
