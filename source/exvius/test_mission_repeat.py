"""Autoplay continuation reports, isolated from the real save.

Run with FFBE_DATA set and source/server on the import path.
"""
import json
import unittest

from ffbe_state import State
from player_state import PlayerState
from exvius_repeat import begin_attempt, complete_attempt
from ffbe_battle import credit_mission_rewards, mission_end_echo, record_result_echo, repeat_run_report

MISSION = '1110101'


class MissionRepeat(unittest.TestCase):
    def setUp(self):
        self.previous = State.player
        self.p = PlayerState.load('/nonexistent', slot='mission-repeat')
        State.player = self.p

    def tearDown(self):
        State.player = self.previous

    def run_end(self, exp, gil, drops, run=None):
        row = {'S4U09svH': str(exp), 'Wdi3MAs2': str(gil), 'xF9Sr1a6': drops}
        if run:
            row['exvRepeatRun'] = str(run)
        plaintext = repeat_run_report(json.dumps({'jQsE54Iz': [{'qo3PECw6': MISSION}], '09HRWXDf': [row]}))
        begin_attempt(self.p, MISSION)
        spec = mission_end_echo({'09HRWXDf': [{}]}, plaintext)
        spec = credit_mission_rewards(plaintext, spec)
        complete_attempt(self.p, MISSION, True, [], {}, {})
        return record_result_echo(spec, plaintext)

    def test_marked_runs_pay_only_their_own_share_of_the_running_totals(self):
        # Device 2026-11-06, Siren's Test x3: each report adds the previous reply's echo.
        gil = self.p.currencies['gil']
        out = self.run_end(20000, 30000, '20:202000400:1')
        share = int(out['09HRWXDf'][0]['kcb0tsM6'])
        out = self.run_end(20000 + share, 60000, '20:202000400:2,20:290050200:1', run=2)
        self.assertEqual(out['09HRWXDf'][0]['16LQuC5r'], '30000')
        self.assertEqual(out['09HRWXDf'][0]['xF9Sr1a6'], '20:202000400:1,20:290050200:1')
        self.assertEqual(int(out['09HRWXDf'][0]['kcb0tsM6']), share)
        # Run 3 adds to run 2's corrected echo, not to the old running total.
        out = self.run_end(20000 + share, 60000, '20:202000400:1,20:290050200:1,20:290050100:1', run=3)
        self.assertEqual(out['09HRWXDf'][0]['xF9Sr1a6'], '20:290050100:1')
        self.assertEqual(self.p.currencies['gil'], gil + 90000)

    def test_unmarked_and_inconsistent_reports_are_credited_as_sent(self):
        gil = self.p.currencies['gil']
        self.run_end(20000, 30000, '20:202000400:1')
        self.run_end(20000, 30000, '20:202000400:1')                  # normal replay, no mark
        self.run_end(20000, 20000, '', run=2)                         # stale mark: less than the echo
        self.assertEqual(self.p.currencies['gil'], gil + 80000)


if __name__ == '__main__':
    unittest.main()
