"""Check for updates (engine/update.py) against a local HTTPS test server (test_setup.py's). Never shipped.
The check only says what is on the website: these tests also make sure nothing else can be asked of it.
NoticesTest: the opt-in daily check behind the sidebar's "Update available" (consent, once a day, offline, stale notices).
UpdateNowTest: About's Update now, only through a native updater the desktop app registers (app/update_macos.py), on a click.

Run:  python3 app/tests/test_update.py
"""
import json
import sys
import threading
import time
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]
import test_setup as T            # noqa: E402
from engine import update         # noqa: E402

ALLOWED = {'127.0.0.1'}


def wait(u, t=20):
    end = time.time() + t
    while time.time() < end:
        s = u.state()
        if s['state'] != 'checking':
            return s
        time.sleep(0.05)
    raise AssertionError(f'still {u.state()}')


class UpdateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.files = T.Files()
        cls.srv, cls.ctx, cls.base = T.start_server(cls.tmp, cls.files)

    def meta(self, version='1.2.0', min_os='10.0', **extra):
        self.files.data['app-v1.json'] = json.dumps({'version': 1, **{k: dict(version=version, min_os=min_os, **extra) for k in ('mac', 'windows', 'linux')}}).encode()

    def check(self, version='1.1.2', url=None, key='mac', system='14.0'):
        """system: this computer's version as os_version() would say, so the result does not depend on the machine running the tests."""
        u = update.Updater(url or f'{self.base}/app-v1.json', allowed=ALLOWED, context=self.ctx, key=key, version=version)
        with mock.patch.object(update, 'os_version', return_value=system):
            u.check()
            return wait(u)

    def test_available(self):
        self.meta(url='https://evil.example/x.dmg', sha256='0' * 64, size=1)    # anything else in the file is not read
        s = self.check()
        self.assertEqual((s['state'], s['version'], s['current'], s['website']), ('available', '1.2.0', '1.1.2', 'lastbook.org'))
        self.assertEqual(set(s), {'state', 'version', 'current', 'website'})

    def test_up_to_date(self):
        self.meta(version='1.1.2')
        self.assertEqual(self.check()['state'], 'up_to_date')

    def test_offline(self):
        s = self.check(url='https://127.0.0.1:1/app-v1.json')     # an allowed address that nothing answers
        self.assertEqual(s['code'], 'offline')
        self.assertIn('still works', s['message'])

    def test_not_published(self):
        self.files.data.pop('app-v1.json', None)
        self.assertEqual(self.check()['state'], 'not_published')

    def test_bad_version(self):
        self.meta(version='<b>2</b>')
        self.assertEqual(self.check()['code'], 'bad_info')

    def test_too_old_os(self):
        self.meta(min_os='99.0')
        self.assertEqual(self.check()['state'], 'too_old_os')

    def test_unknown_system_is_never_too_old(self):
        self.meta(min_os='99.0')
        self.assertEqual(self.check(system=None)['state'], 'available')

    def test_linux_built_on_ubuntu(self):
        self.meta(min_os='24.04')
        self.assertEqual(self.check(key='linux', system='24.04')['state'], 'available')
        s = self.check(key='linux', system='22.04')
        self.assertEqual(s['state'], 'too_old_os')
        self.assertEqual(s['message'], 'Version 1.2.0 needs Ubuntu 24.04 or later, or a system built on it.')

    def test_linux_version(self):
        cases = [
            ({'ID': 'ubuntu', 'VERSION_ID': '24.04', 'UBUNTU_CODENAME': 'noble'}, '24.04'),
            ({'ID': 'ubuntu', 'VERSION_ID': '26.04', 'UBUNTU_CODENAME': 'resolute'}, '26.04'),
            ({'ID': 'linuxmint', 'ID_LIKE': 'ubuntu debian', 'VERSION_ID': '22.1', 'UBUNTU_CODENAME': 'noble'}, '24.04'),   # not 22.1
            ({'ID': 'elementary', 'ID_LIKE': 'ubuntu debian', 'VERSION_ID': '8', 'UBUNTU_CODENAME': 'noble'}, '24.04'),       # not 8
            ({'ID': 'zorin', 'ID_LIKE': 'ubuntu debian', 'VERSION_ID': '17', 'UBUNTU_CODENAME': 'jammy'}, '22.04'),
            ({'ID': 'pop', 'ID_LIKE': 'ubuntu debian', 'VERSION_ID': '24.04', 'UBUNTU_CODENAME': 'noble'}, '24.04'),
            ({'ID': 'linuxmint', 'VERSION_ID': '30', 'UBUNTU_CODENAME': 'someday'}, None),      # a code name this version does not know
            ({'ID': 'debian', 'VERSION_ID': '13'}, None),
            ({'ID': 'fedora', 'VERSION_ID': '43'}, None),
            ({'ID': 'arch', 'BUILD_ID': 'rolling'}, None),
            ({}, None),
        ]
        for release, want in cases:
            with self.subTest(release=release.get('ID')):
                self.assertEqual(update.linux_version(release), want)

    def test_windows_build_numbers(self):
        self.assertEqual(update._ver('10.0.26200'), (10, 0, 26200))     # five-digit Windows builds must compare
        self.assertGreater(update._ver('10.0.26200'), update._ver('10.0'))

    def test_product_reaches_only_downloads_lastbook_org(self):
        u = update.Updater(key='mac', version='1.0.0')
        self.assertEqual((u.allowed, u.url), ({'downloads.lastbook.org'}, 'https://downloads.lastbook.org/app-v1.json'))
        for other in ('https://pub-28c3cc06eb774c5cac057e6c9343efbd.r2.dev/app-v1.json', 'https://huggingface.co/app-v1.json',
                      'https://downloads.lastbook.org:8443/app-v1.json'):
            u = update.Updater(key='mac', version='1.0.0')
            u.url = other
            u.check()
            s = wait(u)
            self.assertEqual(s['state'], 'error', other)
            self.assertNotEqual(s['state'], 'available')

    def test_only_check_state_and_notices(self):
        self.assertEqual(set(update.ROUTES), {('GET', 'state'), ('POST', 'check'), ('GET', 'notice'), ('POST', 'auto'), ('POST', 'open'), ('POST', 'now')})
        self.assertIsNone(update.NATIVE)                   # only the Mac shell sets one: the engine itself installs nothing
        for gone in ('download', 'install', 'stop', '_install_mac', '_install_windows'):
            self.assertFalse(hasattr(update.Updater, gone), gone)
            self.assertFalse(hasattr(update.Notices, gone), gone)
        self.assertFalse(hasattr(update, 'QUIT'))
        self.assertNotIn('subprocess', vars(update))      # nothing to start: no program is run


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


