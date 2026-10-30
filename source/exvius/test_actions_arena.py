"""Isolated arena/social checks. Uses shipped masters and never writes a save.

Run with FFBE_DATA set to the shipped data root:
python -I -c "import sys; sys.path[:0]=['source/server','source/exvius']; import test_actions_arena"
"""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import exvius_actions_arena as actions
import ffbe_state
from exvius_actions import UNIT_GROUP, _mst
from player_state import PlayerState


REQUESTS = {
    "RbEntryRequest": "f8kXGWy0", "RbMatchingRequest": "DgG4Cy0F",
    "RbStartRequest": "eHY7X8Nn", "RbEndRequest": "os4k7C0b",
    "RbReStartRequest": "6ZNY3zAm", "RbRankingRequest": "kcW85SfU",
    "RbBoardPieceOpenRequest": "hqzU9Qc5", "ClsmStartRequest": "4uCSA3ko",
    "ClsmEntryRequest": "5g0vWZFq",
    "ClsmEndRequest": "3zgbapQ7", "ClsmLotteryRequest": "Un16HuNI",
    "FriendAgreeRequest": "kx13SLUY", "FriendDeleteRequest": "a2d6omAy",
    "FriendDetailRequest": "7kG0JAvE", "FriendFavoriteRequest": "1oE3Fwn4",
    "FriendRefuseRequest": "1nbWRV9w", "FriendRequest": "j0A5vQd8",
    "FriendSearchRequest": "3siZRSU4", "FriendSuggestRequest": "iAs67PhJ",
    "FriendListRequest": "u7Id4bMg", "GetReinforcementInfoRequest": "AJhnI37s",
}


