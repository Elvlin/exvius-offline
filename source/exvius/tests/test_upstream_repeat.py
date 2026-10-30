"""Approved isolated imports: pinned player_state and data_paths; stdlib only."""
import os
import re
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
# Ensure decoded-data probes never read any existing game data.
TEMP=tempfile.TemporaryDirectory()
os.environ['FFBE_DATA']=TEMP.name
# Synthetic table schema fixtures, not recovered game data.
mst=Path(TEMP.name)/'mst_decoded';mst.mkdir()
source=(ROOT.parents[1]/'server/player_state.py').read_text()
for name in set(re.findall(r'F_[A-Z0-9_]+\.ndjson', source)):
    (mst/name).write_text('')
(mst/'F_UNIT_MST.ndjson').write_text('\n'.join(json.dumps({'3HriTp6B':mid,'aU3o2D4t':100}) for mid in ['100000102','100000202']))
(mst/'F_EQUIP_ITEM_MST.ndjson').write_text('\n'.join(json.dumps({'J1YX9kmM':mid}) for mid in ['302000100','404000200','406000100','409000100','403046900']))
sys.path[:0]=[str(ROOT.parents[1]/'server')]
from exvius_repeat import begin_attempt,complete_attempt
from player_state import PlayerState
ROWS=[{'id':'fixture1','condition':'clear:','rewards':'50:1:20,30:1:50,20:101:2'}]
CHECKS={'clear':lambda c,p:c['cleared']}
def finish(p,clear=True,rows=ROWS):
    return complete_attempt(p,'fixture-mission',clear,rows,CHECKS,{'cleared':clear})
class Upstream(unittest.TestCase):
    def test_repeat_save_reload_retry(self):
        path=str(Path(TEMP.name)/'repeat.json')
        p=PlayerState.load(path)
        initial=dict(p.currencies)
        for i in range(2):
            begin_attempt(p,'fixture-mission')
            r=finish(p)
            self.assertEqual(len(r['paid']),1)
            self.assertEqual(finish(p)['paid'],[])
        self.assertEqual(p.currencies['lapis_free'],initial['lapis_free']+40)
        self.assertEqual(p.currencies['gil'],initial['gil']+50)
        self.assertEqual(p.item_count(20,'101'),2)
        self.assertTrue(p.save(path))
        q=PlayerState.load(path)
        self.assertEqual(finish(q)['paid'],[])
        begin_attempt(q,'fixture-mission'); finish(q)
        self.assertEqual(q.currencies['lapis_free'],initial['lapis_free']+60)
        self.assertEqual(q.item_count(20,'101'),2)
    def test_frozen_and_ephemeral(self):
        for mode in ('frozen','ephemeral'):
            p=PlayerState.load('',mode=mode); before=p.currencies['lapis_free']
            begin_attempt(p,'fixture-mission');finish(p)
            self.assertEqual(p.currencies['lapis_free'],before+(20 if mode=='ephemeral' else 0))
            self.assertFalse(p.save(str(Path(TEMP.name)/(mode+'.json'))))
    def test_failed_clear_and_unsupported(self):
        p=PlayerState.load('');before=p.currencies['lapis_free']
        begin_attempt(p,'fixture-mission');finish(p,False)
        self.assertEqual(p.currencies['lapis_free'],before)
        begin_attempt(p,'fixture-mission')
        result=finish(p,rows=[{'id':'bad','condition':'clear:','rewards':'50:1:20,999:1:1'}])
        self.assertEqual(len(result['blocked']),1)
        self.assertEqual(p.currencies['lapis_free'],before+20)
        self.assertNotIn('bad',p.paid_challenges.get('fixture-mission',set()))
    def test_equipment_uses_real_inventory(self):
        p=PlayerState.load('');begin_attempt(p,'fixture-mission')
        result=finish(p,rows=[{'id':'equip','condition':'clear:','rewards':'21:403046900:1'}])
        self.assertEqual(len(result['paid']),1)
        self.assertTrue(p.data['inventory']['equipment'])
    def test_legacy_paid_remains_one_time(self):
        p=PlayerState.load('');p.credit_challenge('fixture-mission','fixture1')
        before=dict(p.currencies);begin_attempt(p,'fixture-mission');finish(p)
        self.assertEqual(p.currencies['lapis_free'],before['lapis_free']+20)
        self.assertEqual(p.currencies['gil'],before['gil'])
        self.assertEqual(p.item_count(20,'101'),0)
    def test_equipment_only_once_after_restart(self):
        p=PlayerState.load('');rows=[{'id':'equip2','condition':'clear:','rewards':'21:403046900:1,50:1:20'}]
        begin_attempt(p,'fixture-mission');finish(p,rows=rows)
        original=json.dumps(p.data['inventory']['equipment'],sort_keys=True)
        path=str(Path(TEMP.name)/'equip.json');p.save(path);q=PlayerState.load(path)
        begin_attempt(q,'fixture-mission');finish(q,rows=rows)
        self.assertEqual(json.dumps(q.data['inventory']['equipment'],sort_keys=True),original)
    def test_mixed_unknown_encoding_lapis_valid(self):
        p=PlayerState.load('');before=p.currencies['lapis_free']
        rows=[{'id':'mixed','condition':'clear:','rewards':'10:1:1:100,50:1:20'}]
        for _ in range(2):begin_attempt(p,'fixture-mission');finish(p,rows=rows)
        self.assertEqual(p.currencies['lapis_free'],before+40)
        self.assertEqual(p.data['exvius_repeat']['non_lapis_claims']['fixture-mission']['mixed']['entries'],[])
if __name__=='__main__':
    try: unittest.main()
    finally: TEMP.cleanup()
