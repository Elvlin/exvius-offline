"""Recover each archived raid's own scoring, currency and personal rewards."""
from collections import defaultdict
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'source/server'))
from build_event_archive import normal, rows

SOURCE = ROOT / 'logs/reference/raids/archive-raids-wiki-20261026.json'


def item_key(value):
    # A plus sign distinguishes enhanced items from their original version.
    return normal(value) + '+' * value.count('+')


def templates(text, name):
    for start in re.finditer(r'\{\{\s*' + re.escape(name) + r'\b', text, re.I):
        depth, end = 1, start.end()
        for token in re.finditer(r'\{\{|\}\}', text[end:]):
            depth += 1 if token[0] == '{{' else -1
            if depth == 0:
                end += token.end()
                yield start.start(), text[start.end():end - 2]
                break


def plain(value):
    value = re.sub(r'\{\{Item\|([^|}]+)(?:\|[^}]*)?\}\}', r'\1', value, flags=re.I)
    value = re.sub(r'\[\[([^]|]+)\|([^]]+)\]\]', r'\2', value)
    value = re.sub(r'\[\[([^]]+)\]\]', r'\1', value)
    value = re.sub(r'\{\{Rarity\|(\d+)\}\}', r'\1-star ', value, flags=re.I)
    value = re.sub(r'<[^>]*>', '', value)
    return html.unescape(value.replace("'''", '').replace("''", '')).strip()


def name_tables():
    result = {}
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as archive:
        original_ids = {}
        for kind, filename in ((20, 'items.json'), (21, 'equipment.json'), (22, 'materia.json'),
                               (60, 'recipes.json')):
            path = next(name for name in archive.namelist() if name.endswith('/' + filename))
            original_ids[kind] = set(json.loads(archive.read(path)))
    for kind, table in ((20, 'F_TEXT_ITEM_NAME'), (21, 'F_TEXT_ITEM_EQUIP_NAME'),
                        (22, 'F_TEXT_MATERIA_NAME'), (23, 'F_TEXT_IMPORTANT_ITEM_NAME'),
                        (60, 'F_TEXT_RECIPE_BOOK_NAME'), (10, 'F_TEXT_UNITS_NAME')):
        by_name = defaultdict(list)
        for row in rows(table, text=True):
            iid = row['key'].rsplit('_', 1)[1]
            if kind not in original_ids or iid in original_ids[kind]:
                by_name[item_key(row['v'][0])].append(int(iid))
        result[kind] = by_name
    return result


def reward(value, category, tables, context):
    lapis = re.search(r'\{\{Lapis\|([\d,]+)\}\}', value, re.I)
    gil = re.search(r'\{\{Gil\|([\d,]+)\}\}', value, re.I)
    if lapis or gil:
        found = lapis or gil
        return {'kind': 50 if lapis else 30, 'id': 1, 'count': int(found[1].replace(',', ''))}
    currency = re.search(r'\{\{Currency\|([^|}]+)\|([\d,]+)\}\}', value, re.I)
    if currency:
        value = currency[1] + ' (' + currency[2] + ')'
    label = plain(value)
    count_match = re.search(r'\s*\(([\d,]+)\)\s*$', label)
    count = int(count_match[1].replace(',', '')) if count_match else 1
    name = label[:count_match.start()].strip() if count_match else label
    explicit = {'Glitz Gem': (20, 1209000868), 'Dark Matter (KH)': (20, 235004100),
                'Recipe for Dragon Scale (DQ)': (60, 904002080),
                'DQXI S Special Unit Summoning Key No.2 (Silver)': (20, 1209001069),
                'Raid Restore': (23, 903),
                'Super Trust Moogle (Alena & Marquis de Léon 100%)': (10, 906000105)}
    if name in explicit:
        kind, iid = explicit[name]
        return {'kind': kind, 'id': iid, 'count': count}
    if name == 'Monthly Fortune Hunt Coin':
        year, month = map(int, context['release'].split('-')[:2])
        index = (year - 2020) * 12 + month - 12
        if 0 <= index < 4:
            return {'kind': 20, 'id': [1209001309, 1209001313, 1209001334, 1209001337][index], 'count': count}
    if name == 'Red Dragon Raid Coin' and context.get('coin'):
        return {'kind': 20, 'id': context['coin'], 'count': count}
    if name.startswith('Recipe for '):
        kind, name = 60, name[len('Recipe for '):]
    elif 'Trust Moogle' in name and re.search(r'ALL\s+\d+%', name):
        percent = int(re.search(r'ALL\s+(\d+)%', name)[1])
        return {'kind': 10, 'id': 904000100 + {1: 1, 5: 4, 10: 5}[percent], 'count': count}
    elif normal(name) in {normal('Rare Summon Ticket'), normal('4★+ Guaranteed Ticket')}:
        return {'kind': 23, 'id': 50 if name == 'Rare Summon Ticket' else 70, 'count': count}
    else:
        kind = (10 if 'unit' in category.lower() or 'enhanc' in category.lower() else
                22 if re.search(r'\b(?:ability|materia)\b', category, re.I) else 20)
    name = re.sub(r'^\d-star\s+', '', name)
    name = {"Scion Conjurer's Patten": "Scion Conjurer's Pattens", 'Magi Staff': 'Magi Staff (FFV)',
            'Recipe for Magi Staff': 'Magi Staff (FFV)'}.get(name, name)
    if not tables[kind].get(item_key(name)):
        unqualified = re.sub(r'\s*\((?:DQ|KH|FFVII REMAKE)\)\s*$', '', name)
        if tables[kind].get(item_key(unqualified)):
            name = unqualified
    if kind == 20 and item_key(name) not in tables[20]:
        for candidate in (23, 21, 22, 10):
            if item_key(name) in tables[candidate]:
                kind = candidate
                break
    candidates = tables[kind].get(item_key(name), [])
    # Global units have one ID per rarity. The wiki's explicit rarity picks it;
    # otherwise use the lowest original base form, as a unit reward does.
    if kind == 10 and candidates:
        if candidates:
            candidates = [min(candidates)]
    if len(candidates) != 1:
        raise ValueError('Unmapped or ambiguous reward: ' + label)
    return {'kind': kind, 'id': candidates[0], 'count': count}


