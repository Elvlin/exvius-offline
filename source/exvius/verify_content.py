"""Check every package the client's resource tables list against the content the phone gets.

Sources: data/client/files (saved Global cache) and data/memorial_fill (fill_content_from_memorial).
Native movies and sound banks must have their original CRI headers. CPK event packages must contain
`<id>_event_text_sg.txt` covering all ids of `<id>_event_text.txt`, or the client shows
raw MAP_TEXT keys. Every speaker a scene names (`<name=N>`) must be a 3xxxxx id in its
`_event_teller` (looked up per scene) or in the shared common_teller (looked up bare), or the client shows MAP_TELLER_N. Prints totals and writes one JSON
line per package.

usage: verify_content.py OUT.jsonl
"""
import collections
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'tools/vendor/python'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cricodecs import cpk  # noqa: E402
from fill_content_from_memorial import (DATA, TEXT_TABLES, device_dir, localized_rows,
                                        scene_scoped, text_rows, wanted_files, rows)  # noqa: E402


@lru_cache(maxsize=1)
def development_packages():
    """Original editor packages with no mission or map-introduction reference."""
    names = {'debug_event.cpk', 'debug_event2.cpk', 'debug_event3.cpk',
             'ikai_TestEvent.cpk', '1002001test.cpk', 'effect1101.cpk',
             'debug_map.cpk', 'debug_town.cpk', 'soundroom.cpk',
             'scriptroom.cpk', 'test9901.cpk'}
    resources = {str(row['Nnb20keZ']): row['pJ56sAEo']
                 for row in rows('F_RESOURCE_MAP_MST.ndjson')
                 if row.get('pJ56sAEo') in names}
    referenced = {rid for table, field in (('F_MISSION_MST', 'q4f9IdMs'),
                                          ('F_MAP_EXT_RESOURCE_MST', 'Y4PER0gB'))
                  for row in rows(table + '.ndjson')
                  for rid in re.findall(r'\d+', str(row.get(field, '')))}
    return frozenset(name for rid, name in resources.items() if rid not in referenced)


def text_ids(data):
    ids = set()
    for line in data.decode('utf-8-sig', 'replace').splitlines():
        if line.strip():
            ids.add(line.split('^' if '^' in line else ',', 1)[0])
    return ids


def common_tellers():
    archive = cpk.load(str(DATA / 'client/files/common_lang/sd/common/Ver94_map_common_tutorial.cpk'))
    for index, entry in enumerate(archive.file_infos()):
        if entry.full_path == 'common_teller_sg.txt':
            return {i for i, cells in localized_rows(archive.file_bytes(index)).items()
                    if cells and cells[0].strip()}
    return set()


def common_npc_names():
    """English native NPC captions, including the generated localized extension."""
    labels = {r['key'].removeprefix('MST_NPC_NAME_'): r['v'][0]
              for r in map(json.loads, (DATA / 'text_decoded/F_TEXT_NPC_NAME.ndjson')
                           .read_text(encoding='utf8').splitlines())}
    reviewed = json.loads((PROJECT / 'source/server/content/dialogue_en.json').read_text(encoding='utf8'))
    labels.update({key: row['english'] for key, row in reviewed['npc_names'].items()})
    return {key for key, text in labels.items() if text.strip()
            and not re.search(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff\u3400-\u9fff\uac00-\ud7af]', text)}


def inspect(path, event, common=frozenset(), npc=None):
    if path.suffix == '.usm':
        with path.open('rb') as movie:
            return ([] if movie.read(4) == b'CRID' else
                    [{'kind': 'not a CRI movie'}]), 0
    if path.suffix in ('.acb', '.awb'):
        return ([] if path.read_bytes()[:4] in (b'@UTF', b'AFS2') else
                [{'kind': 'not a sound bank'}]), 0
    try:
        archive = cpk.load(str(path))
        members = {entry.full_path: index for index, entry in enumerate(archive.file_infos())}
    except Exception as exc:  # noqa: BLE001
        return [{'kind': 'unreadable', 'error': type(exc).__name__}], 0
    lines, issues = 0, []
    for name, index in members.items():
        if not any(name == s or name.endswith(s) for s in TEXT_TABLES):
            continue
        localized = name[:-len('.txt')] + '_sg.txt'
        if localized not in members:
            issues.append({'kind': 'no localized table', 'member': name})
            continue
        # Localized files also contain legacy multiline prose continuations.
        # Those are not native numeric text IDs and cannot be requested by a scene.
        base = {i: text for i, text in text_rows(archive.file_bytes(index)) if i.isdigit()}
        sg = {i: cells for i, cells in localized_rows(archive.file_bytes(members[localized])).items()
              if i.isdigit()}
        missing = sorted(base.keys() - sg.keys())
        if missing:
            issues.append({'kind': 'missing localized ids', 'member': localized, 'ids': missing})
        # An existing row with an empty English cell is not translated dialogue.
        # Empty teller captions and unused map editor labels are not dialogue.
        if name.endswith('_event_text.txt'):
            blank = sorted(i for i, text in base.items() if text.strip() and i in sg
                           and not (sg[i] and sg[i][0].strip()))
            if blank:
                issues.append({'kind': 'blank English dialogue', 'member': localized, 'ids': blank})
        untranslated = sorted(i for i, cells in sg.items() if cells and
                              re.search(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff\u3400-\u9fff\uac00-\ud7af]',
                                        re.sub(r'<[^>]+>', '', cells[0])))
        if untranslated:
            issues.append({'kind': ('non-English dialogue needs review' if name.endswith('_event_text.txt')
                                    else 'non-English map text or caption needs review'),
                           'member': localized, 'ids': untranslated})
        if npc is not None and name.endswith(('_event_text.txt', 'map_text.txt')):
            requested = {speaker for cells in sg.values() if cells
                         for speaker in re.findall(r'<name_npc=(\d+)>', cells[0])}
            if requested - npc:
                issues.append({'kind': 'unnamed native NPC captions', 'member': localized,
                               'ids': sorted(requested - npc)})
        lines += len(base)
        if name.endswith('_event_text.txt'):
            teller = members.get(name.replace('_event_text.txt', '_event_teller_sg.txt'))
            scene = (localized_rows(archive.file_bytes(teller)) if teller is not None else {})
            known = common | {i for i, cells in scene.items()
                              if scene_scoped(i) and cells and cells[0].strip()}
            named = {speaker for cells in sg.values() if cells
                     for speaker in re.findall(r'<name=(\d+)>', cells[0])}
            if named - known:
                issues.append({'kind': 'unnamed English speakers', 'member': localized,
                               'ids': sorted(named - known)})
    return issues, lines


