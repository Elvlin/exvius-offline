"""Update the existing native News menu data and its original banner pack."""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def configuration():
    return json.loads((ROOT / 'source/server/content/news_menu.json').read_text('utf-8'))


def rewrite_banner_cache(raw, key):
    from prepare_offline_cache import cbc_decrypt, cbc_encrypt, json_record, key16
    config = configuration()
    replacements = {str(row['id']): row for row in config['banners']}
    output, seen = [], set()
    for line in raw.decode('ascii').splitlines():
        if not line:
            continue
        plain = cbc_decrypt(key16(key), line)
        row = json_record(plain)
        if row.get('w2A76noc') == '1' and str(row.get('6Dgaqir0', '')).startswith('SMBanner_'):
            update = replacements.get(str(row['fSxqkF10']))
            if update:
                row.update(G4L0YIB2=update['name'])
                row['1X65WPLU'] = update['url']
                assert row['6Dgaqir0'] == update['image']
                pad = plain[-1]
                double = 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad
                line = cbc_encrypt(key16(key), json.dumps(row, ensure_ascii=False,
                                   separators=(',', ':')).encode('utf-8'), double_pad=double)
                seen.add(str(row['fSxqkF10']))
            elif config['hide_other_social_banners']:
                continue
        output.append(line)
    assert seen == set(replacements), 'Original social-menu banner IDs were not all found'
    return ('\n'.join(output) + '\n').encode('ascii')


def build_files():
    from cricodecs import cpk
    from fill_content_from_memorial import global_cpk_header
    from PIL import Image
    source = ROOT / 'data/client/files/en/sd/banner/Ver328_banner1.cpk'
    archive = cpk.load(str(source))
    entries = {Path(entry.full_path).name: index for index, entry in enumerate(archive.file_infos())}
    before = {entry.full_path: archive.file_bytes(index) for index, entry in enumerate(archive.file_infos())}
    changed = set()
    for row in configuration()['banners']:
        name = row['image']
        image = ROOT / 'source/server/assets/banner_art' / name
        with Image.open(image) as picture:
            assert picture.size == (600, 120), (name, picture.size)
        archive.replace_bytes(entries[name], image.read_bytes())
        changed.add(name)
    packet = archive.save_bytes()
    header_size = 16 + struct.unpack_from('<Q', packet, 8)[0]
    packet = global_cpk_header(packet[:header_size]) + packet[header_size:]
    verify = cpk.Cpk.load_bytes(packet)
    for index, entry in enumerate(verify.file_infos()):
        expected = ((ROOT / 'source/server/assets/banner_art' / Path(entry.full_path).name).read_bytes()
                    if Path(entry.full_path).name in changed else before[entry.full_path])
        assert verify.file_bytes(index) == expected, entry.full_path
    return {'native/en/sd/banner/Ver328_banner1.cpk': packet}
