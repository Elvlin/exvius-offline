"""Recover EX-bonus masters from the preserved Memorial asset pack.

Original Global rows always win for shared ability/recipe IDs. This adds the
missing bonus definitions and their referenced native skill dependencies.
"""
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import zipfile

from decode_client_data import client_manifest, decode

ROOT = Path(__file__).resolve().parents[2]

PREFIXES = {
    'D.エレメンタルバースト': 'D. Elemental Burst', 'H.エレメンタルバースト': 'H. Elemental Burst',
    'I.エレメンタルバースト': 'I. Elemental Burst', 'TA.エレメンタルバースト': 'TA. Elemental Burst',
    'LBエクステンション': 'LB Extension', 'LBチャージ': 'LB Charge', 'Tアビリティ': 'Triple Ability',
    'Wフィールド・火氷': 'Double Field: Fire and Ice', 'かばう・全': 'Cover All',
    'アタックウォール': 'Attack Wall', 'インビンシブルシールド': 'Invincible Shield',
    'ウォタフィールド': 'Water Field', 'ウォタリストリクト': 'Water Restrict', 'ウォール': 'Wall',
    'エアロフィールド': 'Wind Field', 'エナジーレゾナンス': 'Energy Resonance',
    'オフェンスクラッシュ': 'Offense Crush', 'ガードクラッシュ': 'Guard Crush',
    'サンダフィールド': 'Lightning Field', 'スキルソウル': 'Skill Soul', 'ストンフィールド': 'Earth Field',
    'ダークフィールド': 'Dark Field', 'ダークリストリクト': 'Dark Restrict',
    'デヴァステイトブリザ': 'Devastating Blizzard', 'トータルエクステンション': 'Total Extension',
    'トータルライズ': 'Total Rise', 'バーストサモン': 'Burst Summon', 'バーストソウル': 'Burst Soul',
    'バーストフォース': 'Burst Force', 'バーストラディエイト': 'Burst Radiate',
    'パラメーターインクリーズ': 'Stat Increase', 'ヒプノシスミラージュ': 'Hypnosis Mirage',
    'ヒューマンウォール': 'Human Wall', 'ファイアフィールド': 'Fire Field', 'ファイアブースト': 'Fire Boost',
    'フォースアクセレイト': 'Force Acceleration', 'フォースエンハンス': 'Force Enhance',
    'フルエクステンション': 'Full Extension', 'ブリザフィールド': 'Ice Field',
    'ブレイクウォタ': 'Water Break', 'ブレイクエアロ': 'Wind Break', 'ブレイクサンダ': 'Lightning Break',
    'ブレイクストン': 'Earth Break', 'ブレイクダーク': 'Dark Break', 'ブレイクファイア': 'Fire Break',
    'ブレイクライト': 'Light Break', 'プラントハンター': 'Plant Hunter',
    'マルチブレイク・水光': 'Multi Break: Water and Light',
    'マルチブレイク・火水風土': 'Multi Break: Fire, Water, Wind and Earth',
    'マルチリストリクト・火雷光': 'Multi Restrict: Fire, Lightning and Light',
    'ライトフィールド': 'Light Field', 'レジストダウン': 'Resistance Down',
    '光の闘域': 'Domain of Light', '闇の闘域': 'Domain of Darkness',
    '剣の道を征く者・凱歌II': "Way of the Sword: Victory II", '幸運の星': 'Lucky Star',
    '攻防魔精エクステンション': 'ATK, DEF, MAG and SPR Extension',
    '攻防魔精リダクション': 'ATK, DEF, MAG and SPR Reduction',
    '攻魔精固定値アップ：1000': 'ATK, MAG and SPR +1000', '攻魔精固定値アップ：900': 'ATK, MAG and SPR +900',
    '未来を担いし緋き英雄': 'Crimson Hero of the Future', '真・りょうてもち(魔)': 'True Doublehand (MAG)',
    '破壊と再生の王': 'King of Destruction and Rebirth', '祝祭/剣の道の凱歌': 'Festival: Victory of the Sword',
    '討滅の力・虫&死霊': 'Extermination: Insects and Undead', '魔力供給場展開': 'Deploy Magic Supply Field'}


