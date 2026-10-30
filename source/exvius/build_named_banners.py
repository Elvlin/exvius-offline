"""Build source/server/gacha_named.json: one banner per unused real Global banner image.

The saved Global cache (data/client/files/en/sd/static_banner/gacha) holds the English summon
banners of the final Global client, named by hash. Each image below was read by eye; the name,
step costs and draw counts are the text printed on its own banner and detail art. Featured units
are the game's own unit ids for the names on the art (F_TEXT_UNITS_NAME). Ticket ids are the
game's own items named on the art (F_TEXT_ITEM_NAME). Release months are approximate: they come
from the neighbouring dated ticket items, and every one of these banners is from the 2023-2024
client, which is Season 4.

Run: python -I source/exvius/build_named_banners.py
"""
import hashlib
import json
from pathlib import Path
import sys
import shutil
import unicodedata
import os

PROJECT = Path(__file__).resolve().parents[2]
os.environ.setdefault('FFBE_DATA', str(PROJECT / 'data'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
ART = PROJECT / 'data/client/files/en/sd/static_banner/gacha'
OUT = PROJECT / 'source/server/gacha_named.json'


def lapis(amount):
    return {'kind': 'lapis', 'amount': amount}


def ticket(item_id):
    return {'kind': 'item', 'item_id': item_id, 'amount': 1}


def steps(*rows):
    return [{'cost': lapis(cost) if cost else {'kind': 'free'}, 'draws': draws} for cost, draws in rows]


# hash, name, tab, release (approx.), cost/steps, draws, featured unit ids, detail images
BANNERS = [
    ('03ad8d03a1f090c6e70f1413e43c9c56', 'Azure and Crimson Blades Rhus NV Premium Step-Up Summon', 'limited',
     '2024-08-15', steps((1000, 4), (3000, 8), (5000, 11), (0, 6)), None, ['100045107'], 4),
    ('2737aaf0bd539ad578ad15706856c980', 'Azure Knight Lasswell Step-Up Summon', 'limited',
     '2024-08-08', steps((3000, 11), (4000, 11), (5000, 11), (5000, 11), (5000, 11), (6000, 11)), None,
     ['100044907'], 6),
    ('d952ec7166612ea380811c2bc8e853ce', 'Azure Knight Lasswell NV Premium Step-Up Summon', 'limited',
     '2024-08-08', steps((1000, 4), (3000, 8), (5000, 11), (0, 6)), None, ['100044907'], 4),
    ('9dea16ad6acf93fab24c9ccd90bbb2a8', 'C.K.Rain/H.R.Taivas NV Premium Step-Up Summon', 'limited',
     '2024-08-01', steps((1000, 4), (3000, 8), (5000, 11), (0, 6)), None, ['100044807', '100045007'], 4),
    ('baebcb30e5ce42931b56e372607d211c', 'United Forces Step-Up Summon', 'limited',
     '2024-08-22', steps((3000, 6), (4000, 9), (4000, 9), (4500, 10), (4500, 10), (5000, 11)), None,
     ['401016307', '210003007', '401016407', '401016507'], 6),
    ('43eca28c60532db1a6ebf98bf646c244', 'NV Guaranteed Special Step-Up Summon', 'limited',
     '2023-06', steps((3000, 11), (3000, 11), (3000, 11), (4000, 10), (4000, 11), (5000, 11)), None, [], 6),
    ('40339e27526da74902e32a6b6265daba', 'Featured Summon (Final Fantasy Brave Exvius)', 'limited',
     '2024-03', lapis(250), 1, ['100043107'], 1),
    ('437ed7b5e3b0166da04b446dfd2bf3b1', 'Featured Summon (Final Fantasy Brave Exvius: Hero Resurrected Taivas)',
     'limited', '2024-06', lapis(250), 1, ['100045007'], 1),
    ('11f9a39d6c4bfee7caba9ee8ef8d7990', '8th Anniversary Weekly Free 15+1 Summon', 'free',
     '2024-06', {'kind': 'free'}, 16, [], 1),
    ('2c9fb2294b385e5321fae6368ba7e938', 'The Final Daily Free 10 Summon', 'free',
     '2024-08', {'kind': 'free'}, 10, [], 1),
    ('91863e7916c47a261d8822c83c07c3f0', 'Daily Video Summon', 'free', '2023-11', {'kind': 'free'}, 1, [], 1),
    ('23d11bd0ad89e0dee2ad795bb816a4c5', '8th Anniversary NV Guaranteed Video Summon II', 'free',
     '2024-06', {'kind': 'free'}, 2, [], 1),
    ('afeb356f41009c1d029e715f9e9ce93e', '8th Anniversary Seasonal Unit Guaranteed Video Summon II', 'free',
     '2024-06', {'kind': 'free'}, 3, [], 1),
    ('164171bef56ba533d6320ca66b0d02b1', 'Rewards Wheel', 'free', '2024-06', {'kind': 'free'}, 1, [], 1),
    ('8099f68c1832301560ab134a72656b91', 'Esper of Destruction 10+1 Ticket Summon', 'free',
     '2024-03', ticket(1209002047), 11, ['100043107'], 1),
    ('a49633e33917c76f7a9166272250ee84', 'Esper of Destruction NV Guaranteed 5 Ticket Summon', 'free',
     '2024-03', ticket(1209002046), 5, ['100043107'], 1),
    ('c0dcca29a0596f4e2009188219eadd3f', '8th Anniversary 10+1 Ticket Summon', 'free',
     '2024-06', ticket(1209002123), 11, [], 1),
    ('cd9e98f305a3f746f7e2a30854e0cab3', '8th Anniversary NV Guaranteed 11 Summon', 'free',
     '2024-06', ticket(1209002107), 11, [], 1),
    ('8da769b46e600673fed70da57f505f62', 'NV Guaranteed 10+1 Summon', 'free',
     '2023-04', ticket(1209001623), 11, [], 1),
    ('435e7e03529984b0da37db11781e8450', '10+1 (3★/4★/5★/NV) Summon', 'free',
     '2023-04', ticket(1209001623), 11, [], 1),
    ('1710891530e05b8fcda2b4dee7e97988', '1/40 NV Guaranteed EX Summon', 'free',
     '2023-11', ticket(1209001975), 1, [], 1),
    ('c80787fd8f73bc54e76a4cc58c623ff2', 'NV Guaranteed EX Summon', 'free',
     '2023-05', ticket(110260), 1, [], 1),
    ('44ca2c0ff5f096ee4b3ada1a82f56cdc', 'NV Guaranteed EX Summon B', 'free',
     '2023-08', ticket(110260), 1, [], 1),
    ('2cac0c125a8b1286ec21c373fdc5a8dd', 'Curated NV Guaranteed Summon', 'free',
     '2023-07', ticket(1209001717), 1, [], 1),
    ('a705f7d65d5897fe0506f91a73dc6520', 'Brave Exvius Ticket Summon', 'free',
     '2023-12', ticket(1209001319), 1, [], 1),
    ('1e977f876d0870cc87d93576fe540a0c', 'Guaranteed NV Summon', 'free',
     '2023-01', ticket(1209001319), 1, [], 1),
    ('d79ae09adb3fca461cbf6e320aedb219', 'Guaranteed NV Summon II', 'free',
     '2023-06', ticket(1209001473), 1, [], 1),
    ('b4d7df3f62e8e4ee498f8dda5af725b3', 'Guaranteed NV Start-Up Summon', 'free',
     '2023-10', ticket(1209001925), 3, [], 1),
    ('d8ca4b999bebca646b94537786e950d6', 'Bonus Present Ticket Summon', 'free',
     '2022-12', ticket(1209001344), 1, [], 1),
    ('f06f8f2dc482ffdcf64fef87ab30fa2a', '5★ Select Summon', 'free',
     '2023-01', {'kind': 'important', 'item_id': 260, 'amount': 1}, 1, [], 1),
    ('6ca7c5fcd7d6549fcb152b0c1cceb0bb', 'Raid Box Summon: The Power of Destruction', 'free',
     '2024-03', ticket(106301000), 1, [], 1),
]

# JP-only 4.5th-anniversary banners (April-May 2020) with no Global English original. Their art was
# translated into English (data/gacha_translated/translations.json) and is bundled with the community art.
# stem, name, cost, draws, featured unit ids, guarantee, daily limit
TRANSLATED = [
    ('gacha_20200430_ability_pickup', 'Ability Awakening Celebration Featured 11-Summon (FFVII)', lapis(5000), 11,
     ['207000407', '207001107', '207000607'], {'any_of': ['207000407', '207001107', '207000607']}, 0),
    ('gacha_20200511_ability_pickup', 'Ability Awakening Celebration Featured 11-Summon (FFXIII)', lapis(5000), 11,
     ['213001007', '213001107'], {'any_of': ['213001007', '213001107']}, 0),
    ('gacha_20200430_free_FF7R', 'FINAL FANTASY VII Free 11-Summon', {'kind': 'free'}, 11,
     ['207002007'], None, 1),
    ('gacha_20200430_free_daily_10ren', 'Daily Free 10-Summon (Cloud (FFVII REMAKE))', {'kind': 'free'}, 10,
     ['207002007'], None, 1),
    ('gacha_20200511_free_daily_10ren', 'Daily Free 10-Summon (Rain -Neo Vision-)', {'kind': 'free'}, 10,
     ['100031007'], None, 1),
]
TRANSLATED_ART = PROJECT / 'data/gacha_translated'

# Additional original Global wiki art, separate from the 2016-2022 calendar.
# Each featured identity below is the shipped unit shown on that image.
WIKI_BANNERS = [
    ('Gacha-AS Kir.png', 'Arcane Scholar Kir', '401015107'),
    ('Gacha-Addison Rae.PNG', 'Cool Moves Addison Rae', '401015407'),
    ('Gacha-Angeal.png', 'Angeal', '207002707'),
    ('Gacha-Aphmau.png', 'Royal Puppeteer Aphmau', '211001507'),
    ('Gacha-BW Yshe.PNG', 'Bewitching Warrior Yshe', '100042907'),
    ('Gacha-BoBF Raegen.png', 'Blades of Black Flame Raegen', '100041707'),
    ('Gacha-BoV Ibara.png', 'Blade of Vengeance Ibara', '401014407'),
    ('Gacha-CF Hope.png', 'Challenger of Fate Hope', '213001507'),
    ('Gacha-CI Melissa.png', 'Curse of Immunity Melissa', '401014307'),
    ('Gacha-DK Duane.png', 'Dark Knight Duane', '401014507'),
    ('Gacha-Dioxus.png', 'Dioxus', '100040607'),
    ('Gacha-Dlord Rhus.PNG', 'Dragonlord Rhus', '100042807'),
    ('Gacha-DoW Taivas.PNG', 'Deity of War Taivas', '100042407'),
    ('Gacha-ED Edgar.png', 'Embracer of Duty Edgar', '206003207'),
    ('Gacha-ER Elena.png', 'Eternal Radiance Elena', '401014807'),
    ('Gacha-ES Irvine.png', 'Expert Sharpshooter Irvine', '208002707'),
    ('Gacha-FA Rain.png', 'Flaring Aether Rain', '100041207'),
    ('Gacha-FG Jecht.png', 'Fabled Guardian Jecht', '210002607'),
    ('Gacha-GU Chow.png', 'Guardian of the Underworld Chow', '401015507'),
    ('Gacha-Genesis.png', 'Genesis', '207002807'),
    ('Gacha-Jayden Rundall.png', 'Jayden Rundall (WOTV FFBE)', '339000707'),
    ('Gacha-LNY Cleome.png', 'Lunar Festival Cleome', '401014107'),
    ('Gacha-Lasswell DL.png', 'Lasswell -Dark Lineage-', '100040807'),
    ('Gacha-Lion.png', 'Lion', '211001707'),
    ('Gacha-MM Abigail.png', 'Master Machinist Abigail', '401014207'),
    ('Gacha-Mid.png', 'Mid', '100041407'),
    ('Gacha-NV Quistis.png', "SeeD's Blue Mage Quistis", '208002607'),
    ('Gacha-Nier Automata-2.png', 'NieR:Automata (2023 rerun)', '401013807'),
    ('Gacha-Noppy.png', 'Noppy', '401010407'),
    ('Gacha-PoC Sarah.PNG', 'Princess of Cornelia Sarah', '201000807'),
    ('Gacha-RE Nora.png', 'Ruin Explorer Nora', '401014607'),
    ('Gacha-Richt.png', 'Richt', '401014907'),
    ('Gacha-SK Squall.png', "Sorceress's Knight Squall", '208002507'),
    ('Gacha-Shiloh.png', 'Shiloh (Legend of Mana)', '342000307'),
    ('Gacha-Snovlinka.png', 'Snovlinka', '100041907'),
    ('Gacha-ToT Zidane.png', 'Thief of Tantalus Zidane', '209003407'),
    ('Gacha-VCZ Ace.png', 'Vermilion Class Zero Ace', '254002307'),
    ('Gacha-VCZ Trey.png', 'Vermilion Class Zero Trey', '254002507'),
    ('Gacha-VV Fina.png', 'Vacation Voyager Fina', '100040407'),
    ('Gacha-VoF.png', 'Veritas of the Frost', '100041007'),
    ('Gacha-WF Lightning.png', 'Wondrous Flash Lightning', '213001407'),
    ('Gacha-WH Gilga.png', "World's Hero Gilgamesh", '205002007'),
    ('Gacha-WW Bartz.png', 'World Wayfarer Bartz', '205001807'),
    ('Gacha-WoM Malphasie.png', 'Wings of Midnight Malphasie', '401015007'),
    ('Gacha- Chrono Cross.png', 'CHRONO CROSS', '345000107'),
    ('Gacha-Edward Elric.png', 'Edward Elric (Fullmetal Alchemist Brotherhood)', '338000105'),
    ('Gacha-Halloween-Demon Rain.png', 'Halloween (2017)', '401000205'),
    ('Gacha-YH Zack.png', 'Young Hero Zack', '207002607'),
]

# The names of the shipped exchange currencies identify the original campaign
# partners as well as the coin/ticket paid by each printed 11-summon offer.
WIKI_CAMPAIGNS = {
    'Gacha-AS Kir.png': (1209001889, []),
    'Gacha-Addison Rae.PNG': (1209001909, []),
    'Gacha-Angeal.png': (1209001810, []),
    'Gacha-Aphmau.png': (1209001404, []),
    'Gacha-BW Yshe.PNG': (1209001936, ['100042807']),
    'Gacha-BoBF Raegen.png': (1209001818, ['100041807']),
    'Gacha-BoV Ibara.png': (1209001783, []),
    'Gacha-CF Hope.png': (1209001893, []),
    'Gacha-CI Melissa.png': (1209001776, []),
    'Gacha-DK Duane.png': (1209001800, []),
    'Gacha-Dioxus.png': (1209001787, []),
    'Gacha-Dlord Rhus.PNG': (1209001936, ['100042907']),
    'Gacha-DoW Taivas.PNG': (1209001928, []),
    'Gacha-ED Edgar.png': (1209001700, []),
    'Gacha-ER Elena.png': (1209001851, []),
    'Gacha-ES Irvine.png': (1209001828, []),
    'Gacha-FA Rain.png': (1209001798, ['100041307']),
    'Gacha-FG Jecht.png': (1209001657, []),
    'Gacha-GU Chow.png': (1209001940, []),
    'Gacha-Genesis.png': (1209001804, []),
    'Gacha-Jayden Rundall.png': (1209001887, ['339000807']),
    'Gacha-LNY Cleome.png': (1209001739, []),
    'Gacha-Lasswell DL.png': (1209001789, ['100040907']),
    'Gacha-Lion.png': (1209001780, []),
    'Gacha-MM Abigail.png': (1209001764, []),
    'Gacha-Mid.png': (1209001769, []),
    'Gacha-NV Quistis.png': (1209001835, []),
    'Gacha-Nier Automata-2.png': (1209001855, ['401013907']),
    'Gacha-Noppy.png': (1209001402, []),
    'Gacha-PoC Sarah.PNG': (1209001938, ['203004507']),
    'Gacha-RE Nora.png': (1209001823, []),
    'Gacha-Richt.png': (1209001853, []),
    'Gacha-SK Squall.png': (1209001833, []),
    'Gacha-Shiloh.png': (1209001837, ['342000407']),
    'Gacha-Snovlinka.png': (1209001877, ['100042007']),
    'Gacha-ToT Zidane.png': (1209001879, ['209003607']),
    'Gacha-VCZ Ace.png': (1209001842, ['254002607']),
    'Gacha-VCZ Trey.png': (1209001846, []),
    'Gacha-VV Fina.png': (1209001758, ['100040507']),
    'Gacha-VoF.png': (1209001793, ['100041107']),
    'Gacha-WF Lightning.png': (1209001891, []),
    'Gacha-WH Gilga.png': (1209001762, []),
    'Gacha-WW Bartz.png': (1209001744, ['205001907']),
    'Gacha-WoM Malphasie.png': (1209001881, []),
    'Gacha- Chrono Cross.png': (1209001695, ['345000207', '345000307']),
    'Gacha-YH Zack.png': (1209001812, []),
}


def normalized_name(name):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKC', name)
                            if unicodedata.category(c) != 'Cf').split()).casefold()


