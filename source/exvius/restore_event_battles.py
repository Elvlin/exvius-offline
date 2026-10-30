"""Reconstruct sourced Global event bundles through the existing authored path.

This does not replace Global master tables with Memorial tables. Provenance
distinguishes recovered values from explicitly approved reconstruction choices.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'source/server'))
import battle_content


def read_table(name):
    path = PROJECT / 'data/mst_decoded' / (name + '.ndjson')
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def morgana_lgd():
    archive = PROJECT / 'repository snapshots/aEnigmatic__ffbe-95727376e82d.zip'
    with zipfile.ZipFile(archive) as source:
        path = next(n for n in source.namelist() if n.endswith('/monster_skills.json'))
        skills = json.loads(source.read(path))
    units = {row['3HriTp6B']: row for row in read_table('F_UNIT_MST')}
    unit = units['401007007']
    source = battle_content.IndexSource()
    template = next(row for row in source.load('F_MONSTER_PARTS_MST')
                    if row['xqartN26'] == '205771000')
    part = {key: template.get(key, battle_content.PARTS_DEFAULTS.get(key, ''))
            for key in battle_content.PARTS_TOKENS}
    part.update({
        'xqartN26': '900010677', 'G4L0YIB2': 'Morgana',
        'fh31sk7B': '10000000', 'PC97pWQj': '100000',
        '9NBV1XCS': '400', 'Pn5w9dfh': '100', '84FJM3PD': '500', 'T8xMDAZ4': '300',
        'hn42BL3Q': '20,20,20,20,20,20,-50,20,20',
        'D9Nb7jgd': '100,100,100,100,100,100,100,100',
        'Rcqa1Zt7': '0,0,0,0,100,100,100', 'n0UEb71s': '80,100',
        '4Y2DGP7m': '10,10', '7wV3QZ80': '99',
        '8a6gAwN9': '900010671', 'A5x02C6a': '900010671',
        'B6H34Mea': '10000', '7UR4J2SE': '0', 'ATM35pjf': '0',
        '3HriTp6B': '401007007', 'a9qg8vnP': '5',
    })
    for token in ('5A8SmwyC', 'a9DvZ70c', '7KYufEd5', 'w04FtZqB', 'rtw4F6hn', 'rB70Ls63'):
        part[token] = unit[token]
    # Presentation defaults come from an existing unit-model enemy. They are
    # reconstruction choices, not a claim to have recovered the original row.
    native = {row['6E5u1xrs']: row for row in source.load('F_MONSTER_SKILL_MST')}
    skill_rows = []
    for sid, element in (('900305', 1), ('900306', 7), ('900307', 4),
                         ('900308', 7), ('900309', 6)):
        original = skills[sid]
        effects = original['effects_raw']
        row = copy.deepcopy(native['110060'])
        elements = ['0'] * 8
        elements[element] = '1'
        row.update({
            '6E5u1xrs': sid, 'G4L0YIB2': original['name'], '8cY9hejo': '0',
            'oPD4yL58': '@'.join(str(e[0]) for e in effects),
            'a4hXTIm0': '@'.join(str(e[1]) for e in effects),
            '2kq0BpnD': '@'.join(str(e[2]) for e in effects),
            'PI18xnkD': '@'.join('0' for e in effects),
            'Ha9G5sCS': '@'.join(','.join(str(v) for v in e[3]) for e in effects),
            'Jn6BbR2P': ','.join(elements),
            'Isb1GDe2': '2' if original['attack_type'] == 'Magic' else '4',
            '5w1o9DPV': '2' if original['attack_type'] == 'Magic' else '0',
            '7irj9hAb': ','.join(str(int(flag)) for flag in original['flags']),
        })
        skill_rows.append(row)
    mid, group = '9700112', '970011201'
    phase = {
        'qo3PECw6': mid, '6v7y3QcJ': '1', 'gou39JeI': '2', 'i2ar9yXM': '0',
        '5LZN8C9I': '0', 'YS9kfCX7': '400007', 'DYTx1Is3': '1000025',
        'T03qgLWA': '1', '2fY1IomW': group, '6uIYE15X': group, 'J9gafF0t': '0',
        'V2mCH5UR': '', 'juA0Z4m7': '', '1C7GDEv4': '', 'Us0znif6': '0',
        'k6Y8ysMA': '0', 'wTMK0x5p': '0:0:0:0',
    }
    drops = {'qo3PECw6': mid, '6v7y3QcJ': '1', 'pIHCrf40': '1',
             '2fY1IomW': group, 'xqartN26': '900010677', 'Z0EN6jSh': '1',
             '6Yc4RkdM': '1', '9BetM2Ds': '20:1209000976:450:100,20:1209000975:1200:100',
             'MZn8LC6H': '', 'g4voc2Aw': '', '3frn4ILX': '', 'IRf10dwx': '',
             'ATM35pjf': '', 'e5xoiC84': '', 'Vf5DGw07': ''}
    return {'an6TB4WS': [phase], 'Bi6hVv34': [{
                '2fY1IomW': group, 'xqartN26': '900010677', 'MxLFKZ13': '170,340',
                'Z0EN6jSh': '1', '3t7pZM5V': '2', 'WJdBp9f0': '1', 'm9BvFk2X': '1'}],
            'wbet57nF': [{'xqartN26': '900010677', 'G4L0YIB2': 'Morgana',
                          'V9j8wJcC': '10000050'}],
            'bV34YIJQ': [part], 'Wp39QX52': skill_rows, 'y35YvQjZ': [drops]}


class ReconstructionSource(battle_content.Source):
    def __init__(self, base, tables):
        self.base, self.tables = base, tables

    def load(self, table):
        return self.tables[table] if table in self.tables else self.base.load(table)


def reconstructed_stages(lgd):
    """Keep the established lottery/group/parts/skills assembly chain intact."""
    base = battle_content.IndexSource()
    parts = {r['xqartN26']: r for r in base.load('F_MONSTER_PARTS_MST')}
    monsters = {r['xqartN26']: r for r in base.load('F_MONSTER_MST')}
    missions = {r['qo3PECw6']: r for r in read_table('F_MISSION_MST')}
    gl_sets = read_table('F_MONSTER_SKILL_SET_MST')
    skill_rows = base.load('F_MONSTER_SKILL_MST') + lgd['Wp39QX52']
    definitions = [
        ('9700104', [('212021000', 'Fossil Dragon'), ('208036000', 'Leanan-Sidhe'),
                     ('210031000', 'Gargoyle')], 1200, 50, 20, None),
        ('9700106', [('407012000', 'Evil Drake')], 150, 100, 50, None),
        ('9700108', [('900010677', 'Morgana')], 1000, 150, 200, (400000, 300, 35)),
        ('9700110', [('900010677', 'Morgana')], 2000, 350, 800, (2000000, 10000, 60)),
        ('9700111', [('900010677', 'Morgana')], 5000, 400, 900, (5000000, 100000, 80)),
    ]
    for mid, lineup, experience, coins, shards, tier in definitions:
        phase_rows, lotteries, groups, monster_rows, part_rows = [], [], [], [], []
        for ix, (source_id, name) in enumerate(lineup, 1):
            # Preserve existing IDs for ordinary profiles; local Morgana tiers
            # use the explicitly assigned UnitID for their presentation.
            pid = str(1900000000 + int(mid) * 10 + ix) if tier else source_id
            gid = str(int(mid) * 100 + ix)
            phase = dict(lgd['an6TB4WS'][0])
            phase.update({'qo3PECw6': mid, '6v7y3QcJ': str(ix),
                          '2fY1IomW': gid, '6uIYE15X': gid,
                          'YS9kfCX7': missions[mid]['6w4xiIsS'],
                          'DYTx1Is3': missions[mid]['DYTx1Is3']})
            phase_rows.append(phase)
            lotteries.append({'c2gnh6Jd': gid, 'ixDq7yJ8': '100', '2fY1IomW': gid})
            group = dict(lgd['Bi6hVv34'][0])
            group.update({'2fY1IomW': gid, 'xqartN26': pid})
            groups.append(group)
            part = copy.deepcopy(lgd['bV34YIJQ'][0] if tier else parts[source_id])
            monster = (dict(lgd['wbet57nF'][0]) if tier else dict(monsters[source_id]))
            monster.update({'xqartN26': pid, 'G4L0YIB2': name})
            part.update({'xqartN26': pid, 'G4L0YIB2': name,
                         'B6H34Mea': str(experience // len(lineup) + (ix <= experience % len(lineup))),
                         '7UR4J2SE': '0', 'ATM35pjf': '0'})
            if tier:
                part.update({'fh31sk7B': str(tier[0]), 'PC97pWQj': str(tier[1]),
                             '7wV3QZ80': str(tier[2])})
            coin_count = coins // len(lineup) + (ix <= coins % len(lineup))
            shard_count = shards // len(lineup) + (ix <= shards % len(lineup))
            part['9BetM2Ds'] = f'20:1209000976:{coin_count}:100,20:1209000975:{shard_count}:100'
            monster_rows.append(monster)
            part_rows.append(part)
        tables = {
            'F_MISSION_PHASE_MST': phase_rows, 'F_BATTLE_LOTTERY_MST': lotteries,
            'F_BATTLE_GROUP_MST': groups, 'F_MONSTER_MST': monster_rows,
            'F_MONSTER_PARTS_MST': part_rows, 'F_MONSTER_SKILL_SET_MST': gl_sets,
            'F_MONSTER_SKILL_MST': skill_rows,
        }
        yield mid, battle_content.derive_mission(mid, ReconstructionSource(base, tables))


def followers(lgd):
    """Reconstruct the recorded four waves using the original Global graphics.

    MonsterParty::entryMonster reads MonsterMst.DictionaryID (offset 0x28)
    when building the animation suffix. The battle-only ID can therefore be
    local while the dictionary ID retains the original cached sprite binding.
    """
    base = battle_content.IndexSource()
    parts = {r['xqartN26']: r for r in base.load('F_MONSTER_PARTS_MST')}
    mid = '9700102'
    phases, lotteries, groups, monsters, profiles = [], [], [], [], []
    for wave, count in enumerate((1, 2, 3, 1), 1):
        captain = wave == 4
        pid, gid = str(1900000100 + wave), str(int(mid) * 100 + wave)
        phase = dict(lgd['an6TB4WS'][0])
        phase.update({'qo3PECw6': mid, '6v7y3QcJ': str(wave),
                      '2fY1IomW': gid, '6uIYE15X': gid, 'DYTx1Is3': '1000023'})
        phases.append(phase)
        lotteries.append({'c2gnh6Jd': gid, 'ixDq7yJ8': '100', '2fY1IomW': gid})
        for slot in range(1, count + 1):
            group = dict(lgd['Bi6hVv34'][0])
            group.update({'2fY1IomW': gid, 'xqartN26': pid, 'Z0EN6jSh': str(slot),
                          'MxLFKZ13': f'{170 if slot % 2 else 100},{260 + 80 * slot}'})
            groups.append(group)
        name = "Captain of the Empress's Guard" if captain else "Empress's Knight"
        source_id = '225111000' if captain else '205301000'
        profile = copy.deepcopy(parts[source_id])
        profile.update({'xqartN26': pid, 'G4L0YIB2': name,
                        'fh31sk7B': '200000' if captain else '100000',
                        'PC97pWQj': '100', '7wV3QZ80': '25' if captain else '10',
                        'hn42BL3Q': '0,0,0,0,0,0,-100,0,0',
                        'D9Nb7jgd': '100,100,100,100,100,100,100,100',
                        'B6H34Mea': '550' if captain else '200',
                        '7UR4J2SE': '0', 'ATM35pjf': '0',
                        '9BetM2Ds': f'20:1209000976:{13 if wave < 3 else 12}:100,20:1209000975:5:100'})
        profiles.append(profile)
        monsters.append({'xqartN26': pid, 'G4L0YIB2': name,
                         'V9j8wJcC': '10000049' if captain else '10000053'})
    tables = {'F_MISSION_PHASE_MST': phases, 'F_BATTLE_LOTTERY_MST': lotteries,
              'F_BATTLE_GROUP_MST': groups, 'F_MONSTER_MST': monsters,
              'F_MONSTER_PARTS_MST': profiles,
              'F_MONSTER_SKILL_SET_MST': read_table('F_MONSTER_SKILL_SET_MST')}
    return battle_content.derive_mission(mid, ReconstructionSource(base, tables))


def king_mog_counterattack(document):
    """Original Global boss stats, preserving its existing model, AI and skill set."""
    base = battle_content.IndexSource()
    source = ReconstructionSource(base, {'F_MONSTER_SKILL_SET_MST': read_table('F_MONSTER_SKILL_SET_MST')})
    bundle = battle_content.derive_mission('7340105', source)
    if len(bundle['bV34YIJQ']) != 1 or bundle['bV34YIJQ'][0]['xqartN26'] != '508001004':
        raise ValueError('King Mog source encounter changed')
    boss = bundle['bV34YIJQ'][0]
    boss.update({'G4L0YIB2': 'King Mog', 'fh31sk7B': '4000000', 'PC97pWQj': '10000',
                 '9NBV1XCS': '630', 'Pn5w9dfh': '85', '84FJM3PD': '600', 'T8xMDAZ4': '65',
                 '7wV3QZ80': '99'})
    bundle['wbet57nF'][0]['G4L0YIB2'] = 'King Mog'
    document['jnw49dUq@7340105'] = battle_content.wire_bundle(bundle, document)
    document['_gl_raid_reconstruction'] = {
        '7340105': {
            'source': 'https://exvius.fandom.com/wiki/One_Year_Anniversary,_Kupo!',
            'recovered': 'King Mog: level 99, HP 4000000, MP 10000, ATK 630, DEF 85, MAG 600, SPR 65.',
            'preserved': 'Existing encounter/model/AI IDs and shipped Global skill-set row. No solo scaling of battle stats.',
            'status': 'Global stat correction; native phone acceptance pending.'}}


def main():
    path = PROJECT / 'source/server/responses.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    king_mog_counterattack(document)
    lgd = morgana_lgd()
    document['jnw49dUq@9700112'] = battle_content.wire_bundle(lgd, document)
    document['jnw49dUq@9700102'] = battle_content.wire_bundle(followers(lgd), document)
    for mid, bundle in reconstructed_stages(lgd):
        document['jnw49dUq@' + mid] = battle_content.wire_bundle(bundle, document)
    for mission in read_table('F_MISSION_MST'):
        if mission['qo3PECw6'] in ('9700101', '9700103', '9700105', '9700107', '9700109'):
            # These scenes use the original Global resource/script list. Never
            # replace them with the unrelated Memorial same-ID Ifrit fights.
            document['jnw49dUq@' + mission['qo3PECw6']] = battle_content.wire_bundle(
                {'1IfDqR4n': [mission]}, document)
    document['_gl_event_reconstruction'] = {
        'approval': 'User explicitly approved reconstruction from available data on 2026-10-23.',
        'recording': 'https://www.youtube.com/watch?v=MNwueRuqEvU',
        'recording_times': {'9700102': '11:55', '9700104': '17:44', '9700106': '21:39', '9700108': '24:01',
                            '9700110': '30:26', '9700111': '31:01 and 35:42', '9700112': '37:23'},
        '9700102': {
            'status': 'reconstructed; native client acceptance pending',
            'sources': ['https://exvius.fandom.com/wiki/Empress%27s_Knight',
                        'https://exvius.fandom.com/wiki/Captain_of_the_Empress%27s_Guard'],
            'recovered': 'Four waves of 1, 2, 3 knights, then one captain. Original Global sprites 10000053 and 10000049. Knight level 10, HP 100000, MP 100; captain level 25, HP 200000, MP 100. Stage unit XP 1750, coins 50 and shards 20.',
            'assumptions': 'Soldier 205301000 and heavy soldier 225111000 supply missing attack/defense values, AI and skills. XP assigned 200 per knight and 550 to the captain. Currency is split across waves; original roll distribution was not recovered.',
        },
        'cutscenes': 'Five original Global F_MISSION_MST resource rows, including unmodified q4f9IdMs script/resource IDs. No combat phases or enemies are supplied.',
        '9700104': {
            'status': 'reconstructed; native client acceptance pending',
            'observed': 'Three single-enemy waves: Fossil Dragon, Leanan-Sidhe, Gargoyle.',
            'assumptions': 'Existing native monster profiles 212021000, 208036000 and 210031000; exact event variant stats unavailable. Published stage XP and minimum currency split across waves.',
        },
        '9700106': {
            'status': 'reconstructed; native client acceptance pending',
            'observed': 'One Evil Drake wave, original mission background/music, 150 unit XP.',
            'assumptions': 'Existing native Evil Drake profile 407012000. Exact original event variant not recovered.',
        },
        '9700108': {
            'status': 'reconstructed; native client acceptance pending',
            'recovered': 'Morgana, level 35, 400000 HP, 300 MP and 1000 unit XP from the monster wiki.',
            'assumptions': 'LGD offensive/defensive profile, original AI and skill set reused; presentation and drop choices follow LGD reconstruction.',
        },
        '9700110': {
            'status': 'reconstructed; native client acceptance pending',
            'recovered': 'One Morgana wave and 2000 unit XP.',
            'assumptions': 'Authored intermediate tier: 2000000 HP, 10000 MP, level 60. LGD remaining stats/AI reused. These values are not historical recovered facts.',
        },
        '9700111': {
            'status': 'reconstructed; native client acceptance pending',
            'recovered': 'One Morgana wave and 5000 unit XP. Recording shows 98406 damage leaving 98 percent HP at 32:10.',
            'assumptions': '5000000 HP is an inference consistent with the visible HP loss, not an exact measurement. Authored 100000 MP and level 80; LGD remaining stats/AI reused.',
        },
        '9700112': {
            'status': 'reconstructed; native client acceptance pending',
            'sources': [
                'https://gist.github.com/aEnigmatic/bed7cab8da88c2e8be45ab57963b2f57',
                'https://www.youtube.com/watch?v=MNwueRuqEvU&t=2243s',
                'https://exvius.fandom.com/wiki/Fundamental_Forces',
            ],
            'recovered': 'Monster/AI IDs, stats, resistances, action count and five effect definitions.',
            'existing_global_tables': 'F_AI_MST, F_MONSTER_SKILL_SET_MST, F_UNIT_MST, F_MISSION_MST, item/dictionary rows.',
            'reconstruction_choices': [
                'Morgana 7-star unit presentation and existing unit-model enemy defaults.',
                'Existing Banish spell presentation; boss skill MP cost set to zero because no source records it.',
                'Single resolved group, position and source mission background/music.',
                'Conservative published minimum drop amounts; original roll distribution and bonuses not recovered.',
            ],
            'unimplemented': 'Event points, bonus-unit drop scaling and original summon/reward pool.',
        }
    }
    temporary = path.with_suffix('.json.pending')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    temporary.replace(path)
    print('Authored seven reconstructed Global event bundles:', path)
    print('SHA256:', hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
