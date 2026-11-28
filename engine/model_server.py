"""A model server the person already runs on this computer (Ollama, llama.cpp's llama-server), reached over loopback only.

assistant.py sends its questions through model_open; Setup lists a server's models with list_models before the person
chooses one. Nothing here runs until the person asks: no address is tried on its own (#78).
"""
import json, re, urllib.error, urllib.request

LOOPBACK = re.compile(r'http://(127\.0\.0\.1|\[::1\]):\d+(/[^\s]*)?')
LIST_TIMEOUT = 2.5      # seconds: a server on this computer answers its model list at once, or not at all
MAX_MODELS = 200        # more than anyone runs; a longer list is cut, not refused
MAX_ID = 200            # characters in one model's name


def loopback_base(value):
    """The model server's address, or ValueError for anything off this computer. 'localhost' becomes 127.0.0.1: a hosts file could point the name anywhere."""
    base = re.sub(r'^http://localhost:', 'http://127.0.0.1:', value.rstrip('/'))
    if not re.fullmatch(r'http://(127\.0\.0\.1|\[::1\]):\d+', base):
        raise ValueError('not a loopback http address')
    return base


def typed_base(text):
    """What the person typed in Setup, as loopback_base wants it: '127.0.0.1:11434', 'localhost:8080/v1', 'http://[::1]:8080/'."""
    t = str(text or '').strip()
    if not re.match(r'^[a-z]+://', t, re.I):
        t = 'http://' + t
    t = re.sub(r'/v1/?$', '', t.rstrip('/'))     # the address servers print for OpenAI clients ends in /v1
    base = loopback_base(t)
    port = int(base.rsplit(':', 1)[1])
    if not 0 < port < 65536:
        raise ValueError('no such port')
    return base


def shown(base):
    """The address as Setup shows it: no scheme, so our pages hold no web address."""
    return base[len('http://'):]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None     # the answer comes back as an error instead of being followed: a redirect could lead off this computer


_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)    # ProxyHandler({}): a proxy set on this computer would carry the conversation out


def model_open(req, timeout):
    """The only way out of this program to a model, and it goes no further than this computer."""
    url = req if isinstance(req, str) else req.full_url
    if not LOOPBACK.fullmatch(url):
        raise urllib.error.URLError('not a loopback address')
    return _opener.open(req, timeout=timeout)


def list_models(text):
    """{'base', 'models'} from the server's /v1/models, or {'error', 'code'} in words Setup can show."""
    try:
        base = typed_base(text)
    except ValueError:
        return {'code': 'not_here', 'error': 'Lastbook only uses a model server on this computer. Use an address like 127.0.0.1:11434.'}
    where = shown(base)
    try:
        with model_open(base + '/v1/models', timeout=LIST_TIMEOUT) as r:
            data = json.loads(r.read(1 << 20))
    except urllib.error.HTTPError as e:
        e.close()
        if e.code in (401, 403):
            return {'code': 'needs_key', 'error': f'The server at {where} asks for a key. Lastbook cannot send one yet. Start it without a key.'}
        return {'code': 'no_list', 'error': f'The server at {where} answered, but not with a list of models (error {e.code}).'}
    except (urllib.error.URLError, OSError):
        return {'code': 'no_answer', 'error': f'Nothing answers at {where}. Check that the model server is running and the port is right.'}
    except ValueError:
        return {'code': 'no_list', 'error': f'The server at {where} answered, but not with a list of models.'}
    rows = data.get('data') if isinstance(data, dict) else None
    ids = [m['id'] for m in rows if isinstance(m, dict) and isinstance(m.get('id'), str) and 0 < len(m['id']) <= MAX_ID] if isinstance(rows, list) else None
    if ids is None:
        return {'code': 'no_list', 'error': f'The server at {where} answered, but not with a list of models.'}
    if not ids:
        return {'code': 'no_models', 'error': f'The server at {where} has no models loaded.'}
    return {'base': base, 'address': where, 'models': ids[:MAX_MODELS]}
