"""Shortlist summon artwork with weak or incomplete decorative borders.

Read-only image analysis. A detected border does not certify its artistic style.
Width and height are reported separately and never used as evidence of a frame.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def art_index():
    roots = [ROOT / p for p in (
        'data/cpk_extract/en/banner', 'data/cpk_extract/en/gacha',
        'data/cpk_extract/common_lang/banner', 'data/cpk_extract/common_lang/gacha',
        'data/gacha_community/art', 'data/client/files/en/sd/static_banner',
        'data/client/files/common_lang/sd/static_banner',
        'source/server/assets/banner_art')]
    result = {}
    for root in roots:
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                result.setdefault(path.name, path)
    return result


def resolve(name, index):
    # Exact native files win before the native basename fallback index.
    for base in ('data/overlay', 'data/client/files'):
        path = ROOT / base / 'en/sd/static_banner/gacha/main' / name
        if path.is_file():
            return path
    return index.get(name)


def frame_metrics(path):
    with Image.open(path) as im:
        width, height = im.size
        rgba = np.asarray(im.convert('RGBA').resize((640, max(40, round(height * 640 / width)))))
    rgb = rgba[:, :, :3].astype(float)
    r, g, b = rgb.transpose(2, 0, 1)
    high, low = rgb.max(2), rgb.min(2)
    # Gold or silver decorative strokes. Alpha and luminance reject empty edges.
    metal = (((r > 125) & (g > 85) & (r >= g * .90) & (g > b * 1.10)) |
             ((low > 100) & (high - low < 55))) & (rgba[:, :, 3] > 200)
    h, w = metal.shape
    # Retail strips can inset their complete frame by 15-22 pixels.
    depth = min(32, max(12, h // 4))
    mx, my = round(w * .08), round(h * .08)
    strips = {'top': metal[:depth, mx:-mx], 'bottom': metal[-depth:, mx:-mx],
              'left': metal[my:-my, :depth].T, 'right': metal[my:-my, -depth:].T}
    coverage = {}
    for side, strip in strips.items():
        # Permit a three-pixel curved/antialiased stroke, not arbitrary bright art.
        scores = [np.any(strip[i:i+3], axis=0).mean() for i in range(len(strip)-2)]
        coverage[side] = round(float(max(scores, default=0)), 4)
    corners = []
    for corner in (metal[:depth, :depth], metal[:depth, -depth:],
                   metal[-depth:, :depth], metal[-depth:, -depth:]):
        corners.append(round(float(corner.mean()), 4))
    weak = [side for side, value in coverage.items() if value < .50]
    reason = 'weak border on ' + ', '.join(weak) if weak else ''
    if not reason and min(corners) < .025:
        reason = 'weak or empty corner decoration'
    return {'width': width, 'height': height, **coverage,
            'min_corner': min(corners), 'result': 'REVIEW' if reason else 'BORDER_DETECTED',
            'reason': reason}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    document = json.loads((ROOT / 'source/server/summon/index.json').read_bytes())
    listed = {str(i) for group in document['groups'] for i in group['ids']}
    index = art_index()
    cache, rows = {}, []
    for banner in document['banners']:
        if str(banner['id']) not in listed:
            continue
        name = banner.get('art', {}).get('banner', '')
        path = resolve(name, index)
        if path and path not in cache:
            cache[path] = frame_metrics(path)
        metrics = cache[path] if path else {'result': 'MISSING_IMAGE', 'reason': 'image not resolved'}
        rows.append({'id': str(banner['id']), 'name': banner['name'], 'image': name,
                     'path': path.relative_to(ROOT).as_posix() if path else '', **metrics})
    fields = ['id','name','image','path','width','height','top','bottom','left','right',
              'min_corner','result','reason']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    candidates = args.output.with_name(args.output.stem + '-candidates.csv')
    with candidates.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(row for row in rows if row['result'] != 'BORDER_DETECTED')
    summary = {'listed_banners': len(rows), 'unique_images': len(cache),
               'review_banners': sum(r['result'] == 'REVIEW' for r in rows),
               'review_unique_images': len({r['path'] for r in rows if r['result'] == 'REVIEW'}),
               'width_640_review_banners': sum(r['result'] == 'REVIEW' and r.get('width') == 640 for r in rows),
               'missing_images': sum(r['result'] == 'MISSING_IMAGE' for r in rows),
               'limitation': 'Border continuity shortlist only. BORDER_DETECTED does not certify Global style.'}
    args.output.with_suffix('.json').write_text(json.dumps({'summary': summary, 'entries': rows}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
