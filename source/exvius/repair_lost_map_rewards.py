"""Restore Global Lost Maps waves and native per-enemy reward carriers."""
import copy

from battle_content import IndexSource, derive_mission
from build_event_archive import rows
from restore_event_battles import ReconstructionSource


SOURCE = 'https://exvius.fandom.com/wiki/King_Mog%27s_Lost_Maps'
REFERENCE = 'logs/reference/event-battles-wiki-20261026.json'


def _moogle_carriers(bundle):
    result = []
    for template in bundle['y35YvQjZ']:
        phase = next(p for p in bundle['an6TB4WS']
                     if p['6v7y3QcJ'] == template['6v7y3QcJ'])
        for slot in bundle['Bi6hVv34']:
            if slot['2fY1IomW'] != phase['2fY1IomW']:
                continue
            if slot['xqartN26'] != '204231000' or slot['WJdBp9f0'] != '1':
                raise ValueError('Lost Maps Mini Mogcaptor identity changed')
            row = copy.deepcopy(template)
            row.update(**{'2fY1IomW': slot['2fY1IomW'], 'xqartN26': slot['xqartN26'],
                          'Z0EN6jSh': slot['Z0EN6jSh'], '6Yc4RkdM': '1',
                          '9BetM2Ds': '', 'Vf5DGw07': '10:904000101:1'})
            result.append(row)
    bundle['y35YvQjZ'] = result


def _trust_map(source, mission):
    mid = '8180101'
    phases = sorted((r for r in source.load('F_MISSION_PHASE_MST') if r['qo3PECw6'] == mid),
                    key=lambda r: int(r['6v7y3QcJ']))
    if int(mission['8xi6Xvyk']) != 3 or len(phases) != 3:
        raise ValueError('Original Global Trust Map wave count changed')
    lottery = source.load('F_BATTLE_LOTTERY_MST')
    selection = []
    for phase in phases:
        candidates = []
        members = [r for r in lottery if r['c2gnh6Jd'] == phase['6uIYE15X']]
        expected = ('818010100',) if phase['6v7y3QcJ'] != '3' else (
            '818010100', '818010101', '818010102')
        if tuple(r['2fY1IomW'] for r in members) != expected or any(r['ixDq7yJ8'] != '100' for r in members):
            raise ValueError('Original Trust Map formation weights changed')
        for member in members:
            view = ReconstructionSource(source, {'F_MISSION_PHASE_MST': [phase],
                                                'F_BATTLE_LOTTERY_MST': [member]})
            fragment = derive_mission(int(mid), view)
            _moogle_carriers(fragment)
            expected_count = 1 if member['2fY1IomW'] == '818010100' else int(member['2fY1IomW'][-1]) + 1
            if len(fragment['y35YvQjZ']) != expected_count:
                raise ValueError('Original Trust Map Mini Mogcaptor count changed')
            candidates.append({'group': member['2fY1IomW'],
                               'weight': int(member['ixDq7yJ8']), 'bundle': fragment})
        selection.append({'phase': phase['6v7y3QcJ'], 'candidates': candidates})
    bundle = derive_mission(int(mid), source)
    bundle['1IfDqR4n'] = [copy.deepcopy(mission)]
    _moogle_carriers(bundle)
    for candidate in [bundle] + [c['bundle'] for p in selection for c in p['candidates']]:
        for monster in candidate['wbet57nF']:
            monster['G4L0YIB2'] = 'Mini Mogcaptor'
    return bundle, {
        'campaign': "King Mog's Lost Maps", 'sources': [SOURCE, REFERENCE],
        'source_revision': 316377,
        'recovered': 'Three Global waves and three to five ALL1%Trust Moogles. '
                     'Original indexed first two one-Mog formations and third-wave '
                     'one/two/three-Mog groups retain their equal original weights100.',
        'reward_contract': 'Each actual Mini Mogcaptor owns one level1 '
                           'Trust Moogle904000101 in native Vf5DGw07. Native owned '
                           'unit generation initializes its1%ALL affinity metadata. '
                           'No unit is represented as an item; no fabricated affinity IDs.',
        'regional_limit': 'Global wave count and written reward range agree with '
                          'the preserved Japanese exact Lost Map actor/group/lottery '
                          'records. Japanese indexed combat profiles retained unchanged.',
        'original_weighted_lottery': {'scope': 'original-lost-maps', 'phases': selection},
    }