class NoticesTest(unittest.TestCase):
    """Opt-in update notices (update.Notices): off unless turned on, at most one check a day, quiet offline, and nothing kept
    once turned off. The network is the local HTTPS test server; every request it gets is in files.log."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_class = Path(tempfile.mkdtemp())
        cls.files = T.Files()
        cls.srv, cls.ctx, cls.base = T.start_server(cls.tmp_class, cls.files)

    def setUp(self):
        self.files.data.clear()
        self.files.log.clear()
        self.meta()
        self.dir = Path(tempfile.mkdtemp()) / 'settings'
        self.clock = Clock()
        self.saved_notices = update.NOTICES

    def tearDown(self):
        update.NOTICES = self.saved_notices

    def meta(self, version='1.2.0', min_os='10.0'):
        self.files.data['app-v1.json'] = json.dumps({'version': 1, **{k: {'version': version, 'min_os': min_os} for k in ('mac', 'windows', 'linux')}}).encode()

    def make(self, version='1.1.2', url=None, key='mac'):
        u = update.Updater(url or f'{self.base}/app-v1.json', allowed=ALLOWED, context=self.ctx, key=key, version=version)
        return update.Notices(self.dir, u, now=self.clock)

    def requests(self):
        with self.files.lock:
            return sum(1 for name, *_ in self.files.log if name == 'app-v1.json')

    def finish(self, n):
        if n.u.thread is not None:
            n.u.thread.join(20)
            self.assertFalse(n.u.thread.is_alive())

    def auto(self, n, system='14.0'):
        with mock.patch.object(update, 'os_version', return_value=system):
            out = n.auto()
            self.finish(n)
        return out

    def prefs(self):
        return json.loads((self.dir / update.PREFS).read_text(encoding='utf-8'))

    # ---------------------------------------------------------------------------------------------------- consent --
    def test_off_by_default_no_network_and_nothing_written(self):
        n = self.make()
        self.assertEqual(self.auto(n), {'notify': False, 'available': None, 'checking': False})
        self.assertEqual(n.notice()['available'], None)
        self.assertIsNone(n.u.thread)
        self.assertEqual(self.requests(), 0)
        self.assertFalse((self.dir / update.PREFS).exists())     # only the person's own choice writes the file

    def test_missing_or_invalid_config_is_off(self):
        self.dir.mkdir(parents=True)
        for text in ('', '{', 'null', '[]', '"notify"', '{"notify": "yes"}', '{"notify": 1}', '{"enabled": true}',
                     '{"notify": null, "found": {"version": "9.9.9", "key": "mac"}}'):
            with self.subTest(text=text):
                (self.dir / update.PREFS).write_text(text, encoding='utf-8')
                n = self.make()
                out = self.auto(n)
                self.assertEqual((out['notify'], out['available']), (False, None))
                self.assertIsNone(n.u.thread)
        self.assertEqual(self.requests(), 0)

    def test_manual_check_does_not_turn_notices_on(self):
        n = self.make()
        with mock.patch.object(update, 'os_version', return_value='14.0'):
            n.u.check(n.gen)
            self.finish(n)
        self.assertEqual(n.u.state()['state'], 'available')        # About still says so
        self.assertEqual(n.notice(), {'notify': False, 'available': None, 'checking': False})
        self.assertFalse((self.dir / update.PREFS).exists())

    def test_server_version_has_no_notices(self):
        update.NOTICES = None
        self.assertEqual(update.ROUTES[('POST', 'auto')](update.Updater(key='mac', version='1.0.0')), update.OFF)
        self.assertEqual(self.requests(), 0)
        from engine.setup import api
        self.assertEqual(api._updates(), {'supported': False, 'notify': False})
        self.assertEqual(api._set_update_notice(True)['code'], 'unsupported')

    def test_setup_route_sets_only_a_boolean(self):
        update.NOTICES = n = self.make()
        from engine.setup import api
        self.assertEqual(api._updates(), {'supported': True, 'notify': False, 'available': None, 'checking': False})
        route = api.ROUTES[('POST', 'updates')]
        for body in ({}, {'notify': None}, {'notify': 'yes'}):
            self.assertEqual(route(None, body)['code'], 'bad_request')
        self.assertFalse((self.dir / update.PREFS).exists())
        self.assertTrue(api._set_update_notice(True)['notify'])
        self.assertIs(self.prefs()['notify'], True)
        self.assertIsNone(n.u.thread)                       # turning it on starts nothing: the window asks
        self.assertEqual(self.requests(), 0)

    # ------------------------------------------------------------------------------------------------------- daily --
    def test_opted_in_checks_at_most_once_a_day(self):
        n = self.make()
        n.set_notify(True)
        self.assertEqual(self.auto(n)['notify'], True)
        self.assertEqual(self.requests(), 1)
        self.assertEqual(n.notice()['available'], '1.2.0')
        for _ in range(5):                                   # reloads, a second window, the hourly nudge
            self.auto(n)
        self.clock.t += update.DAY - 60
        self.auto(n)
        self.assertEqual(self.requests(), 1)
        self.clock.t += 120
        self.auto(n)
        self.assertEqual(self.requests(), 2)

    def test_restart_keeps_the_notice_and_the_day(self):
        n = self.make()
        n.set_notify(True)
        self.auto(n)
        again = self.make()                                  # the app opened again: a new process, the same settings folder
        self.assertEqual(again.notice(), {'notify': True, 'available': '1.2.0', 'checking': False})
        self.auto(again)
        self.assertEqual(self.requests(), 1)

    def test_two_app_instances_share_one_daily_attempt(self):
        first, second = self.make(), self.make()
        first.set_notify(True)
        start = threading.Barrier(2)

        def nudge(notices):
            start.wait(timeout=5)
            notices.auto()

        workers = [threading.Thread(target=nudge, args=(n,)) for n in (first, second)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.finish(first)
        self.finish(second)
        self.assertEqual(self.requests(), 1)

    def test_a_check_under_way_is_not_started_twice(self):
        n = self.make()
        n.set_notify(True)
        go = threading.Event()
        real = n.u._fetch
        n.u._fetch = lambda: (go.wait(10), real())[1]
        self.assertTrue(n.auto()['checking'])
        self.clock.t += update.DAY * 2                       # even when due again, nothing starts while one runs
        self.assertTrue(n.auto()['checking'])
        go.set()
        self.finish(n)
        self.assertEqual(self.requests(), 1)

    def test_clock_set_back_does_not_stop_checks_for_ever(self):
        n = self.make()
        n.set_notify(True)
        self.auto(n)
        self.clock.t -= 30 * update.DAY
        self.auto(n)
        self.assertEqual(self.requests(), 2)
        self.auto(n)                                          # and then once a day again
        self.assertEqual(self.requests(), 2)

    def test_no_check_when_tried_cannot_be_saved(self):
        n = self.make()
        n.set_notify(True)
        with mock.patch.object(n, '_save', return_value=False):
            self.auto(n)
        self.assertIsNone(n.u.thread)
        self.assertEqual(self.requests(), 0)

    def test_unbuilt_app_never_checks_on_its_own(self):
        with mock.patch.object(update, 'app_version', return_value=None):
            n = self.make(version=None)
        self.assertIsNone(n.u.version)
        n.set_notify(True)
        self.auto(n)
        self.assertEqual(self.requests(), 0)

    # ----------------------------------------------------------------------------------------------------- offline --
    def test_offline_is_quiet_and_waits_a_day(self):
        n = self.make(url='https://127.0.0.1:1/app-v1.json')    # an allowed address that nothing answers
        n.set_notify(True)
        out = self.auto(n)
        self.assertEqual(n.u.state()['code'], 'offline')
        self.assertEqual(n.u.state(manual=True)['state'], 'idle')
        self.assertEqual(n.notice(), {'notify': True, 'available': None, 'checking': False})
        self.assertNotIn('checked', self.prefs())            # not the day's check
        first = n.u.thread
        self.auto(n)
        self.assertIs(n.u.thread, first)                     # not again straight away
        self.clock.t += update.DAY - 1
        self.auto(n)
        self.assertIs(n.u.thread, first)
        self.clock.t += 1
        self.auto(n)
        self.assertIsNot(n.u.thread, first)
        self.assertNotIn('error', out)

    def test_offline_keeps_what_was_found(self):
        n = self.make()
        n.set_notify(True)
        self.auto(n)
        n.u.url = 'https://127.0.0.1:1/app-v1.json'
        self.clock.t += update.DAY
        self.auto(n)
        self.assertEqual(n.notice()['available'], '1.2.0')

    # ------------------------------------------------------------------------------------------------ stale notices --
    def test_opting_out_removes_the_notice_and_stops_checks(self):
        n = self.make()
        n.set_notify(True)
        self.auto(n)
        self.assertEqual(n.set_notify(False), {'notify': False, 'available': None, 'checking': False})
        self.assertNotIn('found', self.prefs())
        self.clock.t += 3 * update.DAY
        self.auto(n)
        self.assertEqual(self.requests(), 1)
        n.u.check(n.gen)                                      # the person's own check, while notices are off
        self.finish(n)
        self.assertNotIn('found', self.prefs())

    def test_opt_out_during_a_check_drops_its_result(self):
        n = self.make()
        n.set_notify(True)
        go = threading.Event()
        real = n.u._fetch
        n.u._fetch = lambda: (go.wait(10), real())[1]
        n.auto()
        n.set_notify(False)
        n.set_notify(True)                                    # and on again before it ends: still not this check's to record
        go.set()
        self.finish(n)
        self.assertNotIn('found', self.prefs())
        self.assertEqual(n.notice()['available'], None)

    def test_updated_app_hides_the_notice(self):
        n = self.make(version='1.1.2')
        n.set_notify(True)
        self.auto(n)
        self.assertEqual(n.notice()['available'], '1.2.0')
        self.assertIsNone(self.make(version='1.2.0').notice()['available'])
        self.assertIsNone(self.make(version='1.3.0').notice()['available'])
        self.assertIsNone(self.make(key='windows').notice()['available'])    # found for another platform's installer

    def test_no_notice_when_up_to_date_too_old_or_withdrawn(self):
        n = self.make()
        n.set_notify(True)
        self.auto(n)
        self.assertEqual(n.notice()['available'], '1.2.0')
        self.meta(version='1.1.2')                            # the site now lists this version: the old notice goes
        self.clock.t += update.DAY
        self.auto(n)
        self.assertIsNone(n.notice()['available'])
        self.meta(version='1.3.0', min_os='99.0')            # newer, but not for this system
        self.clock.t += update.DAY
        self.auto(n)
        self.assertEqual(n.u.state()['state'], 'too_old_os')
        self.assertIsNone(n.notice()['available'])

    def test_state_route_carries_the_notice_for_about(self):
        update.NOTICES = n = self.make()
        n.set_notify(True)
        self.auto(n)
        fresh = self.make()                                   # after a restart: About has not checked, the notice is known
        update.NOTICES = fresh
        s = update.ROUTES[('GET', 'state')](fresh.u)
        self.assertEqual((s['state'], s['notice']), ('idle', '1.2.0'))

    def test_open_download_for_persisted_notice(self):
        update.NOTICES = n = self.make()
        n.set_notify(True)
        self.auto(n)
        update.NOTICES = fresh = self.make()                  # new window and updater, with a saved offer
        with mock.patch.object(update.webbrowser, 'open_new_tab', return_value=True) as browser:
            self.assertEqual(update.ROUTES[('POST', 'open')](fresh.u), {'opened': True})
            browser.assert_called_once_with('https://lastbook.org/download/')

    def test_open_download_only_when_desktop_has_an_offer(self):
        n = self.make()
        with mock.patch.object(update.webbrowser, 'open_new_tab') as browser:
            update.NOTICES = None
            self.assertIn('error', update._open_download(n.u))
            update.NOTICES = n
            self.assertIn('error', update._open_download(n.u))
            browser.assert_not_called()

    def test_open_download_failure_after_manual_check(self):
        update.NOTICES = n = self.make()
        with mock.patch.object(update, 'os_version', return_value='14.0'):
            update.ROUTES[('POST', 'check')](n.u)
            self.finish(n)
        self.assertFalse(n.notice()['notify'])
        with mock.patch.object(update.webbrowser, 'open_new_tab', return_value=False) as browser:
            self.assertIn('could not open your browser', update._open_download(n.u)['error'])
            browser.assert_called_once_with(update.DOWNLOAD_URL)


class Native:
    def __init__(self, ready=True, result=None):
        self.is_ready, self.calls = ready, 0
        self.result = result or {'started': True}

    def ready(self):
        return self.is_ready

    def status(self):
        return {'ready': self.is_ready, 'error': None if self.is_ready else 'off'}

    def begin(self):
        self.calls += 1
        return dict(self.result)


class UpdateNowTest(NoticesTest):
    """Reuses NoticesTest's server and settings; none of its tests are run again here."""

    def setUp(self):
        super().setUp()
        self.saved_native = update.NATIVE

    def tearDown(self):
        update.NATIVE = self.saved_native
        super().tearDown()

    def offered(self, native):
        update.NATIVE = native
        update.NOTICES = n = self.make()
        with mock.patch.object(update, 'os_version', return_value='14.0'):
            update.ROUTES[('POST', 'check')](n.u)
            self.finish(n)
        return n

    def test_update_now_starts_only_on_its_own_route(self):
        native = Native()
        n = self.offered(native)
        s = update.ROUTES[('GET', 'state')](n.u)
        self.assertEqual((s['state'], s['can_update_now'], s['can_open_download']), ('available', True, True))
        for route in (('GET', 'state'), ('POST', 'check'), ('GET', 'notice'), ('POST', 'auto')):
            update.ROUTES[route](n.u)
            self.finish(n)
        self.assertEqual(native.calls, 0)                  # nothing but the click starts the updater
        with mock.patch.object(update.webbrowser, 'open_new_tab') as browser:
            self.assertEqual(update.ROUTES[('POST', 'now')](n.u), {'started': True})
            browser.assert_not_called()
        self.assertEqual(native.calls, 1)

    def test_update_now_needs_an_offer(self):
        native = Native()
        update.NATIVE = native
        update.NOTICES = n = self.make()
        self.assertIn('Check for an update', update.ROUTES[('POST', 'now')](n.u)['error'])
        self.assertEqual(native.calls, 0)

    def test_download_page_without_a_trusted_native_updater(self):
        for native in (None, Native(ready=False)):
            n = self.offered(native)
            s = update.ROUTES[('GET', 'state')](n.u)
            self.assertFalse(s['can_update_now'])
            self.assertTrue(s['can_open_download'])        # Windows, Linux, Mac builds without Sparkle: the download page
            out = update.ROUTES[('POST', 'now')](n.u)
            self.assertTrue(out['fallback'])
            self.assertIn('download page', out['error'])
            if native:
                self.assertEqual(native.calls, 0)

    def test_native_failure_falls_back(self):
        n = self.offered(Native(result={'error': 'The updater could not start.'}))
        out = update.ROUTES[('POST', 'now')](n.u)
        self.assertEqual((out['error'], out['fallback']), ('The updater could not start.', True))

    def test_server_version_never_offers_update_now(self):
        update.NATIVE, update.NOTICES = Native(), None
        u = update.Updater(key='mac', version='1.1.2')
        self.assertFalse(update.ROUTES[('GET', 'state')](u)['can_update_now'])
        self.assertTrue(update.ROUTES[('POST', 'now')](u)['fallback'])
        self.assertEqual(update.NATIVE.calls, 0)


for name in [k for k in vars(NoticesTest) if k.startswith('test_')]:
    setattr(UpdateNowTest, name, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
