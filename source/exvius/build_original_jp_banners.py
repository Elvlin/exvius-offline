"""Build evidenced historical JP summon variants using their translated original art."""
from __future__ import annotations

import hashlib
import argparse
import copy
import csv
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / 'Japan content/Earlier JP crossovers/Sources'
OUTPUT = ROOT / 'source/server/gacha_original_jp.json'
SOURCE_TAG = 'historical-jp-summon'
PRESENTATION = SOURCES / 'original-summon-art-presentation.json'


def apply_art_presentation(banners, art_receipts):
    """Bind reviewed originals without changing a summon's gameplay contract."""
    if not PRESENTATION.is_file():
        return
    document=json.loads(PRESENTATION.read_text(encoding='utf8'))
    if document.get('schema')!=1 or document.get('status')not in ('REVIEWED_READY_TO_BIND','REVIEWED_PRESENTATION_DECISIONS_APPLIED'):
        raise ValueError('Summon presentation decisions are not finalized')
    entries=document['variants']
    if len(entries)!=31 or len({r['id']for r in entries})!=31:
        raise ValueError('Expected the original31 scoped presentation decisions')
    by_id={r['id']:r for r in banners}
    for decision in entries:
        banner=by_id.get(decision['id'])
        if banner is None or banner.get('source')!=SOURCE_TAG:
            raise ValueError('Presentation decision does not own this summon: '+decision['id'])
        for asset_key in ('asset','detail_asset'):
            asset=decision.get(asset_key)
            if not asset:
                continue
            original=ROOT/asset['source_file'];english=ROOT/asset['english_file']
            if not original.is_relative_to(SOURCES)or not english.is_relative_to(SOURCES):
                raise ValueError('Original and translated artwork must remain in the established source home')
            if hashlib.sha256(original.read_bytes()).hexdigest()!=asset['source_sha256']:
                raise ValueError('Reviewed original artwork changed: '+decision['id'])
            if hashlib.sha256(english.read_bytes()).hexdigest()!=asset['english_sha256']:
                raise ValueError('Reviewed English artwork changed: '+decision['id'])
            target=ROOT/'data/gacha_community/art'/english.name
            shutil.copyfile(english,target)
            art=banner.setdefault('art',{})
            if asset_key=='detail_asset' or decision['presentation']=='translated_original_detail_notice':
                art['detail_banner']=english.name
            else:
                art['banner']=english.name
                art['detail_banner']=english.name
            art.setdefault('anime_file','gacha_animation')
            art.setdefault('anime_name','gacha_moogle_rare/anime')
            art.setdefault('img_btn','gacha_btn_n')
            receipt={'original':asset['source_file'],'original_sha256':asset['source_sha256'],
                     'english':asset['english_file'],'english_sha256':asset['english_sha256'],
                     'runtime':target.relative_to(ROOT).as_posix(),
                     'source_role':asset['source_role'],'source_evidence':decision['evidence']}
            art_receipts[:]=[r for r in art_receipts if r['english']!=receipt['english']]
            art_receipts.append(receipt)
        if decision.get('english_name'):
            banner['name']=decision['english_name']
        banner['art_presentation']={'presentation':decision['presentation'],
            'historical_native_list_presentation_confirmed':decision['historical_native_list_presentation_confirmed'],
            'evidence_file':PRESENTATION.relative_to(ROOT).as_posix(),
            'dedicated_art_absence_proven':False}
        if banner.get('reconstruction',{}).get('art_role'):
            banner['reconstruction']['art_role']=decision['practical_disposition']


