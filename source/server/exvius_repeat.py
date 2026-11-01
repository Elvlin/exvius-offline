"""Repeat only original Lapis; other challenge rewards are lifetime one-time. Authored integration, no new economy.

No client attempt nonce is available. Mission-load -> one completion is the
smallest supported idempotency boundary. See README for delayed retry limits.
"""
import copy
import json
import threading

_LOCK = threading.RLock()


def begin_attempt(player, mid):
    if player.mode == 'frozen' or not mid:
        return False
    with _LOCK:
        state = player.data.setdefault('exvius_repeat', {})
        current = state.get('attempt', {})
        if current.get('mid') == str(mid) and current.get('status') == 'pending':
            return False  # repeated load while this mission is active
        state['attempt'] = {'mid': str(mid), 'sequence': current.get('sequence', 0) + 1,
                            'status': 'pending'}
        player.dirty = True
        return True


def parse_rewards(raw):
    from exvius_rewards import parse
    return parse(raw)


def complete_attempt(player, mid, cleared, challenges, checks, context, lapis_enabled=True):
    """One serialized reward transaction, using upstream reward projection methods.

    challenges: dictionaries with id, condition, rewards (unchanged MST strings).
    Unknown/unmet conditions do not pay. Unsupported reward groups are reported,
    not converted into Lapis. State rollback protects against a partial grant.
    """
    if player.mode == 'frozen':
        return {'paid': [], 'blocked': [], 'reason': 'frozen'}
    with _LOCK:
        attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
        if attempt.get('mid') != str(mid) or attempt.get('status') != 'pending':
            return {'paid': [], 'blocked': [], 'reason': 'no pending mission load'}
        before = copy.deepcopy(player.data)
        dirty_before = player.dirty
        paid, blocked = [], []
        try:
            if cleared is True:
                for challenge in challenges:
                    cid = str(challenge['id'])
                    code, _, param = challenge['condition'].partition(':')
                    check = checks.get(code)
                    if check is None or check(context, param) is not True:
                        continue
                    player.mark_challenge_cleared(str(mid), cid)
                    # Grandfather historical paid challenges conservatively, once per challenge.
                    # Legacy marker is NOT proof that non-Lapis inventory was delivered.
                    claims = player.data['exvius_repeat'].setdefault('non_lapis_claims', {}).setdefault(str(mid), {})
                    if cid not in claims:
                        legacy_paid = cid in player.data.get('progress', {}).get('paid_challenges', {}).get(str(mid), [])
                        claims[cid] = {'legacy_completed_unknown_receipt': legacy_paid, 'entries': []}
                    claim = claims[cid]
                    granted_rows = []
                    all_supported = True
                    # Comma-delimited entries are independent upstream reward records.
                    # An unsupported entry must not suppress a separate valid Lapis entry.
                    occurrences = {}
                    for index, entry in enumerate(str(challenge.get('rewards') or '').split(',')):
                        if not entry.strip():
                            continue
                        try:
                            row = parse_rewards(entry)[0]
                        except ValueError as exc:
                            blocked.append({'id': cid, 'entry': entry, 'reason': str(exc)})
                            all_supported = False
                            continue
                        identity = str(row['kind']) + ':' + str(row['id'])
                        occurrence = occurrences.get(identity, 0)
                        occurrences[identity] = occurrence + 1
                        key = identity + ':' + str(occurrence)
                        if row['kind'] == 50:
                            if not lapis_enabled:
                                all_supported = False
                                continue
                        elif claim['legacy_completed_unknown_receipt'] or key in claim['entries']:
                            continue
                        if not player._can_credit(row):
                            blocked.append({'id': cid, 'entry': entry, 'reason': 'unsupported reward type or missing master data'})
                            all_supported = False
                            continue
                        if player._grant_items([row]) != [row]:
                            raise RuntimeError('partial upstream reward grant; transaction rolled back')
                        if row['kind'] != 50:
                            claim['entries'].append(key)
                        granted_rows.append(row)
                    if all_supported:
                        player.credit_challenge(str(mid), cid)
                    if granted_rows:
                        paid.append({'id': cid, 'rewards': granted_rows})
            # A failed/unknown result also closes its attempt; a new load re-arms.
            attempt['status'] = 'completed'
            attempt['cleared'] = cleared is True
            attempt['paid'] = paid
            attempt['blocked'] = blocked
            if cleared is True:
                player.record_archive({'TOTAL_MISSION_CLEAR': 1})
            player.dirty = True
            return {'paid': paid, 'blocked': blocked, 'reason': 'completed'}
        except Exception:
            player.data = before
            player.dirty = dirty_before
            raise


