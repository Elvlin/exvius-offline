"""Explicitly approved pinned pipeline test; temp synthetic data only, no server.
Invocation: python3 test_pipeline_isolated.py --bundle PATH
"""
import argparse
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

AP=argparse.ArgumentParser();AP.add_argument('--bundle',required=True);ARGS=AP.parse_args()
TEMP=tempfile.TemporaryDirectory(prefix='exvius-pipeline-');ROOT=Path(TEMP.name)
SERVER=ROOT/'server';SERVER.mkdir();DATA=ROOT/'data';MST=DATA/'mst_decoded';MST.mkdir(parents=True)
NAMES={'data_paths','player_state','season','ffbe_config','ffbe_state','ffbe_battle','ffbe_banner',
       'ffbe_friends','ffbe_gacha','ffbe_player','ffbe_pipeline','exvius_repeat','exvius_events','exvius_raid_progress'}
with zipfile.ZipFile(ARGS.bundle) as z:
    for n in z.namelist():
        if not n.startswith('exvius/server/'):continue
        rel=Path(n).name
        if (rel.endswith('.py') and Path(rel).stem in NAMES) or (rel.endswith('.json') and z.getinfo(n).file_size<1024*1024):
            (SERVER/rel).write_bytes(z.read(n))
source='\n'.join(p.read_text() for p in SERVER.glob('*.py'))
for name in set(re.findall(r'F_[A-Z0-9_]+\.ndjson',source)):(MST/name).write_text('')
(MST/'F_UNIT_MST.ndjson').write_text('\n'.join(json.dumps({'3HriTp6B':mid,'aU3o2D4t':100}) for mid in ['100000102','100000202']))
(MST/'F_EQUIP_ITEM_MST.ndjson').write_text('\n'.join(json.dumps({'J1YX9kmM':mid}) for mid in ['302000100','404000200','406000100','409000100','403046900']))
(MST/'F_CHALLENGE_MST.ndjson').write_text('\n'.join(json.dumps(row) for row in [
 {'qo3PECw6':'123','V36ygRYs':'fixture','Pzn5h0Ga':'68:','dX6cor8j':'50:1:20,30:1:50,20:101:2'},
 {'qo3PECw6':'124','V36ygRYs':'turns','Pzn5h0Ga':'73:1','dX6cor8j':'50:1:10'}]))
(MST/'F_DUNGEON_MST.ndjson').write_text(json.dumps({'uv60hgDW':'777','U9iHsau3':'77'}))
(MST/'F_MISSION_MST.ndjson').write_text(json.dumps({'U9iHsau3':'77','qo3PECw6':'123'}))
# No inherited overrides may point the test at real data or user saves.
for key in list(os.environ):
    if key.startswith(('FFBE_','GACHA_','STATE_','OUT_','CDN_','EVENT_','FRIENDS_')) or key in ('MST_DIR','TEXT_DIR','ART_ROOT','VERSION_TABLE_XML','CHALLENGE_MST'):
        os.environ.pop(key,None)
os.environ.update({'FFBE_DATA':str(DATA),'STATE_FILE':str(DATA/'state/fixture.json'),
                   'FRIENDS_FILE':str(ROOT/'absent-friends.yaml'),'LAPIS_AWARD':'1'})
sys.dont_write_bytecode=True
sys.path.insert(0,str(SERVER))

def guard(event,args):
    if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.fork','os.posix_spawn','pty.spawn'):
        raise RuntimeError('Denied test side effect: '+event)
    targets=[]
    if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
        flags=args[2] if len(args)>2 else 0
        if isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):targets=[args[0]]
    elif event in ('os.mkdir','os.remove','os.rmdir'):
        target=args[0];fd=args[2] if event=='os.mkdir' and len(args)>2 else args[1] if len(args)>1 else -1
        if isinstance(fd,int) and fd>=0 and not os.path.isabs(target):
            target=os.path.join(os.readlink('/proc/self/fd/'+str(fd)),os.fsdecode(target))
        targets=[target]
    elif event in ('os.rename','os.link','os.symlink'):targets=list(args[:2])
    for target in targets:
        if isinstance(target,int):continue
        if not Path(os.fsdecode(target)).resolve().is_relative_to(ROOT):
            raise RuntimeError('Denied write outside temporary fixture')
sys.addaudithook(guard)

import ffbe_pipeline as pipeline
import ffbe_state as state
import ffbe_config as config
from player_state import PlayerState

