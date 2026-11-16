"""Finite own-species encounters for the three-minute Bamboo exploration."""
import copy
import math


# The original Global name table places each four-species block AFTER Mermaid.
# Values are published event level, HP, MP, EXP and gil, in native species order.
SPECIES = (
    ('Mini Dragon', '107001', '5', '107001000',
     ((10,50000,50,69,51),(30,100000,100,98,74),
      (50,200000,200,140,105),(70,400000,400,200,150))),
    ('Greater Mantis', '209002', '5', '209001000',
     ((10,52500,52,86,38),(30,105000,105,123,55),
      (50,210000,210,175,78),(70,420000,420,250,112))),
    ('Cobalt Frog', '103007', '5', '103007000',
     ((10,43750,44,96,64),(30,87500,88,137,91),
      (50,175000,175,196,130),(70,350000,350,280,186))),
    ('Adamantoise', '203012', '203012000', '203012000',
     ((10,62500,62,103,89),(30,125000,125,147,127),
      (50,250000,250,210,182),(70,500000,500,300,260))))


def augment(recovery, stages, actor, skill_dependencies):
    for tier in range(4):
        mid = str(9002001 + tier)
        bundle, provenance = stages[mid]
        actors, evidence = [], []
        for species, (name, prefix, ai, skillset, values) in enumerate(SPECIES):
            level, hp, mp, experience, gil = values[tier]
            candidates = [p[0] for iid, p in recovery.parts.items()
                          if iid.startswith(prefix) and len(p) == 1
                          and p[0]['8a6gAwN9'] == ai
                          and p[0]['A5x02C6a'] == skillset]
            anchor = min(candidates, key=lambda p: (
                abs(int(p['7wV3QZ80']) - level), int(p['xqartN26'])))
            iid = str(900010320 + tier * 5 + species)
            resistance = dict(water=-50) if species in (0, 1) else (
                dict(lightning=-50, water=50, poison=30, petrify=100)
                if species == 2 else dict(ice=-50, poison=30, petrify=100))
            monster, parts, basis = actor(recovery, name, 'The Misty Bamboo Forest',
                ('INT','ADV','PRO','ELT')[tier], values[tier], (iid, ai), resistance)
            monster['V9j8wJcC'] = recovery.monsters[anchor['xqartN26']]['V9j8wJcC']
            for part in parts:
                for token in ('9NBV1XCS','Pn5w9dfh','84FJM3PD','T8xMDAZ4'):
                    part[token] = str(math.ceil(int(anchor[token]) * level / int(anchor['7wV3QZ80'])))
                part['8a6gAwN9'], part['A5x02C6a'] = ai, skillset
                part['4Y2DGP7m'] = anchor['4Y2DGP7m']
                part['Rcqa1Zt7'], part['zPu2iUK8'] = anchor['Rcqa1Zt7'], anchor['zPu2iUK8']
                # The event-specific resistance boxes leave other ailments open.
                part['hn42BL3Q'] = ('0,0,0,-50,0,0,0,0,0' if species in (0,1)
                    else '0,0,-50,50,0,0,0,0,0' if species == 2
                    else '0,-50,0,0,0,0,0,0,0')
                part['D9Nb7jgd'] = ('30,0,0,0,0,0,0,100' if species in (2,3)
                                      else '0,0,0,0,0,0,0,0')
                if species in (0,1):
                    part['D9Nb7jgd'] = '0,0,0,0,0,0,0,0'
            basis['own_species_combat_anchor'] = anchor['xqartN26']
            basis['unpublished_values'] = ('ATK/DEF/MAG/SPR = ceil(original same-species '
                'normal profile stat * event level / anchor level). Nearest preserved '
                'same-species normal AI/skill profile selected, not retail event stats. '
                'Published event HP/MP/level/EXP/gil and event resistance box are exact.')
            actors.append((monster, parts, ''))
            evidence.append(basis)
        if tier == 3:
            for iid, unit in (('111091000','900020401'), ('103111000','900010401')):
                monster = copy.deepcopy(recovery.monsters[iid])
                parts = copy.deepcopy(recovery.parts[iid])
                actors.append((monster, parts, '10:' + unit + ':1'))
        bundle['6v0LPiRe'] = []
        for field in ('10', '11', '12'):
            for number, (monster, parts, reward) in enumerate(actors):
                # Local group identities describe reconstructed formations, while
                # the actors retain the original event or exact bonus species ID.
                gid = str(1719100000 + tier * 1000 + int(field) * 10 + number)
                iid = monster['xqartN26']
                bundle['Bi6hVv34'].append({'2fY1IomW':gid,'xqartN26':iid,
                    'MxLFKZ13':'170,340','Z0EN6jSh':'1','3t7pZM5V':'2',
                    'WJdBp9f0':'1','m9BvFk2X':'1'})
                for part in parts:
                    bundle['6v0LPiRe'].append({'qo3PECw6':mid,'YzGa63QM':field,
                        '2fY1IomW':gid,'h4Sjf96p':'0','Z0EN6jSh':'1',
                        'xqartN26':iid,'6Yc4RkdM':part['6Yc4RkdM'],
                        '9BetM2Ds':'','MZn8LC6H':'','g4voc2Aw':'','Vf5DGw07':reward,
                        '4K8t5dVh':'0','V2mCH5UR':'','14FMQseU':'0'})
                if not any(r['xqartN26'] == iid for r in bundle['wbet57nF']):
                    bundle['wbet57nF'].append(monster)
                    bundle['bV34YIJQ'].extend(parts)
        skill_dependencies(recovery, bundle)
        provenance['random_encounters'] = {
            'sources': ['https://exvius.fandom.com/wiki/The_Misty_Bamboo_Forest'] +
                ['https://exvius.fandom.com/wiki/' + row[0].replace(' ','_') for row in SPECIES],
            'actors': evidence,
            'recovered': 'Original own event90000501 external planes provide fields10,11,12 '
                'on maps21..33. Only those existing positive encounter planes receive '
                'allocations; no previously noncombat room is enabled. Original sixteen '
                'Global event actor identities, four published tier profiles and normal '
                'species AI/skills are restored. Mermaid remains solely script-triggered.',
            'reconstructed': 'One finite single-species formation per published ordinary '
                'species in each positive field. ELT also has one finite KingMetalMinituar '
                'and GilSnapperFamily capture per field using the exact original bonus '
                'species and original level1 unit identities. Formation composition, '
                'counters and bonus rarity probabilities are unpreserved and these '
                'representative allocations are not claimed to reproduce retail rarity. '
                'Counters start at0 and never refill, including revisits during the timer.',
            'rewards': 'Bonus capture tuples are native category10:unitID:level and earned '
                'only on their own encounters. No entry capture, guessed regular item '
                'probability or duplicate Mermaid Lantern reward is introduced.'}
    return stages
