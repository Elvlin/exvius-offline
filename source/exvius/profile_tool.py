"""Prepare a launch environment without executing the game/server.
Usage: python3 exvius/profile_tool.py exvius/offline.json --banner 9100203
The resulting JSON env maps directly to server_app's existing --env K=V flags.
Restart the server after changing selection. No historical content is fabricated.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from exvius_offline import profile_environment
p = argparse.ArgumentParser()
p.add_argument('profile', type=Path)
g = p.add_mutually_exclusive_group()
g.add_argument('--banner', action='append')
g.add_argument('--campaign')
g.add_argument('--all', action='store_true')
a = p.parse_args()
profile = json.loads(a.profile.read_text())
if a.banner: profile['banners'] = {'mode':'ids','ids':a.banner}
if a.campaign: profile['banners'] = {'mode':'campaign','campaign':a.campaign}
if a.all: profile['banners'] = {'mode':'all'}
print(json.dumps({'env':profile_environment(profile), 'mode':'campaign',
                  'notice':'Configuration only; server not started.'}, indent=2))
