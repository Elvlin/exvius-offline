"""Original coin-summon single and quantity-selectable batch offers."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def contracts():
    return json.loads(Path(__file__).with_name('raid_summon_offers.json').read_text('utf-8'))['currencies']


def schedule_rows(event_id=None):
    links_path = Path(__file__).with_name('raid_summon_links.json')
    links = json.loads(links_path.read_text(encoding='utf8'))['links'] if links_path.exists() else []
    return [{'fSxqkF10': bid, 'VjJQ51uG': '2000-01-01 00:00:00', 'm8ivD4NX': '2099-12-31 23:59:59'}
            for bid in sorted({r['banner_id'] for r in links if event_id is None or r['event_id'] == event_id})]


def batch_detail_id(primary):
    # Preserve existing single-offer IDs. Keep the new row distinct from all
    # finite-box indexes and from ordinary gachaId*10+step detail IDs.
    return str(1_000_000_000 + int(primary))


def prepare(player, banner):
    cost = banner.get('cost') or {}
    variants = contracts().get(str(cost.get('item_id'))) if isinstance(cost, dict) and cost.get('kind') == 'item' else None
    rule = variants.get('box' if banner.get('boxes') else 'normal') if variants else None
    if not rule:
        return banner
    b = dict(banner)
    primary = str(b['detail_id'])
    standard = False
    if b.get('boxes'):
        from gacha_box import detail_id, state
        primary = detail_id(player, b)
        standard = state(player, b)['index'] >= len(b['boxes'])
    price = rule.get('standard_cost' if standard else 'single_cost')
    maximum = rule.get('standard_batch_limit' if standard else 'batch_limit')
    if not price or not maximum:
        return banner
    cost = dict(cost, amount=price)
    b.update(cost=cost, detail_id=primary, gacha_layout=0, exe_type='primary', draws=1,
             img_btn_primary='gacha_btn_c_default', raid_batch_limit=maximum,
             secondary_offer={'detail_id': batch_detail_id(primary), 'cost': cost,
                              'draws': maximum, 'exe_count': maximum,
                              'img_btn': 'gacha_btn_c_multi', 'raid_batch': True})
    return b


def batch_offer(banner, requested_detail, repeats):
    maximum = banner.get('raid_batch_limit')
    if not maximum:
        return None
    secondary = banner['secondary_offer']
    if str(requested_detail) != str(secondary['detail_id']):
        return None
    if not 1 <= repeats <= maximum:
        raise ValueError('Raid batch quantity exceeds the published limit')
    return dict(secondary, cost=dict(banner['cost'], amount=banner['cost']['amount'] * repeats),
                draws=repeats)
