"""Functional recovery checks with real masters and isolated in-memory saves."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ffbe_state import State
from player_state import PlayerState, _normalise, _serialise, unit_mst
from exvius_actions import _mst
import exvius_actions_expedition as expedition
import exvius_actions_modes as modes
from ffbe_battle import CONDITION_CHECKS, mission_result_from
from exvius_repeat import begin_attempt, repeat_challenge_rewards
from exvius_rewards import parse


class Completion(unittest.TestCase):
    def setUp(self):
        self.previous = State.player
        self.p = PlayerState.load('/nonexistent', slot='feature-completion')
        State.player = self.p
        self.p.currencies.update(gil=1000000, lapis_free=10000)
        self.clock = patch.object(expedition.time, 'time', return_value=1800000000)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        State.player = self.previous

    def reload(self):
        self.p = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.p.data)))))
        State.player = self.p

    def context(self, **meta):
        return mission_result_from(json.dumps({'2urzfX6d': [{'69ieJGhD': '0:123:2', 'Z1p0j9uF': '0', **meta}],
                                              'L4i4418y': [{'6q35TL07': '0'}]}))

    def check(self, code, param='', **meta):
        return CONDITION_CHECKS[str(code)](self.context(**meta), param)

    def test_every_shipped_condition_has_an_evaluator(self):
        rows = _mst('F_CHALLENGE_MST.ndjson', None)['__rows__']
        codes = {r['Pzn5h0Ga'].partition(':')[0] for r in rows if r.get('Pzn5h0Ga')}
        self.assertEqual(codes - set(CONDITION_CHECKS), set())
        for code in codes:
            if CONDITION_CHECKS[code].__module__ == 'exvius_challenges':
                self.assertIsNot(CONDITION_CHECKS[code](mission_result_from('{}'), ''), True)

    def test_native_wave_zero_and_turn_limits(self):
        ctx = self.context(**{'69ieJGhD': '0:123:2,0:124:3'})
        self.assertEqual(ctx['turns'], 5)
        self.assertEqual(ctx['battle_turns'], {'123': 2, '124': 3})
        self.assertTrue(CONDITION_CHECKS['76'](ctx, '124:2'))
        self.assertTrue(CONDITION_CHECKS['77'](ctx, '123:2'))
        self.assertFalse(CONDITION_CHECKS['77'](ctx, '124:2'))

    def test_finishing_blow_enum_prevents_overlapping_action_ids(self):
        for code, category in [('4', 3), ('15', 2), ('18', 5), ('23', 1), ('32', 4)]:
            with self.subTest(code=code):
                self.assertTrue(self.check(code, '123:456:1', **{'73CfbLEx': f'123@456:1@{category}:1'}))
                self.assertFalse(self.check(code, '123:456:1', **{'73CfbLEx': '123@456:1@0:1'}))
        for code, category in [('63', 1), ('65', 4), ('67', 5)]:
            self.assertTrue(self.check(code, '123:456:1:789', **{'73CfbLEx': f'123@456:1@{category}:789'}))
            self.assertFalse(self.check(code, '123:456:1:789', **{'73CfbLEx': f'123@456:1@{category}:790'}))

    def test_healing_color_element_and_chain_checks(self):
        self.assertFalse(self.check('12', '3', i1yJ3hmT='10020:1'))
        self.assertTrue(self.check('12', '3', i1yJ3hmT='10130:1'))
        self.assertFalse(self.check('14', '1', i1yJ3hmT='10020:1'))
        self.assertTrue(self.check('14', '1', i1yJ3hmT='20020:1'))
        self.assertTrue(self.check('59', '6:2', qr5PoZ1W='6:3'))
        self.assertFalse(self.check('59', '6:2', qr5PoZ1W='6:2'))
        ctx = self.context()
        ctx['achievements'] = {'MAX_CHAIN_TURN': '10', 'MAX_ELEMENT_CHAIN_TURN': '5'}
        self.assertTrue(CONDITION_CHECKS['122'](ctx, '9'))
        self.assertFalse(CONDITION_CHECKS['132'](ctx, '5'))

    def test_category_helper_rules(self):
        ctx = self.context()
        ctx['helper_master'] = '999999999'
        with patch('exvius_challenges.unit_mst', side_effect=lambda mid: {'GPUkhv72': '2' if str(mid) == '999999999' else '1'}):
            self.assertFalse(CONDITION_CHECKS['170'](ctx, '1'))
            self.assertTrue(CONDITION_CHECKS['171'](ctx, '1'))
            self.assertTrue(CONDITION_CHECKS['172'](ctx, '2:1'))
            self.assertTrue(CONDITION_CHECKS['173'](ctx, '1:2'))

    def test_timed_encounters_and_harvests(self):
        ctx = self.context(vMo5cnmx='456:30:-1,789:10:50', MyIhjd6W='1:5,2:30,3:70', **{'7TyWeg0H': '100'})
        self.assertTrue(CONDITION_CHECKS['1001'](ctx, '60:123:456'))
        self.assertFalse(CONDITION_CHECKS['1002'](ctx, '60:123:456'))
        self.assertTrue(CONDITION_CHECKS['1002'](ctx, '60:123:789'))
        self.assertTrue(CONDITION_CHECKS['1003'](ctx, '60:2'))
        self.assertFalse(CONDITION_CHECKS['1003'](ctx, '60:3'))
        self.assertTrue(CONDITION_CHECKS['1000'](ctx, '100'))

    def test_rated_unit_rewards_preserve_level_and_trust(self):
        rows = parse('10:904000101:1:100:1:0:100000005')
        self.assertEqual(rows[0]['affinity_points'], ['50', ''])
        self.p._grant_items(rows)
        self.assertEqual(self.p.data['roster'][-1]['affinity_points'][0], '50')
        self.assertTrue(self.p.data['roster'][-1]['affinity_info'][0].startswith('70:'))
        rows = parse('10:906000104:1:100:1:0:0:0:1100000050')
        self.assertEqual(rows[0]['affinity_points'], ['', '500'])
        self.assertEqual(parse('20:101000200:1:100:1'), [{'kind': 20, 'id': 101000200, 'count': 1}])
        with self.assertRaises(ValueError):
            parse('20:101000200:1:20')

    def test_moogle_cave_trust_daily_limit_and_retry_after_reload(self):
        expedition.expedition_refresh({}, {expedition.QUEST: [{}]})
        block = self.p.data['exvius_expedition']
        key = next(iter(block['quests']))
        block['quests'][key]['Ko86047K'] = '102'
        member = self.p.data['roster'][0]
        party = f"{member['instance_id']}:{member['master_id']}"
        for iteration in range(3):
            request = {expedition.QUEST: [{'Ko86047K': key, '7mA422N6': party}]}
            expedition.expedition_start({}, request)
            self.assertEqual(self.p.data['exvius_expedition']['quests'][key]['3JND4wjr'], '2')
            before = deepcopy(self.p.data)
            expedition.expedition_accelerate({}, {expedition.QUEST: [{'Ko86047K': key, '8Pa9U16z': '23:901:1'}]})
            self.assertEqual(self.p.data, before)
            self.p.data['exvius_expedition']['quests'][key]['2CL6pZmE'] = '1799999999'
            request = {expedition.QUEST: [{'Ko86047K': key, 'hKcId7sN': '100'}]}
            out = expedition.expedition_end({}, request)
            self.assertIn('UDBrChWN', out)
            self.reload()
            before = deepcopy(self.p.data)
            expedition.expedition_end({}, request)
            self.assertEqual(self.p.data, before)
            key = next(k for k, v in self.p.data['exvius_expedition']['quests'].items() if v['Ko86047K'] == '102')
        member = self.p.data['roster'][0]
        self.assertGreater(int(member['affinity_points'][0]), 0)
        before = deepcopy(self.p.data)
        expedition.expedition_start({}, {expedition.QUEST: [{'Ko86047K': key, '7mA422N6': party}]})
        self.assertEqual(self.p.data, before)

    def test_bad_success_percentage_does_not_consume_job(self):
        expedition.expedition_refresh({}, {expedition.QUEST: [{}]})
        key = next(iter(self.p.data['exvius_expedition']['quests']))
        member = self.p.data['roster'][0]
        expedition.expedition_start({}, {expedition.QUEST: [{'Ko86047K': key, '7mA422N6': f"{member['instance_id']}:{member['master_id']}"}]})
        self.p.data['exvius_expedition']['quests'][key]['2CL6pZmE'] = '1799999999'
        before = deepcopy(self.p.data)
        for rate in ['invalid', 'NaN', 'Infinity', '-1', '101']:
            expedition.expedition_end({}, {expedition.QUEST: [{'Ko86047K': key, 'hKcId7sN': rate}]})
            self.assertEqual(self.p.data, before)

    def test_native_empty_group_refresh_creates_offers_once_per_free_period(self):
        request = {expedition.QUEST: []}
        out = expedition.expedition_refresh({}, request)
        self.assertTrue(out[expedition.QUEST])
        saved = deepcopy(self.p.data)
        self.reload()
        expedition.expedition_refresh({}, request)
        self.assertEqual(self.p.data, saved)

    def test_party_snapshot_restores_owned_loadouts_after_reload(self):
        unit = self.p.data['roster'][0]
        iid = str(unit['instance_id'])
        materia = next(iter(_mst('F_MATERIA_MST.ndjson', 'H5jBL0Vf')))
        self.p.grant_item(22, materia, 1)
        unit['materia'] = [materia, '0', '0', '0']
        card = next(iter(_mst('F_VISION_CARD_MST.ndjson', '5giCMUd2')))
        self.p.data['vision_cards'] = [{'user_vc_id': '1234', 'vc_id': card, 'level': 1}]
        unit['vision_card'] = '1234'
        snapshot = deepcopy(unit['equipment'])
        fields = {'YLi31qam': '1', 'o0T4S52k': '0', 'r21y0YzS': '0', '2A6fYiEC': f'1:0:{iid}'}
        expedition.party_save({}, {expedition.SLOT: [fields]})
        unit.update(equipment={}, materia=[], vision_card='')
        self.reload()
        loaded = expedition.party_load({}, {expedition.SLOT: [fields]})
        reply = self.p.apply_to_reply(loaded, 'Q7jV6pno')
        self.assertNotIn('B71MekS8', reply)
        self.assertEqual(reply['5Eb0Rig6'][0]['2A6fYiEC'], fields['2A6fYiEC'])
        unit = self.p.data['roster'][0]
        self.assertEqual(unit['equipment'], snapshot)
        self.assertEqual(unit['materia'], [materia, '0', '0', '0'])
        self.assertEqual(unit['vision_card'], '1234')
        sold = next(i for i in snapshot.values() if i != '0')
        for row in self.p.data['roster']:
            row['equipment'] = {k: v for k, v in row['equipment'].items() if v != sold}
        self.p.data['inventory']['equipment'] = [e for e in self.p.data['inventory']['equipment'] if str(e['item_id']) != sold]
        expedition.party_load({}, {expedition.SLOT: [fields]})
        self.assertNotIn(sold, self.p.data['roster'][0]['equipment'].values())

    def test_town_delivery_rewards_and_receipts_survive_reload(self):
        quests = _mst('F_QUEST_MST.ndjson', 'Z34jU7ue')
        steps = _mst('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')
        step = next(r for r in steps.values() if r['Z34jU7ue'] == '1001001')
        qid, sid = step['Z34jU7ue'], step['7Svg2kdT']
        self.p.grant_item(20, 102001100, 1)
        request = {'JcxS6A8N': [{'Gh92V3Tx': '1101'}], '1sGiqV9T': [{'i9han5Sz': f'{qid}:{sid}'}]}
        expedition.mission_update({}, request)
        request['1sGiqV9T'] = [{'9YPZuB2i': f'{qid}:{sid}'}]
        out = expedition.mission_update({}, request)
        self.assertEqual(out['JG96kr5C'][0]['4kcAD9fW'], '2')
        self.assertEqual(self.p.item_count(20, 102001100), 0)
        self.assertIn(qid, self.p.data['exvius_map']['rewarded'])
        self.reload()
        before = deepcopy(self.p.data)
        expedition.mission_update({}, request)
        self.assertEqual(self.p.data, before)
        self.assertIn('hQKAwj18', self.p.groups())

    def test_native_saved_equipment_and_shift_forms_survive_legacy_reload(self):
        unit = self.p.data['roster'][0]
        iid = str(unit['instance_id'])
        gear = next(v for v in unit['equipment'].values() if v != '0')
        fields = {'YLi31qam': '0', 'o0T4S52k': '0', 'r21y0YzS': '0',
                  '2A6fYiEC': f'0:0:{iid}', 'w1JG7i9j': f'{iid}:1',
                  '93Y6evuT': f'{iid}:1-{gear}|2-{gear}',
                  '80NUYFMJ': f'{iid}:1-0|1-0@2-0@3-0@4-0',
                  'nQ1iAGf3': f'{iid}:0-0', '2c8nqLrM': f'{iid}:0',
                  'XZ4Kh7Ic': '0:0,1:0,2:0,3:0,4:0', 'xBi3L6yR': '1',
                  'Na7YM2v4': '', 'G4L0YIB2': 'SLOT1'}
        expedition.party_save({}, {expedition.SLOT: [fields]})
        slot = self.p.data['exvius_party_register']['slots']['0:0']
        self.assertEqual(slot['loadouts'][iid]['shift_equipment']['2'], gear)
        del slot['loadouts']
        unit.update(equipment={}, shift_equipment={}, brave_shift=0)
        self.reload()
        expedition.party_load({}, {expedition.SLOT: [fields]})
        unit = self.p.data['roster'][0]
        self.assertEqual(unit['equipment']['1'], gear)
        self.assertEqual(unit['shift_equipment']['2'], gear)
        self.assertEqual(unit['brave_shift'], 1)
        owned = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in self.p.equip_item_rows()}
        self.assertGreaterEqual(owned[gear], 1)

    def test_catalogue_modes_reach_native_groups_and_keep_season_progress(self):
        from event_archive import menu, listings
        from exvius_fortuna import gambit_bonuses
        data = menu(self.p)
        mode_areas = set(data['native_modes'])
        all_mode_dungeons = {str(r['U9iHsau3']) for r in _mst('F_MISSION_MST.ndjson', 'qo3PECw6').values()
                             if str(r.get('uv60hgDW')) in mode_areas}
        self.assertEqual(set(data['mode_dungeon_ids']), all_mode_dungeons)
        self.assertGreater(len(all_mode_dungeons), len(data['native_dungeons']))
        for aid in mode_areas:
            entries = [did for did, info in data['native_dungeons'].items() if info['area'] == aid and info['entry']]
            self.assertEqual(len(entries), 1, aid)
        for mode, expected in [('tfa', 35), ('parade', 46)]:
            self.assertEqual(sum(v == mode for v in data['native_modes'].values()), expected)
            title = 'Clash of Wills' if mode == 'tfa' else 'Dark Visions'
            self.assertEqual(sum(r['name'] == title for r, _ in listings()), 1)
            did = next(k for k, v in data['native_dungeons'].items() if v['mode'] == mode)
            selected = menu(self.p, f'{mode}:{did}')
            self.assertTrue(selected['native_groups'])
            self.assertEqual(selected['scene'], 940000 if mode == 'tfa' else 'parade')
            if mode == 'tfa':
                self.assertEqual(selected['native_groups']['L6XRZb0z'][0]['9gAL7Bur'], '1')
        cow = [k for k, v in data['native_dungeons'].items() if v['mode'] == 'tfa']
        menu(self.p, 'tfa:' + cow[0])
        self.p.data['exvius_tfa']['slots'] = '20:101000100:1-0'
        self.p.data['exvius_tfa']['groups']['L6XRZb0z'][0]['9gAL7Bur'] = '0'
        migrated = menu(self.p, 'tfa:' + cow[0])
        self.assertEqual(migrated['native_groups']['L6XRZb0z'][0]['9gAL7Bur'], '1')
        menu(self.p, 'tfa:' + cow[1])
        self.assertNotEqual(self.p.data['exvius_tfa']['groups']['L6XRZb0z'][0]['pvS5A4kE'], '7101000')
        menu(self.p, 'tfa:' + cow[0])
        self.assertEqual(self.p.data['exvius_tfa']['slots'], '20:101000100:1-0')
        self.assertEqual(gambit_bonuses('7100', 2, ['1000']), (1200, 1000))
        for area, tier, selected in [('7100', 1, ['1000']), ('7100', 5, ['999999']),
                                     ('7100', 5, ['1000', '1000'])]:
            with self.assertRaises(ValueError):
                gambit_bonuses(area, tier, selected)

    def test_special_six_unit_decks_survive_save_edit_and_reload(self):
        from ffbe_player import apply_party_edit
        normal = deepcopy(self.p.data['party']['decks'])
        while len(self.p.data['roster']) < 6:
            self.p.grant_unit('100000102')
        ids = [str(u['instance_id']) for u in self.p.data['roster'][:6]]
        packed = ','.join(f'0:{n}:{iid}' for n, iid in enumerate(ids))
        apply_party_edit(json.dumps({'CN92arJK': [{'xBi3L6yR': '8', 'b61ICxJk': '0'}],
                                     '5Eb0Rig6': [{'r21y0YzS': '0', '2A6fYiEC': packed}]}))
        self.assertEqual(self.p.data['party']['decks'], normal)
        self.assertEqual(self.p.party_instance_ids('9200101'), ids)
        self.assertEqual(mission_result_from(json.dumps({'jQsE54Iz': [{'qo3PECw6': '9200101'}]}))['party_size'], 6)
        fields = {'YLi31qam': '0', 'o0T4S52k': '8', 'r21y0YzS': '0',
                  'xBi3L6yR': '8', '2A6fYiEC': packed, 'XZ4Kh7Ic': ','.join(f'{n}:0' for n in range(6))}
        expedition.party_save({}, {expedition.SLOT: [fields]})
        self.p.special_party('8')['decks'][0]['members'] = []
        self.reload()
        loaded = expedition.party_load({}, {expedition.SLOT: [fields]})
        reply = self.p.apply_to_reply(loaded, 'Q7jV6pno')
        self.assertNotIn('B71MekS8', reply)
        self.assertNotIn('5Eb0Rig6', reply)
        self.assertEqual(reply['GV7Ej6n0'][0]['2A6fYiEC'], packed)
        self.assertEqual(self.p.party_instance_ids('9200101'), ids)
        self.assertEqual(self.p.data['party']['decks'], normal)
        self.assertNotEqual(self.p.battle_party('71000101'), self.p.battle_party('9200101'))
        groups = self.p.groups()
        self.assertIn('GV7Ej6n0', groups)
        self.assertIn('zeucwm6H', groups)
        self.assertNotIn('GV7Ej6n0', self.p.apply_to_reply({'LhVz6aD2': [{}]}, 'pB3st6Tg'))

    def test_global_opening_vision_stage_keeps_its_published_profile(self):
        from battle_content import assemble
        bundle = assemble('9200101', authored={})
        profile = bundle['bV34YIJQ'][0]
        self.assertEqual(profile['G4L0YIB2'], 'Dark Platinal')
        self.assertEqual(profile['fh31sk7B'], '80000000')
        self.assertEqual(profile['hn42BL3Q'], '-50,80,80,80,80,80,80,80,80')
        for mid, expected in [('9200102', 10000), ('9200201', 20000),
                              ('9200303', 30000), ('9200304', 50000), ('9200305', 100000)]:
            row = _mst('F_MISSION_MST.ndjson', 'qo3PECw6')[mid]
            self.assertEqual(int(modes._parade_archive(self.p, row, {'turns': 1})['qf9S3TLg']), expected)

    def test_parade_bests_points_milestones_and_seasons_persist(self):
        from event_archive import menu
        menu(self.p, 'parade:92001')
        f = self.p.data['exvius_parade']
        request = {'jQsE54Iz': [{'qo3PECw6': '9200101'}],
                   '2urzfX6d': [{'69ieJGhD': '0:123:1', 'Z1p0j9uF': '0'}],
                   'nSG9Jb1s': [{'NYb0Cri6': 'MAX_DAMAGE_TURN', '6gAX1BpC': '2147483647'},
                                {'NYb0Cri6': 'MAX_CHAIN', '6gAX1BpC': '100'}]}
        modes._parade_complete(f, '9200101', request)
        self.assertEqual(f['bests']['9200101']['5EWcu4M8'], '1:1,2:2,3:3,4:4,5:5')
        ranks = {int(part.split(':')[0]): int(part.split(':')[1])
                 for part in f['bests']['9200101']['wF5Ac6ey'].split(',')}
        self.assertEqual((ranks[3], ranks[4], ranks[5]), (0, 0, 0))
        self.assertEqual(int(f['bests']['9200101']['cH15BhQ0']), max(ranks.values()))
        self.assertGreater(int(f['bests']['9200101']['7HSK9eBV']), 60000)
        self.assertTrue(f['milestones'])
        before = deepcopy(self.p.currencies), deepcopy(self.p.data['inventory'])
        modes._parade_complete(f, '9200101', request)
        self.assertEqual((self.p.currencies, self.p.data['inventory']), before)
        score = f['bests']['9200101']['7HSK9eBV']
        self.reload()
        data = menu(self.p)
        other = next(did for did, v in data['native_dungeons'].items()
                     if v['mode'] == 'parade' and v['area'] != '920')
        menu(self.p, 'parade:' + other)
        self.assertEqual(self.p.data['exvius_parade']['bests'], {})
        result = menu(self.p, 'parade:92001')
        self.assertEqual(result['native_groups']['yA8Nn9vK'][0]['UbQ26oH4'], score)
        ranks = result['native_groups']['yA8Nn9vK'][0]
        self.assertEqual(ranks['52ibRBqw'], ranks['7SPHKY1j'])
        self.assertEqual(result['native_groups']['gXrD1h58'][0]['L84eYzxv'], '650001')
        event = result['native_groups']['gXrD1h58'][0]
        self.assertEqual(event['RdV4nK8w'], '1')
        self.assertEqual(event['td06MKEX'], '65000')
        import datetime
        datetime.datetime.strptime(event['VjJQ51uG'], '%Y-%m-%d %H:%M:%S')
        page = modes.parade_rewards_page(self.p)
        self.assertIn('Dark Matter', page)
        self.assertIn('25,000', page)
        self.assertIn('Received', page)

    def test_clash_boss_identity_and_level_scaling_use_global_profiles(self):
        import battle_content
        from pathlib import Path
        records = json.loads(Path(battle_content.HERE, 'event_encounters.json').read_text(encoding='utf8'))
        clashes = {mid: row for mid, row in records['missions'].items() if row.get('clash_scale')}
        self.assertEqual(len(clashes), 175)
        from ffbe_battle import challenge_table
        self.assertNotIn('71000101', challenge_table())
        for row in clashes.values():
            self.assertTrue(row['bundle']['wbet57nF'])
            self.assertTrue(row['source_sha256'])
        self.p.data['exvius_tfa'] = {'active': {'boss_level': 1}}
        low = battle_content.event_encounter('71000101')
        self.assertEqual(low['wbet57nF'][0]['G4L0YIB2'], 'Vestige of Morgana')
        self.assertEqual(low['bV34YIJQ'][0]['8a6gAwN9'], '900011024')
        self.p.data['exvius_tfa']['active']['boss_level'] = 10
        high = battle_content.event_encounter('71000101')
        for token in ('fh31sk7B', '9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4'):
            self.assertGreater(int(high['bV34YIJQ'][0][token]), int(low['bV34YIJQ'][0][token]))

    def exbonus_unit(self, mid='100031007'):
        unit = self.p.grant_unit(mid)
        unit['nv_ex_level'] = 3
        self.p.grant_item(20, 250000040 if mid == '100031007' else 250000010, 10000)
        return str(unit['instance_id'])

    def exbonus_draw(self, iid, count):
        return expedition.exbonus_execute({}, {'Rv1YV69s': [{'og2GHy49': iid, '2RtVPS3b': str(count)}]})

    def test_recovered_exbonus_masters_have_native_skills_and_cap_recipes(self):
        rows = _mst('F_UNIT_EX_BONUS_MST.ndjson', None)['__rows__']
        recovered = [r for r in rows if r['woghJa61'] != '1']
        self.assertEqual(len(recovered), 1062)
        for row in recovered:
            self.assertGreater(int(row['es0Yun3Z']), 0)
            if row['xm7c08IS'] == '7':
                self.assertIn(row['xHZj7Va5'], _mst('F_ABILITY_MST.ndjson', 'Ga5V42LZ'))
            elif row['xm7c08IS'] == '8':
                self.assertIn(row['xHZj7Va5'], _mst('F_SUBLIMATION_RECIPE_MST.ndjson', 'SJ56uhz2'))

    def test_all_exbonus_cap_skills_have_english_names_and_nonplaceholder_explanations(self):
        import json
        from pathlib import Path
        text = json.loads((Path(__file__).resolve().parents[1] / 'server/content/exbonus_text.json').read_text(encoding='utf8'))
        bonuses = _mst('F_UNIT_EX_BONUS_MST.ndjson', None)['__rows__']
        recipes = _mst('F_SUBLIMATION_RECIPE_MST.ndjson', 'SJ56uhz2')
        descriptions = _mst('F_ABILITY_EXPLAIN_MST.ndjson', 'Ga5V42LZ')
        ids = {recipes[r['xHZj7Va5']]['Q1n9iYgz'] for r in bonuses if r['xm7c08IS'] == '8'}
        self.assertEqual(len(ids), 22)
        for sid in ids:
            self.assertTrue(text[sid]['name'], sid)
            self.assertTrue(text[sid]['description'], sid)
            self.assertNotEqual(descriptions[sid]['T7aEx3Mj'], 'Test data', sid)
            self.assertNotRegex(text[sid]['name'] + text[sid]['description'], r'[\u3040-\u30ff\u3400-\u9fff]|Unknown')
        self.assertEqual(text['709649']['name'], 'Braver (FFVII REMAKE)')
        self.assertIn('400x', descriptions['709649']['T7aEx3Mj'])

    def test_exbonus_real_draws_pay_fragments_learn_and_survive_reload(self):
        iid = self.exbonus_unit()
        before = self.p.item_count(20, 250000040)
        with patch.object(expedition.secrets, 'randbelow', side_effect=lambda n: n - 1):
            out = self.exbonus_draw(iid, 3)
        self.assertEqual(self.p.item_count(20, 250000040), before - 15)
        user = self.p.data['exvius_exbonus']['units'][iid]
        self.assertEqual(user['step'], 1)
        self.assertEqual(user['details'], {'100201009': 1, '100201008': 1, '100201007': 1})
        self.assertEqual(out['Rv1YV69s'][0]['2RtVPS3b'], '3')
        self.reload()
        projection = self.p.apply_to_reply({'LhVz6aD2': [{}]})
        self.assertEqual({r['L3Nx1Jpb']: int(r['Qy5EvcK1']) for r in projection['Za8XDQi7']}, user['details'])
        native = self.p.apply_to_reply(out, reply_id='68RQ9GwN')
        self.assertNotIn('B71MekS8', native)
        self.assertNotIn('5Eb0Rig6', native)
        self.assertIn('0dNXQa3R', native)
        self.assertIn('Rv1YV69s', native)

    def test_exbonus_finite_pool_never_overdraws_and_refusal_is_atomic(self):
        iid = self.exbonus_unit()
        with patch.object(expedition.secrets, 'randbelow', return_value=0):
            self.exbonus_draw(iid, 178)
        details = self.p.data['exvius_exbonus']['units'][iid]['details']
        self.assertEqual(sum(details.values()), 178)
        rows = [r for r in _mst('F_UNIT_EX_BONUS_MST.ndjson', None)['__rows__'] if r['woghJa61'] == '100031007']
        self.assertEqual(details, {r['L3Nx1Jpb']: int(r['es0Yun3Z']) for r in rows})
        before = deepcopy(self.p.data)
        self.assertNotIn('Rv1YV69s', self.exbonus_draw(iid, 1))
        self.assertEqual(self.p.data, before)

    def test_exbonus_saved_stats_migrate_and_use_the_fifth_native_component(self):
        from player_state import owned_unit_stats
        iid = self.exbonus_unit()
        unit = next(u for u in self.p.data['roster'] if str(u['instance_id']) == iid)
        before = owned_unit_stats(unit)
        self.p.data['exvius_exbonus'] = {'units': {iid: {'step': 1, 'details': {'100201003': 1}}}}
        self.reload()
        unit = next(u for u in self.p.data['roster'] if str(u['instance_id']) == iid)
        self.assertEqual(unit['exbonus_stats'], [0, 0, 2, 0, 0, 0])
        self.assertEqual(owned_unit_stats(unit), [v + (2 if n == 2 else 0) for n, v in enumerate(before)])
        out = self.p.apply_to_reply({'Rv1YV69s': [{'og2GHy49': iid}]}, reply_id='68RQ9GwN')
        self.assertEqual(len(out['8gSkPD6b']), 1)
        self.assertEqual(out['8gSkPD6b'][0]['o7Ynu1XP'].split('-')[-1], '2')
        self.assertNotIn('B71MekS8', out)

    def test_exbonus_learned_abilities_have_original_acquisition_gates(self):
        rows = _mst('F_UNIT_SERIES_LV_ACQUIRE_MST.ndjson', None)['__rows__']
        gated = [r for r in rows if r.get('59kRbpKz') == '1']
        learned = {sid for r in gated for sid in r['1Zsh27mS'].split(',')}
        bonuses = _mst('F_UNIT_EX_BONUS_MST.ndjson', None)['__rows__']
        self.assertTrue({r['xHZj7Va5'] for r in bonuses if r['xm7c08IS'] == '7'} <= learned)
        self.assertTrue(any(r['woghJa61'] == '100031007' and '151360' in r['1Zsh27mS'].split(',') for r in gated))

    def test_exbonus_requires_ex3_and_cannot_spend_unowned_fragments(self):
        iid = self.exbonus_unit()
        unit = next(u for u in self.p.data['roster'] if str(u['instance_id']) == iid)
        unit['nv_ex_level'] = 2
        before = deepcopy(self.p.data)
        self.assertNotIn('Rv1YV69s', self.exbonus_draw(iid, 1))
        self.assertEqual(self.p.data, before)
        unit['nv_ex_level'] = 3
        self.p.spend_item(20, 250000040, self.p.item_count(20, 250000040))
        before = deepcopy(self.p.data)
        self.assertNotIn('Rv1YV69s', self.exbonus_draw(iid, 2))
        self.assertEqual(self.p.data, before)

    def test_exbonus_cap_unlock_allows_the_native_enhancement_recipe(self):
        import exvius_actions_shops as shops
        iid = self.exbonus_unit('207002007')
        recipe = _mst('F_SUBLIMATION_RECIPE_MST.ndjson', 'SJ56uhz2')['400000001']
        request = {'NcI0GgU9': [{'6uIYE15X': iid, 'SJ56uhz2': '400000001', 'yjY4GK3X': '2'}]}
        self.assertNotIn('j0e1xIv9', shops.sublimation_skill({}, request))
        self.p.data['exvius_exbonus'] = {'units': {iid: {'step': 1, 'details': {'100101007': 1}}}}
        self.p.data['exvius_sublimation'] = {'skills': {iid: {recipe['hxu12ZFS']: recipe['hxu12ZFS']}}}
        self.p.currencies['gil'] = 100000000
        for grant in shops._triples(recipe['HS7V6Ww1']):
            self.p.grant_item(grant['kind'], grant['id'], grant['count'])
        out = shops.sublimation_skill({}, request)
        self.assertEqual(out['j0e1xIv9'][0]['6bHxDEL0'], recipe['Q1n9iYgz'])
        self.reload()
        self.assertIn(out['j0e1xIv9'][0], self.p.groups()['j0e1xIv9'])

    def test_cloud_braver_advances_all_prerequisites_then_exbonus_cap(self):
        import exvius_actions_shops as shops
        iid = self.exbonus_unit('207002007')
        self.p.currencies['gil'] = 100000000
        recipes = _mst('F_SUBLIMATION_RECIPE_MST.ndjson', 'SJ56uhz2')
        normal = ('300000002', '300000003', '300000004', '300000005')
        for rid in (*normal, '400000003'):
            row = recipes[rid]
            for grant in shops._triples(row['HS7V6Ww1']):
                self.p.grant_item(grant['kind'], grant['id'], grant['count'])
        def upgrade(rid):
            return shops.sublimation_skill({}, {'NcI0GgU9': [{'6uIYE15X': iid, 'SJ56uhz2': rid,
                                                              'yjY4GK3X': '2'}]})
        for rid in normal:
            first = upgrade(rid)
        self.assertEqual(first['j0e1xIv9'][0]['6bHxDEL0'], '236014')
        self.assertNotIn('j0e1xIv9', upgrade('400000003'))
        self.p.data['exvius_exbonus'] = {'units': {iid: {'step': 1, 'details': {'100101009': 1}}}}
        second = upgrade('400000003')
        self.assertEqual(second['j0e1xIv9'][0]['1MH7Na23'], '236010')
        self.assertEqual(second['j0e1xIv9'][0]['6bHxDEL0'], '709649')

    def test_fortuna_preview_matches_the_pinned_native_five_column_codec(self):
        from exvius_fortuna import preview, policy
        groups = preview().split(',')
        self.assertEqual([int(g.split('@')[0]) for g in groups], [1, 2, 3, 4, 5])
        first = groups[0].split('@')[1].split('-')
        self.assertEqual(sum(int(r.split(':')[2]) for r in first), 100000)
        for encoded, reward in zip(first, policy()['tiers']['1']):
            kind, iid, probability, category, quantity = encoded.split(':')
            self.assertEqual(f'{kind}:{iid}:{quantity}', reward['reward'])
            self.assertEqual(int(category), int(reward['rare']))
            self.assertGreater(int(probability), 0)
        self.assertTrue(preview(3).startswith('3@'))

    def test_all_clash_level_rewards_resolve_and_only_pay_new_levels(self):
        from exvius_fortuna import level_rewards, complete, missions, ensure
        from player_state import emblem_mst
        source = level_rewards()
        self.assertEqual(len(source), 35)
        for season in source.values():
            self.assertEqual(set(season['levels']), {str(n) for n in range(1, 100)})
            for row in season['levels'].values():
                for grant in row['rewards']:
                    self.assertTrue(self.p._can_credit(grant), grant)
                for emblem in row['emblems']:
                    self.assertIsNotNone(emblem_mst(emblem))
        row = missions('710001')[0]
        f = {'active': {'boss_level': 2}}
        ensure(f, '710001')
        self.p.data['exvius_tfa'] = f
        complete(self.p, row['qo3PECw6'], 1, {'cleared': True})
        self.assertEqual(self.p.data['exvius_tfa']['rewarded_level'], 2)
        self.assertTrue(self.p.data['exvius_tfa']['last_level_rewards'])
        personal = self.p.data['exvius_tfa']['groups']['cBHNnXQZ'][0]
        self.assertEqual((personal['3HbFrqo5'], personal['8s9wNSpd']), ('1', '1'))
        self.assertEqual(int(personal['UbQ26oH4']), self.p.data['exvius_tfa']['best_score'])
        self.assertGreater(int(personal['UbQ26oH4']), 0)
        self.reload()
        saved = deepcopy(self.p.data)
        complete(self.p, row['qo3PECw6'], 1, {'cleared': True})
        self.assertEqual(self.p.data, saved)
        complete(self.p, row['qo3PECw6'], 2, {'cleared': True})
        self.assertEqual(self.p.data['roster'], saved['roster'])
        self.assertEqual(len(self.p.mailbox), len(saved['mailbox']))

    def test_every_clash_season_links_its_original_native_ranking_table(self):
        from exvius_fortuna import ensure, level_rewards
        from event_archive import activate_mode
        missions = _mst('F_MISSION_MST.ndjson', 'qo3PECw6').values()
        rankings = _mst('F_SUMALLY_REWARD_MST.ndjson', None)['__rows__']
        for area in level_rewards():
            mission = next(r for r in missions if r['uv60hgDW'] == area and r['gQR24kST'] == '50')
            f = {}
            event = ensure(f, mission['U9iHsau3'])
            self.assertTrue(any(r['L84eYzxv'] == event['L84eYzxv'] for r in rankings), area)
            result = activate_mode(self.p, 'tfa:' + mission['U9iHsau3'])
            expected = [r for r in rankings if r['L84eYzxv'] == event['L84eYzxv']]
            self.assertEqual(result['ranking_id'], int(event['L84eYzxv']))
            self.assertEqual(result['ranking_rewards'], expected)
            event['L84eYzxv'] = '0'
            self.assertNotEqual(ensure(f, mission['U9iHsau3'])['L84eYzxv'], '0')


if __name__ == '__main__':
    unittest.main()
