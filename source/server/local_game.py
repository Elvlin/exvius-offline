"""Call the existing game request handler directly, using local data and saves.

This adapter opens no listener and uses no HTTP client. The existing handler
continues to own request decoding, gameplay, response encoding and persistence.
One data root and save slot are supported per interpreter, as in the original
engine. The Android runtime connection is separate from this transport adapter.
"""
from email.message import Message
from http.client import parse_headers
import io
import os
from pathlib import Path
import re
import sys
from typing import NamedTuple


class LocalResponse(NamedTuple):
    status: int
    headers: dict
    body: bytes


class LocalGame:
    _active = None

    def __init__(self, data, slot='campaign'):
        root = str(Path(data).resolve())
        if not re.fullmatch(r'[A-Za-z0-9_-]+', slot):
            raise ValueError('Invalid local save slot.')
        if self.__class__._active is not None:
            if self.__class__._active != (root, slot):
                raise RuntimeError('This interpreter already owns a different local game.')
            self.server = sys.modules['capture_server']
            return
        bound = sys.modules.get('data_paths')
        if bound is not None and bound.DATA_ROOT != root:
            raise RuntimeError('The game data paths were already bound to a different directory.')
        os.environ['FFBE_DATA'] = root
        # Reuse the existing complete catalogue modes, rather than inheriting
        # the upstream development file's single-banner test selection.
        os.environ.setdefault('GACHA_ONLY', 'all')
        os.environ.setdefault('GACHA_CAMPAIGN', 'all')
        os.environ.setdefault('EXVIUS_SUMMON_ARCHIVE', '1')
        os.environ.setdefault('EXVIUS_EVENT_ARCHIVE', '1')
        # The permanent families (Arena, EXVIUS, 5+1 Ticket) fill the Standard Summon tab.
        os.environ.setdefault('GACHA_STANDARD', '1')
        # Anonymous IDs now serve documented Global campaigns. Their calendar
        # aliases are merged below so each campaign appears once.
        os.environ.setdefault('GACHA_CATALOGUE', '1')
        import capture_server
        result = capture_server.main(['--data', root, '--state', slot], in_process=True)
        if result != 0:
            raise RuntimeError('Existing game initialization failed: ' + str(result))
        self.server = capture_server
        self.__class__._active = (root, slot)

    def request(self, method, path, body=b'', headers=None):
        if method not in {'GET', 'HEAD', 'POST'}:
            raise ValueError('The local game supports GET, HEAD and POST.')
        if not path.startswith('/') or path.startswith('//') or '\r' in path or '\n' in path:
            raise ValueError('Expected a local request path.')
        if isinstance(body, str):
            body = body.encode('utf-8')
        handler = self.server.Handler.__new__(self.server.Handler)
        handler.command = method
        handler.path = path
        handler.request_version = 'HTTP/1.1'
        handler.requestline = method + ' ' + path + ' HTTP/1.1'
        handler.client_address = ('127.0.0.1', 0)
        handler.close_connection = True
        handler.headers = Message()
        for name, value in (headers or {}).items():
            if name.lower() != 'content-length':
                handler.headers[name] = str(value)
        if not handler.headers.get('Content-Type'):
            handler.headers['Content-Type'] = 'application/json'
        handler.headers['Content-Length'] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        with self.server.STATE_LOCK:
            getattr(handler, 'do_' + method)()
        output = io.BytesIO(handler.wfile.getvalue())
        status = int(output.readline().split(b' ', 2)[1])
        response_headers = dict(parse_headers(output).items())
        return LocalResponse(status, response_headers, output.read())
