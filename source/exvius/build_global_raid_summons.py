"""Build Global raid summons from retained event revisions and native identities.

Incomplete source records are retained but never activated. Unlimited weights
are local estimates unless a community survey survives; reward types and finite
slot quantities always come from the raid's own published inventory.
"""
import copy
import json
from pathlib import Path
import re

from build_raid_archive import plain
from map_raid_summon_rewards import Resolver, JP_AREAS, map_rewards
from recover_raid_summons import source_pages, summon_section

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / 'source/server'


def pool_records(text):
    standard = re.search(r'(?:^|\n)Standard\s*=\s*(.*?)(?:</tabber>|\Z)', text, re.S | re.I)
    if standard:
        text = standard[1]
    elif re.search(r'(?:^|\n)Box\s+1\s*=', text):
        return []
    category = 'ordinary'
    survey_table = False
    records = []
    for line in text.splitlines():
        if line.startswith('{|') or line.startswith('|}'):
            survey_table = False
        if line.startswith('!') and re.search(r'Summoned|Chance', line, re.I):
            survey_table = True
        if line.startswith('!') and ('Rare' in line or 'Units' in line or 'Materials' in line):
            category = 'ultra' if 'Rare' in line else 'ordinary'
        if not line.startswith('| ') or line.startswith('| colspan') or line.startswith('| rowspan'):
            continue
        value = line[2:].split('||')[0].strip()
        value = re.sub(r'\{\{Sprite\|[^}]+\}\}', '', value, flags=re.I)
        # Ifrit's original table prints each donor's target and 5% value in
        # separate columns rather than a second wiki link.
        target = re.search(r'\[\[Trust Moogle\]\]\s*<br>\(([^)]+)\)', value, re.I)
        if target and re.search(r'5% TMR Moogle', line):
            value = '{{rarity|3}} [[' + target[1] + '|Trust Moogle]] (5%)'
        if '||' in line and not re.search(r'Moogle|\{\{rarity', value, re.I):
            rarity = re.search(r'\{\{Rarity\|(\d+)\}\}', line.split('||')[1], re.I)
            if rarity:
                value = '{{rarity|' + rarity[1] + '}} ' + value
        if re.fullmatch(r'\d-star', plain(value)) or plain(value).startswith('Total '):
            continue
        if not value or not re.search(r'\[\[|\{\{(?:Item|rarity)|Forticite|cryst', value, re.I):
            continue
        record = {'wiki_label': value, 'award_count': 1, 'category': category, 'source_row': line}
        cells = [c.strip() for c in line[2:].split('||')]
        if len(cells) >= 3:
            reported = re.fullmatch(r'([\d.]+)%?', cells[2]) if survey_table else None
            estimated = re.fullmatch(r'([\d.]+)%?', cells[3]) if survey_table and len(cells) > 3 else None
            if reported:
                # Some original survey pages leave every estimation cell at
                # zero despite a populated observed-count/chance column.
                selected = estimated if estimated and float(estimated[1]) > 0 else reported
                record['survey_rate'] = float(selected[1]) / 100
        records.append(record)
    return records


def expand_source(text, title, pages):
    def replace(match):
        return pages.get(title + '/' + match[1], {}).get('text', match[0])
    return re.sub(r'\{\{/([^}]+)\}\}', replace, text)


def expand_groups(record):
    label = plain(record['wiki_label'])
    if label in ('T1/T2/T3 Forticite', 'Random Forticites'):
        return [dict(record, wiki_label='T' + str(i) + ' Forticite') for i in (1, 2, 3)]
    if label in ('Alcryst/Milcryst/Heavicryst/Giancryst/Purecryst', 'Random Ability Awakening Crysts'):
        return [dict(record, wiki_label=i) for i in ('Alcryst', 'Milcryst', 'Heavicryst', 'Giancryst', 'Purecryst')]
    if label in ('Magicites/Megacites', 'Magicite/Megacite', 'Megacites', 'Magicites'):
        families = ('Magicite', 'Megacite') if '/' in label else ('Megacite',) if label == 'Megacites' else ('Magicite',)
        return [dict(record, wiki_label=colour + ' ' + family) for family in families
                for colour in ('Red', 'Blue', 'Green', 'White', 'Black', 'Yellow', 'Orange', 'Violet')]
    if label.startswith('Megacite {{#tip-info:'):
        return [dict(record, wiki_label=c + ' Megacite') for c in ('Red', 'Blue', 'Yellow', 'Orange', 'Violet')]
    return [record]


