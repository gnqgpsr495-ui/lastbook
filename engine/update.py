"""Check for updates, in the desktop app: when the person asks (About's button, or Lastbook > Check for Updates… on a Mac), and,
only for someone who turned on "Notify me about app updates", at most once a day while the app's window is open (Notices below).
The check only says whether a newer version is on the website. Then About offers one of:
  - Update now, only on a Mac build with a trusted Sparkle setup (app/update_macos.py, NATIVE here): pressing it starts Sparkle,
    which asks the person, verifies the signed archive, replaces Lastbook.app and relaunches. This module never downloads or runs it.
  - Open download page everywhere else (Windows, Linux, Mac builds without that setup, or when Sparkle fails): the official
    installer page in the system browser.

  - One small GET of METADATA through engine/setup/download.py, the one way out (HTTPS, no proxy). Only https://downloads.lastbook.org
    on port 443 is accepted, also after a redirect: not the bucket's r2.dev address, not Hugging Face.
  - METADATA (app-v1.json at the bucket root) is display information only: {"version": 1, "mac": {"version", "min_os"}, "windows": {...}}.
    Other fields (url, size, sha256, notes) may be there for later; they are not read.

Routes, under /api/update/: GET state; POST check; GET notice; POST auto; POST open; POST now (Update now: NATIVE only). Notices and the browser handoff require the
desktop app to call configure(). The setting itself is changed through
/api/setup/updates (Setup and Settings), which calls Notices.set_notify.
"""
import json
import os
import platform
import plistlib
import re
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from pathlib import Path

from engine.setup import download

METADATA = 'https://downloads.lastbook.org/app-v1.json'
HOST = 'downloads.lastbook.org'
VER = re.compile(r'^\d{1,6}(\.\d{1,6}){0,3}$')    # Windows builds have 5 digits (10.0.26200)
MAX_BODY = 4096
WEBSITE = 'lastbook.org'
DOWNLOAD_URL = f'https://{WEBSITE}/download/'

OFFLINE = 'Lastbook could not reach the internet. Everything else in Lastbook still works without it; try again when you are online.'


def _ver(s):
    return tuple(int(x) for x in s.split('.')) if isinstance(s, str) and VER.match(s) else None


def platform_key():
    return 'mac' if sys.platform == 'darwin' else 'windows' if sys.platform == 'win32' else 'linux' if sys.platform.startswith('linux') else None


def _mac_bundle():
    if not getattr(sys, 'frozen', False):
        return None
    for b in Path(sys.executable).resolve().parents:
        if b.suffix == '.app':
            return b
    return None


def _windows_exe_version(path):
    import ctypes
    from ctypes import wintypes as wt
    v = ctypes.windll.version
    n = v.GetFileVersionInfoSizeW(str(path), None)
    if not n:
        return None
    buf = ctypes.create_string_buffer(n)
    if not v.GetFileVersionInfoW(str(path), 0, n, buf):
        return None
    p, ln = ctypes.c_void_p(), wt.UINT()
    if not v.VerQueryValueW(buf, '\\', ctypes.byref(p), ctypes.byref(ln)) or ln.value < 52:
        return None
    f = ctypes.cast(p, ctypes.POINTER(ctypes.c_uint32 * 13)).contents      # VS_FIXEDFILEINFO: [2] FileVersionMS, [3] FileVersionLS
    return f'{f[2] >> 16}.{f[2] & 0xFFFF}.{f[3] >> 16}'


def app_version():
    """This app's version as 'X.Y.Z', or None outside a built app (LASTBOOK_VERSION stands in for tests)."""
    try:
        if sys.platform == 'darwin' and _mac_bundle():
            with open(_mac_bundle() / 'Contents' / 'Info.plist', 'rb') as f:
                return str(plistlib.load(f).get('CFBundleShortVersionString') or '') or None
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            return _windows_exe_version(sys.executable)
        if sys.platform.startswith('linux') and getattr(sys, 'frozen', False):    # the .deb's /opt/lastbook/VERSION
            v = (Path(sys._MEIPASS) / 'VERSION').read_text(encoding='utf-8').strip()
            return v if VER.match(v) else None
    except Exception:
        traceback.print_exc()
    return os.environ.get('LASTBOOK_VERSION') or None


