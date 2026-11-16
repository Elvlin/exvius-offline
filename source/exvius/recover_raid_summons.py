"""Extract raid summon evidence without filling missing historical probabilities.

Uses the retained MediaWiki revisions and the existing raid reward text parser.
The result is a recovery dataset, not a runtime summon catalogue. Survey odds,
unknown slot counts and missing reward identities remain explicitly unresolved.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

from build_raid_archive import plain

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    'logs/reference/raids/archive-raids-wiki-20261026.json',
    'logs/reference/raids/raid-summon-subpages-20261109.json',
    'logs/reference/raids/raid-summon-extra-20261109.json',
    'logs/reference/raids/power-of-destruction-boxes-wiki.json',
]
OUTPUT = 'logs/raid-summon-recovery-20261109.json'
RESEARCH = [
    {'repository': 'aEnigmatic/ffbe', 'evidence': 'Pinned local snapshot: summons.json contains esper records, not gacha pools.'},
    {'repository': 'aEnigmatic/ffbe-jp', 'commit': 'ea7d9fa82659e66fed1a0a5dba4616089cc807dc',
     'evidence': 'Complete 32-entry repository tree: summons files are esper data; no gacha table or response capture.'},
    {'repository': 'ForkGang/ffbe-jp', 'commit': '3a49df29682c46074764e37b7bca77c5a43cfac9',
     'evidence': 'Complete 32-entry repository tree: no gacha probability table or response capture.'},
    {'repository': 'nathypooh/BraveHaxvius', 'commit': 'd8ae103c43caeaaa78b72cfaa629af2a81b09424',
     'evidence': 'DataExtractor/response.json maps obfuscated tags to class names; it is not a captured banner or rate response.'},
    {'repository': 'TBMonkey/ffbe-gl-server', 'evidence': 'Pinned snapshot contains authored gacha catalogues. Original response fixtures do not contain raid pool weights.'},
    {'repository': 'Hirurawa/ExviusReborn', 'evidence': 'Own Godot reconstruction. Search did not locate original raid probability records.'},
    {'repository': 'DanUgore/ffbe_data', 'evidence': 'Extracted client data repository and documented file list; no original raid rate table found.'},
    {'repository': 'librariansstudio/curl-ffbe-jp-dumper', 'evidence': 'Extraction tool; no preserved probability data located.'},
]


def source_pages():
    pages, provenance = {}, []
    for name in SOURCES:
        path = ROOT / name
        if not path.exists():
            continue
        raw = path.read_bytes()
        provenance.append({'file': name, 'sha256': hashlib.sha256(raw).hexdigest()})
        doc = json.loads(raw)
        for batch in doc if isinstance(doc, list) else [doc]:
            for page in batch.get('query', {}).get('pages', {}).values():
                rev = (page.get('revisions') or [{}])[0]
                text = rev.get('slots', {}).get('main', {}).get('*', '')
                if text:
                    pages[page['title']] = {'file': name, 'revision': rev.get('revid'), 'text': text}
            parsed = batch.get('parse', {})
            if parsed.get('wikitext', {}).get('*'):
                pages[parsed['title']] = {'file': name, 'revision': parsed.get('revid'),
                                          'text': parsed['wikitext']['*']}
    return pages, provenance


def summon_section(text):
    match = re.search(r'^==\s*((?:Box|Raid) Summon)\s*==\s*(.*?)(?=\n==[^=]|\Z)',
                      text, re.M | re.S | re.I)
    return (match[1], match[2]) if match else ('', '')


def box_row(raw):
    """Keep award bundle size separate from the number of finite slots."""
    value = raw.lstrip('* ').strip()
    featured = value.lower().startswith('featured:')
    value = re.sub(r'^Featured:\s*', '', value, flags=re.I)
    count = re.search(r'\s*\(([\d,]+)(?:\s+per\s+(type|color))?\)\s*$', value, re.I)
    copies = int(count[1].replace(',', '')) if count else 1
    label = value[:count.start()].strip() if count else value
    bundle = re.search(r'\s*[x×]\s*([\d,]+)\s*$', label)
    amount = int(bundle[1].replace(',', '')) if bundle else 1
    if bundle:
        label = label[:bundle.start()].strip()
    lapis = re.search(r'\{\{Lapis\|([\d,]+)\}\}', label, re.I)
    if lapis:
        label, amount = 'Lapis', int(lapis[1].replace(',', ''))
    row = {'label': plain(label), 'wiki_label': label, 'copies': copies,
           'award_count': amount, 'featured': featured, 'source_row': raw}
    if count and count[2]:
        row['expand_each'] = count[2].lower()
    if re.search(r'\(\d+\s*-\s*\d+\s+per', value):
        row['copies'] = None
        row['unresolved'] = 'Source gives a quantity range, not an exact finite-slot count.'
    return row


def boxes(text):
    result = []
    for match in re.finditer(r'(?:^|\n)Box\s+(\d+)\s*=\s*(.*?)(?=\n\|-\||</tabber>|\Z)',
                             text, re.S | re.I):
        rows = [box_row(line) for line in match[2].splitlines() if line.startswith('*')]
        result.append({'number': int(match[1]), 'entries': rows,
                       'quantity_status': 'published counts; grouped types still require identity expansion'})
    return result


def survey(text):
    if not re.search(r'Survey|Estimation|Estimated|Summoned.*Chance', text, re.I):
        return []
    result = []
    for line in text.splitlines():
        if not line.startswith('| ') or '||' not in line:
            continue
        cells = [part.strip() for part in line[1:].split('||')]
        if len(cells) < 3 or re.search(r'Total|colspan|last update', cells[0], re.I):
            continue
        values = []
        for cell in cells[1:4]:
            number = re.match(r'\s*([\d,]+(?:\.\d+)?)\s*%?', cell)
            values.append(float(number[1].replace(',', '')) if number else None)
        if len(values) > 1 and values[1] is not None:
            result.append({'label': plain(cells[0]), 'wiki_label': cells[0],
                           'observed_count': values[0], 'observed_percent': values[1],
                           'estimated_percent': values[2] if len(values) > 2 else None,
                           'classification': 'community survey, not official server odds'})
    return result


def recover():
    pages, provenance = source_pages()
    events = json.loads((ROOT / 'source/server/raid_archive.json').read_text('utf-8'))['events']
    names = {}
    for line in (ROOT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson').read_text('utf-8').splitlines():
        row = json.loads(line)
        names[row['key'].rsplit('_', 1)[-1]] = row['v'][0]
    banners = {}
    for family in ('catalogue', 'community', 'named', 'authored', 'standard', 'raid'):
        for banner in json.loads((ROOT / f'source/server/gacha_{family}.json').read_text('utf-8'))['banners']:
            if family == 'standard':
                banners.setdefault(str(banner['id']), banner)
            else:
                banners[str(banner['id'])] = banner
    records = []
    for event in events:
        currency = event.get('raid_coin') or {}
        iid = str(currency.get('id', ''))
        title = unquote(event.get('source_url', '').split('/wiki/')[-1]).replace('_', ' ')
        page = pages.get(title) or pages.get(event['name'])
        heading, text = summon_section(page['text']) if page else ('', '')
        record = {'event_id': event['event_id'], 'name': event['name'],
                  'currency_id': iid or None, 'currency_name': names.get(iid),
                  'source_url': event.get('source_url'), 'source_title': title,
                  'source_file': page['file'] if page else None,
                  'source_revision': page['revision'] if page else None,
                  'matching_banners': [{'id': b['id'], 'name': b.get('name'), 'cost': b['cost']}
                                       for b in banners.values()
                                       if str((b.get('cost') or {}).get('item_id')) == iid and iid],
                  'section': heading, 'boxes': boxes(text), 'surveys': [],
                  'official_unlimited_odds': None}
        box_cost = re.search(r'Each box summon will cost ([\d,]+) coins', text, re.I)
        standard_cost = re.search(r'(?:standard raid|Each) summon will cost ([\d,]+) coins', text, re.I)
        record['box_cost'] = int(box_cost[1].replace(',', '')) if box_cost else None
        record['standard_cost'] = int(standard_cost[1].replace(',', '')) if standard_cost else None
        record['summon_source_recovered'] = bool(text)
        record['pool_rows'] = [line for line in text.splitlines()
                               if line.startswith('| ') and
                               ('[[' in line or '{{Item' in line or 'Forticite' in line or 'cryst/' in line)]
        survey_sources = [(title, text)] if text else []
        survey_sources += [(title + suffix, pages[title + suffix]['text'])
                           for suffix in ('/Drop Rates',) if title + suffix in pages]
        for survey_title, source_text in survey_sources:
            entries = survey(source_text)
            if entries:
                record['surveys'].append({'title': survey_title, 'entries': entries})
        record['unresolved'] = ['Official unlimited-pool probabilities have not been recovered.']
        if not text:
            record['unresolved'].append('Missing complete summon section and slot inventory.')
        if event['event_id'] == '4082':
            record['classification_issue'] = ('Original item name is a subjugation certificate. '
                'Official announcement describes an EP exchange event, not raid coin summons.')
        if iid == '106318300':
            record['gnon'] = {'correct_event_id': '6210',
                'original_announcement': 'https://jp.finalfantasy.com/news/4293/',
                'box_highlights_source': 'https://altema.jp/ffbe/gekitouariahannoheigen',
                'existing_problem': 'Invented filler and 95/5 overflow removed on2026-11-10. '
                                    'Source record9400151 is inactive pending complete original slot inventory.',
                'published_highlights': [
                    {'box': 1, 'rewards': ['Featured Summon Ticket', '5-Star Select Summon Ticket']},
                    {'box': 2, 'rewards': ['Featured Summon Ticket', 'Star Quartz x5']},
                    {'box': 3, 'rewards': ['Featured Summon Ticket x3', 'Poron Fragment x50']},
                    {'box': 4, 'rewards': ['Featured Summon Ticket x3', 'Yao Fragment x50']},
                    {'box': 5, 'rewards': ['Featured Summon Ticket x5', 'Arus Fragment x50']},
                ],
                'highlights_limit': 'Published highlights do not establish full slot totals, per-reward copies or overflow odds.'}
        records.append(record)
    summary = {'raid_archive_events': len(records),
               'summon_sections_recovered': sum(r['summon_source_recovered'] for r in records),
               'events_with_box_inventories': sum(bool(r['boxes']) for r in records),
               'box_inventories': sum(len(r['boxes']) for r in records),
               'finite_reward_rows': sum(len(b['entries']) for r in records for b in r['boxes']),
               'events_with_survey_estimates': sum(bool(r['surveys']) for r in records),
               'official_unlimited_odds_recovered': 0,
               'unmatched_currency_ids': sorted({r['currency_id'] for r in records
                                                if r['currency_id'] and not r['matching_banners']})}
    global_events = [r for r in records if r['event_id'] not in {'738', '742', '771', '4082', '6210', '6410', '4480', '4500'}]
    summary['global_coin_events'] = sum(bool(r['currency_id']) for r in global_events)
    summary['global_unmatched_currency_ids'] = sorted({r['currency_id'] for r in global_events if r['currency_id'] and not r['matching_banners']})
    return {'status': 'Global raid runtime integration complete with recorded inferences; retained original evidence below preserves its original gaps.',
            'policy': 'Original data preferred. Community probability estimates, named 5% moogle inferences and three labeled Global source reconstructions are explicitly user-approved. No anonymous filler slots.',
            'code_status': 'Native raid destinations, archive target inclusion and batch offers corrected in source. Separate incomplete JP box sources remain inactive. No APK or phone update performed.',
            'original_odds_search': RESEARCH,
            'search_limit': 'No original unlimited-pool odds found in the checked sources. This does not prove that no other archive holds them.',
            'source_files': provenance, 'summary': summary, 'events': records}


def main():
    doc = recover()
    (ROOT / OUTPUT).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(doc['summary'], unmatched_currency_ids=len(doc['summary']['unmatched_currency_ids']))))
    print('Recovery dataset:', OUTPUT)


if __name__ == '__main__':
    main()
