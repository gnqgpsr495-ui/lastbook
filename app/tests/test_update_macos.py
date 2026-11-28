#!/usr/bin/env python3
"""Update now on a Mac (app/update_macos.py): fails closed without a trusted Sparkle setup, loads nothing before the person presses
Update now, and its Sparkle delegate refuses background checks, installer packages, information-only links and remote release notes.
No Sparkle framework or network is needed: the delegate tests need PyObjC (packaging/requirements_macos.txt) and skip without it.

  PYTHONDONTWRITEBYTECODE=1 <venv python> -B app/tests/test_update_macos.py [-v]
"""
import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / 'app'), str(HERE.parents[1])]
import update_macos as M      # noqa: E402
from engine import update      # noqa: E402

KEY = base64.b64encode(bytes(range(32))).decode()


def good_info():
    return dict(M.REQUIRED, SUPublicEDKey=KEY, CFBundleShortVersionString='1.1.15', CFBundleVersion='1.1.15')


def fake_app(with_framework=True):
    app = Path(tempfile.mkdtemp()) / 'Lastbook.app'
    fw = app / 'Contents' / 'Frameworks' / 'Sparkle.framework'
    fw.mkdir(parents=True)
    if with_framework:
        (fw / 'Sparkle').write_bytes(b'')
        (app / 'Contents' / 'Resources').mkdir()
        (app / 'Contents' / 'Resources' / 'LICENSE-Sparkle.txt').write_text('MIT')
    return app


class URL:
    def __init__(self, s):
        self.s = s

    def absoluteString(self):
        return self.s


class Item:
    def __init__(self, kind='application', info_only=False, url='https://downloads.lastbook.org/mac/Lastbook-1.1.16.zip'):
        self.kind, self.info_only, self.url = kind, info_only, url

    def fileURL(self):
        return None if self.url is None else URL(self.url)

    def installationType(self):
        return self.kind

    def isInformationOnlyUpdate(self):
        return self.info_only


class TrustTest(unittest.TestCase):
    def test_trusted_setup(self):
        self.assertIsNone(M.problem(good_info(), fake_app()))

    def test_fails_closed_without_framework_bundle_or_key(self):
        self.assertIn('not a built app', M.problem(good_info(), None))
        self.assertIn('Sparkle.framework', M.problem(good_info(), fake_app(with_framework=False)))
        for key in (None, '', 'not base64!', base64.b64encode(b'short').decode(), base64.b64encode(bytes(64)).decode()):
            info = good_info()
            info['SUPublicEDKey'] = key
            self.assertIn('SUPublicEDKey', M.problem(info, fake_app()), key)

    def test_every_required_value_is_checked(self):
        app = fake_app()
        for k, want in M.REQUIRED.items():
            if isinstance(want, bool):
                wrongs = (None, not want, int(want))
            elif isinstance(want, int):
                wrongs = (None, want + 1, False, str(want), 1209600)
            else:
                wrongs = (None, want + 'x', want.encode())
            for wrong in wrongs:
                info = good_info()
                if wrong is None:
                    info.pop(k)
                else:
                    info[k] = wrong
                self.assertIn(k, M.problem(info, app) or '', (k, wrong))

    def test_feed_is_the_canonical_https_appcast(self):
        self.assertEqual(M.FEED, 'https://downloads.lastbook.org/mac/appcast.xml')
        info = good_info()
        info['SUFeedURL'] = 'http://downloads.lastbook.org/mac/appcast.xml'
        self.assertIn('SUFeedURL', M.problem(info, fake_app()))

    def test_signed_feed_failures_never_expire(self):
        self.assertEqual(M.REQUIRED['SUSignedFeedFailureExpirationInterval'], 0)
        self.assertIs(type(M.REQUIRED['SUSignedFeedFailureExpirationInterval']), int)

    def test_bundle_version_matches_short_version(self):
        for bad in ({'CFBundleVersion': None}, {'CFBundleVersion': '1.1.14'}, {'CFBundleVersion': 1}):
            info = good_info()
            info.update(bad)
            if bad['CFBundleVersion'] is None:
                info.pop('CFBundleVersion')
            self.assertIn('CFBundleVersion', M.problem(info, fake_app()), bad)

    def test_no_sandbox_services_or_schedule(self):
        for k in M.NEVER + ('SUScheduledCheckInterval',):
            info = good_info()
            info[k] = True if k in M.NEVER else 3600
            self.assertIn(k, M.problem(info, fake_app()), k)

    def test_only_plain_app_archives(self):
        self.assertTrue(M.item_ok(Item()))
        self.assertFalse(M.item_ok(Item('package')))
        self.assertFalse(M.item_ok(Item('interactive-package')))
        self.assertFalse(M.item_ok(Item(info_only=True)))

    def test_archive_only_from_the_first_party_host(self):
        self.assertTrue(M.item_ok(Item(url='https://downloads.lastbook.org/mac/Lastbook-1.1.16.zip')))
        for url in (None, '', 'http://downloads.lastbook.org/mac/a.zip', 'https://downloads.lastbook.org:8443/mac/a.zip',
                    'https://downloads.lastbook.org:443/mac/a.zip', 'https://evil.example/mac/a.zip', 'https://downloads.lastbook.org.evil.example/a.zip',
                    'https://user@downloads.lastbook.org/a.zip', 'https://DOWNLOADS.lastbook.org/a.zip', 'file:///tmp/a.zip',
                    'https://lastbook.org/a.zip', 'https://github.com/a.zip', 'https://downloads.lastbook.org:bad/a.zip'):
            self.assertFalse(M.item_ok(Item(url=url)), url)


