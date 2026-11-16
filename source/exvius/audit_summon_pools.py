"""Audit every packaged banner and offer against retained Global unit evidence."""
from collections import Counter, defaultdict
from functools import lru_cache
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import zipfile

from build_catalogue_banners import calendar_rows, load, normal, text_of

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ('catalogue', 'community', 'named', 'authored', 'raid', 'standard')


@lru_cache(maxsize=1)
def approved_unit_baseline():
    # Use the installed Global/Kira cohort. The source data tree also contains
    # a separate pending JP import, which must not enter this APK's pools.
    with zipfile.ZipFile(ROOT / 'source/build/distribution/assets/exvius-kira-r7.zip') as archive:
        raw = archive.read('static/mst_decoded/F_UNIT_MST.ndjson')
        if hashlib.sha256(raw).hexdigest() != '2ae3532852fb3ba85f5efeaa4cea97ef45ecf594b3933f2340e8a509a9318051':
            raise ValueError('Approved unit baseline changed')
        mst = {row['3HriTp6B']: row for row in map(json.loads, raw.splitlines())}
        names = list(map(json.loads, archive.read('static/text_decoded/F_TEXT_UNITS_NAME.ndjson').splitlines()))
    contract = json.loads((ROOT / 'source/server/content/unit_name_repair.json').read_text('utf-8'))
    names += [{'key': key, 'v': [label, label]} for key, label in contract['labels'].items()]
    return mst, names