def reconcile_community_names():
    """Restore wiki featured names lost to invisible direction marks in names."""
    from player_state import unit_roots_by_rarity, unit_mst
    roots = {uid for group in unit_roots_by_rarity().values() for uid in group}
    names = {}
    table = PROJECT / 'data/text_decoded/F_TEXT_UNITS_NAME.ndjson'
    for line in table.read_text(encoding='utf8').splitlines():
        row = json.loads(line)
        uid = row['key'].rsplit('_', 1)[-1]
        if uid in roots:
            names.setdefault(normalized_name(row['v'][0]), []).append(uid)
    path = PROJECT / 'source/server/gacha_community.json'
    doc = json.loads(path.read_text(encoding='utf8'))
    fixed = 0
    for banner in doc['banners']:
        community = banner.get('community') or {}
        ids = community.setdefault('unit_ids', [])
        for name in community.get('units', []):
            candidates = names.get(normalized_name(name), [])
            if len(candidates) == 1 and candidates[0] not in ids:
                ids.append(candidates[0])
                fixed += 1
        pool = banner.get('pool')
        tiers = pool.get('tiers', []) if isinstance(pool, dict) else []
        for uid in ids:
            rarity = int((unit_mst(uid) or {}).get('9fW0TePj', 0))
            tier = next((t for t in tiers if int(t.get('rarity', 0)) == rarity), None)
            if tier is not None and any(t.get('featured') for t in tiers) and uid not in tier.get('featured', []):
                tier.setdefault('featured', []).append(uid)
                tier.setdefault('featured_share', 0.5)
                fixed += 1
    if fixed:
        doc['_meta']['name_reconciliation'] = 'NFKC and invisible direction marks, build_named_banners.py'
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    print('Restored', fixed, 'missing featured unit mappings')


