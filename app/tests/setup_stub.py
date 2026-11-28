"""A fake /api/setup/* for building the setup screens. Never shipped (app/tests/ is left out of the package).

Run:  python3 app/tests/setup_stub.py [port]      (default 8925)
Then open http://127.0.0.1:8925/__stub/<scenario> to reset to a scenario, which redirects to the setup page.
Scenarios (see SCENARIOS): mac, mac-small (AI does not fit), win, found, low-disk, paused (a restart picked up a job),
network, server, checksum, unpack, activate (each fails once at that step; Retry then goes through), busy (the server
answers 503 for 2 minutes, then the download goes on), manage, manage-ai, upgraded,
manage-notify (app update notices already on), updates-fail (saving the preference fails).
The page itself never knows it talks to a stub.
"""
import copy
import json
import mimetypes
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'web')
GB = 1000 ** 3
GiB = 1024 ** 3
X = '<img src=x onerror="window.PWN=1">'

MANIFEST = {
    'source': 'bundled',
    'packs': [
        {'id': 'small', 'title': 'Small', 'summary': 'The essential manuals: first aid, water, food, shelter and power.', 'records': 315,
         'installed_bytes': 8236931672, 'available': True,
         'files': [{'name': 'Lastbook-Small.zip', 'size': 8236931672, 'kind': 'zip'}]},
        {'id': 'medium', 'title': 'Medium', 'summary': 'Adds videos, maps and many more manuals.', 'records': 2410,
         'installed_bytes': 67100000000, 'available': True,
         'files': [{'name': 'Lastbook-Medium.zip', 'size': 66400000000, 'kind': 'zip'}]},
        {'id': 'all', 'title': 'All', 'summary': 'Everything, with the full encyclopedias.', 'records': 9100,
         'installed_bytes': 268000000000, 'available': False,
         'files': [{'name': 'Lastbook-All.zip', 'size': 262000000000, 'kind': 'zip'}]},
    ],
    'models': [
        {'id': 'gemma-4-26b-a4b', 'title': 'Gemma 4 26B A4B', 'file': 'gemma-4-26B-A4B-it-UD-Q4_K_M.gguf',
         'size': 16947541728, 'memory_bytes': 19027384256, 'available': True},
    ],
    'maps': [   # as docs/SETUP-API.md "State maps"; sizes are made up until map-packages lists the real ones
        {'id': st, 'title': t, 'kind': 'state', 'installed_bytes': inst, 'available': ok,
         'includes': 'Local streets, buildings, terrain and crops, plus water, help and resource points',
         'files': [{'name': f'Lastbook-Map-{st}.zip', 'size': dl, 'kind': 'zip'}]}
        for st, t, dl, inst, ok in [('AZ', 'Arizona', 1600000000, 3900000000, True), ('CA', 'California', 2100000000, 5000000000, True),
                                    ('NV', 'Nevada', 900000000, 2200000000, True), ('OR', 'Oregon', 1100000000, 2700000000, True),
                                    ('RI', 'Rhode Island', 120000000, 300000000, True), ('TX', 'Texas', 0, 0, False)]
    ],
}

def _hostile():
    m = copy.deepcopy(MANIFEST)
    for e in m['packs'] + m['models'] + m['maps']:
        e.update(title=X, summary=X, includes=X)
    m['maps'][0]['installed_bytes'] = X
    m['maps'][1]['id'] = X
    return m


HOSTILE = _hostile()

MAC = '/Users/you/Library/Application Support/Lastbook/LastbookData'
WIN = 'C:\\Users\\you\\Documents\\LastbookData'


def hw(os_='macos', ram=32, free=412, fits=True, gpus=None, why=None):
    root = '/' if os_ == 'macos' else 'C:\\'
    disks = [{'path': root, 'name': 'Macintosh HD' if os_ == 'macos' else 'Local Disk (C:)', 'free_bytes': int(free * GB), 'total_bytes': int(994 * GB)}]
    if os_ == 'windows':
        disks.append({'path': 'D:\\', 'name': 'Data (D:)', 'free_bytes': int(1800 * GB), 'total_bytes': int(2000 * GB)})
    return {'os': os_, 'arch': 'arm64' if os_ == 'macos' else 'x64', 'ram_bytes': ram * GiB, 'unified_memory': os_ == 'macos',
            'gpus': gpus or [], 'disks': disks,
            'ai': {'fits': fits, 'needs_bytes': 19027384256 + int(2.5 * GiB), 'estimate': True,
                   'why': why or ('This computer has enough memory for the local AI.' if fits else
                                  f'The local AI needs about 20 GB of memory, and this computer has {ram} GB.')}}


