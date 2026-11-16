"""Restore Kira from the preserved native Memorial roster and add English text."""
from pathlib import Path
import hashlib
import io
import json
import os
import tempfile
import zipfile

from decode_client_data import client_manifest, decode
from prepare_offline_cache import DATA, PROJECT, exbonus_master, loading_text, localized_text_versions


FORMS = {'346000207', '346000217'}
EVENT = 'Vow of the Revived Legend'
GUIDE = 'https://altema.jp/ffbe/yomigaesiridennsetunotikai'
MONSTER = 'Beast King Gnon'
SKILLS = {'222979': 'Flying Attack', '222980': 'Flame Breath',
          '222981': 'Beast King’s Roar', '222982': 'Beast King’s Sweeping Strike'}
STAGES = ('ATK Pots', 'DEF Pots', 'MAG Pots', 'SPR Pots', 'MP Pots', 'HP Pots',
          'Burst Pots', 'Kira Fragments')
MISSIONS = [str(62110100 + level) for level in range(1, 9)]
BANNER = 'event_6211.png'
RULE_CATEGORIES = 'Only units in the Another World or FFBE S4 category can enter.'
LB_DESCRIPTIONS = {
    '346000207': 'Lowers sword resistance, DEF, and dark resistance for one enemy, then deals dark physical damage.',
    '346000217': 'Lowers sword resistance, DEF, SPR, and dark resistance for one enemy, then deals dark physical damage.',
}
BIO = ("A swordsman from a distant world. Outgoing and loyal, Kira became one of Arus's closest friends "
       "while training under the sage Kadal. When he fought his brother Servain, who was under the sway "
       "of a cursed sword, Kira learned he was descended from the Sword King. He returned to his home "
       "village to master a technique for wielding cursed blades, then rejoined Arus.")
ABILITIES = {
    '1190000': ('Attack', 'Deals physical damage to one enemy and fills the caster’s LB gauge.'),
    '1190010': ('Triple Ability', 'Casts certain abilities three times.'),
    '1190020': ('Cursed Blade Shockwave', 'Deals dark physical damage to one enemy.'),
    '1190030': ('Sword King’s Slash', 'Deals physical damage to all enemies.'),
    '1190040': ('Vacuum Fang: Straight Slash', 'Deals physical damage to one enemy and deals damage each turn.'),
    '1190090': ('Heh… Time to Cut Loose!', 'Boosts the caster’s dark damage, ATK, LB damage, and the power of specific LBs. Available once every four turns.'),
    '1190100': ('Sword King’s Command', 'Increases physical and magic damage against beastmen for all allies.'),
    '1190110': ('Holy Warrior’s Oath: Sword King', 'Increases base ATK by 1,500 and grants 100% resistance to ATK, DEF, MAG, and SPR reductions.'),
    '1190120': ('Wheel Eye', 'Increases equipment ATK by 100% when single-wielding.'),
    '1190130': ('The Three Sword Kings', 'Increases ATK, DEF, MAG, and SPR by 100%.'),
}
for level in range(1, 5):
    name, description = ABILITIES['1190040']
    ABILITIES[str(1190040 + 10 * level)] = (f'{name} +{level}', description)


