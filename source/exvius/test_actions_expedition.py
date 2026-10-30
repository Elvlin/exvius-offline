"""Shipped-master action tests. Import runs the suite; no save file is read or written."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ffbe_state
from ffbe_state import State
import player_state
import exvius_actions_expedition as actions
from exvius_actions import UNIT_GROUP, _mst


class ExpeditionActions(unittest.TestCase):
    covered = set()

    def setUp(self):
        self.previous = State.player
        self.notes = list(ffbe_state.NOTES)
        self.player = player_state.PlayerState.load('/nonexistent', slot='selftest-expedition')
        State.player = self.player
        self.player.data['currencies'].update(gil=100000, lapis_free=1000, lapis_paid=1000)
        self.clock = patch.object(actions.time, 'time', return_value=1800000000)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        State.player = self.previous
        ffbe_state.NOTES[:] = self.notes

    def call(self, name, group=None, **fields):
        endpoints = json.loads((Path(actions.__file__).parent / 'endpoints.json').read_text())['by_class']
        self.covered.add(name)
        req = {group: [fields]} if group else {}
        spec = {'test-envelope': [{'preserve': 'yes'}]}
        before = deepcopy(spec)
        out = actions.HANDLERS[endpoints[name]['request_id']](spec, req)
        self.assertIsInstance(out, dict)
        self.assertEqual(spec, before, 'shared default reply was mutated')
        self.assertEqual(out['test-envelope'], before['test-envelope'])
        return out

    def refresh(self, selector=None):
        fields = {} if selector is None else {'0B8RL54c': selector}
        return self.call('sgExpdQuestRefreshRequest', actions.QUEST, **fields)

    def party(self):
        return ','.join(f"{u['instance_id']}:{u['master_id']}" for u in self.player.data['roster'])

    def test_town_update_switches_survive_sync_and_retry(self):
        from ffbe_battle import record_pushed_switches
        self.addCleanup(setattr, State, 'state_dirty', State.state_dirty)
        sid = '10000152'
        position = player_state.switch_position(sid)
        self.assertIsNotNone(position)
        kind, index = position
        self.player.switches.setdefault(kind, set()).discard(index)
        request = json.dumps({'JcxS6A8N': [{'Gh92V3Tx': '1101', 'dIPkNn61': sid}]})
        record_pushed_switches(request)
        self.assertIn(index, self.player.switches[kind])
        snapshot = deepcopy(self.player.switches)
        record_pushed_switches(request)
        self.assertEqual(self.player.switches, snapshot)

    def start(self, key, consume='0'):
        return self.call('sgExpdQuestStartRequest', actions.QUEST,
                         Ko86047K=key, **{'7mA422N6': self.party(), 'sO308L0M': consume})

    def test_info_initializes_once_and_reopens_saved_jobs(self):
        out = self.call('sgExpdQuestInfoRequest')
        self.assertEqual(len(out[actions.QUEST]), int(actions._define('EXPEDITION_MAX_AVAILABLE')))
        key = out[actions.QUEST][0]['q3D53k94']
        self.start(key)
        saved = deepcopy(self.player.data)
        self.player = player_state.PlayerState(deepcopy(saved))
        State.player = self.player
        out = self.call('sgExpdQuestInfoRequest')
        job = next(row for row in out[actions.QUEST] if row['q3D53k94'] == key)
        self.assertEqual(job['3JND4wjr'], '2')
        self.assertEqual(self.player.data, saved, 'reopen must not replace jobs or charge a refresh')
        self.assertIn('Ec901P4A', out)
        self.assertIn('nv1j95sC', out)
        self.assertIn('nUM2AENx', out)

    def test_expedition_lifecycle_costs_snapshots_and_reservations(self):
        out = self.refresh()
        self.assertEqual(len(out[actions.QUEST]), int(actions._define('EXPEDITION_MAX_AVAILABLE')))
        key = out[actions.QUEST][0]['q3D53k94']
        self.assertNotEqual(key, out[actions.QUEST][0]['Ko86047K'])
        row = _mst('F_EXPEDITION_MST.ndjson', 'Ko86047K')[out[actions.QUEST][0]['Ko86047K']]
        diff = _mst('F_EXPEDITION_DIFFICULTY_MST.ndjson', 'Up7229W2')[row['Up7229W2']]
        gil = self.player.currencies['gil']
        out = self.start(key)
        started = next(q for q in out[actions.QUEST] if q['q3D53k94'] == key)
        self.assertEqual(self.player.currencies['gil'], gil - int(row['7LIoPpG9']))
        self.assertEqual(started['3JND4wjr'], '2')
        self.assertEqual(int(started['2CL6pZmE']) - int(started['Tx6MGkJ1']), int(diff['7Ac7722s']))
        self.assertIn(UNIT_GROUP, out)
        # Start retry, including a different job using reserved units, cannot charge twice.
        paid = self.player.currencies['gil']
        self.start(key)
        other = next(q['q3D53k94'] for q in out[actions.QUEST] if q['q3D53k94'] != key)
        self.start(other)
        self.assertEqual(self.player.currencies['gil'], paid)
        self.player.grant_item(23, 901, 20)
        self.call('sgExpdAccelerateRequest', actions.QUEST, Ko86047K=key, **{'8Pa9U16z': '23:901:1'})
        current = self.player.data['exvius_expedition']['quests'][key]
        self.assertEqual(int(current['2CL6pZmE']), max(1800000000,
                         int(started['2CL6pZmE']) - int(actions._define('EXPEDITION_ADV_DUR'))))
        self.assertEqual(self.player.item_count(23, 901), 19)
        remaining = int(current['2CL6pZmE']) - 1800000000
        needed = (remaining + 3599) // 3600
        if needed:
            self.call('sgExpdAccelerateRequest', actions.QUEST, Ko86047K=key,
                      **{'8Pa9U16z': f'23:901:{needed}'})
        before = deepcopy(self.player.data)
        out = self.call('sgExpdEndRequest', actions.QUEST, Ko86047K=key, hKcId7sN='100.0')
        self.assertIn(out['UDBrChWN'][0]['7x8K23fx'], ('1', '2', '3'))
        self.assertTrue(out['UDBrChWN'][0]['Ra7qY74q'])
        self.assertEqual(out['nv1j95sC'][0]['edd6db2H'], diff['2A07z50y'])
        self.assertNotIn(key, self.player.data['exvius_expedition']['quests'])
        settled = deepcopy(self.player.data)
        self.call('sgExpdEndRequest', actions.QUEST, Ko86047K=key, hKcId7sN='100.0')
        self.assertEqual(self.player.data, settled)
        self.call('sgExpdRecallRequest', actions.QUEST, Ko86047K=key)
        self.start(other)
        self.assertLess(self.player.currencies['gil'], paid)

    def test_refresh_prices_free_timer_and_running_preservation(self):
        out = self.refresh()
        key = out[actions.QUEST][0]['q3D53k94']
        self.start(key)
        next_free = self.player.data['exvius_expedition']['next_free']
        before = deepcopy(self.player.data)
        self.refresh()
        self.assertEqual(self.player.data, before)
        out = self.refresh('50:1')
        exchange = actions._parse_rewards(actions._define('EXPEDITION_REFRESH_EXCHANGE'))
        cost = next(r['count'] for r in exchange if r['kind'] == 50)
        self.assertEqual(self.player.currencies['lapis_free'], 1000 - cost)
        self.assertEqual(self.player.currencies['lapis_paid'], 1000)
        self.assertEqual(out['nUM2AENx'][0]['NB9uKefC'], str(next_free))
        self.assertTrue(any(q['q3D53k94'] == key and q['3JND4wjr'] == '2' for q in out[actions.QUEST]))
        self.player.grant_item(23, 900, 1)
        self.refresh('23:900')
        self.assertEqual(self.player.item_count(23, 900), 0)
        before = deepcopy(self.player.data)
        self.refresh('23:900')
        self.refresh('50:100')
        self.assertEqual(self.player.data, before)

    def test_start_optional_costs_and_atomic_insufficient_funds(self):
        row = next(r for r in _mst('F_EXPEDITION_MST.ndjson', 'Ko86047K').values()
                   if r.get('sO308L0M') and ',' not in r['sO308L0M'])
        self.refresh()
        block = self.player.data['exvius_expedition']
        key = next(iter(block['quests']))
        block['quests'][key]['Ko86047K'] = str(row['Ko86047K'])
        kind, iid, count, bonus = map(int, row['sO308L0M'].split(':'))
        before = deepcopy(self.player.data)
        self.start(key, '1')
        self.assertEqual(self.player.data, before)
        self.player.grant_item(kind, iid, count)
        out = self.start(key, '1')
        self.assertEqual(self.player.item_count(kind, iid), 0)
        self.assertEqual(next(q for q in out[actions.QUEST] if q['q3D53k94'] == key)['Sf2m961q'], str(bonus))

    def test_claims_unlocks_and_entitled_reset(self):
        self.player.data['progress']['cleared_challenges'] = {'1110101': {'1', '2'}}
        self.player.data['progress']['paid_challenges'] = {'1110101': {'1', '2'}}
        before = deepcopy(self.player.data)
        self.call('ChallengeClearRequest')
        self.assertEqual(self.player.data, before)
        kind, bit = player_state.switch_position(actions._define('CHALLENGE_CLEAR_SWITCH'))
        self.player.switches.setdefault(kind, set()).add(bit)
        self.player.data['exvius_repeat'] = {'non_lapis_claims': {'1110101': {'1': {'entries': ['x']}}}}
        self.call('ChallengeClearRequest')
        self.assertEqual(self.player.data['progress']['cleared_challenges'], {})
        self.assertNotIn('non_lapis_claims', self.player.data['exvius_repeat'])
        did = next(iter(_mst('F_DUNGEON_MST.ndjson', 'U9iHsau3')))
        self.assertTrue(self.call('DungeonLiberationRequest', '8FT3kBVA', U9iHsau3=did)['eKZu2j0M'])
        self.assertTrue(self.call('sgMissionUnlockRequest', 'ySFXhkpu', qo3PECw6='1110101')['W0E8BHa8'])
        weekly = actions._expedition_week()
        weekly['points'] = 35
        self.player.data['exvius_expedition'] = weekly
        self.call('sgExpdMileStoneClaimRequest', '5Xh859hl', k60s8T42='1')
        self.assertEqual(self.player.data['exvius_expedition']['claimed'], ['1'])
        before = deepcopy(self.player.data)
        self.call('sgExpdMileStoneClaimRequest', '5Xh859hl', k60s8T42='1')
        self.assertEqual(self.player.data, before)

    def test_switch_update_carry_consumption_retry_and_unknown_switch(self):
        switch = next(iter(_mst('F_SWITCH_MST.ndjson', '8vAYn3IX')))
        self.player.grant_item(20, 101000100, 10)
        self.player.data['inventory']['carry_items'] = [{'disp_order': 0, 'item_id': 101000100, 'count': 5}]
        req = {'0jqUZuT1': [{'dIPkNn61': switch}], 'nE7pV2wr': [{'jsvoa0I2': '0:101000100:3'}]}
        rid = 'Tvq54dx6'
        self.covered.add('MissionSwitchUpdateRequest')
        out = actions.HANDLERS[rid]({}, req)
        stype, bit = player_state.switch_position(switch)
        self.assertIn(bit, self.player.data['progress']['switches'][stype])
        self.assertEqual(self.player.item_count(20, 101000100), 8)
        self.assertEqual(out['nE7pV2wr'], [{'jsvoa0I2': '0:101000100:3'}])
        self.assertIn('juA0Z4m7', out['ExQ7H1ok'][0])
        actions.HANDLERS[rid]({}, req)
        self.assertEqual(self.player.item_count(20, 101000100), 8)
        before = deepcopy(self.player.data)
        req['0jqUZuT1'][0]['dIPkNn61'] = 'not-a-switch'
        req['nE7pV2wr'][0]['jsvoa0I2'] = '0:101000100:1'
        actions.HANDLERS[rid]({}, req)
        self.assertEqual(self.player.data, before)

    def test_map_checkpoint_and_readonly_extra_challenges(self):
        mid = next(iter(_mst('F_MISSION_MST.ndjson', 'qo3PECw6')))
        out = self.call('MissionUpdateRequest', 'jQsE54Iz', qo3PECw6=mid, dIPkNn61='')
        self.assertEqual(self.player.data['exvius_map']['mission'], mid)
        self.assertNotIn('jQsE54Iz', out)
        self.assertEqual(self.player.data['progress']['cleared_missions'], [])
        before = deepcopy(self.player.data)
        out = self.call('sgUserExtraChallengeInfoRequest', 'vKmaUfYm', qo3PECw6=mid + ',' + mid)
        self.assertEqual(out['vKmaUfYm'], [{'qo3PECw6': mid, 'qdhWF7z9': '', 'wf5Toh4k': '', 'JJuN3uaH': ''}])
        self.assertEqual(self.player.data, before)
        actions.mission_update({}, {'jQsE54Iz': [{'qo3PECw6': mid}], '1sGiqV9T': [{'9YPZuB2i': '1:1'}]})
        self.assertEqual(self.player.data, before)

    def test_comeback_batch_trailing_comma_reward_and_idempotence(self):
        row = _mst('F_SG_COMEBACK_QUEST_MST.ndjson', 'ElOXu3qi')['100']
        self.player.data['exvius_comeback'] = {'campaign': '1', 'quests': {
            '100': {'6tSP4s8J': '2', '5rMfWv4X': row['oz5Vt6AR']}}}
        out = self.call('sgComebackQuestClaimRewardRequest', 'cguj1Hd4', MqUuo1XR='1', ElOXu3qi='100,100,')
        self.assertEqual(out['bbjE3Nwh'][0]['6tSP4s8J'], '3')
        reward = actions._parse_rewards(row['dX6cor8j'])[0]
        self.assertEqual(self.player.item_count(reward['kind'], reward['id']), reward['count'])
        before = deepcopy(self.player.data)
        self.call('sgComebackQuestClaimRewardRequest', 'cguj1Hd4', MqUuo1XR='1', ElOXu3qi='100,')
        self.assertEqual(self.player.data, before)
        self.call('sgComebackQuestClaimRewardRequest', 'cguj1Hd4', MqUuo1XR='2', ElOXu3qi='100,')
        self.assertEqual(self.player.data, before)

    def test_panel_completion_reward_duplicate_and_status_readonly(self):
        from ffbe_player import _quest_index
        group = _mst('F_PANEL_QUEST_GROUP_MST.ndjson', 'zF6QIY2r')['1001']
        args = {'fK3W9qYA': group['fK3W9qYA'], 'zF6QIY2r': '1001', 'xm7c08IS': 'L1'}
        before = deepcopy(self.player.data)
        self.call('sgPanelQuestExtraRewardRequest', 'QxrSeO56', **args)
        self.assertEqual(self.player.data, before)
        for qid, meta in _quest_index().items():
            if meta['family'] == 'panelquest' and meta['schedule'] == '1001':
                self.player.data['quest_progress']['counters'][f'panelquest/1001/{qid}'] = meta['max']
        lapis = self.player.currencies['lapis_free']
        out = self.call('sgPanelQuestExtraRewardRequest', 'QxrSeO56', **args)
        self.assertEqual(out['jksIZE9U'][0]['QCLs6SV8'], '1')
        self.assertEqual(self.player.currencies['lapis_free'], lapis + 300)
        self.call('sgPanelQuestExtraRewardRequest', 'QxrSeO56', **args)
        self.assertEqual(self.player.currencies['lapis_free'], lapis + 300)
        self.player.data['exvius_panel']['statuses'] = {'1': {'fK3W9qYA': '1', 'es0Yun3Z': '4', 'uX54AqwV': '1'}}
        before = deepcopy(self.player.data)
        out = self.call('sgPanelQuestStatusGetRequest', 'QxrSeO56', fK3W9qYA='1')
        self.assertEqual(out['UvwpPAtp'][0]['es0Yun3Z'], '4')
        self.assertEqual(out['UvwpPAtp'][0]['uX54AqwV'], '1')
        self.assertEqual(self.player.data, before)

    def test_exbonus_refresh_and_draw_refusal(self):
        iid = str(self.player.data['roster'][0]['instance_id'])
        self.player.data['exvius_exbonus'] = {'units': {iid: {'step': 1, 'details': {'1': 2}}}}
        before = deepcopy(self.player.data)
        out = self.call('ExbonusUpdateRequest', 'N7LA1tUj', og2GHy49=iid)
        self.assertEqual(out['5moIRSz6'][0]['upv38FtD'], '1')
        self.assertEqual(out['Za8XDQi7'][0]['Qy5EvcK1'], '2')
        out = self.call('ExbonusExeRequest', 'Rv1YV69s', og2GHy49=iid, **{'2RtVPS3b': '3', 'UJz5QED2': ''})
        self.assertNotIn('Rv1YV69s', out)
        self.assertEqual(self.player.data, before)

    def test_party_save_load_update_preserve_slots_and_unrelated_decks(self):
        unit = self.player.data['roster'][0]
        iid = str(unit['instance_id'])
        fields = {k: '' for k in actions.SLOT_FIELDS}
        fields.update(YLi31qam='1', o0T4S52k='0', G4L0YIB2='Raid team', xBi3L6yR='1', r21y0YzS='0')
        fields['2A6fYiEC'] = f'1:0:{iid}'
        fields['w1JG7i9j'] = iid + ':0'
        out = self.call('PartyRegisterSlotSaveRequest', actions.SLOT, **fields)
        self.assertEqual(out['0wV1vDmK'][0]['52W9gGbR'], fields['2A6fYiEC'])
        self.assertNotIn('2A6fYiEC', out['0wV1vDmK'][0])
        other = deepcopy(self.player.data['party']['decks'][2])
        saved_gear = deepcopy(unit.get('equipment', {}))
        unit['equipment'] = {'1': '302000100'}
        out = self.call('PartyRegisterSlotLoadRequest', actions.SLOT,
                        YLi31qam='1', o0T4S52k='0', xBi3L6yR='1', r21y0YzS='1')
        self.assertIn(UNIT_GROUP, out)
        projected = self.player.apply_to_reply(out)
        for tag in ('5Eb0Rig6', 'TJ9eL80N', '49rQB3fP', 'MBPCGT84'):
            self.assertIn(tag, projected)
        self.assertEqual(self.player.data['party']['active_deck'], 1)
        self.assertEqual(self.player.data['party']['decks'][1]['members'][0]['instance_id'], iid)
        self.assertEqual(unit['equipment'], saved_gear)
        self.assertTrue(any(r['J1YX9kmM'] == '302000100' for r in self.player.equip_item_rows()))
        self.assertEqual(self.player.data['party']['decks'][2], other)
        before = deepcopy(self.player.data)
        defaults = {k: '' for k in actions.SLOT_FIELDS}
        defaults.update(YLi31qam='0', o0T4S52k='0', xBi3L6yR='1', r21y0YzS='0', Na7YM2v4='302000100')
        out = self.call('PartyRegisterSlotUpdateRequest', actions.SLOT, **defaults)
        self.assertEqual(out['dEA91X0o'][0]['G4L0YIB2'], 'Raid team')
        self.assertEqual(self.player.data['exvius_party_register']['slots']['0:1']['Na7YM2v4'], '302000100')
        # Native strings remain intact while authoritative assignments are restored.
        fields['93Y6evuT'] = 'opaque equipment payload'
        self.call('PartyRegisterSlotSaveRequest', actions.SLOT, **fields)
        before = deepcopy(self.player.data)
        self.call('PartyRegisterSlotLoadRequest', actions.SLOT, YLi31qam='1', o0T4S52k='0', xBi3L6yR='1', r21y0YzS='1')
        self.assertEqual(unit['equipment'], saved_gear)

    def test_frozen_and_malformed_actions_do_not_mutate(self):
        self.refresh()
        key = next(iter(self.player.data['exvius_expedition']['quests']))
        self.player.mode = 'frozen'
        before = deepcopy(self.player.data)
        self.start(key)
        self.refresh('50:1')
        actions.party_save({}, {actions.SLOT: [{'YLi31qam': '1', 'o0T4S52k': '0'}]})
        actions.mission_switch_update({}, {'0jqUZuT1': [{'dIPkNn61': '10000152'}]})
        self.assertEqual(self.player.data, before)
        self.player.mode = 'live'
        for handler in actions.HANDLERS.values():
            if handler is actions.expedition_info:
                continue
            self.assertIsInstance(handler({}, {}), dict)
        self.assertEqual(self.player.data, before)

    def test_z_all_requested_endpoints_were_exercised(self):
        expected = {'sgExpdQuestInfoRequest', 'sgExpdAccelerateRequest', 'sgExpdEndRequest', 'sgExpdMileStoneClaimRequest',
                    'sgExpdQuestRefreshRequest', 'sgExpdQuestStartRequest', 'sgExpdRecallRequest',
                    'ChallengeClearRequest', 'DungeonLiberationRequest', 'MissionSwitchUpdateRequest',
                    'MissionUpdateRequest', 'sgComebackQuestClaimRewardRequest', 'sgPanelQuestExtraRewardRequest',
                    'sgPanelQuestStatusGetRequest', 'sgMissionUnlockRequest', 'sgUserExtraChallengeInfoRequest',
                    'ExbonusExeRequest', 'ExbonusUpdateRequest', 'PartyRegisterSlotLoadRequest',
                    'PartyRegisterSlotSaveRequest', 'PartyRegisterSlotUpdateRequest'}
        self.assertEqual(self.covered, expected)
        self.assertEqual(len(actions.HANDLERS), 22)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExpeditionActions))
if not result.wasSuccessful():
    raise AssertionError('expedition action tests failed')