def build(source=None):
    source = source or IndexSource()
    missions = {r['qo3PECw6']: r for r in rows('F_MISSION_MST')}
    phases = source.load('F_MISSION_PHASE_MST')
    groups = source.load('F_BATTLE_GROUP_MST')
    output = {}
    # The retained Japanese chain has three Quartz waves and one Gil wave.
    # Original Global mission rows and the Global guide agree on one and two.
    for mid, actor, original_group, counts, unit in (
        ('8180105', '111071006', '818010500', (9,), None),
        ('8180106', '103121000', '818010600', (2, 3), '900010501'),
    ):
        mission = missions[mid]
        if int(mission['8xi6Xvyk']) != len(counts):
            raise ValueError('Original Global Lost Map wave count changed: ' + mid)
        originals = sorted((r for r in groups if r['2fY1IomW'] == original_group),
                           key=lambda r: int(r['Z0EN6jSh']))
        if (len(originals) != (9 if unit is None else 1)
                or any(r['xqartN26'] != actor or r['WJdBp9f0'] != '1' for r in originals)):
            raise ValueError('Original Lost Map actor binding changed: ' + mid)
        phase = next(r for r in phases if r['qo3PECw6'] == mid)
        owned_phases, owned_groups, lotteries = [], [], []
        for index, count in enumerate(counts, 1):
            gid = original_group if unit is None else str(1719000400 + index)
            if unit is not None and any(r['2fY1IomW'] == gid for r in groups):
                raise ValueError('Local Lost Map group collides with original data: ' + gid)
            p = copy.deepcopy(phase)
            p.update(qo3PECw6=mid, **{'6v7y3QcJ': str(index), '6uIYE15X': gid})
            owned_phases.append(p)
            lotteries.append({'c2gnh6Jd': gid, '2fY1IomW': gid, 'ixDq7yJ8': '100'})
            for slot in range(1, count + 1):
                row = copy.deepcopy(originals[slot - 1] if unit is None else originals[0])
                row.update(**{'2fY1IomW': gid, 'Z0EN6jSh': str(slot)})
                if unit is not None:
                    row['MxLFKZ13'] = str(120 + 55 * (slot - 1)) + ',' + str(220 + 100 * (slot - 1))
                owned_groups.append(row)
        view = ReconstructionSource(source, {
            'F_MISSION_PHASE_MST': owned_phases,
            'F_BATTLE_LOTTERY_MST': lotteries,
            'F_BATTLE_GROUP_MST': owned_groups,
        })
        bundle = derive_mission(int(mid), view)
        bundle['1IfDqR4n'] = [copy.deepcopy(mission)]
        for monster in bundle['wbet57nF']:
            monster['G4L0YIB2'] = 'Gil Snapper Tower' if unit else 'Minituar'
        # A row belongs to one actual enemy slot. Capture each Tower separately,
        # rather than making its first enemy own the whole wave's unit payout.
        carrier_templates = bundle['y35YvQjZ']
        carriers = []
        for phase, template in zip(owned_phases, carrier_templates):
            for slot in owned_groups:
                if slot['2fY1IomW'] != phase['6uIYE15X']:
                    continue
                row = copy.deepcopy(template)
                row.update(**{'2fY1IomW': slot['2fY1IomW'], 'xqartN26': actor,
                              'Z0EN6jSh': slot['Z0EN6jSh'], '6Yc4RkdM': '1',
                              '9BetM2Ds': '' if unit else '20:106200100:1:100',
                              'Vf5DGw07': '10:' + unit + ':1' if unit else ''})
                carriers.append(row)
        bundle['y35YvQjZ'] = carriers
        output[mid] = (bundle, {
            'campaign': "King Mog's Lost Maps",
            'sources': [SOURCE, REFERENCE], 'source_revision': 316377,
            'recovered': ('Original Global wave count and guide total: '
                          'one battle/nine Star Quartz106200100.' if unit is None else
                          'Original Global wave count and guide total: '
                          'two battles/five Gil Snapper Tower900010501 units.'),
            'native_actors': 'Exact own Lost Map native group actor, unchanged indexed '
                             'monster profile, AI and skills. Japanese source provenance '
                             'is retained; no different same-name donor is used.',
            'reward_contract': ('Nine original native Minituar slots each own one '
                                'guaranteed Star Quartz in the item carrier.' if unit is None else
                                'Five authored Tower slots each own one level1 '
                                'Gil Snapper Tower in native Vf5DGw07 unit carrier. '
                                'No unit is represented as an item or pre-awarded on entry.'),
            'reconstructed': ('No formation or reward quantity reconstruction.' if unit is None else
                              'The preserved Japanese group contains one Tower. Its original '
                              'Global formation is unpreserved; two then three own Towers, '
                              'local group IDs and positions are explicitly reconstructed '
                              'to retain the documented five captures across two battles.'),
            'original_source_group': original_group,
            'wave_actor_counts': list(counts),
        })
    output['8180101'] = _trust_map(source, missions['8180101'])
    return output
