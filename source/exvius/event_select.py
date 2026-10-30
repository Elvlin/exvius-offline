"""Explicit persistent selection; no game/server execution.
python3 exvius/event_select.py --data DATA --area 970 --area 888
python3 exvius/event_select.py --data DATA --disable-added-events
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from exvius_events import save_policy
p=argparse.ArgumentParser()
p.add_argument('--data',required=True)
g=p.add_mutually_exclusive_group(required=True)
g.add_argument('--area',action='append')
g.add_argument('--disable-added-events',action='store_true')
p.add_argument('--historical-window',action='store_true',help='leave existing configured date windows unchanged')
a=p.parse_args()
print(save_policy(a.data,{'version':1,'areas':a.area or [],'permanent':not a.historical_window}))