def unit_evidence(documents):
    mst, name_rows = approved_unit_baseline()
    shift_owners = {uid: str(mst.get(str(row['JPW8Vs40']), {}).get('woghJa61', row['JPW8Vs40']))
                    for uid, row in mst.items() if str(row.get('I3SKJ4q0')) == '1'
                    and row.get('JPW8Vs40') not in (None, '', '0', uid)}
    roots = {uid for uid, row in mst.items() if row.get('woghJa61') == uid and uid not in shift_owners}
    names, retail, limited, friend, labels = defaultdict(set), set(), set(), set(), {}
    seasonal = set()
    named_units = set()
    for row in name_rows:
        uid = row['key'].rsplit('_', 1)[-1]
        named_units.add(uid)
        if uid in roots:
            labels[uid] = row['v'][0]
            names[normal(row['v'][0])].add(uid)
    references = ROOT / 'logs/reference/summons'
    unit_list = text_of(load(references / 'unit-list-wiki.json'))
    for row in unit_list.split('|-'):
        columns = row.split('||')
        icon = re.search(r'unit_icon_(\d+)\.png', row)
        if not icon or len(columns) < 9:
            continue
        uid = str(mst.get(icon[1], {}).get('woghJa61', icon[1]))
        uid = shift_owners.get(uid, uid)
        if uid not in roots:
            continue
        for link in re.findall(r'\[\[([^]]+)\]\]', columns[2]):
            for name in link.split('|'):
                names[normal(name)].add(uid)
        if 'Rare Summon' in columns[7]:
            retail.add(uid)
            if columns[8].strip() in ('Yes', 'Collaboration', 'Seasonal'):
                limited.add(uid)
            if columns[8].strip() == 'Seasonal':
                seasonal.add(uid)
        if 'Friend' in columns[7] or 'Standard Summon' in columns[7]:
            friend.add(uid)
    releases = {}
    launch = text_of(load(references / 'unit-list-launch-wiki.json'))
    for name in re.findall(r'\{\{Sprite\|([^}|]+)', launch):
        for uid in names.get(normal(name), ()):
            if uid in retail and uid not in limited:
                releases[uid] = '2016-06-30'
    for row in calendar_rows(load(references / 'summon-calendar-wiki.json')):
        for name in row['units']:
            candidates = names.get(normal(name), ())
            if len(candidates) == 1:
                uid = next(iter(candidates))
                releases[uid] = min(releases.get(uid, '9999-99-99'), row['release'])
    for document in documents.values():
        for banner in document['banners']:
            info = banner.get('community') or {}
            released = info.get('release') or banner.get('release')
            if not isinstance(released, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', released):
                continue
            for uid in info.get('unit_ids', []):
                uid = str(uid)
                releases[uid] = min(releases.get(uid, '9999-99-99'), released)
            pool = banner.get('pool')
            for tier in pool.get('tiers', []) if isinstance(pool, dict) else []:
                for uid in tier.get('featured', []):
                    uid = str(uid)
                    releases[uid] = min(releases.get(uid, '9999-99-99'), released)
    return dict(mst=mst, roots=roots, labels=labels, retail=retail,
                limited=limited, seasonal=seasonal, friend=friend, releases=releases, shift_owners=shift_owners,
                named_units=named_units)


def allowed_limited(banner, evidence):
    allowed = set(map(str, (banner.get('community') or {}).get('unit_ids', [])))
    # Only this approved friend-point expansion can include the mailbox gift roster.
    expansion = banner.get('mailbox_unit_pool')
    if str(banner['id']) == '1' and banner.get('name') == 'Standard Summon+' and expansion:
        gifts = json.loads((ROOT / 'source/server/content/free_event_units.json').read_text('utf-8'))['units']
        expected = {str(row['unit']) for row in gifts}
        if expansion.get('source') != 'content/free_event_units.json' or set(expansion.get('units', [])) != expected:
            raise ValueError('Standard Summon+ mailbox roster differs from the verified gifts')
        allowed.update(str(evidence['mst'][uid]['woghJa61']) for uid in expected)
    if banner.get('source') == 'translated-jp':
        from jp_summon_pools import FIRST, SECOND, historical_units
        filename = SECOND if str(banner['id']) in ('9200102', '9200105', '9200109', '9200110', '9200111') else FIRST
        # JP regular/Festival membership supersedes a counterpart's Global
        # seasonal classification, for example Sakura & Ayaka.
        allowed.update(row['id'] for row in historical_units(filename, evidence)[0])
    for _, offer in pool_definitions(banner):
        pool = offer.get('pool')
        for tier in pool.get('tiers', []) if isinstance(pool, dict) else []:
            allowed.update(map(str, tier.get('featured', [])))
    source = banner.get('rate_source') or {}
    if source.get('eligibility_authored') is False and 'Widget:Summon_Simulator/' in source.get('url', ''):
        pool = banner.get('pool')
        if isinstance(pool, list):
            # Contemporary Christmas/Lunar New Year simulators also include
            # that celebration's other limited units, beyond the headline art.
            allowed.update(str(evidence['mst'].get(str(r['unit_id']), {}).get('woghJa61', r['unit_id'])) for r in pool)
    if re.search(r'Seasonal|Holiday|Halloween|Christmas', banner['name'], re.I):
        allowed.update(evidence['seasonal'])
    return allowed


def repair_document(document, evidence):
    """Constrain each existing offer without replacing its rarity/featured rates."""
    changes = []
    for banner in document['banners']:
        # These scoped offers carry explicit reviewed or labelled reconstructed pools.
        if banner.get('source') in ('historical-jp-summon', 'prepared-global-20261114', 'prepared-roster-20261114'):
            continue
        from jp_summon_pools import IDS as JP_IDS, repair_banner
        if str(banner['id']) in JP_IDS and banner.get('source') == 'translated-jp':
            if repair_banner(banner, evidence):
                changes.append({'id': str(banner['id']), 'name': banner['name'], 'scopes': ['JP historical roster']})
            continue
        if str(banner['id']) == '9200008' and banner.get('release') == '2024-06':
            # Same Hero Resurrected Taivas campaign as 9200004. The old
            # approximate browsing month predates the unit's Global launch.
            banner['release'] = '2024-08-01'
            banner['release_evidence'] = 'Hero Resurrected Taivas Global campaign, 20240730gbehaRainTaivasFeaturedSummon0829Update.html'
        allowed = allowed_limited(banner, evidence)
        release = (banner.get('community') or {}).get('release') or banner.get('release') or ''
        if banner.get('source') == 'translated-jp':
            # Global launch dates cannot establish availability in Japan.
            release = ''
        if len(release) == 7:
            release += '-99'
        changed = []
        def eligible(uid, explicit=False, friend=False):
            uid = str(uid)
            if uid not in evidence['named_units']:
                return False
            if uid in evidence['shift_owners']:
                return False
            root = str(evidence['mst'].get(uid, {}).get('woghJa61', uid))
            if explicit and root.startswith('9'):
                return True  # Explicit enhancer/material rewards are not retail-unit backgrounds.
            if root in evidence['limited'] and root not in allowed:
                return False
            if root not in evidence['retail'] and root not in allowed and not (friend and (root in evidence['friend'] or root.startswith('9'))):
                return False
            known = evidence['releases'].get(root)
            if release and known and known > release:
                return False
            if release and not known and not explicit and root not in allowed:
                return False
            return True
        def repair(pool, scope, friend=False):
            if not pool:
                return
            before = copy.deepcopy(pool)
            if isinstance(pool, dict):
                for tier in pool.get('tiers', []):
                    if float(tier.get('rate', 0)) <= 0:
                        continue
                    if tier.get('featured'):
                        tier['featured'] = [str(uid) for uid in tier['featured'] if eligible(uid, True, friend)]
                    explicit = bool(tier.get('units'))
                    candidates = tier.get('units') or sorted(uid for uid in evidence['roots']
                        if str(evidence['mst'][uid].get('9fW0TePj')) == str(tier.get('rarity')))
                    units = [str(uid) for uid in candidates if eligible(uid, explicit, friend)]
                    units += [str(uid) for uid in tier.get('featured', []) if str(uid) not in units]
                    if not units:
                        raise ValueError('No evidenced eligible units: ' + str(banner['id']) + ' ' + scope + ' rarity ' + str(tier['rarity']))
                    tier['units'] = units
            elif isinstance(pool, list):
                totals, kept = defaultdict(float), defaultdict(float)
                for row in pool:
                    totals[str(row.get('rarity'))] += float(row['rate'])
                pool[:] = [row for row in pool if eligible(row['unit_id'], True, friend)]
                for row in pool:
                    kept[str(row.get('rarity'))] += float(row['rate'])
                for rarity, total in totals.items():
                    if total > 0 and not kept[rarity]:
                        raise ValueError('Eligibility would erase a rarity tier: ' + str(banner['id']) + ' ' + scope)
                for row in pool:
                    rarity = str(row.get('rarity'))
                    row['rate'] *= totals[rarity] / kept[rarity]
            if pool != before:
                changed.append(scope)
        cost = banner.get('cost') or {}
        friend = isinstance(cost, dict) and cost.get('kind') == 'friend_point'
        repair(banner.get('pool'), 'base', friend)
        offers = [('base', banner)] + [('step:' + str(i + 1), step) for i, step in enumerate(banner.get('steps', []))]
        if banner.get('secondary_offer'):
            offers.append(('secondary', banner['secondary_offer']))
        for label, offer in offers:
            if label != 'base':
                repair(offer.get('pool'), label, friend)
            repair((offer.get('guarantee') or {}).get('pool'), label + ':guarantee', friend)
            for i, slot in enumerate(offer.get('guarantee_slots', [])):
                repair(slot.get('pool'), label + ':guarantee_slot:' + str(i + 1), friend)
        if changed:
            banner['eligibility_source'] = {
                'source': 'logs/reference/summons/unit-list-wiki.json',
                'policy': 'Global acquisition eligibility; Collaboration, Seasonal and Yes are limited. Only this banner evidenced limited units are permitted. Known future releases are excluded.',
                'original_server_pool_recovered': False,
            }
            changes.append({'id': str(banner['id']), 'name': banner['name'], 'scopes': changed})
    return changes


def pool_definitions(banner):
    """Visit base, step, secondary and guaranteed-slot pools individually."""
    yield 'base', banner
    for i, step in enumerate(banner.get('steps', [])):
        yield 'step:' + str(i + 1), dict(banner, **step)
    if banner.get('secondary_offer'):
        yield 'secondary', dict(banner, **banner['secondary_offer'])


def pool_units(pool, evidence):
    if isinstance(pool, list):
        return {str(row['unit_id']) for row in pool}, []
    ids, unbounded = set(), []
    for tier in (pool or {}).get('tiers', []):
        if float(tier.get('rate', 0)) <= 0:
            continue
        if not tier.get('units'):
            unbounded.append(tier.get('rarity'))
            ids.update(uid for uid in evidence['roots']
                       if str(evidence['mst'][uid].get('9fW0TePj')) == str(tier.get('rarity')))
        else:
            ids.update(map(str, tier['units']))
        ids.update(map(str, tier.get('featured', [])))
    return ids, unbounded


def audit(documents):
    evidence = unit_evidence(documents)
    report, summary = [], Counter()
    for family, document in documents.items():
        for banner in document['banners']:
            row = {'family': family, 'id': str(banner['id']), 'name': banner['name'], 'issues': []}
            allowed = allowed_limited(banner, evidence)
            row['served'] = banner.get('serve', True)
            release = (banner.get('community') or {}).get('release') or banner.get('release') or ''
            row['regional_date_evidence_required'] = (banner.get('source') == 'translated-jp' and
                not (banner.get('eligibility_source') or {}).get('regional_roster_reconstructed'))
            if banner.get('source') == 'translated-jp':
                from jp_summon_pools import IDS as JP_IDS, repair_banner
                if str(banner['id']) in JP_IDS:
                    expected = copy.deepcopy(banner)
                    repair_banner(expected, evidence)
                    if expected.get('pool') != banner.get('pool') or expected.get('guarantee') != banner.get('guarantee'):
                        row['issues'].append({'scope': 'base', 'kind': 'incorrect_JP_banner_roster'})
                # Global launch dates cannot validate an older JP roster.
                release = ''
            if row['regional_date_evidence_required']:
                release = ''
            if len(release) == 7:
                # A month is an upper bound for diagnosis, never an invented day in the UI.
                release += '-99'
            for label, offer in pool_definitions(banner):
                definitions = [(label, offer.get('pool'))]
                guarantee = offer.get('guarantee') or {}
                if guarantee.get('pool'):
                    definitions.append((label + ':guarantee', guarantee['pool']))
                for i, slot in enumerate(offer.get('guarantee_slots', [])):
                    if slot.get('pool'):
                        definitions.append((label + ':guarantee_slot:' + str(i + 1), slot['pool']))
                for scope, pool in definitions:
                    if not pool:
                        continue
                    units, unbounded = pool_units(pool, evidence)
                    roots = {str(evidence['mst'].get(uid, {}).get('woghJa61', uid)) for uid in units}
                    shifted = sorted(units & evidence['shift_owners'].keys())
                    if shifted:
                        row['issues'].append({'scope': scope, 'kind': 'brave_shift_forms_in_pool', 'count': len(shifted), 'examples': shifted[:8]})
                    foreign = sorted((roots & evidence['limited']) - allowed)
                    future = sorted(uid for uid in roots if release and evidence['releases'].get(uid, '') > release)
                    is_friend = (offer.get('cost') or {}).get('kind') == 'friend_point' if isinstance(offer.get('cost'), dict) else False
                    if unbounded:
                        row['issues'].append({'scope': scope, 'kind': 'unrestricted_rarity_tier', 'rarities': unbounded})
                    if foreign:
                        row['issues'].append({'scope': scope, 'kind': 'unrelated_limited_units', 'count': len(foreign),
                            'examples': [{'id': uid, 'name': evidence['labels'].get(uid, '')} for uid in foreign[:8]]})
                    if future:
                        row['issues'].append({'scope': scope, 'kind': 'units_released_after_banner', 'count': len(future),
                            'examples': [{'id': uid, 'name': evidence['labels'].get(uid, ''), 'release': evidence['releases'][uid]} for uid in future[:8]]})
            row['rate_source'] = banner.get('rate_source')
            row['rate_notice'] = banner.get('rate_notice')
            row['reward_only'] = bool(banner.get('reward_pool')) and not banner.get('pool')
            report.append(row)
            summary['banner_records'] += 1
            if row['issues']:
                summary['records_with_issues'] += 1
            for kind in {issue['kind'] for issue in row['issues']}:
                summary[kind] += 1
    return {'summary': dict(summary), 'evidence': {'retail_roots': len(evidence['retail']),
            'limited_roots': len(evidence['limited']), 'known_release_dates': len(evidence['releases'])}, 'banners': report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT / 'source/build/distribution/assets/exvius-offline-v0.1.30.apk')
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/ffbe-summon-pool-audit-20261110.json')
    args = parser.parse_args()
    with zipfile.ZipFile(args.apk) as apk:
        documents = {family: json.loads(apk.read('assets/rules/gacha_' + family + '.json')) for family in FAMILIES}
    result = audit(documents)
    result['apk'] = str(args.apk)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'summary': result['summary'], 'evidence': result['evidence'], 'report': str(args.output)}))


if __name__ == '__main__':
    main()