def main():
    manifest = client_manifest(ROOT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
    by_table = {r['table']: (token, r['key']) for token, r in manifest.items()}
    provenance = []

    def recovered(table):
        token, key = by_table[table]
        paths = list((ROOT / 'data/memorial/external').rglob(token + '.dat'))
        assert len(paths) == 1, table
        body = paths[0].read_bytes()
        provenance.append({'table': table, 'path': paths[0].relative_to(ROOT).as_posix(),
                           'sha256': hashlib.sha256(body).hexdigest()})
        return decode(body, key)[1]

    def original(table, key):
        return {r[key]: r for r in map(json.loads, (ROOT / 'data/mst_decoded' / (table + '.ndjson'))
                                     .read_text(encoding='utf8').splitlines())}

    bonus = recovered('F_UNIT_EX_BONUS_MST')
    acquire = [r for r in recovered('F_UNIT_SERIES_LV_ACQUIRE_MST') if r.get('59kRbpKz') == '1']
    pieces = recovered('F_UNIT_SERIES_NV_PIECE_MST')
    units = original('F_UNIT_MST', '3HriTp6B')
    ex_steps = list(original('F_NV_EX_CLASS_UP_MST', 'JPW8Vs40').values())
    adjustments = []
    for piece in pieces:
        master = units.get(piece['woghJa61'])
        step = next((s for s in ex_steps if master and s['JPW8Vs40'] == master['JPW8Vs40']), None)
        if step:
            cost = step['KCk8u0am'].split(',')[0].split(':')
            assert cost[0] == '20' and len(cost) == 3
            if piece['tL6G9egd'] != cost[1]:
                adjustments.append({'series': piece['woghJa61'], 'memorial_fragment': piece['tL6G9egd'],
                                    'global_fragment': cost[1]})
                piece['tL6G9egd'] = cost[1]
    provenance.append({'global_fragment_bindings': adjustments,
                       'source': 'Original Global F_NV_EX_CLASS_UP_MST.KCk8u0am'})
    subs = recovered('F_SUBLIMATION_RECIPE_MST')
    abilities = {r['Ga5V42LZ']: r for r in recovered('F_ABILITY_MST')}
    original_skills = original('F_ABILITY_MST', 'Ga5V42LZ')
    original_subs = original('F_SUBLIMATION_RECIPE_MST', 'SJ56uhz2')
    recipe_ids = {r['xHZj7Va5'] for r in bonus if r['xm7c08IS'] == '8'}
    needed_subs = [r for r in subs if r['SJ56uhz2'] in recipe_ids and r['SJ56uhz2'] not in original_subs]
    assert recipe_ids <= set(original_subs) | {r['SJ56uhz2'] for r in needed_subs}
    needed_skills = {r['xHZj7Va5'] for r in bonus if r['xm7c08IS'] == '7'}
    assert {sid for r in acquire for sid in r['1Zsh27mS'].split(',') if sid} <= needed_skills
    needed_skills.update(r[k] for r in needed_subs for k in ('hxu12ZFS', 'Q1n9iYgz'))
    pending, additions, visited = deque(sorted(needed_skills)), {}, set()
    while pending:
        sid = pending.popleft()
        if sid in visited or sid in original_skills:
            continue
        visited.add(sid)
        assert sid in abilities, 'Missing native ability ' + sid
        row = abilities[sid]
        additions[sid] = row
        # Native effect lists can call another ability (cooldowns, multicast,
        # counters, replacements). Include actual referenced master IDs only.
        for value in row.values():
            for candidate in re.findall(r'\b\d{5,9}\b', str(value)):
                if candidate in abilities and candidate not in original_skills and candidate not in visited:
                    pending.append(candidate)
    unit_names = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in map(json.loads,
                  (ROOT / 'data/text_decoded/F_TEXT_UNITS_NAME.ndjson').read_text(encoding='utf8').splitlines())}
    unit_captions = {r['G4L0YIB2']: unit_names[r['3HriTp6B']] for r in
                     original('F_UNIT_MST', '3HriTp6B').values() if r['3HriTp6B'] in unit_names}
    unit_captions.update({'ALL': 'All', 'クリスマスドミノ': 'Christmas Domino', 'ルイーズ': 'Louise',
                         '獄氷帝ヴラド': 'Ice Emperor Vlad', '白竜の舞姫リン': 'White Dragon Dancer Ling',
                         '黒鳳剣ヒョウ': 'Black Phoenix Sword Hyoh'})
    english = {r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in map(json.loads,
               (ROOT / 'data/text_decoded/F_TEXT_ABILITY_NAME.ndjson').read_text(encoding='utf8').splitlines())}
    english.update({r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in map(json.loads,
                   (ROOT / 'data/text_decoded/F_TEXT_MAGIC_NAME.ndjson').read_text(encoding='utf8').splitlines())})
    english.update({r['key'].rsplit('_', 1)[-1]: r['v'][0] for r in map(json.loads,
                   (ROOT / 'data/text_decoded/F_TEXT_LIMIT_BURST_NAME.ndjson').read_text(encoding='utf8').splitlines())})
    english.update({'1116141': 'Twin Dragon Fang Flame', '100039207': 'Cyclone Combination',
                    '100039217': 'Fantasia Slay', '1334020': 'Liberate of Dragoon',
                    '1216010': 'Meteor (Angel Wing)', '1216011': 'Meteor (Angel Wing)',
                    '1216012': 'Meteor (Angel Wing)', '1417060': 'Ronso Jump+'})
    for sid, row in additions.items():
        name, _, qualifier = row['G4L0YIB2'].partition('【')
        assert name in PREFIXES, name
        english[sid] = PREFIXES[name] + (' (' + unit_captions[qualifier.rstrip('】')] + ')' if qualifier else '')
    datamine = next((ROOT / 'repository snapshots').glob('kaikwb__ffbe-data-jp*'))
    provenance.append({'descriptions': datamine.relative_to(ROOT).as_posix(),
                       'sha256': hashlib.sha256(datamine.read_bytes()).hexdigest(),
                       'translation': 'Skill captions translated here; published parsed English effects and explicit native-master translations.'})
    with zipfile.ZipFile(datamine) as archive:
        mined = {}
        for name in ('skills_ability.json', 'skills_passive.json', 'skills_magic.json'):
            member = next(n for n in archive.namelist() if n.endswith('/' + name))
            mined.update(json.loads(archive.read(member)))
    selected_subs = {r['SJ56uhz2']: r for r in needed_subs}
    selected_subs.update(original_subs)
    caption_ids = set(additions)
    for rid in recipe_ids:
        row = selected_subs[rid]
        sid = row['Q1n9iYgz']
        caption_ids.add(sid)
        english.setdefault(sid, english[row['hxu12ZFS']])
    # Existing Global masters also contain untranslated future upgrades and
    # their cooldown payloads. Recover their text without replacing valid GL text.
    native_names = {**original_skills, **abilities}
    names = {native_names[sid]['G4L0YIB2']: name for sid, name in english.items()
             if sid in native_names and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', name)}
    pending = deque(sorted(caption_ids))
    while pending:
        sid = pending.popleft()
        if sid not in mined:
            continue
        effects = str(mined[sid]['effects'])
        for group in re.findall(r'\(([\d, ]{5,})\)', effects):
            for ref in map(str.strip, group.split(',')):
                if ref not in mined or ref not in native_names or ref in caption_ids:
                    continue
                caption_ids.add(ref)
                pending.append(ref)
                if ref not in english:
                    english[ref] = (english[sid] if mined[ref]['name'] == mined[sid]['name']
                                    else names.get(native_names[ref]['G4L0YIB2'], ''))
    def translate_reference(match):
        return english.get(match[2].split(',')[0].strip(), match[1]) + ' (' + match[2] + ')'
    captions, descriptions, unresolved, missing = {}, [], [], []
    native_descriptions = {
        '111410': 'Increase ATK, MAG and SPR by 900.',
        '111420': 'Increase ATK, MAG and SPR by 1000.',
        '121060': 'Increase equipment MAG by 100% when armed with a single weapon.',
        '150000': 'Reduce fire resistance of all enemies. Imbue caster with fire and increase fire damage of the caster\'s limit bursts, abilities and magic.',
        '3000310': 'Increase ATK and MAG by 200% for units in the Way of the Sword category.',
        '3000311': 'Increase ATK and MAG by 100% for units in the Anniversary Story or Way of the Sword categories.',
        '3000301': 'Increase ATK and MAG by 1500% and DEF and SPR by 200% for units in both All Elements and Crystal\'s Blessing categories. Other All Elements units gain ATK and MAG +1200% and DEF and SPR +200%.',
        '3000331': 'Increase ATK and MAG by 1500% and DEF and SPR by 200% for units in the Way of the Sword category.',
        '3000361': 'Increase ATK and MAG by 1700% and DEF and SPR by 200% for units in both Elite Soldiers and Fire categories. Other Elite Soldiers units gain ATK and MAG +1500% and DEF and SPR +200%.'}
    for sid in sorted(caption_ids):
        if sid not in mined and sid not in native_descriptions:
            missing.append((sid, native_names[sid]['G4L0YIB2']))
            continue
        text = native_descriptions.get(sid) or '; '.join(str(effect) for group in mined[sid]['effects'] for effect in group)
        text = re.sub(r'([\u3040-\u30ff\u3400-\u9fff][^;]*?) \(([\d, ]+)\)', translate_reference, text)
        text = re.sub(r"Unknown passive effect type '106': \[\"none\"\]",
                      'Increase maximum chain damage limit by 200% when armed with two weapons', text)
        text = re.sub(r"Unknown active effect type '172': \[(\d+),0,(\d+),1\]",
                      r'Increase evocation damage by \1% to caster for \2 turns', text)
        if re.search(r'[\u3040-\u30ff\u3400-\u9fff]|Unknown', text):
            unresolved.append((sid, text))
        if not english.get(sid) or re.search(r'[\u3040-\u30ff\u3400-\u9fff]', english[sid]):
            missing.append((sid, native_names[sid]['G4L0YIB2']))
        captions[sid] = {'name': english.get(sid, ''), 'description': text}
        descriptions.append({'Ga5V42LZ': sid, 'T7aEx3Mj': text})
    assert not (unresolved or missing), {'untranslated': unresolved, 'missing': missing}
    tables = {
        'F_UNIT_EX_BONUS_MST': {'key': 'L3Nx1Jpb', 'rows': bonus},
        'F_UNIT_SERIES_NV_PIECE_MST': {'key': 'woghJa61', 'rows': pieces},
        'F_UNIT_SERIES_LV_ACQUIRE_MST': {'key': None, 'rows': acquire},
        'F_SUBLIMATION_RECIPE_MST': {'key': 'SJ56uhz2', 'rows': needed_subs},
        'F_ABILITY_MST': {'key': 'Ga5V42LZ', 'rows': list(additions.values())},
        'F_ABILITY_EXPLAIN_MST': {'key': 'Ga5V42LZ', 'rows': descriptions}}
    output = ROOT / 'source/server/content/exbonus_masters.json'
    output.write_text(json.dumps({'sources': provenance, 'tables': tables}, ensure_ascii=False,
                                 separators=(',', ':')) + '\n', encoding='utf8')
    output.with_name('exbonus_text.json').write_text(json.dumps(captions, ensure_ascii=False,
                                                             separators=(',', ':')) + '\n', encoding='utf8')
    print('Recovered EX-bonus masters:', {k: len(v['rows']) for k, v in tables.items()})


if __name__ == '__main__':
    main()