class ActivationTest(unittest.TestCase):
    def setUp(self):
        self.saved = update.NATIVE
        self.later = []

    def tearDown(self):
        update.NATIVE = self.saved

    def test_nothing_loads_before_the_click(self):
        controller = mock.Mock()
        with mock.patch.object(M, '_start', return_value=(controller, object())) as start:
            n = M.configure(update, fake_app(), good_info(), self.later.append)
            self.assertIs(update.NATIVE, n)
            self.assertTrue(n.ready())
            n.status()
            start.assert_not_called()
            self.assertEqual(self.later, [])
            self.assertEqual(n.begin(), {'started': True})
            start.assert_not_called()                    # only on the main thread, after the click
            self.later.pop()()
            start.assert_called_once()
            controller.checkForUpdates_.assert_called_once_with(None)
            self.assertIs(n.controller, controller)
            self.assertIs(n.delegate, start.return_value[1])   # kept alive here: Sparkle holds its delegate weakly
            n.begin()
            self.later.pop()()
            start.assert_called_once()                   # one updater, started once
            self.assertEqual(controller.checkForUpdates_.call_count, 2)

    def fake_runtime(self, started=True):
        """Foundation/objc stand-ins shaped like PyObjC with Sparkle 2.10.1: startUpdater_ returns a plain bool (B@:^@), and the
        native controller has no instance dictionary (__slots__), so nothing may be stored on it."""
        calls = []

        class Updater:
            def respondsToSelector_(self, sel):
                return True

            def clearFeedURLFromUserDefaults(self):
                calls.append('clear')

            def setAutomaticallyChecksForUpdates_(self, value):
                calls.append(('auto-check', value))

            def setAutomaticallyDownloadsUpdates_(self, value):
                calls.append(('auto-download', value))

            def setSendsSystemProfile_(self, value):
                calls.append(('profile', value))

            def startUpdater_(self, error):
                calls.append(('start', error))
                return started

        class Controller:
            __slots__ = ()

            def updater(self):
                return Updater()

        class ControllerClass:
            @staticmethod
            def alloc():
                return ControllerClass

            @staticmethod
            def initWithStartingUpdater_updaterDelegate_userDriverDelegate_(start, delegate, driver):
                calls.append(('init', start, driver))
                return Controller()

        framework = mock.Mock()
        framework.load.return_value = True
        foundation = mock.Mock()
        foundation.NSBundle.bundleWithPath_.return_value = framework
        objc = mock.Mock()
        objc.NULL = object()
        objc.lookUpClass.return_value = ControllerClass
        return foundation, objc, calls

    def test_start_with_bool_api_and_no_native_attributes(self):
        foundation, objc, calls = self.fake_runtime()
        delegate = object()
        with mock.patch.dict(sys.modules, {'Foundation': foundation, 'objc': objc}), \
                mock.patch.object(M, '_delegate_class', return_value=mock.Mock(**{'alloc.return_value.init.return_value': delegate})):
            controller, kept = M._start(fake_app())
        self.assertIs(kept, delegate)
        self.assertEqual(calls, [('init', False, None), 'clear', ('auto-check', False), ('auto-download', False), ('profile', False), ('start', objc.NULL)])

    def test_start_refusal_raises(self):
        foundation, objc, calls = self.fake_runtime(started=False)
        with mock.patch.dict(sys.modules, {'Foundation': foundation, 'objc': objc}), \
                mock.patch.object(M, '_delegate_class', return_value=mock.Mock()):
            with self.assertRaises(RuntimeError):
                M._start(fake_app())

    def test_untrusted_build_never_starts_sparkle(self):
        with mock.patch.object(M, '_start') as start:
            n = M.Native({}, fake_app(), self.later.append)
            self.assertFalse(n.ready())
            self.assertIn('download page', n.begin()['error'])
            self.assertEqual(self.later, [])
            start.assert_not_called()

    def test_start_failure_falls_back(self):
        with mock.patch.object(M, '_start', side_effect=RuntimeError('Sparkle.framework did not load')):
            n = M.Native(good_info(), fake_app(), self.later.append)
            n.begin()
            self.later.pop()()
        self.assertFalse(n.ready())
        self.assertIn('download page', n.status()['error'])
        self.assertIn('error', n.begin())
        self.assertEqual(self.later, [])

    def test_shell_reads_the_plist_only(self):
        src = (HERE.parent / 'shell_macos.py').read_text(encoding='utf-8')
        body = src[src.index('def _configure_update_now'):src.index('def run(')]
        self.assertNotIn('Sparkle', body.replace('Sparkle loads only', ''))
        self.assertIn('_configure_update_now()', src[src.index('def run('):])


class DelegateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import Foundation
            import objc
        except ImportError:
            raise unittest.SkipTest('the Sparkle delegate needs PyObjC')
        cls.d = M._delegate_class(objc, Foundation).alloc().init()

    def test_only_checks_the_person_started(self):
        self.assertEqual(self.d.updater_mayPerformUpdateCheck_error_(None, 0, None), (True, None))
        for background in (1, 2):
            ok, error = self.d.updater_mayPerformUpdateCheck_error_(None, background, None)
            self.assertFalse(ok)
            self.assertIn('only when you ask', str(error.localizedDescription()))

    def test_refuses_packages_and_links(self):
        self.assertEqual(self.d.updater_shouldProceedWithUpdate_updateCheck_error_(None, Item(), 0, None), (True, None))
        for item, check in ((Item('package'), 0), (Item(info_only=True), 0), (Item(), 1), (Item(url='https://evil.example/a.zip'), 0)):
            ok, error = self.d.updater_shouldProceedWithUpdate_updateCheck_error_(None, item, check, None)
            self.assertFalse(ok)
            self.assertIsNotNone(error)

    def test_no_remote_notes_profile_or_other_feed(self):
        self.assertFalse(self.d.updater_shouldDownloadReleaseNotesForUpdate_(None, Item()))
        self.assertEqual(list(self.d.feedParametersForUpdater_sendingSystemProfile_(None, True)), [])
        self.assertEqual(self.d.feedURLStringForUpdater_(None), M.FEED)


