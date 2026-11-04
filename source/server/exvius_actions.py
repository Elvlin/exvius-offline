"""Player actions the recorded corpus never answered (logs/sweep-unhandled-requests-20261025.md).

The server's default reply only echoes the request, so these actions changed nothing in the save. Each
handler here keys on its own request id (source/server/endpoints.json), reads the fields the client's
`createBody` writes (source/docs/analysis/unhandled_request_fields.json, from
harness/extract_request_fields.py) and applies the change to the one player state. A reply that should
refresh the client's lists carries the unit group, so `apply_to_reply` projects every player group.
"""
from collections import Counter
import json
from exvius_raid_progress import personal_raid_menu
from ffbe_friends import local_friend_action

from ffbe_state import State, _note

UNIT_GROUP = "B71MekS8"        # UserUnitInfoResponse; its presence makes apply_to_reply project all groups
OPTION_GROUP = 'Dqx0MA42'
OPTION_FIELDS = ('ayUH8g4q', '0NBjrDw4', 'p0bM2ZNi', 'bH1T4FLK', 'b70zaGxK')


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


def option_update(spec, req):
    """Save the fields shared by the native option request and response."""
    node = _node(req, OPTION_GROUP) or {}
    player = State.player
    options = dict(player.data.get('user_options', {}))
    for key in OPTION_FIELDS:
        value = node.get(key)
        if type(value) in (str, int) and len(str(value)) <= 4096 and '\x00' not in str(value):
            options[key] = str(value)
    if options != player.data.get('user_options', {}) and player.mode != 'frozen':
        player.data['user_options'] = options
        player.dirty = True
    return option_reply(spec)


def option_reply(spec):
    out = dict(spec) if isinstance(spec, dict) else {}
    options = State.player.data.get('user_options')
    if options:
        out[OPTION_GROUP] = [dict(options, **{'27RyqAGe': 'UNIT_LOCK_RANK'})]
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
    if unit is None or State.player.mode == 'frozen':
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
    from player_state import unit_mst
    destination = unit_mst(unit['master_id']) or {}
    State.player.record_archive({'TOTAL_UNIT_CLASS_UP': 1, 'TOTAL_UNIT_RARE7_CLASS_UP':
                                 int(destination.get('9fW0TePj') == '7' and destination.get('JPW8Vs40') == '0')})
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


def unit_equip(spec, req):
    from exvius_actions_expedition import _retain_owned_equipment, _wire_loadouts

    player = State.player
    rows = req.get("Er92Kdhm")
    if player.mode == "frozen" or not isinstance(rows, list):
        return _refresh(spec)
    roster = {str(unit["instance_id"]): unit for unit in player.data["roster"]}
    gear = {row["J1YX9kmM"]: int(row["Qy5EvcK1"]) for row in player.equip_item_rows()}
    materia = {row["H5jBL0Vf"]: int(row["Qy5EvcK1"]) for row in player.materia_rows()}
    cards = {str(card["user_vc_id"]) for card in player.data.get("vision_cards", [])}
    loadouts = {}
    try:
        for row in rows:
            decoded, _ = _wire_loadouts(row, roster)
            for iid, fields in decoded.items():
                for field, values in fields.items():
                    if field in ("equipment", "shift_equipment", "materia", "shift_materia"):
                        owned = materia if "materia" in field else gear
                        counts = Counter(values if "materia" in field else values.values())
                        if any(item != "0" and count > owned.get(item, 0) for item, count in counts.items()):
                            raise ValueError("unowned equipment or materia")
                    if field in ("vision_card", "shift_vision_card") and values and values not in cards:
                        # Native vision-card strings carry the master id as well as the instance id.
                        if not cards.intersection(values.split("-")):
                            raise ValueError("unowned vision card")
                if str(row.get("xBi3L6yR", "1")) == "1":
                    loadouts.setdefault(iid, {}).update(fields)
    except (AttributeError, TypeError, ValueError):
        _note("unit-equip: invalid equipment update")
        return _refresh(spec)
    if any(any(roster[iid].get(key) != value for key, value in fields.items())
           for iid, fields in loadouts.items()):
        # Older saves infer the starter copies from the worn slots. Keep those
        # copies in inventory before replacing or clearing the slots.
        _retain_owned_equipment()
        from ffbe_player import score_quest_action
        for iid, fields in loadouts.items():
            for field in ('materia', 'shift_materia'):
                if field in fields and fields[field] != roster[iid].get(field) and any(i != '0' for i in fields[field]):
                    score_quest_action('13')
            roster[iid].update(fields)
        player.dirty = True
    return _refresh(spec)


