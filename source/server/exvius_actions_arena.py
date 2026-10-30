"""Offline arena, board and friend actions, from the v9 reverse-engineering report.

AUTHORED / UNRESOLVED
* Replay the most recent shipped short season indefinitely. The offline long season
  mirrors it; state 1 and ranking display selector 0 are authored presentation policy.
* Candidate ratio 1.00 is authored neutral matchmaking, encoded in hundredths.
* Arena battles use exvius_arena, with native rival serialization, orb accounting,
  result settlement, participation rewards and resumable local opponents.
* Colosseum uses preserved encounters and labelled, user-approved Advanced
  reconstructions with original round rewards. Missing data cannot spend an orb.
* The seven original medal boards cycle in master order. Their center reward is
  paid on completion, once per cycle. Original level-1 unit reward descriptors
  and item triples are credited through the authoritative inventory projection.
* YAML friends initially count as accepted, matching ffbe_friends. Offline peers
  are represented by local relationships, with no remote user/save to modify.
  Capacity 100 is authored; pending requests never auto-accept. Removed friends
  become suggestion candidates. Favorite is local to this player.

Two supporting read handlers project the stored relationships on FriendList and
reinforcement replies, after the legacy ffbe_friends step. Otherwise that step
would resurrect deleted YAML friends. No remote account or save is accessed.
Refusals use ffbe_state._note; they are not fabricated successful battle results.
"""
from __future__ import annotations

import copy
import time

from exvius_actions import _node, _refresh, _mst
from ffbe_friends import load_friends, _friend_list_row, _reinforce_row, _vc_info_row, VCINFO_TAG
from ffbe_state import State, _note

AUTHORED_FRIEND_CAPACITY = 100
AUTHORED_RB_SEASON_STATE = 1
AUTHORED_RB_RANK_SELECTOR = 0
AUTHORED_RB_CANDIDATE_RATE = 100
OFFLINE_ARENA_WINDOW = ('2026-01-01 00:00:00', '2099-12-31 23:59:59')
AUTHORED_DEFER_CENTER_UNTIL_COMPLETE = True


def _int(value, default=None):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _out(spec):
    return dict(spec) if isinstance(spec, dict) else {}


def _refuse(spec, reason):
    _note("arena/social: refused: " + reason)
    return _out(spec)


def _writable():
    return State.player is not None and State.player.mode != "frozen"


def _arena():
    """A detached view: failed actions and frozen reads cannot dirty the player."""
    saved = State.player.data.get("exvius_arena")
    if saved is not None:
        return copy.deepcopy(saved)
    seasons = _mst("F_RB_SS_MST.ndjson", "6Z9DxQFf")
    rows = [r for k, r in seasons.items() if _int(k, 0) > 0]
    latest = max(rows, key=lambda r: (r.get("VjJQ51uG", ""), _int(r["6Z9DxQFf"]))) if rows else {}
    return {"season_id": str(latest.get("6Z9DxQFf", "0")),
            "user": {k: "0" for k in ("UbQ26oH4", "mRY52Tib", "5svT7qLR", "egayI1s4",
                                       "p6H4CNw8", "Ka0Pbz5N", "qH5h4GX2", "52ibRBqw")},
            "boards": {}, "complete": {}, "groups": []}


def _save_arena(arena):
    if State.player.data.get("exvius_arena") != arena:
        State.player.data["exvius_arena"] = arena
        State.player.dirty = True


def _arena_rows(arena):
    sid = arena["season_id"]
    season = _mst("F_RB_SS_MST.ndjson", "6Z9DxQFf").get(sid)
    if not season:
        return None
    from exvius_arena import _party, _unit_bonus
    bonus = (arena.get('active') or {}).get('bonus')
    if bonus is None:
        bonus = _unit_bonus(arena, _party())
    user = dict(arena["user"])
    # UserRbInfo contains resolved percentages. The season's unit-group IDs
    # are master rules, and RbStartScene would display their first ID as 999%.
    user.update({"8TStpEr4": "", "AU4qRzL9": "0", "F9gxH37C": str(bonus)})
    states = [{"S3rek7hC": sid, "m9A4tK2r": str(AUTHORED_RB_SEASON_STATE),
               "3HbFrqo5": str(term), "BGFw7qi4": OFFLINE_ARENA_WINDOW[0],
               "2oL4dNFy": OFFLINE_ARENA_WINDOW[1], "0dh7yRIN": "",
               "4yT7FUqj": "", "td06MKEX": "0"} for term in (1, 3)]
    return {"yT12twnc": [{"S3rek7hC": sid, "o8RDmSI9": sid, "Q03VHyjm": "0"}],
            "h5zN9MvP": states, "g4Pu8oUt": [user]}


