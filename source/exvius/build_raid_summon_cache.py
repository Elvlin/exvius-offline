"""Project raid Summon links through the existing encrypted master cache path."""
from pathlib import Path

from prepare_offline_cache import PROJECT, DATA, client_manifest, raid_reward_banners
from native_master_index import build_index


def build_files():
    manifest = client_manifest(PROJECT / 'repository snapshots/FFBE-Global-v9.0.0-original.apk')
    matches = [(token, row['key']) for token, row in manifest.items() if row['table'] == 'F_BANNER_MST']
    if len(matches) != 1:
        raise ValueError('Expected the original BannerMst manifest identity')
    token, key = matches[0]
    sources = list((DATA / 'client/files').rglob('Ver*_' + token + '.dat'))
    if len(sources) != 1:
        raise ValueError('Expected one original BannerMst cache source')
    raw = raid_reward_banners(sources[0], None, key)
    from build_news_menu import rewrite_banner_cache
    raw = rewrite_banner_cache(raw, key)
    return {'native/mst/Ver595_' + token + '.dat': raw,
            'native/mst/' + token + '.i': build_index('F_BANNER_MST', raw, key, 595)}
