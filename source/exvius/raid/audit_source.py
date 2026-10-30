"""Read-only, streaming audit of data inside a pinned ZIP. No vendor imports."""
import argparse
import hashlib
import io
import json
import pathlib
import zipfile

EXPECTED = 'cb91b0cfea59f22285fa7c707d10adff5dd2561b014da66cb0c6af87c2eb489e'


def audit(archive, mission):
    digest = hashlib.file_digest(open(archive, 'rb'), 'sha256').hexdigest()
    if digest != EXPECTED:
        raise ValueError('Archive hash differs from pinned integration manifest')
    metadata = {}
    rows = {}
    with zipfile.ZipFile(archive) as z:
        def select(table, predicate):
            members = [n for n in z.namelist() if n.endswith('/server/content/battle/' + table + '.tsv')]
            if len(members) != 1:
                raise ValueError('Missing or ambiguous table: ' + table)
            count = 0
            picked = []
            h = hashlib.sha256()
            with z.open(members[0]) as raw:
                first = raw.readline()
                h.update(first)
                header = json.loads(first.decode('utf-8')[1:])
                for line in raw:
                    h.update(line)
                    cells = line.decode('utf-8').rstrip('\r\n').split('\t')
                    if len(cells) != len(header['fields']):
                        raise ValueError('Incorrect column count: ' + table)
                    row = dict(zip(header['fields'], (json.loads('"' + v + '"') if '\\' in v else v for v in cells)))
                    count += 1
                    if predicate(row):
                        picked.append(row)
            if count != header['rows']:
                raise ValueError('Header count mismatch: ' + table)
            metadata[table] = {'archive_member': members[0], 'rows_verified': count,
                               'tsv_sha256': h.hexdigest(), 'source_header': header}
            rows[table] = picked
            return picked
        phases = select('F_MISSION_PHASE_MST', lambda r: r['qo3PECw6'] == mission)
        if not phases:
            raise ValueError('Requested mission is absent')
        select('F_MISSION_MST', lambda r: r['qo3PECw6'] == mission)
        pools = {r['6uIYE15X'] for r in phases if r['gou39JeI'] == '2'}
        lottery = select('F_BATTLE_LOTTERY_MST', lambda r: r['c2gnh6Jd'] in pools and int(r['ixDq7yJ8'] or 0) > 0)
        groups = {r['2fY1IomW'] for r in lottery}
        slots = select('F_BATTLE_GROUP_MST', lambda r: r['2fY1IomW'] in groups)
        pids = {r['xqartN26'] for r in slots}
        monsters = select('F_MONSTER_MST', lambda r: r['xqartN26'] in pids)
        parts = select('F_MONSTER_PARTS_MST', lambda r: r['xqartN26'] in pids)
        setids = {r['A5x02C6a'] for r in parts} - {'', '0'}
        sets = select('F_MONSTER_SKILL_SET_MST', lambda r: r['A5x02C6a'] in setids)
        skillids = {v.strip() for r in sets for v in r['7qxLC5hP'].split(',') if v.strip()}
        skills = select('F_MONSTER_SKILL_MST', lambda r: r['6E5u1xrs'] in skillids)
        member = next(n for n in z.namelist() if n.endswith('/harness/break_status_community.json'))
        data = z.read(member)
        breaks = json.loads(data)
        missing = {
            'lottery_pools': sorted(pools - {r['c2gnh6Jd'] for r in lottery}),
            'groups': sorted(groups - {r['2fY1IomW'] for r in slots}),
            'monsters': sorted(pids - {r['xqartN26'] for r in monsters}),
            'parts': sorted(pids - {r['xqartN26'] for r in parts}),
            'skill_sets': sorted(setids - {r['A5x02C6a'] for r in sets}),
            'skills': sorted(skillids - {r['6E5u1xrs'] for r in skills}),
            'community_break_entries': sorted({r['xqartN26'] for r in parts if r['e56NZY42'] not in ('', '0')} - set(breaks['parts']))}
        return {'archive_sha256': digest, 'mission_id': mission,
                'raid_classification': 'UNVERIFIED: this is an encounter reference, not asserted to be a raid',
                'runtime_status': 'data audited only; no vendor code executed',
                'tables': metadata, 'selected_rows': rows, 'missing_references': missing,
                'all_lottery_candidates_included': True,
                'community_break_source': {'member': member, 'sha256': hashlib.sha256(data).hexdigest(),
                   'parts': {p: breaks['parts'][p] for p in sorted(pids) if p in breaks['parts']}},
                'limits': ['AI not interpreted', 'Skill semantics not simulated',
                           'Raid global HP, rank, reward schedules not verified',
                           'Asset/client compatibility and combat untested']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive')
    p.add_argument('--mission', default='8960101')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    pathlib.Path(args.output).write_text(json.dumps(audit(args.archive, args.mission), ensure_ascii=False, indent=2) + '\n')
