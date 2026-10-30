"""Successful lifetime progress from gameplay, isolated from the real save."""
from copy import deepcopy
import json
import unittest

from ffbe_state import State
from player_state import PlayerState, _normalise, _serialise, switch_position, _load_ndjson
from exvius_repeat import begin_attempt, complete_attempt
from ffbe_battle import credit_mission_rewards, mission_end_echo
import exvius_actions_shops as shops


class ArchiveProgress(unittest.TestCase):
    def setUp(self):
        self.previous = State.player
        self.p = PlayerState.load('/nonexistent', slot='archive-progress')
        State.player = self.p

    def tearDown(self):
        State.player = self.previous

    def reload(self):
        State.player = self.p = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.p.data)))))

    def test_earned_gil_unlocks_actual_trophy_and_survives_reload(self):
        self.p.currencies['gil'] = 20000000  # Test funding is not earned progress.
        self.assertEqual(self.p.archive_value('TOTAL_GIL_GET'), 0)
        self.p.add_currency('gil', 6000)
        self.p.add_currency('gil', 4000)
        self.p.spend_currency('gil', 5000)
        self.reload()
        self.assertEqual(self.p.archive_value('TOTAL_GIL_GET'), 10000)
        out = shops.trophy_reward({}, {'y3ubhqI0': [{'m81FLCIz': '1'}]})
        self.assertEqual(self.p.currencies['gil'], 20005500)
        row = _load_ndjson('F_TROPHY_MST.ndjson', 't86L4JR3')['1']
        pos = switch_position(row['dIPkNn61'])
        self.assertIn(pos[1], self.p.switches[pos[0]])
        self.assertIn({'NYb0Cri6': 'TOTAL_GIL_GET', '6gAX1BpC': '10500'}, out['nSG9Jb1s'])
        before = deepcopy(self.p.data)
        shops.trophy_reward({}, {'y3ubhqI0': [{'m81FLCIz': '1'}]})
        self.assertEqual(self.p.data, before)

    def report(self, damage):
        return json.dumps({'jQsE54Iz': [{'qo3PECw6': '1110101'}],
            '09HRWXDf': [{'Wdi3MAs2': '100'}], 'nSG9Jb1s': [
                {'NYb0Cri6': 'TOTAL_ABILITY_USE', '6gAX1BpC': '2'},
                {'NYb0Cri6': 'TOTAL_DAMAGE', '6gAX1BpC': str(damage)},
                {'NYb0Cri6': 'MAX_DAMAGE_TURN', '6gAX1BpC': str(damage)},
                {'NYb0Cri6': 'TOTAL_GIL_GET', '6gAX1BpC': '999999'},
                {'NYb0Cri6': 'TOTAL_MISSION_CLEAR', '6gAX1BpC': '999999'}]})

    def test_captured_battle_totals_accumulate_and_peaks_do_not_sum(self):
        request = self.report(47374773)
        for damage in (47374773, 100):
            begin_attempt(self.p, '1110101')
            request = self.report(damage)
            # Echoing/previewing a reply must never award achievements.
            before = deepcopy(self.p.data)
            mission_end_echo({'09HRWXDf': [{}]}, request)
            self.assertEqual(self.p.data, before)
            credit_mission_rewards(request, {'09HRWXDf': [{}]})
            complete_attempt(self.p, '1110101', True, [], {}, {})
            before = deepcopy(self.p.data)
            credit_mission_rewards(request, {'09HRWXDf': [{}]})
            complete_attempt(self.p, '1110101', True, [], {}, {})
            self.assertEqual(self.p.data, before, 'retried end awarded progress twice')
        self.reload()
        self.assertEqual(self.p.archive_value('TOTAL_DAMAGE'), 47374873)
        self.assertEqual(self.p.archive_value('MAX_DAMAGE_TURN'), 47374773)
        self.assertEqual(self.p.archive_value('TOTAL_ABILITY_USE'), 4)
        self.assertEqual(self.p.archive_value('TOTAL_GIL_GET'), 200)
        self.assertEqual(self.p.archive_value('TOTAL_MISSION_CLEAR'), 2)

    def test_best_rank_uses_smallest_positive_position(self):
        for rank in (40, 80, 15, 0):
            self.p.record_archive({'DARK_VISIONS_BEST_RANK': rank})
        self.assertEqual(self.p.archive_value('DARK_VISIONS_BEST_RANK'), 15)

    def test_claimed_category_trophies_update_collection_achievement(self):
        masters = _load_ndjson('F_TROPHY_MST.ndjson', 't86L4JR3')
        self.p.data['quest_progress']['counters']['TOTAL_GIL_GET'] = 1000000
        shops.trophy_reward({}, {'y3ubhqI0': [{'m81FLCIz': '1,2,3'}]})
        self.assertEqual(self.p.archive_value('AWARD_EXPLOIT_TROPHY_CNT'), 3)
        self.reload()
        self.assertEqual(self.p.archive_value('AWARD_EXPLOIT_TROPHY_CNT'), 3)

    def test_existing_arena_colosseum_and_story_progress_are_retained(self):
        self.p.data['exvius_arena'] = {'user': {'p6H4CNw8': '10', 'Ka0Pbz5N': '7',
            'egayI1s4': '4', 'UbQ26oH4': '1000'}}
        self.p.data['exvius_colosseum'] = {'rounds': {'1': {'battles': 3, 'wins': 2, 'points': 150}}}
        self.p.data['progress']['cleared_missions'] = ['1110101', '1110102']
        self.assertEqual(self.p.archive_value('ARENA_BATTLE_CNT'), 10)
        self.assertEqual(self.p.archive_value('CLSM_BATTLE_CNT'), 3)
        self.assertEqual(self.p.archive_value('TOTAL_MISSION_CLEAR'), 2)
        self.p.record_archive({'ARENA_BATTLE_CNT': 1, 'CLSM_BATTLE_CNT': 1, 'TOTAL_MISSION_CLEAR': 1})
        self.assertEqual(self.p.archive_value('ARENA_BATTLE_CNT'), 11)
        self.assertEqual(self.p.archive_value('CLSM_BATTLE_CNT'), 4)
        self.assertEqual(self.p.archive_value('TOTAL_MISSION_CLEAR'), 3)

    def test_invalid_reports_and_frozen_save_do_not_change_progress(self):
        self.p.record_archive({'TOTAL_DAMAGE': 100})
        before = deepcopy(self.p.data)
        self.p.record_archive({'TOTAL_DAMAGE': '-1', 'MAX_DAMAGE_TURN': 'nan',
                               'TOTAL_GIL_GET': 2**64, 'UNKNOWN_ARCHIVE': 100})
        self.assertEqual(self.p.data, before)
        self.p.mode = 'frozen'
        self.p.record_archive({'TOTAL_DAMAGE': 1000})
        self.p.add_currency('gil', 1000)
        self.assertEqual(self.p.data, before)


if __name__ == '__main__':
    unittest.main()