def load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE.parents[1] / 'packaging' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PackagingTest(unittest.TestCase):
    """packaging/sparkle_framework.py takes only the pinned archive; scan_package_macos.py refuses half a setup."""

    def archive(self, members, name='Sparkle-2.9.9.tar.xz'):
        import io
        import tarfile
        path = Path(tempfile.mkdtemp()) / name
        with tarfile.open(path, 'w:xz') as t:
            for member, data in members:
                info = tarfile.TarInfo(member)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        return path

    def test_only_the_pinned_digest(self):
        F = load('sparkle_framework')
        path = self.archive([('./Sparkle.framework/Sparkle', b'x')])
        lock = {'version': '2.9.9', 'archive': 'Sparkle-{version}.tar.xz', 'sha256': F.sha256(path)}
        F.verify(path, lock)
        for bad in ({**lock, 'sha256': ''}, {**lock, 'version': ''}, {**lock, 'sha256': '0' * 64}, {**lock, 'version': '2.9.8'}):
            with self.assertRaises(SystemExit):
                F.verify(path, bad)
        pinned = F.json.loads(F.LOCK.read_text())
        self.assertEqual(pinned, {**pinned, 'version': '2.10.1', 'archive': 'Sparkle-{version}.tar.xz',
                                  'sha256': '1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27'})
        with self.assertRaises(SystemExit):
            F.verify(path, pinned)                                             # the wrong name and bytes
        wrong = path.with_name('Sparkle-2.10.1.tar.xz')
        path.rename(wrong)
        with self.assertRaises(SystemExit):
            F.verify(wrong, pinned)                                            # the pinned name, other bytes

    def test_bundle_version_from_short_version(self):
        import plistlib
        import re
        F = load('sparkle_framework')
        app = fake_app()
        plist = app / 'Contents' / 'Info.plist'
        plist.write_bytes(plistlib.dumps({'CFBundleShortVersionString': '1.1.15'}))
        F.set_bundle_version(app)
        self.assertEqual(plistlib.loads(plist.read_bytes())['CFBundleVersion'], '1.1.15')
        plist.write_bytes(plistlib.dumps({}))
        with self.assertRaises(SystemExit):
            F.set_bundle_version(app)
        spec = (HERE.parents[1] / 'packaging' / 'lastbook_macos.spec').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r"version='\d+\.\d+\.\d+'", spec)), 1)   # still the one literal the version bump edits
        self.assertNotIn('CFBundleVersion', spec)

    def test_extracts_only_the_framework_and_nothing_outside(self):
        F = load('sparkle_framework')
        into = Path(tempfile.mkdtemp())
        fw = F.extract(self.archive([('./Sparkle.framework/Sparkle', b'x'), ('./LICENSE', b'MIT'), ('./bin/sign_update', b'tool'), ('./Sparkle Test App.app/x', b'')]), into)
        self.assertEqual(sorted(p.name for p in into.iterdir()), ['LICENSE', 'Sparkle.framework'])
        self.assertTrue((fw / 'Sparkle').is_file())
        with self.assertRaises(Exception):
            F.extract(self.archive([('Sparkle.framework/../../escape', b'x'), ('./LICENSE', b'MIT')]), Path(tempfile.mkdtemp()))
        with self.assertRaises(SystemExit):
            F.extract(self.archive([('./Sparkle.framework/Sparkle', b'x')]), Path(tempfile.mkdtemp()))     # no license, no build
        with self.assertRaises(SystemExit):
            F.extract(self.archive([('./LICENSE', b'MIT')]), Path(tempfile.mkdtemp()))

    def test_resigns_nested_code_bottom_up(self):
        F = load('sparkle_framework')
        fw = Path(tempfile.mkdtemp()) / 'Sparkle.framework'
        (fw / 'Versions' / 'B').mkdir(parents=True)
        (fw / 'Versions' / 'Current').symlink_to('B')
        with mock.patch.object(F, 'run') as run:
            F.prepare(fw)
        signed = [Path(c.args[-1]).name for c in run.call_args_list if c.args[0] == 'codesign']
        self.assertEqual(signed, ['Autoupdate', 'Updater.app', 'Sparkle.framework'])

    def test_scan_refuses_half_a_setup(self):
        try:
            S = load('scan_package_macos')
        except ImportError:
            raise unittest.SkipTest('the package scan needs PyInstaller')
        import plistlib

        def app(info, framework):
            a = fake_app(framework)
            if not framework:
                (a / 'Contents' / 'Frameworks' / 'Sparkle.framework').rmdir()
            (a / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
            return a
        plain = {'CFBundleIdentifier': M.BUNDLE_ID}
        self.assertEqual(S.sparkle_problems(app(plain, False)), [])                 # the default build
        self.assertEqual(S.sparkle_problems(app(good_info(), True)), [])
        self.assertTrue(S.sparkle_problems(app(good_info(), False)))               # keys, no framework
        self.assertTrue(S.sparkle_problems(app(plain, True)))                      # framework, no keys
        with_xpc = app(good_info(), True)
        (with_xpc / 'Contents' / 'Frameworks' / 'Sparkle.framework' / 'Installer.xpc').mkdir()
        self.assertTrue(S.sparkle_problems(with_xpc))
        no_license = app(good_info(), True)
        (no_license / 'Contents' / 'Resources' / 'LICENSE-Sparkle.txt').unlink()
        self.assertTrue(S.sparkle_problems(no_license))


if __name__ == '__main__':
    unittest.main(verbosity=2)
