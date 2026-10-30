"""Decode the original rated reward tuples without dropping unit metadata."""
from player_state import unit_mst


def parse(raw):
    result = []
    for entry in filter(None, str(raw or '').split(',')):
        fields = entry.split(':')
        if len(fields) not in (3, 4, 5, 7, 9, 10) or not all(f.isascii() and f.isdigit() for f in fields):
            raise ValueError('invalid native reward tuple: ' + entry)
        kind, iid, count = map(int, fields[:3])
        if count <= 0 or (len(fields) > 3 and fields[3] != '100'):
            raise ValueError('invalid native reward quantity or rate')
        reward = {'kind': kind, 'id': iid, 'count': count}
        if kind == 10:
            if len(fields) >= 5:
                reward['level'] = max(1, int(fields[4]))
            if len(fields) in (7, 9, 10):
                points = int(fields[5])
                target = int(fields[-1])
                channel = 1 if target >= 1000000000 else 0
                target_id = target - channel * 1000000000
                # Only trust moogles carry a target trust reward. Cactuar
                # targets are unit-specific fusion restrictions instead.
                if str(iid).startswith(('904', '906')):
                    master = unit_mst(target_id) if target else None
                    descriptor = (master or {}).get(('9mu4boy7', 'C74EmZ1I')[channel])
                    reward['affinity_points'] = ['', '']
                    reward['affinity_info'] = ['', '']
                    if descriptor:
                        reward['affinity_info'][channel] = descriptor
                        points = points or int(descriptor.split(':')[3])
                    elif 100000000 < target_id <= 100000100:
                        # Original generic trust IDs encode the percentage:
                        # 100000005 = 5%, 1100000050 = 50% super trust.
                        points = points or (target_id - 100000000) * 10
                    reward['affinity_points'][channel] = str(points)
                elif target:
                    reward['reward_target_master'] = target
        elif len(fields) > 5 or (len(fields) == 5 and fields[4] not in ('0', '1')):
            raise ValueError('unit metadata attached to a non-unit reward')
        result.append(reward)
    return result