class ArenaActions(unittest.TestCase):
    def setUp(self):
        self.previous = ffbe_state.State.player
        self.notes = list(ffbe_state.NOTES)
        self.player = PlayerState.load('/nonexistent', slot='selftest-arena')
        ffbe_state.State.player = self.player
        ffbe_state.NOTES.clear()
        self.catalog = actions.load_friends()
        self.assertGreaterEqual(len(self.catalog), 2)
        self.fid = str(self.catalog[0]["friend_id"])
        self.other = str(self.catalog[1]["friend_id"])

    def tearDown(self):
        ffbe_state.State.player = self.previous
        ffbe_state.NOTES[:] = self.notes

    def call(self, name, req=None, spec=None):
        request = copy.deepcopy(req or {})
        default = copy.deepcopy(spec or {})
        out = actions.HANDLERS[REQUESTS[name]](default, request)
        self.assertIsInstance(out, dict)
        self.assertEqual(default, spec or {}, "default reply must not be mutated")
        self.assertEqual(request, req or {}, "request must not be mutated")
        return out

    def friend_req(self, fid=None, **fields):
        return {"I53AVzSo": [{"m3Wghr1j": fid or self.fid, "8zE6w9RP": "0",
                              "0b6e9cwr": "", **fields}]}

    def seed_relation(self, category):
        catalog, state = actions._friends()
        state["relations"][self.fid] = {"type": category, "favorite": 0}
        self.player.data["exvius_friends"] = state
        self.player.data["counts"]["friend"] = sum(r["type"] == 1 for r in state["relations"].values())
        self.player.dirty = False

    def arena_req(self):
        entry = self.call("RbEntryRequest")
        return {"yT12twnc": entry["yT12twnc"]}

    def board_spec(self):
        # Synthetic SERVER group definition, explicitly not a recovered group mapping.
        # Prices, edges, piece IDs and rewards still come from the shipped masters.
        return {"H54XvPis": [{"CIE1rky2": "1", "35iR6h0V": "1000,2000",
            "G4L0YIB2": "Self-test group", "VjJQ51uG": "", "m8ivD4NX": ""}]}

    def board_req(self, ids, board="1000", group="1"):
        return {"7GUQtmb3": [{"CIE1rky2": group, "6m4Rn5jd": board, "mvc31xSV": ids}]}

    def seed_board(self, points=100):
        self.call("RbEntryRequest")
        self.player.data["exvius_arena"]["user"]["mRY52Tib"] = str(points)
        self.player.dirty = False

    def assert_refused(self, name, req, spec=None):
        before = copy.deepcopy(self.player.data)
        dirty = self.player.dirty
        count = len(ffbe_state.NOTES)
        out = self.call(name, req, spec)
        self.assertEqual(self.player.data, before)
        self.assertEqual(self.player.dirty, dirty)
        self.assertGreater(len(ffbe_state.NOTES), count)
        self.assertIn("refused", ffbe_state.NOTES[-1])
        return out

    def test_ids_match_endpoints(self):
        endpoints = json.loads((Path(__file__).parents[1] / "server/endpoints.json").read_text())["by_class"]
        self.assertEqual(set(actions.HANDLERS), set(REQUESTS.values()))
        for name, request_id in REQUESTS.items():
            self.assertEqual(endpoints[name]["request_id"], request_id)

    def test_entry_persists_complete_arena_models(self):
        entry = self.call("RbEntryRequest", {"LhVz6aD2": [{"9Tbns0eI": "selftest"}]})
        self.assertTrue(self.player.dirty)
        sid = entry["yT12twnc"][0]["S3rek7hC"]
        season = _mst("F_RB_SS_MST.ndjson", "6Z9DxQFf")[sid]
        self.assertEqual(entry["g4Pu8oUt"][0]["AU4qRzL9"], '0')
        self.assertEqual(entry["g4Pu8oUt"][0]["F9gxH37C"], '0')
        self.assertEqual({r["3HbFrqo5"] for r in entry["h5zN9MvP"]}, {"1", "3"})
        self.assertEqual(len(entry["g4Pu8oUt"][0]), 11)
        candidates = entry["Tr9m32i1"][0]["TI6deE8P"].split(",")
        self.assertEqual(len(candidates), len(self.catalog))
        for candidate in candidates:
            fields = candidate.split(":")
            self.assertGreaterEqual(len(fields), 10)
            self.assertGreater(int(fields[2]), 0)
            self.assertEqual(int(fields[7]), 100)
        before = copy.deepcopy(self.player.data)
        self.player.dirty = False
        self.assertEqual(self.call("RbEntryRequest"), entry)
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)

    def test_arena_battle_spends_once_resumes_and_pays_once(self):
        req = self.arena_req()
        req["N7Bd3IuL"] = [{"fP8Nv0KZ": self.fid}]
        orbs = self.player.orb_view('clsm')[0]
        matched = self.call("RbMatchingRequest", req)
        self.assertEqual(len(matched['DW0rgk3C'][0]['Jc4udh7x'].split(':')), 18)
        self.assertGreaterEqual(int(matched['DW0rgk3C'][0]['Jc4udh7x'].split(':')[10]), 1)
        self.assertEqual(self.player.orb_view('clsm')[0], orbs)
        self.call("RbStartRequest", req)
        self.assertEqual(self.player.orb_view('clsm')[0], orbs - 1)
        self.call("RbStartRequest", req)
        legacy = self.player.data['exvius_arena']['active']['rival'].split(':')
        legacy[10] = '0'
        self.player.data['exvius_arena']['active']['rival'] = ':'.join(legacy)
        restart = self.call("RbReStartRequest", req)
        self.assertEqual(restart['KMwJ3s6W'][0]['uC8E0opI'], '2')
        self.assertEqual(restart['DW0rgk3C'][0]['Jc4udh7x'].split(':')[10], '1')
        self.assertEqual(self.player.orb_view('clsm')[0], orbs - 1)
        active = self.player.data['exvius_arena']['active']
        rival = active['rival'].split(':')
        req['g3JFd0y7'] = [{
            'GA1D6XIC': ','.join(master + ':' + iid + ':1:0' for iid, master in active['own'].items()),
            'Pch7J9Ty': rival[1] + ':' + rival[0] + ':0:1',
            '3S8pMym0': '100', 'bB69ZWQY': '0', 'z8uj9TAU': '1', 'g9t7dBCH': '0'}]
        result = self.call('RbEndRequest', req)['g3JFd0y7'][0]
        self.assertEqual(result['2q7sZreS'], '1')
        self.assertEqual(result['42GLsTok'], '0,100,0,0')
        self.assertEqual(result['PDi5wos8'], '0,8')
        after = copy.deepcopy(self.player.data)
        self.assertEqual(self.call('RbEndRequest', req)['g3JFd0y7'][0], result)
        self.assertEqual(self.player.data, after)

    def test_arena_invalid_party_and_orb_selection_are_atomic(self):
        req = self.arena_req()
        req['N7Bd3IuL'] = [{'fP8Nv0KZ': self.fid}]
        self.call('RbMatchingRequest', req)
        req['yT12twnc'][0]['Q03VHyjm'] = '2'
        self.assert_refused('RbStartRequest', req)
        req['yT12twnc'][0]['Q03VHyjm'] = '0'
        self.call('RbStartRequest', req)
        req['g3JFd0y7'] = [{'GA1D6XIC': '100000102:123:1:0',
            'Pch7J9Ty': '100000102:456:0:1', 'z8uj9TAU': '1', 'g9t7dBCH': '0'}]
        self.assert_refused('RbEndRequest', req)

    def test_arena_all_orb_win_and_loss_follow_original_consumption_rules(self):
        for win in (True, False):
            with self.subTest(win=win):
                self.player.data.pop('exvius_arena', None)
                self.player.data.pop('orbs', None)
                req = self.arena_req()
                req['N7Bd3IuL'] = [{'fP8Nv0KZ': self.fid}]
                req['yT12twnc'][0]['Q03VHyjm'] = '1'
                self.call('RbMatchingRequest', req)
                before = self.player.orb_view('clsm')[0]
                self.call('RbStartRequest', req)
                self.assertEqual(self.player.orb_view('clsm')[0], 0)
                self.call('RbStartRequest', req)
                active = self.player.data['exvius_arena']['active']
                rival = active['rival'].split(':')
                req['g3JFd0y7'] = [{
                    'GA1D6XIC': ','.join(master + ':' + iid + (':1:0' if win else ':0:1')
                                        for iid, master in active['own'].items()),
                    'Pch7J9Ty': rival[1] + ':' + rival[0] + (':0:1' if win else ':1:0'),
                    'z8uj9TAU': '1', 'g9t7dBCH': '0'}]
                result = self.call('RbEndRequest', req)['g3JFd0y7'][0]
                used = before if win else 1
                self.assertEqual(self.player.orb_view('clsm')[0], before - used)
                self.assertEqual(result['42GLsTok'], '0,1000,0,0' if win else '0,10,0,0')
                self.assertEqual(result['PDi5wos8'], '0,80' if win else '0,1')
                model = self.player.data['exvius_arena']
                self.assertEqual(list(model['daily'].values()), [used])
                self.assertEqual(model['user']['5svT7qLR'], '1' if win else '0')
                after = copy.deepcopy(self.player.data)
                self.assertEqual(self.call('RbEndRequest', req)['g3JFd0y7'][0], result)
                self.assertEqual(self.player.data, after)

    def test_restart_and_rank_are_read_only(self):
        req = self.arena_req()
        before = copy.deepcopy(self.player.data)
        self.player.dirty = False
        restart = self.call("RbReStartRequest", req)
        self.assertEqual(restart["KMwJ3s6W"][0]["uC8E0opI"], "0")
        self.assertIn(UNIT_GROUP, restart)
        for term in (1, 3):
            req["e7n2P5IJ"] = [{"3HbFrqo5": str(term)}]
            rank = self.call("RbRankingRequest", req)
            self.assertEqual(rank["YQN6zx3R"][0]["CLg9j1sh"], "")
            self.assertEqual(rank["YQN6zx3R"][0]["3HbFrqo5"], str(term))
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)
        req["yT12twnc"][0]["S3rek7hC"] = "999999"
        self.assert_refused("RbReStartRequest", req)
        self.assert_refused("RbRankingRequest", req)

    def test_board_master_cost_reward_hex_and_retry(self):
        self.seed_board()
        before_roster = len(self.player.data["roster"])
        center = self.call("RbBoardPieceOpenRequest", self.board_req("1001"), self.board_spec())
        self.assertEqual(center["2pJ8F0SK"][0]["3qJw1vUG"], "8")
        self.assertEqual(len(self.player.data["roster"]), before_roster, "center reward waits for board completion")
        piece = _mst("F_RB_TRADE_BOARD_PIECE_MST.ndjson", "AyCR5h7s")["1002"]
        from exvius_arena import reward_entries
        reward = reward_entries(piece["i9w6ZCFM"])[0]
        held = self.player.item_count(reward["kind"], reward["id"])
        reply = self.call("RbBoardPieceOpenRequest", self.board_req("1002,1002"))
        self.assertIn(UNIT_GROUP, reply)
        self.assertEqual(reply["2pJ8F0SK"][0]["3qJw1vUG"], "c")
        self.assertEqual(reply["ki9hJ5vq"][0]["N9Aw4kxC"], "1000")
        self.assertEqual(self.player.item_count(reward["kind"], reward["id"]), held + reward["count"])
        self.assertEqual(reply["g4Pu8oUt"][0]["mRY52Tib"], str(100 - int(piece["mRY52Tib"])))
        before = copy.deepcopy(self.player.data)
        self.call("RbBoardPieceOpenRequest", self.board_req("1002"))
        self.assertEqual(self.player.data, before)
        projected = self.player.apply_to_reply(reply)
        self.assertIn("Md0N5abE", projected)
        self.assertIn("0dNXQa3R", projected)

    def test_board_batch_is_atomic_and_order_independent(self):
        self.seed_board()
        out = self.call("RbBoardPieceOpenRequest", self.board_req("1002,1001"), self.board_spec())
        self.assertEqual(out["2pJ8F0SK"][0]["3qJw1vUG"], "c")
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("1003,999999"))
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("2002"))
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("1003", group="2"))
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("2001", board="2000"))

    def test_board_requires_group_master_and_connectivity(self):
        self.seed_board()
        self.player.data['exvius_arena']['groups'] = []
        with patch('exvius_arena._mst', return_value={}):
            self.assert_refused("RbBoardPieceOpenRequest", self.board_req("1001"))
        self.call('RbEntryRequest')
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("1002"), self.board_spec())
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("not-ids"), self.board_spec())

    def test_board_insufficient_points_and_unknown_reward_are_atomic(self):
        self.seed_board(points=0)
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("1001,1002"), self.board_spec())
        self.player.data["exvius_arena"]["user"]["mRY52Tib"] = "1000000"
        pieces = _mst("F_RB_TRADE_BOARD_PIECE_MST.ndjson", "AyCR5h7s")
        ids = ",".join(k for k, r in pieces.items() if r["6m4Rn5jd"] == "1000")
        with patch.object(self.player, '_can_credit', return_value=False):
            self.assert_refused("RbBoardPieceOpenRequest", self.board_req(ids), self.board_spec())
        self.assertIn("inventory projection", ffbe_state.NOTES[-1])

    def test_board_completion_pays_center_once_and_advances(self):
        self.seed_board(points=1000000)
        pieces = _mst('F_RB_TRADE_BOARD_PIECE_MST.ndjson', 'AyCR5h7s')
        ids = ','.join(k for k, r in pieces.items() if r['6m4Rn5jd'] == '1000')
        before = len(self.player.data['roster'])
        center_before = sum(str(u['master_id']) == '905000103' for u in self.player.data['roster'])
        reply = self.call('RbBoardPieceOpenRequest', self.board_req(ids))
        self.assertEqual(len(self.player.data['roster']), before + 20)
        self.assertEqual(sum(str(u['master_id']) == '905000103' for u in self.player.data['roster']), center_before + 1)
        self.assertEqual(reply['ki9hJ5vq'][0]['N9Aw4kxC'], '1000,2000')
        self.assert_refused('RbBoardPieceOpenRequest', self.board_req(ids))

    def test_colosseum_lifecycle_and_untrusted_drops(self):
        req = {"wPBq3it9": [{"i5pd8xr3": "10101", "VR3DuS2M": "0", "Jnt7cCV5": "0"}]}
        self.assert_refused("ClsmStartRequest", req)
        orbs = self.player.orb_view('clsm')[0]
        lottery = self.call('ClsmLotteryRequest', req)
        self.assertTrue(lottery['p9ortU42'][0]['g35y6a4N'])
        self.assertEqual(self.player.orb_view('clsm')[0], orbs)
        self.call('ClsmStartRequest', req)
        self.call('ClsmStartRequest', req)
        self.assertEqual(self.player.orb_view('clsm')[0], orbs - 1)
        req['wPBq3it9'][0]['VR3DuS2M'] = '2'
        req['09HRWXDf'] = [{'Wdi3MAs2': '99999999', 'Sp7fF6I9': '101000100:999'}]
        inventory = copy.deepcopy(self.player.data['inventory'])
        gil = self.player.currencies['gil']
        self.call('ClsmEndRequest', req)
        self.assertEqual(self.player.data['exvius_colosseum']['rounds']['10101']['points'], 100)
        self.assertEqual(self.player.data['inventory'], inventory)
        self.assertEqual(self.player.currencies['gil'], gil)
        after = copy.deepcopy(self.player.data)
        self.call('ClsmEndRequest', req)
        self.assertEqual(self.player.data, after)
        req["wPBq3it9"][0]["i5pd8xr3"] = "9999999"
        self.assert_refused("ClsmLotteryRequest", req)

    def test_all_advanced_rounds_keep_original_names_and_sourced_stats(self):
        from exvius_colosseum import _encounters
        document = json.loads((Path(__file__).parents[1] / 'server/colosseum_encounters.json').read_text(encoding='utf8'))
        self.assertEqual(len(_encounters()), 75)
        self.assertEqual(len(document['reconstructed_rounds']), 25)
        for round_data in _encounters().values():
            for encounter in round_data['normal'] + round_data['boss']:
                self.assertEqual(encounter['background'], '100103')
                for preview in encounter['enemy_info'].split('-'):
                    graphic, order, position = preview.split(':')
                    self.assertGreater(int(graphic), 100000,
                                       'Native preview field 1 is a graphic ID, not the slot')
                    self.assertIn(int(order), range(1, 7))
                    self.assertEqual(len(position.split(',')), 2)
        self.assertEqual(_encounters()['30205']['boss'][0]['enemy_info'],
                         '3030110:1:170,300')
        self.assertEqual(document['local_monster_names']['883020504A'], 'Architeuth')
        self.assertEqual(document['local_monster_names']['883020504D'], 'Architeuth Tentacle')
        for progress in document['reconstructed_rounds']:
            round_data = _encounters()[progress]
            self.assertEqual(len(round_data['normal']), 5)
            self.assertEqual(len(round_data['boss']), 1)
            for encounter in round_data['normal'] + round_data['boss']:
                self.assertTrue(encounter['local_reconstruction'])
                self.assertTrue(encounter['bundle']['Bi6hVv34'])
                self.assertTrue(all('[Local]' not in row['G4L0YIB2']
                                    for row in encounter['bundle']['bV34YIJQ']))
        mantis = _encounters()['30101']['boss'][0]['bundle']['bV34YIJQ']
        self.assertEqual(len(mantis), 1)
        self.assertEqual(mantis[0]['G4L0YIB2'], 'Greater Mantis')
        self.assertEqual((mantis[0]['fh31sk7B'], mantis[0]['PC97pWQj'], mantis[0]['7wV3QZ80']),
                         ('31900', '70', '58'))
        self.assertEqual(mantis[0]['hn42BL3Q'], '0,0,0,50,100,50,0,0,0')
        squid = _encounters()['30205']['boss'][0]['bundle']
        self.assertEqual(len(squid['Bi6hVv34']), 1, 'Architeuth is one four-part enemy')
        self.assertEqual([row['fh31sk7B'] for row in squid['bV34YIJQ']],
                         ['61500', '42167', '42167', '42167'])
        europa = _encounters()['30505']['boss'][0]['bundle']['bV34YIJQ'][0]
        self.assertEqual((europa['fh31sk7B'], europa['PC97pWQj'], europa['7wV3QZ80']),
                         ('60100', '270', '64'))

    def test_colosseum_boss_reward_is_once_per_settlement_and_unlocks_advanced(self):
        from exvius_colosseum import _state, _masters
        model = _state()
        progress = '20505'
        source, round_master = _masters(progress)
        model['highest'] = progress
        model['unlocked'].append(progress)
        model['rounds'][progress] = {'points': int(round_master['sCd0L6Ka']), 'battles': 0,
                                    'wins': 0, 'boss_wins': 0, 'selection': None}
        self.player.data['exvius_colosseum'] = model
        req = {'wPBq3it9': [{'i5pd8xr3': progress, 'VR3DuS2M': '0', 'Jnt7cCV5': '0'}]}
        self.call('ClsmLotteryRequest', req)
        self.call('ClsmStartRequest', req)
        req['wPBq3it9'][0]['VR3DuS2M'] = '2'
        self.call('ClsmEndRequest', req)
        model = self.player.data['exvius_colosseum']
        self.assertEqual(source['ewPqs8h6'], '30101')
        self.assertEqual(model['highest'], '30101')
        self.assertIn('30101', model['unlocked'])
        self.assertEqual(model['rounds'][progress]['boss_wins'], 1)
        state = copy.deepcopy(self.player.data)
        self.call('ClsmEndRequest', req)
        self.assertEqual(self.player.data, state)

    def test_search_detail_and_suggest_are_read_only_complete_rows(self):
        before = copy.deepcopy(self.player.data)
        found = self.call("FriendSearchRequest", self.friend_req())
        row = found["2K05IxtX"][0]
        self.assertEqual(row["K3BV17gk"], "4")
        for token in ("m3Wghr1j", "9qh17ZUf", "3HriTp6B", "og2GHy49", "10fNKueF", "em5hx4FX"):
            self.assertTrue(row[token])
        self.assertEqual(self.call("FriendSearchRequest", self.friend_req("999999999"))["2K05IxtX"], [])
        detail = self.call("FriendDetailRequest", self.friend_req(K3BV17gk="1"))
        self.assertEqual(detail["2vuhy0Ex"][0]["K3BV17gk"], "1")
        self.assertEqual(self.call("FriendSuggestRequest")["f6yGgCj2"], [])
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)

    def test_favorite_delete_request_cancel_and_suggest(self):
        resources = copy.deepcopy((self.player.data["currencies"], self.player.data["inventory"]))
        reply = self.call("FriendFavoriteRequest", self.friend_req(**{"8zE6w9RP": "1"}))
        self.assertEqual(reply["2vuhy0Ex"][0]["8zE6w9RP"], "1")
        self.assertTrue(self.player.dirty)
        self.assertEqual(self.player.data["exvius_friends"]["relations"][self.fid]["favorite"], 1)
        deleted = self.call("FriendDeleteRequest", self.friend_req())
        self.assertEqual(deleted["I53AVzSo"][0]["0NVFk2fD"], self.fid)
        self.assertIn(UNIT_GROUP, deleted)
        self.assertEqual(self.player.data["counts"]["friend"], len(self.catalog) - 1)
        suggestions = self.call("FriendSuggestRequest")["f6yGgCj2"]
        self.assertEqual([r["m3Wghr1j"] for r in suggestions], [self.fid])
        self.assertEqual(suggestions[0]["K3BV17gk"], "5")
        outgoing = self.call("FriendRequest", self.friend_req())
        self.assertEqual(outgoing["2vuhy0Ex"][0]["K3BV17gk"], "2")
        self.assertEqual(self.call("FriendSuggestRequest")["f6yGgCj2"], [])
        before = copy.deepcopy(self.player.data)
        self.call("FriendRequest", self.friend_req())
        self.assertEqual(self.player.data, before)
        self.assert_refused("FriendAgreeRequest", self.friend_req())
        cancelled = self.call("FriendRefuseRequest", self.friend_req())
        self.assertEqual(cancelled["I53AVzSo"][0]["0NVFk2fD"], self.fid)
        self.assertEqual(self.player.data["exvius_friends"]["relations"][self.fid], {"type": 0, "favorite": 0})
        self.assertEqual((self.player.data["currencies"], self.player.data["inventory"]), resources)

    def test_accept_incoming_replaces_pending_without_deletion(self):
        self.seed_relation(3)
        reply = self.call("FriendAgreeRequest", self.friend_req())
        self.assertEqual(reply["2vuhy0Ex"][0]["K3BV17gk"], "1")
        self.assertEqual(reply["I53AVzSo"][0]["0NVFk2fD"], "")
        self.assertEqual(self.player.data["counts"]["friend"], len(self.catalog))
        projected = self.player.apply_to_reply(reply)
        self.assertEqual(projected["3oU9Ktb7"][0]["tsT4vP7w"], str(len(self.catalog)))
        before = copy.deepcopy(self.player.data)
        self.call("FriendAgreeRequest", self.friend_req())
        self.assertEqual(self.player.data, before)

    def test_refuse_incoming_preserves_other_relationships(self):
        self.seed_relation(3)
        self.call("FriendRefuseRequest", self.friend_req())
        self.assertEqual(self.player.data["exvius_friends"]["relations"][self.other]["type"], 1)
        self.assert_refused("FriendRefuseRequest", self.friend_req(self.other))

    def test_friend_invalid_category_self_and_capacity(self):
        self.assert_refused("FriendFavoriteRequest", self.friend_req(**{"8zE6w9RP": "2"}))
        self.assert_refused("FriendDetailRequest", self.friend_req(K3BV17gk="3"))
        self.assert_refused("FriendDeleteRequest", self.friend_req("999999999"))
        self.player.data["identity"]["user_id"] = self.fid
        self.assert_refused("FriendRequest", self.friend_req())
        self.player.data["identity"]["user_id"] = "selftest"
        self.seed_relation(3)
        relations = self.player.data["exvius_friends"]["relations"]
        relations.update({"test-" + str(n): {"type": 1, "favorite": 0}
                          for n in range(actions.AUTHORED_FRIEND_CAPACITY)})
        self.assert_refused("FriendAgreeRequest", self.friend_req())

    def test_feature_state_survives_json_roundtrip(self):
        self.seed_board()
        self.call("RbBoardPieceOpenRequest", self.board_req("1001,1002"), self.board_spec())
        self.call("FriendDeleteRequest", self.friend_req())
        self.player.data = json.loads(json.dumps(self.player.data))
        before = copy.deepcopy(self.player.data)
        self.call("RbBoardPieceOpenRequest", self.board_req("1002"))
        self.assertEqual(self.call("FriendSuggestRequest")["f6yGgCj2"][0]["m3Wghr1j"], self.fid)
        self.assertEqual(self.player.data, before)

    def test_legacy_friend_refresh_cannot_resurrect_deleted_or_pending_helpers(self):
        from ffbe_friends import serve_friends
        self.call("FriendDeleteRequest", self.friend_req())
        self.player.data = json.loads(json.dumps(self.player.data))
        legacy = serve_friends({}, REQUESTS["FriendListRequest"])
        self.assertIn(self.fid, [r["m3Wghr1j"] for r in legacy["56gJBnVh"]])
        updated = self.call("FriendListRequest", spec=legacy)
        self.assertNotIn(self.fid, [r["m3Wghr1j"] for r in updated["56gJBnVh"]])
        self.assertEqual(len(updated["56gJBnVh"]), len(self.catalog) - 1)
        self.call("FriendRequest", self.friend_req())
        updated = self.call("FriendListRequest", spec=legacy)
        self.assertEqual(updated["hZR64mDe"][0]["K3BV17gk"], "2")
        legacy_support = serve_friends({}, REQUESTS["GetReinforcementInfoRequest"])
        updated = self.call("GetReinforcementInfoRequest", spec=legacy_support)
        self.assertNotIn("9Tp2fiyB", updated)
        self.assertNotIn(self.fid, [r["m3Wghr1j"] for r in updated["pzf5se6V"]])
        self.assertIn(self.other, [r["m3Wghr1j"] for r in updated["pzf5se6V"]])

    def test_frozen_player_is_never_mutated(self):
        self.seed_board()
        self.player.mode = "frozen"
        self.assert_refused("RbBoardPieceOpenRequest", self.board_req("1001"), self.board_spec())
        self.assert_refused("FriendDeleteRequest", self.friend_req())
        self.assert_refused("FriendFavoriteRequest", self.friend_req(**{"8zE6w9RP": "1"}))
        del self.player.data["exvius_arena"]
        before = copy.deepcopy(self.player.data)
        self.call("RbEntryRequest")
        self.assertEqual(self.player.data, before)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ArenaActions))
if not result.wasSuccessful():
    raise AssertionError("arena action self-tests failed")