def standard_pool(text, resolver):
    records = pool_records(text)
    rows, missing, seen, measured = [], [], set(), {}
    for record in records:
        try:
            expanded_rewards = [reward for expanded in expand_groups(record) for reward in resolver.resolve(expanded)]
            for reward in expanded_rewards:
                identity = json.dumps(reward, sort_keys=True)
                if identity not in seen:
                    rows.append((reward, record['category']))
                    seen.add(identity)
                if 'survey_rate' in record:
                    measured[identity] = record['survey_rate'] / len(expanded_rewards)
        except (ValueError, KeyError) as exc:
            missing.append({'source_row': record['source_row'], 'error': str(exc)})
    if not rows:
        missing.append({'error': 'No complete unlimited pool recovered'})
        return [], missing
    # Only the probabilities are estimates. Rare source rows share 1% of the
    # pool, with the other published entries sharing the rest equally.
    rare = sum(category == 'ultra' for _, category in rows)
    regular = len(rows) - rare
    result = []
    unmeasured = sum(json.dumps(reward, sort_keys=True) not in measured for reward, _ in rows)
    remainder = max(0, 1 - sum(measured.values()))
    for reward, category in rows:
        mass = (.01 if regular else 1) if category == 'ultra' else (.99 if rare else 1)
        rate = mass / (rare if category == 'ultra' else regular)
        if measured:
            rate = measured.get(json.dumps(reward, sort_keys=True), remainder / unmeasured if unmeasured else 0)
        result.append(dict(reward, rate=rate))
    total = sum(r['rate'] for r in result)
    if total:
        for row in result:
            row['rate'] /= total
    return result, missing