def apply_presentation_only():
    """Update the existing catalogues and ledger, preserving all draw rules."""
    canonical=ROOT/'source/server/gacha_named.json'
    documents={p:json.loads(p.read_text(encoding='utf8'))for p in (canonical,OUTPUT)}
    allowed={'art','art_presentation','name','reconstruction'}
    for path,document in documents.items():
        before=copy.deepcopy(document['banners'])
        receipts=document.setdefault('original_art',[])if path==OUTPUT else []
        apply_art_presentation(document['banners'],receipts)
        for old,new in zip(before,document['banners']):
            if {k:v for k,v in old.items()if k not in allowed}!={k:v for k,v in new.items()if k not in allowed}:
                raise ValueError('Summon gameplay changed during artwork binding: '+old['id'])
            old_reconstruction={k:v for k,v in old.get('reconstruction',{}).items()if k!='art_role'}
            new_reconstruction={k:v for k,v in new.get('reconstruction',{}).items()if k!='art_role'}
            if old_reconstruction!=new_reconstruction:
                raise ValueError('Unrelated reconstruction metadata changed: '+old['id'])
        path.write_text(json.dumps(document,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
    decisions=json.loads(PRESENTATION.read_text(encoding='utf8'))
    by_id={r['id']:r for r in decisions['variants']}
    ledger_path=SOURCES/'original-summon-chronological-ledger.csv'
    with ledger_path.open(encoding='utf-8-sig',newline='')as stream:
        reader=csv.DictReader(stream);fields=list(reader.fieldnames);ledger=list(reader)
    for row in ledger:
        decision=by_id.get(row['current_offer_id'])
        if not decision:
            continue
        asset=decision.get('asset')or{}
        row['english_name']=decision.get('english_name')or row['english_name']
        row['original_art']=asset.get('source_file','')
        row['translated_original_art']=asset.get('english_file','')
        row['art_status']=decision['presentation']
    with ledger_path.open('w',encoding='utf-8-sig',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(ledger)
    write_presentation_completion(documents[canonical]['banners'])
    decisions['status']='REVIEWED_PRESENTATION_DECISIONS_APPLIED'
    PRESENTATION.write_text(json.dumps(decisions,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'scope':31,'gameplay_contracts_preserved':True,
                      'original_art_presentations':sum(bool(r.get('asset'))for r in by_id.values()),
                      'documented_native_text_fallbacks':sum(not r.get('asset')for r in by_id.values())}))


def write_presentation_completion(banners):
    scoped=[b for b in banners if b.get('source')==SOURCE_TAG]
    with_list=[b for b in scoped if b.get('art',{}).get('banner')]
    with_any=[b for b in scoped if b.get('art',{}).get('banner')or b.get('art',{}).get('detail_banner')]
    primary_images={b['art'].get('banner')or b['art'].get('detail_banner')for b in with_any}
    images={b['art'][key] for b in with_any for key in ('banner','detail_banner') if b['art'].get(key)}
    missing=[b for b in scoped if b not in with_any]
    result={'variants':len(scoped),'distinct_original_translations':len(images),
            'without_dedicated_art':len(missing),
            'without_dedicated_art_definition':'Current offers without any bound original-source image; this is not a count of proven distinct missing historical images.',
            'with_art_variant_bindings':len(with_any),'shared_art_variant_bindings':len(with_any)-len(primary_images),
            'with_list_art_variant_bindings':len(with_list),'detail_only_variant_bindings':len(with_any)-len(with_list),
            'historical_exhaustive_total_confirmed':False,
            'presentation_decision_source':PRESENTATION.relative_to(ROOT).as_posix(),
            'without_art_variants':[{'id':b['id'],'name':b['name'],'source_date':b['release'],
                                     'presentation':'documented_native_text_fallback',
                                     'dedicated_historical_art_absence_proven':False}for b in missing]}
    (SOURCES/'original-summon-completion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def hold_incomplete_raid_box(banner):
    """Retain published highlights without turning them into invented slots."""
    banner = copy.deepcopy(banner)
    observations = []
    for index, box in enumerate(banner.pop('boxes', [])):
        entries = []
        for entry in box:
            row = copy.deepcopy(entry)
            row['copies'] = None
            if str(banner['id']) == '9400153' and row.get('label') == 'Event Summon Ticket':
                row['reward']['id'] = None
                row['unresolved_identity'] = 'The guide names Event Summon Ticket; its exact original item ID is not established.'
            entries.append(row)
        observations.append({'number': index + 1, 'published_highlights': entries,
                             'complete': False, 'total_slots': None})
    cost = banner.pop('cost', {})
    banner['reported_currency'] = {'kind': 20, 'id': cost.get('item_id')}
    banner['published_box_observations'] = observations
    for key in ('pool', 'reward_pool', 'box_base_id'):
        banner.pop(key, None)
    banner['activation_ready'] = False
    banner['rate_notice'] = 'Incomplete historical reward inventory. This source record is not an active summon.'
    banner['reconstruction'].update({
        'authored_fields': 'None for finite-slot contents, slot multiplicities, coin cost or overflow probabilities.',
        'unknown_original_fields': ['Complete finite-slot inventory', 'Per-entry copies', 'Coin cost',
                                    'Complete overflow pool and probabilities'],
        'activation': 'Pending complete source-backed inventory. Do not award inferred filler items.'})
    return banner


def read_rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8') if line.strip()]


def build():
    original = json.loads((SOURCES / 'original-unit-content.json').read_text(encoding='utf-8'))
    imported = {r['3HriTp6B'] for r in original['tables']['F_UNIT_MST']['rows']}
    unit_map = json.loads((SOURCES / 'native-unit-id-map.json').read_text(encoding='utf-8'))['mappings']
    imported.update(unit_map.get('F_UNIT_MST', {}).values())
    units = {r['3HriTp6B']: r for r in read_rows(ROOT / 'data/mst_decoded/F_UNIT_MST.ndjson')}
    with zipfile.ZipFile(ROOT / 'Japan content/Shared sources/ffbe-jp-ea7d9fa82659.zip') as archive:
        member = next(n for n in archive.namelist() if n == 'units.json' or n.endswith('/units.json'))
        final_units = json.loads(archive.read(member))
    evolved = {r['t74crqAL'] for r in read_rows(ROOT / 'data/mst_decoded/F_UNIT_CLASS_UP_MST.ndjson')}
    names = {r['key'].rsplit('_', 1)[1]: r['v'][0]
             for r in read_rows(ROOT / 'data/text_decoded/F_TEXT_UNITS_NAME.ndjson') if r.get('v')}
    community = json.loads((ROOT / 'source/server/gacha_community.json').read_text(encoding='utf-8'))
    dated_ids = set()
    first_release = {}

    def pool_ids(pool):
        if isinstance(pool, list):
            for row in pool:
                if row.get('unit_id'):
                    yield str(row['unit_id'])
        elif isinstance(pool, dict):
            for tier in pool.get('tiers', []):
                yield from map(str, tier.get('units', []))

    for banner in community['banners']:
        release = str(banner.get('release') or banner.get('community', {}).get('release') or '')
        if release and release[:10] <= '2022-11-22':
            for identity in pool_ids(banner.get('pool')):
                dated_ids.add(identity)
                first_release[identity] = min(first_release.get(identity, release[:10]), release[:10])
    background = {rarity: sorted(i for i in dated_ids if i.startswith(('100', '2')) and i in units
        and i not in imported and i not in evolved and units[i].get('woghJa61') == i
        and units[i].get('I3SKJ4q0') != '1' and int(units[i]['9fW0TePj']) == rarity
        and names.get(i) and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', names[i]))
        for rarity in (3, 4, 5, 7)}
    if not all(background.values()):
        raise ValueError('A bounded contemporary background tier is empty')

    def weighted_background(allocations, before=None):
        rosters = {rarity: [i for i in background[rarity] if not before or first_release[i] <= before]
                   for rarity in allocations}
        if any(weight > 0 and not rosters[rarity] for rarity, weight in allocations.items()):
            raise ValueError('Dated replacement background is empty')
        return [{'unit_id': i, 'rarity': rarity, 'rate': weight / len(rosters[rarity])}
                for rarity, weight in allocations.items() for i in rosters[rarity] if weight > 0]

    def normal(featured, total):
        return weighted_background({3: .45, 4: .40, 5: .10, 7: .05 - total}) + [
            {'unit_id': i, 'rarity': 7, 'rate': total / len(featured)} for i in featured]

    def five_plus(featured, total):
        return weighted_background({5: .95, 7: .05 - total}) + [
            {'unit_id': i, 'rarity': 7, 'rate': total / len(featured)} for i in featured]

    def nv_slot(featured, total):
        return weighted_background({7: 1 - total}) + [
            {'unit_id': i, 'rarity': 7, 'rate': total / len(featured)} for i in featured]

    artwork = {
        'arus': ('2022y11m22d_1719571929.jpg', 'arus-original-summon-english.png'),
        'yao_poron': ('2022y11m22d_1720421251.jpg', 'yao-poron-original-summon-english.png'),
        'arus_step': ('2022y11m22d_1727074017.jpg', 'arus-original-stepup-english.png'),
        'yao_poron_step': ('2022y11m22d_1727361238.jpg', 'yao-poron-original-stepup-english.png'),
    }
    art_receipts = []
    for source_name, english_name in artwork.values():
        source = SOURCES / 'Roto/original-art' / source_name
        english = SOURCES / 'Roto/english-art' / english_name
        if not source.is_file() or not english.is_file():
            raise FileNotFoundError(english)
        target = ROOT / 'data/gacha_community/art' / english_name
        shutil.copyfile(english, target)
        art_receipts.append({'original': source.relative_to(ROOT).as_posix(),
            'original_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'english': english.relative_to(ROOT).as_posix(),
            'english_sha256': hashlib.sha256(english.read_bytes()).hexdigest(),
            'runtime': target.relative_to(ROOT).as_posix()})

    disclaimer = ('The original artwork, printed offer features and cited contemporary mechanics are preserved. '
        'The complete historical server pool was not recovered. The explicit residual character list, '
        'non-NV weights and unspecified guaranteed-slot weights are authored source data, not a recovered JP rate table.')
    banners = []

    def create(number, name, art_key, featured, rate, **extra):
        identity = str(9400100 + number)
        b = {'id': identity, 'detail_id': str(int(identity) * 10 + 1), 'type': 'normal',
            'name': name, 'name_override': True, 'exe_type': 'primary', 'draws': 1,
            'release': '2022-11-22', 'season': 'collaborations', 'tab': 'limited',
            'schedule': {'disp_order': 940100 + number, 'banner_type': 0,
                'window': {'from': '2022-11-22 17:00:00', 'to': '2099-12-31 23:59:59'}},
            'art': {'banner': artwork[art_key][1], 'detail_banner': artwork[art_key][1],
                'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_rare/anime', 'img_btn': 'gacha_btn_n'},
            'cost': {'kind': 'lapis', 'amount': 500}, 'pool': normal(featured, rate),
            'preview_units': featured[:1], 'source': SOURCE_TAG, 'provenance': 'original-jp-offer',
            'historical_window': {'from': '2022-11-22T17:00:00+09:00', 'to': '2022-12-18T23:59:00+09:00'},
            'historical_original_server_id': None, 'pool_authored': True,
            'rate_notice': disclaimer,
            'sources': ['https://jp.finalfantasy.com/news/4293/',
                'https://altema.jp/ffbe/rotonomonsyouhikubekika',
                'Japan content/Earlier JP crossovers/Sources/Roto/original-art/' + artwork[art_key][0]]}
        b.update(extra)
        banners.append(b)
        return b

    featured_by_key = {'arus': ['346000107'], 'yao_poron': ['346000307', '346000407']}
    for number, key, title, rate in [(1, 'arus', 'Arus', .01), (2, 'yao_poron', 'Yao and Poron', .015)]:
        featured = featured_by_key[key]
        create(number, title + ' Featured Summon', key, featured, rate,
            secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1,
                'bonus_rewards': [{'kind': 20, 'id': 106230830, 'count': 1,
                    'display_name': 'Collaboration Special Exchange Ticket 2022/11'}]},
            historical_offer_family='JP-ROTO-20221122-' + ('ARUS' if key == 'arus' else 'YAO-PORON') + '-PICKUP')
        step_banner = create(number + 2, title + ' Step-Up Summon', key + '_step', featured, rate,
            type='step', draws=11, lap_limit=1, steps=[],
            historical_offer_family='JP-ROTO-20221122-' + ('ARUS' if key == 'arus' else 'YAO-PORON') + '-STEPUP')
        for index, amount in enumerate([2500, 3000, 5000, 0, 5000, 5000]):
            step = {'cost': {'kind': 'lapis', 'amount': amount} if amount else {'kind': 'free'}, 'draws': 11}
            if index in (0, 1):
                step['guarantee_slots'] = [{'count': 1 if index == 0 else 3,
                    'label': '5-star or NV', 'pool': five_plus(featured, rate)}]
            if key == 'arus' and index in (2, 5):
                step['guarantee_slots'] = [{'count': 1, 'label': 'NV',
                    'pool': nv_slot(featured, .05 if index == 2 else .10)}]
            if key == 'yao_poron' and index == 5:
                step['guarantee_slots'] = [{'count': 1, 'label': 'NV', 'pool': nv_slot(featured, .10)}]
            fragment = ('250016800' if key == 'arus' and index == 4 else
                        '250017000' if key == 'yao_poron' and index == 2 else
                        '250017100' if key == 'yao_poron' and index == 4 else None)
            if fragment:
                step['bonus_rewards'] = [{'kind': 20, 'id': int(unit_map.get('F_ITEM_MST', {}).get(fragment, fragment)), 'count': 50}]
            step_banner['steps'].append(step)
        create(number + 4, title + ' Daily Half-Price Summon', key, featured, rate,
            cost={'kind': 'lapis', 'amount': 250}, daily_limit=1, single_only=True,
            historical_offer_family='JP-ROTO-20221122-' + ('ARUS' if key == 'arus' else 'YAO-PORON') + '-PICKUP',
            historical_variant='Printed once-per-day half-price single from the same original pickup menu')

    def extra_art(original, english):
        source, translated = SOURCES / original, SOURCES / english
        if not source.is_file() or not translated.is_file():
            raise FileNotFoundError(translated)
        target = ROOT / 'data/gacha_community/art' / translated.name
        shutil.copyfile(translated, target)
        art_receipts.append({'original': source.relative_to(ROOT).as_posix(),
            'original_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'english': translated.relative_to(ROOT).as_posix(),
            'english_sha256': hashlib.sha256(translated.read_bytes()).hexdigest(),
            'runtime': target.relative_to(ROOT).as_posix()})
        return {'banner': translated.name, 'detail_banner': translated.name,
            'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_rare/anime', 'img_btn': 'gacha_btn_n'}

    def explicit(ids):
        mapped = [str(unit_map.get('F_UNIT_MST', {}).get(str(i), str(i))) for i in ids]
        return [{'unit_id': i, 'rarity': int(units[i]['9fW0TePj']), 'rate': 1 / len(mapped)} for i in mapped]

    def reconstructed_pool(featured, allocations, release=None):
        featured = [str(unit_map.get('F_UNIT_MST', {}).get(str(i), str(i))) for i in featured]
        by_rarity = {r: [i for i in featured if int(units[i]['9fW0TePj']) == r] for r in allocations}
        pool = []
        for rarity, weight in allocations.items():
            # Half of each represented rarity belongs to the published featured roster.
            # This is a documented replacement weight, never a historical disclosure.
            selected = by_rarity[rarity]
            featured_weight = weight / 2 if selected else 0
            pool.extend(weighted_background({rarity: weight - featured_weight}, before=release))
            pool.extend({'unit_id': i, 'rarity': rarity, 'rate': featured_weight / len(selected)} for i in selected)
        return pool

    def historical(number, name, featured, release, until, source, original_art, english_art,
                   pool=None, **extra):
        identity = str(9400100 + number)
        banner = {'id': identity, 'detail_id': str(int(identity) * 10 + 1), 'type': 'normal',
            'name': name, 'name_override': True, 'exe_type': 'primary', 'draws': 1,
            'release': release, 'season': 'collaborations', 'tab': 'limited',
            'schedule': {'disp_order': 940100 + number, 'banner_type': 0,
                'window': {'from': (release if len(release) == 10 else '2015-01-01') + ' 00:00:00', 'to': '2099-12-31 23:59:59'}},
            'art': extra_art(original_art, english_art) if original_art and english_art else {}, 'cost': {'kind': 'lapis', 'amount': 500},
            'pool': pool or explicit(featured),
            'preview_units': [str(unit_map.get('F_UNIT_MST', {}).get(str(i), str(i))) for i in featured[:3]],
            'source': SOURCE_TAG, 'provenance': 'original-jp-offer',
            'historical_window': {'from': release, 'to': until}, 'historical_original_server_id': None,
            'pool_authored': True, 'rate_notice': disclaimer, 'sources': [source],
            'reconstruction': {'reason': 'The original named offer and associated artwork are preserved; the complete original server reply and rate table were not recovered after the recorded original-source search.',
                'unknown_original_fields': ['Residual eligible roster', 'Per-reward rates', 'Unprinted purchase terms'],
                'runtime_schedule': 'Historical event made available without an expired closing date.'}}
        banner.update(extra)
        banners.append(banner)
        return banner

    mh = ['100000115', '100000324', '100000414', '100000513']
    historical(7, 'Monster Hunter Explore Rare Summon', mh, '2016-12-22', '2017-01-01',
        'https://www.4gamer.net/games/282/G028200/20161222153/',
        'original-art/mh-20161222-notice-01.jpg', 'english-art/mh-20161222-pickup-english.png',
        pool=reconstructed_pool(mh, {3: .80, 4: .19, 5: .01}, '2016-12-22'),
        historical_offer_family='JP-MH-20161222-RARE',
        secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1})
    bravely = ['313000105', '313000205', '313000404', '314000104', '314000203']
    historical(8, 'Bravely Series Rare Summon', bravely, '2017-07-21', '2017-07-31',
        'https://gamebiz.jp/news/189451', 'original-art/bravely-20170721-rare-header.jpg',
        'english-art/bravely-20170721-pickup-english.png',
        pool=reconstructed_pool(bravely, {3: .76, 4: .21, 5: .03}, '2017-07-21'),
        historical_offer_family='JP-BRAVELY-20170721-RARE',
        secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1})
    sin = ['336000105', '336000205', '336000304']
    sin_art = ('original-art/sin-20210906-pickup-original.png', 'english-art/sin-20210906-pickup-english.png')
    historical(9, 'SINoALICE Featured Summon Festival', sin, '2021-09-06', '2021-09-18',
        'https://jp.finalfantasy.com/news/3653/', *sin_art,
        pool=reconstructed_pool(sin, {3: .45, 4: .40, 5: .10, 7: .05}, '2021-09-06'),
        historical_offer_family='JP-SINO-20210906-PICKUP',
        secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1})
    historical(10, 'SINoALICE Collaboration Commemorative Ticket Summon', sin,
        '2021-09-06', '2021-09-18', 'https://jp.finalfantasy.com/news/3653/', None, None,
        cost={'kind': 'item', 'item_id': 106224700, 'amount': 1},
        historical_offer_family='JP-SINO-20210906-COLLAB-TICKET')
    historical(11, '7-Star SINoALICE Unit Guaranteed Ticket Summon', ['336000107', '336000207'],
        '2021-09-06', '2021-09-18', 'https://jp.finalfantasy.com/news/3653/', None, None,
        cost={'kind': 'item', 'item_id': 106224600, 'amount': 1}, awakened_ticket=True,
        historical_offer_family='JP-SINO-20210906-7STAR-TICKET')

    # These are the original raid coin summons, not paid character banners.
    raids = [(12, '738', 'Assault! Nef-Garmat! Raid Summon', 106301700,
              ['100000215', '100000614', '100000713'], range(213000100, 213001801, 100),
              '2016-12-22', 'https://www.4gamer.net/games/282/G028200/20161222153/'),
             (13, '742', 'The Four Sinistrals Attack! Raid Summon', 106302500,
              ['303000204'], range(215000100, 215000601, 100),
              '2017-01-20', 'https://x.com/FFRS_JP/status/822359064797728769'),
             (14, '771', 'Luxendarc Raid Summon', 106303700,
              ['315000104'], range(218000700, 218001201, 100),
              '2017-07-21', 'https://gamebiz.jp/news/189451')]
    for number, area, title, coin, characters, materials, date, source in raids:
        materials = list(materials)
        reward_pool = [{'kind': 10, 'id': int(i), 'count': 1, 'rate': .03 / len(characters)} for i in characters]
        reward_pool += [{'kind': 20, 'id': i, 'count': 1, 'rate': .97 / len(materials)} for i in materials]
        b = historical(number, title, characters, date, None, source, None, None,
            reward_pool=reward_pool, cost={'kind': 'item', 'item_id': coin, 'amount': 100, 'is_coin': True},
            historical_offer_family='JP-' + area + '-RAID-SUMMON')
        b.pop('pool')
        b['reconstruction'].update({'art_role': 'Original dedicated summon artwork not recovered. No substitute event card or invented artwork is bound.',
            'explicit_authored_terms': '100 original raid coins per pull;3% total among published raid characters;97% equally among original recovered crafting materials; one item per material draw. These costs, quantities and weights are replacements, not recovered historical values.'})

    mana = ['312000105', '312000205', '312000305', '312000404', '312000505',
            '312000605', '312000705', '312000805', '312000905', '312001007']
    historical(15, 'Trials of Mana Featured Summon Festival', mana, '2021-02-19', '2021-02-26',
        'https://jp.finalfantasy.com/news/3397/', 'original-art/mana-20210219-collab-original.png',
        'english-art/mana-20210219-collab-english.png',
        pool=reconstructed_pool(mana, {3: .45, 4: .40, 5: .10, 7: .05}, '2021-02-19'),
        historical_offer_family='JP-MANA-20210219-PICKUP',
        secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1})
    historical(16, 'Trials of Mana Collaboration Unit Guaranteed Free Summon',
        [i for i in mana if i != '312000404'], '2021-02-19', '2021-02-28',
        'https://jp.finalfantasy.com/news/3397/', 'original-art/mana-20210219-free-original.png',
        'english-art/mana-20210219-free-english.png', cost={'kind': 'free'}, purchase_limit=1,
        historical_offer_family='JP-MANA-20210219-ONCE-FREE',
        original_guarantee='One 5-star or NV Trials of Mana collaboration unit, one time only')

    historical(17, 'Collaboration New NV 30% Ticket Summon 2022/11',
        ['346000107', '346000307', '346000407'], '2022-11-22', '2022-12-18',
        'https://altema.jp/ffbe/rotonomonsyouhikubekika', None, None,
        pool=weighted_background({5: .70}) + [{'unit_id': i, 'rarity': 7, 'rate': .10}
            for i in ['346000107', '346000307', '346000407']],
        cost={'kind': 'item', 'item_id': 106230840, 'amount': 1},
        historical_offer_family='JP-ROTO-20221122-COLLAB-NV30-TICKET',
        original_guarantee='The three new collaboration NV units have a combined30% appearance rate.',
        reconstruction={'verified': 'Exact original item106230840 states combined30% new collaboration NV; originalSPexchange sells3ticketsfor3SPtickets each.',
            'authored_fields': 'Equal10% per new collaboration NV; remaining70% assigned to preserved FFBE5-star bases. Residual identities, residual rarity and exact individual split were not recovered.',
            'art_role': 'No dedicated original ticket-summon panel recovered. No artwork substituted.'})

    saga_january = [('rocbouquet', 'Rocbouquet', '349000107', .0075, '250031100'),
                    ('albert', 'Albert', '348000107', .01, '250031000'),
                    ('ellen', 'Ellen', '309000507', .01, '250031200')]
    for offset, (key, title, unit, rate, fragment) in enumerate(saga_january):
        source = 'https://altema.jp/ffbe/romasagagachahikubekika'
        base = 'saga-20240111-' + key
        normal_art = ('original-art/' + base + '-pickup-original.jpg',
                      'english-art/' + base + '-pickup-english.png')
        common = {'historical_offer_family': 'JP-SAGA-20240111-' + key.upper()}
        historical(18 + offset, title + ' Featured Summon', [unit], '2024-01-11', '2024-02-04',
            source, *normal_art, pool=normal([unit], rate),
            secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1,
                'bonus_rewards': [{'kind': 20, 'id': 106233670, 'count': 1}]}, **common)
        step = historical(21 + offset, title + ' Step-Up Summon', [unit], '2024-01-11', '2024-02-04',
            source, 'original-art/' + base + '-stepup-original.jpg',
            'english-art/' + base + '-stepup-english.png', pool=normal([unit], rate),
            type='step', draws=11, lap_limit=1, steps=[], **common)
        seven = key == 'rocbouquet'
        curated = [unit, *[i for i in background[7] if i != unit][:49]]
        for index, amount in enumerate([2500, 3000, 5000, 0, 5000, 5000] + ([5000] if seven else [])):
            row = {'cost': {'kind': 'lapis', 'amount': amount} if amount else {'kind': 'free'}, 'draws': 11}
            if seven:
                if index in (0, 1, 2):
                    row['guarantee_slots'] = [{'count': index + 1, 'label': 'NV', 'pool': nv_slot([unit], .15)}]
                elif index in (4, 5):
                    special = explicit(curated) if index == 4 else [
                        {'unit_id': i, 'rarity': 7, 'rate': .10 if i == unit else .90 / 49} for i in curated]
                    row['guarantee_slots'] = [{'count': 1, 'label': 'Curated50 NV', 'pool': special}]
                elif index == 6:
                    row['guarantee_slots'] = [{'count': 1, 'label': 'NV', 'pool': nv_slot([unit], .15)}]
                    row['bonus_rewards'] = [{'kind': 20, 'id': int(unit_map.get('F_ITEM_MST', {}).get(fragment, fragment)), 'count': 50}]
            else:
                if index in (0, 1):
                    row['guarantee_slots'] = [{'count': 1 if index == 0 else 3, 'label': '5-star or NV', 'pool': five_plus([unit], rate)}]
                elif index in (2, 5):
                    row['guarantee_slots'] = [{'count': 1, 'label': 'NV', 'pool': nv_slot([unit], .05 if index == 2 else .10)}]
                elif index == 4:
                    row['bonus_rewards'] = [{'kind': 20, 'id': int(unit_map.get('F_ITEM_MST', {}).get(fragment, fragment)), 'count': 50}]
            step['steps'].append(row)
        if seven:
            step['reconstruction']['curated50'] = 'Original promises50 curatedNV but identities were not recovered. Explicit replacement50 = Rocbouquet plus49 dated preserved FF/NV bases; uniformSTEP5, Rocbouquet10%STEP6. Other unspecified guaranteedNV weights authored.'
        historical(25 + offset, title + ' Daily Half-Price Summon', [unit], '2024-01-11', '2024-02-04',
            source, *normal_art, pool=normal([unit], rate), cost={'kind': 'lapis', 'amount': 250},
            daily_limit=1, single_only=True, **common)
    guaranteed_saga = [x[2] for x in saga_january]
    special = historical(24, 'SaGa Collaboration Special Step-Up Summon', guaranteed_saga,
        '2024-01-11', '2024-02-04', 'https://altema.jp/ffbe/romasagagachahikubekika',
        'original-art/saga-20240111-guaranteed-stepup-original.jpg',
        'english-art/saga-20240111-guaranteed-stepup-english.png',
        pool=normal(guaranteed_saga, .0275), type='step', draws=11, lap_limit=1,
        historical_offer_family='JP-SAGA-20240111-GUARANTEED-STEPUP', steps=[])
    for index in range(3):
        special['steps'].append({'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11,
            'guarantee_slots': [{'count': 1, 'label': 'SaGa NV' if index == 2 else 'NV',
                'pool': explicit(guaranteed_saga) if index == 2 else nv_slot(guaranteed_saga, .55)}]})

    # Original older paid campaigns remain separate from the2024 releases.
    for number, title, roster, date, source in [
        (28, 'Romancing SaGa 3 Rare Summon', ['309000105', '309000205', '309000304', '309000403'],
         '2017-01-20', 'https://ffbe.gorillawiki.jp/entry/11451'),
        (29, 'Imperial SaGa Revival Featured Summon', ['303000305'],
         '2018', 'https://altema.jp/ffbe/ffbeoriginalchara153')]:
        historical(number, title, roster, date, None, source, None, None,
            pool=reconstructed_pool(roster, {3: .76, 4: .21, 5: .03}, date if len(date) == 10 else date + '-12-31'),
            historical_offer_family='JP-SAGA-' + date + '-RARE',
            historical_date_precision='day' if len(date) == 10 else 'year',
            secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1})

    def available_art(original, english):
        return (original, english) if (SOURCES / original).is_file() and (SOURCES / english).is_file() else (None, None)

    def published_normal(rates):
        # Preserve every recovered co-featured rate whose actual native identity exists.
        usable = lambda i: i in units and names.get(i) and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', names[i])
        unavailable = {i: v for i, v in rates.items() if not usable(i)}
        rates = {i: v for i, v in rates.items() if usable(i)}
        eligible_background = [r for r in weighted_background({3: .45, 4: .40, 5: .10, 7: .05 - sum(rates.values())})
                               if r['unit_id'] not in rates]
        # Some already-present FF units also occur in the residual tier. Distribute
        # that residual tier across the other bases rather than duplicating them.
        for rarity in (3, 4, 5, 7):
            rows = [r for r in eligible_background if r['rarity'] == rarity]
            allocation = {3: .45, 4: .40, 5: .10, 7: .05 - sum(rates.values())}[rarity]
            for row in rows:
                row['rate'] = allocation / len(rows)
        return eligible_background + [{'unit_id': i, 'rarity': 7, 'rate': rate} for i, rate in rates.items()], unavailable

    new_2024 = [
        (30, 'saga', '20240119', 'asellus', 'Asellus', '350000107', .0075, '250031300', True, 106233740, {}),
        (31, 'saga', '20240119', 'gustave', 'Gustave XIII', '351000107', .01, '250031400', False, 106233740, {}),
        (36, 'roto', '20240219', 'alan', 'Hero Alan', '346000507', .0075, '250032100', True, 106233930,
            {'100043407': .005, '253001907': .005, '346000107': .005, '346000307': .005}),
        (37, 'roto', '20240219', 'caesarion', 'Sea King II Caesarion', '346000707', .0075, '250032200', True, 106233930,
            {'100043707': .005, '100042607': .005, '346000307': .005, '346000407': .005}),
        (38, 'roto', '20240219', 'asthea', 'Hero Asthea', '346000607', .01, '250032000', False, 106233930,
            {'215003107': .005, '346000107': .005, '346000407': .005}),
        (45, 'roto', '20240229', 'hero-arus', 'Hero Arus', '346000907', .0075, '250032300', True, 106234070,
            {'100043907': .005, '215003207': .005, '346000307': .005, '346000407': .005}),
        (46, 'roto', '20240229', 'imagine', 'Imagine', '346000807', .0075, '250032400', True, 106234070,
            {'210002807': .005, '204003407': .005, '346000107': .005, '346000407': .005}),
    ]
    for number, family, compact_date, key, title, unit, rate, fragment, seven, ticket, cofeatured in new_2024:
        date = compact_date[:4] + '-' + compact_date[4:6] + '-' + compact_date[6:]
        until = '2024-02-04' if family == 'saga' else '2024-03-20'
        source = ('https://altema.jp/ffbe/sagagachahikubekika2' if family == 'saga' else
                  'https://altema.jp/ffbe/rotonomonsyouhikubekika' + ('2' if compact_date == '20240219' else '3'))
        prefix = '' if family == 'saga' else 'Roto/'
        stem = family + '-' + compact_date + '-' + key
        normal_art = available_art(prefix + 'original-art/' + stem + '-pickup-original.jpg',
                                   prefix + 'english-art/' + stem + '-pickup-english.png')
        step_art = available_art(prefix + 'original-art/' + stem + '-stepup-original.jpg',
                                 prefix + 'english-art/' + stem + '-stepup-english.png')
        pool, unavailable = published_normal({unit: rate, **cofeatured})
        offset = 2 if family == 'saga' or compact_date == '20240229' else 3
        common = {'historical_offer_family': 'JP-' + family.upper() + '-' + compact_date + '-' + key.upper(),
                  'unavailable_original_cofeatured_units': unavailable}
        historical(number, title + ' Featured Summon', [unit], date, until, source, *normal_art,
            pool=pool, secondary_offer={'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11, 'exe_count': 1,
                'bonus_rewards': [{'kind': 20, 'id': ticket, 'count': 1}]}, **common)
        step = historical(number + offset, title + ' Step-Up Summon', [unit], date, until, source, *step_art,
            pool=pool, type='step', draws=11, lap_limit=1, steps=[], **common)
        curated = [unit, *[i for i in background[7] if i != unit][:49]]
        for index, amount in enumerate([2500, 3000, 5000, 0, 5000, 5000] + ([5000] if seven else [])):
            row = {'cost': {'kind': 'lapis', 'amount': amount} if amount else {'kind': 'free'}, 'draws': 11}
            if seven:
                if index in (0, 1, 2, 6):
                    row['guarantee_slots'] = [{'count': index + 1 if index < 3 else 1, 'label': 'NV',
                        'pool': nv_slot([unit], .15)}]
                elif index in (4, 5):
                    special_pool = explicit(curated) if index == 4 else [
                        {'unit_id': i, 'rarity': 7, 'rate': .10 if i == unit else .90 / 49} for i in curated]
                    row['guarantee_slots'] = [{'count': 1, 'label': 'Curated50 NV', 'pool': special_pool}]
                bonus_index = 6
            else:
                if index in (0, 1):
                    row['guarantee_slots'] = [{'count': 1 if index == 0 else 3, 'label': '5-star or NV',
                        'pool': five_plus([unit], rate)}]
                elif index in (2, 5):
                    row['guarantee_slots'] = [{'count': 1, 'label': 'NV',
                        'pool': nv_slot([unit], .05 if index == 2 else .10)}]
                bonus_index = 4
            if index == bonus_index:
                row['bonus_rewards'] = [{'kind': 20, 'id': int(unit_map.get('F_ITEM_MST', {}).get(fragment, fragment)), 'count': 50}]
            step['steps'].append(row)
        step['reconstruction']['curated50_if_applicable'] = 'Original size50 and printed10%featured slot retained; actual historical50 identities absent. Replacement roster explicitly frozen from the reviewed contemporary native bases. Unprinted guaranteed-slot weights authored.'
        historical(number + 2 * offset, title + ' Daily Half-Price Summon', [unit], date, until, source,
            *normal_art, pool=pool, cost={'kind': 'lapis', 'amount': 250}, daily_limit=1, single_only=True, **common)

    def mapped_item(identity):
        return int(unit_map.get('F_ITEM_MST', {}).get(str(identity), str(identity)))

    item_names = {r['key'].rsplit('_', 1)[1]: r['v'][0]
                  for r in read_rows(ROOT / 'data/text_decoded/F_TEXT_ITEM_NAME.ndjson') if r.get('v')}

    def box_entry(kind, identity, count, copies=1, featured=True, label=None):
        if not label or label.startswith('Reward '):
            label = item_names.get(str(mapped_item(identity))) if kind == 20 else names.get(str(identity))
        return {'reward': {'kind': kind, 'id': mapped_item(identity) if kind == 20 else int(identity), 'count': count},
                'copies': copies, 'featured': featured, 'label': label or ('Item ' + str(identity))}

    # These guides publish highlights, not complete finite-slot inventories.
    # Preserve them as inactive observations until the missing data is recovered.
    box_specs = []
    roto_old = json.loads((SOURCES / 'Roto/partial-box-observations.json').read_text(encoding='utf-8'))
    old_boxes = []
    for row in roto_old['boxes']:
        entries = []
        for reward in row['reported_rewards']:
            identity = reward.get('native_item_id')
            if not identity and reward.get('name_ja') == 'セレクト召喚チケット':
                entries.append(box_entry(23, 260, None, label='5-Star Select Summon Ticket'))
            elif identity:
                entries.append(box_entry(20, identity, reward.get('reported_quantity'),
                    label=names.get(str(identity)) or ('Reward ' + str(identity))))
        old_boxes.append(entries)
    box_specs.append((51, 'Fierce Battle on the Aliahan Plain! Box Summon', '2022-11-22',
        106318300, old_boxes, roto_old['source']))
    saga_boxes = [
        [box_entry(20, 106233700, 5, label='The Labyrinth in the Volcano Depths Event Summon Ticket'),
         box_entry(10, 303000204, 1, label='Demigod Adel')],
        [box_entry(20, 106233700, 5, label='The Labyrinth in the Volcano Depths Event Summon Ticket'),
         box_entry(20, 293000200, 1, label='Ascension Pearl')],
        [box_entry(20, 106233700, 5, label='The Labyrinth in the Volcano Depths Event Summon Ticket'),
         box_entry(20, 293000200, 1, label='Ascension Pearl')],
        [box_entry(20, 106233700, 5, label='The Labyrinth in the Volcano Depths Event Summon Ticket'),
         box_entry(20, 250031000, 50, label='Albert Fragments')],
    ]
    box_specs.append((52, 'The Labyrinth in the Volcano Depths Box Summon', '2024-01-11',
        106323500, saga_boxes, 'https://altema.jp/ffbe/kazannookusoko'))
    # The recovered event guide identifies five boxes and their key rewards.
    # It does not establish the complete inventories or each entry's copies.
    saga_raid_boxes = [
        [box_entry(21, 409013200, 1, label='Kris Knife'), box_entry(20, 106233700, 3, label='Event Summon Ticket')],
        [box_entry(20, 106233700, 5, label='Event Summon Ticket'), box_entry(20, 106211240, 20, label='Red Star Quartz')],
        [box_entry(20, 106233700, 1, label='Event Summon Ticket'), box_entry(20, 106211240, 30, label='Red Star Quartz')],
        [box_entry(20, 106233700, 1, label='Event Summon Ticket'), box_entry(20, 106211240, 40, label='Red Star Quartz')],
        [box_entry(20, 250031400, 50, label='Gustave XIII Fragments'), box_entry(20, 106233700, 3, label='Event Summon Ticket')],
    ]
    box_specs.append((53, 'Half-Human, Half-Mystic Fate Box Summon', '2024-01-19',
        106323600, saga_raid_boxes, 'https://altema.jp/ffbe/hannzinnhannyounounnmei'))
    castle_boxes = []
    for event_tickets, nv_tickets, fragment_tickets in [(5, 0, 0), (5, 1, 0), (10, 1, 1), (10, 2, 1)]:
        entries = [box_entry(20, 106234100, event_tickets, label='Air Raid! Loran Castle Event Summon Ticket')]
        if nv_tickets:
            entries.append(box_entry(20, 106234110, nv_tickets, label='Air Raid! Loran Castle NV Guaranteed Summon Ticket'))
        if fragment_tickets:
            entries.append(box_entry(20, 106234120, fragment_tickets, label='Air Raid! Loran Castle NV Fragment Exchange Ticket'))
        castle_boxes.append(entries)
    # Source rows are resolved by the reward worker and added as exact item IDs
    # in the source receipt. Do not substitute Roto fragments for FF fragments.
    castle_fragments = SOURCES / 'Roto/loran-castle-box-fragments.json'
    if castle_fragments.is_file():
        for reward in json.loads(castle_fragments.read_text(encoding='utf-8'))['rows']:
            for index, count in enumerate(reward['box_counts']):
                if count:
                    castle_boxes[index].append(box_entry(20, reward['item_id'], count, label=reward['english_name']))
    box_specs.append((54, 'Air Raid! Loran Castle Box Summon', '2024-02-29',
        106323900, castle_boxes, 'https://altema.jp/ffbe/kuusyuuroranjyou'))
    for number, title, date, coin, boxes, source in box_specs:
        b = historical(number, title, [], date, None, source, None, None,
            type='box', boxes=boxes, box_base_id=980000 + number * 10,
            cost={'kind': 'item', 'item_id': coin},
            historical_offer_family='JP-' + str(coin) + '-BOX-SUMMON')
        b.pop('pool')
        b['reconstruction'].update({'verified': 'The cited source supplies the named box summon and published key-reward highlights. Full slot inventories are missing.',
            'finite_box_count': 'Five originally reported sets' if number == 51 else
                'Four originally reported sets' if number in (52, 54) else 'Five published boxes; full inventories missing',
            'art_role': 'No dedicated original summon panel bound. Event cards are not substituted.'})
        b.update(hold_incomplete_raid_box(b))
        # update() preserves removed keys on the original dict; remove the
        # executable fields explicitly so no generator run restores the filler.
        for field in ('boxes', 'cost', 'pool', 'reward_pool', 'box_base_id'):
            b.pop(field, None)

    def category_pool(category):
        candidates = []
        for identity, record in final_units.items():
            if identity not in units or int(record.get('rarity_min', 0)) != 7 or not record.get('is_summonable'):
                continue
            u = units[identity]
            if u.get('woghJa61') != identity or u.get('I3SKJ4q0') == '1' or identity in evolved:
                continue
            categories = record.get('entries', {}).get(identity, {}).get('categories', [])
            if category in categories and names.get(identity) and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', names[identity]):
                candidates.append(identity)
        if not candidates:
            raise ValueError('No source-backed current native category candidate: ' + category)
        return explicit(sorted(candidates))

    ticket_specs = [
        (55, 'SaGa Collaboration Commemorative Daily Free 10 Summons', None, '2024-01-12',
            ['349000107', '348000107', '309000507'], {'daily_limit': 1, 'draws': 10, 'cost': {'kind': 'free'}}),
        (56, 'Emblem of Roto Collaboration Daily Free Summon', None, '2022-11-22',
            ['346000107', '346000307', '346000407'], {'daily_limit': 1, 'cost': {'kind': 'free'}}),
        (57, 'Emblem of Roto Collaboration Guaranteed Free 10 Summons', None, '2024-02-19',
            ['346000107', '346000307', '346000407'], {'purchase_limit': 1, 'draws': 10, 'cost': {'kind': 'free'},
                'guarantee_slots': [{'count': 1, 'label': 'Arus, Yao or Poron', 'pool': explicit(['346000107', '346000307', '346000407'])}]}),
        (58, 'Emblem of Roto Collaboration Daily Free 10 Summons', None, '2024-02-20',
            ['346000107', '346000307', '346000407', '346000507', '346000607', '346000707'],
            {'daily_limit': 1, 'draws': 10, 'cost': {'kind': 'free'}}),
        (59, 'Avalon Vestment Coin Summon 2024/1', 106233720, '2024-01-11', [], {'category': 'Earth', 'coin_amount': 5, 'bonus_rewards': [{'kind': 21, 'id': 405038900, 'count': 1}, {'kind': 20, 'id': 235037700, 'count': 2}, {'kind': 20, 'id': 900000001, 'count': 10}, {'kind': 20, 'id': 293000200, 'count': 10}, {'kind': 20, 'id': 293000100, 'count': 10}, {'kind': 20, 'id': 500000001, 'count': 10}, {'kind': 20, 'id': 500000002, 'count': 50}, {'kind': 20, 'id': 500000004, 'count': 25}, {'kind': 20, 'id': 500000003, 'count': 10}, {'kind': 20, 'id': 500000005, 'count': 15}, {'kind': 23, 'id': 110, 'count': 50}]}),
        (60, 'Half-Human, Half-Mystic Fate Coin Summon 2024/1/19', 106233750, '2024-01-19', [], {'category': 'Dark', 'coin_amount': 5, 'bonus_rewards': [{'kind': 21, 'id': 406009500, 'count': 1}, {'kind': 20, 'id': 235037700, 'count': 2}, {'kind': 20, 'id': 900000001, 'count': 10}, {'kind': 20, 'id': 293000200, 'count': 10}, {'kind': 20, 'id': 293000100, 'count': 10}, {'kind': 20, 'id': 500000001, 'count': 10}, {'kind': 20, 'id': 500000002, 'count': 50}, {'kind': 20, 'id': 500000004, 'count': 25}, {'kind': 20, 'id': 500000003, 'count': 10}, {'kind': 20, 'id': 500000005, 'count': 15}, {'kind': 23, 'id': 110, 'count': 50}]}),
        (61, 'SaGa New NV 30% Ticket Summon 2024/1', 106233680, '2024-01-11',
            ['349000107', '348000107', '309000507'], {'new_nv_rate': .30}),
        (62, 'Light Category NV Guaranteed Ticket Summon 2024/1', 106233690, '2024-01-11', [], {'category': 'Light'}),
        (63, 'Earth Category NV Guaranteed Ticket Summon 2024/1', 106233580, '2024-01-11', [], {'category': 'Earth'}),
        (64, 'Dark Category NV Guaranteed Ticket Summon 2024/1', 106233570, '2024-01-19', [], {'category': 'Dark'}),
        (65, 'Emblem of Roto Category NV Guaranteed Ticket Summon 2024/2', 106233940, '2024-02-19', [], {'category': 'Emblem of Roto'}),
        (66, 'Light Category NV Guaranteed Ticket Summon 2024/2/19', 106233950, '2024-02-19', [], {'category': 'Light'}),
        (67, 'The Saviors Category NV Guaranteed Ticket Summon 2024/2', 106233960, '2024-02-19', [], {'category': 'The Saviors'}),
        (68, 'Water Category NV Guaranteed Ticket Summon 2024/2', 106233970, '2024-02-19', [], {'category': 'Water'}),
        (69, 'Earth Category NV Guaranteed Ticket Summon 2024/3', 106234080, '2024-02-29', [], {'category': 'Earth'}),
        (70, 'Fire Category NV Guaranteed Ticket Summon 2024/3', 106234090, '2024-02-29', [], {'category': 'Fire'}),
        (71, 'The Labyrinth in the Volcano Depths Event Ticket Summon', 106233700, '2024-01-11',
            ['349000107', '348000107', '309000507'], {}),
        (72, 'Fierce Battle on the Aliahan Plain! Featured Ticket Summon', 106230850, '2022-11-22',
            ['346000107', '346000307', '346000407'], {}),
        (73, 'Air Raid! Loran Castle Event Ticket Summon', 106234100, '2024-02-29',
            ['346000907', '346000807'], {}),
    ]
    for number, title, ticket, date, featured, mechanics in ticket_specs:
        mechanics = dict(mechanics)
        category = mechanics.pop('category', None)
        coin_amount = mechanics.pop('coin_amount', 1)
        new_rate = mechanics.pop('new_nv_rate', None)
        pool = category_pool(category) if category else normal(featured, new_rate or .015)
        if new_rate:
            pool = weighted_background({5: 1 - new_rate}) + [
                {'unit_id': i, 'rarity': 7, 'rate': new_rate / len(featured)} for i in featured]
        cost = {'kind': 'item', 'item_id': ticket, 'amount': coin_amount, 'is_coin': coin_amount == 5} if ticket else {'kind': 'free'}
        cost = mechanics.pop('cost', cost)
        source = ('https://jp.finalfantasy.com/news/4854/' if number in (55, 59, 61, 62, 63, 71) else
                  'https://jp.finalfantasy.com/news/4870/' if number in (60, 64) else
                  'https://jp.finalfantasy.com/news/4293/' if number in (56, 72) else
                  'https://jp.finalfantasy.com/news/4917/' if number in (57, 58, 65, 66, 67, 68) else
                  'https://jp.finalfantasy.com/news/4940/')
        b = historical(number, title, featured, date, None, source, None, None,
            pool=pool, cost=cost, **mechanics, historical_offer_family='JP-' + (str(ticket) if ticket else str(number)) + '-ORIGINAL-OFFER')
        b['reconstruction']['category_pool_policy'] = 'Eligible category, exact ticket identity, printed coin cost and NV guarantee retained; complete historical eligible lists/weights absent. Explicit equal pool contains only original source-category nativeNV base forms currently present, not NVA or shifts.' if category else 'Unprinted residual eligibility, featured split and weights authored; printed guarantee/free/daily entitlement retained.'

    roto_old_nv = ['346000107', '346000307', '346000407']
    roto_new_nv = ['346000507', '346000607', '346000707', '346000807', '346000907']
    current_ff_nv = sorted(i for i, u in units.items() if i.startswith(('100', '2'))
        and u.get('9fW0TePj') == '7' and u.get('woghJa61') == i
        and u.get('I3SKJ4q0') != '1' and i not in evolved and names.get(i)
        and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', names[i]))
    curated200 = [*roto_old_nv, *roto_new_nv, *current_ff_nv][:200]
    if len(curated200) != 200 or len(set(curated200)) != 200:
        raise ValueError('Printed curated200 size cannot be fulfilled')
    for number, date, count in [(74, '20240219', 3), (75, '20240229', 5)]:
        date_iso = date[:4] + '-' + date[4:6] + '-' + date[6:]
        art = available_art('Roto/original-art/roto-' + date + '-guaranteed-stepup-original.jpg',
                            'Roto/english-art/roto-' + date + '-guaranteed-stepup-english.png')
        special = historical(number, 'Emblem of Roto Collaboration Special ' + str(count) + '-Step Summon',
            roto_new_nv[:3] if count == 3 else roto_new_nv, date_iso, '2024-03-20',
            'https://altema.jp/ffbe/rotonomonsyouhikubekika' + ('2' if count == 3 else '3'),
            *art, type='step', draws=11, lap_limit=1, pool=explicit(curated200), steps=[],
            historical_offer_family='JP-ROTO-' + date + '-SPECIAL-STEPUP')
        for index in range(count):
            pool = explicit(roto_old_nv) if index < 2 else explicit(roto_new_nv[:3] if count == 3 else roto_new_nv)
            if index == 3:
                pool = [{'unit_id': i, 'rarity': 7, 'rate': .10 if i in ['346000907', '346000807'] else .80 / 198}
                        for i in curated200]
            elif index == 4:
                pool = explicit(curated200)
            step = {'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11,
                    'guarantee_slots': [{'count': 1, 'label': 'Original printed guaranteed slot', 'pool': pool}]}
            if index == 4:
                step['bonus_rewards'] = [{'kind': 20, 'id': 106234130, 'count': 1}]
            special['steps'].append(step)
        special['reconstruction'].update({'verified': 'Original captures specify each guaranteed roster, once-only lap, curated200 residual size and combined20% newNV onSTEP4 of the5-step offer. Guide supplies15000cumulative throughSTEP3 and25000throughSTEP5.',
            'authored_fields': 'Individual5000step costs assigned to match the published cumulative totals. Original200residual identities and weights absent; explicit replacement200 preserves the printed size using8RotoNV and192current English FF/NV bases. Guaranteed roster weights uniform where unprinted; STEP4 combined20% split10%each.'})

    ticket_evidence_path = SOURCES / 'Roto/loran-castle-nv-ticket-pool.json'
    if ticket_evidence_path.is_file():
        evidence = json.loads(ticket_evidence_path.read_text(encoding='utf-8'))
        roster = [str(r['unit_id']) for r in evidence['members']]
        if len(roster) != 8:
            raise ValueError('The original event ticket promises exactly8eligible units')
        art = available_art('Roto/original-art/roto-20240229-event-nv-ticket-original.png',
                            'Roto/english-art/roto-20240229-event-nv-ticket-english.png')
        b = historical(76, 'Air Raid! Loran Castle NV Guaranteed Ticket Summon', roster,
            '2024-02-29', '2024-03-24', 'https://jp.finalfantasy.com/news/4940/', *art,
            pool=explicit(roster), cost={'kind': 'item', 'item_id': 106234110, 'amount': 1},
            historical_offer_family='JP-ROTO-20240229-NV-TICKET')
        b['reconstruction'] = {'verified': 'Original banner promises exactly one of8curatedNV. Three depicted identities independently confirmed.',
            'members': evidence['members'], 'authored_fields': 'Five remaining eligible identities are explicit authored choices after the documented bounded original-sprite comparison; equal12.5%weights not recovered historical rates.'}

    existing = set()
    for path in (ROOT / 'source/server').glob('gacha*.json'):
        if path == OUTPUT:
            continue
        doc = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(doc, dict):
            existing.update(str(b['id']) for b in doc.get('banners', []) if b.get('id') and b.get('source') != SOURCE_TAG)
    for b in banners:
        if b['id'] in existing:
            raise ValueError('Historical local offer ID collision: ' + b['id'])
        for pool in [b.get('pool', []), *[slot['pool'] for st in b.get('steps', []) for slot in st.get('guarantee_slots', [])]]:
            if not pool:
                continue
            if abs(sum(r['rate'] for r in pool) - 1) > 1e-9 or len({r['unit_id'] for r in pool}) != len(pool):
                raise ValueError('Invalid explicit historical offer pool')
            for r in pool:
                u = units[r['unit_id']]
                if not b.get('awakened_ticket') and (u['woghJa61'] != r['unit_id'] or u['I3SKJ4q0'] == '1' or r['unit_id'] in evolved):
                    raise ValueError('An awakening/shift form entered an ordinary summon pool')
                if int(u['9fW0TePj']) != r['rarity']:
                    raise ValueError('Awarded rarity differs from native source form')
    apply_art_presentation(banners,art_receipts)
    document = {'_meta': {'classification': 'Evidenced historical JP variants with original translated artwork',
        'source_complete_original_pools': False, 'background_policy': disclaimer,
        'background_scope': 'English-named Final Fantasy and FFBE base forms found in preserved Global pools released by2022-11-22; earlier offers are additionally bounded by their known Global availability date. A replacement residual roster, not original JP eligibility.',
        'background_rosters': {str(k): v for k, v in background.items()},
        'normal_multi_cost_basis': 'Original captures give one special ticket per11draws; contemporary article gives12tickets=60000Lapis, yielding5000Lapis per11draws',
        'unknowns': ['Complete original residual pools and non-NV rarity weights',
            'Unprinted guaranteed5-star-or-NV slot weights', 'Individual Yao/Poron split within the combined10% final guaranteed NV slot'],
        'guaranteed_Yao_Poron_split': 'Equal5%each authored within the original combined10%',
        'native_offer_IDs': 'Unused local identities; original server offer IDs were not preserved'},
        'original_art': list({r['original']: r for r in art_receipts}.values()),
        'banners': sorted(banners, key=lambda b: int(b['id']))}
    text = json.dumps(document, ensure_ascii=False, indent=1) + '\n'
    if '\u2014' in text:
        raise ValueError('Em dash is not allowed')
    OUTPUT.write_text(text, encoding='utf-8')
    return document['banners']


def main():
    banners = build()
    path = ROOT / 'source/server/gacha_named.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    previous = [b for b in doc['banners'] if b.get('source') != SOURCE_TAG]
    doc['banners'] = previous + banners
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    source_document = json.loads(OUTPUT.read_text(encoding='utf-8'))
    art_by_name = {Path(r['english']).name: r for r in source_document['original_art']}
    ledger = []
    for banner in sorted(banners, key=lambda b: (b['release'], int(b['id']))):
        if banner.get('activation_ready') is False:
            continue
        art = art_by_name.get(banner.get('art', {}).get('banner')or banner.get('art',{}).get('detail_banner'), {})
        ledger.append({'current_offer_id': banner['id'],
            'historical_campaign_or_variant': banner.get('historical_offer_family', ''),
            'english_name': banner['name'], 'historical_start': banner['historical_window']['from'],
            'historical_end': banner['historical_window']['to'],
            'date_precision': banner.get('historical_date_precision', 'day'),
            'original_server_id': '', 'offer_type': banner['type'], 'step_count': len(banner.get('steps', [])),
            'original_art': art.get('original', ''), 'translated_original_art': art.get('english', ''),
            'art_status': banner.get('art_presentation',{}).get('presentation')or('Original source translated' if art else 'Original visual presentation unconfirmed; native text entry retained'),
            'current_native_rules': 'source/server/gacha_named.json',
            'complete_original_pool_recovered': False,
            'documented_reconstruction': json.dumps(banner.get('reconstruction') or {'fields': source_document['_meta']['unknowns']}, ensure_ascii=False),
            'source_urls': ';'.join(banner['sources']), 'phone_verified': False})
    with (SOURCES / 'original-summon-chronological-ledger.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ledger[0])); writer.writeheader(); writer.writerows(ledger)

    # Preserve the original inspection columns. Current acquisition is a separate
    # implementation observation with concrete native/reward identities.
    inventory = SOURCES.parent / 'unit-completion-status.csv'
    with inventory.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream); fields = list(reader.fieldnames); unit_rows = list(reader)
    extra_fields = ['current_acquisition_routes', 'current_primary_acquisition_route',
                    'current_acquisition_source', 'current_acquisition_status', 'current_remaining']
    fields += [field for field in extra_fields if field not in fields]
    mapping = json.loads((SOURCES / 'native-unit-id-map.json').read_text(encoding='utf-8'))['mappings'].get('F_UNIT_MST', {})
    for row in unit_rows:
        target = str(mapping.get(row['unit_version_id'], row['unit_version_id']))
        routes = []
        primary = []
        for banner in banners:
            pool_ids = {str(r['unit_id']) for r in banner.get('pool', [])}
            pool_ids.update(str(r['id']) for r in banner.get('reward_pool', []) if r['kind'] == 10)
            pool_ids.update(str(e['reward']['id']) for box in banner.get('boxes', []) for e in box if e['reward']['kind'] == 10)
            if target in pool_ids:
                routes.append('summon:' + banner['id'])
                if target in banner.get('preview_units', []) or any(str(r.get('id')) == target and r['kind'] == 10 for r in banner.get('reward_pool', [])):
                    primary.append('summon:' + banner['id'])
        if row['unit_version_id'] == '303000103':
            routes.append('mission_first_clear:7020101'); primary.append('mission_first_clear:7020101')
        if row['unit_version_id'] == '313000305':
            routes.append('login_mail:932017072401'); primary.append('login_mail:932017072401')
        if row['unit_version_id'] == '346000207':
            routes.append('challenge:621101010'); primary.append('challenge:621101010')
        if not routes:
            raise ValueError('Crossover version has no current acquisition route: ' + row['unit_version_id'])
        row.update({'current_acquisition_routes': ';'.join(routes),
            'current_primary_acquisition_route': ';'.join(primary or routes[:1]),
            'current_acquisition_source': 'Sources/original-summon-chronological-ledger.csv;Sources/Event rewards/reward-runtime-provenance.json',
            'current_acquisition_status': 'Source implementation complete; original role/campaign evidenced; missing original pool terms explicitly reconstructed',
            'current_remaining': 'Approved APK rebuild and actual phone acquisition/persistence playtest; exact historical residual pools and dedicated missing summon artwork remain source gaps.'})
    with inventory.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(unit_rows)
    write_presentation_completion(banners)
    print(json.dumps({'existing_named_rows_preserved': len(previous), 'historical_variants': len(banners),
        'original_source_artworks': len(json.loads(OUTPUT.read_text(encoding='utf-8'))['original_art']),
        'new_free_catchup_offers': 0}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--art-presentation-only',action='store_true',
                        help='Apply reviewed artwork decisions without rebuilding summon pools or rewards.')
    args=parser.parse_args()
    apply_presentation_only()if args.art_presentation_only else main()
