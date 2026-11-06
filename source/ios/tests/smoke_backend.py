"""Exercise the existing local backend with synthetic data, without game assets."""
from pathlib import Path
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import traceback

sys.dont_write_bytecode = True
SERVER = Path(__file__).resolve().parents[2] / 'server'


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(root):
    # This is a standalone process: discard inherited gameplay/test overrides
    # before importing modules whose configuration is bound at import time.
    retained = {k: v for k, v in os.environ.items()
                if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP',
                                 'HOME', 'USERPROFILE', 'LANG', 'LC_ALL'}}
    os.environ.clear()
    os.environ.update(retained)
    for relative in ('mst_decoded', 'text_decoded', 'cpk_extract', 'overlay',
                     'client/files', 'client/shared_prefs', 'state'):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / 'client/shared_prefs/gamedata.xml').write_text('<map/>', encoding='utf-8')
    # The real table reader requires files even when they contain no records.
    # Materialize only table names declared by the backend, never game content.
    table_names = set()
    for source in SERVER.glob('*.py'):
        table_names.update(re.findall(r'F_[A-Z0-9_]+\.ndjson',
                                     source.read_text(encoding='utf-8')))
    for name in table_names:
        (root / 'mst_decoded' / name).write_text('', encoding='utf-8')
    # Minimal authored identities for the engine's two default starter units.
    # No stats, text, artwork, or original master-table records are copied.
    (root / 'mst_decoded/F_UNIT_MST.ndjson').write_text(
        '\n'.join(json.dumps({'3HriTp6B': mid})
                  for mid in ('100000102', '100000202')) + '\n', encoding='utf-8')
    (root / 'mst_decoded/F_EQUIP_ITEM_MST.ndjson').write_text(
        '\n'.join(json.dumps({'J1YX9kmM': item})
                  for item in ('302000100', '404000200', '406000100', '409000100'))
        + '\n', encoding='utf-8')
    resource = b'ios-backend-smoke\x00\xff'
    (root / 'client/files/smoke.bin').write_bytes(resource)
    endpoints = json.loads((SERVER / 'endpoints.json').read_text(encoding='utf-8'))
    endpoint = endpoints['by_class']['GameSettingRequest']
    fixture = root / 'responses.json'
    fixture.write_text(json.dumps({endpoint['request_id']: {'smoke_marker': 'local'}}),
                       encoding='utf-8')
    os.environ.update(FFBE_DATA=str(root), FFBE_CRYPTO='cryptography',
                      REPLIES=str(fixture), SEASON='off',
                      FRIENDS_FILE=str(root / 'friends.yaml'))

    def deny_network(event, args):
        if event in {'socket.__new__', 'socket.bind', 'socket.connect', 'socket.getaddrinfo'}:
            raise RuntimeError('Unexpected network operation: ' + event)
    sys.addaudithook(deny_network)
    sys.path.insert(0, str(SERVER))
    from local_game import LocalGame
    from player_state import PlayerState
    import ffbe_crypto as crypto
    from ffbe_pipeline import validate_pipeline

    game = LocalGame(root, slot='ios_smoke')
    check(crypto.backend() == 'cryptography', 'External crypto fallback selected')
    check(not validate_pipeline(), 'Invalid gameplay pipeline ordering')
    response = game.request('GET', '/smoke.bin')
    check(response.status == 200 and response.body == resource, 'Local resource mismatch')

    key = crypto.key16(endpoint['encode_key'])
    body = json.dumps({
        'TEAYk6R1': {'z5hB3P01': endpoint['request_id'],
                     'ytHoz4E2': '1', '9K0Pzcpd': '1166'},
        't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, b'{}', double_pad=True)},
    }).encode()
    response = game.request('POST', endpoint['url'], body)
    check(response.status == 200, 'Encrypted request failed')
    envelope = json.loads(response.body)
    plain = crypto.cbc_decrypt(key, envelope['t7n6cVWf']['qrVcDe48'])
    # The existing client protocol uses a second PKCS padding layer.
    pad = plain[-1]
    check(1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad,
          'Missing inner response padding')
    check(json.loads(plain[:-pad])['smoke_marker'] == 'local', 'Response dispatch mismatch')
    records = list((root / 'state/requests').glob('*.json'))
    check(len(records) == 1, 'Expected one request audit record')
    record = json.loads(records[0].read_text(encoding='utf-8'))
    check(json.JSONDecoder().raw_decode(record['plaintext'])[0] == {},
          'Request decryption mismatch')
    check(not record['decrypt_error'], 'Backend recorded a decryption error')

    player = game.server.State.player
    before = player.currencies['lapis_free']
    player.add_currency('lapis_free', 100)
    check(player.spend_currency('lapis_free', 25), 'Currency debit failed')
    check(not player.spend_currency('lapis_free', before + 101), 'Overdraft accepted')
    game.server.st.save_state()
    saved = root / 'state/ios_smoke.json'
    check(saved.is_file(), 'Save was not created')
    restored = PlayerState.load(str(saved), slot='ios_smoke', mode='live')
    check(restored.currencies['lapis_free'] == before + 75, 'Save reload mismatch')


def main():
    log = io.StringIO()
    try:
        # Existing backend diagnostic relpath calls require the same drive on
        # Windows. Keep fixtures beneath this ignored, task-specific directory.
        scratch = (Path(__file__).resolve().parents[1] / '.local').resolve()
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='backend-smoke-', dir=scratch) as directory:
            check(Path(directory).resolve().is_relative_to(scratch),
                  'Temporary directory escaped smoke workspace')
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                run(Path(directory))
    except Exception:
        print(log.getvalue(), file=sys.stderr)
        traceback.print_exc()
        return 1
    print('PASS: engine initialization, pipeline validation, local resource serving,')
    print('encrypted request/response, currency debit/overdraft, save and reload.')
    print('Network operations blocked; temporary fixtures and saves removed.')
    print('Synthetic data only: no client, summon, battle, or iOS runtime validation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