SCENARIOS = {
    'mac': dict(hardware=hw(), recommend={'pack': 'medium', 'ai': True, 'why': 'There is plenty of room and memory, so Medium with the local AI fits well.'}),
    'mac-small': dict(hardware=hw(ram=16, free=120, fits=False), recommend={'pack': 'medium', 'ai': False, 'why': 'Medium fits on this disk; the local AI needs more memory than this Mac has.'}),
    'win': dict(hardware=hw('windows', ram=32, free=300, gpus=[{'name': 'NVIDIA GeForce RTX 4070', 'vram_bytes': 12 * GiB}]),
                recommend={'pack': 'medium', 'ai': True, 'why': 'The graphics card and memory are enough for the local AI, and Medium fits on this disk.'}),
    'found': dict(hardware=hw(), recommend={'pack': 'small', 'ai': True, 'why': 'You already downloaded Small, so it can be used straight away.'},
                  found=[{'path': '/Users/you/Downloads/Lastbook-Small.zip', 'kind': 'pack', 'id': 'small', 'name': 'Lastbook-Small.zip', 'size': 8236931672, 'size_ok': True},
                         {'path': '/Users/you/Downloads/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf', 'kind': 'model', 'id': 'gemma-4-26b-a4b', 'name': 'gemma-4-26B-A4B-it-UD-Q4_K_M.gguf', 'size': 16947541728, 'size_ok': True}]),
    'found-bad': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'You already downloaded Small.'}, fault=('verifying', 'found_mismatch'),
                      found=[{'path': '/Users/you/Downloads/Lastbook-Small.zip', 'kind': 'pack', 'id': 'small', 'name': 'Lastbook-Small.zip', 'size': 8236931672, 'size_ok': True}]),
    'paused-found': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': ''},   # killed while unpacking the person's own zip
                         found=[{'path': '/Users/you/Downloads/Lastbook-Small.zip', 'kind': 'pack', 'id': 'small', 'name': 'Lastbook-Small.zip', 'size': 8236931672, 'size_ok': True}],
                         job={'pack': 'small', 'ai': False, 'state': 'paused', 'done0': 0, 'source': 'found', 'paused_from': 'unpacking'}),
    'low-disk': dict(hardware=hw(free=30), recommend={'pack': 'small', 'ai': False, 'why': 'This disk has 30 GB free, so only Small fits.'}),
    'paused': dict(hardware=hw(), recommend={'pack': 'medium', 'ai': True, 'why': ''}, job={'pack': 'medium', 'ai': True, 'state': 'paused', 'done0': 0.37}),
    'network': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, fault=('downloading', 'network')),
    'server': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, fault=('downloading', 'server')),
    'busy': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, fault=('downloading', 'busy')),
    'checksum': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, fault=('verifying', 'checksum')),
    'unpack': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, fault=('unpacking', 'unpack')),
    'activate': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, fault=('activating', 'activate')),
    'manage': dict(mode='manage', hardware=hw(), current={'folder': MAC, 'pack': 'small', 'model': None, 'map': 'base'},
                   recommend={'pack': 'medium', 'ai': True, 'why': 'There is room for Medium and memory for the local AI.'}),
    'manage-ai': dict(mode='manage', hardware=hw('windows', ram=32, free=300, gpus=[{'name': 'NVIDIA GeForce RTX 4070', 'vram_bytes': 12 * GiB}]),
                      current={'folder': WIN, 'pack': 'medium', 'model': 'gemma-4-26b-a4b', 'map': 'CA'},
                      recommend={'pack': 'medium', 'ai': True, 'why': 'You have Medium and the local AI.'}),
    # every string the engine or a fetched manifest hands the page carries markup; nothing may come out live (security audit C)
    'hostile': dict(hardware={**hw(gpus=[{'name': X, 'vram_bytes': 8 * GiB}], why=X), 'unified_memory': False},
                    recommend={'pack': 'small', 'ai': True, 'why': X}, manifest='hostile',
                    found=[{'path': '/Users/you/Downloads/' + X + '.zip', 'kind': 'pack', 'id': 'small', 'name': X, 'size': X, 'size_ok': True},
                           {'path': '/Users/you/' + X, 'kind': 'library', 'name': X, 'size': 5, 'rejected': True}],
                    fault=('downloading', 'hostile')),
    'upgraded': dict(mode='manage', hardware=hw(), current={'folder': MAC, 'pack': 'medium', 'model': None,
                     'old': [MAC + '.old-2026-11-12']},
                     recommend={'pack': 'medium', 'ai': True, 'why': ''}),
    # "Notify me about app updates" already turned on (Settings shows it ticked); 'updates-fail': saving the setting fails
    'manage-notify': dict(mode='manage', hardware=hw(), current={'folder': MAC, 'pack': 'small', 'model': None, 'map': 'base'},
                          recommend={'pack': 'medium', 'ai': True, 'why': ''}, notify=True),
    'updates-fail': dict(hardware=hw(), recommend={'pack': 'small', 'ai': False, 'why': 'Small fits.'}, updates_fail=True),
}

