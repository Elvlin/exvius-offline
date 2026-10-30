"""Rebuild the material summons using original identities and explicit local rates."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]


def reward(kind, iid, rate):
    return {'kind': kind, 'id': iid, 'count': 1, 'rate': rate}


def regular_offers(banner, digest, nv):
    """Apply the exact quantities, caps and bonuses printed on each Global image."""
    def item(kind, iid, count):
        return {'kind': kind, 'id': iid, 'count': count}
    weekly = '11f9a39d6c4bfee7caba9ee8ef8d7990'
    final = '2c9fb2294b385e5321fae6368ba7e938'
    video = '91863e7916c47a261d8822c83c07c3f0'
    guaranteed = '23d11bd0ad89e0dee2ad795bb816a4c5'
    seasonal = 'afeb356f41009c1d029e715f9e9ce93e'
    if digest in (weekly, final):
        banner['pool'] = {'tiers': [{'rarity': 7, 'rate': .03, 'units': nv}, {'rarity': 5, 'rate': .97}]}
        banner['rate_notice'] = 'LOCAL UNIT POOL: the printed NV rate is 3%. The remaining draws are base five-star units.'
        if digest == weekly:
            banner['guarantee'] = {'rarity': 7, 'count': 1}
            banner['weekly_limit'] = 1
            banner['bonus_rewards'] = [item(23, 110003, 100)]
    if digest == video:
        banner['daily_limit'] = 6
        banner['bonus_rewards'] = [item(20, 1209001975, 1), item(23, 100, 2)]
    if digest == 'a49633e33917c76f7a9166272250ee84':
        banner['purchase_limit'] = 1
    if digest == '6ca7c5fcd7d6549fcb152b0c1cceb0bb':
        banner['cost'] = {'kind': 'item', 'item_id': 106322400, 'amount': 400, 'is_coin': True}
        boxes, standard = destruction_boxes()
        banner.update(type='box', tab='limited', box_base_id=970001, boxes=boxes, reward_pool=standard)
        banner.pop('pool', None)
        banner['rate_notice'] = ('Original five raid boxes: each remaining slot has an equal chance and is removed when drawn. '
                                 'After the boxes, the standard pool uses clearly labelled local rates.')
        banner['historical_notice'] = {'url': 'https://exvius.fandom.com/wiki/The_Power_of_Destruction',
            'file': 'logs/reference/raids/power-of-destruction-boxes-wiki.json'}
    if digest in (guaranteed, seasonal):
        banner.pop('daily_limit', None)
        banner['weekly_limit'] = 8
        banner['bonus_rewards'] = [item(20, 106211340, 8), item(23, 100, 8)]
    if digest == seasonal:
        from gacha_archive import _collaboration
        from player_state import unit_mst
        doc = json.loads((ROOT / 'source/server/gacha_community.json').read_text(encoding='utf-8'))
        units = {u for b in doc['banners'] if (b.get('community') or {}).get('limited') and not _collaboration(b)
                 for u in b['community'].get('unit_ids', [])}
        tiers = []
        for rarity, chance in ((7, .03), (5, .12), (4, .425), (3, .425)):
            eligible = sorted(u for u in units if int(unit_mst(u)['9fW0TePj']) == rarity)
            if eligible:
                tiers.append({'rarity': rarity, 'rate': chance, 'units': eligible})
        if not tiers:
            raise ValueError('Original seasonal unit identities are missing')
        banner['pool'] = {'tiers': tiers}
        banner['rate_notice'] = 'LOCAL RATES: seasonal units from the recovered Global calendar only. Exact probabilities are listed below.'
    if digest in ('c80787fd8f73bc54e76a4cc58c623ff2', '44ca2c0ff5f096ee4b3ada1a82f56cdc'):
        banner['cost'] = {'kind': 'important', 'item_id': 110260, 'amount': 10}
    if digest in ('8099f68c1832301560ab134a72656b91', 'c0dcca29a0596f4e2009188219eadd3f',
                   '435e7e03529984b0da37db11781e8450'):
        banner['guarantee'] = {'rarity': 4, 'count': 1}
    if digest == 'a705f7d65d5897fe0506f91a73dc6520':
        banner['cost'] = {'kind': 'item', 'item_id': 1209001976, 'amount': 1}
        from player_state import unit_roots_by_rarity
        featured = [uid for uid in nv if uid.startswith('100')]
        five = [uid for uid in unit_roots_by_rarity().get('5', []) if uid.startswith('100')]
        banner['pool'] = {'tiers': [{'rarity': 7, 'rate': .05, 'units': featured},
                                    {'rarity': 5, 'rate': .95, 'units': five}]}
        banner['rate_notice'] = ('LOCAL REPLACEMENT POOL: FFBE units only, NV 5% and base five-star 95%. '
                                 'The historical 2022-and-later eligibility list was not preserved.')
    if digest == 'd8ca4b999bebca646b94537786e950d6':
        choices = [item(23, 110180, 1), item(23, 110160, 1), item(23, 260, 1),
                   dict(item(10, 904000105, 2), affinity_points=['100', '']),
                   dict(item(10, 906000104, 1), affinity_points=['', '500']), item(20, 106211340, 10),
                   item(20, 293000100, 1), item(20, 293000200, 1), item(50, 1, 100)]
        banner.pop('pool', None)
        banner['reward_pool'] = [dict(r, rate=1 / len(choices)) for r in choices]
        banner['rate_notice'] = ('LOCAL RATES: equal chance for each reward type shown on the original banner. '
                                 'The unprinted Lapis quantity is locally set to 100.')
    if digest == '164171bef56ba533d6320ca66b0d02b1':
        choices = [(23, 100, 1, .33), (23, 100, 2, .19), (50, 1, 5, .24),
                   (50, 1, 10, .13), (50, 1, 50, .07), (50, 1, 150, .04)]
        banner.pop('pool', None)
        banner['reward_pool'] = [dict(item(k, iid, count), rate=rate) for k, iid, count, rate in choices]
        banner['daily_limit'] = 7
        banner['milestone_bonus'] = {'every': 50, 'rewards': [item(50, 1, 250), item(23, 110003, 75)]}
        banner['rate_notice'] = ('The original wiki estimated odds are used. Seven free local spins per day; '
                                 'every 50 spins also awards 250 Lapis and 75 VIP Coins. No video is required.')
        banner['historical_notice'] = {'url': 'https://exvius.fandom.com/wiki/Rewards_Wheel'}


def destruction_boxes():
    """The recovered Global reward quantities, including each material type."""
    def entry(kind, iid, copies, count=1, featured=False, affinity=None):
        from gacha_rates import reward_name
        row = {'kind': kind, 'id': iid, 'count': count}
        if affinity:
            row['affinity_points'] = affinity
        return {'reward': row, 'copies': copies, 'featured': featured,
                'label': reward_name(row)}
    pots = [905000104, 900000301, 900001301, 900002301, 900003301, 900004301, 900005301]
    materials = [290050500, 290060100, 290060300, 290060000, 290060200, 290060400]
    forticite = [[271000100 + (colour * 3 + tier) * 100 for colour in range(6)] for tier in range(3)]
    # Each tuple is box-specific original copies: burst pot, other pots,
    # snappers, towers, cactuars, three forticite tiers, awakening material, crystal.
    counts = [(3, 3, 7, 3, 0, 21, 6, 0, 14, 14),
              (10, 5, 4, 3, 0, 20, 5, 0, 13, 13),
              (10, 10, 7, 6, 0, 37, 15, 1, 13, 13),
              (10, 10, 5, 11, 10, 30, 15, 2, 16, 16),
              (10, 10, 4, 8, 10, 30, 15, 4, 14, 14)]
    boxes = []
    for index, values in enumerate(counts):
        burst, other, snaps, towers, cactuars, t1, t2, t3, material, crystal = values
        box = [entry(20, 1209002045, 1, count=400, featured=True)]
        if index == 0:
            box += [entry(21, 409048000, 1, featured=True), entry(23, 110160, 3, featured=True)]
        elif index == 1:
            box += [entry(21, 409062400, 1, featured=True), entry(23, 110160, 5, featured=True)]
        else:
            box += [entry(23, 110180, 4 if index == 4 else 1, featured=True)]
        box += [entry(20, 106211340, 2), entry(23, 110160, 1)]
        if index < 2:
            box.append(entry(23, 260, 1))
        if index:
            box.append(entry(10, 904000105 if index == 4 else 904000104,
                             [0, 1, 3, 5, 5][index], affinity=['100' if index == 4 else '50', '']))
        if index == 4:
            box.append(entry(23, 110170, 3))
        box += [entry(10, uid, burst if n == 0 else other) for n, uid in enumerate(pots)]
        box += [entry(10, 900010401, snaps), entry(10, 900010501, towers)]
        if cactuars:
            box.append(entry(10, 900020401, cactuars))
        for tier, quantity in enumerate((t1, t2, t3)):
            if quantity:
                box += [entry(20, iid, quantity) for iid in forticite[tier]]
        box += [entry(20, iid, material) for iid in materials]
        box.append(entry(20, 290050400, crystal))
        expected = 300 if index < 2 else 500
        if sum(row['copies'] for row in box) != expected:
            raise ValueError('Original raid box quantity does not match its recovered contents')
        boxes.append(box)
    # The original standard pool publishes eligible types without item odds.
    # Use 80% materials, 19% enhancer units and 1% ultra-rare rewards locally.
    units = [entry(10, 900020401, 1), entry(10, 904000101, 1, affinity=['10', '']),
             entry(10, 904000104, 1, affinity=['50', '']), entry(10, 904000105, 1, affinity=['100', ''])]
    item_names = [json.loads(line) for line in (ROOT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson').read_text(
        encoding='utf-8').splitlines()]
    crysts = [int(row['key'].rsplit('_', 1)[-1]) for row in item_names
              if row['v'][0].endswith(('Alcryst', 'Milcryst', 'Heavicryst', 'Giancryst', 'Purecryst'))]
    common = [entry(10, 900010501, 1)] + [entry(20, iid, 1) for tier in forticite for iid in tier]
    common += [entry(20, iid, 1) for iid in crysts + [106200100, 106211240]] + [entry(23, 100, 1)]
    rare = [entry(23, 50, 1), entry(23, 70, 1), entry(20, 106211340, 1),
            entry(20, 900000001, 1), entry(20, 293000100, 1)]
    standard = [dict(row['reward'], rate=chance / len(group))
                for chance, group in ((.8, common), (.19, units), (.01, rare)) for row in group]
    return boxes, standard


def update_arena():
    path = ROOT / 'source/server/gacha_standard.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    # The original English Arena banner depicts pots, cactuars, snappers and
    # consumables. Historical per-item probabilities were not published.
    units = [905000102, 900000101, 900001101, 900002101, 900003101, 900004101, 900005101,
             905000103, 900000201, 900001201, 900002201, 900003201, 900004201, 900005201,
             900020301, 900020401, 900010301, 900010401]
    items = [101002100, 101003100, 106000100, 106200100]
    pool = [reward(10, uid, 0.75 / len(units)) for uid in units]
    pool += [reward(20, iid, 0.25 / len(items)) for iid in items]
    for banner in doc['banners']:
        if str(banner['id']) not in ('70001', '70003'):
            continue
        banner.pop('pool', None)
        banner['reward_pool'] = pool
        banner['pool_authored'] = True
        banner['rate_notice'] = ('LOCAL RATES: enhancer units 75%, consumables 25%, split equally within each group. '
                                 'These replace the unavailable historical item rates. No rare-summon heroes are in this pool.')
        banner['notes'] = 'Original Arena Summon Ticket cost and English art. Explicit local enhancer and consumable pool.'
        banner['sources'] = [{'url': 'https://exvius.fandom.com/wiki/Summon'},
                             {'file': 'data/gacha_wiki_extra/Gacha-Arena Summon.png',
                              'sha256': 'ba368b7b3f78f7f300890c671a937c5c19b903af5cf1955e6d9b0f50e3494f9f'}]
    doc['_meta']['arena_pool'] = 'Explicit local enhancer/consumable replacement, build_reward_summons.py'
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def king_mog():
    manifest = json.loads((ROOT / 'data/gacha_wiki_extra/sources.json').read_text(encoding='utf-8'))
    source = next(row for row in manifest['images'] if row['file'] == 'Gacha-Kig Mog Raid.png')
    image = ROOT / 'data/gacha_wiki_extra' / source['file']
    if hashlib.sha256(image.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('King Mog original banner differs from recorded source')
    shutil.copyfile(image, ROOT / 'data/gacha_community/art' / image.name)
    # Estimated percentages from the original wiki's 26,467-pull community
    # survey. Random colour splits are explicitly local, not recovered odds.
    units = [(100008804, .03), (900010401, .005), (900010301, .0175),
             (900010201, .025), (900010101, .03), (900020401, .005),
             (900020301, .0175), (900020201, .025), (900020101, .03)]
    items = [(212000100, .225), (212000200, .15), (212000400, .08),
             (212000300, .08), (212000500, .08), (107000100, .02), (107000200, .02)]
    magicite = [107001100, 107001200, 107001300, 107001400, 107001500,
                107002100, 107002200, 107002300]
    megacite = [107001600, 107001700, 107001800, 107001900, 107002000,
               107002400, 107002500, 107002600]
    pool = [reward(10, uid, chance) for uid, chance in units]
    pool += [reward(20, iid, chance) for iid, chance in items]
    pool += [reward(20, iid, .15 / len(magicite)) for iid in magicite]
    pool += [reward(20, iid, .01 / len(megacite)) for iid in megacite]
    return {'id': '9400734', 'detail_id': '94007341', 'name': 'King Mog Raid Summon',
        'type': 'normal', 'tab': 'limited', 'season': 'season1', 'release': '2017-06-30',
        'exe_type': 'primary', 'draws': 1, 'single_only': True,
        'cost': {'kind': 'item', 'item_id': 106301500, 'amount': 100, 'is_coin': True},
        'schedule': {'disp_order': 1734, 'banner_type': 0,
                     'window': {'from': '2026-01-01 00:00:00', 'to': '2030-12-31 23:59:59'}},
        'art': {'banner': image.name, 'detail_banner': image.name, 'anime_file': 'gacha_animation',
                'anime_name': 'gacha_moogle_normal/anime', 'img_btn': 'gacha_btn_r'},
        'reward_pool': pool, 'pool_authored': True, 'provenance': 'named', 'source': 'global-wiki',
        'rate_notice': ('LOCAL RATES based on the original 26,467-pull wiki survey estimates. '
                        'Random magicite and megacite use an equal split across the eight colours.'),
        'sources': [{'url': source['source'], 'file': 'data/gacha_wiki_extra/' + image.name,
                     'sha256': source['sha256']},
                    {'url': 'https://exvius.fandom.com/wiki/One_Year_Anniversary,_Kupo!#Raid_Summon',
                     'basis': 'Estimation column, 26467 community pulls'}]}
