"""Use documented Global campaigns for the unidentified shipped summon slots.

Run after build_named_banners.py. Saved wiki revisions provide the campaign
identities and historical rarity rates. Anonymous slot assignments are local;
they are not claims about which campaign originally occupied those server IDs.
"""
import ast
from collections import defaultdict
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / 'source/server'
REFERENCES = ROOT / 'logs/reference/summons'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def normal(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).replace('_', ' ')
                   if unicodedata.category(c) != 'Cf').casefold().strip()


def day(value):
    return date(*map(int, value.split('-')))


def campaign_image(filename, release, units):
    # The 2022 calendar accidentally repeats Cecil's picture for this FFVI
    # campaign. The preserved original banner and official November 18 post
    # both show E.D. Edgar, E.F. Sabin and Gau instead.
    if release == '2022-11-17' and 'Embracer of Duty Edgar' in units:
        return 'Gacha-ED Edgar.png'
    return filename


def text_of(doc):
    if 'parse' in doc:
        return doc['parse']['wikitext']['*']
    return next(iter(doc['query']['pages'].values()))['revisions'][0]['slots']['main']['*']


def calendar_rows(pages):
    result = []
    for page in pages:
        text = page.get('parse', {}).get('wikitext', {}).get('*', '')
        for match in re.finditer(r'\[\[File:([^|\]]+)\|', text):
            end = text.find('[[File:', match.end())
            section = text[match.end():end if end >= 0 else len(text)]
            release = re.search(r"\*'''Release Date:'''\s*(\d{4}-\d{1,2}-\d{1,2})", section)
            units = re.search(r"\*'''(?:Units?|Time-limited units):'''([^\n]+)", section)
            if not release:
                continue
            until = re.search(r"\*'''Available Until:'''\s*(\d{4}-\d{1,2}-\d{1,2})", section)
            featured = re.findall(r'\[\[([^]|]+)(?:\|[^]]+)?\]\]', units[1]) if units else []
            released = day(release[1]).isoformat()
            result.append({'image': campaign_image(match[1], released, featured), 'release': released,
                'until': day(until[1]).isoformat() if until else None,
                'units': featured,
                'free': bool(re.search(r'\bFree\b|\bfree\b', section.split("*'''Release Date:")[0])),
                'once': 'one time only' in section,
                'daily': 'once per day' in section,
                'simulator': next(iter(re.findall(r'\[\[(Summon Simulator/[^]|]+)', section)), None),
                'source': page['url'], 'sha256': page['sha256']})
    unique = {}
    for row in result:
        unique.setdefault((normal(row['image']), row['release']), row)
    return list(unique.values())


def rate_tables(history):
    """Read the preserved tables, rather than reuse a single rate for every year."""
    tables = []
    for record in history:
        revision = next(iter(record['query']['pages'].values()))['revisions'][0]
        text = text_of(record)
        def read_table(section):
            rows = {}
            for line in section.split('|}', 1)[0].splitlines():
                match = re.search(
                    r'\| \{\{Rarity\|(3|4|5|NV)\}\}[^\n]*?\|\|\s*([\d.]+)%[^\n]*?\x27\x27\x27([\d.]+)%', line)
                if match:
                    rarity, featured, total = match.groups()
                    rows[7 if rarity == 'NV' else int(rarity)] = (
                        float(total) / 100, float(featured) / 100, '* N' in line)
            return rows
        sections = text.split('! Rarity !! Crystal')
        rows = read_table(sections[1])
        if not rows:
            raise ValueError('No saved rarity rates for ' + record['date'])
        tables.append({'until': day(record['date']), 'rows': rows,
            'guaranteed_rows': read_table(sections[2]),
            'url': 'https://exvius.fandom.com/wiki/Summon?oldid=' + str(revision['revid']),
            'sha256': record['sha256']})
    return tables


