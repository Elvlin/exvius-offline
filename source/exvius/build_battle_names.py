"""Build native fallback captions for the battle data actually served offline."""
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from battle_content import IndexSource, resolve_pool


def main():
    source = IndexSource()
    skills = {r['6E5u1xrs']: r for r in source.load('F_MONSTER_SKILL_MST')}
    sets = {r['A5x02C6a']: r for r in source.load('F_MONSTER_SKILL_SET_MST')}
    phases, pools, groups, parts = (defaultdict(list) for _ in range(4))
    for table, token, destination in [('F_MISSION_PHASE_MST', 'qo3PECw6', phases),
                                     ('F_BATTLE_LOTTERY_MST', 'c2gnh6Jd', pools),
                                     ('F_BATTLE_GROUP_MST', '2fY1IomW', groups),
                                     ('F_MONSTER_PARTS_MST', 'xqartN26', parts)]:
        for row in source.load(table):
            destination[row[token]].append(row)
    monster_names, used_skills, used_parts = {}, set(), set()
    for filename in ['event_battles.json', 'event_encounters.json', 'colosseum_encounters.json']:
        data = json.loads((ROOT / 'source/server' / filename).read_text(encoding='utf8'))
        monster_names.update(data.get('local_monster_names', {}))
        support = data.get('native_battle_support', {})
        skills.update({r['6E5u1xrs']: r for r in support.get('F_MONSTER_SKILL_MST', [])})
        sets.update({r['A5x02C6a']: r for r in support.get('F_MONSTER_SKILL_SET_MST', [])})
        for record in data.get('missions', {}).values():
            bundle = record.get('bundle', {})
            for row in bundle.get('Wp39QX52', []):
                skills[row['6E5u1xrs']] = row
                used_skills.add(row['6E5u1xrs'])
            if record.get('source'):
                for phase in phases[str(record['source'])]:
                    if phase.get('gou39JeI') != '2':
                        continue
                    pool = resolve_pool(pools[phase['6uIYE15X']], phase['6uIYE15X'])
                    if pool:
                        used_parts.update(r['xqartN26'] for r in groups[pool[0]])
    for pid in used_parts:
        for part in parts[pid]:
            row = sets.get(part.get('A5x02C6a'), {})
            used_skills.update(filter(None, row.get('7qxLC5hP', '').split(',')))
    original = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in map(json.loads,
                (ROOT / 'data/text_decoded/F_TEXT_MONSTER_SKILL_NAME.ndjson').read_text(encoding='utf8').splitlines())}
    translations = json.loads((ROOT / 'source/server/content/battle_skill_translations.json').read_text(encoding='utf8'))['names']
    captions, missing = {}, {}
    for sid in sorted(used_skills):
        name = original.get(sid) or skills.get(sid, {}).get('G4L0YIB2', '')
        name = translations.get(name, name)
        if not name or re.search('[\u3040-\u30ff\u3400-\u9fff]', name):
            missing[sid] = name
        else:
            captions[sid] = name
    if missing:
        (ROOT / 'logs/reference/battle-skill-name-gaps-20261029.json').write_text(
            json.dumps(missing, ensure_ascii=False, indent=1), encoding='utf8')
        raise ValueError('Untranslated used battle skills: ' + str(len(missing)))
    output = {'monster': monster_names, 'skill': captions}
    (ROOT / 'source/server/battle_names.json').write_text(
        json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    print('Native battle fallback captions:', len(monster_names), 'enemies,', len(captions), 'skills.')


if __name__ == '__main__':
    main()
