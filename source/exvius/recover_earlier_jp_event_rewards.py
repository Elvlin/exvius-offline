"""Recover earlier JP event reward contracts and scoped English labels.

Original native rows stay separate from runtime projections. Existing native
versions, unrelated records and distinct Global identities are preserved.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

from recover_jp_unit_content import Inputs, json_bytes, community, numbers, rewrite_rewards

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / 'Japan content/Earlier JP crossovers/Sources'
OUT = HOME / 'Event rewards'
sys.path.insert(0, str(ROOT / 'source/server'))

NATIVE_REWARD_GROUPS = {'4082': '31001', '771': '40011', '6210': '40118', '6410': '40161'}
KEYS = {'F_ITEM_MST': 'tL6G9egd', 'F_EQUIP_ITEM_MST': 'J1YX9kmM',
        'F_MATERIA_MST': 'H5jBL0Vf', 'F_UNIT_MST': '3HriTp6B',
        'F_VISION_CARD_MST': '5giCMUd2', 'F_RECIPE_BOOK_MST': 'staFu8U1',
        'F_RECIPE_MST': 'MpNE6gB5', 'F_ABILITY_MST': 'Ga5V42LZ',
        'F_MAGIC_MST': 'QV1HE7Wq', 'F_MEDAL_EXCHANGE_MST': 'S21FT3L8',
        'F_TOWN_STORE_MST': 'Z20mNDvL'}
KIND_TABLE = {'10': 'F_UNIT_MST', '20': 'F_ITEM_MST', '21': 'F_EQUIP_ITEM_MST',
              '22': 'F_MATERIA_MST', '27': 'F_VISION_CARD_MST', '60': 'F_RECIPE_BOOK_MST'}
DAILY_ROSTERS = {
    '4484': {'1000360800': '348000107', '1000360900': '349000107', '1000361000': '309000507'},
    '6413': {'1000361100': '350000107', '1000361200': '351000107'},
    '6214': {'999097700': '346000107', '999098700': '346000307', '999099700': '346000407'},
    '6216': {'1000361300': '346000507', '1000361400': '346000607', '1000361500': '346000707'},
    '4502': {'1000370700': '346000907', '1000380700': '346000807'},
}

REWARD_LABELS = {
    '竜鱗の鎧(ロマサガ3)': 'Dragon Scale Armor (Romancing SaGa 3)',
    '火神防御輪(ロマサガ)': "Fire God's Guard Ring (Romancing SaGa)",
    '氷のメガリスを制した力': 'Power That Conquered the Ice Megalith',
    '聖なる剣撃': 'Sacred Sword Strike',
    '翠鳥の剣': 'Kingfisher Sword',
    '雷霆の鎌': 'Thunderclap Scythe',
    '悲恋の記録': 'Record of Tragic Love',
    '冥晶刀フェデク': 'Nethercrystal Blade Fedelk',
    'オウロウガ・アロウ': 'Orouga Arrow',
    'アシラアーム': 'Arzuros Vambraces', 'ラギアアーム': 'Lagiacrus Vambraces',
    'バンギスアーム': 'Vangis Vambraces', 'アシラヘルム': 'Arzuros Helm',
    'ラギアヘルム': 'Lagiacrus Helm', 'バンギスヘルム': 'Vangis Helm',
    'アシラメイル': 'Arzuros Mail', 'バンギスメイル': 'Vangis Mail',
    '星辰の鎧': 'Astral Armor', '機動装甲': 'Mobile Armor',
    'SINoALICEグッズプレゼント企画-前編-応募券': 'SINoALICE Merchandise Giveaway Entry (Part 1)',
    'SINoALICEグッズプレゼント企画-後編-応募券': 'SINoALICE Merchandise Giveaway Entry (Part 2)',
    'SP召喚チケット2021/9': 'SP Summon Ticket (September 2021)',
    '立ち塞がる獣王 専用マスタークラウン交換チケット': 'The Beast King Blocks the Way Master Crown Exchange Ticket',
    '空襲！！ローラン城 NVの欠片交換チケット': 'Air Raid! Loran Castle NV Fragment Exchange Ticket',
    'ネフ・ガルムドの感応結晶': 'Nef-Garmat Resonance Crystal',
    '四魔貴族レイドコイン': 'Four Sinistrals Raid Coin',
    '「決戦ノ斉歌」の討伐証': 'Chorus of the Final Battle Subjugation Certificate',
    'デビルテンタクラーレイドコイン': 'Devil Tentacler Raid Coin',
    '昇青石【火神防御輪(ロマサガ)】': "Azure Upgrade Stone [Fire God's Guard Ring (Romancing SaGa)]",
    '異界のブレイブ': 'Otherworld Brave',
    'ライブラリ': 'Library',
}
LABEL_TABLES = {
    'F_EQUIP_ITEM_MST': ('J1YX9kmM', 'F_TEXT_ITEM_EQUIP_NAME', 'MST_EQUIP_ITEM_NAME_'),
    'F_MATERIA_MST': ('H5jBL0Vf', 'F_TEXT_MATERIA_NAME', 'MST_MATERIA_NAME_'),
    'F_ABILITY_MST': ('Ga5V42LZ', 'F_TEXT_ABILITY_NAME', 'MST_ABILITY_NAME_'),
    'F_RECIPE_BOOK_MST': ('staFu8U1', 'F_TEXT_RECIPE_BOOK_NAME', 'MST_RECIPE_BOOK_NAME_'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def contract_table(inputs, table, key, patches, operation='merge_fields'):
    inputs.current(table)
    receipt = inputs.receipts['current:' + table]
    native = receipt['active_native_source']
    if not native:
        raise ValueError('No proven effective native baseline: ' + table)
    authoring = ROOT / 'data/mst_decoded' / (table + '.ndjson')
    raw = authoring.read_bytes() if authoring.is_file() else b''
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    filename = (native.get('member') or native['path']).rsplit('/', 1)[-1]
    return {'table': table, 'identity_fields': [key], 'operation': operation,
            'active_native_path': 'mst/' + filename, 'active_native_source': native,
            'active_native_sha256': native['sha256'],
            'expected_native_decoded_canonical_sha256': receipt['decoded_canonical_sha256'],
            'decoded_baseline_sha256': sha(raw),
            'expected_decoded_canonical_sha256': sha(json_bytes(records)),
            'preserve_unselected_rows': True, 'rows': patches}


def translate_reward_name(value):
    for japanese, english in REWARD_LABELS.items():
        if value == japanese:
            return english
        if value.startswith(japanese + '+') and value[len(japanese) + 1:].isdigit():
            return english + value[len(japanese):]
    return None


def stage_labels(inputs):
    labels, tables, provenance, missing = defaultdict(dict), [], [], []
    for table, (key, text_table, prefix) in LABEL_TABLES.items():
        current = {r[key]: r for r in inputs.current(table)}
        patches = []
        for row in inputs.original(table):
            name = translate_reward_name(row.get('G4L0YIB2', ''))
            if name is None:
                continue
            iid = row[key]
            labels[text_table][prefix + iid] = name
            provenance.append({'table': table, 'source_id': iid,
                               'source_jp': row['G4L0YIB2'], 'english': name,
                               'text_table': text_table, 'text_key': prefix + iid,
                               'source': inputs.receipts[table]})
            old = current.get(iid)
            if old is None:
                missing.append({'table': table, 'source_id': iid, 'name_jp': row['G4L0YIB2']})
                continue
            # This narrow label pass has only seven known exact JP identities.
            # A different Japanese name is a real collision, never localization.
            if old.get('G4L0YIB2') not in (row['G4L0YIB2'], name):
                raise ValueError('Unverified reward identity: ' + table + ':' + iid)
            if old.get('G4L0YIB2') != name:
                patches.append({key: iid, 'G4L0YIB2': name})
        if patches:
            tables.append(contract_table(inputs, table, key, patches))
    write_json(HOME / 'event-reward-labels-en.json', dict(labels))
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY',
                'scope': 'Seven source-verified event reward name families and their native upgrades',
                'tables': tables, 'counts': {t['table']: len(t['rows']) for t in tables},
                'preservation': 'Name fields only. Exact existing native JP identities verified. No gameplay values changed.',
                'missing_name_master_rows': missing}
    write_json(HOME / 'native-event-reward-labels-import.json', contract)
    write_json(HOME / 'event-reward-labels-provenance.json', {'schema': 1, 'bindings': provenance,
                'new_translations': True, 'missing_master_rows': missing})
    return {'labels': sum(map(len, labels.values())), 'tables': contract['counts'],
            'missing_master_rows': missing}


def norm(value):
    return unicodedata.normalize('NFKC', value).replace(' ', '').replace('\u3000', '')


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def reward_parts(text):
    """Read typed reward identities without treating quantities as references."""
    for clause in str(text or '').split(','):
        pieces = clause.strip().split(':')
        if len(pieces) >= 3 and all(v.isdigit() for v in pieces[:3]):
            yield pieces[0], pieces[1], int(pieces[2])


def published_reward(text, originals):
    """Bind a published display item to its exact original JP resource identity."""
    value = unicodedata.normalize('NFKC', text).strip()
    count = 1
    match = re.search(r'[×x](\d+)$', value)
    if match:
        count = int(match[1]); value = value[:match.start()]
    lapis = re.fullmatch(r'([\d,]+)ラピス', value)
    if lapis:
        return '50:1:' + lapis[1].replace(',', '') + ':100'
    explicit = {
        'レア召喚チケット': ('23', '50'), '体力回復薬50': ('23', '110'),
        'ギルガメタワー': ('20', '400000040'), 'メタルミニテンキング': ('10', '900020401'),
        'スパトラモグ交換チケット': ('20', '106211340'),
        '空襲!!ローラン城イベントNV欠片交換チケット': ('20', '106234120'),
        'ハンタージェイク': ('10', '100000713'), 'ハンターサクラ': ('10', '100000614'),
        'ハンターラスウェル': ('10', '100000215'), '半神アデル': ('10', '303000204'),
    }
    if value in explicit:
        kind, iid = explicit[value]
        return f'{kind}:{iid}:{count}:100'
    moogle = re.fullmatch(r'トラストモーグリ\(?☆([145])\)?', value)
    if moogle:
        return f'10:90400010{moogle[1]}:{count}:100'
    if value == 'スパトラモグ(ALL50%)':
        return '10:906000105:1:100:1:500:0:0:1100000050'
    table = None
    if value.endswith('のレシピ'):
        value = value[:-len('のレシピ')]; table = 'F_RECIPE_BOOK_MST'
    candidates = []
    for kind, target in KIND_TABLE.items():
        if table and target != table:
            continue
        if not table and kind not in ('20', '21', '22', '10'):
            continue
        matches = [r for r in originals[target].values() if norm(r.get('G4L0YIB2', '')) == norm(value)]
        if target == 'F_UNIT_MST' and len(matches) > 1:
            matches = [r for r in matches if r['3HriTp6B'] == r.get('woghJa61')]
        candidates.extend((kind, r[KEYS[target]]) for r in matches)
    if len(candidates) != 1:
        raise ValueError(f'Published reward identity ambiguous: {text}: {candidates}')
    kind, iid = candidates[0]
    return f'{kind}:{iid}:{count}:100'


def recover_reward_sources(inputs):
    """Close actual mission, objective, milestone, recipe and exchange references."""
    originals = {t: {r[key]: r for r in inputs.original(t)} for t, key in KEYS.items()
                 if t not in ('F_MAGIC_MST',)}
    originals['F_MAGIC_MST'] = {r['QV1HE7Wq']: r for r in inputs.original('F_MAGIC_MST')}
    missions = read_rows(HOME / 'Event graph/F_MISSION_MST.ndjson')
    challenges = read_rows(HOME / 'Event graph/F_CHALLENGE_MST.ndjson')
    selected = {t: set() for t in originals}
    missing, published_bindings = [], []
    raw_rewards = [r.get('1x4bG2J8', '') for r in missions] + [r.get('dX6cor8j', '') for r in challenges]
    published = json.loads((OUT / 'published-event-rewards.json').read_text(encoding='utf8'))
    groups = set(NATIVE_REWARD_GROUPS.values())
    native_milestones = [r for r in inputs.original('F_SEASON_EVENT_REWARD_MST') if r['pvS5A4kE'] in groups]
    raw_rewards.extend(r['dX6cor8j'] for r in native_milestones)
    for area, info in published['events'].items():
        for row in info.get('milestones', []):
            try:
                reward = published_reward(row['reward_jp'], originals)
                published_bindings.append({'area': area, 'points': row['points'],
                    'reward_jp': row['reward_jp'], 'native_reward': reward, 'source_url': info['source_url'],
                    'binding_status': 'Published quantity and original native named resource; original server award tuple not recovered'})
                raw_rewards.append(reward)
            except ValueError as exc:
                missing.append(str(exc))
    # Existing SIN Library chest identities are original, not milestone copies.
    for iid in ('302011200', '303007300', '310006600'):
        selected['F_EQUIP_ITEM_MST'].add(iid)
    currency_ids = {'106301700', '106301710', '106302500', '106303700', '106314800',
                    '106318300', '106323500', '106323600', '106323900', '106230850',
                    '106233700', '106234100', '106234110', '106234120'}
    selected['F_ITEM_MST'].update(currency_ids)
    # Source daily cards identify these exact versions. The final JP unit
    # dictionary independently binds their original awakening fragment items.
    documents = community()
    daily = {}
    dictionaries = json.loads((HOME.parent / 'stage-gap-evidence.json').read_text(encoding='utf8'))['missing_body_dictionary_candidates']
    for area, roster in DAILY_ROSTERS.items():
        bindings = {}
        for enemy, unit in roster.items():
            native_unit = originals['F_UNIT_MST'][unit]
            dictionary_name = dictionaries[enemy]['dictionary_row']['G4L0YIB2']
            if norm(dictionary_name) != norm(native_unit['G4L0YIB2']):
                raise ValueError('Daily character identity mismatch: ' + enemy)
            versions = [v for v in documents['units'].values() if unit in v.get('entries', {})]
            fragments = {str(i) for v in versions for e in v['entries'].values()
                         for level in e.get('nv_upgrade') or [] for i in level.get('materials') or {}
                         if str(i).startswith('250')}
            if len(fragments) != 1:
                raise ValueError('Daily fragment identity ambiguous: ' + unit)
            fragment = fragments.pop(); selected['F_ITEM_MST'].add(fragment)
            bindings[enemy] = {'kind': 20, 'id': int(fragment), 'count': 10,
                               'source_unit_id': unit, 'source_name_jp': dictionary_name}
        for mission in missions:
            if mission['uv60hgDW'] == area:
                daily[mission['qo3PECw6']] = {'area': area, 'once_per_source_dated_mission': True,
                    'chosen_enemy_rewards': bindings, 'source': 'Original daily card roster plus native enemy dictionary and JP unit awakening fragment resource'}
    # Iterative recipe graph retains exact quantities and source results.
    queue = list(raw_rewards)
    while queue:
        for kind, iid, _count in reward_parts(queue.pop()):
            table = KIND_TABLE.get(kind)
            if not table or iid in selected[table]:
                continue
            if iid not in originals[table]:
                missing.append(f'Missing original reward master {table}:{iid}'); continue
            selected[table].add(iid)
        changed = False
        for iid in list(selected['F_RECIPE_BOOK_MST']):
            for rid in originals['F_RECIPE_BOOK_MST'][iid]['8Qt4Ccew'].split(','):
                if rid and rid not in selected['F_RECIPE_MST']:
                    if rid not in originals['F_RECIPE_MST']:
                        missing.append('Missing original recipe:' + rid); continue
                    selected['F_RECIPE_MST'].add(rid)
                    row = originals['F_RECIPE_MST'][rid]
                    queue += [row['HS7V6Ww1'], f"{row['gak9Gb3N']}:{row['6uIYE15X']}:{row['Qy5EvcK1']}"]
                    changed = True
        if not changed and not queue:
            break
    # Original medal products retain exact costs and lifetime limits.
    for iid, row in originals['F_MEDAL_EXCHANGE_MST'].items():
        if row['ak2dhKm3'] in currency_ids:
            selected['F_MEDAL_EXCHANGE_MST'].add(iid)
            for kind, target, _count in reward_parts(row['7iJpH5zZ']):
                table = KIND_TABLE.get(kind)
                if table and target in originals[table]: selected[table].add(target)
    for table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST'):
        for iid in selected[table]:
            row = originals[table][iid]
            for field in ('GiBvPK84', 't42Xb3jV', '5Sx0haBw', '82PrpZU6'):
                for sid in numbers(row.get(field, '')):
                    if sid in originals['F_ABILITY_MST']: selected['F_ABILITY_MST'].add(sid)
                    if sid in originals['F_MAGIC_MST']: selected['F_MAGIC_MST'].add(sid)
    source_tables = {t: {'key': KEYS[t], 'rows': [originals[t][i] for i in sorted(ids, key=int)]}
                     for t, ids in selected.items() if ids}
    source_tables['F_SEASON_EVENT_REWARD_MST'] = {'key': 'rYGk3Q7t', 'rows': native_milestones}
    result = {'schema': 1, 'status': 'SOURCE_RECOVERED_IMPORT_PENDING',
              'tables': source_tables, 'source_inputs': inputs.receipts,
              'published_milestone_bindings': published_bindings, 'daily_fragment_rewards': daily,
              'missing': sorted(set(missing)),
              'counts': {t: len(v['rows']) for t, v in source_tables.items()}}
    write_json(OUT / 'original-event-reward-content.json', result)
    return result


def prepare_native_import(inputs, source):
    """Add missing native records; preserve all existing Global records."""
    mappings = copy.deepcopy(json.loads((HOME / 'native-unit-id-map.json').read_text(encoding='utf8'))['mappings'])
    mappings.setdefault('F_VISION_CARD_MST', {})['336000101'] = '873100001'
    item_map = mappings.setdefault('F_ITEM_MST', {})
    current_items = {r['tL6G9egd']: r for r in inputs.current('F_ITEM_MST')}
    source_items = {r['tL6G9egd']: r for r in source['tables']['F_ITEM_MST']['rows']}
    new_item = '872100001'
    old = current_items.get('260000100')
    if old and old.get('G4L0YIB2') != source_items['260000100']['G4L0YIB2']:
        occupied = set(current_items) | {r['tL6G9egd'] for r in inputs.original('F_ITEM_MST')}
        if new_item in occupied and current_items.get(new_item, {}).get('G4L0YIB2') != 'Otherworld Brave':
            raise ValueError('Reserved event item ID is occupied: ' + new_item)
        item_map['260000100'] = new_item
    # Existing source recipe identities are reused only when their actual
    # result/material/gil/time contract agrees after typed JP remapping.
    recipe_map = mappings.setdefault('F_RECIPE_MST', {})
    book_map = mappings.setdefault('F_RECIPE_BOOK_MST', {})
    current_recipes = {r['MpNE6gB5']: r for r in inputs.current('F_RECIPE_MST')}
    current_books = {r['staFu8U1']: r for r in inputs.current('F_RECIPE_BOOK_MST')}
    recipe_fields = ('gak9Gb3N', '6uIYE15X', 'Qy5EvcK1', 'M5VLKe2F', 'HS7V6Ww1', '7UR4J2SE', 'MHNbK26X')
    number = 1
    for original in source['tables']['F_RECIPE_MST']['rows']:
        iid = original['MpNE6gB5']; row = rewrite_event_row('F_RECIPE_MST', original, mappings)
        previous = current_recipes.get(iid)
        if previous and any(previous.get(f, '') != row.get(f, '') for f in recipe_fields):
            rid, bid = str(875100000 + number), str(875200000 + number)
            if rid in current_recipes or bid in current_books:
                raise ValueError('Reserved event recipe/book ID is occupied')
            recipe_map[iid] = rid; book_map[iid] = bid; number += 1
    patches, comparison = [], []
    tables = source['tables']
    max_index = max(int(r.get('QLfe23bu') or 0) for r in list(current_items.values()) + inputs.original('F_ITEM_MST'))
    english_path = OUT / 'event-reward-english-names.json'
    english = json.loads(english_path.read_text('utf8')) if english_path.is_file() else {}
    occupied_book_indices = {r['gJf3zp8a'] for r in current_books.values() if r.get('gJf3zp8a')}
    next_book_index = max(map(int, occupied_book_indices | {r['gJf3zp8a'] for r in inputs.original('F_RECIPE_BOOK_MST') if r.get('gJf3zp8a')})) + 1
    for table in ('F_ITEM_MST', 'F_RECIPE_BOOK_MST', 'F_RECIPE_MST', 'F_MEDAL_EXCHANGE_MST'):
        key = tables[table]['key']
        current = {r[key]: r for r in inputs.current(table)}
        additions = []
        for original in tables[table]['rows']:
            row = rewrite_event_row(table, original, mappings)
            iid = row[key]
            if iid in current:
                comparison.append({'table': table, 'source_id': original[key], 'target_id': iid, 'action': 'preserved_existing'})
                continue
            if table == 'F_ITEM_MST' and iid == new_item:
                row['G4L0YIB2'] = 'Otherworld Brave'; max_index += 1; row['QLfe23bu'] = str(max_index)
            if table == 'F_RECIPE_BOOK_MST':
                name = english.get('60:' + iid) or translate_reward_name(original.get('G4L0YIB2', ''))
                if not name: raise ValueError('Recipe book has no prepared English name:' + iid)
                row['G4L0YIB2'] = name
                if row['gJf3zp8a'] in occupied_book_indices:
                    row['gJf3zp8a'] = str(next_book_index); next_book_index += 1
                occupied_book_indices.add(row['gJf3zp8a'])
            if table == 'F_RECIPE_MST':
                hints = {'ImperialSaGa': 'Imperial SaGa: The Seven Heroes Attack!',
                         'インペリアル': 'Imperial SaGa: The Four Sinistrals Attack!',
                         'モンスターハンター': 'Monster Hunter Explore: Assault! Nef-Garmat!',
                         'ブレイブリー': 'Bravely: Luxendarc, Land of Light and Shadow',
                         'ドラゴンクエスト': 'Dragon Quest: Emblem of Roto'}
                raw_hint = row.get('VC9F3eJn', '')
                title = next((v for k, v in hints.items() if raw_hint.startswith(k)), 'Limited-time event')
                row['VC9F3eJn'] = title + '<br>Event reward'
            if table == 'F_MEDAL_EXCHANGE_MST':
                descriptions = {
                    '【★6覚醒素材】ユニット★6覚醒時に必要な素材の一つ': 'One of the materials required to awaken a unit to 6 stars.',
                    '【ユニット強化素材専用ユニット】合成すると絶大な量の経験値を得られるユニット（Lv.MAX）': 'Enhancement material that grants a vast amount of experience when fused (maximum level).',
                    '限界を超える力を与えるポット': 'A pot that grants power beyond the limit.',
                    '【ユニット強化素材専用ユニット】合成するとトラストが50%上がるユニット': 'Enhancement material that raises trust by 50% when fused.',
                    '【売却専用ユニット】売却すると超大量のギルを得られるユニット': 'A unit for selling that yields a huge amount of gil.',
                    '【アビリティ覚醒素材】アビリティ覚醒時に必要な素材の一つ': 'One of the materials required for ability awakening.',
                    '0': ''}
                row['6uvHX2JG'] = descriptions[original['6uvHX2JG']]
                if original['S21FT3L8'] == '79504':
                    fields = row['7iJpH5zZ'].split(':')
                    if fields != ['10', '904000105', '1', '100', '1', '0', '100000008']:
                        raise ValueError('SIN50%Trust Moogle source changed')
                    fields[5] = '500'; row['7iJpH5zZ'] = ':'.join(fields)
            additions.append(row)
            comparison.append({'table': table, 'source_id': original[key], 'target_id': iid, 'action': 'append_exact_typed_source'})
        if additions:
            entry = contract_table(inputs, table, key, additions, 'replace')
            entry['append_only'] = True
            entry['verified_absent_native_identities'] = [r[key] for r in additions]
            patches.append(entry)
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY' if not source['missing'] else 'BLOCKED_MISSING_SOURCE',
                'scope': 'Earlier JP crossover event crafting, exact exchanges and one colliding bravery material',
                'tables': patches, 'counts': {r['table']: len(r['rows']) for r in patches},
                'preservation': 'Append-only native identities. Existing Global recipes/items/products and all45English reward names preserved.',
                'missing': source['missing']}
    # The baseline already has this JP-labelled card. Its current artwork
    # differs, so the explicit approved card fork preserves existing ownership.
    card_table = 'F_VISION_CARD_MST'
    card = dict(next(r for r in inputs.original(card_table) if r['5giCMUd2'] == '336000101'))
    current_cards = inputs.current(card_table)
    if any(r['5giCMUd2'] == '873100001' for r in current_cards):
        raise ValueError('Library card target already exists; compare before rerunning import')
    card.update({'5giCMUd2': '873100001', 'efb6J8AZ': '873100001', 'G4L0YIB2': 'Library JP', 'cnLF6Cz1': 'Library JP',
                 'QLfe23bu': str(max(int(r.get('QLfe23bu') or 0) for r in current_cards + inputs.original(card_table)) + 1)})
    patches.append(contract_table(inputs, card_table, '5giCMUd2', [card], 'replace'))
    biography = 'The characters spend a moment in the Library, a mysterious space where countless stories float. They sometimes fight together to revive their authors, but ultimately they are destined to kill one another.'
    explain = dict(next(r for r in inputs.current('F_VISION_CARD_EXPLAIN_MST') if r['5giCMUd2'] == '336000101'))
    explain.update({'5giCMUd2': '873100001', 'T7aEx3Mj': biography, 'VC9F3eJn': biography, 'fYhnz5N9': biography,
                    'J5QKLzW7': 'The vision card has gained experience!', 'BGWpF0i2': 'Library JP',
                    'ShTbN3q9': 'Library JP', '1ux5sP4L': 'Apocrypha and the World'})
    patches.append(contract_table(inputs, 'F_VISION_CARD_EXPLAIN_MST', '5giCMUd2', [explain], 'replace'))
    for table, identity in [('F_VISION_CARD_ABILITY_ACT_COND_MST', ['5giCMUd2', '9qQg2zjH']),
                            ('F_VISION_CARD_LV_ACQUIRE_MST', ['5giCMUd2', '7wV3QZ80'])]:
        rows = []
        for original in inputs.original(table):
            if original['5giCMUd2'] != '336000101': continue
            row = dict(original); row['5giCMUd2'] = '873100001'
            if table == 'F_VISION_CARD_ABILITY_ACT_COND_MST': row['6uvHX2JG'] = 'Requirement: SINoALICE Unit'
            rows.append(row)
        entry = contract_table(inputs, table, '5giCMUd2', rows, 'replace'); entry['identity_fields'] = identity; patches.append(entry)
    # These3 passive abilities already have the exact JP gameplay processes.
    ability_labels = {'243012': '[VC] Countless Stories', '243013': '[VC] For Their Authors', '243014': '[VC] Fated to Kill One Another'}
    patches.append(contract_table(inputs, 'F_ABILITY_MST', 'Ga5V42LZ', [{'Ga5V42LZ': i, 'G4L0YIB2': v} for i, v in ability_labels.items()]))
    patches.append(contract_table(inputs, 'F_ABILITY_EXPLAIN_MST', 'Ga5V42LZ', [{'Ga5V42LZ': i, 'T7aEx3Mj': v} for i, v in
        {'243012': 'Increase ATK by 50%', '243013': 'Increase LB damage by 25%', '243014': 'Increase static ATK by 500'}.items()]))
    contract['counts'] = {r['table']: len(r['rows']) for r in patches}
    mapping = {'schema': 1, 'status': 'RESERVED_AND_VALIDATED_NATIVE_EVENT_MAPPING', 'mappings': mappings,
               'new_event_mappings': {t: m for t, m in mappings.items() if t in ('F_RECIPE_MST', 'F_RECIPE_BOOK_MST')},
               'new_item_collision': {'source': '260000100', 'target': item_map.get('260000100', '260000100'),
                    'source_name': source_items['260000100']['G4L0YIB2'], 'preserved_global_name': old.get('G4L0YIB2') if old else None},
               'comparison': comparison}
    write_json(OUT / 'native-event-reward-import.json', contract)
    write_json(OUT / 'native-event-reward-map.json', mapping)
    return contract, mapping


def rewrite_event_row(table, original, mappings):
    row = dict(original)
    key = KEYS.get(table)
    if key: row[key] = mappings.get(table, {}).get(row[key], row[key])
    if table == 'F_RECIPE_BOOK_MST':
        row['8Qt4Ccew'] = ','.join(mappings.get('F_RECIPE_MST', {}).get(i, i) for i in row['8Qt4Ccew'].split(','))
    elif table == 'F_RECIPE_MST':
        row['HS7V6Ww1'] = rewrite_rewards(row['HS7V6Ww1'], mappings)
        target = KIND_TABLE.get(row['gak9Gb3N'])
        row['6uIYE15X'] = mappings.get(target, {}).get(row['6uIYE15X'], row['6uIYE15X'])
    elif table == 'F_MEDAL_EXCHANGE_MST':
        row['ak2dhKm3'] = mappings.get('F_ITEM_MST', {}).get(row['ak2dhKm3'], row['ak2dhKm3'])
        row['7iJpH5zZ'] = rewrite_rewards(row['7iJpH5zZ'], mappings)
    return row


def stage_runtime(inputs, source):
    """Project recovered milestones, stock and dated character rewards."""
    import os
    os.environ.setdefault('FFBE_DATA', str(ROOT / 'data'))
    from exvius_rewards import parse
    def source_rewards(raw):
        rewards = parse(raw)
        for entry, reward in zip(filter(None, raw.split(',')), rewards):
            fields = entry.split(':')
            if reward['kind'] != 10 or not str(reward['id']).startswith('904'): continue
            if len(fields) < 7:
                amount = {904000101: 10, 904000104: 50, 904000105: 100}.get(reward['id'])
            elif int(fields[5]): amount = int(fields[5])
            else: amount = {'100000005': 10, '100000001': 50, '100000002': 100, '100000008': 500}.get(fields[-1])
            if amount is None: raise ValueError('Unknown original generic Trust Moogle option:' + entry)
            reward['affinity_points'] = [str(amount), '']; reward['affinity_info'] = ['', '']
        return rewards
    primary_plan = json.loads((HOME / 'native-unit-id-map.json').read_text('utf8'))
    mappings = primary_plan['mappings']
    mappings.setdefault('F_VISION_CARD_MST', {})['336000101'] = '873100001'
    kinds = {10: ('UNITS', 'MST_UNIT_NAME_'), 20: ('ITEM', 'MST_ITEM_NAME_'),
             21: ('ITEM_EQUIP', 'MST_EQUIP_ITEM_NAME_'), 22: ('MATERIA', 'MST_MATERIA_NAME_'),
             23: ('IMPORTANT_ITEM', 'MST_IMPORTANT_ITEM_NAME_'),
             27: ('VISION_CARD', 'MST_VISION_CARD_NAME_'), 60: ('RECIPE_BOOK', 'MST_RECIPE_BOOK_NAME_')}
    texts = {kind: inputs.text('F_TEXT_' + table + '_NAME') for kind, (table, _) in kinds.items()}
    extra, english_names = defaultdict(dict), {}
    for kind, table in KIND_TABLE.items():
        if table == 'F_RECIPE_BOOK_MST': continue
        for row in source['tables'].get(table, {}).get('rows', []):
            iid = mappings.get(table, {}).get(row[KEYS[table]], row[KEYS[table]])
            name = translate_reward_name(row['G4L0YIB2'])
            if table == 'F_VISION_CARD_MST' and row[KEYS[table]] == '336000101': name = 'Library JP'
            prefix = kinds[int(kind)][1]
            current = texts[int(kind)].get(prefix + iid)
            if (table == 'F_ITEM_MST' and (not current or current in ('collab', '<blank>'))
                    and iid in primary_plan.get('shared_common_item_ids', [])):
                retained = primary_plan.get('retained_common_item_alias_records', {}).get(iid)
                if retained:
                    current = texts[int(kind)].get(prefix + retained)
                    if current: extra['F_TEXT_ITEM_NAME'][prefix + iid] = current
            if table == 'F_ITEM_MST' and iid in ('360000800', '360000900') and current:
                extra['F_TEXT_ITEM_NAME'][prefix + iid] = current
            if not current or current in ('collab', '<blank>'):
                if not name: raise ValueError('Missing actual English reward name: ' + table + ':' + iid)
                extra['F_TEXT_' + kinds[int(kind)][0] + '_NAME'][prefix + iid] = name
                current = name
            elif name == current:
                # Keep the accepted translation reproducible after apply.
                extra['F_TEXT_' + kinds[int(kind)][0] + '_NAME'][prefix + iid] = name
            english_names[int(kind), iid] = current
    recipes = {r['MpNE6gB5']: r for r in source['tables']['F_RECIPE_MST']['rows']}
    for book in source['tables']['F_RECIPE_BOOK_MST']['rows']:
        row = recipes[book['8Qt4Ccew'].split(',')[0]]
        target_table = KIND_TABLE[row['gak9Gb3N']]
        target = mappings.get(target_table, {}).get(row['6uIYE15X'], row['6uIYE15X'])
        name = translate_reward_name(book['G4L0YIB2']) or english_names[int(row['gak9Gb3N']), target]
        suffix = re.search(r'\+\d+$', book['G4L0YIB2'])
        if suffix and not name.endswith(suffix[0]): name += suffix[0]
        iid = mappings.get('F_RECIPE_BOOK_MST', {}).get(book['staFu8U1'], book['staFu8U1'])
        extra['F_TEXT_RECIPE_BOOK_NAME']['MST_RECIPE_BOOK_NAME_' + iid] = name
        english_names[60, iid] = name
    biography = 'The characters spend a moment in the Library, a mysterious space where countless stories float. They sometimes fight together to revive their authors, but ultimately they are destined to kill one another.'
    for table, prefix, value in [
            ('EXPLAIN_SHORT', 'EXPLAIN_SHORT', biography), ('EXPLAIN_LONG', 'EXPLAIN_LONG', biography),
            ('DICTIONARY', 'DICTIONARY', biography), ('MIX', 'MIX', 'The vision card has gained experience!'),
            ('SUMMON', 'SUMMON', 'Library JP'), ('SHOP', 'SHOP', 'Library JP'),
            ('BGM', 'BGM_NAME', 'Apocrypha and the World'), ('ABILITY_ACT_COND', 'ABILITY_ACT_COND', 'Requirement: SINoALICE Unit')]:
        extra['F_TEXT_VISION_CARD_' + table]['MST_VISION_CARD_' + prefix + '_873100001'] = value
    for iid, name, description in [('243012', '[VC] Countless Stories', 'Increase ATK by 50%'),
                                   ('243013', '[VC] For Their Authors', 'Increase LB damage by 25%'),
                                   ('243014', '[VC] Fated to Kill One Another', 'Increase static ATK by 500')]:
        extra['F_TEXT_ABILITY_NAME']['MST_ABILITY_NAME_' + iid] = name
        extra['F_TEXT_ABILITY_EXPLAIN_SHORT']['MST_ABILITY_SHORTDESCRIPTION_' + iid] = description

    def reward_label(rewards):
        labels = []
        for reward in rewards:
            kind, iid = reward['kind'], str(reward['id'])
            if kind == 50: name = 'Lapis'
            else:
                prefix = kinds[kind][1]
                name = english_names.get((kind, iid)) or texts[kind].get(prefix + iid)
            if not name or name in ('collab', '<blank>') or re.search(r'[\u3040-\u30ff\u3400-\u9fff]', name):
                raise ValueError('Untranslated milestone reward:' + str(reward))
            if reward.get('affinity_points'):
                amount = next((int(p) // 10 for p in reward['affinity_points'] if p), 0)
                name += ' (ALL ' + str(amount) + '%)'
            labels.append(name + (' x' + str(reward['count']) if reward['count'] > 1 else ''))
        return ', '.join(labels)

    archive_path = ROOT / 'source/server/raid_archive.json'
    runtime = json.loads(archive_path.read_text('utf8'))
    events = {r['area']: r for r in json.loads((ROOT / 'source/server/event_archive.json').read_text('utf8'))['events']}
    points = {'738': [800, 1500, 2400, 7000], '742': [800, 1500, 2400, 7000],
              '771': [800, 1500, 2400, 7000], '4082': [100, 300, 600, 800, 1000],
              '6210': [800, 2400, 7000], '6410': [800, 2400, 7000],
              '4480': [100, 300, 600, 800, 1000], '4500': [100, 300, 600, 800, 1000]}
    coins = {'738': 106301700, '742': 106302500, '771': 106303700, '4082': 106314800,
             '6210': 106318300, '6410': 106323600, '4480': 106323500, '4500': 106323900}
    clear_currency = {'4082': [200, 400, 600, 800, 1000], '4480': [45, 66, 129, 247, 564], '4500': [45, 66, 129, 247, 564]}
    bonus_ids = {'4082': ['104028082', '404071024'], '4480': ['104028549', '404071075'], '4500': ['104028551', '404071077']}
    prepared = []
    for area, curve in points.items():
        event = events[area]; mids = event['missions']; mode = 'clear' if area in clear_currency else 'damage'
        if len(mids) != len(curve): raise ValueError('Point tiers differ from original stage count')
        milestones = []
        native = [r for r in source['tables']['F_SEASON_EVENT_REWARD_MST']['rows'] if r['pvS5A4kE'] == NATIVE_REWARD_GROUPS.get(area)]
        for row in native:
            rewards = source_rewards(rewrite_rewards(row['dX6cor8j'], mappings))
            milestones.append({'points': int(row['1UB3Hqfc']), 'label': reward_label(rewards), 'rewards': rewards})
        for row in source['published_milestone_bindings']:
            if row['area'] != area: continue
            rewards = source_rewards(rewrite_rewards(row['native_reward'], mappings))
            milestones.append({'points': row['points'], 'label': reward_label(rewards), 'rewards': rewards})
        if not milestones: raise ValueError('No original milestone ledger:' + area)
        prepared.append({'event_id': area, 'dungeon_id': event['first_dungeon'], 'dungeon_ids': event['dungeons'],
            'name': event['name'], 'menu_background': event['filename'], 'reward_banner_id': str(900000000 + int(area)),
            'source_url': event['source_page'], 'jp_original_scope': 'earlier-jp-28', 'point_mode': mode,
            'mission_points': dict(zip(mids, curve)), 'raid_coin': {'kind': 20, 'id': coins[area]},
            'points_per_coin': 10, 'level_bonus_percent': 0 if mode == 'clear' else 8,
            'solo_pacing': {'shared_hp_per_level': 40000000, 'authored': True},
            'personal_milestones': sorted(milestones, key=lambda r: r['points']),
            'all_parts_hp': area == '738', 'bonus_enemy_ids': bonus_ids.get(area, []),
            'currency_per_clear': dict(zip(mids, clear_currency.get(area, []))),
            'status': 'Original JP milestones with documented offline scoring projection'})
        destination = {'738': '9400112', '742': '9400113', '771': '9400114', '6210': '9400151',
                       '4480': '9400152', '6410': '9400153', '4500': '9400154'}.get(area)
        if destination: prepared[-1]['coin_summon_id'] = destination
    ids = set(points)
    runtime['events'] = [r for r in runtime['events'] if r['event_id'] not in ids] + prepared
    daily = copy.deepcopy(source['daily_fragment_rewards'])
    for contract in daily.values():
        for reward in contract['chosen_enemy_rewards'].values():
            reward['id'] = int(mappings.get('F_ITEM_MST', {}).get(str(reward['id']), str(reward['id'])))
    runtime['jp_daily_fragment_rewards'] = daily
    runtime['jp_login_campaign_rewards'] = {'bravely_20170724_day1': {
        'kind': 10, 'id': 313000305, 'count': 1, 'mail_id': '932017072401',
        'title': 'Bravely Collaboration Login Bonus', 'message': 'Day 1: Bravo Bunny Agnès.',
        'original_window': '2017-07-24 05:00:00 through 2017-07-31 04:59:59 JST',
        'source_url': 'https://gamebiz.jp/news/189451',
        'projection': 'Original day-one reward issued once per offline account on its login-bonus request. Original calendar window is archived.'}}
    runtime['jp_login_campaign_rewards']['sinoalice_20210907_total'] = {
        'kind': 20, 'id': 106224700, 'count': 10, 'mail_id': '932021090710',
        'title': 'SINoALICE Collaboration Login Bonus', 'message': '10 collaboration commemorative summon tickets.',
        'original_window': '2021-09-07 through 2021-09-19 JST',
        'source_url': 'https://jp.finalfantasy.com/news/3653/',
        'projection': 'Original notice verifies10total. Original login banner has no daily counts. The verified total is issued once per offline account; original daily cadence remains unrecovered.'}
    # Original crafting materials and stage IDs are known; original random
    # drop rates are not. This scoped clear projection is documented below.
    runtime['jp_mission_clear_rewards'] = {
        mid: [{'kind': 20, 'id': int(iid), 'count': tier}
              for iid in ('206000100', '206000200', '206000300', '206000400', '206000500', '206000600', '206000700')]
        for tier, mid in enumerate(events['702']['missions'], 1)}
    runtime['jp_medal_store_schedules'] = [
        {'Z20mNDvL': store, 'za2xsDj5': store, 'w7VR6ypY': '0',
         'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': '2099-12-31 23:59:59',
         'suR36Jpm': '20:' + currency, '89YmCAzo': '', '0euar5mZ': ''}
        for store, currency in [('900119', '106301710'), ('900216', '106314800')]]
    # Recovered contemporary exchange table, projected through the existing
    # shop engine. Runtime product IDs are not historical native-ID claims.
    roto_facts = json.loads((HOME / 'Roto/original-summon-source-facts.json').read_text('utf8'))
    special_rewards = ['10:346000107:1', '10:346000407:1', '10:346000307:1',
        '20:106230840:1', '20:235037300:1', '20:235037700:1', '20:235037700:1',
        '20:900000001:1', '10:906000105:1:100:1:1000:0:0:1100000100',
        '20:106213510:1', '23:260:1', '23:110:10', '10:900020401:1:100:60', '20:400000040:1']
    special_names = ['Arus', 'Poron', 'Yao', 'Collaboration New NV 30% Summon Ticket (2022/11)',
        'Mystery Crystal', "Master's Crown", "Master's Crown", 'Omniprism',
        'Super Trust Moogle (ALL 100%)', 'Fragment Select Exchange Ticket', '5-Star Select Summon Ticket',
        'Energy Restore 50 x10', 'King Metal Minituar (MAX)', 'Gil Snapper Tower']
    if len(roto_facts['products']) != len(special_rewards): raise ValueError('Roto2022 exchange source changed')
    shop_path = ROOT / 'source/server/content/permanent_shops.json'
    permanent = json.loads(shop_path.read_text('utf8'))
    shop_name = 'Collaboration Special Exchange (2022/11)'
    shop = {'name': shop_name, 'source': roto_facts['source_url'], 'currency': [20, '106230830'],
        'category': 5, 'reset_months': 0, 'jp_original_scope': 'earlier-jp-28',
        'evidence': 'Published original2022 table with captured in-game panel; generic IDs verified against original native master names.',
        'products': [{'reward': rewrite_rewards(raw, mappings), 'price': row['ticket_cost'],
                      'limit': row['purchase_limit'] if row['purchase_limit'] is not None else 2147483647,
                      'label': name}
                     for raw, name, row in zip(special_rewards, special_names, roto_facts['products'])]}
    previous = next((i for i, row in enumerate(permanent['shops']) if row['name'] == shop_name), None)
    if previous is None: permanent['shops'].append(shop)
    else: permanent['shops'][previous] = shop
    write_json(shop_path, permanent)
    extra['F_TEXT_ITEM_NAME'].update({'MST_ITEM_NAME_106230830': 'Collaboration Special Exchange Ticket 2022/11',
        'MST_ITEM_NAME_106230840': 'Collaboration New NV 30% Summon Ticket (2022/11)',
        'MST_ITEM_NAME_106213510': 'Fragment Select Exchange Ticket',
        'MST_ITEM_NAME_106224700': 'SINoALICE Collaboration Commemorative Summon Ticket'})
    stage_followup_exchanges(inputs, mappings, extra)
    reconstruction = {
        'scope': 'Earlier JP point acquisition and original exchange availability only',
        'original': {'milestone_rows': sum(len(e['personal_milestones']) for e in prepared),
            'native_groups': NATIVE_REWARD_GROUPS, 'published_complete_tables': ['738', '742', '4480', '4500'],
            'verified_base_points': {'742': points['742'], '771': points['771'], '4480': points['4480'], '4500': points['4500']},
            'daily_fragment_contracts': len(daily), 'daily_quantity': 10,
            'merchant_stock': 'Original F_TOWN_STORE plus F_STORE_ITEM and26 F_MEDAL_EXCHANGE rows',
            'trust_projection': 'Original source option IDs100000005/001/002 correspond to1-star1%,4-star5%,5-star10%moogles; SIN79504 native description explicitly50%with option100000008. Scope supplies instance wildcard10/50/100/500points and preserves them through mailbox.',
            'source_bonus_enemy_currency_drops': 'All6 original gold-bomb rows retained without added baseline currency'},
        'reconstructed': {'738_base_points': 'Standard4-tier800/1500/2400/7000. Published displayed106/1980/2400/7000 cannot establish base values.',
            '6210_6410_base_points': 'Standard existing3-tier800/2400/7000. Exact original scoring formula not recovered.',
            '4082_clear_points': '100/300/600/800/1000 per successful clear, using retained5-tier mission order. Original formula not recovered.',
            'raid_currency': 'Floor earned points/10, existing engine convention; exact original dynamic raid formula not recovered.',
            '4480_ordinary_currency': '45/66/129/247/564, adapting the observed same-period Roto5-tier totals. Original SaGa ordinary per-formation counts not recovered.',
            '4500_ordinary_currency': '45/66/129/247/564 observed published totals used as fixed ordinary-clear amounts; original random formation allocation unknown.',
            '4082_ordinary_currency': '200/400/600/800/1000, authored after no original server drop rows were recovered. Original bonus200/5000 preserved.',
            'shared_raid_pacing': 'Existing solo40millionHP budget per level and8% level bonus. Shared server totals unavailable.',
            'merchant_availability': 'Permanent local windows for the2 original merchant IDs. Original FxLAYGHn schedules absent from5999-file JP archive and owned current schedule table.'},
        'no_claim': 'No fabricated historical banner, box pool, unit, source stat or exact historical scoring claim.'}
    reconstruction['reconstructed']['702_material_drops'] = 'Original7 named crafting materials granted after each successful original stage:1/2/3/4/5 of each by tier. Original per-enemy random rates absent from original server captures and published guide. No reward on failed clears and no duplicate accepted-attempt credit.'
    reconstruction['original']['login_grants'] = 'Bravo Bunny Agnes313000305 day1, primarygamebiz189451. SINoALICE primary3653 verifies10commemorative tickets106224700 total. Milestone7-star ticket106224600 is separate.'
    reconstruction['reconstructed']['archived_login_availability'] = 'Once per offline account at its login-bonus request. Bravely originalday1 retained; SINoriginal per-day cadence unknown, verified10total issued together. No fabricated historical daily schedule.'
    write_json(OUT / 'reward-runtime-provenance.json', reconstruction)
    write_json(OUT / 'event-reward-additional-en.json', dict(extra))
    write_json(OUT / 'event-reward-english-names.json', {str(k) + ':' + i: v for (k, i), v in english_names.items()})
    write_json(archive_path, runtime)
    return {'events': len(prepared), 'milestones': reconstruction['original']['milestone_rows'],
            'daily_missions': len(daily), 'additional_english': sum(map(len, extra.values()))}


def stage_followup_exchanges(inputs, mappings, extra):
    """Bind published historical stock to exact native identities."""
    path = ROOT / 'source/server/content/permanent_shops.json'
    book = json.loads(path.read_text('utf8'))
    original_items = {r['tL6G9egd']: r for r in inputs.original('F_ITEM_MST')}
    items = {r['tL6G9egd']: r for r in inputs.current('F_ITEM_MST')}
    units = {r['3HriTp6B']: r for r in inputs.original('F_UNIT_MST')}
    current_units = {r['3HriTp6B']: r for r in inputs.current('F_UNIT_MST')}
    item_names = inputs.text('F_TEXT_ITEM_NAME'); unit_names = inputs.text('F_TEXT_UNITS_NAME')
    source_ex = inputs.original('F_NV_EX_CLASS_UP_MST'); current_ex = inputs.current('F_NV_EX_CLASS_UP_MST')
    required_items = set()

    def normalized(value):
        return re.sub(r'[\s&＆()（）\-・]', '', unicodedata.normalize('NFKC', value))

    def add(shop):
        previous = next((i for i, row in enumerate(book['shops']) if row['name'] == shop['name'] or
                         (row.get('jp_original_scope') == 'earlier-jp-28' and row['currency'] == shop['currency'])), None)
        if previous is None: book['shops'].append(shop)
        else: book['shops'][previous] = shop

    def fragment_label(source_iid, target):
        existing = item_names.get('MST_ITEM_NAME_' + target)
        if existing and existing not in ('collab', '<NA>', '<blank>'):
            if source_iid in ('250000460', '250000560', '250028600', '250028900', '250029700', '250028700', '250024400'):
                extra['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_' + target] = existing
            return existing
        japanese = original_items[source_iid]['G4L0YIB2']
        owner = japanese.removesuffix('の欠片')
        fallback = {'リド&ジェイク': 'Lid & Jake', 'グリムロードサクラ': 'Grim Lord Sakura',
            'カオス＝ビスマルク': 'Chaos=Bismarck', 'カオス=ビスマルク': 'Chaos=Bismarck',
            'ネイリッカ-破滅の幻獣-': 'Neilikka -Esper of Destruction-',
            'パラディンオブグランシェルト': 'Paladin of Grandshelt',
            'リュース-破滅の幻獣-': 'Rhus -Esper of Destruction-',
            '幻獣と通じ合う少女リディア': 'Rydia, Girl Who Communes with Espers'}
        names = {unit_names.get('MST_UNIT_NAME_' + r['3HriTp6B']) for r in units.values()
                 if normalized(r['G4L0YIB2']) == normalized(owner)}
        names = {n for n in names if n and n not in ('collab', '<NA>', '<blank>') and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', n)}
        english = next(iter(names)) if len(names) == 1 else next((v for k, v in fallback.items() if normalized(k) == normalized(owner)), None)
        if not english: raise ValueError('Published fragment English missing:' + source_iid + ':' + owner + ':' + str(names))
        label = english + ' Fragment'
        extra['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_' + target] = label
        return label

    facts = json.loads((HOME / 'Roto/generic-fragment-select-source.json').read_text('utf8'))
    aliases = {'フォルカ&シトラ': 'フォルカ&シトラ2018夏', 'フィーナ&リド': 'フィーナ&リド2018夏',
        '白蓮フィーナ': '白蓮の魔道士フィーナ', '聖盾シャルロット': '聖盾の騎士シャルロット',
        'コルツマッシュ': 'コルツの格闘家マッシュ', 'ギルガメッシュ(FFⅤ)': 'ギルガメッシュ',
        'バレット(FF7R)': 'バレット(FFVII REMAKE)', 'ルーファウス神羅': 'ルーファウス神羅(FFVII REMAKE)'}
    generic_products, generic_bindings = [], []
    for info in facts['published_eligible_names']:
        name = aliases.get(info['name_ja'], info['name_ja'])
        matches = [r for r in units.values() if normalized(r['G4L0YIB2']) == normalized(name)
                   and r.get('I3SKJ4q0') == '0' and int(r.get('JPW8Vs40') or 0) > 0
                   and units.get(r['woghJa61'], {}).get('9fW0TePj') == '5']
        if len(matches) != 1: raise ValueError('Published NVA identity ambiguous:' + info['name_ja'])
        unit = matches[0]; nv = unit['JPW8Vs40']
        pieces = {iid for row in source_ex if row['JPW8Vs40'] == nv
                  for kind, iid, _ in reward_parts(row['KCk8u0am'])
                  if kind == '20' and iid in original_items and 'の欠片' in original_items[iid]['G4L0YIB2']}
        if len(pieces) != 1: raise ValueError('Published NVA fragment ambiguous:' + info['name_ja'])
        source_iid = pieces.pop(); iid = mappings.get('F_ITEM_MST', {}).get(source_iid, source_iid)
        if iid not in items: required_items.add(source_iid)
        if iid in items and normalized(items[iid]['G4L0YIB2']) != normalized(original_items[source_iid]['G4L0YIB2']) and re.search(r'[\u3040-\u30ff\u3400-\u9fff]', items[iid]['G4L0YIB2']):
            raise ValueError('NVA fragment character identity differs:' + iid)
        if unit['3HriTp6B'] in current_units:
            expected = {p[1] for r in current_ex if r['JPW8Vs40'] == current_units[unit['3HriTp6B']]['JPW8Vs40'] for p in reward_parts(r['KCk8u0am']) if p[0] == '20'}
            if iid not in expected: raise ValueError('Current NVA unit consumes another fragment:' + info['name_ja'])
        label = fragment_label(source_iid, iid)
        generic_products.append({'reward': '20:' + iid + ':25', 'price': 10, 'limit': 2147483647, 'label': label + ' x25'})
        generic_bindings.append(dict(info, source_unit_id=unit['3HriTp6B'], source_fragment_id=source_iid,
            current_fragment_id=iid, current_native_NVA_form_present=unit['3HriTp6B'] in current_units))
    add({'name': 'Fragment Select Exchange', 'source': facts['source_url'], 'currency': [20, '106213510'],
         'category': 5, 'reset_months': 0, 'jp_original_scope': 'earlier-jp-28',
         'evidence': 'Published46eligible five-star-base NVA units. Exact10tickets for25fragments. Source publishes no stock cap; permanent local availability is uncapped.',
         'products': generic_products})
    # The paid2024/3ticket explicitly selects50Roto fragments. Its complete
    # original eligibility table is missing, so only the8evidenced paid NV
    # versions are projected. The free Frea is not silently added.
    source_roto = ['250016800', '250017000', '250017100', '250032100',
                   '250032000', '250032200', '250032300', '250032400']
    roto_fragments = []
    for iid in source_roto:
        target = mappings.get('F_ITEM_MST', {}).get(iid, iid)
        label = fragment_label(iid, target)
        roto_fragments.append({'reward': '20:' + target + ':50', 'price': 1, 'limit': 2147483647, 'label': label + ' x50'})
    add({'name': 'Emblem of Roto NV Fragment Exchange (2024/3)',
        'source': 'https://altema.jp/ffbe/rotonomonsyoudai2dangacha', 'currency': [20, '106234130'],
        'category': 5, 'reset_months': 0, 'jp_original_scope': 'earlier-jp-28', 'products': roto_fragments,
        'evidence': 'Original special STEP5 ticket and50fragment quantity published. Complete original selection table unrecovered;8paid Roto NV versions are a documented eligibility reconstruction.'})
    box_fragment_path = HOME / 'Roto/loran-castle-box-fragments.json'
    if box_fragment_path.is_file():
        rows = json.loads(box_fragment_path.read_text('utf8'))['rows']
        ep_products = [{'reward': '20:' + mappings.get('F_ITEM_MST', {}).get(r['item_id'], r['item_id']) + ':50',
                        'price': 1, 'limit': 2147483647, 'label': r['english_name'] + ' x50'} for r in rows]
        add({'name': 'Air Raid! Loran Castle NV Fragment Exchange', 'source': 'https://altema.jp/ffbe/kuusyuuroranjyou',
            'currency': [20, '106234120'], 'category': 5, 'reset_months': 0, 'jp_original_scope': 'earlier-jp-28',
            'products': ep_products, 'evidence': 'The published300kEP ticket and Summon to Exchange destination are exact. Original quantity/pool unrecovered after guide/native search. Offline1ticket for50fragments from the7published event-box versions is explicitly reconstructed.'})
    extra['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_106234130'] = 'Emblem of Roto Collaboration NV Fragment Exchange Ticket (2024/3)'

    common = {'????のクリスタル': '20:235037300:1', 'マスタークラウン': '20:235037700:1',
        'ALL輝源': '20:900000001:1', 'ALL100%スパモグ': '10:906000105:1:100:1:1000:0:0:1100000100',
        '欠片セレクトチケット': '20:106213510:1', 'セレクトチケット': '23:260:1', '体力回復薬50×10': '23:110:10',
        'メタルミニテンキング(MAX)': '10:900020401:1:100:60', 'ギルガメタワー': '20:400000040:1'}
    common_labels = {'????のクリスタル': 'Mystery Crystal', 'マスタークラウン': "Master's Crown", 'ALL輝源': 'Omniprism',
        'ALL100%スパモグ': 'Super Trust Moogle (ALL 100%)', '欠片セレクトチケット': 'Fragment Select Exchange Ticket',
        'セレクトチケット': '5-Star Select Summon Ticket', '体力回復薬50×10': 'Energy Restore 50 x10',
        'メタルミニテンキング(MAX)': 'King Metal Minituar (MAX)', 'ギルガメタワー': 'Gil Snapper Tower'}
    exact_units = {'ロックブーケ': '349000107', 'アルベルト': '348000107', 'エレン': '309000507',
        'アセルス': '350000107', 'ギュスターヴ13世': '351000107', '勇者アラン': '346000507',
        '海王Ⅱ世シーザリオン': '346000707', '勇者アステア': '346000607', '勇者アルス': '346000907', '異魔神': '346000807'}
    ticket_maps = [
        {'新キャラ排出確率30%チケット': '106233680', '光NV確定チケット': '106233690', '土NV確定チケット': '106233580'},
        {'闇NV確定チケット': '106233570', '土NV確定チケット': '106233580'},
        {'ロトの紋章NVキャラ確定チケット': '106233940', '光NV確定チケット': '106233950', '世界を救いし者たちNV確定チケット': '106233960', '水NV確定チケット': '106233970'},
        {'ロトの紋章NV確定チケット': '106233940', '世界を救いし者たちNV確定チケット': '106233960', '土カテゴリNV確定チケット': '106234080', '火カテゴリNV確定チケット': '106234090'}]
    files = ['saga-20240111-original-summon-facts.json', 'saga-20240119-original-summon-facts.json',
             'Roto/roto-20240219-original-summon-facts.json', 'Roto/roto-20240229-original-summon-facts.json']
    titles = ['SaGa Collaboration Special Exchange (2024/1/11)', 'SaGa Collaboration Special Exchange (2024/1/19)',
              'Emblem of Roto Special Exchange (2024/2/19)', 'Emblem of Roto Special Exchange (2024/3)']
    english_ticket_labels = {'106233680': 'Collaboration New NV 30% Summon Ticket (2024/1)',
        '106233690': 'Light NV Guaranteed Summon Ticket (2024/1)', '106233580': 'Earth NV Guaranteed Summon Ticket (2024/1)',
        '106233570': 'Dark NV Guaranteed Summon Ticket (2024/1)', '106233940': 'Emblem of Roto NV Guaranteed Summon Ticket (2024/2)',
        '106233950': 'Light NV Guaranteed Summon Ticket (2024/2/19)', '106233960': 'The Saviors NV Guaranteed Summon Ticket (2024/2)',
        '106233970': 'Water NV Guaranteed Summon Ticket (2024/2)', '106234080': 'Earth NV Guaranteed Summon Ticket (2024/3)',
        '106234090': 'Fire NV Guaranteed Summon Ticket (2024/3)'}
    currency_labels = {'106233670': 'SaGa Series 35th Anniversary Collaboration Special Exchange Ticket (2024/1)',
        '106233740': 'SaGa Series 35th Anniversary Collaboration Special Exchange Ticket (2024/1/19)',
        '106233930': 'Emblem of Roto Collaboration Special Exchange Ticket (2024/2)',
        '106234070': 'Emblem of Roto Collaboration Special Exchange Ticket (2024/3)'}
    source_bindings = []
    for filename, title, tickets in zip(files, titles, ticket_maps):
        source = json.loads((HOME / filename).read_text('utf8')); products = []
        currency = str(source['SP_currency'])
        if currency not in items: raise ValueError('Historical SP currency not owned:' + currency)
        extra['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_' + currency] = currency_labels[currency]
        for row in source['SP_products']:
            name = row['name_ja']; label = None
            if name in common: raw = common[name]; label = common_labels[name]
            elif name in tickets:
                iid = tickets[name]
                if iid not in items: raise ValueError('Historical SP reward ticket not owned:' + iid)
                raw = '20:' + iid + ':1'; label = english_ticket_labels[iid]
                extra['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_' + iid] = label
            elif name in exact_units:
                iid = exact_units[name]; target = mappings.get('F_UNIT_MST', {}).get(iid, iid)
                if target not in current_units: raise ValueError('Historical SP unit missing:' + target)
                raw = '10:' + target + ':1'; label = unit_names['MST_UNIT_NAME_' + target]
            elif name.endswith('の欠片×50'):
                wanted = name[:-len('×50')]
                wanted = {'忠義の騎士アグリアスの欠片': '信義の騎士アグリアスの欠片'}.get(wanted, wanted)
                candidates = [r for r in original_items.values() if normalized(r['G4L0YIB2']) == normalized(wanted)]
                if len(candidates) != 1: raise ValueError('Historical SP fragment identity ambiguous:' + wanted)
                iid = candidates[0]['tL6G9egd']; target = mappings.get('F_ITEM_MST', {}).get(iid, iid)
                if target not in items: required_items.add(iid)
                label = fragment_label(iid, target)
                raw = '20:' + target + ':50'; label += ' x50'
            else: raise ValueError('Unbound original historical SP reward:' + name)
            raw = rewrite_rewards(raw, mappings)
            products.append({'reward': raw, 'price': row['cost_tickets'],
                             'limit': row['limit'] if row['limit'] is not None else 2147483647, 'label': label})
            source_bindings.append({'source_file': filename, 'name_ja': name, 'native_reward': raw, 'price': row['cost_tickets'], 'limit': row['limit']})
        add({'name': title, 'source': source['source_url'], 'currency': [20, currency], 'category': 5,
             'reset_months': 0, 'jp_original_scope': 'earlier-jp-28', 'products': products})
    write_json(HOME / 'Roto/generic-fragment-native-bindings.json', {'rate_tickets': 10, 'fragment_quantity': 25,
        'eligible_count': len(generic_bindings), 'rows': generic_bindings,
        'unit_scope': 'Only fragments are supplied. Existing Global unit data unchanged; no unrelated JP NVA forms are imported.'})
    write_json(OUT / 'historical-sp-exchange-bindings.json', {'rows': source_bindings, 'count': len(source_bindings),
        'evidence': 'All98published2024SProws retain exactquantity/cost/limit and exact native named identities.2022original14rows are retained separately.'})
    write_json(OUT / 'required-exchange-item-additions.json', {'source_ids': sorted(required_items, key=int),
        'rows': [original_items[i] for i in sorted(required_items, key=int)],
        'reason': 'Exact original fragment rewards needed by published historical exchange stock. No unit form imports.'})
    write_json(path, book)


def stage_exchange_item_import(inputs):
    needed = json.loads((OUT / 'required-exchange-item-additions.json').read_text('utf8'))
    current = {r['tL6G9egd']: r for r in inputs.current('F_ITEM_MST')}
    labels = json.loads((OUT / 'event-reward-additional-en.json').read_text('utf8'))['F_TEXT_ITEM_NAME']
    next_index = max(int(r.get('QLfe23bu') or 0) for r in list(current.values()) + inputs.original('F_ITEM_MST')) + 1
    rows = []
    for source in needed['rows']:
        iid = source['tL6G9egd']
        if iid in current: raise ValueError('Required exchange item target already exists; verify before rerun:' + iid)
        row = dict(source); row['G4L0YIB2'] = labels['MST_ITEM_NAME_' + iid]
        row['QLfe23bu'] = str(next_index); next_index += 1; rows.append(row)
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY',
        'scope': 'One required original JP fragment item for the published generic exchange. No unrelated unit form imported.',
        'tables': [contract_table(inputs, 'F_ITEM_MST', 'tL6G9egd', rows, 'replace')]}
    write_json(OUT / 'native-exchange-item-import.json', contract)
    return {'native_item_additions': len(rows)}


def stage_common_wallet_reuse(inputs):
    """Stage only verified29*/36*wallet aliases and typed JP references."""
    primary_path = HOME / 'native-unit-id-map.json'
    primary_bytes = primary_path.read_bytes(); primary = json.loads(primary_bytes)
    item_map = primary['mappings']['F_ITEM_MST']
    source_items = {r['tL6G9egd']: r for r in inputs.original('F_ITEM_MST')}
    current_items = {r['tL6G9egd']: r for r in inputs.current('F_ITEM_MST')}
    verified = []
    for source, target in item_map.items():
        if not source.startswith(('29', '36')): continue
        original, current = source_items[source], current_items[source]
        left = {k: v for k, v in original.items() if k != '9J6uRe8f'}
        right = {k: v for k, v in current.items() if k != '9J6uRe8f'}
        if left != right: raise ValueError('Common material has another semantic difference:' + source)
        verified.append({'source_id': source, 'orphan_alias_id': target, 'name_jp': original['G4L0YIB2'],
                         'JP_stack_cap': original['9J6uRe8f'], 'Global_stack_cap_preserved': current['9J6uRe8f']})
    reverse = {r['orphan_alias_id']: r['source_id'] for r in verified}
    reverse_map = {'F_ITEM_MST': reverse}
    mappings = primary['mappings']; unit_map = mappings['F_UNIT_MST']
    content = json.loads((HOME / 'original-unit-content.json').read_text('utf8'))['tables']
    original_events = json.loads((OUT / 'original-event-reward-content.json').read_text('utf8'))['tables']
    unit_rows = {unit_map.get(r['3HriTp6B'], r['3HriTp6B']) for r in content['F_UNIT_MST']['rows']}
    nv_roots = {unit_map.get(r['JPW8Vs40'], r['JPW8Vs40']) for r in content['F_NV_EX_CLASS_UP_MST']['rows']}
    definitions = [
        ('F_UNIT_MST', ['3HriTp6B'], unit_rows, '3HriTp6B', ('9mu4boy7', 'C74EmZ1I')),
        ('F_UNIT_CLASS_UP_MST', ['3HriTp6B'], {unit_map.get(r['3HriTp6B'], r['3HriTp6B']) for r in content['F_UNIT_CLASS_UP_MST']['rows']}, '3HriTp6B', ('KCk8u0am',)),
        ('F_NV_EX_CLASS_UP_MST', ['JPW8Vs40', 'f8vk4JrD'], nv_roots, 'JPW8Vs40', ('KCk8u0am', 'dX6cor8j')),
        ('F_RECIPE_MST', ['MpNE6gB5'], {r['MpNE6gB5'] for r in original_events['F_RECIPE_MST']['rows']}, 'MpNE6gB5', ('HS7V6Ww1',)),
        ('F_MEDAL_EXCHANGE_MST', ['S21FT3L8'], {r['S21FT3L8'] for r in original_events['F_MEDAL_EXCHANGE_MST']['rows']}, 'S21FT3L8', ('7iJpH5zZ',)),
        ('F_MISSION_MST', ['qo3PECw6'], {r['qo3PECw6'] for r in read_rows(HOME / 'Event graph/F_MISSION_MST.ndjson')}, 'qo3PECw6', ('1x4bG2J8',)),
        ('F_CHALLENGE_MST', ['qo3PECw6', 'V36ygRYs', 'Z0EN6jSh'], {r['qo3PECw6'] for r in read_rows(HOME / 'Event graph/F_MISSION_MST.ndjson')}, 'qo3PECw6', ('dX6cor8j',))]
    patches, evidence, inspected = [], [], {}
    for table, keys, scope, owner, fields in definitions:
        scoped = [r for r in inputs.current(table) if r.get(owner) in scope]
        inspected[table] = len(scoped); rows = []
        for row in scoped:
            changes = {}
            for field in fields:
                before = row.get(field, ''); after = rewrite_rewards(before, reverse_map)
                if after != before:
                    changes[field] = after
                    evidence.append({'table': table, 'identity': {k: row[k] for k in keys},
                                     'field': field, 'before': before, 'after': after})
            if changes: rows.append(dict({k: row[k] for k in keys}, **changes))
        if rows:
            entry = contract_table(inputs, table, keys[0], rows)
            entry['identity_fields'] = keys; patches.append(entry)
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY',
        'scope': 'Typed references for verified shared29*/36*materials only. Shared Global rows and orphan aliases preserved.',
        'tables': patches, 'counts': {t['table']: len(t['rows']) for t in patches}}
    write_json(OUT / 'native-shared-common-wallet-import.json', contract)
    result = {'status': 'REVIEW_REQUIRED_BEFORE_NATIVE_APPLY', 'primary_map_before_sha256': sha(primary_bytes),
        'verified_aliases': verified, 'alias_count': len(verified), 'native_counts': contract['counts'],
        'consumer_fields': dict(__import__('collections').Counter(r['table'] + '.' + r['field'] for r in evidence)),
        'native_changes': evidence, 'inspected_scoped_rows': inspected,
        'runtime_refresh': 'Regenerate465milestones, exactSPshops and JP raid/boxpools through final primary map after removal.',
        'preservation': 'No25*fragment alias, unit/effect/skill identity, shared Global item row, stack cap, English field or saved inventory is changed. Old alias records remain.'}
    write_json(OUT / 'shared-common-wallet-reuse-plan.json', result)
    return {k: result[k] for k in ('alias_count', 'native_counts', 'consumer_fields', 'inspected_scoped_rows')}


def stage_gear_descriptions(inputs):
    authored = {
      '304001600': ('A longsword made from Nef-Garmat materials.',
        'A longsword brought from another world, made from materials of the monster Nef-Garmat that lives there. Known as the Nethercrystal Dragon, Nef-Garmat is an earth-element elder dragon, and this longsword also harbors the power of earth.'),
      '312001700': ('A bow made from Immortal Zinogre materials.',
        'A bow brought from another world, made from materials of the Immortal Zinogre that lives there. The monster cloaks itself in enormous amounts of electrical energy, and this bow also harbors the power of lightning.'),
      '404001800': ('Armor made from Arzuros materials.',
        'Head armor brought from another world, made from materials of the monster Arzuros that lives there. Arzuros is an omnivore with a hearty appetite and is especially fond of honey.'),
      '404001900': ('Armor made from Lagiacrus materials.',
        'Head armor brought from another world, made from materials of the monster Lagiacrus that lives there. Also known as the Sea Wyvern, Lagiacrus confounds hunters by swimming freely underwater and excels at breathing powerful electrical discharges.'),
      '404002000': ('Armor made from Deviljho materials.',
        'Head armor brought from another world, made from materials of the monster Deviljho that lives there. Known as the Violent Wyvern, Deviljho is as ferocious as its name suggests and has an extraordinary appetite that drives it to prey on every kind of creature.'),
      '406002100': ('Armor made from Arzuros materials.',
        'Torso armor brought from another world, made from materials of the monster Arzuros that lives there. Its highly developed forelegs have sharp claws and thick shells. True to its other name, the Blue Bear Beast, it is covered in beautiful blue fur.'),
      '406002300': ('Armor made from Deviljho materials.',
        'Torso armor brought from another world, made from materials of the monster Deviljho that lives there. It features red lines against Deviljho\'s distinctive dark green coloring, with characteristic projections on the shoulders and chest.'),
      '406002500': ('Armor made from meteorite fragments.', None),
      '407002100': ('A mechanized suit of full-body armor.', None),
      '409012000': ('Armor made from Arzuros materials.',
        'Arm armor brought from another world, made from materials of the monster Arzuros that lives there. Its head and back are covered by a hard shell, and it is also known as the Blue Bear Beast.'),
      '409012100': ('Armor made from Lagiacrus materials.',
        'Arm armor brought from another world, made from materials of the monster Lagiacrus that lives there. Lagiacrus is an enormous aquatic monster with a long neck, feared by the people of that world for its ferocity.'),
      '409012200': ('Armor made from Deviljho materials.',
        'Arm armor brought from another world, made from materials of the monster Deviljho that lives there. Deviljho has a huge mouth that extends to its neck and a jaw covered in countless spikes. These spikes are fangs that have grown beyond its mouth, and this armor also bears sharp projections inherited from its materials.')}
    table = 'F_EQUIP_ITEM_EXPLAIN_MST'
    current = {r['J1YX9kmM']: r for r in inputs.current(table)}
    original = {r['J1YX9kmM']: r for r in inputs.original(table, required=False)}
    existing_long = inputs.text('F_TEXT_ITEM_EQUIP_LONG')
    texts, patches, provenance = defaultdict(dict), [], []
    for iid, (short, long) in authored.items():
        row = current[iid]
        if original:
            for field in ('T7aEx3Mj', 'VC9F3eJn'):
                if original[iid][field] != row[field] and re.search(r'[\u3040-\u30ff\u3400-\u9fff]', row[field]):
                    raise ValueError('Original and retained gear text disagree:' + iid)
        if long is None:
            long = existing_long['MST_EQUIP_ITEM_LONGDESCRIPTION_' + iid]
            if not long or long in ('NA', '<NA>', 'collab'): raise ValueError('Existing English long description missing')
        patches.append({'J1YX9kmM': iid, 'T7aEx3Mj': short, 'VC9F3eJn': long})
        texts['F_TEXT_ITEM_EQUIP_SHORT']['MST_EQUIP_ITEM_SHORTDESCRIPTION_' + iid] = short
        texts['F_TEXT_ITEM_EQUIP_LONG']['MST_EQUIP_ITEM_LONGDESCRIPTION_' + iid] = long
        provenance.append({'item_id': iid, 'source_jp': original.get(iid, row), 'short_en': short, 'long_en': long,
                           'long_reused_existing_English': iid in ('406002500', '407002100')})
    contract = {'schema': 1, 'status': 'VALIDATED_READY_TO_APPLY', 'scope': 'Twelve earlier JP event gear descriptions, text fields only',
        'tables': [contract_table(inputs, table, 'J1YX9kmM', patches)], 'counts': {table: 12}}
    write_json(OUT / 'event-gear-descriptions-en.json', dict(texts))
    write_json(OUT / 'native-event-gear-descriptions-import.json', contract)
    write_json(OUT / 'event-gear-descriptions-provenance.json', {'source_receipts': inputs.receipts,
        'original_archive_owned': bool(original), 'rows': provenance, 'gameplay_fields_changed': False})
    return {'gear': 12, 'English_keys': 24, 'original_archive_owned': bool(original)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', action='store_true')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--gear-descriptions', action='store_true')
    parser.add_argument('--exchange-items', action='store_true')
    parser.add_argument('--shared-materials', action='store_true')
    args = parser.parse_args()
    inputs = Inputs()
    if args.labels:
        print(json.dumps(stage_labels(inputs), ensure_ascii=False))
    elif args.recover:
        result = recover_reward_sources(inputs)
        print(json.dumps({'counts': result['counts'], 'published': len(result['published_milestone_bindings']),
                          'daily_missions': len(result['daily_fragment_rewards']), 'missing': result['missing']}, ensure_ascii=False))
    elif args.prepare:
        source = json.loads((OUT / 'original-event-reward-content.json').read_text(encoding='utf8'))
        contract, mapping = prepare_native_import(inputs, source)
        print(json.dumps({'status': contract['status'], 'counts': contract['counts'],
                          'item_collision': mapping['new_item_collision'], 'recipe_remaps': mapping['new_event_mappings']}))
    elif args.runtime:
        source = json.loads((OUT / 'original-event-reward-content.json').read_text('utf8'))
        print(json.dumps(stage_runtime(inputs, source)))
    elif args.gear_descriptions:
        print(json.dumps(stage_gear_descriptions(inputs)))
    elif args.exchange_items:
        print(json.dumps(stage_exchange_item_import(inputs)))
    elif args.shared_materials:
        print(json.dumps(stage_common_wallet_reuse(inputs)))
    else:
        parser.error('Choose --labels or --recover')


if __name__ == '__main__':
    main()
