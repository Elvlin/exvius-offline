"""Summon transaction regressions. Fixtures stay in memory and never save a campaign."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'source/server'))

import ffbe_state
import gacha_box
from player_state import PlayerState


class SummonTransactions(unittest.TestCase):
    def setUp(self):
        self.previous = ffbe_state.State.player
        self.notes = list(ffbe_state.NOTES)
        self.player = PlayerState.load('/nonexistent', slot='selftest-summons')
        ffbe_state.State.player = self.player
        self.player.add_currency('lapis_free', 20000)
        self.player.dirty = False

    def tearDown(self):
        ffbe_state.State.player = self.previous
        ffbe_state.NOTES[:] = self.notes

    def banner(self, **fields):
        return dict({'id': '9800001', 'detail_id': '98000011', 'name': 'Transaction fixture',
            'cost': {'kind': 'lapis', 'amount': 500}, 'draws': 1,
            'pool': [{'unit_id': '100000315', 'rarity': 5, 'rate': 1}]}, **fields)

    def assert_declined(self, banner, repeats=1):
        before, dirty = copy.deepcopy(self.player.data), self.player.dirty
        self.assertIsNone(self.player.roll_gacha(banner, repeats=repeats))
        self.assertEqual(self.player.data, before)
        self.assertEqual(self.player.dirty, dirty)

    def test_campaign_alias_uses_existing_purchase_and_daily_counters(self):
        banner = self.banner(state_id='9100001', purchase_limit=1)
        existing = self.player.banner_state('9100001')
        existing['total_exe_count'] = 1
        self.assert_declined(banner)
        banner.pop('purchase_limit')
        banner['daily_limit'] = 1
        from player_state import gacha_period
        self.player.data['gacha'].setdefault('daily', {})['9100001'] = {'date': gacha_period(banner)[0], 'count': 1}
        self.assert_declined(banner)
        self.player.data['gacha']['daily'].clear()
        self.assertIsNotNone(self.player.roll_gacha(banner))
        self.assertEqual(existing['total_exe_count'], 2)
        self.assertEqual(self.player.data['gacha']['daily']['9100001']['count'], 1)
        self.assertNotIn(banner['id'], self.player.data['gacha']['user_banners'])

    def test_failed_first_purchase_does_not_initialize_counters_or_spend(self):
        self.assert_declined(self.banner(purchase_limit=1, cost={'kind': 'lapis', 'amount': 20001}))
        self.assert_declined(self.banner(weekly_limit=1, pool=[]))
        self.assert_declined(self.banner(bonus_rewards=[{'kind': 999999, 'id': 1, 'count': 1}]))

    def test_batch_cannot_cross_lifetime_or_period_purchase_limit(self):
        for field in ('purchase_limit', 'daily_limit', 'weekly_limit'):
            banner = self.banner(**{field: 1})
            self.assert_declined(banner, repeats=2)

    def test_lifetime_and_period_limits_survive_reload(self):
        for field in ('purchase_limit', 'daily_limit', 'weekly_limit'):
            banner = self.banner(id={'purchase_limit': '9800002', 'daily_limit': '9800003',
                                     'weekly_limit': '9800004'}[field], **{field: 1})
            self.assertIsNotNone(self.player.roll_gacha(banner))
            self.player.data = json.loads(json.dumps(self.player.data))
            self.assert_declined(banner)
            if field != 'purchase_limit':
                self.player.data['gacha']['daily'][banner['id']]['date'] = '2000-01-01'
                self.assertIsNotNone(self.player.roll_gacha(banner))

    def test_archive_preserves_distinct_bonuses_and_lap_limits(self):
        from gacha_archive import catalogue
        first = self.banner(type='step', tab='limited', season='season4', release='2024-01-01',
            lap_limit=1, art={'banner': 'transaction-fixture.png'},
            steps=[{'draws': 1, 'cost': {'kind': 'lapis', 'amount': 500}}])
        second = dict(first, id='9800002', lap_limit=2)
        third = dict(first, id='9800003', bonus_rewards=[{'kind': 50, 'id': 1, 'count': 100}])
        duplicate = dict(first, id='9800004')
        with patch('gacha_archive.english_art', return_value=True):
            groups = catalogue([first, second, third, duplicate])
        season = next(group for group in groups if group['id'] == 'season4')
        self.assertEqual(season['ids'], ['9800001', '9800002', '9800003'])
        self.assertEqual(season['tab'], 2)

    def test_archive_merges_explicit_aliases_and_old_identity_formats(self):
        from gacha_archive import catalogue
        first = self.banner(season='season4', release='2024-01-01',
                            art={'banner': 'identity-fixture.png'}, campaign_identity='legacy-name')
        duplicate = dict(first, id='9800002', campaign_identity='global:2024-01-01:identity-fixture.png')
        alias = dict(first, id='9800003', ticket_group_id=10010)
        replacement = dict(first, id='9800004', alias_ids=['9800003'],
                           art={'banner': 'replacement-fixture.png'})
        groups = catalogue([first, duplicate, alias, replacement])
        ids = next(group['ids'] for group in groups if group['id'] == 'season4')
        self.assertEqual(ids, ['9800001', '9800004'])

    def test_bonus_moogle_metadata_and_step_lap_cap(self):
        bonus = {'kind': 10, 'id': 904000105, 'count': 1, 'affinity_points': ['1000', '']}
        banner = self.banner(lap_limit=1, steps=[{'draws': 1,
            'cost': {'kind': 'lapis', 'amount': 500}, 'bonus_rewards': [bonus]}])
        before = len(self.player.data['roster'])
        result = self.player.roll_gacha(banner)
        self.assertEqual(len(self.player.data['roster']), before + 2)
        self.assertEqual(len(result['awards']), 2)
        self.assertEqual(len(result['bonus_awards']), 1)
        moogle = self.player.data['roster'][-1]
        self.assertEqual(str(moogle['master_id']), '904000105')
        self.assertEqual(moogle['affinity_points'], ['1000', ''])
        self.assertEqual(moogle['affinity_info'], ['70:0:0:1000:0:0:0', ''])
        wire = next(r for r in self.player._unit_rows() if r['og2GHy49'] == str(moogle['instance_id']))
        self.assertEqual(wire['9mu4boy7'], '70:0:0:1000:0:0:0')
        self.assertEqual(self.player.currencies['lapis_free'], 19500)
        self.assert_declined(banner)

    def test_ordinary_reward_moogles_have_usable_native_donation_info(self):
        for iid, channel, amount in [('904000101', 0, 10), ('904000104', 0, 50),
                                     ('904000105', 0, 100), ('906000104', 1, 500),
                                     ('906000105', 1, 1000)]:
            unit = self.player.grant_unit(iid)
            self.assertEqual(unit['affinity_info'][channel], '70:0:0:1000:0:0:0')
            self.assertEqual(int(unit['affinity_points'][channel]), amount)

    def test_event_moogle_preserves_its_specific_trust_target(self):
        from player_state import unit_mst
        base = self.player.grant_unit('302001405')
        donor = self.player.grant_unit('904000103')
        target = unit_mst(base['master_id'])['9mu4boy7']
        self.player._apply_unit_reward_metadata(donor, {
            'affinity_points': ['50', ''], 'affinity_info': [target, '']})
        self.assertEqual(donor['affinity_info'][0], target)
        self.player.mix_units(base['instance_id'], [donor['instance_id']])
        self.assertEqual(int(base['affinity_points'][0]), 50)

    def test_moogle_fusion_awards_mastery_once_and_caps_progress(self):
        from player_state import unit_mst
        base = self.player.grant_unit('100000315')
        small = self.player.grant_unit('904000104')
        self.player.mix_units(base['instance_id'], [small['instance_id']])
        self.assertEqual(base['affinity_points'][0], '50')
        moogle = self.player.grant_unit('904000105')
        self.player._apply_unit_reward_metadata(moogle, {'affinity_points': ['1000', '']})
        kind, iid, count = map(int, unit_mst(base['master_id'])['9mu4boy7'].split(':')[:3])
        owned = self.player.item_count(kind, iid)
        result = self.player.mix_units(base['instance_id'], [moogle['instance_id']])
        self.assertEqual(base['affinity_points'][0], '1000')
        self.assertEqual(self.player.item_count(kind, iid), owned + count)
        self.assertEqual(result['trust_rewards'], [{'kind': kind, 'id': iid, 'count': count}])
        state = copy.deepcopy(self.player.data)
        self.assertIsNone(self.player.mix_units(base['instance_id'], [moogle['instance_id']]))
        self.assertEqual(self.player.data, state)
        extra = self.player.grant_unit('904000104')
        self.player.mix_units(base['instance_id'], [extra['instance_id']])
        self.assertEqual(base['affinity_points'][0], '1000')
        self.assertEqual(self.player.item_count(kind, iid), owned + count)

    def test_unavailable_mastery_reward_does_not_consume_the_moogle(self):
        base = self.player.grant_unit('100000315')
        moogle = self.player.grant_unit('904000105')
        self.player._apply_unit_reward_metadata(moogle, {'affinity_points': ['1000', '']})
        state, dirty = copy.deepcopy(self.player.data), self.player.dirty
        with patch.object(self.player, '_can_credit', return_value=False):
            self.assertIsNone(self.player.mix_units(base['instance_id'], [moogle['instance_id']]))
        self.assertEqual(self.player.data, state)
        self.assertEqual(self.player.dirty, dirty)

    def raid_box(self):
        document = json.loads((PROJECT / 'source/server/gacha_named.json').read_text(encoding='utf8'))
        banner = next(b for b in document['banners'] if str(b['id']) == '9200031')
        self.player._grant_items([{'kind': 20, 'id': banner['cost']['item_id'], 'count': 100000}])
        return banner

    def test_original_raid_boxes_have_exact_slot_totals_and_do_not_replace_draws(self):
        banner = self.raid_box()
        self.assertEqual([sum(e['copies'] for e in box) for box in banner['boxes']], [300, 300, 500, 500, 500])
        coins = self.player.item_count(20, banner['cost']['item_id'])
        detail = gacha_box.detail_id(self.player, banner)
        with patch('gacha_box.secrets.randbelow', return_value=0):
            result = gacha_box.roll(self.player, banner, detail, 5)
        self.assertEqual(result['count'], 5)
        self.assertEqual(self.player.item_count(20, banner['cost']['item_id']), coins - 2000)
        self.assertEqual(sum(gacha_box.state(self.player, banner)['drawn']['0'].values()), 5)
        self.assertEqual(result['reward_awards'], self.player.data['gacha']['last_pull']['reward_awards'])
        self.player.data = json.loads(json.dumps(self.player.data))
        self.assertEqual(sum(gacha_box.state(self.player, banner)['drawn']['0'].values()), 5)

    def test_raid_box_stale_detail_and_invalid_batch_spend_nothing(self):
        banner = self.raid_box()
        before = copy.deepcopy(self.player.data)
        detail = gacha_box.detail_id(self.player, banner)
        self.assertIsNone(gacha_box.roll(self.player, banner, str(int(detail) + 1), 1))
        self.assertIsNone(gacha_box.roll(self.player, banner, detail, 51))
        self.assertEqual(self.player.data, before)

    def test_raid_box_failure_rolls_back_the_whole_batch(self):
        banner = self.raid_box()
        before = copy.deepcopy(self.player.data)
        original = self.player.roll_gacha
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs) if calls == 1 else None
        with patch.object(self.player, 'roll_gacha', side_effect=fail_second), \
                patch('gacha_box.secrets.randbelow', return_value=0):
            with self.assertRaises(ValueError):
                gacha_box.roll(self.player, banner, gacha_box.detail_id(self.player, banner), 2)
        self.assertEqual(self.player.data, before)

    def test_select_summon_grants_the_chosen_unit_and_charges_original_price(self):
        import exvius_gacha_select
        from exvius_actions import _mst
        iid, row = next(iter(_mst('F_GACHA_SELECT_UNIT_MST.ndjson', '3HriTp6B').items()))
        banner = self.banner(selection=True)
        cost = int(row['e4mG8jTc'])
        self.player._grant_items([{'kind': 23, 'id': 260, 'count': cost}])
        request = {'u9jY6hQJ': [{'X1IuZnj2': banner['id'], 'nqzG3b2v': banner['detail_id'],
                                '3HriTp6B': iid}]}
        before = len(self.player.data['roster'])
        with patch('ffbe_gacha.all_banners', return_value=[banner]):
            result = exvius_gacha_select.select_unit({}, request)
            self.assertEqual(len(self.player.data['roster']), before + 1)
            self.assertEqual(str(self.player.data['roster'][-1]['master_id']), iid)
            self.assertEqual(self.player.item_count(23, 260), 0)
            self.assertTrue(result['u9jY6hQJ'][0]['UJz5QED2'])
            state = copy.deepcopy(self.player.data)
            refused = exvius_gacha_select.select_unit({}, request)
        self.assertEqual(refused['u9jY6hQJ'][0]['UJz5QED2'], '')
        self.assertEqual(self.player.data, state)


if __name__ == '__main__':
    unittest.main(verbosity=2)
