"""Source-backed raid batch buttons and transaction settlement, without a save."""
import copy
import json
from pathlib import Path
import sys
import unittest
import hashlib
import struct
import zipfile
import io
import re
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'source/exvius')]
import ffbe_gacha
import ffbe_state
import gacha_box
import raid_summon
from test_summon_transactions import SummonTransactions


class RaidBannerResources(unittest.TestCase):
    def test_packaged_native_indexes_and_install_manifest_match_their_masters(self):
        from decode_client_data import client_manifest
        from native_master_index import SCHEMAS, build_index
        apk = ROOT / 'source/build/distribution/assets/exvius-offline-v0.1.30.apk'
        manifest = client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
        with zipfile.ZipFile(apk) as packed:
            archive = packed.read('assets/rules/native_content.zip')
            install = json.loads(packed.read('assets/rules/native_content.json'))
            self.assertEqual(hashlib.sha256(archive).hexdigest(), install['sha256'])
            with zipfile.ZipFile(io.BytesIO(archive)) as native:
                files = {name: native.read(name) for name in native.namelist()}
            self.assertEqual(set(files), {row['path'] for row in install['files']})
            self.assertEqual(sum(map(len, files.values())), install['expanded_bytes'])
            for row in install['files']:
                self.assertEqual(hashlib.sha256(files[row['path']]).hexdigest(), row['sha256'])
            checked = set()
            for info in manifest.values():
                if info['table'] not in SCHEMAS:
                    continue
                for name, raw in files.items():
                    match = re.fullmatch(r'native/mst/Ver(\d+)_' + info['token'] + r'\.dat', name)
                    if match:
                        index = files['native/mst/' + info['token'] + '.i']
                        self.assertEqual(index, build_index(info['table'], raw, info['key'], match[1]), info['table'])
                        checked.add(info['table'])
            self.assertIn('F_BANNER_MST', checked)

    def test_all_global_raid_images_are_deliverable_from_the_apk(self):
        apk = ROOT / 'source/build/distribution/assets/exvius-offline-v0.1.30.apk'
        with zipfile.ZipFile(apk) as packed:
            banners = json.loads(packed.read('assets/rules/gacha_raid.json'))['banners']
            index = set(json.loads(packed.read('assets/rules/assets/banner_art/index.json')))
            events = json.loads(packed.read('assets/rules/event_art.json'))['events']
            self.assertEqual(len(banners), 71)
            checked = set()
            for banner in banners:
                for field in ('banner', 'detail_banner'):
                    name = banner['art'][field]
                    self.assertTrue(name in index, f"Unpackaged raid image: {banner['id']} {field} {name}")
                    raw = packed.read('assets/rules/assets/banner_art/' + name)
                    self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
                    self.assertTrue(all(struct.unpack('>II', raw[16:24])))
                    if name.startswith('event_'):
                        original = events[str(banner['raid_event_id'])]
                        self.assertEqual(hashlib.sha256(raw).hexdigest(), original['runtime_sha256'])
                    checked.add(name)
            self.assertEqual(len(checked), 72)


