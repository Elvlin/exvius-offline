"""Authored fixtures only; does not execute downloaded source."""
import copy
import json
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'server'))
from exvius_repeat import begin_attempt, complete_attempt, parse_rewards

class Player:
    def __init__(self, mode='live'):
        self.mode=mode; self.data={'wallet':{},'cleared':[],'paid':[]}; self.dirty=False
    def mark_challenge_cleared(self, mid, cid):
        self.data['cleared'].append(cid)
    def credit_challenge(self, mid, cid):
        self.data['paid'].append(cid)
    def _can_credit(self,row): return row['kind'] in (50,30,20)
    def _grant_items(self,rows):
        for r in rows:
            key=f"{r['kind']}:{r['id']}"
            self.data['wallet'][key]=self.data['wallet'].get(key,0)+r['count']
        return copy.deepcopy(rows)

ROWS=[{'id':'c1','condition':'clear:','rewards':'50:1:20,30:1:50,20:101:2'},
      {'id':'c2','condition':'optional:','rewards':'50:1:10'}]
CHECKS={'clear':lambda c,p:c['clear'], 'optional':lambda c,p:c['optional']}
def finish(p,clear=True,optional=False,rows=ROWS):
    return complete_attempt(p,'m1',clear,rows,CHECKS,{'clear':clear,'optional':optional})

class Repeat(unittest.TestCase):
    def test_every_clear_original_amounts_and_types(self):
        p=Player()
        for i in range(3): begin_attempt(p,'m1'); finish(p)
        self.assertEqual(p.data['wallet'],{'50:1':60,'30:1':50,'20:101':2})
    def test_same_completion_retry_no_pay(self):
        p=Player(); begin_attempt(p,'m1'); finish(p)
        before=copy.deepcopy(p.data); finish(p)
        self.assertEqual(p.data,before)
    def test_duplicate_pending_load_does_not_rearm(self):
        p=Player(); begin_attempt(p,'m1'); begin_attempt(p,'m1')
        self.assertEqual(p.data['exvius_repeat']['attempt']['sequence'],1)
    def test_restart_replay_and_new_load(self):
        p=Player(); begin_attempt(p,'m1'); finish(p)
        q=Player(); q.data=json.loads(json.dumps(p.data)); finish(q)
        self.assertEqual(q.data['wallet'],p.data['wallet'])
        begin_attempt(q,'m1'); finish(q)
        self.assertEqual(q.data['wallet']['50:1'],40)
    def test_failed_unknown_and_missing_load(self):
        for cleared in (False,None):
            p=Player(); begin_attempt(p,'m1'); finish(p,cleared)
            self.assertEqual(p.data['wallet'],{})
        self.assertEqual(finish(Player())['reason'],'no pending mission load')
    def test_objective_required_each_run(self):
        p=Player(); begin_attempt(p,'m1'); finish(p,optional=True)
        begin_attempt(p,'m1'); finish(p,optional=False)
        self.assertEqual(p.data['wallet']['50:1'],50)
    def test_unsupported_group_not_partially_paid(self):
        p=Player(); begin_attempt(p,'m1')
        rows=[{'id':'bad','condition':'clear:','rewards':'50:1:20,999:1:1'}]
        result=finish(p,rows=rows)
        self.assertEqual(p.data['wallet'],{'50:1':20}); self.assertEqual(p.data['paid'],[])
        self.assertEqual(len(result['blocked']),1)
    def test_extended_encoding_not_silently_truncated(self):
        self.assertEqual(parse_rewards('10:1:1:100:1'), [{'kind': 10, 'id': 1, 'count': 1, 'level': 1}])
        with self.assertRaises(ValueError): parse_rewards('10:1:1:50:1')
    def test_frozen(self):
        p=Player('frozen'); before=copy.deepcopy(p.data)
        begin_attempt(p,'m1'); finish(p)
        self.assertEqual(p.data,before)
    def test_rollback_partial_grant(self):
        p=Player(); begin_attempt(p,'m1'); before=copy.deepcopy(p.data)
        def broken(rows): p.data['wallet']['50:1']=20; return []
        p._grant_items=broken
        with self.assertRaises(RuntimeError): finish(p)
        self.assertEqual(p.data,before)
    def test_concurrent_completion_retry(self):
        p=Player(); begin_attempt(p,'m1')
        ts=[threading.Thread(target=finish,args=(p,)) for _ in range(5)]
        for t in ts:t.start()
        for t in ts:t.join()
        self.assertEqual(p.data['wallet']['50:1'],20)
    def test_other_mission_cannot_consume(self):
        p=Player(); begin_attempt(p,'m2'); finish(p)
        self.assertEqual(p.data['wallet'],{})
        self.assertEqual(p.data['exvius_repeat']['attempt']['status'],'pending')
    def test_legacy_paid_migration(self):
        p=Player(); p.data['progress']={'paid_challenges':{'m1':['c1']}}
        begin_attempt(p,'m1'); finish(p)
        self.assertEqual(p.data['wallet'],{'50:1':20})
    def test_unsupported_can_be_granted_later_once(self):
        p=Player(); rows=[{'id':'x','condition':'clear:','rewards':'50:1:20,999:1:1,30:1:5'}]
        begin_attempt(p,'m1'); finish(p,rows=rows)
        self.assertEqual(len(p.data['exvius_repeat']['non_lapis_claims']['m1']['x']['entries']),1)
        p._can_credit=lambda row: True
        begin_attempt(p,'m1'); finish(p,rows=rows)
        begin_attempt(p,'m1'); finish(p,rows=rows)
        self.assertEqual(p.data['wallet'],{'50:1':60,'999:1':1,'30:1':5})
    def test_malformed_separate_reward_does_not_block_lapis(self):
        p=Player(); begin_attempt(p,'m1')
        finish(p,rows=[{'id':'x','condition':'clear:','rewards':'10:1:1:99,50:1:20'}])
        self.assertEqual(p.data['wallet'],{'50:1':20})
    def test_lapis_disabled_does_not_mark_lapis_paid(self):
        p=Player();begin_attempt(p,'m1')
        complete_attempt(p,'m1',True,ROWS,CHECKS,{'clear':True,'optional':False},False)
        self.assertEqual(p.data['wallet'],{'30:1':50,'20:101':2})
        begin_attempt(p,'m1');finish(p)
        self.assertEqual(p.data['wallet'],{'30:1':50,'20:101':2,'50:1':20})
    def test_reordered_changed_amount_non_lapis_not_repaid(self):
        p=Player();begin_attempt(p,'m1');finish(p)
        begin_attempt(p,'m1')
        finish(p,rows=[{'id':'c1','condition':'clear:','rewards':'20:101:999,30:1:999,50:1:20'}])
        self.assertEqual(p.data['wallet'],{'50:1':40,'30:1':50,'20:101':2})
    def test_duplicate_original_reward_occurrences_once_each(self):
        p=Player();rows=[{'id':'dupe','condition':'clear:','rewards':'30:1:5,50:1:20,30:1:7'}]
        for _ in range(2):begin_attempt(p,'m1');finish(p,rows=rows)
        self.assertEqual(p.data['wallet'],{'30:1':12,'50:1':40})
if __name__=='__main__':unittest.main()