# Ubuntu releases by code name, for systems built on Ubuntu that number their own releases (Linux Mint 22 and elementary OS 8 are
# both Ubuntu 24.04 underneath) and name the Ubuntu they are built on in os-release's UBUNTU_CODENAME. A name missing here is
# simply not known: the check then says nothing about the system, as on any other Linux.
UBUNTU_CODENAMES = {'jammy': '22.04', 'noble': '24.04', 'oracular': '24.10', 'plucky': '25.04', 'questing': '25.10', 'resolute': '26.04'}


def linux_version(release):
    """The Ubuntu version this Linux is, or is built on, from os-release's fields; None when it cannot be told. Only Ubuntu's
    numbers compare with the Linux min_os: Mint's 22 or Fedora's 43 are not Ubuntu versions."""
    if release.get('ID') == 'ubuntu':
        return release.get('VERSION_ID') or None
    return UBUNTU_CODENAMES.get(release.get('UBUNTU_CODENAME', '').lower())


def os_version():
    """This system's version as min_os counts it, or None when it cannot be told (and then no system is called too old)."""
    if sys.platform == 'darwin':
        return platform.mac_ver()[0] or None
    if sys.platform == 'win32':
        w = sys.getwindowsversion()
        return f'{w.major}.{w.minor}.{w.build}'
    if sys.platform.startswith('linux'):
        try:
            return linux_version(platform.freedesktop_os_release())
        except OSError:
            return None
    return None


def validate(m, key):
    """This platform's version and minimum system from app-v1.json, or None if they are not there or not plain version numbers."""
    if not isinstance(m, dict) or m.get('version') != 1 or not isinstance(m.get(key), dict):
        return None
    e = m[key]
    if not _ver(e.get('version')):
        return None
    return {'version': e['version'], 'min_os': e['min_os'] if _ver(e.get('min_os')) else None}


OS_NAMES = {'mac': 'macOS', 'windows': 'Windows', 'linux': 'Ubuntu'}


def _has_no_entry(data, key):
    try:
        m = json.loads(data)
    except ValueError:
        return False
    return isinstance(m, dict) and m.get('version') == 1 and key not in m


