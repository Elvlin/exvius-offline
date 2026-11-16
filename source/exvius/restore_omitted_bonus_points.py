"""Bind restored daily bonus battles to their own parent Event Point rewards."""
import json
import re

from build_event_archive import ROOT, normal, rows
from build_raid_archive import item_key, plain, templates
from map_raid_summon_rewards import Resolver
from reconstruct_event_battles import fields

SOURCE = ROOT / 'logs/reference/restored-event-rewards-wiki-20261111.json'
SCOPE = {'3148': ('31500101', 'VS Specimen H0512'),
         '3175': ('31760101', 'VS Two-Headed Frost Dragon')}


def resolve_reward(raw, resolver):
    amount = re.search(r'\s*\(([\d,]+)\)\s*$', raw)
    count = int(amount[1].replace(',', '')) if amount else 1
    if amount:
        raw = raw[:amount.start()]
    macro = re.fullmatch(r'\s*\{\{(?:Item|Currency|Lapis|Gil)\|([^|}]+)(?:\|([\d,]+))?\}\}\s*', raw, re.I)
    if macro:
        if raw.lower().startswith('{{lapis|') or raw.lower().startswith('{{gil|'):
            return [{'kind': 50 if raw.lower().startswith('{{lapis|') else 30,
                     'id': 1, 'count': int(macro[1].replace(',', ''))}]
        raw, count = '[[' + macro[1] + ']]', int(macro[2].replace(',', '')) if macro[2] else count
    donor = re.fullmatch(r'\[\[Trust Moogle\]\]\s*<br\s*/?>\s*\(\[\[([^]]+)\]\]\s+(\d+)%\)', raw, re.I)
    if donor:
        candidates = resolver.names[10].get(item_key(donor[1]), [])
        infos = {resolver.units[str(uid)].get('9mu4boy7') for uid in candidates}
        infos.discard('')
        infos.discard(None)
        if not infos or len({tuple(value.split(':')[:3]) for value in infos}) != 1:
            raise ValueError('Ambiguous own unit-targeted Moogle: ' + raw)
        # The explicit source percentage overrides donation points; the original
        # unit's own TMR descriptor determines which reward it targets.
        return [{'kind': 10, 'id': 904000103, 'count': count,
                 'affinity_points': [str(int(donor[2]) * 10), ''],
                 'affinity_info': [sorted(infos)[0], '']}]
    return resolver.resolve({'wiki_label': raw, 'award_count': count})


def main():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    pages = {row['title']: row for row in source['query']['pages'].values() if row.get('revisions')}
    archive_path = ROOT / 'source/server/event_archive.json'
    catalogue = {row['area']: row for row in json.loads(archive_path.read_text(encoding='utf-8'))['events']}
    mission_names = {row['key'].rsplit('_', 1)[1]: row['v'][0]
                     for row in rows('F_TEXT_MISSION', text=True)}
    mission_rows = {row['qo3PECw6']: row for row in rows('F_MISSION_MST')}
    resolver = Resolver()
    restored, receipts = [], []
    for aid, (bonus_mid, bonus_title) in SCOPE.items():
        event = catalogue[aid]
        page = pages[event['name']]
        revision = page['revisions'][0]
        text = revision['slots']['main']['*']
        section = re.search(r'^==\s*Event Points\s*==(.*?)(?=^==[^=]|\Z)', text, re.M | re.S)
        if not section:
            raise ValueError('Own parent Event Point table absent: ' + aid)
        milestones = []
        for match in re.finditer(r'^\|\s*([\d,]+)\s+pts\s*\|\|\s*(.*?)\s*$', section[1], re.M):
            milestones.append({'points': int(match[1].replace(',', '')),
                               'label': plain(match[2]), 'rewards': resolve_reward(match[2], resolver)})
        points = {}
        for position, block in templates(text, 'Battle Infobox'):
            values = fields(block)
            found = re.search(r'([\d,]+)\s+event points', values.get('drop', ''), re.I)
            if not found:
                continue
            headings = re.findall(r'={2,}\s*(.*?)\s*={2,}', text[:position])
            title = normal(headings[-1])
            matches = [mid for mid in event['missions'] if normal(mission_names[mid]) == title]
            if len(matches) != 1:
                raise ValueError('Parent stage identity mismatch: ' + aid + ' ' + title)
            points[matches[0]] = int(found[1].replace(',', ''))
        bonus_page = pages[bonus_title]
        bonus_text = bonus_page['revisions'][0]['slots']['main']['*']
        bonus_points = re.search(r'\|drop\s*=\s*\x27*([\d,]+)\s+event points', bonus_text, re.I)
        if not bonus_points or not milestones or len(points) != 6:
            raise ValueError('Incomplete original Event Point contract: ' + aid)
        points[bonus_mid] = int(bonus_points[1].replace(',', ''))
        dids = list(event['dungeons'])
        dids.append(mission_rows[bonus_mid]['U9iHsau3'])
        restored.append({'event_id': aid, 'name': event['name'], 'dungeon_id': event['first_dungeon'],
            'dungeon_ids': dids, 'menu_background': event['filename'],
            'reward_banner_id': str(900000000 + int(aid)), 'point_mode': 'clear',
            'mission_points': points, 'raid_coin': None, 'points_per_coin': 10,
            'level_bonus_percent': 0, 'solo_pacing': {'shared_hp_per_level': 40000000, 'authored': True},
            'personal_milestones': milestones, 'source_url': event['source_page'],
            'source_revision': revision['revid']})
        receipts.append({'parent_area': aid, 'bonus_mission': bonus_mid, 'bonus_points': points[bonus_mid],
                         'milestones': len(milestones), 'parent_points': points})
    output = ROOT / 'source/server/raid_archive.json'
    document = json.loads(output.read_text(encoding='utf-8'))
    document['events'] = [row for row in document['events'] if str(row['event_id']) not in SCOPE] + restored
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'logs/ffbe-omitted-bonus-point-restoration-20261111.json').write_text(
        json.dumps({'events': receipts}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipts))


if __name__ == '__main__':
    main()