SCENARIOS['hostile']['hardware']['disks'][0]['name'] = X

RATE = 2.2 * GB        # pretend bytes per second, so a whole run takes about half a minute
STEP_S = 2.5           # seconds each of checking, unpacking and finishing takes
CHECK_S = 12           # seconds a repair's check of each item takes, long enough to watch it count


class Stub:
    def __init__(self, name):
        self.name = name
        s = copy.deepcopy(SCENARIOS[name])   # each reset starts clean
        self.s = s
        self.M = HOSTILE if s.get('manifest') == 'hostile' else MANIFEST
        self.current = s.get('current')
        self.job = None
        self.fault = s.get('fault')
        self.busy_until = None
        self.found = s.get('found', [])
        self.notify = s.get('notify', False)     # as engine/update.py: off unless turned on
        self.folder = (self.current or {}).get('folder') or (WIN if s['hardware']['os'] == 'windows' else MAC)
        if 'job' in s:
            j = s['job']
            self._make(j['pack'], j['ai'])
            it = self.job['items'][0]
            it['bytes_done'] = int(it['bytes_total'] * j['done0'])
            if j.get('source'):
                it.update(source=j['source'], paused_from=j['paused_from'], bytes_done=1700000000, bytes_total=8236695548)   # as the engine: unpack progress
            self._set_all('paused')

    def state(self):
        self.tick()
        return {'mode': self.s.get('mode', 'first-run'), 'hardware': self.s['hardware'], 'manifest': self.M,
                'current': self.current, 'found': self.found, 'recommend': {**self.s['recommend'], 'folder': self.folder.rsplit('\\' if '\\' in self.folder else '/', 1)[0]},
                'job': self.public()}

    def _make(self, pack, ai, use=None, map_=None):
        items = []
        cur = self.current or {}
        if pack and pack != cur.get('pack'):
            p = next(p for p in self.M['packs'] if p['id'] == pack)
            items.append({'id': pack, 'kind': 'pack', 'title': p['title'], 'state': 'waiting', 'bytes_done': 0,
                          'bytes_total': sum(f['size'] for f in p['files']), 'rate_bps': 0, 'eta_s': None, 'error': None})
        if map_ and map_ != cur.get('map'):
            m = next(m for m in self.M['maps'] if m['id'] == map_)
            items.append({'id': map_, 'kind': 'map', 'title': m['title'], 'state': 'waiting', 'bytes_done': 0,
                          'bytes_total': sum(f['size'] for f in m['files']), 'rate_bps': 0, 'eta_s': None, 'error': None})
        if ai and not cur.get('model'):
            m = self.M['models'][0]
            items.append({'id': m['id'], 'kind': 'model', 'title': m['title'], 'state': 'waiting', 'bytes_done': 0,
                          'bytes_total': m['size'], 'rate_bps': 0, 'eta_s': None, 'error': None})
        for it in items:    # as the engine: a file of the right size already here is used, and checked from its first byte
            ok = [f for f in self.found if f['id'] == it['id'] and f['kind'] == it['kind'] and f.get('size_ok') and not f.get('rejected')]
            it['source'] = 'found' if ok else 'download'
            if use and any(f['path'] == use for f in ok):
                it['use'] = True
        self.job = {'id': 'j1', 'state': 'waiting', 'items': items, 'error': None, 'started': time.time(), 'folder': self.folder}
        self.last = time.time()
        self.phase_t = 0.0

    def _set_all(self, st):
        for it in self.job['items']:
            if it['state'] not in ('done',):
                it['state'] = st
        self.job['state'] = st

    def need(self, pack, ai, map_=None):
        cur = self.current or {}
        n = 2 * GB
        if map_ and map_ != cur.get('map'):
            m = next(m for m in self.M['maps'] if m['id'] == map_)
            n += sum(f['size'] for f in m['files']) + m['installed_bytes']
        if pack and pack != cur.get('pack'):
            p = next(p for p in self.M['packs'] if p['id'] == pack)
            n += sum(f['size'] for f in p['files']) + p['installed_bytes']
        if ai and not cur.get('model'):
            n += self.M['models'][0]['size']
        return n

    def free(self):
        return self.s['hardware']['disks'][0]['free_bytes'] if not self.folder.startswith('D:') else self.s['hardware']['disks'][1]['free_bytes']

    def start(self, body):
        pack, ai = body.get('pack'), bool(body.get('ai'))
        if body.get('folder'):
            self.folder = body['folder']
        need = self.need(pack, ai, body.get('map'))
        if body.get('repair'):
            self._make(None, False)
            p = next(p for p in self.M['packs'] if p['id'] == self.current['pack'])
            # as the engine answers: the job says it is a repair, and every item is still waiting
            self.job['items'] = [{'id': p['id'], 'kind': 'pack', 'title': p['title'], 'state': 'waiting', 'bytes_done': 0, 'source': 'download',
                                  'bytes_total': p['installed_bytes'], 'rate_bps': 0, 'eta_s': None, 'error': None}]
            if self.current.get('model'):    # the installed AI file is found on this computer and checked after the library
                m = self.M['models'][0]
                self.job['items'].append({'id': m['id'], 'kind': 'model', 'title': m['title'], 'state': 'waiting', 'bytes_done': 0,
                                          'source': 'found', 'bytes_total': m['size'], 'rate_bps': 0, 'eta_s': None, 'error': None})
            self.job['repair'] = True
            return self.public()
        if need > self.free():
            return {'error': 'There is not enough room on this disk.', 'code': 'no_space', 'need_bytes': need, 'free_bytes': self.free()}
        self._make(pack, ai, map_=body.get('map'))
        if not self.job['items']:
            return {'error': 'Nothing to add: this is what you have.', 'code': 'nothing'}
        return self.public()

    def tick(self):
        j = self.job
        if not j or j['state'] in ('paused', 'failed', 'done'):
            if j:
                self.last = time.time()
            return
        now = time.time()
        dt, self.last = now - self.last, now
        for it in j['items']:
            if it['state'] == 'done':
                continue
            if it['state'] in ('waiting', 'paused'):
                check = it.get('source') == 'found' or (j.get('repair') and it['kind'] == 'pack')   # a file already here, or the open library
                it['state'] = 'downloading' if it['bytes_done'] < it['bytes_total'] and not check else 'verifying'
            if it['state'] == 'downloading' and self.fault and self.fault[1] == 'busy' and it['bytes_done'] > it['bytes_total'] * 0.4:
                self.busy_until = self.busy_until or now + 120     # as the engine: no rate, and the time of the next try
                it['retry_in_s'], it['rate_bps'], it['eta_s'] = round(self.busy_until - now), 0, None
                if now >= self.busy_until:
                    self.fault = self.busy_until = None
                    it.pop('retry_in_s')
                break
            if it['state'] == 'downloading':
                it['bytes_done'] = min(it['bytes_total'], it['bytes_done'] + int(RATE * dt))
                it['rate_bps'] = int(RATE * (0.9 + 0.2 * ((now * 3) % 1)) / 50)   # show a believable rate
                it['eta_s'] = int((it['bytes_total'] - it['bytes_done']) / max(it['rate_bps'], 1))
                if self.fault and self.fault[0] == 'downloading' and self.fault[1] != 'busy' and it['bytes_done'] > it['bytes_total'] * 0.4:
                    return self._fail(it)          # busy does not fail: it waits, in the branch above, from the next tick
                if it['bytes_done'] >= it['bytes_total']:
                    it['state'], it['rate_bps'], it['eta_s'] = 'unpacking' if it['kind'] == 'map' else 'verifying', 0, None
                    self.phase_t = 0
            else:
                self.phase_t += dt
                if it['state'] == 'unpacking':     # as the engine: unpack progress in bytes, total = installed size
                    p = next((p for p in self.M['packs' if it['kind'] == 'pack' else 'maps'] if p['id'] == it['id']), None)
                    if p:
                        it['bytes_total'] = p['installed_bytes']
                        it['bytes_done'] = int(p['installed_bytes'] * min(1, self.phase_t / STEP_S))
                        it['eta_s'] = int(max(0, STEP_S - self.phase_t) * 40)
                span = CHECK_S if j.get('repair') else STEP_S
                counts = it['state'] == 'verifying' and (j.get('repair') or it.get('source') == 'found')
                if counts:                         # as the engine: a check of a whole file or library counts the bytes it reads
                    it['bytes_done'] = int(it['bytes_total'] * min(1, self.phase_t / span))
                    it['eta_s'] = int(max(0, span - self.phase_t) * 40)
                if self.phase_t >= (span if counts else STEP_S):
                    self.phase_t = 0
                    if self.fault and self.fault[0] == it['state']:
                        return self._fail(it)
                    order = ['verifying', 'unpacking', 'activating', 'done'] if it['kind'] == 'pack' else ['unpacking', 'done'] if it['kind'] == 'map' else ['verifying', 'activating', 'done']
                    if j.get('repair'):
                        order = ['verifying', 'done']
                    it['state'] = order[order.index(it['state']) + 1]
                    if it['state'] == 'unpacking':
                        it['bytes_done'] = 0     # as the engine: unpacking counts from nothing
            j['state'] = it['state'] if it['state'] != 'done' else j['state']
            break
        if all(it['state'] == 'done' for it in j['items']):
            j['state'] = 'done'

    def _fail(self, it):
        code = self.fault[1]
        msg = {'network': 'The download stopped: the connection to the internet was lost.',
               'server': 'The download stopped: the download server stayed busy.',
               'checksum': 'The file was damaged twice in a row.', 'unpack': 'The library could not be unpacked.',
               'activate': 'The new library could not be switched in.',
               'hostile': X,
               'found_mismatch': 'The Lastbook-Small.zip in Downloads doesn’t match the published file, so it was not used.'}[code]
        if code == 'found_mismatch':      # as the engine: the person's file is left alone, no longer offered, and retry downloads it
            for f in self.found:
                f.update(rejected=True, size_ok=False)
            it['bytes_done'] = 0
            it['source'] = 'download'
        it['state'], it['error'], it['rate_bps'], it['eta_s'] = 'failed', {'code': code, 'message': msg}, 0, None
        self.job['state'] = 'failed'
        self.job['error'] = {'code': code, 'message': msg, **({'file': self.found[0]['path']} if code == 'found_mismatch' else {})}
        self.fault = None   # it fails once; Retry goes through

    def act(self, a):
        j = self.job
        if not j:
            return {'error': 'No download is running.'}
        self.tick()
        if a == 'pause' and j['state'] == 'downloading':
            self._set_all('paused')
            for it in j['items']:
                it['rate_bps'], it['eta_s'] = 0, None
        elif a == 'resume' and j['state'] == 'paused':
            for it in j['items']:
                if it['state'] == 'paused':
                    it['state'] = 'waiting'
                    if it.get('source') == 'found':
                        it['bytes_done'] = it['bytes_total']
                    it.pop('paused_from', None)
            j['state'] = 'waiting'
            self.last = time.time()
        elif a == 'cancel':
            j['state'] = 'failed'
            j['error'] = {'code': 'cancelled', 'message': 'Cancelled.'}
            for it in j['items']:
                if it['state'] != 'done':
                    it['state'] = 'failed'
        elif a == 'retry' and j['state'] == 'failed':
            j['error'] = None
            for it in j['items']:
                if it['state'] == 'failed':
                    it['state'], it['error'] = 'waiting', None
                    if self.s.get('fault', ('',))[0] == 'verifying':
                        it['bytes_done'] = 0   # a damaged file is downloaded again
            j['state'] = 'waiting'
            self.last = time.time()
            self.phase_t = 0
        return self.public()

    def public(self):
        if not self.job:
            return None
        j = dict(self.job)
        j['items'] = [{k: v for k, v in it.items() if k != 'use'} for it in j['items']]
        return j


