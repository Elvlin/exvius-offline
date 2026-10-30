"""Offline workload model, NOT an FFBE combat engine. Python stdlib only."""
import argparse
import json


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def simulate(config):
    """Replay user-supplied final damage/BP traces; no damage/AI inference.

    Each trace row is one full player turn. Break begins after that turn's
    damage and lasts the following N full turns. This timing is a MODEL
    convention, not verified client timing. Trace rows are not auto-repeated.
    """
    hp = integer(config['hp'], 'hp', 1)
    original_hp = hp
    trace = config['turns']
    if not isinstance(trace, list) or not trace or len(trace) > 10000:
        raise ValueError('turns must contain 1..10000 rows')
    spec = config.get('break_gauge')
    if spec is not None:
        base = integer(spec['base_bp'], 'base_bp', 1)
        delta = integer(spec['delta_after_first'], 'delta_after_first')
        duration = integer(spec['duration_turns'], 'duration_turns', 1)
        gauge = base
    else:
        base = delta = duration = gauge = 0
    broken_left = breaks = total_damage = 0
    out = []
    for number, row in enumerate(trace, 1):
        damage = integer(row['damage'], 'damage')
        bp = integer(row.get('bp_damage', 0), 'bp_damage')
        was_broken = broken_left > 0
        hp = max(0, hp - damage)
        total_damage += damage
        triggered = False
        if spec is not None:
            if was_broken:
                broken_left -= 1
                if broken_left == 0:
                    gauge = base + delta
            elif hp > 0:
                gauge = max(0, gauge - bp)
                if gauge == 0:
                    breaks += 1
                    broken_left = duration
                    triggered = True
        out.append({'turn': number, 'hp_remaining': hp,
                    'broken_during_turn': was_broken, 'break_triggered': triggered,
                    'broken_turns_remaining': broken_left, 'bp_remaining': gauge})
        if hp == 0:
            break
    return {'model_only': True, 'client_acceptance': False,
            'cleared_in_trace': hp == 0, 'turns_used': len(out),
            'hp_removed': original_hp - hp, 'submitted_damage': total_damage,
            'overkill_damage': max(0, total_damage - original_hp),
            'breaks_triggered': breaks, 'turns': out}


def solo_target(damage_per_attempt, desired_attempts):
    """Authored local raid pool recommendation, not a historical raid formula."""
    return integer(damage_per_attempt, 'damage_per_attempt', 1) * integer(desired_attempts, 'desired_attempts', 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', help='JSON input matching scenario.schema.json')
    args = parser.parse_args()
    with open(args.scenario, encoding='utf-8') as stream:
        print(json.dumps(simulate(json.load(stream)), indent=2))
