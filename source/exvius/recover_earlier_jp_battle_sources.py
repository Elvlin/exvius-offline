"""Recover owned native support for the exact earlier JP battle source gaps.

This is offline source authoring. It does not activate events, fabricate enemy
stats, change a source row, substitute a Global enemy or build an APK. Missing
body/part rows remain explicit blockers. Same-ID support is a recovery candidate,
not proof of its original Japanese version or the missing part's pointers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / 'Japan content'
EARLIER = CONTENT / 'Earlier JP crossovers'
APK_SHA256 = '3625b1e6c423d1c4dfdb54172d8f512444314bd2dd9065d67e32adb45061b531'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_rows(path):
    raw = path.read_bytes()
    return raw, [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]


def collect():
    evidence_path = EARLIER / 'stage-gap-evidence.json'
    evidence_bytes = evidence_path.read_bytes()
    evidence = json.loads(evidence_bytes)
    if evidence['summary']['apk_sha256'] != APK_SHA256:
        raise ValueError('Stage analysis is for another APK; re-derive its exact source graph first.')
    missing = set(evidence['summary']['missing_monster_ids'])
    model_prefixes = {ident[:-2] for ident in missing}
    if missing != set(evidence['summary']['missing_part_ids']):
        raise ValueError('Monster and part gaps differ; a new targeted source selection is required.')
    inputs = [{'path': evidence_path.relative_to(ROOT).as_posix(), 'sha256': digest(evidence_bytes)}]
    raw_base = CONTENT / 'Shared sources/memorial_battle_decoded'
    recovered = {}
    remaining = {}
    for table in ('F_MONSTER_MST', 'F_MONSTER_PARTS_MST'):
        path = raw_base / (table + '.ndjson')
        raw, rows = read_rows(path)
        selected = [row for row in rows if row['xqartN26'] in missing]
        recovered[table] = selected
        remaining[table] = sorted(missing - {row['xqartN26'] for row in selected}, key=int)
        inputs.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(raw)})
    for table, key in (('F_AI_MST', '8a6gAwN9'),
                       ('F_MONSTER_SKILL_SET_MST', 'A5x02C6a')):
        path = ROOT / 'data/mst_decoded' / (table + '.ndjson')
        raw, rows = read_rows(path)
        recovered[table] = [row for row in rows if row[key] in missing or row[key][:-2] in model_prefixes]
        inputs.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(raw)})
    wanted = {skill.strip() for row in recovered['F_MONSTER_SKILL_SET_MST']
              for skill in row['7qxLC5hP'].split(',') if skill.strip()}
    path = raw_base / 'F_MONSTER_SKILL_MST.ndjson'
    raw, rows = read_rows(path)
    recovered['F_MONSTER_SKILL_MST'] = [row for row in rows if row['6E5u1xrs'] in wanted]
    absent_skills = sorted(wanted - {row['6E5u1xrs'] for row in recovered['F_MONSTER_SKILL_MST']}, key=int)
    inputs.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(raw)})
    jp_path = CONTENT / 'Shared sources/ffbe-jp-ea7d9fa82659.zip'
    raw = jp_path.read_bytes()
    with zipfile.ZipFile(jp_path) as archive:
        community = {}
        for table in ('monster_ai', 'monster_skillsets'):
            member = next(name for name in archive.namelist() if name.endswith('/' + table + '.json'))
            document = json.loads(archive.read(member))
            community[table] = {ident: document[ident] for ident in sorted(document, key=int)
                                if ident in missing or ident[:-2] in model_prefixes}
    inputs.append({'path': jp_path.relative_to(ROOT).as_posix(), 'sha256': digest(raw)})
    report = {
        'classification': 'Owned original native support candidates. Inactive; original body/part source gaps remain.',
        'apk_sha256': APK_SHA256,
        'source_inputs': inputs,
        'missing_original_enemy_identities': len(missing),
        'owned_monster_rows_recovered': len(recovered['F_MONSTER_MST']),
        'owned_part_rows_recovered': len(recovered['F_MONSTER_PARTS_MST']),
        'remaining_original_body_ids': remaining['F_MONSTER_MST'],
        'remaining_original_part_ids': remaining['F_MONSTER_PARTS_MST'],
        'owned_native_AI_IDs': len({row['8a6gAwN9'] for row in recovered['F_AI_MST']}),
        'owned_native_AI_rows': len(recovered['F_AI_MST']),
        'owned_native_same_ID_skillset_rows': len(recovered['F_MONSTER_SKILL_SET_MST']),
        'owned_native_direct_skill_rows': len(recovered['F_MONSTER_SKILL_MST']),
        'missing_direct_skill_ids': absent_skills,
        'stage_activation_ready': False,
        'reason': 'The source part rows carry HP, MP, ATK, DEF, MAG, SPR, level, resistances, AI and skill-set pointers, drops and multipart behavior. These fields cannot be invented from model files, enemy names or same-ID skill lists.',
        'version_limit': 'AI and skill support is retained in its existing native source version. The original missing Japanese part pointers and cross-version equivalence have not been recovered.',
        'runtime_changes': False,
        'enemy_substitutions': False,
    }
    return recovered, community, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=EARLIER / 'Sources/Battle recovery')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to((EARLIER / 'Sources').resolve()):
        raise ValueError('Write only to this task\'s original-source recovery folder.')
    recovered, community, report = collect()
    out.mkdir(parents=True, exist_ok=True)
    outputs = []
    for table, rows in recovered.items():
        if not rows:
            continue
        payload = ''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n'
                          for row in rows).encode('utf-8')
        target = out / (table + '.ndjson')
        target.write_bytes(payload)
        outputs.append({'file': target.name, 'rows': len(rows), 'bytes': len(payload), 'sha256': digest(payload)})
    target = out / 'community-support-candidates.json'
    payload = (json.dumps({'classification': 'Parsed community data, not native bodies or source-version equivalence.',
                          'selected': community}, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    target.write_bytes(payload)
    outputs.append({'file': target.name, 'bytes': len(payload), 'sha256': digest(payload)})
    report['outputs'] = outputs
    (out / 'recovery-status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for entry in outputs:
        if digest((out / entry['file']).read_bytes()) != entry['sha256']:
            raise ValueError('Recovered source readback differs: ' + entry['file'])
    print(json.dumps({key: report[key] for key in ('owned_monster_rows_recovered', 'owned_part_rows_recovered',
          'owned_native_AI_IDs', 'owned_native_AI_rows', 'owned_native_same_ID_skillset_rows',
          'owned_native_direct_skill_rows', 'missing_direct_skill_ids', 'stage_activation_ready')}, sort_keys=True))


if __name__ == '__main__':
    main()
