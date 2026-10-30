"""Player actions the recorded corpus never answered (logs/sweep-unhandled-requests-20261025.md).

The server's default reply only echoes the request, so these actions changed nothing in the save. Each
handler here keys on its own request id (source/server/endpoints.json), reads the fields the client's
`createBody` writes (source/docs/analysis/unhandled_request_fields.json, from
harness/extract_request_fields.py) and applies the change to the one player state. A reply that should
refresh the client's lists carries the unit group, so `apply_to_reply` projects every player group.
"""
import json
from exvius_raid_progress import personal_raid_menu
from ffbe_friends import local_friend_action

from ffbe_state import State, _note

UNIT_GROUP = "B71MekS8"        # UserUnitInfoResponse; its presence makes apply_to_reply project all groups


def _request(plaintext):
    if not plaintext:
        return None
    try:
        req = json.JSONDecoder().raw_decode(plaintext)[0]
    except ValueError:
        return None
    return req if isinstance(req, dict) else None


def _node(req, group):
    rows = req.get(group) if req else None
    return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None


def _refresh(spec):
    out = dict(spec) if isinstance(spec, dict) else {}
    out.setdefault(UNIT_GROUP, [])
    return out


def _mst(name, key):
    from player_state import _load_ndjson
    return _load_ndjson(name, key)


def item_sell(spec, req):
    """Use the shop transaction path, including equipment's separate ownership store."""
    from exvius_actions_shops import item_sell as sell
    return sell(spec, req)


def mission_restart(spec, req):
    """MissionReStartRequest (a continue): the client spends F_DEFINE_MST CONTINUE_COST Lapis (100)."""
    row = _mst("F_DEFINE_MST.ndjson", "AK8Nn7ta").get("CONTINUE_COST") or {}
    cost = int(row.get("YjIUDJ97") or 100)
    paid = State.player.spend_lapis(cost)
    print(f"mission: continue {'paid' if paid else 'NOT paid (balance)'} {cost} lapis", flush=True)
    return _refresh(spec)


def unit_class_up(spec, req):
    """UnitClassUpRequest (awakening): group `sWc7EH69`, `og2GHy49` = the base unit. F_UNIT_CLASS_UP_MST
    names the next rarity (`t74crqAL`), its gil (`7UR4J2SE`) and materials (`KCk8u0am`). The reply is
    UnitClassUpResponse on the same tag (UserUnitClassUpResult: og2GHy49 unit, 5u7VYNEX new unit,
    KCk8u0am materials, WbGYcN17/02CI3bpE element info, p9Xj4Anc all-kigen flag)."""
    node = _node(req, "sWc7EH69")
    iid = str(node.get("og2GHy49") or "") if node else ""
    unit = next((u for u in State.player.data["roster"] if str(u["instance_id"]) == iid), None)
    if unit is None:
        _note(f"unit-class-up: unit {iid or '?'} not in the roster")
        return spec
    step = _mst("F_UNIT_CLASS_UP_MST.ndjson", "3HriTp6B").get(str(unit["master_id"]))
    if not step:
        _note(f"unit-class-up: no F_UNIT_CLASS_UP_MST row for {unit['master_id']}")
        return spec
    materials = str(step.get("KCk8u0am") or "")
    gil = int(step.get("7UR4J2SE") or 0)
    rows = [m.split(":") for m in materials.split(",") if m.count(":") == 2]
    if any(State.player.item_count(int(k), i) < int(c) for k, i, c in rows) or \
            int(State.player.currencies.get("gil", 0)) < gil:
        _note(f"unit-class-up: {unit['master_id']} lacks materials or gil; not awakened")
        return spec
    for k, i, c in rows:
        State.player.spend_item(int(k), i, int(c))
    State.player.spend_currency("gil", gil)
    before = unit["master_id"]
    unit["master_id"] = str(step["t74crqAL"])
    unit = State.player.renew_unit_instance(iid)
    State.player.record_archive({'TOTAL_UNIT_CLASS_UP': 1})
    State.player.dirty = True
    print(f"unit: awakened {iid} {before} -> {unit['master_id']} for {gil} gil + {materials}", flush=True)
    out = _refresh(spec)
    out["sWc7EH69"] = [{"og2GHy49": iid, "5u7VYNEX": unit['instance_id'], "KCk8u0am": materials, "WbGYcN17": "",
                        "02CI3bpE": "", "p9Xj4Anc": "0"}]
    return out


