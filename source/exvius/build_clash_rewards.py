"""Import all 99 original level rewards for each preserved Global CoW season."""
import json
from pathlib import Path
import re

from build_raid_archive import name_tables, reward, plain, item_key
from build_event_archive import rows
from player_state import max_level

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = ROOT / 'logs/reference/event-battle-clash-wiki-20261028.json'
    pages = {p['title']: p for p in json.loads(source.read_text(encoding='utf8'))[0]['query']['pages'].values()}
    missions = rows('F_MISSION_MST')
    names = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in rows('F_TEXT_MISSION', text=True)}
    titles = {r['uv60hgDW']: names[r['qo3PECw6']] for r in missions if r['gQR24kST'] == '50'}
    emblems = {item_key(r['G4L0YIB2']): int(r['0w6XzofV']) for r in rows('F_EMBLEM_ITEM_MST')}
    # Wiki captions and shipped emblem names differ for these same bosses.
    emblems.update({item_key(name): iid for name, iid in {
        "Empress's Faceted Sigil": 90045, "Beast's Faceted Sigil": 90070,
        "Dragon Spirit's Faceted Sigil": 90078, "Trickster's Faceted Sigil": 90086,
        "Manticore's Faceted Sigil": 90095, "Champion's Faceted Sigil": 90107,
        "Automaton's Faceted Sigil": 90111, "Dark Swordswoman's Faceted Sigil": 90140,
        "Sea Serpent's Faceted Sigil": 90178, "Evil Deity's Faceted Sigil": 90186}.items()})
    tables = name_tables()
    seasons = {}
    for area, title in titles.items():
        page = pages[title]
        text = page['revisions'][0]['slots']['main']['*']
        section = re.search(r'=== Individual Rewards ===(.*?)(?:Ranking=|=== Ranking Rewards ===)', text, re.S)[1]
        levels = {}
        for level, value in re.findall(r'^\|\s*(\d+)\s*\|\|\s*([^\n]+)', section, re.M):
            entry = {'rewards': [], 'emblems': []}
            if 'Emblem-' in value:
                label = re.search(r'Emblem-([^]|]+)\.png', value)[1].replace('_', ' ')
                if item_key(label) not in emblems:
                    raise ValueError('Unmapped emblem: ' + label)
                entry['emblems'].append(emblems[item_key(label)])
            else:
                for part in re.split(r'<br\s*/?>', value, flags=re.I):
                    item = re.search(r'\{\{Item\|([^|}]+)\|([\d,]+)\}\}', part, re.I)
                    if item:
                        name, count = item[1], int(item[2].replace(',', ''))
                        if name == 'Lapis Replica (8th Anniversary)':
                            grant = {'kind': 20, 'id': 1209002122, 'count': count}
                        else:
                            grant = reward(name + f' ({count})', '', tables, {})
                    elif plain(part).startswith('Dark Matter ('):
                        grant = {'kind': 20, 'id': 235018200, 'count': int(re.search(r'\((\d+)\)', plain(part))[1])}
                    else:
                        grant = reward(part, '', tables, {})
                    if grant['kind'] == 10 and 'Trust Moogle' in plain(part):
                        percent = int(re.search(r'ALL\s+(\d+)%', plain(part))[1])
                        grant['affinity_points'] = [str(percent * 10), '']
                        grant['affinity_info'] = ['', '']
                    if grant['kind'] == 10 and 'Max level' in part:
                        grant['level'] = max_level(grant['id'])
                    entry['rewards'].append(grant)
            levels[level] = entry
        if set(levels) != {str(n) for n in range(1, 100)}:
            raise ValueError('Incomplete level rewards: ' + title)
        ranking_text = text.split('=== Ranking Rewards ===', 1)[1].split('</tabber>', 1)[0]
        ranking = []
        for rank, value in re.findall(r'^\|\s*(?:align="center"\s*\|\s*)?(\d[\d,\s+<>=-]*)\s*\|\|\s*([^\n]+)', ranking_text, re.M):
            labels = [plain(part).strip() for part in re.split(r'<br\s*/?>', value, flags=re.I)
                      if not part.strip().startswith('[[File:')]
            ranking.append({'rank': rank.strip(), 'rewards': [label for label in labels if label]})
        if not ranking:
            raise ValueError('Missing published ranking rewards: ' + title)
        seasons[area] = {'name': title, 'source_page': 'https://exvius.fandom.com/wiki/' + title.replace(' ', '_'),
                         'source_revision': page['revisions'][0]['revid'], 'levels': levels, 'ranking': ranking}
    target = ROOT / 'source/server/content/clash_level_rewards.json'
    target.write_text(json.dumps({'version': 1, 'seasons': seasons}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf8')
    print('Imported original Clash level rewards:', len(seasons), 'seasons,', sum(len(s['levels']) for s in seasons.values()), 'levels')


if __name__ == '__main__':
    main()
