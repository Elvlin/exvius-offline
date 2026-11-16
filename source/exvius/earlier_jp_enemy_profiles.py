"""Estimate missing earlier-JP enemy numbers from dated native combat cohorts.

These are authored estimates, not recovered enemy records. This module reads
original native tables and documented observations only. It imports no gameplay
runtime, changes no AI, graphics, resistance or reward fields, and writes nothing.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import re
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'Japan content/Earlier JP crossovers'
ORIGINAL = ROOT / 'Japan content/Shared sources/memorial_battle_decoded'
TOKENS = {'HP': 'fh31sk7B', 'MP': 'PC97pWQj', 'ATK': '9NBV1XCS',
          'DEF': 'Pn5w9dfh', 'MAG': '84FJM3PD', 'SPR': 'T8xMDAZ4',
          'level': '7wV3QZ80'}
NONCOMBAT_NAME = re.compile(
    r'サボテンダ|ジャボテン|ミニテン|ギルガメ|ポット|もぐり|モーグリ|'
    r'cactuar|gil snapper|metal minituar|burst pot|king pot', re.I)


def _json(path):
    return json.loads(path.read_text(encoding='utf8'))


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def _index(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def _encounters(folder):
    missions = {row['qo3PECw6']: row for row in _rows(folder / 'F_MISSION_MST.ndjson')}
    phases = _index(_rows(folder / 'F_MISSION_PHASE_MST.ndjson'), 'qo3PECw6')
    lotteries = _index(_rows(folder / 'F_BATTLE_LOTTERY_MST.ndjson'), 'c2gnh6Jd')
    groups = _index(_rows(folder / 'F_BATTLE_GROUP_MST.ndjson'), '2fY1IomW')
    result = []
    for mid, mission in missions.items():
        combat = [p for p in phases[mid] if p.get('gou39JeI') == '2']
        final = max((int(p['6v7y3QcJ']) for p in combat), default=-1)
        for phase in combat:
            role = 'final_wave' if int(phase['6v7y3QcJ']) == final else 'normal_wave'
            for lottery in lotteries[phase['6uIYE15X']]:
                for slot in groups[lottery['2fY1IomW']]:
                    result.append((mid, slot['xqartN26'], role))
    return missions, result


def _offensive_fingerprint(skill_ids, skills):
    """Classify retained direct damage, without guessing an archetype from names."""
    physical, magical, hybrid, unresolved, opcodes = [], [], [], [], set()
    seen = set()
    pending = list(skill_ids)
    while pending:
        sid = pending.pop()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        skill = skills.get(sid)
        if skill is None:
            unresolved.append(sid)
            continue
        commands = skill.get('2kq0BpnD', '').split('@')
        opcodes.update(commands)
        if '1' in commands:
            physical.append(sid)
        if '15' in commands:
            magical.append(sid)
        if '40' in commands:
            hybrid.append(sid)
        # Native random casts use childID&chance operands. Follow only children
        # actually present in this same original skill table.
        for command, params in zip(commands, skill.get('Ha9G5sCS', '').split('@')):
            if command == '29':
                for field in params.split(','):
                    child = field.split('&')[0]
                    if child in skills:
                        pending.append(child)
    if hybrid or (physical and magical):
        archetype = 'mixed'
    elif physical:
        archetype = 'physical'
    elif magical:
        archetype = 'magical'
    elif unresolved or not seen or opcodes.intersection({'29', '99', '100'}):
        archetype = 'unresolved'
    else:
        archetype = 'support_or_indirect'
    return {'archetype': archetype, 'physical_skill_ids': sorted(physical, key=int),
            'magical_skill_ids': sorted(magical, key=int), 'hybrid_skill_ids': sorted(hybrid, key=int),
            'unresolved_skill_ids': sorted(unresolved), 'opcodes': sorted(opcodes),
            'basis': 'Direct native physical1, magical15 and hybrid40 effect opcodes; no name-based role inference. Support_or_indirect means no such direct-damage opcode observed, not proof that all other mechanics are nondamaging.'}


def _skill_fingerprints(folder):
    skills = {r['6E5u1xrs']: r for r in _rows(folder / 'F_MONSTER_SKILL_MST.ndjson')}
    sets = {r['A5x02C6a']: r for r in _rows(folder / 'F_MONSTER_SKILL_SET_MST.ndjson')}
    return skills, sets


def _event_kind(event):
    text = (event.get('kind', '') + ' ' + event.get('name', '')).casefold()
    if any(term in text for term in ('challenge', 'trial', 'chronicle', 'crown',
                                     'boss rush', 'scorn', 'purgatory', 'extreme weapon')):
        return 'challenge'
    if 'raid' in text:
        return 'raid'
    if any(term in text for term in ('ranking', 'dark visions', 'clash of wills')):
        return 'ranking'
    if any(term in text for term in ('character battle', 'unit strengthening', 'training')):
        return 'training'
    if 'story' in text:
        return 'story'
    return 'event'


def _dated_native_observations():
    """Crosswalk archived release dates to original encounter IDs, then join bodies."""
    missions, encounters = _encounters(ORIGINAL)
    monsters = {r['xqartN26']: r for r in _rows(ORIGINAL / 'F_MONSTER_MST.ndjson')}
    parts = {r['xqartN26']: r for r in _rows(ORIGINAL / 'F_MONSTER_PARTS_MST.ndjson')
             if r['6Yc4RkdM'] == '1'}
    skills, sets = _skill_fingerprints(ORIGINAL)
    fingerprints = {sid: _offensive_fingerprint(row['7qxLC5hP'].split(','), skills)
                    for sid, row in sets.items()}
    archive = _json(ROOT / 'source/server/event_archive.json')['events']
    crosswalk = _json(ROOT / 'source/server/event_battles.json')['missions']
    years = defaultdict(set)
    target_years = defaultdict(set)
    kinds = defaultdict(list)
    target_kinds = defaultdict(list)
    for event in archive:
        match = re.match(r'(\d{4})', event.get('release') or '')
        if not match:
            continue
        year = int(match[1])
        kind = _event_kind(event)
        for mid in event['missions']:
            target_years[mid].add(year)
            target_kinds[mid].append((year, kind))
            source = crosswalk.get(mid, {}).get('source', mid)
            if source in missions:
                years[source].add(year)
                kinds[source].append((year, kind))
    observations = []
    seen = set()
    for mid, iid, role in encounters:
        if mid not in years or iid not in parts or iid not in monsters or int(iid) >= 800000000:
            continue
        part = parts[iid]
        if NONCOMBAT_NAME.search(monsters[iid]['G4L0YIB2']):
            continue
        if any(not str(part.get(token, '')).isdigit() or int(part[token]) <= 0
               for token in TOKENS.values()):
            continue
        # Tiny-HP economic/training/puzzle actors must not become raid/boss donors.
        if int(part[TOKENS['HP']]) < 1000 or int(part[TOKENS['level']]) < 2:
            continue
        key = (mid, iid, role)
        if key in seen:
            continue
        seen.add(key)
        observations.append({
            'enemy': iid, 'mission': mid, 'year': min(years[mid]), 'role': role,
            'graphic': monsters[iid]['V9j8wJcC'],
            'difficulty': max(1, int(missions[mid].get('52KBR9qV') or 1)),
            'event_kind': min(kinds[mid])[1],
            'race': part.get('a9qg8vnP', ''),
            'offensive_archetype': fingerprints.get(part.get('A5x02C6a'), {}).get('archetype', 'unresolved'),
            **{name: int(part[token]) for name, token in TOKENS.items()},
        })
    return observations, target_years, target_kinds


def _cohort(observations, target, exact):
    same_role = [o for o in observations if o['role'] == target['role']]
    pool, era_width = [], 0
    # Select an era first. A newer quest with the same printed difficulty is not
    # an interchangeable combat profile for an early collaboration.
    for width in (1, 2, 3, 5, 20):
        pool = [o for o in same_role if abs(o['year'] - target['year']) <= width]
        if len({o['enemy'] for o in pool}) >= 5:
            era_width = width
            break
    event_pool = [o for o in pool if o['event_kind'] == target['event_kind']]
    event_matched = len({o['enemy'] for o in event_pool}) >= 5
    if event_matched:
        pool = event_pool
    races = set(target['race'].split(',')) - {''}
    racial = [o for o in pool if races.intersection(o['race'].split(','))]
    same_race = len({o['enemy'] for o in racial}) >= 5
    if same_race:
        pool = racial
    known_level = exact.get('level')
    if known_level:
        for width in (max(10, known_level * .25), max(25, known_level * .5)):
            close = [o for o in pool if abs(o['level'] - known_level) <= width]
            if len({o['enemy'] for o in close}) >= 5:
                pool = close
                break
    difficulty_window = max(10, target['difficulty'] * .5)
    close_difficulty = [o for o in pool if abs(o['difficulty'] - target['difficulty']) <= difficulty_window]
    difficulty_matched = len({o['enemy'] for o in close_difficulty}) >= 5
    if difficulty_matched:
        pool = close_difficulty
    matching_attack = [o for o in pool if o['offensive_archetype'] == target['offensive_archetype']]
    matching_attack_count = len({o['enemy'] for o in matching_attack})
    attack_matched = target['offensive_archetype'] != 'unresolved' and matching_attack_count >= 5
    if attack_matched:
        pool = matching_attack
    def distance(o):
        score = abs(math.log1p(o['difficulty']) - math.log1p(target['difficulty']))
        score += .35 * abs(o['year'] - target['year'])
        if known_level:
            score += 2 * abs(math.log1p(o['level']) - math.log1p(known_level))
        if exact.get('hp'):
            score += .75 * abs(math.log(o['HP']) - math.log(exact['hp']))
        return score
    # Repeated appearances of one enemy are one donor, never nine votes.
    unique = {}
    for row in pool:
        old = unique.get(row['enemy'])
        if old is None or (distance(row), row['mission']) < (distance(old), old['mission']):
            unique[row['enemy']] = row
    ordered = sorted(unique.values(), key=lambda o: (distance(o), int(o['enemy'])))
    by_model = {}
    for row in ordered:
        by_model.setdefault(row['graphic'], row)
    model_diverse = len(by_model) >= 5
    donors = list(by_model.values())[:9] if model_diverse else ordered[:9]
    if len(donors) < 5:
        raise ValueError('Fewer than five independent native numeric donors: ' + target['enemy'])
    values = {name: max(1, round(median(o[name] for o in donors))) for name in TOKENS}
    return values, {'era_window_years': era_width, 'race_matched': same_race,
                    'event_kind_matched': event_matched,
                    'nearby_difficulty_matched': difficulty_matched,
                    'independent_model_diversity': model_diverse,
                    'offensive_archetype_matched': attack_matched,
                    'same_archetype_unique_donors': matching_attack_count,
                    'archetype_fallback': None if attack_matched else 'Retained skill fingerprint unresolved or fewer than five independent same-archetype donors in the evidenced era/race/wave cohort.',
                    'eligible_unique_donors': len(unique), 'donors': donors,
                    'method': 'Median of up to nine independent original-native numeric donors, conditioned on era, archived event kind, final/normal wave, race and retained-skill offensive archetype where supported, log difficulty, and observed enemy level/HP where known.'}


def _interpolate(points, at):
    points = sorted(points)
    if at <= points[0][0]:
        return points[0][1]
    if at >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= at <= x1:
            return y0 + (y1 - y0) * (at - x0) / max(1e-9, x1 - x0)
    raise AssertionError('Interpolation interval missing')


def build_profiles(references, unit_graphics=()):
    """Return enemy -> authored native numeric fields and source/estimation trace.

    ``references`` is the generator's verified published HP/MP/level dictionary.
    ``unit_graphics`` excludes the already verified same-unit training profiles.
    No resistance, AI, model, race, rewards or presentation fields are returned.
    """
    observations, years, kinds = _dated_native_observations()
    missions, encounters = _encounters(BASE / 'Sources/Event graph')
    evidence = _json(BASE / 'stage-gap-evidence.json')
    missing = set(evidence['summary']['missing_monster_ids'])
    target_skills, target_sets = _skill_fingerprints(BASE / 'Sources/Battle recovery')
    sets_by_graphic = defaultdict(list)
    for sid in target_sets:
        sets_by_graphic[sid[:-2]].append(sid)
    contexts = defaultdict(list)
    for mid, iid, role in encounters:
        if iid in missing:
            contexts[iid].append((mid, role))
    targets, groups = {}, defaultdict(list)
    for iid in sorted(missing, key=int):
        candidate = evidence['missing_body_dictionary_candidates'][iid]
        graphic = candidate['candidate_graphic_id']
        if graphic in unit_graphics:
            continue
        uses = contexts[iid]
        owned = sorted({mid for mid, _ in uses}, key=int)
        dates = {year for mid in owned for year in years.get(mid, ())}
        if not dates:
            raise ValueError('Earlier JP enemy lacks an evidenced event year: ' + iid)
        role = 'final_wave' if any(r == 'final_wave' for _, r in uses) else 'normal_wave'
        areas = tuple(sorted({missions[mid]['uv60hgDW'] for mid in owned}, key=int))
        target = {'enemy': iid, 'graphic': graphic, 'race': candidate['dictionary_row']['a9qg8vnP'],
                  'year': min(dates), 'role': role, 'missions': owned, 'areas': areas,
                  'event_kind': min(pair for mid in owned for pair in kinds[mid])[1],
                  'difficulty': max(int(missions[mid]['52KBR9qV']) for mid in owned)}
        # A tier's exact-ID set can be a tail retreat set. Classify all retained
        # same-graphic sets together instead of treating an unverified pointer
        # as the original actor's offensive role.
        family_sets = sorted(sets_by_graphic[graphic], key=int)
        fingerprint = _offensive_fingerprint(
            {sid for set_id in family_sets for sid in target_sets[set_id]['7qxLC5hP'].split(',') if sid},
            target_skills)
        target['offensive_archetype'] = fingerprint['archetype']
        target['offensive_fingerprint'] = dict(fingerprint, source_skillsets=family_sets)
        exact = references.get(iid) or {}
        values, trace = _cohort(observations, target, exact)
        targets[iid] = {'target': target, 'baseline': values, 'values': dict(values), 'cohort': trace,
                        'exact': {name: exact[key] for name, key in (('HP', 'hp'), ('MP', 'mp'), ('level', 'level')) if key in exact}}
        # Do not carry a boss's 2022 curve into its independent 2024 event.
        groups[(graphic, areas)].append(iid)
    for family in groups.values():
        ordered = sorted(family, key=lambda iid: (targets[iid]['target']['difficulty'], int(iid)))
        anchor_ids = [iid for iid in ordered if 'HP' in targets[iid]['exact']]
        for iid in ordered:
            targets[iid]['published_anchor'] = anchor_ids
        # Empirical native medians define the baseline curve, not difficulty^2.
        last = {name: 1 for name in TOKENS}
        for iid in ordered:
            for name in TOKENS:
                last[name] = max(last[name], targets[iid]['values'][name])
                targets[iid]['values'][name] = last[name]
        anchors = [(math.log1p(targets[iid]['target']['difficulty']),
                    math.log(targets[iid]['exact']['HP'] / targets[iid]['values']['HP']))
                   for iid in ordered if 'HP' in targets[iid]['exact']]
        if anchors:
            for iid in ordered:
                row = targets[iid]
                row['values']['HP'] = max(1, round(row['values']['HP'] * math.exp(_interpolate(anchors, math.log1p(row['target']['difficulty'])))))
        for name in TOKENS:
            last = 1
            for index, iid in enumerate(ordered):
                row = targets[iid]
                if name in row['exact']:
                    row['values'][name] = row['exact'][name]
                else:
                    following = [targets[j]['exact'][name] for j in ordered[index + 1:] if name in targets[j]['exact']]
                    value = max(last, row['values'][name])
                    row['values'][name] = min(value, following[0]) if following else value
                last = row['values'][name]
    result = {}
    for iid, row in targets.items():
        result[iid] = {'native_fields': {TOKENS[name]: str(value) for name, value in row['values'].items()},
                       'trace': {'classification': 'Documented authored combat estimates; published anchors remain observed values, not recovered server records.',
                                 'target': row['target'], 'published_numeric_anchors': row['exact'],
                                 'published_anchor': row['published_anchor'],
                                 'estimated_fields': [name for name in TOKENS if name not in row['exact']],
                                 'raw_cohort_medians': row['baseline'], 'cohort': row['cohort'],
                                 'family_curve': 'Nondecreasing per-field curve within same graphic and event-area context. Published HP calibrates empirical native HP ratios in log space; known HP/MP/level remain exact.',
                                 'source_numeric_observations': len(observations)}}
    return result
