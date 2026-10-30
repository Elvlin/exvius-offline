"""Mode handler regression tests, run on import for the requested isolated command.

Uses real shipped mission/cost/challenge/item masters and a throwaway in-memory
player. Supplied event, preview, ranking and candidate fixtures represent already
issued server data; their schedules/codecs are not asserted to be retail captures.
No state.save(), network, data writes or live save access.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import exvius_actions_modes as actions
from exvius_actions import UNIT_GROUP, _mst, _parse_rewards
import ffbe_state as state
import player_state

CLASSES = (
    "EquipGrowEntryRequest",
    "TfaMissionStartRequest", "TfaMissionEndRequest", "MissionRetireRequest",
    "TowerEntryRequest", "TowerStartRequest", "TowerEndRequest", "TowerRestartRequest", "TowerRetireRequest",
    "GloryEntryRequest", "GloryMissionStartRequest", "GloryMissionEndRequest", "GloryMissionReStartRequest",
    "GloryConfirmedGimmickRequest", "SurvivalMissionStartRequest", "SurvivalMissionEndRequest",
    "SurvivalMissionRestartRequest", "SurvivalMissionRetireRequest", "SurvivalMissionReturnRequest",
    "ParadeEntryRequest", "ParadeMissionEndRequest", "RmEntryRequest", "RmStartRequest", "RmEndRequest",
    "RmRestartRequest", "RmRetireRequest", "RmDungeonStartRequest", "RmDungeonEndRequest", "TfaEntryRequest",
    "TfaResultRewardFixRequest", "TfaResultRewardSelectResumeRequest", "TfaBonusRewardInfoRequest", "TfaRankingDetailRequest",
)
ENDPOINTS = json.loads((Path(actions.__file__).with_name("endpoints.json")).read_text(encoding="utf8"))["by_class"]
CALLED = set()


def mission_req(mid, **fields):
    return {"jQsE54Iz": [{"qo3PECw6": str(mid), "UgX1Es9x": "", **fields}]}


def end_req(mid, **fields):
    return {**mission_req(mid, **fields), "09HRWXDf": [{"S4U09svH": "100", "Wdi3MAs2": "50"}],
            "2urzfX6d": [{"69ieJGhD": "1:1:3", "Z1p0j9uF": "0"}], "L4i4418y": [{"6q35TL07": "0"}]}


class Modes(unittest.TestCase):
    def test_equipment_enhancement_entry_refreshes_ownership_without_spending(self):
        self.p.currencies["gil"] = 12345
        before = deepcopy(self.p.data)
        out = self.call("EquipGrowEntryRequest")
        self.groups(out, UNIT_GROUP)
        self.assertEqual(self.p.data, before)

    def setUp(self):
        self.previous = state.State.player
        self.notes = len(state.NOTES)
        self.p = player_state.PlayerState.load("/nonexistent", slot="selftest-modes")
        state.State.player = self.p

    def tearDown(self):
        state.State.player = self.previous
        del state.NOTES[self.notes:]

    def call(self, cls, req=None, spec=None):
        CALLED.add(cls)
        req = {} if req is None else req
        spec = {} if spec is None else spec
        old_req, old_spec = deepcopy(req), deepcopy(spec)
        out = actions.HANDLERS[ENDPOINTS[cls]["request_id"]](spec, req)
        self.assertIsInstance(out, dict)
        self.assertEqual(req, old_req, "handler mutated the caller's request")
        self.assertEqual(spec, old_spec, "handler mutated the shared default reply")
        json.dumps(out)
        return out

    def refused(self, cls, req=None, spec=None):
        before, dirty, notes = deepcopy(self.p.data), self.p.dirty, len(state.NOTES)
        out = self.call(cls, req, spec)
        self.assertEqual(out, spec or {})
        self.assertEqual(self.p.data, before)
        self.assertEqual(self.p.dirty, dirty)
        self.assertGreater(len(state.NOTES), notes)
        return out

    def groups(self, out, *tags):
        for tag in tags:
            self.assertIn(tag, out, state.NOTES[self.notes:])
            self.assertIsInstance(out[tag], list)
            self.assertTrue(all(isinstance(r, dict) for r in out[tag]))

    def reload_memory(self):
        # Exercise PlayerState's actual JSON normalization, including global set fields.
        data = json.loads(json.dumps(player_state._serialise(self.p.data)))
        self.p = player_state.PlayerState(player_state._normalise(data))
        state.State.player = self.p

    def tower(self):
        entry = self.call("TowerEntryRequest")
        self.groups(entry, "MAq9rRd2", "61zcgy04", "56TsktBX")
        self.assertEqual(len(entry["56TsktBX"]), len(self.p.data["party"]["decks"]))
        return entry["61zcgy04"][0]["qo3PECw6"]

    def rm_snapshot(self, hp="opaque|hp|mp|lb|status,detached"):
        return {"jSC4Tx9H": [{"9Tbns0eI": self.p.data["identity"]["user_id"], "r21y0YzS": "0",
            "h0XJ2nPj": hp, "1w6Ju7Ie": "esper:actual", "Y58ENcB4": "2", "0VBhN1UC": "",
            "Zh73m5Nq": "", "Y3oqiA8S": "", "PH7Hg4Zh": "skill:remaining"}]}

    def tfa(self, replacement=False):
        # Candidate quantities come from real reward definitions, supplied as an issued batch.
        definitions = _mst("F_CHALLENGE_MST.ndjson", None)["__rows__"]
        tuples = [r["dX6cor8j"] for r in definitions if str(r.get("dX6cor8j", "")).startswith("50:")
                  and str(r["dX6cor8j"]).count(":") == 2 and "," not in r["dX6cor8j"]]
        new = tuples[0] + "-0"
        old = next(t for t in tuples if t != tuples[0]) + "-0"
        did = str(actions._missions("tfa")[0]["U9iHsau3"])
        spec = {"L6XRZb0z": [{"U9iHsau3": did, "pvS5A4kE": "7100000", "enkCGfPT": "fixture-issued-scale-rows"}],
                "x51bb135": [{"dc10ae96": "1", "cEVau7d8": "1"}],
                "Fs0sexp7": [{"mXQWZ5Ql": old if replacement else "", "IX1hKI6g": "1", "bcd49985": "0:7100000:1"}],
                "AJb8pF71": [{"9Tbns0eI": self.p.data["identity"]["user_id"], "UTRQvH1q": "1"}]}
        out = self.call("TfaEntryRequest", {"9Zok3IK2": [{"U9iHsau3": did}]}, spec)
        self.groups(out, "L6XRZb0z", "Fs0sexp7", "x51bb135", "AJb8pF71")
        self.p.data["exvius_tfa"]["candidates"] = new
        return did, new, old

    def test_tower_lifecycle_and_retries(self):
        mid = self.tower()
        count = len(self.p.data["roster"])
        self.p.data["rank"].update(level=51, nrg=100)
        cost = int(actions._mission("tower", mid)["B6kyCQ9M"])
        start = self.call("TowerStartRequest", mission_req(mid))
        self.groups(start, "61zcgy04", "1Ke2wFgm", "jQsE54Iz", UNIT_GROUP)
        self.assertEqual(self.p.data["rank"]["nrg"], 100 - cost)
        self.assertTrue(self.p.dirty)
        before = deepcopy(self.p.data)
        self.assertEqual(self.call("TowerStartRequest", mission_req(mid)), start)
        self.assertEqual(self.p.data, before)
        self.reload_memory()
        resume = self.call("TowerRestartRequest", mission_req(mid, **{"7vh6LXEw": "2"}))
        self.assertEqual(resume["jQsE54Iz"], start["jQsE54Iz"])
        self.assertEqual(self.p.data["rank"]["nrg"], 100 - cost)
        end = self.call("TowerEndRequest", end_req(mid))
        self.groups(end, "09HRWXDf", "61zcgy04", "56TsktBX", UNIT_GROUP)
        self.assertEqual(end["61zcgy04"][0]["5rMfWv4X"], "1")
        self.assertNotEqual(end["61zcgy04"][0]["qo3PECw6"], mid)
        self.assertEqual(len(self.p.data["roster"]), count)
        self.assertEqual(self.p.data["currencies"]["gil"], 50)
        before = deepcopy(self.p.data)
        self.assertEqual(self.call("TowerEndRequest", end_req(mid)), end)
        self.assertEqual(self.p.data, before)
        mid2 = end["61zcgy04"][0]["qo3PECw6"]
        self.call("TowerStartRequest", mission_req(mid2))
        self.call("TowerRetireRequest", mission_req(mid2, xDVge02X="0"))
        self.assertIsNone(self.p.data["exvius_tower"]["active"])
        self.assertNotIn(mid2, self.p.data["progress"]["cleared_missions"])

    def test_tower_guards_and_full_lists(self):
        mid = self.tower()
        self.p.data["rank"].update(level=51, nrg=0)
        self.refused("TowerStartRequest", mission_req(mid))
        self.refused("TowerStartRequest", mission_req("10060201"))
        self.refused("TowerRestartRequest", mission_req(mid))
        self.p.data["rank"]["nrg"] = 100
        self.refused("TowerStartRequest", mission_req(mid, **{"5qjK76ni": "1:50"}))
        self.call("TowerStartRequest", mission_req(mid))
        self.refused("TowerEndRequest", mission_req(mid))
        self.refused("TowerEndRequest", end_req(mid, dIPkNn61="99999999999999"))
        self.p.mode = "frozen"
        self.refused("TowerRetireRequest", mission_req(mid))

    def test_tower_retains_authoritative_progress(self):
        rows = actions._missions("tower")
        row = rows[3]
        decks = [{"r21y0YzS": "8", "G4L0YIB2": "Saved tower party", "2A6fYiEC": ""}]
        spec = {"61zcgy04": [{"uv60hgDW": row["uv60hgDW"], "U9iHsau3": row["U9iHsau3"],
                "qo3PECw6": row["qo3PECw6"], "5rMfWv4X": "3"}], "56TsktBX": decks}
        out = self.call("TowerEntryRequest", spec=spec)
        self.assertEqual(out["61zcgy04"], spec["61zcgy04"])
        self.assertEqual(out["56TsktBX"], decks)

    def test_glory_key_gimmicks_and_restart(self):
        row = actions._missions("glory")[0]
        entry = self.call("GloryEntryRequest", {"V3oXMq9f": [{"uv60hgDW": row["uv60hgDW"]}]})
        self.groups(entry, "auE57zyr", "dekE2X8K", "4FhDP05Q", "C9g3yKDL")
        event = entry["dekE2X8K"][0]["pvS5A4kE"]
        group = _mst("F_SEASON_EVENT_GLORY_MST.ndjson", "pvS5A4kE")[event]["Z20PuxDY"]
        masters = _mst("F_GLORY_GIMMICK_MST.ndjson", "M3JE6vnF")
        bonus = next(r["M3JE6vnF"] for r in _mst("F_GLORY_GIMMICK_GROUP_MST.ndjson", None)["__rows__"]
                     if r["Z20PuxDY"] == group and masters[r["M3JE6vnF"]]["4Ny9ztLJ"] == "2")
        # A server-side unlocked fixture; never unlock from a client assertion.
        user = self.p.data["exvius_glory"]["groups"]["dekE2X8K"][0]
        user["D2gU5tET"] = ",".join(dict.fromkeys(user["D2gU5tET"].split(",") + [bonus]))
        user["Vm07pZ2A"] = bonus
        req = {**mission_req(row["qo3PECw6"]), "9zULH4p1": [{"pvS5A4kE": event, "51xkq83U": bonus, "U92bySoZ": True}]}
        self.refused("GloryMissionStartRequest", req)
        self.p.grant_item(20, actions.GLORY_MAGIC_KEY, 1)
        self.p.data["rank"].update(level=51, nrg=0)
        self.refused("GloryMissionStartRequest", req)
        self.assertEqual(self.p.item_count(20, actions.GLORY_MAGIC_KEY), 1, "cost failure must roll back the key debit")
        self.p.data["rank"]["nrg"] = 100
        out = self.call("GloryMissionStartRequest", req)
        self.groups(out, "1Ke2wFgm", "aGPc06ym", "dekE2X8K", "jQsE54Iz", UNIT_GROUP)
        self.assertEqual(self.p.item_count(20, actions.GLORY_MAGIC_KEY), 0)
        again = self.call("GloryMissionStartRequest", req)
        self.assertEqual(again, out)
        self.reload_memory()
        resumed = self.call("GloryMissionReStartRequest", mission_req(row["qo3PECw6"]))
        self.assertEqual(resumed["aGPc06ym"], out["aGPc06ym"])
        self.assertEqual(resumed["jQsE54Iz"], out["jQsE54Iz"])
        self.call("GloryConfirmedGimmickRequest", {"9zULH4p1": [{"pvS5A4kE": event, "51xkq83U": bonus}]})
        f = self.p.data["exvius_glory"]
        self.assertIn(bonus, f["confirmed"])
        self.assertEqual(f["groups"]["dekE2X8K"][0]["Vm07pZ2A"], "")
        out = self.call("GloryMissionEndRequest", end_req(row["qo3PECw6"]))
        self.groups(out, "09HRWXDf", "ZDxy76LN", "dekE2X8K", "4FhDP05Q", "C9g3yKDL", "1Ke2wFgm", UNIT_GROUP)
        self.assertEqual(out["ZDxy76LN"][0]["J0tnsW5m"], "0")
        before = deepcopy(self.p.data)
        self.call("GloryMissionEndRequest", end_req(row["qo3PECw6"]))
        self.assertEqual(self.p.data, before)

    def test_survival_party_consumption_rewards_and_return(self):
        mid = "10060201"
        rewards = [r for r in _mst("F_CHALLENGE_MST.ndjson", None)["__rows__"] if r["qo3PECw6"] == mid and r["Pzn5h0Ga"] == "68"]
        reward = _parse_rewards(rewards[0]["dX6cor8j"])[0]
        item = actions.GLORY_MAGIC_KEY
        self.p.grant_item(20, item, 5)
        self.p.data["inventory"]["carry_items"] = [{"disp_order": 3, "item_id": int(item), "count": 3}]
        self.p.data["rank"].update(level=51, nrg=0)
        from ffbe_friends import load_friends
        friend = load_friends()[0]
        req = mission_req(mid, dUX7Pt5i=str(friend["friend_id"]), qLke7K8f=str(friend["unit"]["master_id"]), **{"0XUs3Tv6": "999999"})
        out = self.call("SurvivalMissionStartRequest", req)
        self.groups(out, "1Ke2wFgm", "65cMLkuQ", "2w9Iyeaq", "jQsE54Iz", UNIT_GROUP)
        self.assertEqual(self.p.data["rank"]["nrg"], 0)
        self.assertEqual(self.p.data["currencies"]["friend_point"], actions.AUTHORED_HELPER_POINTS)
        self.call("SurvivalMissionStartRequest", req)
        self.assertEqual(self.p.data["currencies"]["friend_point"], actions.AUTHORED_HELPER_POINTS)
        self.call("SurvivalMissionRestartRequest", mission_req(mid))
        packed = "1@100@0|400|50|30|1,2|3,4|5,6|7,8|9,10"
        req = {**end_req(mid), "nE7pV2wr": [{"jsvoa0I2": f"3:{item}:1"}], "2w9Iyeaq": [{"3KJpzuC5": packed}]}
        out = self.call("SurvivalMissionEndRequest", req)
        self.groups(out, "09HRWXDf", "65cMLkuQ", "2w9Iyeaq", "1Ke2wFgm", UNIT_GROUP, "nE7pV2wr")
        self.assertEqual(out["2w9Iyeaq"][0]["3KJpzuC5"], packed)
        self.assertEqual(self.p.item_count(20, item), 3)
        self.assertGreaterEqual(self.p.item_count(reward["kind"], reward["id"]), reward["count"])
        before = deepcopy(self.p.data)
        self.call("SurvivalMissionEndRequest", req)
        self.assertEqual(self.p.data, before)
        balances = deepcopy(self.p.data["inventory"])
        self.reload_memory()
        returned = self.call("SurvivalMissionReturnRequest", {"V3oXMq9f": [{"uv60hgDW": "1006"}]})
        self.assertEqual(returned["2w9Iyeaq"], [{"3KJpzuC5": "1@0"}])
        self.assertEqual(self.p.data["inventory"], balances)
        self.call("SurvivalMissionStartRequest", mission_req(mid))
        self.call("SurvivalMissionRetireRequest", mission_req(mid, xDVge02X="0"))
        self.assertIsNone(self.p.data["exvius_survival"]["active"])

    def test_survival_refusals_are_atomic(self):
        mid = "10060201"
        self.refused("SurvivalMissionStartRequest", mission_req(mid, dUX7Pt5i="123", qLke7K8f="100000102"))
        self.call("SurvivalMissionStartRequest", mission_req(mid))
        self.refused("SurvivalMissionReturnRequest", {"V3oXMq9f": [{"uv60hgDW": "1006"}]})
        req = {**end_req(mid), "2w9Iyeaq": [{"3KJpzuC5": "1@0@bad"}]}
        self.refused("SurvivalMissionEndRequest", req)
        self.assertEqual(self.p.item_count(20, 106213260), 0)
        req = {**end_req(mid), "nE7pV2wr": [{"jsvoa0I2": "0:106100100:100"}]}
        self.refused("SurvivalMissionEndRequest", req)

    def test_rm_dungeon_lifecycle_and_opaque_snapshots(self):
        snap = self.rm_snapshot()
        entry = self.call("RmEntryRequest", snap)
        self.groups(entry, *actions.TAGS["rm"])
        rows = actions._missions("rm", "92001")
        req = {**snap, "9Zok3IK2": [{"U9iHsau3": "92001", "dUX7Pt5i": "", "w40YsHIz": "", "xojJ2w0S": "0", "Y58ENcB4": "1"}]}
        entered = self.call("RmDungeonStartRequest", req)
        self.assertEqual(entered['Wmr7y9a0'][0]['qo3PECw6'], '0')
        start = None
        for index, row in enumerate(rows):
            mid = row["qo3PECw6"]
            start_req = {**mission_req(mid, **{"7vh6LXEw": "0", "b6PwoB37": "123"}), **snap}
            out = self.call("RmStartRequest", start_req)
            self.groups(out, "Wmr7y9a0", "Ur6CKS2e", "jSC4Tx9H", "jQsE54Iz", UNIT_GROUP)
            self.assertEqual(out["jQsE54Iz"][0]["b6PwoB37"].split(",")[0], "123")
            self.assertNotIn("Y58ENcB4", out["jSC4Tx9H"][0])
            if index == 0:
                start = out
                self.call("RmStartRequest", start_req)
                self.reload_memory()
                restart = self.call("RmRestartRequest", mission_req(mid, **{"7vh6LXEw": "0"}))
                self.assertEqual(restart["jQsE54Iz"], start["jQsE54Iz"])
                # Reopening Entry cannot replace an existing run's actual snapshot.
                reopened = self.call("RmEntryRequest", self.rm_snapshot("stale upload"))
                self.assertEqual(reopened["jSC4Tx9H"][0]["h0XJ2nPj"], snap["jSC4Tx9H"][0]["h0XJ2nPj"])
            end = {**end_req(mid), **self.rm_snapshot("final|hp|mp|status")}
            settled = self.call("RmEndRequest", end)
            self.assertEqual(settled['Wmr7y9a0'][0]['qo3PECw6'], mid)
            before = deepcopy(self.p.data)
            self.call("RmEndRequest", end)
            self.assertEqual(self.p.data, before)
        final = {**req, **self.rm_snapshot("final dungeon snapshot"), "09HRWXDf": [{"nZ1gR2h3": "party params"}]}
        out = self.call("RmDungeonEndRequest", final)
        self.groups(out, "Wmr7y9a0", "Ur6CKS2e", "jSC4Tx9H", "09HRWXDf")
        self.assertFalse(self.p.data["exvius_rm"]["run"])
        before = deepcopy(self.p.data)
        self.call("RmDungeonEndRequest", final)
        self.assertEqual(self.p.data, before)
        self.call("RmDungeonStartRequest", req)
        self.call("RmStartRequest", {**mission_req(rows[0]["qo3PECw6"]), **snap})
        self.call("RmRetireRequest", {**mission_req(rows[0]["qo3PECw6"]), **snap})
        self.assertFalse(self.p.data["exvius_rm"]["run"])

    def test_rm_map_give_up_uses_native_zero_mission_and_retries_once(self):
        snap = self.rm_snapshot()
        req = {**snap, '9Zok3IK2': [{'U9iHsau3': '92001'}]}
        self.call('RmEntryRequest', snap)
        self.call('RmDungeonStartRequest', req)
        withdrawal = {**mission_req('0'), **snap, 'nE7pV2wr': [{'jsvoa0I2': ''}]}
        out = self.call('RmRetireRequest', withdrawal)
        self.assertEqual(out['Wmr7y9a0'][0]['U9iHsau3'], '0')
        self.assertEqual(out['Wmr7y9a0'][0]['qo3PECw6'], '0')
        self.assertFalse(self.p.data['exvius_rm']['run'])
        saved = deepcopy(self.p.data)
        self.call('RmRetireRequest', withdrawal)
        self.assertEqual(self.p.data, saved)

    def test_rm_cost_is_charged_only_on_mission_start(self):
        self.p.data['rank'].update(level=51, nrg=1000)
        req = {**self.rm_snapshot(), '9Zok3IK2': [{'U9iHsau3': '92001'}]}
        self.call('RmDungeonStartRequest', req)
        self.assertEqual(self.p.data['rank']['nrg'], 1000)
        self.call('RmStartRequest', mission_req('9200101'))
        cost = actions._cost(actions._mission('rm', '9200101'), {})
        self.assertEqual(self.p.data['rank']['nrg'], 1000 - cost)
        before = deepcopy(self.p.data)
        self.call('RmStartRequest', mission_req('9200101'))
        self.assertEqual(self.p.data, before)

    def test_parade_supplied_state_and_missing_schedule(self):
        self.refused("ParadeEntryRequest", {"V3oXMq9f": [{"uv60hgDW": "99999999"}]})
        # The normal MissionStart producer owns Parade's active session. No such start
        # endpoint is requested here; supply its already-validated session as a fixture.
        mid = "9200101"
        self.call("ParadeEntryRequest", {"V3oXMq9f": [{"uv60hgDW": "920"}]})
        self.p.data["exvius_parade"]["active"] = {"mission": mid, "sequence": 1, "carry": [], "operation": {}, "helper": ""}
        out = self.call("ParadeMissionEndRequest", {**end_req(mid), "9uzBbMgf": [{"xWGcqc5w": "0", "UerDbZzt": "history"}]})
        self.groups(out, "09HRWXDf", "yA8Nn9vK", "HMa5VTU8", "94IYZAbg", "1Ke2wFgm", UNIT_GROUP)
        self.assertGreater(int(out["yA8Nn9vK"][0]["UbQ26oH4"]), 10000)
        self.assertEqual(self.p.data['exvius_parade']['party_history']['UerDbZzt'], 'history')
        before = deepcopy(self.p.data)
        self.call("ParadeMissionEndRequest", end_req(mid))
        self.assertEqual(self.p.data, before)

    def test_tfa_select_resume_finalize_once(self):
        did, new, old = self.tfa(replacement=True)
        resumed = self.call("TfaResultRewardSelectResumeRequest")
        self.groups(resumed, "u9jY6hQJ", "Fs0sexp7", "x51bb135")
        self.assertEqual(resumed["u9jY6hQJ"][0]["UJz5QED2"], new)
        old_tuple = old.split("-")[0]
        choice = new + "," + old_tuple + ":0-0"
        req = {"e262323b": [{"U9iHsau3": did, "z4EhuqEN": choice}]}
        before_currency = deepcopy(self.p.data["currencies"])
        out = self.call("TfaResultRewardFixRequest", req)
        self.assertEqual(out["Fs0sexp7"][0]["mXQWZ5Ql"], new)
        self.assertEqual(self.p.data["currencies"], before_currency, "replacement is provisional, not a bag debit/grant")
        self.call("TfaResultRewardFixRequest", req)
        self.reload_memory()
        done = {"e262323b": [{"U9iHsau3": did, "z4EhuqEN": ""}]}
        out = self.call("TfaResultRewardFixRequest", done)
        self.groups(out, "Fs0sexp7", "x51bb135", UNIT_GROUP)
        self.assertEqual(out["x51bb135"], [{"dc10ae96": "0", "cEVau7d8": "0"}])
        amount = int(new.split("-")[0].split(":")[2])
        self.assertEqual(self.p.data["currencies"]["lapis_free"], amount)
        before = deepcopy(self.p.data)
        self.call("TfaResultRewardFixRequest", done)
        self.assertEqual(self.p.data, before)
        self.refused("TfaResultRewardSelectResumeRequest")

    def test_tfa_refuses_forged_candidates_and_slots(self):
        self.refused("TfaEntryRequest", {"9Zok3IK2": [{"U9iHsau3": "99999999"}]})
        did, new, old = self.tfa(replacement=True)
        for choice in ("50:1:999999999-0", new + "," + old.split("-")[0] + ":9-0", new):
            self.refused("TfaResultRewardFixRequest", {"e262323b": [{"U9iHsau3": did, "z4EhuqEN": choice}]})
        self.p.data["exvius_tfa"]["candidates"] = ""
        self.refused("TfaResultRewardSelectResumeRequest")
        self.refused("TfaResultRewardFixRequest", {"e262323b": [{"U9iHsau3": did, "z4EhuqEN": new}]})

    def test_tfa_empty_finish_does_not_pick_a_candidate(self):
        did, new, _ = self.tfa()
        self.call("TfaResultRewardFixRequest", {"e262323b": [{"U9iHsau3": did, "z4EhuqEN": ""}]})
        self.assertEqual(self.p.data["currencies"]["lapis_free"], 0)
        self.assertEqual(self.p.data["exvius_tfa"]["slots"], "")

    def test_tfa_finalization_validates_capacity_and_rolls_back_partial_grants(self):
        did, new, _ = self.tfa()
        f = self.p.data["exvius_tfa"]
        done = {"e262323b": [{"U9iHsau3": did, "z4EhuqEN": ""}]}
        f["slots"] = new + "," + new
        self.refused("TfaResultRewardFixRequest", done)
        f = self.p.data["exvius_tfa"]
        f["pass"] = "0:7100000:2"
        f["slots"] = new + ",22:99999999:1-0"  # Unsupported projection must roll back earlier lapis.
        self.refused("TfaResultRewardFixRequest", done)
        self.assertEqual(self.p.data["currencies"]["lapis_free"], 0)

    def test_tfa_preview_and_offline_friend_detail_are_read_only(self):
        did, _, _ = self.tfa()
        req = {"b62c2649": [{"Nmcx68HU": "2", "U9iHsau3": did, "7dkQA0K4": "1", "F9gxH37C": "1000", "rSpOEfsX": "1000"}]}
        self.groups(self.call("TfaBonusRewardInfoRequest", req), "hK7NyNhP")
        preview = [{"Nmcx68HU": "2", "k5Oa5kC0": "-1", "mXQWZ5Ql": "1@20:106100100:1000:1:1"}]
        self.p.data["exvius_tfa"]["bonus_previews"] = {f"2|{did}|1|1000|1000": preview}
        from ffbe_friends import load_friends
        uid = str(load_friends()[0]["friend_id"])
        detail = [{"UbQ26oH4": "0", "cH15BhQ0": "0", "7dkQA0K4": "1"}]
        self.p.data["exvius_tfa"]["ranking_details"] = {did: {uid: detail}}
        before = deepcopy(self.p.data)
        self.assertEqual(self.call("TfaBonusRewardInfoRequest", req)["hK7NyNhP"], preview)
        out = self.call("TfaRankingDetailRequest", {"C0SFBLx4": [{"m3Wghr1j": uid, "U9iHsau3": did}]})
        self.assertEqual(out["LsaiWo2f"], detail)
        self.assertEqual(self.p.data, before)
        self.refused("TfaRankingDetailRequest", {"C0SFBLx4": [{"m3Wghr1j": "99999999999", "U9iHsau3": did}]})

    def test_tfa_native_start_clear_draw_collect_and_retire(self):
        row = actions._missions('tfa')[0]
        mid, did = row['qo3PECw6'], row['U9iHsau3']
        self.call('TfaEntryRequest', {'9Zok3IK2': [{'U9iHsau3': did}]})
        req = {**mission_req(mid), 'WaBIK8pI': [{'U9iHsau3': did, 'UTRQvH1q': '1', 'i1kVPwjL': ''}]}
        start = self.call('TfaMissionStartRequest', req)
        self.groups(start, 'jQsE54Iz', '1Ke2wFgm')
        before = deepcopy(self.p.data)
        self.call('TfaMissionStartRequest', req)
        self.assertEqual(self.p.data, before)
        end = self.call('TfaMissionEndRequest', end_req(mid))
        self.groups(end, '09HRWXDf', 'u9jY6hQJ', 'AJb8pF71', 'XHnyfiwg')
        self.assertEqual(self.p.data['exvius_repeat']['attempt']['status'], 'completed')
        self.assertEqual(self.p.data['exvius_tfa']['groups']['L6XRZb0z'][0]['RdD05iaE'], '1')
        candidate = end['u9jY6hQJ'][0]['UJz5QED2'].split(',')[0]
        self.reload_memory()
        pick = {'e262323b': [{'U9iHsau3': did, 'z4EhuqEN': candidate}]}
        self.call('TfaResultRewardFixRequest', pick)
        claim = {'e262323b': [{'U9iHsau3': did, 'z4EhuqEN': ''}]}
        self.call('TfaResultRewardFixRequest', claim)
        before = deepcopy(self.p.data)
        self.call('TfaResultRewardFixRequest', claim)
        self.assertEqual(self.p.data, before)
        self.call('TfaMissionStartRequest', req)
        self.call('MissionRetireRequest', mission_req(mid))
        self.assertIsNone(self.p.data['exvius_tfa']['active'])
        self.assertEqual(self.p.data['exvius_repeat']['attempt']['status'], 'retired')
        # The older ordinary-trial use of these endpoints stays supported.
        original = {'preserve': [{'normal': 'yes'}]}
        self.assertEqual(self.call('TfaMissionStartRequest', mission_req('1110101'), original), original)
        self.assertEqual(self.call('TfaMissionEndRequest', end_req('1110101'), original), original)

    def test_z_all_29_endpoint_ids_and_handlers_covered(self):
        self.assertEqual(set(actions.HANDLERS), {ENDPOINTS[c]["request_id"] for c in CLASSES})
        self.assertEqual(CALLED, set(CLASSES))


if __name__ in ("__main__", "test_actions_modes"):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Modes))
    if not result.wasSuccessful():
        raise AssertionError("mode handler tests failed")