def claim_mission_rewards(player, mid):
    """Normal loot is unchanged, but one loaded attempt may pay it only once."""
    if player.mode == 'frozen' or not mid:
        return False
    with _LOCK:
        attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
        if (attempt.get('mid') != str(mid) or attempt.get('status') != 'pending'
                or attempt.get('normal_rewards_recorded')):
            return False
        attempt['normal_rewards_recorded'] = True
        player.dirty = True
        return True


def claim_quest_progress(player, mid):
    """Use the existing durable completion receipt once for quest counters."""
    if player.mode == 'frozen' or not mid:
        return False
    with _LOCK:
        attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
        if (attempt.get('mid') != str(mid) or attempt.get('status') != 'completed'
                or attempt.get('cleared') is not True or attempt.get('quest_progress_recorded')):
            return False
        attempt['quest_progress_recorded'] = True
        player.dirty = True
        return True


def observe_load(spec, mid, is_battle_bundle):
    from ffbe_state import State
    from ffbe_config import RESULT_TAG
    if is_battle_bundle and isinstance(spec, dict) and RESULT_TAG not in spec:
        if begin_attempt(State.player, mid):
            from exvius_raid_progress import observe_personal_raid
            observe_personal_raid(State.player, mid, spec)
            State.state_dirty = True
    return spec


def repeat_challenge_rewards(spec, mid, plaintext):
    from ffbe_state import State, _note
    from ffbe_config import RESULT_TAG, CHALLENGE_MST, LAPIS_AWARD
    from ffbe_battle import mission_result_from, CONDITION_CHECKS, challenge_table
    if not isinstance(spec, dict) or RESULT_TAG not in spec or not mid:
        return spec
    context = mission_result_from(plaintext)
    challenges = {}
    allowed = challenge_table().get(str(mid), {})
    try:
        with open(CHALLENGE_MST, encoding='utf-8') as source:
            for line in source:
                row = json.loads(line)
                if (str(row.get('qo3PECw6')) == str(mid) and row.get('Pzn5h0Ga')
                        and str(row.get('V36ygRYs')) in allowed):
                    challenges[str(row['V36ygRYs'])] = {'id': row['V36ygRYs'], 'condition': row['Pzn5h0Ga'],
                                       'rewards': row.get('dX6cor8j', '')}
    except (OSError, ValueError) as exc:
        _note('repeat rewards withheld: challenge table unavailable/invalid: ' + str(exc))
        return spec
    already = set(State.player.cleared_challenges.get(str(mid), set()))
    result = complete_attempt(State.player, mid, context['cleared'], challenges.values(),
                              CONDITION_CHECKS, context, LAPIS_AWARD)
    if result['reason'] == 'completed':
        State.state_dirty = True
        from exvius_fortuna import complete as complete_fortuna
        complete_fortuna(State.player, mid,
                         State.player.data.get('exvius_repeat', {}).get('attempt', {}).get('sequence', 0), context)
        from exvius_raid_progress import complete_secret_unlock
        complete_secret_unlock(State.player, mid)
        # Only explicitly configured shared raid progress; combat/personal rewards unchanged.
        from exvius_raid_progress import credit_configured_raid
        from data_paths import DATA_ROOT
        attempt = State.player.data.get('exvius_repeat', {}).get('attempt', {})
        completion_id = 'mission:%s:attempt:%s' % (mid, attempt.get('sequence'))
        try:
            credit_configured_raid(State.player, mid, completion_id, context['cleared'], DATA_ROOT)
        except (OSError, ValueError) as exc:
            _note('local shared raid progress withheld: ' + str(exc))
    # A replay's Lapis is paid but no result screen announces it (the challenge stars animate only on a
    # first clear). Use the native reward CSV, not the item-drop CSV: that
    # parser fixes the category to items and treats 50 as an item identifier.
    # REB5tAL9 entries are source@kind:id:count@state. State 0 is the normal
    # reward row. Payment above remains the only currency transaction.
    replay_lapis = sum(row['count'] for paid in result['paid'] if str(paid['id']) in already
                       for row in paid['rewards'] if row['kind'] == 50)
    if replay_lapis:
        spec = copy.deepcopy(spec)
        for row in spec.get(RESULT_TAG, []):
            if isinstance(row, dict):
                rewards = str(row.get('REB5tAL9') or '')
                row['REB5tAL9'] = (rewards + ',' if rewards else '') + '0@50:1:%d@0' % replay_lapis
        _note('replay lapis %d listed in the results for mission %s' % (replay_lapis, mid))
    for blocked in result['blocked']:
        _note('repeat challenge %s withheld: %s' % (blocked['id'], blocked['reason']))
    from exvius_fortuna import project as project_fortuna
    spec = project_fortuna(State.player, spec, mid)
    from exvius_raid_progress import apply_personal_raid_result
    return apply_personal_raid_result(State.player, spec, mid, plaintext)