def sacrifice(spec, req, group="6kvFj2Kw"):
    """Consume eligible units only after resolving the fragment rewards for the full batch."""
    from exvius_actions_shops import deployed_unit_ids
    from player_state import unit_mst

    player = State.player
    nodes = req.get(group)
    if player.mode == "frozen" or not isinstance(nodes, list) or not nodes:
        return spec
    table = _mst("F_SACRIFICE_MST.ndjson", "woghJa61")
    deployed = deployed_unit_ids(player)
    ids, rewards, result = set(), [], []
    for node in nodes:
        iid = str(node.get("og2GHy49", "")) if isinstance(node, dict) else ""
        unit = player.roster_row(iid)
        if not unit or iid in ids or iid in deployed or unit.get("favourite"):
            return _refresh(spec)
        master = unit_mst(unit["master_id"]) or {}
        row = table.get(str(unit["master_id"])) or table.get(master.get("woghJa61"))
        if not row:
            return _refresh(spec)
        # The native picker can send pure NV units through SacrificeRequest.
        # The unit's master row determines its rewards for either request.
        items = str(row.get("1swM3H4T") or row.get("q1PJQ3eE") or "")
        unit_rewards = _parse_rewards(items)
        prism = str(row.get("tL6G9egd") or "0")
        if group == "4Ncra9DF":
            prism = "0"
        if prism != "0":
            unit_rewards.insert(0, {"kind": 20, "id": int(prism), "count": 1})
        if not unit_rewards or any(not player._can_credit(reward) for reward in unit_rewards):
            return _refresh(spec)
        ids.add(iid)
        rewards.extend(unit_rewards)
        result.append({"og2GHy49": iid, "ijEey5f7": str(node.get("ijEey5f7", "1")),
                       "tL6G9egd": prism, "1swM3H4T": items})
    if len(ids) >= len(player.data["roster"]):
        return _refresh(spec)
    player.drop_units(ids)
    player._grant_items(rewards)
    out = _refresh(spec)
    out[group] = result
    _note(f"unit-convert: granted rewards for {len(ids)} unit(s)")
    return out


def update_profile(spec, req):
    player = State.player
    row = _node(req, 'MZzST52W')
    if player.mode == 'frozen' or row is None:
        return spec
    name, message = row.get('9qh17ZUf'), row.get('Wk1v6upb')
    if isinstance(name, str) and name.strip() and len(name) <= 64 and name.isprintable():
        player.data['identity']['handle_name'] = name
        player.dirty = True
    if isinstance(message, str) and len(message) <= 256 and (not message or message.isprintable()):
        player.data['profile']['message'] = message
        player.dirty = True
    out = _refresh(spec)
    out['LhVz6aD2'] = [dict((out.get('LhVz6aD2') or [{}])[0],
                             **{'9qh17ZUf': player.data['identity']['handle_name']})]
    return out


def inventory_favourite(spec, req, group, on_keys, off_keys):
    player = State.player
    row = _node(req, group)
    if player.mode == 'frozen' or row is None:
        return spec
    if group == '4I71fGzq':
        existing = {str(card['user_vc_id']): card for card in player.data.get('vision_cards', [])}
    else:
        owned = (player.equip_item_rows() if group == 'K8pR0Fvb' else player.materia_rows())
        token = 'J1YX9kmM' if group == 'K8pR0Fvb' else 'H5jBL0Vf'
        existing = {str(item[token]): item for item in owned}
    saved = dict(player.data.get('inventory_favourites', {}).get(group, {}))
    changes = {}
    for enabled, keys in ((True, on_keys), (False, off_keys)):
        for key in keys:
            accepted = []
            for entry in str(row.get(key) or '').split(','):
                parts = entry.split(':')
                if (not all(p.isascii() and p.isdigit() for p in parts)
                        or len(parts) != (1 if group == '4I71fGzq' else 2)
                        or parts[0] not in existing):
                    continue
                accepted.append(entry)
                if group == '4I71fGzq':
                    existing[entry]['favourite'] = int(enabled)
                elif enabled:
                    saved[parts[0]] = parts[1]
                else:
                    saved.pop(parts[0], None)
            if accepted:
                changes[key] = ','.join(accepted)
    if changes:
        if group != '4I71fGzq':
            player.data.setdefault('inventory_favourites', {})[group] = saved
        player.dirty = True
    return dict(spec or {}, **{group: [changes]})