def rb_entry(spec, req):
    from exvius_arena import _model
    arena = _model()
    rows = _arena_rows(arena)
    if rows is None:
        return _refuse(spec, "no shipped arena season")
    if _writable():
        _save_arena(arena)
    candidates = []
    for friend in load_friends():
        # Delimiters in a YAML display name must not create extra packed columns.
        name = friend["display_name"].replace(":", " ").replace(",", " ")
        candidates.append(":".join(map(str, (friend["friend_id"], name,
            friend["unit"]["master_id"], friend["unit"]["level"], 0, 0,
            friend["rank"], AUTHORED_RB_CANDIDATE_RATE, friend["emblem_id"], 0, 0))))
    out = _out(spec)
    out.update(rows)
    out["Tr9m32i1"] = [{"TI6deE8P": ",".join(candidates)}]
    from exvius_arena import _versus
    out.update(_versus(arena, 2 if arena.get('active') else 0))
    out['H54XvPis'] = copy.deepcopy(arena['groups'])
    out['IqkX0gV1'] = State.player._equip_rows()
    pieces = _mst('F_RB_TRADE_BOARD_PIECE_MST.ndjson', 'AyCR5h7s')
    projected = _board_reply({}, arena, pieces)
    for tag in ('2pJ8F0SK', 'ki9hJ5vq'):
        out[tag] = projected[tag]
    return out


def _valid_season(req, arena):
    node = _node(req, "yT12twnc") or {}
    return all(str(node.get(k)) == arena["season_id"] for k in ("S3rek7hC", "o8RDmSI9"))


def rb_matching(spec, req):
    from exvius_arena import matching
    return matching(spec, req)


def rb_start(spec, req):
    from exvius_arena import start
    return start(spec, req)


def rb_end(spec, req):
    from exvius_arena import end
    return end(spec, req)


def rb_restart(spec, req):
    from exvius_arena import restart
    return restart(spec, req)


def rb_ranking(spec, req):
    arena = _arena()
    term = _int((_node(req, "e7n2P5IJ") or {}).get("3HbFrqo5"))
    if not _valid_season(req, arena) or term not in (1, 3):
        return _refuse(spec, "unknown ranking season or term")
    rows = _arena_rows(arena)
    if rows is None:
        return _refuse(spec, "no shipped arena season")
    out = _out(spec)
    out.update(rows)
    out["YQN6zx3R"] = [{"3HbFrqo5": str(term), "8s9wNSpd": str(AUTHORED_RB_RANK_SELECTOR),
                          "CLg9j1sh": ""}]
    return out


def _csv_ids(value):
    parts = str(value or "").split(",")
    return parts if all(p.isdigit() and int(p) > 0 for p in parts) else None


