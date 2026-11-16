"""Exercise scoped JP rewards without loading or writing a player save."""
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
import exvius_raid_progress as raid
import exvius_actions_shops as shops


class Player:
    mode = 'live'

    def __init__(self, mid, sequence=1):
        self.data = {'exvius_repeat': {'attempt': {'mid': mid, 'sequence': sequence, 'status': 'pending'}}}
        self.dirty = False

    def _can_credit(self, reward):
        return reward['count'] > 0

    def _grant_items(self, rows):
        for row in rows:
            key = str(row['kind']) + ':' + str(row['id'])
            owned = self.data.setdefault('test_inventory', {})
            owned[key] = owned.get(key, 0) + row['count']
        return copy.deepcopy(rows)

    def deliver_mail(self, title, rows, message):
        self.data.setdefault('test_mail', []).append({'title': title, 'rewards': rows, 'message': message})
        return self.data['test_mail'][-1]

    def complete(self, cleared=True):
        self.data['exvius_repeat']['attempt'].update(status='completed', cleared=cleared)


class EarlierJPRewards(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'source/server/raid_archive.json').read_text('utf8'))
        self.source = json.loads((ROOT / 'Japan content/Earlier JP crossovers/Sources/Event rewards/original-event-reward-content.json').read_text('utf8'))

    def test_original_milestone_and_daily_counts(self):
        selected = [r for r in self.config['events'] if r.get('jp_original_scope') == 'earlier-jp-28']
        self.assertEqual(len(selected), 8)
        self.assertEqual(sum(len(r['personal_milestones']) for r in selected), 465)
        self.assertEqual(sum(len(r['mission_points']) for r in selected), 33)
        self.assertEqual(len(self.config['jp_daily_fragment_rewards']), 40)
        self.assertEqual(len(self.config['jp_mission_clear_rewards']), 5)

    def test_actual_selected_character_only_once_and_reload(self):
        for mid, contract in self.config['jp_daily_fragment_rewards'].items():
            for enemy, expected in contract['chosen_enemy_rewards'].items():
                with self.subTest(mid=mid, enemy=enemy):
                    player = Player(mid)
                    raid.observe_personal_raid(player, mid, {'Bi6hVv34': [{'xqartN26': enemy}]})
                    player.complete()
                    spec = {'09HRWXDf': [{'xF9Sr1a6': ''}]}
                    reply = raid.apply_personal_raid_result(player, spec, mid, '{}')
                    owned = copy.deepcopy(player.data)
                    self.assertEqual(player.data['test_inventory'], {'20:' + str(expected['id']): 10})
                    self.assertEqual(raid.apply_personal_raid_result(player, reply, mid, '{}'), reply)
                    self.assertEqual(player.data, owned)
                    player.data = json.loads(json.dumps(player.data))
                    raid.apply_personal_raid_result(player, spec, mid, '{}')
                    self.assertEqual(player.data, owned)
                    player.data['exvius_repeat']['attempt'] = {'mid': mid, 'sequence': 2, 'status': 'pending'}
                    raid.observe_personal_raid(player, mid, {'Bi6hVv34': [{'xqartN26': enemy}]})
                    player.complete()
                    raid.apply_personal_raid_result(player, spec, mid, '{}')
                    self.assertEqual(player.data['test_inventory'], owned['test_inventory'])

    def test_failed_daily_and_ambiguous_roster_grant_nothing(self):
        mid, contract = next(iter(self.config['jp_daily_fragment_rewards'].items()))
        enemy = next(iter(contract['chosen_enemy_rewards']))
        player = Player(mid)
        raid.observe_personal_raid(player, mid, {'Bi6hVv34': [{'xqartN26': enemy}]})
        player.complete(False)
        raid.apply_personal_raid_result(player, {}, mid, '{}')
        self.assertNotIn('test_inventory', player.data)
        player = Player(mid)
        with self.assertRaises(ValueError):
            raid.observe_personal_raid(player, mid, {'Bi6hVv34': [{'xqartN26': e} for e in contract['chosen_enemy_rewards']]})

    def test_ep_clear_fixed_without_damage_mail_once_bonus_currency_not_duplicated(self):
        mid = '45000105'
        player = Player(mid)
        raid.observe_personal_raid(player, mid, {'Bi6hVv34': [{'xqartN26': 'ordinary'}]})
        player.complete()
        result = raid.apply_personal_raid_result(player, {'09HRWXDf': [{}]}, mid, '{}')
        state = copy.deepcopy(player.data)
        saved = state['exvius_raid_progress']['personal_events']['4500']
        self.assertEqual(saved['points'], 1000)
        self.assertEqual(state['test_inventory']['20:106323900'], 564)
        self.assertNotIn('dg5ZV3kQ', result)
        raid.apply_personal_raid_result(player, result, mid, '{}')
        self.assertEqual(player.data, state)
        player.data['exvius_repeat']['attempt'] = {'mid': mid, 'sequence': 2, 'status': 'pending'}
        raid.observe_personal_raid(player, mid, {'Bi6hVv34': [{'xqartN26': '404071077'}]})
        player.complete()
        raid.apply_personal_raid_result(player, {}, mid, '{}')
        self.assertEqual(player.data['test_inventory']['20:106323900'], 564)
        self.assertEqual(player.data['exvius_raid_progress']['personal_events']['4500']['points'], 2000)

    def test_failed_ep_and_imperial_materials(self):
        for mid in ['44800105', '7020105']:
            player = Player(mid)
            raid.observe_personal_raid(player, mid, {'Bi6hVv34': []})
            player.complete(False)
            raid.apply_personal_raid_result(player, {}, mid, '{}')
            self.assertNotIn('test_inventory', player.data)
        player = Player('7020105'); player.complete()
        result = raid.apply_personal_raid_result(player, {'09HRWXDf': [{}]}, '7020105', '{}')
        owned = copy.deepcopy(player.data)
        self.assertEqual(len(owned['test_inventory']), 7)
        self.assertEqual(set(owned['test_inventory'].values()), {5})
        raid.apply_personal_raid_result(player, result, '7020105', '{}')
        self.assertEqual(player.data, owned)

    def test_actual_multipart_hp_and_partial_damage(self):
        player = Player('7380101')
        raid.observe_personal_raid(player, '7380101', {'Bi6hVv34': [{'xqartN26': 'boss'}],
            'bV34YIJQ': [{'xqartN26': 'boss', 'fh31sk7B': '900'}, {'xqartN26': 'boss', 'fh31sk7B': '100'}]})
        self.assertEqual(player.data['exvius_repeat']['attempt']['raid_boss_hp'], 1000)
        player.complete(False)
        raid.apply_personal_raid_result(player, {}, '7380101', json.dumps({'nSG9Jb1s': [{'NYb0Cri6': 'TOTAL_DAMAGE', '6gAX1BpC': '500'}]}))
        saved = player.data['exvius_raid_progress']['personal_events']['738']
        self.assertEqual(saved['points'], 400)
        self.assertEqual(player.data['test_inventory']['20:106301700'], 40)

    def test_trust_milestones_preserve_actual_percent_metadata(self):
        for event in self.config['events']:
            if event.get('jp_original_scope') != 'earlier-jp-28': continue
            for m in event['personal_milestones']:
                for r in m['rewards']:
                    if r['kind'] == 10 and str(r['id']).startswith(('904', '906')):
                        self.assertTrue(any(r.get('affinity_points', [])), r)
        moogle = next(m for e in self.config['events'] if e['event_id'] == '4500'
                      for m in e['personal_milestones'] if any(str(r['id']).startswith('906') for r in m['rewards']))
        player = Player('45000105')
        raid.observe_personal_raid(player, '45000105', {'Bi6hVv34': []})
        player.data['exvius_raid_progress'] = {'personal_events': {'4500': {'points': moogle['points'] - 1000,
            'shared_damage': 0, 'receipts': {}, 'mailed_milestones': []}}}
        player.complete(); raid.apply_personal_raid_result(player, {}, '45000105', '{}')
        self.assertTrue(any(row[3].get('affinity_points') == ['', '500'] for mail in player.data['test_mail'] for row in mail['rewards']))

    def test_all_exact_recipes_require_owned_book_and_keep_original_costs(self):
        contract = json.loads((ROOT / 'Japan content/Earlier JP crossovers/Sources/Event rewards/native-event-reward-import.json').read_text('utf8'))
        tables = {t['table']: {r[t['identity_fields'][0]]: r for r in t['rows']} for t in contract['tables']}
        for rid, row in tables['F_RECIPE_MST'].items():
            book = next(b for b in tables['F_RECIPE_BOOK_MST'].values() if rid in b['8Qt4Ccew'].split(','))
            bid = book['staFu8U1']; node = {'MpNE6gB5': rid, 'staFu8U1': bid}
            with patch.object(shops, '_table', side_effect=lambda t, k: tables[t]), patch.object(shops, '_rewards'), patch.object(shops, '_feature', return_value={'books': {bid: True}}):
                actual, mats, gil, reward = shops._recipe(node, 2)
                self.assertEqual(actual, row)
                self.assertEqual(gil, int(row['7UR4J2SE']) * 2)
                self.assertEqual(reward['count'], int(row['Qy5EvcK1']) * 2)
                self.assertEqual(mats, [dict(r, count=r['count'] * 2) for r in shops._triples(row['HS7V6Ww1'])])
            with patch.object(shops, '_table', side_effect=lambda t, k: tables[t]), patch.object(shops, '_feature', return_value={'books': {}}):
                with self.assertRaises(shops.Refused): shops._recipe(node)

    def test_imported_native_recipe_graph_and_indices(self):
        contract = json.loads((ROOT / 'Japan content/Earlier JP crossovers/Sources/Event rewards/native-event-reward-import.json').read_text('utf8'))
        for entry in contract['tables']:
            if entry['table'] not in ('F_RECIPE_MST', 'F_RECIPE_BOOK_MST', 'F_ITEM_MST', 'F_MEDAL_EXCHANGE_MST'): continue
            key = entry['identity_fields'][0]
            current = shops._table(entry['table'], key)
            for expected in entry['rows']:
                expected = dict(expected)
                if entry['table'] == 'F_ITEM_MST' and expected['tL6G9egd'] == '872100001':
                    expected['0HUPxDf1'] = '872100001'
                self.assertEqual(current[expected[key]], expected)
        books = shops._rows('F_RECIPE_BOOK_MST')
        imported = {r['staFu8U1'] for e in contract['tables'] if e['table'] == 'F_RECIPE_BOOK_MST' for r in e['rows']}
        other = {r['gJf3zp8a'] for r in books if r['staFu8U1'] not in imported}
        indices = [r['gJf3zp8a'] for r in books if r['staFu8U1'] in imported]
        self.assertEqual(len(indices), 46)
        self.assertEqual(len(set(indices)), 46)
        self.assertFalse(set(indices) & other)

    def test_final_scoped_display_text_has_no_placeholders(self):
        home = ROOT / 'Japan content/Earlier JP crossovers/Sources/Event rewards'
        final = json.loads((home / 'event-reward-final-en.json').read_text('utf8'))
        import re
        for table, labels in final.items():
            actual = {r['key']: r['v'][0] for r in map(json.loads, (ROOT / 'data/text_decoded' / (table + '.ndjson')).read_text('utf8').splitlines())}
            for key, expected in labels.items():
                self.assertEqual(actual[key], expected)
                self.assertNotIn(expected, ('collab', '<NA>', 'NA', '<blank>', ''))
                self.assertFalse(re.search(r'[\u3040-\u30ff\u3400-\u9fff]', expected))

    def test_shared_material_wallets_and_scoped_costs(self):
        home = ROOT / 'Japan content/Earlier JP crossovers/Sources'
        primary = json.loads((home / 'native-unit-id-map.json').read_text('utf8'))
        proof = json.loads((home / 'Event rewards/shared-common-wallet-reuse-plan.json').read_text('utf8'))
        self.assertEqual(len(proof['verified_aliases']), 40)
        self.assertEqual(len(primary['shared_common_item_ids']), 40)
        for row in proof['verified_aliases']:
            self.assertNotIn(row['source_id'], primary['mappings']['F_ITEM_MST'])
            self.assertIn(row['orphan_alias_id'], shops._table('F_ITEM_MST', 'tL6G9egd'))
            self.assertEqual(shops._table('F_ITEM_MST', 'tL6G9egd')[row['source_id']]['9J6uRe8f'], row['Global_stack_cap_preserved'])
        for change in proof['native_changes']:
            row = next(r for r in shops._rows(change['table']) if all(r.get(k) == v for k, v in change['identity'].items()))
            self.assertEqual(row[change['field']], change['after'])
        retired = set(primary['retained_common_item_alias_records'].values())
        for event in self.config['events']:
            if event.get('jp_original_scope') != 'earlier-jp-28': continue
            for milestone in event['personal_milestones']:
                self.assertFalse(any(r['kind'] == 20 and str(r['id']) in retired for r in milestone['rewards']))


if __name__ == '__main__': unittest.main()
