"""Isolated shop-action checks against the shipped masters. Never load or save a slot.

Run with FFBE_DATA set, using the isolated import command in the implementation job.
Synthetic feature state below provisions legacy crafting slots and received
gifts. Recipe purchases also exercise the normal fresh-account acquisition path.
"""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

import exvius_actions_shops as shops
import ffbe_state
from ffbe_state import State
from player_state import PlayerState, _load_ndjson, switch_position


class ActionsShops(unittest.TestCase):
    seen = set()

    def setUp(self):
        self.old_player = State.player
        self.player = PlayerState.load('/nonexistent', slot='selftest-shops')
        State.player = self.player
        self.player.currencies.update(gil=10000000, lapis_free=5000)
        self.player.dirty = False
        self.iid = self.player.data['roster'][0]['instance_id']

    def tearDown(self):
        State.player = self.old_player

    def call(self, rid, group=None, node=None, spec=None):
        self.seen.add(rid)
        request = {group: node if isinstance(node, list) else [node]} if group else {}
        original = deepcopy(request)
        default = {'sentinel': []} if spec is None else spec
        saved = deepcopy(default)
        result = shops.HANDLERS[rid](default, request)
        self.assertIsInstance(result, dict)
        self.assertIn(shops.UNIT_GROUP, result)
        self.assertIn('0dNXQa3R', result)
        self.assertIn('3oU9Ktb7', result)
        self.assertEqual(default, saved, 'handler mutated the shared default reply')
        self.assertEqual(request, original, 'handler mutated the request')
        return result

    def unchanged(self, rid, group, node):
        before = deepcopy(self.player.data)
        notes = len(ffbe_state.NOTES)
        self.player.dirty = False
        out = self.call(rid, group, node)
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)
        self.assertGreater(len(ffbe_state.NOTES), notes)
        return out

    def seed_costs(self, text, multiplier=1):
        for row in shops._triples(text):
            if row['kind'] == 21:
                self.player.grant_equipment(row['id'], row['count'] * multiplier)
            else:
                self.player.grant_item(row['kind'], row['id'], row['count'] * multiplier)

    def provision_craft(self):
        self.player.data['exvius_craft'] = {
            'books': {'901000010': True}, 'slots': {'20:1': {'recipe': 0, 'join_reason': 0}}}
        row = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')['901000010']
        self.seed_costs(row['HS7V6Ww1'], 10)
        return row

    def test_item_buy_recomputes_price_and_grants_full_bag(self):
        row = _load_ndjson('F_ITEM_MST.ndjson', 'tL6G9egd')['101000100']
        price = int(row['E61qF5Lp']) * 2
        gil = self.player.currencies['gil']
        out = self.call('sxK2HG6T', '2aciVI9Y', {
            'Gh92V3Tx': 1101, 'j9NS0H15': '20:101000100:2', 'U1uaXph4': price})
        self.assertEqual(self.player.item_count(20, 101000100), 2)
        self.assertEqual(self.player.currencies['gil'], gil - price)
        self.assertEqual(out['0dNXQa3R'], self.player.item_rows())
        self.assertTrue(self.player.dirty)
        for entries, preview in [('20:101000100:2', 1), ('20:101000100:-1', price),
                                 ('20:101000100:1,20:999:1', price)]:
            self.unchanged('sxK2HG6T', '2aciVI9Y', {
                'Gh92V3Tx': 1101, 'j9NS0H15': entries, 'U1uaXph4': preview})

    def test_item_buy_equipment_and_materia_projections(self):
        towns = _load_ndjson('F_TOWN_STORE_MST.ndjson', 'Z20mNDvL')
        products = _load_ndjson('F_STORE_ITEM_MST.ndjson')['__rows__']
        for kind in (21, 22):
            product = next(p for p in products if p['YWF08vZS'] == str(kind)
                           and towns[p['Z20mNDvL']]['kaG4xf3I'] == '1'
                           and int(shops._product(kind, p['6uIYE15X'])['E61qF5Lp']) > 0)
            iid = product['6uIYE15X']
            cost = int(shops._product(kind, iid)['E61qF5Lp'])
            out = self.call('sxK2HG6T', '2aciVI9Y', {
                'Gh92V3Tx': towns[product['Z20mNDvL']]['Gh92V3Tx'],
                'j9NS0H15': f'{kind}:{iid}:1', 'U1uaXph4': cost})
            group, key = ('MBPCGT84', 'J1YX9kmM') if kind == 21 else ('rL81fVUI', 'H5jBL0Vf')
            self.assertTrue(any(r[key] == iid for r in out[group]))

    def test_buy_batch_insufficient_gil_is_atomic(self):
        self.player.currencies['gil'] = 0
        price = int(shops._product(20, 101000100)['E61qF5Lp'])
        self.unchanged('sxK2HG6T', '2aciVI9Y', {
            'Gh92V3Tx': 1101, 'j9NS0H15': '20:101000100:1', 'U1uaXph4': price})

    def test_equipment_sale_survives_state_reload(self):
        from exvius_actions import item_sell
        gil = self.player.currencies['gil']
        self.call('sxK2HG6T', '2aciVI9Y', {
            'Gh92V3Tx': 1101, 'j9NS0H15': '21:301000200:1', 'U1uaXph4': 100})
        out = item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': '21:301000200:1', '97h4mIQo': 10}]})
        reloaded = PlayerState(json.loads(json.dumps(self.player.data)))
        self.assertEqual(reloaded.currencies['gil'], gil - 90)
        self.assertFalse(any(r['J1YX9kmM'] == '301000200' for r in reloaded.equip_item_rows()))
        self.assertEqual(out['MBPCGT84'], reloaded.equip_item_rows())
        self.assertTrue(self.player.dirty)

    def test_equipment_sale_preserves_shifted_form_wearer(self):
        self.player.grant_equipment(301000200, 2)
        self.player.data['roster'][0]['shift_equipment'] = {'0': '301000200'}
        before = deepcopy(self.player.data)
        shops.item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': '21:301000200:2', '97h4mIQo': 20}]})
        self.assertEqual(self.player.data, before, 'sale consumed a worn Brave Shift copy')
        out = shops.item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': '21:301000200:1', '97h4mIQo': 10}]})
        self.assertEqual(next(r['Qy5EvcK1'] for r in out['MBPCGT84'] if r['J1YX9kmM']=='301000200'), '1')
        self.reopen()
        self.assertEqual(self.player.data['roster'][0]['shift_equipment'], {'0': '301000200'})

    def test_town_chest_reports_credit_once_across_reload(self):
        from exvius_field_treasures import serve, GROUP
        from player_state import _serialise, _normalise
        req = json.dumps({'JcxS6A8N': [{'Gh92V3Tx': '1101', 'NiG2wL3A': '1101008'}]})
        before = self.player.item_count(20, 101000100)
        out = serve({'sentinel': []}, req)
        self.assertEqual(self.player.item_count(20, 101000100), before + 1)
        self.assertEqual(next(r['NiG2wL3A'] for r in out[GROUP]
                              if r['4tNM5fGC'] == '1101008'), '20:101000100:1')
        self.assertIn(switch_position(40004008)[1], self.player.switches[switch_position(40004008)[0]])
        State.player = self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
        serve({}, req)
        self.assertEqual(self.player.item_count(20, 101000100), before + 1)

    def test_town_chest_unknown_wrong_town_and_frozen_do_not_credit(self):
        from exvius_field_treasures import serve
        for town, iid in [('999', '1101008'), ('1101', '999')]:
            before = deepcopy(self.player.data)
            serve({}, json.dumps({'JcxS6A8N': [{'Gh92V3Tx': town, 'NiG2wL3A': iid}]}))
            self.assertEqual(self.player.data, before)
        self.player.mode = 'frozen'
        before = deepcopy(self.player.data)
        serve({}, json.dumps({'JcxS6A8N': [{'Gh92V3Tx': '1101', 'NiG2wL3A': '1101008'}]}))
        self.assertEqual(self.player.data, before)

    def mission_chest_request(self, raw='60:1000000020:1:90001204', mid='9001101'):
        return json.dumps({'jQsE54Iz': [{'qo3PECw6': mid, 'dIPkNn61': '90001199,90001204'}],
                           '09HRWXDf': [{'S4U09svH': '0', 'Wdi3MAs2': '0', 'Z7G0yxXe': raw}]})

    def complete_chest_attempt(self):
        self.player.data['exvius_repeat'] = {'attempt': {
            'mid': '9001101', 'sequence': 1, 'status': 'completed',
            'cleared': False, 'normal_rewards_recorded': True}}

    def test_mission_recipe_chest_persists_and_retries_keep_display_without_paying(self):
        from exvius_field_treasures import serve
        from player_state import _serialise, _normalise
        self.complete_chest_attempt()
        spec = {'09HRWXDf': [{}]}
        req = self.mission_chest_request()
        out = serve(spec, req)
        self.assertEqual(spec, {'09HRWXDf': [{}]})
        self.assertEqual(out['09HRWXDf'][0]['eAM5B1qt'], '1000000020')
        self.assertTrue(self.player.data['exvius_craft']['books']['1000000020'])
        self.assertEqual(self.player.data['exvius_field_treasures'], ['610000058'])
        State.player = self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
        before = deepcopy(self.player.data)
        self.assertEqual(serve(spec, req)['09HRWXDf'], out['09HRWXDf'])
        self.assertEqual(self.player.data, before)

    def test_earth_shrine_exploration_chests_settle_items_equipment_and_recipe_once(self):
        from exvius_field_treasures import serve, catalogue
        from player_state import _serialise, _normalise
        rows = [row for row in catalogue().values() if row.get('mission') == 1110104]
        self.assertEqual(len(rows), 7)
        self.player.data['exvius_repeat'] = {'attempt': {
            'mid': '1110104', 'sequence': 1, 'status': 'completed',
            'cleared': False, 'normal_rewards_recorded': True}}
        req = json.dumps({'jQsE54Iz': [{'qo3PECw6': '1110104',
                         'dIPkNn61': ','.join(str(r['switch']) for r in rows)}],
                         '09HRWXDf': [{'R1kg3EBA': ','.join(
                             r['rewards'] + ':' + str(r['switch']) for r in rows)}]})
        before = self.player.item_count(20, 101000100)
        old_equipment = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in self.player.equip_item_rows()}
        out = serve({'09HRWXDf': [{}]}, req)
        self.assertEqual(self.player.item_count(20, 101000100), before + 2)
        equipment = {r['J1YX9kmM']: r['Qy5EvcK1'] for r in self.player.equip_item_rows()}
        self.assertEqual(int(equipment['302000100']), old_equipment.get('302000100', 0) + 1)
        self.assertEqual(int(equipment['406000100']), old_equipment.get('406000100', 0) + 1)
        self.assertEqual(out['09HRWXDf'][0]['eAM5B1qt'], '905000740')
        State.player = self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
        saved = deepcopy(self.player.data)
        serve({'09HRWXDf': [{}]}, req)
        self.assertEqual(self.player.data, saved)

    def test_mission_chest_rejects_wrong_reward_mission_switch_and_uncompleted_attempt(self):
        from exvius_field_treasures import serve
        spec = {'09HRWXDf': [{}]}
        self.complete_chest_attempt()
        for req in (self.mission_chest_request(raw='60:1000000020:99:90001204'),
                    self.mission_chest_request(mid='1110101'),
                    self.mission_chest_request(raw='60:1000000020:1:90001205')):
            before = deepcopy(self.player.data)
            self.assertEqual(serve(spec, req)['09HRWXDf'], [{}])
            self.assertEqual(self.player.data, before)
        for status, cleared, recorded in [('pending', True, True), ('completed', False, False)]:
            self.complete_chest_attempt()
            self.player.data['exvius_repeat']['attempt'].update(
                status=status, cleared=cleared, normal_rewards_recorded=recorded)
            before = deepcopy(self.player.data)
            serve(spec, self.mission_chest_request())
            self.assertEqual(self.player.data, before)
        self.complete_chest_attempt()
        self.player.mode = 'frozen'
        before = deepcopy(self.player.data)
        serve(spec, self.mission_chest_request())
        self.assertEqual(self.player.data, before)

    def test_mission_chest_failure_rolls_back_ownership_and_receipt(self):
        from exvius_field_treasures import serve
        self.complete_chest_attempt()
        before = deepcopy(self.player.data)
        with patch.object(self.player, '_grant_items', return_value=[]):
            with self.assertRaises(RuntimeError):
                serve({'09HRWXDf': [{}]}, self.mission_chest_request())
        self.assertEqual(self.player.data, before)

    def test_empty_exploration_result_omits_template_loot_instead_of_empty_csv(self):
        from ffbe_battle import mission_end_echo
        from ffbe_config import RESULT_ITEM_TOKENS
        spec = {'09HRWXDf': [{key: '20:101000100:1' for key in RESULT_ITEM_TOKENS}]}
        original = deepcopy(spec)
        out = mission_end_echo(spec, self.mission_chest_request())
        self.assertTrue(all(key not in out['09HRWXDf'][0] for key in RESULT_ITEM_TOKENS))
        self.assertEqual(out['09HRWXDf'][0]['16LQuC5r'], '0')
        self.assertEqual(spec, original)

    def test_exploration_exit_settles_recipe_through_real_result_transform_order(self):
        from ffbe_battle import mission_end_echo, credit_mission_rewards, record_pushed_switches
        from exvius_repeat import begin_attempt, repeat_challenge_rewards
        from exvius_field_treasures import serve
        req = self.mission_chest_request()
        begin_attempt(self.player, '9001101')
        spec = {'09HRWXDf': [{'wuUakq71': '10', 'xF9Sr1a6': '20:101000100:1',
                             'Z7G0yxXe': '20:290050200:1'}]}
        out = mission_end_echo(spec, req)
        out = credit_mission_rewards(req, out)
        out = repeat_challenge_rewards(out, '9001101', req)
        record_pushed_switches(req)
        out = serve(out, req)
        self.assertFalse(self.player.data['exvius_repeat']['attempt']['cleared'])
        self.assertEqual(out['09HRWXDf'][0]['eAM5B1qt'], '1000000020')
        self.assertNotIn('xF9Sr1a6', out['09HRWXDf'][0])
        self.assertNotIn('Z7G0yxXe', out['09HRWXDf'][0])
        self.assertTrue(self.player.data['exvius_craft']['books']['1000000020'])
        self.assertEqual(self.player.item_count(20, 101000100), 0)
        kind, index = switch_position(90001199)
        self.assertIn(index, self.player.switches[kind])

    def test_captured_gl9_exploration_reward_field_settles_and_reloads_once(self):
        from ffbe_battle import mission_end_echo, credit_mission_rewards, record_pushed_switches
        from exvius_repeat import begin_attempt, repeat_challenge_rewards
        from exvius_field_treasures import serve
        from player_state import _serialise, _normalise
        # Gameplay capture 20261028T160118_0020: GL9 sends these two opened
        # chests in Z7G0yxXe, with no R1kg3EBA field at all.
        req = json.dumps({
            'jQsE54Iz': [{'qo3PECw6': '1110104', 'dIPkNn61': '40002003,40002005'}],
            '09HRWXDf': [{'S4U09svH': '20', 'Wdi3MAs2': '5',
                           'Z7G0yxXe': '20:101000100:1:40002003,20:102000100:1:40002005'}]})
        before = [self.player.item_count(20, iid) for iid in (101000100, 102000100)]
        begin_attempt(self.player, '1110104')
        out = mission_end_echo({'09HRWXDf': [{}]}, req)
        out = credit_mission_rewards(req, out)
        out = repeat_challenge_rewards(out, '1110104', req)
        record_pushed_switches(req)
        out = serve(out, req)
        self.assertEqual([self.player.item_count(20, iid) for iid in (101000100, 102000100)],
                         [count + 1 for count in before])
        self.assertEqual(set(self.player.data['exvius_field_treasures']),
                         {'111010403', '111010405'})
        self.assertEqual(out['09HRWXDf'][0]['Z7G0yxXe'], '20:101000100:1,20:102000100:1')
        State.player = self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
        saved = deepcopy(self.player.data)
        retry = serve({'09HRWXDf': [{}]}, req)
        self.assertEqual(retry['09HRWXDf'][0]['Z7G0yxXe'], out['09HRWXDf'][0]['Z7G0yxXe'])
        self.assertEqual(self.player.data, saved)

    def test_map_result_switches_require_matching_settled_attempt_and_live_player(self):
        from ffbe_battle import record_pushed_switches
        for state in ('absent', 'pending', 'wrong-mission', 'frozen'):
            self.player.data.pop('exvius_repeat', None)
            self.player.mode = 'live'
            if state != 'absent':
                self.complete_chest_attempt()
            if state == 'pending':
                self.player.data['exvius_repeat']['attempt']['status'] = 'pending'
            if state == 'wrong-mission':
                self.player.data['exvius_repeat']['attempt']['mid'] = '1110101'
            if state == 'frozen':
                self.player.mode = 'frozen'
            before = deepcopy(self.player.data)
            record_pushed_switches(self.mission_chest_request())
            self.assertEqual(self.player.data, before)

    def test_pushed_chest_switch_waits_for_valid_reward_receipt(self):
        from ffbe_battle import record_pushed_switches
        self.complete_chest_attempt()
        record_pushed_switches(self.mission_chest_request(raw='60:1000000020:99:90001204'))
        kind, index = switch_position(90001204)
        self.assertNotIn(index, self.player.switches.get(kind, set()))


    def test_sale_invalid_batch_preserves_equipment_and_gil(self):
        from exvius_actions import item_sell
        self.player.grant_equipment(301000200, 1)
        for selected, price in [('21:301000200:1', 11),
                                ('21:301000200:1,21:301000200:1', 20),
                                ('21:301000200:1,20:999:1', 10),
                                ('21:301000200:0', 0)]:
            before = deepcopy(self.player.data)
            item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': selected, '97h4mIQo': price}]})
            self.assertEqual(self.player.data, before)
        self.player.mode = 'frozen'
        before = deepcopy(self.player.data)
        item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': '21:301000200:1', '97h4mIQo': 10}]})
        self.assertEqual(self.player.data, before)

    def test_sale_keeps_equipment_worn_by_starter_units(self):
        from exvius_actions import item_sell
        iid = '301000200'
        for unit in self.player.data['roster']:
            unit['equipment'] = {'weapon': iid}
        self.player.grant_equipment(iid, 1)  # one spare in addition to the two worn copies
        unit_rows = deepcopy(self.player.data['roster'])
        price = int(shops._product(21, iid)['bz6RS3pI'])
        out = item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': f'21:{iid}:1', '97h4mIQo': price}]})
        self.assertEqual(next(r['Qy5EvcK1'] for r in out['MBPCGT84'] if r['J1YX9kmM'] == iid), '2')
        self.assertEqual(self.player.data['roster'], unit_rows)
        before = deepcopy(self.player.data)
        item_sell({}, {'2tHu3Chy': [{'8X7LwE3r': f'21:{iid}:1', '97h4mIQo': price}]})
        self.assertEqual(self.player.data, before)

    def test_item_buy_recipe_uses_retail_price_and_native_ownership(self):
        book = '901000010'
        row = shops._product(60, book)
        price = int(row['7UR4J2SE'])
        self.assertEqual(price, 30)
        before = self.player.currencies['gil']
        out = self.call('sxK2HG6T', '2aciVI9Y', {
            'Gh92V3Tx': 1101, 'j9NS0H15': '60:' + book + ':1', 'U1uaXph4': price})
        self.assertTrue(self.player.data['exvius_craft']['books'][book])
        self.assertEqual(self.player.currencies['gil'], before - price)
        self.assertEqual(out['ZrDPm3j5'], self.player.recipe_book_rows())
        index = int(row['gJf3zp8a'])
        bits = out['ZrDPm3j5'][0]['eAM5B1qt']
        self.assertTrue(int(bits[index // 4], 16) & (1 << (3 - index % 4)))
        self.unchanged('sxK2HG6T', '2aciVI9Y', {
            'Gh92V3Tx': 1101, 'j9NS0H15': '60:' + book + ':1', 'U1uaXph4': price})

    def test_recipe_purchase_rejects_bad_batches_before_spending(self):
        for entries, price in [('60:901000010:2', 60),
                               ('60:901000010:1,60:901000010:1', 60),
                               ('60:901000010:1,20:101000100:1', 1)]:
            self.unchanged('sxK2HG6T', '2aciVI9Y', {
                'Gh92V3Tx': 1101, 'j9NS0H15': entries, 'U1uaXph4': price})
        self.player.currencies['gil'] = 0
        self.unchanged('sxK2HG6T', '2aciVI9Y', {
            'Gh92V3Tx': 1101, 'j9NS0H15': '60:901000010:1', 'U1uaXph4': 30})

    def test_strongbox_spends_key_once_and_sets_real_switch_bits(self):
        row = _load_ndjson('F_STRONGBOX_MST.ndjson', 'IXxi7Z8A')['1101001']
        self.seed_costs(row['wEofF38K'], 2)
        node = {'Z20mNDvL': 110101, '7NXY1JnT': '1101001'}
        out = self.call('PIv7u8jU', '3m6ToI0L', node)
        self.assertEqual(self.player.item_count(20, 109201000), 1)
        self.assertTrue(any(r['J1YX9kmM'] == '301000900' for r in out['MBPCGT84']))
        for token in ('dIPkNn61', '8aVAUgN5'):
            stype, bit = switch_position(row[token])
            self.assertIn(bit, self.player.switches[stype])
            container = next(r['juA0Z4m7'] for r in out['ExQ7H1ok'] if r['5opcUT9t'] == stype)
            self.assertTrue(int(container[bit // 4], 16) & (8 >> (bit % 4)))
        before = deepcopy(self.player.data)
        self.call('PIv7u8jU', '3m6ToI0L', node)
        self.assertEqual(self.player.data, before)
        self.unchanged('PIv7u8jU', '3m6ToI0L', dict(node, **{'7NXY1JnT': '1101001,1101001'}))

    def test_strongbox_unknown_probability_is_refused(self):
        original = shops._table
        box = deepcopy(original('F_STRONGBOX_MST', 'IXxi7Z8A')['1101001'])
        box['XPd8xR29'] = '21:301000900:1:50'
        def table(name, key=None):
            return {'1101001': box} if name == 'F_STRONGBOX_MST' else original(name, key)
        self.seed_costs(box['wEofF38K'])
        with patch.object(shops, '_table', side_effect=table):
            self.unchanged('PIv7u8jU', '3m6ToI0L', {'Z20mNDvL': 110101, '7NXY1JnT': '1101001'})

    def test_magic_key_pack_uses_master_cost_and_free_then_paid_lapis(self):
        row = _load_ndjson('F_EXCHANGE_SHOP_ITEM_MST.ndjson', 'wpM08VZ7')['200002']
        self.player.currencies.update(lapis_free=50, lapis_paid=1000)
        out = self.call('I7fmVX3R', 'V5W9ZAPx', {'wpM08VZ7': '200002'})
        self.assertEqual(self.player.currencies['lapis_free'], 0)
        self.assertEqual(self.player.currencies['lapis_paid'], 1050 - int(row['8f7mxN3j']))
        self.assertEqual(self.player.item_count(20, row['6uIYE15X']), int(row['Qy5EvcK1']))
        self.assertIn('J3pAG0I5', out)
        self.player.currencies.update(lapis_free=0, lapis_paid=0)
        self.unchanged('I7fmVX3R', 'V5W9ZAPx', {'wpM08VZ7': '200002'})

    def test_invalid_products_and_ineligible_enhancements_preserve_resources(self):
        self.player.grant_item(23, 300, 5000)
        self.player.data['exvius_point'] = {'0': {'LD4UJaf0': 100}, '100000102': {'LD4UJaf0': 100}}
        cases = [
            ('xD5b6PqQ', 'R0bWsV9y', {'d9gKeu0T': 1, 'Qy5EvcK1': 1}),
            ('Vgi7j68T', 'gGCM0Q3h', {'og2GHy49': self.iid}),
            ('LiM9Had2', '2d6RAkvh', {'Z20mNDvL': 110101, 'L2gHC5ta': '1001:1'}),
            ('nsxUW3Y7', '5xfBN93i', [{'og2GHy49': self.iid, 'woghJa61': 0, 'LD4UJaf0': 10},
                                     {'og2GHy49': self.iid, 'woghJa61': 100000102, 'LD4UJaf0': 10}]),
            ('Pf5C8xjJ', '6U5w20zk', {'og2GHy49': self.iid, 'KCk8u0am': '20:293000200:1', 'Knra4I19': 0}),
            ('V8GtMQ2q', '6U5w20zk', {'og2GHy49': self.iid, 'KCk8u0am': '20:293000200:1', 'Knra4I19': 0}),
            ('k6NI9Tm1', '14vWb7kX', {'og2GHy49': self.iid, 'KCk8u0am': '20:293000200:1', 'Knra4I19': 0}),
            ('QkN1Sp64', '0eDvu2N3', {'KosY4a18': 1, 'gak9Gb3N': '999'}),
        ]
        for rid, group, node in cases:
            with self.subTest(request=rid):
                self.unchanged(rid, group, node)
        before = deepcopy(self.player.data)
        out = self.call('syKz34cE')
        self.assertEqual(len(out['E4r63ukD']), 10)
        self.assertEqual(out['ibt8aCI7'], [])
        self.assertEqual(out['Md0N5abE'], self.player.important_item_rows())
        self.assertEqual(self.player.data, before)

    def test_medal_unlimited_zero_uses_master_price_and_full_count_projection(self):
        row = shops._table('F_MEDAL_EXCHANGE_MST', 'S21FT3L8')['70301']
        self.assertEqual((row['kR4n5DxP'], row['x0NDnEC9']), ('2', '0'))
        currency, price = int(row['ak2dhKm3']), int(row['Qy5EvcK1'])
        self.player.grant_item(20, currency, price * 5)
        reward = shops._triples(row['7iJpH5zZ'], rated=True)[0]
        before = self.player.item_count(reward['kind'], reward['id'])
        for quantity, total in [(3, 3), (2, 5)]:
            out = self.call('LiM9Had2', '2d6RAkvh', {
                'Z20mNDvL': '900105', 'L2gHC5ta': f'70301:{quantity}', 'Qy5EvcK1': '1'})
            self.assertEqual(self.player.item_count(20, currency), price * (5 - total))
            self.assertEqual(self.player.item_count(reward['kind'], reward['id']),
                             before + reward['count'] * total)
            self.assertEqual(out['R5kozET8'], [{'S21FT3L8': '70301', 'ngQX7a3N': str(total)}])
        self.unchanged('LiM9Had2', '2d6RAkvh', {'Z20mNDvL': 900105, 'L2gHC5ta': '70301:1'})

    def test_medal_finite_limit_and_invalid_batch_are_atomic(self):
        masters = shops._table('F_MEDAL_EXCHANGE_MST', 'S21FT3L8')
        stores = shops._table('F_TOWN_STORE_MST', 'Z20mNDvL')
        offer = next(r for r in shops._rows('F_STORE_ITEM_MST')
                     if r['YWF08vZS'] == '50' and stores[r['Z20mNDvL']]['kaG4xf3I'] == '5'
                     and masters[r['6uIYE15X']]['kR4n5DxP'] == '1'
                     and 0 < int(masters[r['6uIYE15X']]['x0NDnEC9']) <= 5
                     and masters[r['6uIYE15X']]['7iJpH5zZ'].startswith('20:')
                     and len(masters[r['6uIYE15X']]['7iJpH5zZ'].split(':')) == 4)
        iid, store = offer['6uIYE15X'], offer['Z20mNDvL']
        row = masters[iid]; limit = int(row['x0NDnEC9'])
        self.player.grant_item(20, row['ak2dhKm3'], int(row['Qy5EvcK1']) * (limit + 5))
        for entries in [f'{iid}:1,999999999:1', f'{iid}:1,{iid}:1', f'{iid}:0', f'{iid}:-1']:
            self.unchanged('LiM9Had2', '2d6RAkvh', {'Z20mNDvL': store, 'L2gHC5ta': entries})
        self.call('LiM9Had2', '2d6RAkvh', {'Z20mNDvL': store, 'L2gHC5ta': f'{iid}:{limit}'})
        self.unchanged('LiM9Had2', '2d6RAkvh', {'Z20mNDvL': store, 'L2gHC5ta': f'{iid}:1'})
        self.unchanged('LiM9Had2', '2d6RAkvh', {'Z20mNDvL': 110101, 'L2gHC5ta': f'{iid}:1'})

    def test_variable_store_and_star_quartz_unit_purchase(self):
        from datetime import datetime
        out = self.call('i0woEP4B')
        schedule, minister = out['3VS1Bhmf']
        self.assertEqual((schedule['Z20mNDvL'], schedule['za2xsDj5'], schedule['suR36Jpm']),
                         ('900104', '7000458', '20:106200100'))
        self.assertEqual((minister['Z20mNDvL'], minister['za2xsDj5'], minister['suR36Jpm']),
                         ('900122', '900105', '20:106300100'))
        self.assertIn('star quartz', schedule['89YmCAzo'])
        self.assertIn('auracite shards', minister['89YmCAzo'])
        self.assertLess(datetime.strptime(schedule['VjJQ51uG'], '%Y-%m-%d %H:%M:%S'),
                        datetime.now())
        self.assertGreater(datetime.strptime(schedule['m8ivD4NX'], '%Y-%m-%d %H:%M:%S'),
                           datetime.now())
        self.player.grant_item(20, 106200100, 40)
        before = len(self.player.data['roster'])
        out = self.call('LiM9Had2', '2d6RAkvh', {
            'Z20mNDvL': '7000458', 'L2gHC5ta': '230701:2'})
        self.assertEqual(self.player.item_count(20, 106200100), 0)
        self.assertEqual(len(self.player.data['roster']), before + 2)
        self.assertEqual([str(u['master_id']) for u in self.player.data['roster'][-2:]],
                         ['100006303', '100006303'])
        self.assertEqual(out['R5kozET8'], [{'S21FT3L8': '230701', 'ngQX7a3N': '2'}])
        self.unchanged('LiM9Had2', '2d6RAkvh', {
            'Z20mNDvL': '7000458', 'L2gHC5ta': '70301:1'})

    def test_trophy_progress_and_repeat_claims(self):
        row = _load_ndjson('F_TROPHY_MST.ndjson', 't86L4JR3')['1']
        node = {'m81FLCIz': '1'}
        self.unchanged('wukWY4t2', 'y3ubhqI0', node)
        self.player.data['quest_progress']['counters'][row['NYb0Cri6']] = int(row['nw2FXyo8'])
        gil = self.player.currencies['gil']
        out = self.call('wukWY4t2', 'y3ubhqI0', node)
        self.assertEqual(self.player.currencies['gil'], gil + 500)
        self.assertIn('ExQ7H1ok', out)
        before = deepcopy(self.player.data)
        self.call('wukWY4t2', 'y3ubhqI0', node)
        self.assertEqual(self.player.data, before)
        self.unchanged('wukWY4t2', 'y3ubhqI0', {'15Y6b8Kp': 1})

    def test_all_trophies_and_all_nine_meter_rewards_grant_once_after_reload(self):
        from player_state import _serialise, _normalise
        trophies = _load_ndjson('F_TROPHY_MST.ndjson', 't86L4JR3')
        for row in trophies.values():
            counters = self.player.data['quest_progress']['counters']
            counters[row['NYb0Cri6']] = max(int(counters.get(row['NYb0Cri6'], 0)), int(row['nw2FXyo8']))
        # Progress alone cannot pay the meter before trophies are collected.
        self.unchanged('wukWY4t2', 'y3ubhqI0', {'15Y6b8Kp': 1})
        for iid, row in trophies.items():
            out = self.call('wukWY4t2', 'y3ubhqI0', {'m81FLCIz': iid})
            pos = switch_position(row['dIPkNn61'])
            self.assertIn(pos[1], self.player.switches[pos[0]], iid)
            for reward in shops._triples(row['dX6cor8j']):
                if reward['kind'] == 26:
                    self.assertIn({'0w6XzofV': str(reward['id'])}, out['3Ys8WPS6'])
        meters = _load_ndjson('F_TROPHY_REWARD_MST.ndjson', '15Y6b8Kp')
        for iid, row in meters.items():
            out = self.call('wukWY4t2', 'y3ubhqI0', {'15Y6b8Kp': iid})
            pos = switch_position(row['dIPkNn61'])
            self.assertIn(pos[1], self.player.switches[pos[0]], iid)
            for reward in shops._triples(row['dX6cor8j']):
                if reward['kind'] == 60:
                    self.assertTrue(self.player.data['exvius_craft']['books'][str(reward['id'])])
                else:
                    self.assertEqual(self.player.item_count(reward['kind'], reward['id']), reward['count'])
            State.player = self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
            before = deepcopy(self.player.data)
            self.call('wukWY4t2', 'y3ubhqI0', {'15Y6b8Kp': iid})
            self.assertEqual(self.player.data, before, 'meter tier paid twice: ' + iid)
        self.assertEqual(len(out['nSG9Jb1s']), len(_load_ndjson('F_ARCHIVE_MST.ndjson', 'NYb0Cri6')))
        self.assertEqual(len(meters), 9)

    def test_card_display_set_and_literal_zero_clear(self):
        self.player.data['vision_cards'] = [{'user_vc_id': '101', 'vc_id': '100000101', 'level': 1}]
        for iid in ('101', '0'):
            out = self.call('TmS3EjZ8', 'kwK4W0Si', {'gXb32xzQ': iid})
            self.assertEqual(self.player.data['exvius_vision_card']['display'], iid)
            self.assertEqual(out['3oU9Ktb7'][0]['gXb32xzQ'], iid)
        self.unchanged('TmS3EjZ8', 'kwK4W0Si', {'gXb32xzQ': '999'})

    def test_card_mix_ordinary_result_keeps_client_animation_objects(self):
        self.player.data['vision_cards'] = [
            {'user_vc_id': '101', 'vc_id': '100000101', 'level': 1, 'exp': 0, 'total_exp': 0},
            {'user_vc_id': '102', 'vc_id': '100000101', 'level': 1, 'exp': 0, 'total_exp': 0}]
        gil = self.player.currencies['gil']
        node = {'gXb32xzQ': '101', 'iUeA3z71': '102', '7UR4J2SE': 1, 'B6H34Mea': 999999}
        out = self.call('5J14x3Qz', 'oh5yce1m', node, spec={'2Xi0wuGA': []})
        self.assertNotIn('2Xi0wuGA', out)
        self.assertEqual(len(self.player.data['vision_cards']), 1)
        self.assertEqual(self.player.data['vision_cards'][0]['level'], 5)
        self.assertEqual(self.player.data['vision_cards'][0]['exp'], 100)
        self.assertEqual(self.player.data['vision_cards'][0]['total_exp'], 500)
        self.assertEqual(self.player.currencies['gil'], gil - 60)
        result = out['oh5yce1m'][0]
        self.assertEqual(result['1dT7ha9H'], '0')
        self.assertEqual(result['Wpro0aE7'], '0:1_100:5')
        self.assertEqual(result['iUeA3z71'], '102')
        self.assertEqual([r['gXb32xzQ'] for r in out['4hPYneL3']], ['101'])
        self.unchanged('5J14x3Qz', 'oh5yce1m', node)

    def test_card_mix_duplicate_and_equipped_materials_refused(self):
        self.player.data['vision_cards'] = [
            {'user_vc_id': str(i), 'vc_id': '100000101', 'level': 1} for i in (101, 102)]
        self.unchanged('5J14x3Qz', 'oh5yce1m', {'gXb32xzQ': '101', 'iUeA3z71': '102,102'})
        self.player.data['roster'][0]['vision_card'] = '0-102'
        self.unchanged('5J14x3Qz', 'oh5yce1m', {'gXb32xzQ': '101', 'iUeA3z71': '102'})

    def test_card_mix_series_penalty_and_max_level_cost_rounding(self):
        self.player.data['vision_cards'] = [
            {'user_vc_id': '101', 'vc_id': '100000101', 'level': 1},
            {'user_vc_id': '102', 'vc_id': '100000201', 'level': 1}]
        out = self.call('5J14x3Qz', 'oh5yce1m', {'gXb32xzQ': '101', 'iUeA3z71': '102'})
        self.assertEqual(out['oh5yce1m'][0]['B6H34Mea'], '100')
        self.assertEqual(self.player.data['vision_cards'][0]['level'], 2)
        # A provisioned max-level card without stored EXP derives its real total.
        self.player.data['vision_cards'] = [
            {'user_vc_id': '101', 'vc_id': '100000101', 'level': 10},
            {'user_vc_id': '102', 'vc_id': '100000101', 'level': 1}]
        out = self.call('5J14x3Qz', 'oh5yce1m', {'gXb32xzQ': '101', 'iUeA3z71': '102'})
        self.assertEqual(out['oh5yce1m'][0]['7UR4J2SE'], '83')
        self.assertEqual(self.player.data['vision_cards'][0]['total_exp'], 1500)
        self.assertEqual(self.player.data['vision_cards'][0]['exp'], 0)

    def test_refusal_does_not_echo_stale_success_or_clear_animation_cards(self):
        before = deepcopy(self.player.data)
        spec = {'oh5yce1m': [{'gXb32xzQ': '999', 'iUeA3z71': '998'}], '2Xi0wuGA': []}
        out = self.call('5J14x3Qz', 'oh5yce1m', {'gXb32xzQ': '999', 'iUeA3z71': '998'}, spec=spec)
        self.assertNotIn('oh5yce1m', out)
        self.assertNotIn('2Xi0wuGA', out)
        self.assertEqual(self.player.data, before)

    def test_unlock_and_release_return_item_only_through_mail(self):
        cost = shops._triples(shops._define('VISION_CARD_SACRIFICE_ITEM_ID'))[0]
        self.seed_costs(shops._define('VISION_CARD_SACRIFICE_ITEM_ID'))
        out = self.call('a54L9CKY', 'x3tm7qUF', {'og2GHy49': self.iid})
        self.assertEqual(self.player.item_count(cost['kind'], cost['id']), 0)
        delta = out['8gSkPD6b'][0]
        self.assertEqual(delta['T9Apq5fS'], '1')
        self.assertEqual(list(delta)[-1], '9Tbns0eI')
        before = deepcopy(self.player.data)
        self.call('a54L9CKY', 'x3tm7qUF', {'og2GHy49': self.iid})
        self.assertEqual(self.player.data, before)
        lapis = self.player.currencies['lapis_free']
        out = self.call('23fbcXt4', 'w7J3XBtq', {'og2GHy49': self.iid})
        self.assertEqual(self.player.currencies['lapis_free'], lapis - int(shops._define('REMOVE_MASTERCARD_LAPIS')))
        self.assertEqual(self.player.item_count(cost['kind'], cost['id']), 0)
        self.assertEqual(out['8gSkPD6b'][0]['T9Apq5fS'], '0')
        self.assertEqual(len(self.player.mailbox), 1)
        self.assertEqual(self.player.mailbox[0]['receive_type'], 0)
        self.assertEqual(self.player.mailbox[0]['items'][0]['item_id'], cost['id'])
        self.assertIn('qja26wHb', out)
        self.assertIn('t8TPs6o2', out)
        self.unchanged('23fbcXt4', 'w7J3XBtq', {'og2GHy49': self.iid})

    def test_sublimation_skill_costs_mapping_and_chain(self):
        unit = self.player.grant_unit('209001127')
        iid = unit['instance_id']
        table = _load_ndjson('F_SUBLIMATION_RECIPE_MST.ndjson', 'SJ56uhz2')
        n = {'6uIYE15X': iid, 'yjY4GK3X': 2, 'SJ56uhz2': 10170001}
        self.unchanged('s48Qzvhd', 'NcI0GgU9', dict(n, yjY4GK3X=1))
        self.unchanged('s48Qzvhd', 'NcI0GgU9', dict(n, SJ56uhz2=10170002))
        for recipe in ('10170001', '10170002'):
            row = table[recipe]
            self.seed_costs(row['HS7V6Ww1'])
            gil = self.player.currencies['gil']
            out = self.call('s48Qzvhd', 'NcI0GgU9', dict(n, SJ56uhz2=recipe))
            self.assertEqual(self.player.currencies['gil'], gil - int(row['7UR4J2SE']))
            self.assertEqual(out['j0e1xIv9'][0]['1MH7Na23'], '10170')
            self.assertEqual(out['j0e1xIv9'][0]['6bHxDEL0'], row['Q1n9iYgz'])
        self.unchanged('s48Qzvhd', 'NcI0GgU9', n)

    def test_hidden_skill_uses_ep_item_and_preserves_unrelated_ids(self):
        self.player.grant_unit('100000315')
        series, root = '100000315', '8000310'
        table = _load_ndjson('F_HIDDEN_SKILL_MST.ndjson', 'uNQgv5QM')
        self.player.grant_item(20, 1209001000, 100000)
        self.player.data['exvius_hidden_skill'] = {series: ['8000320']}
        next_id = table[root]['kjK5eW55']
        self.unchanged('qxUUaS8s', 'gK8NR3Lt', {'woghJa61': series, 'uNQgv5QM': next_id})
        for hid in (root, next_id):
            ep = self.player.item_count(20, 1209001000)
            out = self.call('qxUUaS8s', 'gK8NR3Lt', {'woghJa61': series, 'uNQgv5QM': hid})
            self.assertEqual(self.player.item_count(20, 1209001000), ep - int(table[hid]['3V7vwrcM']))
            learned = out['dnUSYLgn'][0]['umTJJ97w'].split(',')
            self.assertIn(hid, learned)
            self.assertIn('8000320', learned)
        self.assertNotIn(root, self.player.data['exvius_hidden_skill'][series])
        self.unchanged('qxUUaS8s', 'gK8NR3Lt', {'woghJa61': series, 'uNQgv5QM': root})

    def test_craft_exe_batch_costs_and_result_count(self):
        row = self.provision_craft()
        gil = self.player.currencies['gil']
        out = self.call('PKDhIN34', 'ayrzi0H4', [
            {'staFu8U1': 901000010, 'MpNE6gB5': 901000010, '3EhUu8Xm': 2},
            {'staFu8U1': 901000010, 'MpNE6gB5': 901000010, '3EhUu8Xm': 1}])
        self.assertEqual(self.player.currencies['gil'], gil - 3 * int(row['7UR4J2SE']))
        self.assertEqual(self.player.item_count(20, 101000100), 3)
        self.assertEqual(out['0T5wP98d'][0]['jsvoa0I2'], '20:101000100:2')
        self.assertEqual(len(out['0T5wP98d']), 2)
        self.assertEqual(out['0eDvu2N3'], [{'MHNbK26X': ''}])

    def test_craft_exe_requires_owned_book_and_atomic_material_batch(self):
        n = {'staFu8U1': 901000010, 'MpNE6gB5': 901000010, '3EhUu8Xm': 1}
        self.unchanged('PKDhIN34', 'ayrzi0H4', n)
        row = self.provision_craft()
        self.unchanged('PKDhIN34', 'ayrzi0H4', [n, dict(n, **{'3EhUu8Xm': 100})])
        self.unchanged('PKDhIN34', 'ayrzi0H4', dict(n, XjLm3Y0r='301000900'))
        self.unchanged('PKDhIN34', 'ayrzi0H4', dict(n, **{'3EhUu8Xm': -1}))

    def test_timed_craft_grants_at_end_once_and_cancel_has_no_refund(self):
        row = self.provision_craft()
        n = {'KosY4a18': 2, 'gak9Gb3N': 20, '6ukvMSg9': 1,
             'MpNE6gB5': 901000010, 'staFu8U1': 901000010}
        out = self.call('Gr9zxXk5', '0eDvu2N3', n)
        self.assertEqual(self.player.item_count(20, 101000100), 0)
        self.assertEqual(out['yeXn0tk1'][0]['MpNE6gB5'], '901000010')
        self.assertEqual(len(out['yeXn0tk1'][0]['f5De4ZpL']), 19)
        self.unchanged('Gr9zxXk5', '0eDvu2N3', n)
        end = dict(n, KosY4a18=3, I5o3stxJ=False)
        self.unchanged('WIuvh09n', '0eDvu2N3', end)
        self.player.data['exvius_craft']['slots']['20:1']['end'] = 1
        gil = self.player.currencies['gil']
        out = self.call('WIuvh09n', '0eDvu2N3', end)
        self.assertEqual(self.player.item_count(20, 101000100), 1)
        self.assertEqual(self.player.currencies['gil'], gil)
        self.assertEqual(out['yeXn0tk1'][0]['MpNE6gB5'], '0')
        self.unchanged('WIuvh09n', '0eDvu2N3', end)
        self.call('Gr9zxXk5', '0eDvu2N3', n)
        gil = self.player.currencies['gil']
        before_items = deepcopy(self.player.data['inventory'])
        cancel = dict(n, KosY4a18=4, I5o3stxJ=0)
        out = self.call('79xDN1Mw', '0eDvu2N3', cancel)
        self.assertEqual(out['yeXn0tk1'][0]['MpNE6gB5'], '0')
        self.assertEqual(self.player.currencies['gil'], gil)
        self.assertEqual(self.player.data['inventory'], before_items)
        self.unchanged('79xDN1Mw', '0eDvu2N3', cancel)

    def test_craft_upgrade_consumes_equipment_and_preserves_worn_copy(self):
        recipe = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')['903020110']
        self.player.data['exvius_craft'] = {'books': {'903020110': True}}
        self.seed_costs(recipe['HS7V6Ww1'])
        self.player.grant_equipment(302011100, 1)
        self.player.data['roster'][0]['shift_equipment'] = {'0': '302011100'}
        out = self.call('PKDhIN34', 'ayrzi0H4', [
            {'staFu8U1': 903020110, 'MpNE6gB5': 903020110, '3EhUu8Xm': 1, 'XjLm3Y0r': '302011100'}])
        counts = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in out['MBPCGT84']}
        self.assertEqual(counts['302011100'], 1)
        self.assertEqual(counts['302011110'], 1)
        self.assertEqual(out['0T5wP98d'][0]['jsvoa0I2'], '21:302011110:1')
        self.assertEqual(self.player.progress_value('TOTAL_CRAFT_EQUIP'), 1)
        # A second upgrade cannot consume the remaining worn copy.
        self.seed_costs('20:235018200:10')
        self.unchanged('PKDhIN34', 'ayrzi0H4', [
            {'staFu8U1': 903020110, 'MpNE6gB5': 903020110, '3EhUu8Xm': 1}])

    def test_craft_byproduct_success_and_miss_use_shipped_rate_and_amount(self):
        row = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')['904001410']
        self.player.data['exvius_craft'] = {'books': {'904001410': True}}
        self.seed_costs(row['HS7V6Ww1'], 2)
        node = {'staFu8U1': 904001410, 'MpNE6gB5': 904001410, '3EhUu8Xm': 1}
        with patch.object(shops.random, 'randrange', return_value=0):
            out = self.call('PKDhIN34', 'ayrzi0H4', [node])
        self.assertEqual(out['0T5wP98d'][0]['MHNbK26X'], '20:202002800:1')
        self.assertEqual(self.player.item_count(20, 202002800), 1)
        with patch.object(shops.random, 'randrange', return_value=99):
            out = self.call('PKDhIN34', 'ayrzi0H4', [node])
        self.assertEqual(out['0T5wP98d'][0]['MHNbK26X'], '')
        self.assertEqual(self.player.item_count(20, 202002800), 1)

    def test_craft_instant_completion_debits_previewed_lapis_and_survives_reload(self):
        from player_state import _serialise, _normalise
        self.provision_craft()
        node = {'KosY4a18': 2, 'gak9Gb3N': 20, '6ukvMSg9': 1,
                'MpNE6gB5': 901000010, 'staFu8U1': 901000010}
        with patch.object(shops.time, 'time', return_value=1800000000):
            out = self.call('Gr9zxXk5', '0eDvu2N3', node)
            price = int(out['yeXn0tk1'][0]['nRHg3K2h'])
            self.assertEqual(price, 1)
            self.player.currencies['lapis_free'] = 0
            self.unchanged('WIuvh09n', '0eDvu2N3', dict(node, KosY4a18=3, I5o3stxJ=True))
            self.player.currencies['lapis_free'] = 10
            out = self.call('WIuvh09n', '0eDvu2N3', dict(node, KosY4a18=3, I5o3stxJ=True))
            self.assertEqual(self.player.currencies['lapis_free'], 10-price)
            self.assertEqual(self.player.item_count(20, 101000100), 1)
            self.assertEqual(out['yeXn0tk1'][0]['MpNE6gB5'], '0')
            State.player = self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
            self.unchanged('WIuvh09n', '0eDvu2N3', dict(node, KosY4a18=3, I5o3stxJ=True))

    def test_every_catalogued_recipe_accepts_its_real_materials(self):
        recipes = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')
        books = _load_ndjson('F_RECIPE_BOOK_MST.ndjson', 'staFu8U1')
        bindings = {rid: bid for bid, row in books.items() for rid in str(row['8Qt4Ccew']).split(',')}
        checked = 0
        for rid, row in recipes.items():
            if rid not in bindings:
                continue  # A recipe without a book cannot be selected by GL9.
            with self.subTest(recipe=rid):
                self.player.data['inventory'] = {'items': [], 'equipment': []}
                self.player.data['exvius_craft'] = {'books': {bindings[rid]: True}}
                self.player.currencies['gil'] = 10**12
                for unit in self.player.data['roster']:
                    unit['equipment'], unit['materia'] = {}, []
                    unit['shift_equipment'], unit['shift_materia'] = {}, []
                self.seed_costs(row['HS7V6Ww1'])
                out = self.call('PKDhIN34', 'ayrzi0H4', [
                    {'staFu8U1': bindings[rid], 'MpNE6gB5': rid, '3EhUu8Xm': 1}])
                self.assertIn('0T5wP98d', out, 'valid recipe refused')
                reward = out['0T5wP98d'][0]['jsvoa0I2']
                self.assertEqual(reward, ':'.join(str(row[k]) for k in ('gak9Gb3N', '6uIYE15X', 'Qy5EvcK1')))
                self.assertEqual(self.player.currencies['gil'], 10**12-int(row['7UR4J2SE']))
                expected = Counter()
                for item in shops._triples(reward) + shops._triples(out['0T5wP98d'][0]['MHNbK26X']):
                    expected[item['kind'], str(item['id'])] += item['count']
                actual = Counter()
                for item in self.player.data['inventory']['items']:
                    if item['count']:
                        actual[int(item['item_type']), str(item['item_id'])] += item['count']
                for item in self.player.equip_item_rows():
                    actual[21, item['J1YX9kmM']] += int(item['Qy5EvcK1'])
                self.assertEqual(actual, expected, 'materials were not consumed or output was not granted')
                checked += 1
        self.assertGreaterEqual(checked, 2048)

    def test_gift_receive_owns_receipt_and_never_pays_twice(self):
        uid = self.player.data['identity']['user_id']
        self.player.data['exvius_gift'] = {'receipts': {
            '501': {'2HqjK1F7': '501', 'bUfq8BJ3': uid, 'Igd28KXq': '0', 'jsvoa0I2': '51:1:10',
                    'm94IYp6a': '900000001', 'AJGfV35v': 'Offline friend', 'f5LHNT4v': '2026-10-25 00:00:00'},
            '502': {'2HqjK1F7': '502', 'bUfq8BJ3': uid, 'Igd28KXq': '0', 'jsvoa0I2': '30:1:500'}}}
        fp = self.player.currencies['friend_point']
        out = self.call('9KN5rcwj', 'WSH38iMI', {'Utx8P1Qo': 10, '9wXIbKq2': '501', '2L0dxwuN': ''})
        self.assertEqual(self.player.currencies['friend_point'], fp + 10)
        self.assertEqual(len(out['h5XGny0N']), 2)
        self.assertEqual(out['h5XGny0N'][0]['Igd28KXq'], '1')
        before = deepcopy(self.player.data)
        self.call('9KN5rcwj', 'WSH38iMI', {'9wXIbKq2': '501'})
        self.assertEqual(self.player.data, before)
        self.unchanged('9KN5rcwj', 'WSH38iMI', {'9wXIbKq2': '502,999'})
        self.player.data['exvius_gift']['receipts']['502']['bUfq8BJ3'] = 'other-player'
        self.unchanged('9KN5rcwj', 'WSH38iMI', {'9wXIbKq2': '502'})

    def test_gift_send_rejects_unknown_gift_for_actual_offline_friend(self):
        from ffbe_friends import load_friends
        friend = load_friends()[0]['friend_id']
        self.unchanged('9KN5rcwj', 'WSH38iMI', {'Utx8P1Qo': 1, '2L0dxwuN': f'{friend}:1'})

    def reopen(self):
        from player_state import _serialise, _normalise
        State.player = self.player = PlayerState(
            _normalise(json.loads(json.dumps(_serialise(self.player.data)))))

    def test_trust_coin_purchase_stock_cost_and_restart(self):
        self.player.grant_item(23, 300, 1000)
        out = self.call('xD5b6PqQ', 'R0bWsV9y', {'d9gKeu0T': 900006, 'Qy5EvcK1': 2})
        self.assertEqual(self.player.item_count(23, 300), 200)
        self.assertEqual(self.player.item_count(20, 1209002041), 20)
        self.assertEqual(out['ibt8aCI7'], [{'d9gKeu0T': '900006', '0zBQbX4N': '2'}])
        self.assertEqual(next(r for r in out['E4r63ukD'] if r['d9gKeu0T'] == '900005')['Hp54A9JM'], '-1')
        self.reopen()
        self.assertEqual(self.player.data['exvius_exchange']['counts']['900006'], 2)
        for count in (29, 1, 0, -1):
            self.unchanged('xD5b6PqQ', 'R0bWsV9y', {'d9gKeu0T': 900006, 'Qy5EvcK1': count})

    def test_trust_coin_max_level_unit_reward(self):
        self.player.grant_item(23, 300, 150)
        before = {u['instance_id'] for u in self.player.data['roster']}
        self.call('xD5b6PqQ', 'R0bWsV9y', {'d9gKeu0T': 900009, 'Qy5EvcK1': 1})
        awarded = [u for u in self.player.data['roster'] if u['instance_id'] not in before]
        self.assertEqual([(u['master_id'], u['level']) for u in awarded], [('900020401', 60)])
        self.assertEqual(self.player.item_count(23, 300), 0)

    def test_trust_coin_conversion_eligibility_lock_and_retry(self):
        unit = self.player.grant_unit('100000315')
        iid = unit['instance_id']
        self.unchanged('Vgi7j68T', 'gGCM0Q3h', {'og2GHy49': iid})
        unit = self.player.roster_row(iid)
        unit['affinity_points'][0] = '1000'
        unit['favourite'] = 1
        self.unchanged('Vgi7j68T', 'gGCM0Q3h', {'og2GHy49': iid})
        self.player.roster_row(iid)['favourite'] = 0
        self.unchanged('Vgi7j68T', 'gGCM0Q3h', {'og2GHy49': iid + ',' + iid})
        self.call('Vgi7j68T', 'gGCM0Q3h', {'og2GHy49': iid})
        self.assertIsNone(self.player.roster_row(iid))
        self.assertEqual(self.player.item_count(23, 300), 500)
        self.reopen()
        self.unchanged('Vgi7j68T', 'gGCM0Q3h', {'og2GHy49': iid})

    def test_nv_awakening_replaces_native_instance_and_preserves_trust(self):
        unit = self.player.grant_unit('100010007')
        iid = unit['instance_id']
        self.player.set_unit_level(iid, 120)
        step = _load_ndjson('F_UNIT_CLASS_UP_MST.ndjson', '3HriTp6B')['100010007']
        self.seed_costs(step['KCk8u0am'])
        node = {'og2GHy49': iid, 'KCk8u0am': step['KCk8u0am'], 'Knra4I19': 0}
        self.unchanged('Pf5C8xjJ', '6U5w20zk', node)
        self.player.roster_row(iid)['affinity_points'] = ['1000', '1000']
        self.player.data['party']['decks'][0]['members'].append(
            {'member_type': 1, 'disp_order': 2, 'instance_id': iid})
        self.player.data['exvius_dark_visions'] = {'parties': [
            {'2A6fYiEC': '1:2:' + iid, 'w1JG7i9j': iid + ':0'}]}
        self.player.data['exvius_sublimation'] = {'slots': {iid: 2}}
        gil = self.player.currencies['gil']
        out = self.call('Pf5C8xjJ', '6U5w20zk', node)
        new_id = out['6U5w20zk'][0]['5u7VYNEX']
        self.assertNotEqual(new_id, iid)
        self.assertEqual(out['6U5w20zk'][0]['og2GHy49'], iid)
        self.assertIsNone(self.player.roster_row(iid))
        upgraded = self.player.roster_row(new_id)
        self.assertEqual((upgraded['master_id'], upgraded['level']), ('100010017', 120))
        self.assertEqual(upgraded['affinity_points'], ['1000', '1000'])
        self.assertEqual(self.player.data['party']['decks'][0]['members'][-1]['instance_id'], new_id)
        self.assertEqual(self.player.data['exvius_dark_visions']['parties'][0]['2A6fYiEC'], '1:2:' + new_id)
        self.assertEqual(self.player.data['exvius_sublimation']['slots'], {new_id: 2})
        self.assertEqual(self.player.currencies['gil'], gil - int(step['7UR4J2SE']))
        self.reopen()
        self.assertEqual(self.player.roster_row(new_id)['master_id'], '100010017')
        self.assertEqual(self.player.archive_value('TOTAL_UNIT_CLASS_UP'), 1)
        self.unchanged('Pf5C8xjJ', '6U5w20zk', node)

    def test_ordinary_awakening_also_replaces_the_consumed_instance(self):
        from exvius_actions import unit_class_up
        unit = self.player.roster_row(self.iid)
        step = _load_ndjson('F_UNIT_CLASS_UP_MST.ndjson', '3HriTp6B')[unit['master_id']]
        self.seed_costs(step['KCk8u0am'])
        out = unit_class_up({'LhVz6aD2': [{}]}, {'sWc7EH69': [{'og2GHy49': self.iid}]})
        new_id = out['sWc7EH69'][0]['5u7VYNEX']
        self.assertNotEqual(new_id, self.iid)
        self.assertIsNone(self.player.roster_row(self.iid))
        self.assertEqual(self.player.roster_row(new_id)['master_id'], step['t74crqAL'])
        self.assertTrue(any(m['instance_id'] == new_id for d in self.player.data['party']['decks']
                            for m in d['members']))
        self.assertEqual(self.player.archive_value('TOTAL_UNIT_CLASS_UP'), 1)

    def test_nv_plus_accepts_ex_zero_and_uses_original_cost(self):
        unit = self.player.grant_unit('100043107')
        iid = unit['instance_id']
        step = _load_ndjson('F_UNIT_CLASS_UP_MST.ndjson', '3HriTp6B')['100043107']
        self.seed_costs(step['KCk8u0am'])
        gil = self.player.currencies['gil']
        out = self.call('V8GtMQ2q', '6U5w20zk', {
            'og2GHy49': iid, 'KCk8u0am': step['KCk8u0am'], 'Knra4I19': 0})
        new_id = out['6U5w20zk'][0]['5u7VYNEX']
        self.assertNotEqual(new_id, iid)
        self.assertIsNone(self.player.roster_row(iid))
        unit = self.player.roster_row(new_id)
        self.assertEqual((unit['master_id'], unit['nv_ex_level']), ('100043127', 0))
        self.assertEqual(unit['level'], 1)
        self.assertEqual(self.player.currencies['gil'], gil - int(step['7UR4J2SE']))
        self.assertEqual(self.player.item_count(20, 1209002041), 0)
        self.assertEqual(out['6U5w20zk'][0]['og2GHy49'], iid)
        self.assertEqual(self.player.archive_value('TOTAL_UNIT_CLASS_UP'), 1)

    def test_ex_all_three_steps_costs_stats_cards_and_restart(self):
        from player_state import unit_stats
        unit = self.player.grant_unit('100000327')
        iid = unit['instance_id']
        self.player.set_unit_level(iid, 120)
        steps = [r for r in shops._rows('F_NV_EX_CLASS_UP_MST') if r['JPW8Vs40'] == '100000327']
        steps.sort(key=lambda r: int(r['f8vk4JrD']))
        for row in steps:
            self.seed_costs(row['KCk8u0am'])
        base_hp = unit_stats('100000327', 120)[0]
        for level, row in enumerate(steps, 1):
            node = {'og2GHy49': iid, 'KCk8u0am': row['KCk8u0am'], 'Knra4I19': 0}
            gil = self.player.currencies['gil']
            out = self.call('k6NI9Tm1', '14vWb7kX', node)
            self.assertEqual(self.player.roster_row(iid)['nv_ex_level'], level)
            self.assertEqual(self.player.currencies['gil'], gil - int(row['7UR4J2SE']))
            wire = next(r for r in out[shops.UNIT_GROUP] if r['og2GHy49'] == iid)
            self.assertEqual(wire['f8vk4JrD'], str(level))
            self.assertEqual(int(wire['em5hx4FX'].split('-')[0]), base_hp)
            if level == 1:
                self.assertEqual(int(wire['em5hx4FX'].split('-')[3]), 587)
                self.unchanged('k6NI9Tm1', '14vWb7kX', node)
            self.reopen()
        self.assertEqual(len(self.player.data['vision_cards']), 3)
        self.assertEqual(len({c['user_vc_id'] for c in self.player.data['vision_cards']}), 3)

    def test_ex_specific_stmr_moogles_and_global_target_mapping(self):
        from player_state import unit_mst
        for mid in ('100031007', '100041517', '401010807'):
            with self.subTest(unit=mid):
                unit = self.player.grant_unit(mid)
                iid = unit['instance_id']
                unit['nv_ex_level'] = 1
                group = unit_mst(mid)['JPW8Vs40']
                step = next(r for r in shops._rows('F_NV_EX_CLASS_UP_MST')
                            if r['JPW8Vs40'] == group and r['f8vk4JrD'] == '2')
                self.seed_costs(step['KCk8u0am'])
                previous = {u['instance_id'] for u in self.player.data['roster']}
                self.call('k6NI9Tm1', '14vWb7kX', {
                    'og2GHy49': iid, 'KCk8u0am': step['KCk8u0am'], 'Knra4I19': 0})
                self.assertEqual(self.player.roster_row(iid)['nv_ex_level'], 2)
                moogles = [u for u in self.player.data['roster']
                           if u['instance_id'] not in previous and u['master_id'] == '906000103']
                self.assertEqual(len(moogles), 1)
                self.assertEqual(moogles[0]['affinity_info'][1], unit_mst(mid)['C74EmZ1I'])
                self.assertEqual(moogles[0]['affinity_points'], ['', '1000'])
                self.reopen()

    def test_gifts_send_receive_daily_limit_and_restart(self):
        from ffbe_friends import load_friends
        friend = str(load_friends()[0]['friend_id'])
        node = {'Utx8P1Qo': 20, '2L0dxwuN': friend + ':10'}
        before = deepcopy(self.player.currencies)
        out = self.call('9KN5rcwj', 'WSH38iMI', node)
        self.assertEqual(len(out['h5XGny0N']), 2)
        self.assertEqual(self.player.currencies, before)
        uid = str(self.player.data['identity']['user_id'])
        incoming = next(r['2HqjK1F7'] for r in out['h5XGny0N'] if r['bUfq8BJ3'] == uid)
        self.call('9KN5rcwj', 'WSH38iMI', node)
        self.assertEqual(len(self.player.data['exvius_gift']['receipts']), 2)
        self.call('9KN5rcwj', 'WSH38iMI', {'9wXIbKq2': incoming})
        self.assertEqual(self.player.currencies['friend_point'], before['friend_point'] + 10)
        self.assertEqual(self.player.archive_value('TOTAL_GIFT_PRESENT'), 1)
        self.assertEqual(self.player.archive_value('TOTAL_GIFT_RECIEVE'), 1)
        self.reopen()
        self.call('9KN5rcwj', 'WSH38iMI', {'9wXIbKq2': incoming})
        self.assertEqual(self.player.currencies['friend_point'], before['friend_point'] + 10)
        self.player.data['exvius_gift']['sent'][friend] = '2026-10-01'
        self.assertEqual(self.player.archive_value('TOTAL_GIFT_RECIEVE'), 1)
        self.reopen()
        self.call('9KN5rcwj', 'WSH38iMI', node)
        self.assertEqual(len(self.player.data['exvius_gift']['receipts']), 4)
        self.assertEqual(self.player.archive_value('TOTAL_GIFT_PRESENT'), 2)
        self.unchanged('9KN5rcwj', 'WSH38iMI', {'Utx8P1Qo': 20, '2L0dxwuN': '999:10'})

    def test_gift_native_friend_identity_currency_wire_and_progress(self):
        from ffbe_friends import load_friends
        self.player.data['identity']['friend_id'] = '123456789'
        original = {'LhVz6aD2': [{'9Tbns0eI': '100000001'}]}
        out = self.player.apply_to_reply(original)
        self.assertEqual(out['LhVz6aD2'][0]['m3Wghr1j'], '123456789')
        self.assertNotIn('m3Wghr1j', original['LhVz6aD2'][0])
        friends = load_friends()
        node = {'Utx8P1Qo': 20,
                '2L0dxwuN': ','.join(str(f['friend_id']) + ':10' for f in friends)}
        with patch('ffbe_player._satisfied_quests', return_value=[]), patch(
                'ffbe_player._daily_quests_for_action', return_value=[('gift-test', '6', 5)]):
            out = self.call('9KN5rcwj', 'WSH38iMI', node)
            incoming = [r for r in out['h5XGny0N'] if r['bUfq8BJ3'] == '123456789']
            self.assertEqual(len(incoming), len(friends))
            self.assertTrue(all(r['jsvoa0I2'] == '51:10' for r in incoming))
            self.assertTrue(all(r['f5LHNT4v'].isdigit() and int(r['f5LHNT4v']) > 1700000000
                                for r in incoming))
            self.assertEqual(self.player.progress_value('gift-test'), len(friends))
            self.call('9KN5rcwj', 'WSH38iMI', node)
            self.assertEqual(self.player.progress_value('gift-test'), len(friends))
            before = self.player.currencies['friend_point']
            self.call('9KN5rcwj', 'WSH38iMI', {'9wXIbKq2': incoming[0]['2HqjK1F7']})
            self.assertEqual(self.player.currencies['friend_point'], before + 10)
            self.assertEqual(self.player.progress_value('gift-test'), len(friends))

    def test_craft_slots_support_independent_jobs_and_restart(self):
        self.provision_craft()
        self.call('QkN1Sp64', '0eDvu2N3', {'KosY4a18': 1, 'gak9Gb3N': '20,21'})
        self.assertEqual(len(self.player.data['exvius_craft']['slots']), 8)
        node = {'KosY4a18': 2, 'gak9Gb3N': 20, '6ukvMSg9': 1,
                'MpNE6gB5': 901000010, 'staFu8U1': 901000010}
        for number in (1, 2):
            self.call('Gr9zxXk5', '0eDvu2N3', dict(node, **{'6ukvMSg9': number}))
        self.reopen()
        self.assertTrue(all(self.player.data['exvius_craft']['slots'][f'20:{n}']['recipe'] for n in (1, 2)))
        for number in (1, 2):
            self.player.data['exvius_craft']['slots'][f'20:{number}']['end'] = 1
            self.call('WIuvh09n', '0eDvu2N3', dict(node, KosY4a18=3, **{'6ukvMSg9': number}))
        self.assertEqual(self.player.item_count(20, 101000100), 2)

    def test_legacy_treasure_aliases_do_not_duplicate_a_chest_reward(self):
        from exvius_field_treasures import catalogue, _credit
        self.assertTrue(_credit('111010105', catalogue()['111010105']))
        self.assertFalse(_credit('991020103', catalogue()['991020103']))
        self.assertEqual(self.player.item_count(22, 504020010), 1)
        self.reopen()
        self.assertFalse(_credit('991020103', catalogue()['991020103']))
        self.assertEqual(self.player.item_count(22, 504020010), 1)

    def test_treasures_extend_beyond_original_three_locations(self):
        from exvius_field_treasures import catalogue, serve
        self.assertEqual(len(catalogue()), 2667)
        self.assertTrue(all(self.player._can_credit(reward)
                            for row in catalogue().values()
                            for reward in shops._triples(row['rewards'])))
        before = self.player.item_count(20, 101000200)
        request = json.dumps({'JcxS6A8N': [{'Gh92V3Tx': '1103', 'NiG2wL3A': '110301'}]})
        serve({}, request)
        self.assertEqual(self.player.item_count(20, 101000200), before + 1)
        self.reopen()
        serve({}, request)
        self.assertEqual(self.player.item_count(20, 101000200), before + 1)

    def test_exploration_load_contains_enemies_without_opening_phases(self):
        from battle_content import field_mission_bundle
        mission = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6')['1110104']
        out = field_mission_bundle({'LhVz6aD2': [{}]}, mission)
        groups = {r['2fY1IomW'] for r in out['Bi6hVv34']}
        self.assertIn('111010401', groups)
        self.assertIn('111010430', groups)
        # Native boss crash: this group is reached through scenario 1110101,
        # and belongs to the Exit mission rather than the exploration prefix.
        self.assertIn('111010306', groups)
        self.assertTrue(out['wbet57nF'])
        self.assertTrue(out['bV34YIJQ'])
        self.assertFalse(out.get('an6TB4WS'))

    def test_legacy_scene_skip_repair_is_narrow_and_runs_once(self):
        from ffbe_state import repair_legacy_resource_skips
        data = Path(__file__).resolve().parents[1] / 'server/content/legacy_resource_skips.json'
        flags = json.loads(data.read_text())['switches']
        for flag in flags:
            group, bit = switch_position(flag)
            self.player.switches.setdefault(group, set()).add(bit)
        story = deepcopy(self.player.switches.get('100', set()))
        repair_legacy_resource_skips(self.player, lambda _: True)
        self.assertTrue(self.player.data['exvius_resource_recovery']['complete'])
        self.assertEqual(self.player.switches.get('100', set()), story)
        self.assertTrue(all(switch_position(flag)[1] not in self.player.switches[switch_position(flag)[0]] for flag in flags))
        group, bit = switch_position(flags[0])
        self.player.switches[group].add(bit)
        repair_legacy_resource_skips(self.player, lambda _: True)
        self.assertIn(bit, self.player.switches[group])

    def test_frozen_player_and_missing_inputs_do_not_mutate(self):
        self.player.mode = 'frozen'
        for rid in shops.HANDLERS:
            self.unchanged(rid, None, None)
        self.player.mode = 'live'
        for rid in shops.HANDLERS:
            if rid != 'syKz34cE':
                self.call(rid)  # No untrusted empty request may crash the server.

    @classmethod
    def tearDownClass(cls):
        endpoints = json.loads((Path(__file__).resolve().parents[1] / 'server' / 'endpoints.json').read_text())['by_class']
        names = ['ItemBuyRequest', 'StrongBoxOpenRequest', 'ExchangeShopRequest', 'ShopExchangeItemListRequest',
                 'ShopExchangeItemRequest', 'ShopExchangeUnitRequest', 'MedalExchangeRequest', 'TrophyRewardRequest',
                 'VisionCardMixRequest', 'VisionCardDisplayRequest', 'UnitSublimationRequest', 'SublimationSkillRequest',
                 'UnitUsePointRequest', 'UnitNvClassUpRequest', 'UnitNvpClassUpRequest', 'UnitExClassUpRequest',
                 'VariableStoreCheckRequest', 'CraftAddRequest', 'CraftCancelRequest', 'CraftEndRequest', 'CraftExeRequest', 'CraftStartRequest',
                 'sgHiddenSkillUpgrade', 'MasterCardReleaseRequest', 'GiftUpdateRequest']
        expected = {endpoints[n]['request_id'] for n in names}
        assert set(shops.HANDLERS) == expected
        assert cls.seen == expected, 'not every handler was exercised'


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActionsShops))
    if not result.wasSuccessful():
        raise AssertionError('shop action selftests failed')


run()