class Updater:
    """allowed and context are for tests (a local HTTPS server); the product passes neither and reaches only HOST on port 443."""

    def __init__(self, url=METADATA, allowed=None, context=None, key=None, version=None):
        self.url, self.context = url, context
        self.product = allowed is None
        self.allowed = {HOST} if allowed is None else allowed
        self.key = key or platform_key()
        self.version = version or app_version()
        self.lock = threading.Lock()
        self.s = {'state': 'idle'}
        self.thread = None
        self.automatic = False
        self.on_done = None          # Notices._record, in the desktop app: called with (state, token) once a check has ended

    def state(self, *, manual=False):
        with self.lock:
            out = {'state': 'idle'} if manual and self.automatic else dict(self.s)
        out['current'] = self.version
        out['website'] = WEBSITE
        return out

    def _set(self, **kw):
        with self.lock:
            self.s = kw

    def check(self, token=None, *, automatic=False):
        """token: handed back to on_done with the result (Notices drops a result whose token is from before an opt-out)."""
        if not self.key:
            return {'error': 'Updates are for the Mac, Windows and Linux app.', 'code': 'unsupported'}
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.s = {'state': 'checking'}
                self.automatic = automatic
                self.thread = threading.Thread(target=self._guard, args=(token,), daemon=True, name='update-check')
                self.thread.start()
            elif not automatic:
                self.automatic = False    # an explicit check shares the in-flight result and shows its status in About
        return self.state()

    def _guard(self, token=None):
        try:
            self._check()
        except Exception as e:
            traceback.print_exc()
            self._set(state='error', code='internal', message=f'The check stopped on an internal error ({type(e).__name__}).')
        done = self.on_done
        if done:
            try:
                done(self.state(), token)
            except Exception:
                traceback.print_exc()

    def _fetch(self):
        """(status, bytes) of the metadata through download.py. Raises download.Failed with code 'offline' when nothing answers."""
        if self.product and urllib.parse.urlsplit(self.url).port not in (None, 443):
            raise download.Failed('network', 'Lastbook refused to check an address it does not know.')
        try:
            conn, r, final = download._open(self.url, 0, None, self.allowed, self.context or download.tls_context(), 15)
        except download.Failed:
            raise
        except download.ssl.SSLCertVerificationError:
            raise download.Failed('network', 'Lastbook could not confirm it was talking to the real download site, so it stopped. '
                                             'A network that intercepts secure connections (some offices, hotels) can cause this.')
        except (OSError, ValueError, download.http.client.HTTPException):   # names through download.py: no network module here
            raise download.Failed('offline', OFFLINE)
        try:
            if self.product and urllib.parse.urlsplit(final).port not in (None, 443):     # a redirect on HOST to another port
                return 0, b''
            data = r.read(MAX_BODY + 1) if r.status == 200 else b''
            return r.status, data
        except OSError:
            raise download.Failed('offline', OFFLINE)
        finally:
            conn.close()

    def _check(self):
        try:
            status, data = self._fetch()
        except download.Failed as f:
            return self._set(state='error', code=f.code, message=f.message)
        if status in (403, 404):
            return self._set(state='not_published', message='No update information yet. Try again later.')
        if status != 200 or len(data) > MAX_BODY:
            return self._set(state='error', code='server', message='The download site did not answer properly. Try again later.')
        try:
            offer = validate(json.loads(data), self.key)
        except ValueError:
            offer = None
        if not offer and self.key == 'linux' and _has_no_entry(data, self.key):   # Linux is announced only once the site lists it
            return self._set(state='not_published', message='No update information yet. Try again later.')
        if not offer:
            return self._set(state='error', code='bad_info', message='The update information on the download site could not be read. Try again later.')
        mine = _ver(self.version or '')
        if mine and _ver(offer['version']) <= mine:
            return self._set(state='up_to_date', latest=offer['version'])
        have = _ver(os_version())
        if offer['min_os'] and have and have < _ver(offer['min_os']):
            built_on = ', or a system built on it' if self.key == 'linux' else ''
            return self._set(state='too_old_os', version=offer['version'],
                             message=f"Version {offer['version']} needs {OS_NAMES.get(self.key, self.key)} {offer['min_os']} or later{built_on}.")
        self._set(state='available', version=offer['version'])


PREFS = 'updates.json'       # in the app's own settings folder (app/main.py app_folders()[0]), beside setup.json
DAY = 24 * 60 * 60           # at most one automatic attempt in this interval, even if the site cannot be reached
CLOCK_SLACK = 5 * 60         # a time saved further ahead than this means the clock went back: it is not trusted
OFF = {'notify': False, 'available': None, 'checking': False}


