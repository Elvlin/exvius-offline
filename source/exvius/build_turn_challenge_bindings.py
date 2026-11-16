"""Bind original party-turn challenge targets to their served battle identities.

This authoring tool never substitutes total mission turns. Each alias identifies
one actual phase/group, or an original scenario's explicitly linked group.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'source/exvius')]
from battle_content import IndexSource, EventSource, resolve_pool

OUTPUT = ROOT / 'source/server/content/turn_challenge_bindings.json'


def build(document=None):
    source = IndexSource()
    read = lambda path: json.loads((ROOT / path).read_text(encoding='utf8'))
    raw = ROOT / 'data/mst_decoded/F_CHALLENGE_MST.ndjson'
    challenges = [json.loads(line) for line in raw.read_text(encoding='utf8').splitlines()]
    missions = {r['qo3PECw6']: r for r in map(json.loads,
        (ROOT / 'data/mst_decoded/F_MISSION_MST.ndjson').read_text(encoding='utf8').splitlines())}
    document = document if document is not None else read('source/server/event_encounters.json')
    entries = document['missions']
    bindings = read('source/server/event_battles.json')['missions']
    targets = defaultdict(lambda: defaultdict(list))
    for row in challenges:
        fields = row['Pzn5h0Ga'].split(':')
        if len(fields) == 3 and fields[0] in ('76', '77'):
            targets[row['qo3PECw6']][fields[1]].append({
                'challenge': row['V36ygRYs'], 'condition': row['Pzn5h0Ga']})
    native_groups = defaultdict(list)
    for row in source.load('F_BATTLE_GROUP_MST'):
        native_groups[row['2fY1IomW']].append(row)
    native_monsters = {r['xqartN26']: r for r in source.load('F_MONSTER_MST')}
    native_phases = defaultdict(list)
    for row in source.load('F_MISSION_PHASE_MST'):
        if row.get('gou39JeI') == '2':
            native_phases[row['qo3PECw6']].append(row)
    original_scenarios = defaultdict(set)
    for row in map(json.loads, (ROOT / 'data/web_sources/global_archive_mst_decoded/'
                                'F_SCENARIO_BATTLE_GROUP_MST.ndjson').read_text(encoding='utf8').splitlines()):
        original_scenarios[row['2fY1IomW']].add(row['ja07xgLF'])
    output, unresolved = {}, []

    def signature(slots, monsters):
        values = []
        for row in slots:
            if row.get('WJdBp9f0', '1') != '1':
                continue
            monster = monsters.get(row['xqartN26'])
            if not monster:
                return None
            values.append(monster['V9j8wJcC'])
        return tuple(sorted(values)) or None

    for mid, expected in targets.items():
        entry = entries.get(mid, {})
        authored = entry.get('bundle')
        binding = bindings.get(mid)
        if not authored and not binding:
            continue
        if authored:
            phases = [r for r in authored.get('an6TB4WS', []) if r.get('gou39JeI') == '2']
            served_groups = authored.get('Bi6hVv34', [])
            served_monsters = {r['xqartN26']: r for r in authored.get('wbet57nF', [])}
        else:
            view = EventSource(source, mid, binding)
            phases = []
            for row in view.load('F_MISSION_PHASE_MST'):
                if row.get('qo3PECw6') != mid or row.get('gou39JeI') != '2':
                    continue
                selected = resolve_pool(view.load('F_BATTLE_LOTTERY_MST'), row['6uIYE15X'])
                if selected:
                    phases.append(dict(row, **{'2fY1IomW': selected[0]}))
            served_groups = source.load('F_BATTLE_GROUP_MST')
            served_monsters = native_monsters
        for target, conditions in expected.items():
            # Already preserved exact identities need no remapping. Native
            # field fallback also supplies original own-prefix formations.
            if any(r.get('2fY1IomW') == target for r in phases):
                continue
            if not phases and target in native_groups and target.startswith(mid):
                continue
            aliases = []
            # In retained remapped missions the original party reference can
            # be the exact phase encounter/lottery ID. Follow that explicit
            # reference to its actual selected formation, not a numeric suffix.
            if not authored:
                source_phases = phases
            else:
                origin = entry.get('preserved_formation_source', {}).get('mission', mid)
                source_phases = native_phases.get(str(origin), [])
            referenced = [p for p in source_phases if p.get('6uIYE15X') == target]
            if len(referenced) == 1:
                own = [p for p in phases if p['6v7y3QcJ'] == referenced[0]['6v7y3QcJ']]
                if len(own) == 1:
                    aliases = [{'phase': own[0]['6v7y3QcJ'], 'group': own[0]['2fY1IomW'],
                        'basis': 'Retained source phase explicitly references the original '
                                 'challenge party ID as its encounter/lottery key; follow '
                                 'that same phase to its exact served formation.'}]
            if (len(expected) == 1 and len(phases) == 1
                    and missions.get(mid, {}).get('8xi6Xvyk') == '1'
                    and not aliases
                    and not any(entry.get(k) for k in ('jp_lottery', 'original_weighted_lottery',
                                                     'global_vault_lottery'))):
                phase = phases[0]
                aliases = [{'phase': phase['6v7y3QcJ'], 'group': phase['2fY1IomW'],
                    'basis': 'This original mission has one combat wave and one original '
                             'party-turn target; bind only its exact served battle group.'}]
            if not aliases and target in native_groups:
                original = signature(native_groups[target], native_monsters)
                matches = []
                for phase in phases:
                    slots = [r for r in served_groups if r['2fY1IomW'] == phase['2fY1IomW']]
                    if original and signature(slots, served_monsters) == original:
                        matches.append(phase)
                if len(matches) == 1:
                    aliases = [{'phase': matches[0]['6v7y3QcJ'], 'group': matches[0]['2fY1IomW'],
                        'basis': 'Exact original target formation has the same full visible '
                                 'enemy-model multiset as one unique served phase.'}]
            if not aliases and authored:
                for row in authored.get('YjHhvN65', []):
                    if row['ja07xgLF'] in original_scenarios.get(target, set()):
                        aliases.append({'group': row['2fY1IomW'], 'scenario': row['ja07xgLF'],
                            'basis': 'Original Global scenario link and served link share '
                                     'the exact same scenario ID.'})
                aliases = list({(a['group'], a.get('scenario')): a for a in aliases}.values())
            if aliases:
                output.setdefault(mid, {})[target] = {'aliases': aliases, 'original_conditions': conditions}
            elif phases:
                unresolved.append({'mission': mid, 'target': target,
                    'phases': [{'phase': p['6v7y3QcJ'], 'group': p['2fY1IomW']} for p in phases],
                    'reason': 'No unique own-battle or original formation/scenario mapping proved.'})
    return {'version': 1, 'source': 'Original Global F_CHALLENGE_MST party-turn targets '
            'and the current exact served mission phase/group graph.',
            'challenge_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
            'semantics': 'Native69ieJGhD is wave:actualBattleGroupID:turns. Each alias '
                'requires an actual logged group, and a matching wave when specified. '
                'No overall-mission-turn fallback and no guessed suffix mapping.',
            'missions': output, 'unresolved': unresolved}


def write(document):
    pending = ROOT / 'build/scratch/turn-challenge-bindings-write.json'
    pending.parent.mkdir(parents=True, exist_ok=True)
    try:
        pending.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        pending.replace(OUTPUT)
    finally:
        pending.unlink(missing_ok=True)


def main():
    document = build()
    write(document)
    print('CHECKPOINT own turn-target bindings', len(document['missions']),
          'missions;', sum(map(len, document['missions'].values())), 'targets;',
          len(document['unresolved']), 'unresolved phase targets')


if __name__ == '__main__':
    main()