def build():
    recovered = json.loads((ROOT / 'logs/raid-summon-recovery-20261109.json').read_text('utf-8'))
    mapped = {e['event_id']: e for e in map_rewards()['events']}
    archive = {e['area']: e for e in json.loads((SERVER / 'event_archive.json').read_text('utf-8'))['events']}
    raids = json.loads((SERVER / 'raid_archive.json').read_text('utf-8'))['events']
    by_area = {e['event_id']: e for e in raids}
    contracts = json.loads((SERVER / 'raid_summon_offers.json').read_text('utf-8'))['currencies']
    existing = {}
    for family in ('catalogue', 'community', 'named', 'authored', 'standard'):
        for b in json.loads((SERVER / ('gacha_' + family + '.json')).read_text('utf-8'))['banners']:
            if b.get('activation_ready') is not False:
                existing[str(b['id'])] = b
    pages, _ = source_pages()
    resolver = Resolver()
    banners, links = [], []
    for event in recovered['events']:
        area = str(event['event_id'])
        if area in JP_AREAS or not event['currency_id']:
            continue
        currency = str(event['currency_id'])
        candidates = [b for b in existing.values() if str((b.get('cost') or {}).get('item_id')) == currency]
        old = next((b for b in candidates if b.get('release') == archive.get(area, {}).get('release')), None)
        if old is None and len(candidates) == 1:
            old = candidates[0]
        page = pages.get(event['source_title'])
        text = expand_source(summon_section(page['text'])[1], event['source_title'], pages) if page else ''
        pool, missing = standard_pool(text, resolver)
        finite = mapped[area]
        has_boxes = bool(finite['boxes'])
        offer = contracts.get(currency, {}).get('box' if has_boxes else 'normal', {})
        if not offer.get('single_cost'):
            missing.append({'error': 'Original single-summon cost is missing'})
        if has_boxes and not finite['finite_inventory_mapped']:
            missing.append({'error': 'Finite box inventory has unresolved native identities or quantities'})
        # Existing original summons remain usable while their additional source
        # recovery is incomplete. No partial replacement may override them.
        ready = not missing
        if old and not ready:
            banner = copy.deepcopy(old)
        else:
            bid = str(old['id']) if old else str(9600000 + int(area))
            banner = {'id': bid, 'name': event['name'] + ' Raid Summon', 'name_override': True,
                      'type': 'box' if has_boxes else 'normal', 'tab': 'limited' if has_boxes else 'free',
                      'release': archive.get(area, {}).get('release'), 'detail_id': bid + '1',
                      'cost': {'kind': 'item', 'item_id': int(currency), 'amount': offer.get('single_cost', 0), 'is_coin': True},
                      'draws': 1, 'exe_type': 'primary', 'reward_pool': pool,
                      'art': copy.deepcopy(old.get('art', {})) if old else {
                          'banner': archive.get(area, {}).get('filename'),
                          'detail_banner': archive.get(area, {}).get('filename'),
                          'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_normal/anime'},
                      'rate_notice': 'LOCAL ESTIMATED RATES for the published rewards of this raid. Finite box slots use their original published quantities.',
                      'rate_source': {'url': event['source_url'], 'revision': event['source_revision'],
                                      'scope': 'Raid-specific rewards and published finite quantities; unlimited probabilities locally estimated.'}}
            if has_boxes:
                banner['box_base_id'] = 500000 + int(area) * 10
                banner['boxes'] = [[copy.deepcopy(r) for r in b['entries']] for b in finite['boxes']]
        banner.update(raid_event_id=area, raid_currency_id=int(currency))
        banner['recovery'] = {'complete': ready, 'missing': missing}
        reconstructions = list(finite.get('reconstructions', []))
        if offer.get('reconstruction'):
            reconstructions.append({'decision': offer['reconstruction']})
        if reconstructions:
            banner['reconstructions'] = reconstructions
            banner['rate_notice'] = ('LOCAL ESTIMATED RATES for this raid. Published finite counts are retained, '
                                     'with user-approved reconstructions for source gaps recorded in the banner data.')
            banner['rate_source']['scope'] = 'Raid-specific rewards, published finite quantities, and explicit user-approved reconstructions.'
            if area == '3128':
                banner['rate_notice'] += ' The unnamed featured moogle is reconstructed as Trust Moogle (ALL 5%).'
            elif area == '3231':
                banner['rate_notice'] += ' Awakening groups are reconstructed as the six-star material family plus Holy Crystal, 15 copies each. No filler is added to force a box total.'
            elif area == '6160':
                banner['rate_notice'] += ' Box price400 coins and cap50 are reconstructed; the standard price400 and cap500 are published.'
        if any(r.get('trust_value_source') for r in banner.get('reward_pool', [])) or any(
                r['reward'].get('trust_value_source') for box in banner.get('boxes', []) for r in box):
            banner['trust_notice'] = 'Named three-star moogles without a printed value use the user-approved 5% inference. Explicit published percentages take precedence.'
            banner['rate_notice'] += ' Named moogles without a published trust value use a recorded 5% inference.'
        if not old or ready:
            banner['activation_ready'] = ready
        banners.append(banner)
        if banner.get('activation_ready') is not False:
            for dungeon in by_area[area].get('dungeon_ids', [by_area[area]['dungeon_id']]):
                links.append({'event_id': area, 'dungeon_id': str(dungeon), 'gacha_id': str(banner['id']),
                              'banner_id': str(910000000 + int(area)), 'name': event['name']})
    return {'banners': banners, 'scope': 'Global raid summons only'}, {'links': links}


if __name__ == '__main__':
    banners, links = build()
    for name, doc in [('gacha_raid.json', banners), ('raid_summon_links.json', links)]:
        (SERVER / name).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    active = sum(b.get('activation_ready') is not False for b in banners['banners'])
    print('Global raid sources:', len(banners['banners']), 'active:', active, 'pending:', len(banners['banners']) - active)
    for b in banners['banners']:
        if not b['recovery']['complete']:
            print(b['raid_event_id'], b['name'], [g['error'] for g in b['recovery']['missing']][:3])
