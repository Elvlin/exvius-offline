"""Persistent event selection, using existing area/dungeon/mission interfaces.
No runtime imports. No content, combat, reward, or unlock data is invented.
"""
import copy
import json
import os
import time
from pathlib import Path

DATE_START = ('VjJQ51uG', 'NTXoA6e2')
DATE_END = ('m8ivD4NX', 'V48um7Jw', '7Gvw6J82')


def policy_path(data_root):
    if not data_root:
        return None
    return Path(data_root) / 'state' / 'exvius_events.json'


def validate_policy(policy):
    if not isinstance(policy, dict) or policy.get('version') != 1:
        raise ValueError('event policy version must be 1')
    areas = policy.get('areas')
    if not isinstance(areas, list) or not all(type(x) in (str, int) and str(x).isdigit() for x in areas):
        raise ValueError('areas must be a list of numeric IDs; [] disables added event tiles')
    if type(policy.get('permanent')) is not bool:
        raise ValueError('permanent must be a boolean')
    return {'version': 1, 'areas': list(dict.fromkeys(map(str, areas))),
            'permanent': policy['permanent']}


def load_policy(data_root, fallback_areas=()):
    path = policy_path(data_root)
    if path is None or not path.exists():
        return validate_policy({'version': 1, 'areas': list(fallback_areas), 'permanent': True})
    return validate_policy(json.loads(path.read_text(encoding='utf-8')))


def save_policy(data_root, policy):
    """Explicit CLI save only; atomic replace and versioned backup of previous bytes."""
    clean = validate_policy(policy)
    path = policy_path(data_root)
    if path is None:
        raise ValueError('data root is required to persist selection')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + '.backup-' + str(time.time_ns()))
        backup.write_bytes(path.read_bytes())
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    return str(path)


def event_facts(areas, dungeons, missions):
    """Mirror upstream first-in-file area -> dungeon -> mission lookup, no ID guessing."""
    facts, missing = [], []
    for area in dict.fromkeys(map(str, areas)):
        dungeon = next((str(r['U9iHsau3']) for r in dungeons
                        if str(r.get('uv60hgDW')) == area and r.get('U9iHsau3')), None)
        mission = next((str(r['qo3PECw6']) for r in missions
                        if str(r.get('U9iHsau3')) == dungeon and r.get('qo3PECw6')), None) if dungeon else None
        if dungeon and mission:
            facts.append({'area': area, 'dungeon': dungeon, 'first_mission': mission})
        else:
            missing.append({'area': area, 'missing': 'mission' if dungeon else 'dungeon'})
    return facts, missing


def apply_availability(spec, policy, now=None, resolved_areas=None):
    """Extend only selected AND resolved gate rows, including pre-existing rows.

    A rolling ten-year horizon, refreshed each served gate response, removes a
    calendar cutoff while avoiding an invented sentinel timestamp. Other gate
    predicates, currencies, transitions and all unselected rows stay unchanged.
    """
    clean = validate_policy(policy)
    if not clean['permanent'] or not isinstance(spec, dict):
        return spec
    rows = spec.get('0xkoNP8U')
    if not isinstance(rows, list):
        return spec
    allowed = set(clean['areas'])
    if resolved_areas is not None:
        allowed &= set(map(str, resolved_areas))
    now = int(time.time() if now is None else now)
    out = copy.deepcopy(spec)
    for row in out['0xkoNP8U']:
        if not isinstance(row, dict) or str(row.get('uv60hgDW')) not in allowed:
            continue
        # GL9 CommonUtils::convertToTime uses strptime, not an epoch parser.
        for key in DATE_START:
            row[key] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(max(0, now - 86400)))
        for key in DATE_END:
            row[key] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now + 10 * 366 * 86400))
    return out


def native_gate_dates(spec):
    """Preserve captured instants while spelling them for GL9's date-text reader."""
    if not isinstance(spec, dict) or not isinstance(spec.get('0xkoNP8U'), list):
        return spec
    out = copy.deepcopy(spec)
    for row in out['0xkoNP8U']:
        if not isinstance(row, dict):
            continue
        for key in DATE_START + DATE_END:
            value = str(row.get(key, ''))
            if value.isdigit():
                row[key] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(value)))
    return out
