import unittest
from raid_model import simulate, solo_target


class WorkloadTests(unittest.TestCase):
    def test_clear_caps_hp(self):
        result = simulate({'hp': 100, 'turns': [{'damage': 150}]})
        self.assertTrue(result['cleared_in_trace'])
        self.assertEqual(result['hp_removed'], 100)
        self.assertEqual(result['overkill_damage'], 50)

    def test_incomplete_trace_not_clear(self):
        self.assertFalse(simulate({'hp': 100, 'turns': [{'damage': 0}]})['cleared_in_trace'])

    def test_break_rearms_with_additive_delta_not_accumulation(self):
        config = {'hp': 1000, 'break_gauge': {'base_bp': 10000, 'delta_after_first': 20000, 'duration_turns': 3},
                  'turns': [{'damage': 1, 'bp_damage': 10000}] + [{'damage': 1}] * 3 +
                           [{'damage': 1, 'bp_damage': 30000}] + [{'damage': 1}] * 3}
        result = simulate(config)
        self.assertEqual(result['breaks_triggered'], 2)
        self.assertEqual(result['turns'][3]['bp_remaining'], 30000)
        self.assertEqual(result['turns'][7]['bp_remaining'], 30000)
        self.assertFalse(result['turns'][0]['broken_during_turn'])
        self.assertTrue(result['turns'][1]['broken_during_turn'])

    def test_clear_does_not_trigger_break(self):
        r = simulate({'hp': 1, 'break_gauge': {'base_bp': 1, 'delta_after_first': 0, 'duration_turns': 1},
                      'turns': [{'damage': 1, 'bp_damage': 1}]})
        self.assertEqual(r['breaks_triggered'], 0)

    def test_no_silent_repeat(self):
        self.assertEqual(simulate({'hp': 100, 'turns': [{'damage': 1}]})['turns_used'], 1)

    def test_invalid_numbers(self):
        for bad in (-1, True, 1.5, '1'):
            with self.assertRaises(ValueError):
                simulate({'hp': 1, 'turns': [{'damage': bad}]})
        with self.assertRaises(ValueError):
            simulate({'hp': 0, 'turns': [{'damage': 1}]})

    def test_local_target(self):
        self.assertEqual(solo_target(1000, 20), 20000)


if __name__ == '__main__':
    unittest.main()