def simulator_pool(source, names, mst, forms, releases, release, variable):
    """Interpret the saved data arrays only. No wiki JavaScript is executed."""
    text = text_of(source)
    def array(name):
        match = re.search(r'var\s+' + re.escape(name) + r'\s*=\s*\[(.*?)\];', text, re.S)
        return match[1] if match else ''
    units = []
    for obj in re.findall(r'\{([^{}]+)\}', array('units')):
        fields = {}
        for key, literal in re.findall(
                r'(\w+)\s*:\s*(\x27(?:\\.|[^\x27\\])*\x27|"(?:\\.|[^"\\])*"|\d+|true|false)', obj):
            fields[key] = (literal == 'true' if literal in ('true', 'false') else ast.literal_eval(literal))
        if 'name' in fields:
            units.append(fields)
    weights = [(code, float(weight)) for code, weight in re.findall(
        r'\[\s*[\x27"]([^\x27"]+)[\x27"]\s*,\s*([\d.]+)\s*\]', array(variable))]
    if not weights or not units:
        raise ValueError('missing data arrays')
    totals = defaultdict(float)
    for code, weight in weights:
        if weight <= 0:
            continue
        bits = code.split('_')
        rarity, featured = int(bits[0]), bits[-1] == 'ft'
        legacy = len(bits) > 1 and bits[1] in ('common', 'rare')
        candidates = [u for u in units if bool(u.get('featured')) == featured]
        bases = [(None, 1.)]
        if legacy:
            flag = {3: 'three_stars', 4: 'four_stars', 5: 'five_stars'}[rarity]
            candidates = [u for u in candidates if u.get('type') == bits[1] and u.get(flag)]
            if rarity in (4, 5) and bits[1] == 'rare':
                definition = array('type_' + str(rarity) + ('_ft' if featured else ''))
                choices = [(int(base), float(w)) for base, w in re.findall(r"\['base_(\d+)'\s*,\s*([\d.]+)\]", definition)]
                if not choices or not sum(w for _, w in choices):
                    raise ValueError('missing awakened base weights: ' + code)
                bases = [(base, w / sum(v for _, v in choices)) for base, w in choices if w > 0]
        else:
            candidates = [u for u in candidates if int(u.get('base', 0)) == rarity]
        for base, fraction in bases:
            selected = [u for u in candidates if base is None or int(u['base']) == base]
            if not selected:
                raise ValueError('empty historical group: ' + code)
            for unit in selected:
                roots = [uid for uid in names.get(normal(unit['name']), ())
                         if int(mst[uid]['9fW0TePj']) == int(unit['base'])]
                if len(roots) > 1:
                    roots = [uid for uid in roots if releases.get(uid, date.max) <= release]
                if len(roots) != 1:
                    raise ValueError('unresolved unit name: ' + unit['name'])
                ids = forms.get((roots[0], rarity), [])
                if len(ids) != 1:
                    raise ValueError('unresolved awakened form: ' + unit['name'])
                totals[(ids[0], rarity)] += weight / 100 * fraction / len(selected)
    if abs(sum(totals.values()) - 1) > .005:
        raise ValueError('historical probabilities do not total 100%')
    return [{'unit_id': uid, 'rarity': rarity, 'rate': rate}
            for (uid, rarity), rate in sorted(totals.items())]


