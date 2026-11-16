"""Finite classic exploration allocations with exact stage-owned formations.

Counts are authored finite coverage, not recovered retail quotas. Every declared
regular formation occurs once and then exhausts. Boss groups stay scripted.
Classic Gapra HARD has stage-owned records in repair_classic_hard_explorations.
Its inferred fields are explicit; shared later profiles remain unchanged.
"""
import copy
import json
from pathlib import Path

from battle_content import PARTS_DEFAULTS, PARTS_TOKENS
from player_state import mission_row

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'logs/ffbe-field-channel-audit-20261109.json'
REFERENCE = ROOT / 'logs/reference/late-exploration-wiki-20261110.json'
EARLIER_REFERENCE = ROOT / 'logs/reference/field-scenario-wiki-20261109.json'

# Explicit audited regular suffixes and actor identities. The native prefix is
# not used to discover an encounter pool. Rows at these exact IDs supply the
# original slot positions, display order and initial visibility unchanged.
FAMILIES = (
    ('811', 'Big Bridge - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('201231007', '205211107', '205261010', '306081004'), ('201231006', '205211106')),
    ('816', "Doga's Grotto - Exploration", tuple(range(2, 11)), (2, 3, 4),
     ('201241006', '201251004', '201261003', '201271000', '204211008', '204221001'),
     ('201241005', '204211007')),
    ('822', 'Dome - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('205681007', '301131003', '303061006', '309041004'), ('301131002', '303061005')),
    ('837', 'Forgotten Capital - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('103171010', '204251009', '205971008', '301211009'), ('103171009', '205971007')),
    ('842', 'Figaro Castle - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('104191010', '106091008', '204271009', '205981009'), ('104191009', '106091007')),
    ('848', 'Chocobo Forest - Exploration', tuple(range(2, 12)), (2, 3, 4, 5),
     ('101011012', '101023015', '101034002', '201011015', '201021020', '202011014'),
     ('101011011', '101023014', '101034001')),
    ('854', 'The Gapra Whitewood - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('201341008', '206201009', '209111010', '306121008'), ('201341007', '209111009')),
    ('860', 'Castle Exdeath - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('101161000', '201351010', '207111009', '307102009', '307161008', '310022008'),
     ('201351009', '310022007')),
    ('865', 'Narshe - Exploration', tuple(range(2, 11)), (2, 3, 4),
     ('101026201', '206211000', '301192001', '307181000', '307191000'),
     ('101026200', '301192000')),
    ('871', 'Castle Palamecia - Exploration', tuple(range(2, 10)), (2, 3, 4),
     ('201024101', '305602000', '310032001'), ('201024100', '310032000')),
    ('877', 'Flying Fortress - Exploration', tuple(range(2, 10)), (2, 3, 4),
     ('206222000', '225052001', '225061001'), ('225052000', '225061000')),
    ('882', 'Goldor Manor - Exploration', tuple(range(2, 10)), (2, 3, 4),
     ('112061000', '201391001', '225081001', '225091001'), ('201391000', '225081000', '225091000')),
    ('887', 'Altissia - Exploration', (2, 3, 4, 5, 6), (2, 3, 4),
     ('225101001', '225111001', '225121000'), ('225101000', '225111000')),
    ('892', 'Tower of Zot - Exploration', (2, 3, 4, 5, 6), (2, 3, 4),
     ('103161004', '205853001', '206052010'), ('205853000', '206052009')),
)

# These actors are not random even when a later/reused script names a different
# namespace. Zot's Magus Sisters and the optional bridge/Doga fights stay out.
SCRIPTED_GROUPS = {
    '8110101': ('811010101', '811010111'), '8110102': ('811010201',),
    '8160101': ('816010101', '816010111'), '8160102': ('816010201', '816010205'),
    '8220101': ('822010101',), '8220102': ('822010201',),
    '8370101': ('837010101',), '8370102': ('837010201',),
    '8420101': ('842010101',), '8420102': ('842010201',),
    '8480101': ('848010101',), '8480102': ('848010201',),
    '8540101': ('854010101', '854010111'), '8540102': ('854010201', '854010205'),
    '8600101': ('860010101', '423401017'), '8600102': ('860010201',),
    '8650101': ('865010101',), '8650102': ('865010201',),
    '8710101': ('871010101',), '8710102': ('871010201',),
    '8770101': ('877010101',), '8770102': ('877010201',),
    '8820101': ('882010101',), '8820102': ('882010201',),
    '8870101': ('887010101',), '8870102': ('887010201',),
    '8920101': ('892010101', '892010107', '892010201'),
    '8920102': ('892010107', '892010201'),
}
UNRECOVERED = {
    '8540101': {
        'reason': 'Same native IDs now contain later 300M-4.2B HP profiles. The dedicated classic helper owns the separately identified reconstruction; this exact-profile module must not reuse the later values.',
        'direct_published': {'306141000': {'level': 99, 'hp': 9180000, 'mp': 5000,
                                         'light_resist': -50, 'atk_mag_break_immune': True}},
        'missing': 'Direct older regular HP/MP/level/combat values and Aster/Alpha combat values. The published boss HP/MP alone cannot repair all six overwritten actors.',
        'actors': ('209111010', '201341008', '206201009', '306121008', '306141000', '401141008'),
        'source': 'https://exvius.fandom.com/wiki/The_Gapra_Whitewood_-_Exploration',
        'direct_source_limits': {
            'historical_commit': 'aEnigmatic/ffbe@8ce79b6c9aac5cf9265cb87bb7faadda002cf326',
            'historical_commit_contents': 'The 2019 event commit preserves mission, skill and skill-set definitions, but no monster combat-profile file.',
            'retained_memorial': 'Japan content/Shared sources/memorial_battle_decoded/F_MONSTER_PARTS_MST.ndjson',
            'retained_memorial_result': 'All six exact IDs have the same newer HP/MP/level values as the current Global parts table.',
        },
    },
}


def _audit_records():
    document = json.loads(AUDIT.read_text(encoding='utf8'))
    for rows in document.values():
        if isinstance(rows, list) and any(isinstance(row, dict) and row.get('mission') == '8110101' for row in rows):
            return {str(row['mission']): row for row in rows}
    raise ValueError('The retained typed exploration ownership audit is missing.')


def _guide_evidence(campaign):
    """Only cite a guide actually retained; native ownership is independent."""
    for reference in (REFERENCE, EARLIER_REFERENCE):
        if campaign in json.loads(reference.read_text(encoding='utf8'))['pages']:
            return {'sources': ['https://exvius.fandom.com/wiki/' + campaign.replace(' ', '_')],
                    'guide_reference': reference.relative_to(ROOT).as_posix()}
    return {'sources': [],
            'guide_limit': 'No matching contemporary guide was recovered. Formation ownership comes from the retained native tables and typed field resources; no published quota is claimed.'}


def _attach_dependencies(recovery, bundle, formations):
    """Copy exact owned dependencies; never change the shared source tables."""
    actors = {row['xqartN26'] for row in formations}
    bundle['Bi6hVv34'] = copy.deepcopy(formations)
    bundle['wbet57nF'] = [copy.deepcopy(recovery.monsters[iid]) for iid in sorted(actors, key=int)]
    bundle['bV34YIJQ'] = [{token: part.get(token, PARTS_DEFAULTS.get(token, '')) for token in PARTS_TOKENS}
                          for iid in sorted(actors, key=int) for part in recovery.parts[iid]]
    sets = {row['A5x02C6a']: row for row in recovery.base.load('F_MONSTER_SKILL_SET_MST')}
    wanted = set()
    for part in bundle['bV34YIJQ']:
        setid = part.get('A5x02C6a')
        if setid in ('', '0', None):
            continue
        skillset = recovery.global_sets.get(setid) or sets.get(setid)
        if not skillset:
            raise ValueError('Missing exact original exploration skill set: ' + str(setid))
        if setid in recovery.global_sets:
            recovery.recover_skills(setid)
        wanted.update(value for value in skillset['7qxLC5hP'].split(',') if value)
    bundle['Wp39QX52'] = [copy.deepcopy(recovery.skill_rows[skill]) for skill in sorted(wanted, key=int)]


def _classic_exdeath(recovery, bundle, all_groups, carrier):
    """Bind the retained field opcode to its own 2019 battle, only in this entry."""
    own = '860010101'
    selected = [row for row in all_groups if row['2fY1IomW'] == own]
    if {row['xqartN26'] for row in selected} != {'405041101'}:
        raise ValueError('Classic Castle Exdeath formation identity changed.')
    part = recovery.parts['405041101']
    if len(part) != 1 or (part[0]['fh31sk7B'], part[0]['PC97pWQj']) != ('9250000', '5000'):
        raise ValueError('Classic Castle Exdeath profile no longer matches the 2019 source.')
    master = next(copy.deepcopy(row) for row in carrier['rqxw0p9k'] if row['ja07xgLF'] == '8600101')
    link = next(copy.deepcopy(row) for row in carrier['YjHhvN65']
                if row['ja07xgLF'] == '8600101' and row['2fY1IomW'] == own)
    master['ja07xgLF'] = link['ja07xgLF'] = '42340101'
    bundle['rqxw0p9k'] = [master]
    bundle['YjHhvN65'] = [link]
    bundle['JR7jZci2'] = [{'ja07xgLF': '42340101', '2fY1IomW': own,
                           'xqartN26': row['xqartN26'], 'Z0EN6jSh': row['Z0EN6jSh'],
                           '6Yc4RkdM': p['6Yc4RkdM'], '9BetM2Ds': '',
                           'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': ''}
                          for row in selected if row['WJdBp9f0'] == '1'
                          for p in recovery.parts[row['xqartN26']]]
    _attach_dependencies(recovery, bundle, bundle['Bi6hVv34'] + selected)


def build(recovery, indexed_random_allocations):
    """Return {mission: (bundle, provenance)} for the assigned classic stages.

    Gapra HARD is supplied by the dedicated classic reconstruction helper.
    Its EASY counterpart has intact original profiles and is restored here.
    This function writes neither event_encounters.json nor the main generator.
    """
    audit = _audit_records()
    groups = recovery.base.load('F_BATTLE_GROUP_MST')
    carrier = json.loads((ROOT / 'source/server/responses.json').read_text(encoding='utf8'))['29JRaDbd']
    output = {}
    for prefix, campaign, hard_suffixes, easy_suffixes, hard_actors, easy_actors in FAMILIES:
        for tier, suffixes, expected_actors, energy in (
                ('1', hard_suffixes, hard_actors, '20'), ('2', easy_suffixes, easy_actors, '3')):
            mid = prefix + '010' + tier
            if mid in UNRECOVERED:
                continue
            record = audit[mid]
            fields = record.get('own_external_positive_fields', {})
            mission = mission_row(mid)
            if set(fields) != {'11'} or not mission or mission.get('B6kyCQ9M') != energy:
                raise ValueError('Original classic stage/zone ownership changed: ' + mid)
            gids = {mid + str(suffix).zfill(2) for suffix in suffixes}
            if gids.intersection(SCRIPTED_GROUPS[mid]):
                raise ValueError('A scripted boss entered the regular exploration pool: ' + mid)
            formations = [row for row in groups if row['2fY1IomW'] in gids]
            if {row['2fY1IomW'] for row in formations} != gids:
                raise ValueError('An exact original regular group is missing: ' + mid)
            actors = {row['xqartN26'] for row in formations}
            if actors != set(expected_actors):
                raise ValueError('Original regular formation roster changed: ' + mid)
            for iid in actors:
                for part in recovery.parts[iid]:
                    # A later same-ID monster must not enter an older mission.
                    if tier == '2':
                        valid = int(part['7wV3QZ80']) == 4 and int(part['fh31sk7B']) <= 500
                    elif iid == '201271000':
                        valid = (part['7wV3QZ80'], part['fh31sk7B']) == ('85', '3800000')
                    else:
                        valid = int(part['7wV3QZ80']) == 75 and 100000 <= int(part['fh31sk7B']) <= 1000000
                    if not valid:
                        raise ValueError('A later/unknown regular profile cannot serve the classic stage: ' + mid + ':' + iid)
            allocations = tuple((suffix, 1) for suffix in suffixes)
            bundle = indexed_random_allocations(recovery, mid, allocations, field='11')
            _attach_dependencies(recovery, bundle, formations)
            evidence = {
                'campaign': campaign,
                **_guide_evidence(campaign),
                'typed_source': {'audit': AUDIT.relative_to(ROOT).as_posix(),
                                 'resources': record['base_resources'], 'field': '11',
                                 'sources': fields['11']['sources']},
                'classic_version': {'energy': int(energy), 'regular_actor_ids': sorted(actors, key=int)},
                'original_regular_groups': sorted(gids, key=int),
                'excluded_scripted_groups': list(SCRIPTED_GROUPS[mid]),
                'recovered': 'Exact own typed encounter zone and explicitly listed original regular formations, actors, visible/hidden slots, positions, profile values, AI and skills. Original scripted bosses remain outside the random encounter list.',
                'reconstructed': 'The retired server occurrence quotas are absent. This finite coverage reconstruction gives each explicitly owned regular formation one occurrence, with native counter 0 and exhaustion thereafter. It is not claimed to reproduce retail encounter totals, draw order, rare-monster frequency, EXP/gil totals or drop probabilities.',
                'allocation_policy': {'occurrences_per_original_formation': 1, 'random_battles': len(suffixes),
                                      'retail_quota_recovered': False, 'refill': False},
                'loot': 'No unpublished item-roll or capture probabilities are invented. Original actor EXP/gil and script, mission, chest and first-clear rewards remain separate.',
            }
            if mid == '8600101':
                _classic_exdeath(recovery, bundle, groups, carrier)
                evidence['scoped_script_repair'] = {
                    'typed_opcode_scenario': '42340101', 'classic_group': '860010101', 'classic_actor': '405041101',
                    'direct_profile': {'hp': 9250000, 'mp': 5000, 'experience': 5500, 'gil': 600},
                    'reason': 'The retained own event opcode points to a reused newer 150M-HP Gilgamesh scenario. This field response binds that opcode to its exact original 2019 own battle and dependencies. The shared 4234 scenario and all other mission responses are unchanged.',
                    'source': 'https://exvius.fandom.com/wiki/Castle_Exdeath_-_Exploration',
                    'reference': REFERENCE.relative_to(ROOT).as_posix(),
                }
            output[mid] = bundle, evidence
    return output
