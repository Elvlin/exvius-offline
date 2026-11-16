"""Recover coin costs and batch limits separately from uncertain reward pools."""
import json
from pathlib import Path
import re
from urllib.parse import unquote

from recover_raid_summons import source_pages, summon_section

ROOT = Path(__file__).resolve().parents[2]


def build():
    pages, _ = source_pages()
    events = json.loads((ROOT / 'source/server/raid_archive.json').read_text('utf-8'))['events']
    offers = {}
    for event in events:
        currency = event.get('raid_coin') or {}
        if not currency:
            continue
        title = unquote(event.get('source_url', '').split('/wiki/')[-1]).replace('_', ' ')
        page = pages.get(title) or pages.get(event['name'])
        heading, text = summon_section(page['text']) if page else ('', '')
        if not text:
            continue
        limits = [int(m.replace(',', '')) for m in re.findall(r'batch summon up to ([\d,]+) summons', text, re.I)]
        prices = [int(m.replace(',', '')) for m in re.findall(r'(?:Each(?: box)?|standard raid) summon will cost ([\d,]+) coins', text, re.I)]
        if not limits or not prices:
            continue
        boxed = heading.lower().startswith('box') or bool(re.search(r'(?:^|\n)Box\s+1\s*=', text))
        row = {'source_url': event['source_url'], 'source_revision': page['revision']}
        if boxed:
            if len(prices) == 2 and len(limits) == 2:
                row.update(single_cost=prices[0], batch_limit=limits[0],
                           standard_cost=prices[1], standard_batch_limit=limits[1])
            elif len(prices) == 1 and len(limits) == 1 and 'Each box summon will cost' not in text:
                row.update(standard_cost=prices[0], standard_batch_limit=limits[0])
                if str(event['event_id']) == '6160':
                    row.update(single_cost=400, batch_limit=50,
                               reconstruction='User-approved reconstruction: box price 400 coins and batch cap50 from contemporary Global raid offers. This event source prints only the standard price400 and cap500.')
            else:
                raise ValueError('Ambiguous box and standard offer: ' + event['name'])
        else:
            row.update(single_cost=prices[0], batch_limit=limits[0])
        key = str(currency['id'])
        mode = 'box' if boxed else 'normal'
        previous = offers.get(key, {}).get(mode)
        if previous and any(previous.get(k) != row.get(k) for k in
                            ('single_cost', 'batch_limit', 'standard_cost', 'standard_batch_limit')):
            # A repeated event can reuse its coin with a different summon family.
            # Bind those contracts by event rather than guessing one for the coin.
            raise ValueError('Conflicting historical offers for coin ' + key)
        offers.setdefault(key, {})[mode] = row
    return {'version': 1, 'currencies': offers,
            'scope': 'Published offer costs and batch limits only. No reward pool or probability substitutions.'}


if __name__ == '__main__':
    doc = build()
    target = ROOT / 'source/server/raid_summon_offers.json'
    target.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    print('Recovered source-backed offers for', len(doc['currencies']), 'raid currencies')
