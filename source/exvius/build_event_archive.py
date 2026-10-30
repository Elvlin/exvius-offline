"""Join original Global Vortex masters to the preserved, dated wiki archive."""
from collections import defaultdict
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from gacha_archive import STORY_STARTS, COLLABORATIONS

SOURCE = ROOT / 'logs/reference/events-archives-wiki-20261026.json'


def normal(value):
    text = unicodedata.normalize('NFKD', value).casefold().replace('&', 'and')
    return re.sub(r'[^a-z0-9]', '', text)


def rows(table, text=False):
    directory = 'text_decoded' if text else 'mst_decoded'
    return [json.loads(line) for line in (ROOT / 'data' / directory / (table + '.ndjson')).read_text(encoding='utf-8').splitlines()]


def first_date(value):
    numeric = re.search(r'(\d{1,2})/(\d{1,2})/(20\d{2})', value)
    if numeric:
        month, day, year = map(int, numeric.groups())
        return date(year, month, day)
    named = re.search(r'([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})', value)
    if named:
        months = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
        month = months.index(named[1][:3].lower()) + 1
        return date(int(named[3]), month, int(named[2]))
    return None


def archive_records(document):
    result = defaultdict(list)
    for block in re.findall(r'\{\{Recent Event\b(.*?)\}\}', document['text'], re.S):
        row = dict((key.strip(), value.strip()) for key, value in
                   re.findall(r'^\s*\|\s*(\w+)\s*=\s*(.*?)\s*$', block, re.M))
        if not row.get('name'):
            continue
        row['release'] = first_date(row.get('duration', ''))
        for title in {row['name'], row.get('link', ''), re.sub(r'\s*\(Rerun\)\s*$', '', row['name'], flags=re.I)}:
            if title:
                result[normal(title)].append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-unidentified', action='store_true',
                        help='Include unused/unidentified master entries for source recovery only')
    args = parser.parse_args()
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    archive = archive_records(source)
    names = {row['key'].rsplit('_', 1)[1]: row['v'][0] for row in rows('F_TEXT_AREA_NAME', text=True)}
    mission_names = {row['key'].rsplit('_', 1)[1] for row in rows('F_TEXT_MISSION', text=True)}
    missions = [row for row in rows('F_MISSION_MST') if row['qo3PECw6'] in mission_names]
    by_dungeon = defaultdict(list)
    for mission in missions:
        by_dungeon[mission['U9iHsau3']].append(mission)
    dungeons = defaultdict(list)
    for dungeon in rows('F_DUNGEON_MST'):
        if by_dungeon[dungeon['U9iHsau3']]:
            dungeons[dungeon['uv60hgDW']].append(dungeon)
    originals = json.loads((ROOT / 'source/server/event_art.json').read_text(encoding='utf-8'))['events']
    events = []
    for area in rows('F_AREA_MST'):
        aid = area['uv60hgDW']
        if area.get('Esxe71j3') != '21' or aid not in names or not dungeons[aid]:
            continue
        # English master text also contains unused and JP-only areas. A
        # recovered Global event picture establishes the browsable campaign.
        if not args.include_unidentified and aid not in originals:
            continue
        own_dungeons = dungeons[aid]
        own_missions = [mission for dungeon in own_dungeons for mission in by_dungeon[dungeon['U9iHsau3']]]
        modes = {row['gQR24kST'] for row in own_missions}
        name = (names[aid] if '12' in modes or '50' in modes else
                originals.get(aid, {}).get('name') or names[aid])
        candidates = archive.get(normal(name), []) or archive.get(normal(names[aid]), [])
        if not candidates:
            parent = re.sub(r'\s*[-:]\s*(?:Trial|Exploration|Challenge)\s*$', '', name, flags=re.I)
            candidates = archive.get(normal(parent), [])
        dated = [record for record in candidates if record['release']]
        record = min(dated, key=lambda row: row['release']) if dated else (candidates[0] if candidates else {})
        release = record.get('release')
        kind = record.get('type', '')
        collaboration = next((series for series in COLLABORATIONS if normal(series) in normal(kind + ' ' + name)), None)
        permanent = (name in ('Dark Visions', 'Clash of Wills') or
                     not release and (name.startswith(('Chamber of ', 'Training ', 'The Farplane')) or
                     name in ('Daily Fragment Challenge', 'Steel Castle Melfikya')))
        group = ('permanent' if permanent else 'collaborations' if collaboration else
                 'season' + str(1 + sum(release >= start for start in STORY_STARTS)) if release else 'other')
        raid = any(row.get('gQR24kST') == '2' for row in own_missions)
        banner = record.get('banner') or name
        event = {'area': aid, 'name': name, 'group': group,
                 'release': release.isoformat() if release else None,
                 'kind': 'raid' if raid else kind or 'Vortex event',
                 'collaboration': collaboration,
                 'dungeons': [row['U9iHsau3'] for row in own_dungeons],
                 'missions': [row['qo3PECw6'] for row in own_missions],
                 'first_dungeon': own_dungeons[0]['U9iHsau3'],
                 'first_mission': by_dungeon[own_dungeons[0]['U9iHsau3']][0]['qo3PECw6'],
                 'banner_title': 'File:Banner-' + banner + '.png',
                 'filename': originals.get(aid, {}).get('filename') or 'event_' + aid + '.png',
                 'source_page': originals.get(aid, {}).get('source_page') or
                     'https://exvius.fandom.com/wiki/' + record.get('link', name).replace(' ', '_'),
                 'date_source': source['source'] if release else None}
        if modes == {'50'}:
            event['native_mode'] = 'tfa'
        elif '12' in modes and modes <= {'0', '12'}:
            event['native_mode'] = 'parade'
        if event.get('native_mode') == 'tfa' or (event.get('native_mode') == 'parade' and name == 'Dark Visions'):
            title = 'Clash of Wills' if event['native_mode'] == 'tfa' else 'Dark Visions'
            event.update(name=title, group='permanent', release=None,
                         banner_title='File:Banner-' + title + '.png',
                         source_page=('https://exvius.fandom.com/wiki/Category:Clash_of_Wills' if title == 'Clash of Wills'
                                      else 'https://exvius.fandom.com/wiki/Dark_Visions_-_The_Advent_of_Chaos'))
        events.append(event)
    events.sort(key=lambda row: (row['release'] or '', row['name'], int(row['area'])))
    document = {'version': 1, 'source_revision': source['revision'],
                'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'events': events}
    output = ROOT / 'source/server/event_archive.json'
    output.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Indexed', len(events), 'original Global Vortex areas;', sum(bool(row['release']) for row in events), 'dated;',
          sum(row['kind'] == 'raid' for row in events), 'raids')


if __name__ == '__main__':
    main()
