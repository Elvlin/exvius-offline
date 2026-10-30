"""Authored banner/event selector. No supplemental stage reward."""

def profile_environment(profile):
    """Map user choices to EXISTING upstream switches, with no shell execution."""
    selection = profile.get('banners', {'mode': 'all'})
    mode = selection.get('mode')
    env = {'GACHA_CATALOGUE': '1', 'GACHA_COMMUNITY': '1',
           'GACHA_STANDARD': '1' if profile.get('standard_banners', False) else '0',
           'LAPIS_AWARD': '1',
           'FFBE_UPDATE_URL': ''}
    if mode == 'all':
        env.update(GACHA_ONLY='off', GACHA_CAMPAIGN='all')
    elif mode == 'ids':
        ids = selection.get('ids', [])
        if not ids or not all(str(x).isdigit() for x in ids):
            raise ValueError('choose at least one numeric banner ID')
        env.update(GACHA_ONLY=','.join(map(str, ids)), GACHA_CAMPAIGN='all')
    elif mode == 'campaign':
        key = selection.get('campaign', '')
        if not key or not all(x.isalnum() or x in '-_' for x in key):
            raise ValueError('invalid campaign key')
        env.update(GACHA_ONLY='off', GACHA_CAMPAIGN=key)
    else:
        raise ValueError('banner mode must be all, ids, or campaign')
    areas = profile.get('event_areas', [])
    if not areas or not all(str(x).isdigit() for x in areas):
        raise ValueError('explicit event area IDs required; missing events cannot be invented')
    env.update(EVENT_GATE_AREAS=','.join(map(str, areas)),
               EVENT_GATE_WINDOW_START='1577836800', EVENT_GATE_WINDOW_END='4102444800')
    return env
