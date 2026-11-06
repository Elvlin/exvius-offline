"""Battle trust and duplicate-fusion super trust, isolated from the real save.

Run with FFBE_DATA set and source/server on the import path.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ffbe_state import State
from player_state import PlayerState
from exvius_repeat import begin_attempt
from ffbe_battle import credit_mission_rewards

IGNIS_5, IGNIS_7 = '215000505', '215000507'
IGNIS_TMR = (21, 409020400)


class BattleTrust(unittest.TestCase):
    def setUp(self):
        self.previous = State.player
        self.p = PlayerState.load('/nonexistent', slot='battle-trust')
        State.player = self.p
        self.ignis = self.p.grant_unit(IGNIS_7)
        party = self.p.data['party']
        deck = next(d for d in party['decks'] if str(d['id']) == str(party['active_deck']))
        deck['members'][0]['instance_id'] = self.ignis['instance_id']
        self.iid = str(self.ignis['instance_id'])

    def tearDown(self):
        State.player = self.previous

    def end(self, cleared=True, exp='30'):
        request = {'jQsE54Iz': [{'qo3PECw6': '1110101'}], '09HRWXDf': [{'S4U09svH': exp}]}
        if cleared:
            request['2urzfX6d'] = [{'69ieJGhD': '1:1:3'}]
        begin_attempt(self.p, '1110101')
        return credit_mission_rewards(json.dumps(request), {'09HRWXDf': [{}]})

    def trust(self):
        return int((self.p.roster_row(self.iid).get('affinity_points') or ['0'])[0] or 0)

    def lv_row(self, out):
        rows = dict(r.split('@', 1) for r in out['09HRWXDf'][0]['Qic38SuC'].split(','))
        before, after = rows[self.iid].split('_')
        return before.split(':'), after.split(':')

    def test_cleared_battle_gives_master_rate_trust_and_shows_it_in_field_nine(self):
        with patch('ffbe_battle.random.randrange', return_value=29) as roll:
            out = self.end()
        roll.assert_called_with(100)
        self.assertEqual(self.trust(), 10)
        before, after = self.lv_row(out)
        self.assertEqual((before[9], after[9]), ('0', '10'))

    def test_result_gauge_field_is_the_gain_not_the_residual(self):
        # Device 2026-11-06: serving the residual made the client add it on top of the BEFORE exp.
        self.ignis['level'], self.ignis['exp'] = 1, 11
        with patch('ffbe_battle.random.randrange', return_value=99):
            out = self.end(exp='8')
        before, after = self.lv_row(out)
        self.assertEqual((before[0], before[2], before[12]), ('1', '11', '0'))
        gain = 8 // len(self.p.party_instance_ids())
        self.assertEqual(after[12], str(gain))
        self.assertEqual(int(after[2]), self.p.roster_row(self.iid)['exp'])

    def test_failed_roll_and_uncleared_exit_give_no_trust(self):
        with patch('ffbe_battle.random.randrange', return_value=30):
            self.end()
        self.assertEqual(self.trust(), 0)
        with patch('ffbe_battle.random.randrange', return_value=0):
            self.end(cleared=False)
        self.assertEqual(self.trust(), 0)

    def test_trust_without_exp_still_reaches_the_result_screen(self):
        with patch('ffbe_battle.random.randrange', return_value=0):
            out = self.end(exp='0')
        self.assertEqual(self.lv_row(out)[1][9], '10')

    def tmr_count(self):
        rows = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in self.p.equip_item_rows()}
        return rows.get(str(IGNIS_TMR[1]), 0)

    def test_reaching_full_trust_grants_the_master_reward_once(self):
        self.p.roster_row(self.iid)['affinity_points'] = ['995', '']
        owned = self.tmr_count()
        with patch('ffbe_battle.random.randrange', return_value=0):
            self.end()
            self.assertEqual(self.trust(), 1000)
            self.assertEqual(self.tmr_count(), owned + 1)
            before = deepcopy(self.p.roster_row(self.iid))
            self.end()
        self.assertEqual(self.p.roster_row(self.iid)['affinity_points'], before['affinity_points'])
        self.assertEqual(self.tmr_count(), owned + 1)

    def test_five_star_duplicate_fusion_raises_super_trust_by_half(self):
        duplicate = self.p.grant_unit(IGNIS_5)
        result = self.p.mix_units(self.iid, [duplicate['instance_id']])
        self.assertIsNotNone(result)
        self.assertEqual(self.p.roster_row(self.iid)['affinity_points'][1], '500')

    def test_first_identical_fusion_mails_one_all_fifty_percent_trust_moogle(self):
        # The client's final warning promises this once per 7★ base (device 2026-11-06).
        first = self.p.mix_units(self.iid, [self.p.grant_unit(IGNIS_5)['instance_id']])
        self.assertTrue(first['special_bonus'])
        mails = [m for m in self.p.mailbox if m['title'] == 'Special Fusion Bonus']
        self.assertEqual(len(mails), 1)
        second = self.p.mix_units(self.iid, [self.p.grant_unit(IGNIS_5)['instance_id']])
        self.assertFalse(second['special_bonus'])
        self.assertEqual(len([m for m in self.p.mailbox if m['title'] == 'Special Fusion Bonus']), 1)
        granted = self.p.receive_mail(mails[0]['mail_id'])
        self.assertEqual([(r['kind'], r['id']) for r in granted], [(10, 904000105)])
        moogle = self.p.data['roster'][-1]
        self.assertEqual((moogle['master_id'], moogle['affinity_points'][0]), ('904000105', '500'))
        self.assertEqual(self.p.receive_mail(mails[0]['mail_id']), [])

    def test_no_fusion_bonus_below_seven_stars(self):
        base = self.p.grant_unit(IGNIS_5)
        result = self.p.mix_units(base['instance_id'], [self.p.grant_unit(IGNIS_5)['instance_id']])
        self.assertFalse(result['special_bonus'])
        self.assertFalse([m for m in self.p.mailbox if m['title'] == 'Special Fusion Bonus'])


if __name__ == '__main__':
    unittest.main()