class RaidSummonOffers(SummonTransactions):
    # Reuse the in-memory campaign fixture; only the methods declared below run
    # when this module selects this class's own test cases.
    def coin_banner(self, coin=106301000):
        return dict(self.banner(), id='9800001', detail_id='98000011',
                    cost={'kind': 'item', 'item_id': coin, 'amount': 1},
                    reward_pool=[{'kind': 20, 'id': 106200100, 'count': 1, 'rate': 1}])

    def recovered(self):
        return ffbe_gacha._banner_doc(str(ROOT / 'source/server/gacha_raid.json'), note='test')

    def test_direct_raid_destination_survives_another_selected_archive_era(self):
        from gacha_archive import raid_summon_target, visible_banners, menu
        banners = self.recovered()
        target = next(b for b in banners if b['raid_event_id'] == '722')
        self.player.data['summon_archive'] = 'season4'
        self.assertNotIn(target['id'], {b['id'] for b in visible_banners(self.player, banners)})
        raid_summon_target(self.player, target['id'])
        self.assertIn(target['id'], {b['id'] for b in visible_banners(self.player, banners)})
        self.assertEqual(self.player.data['summon_archive'], 'season4')
        menu(self.player, banners, 'season4')
        self.assertNotIn(target['id'], {b['id'] for b in visible_banners(self.player, banners)})

    def test_every_ready_raid_has_its_own_coin_destination_and_usable_offer_rows(self):
        banners = self.recovered()
        by_id = {str(b['id']): b for b in banners}
        links = json.loads((ROOT / 'source/server/raid_summon_links.json').read_text('utf-8'))['links']
        events = {str(e['event_id']): e for e in json.loads((ROOT / 'source/server/raid_archive.json').read_text('utf-8'))['events']}
        self.assertEqual(len(banners), 71)
        for link in links:
            b, event = by_id[link['gacha_id']], events[link['event_id']]
            self.assertEqual(b['cost']['item_id'], event['raid_coin']['id'])
            self.assertIn(link['dungeon_id'], event.get('dungeon_ids', [event['dungeon_id']]))
            active = raid_summon.prepare(self.player, b)
            self.assertGreater(active['raid_batch_limit'], 1, b['name'])
            self.assertEqual(active['secondary_offer']['img_btn'], 'gacha_btn_c_multi')

    def test_only_three_explicit_source_reconstructions_are_used(self):
        banners = self.recovered()
        rebuilt = {b['raid_event_id']: b for b in banners if b.get('reconstructions')}
        self.assertEqual(set(rebuilt), {'3128', '3231', '6160'})
        self.assertEqual(raid_summon.prepare(self.player, rebuilt['6160'])['cost']['amount'], 400)
        for box in rebuilt['3231']['boxes']:
            reconstructed = [r for r in box if r.get('reconstruction')]
            self.assertEqual(len(reconstructed), 7)
            self.assertTrue(all(r['copies'] == 15 for r in reconstructed))

    def test_recovered_rewards_are_native_creditable_and_unlimited_rates_sum_to_one(self):
        seen = set()
        for b in self.recovered():
            pool = b.get('reward_pool', [])
            self.assertAlmostEqual(sum(r['rate'] for r in pool), 1, places=8, msg=b['name'])
            self.assertTrue(all(r['rate'] > 0 for r in pool), b['name'])
            rewards = list(pool) + [r['reward'] for box in b.get('boxes', []) for r in box]
            for reward in rewards:
                identity = json.dumps(reward, sort_keys=True)
                if identity in seen:
                    continue
                seen.add(identity)
                self.assertTrue(self.player._can_credit(reward), (b['name'], reward))
                self.assertEqual(self.player._grant_items([reward]), [reward], (b['name'], reward))

    def test_native_banner_cache_preserves_original_rows_and_links_each_raid(self):
        from build_raid_summon_cache import build_files
        from prepare_offline_cache import DATA, PROJECT, client_manifest, json_record, cbc_decrypt, key16
        manifest = client_manifest(PROJECT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
        token, key = next((t, r['key']) for t, r in manifest.items() if r['table'] == 'F_BANNER_MST')
        original = next((DATA / 'client/files').rglob('Ver*_' + token + '.dat')).read_text('ascii').splitlines()
        generated = next(iter(build_files().values())).decode('ascii').splitlines()
        self.assertEqual(generated[:len(original)], original)
        rows = {r['fSxqkF10']: r for r in (json_record(cbc_decrypt(key16(key), line)) for line in generated)}
        links = json.loads((ROOT / 'source/server/raid_summon_links.json').read_text('utf-8'))['links']
        schedules = {r['fSxqkF10'] for r in raid_summon.schedule_rows()}
        for link in links:
            row = rows[link['banner_id']]
            self.assertEqual((row['w2A76noc'], row['rUP3Gix0'], row['1X65WPLU']), ('6', '4', link['gacha_id']))
            self.assertIn(link['banner_id'], schedules)

    def test_ifrit_exposes_original_coin_single_and_batch_rows(self):
        b = self.coin_banner()
        with patch.object(ffbe_gacha, 'GACHA_MULTI_BTN', '1'):
            groups = ffbe_gacha.gacha_groups([b])
        rows = next(v for v in groups.values() if isinstance(v, list) and v and 'ijEey5f7' in v[0])
        self.assertEqual([r['ijEey5f7'] for r in rows], ['1', '2'])
        self.assertEqual([r['0GgK6ytT'] for r in rows], ['20:106301000:100:1', '20:106301000:100:50'])
        self.assertEqual(rows[1]['XFLm4Mx6'], 'gacha_btn_c_multi')
        self.assertEqual(rows[0]['XFLm4Mx6'], 'gacha_btn_c_default')
        for row in rows:
            for state in (1, 2):
                self.assertTrue((ROOT / 'data/cpk_extract/en/gacha/Ver58_gacha1' /
                                 (row['XFLm4Mx6'] + f'_{state}.png')).is_file())
        self.assertNotEqual(rows[0]['nqzG3b2v'], rows[1]['nqzG3b2v'])

    def test_normal_batch_charges_each_draw_and_awards_selected_quantity(self):
        b = self.coin_banner()
        self.player.grant_item(20, 106301000, 1000)
        active = raid_summon.prepare(self.player, b)
        request = json.dumps({'5yLD4dYI': [{'X1IuZnj2': b['id'],
                            'nqzG3b2v': active['secondary_offer']['detail_id'], '2RtVPS3b': '7'}]})
        before = self.player.item_count(20, 106200100)
        with patch('ffbe_gacha.all_banners', return_value=[b]):
            ffbe_gacha.serve_gacha({'5yLD4dYI': []}, request, '9fVIioy1')
        self.assertEqual(self.player.item_count(20, 106301000), 300)
        self.assertEqual(self.player.item_count(20, 106200100), before + 7)

    def test_over_limit_batch_does_not_spend_or_award(self):
        b = self.coin_banner()
        self.player.grant_item(20, 106301000, 10000)
        active = raid_summon.prepare(self.player, b)
        before = copy.deepcopy(self.player.data)
        request = json.dumps({'5yLD4dYI': [{'X1IuZnj2': b['id'],
                            'nqzG3b2v': active['secondary_offer']['detail_id'], '2RtVPS3b': '51'}]})
        with patch('ffbe_gacha.all_banners', return_value=[b]):
            ffbe_gacha.serve_gacha({'5yLD4dYI': []}, request, '9fVIioy1')
        self.assertEqual(self.player.data, before)

    def test_batch_offer_with_insufficient_coins_keeps_inventory_unchanged(self):
        b = self.coin_banner()
        self.player.grant_item(20, 106301000, 100)
        active = raid_summon.prepare(self.player, b)
        before = copy.deepcopy(self.player.data)
        request = json.dumps({'5yLD4dYI': [{'X1IuZnj2': b['id'],
                            'nqzG3b2v': active['secondary_offer']['detail_id'], '2RtVPS3b': '2'}]})
        with patch('ffbe_gacha.all_banners', return_value=[b]):
            ffbe_gacha.serve_gacha({'5yLD4dYI': []}, request, '9fVIioy1')
        self.assertEqual(self.player.data, before)

    def test_pending_original_box_sources_are_excluded_from_runtime_catalogue(self):
        records = ffbe_gacha._banner_doc(str(ROOT / 'source/server/gacha_named.json'), note='test')
        self.assertFalse({'9400151', '9400152', '9400153', '9400154'} & {str(b['id']) for b in records})

    def test_every_existing_source_backed_raid_has_both_native_offer_rows(self):
        by_id = {}
        for family in ('catalogue', 'community', 'named', 'authored', 'standard'):
            for b in ffbe_gacha._banner_doc(str(ROOT / f'source/server/gacha_{family}.json'), note='test'):
                by_id[str(b['id'])] = b
        selected = [b for b in by_id.values() if raid_summon.prepare(self.player, b).get('raid_batch_limit')]
        self.assertGreaterEqual(len(selected), 7)
        with patch.object(ffbe_gacha, 'GACHA_MULTI_BTN', '1'):
            groups = ffbe_gacha.gacha_groups(selected)
        rows = next(v for v in groups.values() if isinstance(v, list) and v and 'ijEey5f7' in v[0])
        for b in selected:
            own = [r for r in rows if r['X1IuZnj2'] == str(b['id'])]
            self.assertEqual([r['ijEey5f7'] for r in own], ['1', '2'], b['name'])

    def test_finite_box_batch_uses_current_detail_and_preserves_finite_slots(self):
        b = raid_summon.prepare(self.player, self.raid_box())
        coins = self.player.item_count(20, b['cost']['item_id'])
        with patch('gacha_box.secrets.randbelow', return_value=0):
            result = gacha_box.roll(self.player, b, b['secondary_offer']['detail_id'], 50)
        self.assertEqual(result['count'], 50)
        self.assertEqual(self.player.item_count(20, b['cost']['item_id']), coins - 20000)
        self.assertEqual(sum(gacha_box.state(self.player, b)['drawn']['0'].values()), 50)
        self.player.data['gacha']['boxes'][b['id']]['index'] = 1
        before = copy.deepcopy(self.player.data)
        self.assertIsNone(gacha_box.roll(self.player, b, b['secondary_offer']['detail_id'], 1))
        self.assertEqual(self.player.data, before)

    def test_homecoming_changes_price_and_batch_cap_after_last_box(self):
        b = dict(self.coin_banner(106308000), boxes=[[{}]] * 5, box_base_id=980001)
        finite = raid_summon.prepare(self.player, b)
        self.assertEqual((finite['cost']['amount'], finite['raid_batch_limit']), (200, 50))
        self.player.data.setdefault('gacha', {}).setdefault('boxes', {})[b['id']] = {'index': 5, 'drawn': {}}
        standard = raid_summon.prepare(self.player, b)
        self.assertEqual((standard['cost']['amount'], standard['raid_batch_limit']), (100, 500))
        self.assertNotEqual(finite['secondary_offer']['detail_id'], standard['secondary_offer']['detail_id'])

    def test_batch_box_can_advance_and_its_old_detail_cannot_advance_again(self):
        raw = self.raid_box()
        b = raid_summon.prepare(self.player, raw)
        bid = int(b['box_base_id'])
        drawn = {str(bid * 1000 + i + 1): e['copies']
                 for i, e in enumerate(b['boxes'][0]) if e.get('featured')}
        self.player.data.setdefault('gacha', {}).setdefault('boxes', {})[b['id']] = {'index': 0, 'drawn': {'0': drawn}}
        request = {'5yLD4dYI': [{'X1IuZnj2': b['id'], 'nqzG3b2v': b['secondary_offer']['detail_id']}]}
        with patch('ffbe_gacha.all_banners', return_value=[raw]), \
                patch('gacha_archive.visible_banners', return_value=[]), \
                patch('exvius_actions._refresh', return_value={}):
            gacha_box.next_box({}, request)
            self.assertEqual(gacha_box.state(self.player, b)['index'], 1)
            before = copy.deepcopy(self.player.data)
            gacha_box.next_box({}, request)
            self.assertEqual(self.player.data, before)


if __name__ == '__main__':
    names = [name for name in RaidSummonOffers.__dict__ if name.startswith('test_')]
    suite = unittest.TestSuite(RaidSummonOffers(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
