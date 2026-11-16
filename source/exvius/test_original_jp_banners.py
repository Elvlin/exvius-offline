"""Exercise historical JP offer transactions in memory, without a save or APK."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('FFBE_DATA', str(ROOT / 'data'))
sys.path.insert(0, str(ROOT / 'source/server'))
import ffbe_state
import gacha_box
from player_state import PlayerState


class OriginalJPSummons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banners = {b['id']: b for b in json.loads(
            (ROOT / 'source/server/gacha_original_jp.json').read_text(encoding='utf-8'))['banners']}
        cls.items = json.loads((ROOT / 'Japan content/Earlier JP crossovers/Sources/native-unit-id-map.json')
            .read_text(encoding='utf-8'))['mappings'].get('F_ITEM_MST', {})

    def setUp(self):
        self.previous = ffbe_state.State.player
        self.player = PlayerState.load('/nonexistent', slot='historical-jp-memory-check')
        ffbe_state.State.player = self.player
        self.player.add_currency('lapis_free', 50000)

    def tearDown(self):
        ffbe_state.State.player = self.previous

    def test_normal_eleven_draws_charge5000_and_grant_original_exchange_ticket(self):
        for identity in ('9400101', '9400102'):
            b = self.banners[identity]
            before = self.player.currencies['lapis_free']
            with patch('player_state.random.random', return_value=.999999):
                result = self.player.roll_gacha(b, offer=b['secondary_offer'])
            self.assertEqual(result['count'], 11)
            self.assertEqual(before - self.player.currencies['lapis_free'], 5000)
        self.assertEqual(self.player.item_count(20, 106230830), 2)
        self.assertEqual(self.player.item_count(20, 106230850), 0)

    def test_arus_six_steps_preserve_fragment_reward_cost_and_one_lap(self):
        b = self.banners['9400103']
        before = self.player.currencies['lapis_free']
        with patch('player_state.random.random', return_value=.999999):
            results = [self.player.roll_gacha(b) for _ in range(6)]
        self.assertTrue(all(r and r['count'] == 11 for r in results))
        self.assertEqual(before - self.player.currencies['lapis_free'], 20500)
        self.assertEqual(self.player.item_count(20, int(self.items.get('250016800', '250016800'))), 50)
        restored = PlayerState(json.loads(json.dumps(self.player.data)))
        snapshot = copy.deepcopy(restored.data)
        self.assertIsNone(restored.roll_gacha(b))
        self.assertEqual(restored.data, snapshot)

    def test_yao_poron_steps_grant_their_respective_fifty_fragments(self):
        b = self.banners['9400104']
        with patch('player_state.random.random', return_value=.999999):
            results = [self.player.roll_gacha(b) for _ in range(6)]
        self.assertTrue(all(r and r['count'] == 11 for r in results))
        for source in ('250017000', '250017100'):
            self.assertEqual(self.player.item_count(20, int(self.items.get(source, source))), 50)
        self.assertNotIn('guarantee_slots', b['steps'][2])
        self.assertAlmostEqual(sum(r['rate'] for r in b['steps'][5]['guarantee_slots'][0]['pool']
            if r['unit_id'] in ('346000307', '346000407')), .10)

    def test_printed_daily_discount_persists_and_does_not_lock_regular_summon(self):
        for daily, regular in [('9400105', '9400101'), ('9400106', '9400102')]:
            b = self.banners[daily]
            before = self.player.currencies['lapis_free']
            self.assertIsNotNone(self.player.roll_gacha(b))
            self.assertEqual(before - self.player.currencies['lapis_free'], 250)
            restored = PlayerState(json.loads(json.dumps(self.player.data)))
            snapshot = copy.deepcopy(restored.data)
            self.assertIsNone(restored.roll_gacha(b))
            self.assertEqual(restored.data, snapshot)
            self.assertIsNotNone(restored.roll_gacha(self.banners[regular]))

    def test_actual_mana_free_guarantee_excludes_four_star_and_shift_forms(self):
        b = self.banners['9400116']
        pool = b['pool']
        self.assertEqual(len(pool), 9)
        self.assertNotIn('312000404', {r['unit_id'] for r in pool})
        self.assertIn('820005505', {r['unit_id'] for r in pool})
        self.assertIn('820006605', {r['unit_id'] for r in pool})
        self.assertTrue(all(r['rarity'] in (5, 7) for r in pool))
        self.assertIsNotNone(self.player.roll_gacha(b))
        restored = PlayerState(json.loads(json.dumps(self.player.data)))
        before = copy.deepcopy(restored.data)
        self.assertIsNone(restored.roll_gacha(b))
        self.assertEqual(before, restored.data)

    def test_original_sin_tickets_spend_separate_items_and_award_correct_form(self):
        for identity, ticket in [('9400110', 106224700), ('9400111', 106224600)]:
            b = self.banners[identity]
            self.assertIsNone(self.player.roll_gacha(b))
            self.player.grant_item(20, ticket, 1)
            result = self.player.roll_gacha(b)
            self.assertIsNotNone(result)
            self.assertEqual(self.player.item_count(20, ticket), 0)
            if identity == '9400111':
                self.assertIn(result['awards'][0]['unit_id'], ['336000107', '336000207'])

    def test_original_raid_only_characters_and_materials_use_exact_earned_coins(self):
        paid = {r['unit_id'] for b in self.banners.values() if b.get('cost', {}).get('kind') == 'lapis'
                for r in b.get('pool', [])}
        for identity in ['9400112', '9400113', '9400114']:
            b = self.banners[identity]
            self.assertEqual(b['art'], {})
            for row in b['reward_pool']:
                if row['kind'] == 10:
                    self.assertNotIn(str(row['id']), paid)
            snapshot = copy.deepcopy(self.player.data)
            self.assertIsNone(self.player.roll_gacha(b))
            self.assertEqual(snapshot, self.player.data)
            self.player.grant_item(20, b['cost']['item_id'], 200)
            with patch('player_state.random.random', return_value=0):
                character = self.player.roll_gacha(b)
            self.assertEqual(len(character['awards']), 1)
            with patch('player_state.random.random', return_value=.999999):
                material = self.player.roll_gacha(b)
            self.assertEqual(len(material['reward_awards']), 1)
            self.assertEqual(self.player.item_count(20, b['cost']['item_id']), 0)

    def test_original_global_named_rows_are_preserved(self):
        import zipfile
        apk = ROOT / 'source/build/distribution/repository/release/exvius-offline-v0.1.25.apk'
        with zipfile.ZipFile(apk) as archive:
            published = json.loads(archive.read('assets/rules/gacha_named.json'))['banners']
        current = {b['id']: b for b in json.loads((ROOT / 'source/server/gacha_named.json')
            .read_text(encoding='utf-8'))['banners']}
        self.assertEqual(len(published), 90)
        self.assertTrue(all(current[b['id']] == b for b in published))

    def test_every_current_original_offer_executes_its_native_schema_contract(self):
        for identity, banner in self.banners.items():
            with self.subTest(banner=identity):
                player = PlayerState.load('/nonexistent', slot='one-original-offer')
                ffbe_state.State.player = player
                if banner.get('activation_ready') is False:
                    before = copy.deepcopy(player.data)
                    self.assertIsNone(gacha_box.roll(player, banner, gacha_box.detail_id(player, banner)))
                    self.assertEqual(player.data, before)
                    continue
                player.add_currency('lapis_free', 100000)
                cost = banner.get('cost', {})
                if cost.get('kind') == 'item':
                    player.grant_item(20, int(cost['item_id']), 100000)
                with patch('player_state.random.random', return_value=.999999):
                    if banner.get('boxes'):
                        with patch('gacha_box.secrets.randbelow', return_value=0):
                            result = gacha_box.roll(player, banner, gacha_box.detail_id(player, banner))
                    else:
                        result = player.roll_gacha(banner)
                self.assertIsNotNone(result)
                self.assertGreater(result['count'], 0)
                for award in result['awards']:
                    self.assertIn(award['unit_id'], {str(r['unit_id']) for r in banner.get('pool', [])}
                        | {str(r['id']) for r in banner.get('reward_pool', []) if r['kind'] == 10}
                        | {str(r['unit_id']) for step in banner.get('steps', [])
                           for slot in step.get('guarantee_slots', []) for r in slot['pool']}
                        | {str(e['reward']['id']) for box in banner.get('boxes', []) for e in box
                           if e['reward']['kind'] == 10}
                        | {str(r['unit_id']) for slot in banner.get('guarantee_slots', []) for r in slot['pool']})

    def test_no_original_free_reward_is_sold_as_a_paid_character(self):
        free_units = {'346000207', '313000305', '303000103', '303000204',
                      '100000215', '100000614', '100000713', '315000104'}
        for banner in self.banners.values():
            if banner.get('cost', {}).get('kind') == 'lapis':
                self.assertFalse(free_units & {r['unit_id'] for r in banner['pool']})
            if 'Category NV Guaranteed' in banner['name']:
                self.assertNotIn('346000207', {r['unit_id'] for r in banner['pool']})

    def test_incomplete_box_sources_never_award_invented_filler(self):
        for identity, box_count in [('9400151', 5), ('9400152', 4), ('9400153', 5), ('9400154', 4)]:
            banner = self.banners[identity]
            self.assertIs(banner['activation_ready'], False)
            self.assertEqual(len(banner['published_box_observations']), box_count)
            self.assertNotIn('boxes', banner)
            self.assertNotIn('cost', banner)
            self.assertNotIn('reward_pool', banner)
            before = copy.deepcopy(self.player.data)
            self.assertIsNone(gacha_box.roll(self.player, banner, gacha_box.detail_id(self.player, banner)))
            self.assertEqual(self.player.data, before)
            self.assertTrue(all(e['copies'] is None for box in banner['published_box_observations']
                                for e in box['published_highlights']))
        castle = self.banners['9400154']
        self.assertEqual([sum(e['reward']['count'] for e in box if e['reward']['id'] == 106234110)
                          for box in [b['published_highlights'] for b in castle['published_box_observations']]], [0, 1, 1, 2])
        self.assertEqual([sum(e['reward']['count'] for e in box if e['reward']['id'] == 106234120)
                          for box in [b['published_highlights'] for b in castle['published_box_observations']]], [0, 0, 1, 1])

    def test_special_roto_steps_keep_distinct_old_and_new_character_guarantees(self):
        for identity, steps in [('9400174', 3), ('9400175', 5)]:
            banner = self.banners[identity]
            self.assertEqual(len(banner['pool']), 200)
            self.assertEqual(len(banner['steps']), steps)
            self.assertEqual({r['unit_id'] for r in banner['steps'][0]['guarantee_slots'][0]['pool']},
                             {'346000107', '346000307', '346000407'})
            before = self.player.currencies['lapis_free']
            self.player.add_currency('lapis_free', 25000)
            for _ in range(steps):
                self.assertIsNotNone(self.player.roll_gacha(banner))
            self.assertEqual(before + 25000 - self.player.currencies['lapis_free'], steps * 5000)
            self.assertIsNone(self.player.roll_gacha(banner))
        slot = self.banners['9400175']['steps'][3]['guarantee_slots'][0]['pool']
        self.assertAlmostEqual(sum(r['rate'] for r in slot if r['unit_id'] in ['346000907', '346000807']), .20)
        self.assertEqual(self.player.item_count(20, 106234130), 1)

    def test_eight_unit_original_ticket_keeps_three_confirmed_identities(self):
        banner = self.banners['9400176']
        self.assertEqual(len(banner['pool']), 8)
        self.assertTrue({'207002007', '207002207', '100033207'} <= {r['unit_id'] for r in banner['pool']})
        self.assertTrue(all(r['rarity'] == 7 for r in banner['pool']))
        members = banner['reconstruction']['members']
        self.assertEqual(sum(r['membership'] == 'visually_confirmed_original' for r in members), 3)
        self.player.grant_item(20, 106234110, 1)
        result = self.player.roll_gacha(banner)
        self.assertEqual(len(result['awards']), 1)
        self.assertEqual(self.player.item_count(20, 106234110), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