STUB = Stub('mac')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json'):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        global STUB
        u = urlparse(self.path)
        p = u.path
        if p.startswith('/__stub/'):
            name = p.split('/')[2]
            if name not in SCENARIOS:
                return self.send(404, {'error': 'scenarios: ' + ', '.join(SCENARIOS)})
            STUB = Stub(name)
            self.send_response(302)
            self.send_header('Location', '/ui/setup.html' + ('#manage' if SCENARIOS[name].get('mode') == 'manage' else ''))
            self.end_headers()
            return
        if p == '/api/setup/state':
            return self.send(200, STUB.state())
        if p == '/api/setup/job':
            STUB.tick()
            return self.send(200, STUB.public())
        if p == '/api/setup/updates':
            return self.send(200, {'supported': True, 'notify': STUB.notify, 'available': None, 'checking': False})
        if p in ('/', ''):
            return self.send(200, b'<!doctype html><title>Library</title><h1>The library would open here.</h1><p><a href="/ui/setup.html#manage">Library and local AI</a>', 'text/html')
        if p.startswith('/ui/'):
            f = os.path.normpath(os.path.join(WEB, p[4:]))
            if f.startswith(os.path.normpath(WEB)) and os.path.isfile(f):
                with open(f, 'rb') as fh:
                    return self.send(200, fh.read(), mimetypes.guess_type(f)[0] or 'application/octet-stream')
        return self.send(404, {'error': 'Not here.'})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            body = {}
        a = p.rsplit('/', 1)[-1]
        if a == 'start':
            r = STUB.start(body)
            return self.send(400 if r.get('error') else 200, r)
        if a in ('pause', 'resume', 'cancel', 'retry'):
            return self.send(200, STUB.act(a))
        if a == 'use':
            path = body.get('path', '')
            f = next((f for f in STUB.found if f['path'] == path), None)
            if not f:
                return self.send(400, {'error': 'That folder does not hold a Lastbook library.'})
            if f['kind'] == 'model' and STUB.s.get('mode') != 'manage':
                return self.send(200, {'job': None, 'noted': True})
            STUB._make(f['id'] if f['kind'] == 'pack' else None, f['kind'] == 'model', use=path)
            return self.send(200, STUB.public())
        if a == 'pick':      # the real engine: {path} or {path: null}; free_bytes and disk asked for in the contract
            if body.get('library'):
                return self.send(200, {'path': None, 'cancelled': True})
            other = 'D:\\LastbookData' if STUB.s['hardware']['os'] == 'windows' else '/Volumes/Big Disk/LastbookData'
            if STUB.s['hardware']['os'] == 'macos':
                STUB.s['hardware']['disks'].append({'path': '/Volumes/Big Disk', 'name': 'Big Disk', 'free_bytes': 1800 * GB, 'total_bytes': 2000 * GB})
            return self.send(200, {'path': other, 'free_bytes': 1800 * GB, 'disk': 'Data (D:)' if STUB.s['hardware']['os'] == 'windows' else 'Big Disk'})
        if a == 'updates':
            if STUB.s.get('updates_fail'):
                return self.send(400, {'error': 'Lastbook could not save this setting. Try again.', 'code': 'save'})
            STUB.notify = body.get('notify') is True
            print('stub: notify =', STUB.notify, flush=True)     # what a reviewer can watch: only a click on the box writes it
            return self.send(200, {'supported': True, 'notify': STUB.notify, 'available': None, 'checking': False})
        if a == 'remove-ai':
            if STUB.current:
                STUB.current['model'] = None
            return self.send(200, {'ok': True, 'freed_bytes': STUB.M['models'][0]['size']})
        if a == 'delete-old':
            if STUB.current:
                STUB.current['old'] = [o for o in STUB.current.get('old', []) if o != body.get('path')]
            return self.send(200, {'ok': True})
        if a == 'finish':
            if STUB.job and STUB.job['state'] == 'done' and STUB.job.get('repair'):
                STUB.job = None              # a repair leaves the library what it was
            elif STUB.job and STUB.job['state'] == 'done':
                cur = STUB.current or {'folder': STUB.folder, 'pack': None, 'model': None, 'map': 'base'}
                for it in STUB.job['items']:
                    if it['kind'] == 'pack' and it['id'] != 'repair':
                        cur['pack'] = it['id']
                        if not any(i['kind'] == 'map' for i in STUB.job['items']):
                            cur['map'] = next(p for p in STUB.M['packs'] if p['id'] == it['id']).get('map') or 'base'
                    if it['kind'] == 'model':
                        cur['model'] = it['id']
                    if it['kind'] == 'map':
                        cur['map'] = it['id']
                STUB.current, STUB.job = cur, None
            return self.send(200, {'ok': True})
        return self.send(404, {'error': 'Not here.'})


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8925
    print(f'setup stub on http://127.0.0.1:{port}/__stub/mac')
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