def build(output):
    original_apk = PROJECT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk'
    tables = {row['table']: (token, row['key']) for token, row in client_manifest(original_apk).items()}
    native = DATA / 'client/files'
    overlay = DATA / 'overlay'
    unit_token, unit_key = tables['F_UNIT_MST']
    memorial = next((DATA / 'memorial/client/files/side_stories').rglob(unit_token + '.dat'))
    _, roster = decode(memorial.read_bytes(), unit_key)
    units = [row for row in roster if row['3HriTp6B'] in FORMS]
    assert {row['3HriTp6B'] for row in units} == FORMS
    challenges = {row['V36ygRYs']: row for row in
                  map(json.loads, (DATA / 'mst_decoded/F_CHALLENGE_MST.ndjson').read_text('utf-8').splitlines())
                  if row['qo3PECw6'] in MISSIONS}
    challenge_labels = {'68': 'Complete the quest', '1': 'Clear without using items',
                        '38': 'Clear without continuing', '33': 'Clear without any allies being KO’d',
                        '73:5': 'Clear within 5 turns'}
    challenge_rewards = {
        'MST_CHALLENGE_REWARD_DETAIL_' + cid: 'Cactuar Emperor (Kira)'
        for cid, row in challenges.items() if row['dX6cor8j'].startswith('10:902000605:')
    }
    points = json.loads((PROJECT / 'source/server/content/series_point_rewards.json').read_text('utf-8'))
    points = points['tables']['F_UNIT_SERIES_POWER_UP_POINT_MST']['rows']
    english = {
        'F_TEXT_UNITS_NAME': {'MST_UNIT_NAME_' + form: 'Kira' for form in FORMS},
        'F_TEXT_ABILITY_NAME': {'MST_ABILITY_NAME_' + key: row[0] for key, row in ABILITIES.items()},
        'F_TEXT_ABILITY_EXPLAIN_SHORT': {'MST_ABILITY_SHORTDESCRIPTION_' + key: row[1]
                                         for key, row in ABILITIES.items()},
        'F_TEXT_LIMIT_BURST_NAME': {
            'MST_LIMITBURST_NAME_346000207': 'Sword King’s Vacuum Fang',
            'MST_LIMITBURST_NAME_346000217': 'Sword King’s Thunderblade Fang',
        },
        'F_TEXT_LIMIT_BURST_DES': {'MST_LIMITBURST_DESCRIPTION_' + form: description
                                  for form, description in LB_DESCRIPTIONS.items()},
        'F_TEXT_ITEM_EQUIP_NAME': {'MST_EQUIP_ITEM_NAME_406007900': 'Black Caesar'},
        'F_TEXT_ITEM_NAME': {'MST_ITEM_NAME_250016900': 'Kira Fragment'},
        'F_TEXT_MATERIA_NAME': {'MST_MATERIA_NAME_504244202': 'Warrior Fulcas’s Teachings'},
        'F_TEXT_VISION_CARD_NAME': {'MST_VISION_CARD_NAME_346000201': 'The Sword Kings Assemble!'},
        'F_TEXT_AREA_NAME': {'MST_AREA_NAME_6211': EVENT},
        'F_TEXT_DUNGEON_NAME': {'MST_DUNGEONS_NAME_621101': EVENT},
        'F_TEXT_MISSION': {'MST_MISSION_NAME_' + mid: f'Lv. {level} - {name}'
                           for level, (mid, name) in enumerate(zip(MISSIONS, STAGES), 1)},
        'F_TEXT_CHALLENGE_NAME': dict(challenge_rewards, **{
            'MST_CHALLENGE_NAME_' + cid: challenge_labels[row['Pzn5h0Ga']]
            for cid, row in challenges.items() if row['Pzn5h0Ga'] in challenge_labels}),
        'F_TEXT_UNIT_SERIES_POWER_UP': {'MST_UNIT_POWER_UP_NAME_' + row['RvN2W9Qx']: row['G4L0YIB2']
                                       for row in points if row['woghJa61'] == '346000207'},
        'F_TEXT_RULE_DESCRIPTION': {'MST_RULE_DESC_4036': 'Use a party that meets the category requirement.',
                                    'MST_RULE_COND_4036': RULE_CATEGORIES},
        'F_TEXT_MONSTER_NAME': {'MST_MONSTER_NAME_' + mid: MONSTER
                               for mid in ['3014310'] + [str(301431000 + level) for level in range(1, 9)]},
        'F_TEXT_MONSTER_SKILL_NAME': {'MST_MONSTER_SKILL_NAME_' + key: name for key, name in SKILLS.items()},
    }
    index, index_key = tables['F_LOCALIZED_TEXT_MST']
    current = overlay / 'mst' / f'Ver710_{index}.dat'
    _, index_rows = decode(current.read_bytes(), index_key)
    versions = {row['a4hXTIm0']: row['00zAYGYS'] for row in index_rows}
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        temp = Path(scratch)
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            # Vortex reads Farplane town 9001 while opening.
            town = 'mst/Ver64_6P9XZ7ts.dat'
            archive.write(native / town, 'native/' + town)
            rules = 'mst/Ver125_7s4egUBN.dat'
            archive.write(native / rules, 'native/' + rules)
            banner = 'en/sd/area/' + BANNER
            archive.write(overlay / banner, 'native/' + banner)
            localized = {}
            for table, lines in english.items():
                token, key = tables[table]
                relative = Path('localized_texts/en') / f'Ver{versions[table]}_{token}.dat'
                source = overlay / relative
                if not source.is_file():
                    source = native / relative
                target = temp / source.name
                loading_text(source, target, key, lines, append_missing=True)
                localized[table] = (source.name.split('_', 1)[0][3:], target)
                archive.write(target, 'native/' + relative.as_posix())
                _, rows = decode(target.read_bytes(), key, localized=True)
                archive.writestr(f'static/text_decoded/{table}.ndjson', ndjson(rows))
            localized_text_versions(current, temp / current.name, index_key, localized)
            archive.write(temp / current.name, 'native/mst/' + current.name)

            changes = {
                'F_UNIT_MST': ('3HriTp6B', units),
                'F_UNIT_EXPLAIN_MST': ('3HriTp6B', [
                    {'3HriTp6B': form, 'fYhnz5N9': BIO, 'BGWpF0i2': 'Heh…<br>Time to cut loose!'}
                    for form in sorted(FORMS)]),
                'F_LIMITBURST_MST': ('PR2HIc71', [
                    {'PR2HIc71': form, '6uvHX2JG': description}
                    for form, description in LB_DESCRIPTIONS.items()
                ]),
                'F_ABILITY_EXPLAIN_MST': ('Ga5V42LZ', [
                    {'Ga5V42LZ': key, 'T7aEx3Mj': row[1]} for key, row in ABILITIES.items()]),
                'F_EQUIP_ITEM_MST': ('J1YX9kmM', [
                    {'J1YX9kmM': '406007900', 'G4L0YIB2': 'Black Caesar'}]),
            }
            for table, (identity, patches) in changes.items():
                token, key = tables[table]
                source = (overlay / 'mst' / f'Ver404_{token}.dat' if table == 'F_ABILITY_EXPLAIN_MST'
                          else next(native.glob(f'mst/Ver*_{token}.dat')))
                _, original = decode(source.read_bytes(), key)
                rows = {row[identity]: row for row in original}
                replacement = [dict(rows.get(row[identity], {}), **row) for row in patches]
                restored = {'key': identity, 'rows': replacement, 'replace': table != 'F_UNIT_MST'}
                target = temp / source.name
                exbonus_master(source, target, key, table, restored)
                _, merged = decode(target.read_bytes(), key)
                assert {row[identity]: row for row in merged} == dict(rows, **{
                    row[identity]: row for row in replacement})
                archive.write(target, 'native/mst/' + source.name)
                from native_master_index import paired_index
                paired = paired_index(table, target, target.read_bytes(), key)
                if paired is not None:
                    archive.writestr('native/mst/' + paired[0].name, paired[1])
                archive.writestr(f'static/mst_decoded/{table}.ndjson', ndjson(merged))
    print(f'{output}: {output.stat().st_size:,} bytes')


