"""Real banner/transaction tests with metadata-only local fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
IOS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IOS / 'prototype'))
from demo_data import prepare
from summon_service import SummonError, SummonService


class SummonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = (IOS / '.local').resolve()
        scratch.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='summon-tests-', dir=scratch)
        cls.root = Path(cls.temporary.name).resolve()
        if not cls.root.is_relative_to(scratch):
            raise RuntimeError('Test directory escaped scratch root')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.data = prepare(cls.root / 'data')

    def setUp(self):
        self.save = self.root / (self._testMethodName + '.json')
        self.service = SummonService(self.data, self.save, demo=True, initial_lapis=10000)

    def test_single_uses_existing_banner_price_pool_and_grant(self):
        details = self.service.details('9100203')
        count = len(self.service.state()['units'])
        response = self.service.summon('9100203')
        self.assertEqual(response['state']['currencies']['lapis_free'], 9500)
        self.assertEqual(details['cost']['amount'], 500)
        self.assertEqual(len(response['state']['units']), count + 1)
        award = response['result']['awards'][0]
        self.assertIn(award['unit_id'], {r['unit_id'] for r in details['base_pool']})
        self.assertIn(award['instance_id'], {r['instance_id'] for r in response['state']['units']})

    def test_multi_charges_once_and_honors_guaranteed_slot(self):
        response = self.service.summon('9100203', 'secondary')
        self.assertEqual(response['state']['currencies']['lapis_free'], 5000)
        self.assertEqual(len(response['result']['awards']), 11)
        self.assertTrue(any(int(r['granted_rarity']) >= 4 for r in response['result']['awards']))
        ids = [r['instance_id'] for r in response['state']['units']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_insufficient_currency_changes_neither_memory_nor_disk(self):
        service = SummonService(self.data, self.root / 'poor.json', demo=True)
        before, saved = service.state(), service.save_path.read_bytes()
        with self.assertRaises(SummonError) as raised:
            service.summon('9100203')
        self.assertEqual(raised.exception.code, 'summon_refused')
        self.assertEqual(service.state(), before)
        self.assertEqual(service.save_path.read_bytes(), saved)

    def test_published_tier_weights_preserved(self):
        original = next(b for b in json.loads((IOS.parent / 'server/gacha_authored.json').read_text(encoding='utf-8'))['banners']
                        if str(b['id']) == '9100203')
        self.assertEqual(self.service.catalogue['9100203'], original)
        details = self.service.details('9100203')
        for tier in original['pool']['tiers']:
            actual = sum(row['probability'] for row in details['base_pool']
                         if int(row['rarity']) == tier['rarity'])
            self.assertAlmostEqual(actual, tier['rate'])
        self.assertEqual({b['id'] for b in self.service.banners()}, {'9100203', '49'})

    def test_fresh_process_reload_preserves_awards_currency_and_counters(self):
        self.service.summon('49', 'secondary')
        expected = self.service.state()
        completed = subprocess.run([sys.executable, '-B', str(IOS / 'prototype/summon_cli.py'),
            '--demo', '--workspace', str(self.root), '--save', str(self.save), '--json', 'state'],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(completed.stdout), expected)
        restored = SummonService(self.data, self.save, demo=True, initial_lapis=999999)
        self.assertEqual(restored.state(), expected)  # startup never refills an existing campaign
        self.assertEqual(restored.player.data['gacha'], self.service.player.data['gacha'])

    def test_failed_save_rolls_back_awards_and_currency(self):
        before, saved = copy.deepcopy(self.service.player.data), self.save.read_bytes()
        with patch.object(self.service.player, 'save', return_value=False):
            with self.assertRaises(SummonError) as raised:
                self.service.summon('9100203')
        self.assertEqual(raised.exception.code, 'save_failed')
        self.assertEqual(self.service.player.data, before)
        self.assertEqual(self.save.read_bytes(), saved)

    def test_invalid_offer_and_banner_do_not_change_campaign(self):
        before = self.service.state()
        for banner, offer in [('missing', 'primary'), ('49', 'arbitrary')]:
            with self.assertRaises(SummonError):
                self.service.summon(banner, offer)
        self.assertEqual(self.service.state(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
