"""Project exact original typed field scenarios onto preserved dependency groups."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('source/server', 'custom-engine/tools')]
from cpk import Cpk
import battle_content
from player_state import _load_ndjson
from repair_field_scenarios import script_scenarios


def candidates():
    resources = _load_ndjson('F_RESOURCE_MAP_MST.ndjson', 'Nnb20keZ')
    versions = _load_ndjson('F_RESOURCE_MAP_VERSION_MST_LOCALIZE.ndjson', 'Nnb20keZ')
    dungeons = _load_ndjson('F_DUNGEON_MST.ndjson', 'U9iHsau3')
    response = json.loads((ROOT / 'source/server/responses.json').read_text(encoding='utf8'))['29JRaDbd']
    groups = {}
    for row in response['YjHhvN65']:
        groups.setdefault(row['ja07xgLF'], set()).add(row['2fY1IomW'])
    cache = {}
    for mission in _load_ndjson('F_MISSION_MST.ndjson')['__rows__']:
        if mission.get('Y4VoF8yu') != '2':
            continue
        mid = mission['qo3PECw6']
        dungeon = dungeons.get(mission['U9iHsau3'], {})
        ids = set(mission.get('q4f9IdMs', '').split(',')) | set(dungeon.get('q4f9IdMs', '').split(','))
        for rid in sorted(ids):
            row = resources.get(rid)
            version = versions.get(rid)
            if not row or not version or row.get('drE35YcF') != 'event':
                continue
            relative = 'common_lang/sd/' + row['3LHdc6Qa'] + '/Ver' + version['OzT5lSz3'] + '_' + row['pJ56sAEo']
            path = next((ROOT / p / relative for p in ('data/overlay', 'data/client/files')
                         if (ROOT / p / relative).is_file()), None)
            if path is None:
                continue
            member = Path(row['pJ56sAEo']).stem + '_event.bin'
            key = (path, member)
            if key not in cache:
                pack = Cpk(path.read_bytes())
                if member not in pack.files:
                    cache[key] = None
                else:
                    payload = pack.read(member)
                    try:
                        cache[key] = (script_scenarios(payload), hashlib.sha256(payload).hexdigest())
                    except (ValueError, IndexError, AssertionError):
                        cache[key] = None
            if cache[key] is None:
                continue
            scenarios, digest = cache[key]
            for sid in sorted(scenarios, key=int):
                for gid in sorted(groups.get(sid, []), key=int):
                    yield mid, gid, {'scenario': sid, 'group': gid, 'resource': rid,
                                    'cpk': path.relative_to(ROOT).as_posix(),
                                    'member': member, 'member_sha256': digest}


def repair():
    path = ROOT / 'source/server/content/field_group_bindings.json'
    document = json.loads(path.read_text(encoding='utf8'))
    source = battle_content._default_index_source()
    proven = document.setdefault('typed_scenario_links', {})
    added, unresolved = {}, {}
    validated = {}
    for mid, gid, evidence in candidates():
        # The old prefix loader already provides these groups. This repair
        # supplies only exact cross-stage or irregularly numbered roots.
        if gid.startswith(mid) and len(gid) == len(mid) + 2:
            continue
        if gid not in validated:
            try:
                battle_content.derive_mission(int(mid), source, field_groups={gid})
                validated[gid] = None
            except (Exception, SystemExit) as error:
                validated[gid] = str(error)
        if validated[gid]:
            unresolved.setdefault(mid, {})[gid] = validated[gid]
            continue
        values = document['missions'].setdefault(mid, [])
        if gid not in values:
            values.append(gid)
            values.sort(key=int)
            added.setdefault(mid, []).append(gid)
        links = proven.setdefault(mid, [])
        if evidence not in links:
            links.append(evidence)
    document['typed_scenario_note'] = (
        'Exact opcode0x47 scenario IDs from each declared original event package own typed member, '
        'resolved through the mandatory original MissionStart response scenario-group list. '
        'Only groups with complete preserved actor/parts/skill dependencies are projected. '
        'Cumulative foreign members, arbitrary integer scans and random allocation guesses are excluded. '
        'Page conditions still determine whether a scripted fight is reached.')
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    print('CHECKPOINT typed field dependency bindings added:', len(added), 'missions,',
          sum(map(len, added.values())), 'group projections')
    print('UNRESOLVED preserved dependencies:', json.dumps(unresolved, separators=(',', ':')))
    return added, unresolved


if __name__ == '__main__':
    repair()