def _board_reply(spec, arena, pieces):
    out = _refresh(spec)
    out["g4Pu8oUt"] = _arena_rows(arena)["g4Pu8oUt"]
    out["H54XvPis"] = copy.deepcopy(arena["groups"])
    out["2pJ8F0SK"] = []
    for key, opened in arena["boards"].items():
        group, board = key.split(":")
        indexes = [int(pieces[p]["pgS67dFz"]) for p in opened]
        mask = [0] * (max(indexes, default=0) // 4 + 1)
        for index in indexes:
            mask[index // 4] |= 1 << (3 - index % 4)
        out["2pJ8F0SK"].append({"CIE1rky2": group, "6m4Rn5jd": board,
                                "3qJw1vUG": "".join(format(n, "x") for n in mask)})
    out["ki9hJ5vq"] = [{"CIE1rky2": str(g["CIE1rky2"]),
        "N9Aw4kxC": ','.join(arena.get('board_paths', {}).get(str(g['CIE1rky2']),
                            [str(g["35iR6h0V"]).split(",")[0]])), "KA68CYFo": "0"}
        for g in arena["groups"]]
    return out


def rb_board_open(spec, req):
    node = _node(req, "7GUQtmb3") or {}
    group, board = str(node.get("CIE1rky2", "")), str(node.get("6m4Rn5jd", ""))
    ids = _csv_ids(node.get("mvc31xSV"))
    from exvius_arena import _model, reward_entries
    arena = _model()
    boards = _mst("F_RB_TRADE_BOARD_MST.ndjson", "6m4Rn5jd")
    pieces = _mst("F_RB_TRADE_BOARD_PIECE_MST.ndjson", "AyCR5h7s")
    # Membership comes from the saved offline season, never the client request.
    groups = arena['groups']
    valid_groups = isinstance(groups, list) and all(isinstance(g, dict) and
        _csv_ids(g.get("35iR6h0V")) and str(g.get("CIE1rky2", "")).isdigit() for g in groups)
    membership = next((g for g in groups if str(g["CIE1rky2"]) == group), None) if valid_groups else None
    if not ids or board not in boards or not membership or board not in _csv_ids(membership["35iR6h0V"]):
        return _refuse(spec, "invalid board/piece IDs or unresolved server-fed board-group membership")
    sequence = _csv_ids(membership["35iR6h0V"])
    paths = arena.setdefault('board_paths', {})
    path = paths.setdefault(group, [sequence[0]])
    if board != path[-1]:
        return _refuse(spec, "board is not the current board in this reward cycle")
    own = {k: r for k, r in pieces.items() if str(r.get("6m4Rn5jd")) == board}
    if any(p not in own for p in ids):
        return _refuse(spec, "piece is not on the requested board")
    key = group + ":" + board
    opened = set(arena["boards"].get(key, []))
    pending = set(ids) - opened
    reachable = set(opened)
    centers = {p for p, r in own.items() if r.get("1XRtI2d9") == "0:0"}
    while pending:
        frontier = centers if not reachable else {p for old in reachable
            for p in str(own[old].get("3h9XCMqj") or "").split(",")}
        step = pending & frontier
        if not step:
            return _refuse(spec, "board pieces are disconnected from the opened graph")
        reachable.update(step)
        pending.difference_update(step)
    new = reachable - opened
    cost = sum(_int(own[p].get("mRY52Tib"), -1) for p in new)
    if any(_int(own[p].get("mRY52Tib"), -1) < 0 for p in new):
        return _refuse(spec, "invalid master board cost")
    rewards = [str(own[p].get("i9w6ZCFM") or "") for p in sorted(new)
               if p not in centers or not AUTHORED_DEFER_CENTER_UNTIL_COMPLETE]
    completed = reachable == set(own)
    if completed and key not in arena["complete"]:
        rewards.append(str(boards[board].get("dX6cor8j") or ""))
    grants = []
    for text in rewards:
        try:
            parsed = reward_entries(text)
        except ValueError as error:
            return _refuse(spec, str(error))
        if any(not State.player._can_credit(reward) for reward in parsed):
            return _refuse(spec, "board reward has no inventory projection")
        if any(r["kind"] == 10 and str(r["id"]) not in _mst("F_UNIT_MST.ndjson", "3HriTp6B") for r in parsed):
            return _refuse(spec, "board reward unit is absent from the shipped master")
        grants.extend(parsed)
    points = _int(arena["user"].get("mRY52Tib"), 0)
    if cost > points or not _writable():
        return _refuse(spec, "insufficient arena trade points or frozen player")
    if _arena_rows(arena) is None:
        return _refuse(spec, "no shipped arena season")
    if new:
        before, dirty = copy.deepcopy(State.player.data), State.player.dirty
        if State.player._grant_items(grants) != grants:
            State.player.data, State.player.dirty = before, dirty
            return _refuse(spec, "board reward was not granted completely")
        arena["user"]["mRY52Tib"] = str(points - cost)
        arena["boards"][key] = sorted(reachable, key=int)
        arena["groups"] = copy.deepcopy(groups)
        if completed:
            arena["complete"][key] = True
            next_index = (sequence.index(board) + 1) % len(sequence)
            next_board = sequence[next_index]
            paths[group] = path + [next_board] if next_index else [next_board]
            next_key = group + ':' + next_board
            arena['boards'].pop(next_key, None)
            arena['complete'].pop(next_key, None)
        _save_arena(arena)
    return _board_reply(spec, arena, pieces)


def clsm_lottery(spec, req):
    from exvius_colosseum import lottery
    return lottery(spec, req)


def clsm_entry(spec, req):
    from exvius_colosseum import entry
    return entry(spec, req)


def clsm_start(spec, req):
    from exvius_colosseum import start
    return start(spec, req)


def clsm_end(spec, req):
    from exvius_colosseum import end
    return end(spec, req)


def _friends():
    catalog = {str(f["friend_id"]): f for f in load_friends()}
    saved = State.player.data.get("exvius_friends")
    state = copy.deepcopy(saved) if saved is not None else {
        "relations": {fid: {"type": 1, "favorite": 0} for fid in catalog}}
    return catalog, state


def _friend_row(friend, relation, category=None):
    row = _friend_list_row(friend, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
    row.update({"K3BV17gk": str(category if category is not None else relation["type"]),
                "8zE6w9RP": str(relation.get("favorite", 0))})
    return row


def _friend_reply(spec, tag, friends):
    out = _out(spec)
    out[tag] = [row for friend, row in friends]
    cards = [_vc_info_row(friend, friend["unit"]["vision_card"])
             for friend, row in friends if friend["unit"]["vision_card"]]
    if cards:
        known = {r["gXb32xzQ"]: r for r in out.get(VCINFO_TAG, [])}
        known.update({r["gXb32xzQ"]: r for r in cards})
        out[VCINFO_TAG] = list(known.values())
    return out


def _ope(out, deleted=""):
    out["I53AVzSo"] = [{"0j67QHm1": "", "0NVFk2fD": deleted, "H4zD2IQ5": "-1"}]
    return out


def _save_friends(state):
    State.player.data["exvius_friends"] = state
    State.player.data.setdefault("counts", {})["friend"] = sum(
        r["type"] == 1 for r in state["relations"].values())
    State.player.dirty = True


def _friend_target(req):
    return str((_node(req, "I53AVzSo") or {}).get("m3Wghr1j", ""))


def _friend_change(spec, req, action):
    catalog, state = _friends()
    target = _friend_target(req)
    if target not in catalog or target == str(State.player.data["identity"]["user_id"]):
        return _refuse(spec, "unknown offline friend or self relationship")
    if not _writable():
        return _refuse(spec, "frozen friend state")
    relation = state["relations"].get(target, {"type": 0, "favorite": 0})
    category = relation["type"]
    accepted = sum(r["type"] == 1 for r in state["relations"].values())
    if action == "agree":
        if category not in (1, 3) or (category == 3 and accepted >= AUTHORED_FRIEND_CAPACITY):
            return _refuse(spec, "only incoming requests can be accepted; capacity must be available")
        relation["type"] = 1
    elif action == "request":
        if category not in (0, 2) or (category == 0 and accepted >= AUTHORED_FRIEND_CAPACITY):
            return _refuse(spec, "friend already accepted/incoming, or capacity reached")
        relation["type"] = 2
    elif action == "favorite":
        flag = _int((_node(req, "I53AVzSo") or {}).get("8zE6w9RP"))
        if category != 1 or flag not in (0, 1):
            return _refuse(spec, "favorite requires an accepted friend and flag 0/1")
        relation["favorite"] = flag
    elif action in ("delete", "refuse"):
        if category not in ((0, 1) if action == "delete" else (0, 2, 3)):
            return _refuse(spec, "delete requires accepted friendship; refuse requires pending request")
        # Keep an explicit tombstone, so YAML defaults do not resurrect the friend.
        relation = {"type": 0, "favorite": 0}
    state["relations"][target] = relation
    previous_count = State.player.data.get("counts", {}).get("friend", 0)
    _save_friends(state)
    if action in ("delete", "refuse"):
        out = _ope(_out(spec), target)
    else:
        friend = catalog[target]
        out = _friend_reply(spec, "2vuhy0Ex", [(friend, _friend_row(friend, relation))])
        if action != "favorite":
            _ope(out)  # Never delete the accepted row in the same reply.
    count_changed = previous_count != State.player.data["counts"]["friend"]
    return _refresh(out) if action in ("agree", "delete") or count_changed else out


def friend_agree(spec, req):
    return _friend_change(spec, req, "agree")


def friend_delete(spec, req):
    return _friend_change(spec, req, "delete")


def friend_refuse(spec, req):
    return _friend_change(spec, req, "refuse")


def friend_favorite(spec, req):
    return _friend_change(spec, req, "favorite")


def friend_request(spec, req):
    return _friend_change(spec, req, "request")


def friend_search(spec, req):
    catalog, state = _friends()
    target = _friend_target(req)
    friend = catalog.get(target)
    rows = [(friend, _friend_row(friend, {}, 4))] if friend else []
    return _friend_reply(spec, "2K05IxtX", rows)


def friend_detail(spec, req):
    catalog, state = _friends()
    target = _friend_target(req)
    category = _int((_node(req, "I53AVzSo") or {}).get("K3BV17gk"))
    relation = state["relations"].get(target, {"type": 0})
    if target not in catalog or category not in (1, 2, 3, 4, 5) or (
            category in (1, 2, 3) and category != relation["type"]):
        return _refuse(spec, "friend detail category does not match the stored relationship")
    friend = catalog[target]
    return _friend_reply(spec, "2vuhy0Ex", [(friend, _friend_row(friend, relation, category))])


def friend_suggest(spec, req):
    catalog, state = _friends()
    own = str(State.player.data["identity"]["user_id"])
    rows = [(friend, _friend_row(friend, {}, 5)) for fid, friend in catalog.items()
            if fid != own and state["relations"].get(fid, {}).get("type", 0) == 0]
    return _friend_reply(spec, "f6yGgCj2", rows)


def friend_list(spec, req):
    """Read projection needed so a later list refresh cannot undo these actions."""
    catalog, state = _friends()
    out = _out(spec)
    for category, tag in ((1, "56gJBnVh"), (2, "hZR64mDe"), (3, "9Qt5cI0n")):
        rows = [(friend, _friend_row(friend, state["relations"][fid]))
                for fid, friend in catalog.items() if state["relations"].get(fid, {}).get("type") == category]
        out = _friend_reply(out, tag, rows)
    if _writable() and "exvius_friends" not in State.player.data:
        _save_friends(state)
    return _ope(_refresh(out))


def friend_reinforcements(spec, req):
    catalog, state = _friends()
    rows = [(friend, _reinforce_row(friend)) for fid, friend in catalog.items()
            if state["relations"].get(fid, {}).get("type") == 1]
    out = _out(spec)
    # Replace the whole support list. A non-clearing delta would retain a deleted helper.
    out.pop("9Tp2fiyB", None)
    out.pop(VCINFO_TAG, None)
    return _ope(_friend_reply(out, "pzf5se6V", rows))


HANDLERS = {
    "f8kXGWy0": rb_entry,        # RbEntryRequest
    "DgG4Cy0F": rb_matching,     # RbMatchingRequest
    "eHY7X8Nn": rb_start,        # RbStartRequest
    "os4k7C0b": rb_end,          # RbEndRequest
    "6ZNY3zAm": rb_restart,      # RbReStartRequest
    "kcW85SfU": rb_ranking,      # RbRankingRequest
    "hqzU9Qc5": rb_board_open,   # RbBoardPieceOpenRequest
    "5g0vWZFq": clsm_entry,      # ClsmEntryRequest
    "4uCSA3ko": clsm_start,      # ClsmStartRequest
    "3zgbapQ7": clsm_end,        # ClsmEndRequest
    "Un16HuNI": clsm_lottery,    # ClsmLotteryRequest
    "kx13SLUY": friend_agree,    # FriendAgreeRequest
    "a2d6omAy": friend_delete,   # FriendDeleteRequest
    "7kG0JAvE": friend_detail,   # FriendDetailRequest
    "1oE3Fwn4": friend_favorite, # FriendFavoriteRequest
    "1nbWRV9w": friend_refuse,   # FriendRefuseRequest
    "j0A5vQd8": friend_request,  # FriendRequest
    "3siZRSU4": friend_search,   # FriendSearchRequest
    "iAs67PhJ": friend_suggest,  # FriendSuggestRequest
    "u7Id4bMg": friend_list,     # FriendListRequest: preserve relationship edits on refresh
    "AJhnI37s": friend_reinforcements,  # GetReinforcementInfoRequest: remove deleted helpers
}