NOTICE_GROUPS = ('3BI1xSGW', 'R17unt2e', 'VKA5urE1', 'fzm3je8p', 'oUk10RXm', 'tN8f0PSB')


def notice_state(spec, req, reply_id):
    player = State.player
    if not isinstance(spec, dict):
        spec = {}
    saved = player.data.get('notices', {})
    catalogue = dict(saved.get('index', {}))
    for group in NOTICE_GROUPS:
        for row in spec.get(group, ()):
            notice_id = str(row.get('td06MKEX', ''))
            year = str(row.get('1d8R5ajV', '')).split('-', 1)[0].split('/', 1)[0]
            index = str(row.get('QLfe23bu', ''))
            if notice_id.isdigit() and year.isdigit() and len(year) == 4 and index.isdigit() and int(index) < 65536:
                catalogue[notice_id] = (year, int(index))
    marked = set(saved.get('read', ()))
    row = _node(req, 'p4U2NosZ') if reply_id == 'pC3a2JWU' else None
    if row and player.mode != 'frozen':
        marked.update(i for i in str(row.get('goAiX84L') or '').split(',') if i.isascii() and i.isdigit())
    if player.mode != 'frozen' and (set(saved.get('read', ())) != marked or
                                   any(list(v) != list(saved.get('index', {}).get(k, ())) for k, v in catalogue.items())):
        player.data['notices'] = dict(saved, index=catalogue, read=sorted(marked))
        player.dirty = True
    if not marked or (reply_id not in ('pC3a2JWU', 'CQ4jTm2F') and 'LhVz6aD2' not in spec
                      and not any(group in spec for group in NOTICE_GROUPS)):
        return spec
    masks = {}
    for notice_id in marked.intersection(catalogue):
        year, index = catalogue[notice_id]
        nibbles = masks.setdefault(year, [])
        slot = index // 4
        if slot >= len(nibbles):
            nibbles.extend([0] * (slot + 1 - len(nibbles)))
        nibbles[slot] |= 8 >> (index % 4)
    if masks:
        spec = dict(spec, Z53gL0RU=[{'Gs6BT8n5': year, 'goAiX84L': ''.join(format(n, 'x') for n in mask)}
                                   for year, mask in sorted(masks.items())])
    return spec


HANDLERS = {
    'ey8mupb4': update_profile,
    'otgXV79T': option_update,    # OptionUpdateRequest
    'cVRHU84e': lambda s, r: inventory_favourite(s, r, 'K8pR0Fvb', ('I3FUD4Mt', 'DWJ3P8cg'), ('aME25KS0', 'Exp2A1u7')),
    'k5v0hMd8': lambda s, r: inventory_favourite(s, r, 'pJ9Eo6cn', ('8UJhyb4u',), ('85HUgcbK',)),
    'VTbX14dD': lambda s, r: inventory_favourite(s, r, '4I71fGzq', ('E0zptv3J',), ('N4ikBXn9',)),
    "7kG0JAvE": lambda spec, req: local_friend_action(spec, req, 'detail'),
    "3siZRSU4": lambda spec, req: local_friend_action(spec, req, 'search'),
    "iAs67PhJ": lambda spec, req: local_friend_action(spec, req, 'suggest'),
    "1oE3Fwn4": lambda spec, req: local_friend_action(spec, req, 'favorite'),
    "g0BjrU5D": personal_raid_menu,  # RoutineRaidMenuUpdateRequest
    "pB3st6Tg": unit_equip,         # UnitEquipRequest
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
    if reply_id in ('75fYdNxq', 'X07iYtp5') and State.player.data.get('user_options'):
        spec = option_reply(spec)
    from exvius_colosseum import project
    if (reply_id in ('pC3a2JWU', 'CQ4jTm2F') or isinstance(spec, dict)
            and ('LhVz6aD2' in spec or any(group in spec for group in NOTICE_GROUPS))):
        spec = notice_state(spec, _request(plaintext), reply_id)
    if handler is None:
        return project(spec)
    req = _request(plaintext)
    if req is None:
        return project(spec)
    return project(handler(spec, req))