def check(path, event, common=frozenset()):
    issues, lines = inspect(path, event, common)
    return ('; '.join(dict.fromkeys(i['kind'] for i in issues)) if issues else 'ok'), lines


def main():
    out = open(sys.argv[1], 'w', encoding='utf-8')
    totals, problems = collections.Counter(), collections.Counter()
    editor_issues = collections.Counter()
    dialogue = collections.Counter()
    common = common_tellers()
    npc = common_npc_names()
    for directory, name, version in wanted_files():
        relative = f'{device_dir(directory)}/Ver{version}_{name}'
        candidates = [('overlay', DATA / 'overlay/common_lang' / relative),
                      ('overlay', DATA / 'overlay/en' / relative),
                      ('global', DATA / 'client/files/common_lang' / relative),
                      ('global', DATA / 'client/files/en' / relative),
                      ('memorial', DATA / 'memorial_fill/common_lang' / relative),
                      ('memorial', DATA / 'memorial_fill/en' / relative)]
        if str(version) == '0':
            builtin = PROJECT / 'source/build/android/client/assets'
            candidates.extend((('apk', builtin / 'cpk/common_lang' / device_dir(directory) / name),
                               ('apk', builtin / 'cpk/en' / device_dir(directory) / name)))
            if directory.startswith('sound/'):
                candidates.append(('apk', builtin / 'android' / directory.split('/', 1)[1] / name))
        source, path = next(((s, p) for s, p in candidates if p.is_file()), ('missing', None))
        event = directory.split('/')[0].startswith('event')
        issues, lines = inspect(path, event, common, npc) if path else ([{'kind': 'missing'}], 0)
        status = '; '.join(dict.fromkeys(i['kind'] for i in issues)) if issues else 'ok'
        totals[source] += 1
        development = name in development_packages()
        if development and issues and all(i['kind'] == 'unnamed English speakers' for i in issues):
            editor_issues[status] += 1
        elif status != 'ok':
            problems[(source, status)] += 1
        dialogue[source] += lines
        out.write(json.dumps({'dir': directory, 'file': name, 'version': version,
                              'source': source, 'status': status, 'dialogue_lines': lines,
                              'development_only': development, 'issues': issues}) + '\n')
    total = sum(totals.values())
    print(f'packages listed {total}')
    for source in ('overlay', 'global', 'memorial', 'missing'):
        print(f'  {source:9s} {totals[source]:5d} ({100 * totals[source] / total:.1f}%)'
              + (f'  localized text lines {dialogue[source]}' if source != 'missing' else ''))
    print('problems:', dict(problems) or 'none')
    if editor_issues:
        print('unreferenced editor scenes:', dict(editor_issues))


if __name__ == '__main__':
    main()
