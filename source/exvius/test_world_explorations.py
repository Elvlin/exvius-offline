"""World random encounters must resolve and exhaust without replacing bosses."""
from collections import Counter
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'source/exvius')]
import battle_content
from player_state import mission_row
from repair_world_explorations import STAGES, build


class WorldExplorationTests(unittest.TestCase):
    def test_real_world_replies_match_published_finite_runs(self):
        for mid, _, fights, experience, gil, actors in STAGES:
            with self.subTest(mission=mid):
                out = battle_content.field_mission_bundle({}, mission_row(mid))
                rows = out['6v0LPiRe']
                self.assertEqual(Counter(r['xqartN26'] for r in rows), Counter(dict(actors)))
                self.assertEqual({r['YzGa63QM'] for r in rows}, {'10'})
                self.assertEqual(len({r['2fY1IomW'] for r in rows}), fights)
                self.assertEqual({r['h4Sjf96p'] for r in rows}, {'0'})
                profiles = {(r['xqartN26'], r['6Yc4RkdM']): r for r in out['bV34YIJQ']}
                self.assertEqual(sum(int(profiles[r['xqartN26'], r['6Yc4RkdM']]['B6H34Mea'])
                                     for r in rows), experience)
                self.assertEqual(sum(int(profiles[r['xqartN26'], r['6Yc4RkdM']]['7UR4J2SE'])
                                     for r in rows), gil)
                groups = {(r['2fY1IomW'], r['Z0EN6jSh'], r['xqartN26'])
                          for r in out['Bi6hVv34']}
                self.assertTrue(all((r['2fY1IomW'], r['Z0EN6jSh'], r['xqartN26'])
                                    in groups for r in rows))
                self.assertFalse(out.get('an6TB4WS'))
                self.assertFalse(out.get('y35YvQjZ'))
                self.assertEqual(rows, battle_content.field_mission_bundle({}, mission_row(mid))['6v0LPiRe'])

    def test_native_profiles_are_unchanged_and_quest_bosses_do_not_become_random(self):
        originals = {(r['xqartN26'], r['6Yc4RkdM']): r
                     for r in battle_content.IndexSource().load('F_MONSTER_PARTS_MST')}
        for mid, (bundle, _) in build().items():
            for row in bundle['bV34YIJQ']:
                original = originals[row['xqartN26'], row['6Yc4RkdM']]
                self.assertTrue(all(row[k] == original.get(k, battle_content.PARTS_DEFAULTS.get(k, ''))
                                    for k in battle_content.PARTS_TOKENS))
        catacombs = battle_content.field_mission_bundle({}, mission_row('1110604'))
        random = {r['xqartN26'] for r in catacombs['6v0LPiRe']}
        self.assertFalse(random & {'303011000', '101006002', '401013000'})
        self.assertIn('111060312', {r['2fY1IomW'] for r in catacombs['Bi6hVv34']})
        # A boss-only trial must still clear the preceding field's encounters.
        trial = battle_content.field_mission_bundle({}, mission_row('1110404'))
        self.assertEqual(trial['6v0LPiRe'], [])


if __name__ == '__main__':
    unittest.main()