class Notices:
    """Opt-in update notices: the desktop app only (configure()). Off unless the person turned them on, whatever the file says
    otherwise: missing, unreadable, from an older version, or anything but notify: true.

    updates.json: {"notify": bool, "tried": t, "checked": t, "generation": n, "found": {"version", "key"}}. Only Setup's and Settings' checkbox
    write notify; tried/checked/found are written only while notify is true. Turning it off drops found at once and keeps the two
    times, so off and on again does not buy an extra check that day.
      - auto() is the window's nudge (web/update.js: soon after it opens, hourly, and when the system says it is online again). It
        starts a check only if notify is on, this is a built app with a version, and no check was attempted in the last DAY.
        tried is saved before the check starts, so reloads, a second window or a restart cannot start another. If the attempt
        cannot be saved, no check starts.
      - A check that ends (an automatic one or the person's own, while notify is on) is recorded by _record: offline counts as a try
        only; any answer from the site, or another failure, as the day's check. available keeps the version for this platform;
        up to date, too old a system, or nothing published clears it.
      - set_notify(False) takes effect at once: no new check starts, the notice goes, and a check already under way (its request
        cannot be withdrawn) is not recorded when it ends, because its token is from before.
    The notice is shown only while notify is on and the found version is newer than this app, so updating the app hides it."""

    def __init__(self, settings_dir, u, now=time.time):
        self.path = Path(settings_dir) / PREFS
        self.u, self.now = u, now
        self.lock = threading.Lock()
        u.on_done = self._record

    # -------------------------------------------------------------------------------------------------------- the file --
    def _read(self):
        try:
            d = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            d = None
        if not isinstance(d, dict) or type(d.get('notify')) is not bool:
            return {'notify': False}
        p = {'notify': d.get('notify') is True}
        generation = d.get('generation')
        if type(generation) is int and generation >= 0:
            p['generation'] = generation
        for k in ('tried', 'checked'):
            v = d.get(k)
            if type(v) in (int, float) and 0 <= v <= 2**53:
                p[k] = float(v)
        f = d.get('found')
        if isinstance(f, dict) and _ver(f.get('version')) and isinstance(f.get('key'), str) and f['key'] in OS_NAMES:
            p['found'] = {'version': f['version'], 'key': f['key']}
        return p

    @property
    def gen(self):
        return self._read().get('generation', 0)

    def _lock_settings(self):
        """Hold the same lock for every change, even when two app processes share a settings directory."""
        from engine.paths import try_lock
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock = self.path.with_suffix('.lock').open('a+b')
        except OSError:
            return None
        for _ in range(8):
            try:
                try_lock(lock)
                return lock
            except OSError:
                time.sleep(.01)
        lock.close()
        return None

    def _save(self, p):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + '.tmp')
            tmp.write_text(json.dumps(p), encoding='utf-8')
            os.replace(tmp, self.path)
            return True
        except OSError as e:
            print('update: could not save', PREFS + ':', e, flush=True)
            return False

    # ------------------------------------------------------------------------------------------------------- the rules --
    def _busy(self):
        t = self.u.thread
        return t is not None and t.is_alive()

    def _eligible(self, p):
        """The version to show in the sidebar, or None."""
        f, mine = p.get('found'), _ver(self.u.version or '')
        if not p['notify'] or not f or not mine or f['key'] != self.u.key:
            return None
        return f['version'] if _ver(f['version']) > mine else None

    def _due(self, p, now):
        def since(k):
            t = p.get(k)
            return None if t is None or t > now + CLOCK_SLACK else now - t
        checked, tried = since('checked'), since('tried')
        return (checked is None or checked >= DAY) and (tried is None or tried >= DAY)

    def _public(self, p):
        return {'notify': p['notify'], 'available': self._eligible(p), 'checking': self._busy()}

    # ------------------------------------------------------------------------------------------------------ the routes --
    def notice(self):
        with self.lock:
            return self._public(self._read())

    def auto(self):
        with self.lock:
            p = self._read()
            now = self.now()
            if not p['notify'] or not self.u.key or not _ver(self.u.version or '') or self._busy() or not self._due(p, now):
                return self._public(p)
            lock = self._lock_settings()
            if lock is None:
                return self._public(self._read())
            with lock:
                p = self._read()
                if p['notify'] and self._due(p, now):
                    p['tried'] = now
                    if self._save(p):
                        self.u.check(p.get('generation', 0), automatic=True)
                return self._public(p)

    def set_notify(self, on):
        with self.lock:
            lock = self._lock_settings()
            if lock is None:
                return {'error': 'Lastbook could not save this setting. Try again.', 'code': 'save'}
            with lock:
                p = self._read()
                p['notify'] = on is True
                if not p['notify']:
                    p['generation'] = p.get('generation', 0) + 1  # older checks cannot record a notice
                    p.pop('found', None)
                if self._save(p):
                    return self._public(p)
                return {'error': 'Lastbook could not save this setting. Try again.', 'code': 'save'}

    def _record(self, s, token):
        with self.lock:
            if not self._read()['notify']:
                return
            lock = self._lock_settings()
            if lock is None:
                return
            with lock:
                p = self._read()
                if not p['notify'] or token != p.get('generation', 0):
                    return
                now = self.now()
                p['tried'] = now
                if s.get('state') != 'error' or s.get('code') != 'offline':
                    p['checked'] = now
                if s.get('state') == 'available' and _ver(s.get('version')) and self.u.key in OS_NAMES:
                    p['found'] = {'version': s['version'], 'key': self.u.key}
                elif s.get('state') in ('up_to_date', 'too_old_os', 'not_published'):
                    p.pop('found', None)
                self._save(p)


