"""Protect banner-specific eligibility across every staged offer and guarantee."""
import copy
import json
from pathlib import Path
import unittest

from audit_summon_pools import ROOT, FAMILIES, audit, repair_document, unit_evidence


class SummonPoolEligibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT / 'custom-engine/build/fork-client/assets/rules'
        cls.docs = {f: json.loads((folder / ('gacha_' + f + '.json')).read_text('utf-8')) for f in FAMILIES}
        cls.evidence = unit_evidence(cls.docs)
        cls.by_name = {name: uid for uid, name in cls.evidence['labels'].items()}

    def test_collaboration_and_seasonal_source_labels_are_limited(self):
        for name in ('A2 -Neo Vision-', '2B -Neo Vision-', 'Sora (KHIII)', 'Christine'):
            self.assertIn(self.by_name[name], self.evidence['limited'], name)

    def test_ordinary_banner_excludes_collaborations_and_known_future_units(self):
        rain = self.by_name['Rain -Neo Vision-']
        a2 = self.by_name['A2 -Neo Vision-']
        rhus = self.by_name['Azure and Crimson Blades Rhus']
        banner = {'id': 'test', 'name': 'Ordinary summon', 'release': '2024-06-01',
                  'pool': {'tiers': [{'rarity': 7, 'rate': 1, 'units': [rain, a2, rhus]}]}}
        repair_document({'banners': [banner]}, self.evidence)
        self.assertEqual(banner['pool']['tiers'][0]['units'], [rain])
        self.assertEqual(banner['pool']['tiers'][0]['rate'], 1)

    def test_collaboration_keeps_its_own_units_and_rejects_another_collaboration(self):
        two_b, a2, sora = (self.by_name[name] for name in ('2B -Neo Vision-', 'A2 -Neo Vision-', 'Sora (KHIII)'))
        banner = {'id': 'test', 'name': 'NieR summon', 'release': '2024-01-01',
                  'community': {'unit_ids': [two_b, a2]},
                  'pool': {'tiers': [{'rarity': 7, 'rate': 1, 'units': [two_b, a2, sora],
                                      'featured': [two_b], 'featured_share': .5}]}}
        repair_document({'banners': [banner]}, self.evidence)
        self.assertEqual(banner['pool']['tiers'][0]['units'], [two_b, a2])
        self.assertEqual(banner['pool']['tiers'][0]['featured_share'], .5)

    def test_every_staged_banner_and_nested_offer_passes_the_audit(self):
        report = audit(self.docs)
        self.assertEqual(report['summary']['banner_records'], 820)
        failures = [(r['family'], r['id'], r['issues']) for r in report['banners'] if r['issues']]
        self.assertFalse(failures, str([(f, bid, [i['kind'] for i in issues]) for f, bid, issues in failures[:8]]))

    def test_contemporary_holiday_simulator_pool_is_not_erased(self):
        banner = copy.deepcopy(next(b for b in self.docs['community']['banners'] if b['id'] == '9100076'))
        original = copy.deepcopy(banner['pool'])
        repair_document({'banners': [banner]}, self.evidence)
        self.assertEqual(banner['pool'], original)
        roots = {self.evidence['mst'][r['unit_id']]['woghJa61'] for r in original}
        self.assertIn(self.by_name['Christine'], roots)

    def test_no_original_rate_weights_are_changed_when_expanding_an_unbounded_tier(self):
        base = next(b for b in self.docs['named']['banners'] if b['id'] == '9200001')
        banner = copy.deepcopy(base)
        for tier in banner['pool']['tiers']:
            tier.pop('units', None)
        weights = [(t['rarity'], t['rate'], t.get('featured_share')) for t in banner['pool']['tiers']]
        repair_document({'banners': [banner]}, self.evidence)
        self.assertEqual(weights, [(t['rarity'], t['rate'], t.get('featured_share')) for t in banner['pool']['tiers']])
        self.assertTrue(all(t['units'] for t in banner['pool']['tiers']))

    def test_shift_forms_are_not_independently_summonable(self):
        from player_state import unit_roots_by_rarity
        roots = {uid for group in unit_roots_by_rarity().values() for uid in group}
        self.assertIn('401013907', roots)  # A2, owned form.
        self.assertNotIn('401013917', roots)  # Its Brave Shift form.

    def test_a_single_eligible_nv_keeps_the_whole_nv_tier(self):
        from player_state import expand_pool
        cloud = self.by_name['Cloud (FFVII REMAKE)']
        pool = expand_pool({'pool': {'tiers': [{'rarity': 7, 'rate': .0125,
                            'units': [cloud], 'featured': [cloud], 'featured_share': .8}]}})
        self.assertEqual(len(pool), 1)
        self.assertAlmostEqual(pool[0]['rate'], .0125)

    def test_old_jp_nv_banners_have_only_contemporary_nv_units(self):
        named = {b['id']: b for b in self.docs['named']['banners']}
        for bid in ('9200103', '9200104', '9200106', '9200107', '9200108'):
            tier = next(t for t in named[bid]['pool']['tiers'] if t['rarity'] == 7)
            self.assertEqual(tier['units'], ['207002007'], bid)
            self.assertEqual(tier['rate'], .01, bid)
        rain = next(t for t in named['9200105']['pool']['tiers'] if t['rarity'] == 7)
        self.assertEqual(set(rain['units']), {'207002007', '100031007'})
        self.assertEqual(rain['rate'], .01)
        self.assertEqual(named['9200105']['release'], '2020-05-12')

    def test_jp_ffvii_and_ability_banners_obey_their_printed_restrictions(self):
        named = {b['id']: b for b in self.docs['named']['banners']}
        ff7 = named['9200103']
        for tier in ff7['pool']['tiers']:
            if tier['rarity'] >= 5:
                self.assertTrue(all(u.startswith('207') for u in tier['units']))
        for bid, expected in (('9200101', {'207000405', '207001105', '207000605'}),
                              ('9200102', {'213001005', '213001105'})):
            five = next(t for t in named[bid]['pool']['tiers'] if t['rarity'] == 5)
            self.assertEqual(set(five['units']), expected)
            self.assertEqual(set(named[bid]['guarantee']['any_of']), expected)
            self.assertTrue(all(self.evidence['mst'][u]['woghJa61'] == u for u in expected))

    def test_jp_ticket_floors_and_material_only_summons_are_preserved(self):
        named = {b['id']: b for b in self.docs['named']['banners']}
        self.assertEqual({t['rarity'] for t in named['9200107']['pool']['tiers']}, {4, 5, 7})
        self.assertEqual({t['rarity'] for t in named['9200108']['pool']['tiers']}, {5, 7})
        for bid in ('9200109', '9200111'):
            for tier in named[bid]['pool']['tiers']:
                self.assertTrue(all(u.startswith('9') for u in tier['units']))
                self.assertNotEqual(tier['rarity'], 7)

    def test_jp_roster_audit_rejects_a_later_unit_despite_valid_rate(self):
        docs = copy.deepcopy(self.docs)
        banner = next(b for b in docs['named']['banners'] if b['id'] == '9200104')
        next(t for t in banner['pool']['tiers'] if t['rarity'] == 7)['units'].append(self.by_name['Azure and Crimson Blades Rhus'])
        row = next(b for b in audit(docs)['banners'] if b['id'] == '9200104')
        self.assertIn('incorrect_JP_banner_roster', {issue['kind'] for issue in row['issues']})

    def test_all_existing_unit_forms_have_english_names_without_importing_units(self):
        import hashlib
        import zipfile
        from decode_client_data import decode
        folder = ROOT / 'custom-engine/build/fork-client/assets/rules'
        with zipfile.ZipFile(folder / 'native_content.zip') as patch:
            native = patch.read('native/localized_texts/en/Ver229_sZE3Lhgj.dat')
            static = patch.read('static/text_decoded/F_TEXT_UNITS_NAME.ndjson')
            registry = patch.read('native/mst/Ver710_i5QEJpua.dat')
        _, actual = decode(native, '3IfWAnJ3', localized=True)
        actual = {row['key']: row for row in actual}
        static_rows = {row['key']: row for row in map(json.loads, static.splitlines())}
        self.assertEqual(actual, static_rows)
        with zipfile.ZipFile(ROOT / 'source/build/distribution/assets/exvius-kira-r7.zip') as baseline:
            previous = list(map(json.loads, baseline.read('static/text_decoded/F_TEXT_UNITS_NAME.ndjson').splitlines()))
        for row in previous:
            self.assertEqual(actual[row['key']], row)
        missing = set(self.evidence['mst']) - {row['key'].rsplit('_', 1)[-1] for row in previous}
        self.assertEqual(len(missing), 222)
        self.assertTrue(all('MST_UNIT_NAME_' + uid in actual for uid in self.evidence['mst']))
        self.assertEqual(len(self.evidence['mst']), 3313)
        from decode_client_data import client_manifest
        info = next(v for v in client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk').values()
                    if v['table'] == 'F_LOCALIZED_TEXT_MST')
        _, index = decode(registry, info['key'])
        entry = next(r for r in index if r['a4hXTIm0'] == 'F_TEXT_UNITS_NAME')
        self.assertEqual(entry['zptmZGqa'], hashlib.md5(native).hexdigest())
        self.assertEqual(int(entry['MLOSu5E0']), len(native))

    def test_test_profile_is_separate_and_carries_every_raid_coin(self):
        import hashlib
        folder = ROOT / 'custom-engine/build/fork-client/assets/rules'
        profile = json.loads((folder / 'save_profile.json').read_text('utf-8'))
        raw = (folder / profile['seed']).read_bytes()
        seed = json.loads(raw)
        self.assertEqual(profile['slot'], 'testsave')
        self.assertEqual(seed['meta']['slot'], 'testsave')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), profile['seed_id'])
        self.assertEqual(seed['currencies']['lapis_free'], 10_000_000)
        self.assertEqual(seed['currencies']['gil'], 100_000_000)
        self.assertEqual(len(seed['beasts']), 18)
        self.assertEqual(len(seed['progress']['cleared_missions']), 2732)
        coins = {int(b['cost']['item_id']) for b in self.docs['raid']['banners']}
        for name in ('raid_archive.json', 'raid_rewards.json'):
            for event in json.loads((folder / name).read_text('utf-8'))['events']:
                if event.get('raid_coin'):
                    coins.add(int(event['raid_coin']['id']))
        inventory = {int(r['item_id']): int(r['count']) for r in seed['inventory']['items'] if str(r['item_type']) == '20'}
        self.assertEqual(len(coins), 70)
        self.assertTrue(all(inventory.get(coin) == 1_000_000 for coin in coins))


if __name__ == '__main__':
    unittest.main()