def milestones(text, tables, context):
    section = re.search(r'={2,}\s*(?:Individual|Personal) Rewards\s*={2,}(.*?)(?=\n={2,}\s*(?:Ranking|Rank|Raid Summon|Battle|Craft)|\Z)', text, re.I | re.S)
    result, unresolved = [], []
    if not section:
        return result, unresolved
    for row in re.finditer(r'^\|\s*([\d,]+)\s*(?:pts|points)?\s*\|\|\s*(.*?)\s*\|\|\s*(.*?)(?:\|\||$)', section[1], re.M | re.I):
        threshold = int(row[1].replace(',', ''))
        value, category = row[2], plain(row[3])
        try:
            grants = [reward(part, category, tables, context) for part in re.split(r'<br\s*/?>', value, flags=re.I) if part.strip()]
            if not grants:
                continue
        except (ValueError, KeyError) as exc:
            unresolved.append({'points': threshold, 'label': plain(value), 'error': str(exc)})
            continue
        label = plain(value)
        if 'Super Trust Moogle (Alena & Marquis de Léon 100%)' in label:
            label = label.replace('Super Trust Moogle (Alena & Marquis de Léon 100%)', 'Super Trust Moogle (ALL 100%)')
        result.append({'points': threshold, 'label': label, 'rewards': grants})
    unique = {}
    for row in result:
        unique.setdefault(row['points'], row)
    return sorted(unique.values(), key=lambda row: row['points']), unresolved