class PipelineFixture(unittest.TestCase):
    def setUp(self):
        state.State.player=PlayerState.load('')
        state.State.state_dirty=False
        state.LAST_DROPS.clear()
        state.STATE_FILE=str(DATA/'state/fixture.json')
        state.STATE_PERSIST=True
        (DATA/'state').mkdir(exist_ok=True)
        (DATA/'state/exvius_raids.json').write_text('{"version":1,"events":[]}')
    def load(self,mid='123'):
        return pipeline.reply_pipeline({},'fixture-load',None,mid,'fixture-load@'+mid)
    def clear(self,mid='123',success=True):
        body={config.CHALLENGE_GROUP:[{config.BATTLE_CLEAR_TOKEN:'wave:1:3' if success else ''}]}
        return pipeline.reply_pipeline({config.RESULT_TAG:[{}]},'fixture-end',json.dumps(body),mid,None)
    def test_registry_and_hook_order(self):
        self.assertEqual(pipeline.validate_pipeline(),[])
        keys=[s.key for s in pipeline.PIPELINE]
        self.assertLess(keys.index('credit_mission_lapis'),keys.index('apply_to_reply'))
        self.assertLess(keys.index('apply_to_reply'),keys.index('save_state'))
    def test_generated_routes_load_in_real_dispatch(self):
        by_id,by_token=state.load_endpoints(str(SERVER/'endpoints.json'))
        self.assertEqual(len(by_token),211)
        self.assertEqual(by_id['g0BjrU5D']['encode_key'],'z80swWd9')
        self.assertEqual(by_id['g0BjrU5D']['url'],'/actionSymbol/Sv85kcPQ.php')
    def test_persistent_event_policy_real_gate(self):
        from exvius_events import save_policy
        from ffbe_player import serve_event_gate
        import time
        save_policy(DATA,{'version':1,'areas':['777'],'permanent':True})
        original={'uv60hgDW':'888','keep':'original'}
        out=serve_event_gate({config.EVENT_GATE_TAG:[original.copy()]},config.EVENT_GATE_CARRIERS[0])
        rows=out[config.EVENT_GATE_TAG]
        self.assertEqual(rows[0],original)
        event=next(row for row in rows if row['uv60hgDW']=='777')
        self.assertEqual(event['qo3PECw6'],'123')
        self.assertLess(int(event['VjJQ51uG']),time.time())
        self.assertGreater(int(event['m8ivD4NX']),time.time())
        save_policy(DATA,{'version':1,'areas':[],'permanent':True})
        self.assertEqual(serve_event_gate({},config.EVENT_GATE_CARRIERS[0]),{})
    def test_full_loop_lapis_only_and_retry_reload(self):
        p=state.State.player;before=dict(p.currencies)
        self.load();self.clear();self.clear()
        self.assertEqual(p.currencies['lapis_free'],before['lapis_free']+20)
        self.assertEqual(p.currencies['gil'],before['gil']+50)
        self.assertEqual(p.item_count(20,'101'),2)
        state.State.player=PlayerState.load(state.STATE_FILE);q=state.State.player
        self.clear();self.assertEqual(q.currencies['lapis_free'],before['lapis_free']+20)
        self.load();self.clear()
        self.assertEqual(q.currencies['lapis_free'],before['lapis_free']+40)
        self.assertEqual(q.currencies['gil'],before['gil']+50)
        self.assertEqual(q.item_count(20,'101'),2)
    def test_failed_clear_and_unmet_objective(self):
        p=state.State.player;before=dict(p.currencies)
        self.load();self.clear(success=False)
        self.load('124');self.clear('124')
        self.assertEqual(p.currencies['lapis_free'],before['lapis_free'])
        self.assertEqual(p.currencies['gil'],before['gil'])
    def test_configured_shared_progress_seam(self):
        definition={'version':1,'events':[{'event_id':'999','mission_ids':['123'],'source':'synthetic pipeline fixture only',
                    'original_shared_goal':1000,'target_solo_clears':10,'shared_milestones':[]}]}
        (DATA/'state/exvius_raids.json').write_text(json.dumps(definition))
        self.load();self.clear();self.clear()
        from exvius_raid_progress import progress_view
        view=progress_view(definition['events'][0],state.State.player.data['exvius_raid_progress']['events']['999'])
        self.assertEqual(view['clears'],1)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PipelineFixture))
    TEMP.cleanup()
    sys.exit(0 if result.wasSuccessful() else 1)
