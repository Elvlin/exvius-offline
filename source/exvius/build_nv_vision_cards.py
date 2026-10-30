"""Build source/server/nv_vision_cards.json: the Vision Card each Neo Vision unit came with.

A summoned NV unit came with its own Vision Card (GachaExeResponse eb2ANT1m, "27:<card>:<key>" per NV;
UnitGetScene shows it after the unit). The game tables do not link the two (F_UNIT_MST 5giCMUd2 is 0 for
every NV), so the link is read from the FFBE wiki: first the Global Vision Card pages (Category:Vision
Cards: "id", "acquisition = Unit-specific", "unit = <name>"), then for units those do not name, the /JP
unit pages, which list "[Vision Card] <JP name>" beside the TMR/STMR (matched by that exact name in
F_VISION_CARD_MST). Each entry records the page and its revision.

Run: python -I source/exvius/build_nv_vision_cards.py
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
MST = PROJECT / 'data/mst_decoded'
TEXT = PROJECT / 'data/text_decoded'
OUT = PROJECT / 'source/server/nv_vision_cards.json'
API = 'https://exvius.fandom.com/api.php'


def rows(path):
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def fetch(titles):
    query = urllib.parse.urlencode({'action': 'query', 'prop': 'revisions', 'rvprop': 'content|ids',
                                    'rvslots': 'main', 'redirects': 1, 'format': 'json',
                                    'titles': '|'.join(titles)})
    request = urllib.request.Request(API + '?' + query, headers={'User-Agent': 'Mozilla/5.0 (exvius offline)'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)['query']


def category_pages(category):
    titles, cont = [], {}
    while True:
        query = urllib.parse.urlencode({'action': 'query', 'list': 'categorymembers', 'cmtitle': category,
                                        'cmlimit': 500, 'format': 'json', **cont})
        request = urllib.request.Request(API + '?' + query, headers={'User-Agent': 'Mozilla/5.0 (exvius offline)'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
        titles += [m['title'] for m in data['query']['categorymembers'] if m['ns'] == 0]
        if 'continue' not in data:
            return titles
        cont = {'cmcontinue': data['continue']['cmcontinue']}


def global_cards(card_ids):
    """{unit name: (card id, card name, page, revision)} from the Global Vision Card pages."""
    out = {}
    titles = category_pages('Category:Vision Cards')
    for i in range(0, len(titles), 40):
        for page in fetch(titles[i:i + 40]).get('pages', {}).values():
            revs = page.get('revisions') or []
            text = revs[0]['slots']['main']['*'] if revs else ''
            field = lambda k: (re.search(r'\|\s*' + k + r'\s*=\s*([^\n|]*)', text) or [None, ''])[1].strip()
            if field('acquisition').lower() != 'unit-specific' or field('id') not in card_ids:
                continue
            for unit in re.split(r'\s*(?:,|<br\s*/?>)\s*', re.sub(r'\[\[|\]\]', '', field('unit'))):
                if unit:
                    out.setdefault(unit, (field('id'), field('name') or page['title'], page['title'], revs[0]['revid']))
        time.sleep(1)
    return out


def main():
    names = {}
    for r in rows(TEXT / 'F_TEXT_UNITS_NAME.ndjson'):
        names[r['key'].rsplit('_', 1)[1]] = r['v'][0] if isinstance(r['v'], list) else r['v']
    cards = {}
    for r in rows(MST / 'F_VISION_CARD_MST.ndjson'):
        cards.setdefault(r['G4L0YIB2'].strip(), r['5giCMUd2'])
    nv = [r['3HriTp6B'] for r in rows(MST / 'F_UNIT_MST.ndjson')
          if r.get('9fW0TePj') == '7' and r['3HriTp6B'] == r.get('woghJa61') and names.get(r['3HriTp6B'])]
    found, missing = {}, []
    by_global = global_cards(set(cards.values()))
    rest = []
    for uid in nv:
        hit = by_global.get(names[uid])
        if hit:
            found[uid] = {'vision_card': hit[0], 'card_name': hit[1], 'unit_name': names[uid],
                          'source': 'https://exvius.fandom.com/wiki/' + urllib.parse.quote(hit[2].replace(' ', '_')),
                          'revision': hit[3]}
        else:
            rest.append(uid)
    nv_all, nv = nv, rest
    by_title = {}
    for uid in nv:
        by_title.setdefault(names[uid].replace('_', ' ') + '/JP', []).append(uid)
    titles = sorted(by_title)
    for i in range(0, len(titles), 40):
        q = fetch(titles[i:i + 40])
        alias = {n['to']: n['from'] for n in q.get('redirects', []) + q.get('normalized', [])}
        for page in q.get('pages', {}).values():
            title = alias.get(page['title'], page['title'])
            title = alias.get(title, title)
            revs = page.get('revisions') or []
            text = revs[0]['slots']['main']['*'] if revs else ''
            m = re.search(r'\[Vision Card\]\s*([^\n|]+)', text)
            card = cards.get(m.group(1).strip()) if m else None
            for uid in by_title.get(title, []):
                if card:
                    found[uid] = {'vision_card': card, 'card_name': m.group(1).strip(), 'unit_name': names[uid],
                                  'source': 'https://exvius.fandom.com/wiki/' + urllib.parse.quote(page['title'].replace(' ', '_')),
                                  'revision': revs[0]['revid']}
                else:
                    missing.append({'unit': uid, 'unit_name': names[uid],
                                    'reason': 'no page' if not revs else ('no [Vision Card]' if not m else 'name not in F_VISION_CARD_MST: ' + m.group(1).strip())})
        time.sleep(1)
    doc = {'_meta': {'what': 'The Vision Card each NV unit came with when summoned (generator docstring).',
                     'generator': 'source/exvius/build_nv_vision_cards.py', 'nv_units': len(nv_all),
                     'matched': len(found), 'unmatched': missing},
           'units': dict(sorted(found.items()))}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print('NV units', len(nv_all), 'matched', len(found), 'unmatched', len(missing))


if __name__ == '__main__':
    main()