UPDATER = None
NOTICES = None
NATIVE = None        # app/update_macos.Native on a Mac: ready(), status(), begin(). None elsewhere: no Update now.


def updater():
    global UPDATER
    if UPDATER is None:
        UPDATER = Updater()
    return UPDATER


def configure(settings_dir):
    """app/main.py, the desktop app only: notices, with their setting in the app's own settings folder. Reaches no network."""
    global NOTICES
    NOTICES = Notices(settings_dir, updater())
    return NOTICES


def _with_notice(s):
    s['notice'] = NOTICES.notice()['available'] if NOTICES else None
    s['download_url'] = DOWNLOAD_URL
    s['can_open_download'] = NOTICES is not None and bool(_ver(s['current']))
    native = NATIVE.status() if NATIVE is not None and s['can_open_download'] else {'ready': False, 'error': None}
    s['can_update_now'] = native['ready']
    s['update_now_error'] = native['error']
    return s


def _has_offer(u):
    return u.state(manual=True)['state'] == 'available' or bool(NOTICES.notice()['available'])


def _update_now(u):
    """Update now: starts the native updater, which asks the person before anything is installed. Takes nothing from the request."""
    if NATIVE is None or NOTICES is None or not _ver(u.version) or not NATIVE.ready():
        return {'error': 'This copy of Lastbook cannot update itself. Use the download page instead.', 'fallback': True}
    if not _has_offer(u):
        return {'error': 'Check for an update again first.'}
    out = NATIVE.begin()
    if 'error' in out:
        out['fallback'] = True
    return out


def _open_download(u):
    """The desktop app's only browser handoff. The destination comes from this code, never the feed or the request."""
    if NOTICES is None or not _ver(u.version):
        return {'error': 'Open lastbook.org/download/ in your browser for the installer.'}
    if not _has_offer(u):
        return {'error': 'Check for an update again before opening the installer page.'}
    try:
        if webbrowser.open_new_tab(DOWNLOAD_URL):
            return {'opened': True}
    except (OSError, webbrowser.Error):
        pass
    return {'error': 'Lastbook could not open your browser. Copy the download link and open it there.'}


ROUTES = {
    ('GET', 'state'): lambda u: _with_notice(u.state(manual=True)),
    ('POST', 'check'): lambda u: _with_notice(u.check(NOTICES.gen if NOTICES else None)),
    ('GET', 'notice'): lambda u: NOTICES.notice() if NOTICES else dict(OFF),
    ('POST', 'auto'): lambda u: NOTICES.auto() if NOTICES else dict(OFF),
    ('POST', 'open'): _open_download,
    ('POST', 'now'): _update_now,
}


def handle(h, method, path):
    """Answers one /api/update/ request on a BaseHTTPRequestHandler h. This computer only."""
    from engine.setup.api import _send_json
    if h.client_address[0] not in ('127.0.0.1', '::1', '::ffff:127.0.0.1'):
        return _send_json(h, {'error': 'Updates are only open on this computer.'}, 403)
    fn = ROUTES.get(('GET' if method == 'HEAD' else method, path[len('/api/update/'):].strip('/')))
    if not fn:
        return _send_json(h, {'error': 'not found'}, 404)
    if method == 'POST':
        try:
            n = int(h.headers.get('Content-Length') or 0)
            if 0 < n <= 4096:
                h.rfile.read(n)
        except ValueError:
            pass
    try:
        out = fn(updater())
    except Exception as e:
        traceback.print_exc()
        return _send_json(h, {'error': f'The check stopped on an internal error ({type(e).__name__}).'}, 500)
    return _send_json(h, out)