def main():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    pages, redirects = {}, {}
    for batch in source:
        redirects.update({normal(row['from']): normal(row['to']) for row in batch.get('query', {}).get('redirects', [])})
        for page in batch.get('query', {}).get('pages', {}).values():
            if page.get('revisions'):
                pages[normal(page['title'])] = page
    with zipfile.ZipFile(ROOT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip') as archive:
        path = next(name for name in archive.namelist() if name.endswith('/missions.json'))
        original_missions = json.loads(archive.read(path))
    masters = {row['qo3PECw6']: row for row in rows('F_MISSION_MST')}
    tables = name_tables()
    events, gaps = [], []
    archived = json.loads((ROOT / 'source/server/event_archive.json').read_text(encoding='utf-8'))['events']
    for area in archived:
        if area['kind'] != 'raid' or area['area'] == '734':
            continue
        title = normal(unquote(area['source_page'].split('/wiki/')[-1]).replace('_', ' '))
        page = pages.get(redirects.get(title, title))
        text = re.sub(r'<!--.*?-->', '', page['revisions'][0]['slots']['main']['*'], flags=re.S) if page else ''
        points_by_stage, points_by_name, currencies = {}, {}, []
        for position, block in templates(text, 'Battle Infobox'):
            fields = dict((key.strip(), value.strip()) for key, value in re.findall(r'^\|\s*([^=]+?)\s*=\s*(.*)$', block, re.M))
            headings = re.findall(r'={2,}\s*(.*?)\s*={2,}', text[:position])
            heading = headings[-1] if headings else ''
            stage = re.search(r'\b(BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\s*$', heading)
            points = re.search(r'([\d,]+)\s+(?:event\s+|raid\s+)?points', fields.get('drop', ''), re.I)
            if stage and points:
                points_by_stage[stage[1]] = int(points[1].replace(',', ''))
            if points:
                points_by_name[normal(heading)] = int(points[1].replace(',', ''))
            currencies.extend(re.findall(r'\{\{Currency\|([^|}]+)\|', fields.get('drop', ''), re.I))
        coins = {iid for name in currencies for iid in (tables[20].get(item_key(name), []) or
                 tables[20].get(item_key(re.sub(r'\s*\([^)]*\)\s*$', '', name)), []))}
        own = [mid for mid in area['missions'] if masters[mid].get('gQR24kST') == '2']
        if not own:
            continue
        if len(coins) > 1:
            first_clear_coins = {challenge['reward'][1] for mid in own
                                 for challenge in original_missions.get(mid, {}).get('challenges', [])
                                 if challenge.get('reward', [None])[0] == 'ITEM' and challenge['reward'][1] in coins}
            if len(first_clear_coins) == 1:
                coins = first_clear_coins
        if len(coins) > 1:
            gaps.append({'area': area['area'], 'name': area['name'], 'missing': 'unique original raid coin', 'candidates': sorted(coins)})
            continue
        points, missing, reconstructed = {}, [], []
        for mid in own:
            name = original_missions.get(mid, {}).get('name', '')
            stage = re.search(r'\b(BGN|INT|ADV|PRO|ELT|LGD|EXT|SVG)\b\s*$', name)
            if normal(name) in points_by_name:
                points[mid] = points_by_name[normal(name)]
            elif stage and stage[1] in points_by_stage:
                points[mid] = points_by_stage[stage[1]]
            elif stage and stage[1] == 'LGD' and 'ELT' in points_by_stage:
                points[mid] = points_by_stage['ELT']
            elif area['area'] == '948' and stage and stage[1] in ('INT', 'ADV', 'PRO', 'ELT'):
                points[mid] = {'INT': 800, 'ADV': 1500, 'PRO': 2400, 'ELT': 7000}[stage[1]]
                reconstructed.append(mid)
            elif area['area'] == '988':
                points[mid] = 7000
                reconstructed.append(mid)
            else:
                missing.append(mid)
        rewards, unmapped = milestones(text, tables, {'release': area['release'], 'coin': next(iter(coins)) if coins else None})
        if missing or unmapped:
            gaps.append({'area': area['area'], 'name': area['name'], 'missing_points': missing, 'unmapped_rewards': unmapped})
        if not points:
            continue
        rate = re.search(r'\+\s*(\d+)%\s*/\s*Level', text, re.I)
        events.append({'event_id': area['area'], 'dungeon_id': area['first_dungeon'],
                       'dungeon_ids': area['dungeons'], 'name': area['name'],
                       'menu_background': area['filename'], 'reward_banner_id': str(900000000 + int(area['area'])),
                       'source_url': area['source_page'], 'source_revision': page['revisions'][0]['revid'],
                       'reconstructed_scoring': reconstructed,
                       'mission_points': points, 'raid_coin': {'kind': 20, 'id': next(iter(coins))} if coins else None,
                       'points_per_coin': 10, 'level_bonus_percent': int(rate[1]) if rate else 0,
                       'solo_pacing': {'shared_hp_per_level': 40000000, 'authored': True},
                       'personal_milestones': rewards, 'status': 'Recovered Global event data'})
    output = ROOT / 'source/server/raid_archive.json'
    output.write_text(json.dumps({'version': 1, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'events': events}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    (ROOT / 'source/build/raid-archive-gaps-20261026.json').write_text(json.dumps(gaps, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Recovered', len(events), 'separate raids;', sum(len(row['personal_milestones']) for row in events), 'personal milestones;', len(gaps), 'source/mapping gaps')


if __name__ == '__main__':
    main()