def ndjson(rows):
    return ''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows)


def build_banner():
    from cricodecs import cpk
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    def original(pack, name):
        archive = cpk.load(str(DATA / 'client/files/common_lang/sd' / pack))
        index = next(i for i, entry in enumerate(archive.file_infos()) if entry.full_path == name)
        return Image.open(io.BytesIO(archive.file_bytes(index))).convert('RGBA')

    background = original('battlebg/Ver2_battleBg_ex11_q4VC3KaL_common.cpk', 'battle_bg_3025_2.jpg')
    banner = ImageOps.fit(background.crop(background.convert('RGB').getbbox()), (640, 240),
                          Image.Resampling.LANCZOS)
    banner = Image.alpha_composite(banner, Image.new('RGBA', banner.size, (12, 14, 25, 156)))
    kira = original('unit/Ver4_unit24_common.cpk', 'unit_ills_346000207.png')
    kira = kira.crop(kira.getbbox())
    kira = ImageOps.contain(kira, (205, 188), Image.Resampling.NEAREST)
    banner.alpha_composite(kira, (421 + (205 - kira.width) // 2, (240 - kira.height) // 2))
    fonts = Path(os.environ['WINDIR']) / 'Fonts'
    draw = ImageDraw.Draw(banner)
    draw.text((27, 38), 'DRAGON QUEST COLLAB', font=ImageFont.truetype(str(fonts / 'arialbd.ttf'), 18),
              fill='#ffdb94', stroke_width=1, stroke_fill='#15101a')
    draw.multiline_text((25, 69), 'Vow of the\nRevived Legend', spacing=2,
                        font=ImageFont.truetype(str(fonts / 'georgiab.ttf'), 41),
                        fill='#fff0c5', stroke_width=2, stroke_fill='#1e101b')
    draw.text((28, 179), 'Clear Lv. 1 to recruit Kira', font=ImageFont.truetype(str(fonts / 'arialbd.ttf'), 21),
              fill='#fff6e5', stroke_width=1, stroke_fill='#18121f')
    target = DATA / 'overlay/en/sd/area' / BANNER
    banner.save(target, optimize=True)
    path = target.relative_to(PROJECT).as_posix()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    metadata = PROJECT / 'source/server/event_art.json'
    art = json.loads(metadata.read_text('utf-8'))
    art['events']['6211'] = {'filename': BANNER, 'source_file': path, 'runtime_file': path,
                             'source_sha256': digest, 'runtime_sha256': digest,
                             'source_page': GUIDE, 'source_size': [640, 240], 'runtime_size': [640, 240]}
    metadata.write_text(json.dumps(art, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def restore_event():
    from battle_content import Source, _default_index_source, derive_mission

    base = _default_index_source()
    monsters, parts = [], []
    drops = ('28:346000213:1:100', '28:346000214:1:100', '28:346000215:1:100',
             '28:346000216:1:100', '28:346000212:1:100', '28:346000211:1:100',
             '10:905000103:1:100', '20:250016900:5:100')
    for level, drop in enumerate(drops, 1):
        part = str(301431000 + level)
        reference = derive_mission(62210100 + level, base)['bV34YIJQ'][0]
        monsters.append({'xqartN26': part, 'G4L0YIB2': MONSTER, 'V9j8wJcC': '3014310'})
        # Native AI 131 reads the nine preserved skill slots in three turns.
        parts.append(dict(reference, xqartN26=part, G4L0YIB2=MONSTER, a9qg8vnP='1',
                          A5x02C6a='301431001', **{'8a6gAwN9': '131',
                          '5A8SmwyC': '40:5028810:1:1:0', 'hn42BL3Q': '0,0,0,0,0,0,0,0,0',
                          '9BetM2Ds': drop}))

    class GnonSource(Source):
        def load(self, table):
            rows = base.load(table)
            if table == 'F_MONSTER_MST':
                return rows + monsters
            if table == 'F_MONSTER_PARTS_MST':
                return rows + parts
            if table == 'F_MONSTER_SKILL_MST':
                return [dict(row, G4L0YIB2=SKILLS[row['6E5u1xrs']])
                        if row['6E5u1xrs'] in SKILLS else row for row in rows]
            return rows

    server = PROJECT / 'source/server'
    encounters = server / 'event_encounters.json'
    document = json.loads(encounters.read_text('utf-8'))
    for mid in MISSIONS:
        bundle = derive_mission(int(mid), GnonSource())
        assert len(bundle['bV34YIJQ']) == 1 and bundle['wbet57nF'][0]['V9j8wJcC'] == '3014310'
        document['missions'][mid] = {'bundle': bundle, 'enemies': [MONSTER], 'source_url': GUIDE,
                                     'identity_source': 'Original mission, formation and skill records. '
                                     'Missing enemy stats reconstructed from the matching difficulty of 622101. '
                                     'The original skills run on the Global three-turn AI profile.'}
        document['local_monster_names'][bundle['bV34YIJQ'][0]['xqartN26'] + 'A'] = MONSTER
    encounters.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', 'utf-8')

    catalogue = server / 'event_archive.json'
    document = json.loads(catalogue.read_text('utf-8'))
    document['events'] = [{
        'area': '6211', 'name': EVENT, 'group': 'collaborations', 'release': '2022-11-22',
        'kind': 'Dragon Quest unit strengthening event', 'collaboration': 'Dragon Quest: Emblem of Roto',
        'dungeons': ['621101'], 'missions': MISSIONS, 'first_dungeon': '621101',
        'first_mission': MISSIONS[0], 'banner_title': EVENT, 'filename': BANNER,
        'source_page': GUIDE, 'date_source': GUIDE,
    }] + [row for row in document['events'] if row['area'] != '6211']
    catalogue.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n', 'utf-8')


if __name__ == '__main__':
    build_banner()
    restore_event()
    build(PROJECT / 'source/build/distribution/assets/exvius-kira-r7.zip')
