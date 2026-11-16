"""Restore four omitted Global raids using each raid's original reward records."""
import json
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('FFBE_DATA', str(ROOT / 'data'))

from build_event_archive import build_document
from build_raid_archive import build as raid_records
from build_global_raid_summons import expand_source, standard_pool
from map_raid_summon_rewards import Resolver
from recover_raid_summons import summon_section

SERVER = ROOT / 'source/server'
SOURCE = ROOT / 'logs/reference/restored-event-rewards-wiki-20261111.json'
SCOPE = {'747', '797', '940', '958'}


def load(name):
    return json.loads((SERVER / name).read_text(encoding='utf-8'))


def save(name, value):
    (SERVER / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    areas = [row for row in build_document(include_unidentified=True)['events'] if row['area'] in SCOPE]
    raids, gaps = raid_records(areas, [source])
    if gaps or {row['event_id'] for row in raids} != SCOPE:
        raise ValueError('Own raid reward records incomplete: ' + json.dumps(gaps))
    pages = {row['title']: {'text': row['revisions'][0]['slots']['main']['*'],
                             'revision': row['revisions'][0]['revid']}
             for row in source['query']['pages'].values() if row.get('revisions')}
    resolver = Resolver()
    archive, summons = load('raid_archive.json'), load('gacha_raid.json')
    links, offers = load('raid_summon_links.json'), load('raid_summon_offers.json')
    prepared, new_links, receipts = [], [], []
    for raid in raids:
        aid = raid['event_id']
        area = next(row for row in areas if row['area'] == aid)
        title = area['source_page'].split('/wiki/', 1)[1].replace('_', ' ')
        page = pages[title]
        section = expand_source(summon_section(page['text'])[1], title, pages)
        prices = [int(value.replace(',', '')) for value in
                  re.findall(r'(?:Each|standard raid) summon will cost ([\d,]+) coins', section, re.I)]
        limits = [int(value.replace(',', '')) for value in
                  re.findall(r'batch summon up to ([\d,]+) summons', section, re.I)]
        if len(set(prices)) != 1 or len(set(limits)) != 1:
            raise ValueError('Own original raid summon offer missing: ' + aid)
        pool, missing = standard_pool(section, resolver)
        if missing or not pool or not math.isclose(sum(row['rate'] for row in pool), 1, abs_tol=1e-9):
            raise ValueError('Own raid summon inventory incomplete: ' + aid + ' ' + json.dumps(missing))
        bid = str(9600000 + int(aid))
        existing = next((row for row in summons['banners'] if str(row['id']) == bid), None)
        if existing and str(existing.get('raid_event_id')) != aid:
            raise ValueError('Existing summon identity collision: ' + bid)
        coin = raid['raid_coin']['id']
        prepared.append({'id': bid, 'name': raid['name'] + ' Raid Summon', 'name_override': True,
            'type': 'normal', 'tab': 'free', 'release': area['release'], 'detail_id': bid + '1',
            'cost': {'kind': 'item', 'item_id': coin, 'amount': prices[0], 'is_coin': True},
            'draws': 1, 'exe_type': 'primary', 'reward_pool': pool,
            'art': {'banner': area['filename'], 'detail_banner': area['filename'],
                    'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_normal/anime'},
            'raid_event_id': aid, 'raid_currency_id': coin, 'activation_ready': True,
            'rate_source': {'url': area['source_page'], 'revision': page['revision'],
                'scope': 'Own published rewards. Surviving survey chances take precedence; '
                    'unmeasured rows use the existing source-category weight reconstruction. '
                    'Grouped colour weights remain reconstructed in code/data only.'}})
        for did in raid['dungeon_ids']:
            new_links.append({'event_id': aid, 'dungeon_id': str(did), 'gacha_id': bid,
                              'banner_id': str(910000000 + int(aid)), 'name': raid['name']})
        offers['currencies'][str(coin)] = {'normal': {'source_url': area['source_page'],
            'source_revision': page['revision'], 'single_cost': prices[0], 'batch_limit': limits[0]}}
        receipts.append({'area': aid, 'currency': coin, 'pool_entries': len(pool),
                         'milestones': len(raid['personal_milestones']),
                         'mission_points': raid['mission_points'],
                         'single_cost': prices[0], 'batch_limit': limits[0]})
    archive['events'] = [row for row in archive['events'] if str(row['event_id']) not in SCOPE] + raids
    summons['banners'] = [row for row in summons['banners'] if str(row.get('raid_event_id')) not in SCOPE] + prepared
    links['links'] = [row for row in links['links'] if str(row.get('event_id')) not in SCOPE] + new_links
    for name, value in [('raid_archive.json', archive), ('gacha_raid.json', summons),
                        ('raid_summon_links.json', links), ('raid_summon_offers.json', offers)]:
        save(name, value)
    (ROOT / 'logs/ffbe-omitted-raid-restoration-20261111.json').write_text(
        json.dumps({'sources': [SOURCE.relative_to(ROOT).as_posix()], 'raids': receipts}, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(receipts))


if __name__ == '__main__':
    main()
