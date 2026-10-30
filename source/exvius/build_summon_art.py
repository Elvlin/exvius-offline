"""Index original image dimensions and same-campaign wide alternatives."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('FFBE_DATA', str(ROOT / 'data'))
os.environ.update(GACHA_ONLY='off', GACHA_CAMPAIGN='all', GACHA_STANDARD='1')
sys.path[:0] = [str(ROOT / 'source/server'), str(ROOT / 'tools/vendor/python')]
from PIL import Image
from ffbe_gacha import all_banners, banner_art_index


def main():
    index = banner_art_index()
    images, wide = {}, {}
    banners = all_banners()
    for banner in banners:
        art = banner.get('art') or {}
        for role in ('banner', 'detail_banner', 'detail_extra'):
            values = art.get(role) or []
            for name in values if isinstance(values, list) else [values]:
                if not name or name in images:
                    continue
                with Image.open(index[name]) as image:
                    images[name] = [image.width, image.height]
        main_image = art.get('banner')
        if not main_image or main_image not in images:
            continue
        width, height = images[main_image]
        if width / height < 2.8:
            continue
        for role in ('detail_banner', 'detail_extra'):
            values = art.get(role) or []
            for name in values if isinstance(values, list) else [values]:
                if name and images[name][0] / images[name][1] < 2.8:
                    wide.setdefault(name, main_image)
    result = {'version': 1, 'images': images, 'wide': wide}
    destination = ROOT / 'source/server/summon_art.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Indexed', len(images), 'original/approved images and', len(wide), 'same-campaign wide alternatives')


if __name__ == '__main__':
    main()