def _parse_rewards(text):
    rows = []
    for entry in str(text or "").split(","):
        parts = entry.split(":")
        if len(parts) == 3 and all(p.isdigit() for p in parts) and int(parts[2]) > 0:
            rows.append({"kind": int(parts[0]), "id": int(parts[1]), "count": int(parts[2])})
    return rows


def sacrifice(spec, req, group="6kvFj2Kw"):
    """SacrificeRequest / NvSacrificeRequest (the Units "Convert"): one node per unit in `6kvFj2Kw`
    (`4Ncra9DF` for NV), `og2GHy49` = the unit. F_SACRIFICE_MST (keyed by the unit id `woghJa61`) gives
    the item it becomes (`tL6G9egd`) and the extra items (`q1PJQ3eE`). The unit leaves the roster."""
    table = _mst("F_SACRIFICE_MST.ndjson", "woghJa61")
    ids = [str(n.get("og2GHy49")) for n in (req.get(group) or []) if isinstance(n, dict) and n.get("og2GHy49")]
    roster = {str(u["instance_id"]): u for u in State.player.data["roster"]}
    converted = []
    for iid in ids:
        unit = roster.get(iid)
        row = table.get(str(unit["master_id"])) if unit else None
        if not row:
            _note(f"unit-convert: {iid} has no F_SACRIFICE_MST row; kept")
            continue
        rewards = _parse_rewards(row.get("q1PJQ3eE"))
        if str(row.get("tL6G9egd") or "0") not in ("", "0"):
            rewards.insert(0, {"kind": 20, "id": int(row["tL6G9egd"]), "count": 1})
        State.player.drop_units([iid])
        State.player._grant_items(rewards)
        converted.append(f"{unit['master_id']}->" + ",".join(f"{r['id']}x{r['count']}" for r in rewards))
    print(f"unit: converted {len(converted)} unit(s): {' '.join(converted)}", flush=True)
    return _refresh(spec)


HANDLERS = {
    "7kG0JAvE": lambda spec, req: local_friend_action(spec, req, 'detail'),
    "3siZRSU4": lambda spec, req: local_friend_action(spec, req, 'search'),
    "iAs67PhJ": lambda spec, req: local_friend_action(spec, req, 'suggest'),
    "1oE3Fwn4": lambda spec, req: local_friend_action(spec, req, 'favorite'),
    "g0BjrU5D": personal_raid_menu,  # RoutineRaidMenuUpdateRequest
    "7tWdn9zH": sacrifice,                                             # SacrificeRequest
    "x94MnujU": lambda spec, req: sacrifice(spec, req, "4Ncra9DF"),   # NvSacrificeRequest
    "d9Si7TYm": item_sell,          # ItemSellRequest
    "GfI4LaU3": mission_restart,    # MissionReStartRequest
    "zf49XKg8": unit_class_up,      # UnitClassUpRequest
}


# The other action families (Codex-implemented from source/docs/analysis/action_research/, reviewed here).
# Friend list and reinforcement replies retain their established projection.
FAMILIES = ("exvius_actions_arena", "exvius_actions_expedition", "exvius_actions_modes", "exvius_actions_shops",
            "exvius_gacha_select", "gacha_box")
KEEP_EXISTING = {"u7Id4bMg", "AJhnI37s"}
_merged = []


def _all_handlers():
    if not _merged:
        import importlib
        for name in FAMILIES:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            for rid, handler in module.HANDLERS.items():
                if rid not in KEEP_EXISTING and rid not in HANDLERS:
                    HANDLERS[rid] = handler
        _merged.append(True)
    return HANDLERS


def serve_actions(spec, reply_id, plaintext):
    handler = _all_handlers().get(str(reply_id))
    if State.player is None:
        return spec
    from exvius_colosseum import project
    if handler is None:
        return project(spec)
    req = _request(plaintext)
    if req is None:
        return project(spec)
    return project(handler(spec, req))
