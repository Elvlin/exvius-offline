"""Explicit local progress tool; no server, game, inventory or wire execution."""
import argparse
import json
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'server')]
from exvius_raid_progress import record_completion,save_state,validate_config,progress_view
p=argparse.ArgumentParser()
p.add_argument('--state',required=True);p.add_argument('--config',required=True)
p.add_argument('--mission');p.add_argument('--completion-id')
a=p.parse_args();config=validate_config(json.loads(Path(a.config).read_text()));path=Path(a.state)
state=json.loads(path.read_text()) if path.exists() else {}
if a.mission or a.completion_id:
 if not(a.mission and a.completion_id):p.error('both --mission and --completion-id required')
 result=record_completion(state,config,a.mission,a.completion_id,True)
 if result['credited']:save_state(path,state)
 print(json.dumps(result,indent=2))
else:
 ledger=state.get('exvius_raid_progress',{}).get('events',{})
 print(json.dumps({str(e['event_id']):progress_view(e,ledger[str(e['event_id'])]) for e in config['events'] if str(e['event_id']) in ledger},indent=2))