def reconcile_curated_art():
    """Replace unrelated JP artwork with the matching original Global campaign."""
    import copy
    community_path = PROJECT / 'source/server/gacha_community.json'
    curated_path = PROJECT / 'source/server/gacha_authored.json'
    calendar = json.loads(community_path.read_text(encoding='utf-8'))
    curated = json.loads(curated_path.read_text(encoding='utf-8'))
    summer = next(b for b in calendar['banners'] if str(b['id']) == '9100189')
    identity = 'global:ffbe:2019-05-31:summer-fina-lid-folka-citra'
    summer['campaign_identity'] = identity
    summer['alias_ids'] = sorted(set(summer.get('alias_ids', []) + ['49']))
    for index, banner in enumerate(curated['banners']):
        if str(banner['id']) == '49':
            replacement = copy.deepcopy(summer)
            replacement.update(id='49', detail_id='49001', name_override=True)
            replacement['notes'] = ('Original catalogue ID 49 is mapped to the Global campaign with the same '
                                    'Summer Fina & Lid and Summer Folka & Citra units. The duplicate calendar entry is canonical.')
            curated['banners'][index] = replacement
        elif str(banner['id']) == '75':
            banner.pop('ticket_group_id', None)
            banner.update(cost={'kind': 'item', 'item_id': 1209000967, 'amount': 1}, tab='free', release='2019-05-03')
            banner['art'].update(banner='Gacha-FFIV-BM Golbez.png', detail_banner='Gacha-FFIV-BM Golbez.png')
            banner['notes'] = ('Original 100% Black Mage Golbez ticket, item 1209000967. '
                               'English artwork is from the matching Global FFIV campaign; it is not a recovered ticket-specific image.')
            banner['rate_notice'] = 'Black Mage Golbez is guaranteed. This requires the original Black Mage Golbez ticket.'
            image = PROJECT / 'data/gacha_community/art/Gacha-FFIV-BM Golbez.png'
            banner['sources'] = [{'url': 'https://static.wikia.nocookie.net/exvius_gamepedia_en/images/3/3e/Gacha-FFIV-BM_Golbez.png/revision/latest?cb=20190503115641',
                                  'sha256': sha256(image), 'file': str(image.relative_to(PROJECT)).replace('\\', '/')}]
        elif str(banner['id']) == '150':
            from datetime import date
            from gacha_archive import _released
            from player_state import unit_mst
            eligible = {uid for b in calendar['banners'] if _released(b) and _released(b) <= date(2019, 8, 31)
                        and not (b.get('community') or {}).get('limited')
                        for uid in (b.get('community') or {}).get('unit_ids', [])}
            banner['pool'] = {'tiers': [{'rarity': rarity, 'rate': chance,
                'units': sorted(uid for uid in eligible if int(unit_mst(uid)['9fW0TePj']) == rarity)}
                for rarity, chance in ((5, .03), (4, .17), (3, .8))]}
            def reward(kind, iid, count=1, affinity=None):
                return {'kind': kind, 'id': iid, 'count': count, **({'affinity_points': affinity} if affinity else {})}
            moogle5 = reward(10, 904000104, affinity=['50', ''])
            moogle10 = reward(10, 904000105, affinity=['100', ''])
            alternatives = [None, [moogle5, moogle10], [reward(23, 160), reward(23, 50)],
                            [reward(23, 50), reward(23, 70)]]
            banner['steps'] = []
            for step, draws in enumerate((2, 3, 3, 4)):
                row = {'cost': {'kind': 'item', 'item_id': 1209001041, 'amount': 1},
                       'draws': draws, 'guarantee': {'rarity': 4, 'count': 1}}
                if step == 0:
                    row['bonus_rewards'] = [moogle5]
                else:
                    row['bonus_choice'] = [{'rate': .5, 'rewards': [r]} for r in alternatives[step]]
                banner['steps'].append(row)
            banner.update(tab='limited', season='season2', release='2019-09-01', pool_authored=True,
                          lap_limit=6, name_override=True)
            banner['rate_notice'] = ('LOCAL POOL: recovered permanent Global units released by August 2019. '
                'Rates 5-star 3%, 4-star 17%, 3-star 80%, with the original printed guaranteed slots. '
                'Unpublished bonus alternatives use an equal local split.')
            banner['historical_notice'] = {'url': 'https://www.reddit.com/r/FFBraveExvius/comments/cxk9oc/gl_news_clarification_40m_download_stepups_are/'}
            recovered = json.loads((PROJECT / 'data/gacha_wiki_extra/sources.json').read_text(encoding='utf8'))
            image_source = next(row for row in recovered['recoveries'] if row['file'] == 'Gacha-40M DL Step-Up.png')
            image = PROJECT / 'data/gacha_wiki_extra' / image_source['file']
            if sha256(image) != image_source['sha256']:
                raise ValueError('Recovered 40M English artwork differs from its recorded source')
            shutil.copyfile(image, PROJECT / 'data/gacha_community/art' / image.name)
            banner['art'].update(banner=image.name, detail_banner=image.name, detail_extra=[])
            banner['sources'] = [{'url': image_source['recording'], 'image_url': image_source['source'],
                'file': str(image.relative_to(PROJECT)).replace('\\', '/'),
                'sha256': image_source['sha256'], 'source_sha256': image_source['source_sha256'],
                'recovery': image_source['method'], 'limitation': image_source['limitation']}]
            banner['notes'] = ('Original four ticket steps, six-lap limit and reward quantities restored. '
                               'English art recovered from the original Global recording thumbnail; '
                               'low resolution and a recorder control at the far-right edge remain.')
    community_path.write_text(json.dumps(calendar, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    curated_path.write_text(json.dumps(curated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wiki_banners(nv_units):
    """Keep originals, and copy the verified whole image to the runtime art home."""
    directory = PROJECT / 'data/gacha_wiki_extra'
    manifest = json.loads((directory / 'sources.json').read_text(encoding='utf8'))
    sources = {row['file']: row for row in manifest['images']}
    runtime = PROJECT / 'data/gacha_community/art'
    item_names = {row['key'].rsplit('_', 1)[-1]: row['v'][0] for row in
                  map(json.loads, (PROJECT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson').read_text(encoding='utf8').splitlines())}
    item_ids = {name: iid for iid, name in item_names.items()}
    banners = []
    for index, (filename, name, unit) in enumerate(WIKI_BANNERS, 1):
        source = sources[filename]
        original = directory / filename
        if sha256(original) != source['sha256']:
            raise ValueError('Wiki art differs from its recorded source: ' + filename)
        target = runtime / filename
        if not target.exists() or sha256(target) != source['sha256']:
            shutil.copyfile(original, target)
        release = source['uploaded'][:10]
        units = [unit]
        campaign = WIKI_CAMPAIGNS.get(filename)
        if campaign:
            units.extend(u for u in campaign[1] if u not in units)
        if 'Nier Automata' in filename:
            units.append('401013907')
        elif 'Chrono Cross' in filename:
            units.extend(['345000207', '345000307'])
        elif 'Edward Elric' in filename:
            units.extend(['338000205', '338000404', '338000503'])
        elif 'Halloween-Demon Rain' in filename:
            units.extend(['401000305', '401000404', '401000503'])
        pool = [{'rarity': 5, 'rate': 0.10}, {'rarity': 4, 'rate': 0.35}, {'rarity': 3, 'rate': 0.50}]
        from player_state import unit_mst
        featured = {}
        for uid in units:
            rarity = int(unit_mst(uid)['9fW0TePj'])
            featured.setdefault(rarity, []).append(uid)
        if 7 in featured:
            pool.insert(0, {'rarity': 7, 'rate': 0.05, 'units': nv_units,
                            'featured': featured[7], 'featured_share': 0.2})
        else:
            pool[0]['rate'] += 0.05
        for tier in pool:
            if tier['rarity'] in featured:
                tier.update(featured=featured[tier['rarity']], featured_share=0.5)
        bid = str(9300000 + index)
        banners.append({'id': bid, 'type': 'normal', 'name': name + ' Featured Summon',
            'historical_name': name + ' Featured Summon', 'detail_id': str(int(bid) * 10 + 1),
            'exe_type': 'primary', 'cost': lapis(500), 'draws': 1,
            'secondary_offer': {'cost': lapis(5000), 'draws': 11, 'exe_count': 1,
                                'img_btn': 'gacha_btns_gold_11',
                                'guarantee': {'rarity': 4 if ('Edward Elric' in filename or 'Halloween-Demon Rain' in filename) else 5}},
            'schedule': {'disp_order': 3000 + index, 'banner_type': 0,
                         'window': {'from': '2026-01-01 00:00:00', 'to': '2030-12-31 23:59:59'}},
            'art': {'banner': filename, 'detail_banner': filename, 'anime_file': 'gacha_animation',
                    'anime_name': 'gacha_moogle_rare/anime', 'img_btn': 'gacha_btn_n'},
            'pool': {'tiers': pool}, 'pool_authored': True, 'tab': 'limited',
            'release': release, 'release_evidence': 'Wiki image upload, approximate browsing date',
            'provenance': 'named', 'source': 'global-wiki',
            'rate_notice': 'LOCAL RATES: replacement pool; this is not a recovered historical rate table.',
            'sources': [{'file': str(original.relative_to(PROJECT)).replace('\\', '/'),
                         'url': source['source'], 'sha256': source['sha256']}]} )
        if campaign:
            coin = str(campaign[0])
            ticket_name = item_names[coin].replace('Summon Coin', 'NV Exchange Ticket', 1)
            ticket_id = item_ids[ticket_name]
            banners[-1]['secondary_offer']['bonus_rewards'] = [
                {'kind': 20, 'id': int(coin), 'count': 1},
                {'kind': 20, 'id': int(ticket_id), 'count': 1}]
    unique, campaigns = [], {}
    for banner in banners:
        filename = banner['art']['banner']
        campaign = WIKI_CAMPAIGNS.get(filename)
        identity = (campaign[0], banner['release']) if campaign else ('file', filename)
        if identity in campaigns:
            canonical = campaigns[identity]
            canonical['art'].setdefault('detail_extra', []).append(filename)
            canonical['sources'].extend(banner['sources'])
            canonical.setdefault('alias_ids', []).append(banner['id'])
            if campaign[0] == 1209001936:
                canonical['name'] = 'Dragonlord Rhus / Bewitching Warrior Yshe Featured Summon'
                canonical['historical_name'] = 'Dragonlord Rhus / Bewitching Warrior Yshe Featured Summon'
            continue
        campaigns[identity] = banner
        unique.append(banner)
    return unique

# The JP 4.5th-anniversary specials (Elv, 2026-10-24), paid with their own JP ticket items (106213030-080,
# shipped in F_ITEM_MST; sold in the Shop as local bundles, global_bundles.json). The JP rosters and rates
# were never published in full (research: logs/reference/jp_specials/), so the pools below are AUTHORED:
# the SP tickets keep their printed rarity floors, the event summons draw the unit rewards their art and the
# JP notices name (Zenaida, trust moogles, pots, metal cactuars); their item rewards are not drawn.
# The Super Premium Box is a fixed 10,000-Lapis bundle, so it is a Shop bundle, not a summon.
# stem, name, cost, draws, tiers
def featured_nv_units():
    """The NV (rarity 7) units Global banners actually featured: the SP pools draw NV from these, not from
    every rarity-7 row (a 743-unit tier made the banner rows too many to open, phone 2026-10-25)."""
    import glob
    sys.path.insert(0, str(PROJECT / 'source/server'))
    from player_state import unit_mst
    ids = set()
    for path in glob.glob(str(PROJECT / 'source/server/gacha_*.json')):
        if path.endswith('gacha_named.json'):
            continue
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
        for b in (doc if isinstance(doc, list) else doc.get('banners') or []):
            if not isinstance(b, dict):
                continue
            pool = b.get('pool') if isinstance(b.get('pool'), dict) else {}
            for tier in pool.get('tiers') or []:
                ids.update(str(u) for u in tier.get('featured') or [])
            ids.update(str(u) for u in (b.get('community') or {}).get('unit_ids') or [])
    return sorted(u for u in ids if str((unit_mst(u) or {}).get('9fW0TePj')) == '7')


JP_SPECIALS = [
    ('gacha_20200430_special_rare3', 'SP Special Summon', ticket(106213040), 1,
     [{'rarity': 7, 'rate': 0.01, 'units': 'NV'}, {'rarity': 5, 'rate': 0.04}, {'rarity': 4, 'rate': 0.25}, {'rarity': 3, 'rate': 0.70}]),
    ('gacha_20200430_special_rare4', '4★/5★/NV SP Special Summon', ticket(106213050), 1,
     [{'rarity': 7, 'rate': 0.03, 'units': 'NV'}, {'rarity': 5, 'rate': 0.17}, {'rarity': 4, 'rate': 0.80}]),
    ('gacha_20200430_special_rare5', '5★/NV SP Special Summon', ticket(106213030), 1,
     [{'rarity': 7, 'rate': 0.20, 'units': 'NV'}, {'rarity': 5, 'rate': 0.80}]),
    ('gacha_20200511_FFBE_omake', 'Bonus Summon', ticket(106213060), 1,
     [{'rarity': 5, 'rate': 1.0, 'units': ['906000105', '905000104', '900020401']}]),
    ('gacha_20200511_bossrush', 'Boss Rush Event Summon', ticket(106213070), 1,
     [{'rarity': 5, 'rate': 0.10, 'featured': ['100028205'], 'featured_share': 0.2}, {'rarity': 4, 'rate': 0.40},
      {'rarity': 4, 'rate': 0.50, 'units': ['906000105', '900010501', '900020401']}]),
    ('gacha_20200511_brave_ability', 'Brave Ability Enhancement Box Summon', ticket(106213080), 1,
     [{'rarity': 5, 'rate': 1.0, 'units': ['904000105', '905000104', '900020401']}]),
]


# Guaranteed slots read from each original detail image. Missing NV pools
# must refuse the pull before payment rather than substitute lower rarities.
PRINTED_GUARANTEES = {
    '03ad8d03a1f090c6e70f1413e43c9c56': {0: (5, 2), 1: (5, 5), 2: (5, 11), 3: (5, 1)},
    '2737aaf0bd539ad578ad15706856c980': {0: (5, 1), 1: (5, 5), 2: (5, 11),
                                        3: (7, 1), 4: (7, 1), 5: (7, 1)},
    'd952ec7166612ea380811c2bc8e853ce': {0: (5, 2), 1: (5, 5), 2: (5, 11), 3: (5, 1)},
    '9dea16ad6acf93fab24c9ccd90bbb2a8': {0: (5, 2), 1: (5, 5), 2: (5, 11), 3: (5, 1)},
    'baebcb30e5ce42931b56e372607d211c': {0: (5, 6), 1: (7, 2), 2: (7, 2),
                                        3: (7, 3), 4: (7, 3), 5: (7, 2)},
    '43eca28c60532db1a6ebf98bf646c244': {0: (7, 2), 1: (7, 2), 2: (7, 3),
                                        3: (7, 6), 4: (7, 6), 5: (7, 9)},
}

# Original notices and their contemporary transcriptions. These establish
# dates, featured identities and printed steps, not a recovered full draw pool.
ORIGINAL_NOTICES = {
    '03ad8d03a1f090c6e70f1413e43c9c56': {
        'url': 'https://exvius.fandom.com/wiki/Update_Schedule',
        'notice': '20240813gbehACRhusFeaturedSummon0829Update.html'},
    '2737aaf0bd539ad578ad15706856c980': {
        'url': 'https://www.reddit.com/r/FFBraveExvius/comments/1en21y9/gl_gacha_megathread_ffbe_nv_aklasswell_08080904/'},
    'd952ec7166612ea380811c2bc8e853ce': {
        'url': 'https://www.reddit.com/r/FFBraveExvius/comments/1en21y9/gl_gacha_megathread_ffbe_nv_aklasswell_08080904/'},
    '9dea16ad6acf93fab24c9ccd90bbb2a8': {
        'url': 'https://exvius.fandom.com/wiki/Update_Schedule',
        'notice': '20240730gbehaRainTaivasFeaturedSummon0829Update.html'},
    'baebcb30e5ce42931b56e372607d211c': {
        'url': 'https://www.reddit.com/r/FFBraveExvius/comments/1ewooeq/gl_news_821_maintenance_august_crest_pass/',
        'featured_units': ['401016307', '210003007', '401016407', '401016507'],
        'notice': '20240820agehUnitedForcesStepUpSummonExchange.html'},
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def printed_bonuses(banner, digest):
    """Bonuses read from the original step art, using shipped item/unit IDs."""
    def item(iid, count=1, kind=20, **metadata):
        return {'kind': kind, 'id': iid, 'count': count, **metadata}

    premium = {
        '03ad8d03a1f090c6e70f1413e43c9c56': (1209002143, 1209002144, 11),
        'd952ec7166612ea380811c2bc8e853ce': (1209002141, 1209002142, 11),
        '9dea16ad6acf93fab24c9ccd90bbb2a8': (1209002138, 1209002139, 22),
    }
    if digest in premium:
        coin, exchange, limit = premium[digest]
        banner['lap_limit'] = limit
        for step in banner['steps'][:3]:
            step['bonus_rewards'] = [item(coin), item(exchange)]
    elif digest == '2737aaf0bd539ad578ad15706856c980':
        banner['lap_limit'] = 2
        extras = [[], [item(250034000, 25)],
                  [item(250034000, 25), item(110003, 100, 23)], [],
                  [item(110003, 200, 23)], [item(1209002140)]]
        for index, step in enumerate(banner['steps']):
            step['bonus_rewards'] = [item(1209002141, 2 if index == 5 else 1),
                                     item(1209002142), *extras[index]]
    elif digest == 'baebcb30e5ce42931b56e372607d211c':
        banner['lap_limit'] = 1
        rewards = [[item(906000105, kind=10, affinity_points=['', '1000'])], [item(902000505, kind=10)],
                   [item(1209001907)], [item(1209002122, 1000)],
                   [item(1209002122, 1000)], [item(1209002145)]]
        for step, reward in zip(banner['steps'], rewards):
            step['bonus_rewards'] = reward
    elif digest == '43eca28c60532db1a6ebf98bf646c244':
        for index, step in enumerate(banner['steps']):
            step['bonus_rewards'] = [item(106211340, 20)]
            if index < 2:
                step['bonus_rewards'].append(item(904000105, kind=10, affinity_points=['1000', '']))
            if index in (2, 3, 4):
                step['bonus_rewards'].append(item(1209001670, 1 if index == 2 else 2))
            if index in (3, 5):
                step['bonus_rewards'].append(item(1209001717))
            if index == 4:
                step['bonus_rewards'].append(item(290050500, 2))
        banner['bonus_provenance'] = {
            'source': 'Original Global detail art, 43eca28c60532db1a6ebf98bf646c244_01 through _06.png',
            'replacement_mapping': 'Unidentified historical ticket instances use existing NV Guaranteed Special fragment ticket 1670 and playable curated NV ticket 1717. The step-five crystal bonus uses two Transcension Pearls.'}


def main():
    sys.path.insert(0, str(PROJECT / 'source/server'))
    from player_state import unit_mst
    reconcile_community_names()
    reconcile_curated_art()
    banners = []
    nv = featured_nv_units()
    local_nv = sorted(set(nv + [u for row in BANNERS[:6] for u in row[6]] +
                          [u for _, _, u in WIKI_BANNERS if str(unit_mst(u)['9fW0TePj']) == '7']))
    for n, (digest, name, tab, release, cost, draws, units, details) in enumerate(BANNERS, 1):
        main_file = ART / 'main' / (digest + '.png')
        detail_files = [ART / 'sub' / f'{digest}_{i:02d}.png' for i in range(1, details + 1)]
        tier5 = {'rarity': 5, 'rate': 0.05}
        if units:
            tier5.update(featured=units, featured_share=0.5)
        banner = {
            'id': str(9200000 + n), 'type': 'step' if isinstance(cost, list) else 'normal', 'name': name,
            'detail_id': str((9200000 + n) * 10 + 1), 'exe_type': 'primary',
            'schedule': {'disp_order': 2000 + n, 'banner_type': 0,
                         'window': {'from': '2026-01-01 00:00:00', 'to': '2030-12-31 23:59:59'}},
            'art': {'banner': main_file.name, 'detail_banner': detail_files[0].name,
                    'detail_extra': [f.name for f in detail_files[1:]],
                    'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_rare/anime',
                    'img_btn': 'gacha_btn_n'},
            'pool': {'tiers': [tier5, {'rarity': 4, 'rate': 0.25}, {'rarity': 3, 'rate': 0.70}]},
            'tab': tab, 'season': 'season4', 'release': release,
            'provenance': 'named', 'source': 'global-cache',
            'sources': [{'file': str(f.relative_to(PROJECT)).replace('\\', '/'), 'sha256': sha256(f)}
                        for f in [main_file] + detail_files],
        }
        if isinstance(cost, list):
            import copy
            banner['steps'] = copy.deepcopy(cost)
            for index, (rarity, count) in PRINTED_GUARANTEES.get(digest, {}).items():
                banner['steps'][index]['guarantee'] = {'rarity': rarity, 'count': count}
            banner['gacha_layout'] = 2
        else:
            banner['cost'] = cost
            banner['draws'] = draws
        if digest in ORIGINAL_NOTICES:
            banner['historical_notice'] = ORIGINAL_NOTICES[digest]
        if n <= 6:
            # User approved replacement pools without labels in game on 2026-10-25.
            # Keep their provenance in this source and the generated records.
            nv_tier = {'rarity': 7, 'rate': 0.05, 'units': local_nv}
            if units:
                nv_tier.update(featured=units, featured_share=0.2 if n < 5 else 0.8)
            if n == 5:
                banner['pool'] = {'tiers': [nv_tier, {'rarity': 5, 'rate': 0.95}]}
                notice = 'LOCAL RATES: NV 5%, 5★ 95%.'
            elif n == 6:
                nv_tier['rate'] = 0.2
                banner['pool'] = {'tiers': [nv_tier, {'rarity': 5, 'rate': 0.8}]}
                notice = 'LOCAL RATES: NV 20%, 5★ 80%.'
            else:
                banner['pool'] = {'tiers': [nv_tier, {'rarity': 5, 'rate': 0.10},
                                          {'rarity': 4, 'rate': 0.35}, {'rarity': 3, 'rate': 0.50}]}
                notice = 'LOCAL RATES: NV 5%, 5★ 10%, 4★ 35%, 3★ 50%.'
            banner['pool_authored'] = True
            banner['historical_name'] = banner['name']
            banner['rate_notice'] = notice + '\nPrinted guarantees apply. This is a local replacement drop table.'
            if n == 2:
                for index, share in ((3, 0.02), (4, 0.025), (5, 0.05)):
                    banner['steps'][index]['guarantee']['pool'] = {'tiers': [
                        {'rarity': 7, 'rate': 1.0, 'units': local_nv,
                         'featured': units, 'featured_share': share}]}
        else:
            nv_tier = {'rarity': 7, 'rate': .05, 'units': local_nv}
            if units:
                nv_tier.update(featured=units, featured_share=.2)
            banner['pool'] = {'tiers': [nv_tier, {'rarity': 5, 'rate': .10},
                {'rarity': 4, 'rate': .35}, {'rarity': 3, 'rate': .50}]}
            banner['pool_authored'] = True
            banner['rate_notice'] = ('LOCAL RATES: NV 5%, 5-star 10%, 4-star 35%, 3-star 50%. '
                                     'Printed guarantees apply. This replaces the unavailable original table.')
            if 'NV Guaranteed 10+1' in name:
                banner['guarantee'] = {'rarity': 7, 'count': 1}
            elif 'Guaranteed' in name and 'NV' in name:
                nv_tier['rate'] = 1
                banner['pool'] = {'tiers': [nv_tier]}
                banner['guarantee'] = {'rarity': 7, 'count': int(draws)}
                banner['rate_notice'] = 'LOCAL UNIT POOL: every draw is a guaranteed NV unit. Exact unit probabilities are listed below.'
            elif '10+1' in name:
                banner['guarantee'] = {'rarity': 5, 'count': 1}
            elif '5★ Select' in name:
                banner['pool'] = {'tiers': [{'rarity': 5, 'rate': 1}]}
                banner['guarantee'] = {'rarity': 5}
            if cost == {'kind': 'free'}:
                banner['weekly_limit' if 'Weekly' in name else 'daily_limit'] = 1
                banner['single_only'] = True
            if digest in ('40339e27526da74902e32a6b6265daba', '437ed7b5e3b0166da04b446dfd2bf3b1'):
                banner['daily_limit'] = 1
                banner['single_only'] = True
        printed_bonuses(banner, digest)
        if digest == 'f06f8f2dc482ffdcf64fef87ab30fa2a':
            banner.update(type='select', selection=True, cost={'kind': 'important', 'item_id': 260, 'amount': 10})
            banner.pop('pool', None)
            banner.pop('guarantee', None)
            banner['rate_notice'] = 'Choose the unit or prism. There is no random draw. Original master ticket prices apply.'
        if digest == '1710891530e05b8fcda2b4dee7e97988':
            banner['cost']['amount'] = 40
        if digest == '435e7e03529984b0da37db11781e8450':
            banner['cost']['item_id'] = 1300000007
        from build_reward_summons import regular_offers
        regular_offers(banner, digest, local_nv)
        if digest == '43eca28c60532db1a6ebf98bf646c244':
            from player_state import unit_roots_by_rarity
            rows = [json.loads(line) for line in (PROJECT / 'data/mst_decoded/F_UNIT_MST.ndjson').read_text(
                encoding='utf-8').splitlines()]
            roots = set(unit_roots_by_rarity().get('5', []))
            awakenable = sorted({r['woghJa61'] for r in rows if r['woghJa61'] in roots and
                                 r.get('JPW8Vs40') not in (None, '', '0')})
            banner['steps'][-1]['guarantee_slots'] = [{
                'count': 2, 'label': 'NV-awakenable base 5-star unit',
                'pool': {'tiers': [{'rarity': 5, 'rate': 1, 'units': awakenable}]}}]
        banners.append(banner)
    log = {e['output']: e for e in json.loads((TRANSLATED_ART / 'translations.json').read_text(encoding='utf-8'))['images']}
    for n, (stem, name, cost, draws, units, guarantee, daily) in enumerate(TRANSLATED, 101):
        top, detail = stem + '_top_en.png', stem + '_en.png'
        banner = {
            'id': str(9200000 + n), 'type': 'normal', 'name': name,
            'detail_id': str((9200000 + n) * 10 + 1), 'exe_type': 'primary',
            'schedule': {'disp_order': 2000 + n, 'banner_type': 0,
                         'window': {'from': '2026-01-01 00:00:00', 'to': '2030-12-31 23:59:59'}},
            'art': {'banner': top, 'detail_banner': detail,
                    'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_rare/anime',
                    'img_btn': 'gacha_btn_n'},
            'pool': {'tiers': [{'rarity': 5, 'rate': 0.05, 'featured': units, 'featured_share': 0.5},
                               {'rarity': 4, 'rate': 0.25}, {'rarity': 3, 'rate': 0.70}]},
            'cost': cost, 'draws': draws,
            'tab': 'limited', 'season': 'season3', 'release': stem.split('_')[1][:4] + '-' + stem.split('_')[1][4:6],
            'provenance': 'named', 'source': 'translated-jp',
            'sources': [{'file': 'data/gacha_translated/' + f, 'sha256': log[f]['output_sha256'],
                         'translated_from': log[f]['source_file'], 'source_sha256': log[f]['source_sha256']}
                        for f in (top, detail)],
        }
        if guarantee:
            banner['guarantee'] = guarantee
        if daily:
            banner['daily_limit'] = daily
        banners.append(banner)
    for n, (stem, name, cost, draws, tiers) in enumerate(JP_SPECIALS, 101 + len(TRANSLATED)):
        tiers = [dict(t, units=nv) if t.get('units') == 'NV' else t for t in tiers]
        top = stem + '_top_en.png'
        detail = stem + '_en.png' if stem + '_en.png' in log else top
        banners.append({
            'id': str(9200000 + n), 'type': 'normal', 'name': name,
            'detail_id': str((9200000 + n) * 10 + 1), 'exe_type': 'primary',
            'schedule': {'disp_order': 2000 + n, 'banner_type': 0,
                         'window': {'from': '2026-01-01 00:00:00', 'to': '2030-12-31 23:59:59'}},
            'art': {'banner': top, 'detail_banner': detail,
                    'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_rare/anime',
                    'img_btn': 'gacha_btn_n'},
            'pool': {'tiers': tiers}, 'cost': cost, 'draws': draws,
            'tab': 'limited', 'season': 'season3', 'release': stem.split('_')[1][:4] + '-' + stem.split('_')[1][4:6],
            'provenance': 'named', 'source': 'translated-jp', 'pool_authored': True,
            'sources': [{'file': 'data/gacha_translated/' + f, 'sha256': log[f]['output_sha256'],
                         'translated_from': log[f]['source_file'], 'source_sha256': log[f]['source_sha256']}
                        for f in sorted({top, detail})],
        })
    banners.extend(wiki_banners(local_nv))
    from build_reward_summons import king_mog, update_arena
    banners.append(king_mog())
    update_arena()
    doc = {'_meta': {'what': 'Named banners from original Global client art, recovered Global wiki art and '
                             'recorded English translations of the JP-only specials.',
                     'generator': 'source/exvius/build_named_banners.py',
                     'units': 'game unit ids for the names printed on the art (F_TEXT_UNITS_NAME)',
                     'release': 'approximate month, from neighbouring dated ticket items; all Season 4'},
           'banners': banners}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print('wrote', len(banners), 'banners to', OUT)
    from build_catalogue_banners import rebuild
    rebuild()


if __name__ == '__main__':
    main()
