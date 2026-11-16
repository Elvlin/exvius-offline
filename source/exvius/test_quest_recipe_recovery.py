"""Original quest serialization and restored Magic Key acquisition regressions."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ffbe_state import State
from player_state import PlayerState, _load_ndjson, _normalise, _serialise
from ffbe_battle import grant_cleared_mission
import exvius_actions_expedition as quests
import exvius_actions_shops as shops


class QuestRecipeRecovery(unittest.TestCase):
    def setUp(self):
        self.previous = State.player
        self.p = State.player = PlayerState.load('/nonexistent', slot='quest-recipe-test')

    def tearDown(self):
        State.player = self.previous

    def reload(self):
        self.p = State.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.p.data)))))

    def owned(self):
        return self.p.data.get('exvius_craft', {}).get('books', {}).get('901000500', False)

    def test_original_multi_node_checkpoint_and_retry(self):
        request = {'JcxS6A8N': [{'Gh92V3Tx': '1104'}], '1sGiqV9T': [
            {'i9han5Sz': '1004001:100400101'}, {'i9han5Sz': '1021005:102100501'}]}
        # TownOut serializes the inherited TownUpdate body.
        out = quests.HANDLERS['sJcMPy04']({}, request)
        self.assertEqual(len(out['JG96kr5C']), 2)
        request = {'JcxS6A8N': [{'Gh92V3Tx': '1104'}], '1sGiqV9T': [
            {'9YPZuB2i': '1004001:100400101'}, {'9YPZuB2i': '1021005:102100501'}]}
        out = quests.HANDLERS['sJcMPy04']({}, request)
        self.assertTrue(all(r['4kcAD9fW'] == '2' for r in out['JG96kr5C']))
        self.assertTrue(self.p.data['exvius_craft']['books']['901000440'])
        self.reload()
        saved = deepcopy(self.p.data)
        quests.HANDLERS['sJcMPy04']({}, request)
        self.assertEqual(self.p.data, saved)

    def test_two_original_quests_complete_in_the_same_mission_end(self):
        # Both original quest masters name mission1220607, so the retail
        # createEndQuestTag loop can serialize both in the same result.
        masters = _load_ndjson('F_QUEST_MST.ndjson', 'Z34jU7ue')
        for qid in ('1013003', '2006001'):
            self.assertEqual(masters[qid]['Lxj5u3WB'], '1')
            self.assertEqual(masters[qid]['6uIYE15X'], '1220607')
        request = {'jQsE54Iz': [{'qo3PECw6': '1220607'}], '1sGiqV9T': [
            {'9YPZuB2i': '1013003:101300301'}, {'9YPZuB2i': '2006001:200600101'}]}
        out = quests.HANDLERS['x5Unqg2d']({}, request)
        self.assertEqual({r['Z34jU7ue'] for r in out['JG96kr5C']}, {'1013003', '2006001'})
        self.assertTrue(all(r['4kcAD9fW'] == '2' for r in out['JG96kr5C']))
        self.assertEqual(self.p.item_count(20, 290050400), 1)
        self.assertTrue(self.p.data['exvius_craft']['books']['904000090'])
        saved = deepcopy(self.p.data)
        quests.HANDLERS['x5Unqg2d']({}, request)
        self.assertEqual(self.p.data, saved)

    def test_malformed_second_quest_rolls_back_whole_batch(self):
        request = {'JcxS6A8N': [{'Gh92V3Tx': '1104'}], '1sGiqV9T': [
            {'9YPZuB2i': '1004001:100400101'}, {'9YPZuB2i': '9999999:999999901'}]}
        saved = deepcopy(self.p.data)
        quests.HANDLERS['sJcMPy04']({}, request)
        self.assertEqual(self.p.data, saved)

    def test_key_recipe_requires_successful_recorded_castle_clear(self):
        before = deepcopy(self.p.data)
        self.assertFalse(self.p.restore_story_clear_rewards())
        self.assertEqual(self.p.data, before)
        defeat = json.dumps({'jQsE54Iz': [{'qo3PECw6': '1110703'}],
                             '2urzfX6d': [{'Z1p0j9uF': '1'}]})
        grant_cleared_mission({'09HRWXDf': [{}]}, '1110703', defeat)
        self.assertFalse(self.owned())
        self.p.clear_mission('1110702')
        self.assertFalse(self.owned())
        self.p.clear_mission('1110703')
        self.assertTrue(self.owned())
        self.assertTrue(self.p.data['exvius_story_rewards']['1110703:60:901000500'])
        self.reload()
        saved = deepcopy(self.p.data)
        self.assertFalse(self.p.restore_story_clear_rewards())
        self.assertEqual(self.p.data, saved)

    def test_legacy_clear_is_repaired_and_already_owned_is_not_granted_again(self):
        self.p.data['progress']['cleared_missions'].append('1110703')
        self.reload()
        self.assertTrue(self.p.restore_story_clear_rewards())
        self.assertTrue(self.owned())
        del self.p.data['exvius_story_rewards']
        with patch.object(self.p, '_grant_items', side_effect=AssertionError('duplicate recipe grant')):
            self.assertTrue(self.p.restore_story_clear_rewards())
        saved = deepcopy(self.p.data)
        self.p.mode = 'frozen'
        self.assertFalse(self.p.restore_story_clear_rewards())
        self.assertEqual(self.p.data, saved)

    def test_incomplete_recipe_grant_restores_state_without_receipt(self):
        self.p.data['progress']['cleared_missions'].append('1110703')
        saved = deepcopy(self.p.data)
        with patch.object(self.p, '_grant_items', return_value=[]):
            with self.assertRaises(ValueError):
                self.p.restore_story_clear_rewards()
        self.assertEqual(self.p.data, saved)

    def test_existing_legacy_recipe_is_normalized_without_a_second_grant(self):
        self.p.data['progress']['cleared_missions'].append('1110703')
        self.p.grant_item(60, 901000500, 1)
        with patch.object(self.p, '_grant_items', side_effect=AssertionError('duplicate recipe grant')):
            self.assertTrue(self.p.restore_story_clear_rewards())
        self.assertTrue(self.owned())
        self.assertEqual(self.p.item_count(60, 901000500), 1)

    def test_restored_key_recipe_crafts_with_original_material_costs(self):
        recipe = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')['901000500']
        self.assertEqual(recipe['6uIYE15X'], '106100100')
        self.p.clear_mission('1110703')
        for reward in shops._triples(recipe['HS7V6Ww1']):
            self.p.grant_item(reward['kind'], reward['id'], reward['count'])
        shops.craft_exe({}, {'ayrzi0H4': [{'staFu8U1': '901000500',
                                         'MpNE6gB5': '901000500', '3EhUu8Xm': '1'}]})
        self.assertEqual(self.p.item_count(20, 106100100), 1)
        for reward in shops._triples(recipe['HS7V6Ww1']):
            self.assertEqual(self.p.item_count(reward['kind'], reward['id']), 0)
        self.reload()
        self.assertEqual(self.p.item_count(20, 106100100), 1)
        self.assertTrue(self.owned())

    def test_repair_binding_matches_preserved_acquisition_and_original_identity(self):
        path = Path(__file__).resolve().parents[1] / 'server/content/story_reward_repairs.json'
        definitions = [row for row in json.loads(path.read_text(encoding='utf8'))['rewards']
                       if row['reward'].startswith('60:')]
        self.assertEqual(len(definitions), 1)
        binding = definitions[0]
        recipe = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')['901000500']
        self.assertEqual(binding['evidence']['original_acquisition'], recipe['VC9F3eJn'])
        final = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6')[binding['mission']]
        self.assertEqual(final['U9iHsau3'], binding['evidence']['dungeon'])
        self.assertEqual(binding['reward'], '60:901000500:1')


class HolidayQuestRecipeRecovery(unittest.TestCase):
    targets = (('1901015', '904001710', '870000018', '405001600', '213001900', 600),
               ('1901016', '904001720', '870000019', '403041200', '213002000', 300))

    def setUp(self):
        self.previous = State.player
        self.p = State.player = PlayerState.load('/nonexistent', slot='holiday-recipe-test')

    def tearDown(self):
        State.player = self.previous

    def complete(self, qid, only_first=False):
        steps = _load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')
        ids = sorted(k for k, r in steps.items() if r['Z34jU7ue'] == qid)
        if only_first:
            ids = ids[:1]
        return quests.HANDLERS['sJcMPy04']({}, {
            'JcxS6A8N': [{'Gh92V3Tx': '9001'}],
            '1sGiqV9T': [{'9YPZuB2i': qid + ':' + sid} for sid in ids]})

    def craft_request(self):
        return {'ayrzi0H4': [{'staFu8U1': book, 'MpNE6gB5': book, '3EhUu8Xm': '1'}
                             for _, book, *_ in self.targets]}

    def test_original_quest_rewards_unlock_both_books_once(self):
        for qid, book, *_ in self.targets:
            self.complete(qid, only_first=True)
            self.assertFalse(self.p.data.get('exvius_craft', {}).get('books', {}).get(book))
            self.complete(qid)
            self.assertTrue(self.p.data['exvius_craft']['books'][book])
            self.assertIn(qid, self.p.data['exvius_map']['rewarded'])
            snapshot = deepcopy(self.p.data)
            self.complete(qid)
            self.assertEqual(self.p.data, snapshot)
        self.p = State.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.p.data)))))
        projected = self.p.recipe_book_rows()[0]['eAM5B1qt']
        for index in (858, 859):
            self.assertTrue(int(projected[index // 4], 16) & (1 << (3 - index % 4)))

    def test_crafting_pays_original_costs_and_produces_mapped_equipment(self):
        self.p.data['currencies']['gil'] = 1000
        for qid, _, _, base, feather, _ in self.targets:
            self.complete(qid)
            self.p._grant_items([{'kind': 21, 'id': int(base), 'count': 1}])
            self.p.grant_item(20, feather, 10)
        result = shops.craft_exe({}, self.craft_request())
        self.assertEqual({r['jsvoa0I2'] for r in result['0T5wP98d']},
                         {'21:870000018:1', '21:870000019:1'})
        self.assertEqual(self.p.data['currencies']['gil'], 100)
        equipment = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in self.p.equip_item_rows()}
        for _, _, output, base, feather, _ in self.targets:
            self.assertEqual(equipment.get(output, 0), 1)
            self.assertEqual(equipment.get(base, 0), 0)
            self.assertEqual(self.p.item_count(20, feather), 0)
        snapshot = deepcopy(self.p.data)
        shops.craft_exe({}, self.craft_request())
        self.assertEqual(self.p.data, snapshot)

    def test_unowned_book_and_missing_materials_refuse_without_changes(self):
        self.p.data['currencies']['gil'] = 1000
        before = deepcopy(self.p.data)
        shops.craft_exe({}, self.craft_request())
        self.assertEqual(self.p.data, before)
        for qid, *_ in self.targets:
            self.complete(qid)
        before = deepcopy(self.p.data)
        shops.craft_exe({}, self.craft_request())
        self.assertEqual(self.p.data, before)

    def test_exact_source_materials_switches_and_collision_mapping(self):
        recipes = _load_ndjson('F_RECIPE_MST.ndjson', 'MpNE6gB5')
        books = _load_ndjson('F_RECIPE_BOOK_MST.ndjson', 'staFu8U1')
        equipment = _load_ndjson('F_EQUIP_ITEM_MST.ndjson', 'J1YX9kmM')
        icons = _load_ndjson('F_ICON_MST.ndjson', '0HUPxDf1')
        for i, (_, book, output, base, feather, gil) in enumerate(self.targets):
            recipe = recipes[book]
            self.assertEqual(recipe['HS7V6Ww1'], f'21:{base}:1,20:{feather}:10')
            self.assertEqual(recipe['6uIYE15X'], output)
            self.assertEqual(recipe['7UR4J2SE'], str(gil))
            self.assertEqual(recipe['t4Yi1e7B'], str(71000346 + i))
            self.assertEqual(books[book]['gJf3zp8a'], str(858 + i))
            icon = icons[equipment[output]['0HUPxDf1']]
            self.assertEqual(icon['qtkvrS60'], ('item_20127.png', 'item_30133.png')[i])
        self.assertEqual(equipment['405002900']['Z0EN6jSh'], '90054')
        self.assertEqual(equipment['403042600']['Z0EN6jSh'], '90053')
        self.assertEqual(equipment['870000018']['Pn5w9dfh'], '14')
        self.assertEqual(equipment['870000019']['Pn5w9dfh'], '6')


if __name__ == '__main__':
    unittest.main(verbosity=2)