def egg_offer(banner, mst, names):
    items = {}
    for row in map(json.loads, (ROOT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson').read_text(encoding='utf-8').splitlines()):
        items[row['v'][0]] = int(row['key'].rsplit('_', 1)[-1])
    pool = []
    def item(name, rate):
        pool.append({'kind': 20, 'id': items[name], 'count': 1, 'rate': rate})
    def unit(uid, rate, **extra):
        pool.append({'kind': 10, 'id': int(uid), 'count': 1, 'rate': rate, **extra})
    for name, rate in [('Red Egg', .40), ('Blue Egg', .40), ('Rainbow Egg', .0625)]:
        item(name, rate)
    for color in ['Red', 'Blue', 'Yellow', 'Orange', 'Violet']:
        item(color + ' Megacite', .07 / 5)
    for uid, rate in [('900010301', .03), ('900020301', .0175), ('900010401', .002),
                      ('900020401', .0025), ('905000103', .001)]:
        unit(uid, rate)
    for owner, label, rate in [('Fryevia', "Fryevia's Needle", .0045),
                               ('Xon', 'Patches', .0035), ('Aiden', 'Vestment of Mind', .003)]:
        candidates = names[normal(owner)]
        if len(candidates) != 1:
            raise ValueError('Egg Summon trust target is ambiguous: ' + owner)
        target = mst[next(iter(candidates))]['9mu4boy7']
        unit('904000103', rate, affinity_points=['50', ''], affinity_info=[target, ''],
             display_name='Trust Moogle (' + label + ', 5%)')
    crystals = [name for name in items if name.endswith(' Heavicryst') and not name.startswith('Random ')]
    for name in crystals:
        item(name, .0035 / len(crystals))
    banner.update(tab='free', cost={'kind': 'item', 'item_id': items['Metal Egg'], 'amount': 100},
                  draws=1, reward_pool=pool)
    banner.pop('pool', None)
    banner.pop('secondary_offer', None)
    banner['rate_source'] = {'url': 'https://exvius.fandom.com/wiki/The_Egg_Seekers#Egg_Summon',
        'scope': 'Week-two survey estimates from 56,082 pulls. Magicite and crystal groups split equally.',
        'authored_details': '100-egg cost and 5% donor strength; original price and donor instance rows were not preserved.'}


def xiv_offer(banner, mst, names, titan=False):
    pages = {r['title']: r for r in load(REFERENCES / 'special-summons-wiki.json')}
    event = 'March on Titan' if titan else 'March on Ifrit'
    items = {row['v'][0]: int(row['key'].rsplit('_', 1)[-1]) for row in map(json.loads,
        (ROOT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson').read_text(encoding='utf-8').splitlines())}
    def hero(name):
        candidates = names[normal(name)]
        # This 2017 event predates Neo Vision remakes with the same name.
        return min(candidates, key=lambda uid: (int(mst[uid]['9fW0TePj']), uid))
    if titan:
        unit_weights = [("Y'shtola", .006), ('Yda', .017), ('Papalymo', .017),
            ('Minfilia', .015), ('Thancred', .06), ('King Gil Snapper', .0225),
            ('Metal Gigantuar', .03), ('Gil Snapper Family', .0325), ('King Metal Minituar', .04)]
        material_rows = []
        for suffix in ['/Drop Awakening', '/Drop Crafting']:
            for line in text_of(pages[event + suffix]).splitlines():
                match = re.search(r'\{\{Item\|([^}]+)\}\}.*\|\|\s*([\d.]+)%', line)
                if match:
                    material_rows.append((match[1], float(match[2])))
        pool = [{'kind': 10, 'id': int(hero(name)), 'count': 1, 'rate': rate}
                for name, rate in unit_weights]
        total = sum(weight for _, weight in material_rows)
        pool += [{'kind': 20, 'id': items[name], 'count': 1, 'rate': .76 * weight / total}
                 for name, weight in material_rows]
        provenance = {'url': pages[event + '/Drop Rates']['url'],
            'sha256': pages[event + '/Drop Rates']['sha256'],
            'scope': '45,067-pull survey estimates: units and enhancers 24%, materials 76%. '
                     'Material weights use the published relative estimates within the 76% category.'}
    else:
        section = text_of(pages[event]).split('== Raid Summon ==', 1)[1].split('== Battle Info ==', 1)[0]
        materials = sorted(set(re.findall(r'\{\{Item\|([^}]+)\}\}', section)))
        heroes = ["Y'shtola", 'Minfilia', 'Thancred']
        pool = [{'kind': 20, 'id': items[name], 'count': 1, 'rate': .8 / len(materials)} for name in materials]
        pool += [{'kind': 10, 'id': int(hero(name)), 'count': 1, 'rate': .19 / len(heroes)} for name in heroes]
        for name in heroes:
            target = mst[hero(name)]['9mu4boy7']
            pool.append({'kind': 10, 'id': 904000103, 'count': 1, 'rate': .01 / len(heroes),
                'affinity_points': ['50', ''], 'affinity_info': [target, ''],
                'display_name': 'Trust Moogle (' + name + ', 5%)'})
        provenance = {'url': pages[event]['url'], 'sha256': pages[event]['sha256'],
            'scope': 'Original event heroes, materials and specific 5% trust donors.',
            'authored_details': 'Unpreserved item weights: materials 80%, heroes 19%, trust donors 1%, equally divided within each group.'}
    banner.update(reward_pool=pool, single_only=True, draws=1)
    banner.pop('pool', None)
    banner.pop('secondary_offer', None)
    banner['rate_source'] = provenance


def type_offer(banner, filename, roles):
    groups = {'Gacha-Type-Attack.png': {'Physical Attacker', 'Hybrid Attacker'},
              'Gacha-Type-Magic Tank.png': {'Magic Attacker', 'Physical Tank', 'Magic Tank'},
              'Gacha-Type-Support Healer.png': {'Support', 'Healer', 'Debuffer'}}
    wanted = groups[filename]
    base = copy.deepcopy(banner['pool'])
    tier = next(t for t in base['tiers'] if t['rarity'] == 5)
    tier['units'] = [uid for uid in tier['units'] if roles.get(uid, set()) & wanted]
    tier.pop('featured', None)
    tier.pop('featured_share', None)
    if not tier['units']:
        raise ValueError('Missing documented type-summon units: ' + filename)
    doubled = copy.deepcopy(base)
    for entry in doubled['tiers']:
        if entry['rarity'] == 5:
            entry['rate'] *= 2
        elif entry['rarity'] == 3:
            entry['rate'] -= tier['rate']
    banner.update(type='step', tab='limited', gacha_layout=2, lap_limit=1, pool=base,
        steps=[{'cost': {'kind': 'lapis', 'amount': 3000}, 'draws': 11, 'guarantee': {'rarity': 4, 'count': 1}},
               {'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'pool': doubled,
                'guarantee': {'rarity': 4, 'count': 1}, 'bonus_rewards': [
                    {'kind': 10, 'id': 904000105, 'count': 1, 'affinity_points': ['100', '']}]},
               {'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11,
                'guarantee': {'rarity': 5, 'count': 1, 'pool': {'tiers': [dict(tier, rate=1)]}}}])
    banner.pop('cost', None)
    banner.pop('draws', None)
    banner.pop('secondary_offer', None)
    banner['rate_source'] = {'url': 'https://www.reddit.com/r/FFBraveExvius/comments/8u9x7d/global_news_maintenance_just_cause_challenge/',
        'scope': 'Original three 10+1 steps, first-step cost, doubled step-two rainbow rate, 10% trust bonus and final five-star guarantee.',
        'authored_details': 'Unpreserved final two prices use 5000 Lapis each; role eligibility is reconstructed from documented Global units released by June 2018.'}


def rebuild():
    mst = {str(r['3HriTp6B']): r for r in
           map(json.loads, (ROOT / 'data/mst_decoded/F_UNIT_MST.ndjson').read_text(encoding='utf-8').splitlines())}
    roots = {uid for uid, row in mst.items() if str(row.get('woghJa61')) == uid}
    forms = defaultdict(list)
    for uid, row in mst.items():
        forms[(str(row.get('woghJa61')), int(row.get('9fW0TePj', 0)))].append(uid)
    names, legacy_names = {}, {}
    for row in map(json.loads, (ROOT / 'data/text_decoded/F_TEXT_UNITS_NAME.ndjson').read_text(encoding='utf-8').splitlines()):
        uid = row['key'].rsplit('_', 1)[-1]
        if uid in roots:
            names.setdefault(normal(row['v'][0]), set()).add(uid)
            # Later Global names disambiguate legacy units with their series.
            # Match the old name only when base rarity still resolves uniquely.
            legacy_name = re.sub(r'\s+\([^)]*\)$', '', row['v'][0])
            legacy_names.setdefault(normal(legacy_name), set()).add(uid)
    for name, ids in legacy_names.items():
        names.setdefault(name, ids)
    # The 2016 FFV campaign and pre-WOTV simulators use the old bare name.
    names[normal('Gilgamesh')] = names[normal('Gilgamesh (FFV)')]
    pages = load(REFERENCES / 'summon-calendar-wiki.json')
    campaigns = calendar_rows(pages)
    tables = rate_tables(load(REFERENCES / 'summon-rate-history-wiki.json'))
    simulators = {r['title']: r for r in load(REFERENCES / 'summon-simulators-wiki.json')}
    unit_list = text_of(load(REFERENCES / 'unit-list-wiki.json'))
    retail, limited, roles = set(), set(), {}
    for row in unit_list.split('|-'):
        columns = row.split('||')
        icon = re.search(r'unit_icon_(\d+)\.png', row)
        if not icon or len(columns) < 9:
            continue
        uid = str(mst.get(icon[1], {}).get('woghJa61', icon[1]))
        if uid in roots:
            roles.setdefault(uid, set()).update(re.findall(r'Icon-([^.|]+)\.png', columns[3]))
            for link in re.findall(r'\[\[([^]]+)\]\]', columns[2]):
                for name in link.split('|'):
                    names.setdefault(normal(name), {uid})
        if 'Rare Summon' not in columns[7]:
            continue
        if uid in roots:
            retail.add(uid)
            if 'Yes' in columns[8]:
                limited.add(uid)
    releases = {}
    launch = text_of(load(REFERENCES / 'unit-list-launch-wiki.json'))
    for name in re.findall(r'\{\{Sprite\|([^}|]+)', launch):
        for uid in names.get(normal(name), ()):
            if uid in retail and uid not in limited:
                releases[uid] = date(2016, 6, 30)
    for row in campaigns:
        for name in row['units']:
            candidates = names.get(normal(name), ())
            if len(candidates) == 1:
                uid = next(iter(candidates))
                releases[uid] = min(releases.get(uid, date.max), day(row['release']))
    community_path = SERVER / 'gacha_community.json'
    community = load(community_path)
    for banner in community['banners']:
        released = day(banner['community']['release'])
        for uid in banner['community'].get('unit_ids', []):
            releases[uid] = min(releases.get(uid, date.max), released)
    images = load(ROOT / 'data/gacha_community/art_sources.json')['images']
    image_sources = {normal(r['name']): r for r in images}
    for image in load(ROOT / 'data/gacha_wiki_extra/sources.json')['images']:
        image_sources[normal(image['file'])] = image
    count, recovered = 0, 0
    for banner in community['banners']:
        info = banner['community']
        release = day(info['release'])
        filename = campaign_image(banner['art']['banner'], release.isoformat(), info.get('units', []))
        if filename != banner['art']['banner']:
            banner['art'].update(banner=filename, detail_banner=filename)
        matches = [row for row in campaigns if row['release'] == release.isoformat()
                   and normal(row['image']) == normal(filename)]
        if len(matches) != 1:
            raise ValueError('Campaign identity is not unique for ' + banner['id'] + ': ' + filename)
        campaign = matches[0]
        featured = set(info.get('unit_ids', []))
        for name in campaign['units']:
            candidates = names.get(normal(name), ())
            if len(candidates) == 1:
                featured.add(next(iter(candidates)))
        # The historical table before each rate change is used for that era.
        table = next((row for row in tables if release <= row['until']), tables[-1])
        tiers = []
        for rarity, (rate, rate_up, per_unit) in sorted(table['rows'].items(), reverse=True):
            eligible = sorted(uid for uid, released in releases.items() if released <= release
                              and uid in retail and uid not in limited
                              and int(mst[uid]['9fW0TePj']) == rarity)
            current = sorted(uid for uid in featured if uid in roots and int(mst[uid]['9fW0TePj']) == rarity)
            if not eligible and not current:
                # The 2016 table includes rainbows before the first base-five unit.
                # Original awakened-unit probabilities were not preserved.
                continue
            tier = {'rarity': rarity, 'rate': rate, 'units': sorted(set(eligible + current))}
            if current:
                tier.update(featured=current, featured_share=min(1, rate_up * (len(current) if per_unit else 1) / rate))
            tiers.append(tier)
        banner['pool'] = {'tiers': tiers}
        guaranteed_tiers = []
        for tier in tiers:
            rarity = tier['rarity']
            if rarity not in table['guaranteed_rows']:
                continue
            rate, rate_up, per_unit = table['guaranteed_rows'][rarity]
            guaranteed = dict(tier, rate=rate)
            if tier.get('featured'):
                guaranteed['featured_share'] = min(1, rate_up * (len(tier['featured']) if per_unit else 1) / rate)
            guaranteed_tiers.append(guaranteed)
        if campaign['units']:
            banner['name'] = ', '.join(campaign['units']) + ' Featured Summon'
        banner['name_override'] = True
        banner['tab'] = 'limited'
        banner['release'] = release.isoformat()
        banner['campaign_identity'] = 'global:' + release.isoformat() + ':' + normal(filename)
        info.update(release=release.isoformat(), until=campaign['until'], units=campaign['units'], unit_ids=sorted(featured))
        banner['rate_source'] = {'url': table['url'], 'sha256': table['sha256'],
            'scope': 'Era rarity totals and featured rates, including the separate guaranteed-slot table. Incomplete eligibility uses documented Global releases.',
            'eligibility_authored': True,
            'before_first_base_five': release < date(2016, 9, 23)}
        simulator = simulators.get('Widget:' + str(campaign['simulator']))
        recovered_guarantee = None
        if simulator:
            try:
                pool = simulator_pool(simulator, names, mst, forms, releases, release, 'banner_rate')
                banner['pool'] = pool
                banner['rate_source'] = {'url': simulator['url'], 'sha256': simulator['sha256'],
                    'scope': 'Full unit pools and weights preserved by the contemporary community simulator.',
                    'official_server_table': False, 'eligibility_authored': False}
                recovered += 1
            except ValueError as exc:
                banner['rate_source']['simulator_unresolved'] = str(exc)
            if 'var guarantee_rate' in text_of(simulator):
                try:
                    recovered_guarantee = simulator_pool(simulator, names, mst, forms, releases, release, 'guarantee_rate')
                except ValueError as exc:
                    banner['rate_source']['guaranteed_simulator_unresolved'] = str(exc)
        banner['sources'] = [{'url': campaign['source'], 'sha256': campaign['sha256']}]
        if normal(filename) in image_sources:
            source = image_sources[normal(filename)]
            banner['sources'].append({'url': source['source'], 'sha256': source['sha256']})
        if campaign['free'] and not campaign['units']:
            banner['cost'] = {'kind': 'free'}
            banner['single_only'] = True
            banner.pop('secondary_offer', None)
            if campaign['once']:
                banner['purchase_limit'] = 1
            if campaign['daily']:
                banner['daily_limit'] = 1
        elif banner.get('type') == 'normal':
            banner['secondary_offer'] = {'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11,
                'exe_count': 1, 'guarantee': {'rarity': 4, 'count': 1,
                    'pool': recovered_guarantee if recovered_guarantee else {'tiers': guaranteed_tiers}}}
        if filename == 'Gacha-Celebrating 20 Million Downloads.png':
            banner['draws'] = 11
            banner['guarantee'] = {'rarity': 4, 'count': 1, 'pool': recovered_guarantee}
        elif filename == 'Gacha-1st Anniversary-Guaranteed.png':
            banner.update(cost={'kind': 'lapis', 'amount': 5000}, draws=11,
                          purchase_limit=1, single_only=True)
            banner['guarantee'] = {'rarity': 5, 'count': 1, 'pool': recovered_guarantee}
            banner.pop('secondary_offer', None)
        elif filename in ('Gacha-Final Fantasy XIV.png', 'Gacha-Final Fantasy XIV-2.png'):
            coin = 106301000 if filename == 'Gacha-Final Fantasy XIV.png' else 106303000
            banner.update(tab='free', cost={'kind': 'item', 'item_id': coin, 'amount': 100, 'is_coin': True})
            banner.pop('secondary_offer', None)
            xiv_offer(banner, mst, names, titan=filename.endswith('-2.png'))
        elif filename == 'Gacha-Kelsus.png':
            banner.update(tab='free', cost={'kind': 'item', 'item_id': 1209000826, 'amount': 300},
                          draws=1, purchase_limit=1, single_only=True)
            banner['pool'] = [{'unit_id': '100009405', 'rarity': 5, 'rate': 1}]
            banner['guarantee'] = {'unit_id': '100009405', 'count': 1}
            banner.pop('secondary_offer', None)
            banner['rate_source'] = {'url': 'https://exvius.fandom.com/wiki/Summon/2017',
                'scope': 'Fixed Kelsus reward. This offer has no random unit pool.', 'eligibility_authored': False}
            banner['sources'].append({'url': 'https://gamefaqs.gamespot.com/boards/182206-final-fantasy-brave-exvius/75526130',
                'scope': 'Contemporary posts describe 300 shards per summon and the one-per-person banner caption.'})
        elif filename == 'Gacha-Egg Summon.png':
            egg_offer(banner, mst, names)
        elif filename in ('Gacha-Type-Attack.png', 'Gacha-Type-Magic Tank.png', 'Gacha-Type-Support Healer.png'):
            type_offer(banner, filename, roles)
        count += 1
    community['_meta']['rate_source'] = 'logs/reference/summons/summon-rate-history-wiki.json'
    community['_meta']['generator'] = 'source/exvius/build_catalogue_banners.py'
    community['_meta']['what'] = ('Documented Global calendar campaigns, with contemporary simulator pools '
        'where preserved and era rate tables otherwise. Per-banner sources distinguish both from official server data.')
    # Extra English images are campaigns too. Do not leave their pools on the
    # generic modern defaults merely because their artwork came from another folder.
    named_path = SERVER / 'gacha_named.json'
    named = load(named_path)
    named_count = 0
    for banner in named['banners']:
        if (banner.get('source') != 'global-wiki' or not banner.get('pool_authored')
                or not isinstance(banner.get('pool'), dict) or not banner['pool'].get('tiers')):
            continue
        filename = banner['art']['banner']
        release = day(banner['release'])
        matches = [row for row in campaigns if normal(row['image']) == normal(filename)]
        campaign = min(matches, key=lambda row: abs((day(row['release']) - release).days)) if matches else None
        if campaign:
            release = day(campaign['release'])
        featured = {str(uid) for tier in banner['pool']['tiers'] for uid in tier.get('featured', [])}
        if campaign:
            featured = {uid for name in campaign['units'] for uid in names.get(normal(name), ())}
        table = next((row for row in tables if release <= row['until']), tables[-1])
        tiers, guaranteed = [], []
        for rarity, (rate, rate_up, per_unit) in sorted(table['rows'].items(), reverse=True):
            eligible = {uid for uid, released in releases.items() if released <= release
                        and uid in retail and uid not in limited and int(mst[uid]['9fW0TePj']) == rarity}
            current = sorted(uid for uid in featured if uid in roots and int(mst[uid]['9fW0TePj']) == rarity)
            if not eligible and not current:
                continue
            tier = {'rarity': rarity, 'rate': rate, 'units': sorted(eligible | set(current))}
            if current:
                tier.update(featured=current, featured_share=min(1, rate_up * (len(current) if per_unit else 1) / rate))
            tiers.append(tier)
            if rarity in table['guaranteed_rows']:
                total, boosted, individual = table['guaranteed_rows'][rarity]
                extra = dict(tier, rate=total)
                if current:
                    extra['featured_share'] = min(1, boosted * (len(current) if individual else 1) / total)
                guaranteed.append(extra)
        if abs(sum(tier['rate'] for tier in tiers) - 1) > .005:
            raise ValueError('Incomplete historical rarity tiers: ' + filename)
        banner['pool'] = {'tiers': tiers}
        banner['rate_source'] = {'url': table['url'], 'sha256': table['sha256'],
            'scope': 'Historical rarity and featured rates; eligibility reconstructed from documented Global releases.',
            'eligibility_authored': True}
        secondary = banner.get('secondary_offer')
        if secondary and secondary.get('guarantee'):
            minimum = int(secondary['guarantee'].get('rarity', 4))
            secondary['guarantee']['pool'] = {'tiers': [tier for tier in guaranteed if tier['rarity'] >= minimum]}
        if campaign:
            banner.update(release=release.isoformat(), release_evidence=campaign['source'],
                          campaign_identity='global:' + release.isoformat() + ':' + normal(filename))
            banner['sources'].append({'url': campaign['source'], 'sha256': campaign['sha256']})
            simulator = simulators.get('Widget:' + str(campaign['simulator']))
            if simulator:
                try:
                    banner['pool'] = simulator_pool(simulator, names, mst, forms, releases, release, 'banner_rate')
                    banner['rate_source'] = {'url': simulator['url'], 'sha256': simulator['sha256'],
                        'scope': 'Full unit pools and weights preserved by the contemporary community simulator.',
                        'official_server_table': False, 'eligibility_authored': False}
                    if secondary and 'var guarantee_rate' in text_of(simulator):
                        secondary['guarantee']['pool'] = simulator_pool(
                            simulator, names, mst, forms, releases, release, 'guarantee_rate')
                except ValueError as exc:
                    banner['rate_source']['simulator_unresolved'] = str(exc)
        banner['rate_notice'] = 'Rates and guaranteed slots are listed below.'
        named_count += 1
    save(named_path, named)
    catalogue_path = SERVER / 'gacha_catalogue.json'
    catalogue = load(catalogue_path)
    authored_path = SERVER / 'gacha_authored.json'
    authored_doc = load(authored_path)
    authored = {row['id']: row for row in authored_doc['banners']}
    available = sorted(community['banners'], key=lambda b: (day(b['community']['release']), int(b['id'])))
    # Keep prior assignments stable when regenerating or adding newer campaigns.
    previous = {b['id']: b.get('catalogue_replacement', {}).get('campaign_id') for b in catalogue['banners']}
    used = {cid for cid in previous.values() if cid}
    unused = iter(b for b in available if b['id'] not in used)
    by_id = {b['id']: b for b in available}
    # Retire the old isolated button-development fixture's generic modern
    # pool. Keep its requested ID and ticket button, using Charlotte's actual
    # July 2019 campaign data and one shared archive listing.
    if '9100203' in authored:
        reference = copy.deepcopy(by_id['9100203'])
        reference.update(id='9100203', detail_id='91002031', ticket_group_id=10010,
                         state_id='9100203', alias_ids=[], name_override=True)
        authored['9100203'].clear()
        authored['9100203'].update(reference)
        save(authored_path, authored_doc)
    replacements = []
    for old in catalogue['banners']:
        bid = old['id']
        if bid in authored:
            replacements.append(copy.deepcopy(authored[bid]))
            continue
        selected = by_id[previous[bid]] if previous[bid] else next(unused)
        replacement = copy.deepcopy(authored.get(selected['id'], selected))
        replacement['id'] = bid
        replacement['detail_id'] = str(int(bid) * 10 + 1)
        replacement['catalogue_replacement'] = {'campaign_id': selected['id'],
            'assignment': 'User-authorized replacement for an unidentifiable reusable server slot.'}
        replacement['state_id'] = selected['id']
        replacement['alias_ids'] = sorted(set(replacement.get('alias_ids', []) + [selected['id']]))
        replacement['source'] = 'global-campaign-replacement'
        replacements.append(replacement)
    catalogue['banners'] = replacements
    catalogue['_meta'].update(what='Documented Global campaigns assigned to anonymous shipped IDs.',
        generator='source/exvius/build_catalogue_banners.py',
        label='Assignment is local; campaign names, dates, featured units and art have recorded sources.')
    save(community_path, community)
    save(catalogue_path, catalogue)
    print('Updated', count, 'documented campaigns,', named_count, 'extra English campaigns and', len(replacements), 'retained catalogue IDs;', recovered, 'complete historical simulator pools')


if __name__ == '__main__':
    rebuild()
