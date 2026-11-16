"""Banner-specific pools for the eleven retained April/May 2020 JP summons."""
from collections import defaultdict
from functools import lru_cache
import copy
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FIRST = 'jp-unit-list-20200501-wiki.json'
SECOND = 'jp-unit-list-20200512-wiki.json'
IDS = {str(i) for i in range(9200101, 9200112)}


@lru_cache(maxsize=2)
def snapshot(filename):
    doc = json.loads((ROOT / 'logs/reference/summons' / filename).read_text('utf-8'))
    revision = doc['query']['pages'][0]['revisions'][0]
    rows = []
    for raw in revision['slots']['main']['content'].split('|-'):
        columns = raw.split('||')
        icon = re.search(r'unit_icon_(\d+)\.png', raw)
        if not icon or len(columns) < 11:
            continue
        name = re.search(r'\[\[[^]|]+\|([^]]+)\]\]', columns[2])
        rows.append({'id': icon[1], 'name': name[1] if name else '',
                     'base': 7 if 'NV' in columns[5] else int(re.search(r'\d+', columns[5])[0]),
                     'acquisition': columns[7].strip(), 'limited': columns[8].strip(),
                     'series': columns[10].strip()})
    return rows, revision['revid']


def historical_units(filename, evidence):
    """Use JP release membership and available matching Global owned forms."""
    rows, revision = snapshot(filename)
    names = defaultdict(list)
    for uid, label in evidence['labels'].items():
        names[label].append(uid)
    mapped, unavailable = [], []
    for row in rows:
        if row['acquisition'] != 'Rare Summon' or row['limited'] not in ('-', 'Summon Festival'):
            continue
        uid = str(evidence['mst'].get(row['id'], {}).get('woghJa61', row['id']))
        if uid not in evidence['roots'] or uid not in evidence['labels']:
            # A few JP counterparts use different identifiers in Global.
            # Require both exact English identity and the same base rarity.
            matches = [u for u in names[row['name']]
                       if int(evidence['mst'][u]['9fW0TePj']) == row['base']]
            uid = matches[0] if len(matches) == 1 else ''
        if not uid or uid not in evidence['labels']:
            unavailable.append(row['name'])
            continue
        mapped.append(dict(row, id=uid))
    return mapped, revision, unavailable


def repair_banner(banner, evidence):
    if str(banner['id']) not in IDS or banner.get('source') != 'translated-jp':
        return False
    before = copy.deepcopy(banner)
    bid = int(banner['id'])
    filename = SECOND if bid in (9200102, 9200105, 9200109, 9200110, 9200111) else FIRST
    rows, revision, unavailable = historical_units(filename, evidence)
    groups = {rarity: sorted({r['id'] for r in rows if r['base'] == rarity})
              for rarity in (3, 4, 5, 7)}
    def tier(rarity, rate, units=None):
        return {'rarity': rarity, 'rate': rate, 'units': list(groups[rarity] if units is None else units)}
    restrictions = 'Dated JP rare-summon cohort; no collaborations, seasonal units, event rewards or later releases.'
    if bid in (9200101, 9200102):
        featured = (['207000405', '207001105', '207000605'] if bid == 9200101
                    else ['213001005', '213001105'])
        banner['pool'] = {'tiers': [tier(5, .05, featured), tier(4, .25), tier(3, .70)]}
        banner['guarantee'] = {'any_of': featured}
        restrictions += ' Every five-star result and the guaranteed slot use only the units printed on this banner.'
    elif bid in (9200103, 9200104, 9200105, 9200106, 9200107, 9200108):
        rates = [(7, .01), (5, .09), (4, .45), (3, .45)]
        if bid == 9200107:
            rates = [(7, .01), (5, .09), (4, .90)]
        elif bid == 9200108:
            rates = [(7, .01), (5, .99)]
        if bid == 9200103:
            for rarity in (5, 7):
                groups[rarity] = sorted({r['id'] for r in rows if r['base'] == rarity and r['series'] == 'FF7'})
            restrictions += ' All five-star and NV results are FFVII units, as printed on the original screen.'
        banner['pool'] = {'tiers': [tier(rarity, rate) for rarity, rate in rates]}
        if bid == 9200105:
            banner['release'] = '2020-05-12'
        banner['rate_notice'] = 'NV rate: 1%. Shared local rates approved by the user. Banner-specific unit eligibility and minimum rarities apply.'
    elif bid == 9200110:
        # The original art explicitly includes rare-summon heroes as well as
        # event units and enhancers. It is not a Zenaida-only unit summon.
        banner['pool'] = {'tiers': [
            dict(tier(5, .10, sorted(set(groups[5] + ['100028205']))),
                 featured=['100028205'], featured_share=.2), tier(4, .40),
            tier(4, .50, ['906000105', '900010501', '900020401'])]}
        restrictions += ' Retains the original banner featured event unit Zenaida and its explicit enhancer rewards.'
    else:
        # Bonus and Brave Ability summons are material rewards. The common
        # NV probability never adds combat heroes to either inventory.
        restrictions = 'Material-only summon; no random combat-unit background and no NV tier.'
    banner['eligibility_source'] = {
        'source': 'logs/reference/summons/' + filename,
        'revision': revision,
        'policy': restrictions,
        'unavailable_global_counterparts': unavailable if bid not in (9200109, 9200111) else [],
        'original_server_pool_recovered': False,
        'regional_roster_reconstructed': True,
    }
    return banner != before
