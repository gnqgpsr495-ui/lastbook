"""Update now, on a Mac: Sparkle 2 (https://sparkle-project.org), loaded only when the person presses Update now in About.

Nothing here runs at launch. ready() reads only this app's Info.plist and looks for Sparkle.framework on disk: no Sparkle code is
loaded and nothing is asked of the network until begin(). Then Sparkle fetches the appcast, shows its own window (the person
confirms Install Update), checks the archive's EdDSA signature against SUPublicEDKey and the new app's code signature against this
one, replaces only Lastbook.app and relaunches it. The library (LastbookData), settings, the AI model and chats live outside the app
bundle and are not touched.

Fails closed: without the framework, or with any of the Info.plist values below missing or different, ready() is False and About
offers the download page instead (engine/update.py). Sparkle's delegate also refuses, whatever the appcast or the user defaults say:
  - any check the person did not start (background checks, update-information probes),
  - an update that is not a plain app (installer packages run as root; information-only items open a web address),
  - an archive from anywhere but https://downloads.lastbook.org (no other scheme, host or port),
  - release notes from the network, system profile parameters, and any feed address but FEED.
"""
import base64
import traceback
from pathlib import Path
from urllib.parse import urlsplit

FEED = 'https://downloads.lastbook.org/mac/appcast.xml'
HOST = 'downloads.lastbook.org'   # the only host an update archive may come from (HTTPS, default port)
BUNDLE_ID = 'local.lastbook.desktop'
# Info.plist values a trusted build must have (packaging/lastbook_macos.spec writes them only with a pinned framework and a key).
REQUIRED = {
    'SUFeedURL': FEED,
    'SUEnableAutomaticChecks': False,      # no background checks, and Sparkle never asks to turn them on
    'SUAllowsAutomaticUpdates': False,     # no silent downloads or installs
    'SUAutomaticallyUpdate': False,
    'SUEnableSystemProfiling': False,      # no profile information sent with the feed request
    'SUShowReleaseNotes': False,           # no remote release notes in Sparkle's window
    'SUVerifyUpdateBeforeExtraction': True,  # EdDSA checked before the archive is unpacked
    'SURequireSignedFeed': True,           # the appcast itself must be EdDSA-signed (Sparkle 2.9 or later)
    'SUSignedFeedFailureExpirationInterval': 0,  # never fall back to accepting an unsigned feed (Sparkle's default: after 20 days)
    'CFBundleIdentifier': BUNDLE_ID,
}
NEVER = ('SUEnableInstallerLauncherService', 'SUEnableDownloaderService')   # sandbox XPC services: Lastbook is not sandboxed
USER_INITIATED = 0          # SPUUpdateCheckUpdates; 1 is background checks, 2 update information only
NOT_READY = 'This copy of Lastbook cannot update itself. Use the download page instead.'


def public_key_ok(value):
    try:
        return isinstance(value, str) and len(base64.b64decode(value, validate=True)) == 32    # Ed25519 public key
    except ValueError:
        return False


def problem(info, bundle):
    """Why this app cannot use Sparkle, or None. info: its Info.plist as a dict; bundle: Lastbook.app's path (or None)."""
    if bundle is None:
        return 'not a built app'
    if not (Path(bundle) / 'Contents' / 'Frameworks' / 'Sparkle.framework' / 'Sparkle').exists():
        return 'Sparkle.framework is not in the app'
    for k, want in REQUIRED.items():
        if info.get(k) != want or type(info.get(k)) is not type(want):
            return f'Info.plist {k} is missing or not {want!r}'
    if not public_key_ok(info.get('SUPublicEDKey')):
        return 'Info.plist SUPublicEDKey is missing or not an Ed25519 public key'
    for k in NEVER:
        if info.get(k):
            return f'Info.plist {k} must not be set'
    if not isinstance(info.get('CFBundleVersion'), str) or info.get('CFBundleVersion') != info.get('CFBundleShortVersionString'):
        return 'Info.plist CFBundleVersion is missing or not CFBundleShortVersionString'
    if 'SUScheduledCheckInterval' in info:
        return 'Info.plist SUScheduledCheckInterval must not be set'
    return None


def url_ok(url):
    """Exactly https://downloads.lastbook.org/... on the default port: no other host, scheme, port or credentials."""
    try:
        u = urlsplit(str(url or ''))
        return u.scheme == 'https' and u.hostname == HOST and u.netloc == HOST and u.port is None
    except ValueError:
        return False


def item_ok(item):
    """Only a signed app archive from the first-party host: never an installer package or an information-only link."""
    if str(item.installationType() or 'application') != 'application' or item.isInformationOnlyUpdate():
        return False
    file_url = item.fileURL()
    return file_url is not None and url_ok(file_url.absoluteString())


class Native:
    """engine/update.py's NATIVE on a Mac. begin() is called from a request thread; Sparkle starts on the main thread."""

    def __init__(self, info, bundle, call_after):
        self.why = problem(info, bundle)
        self.bundle = bundle
        self.call_after = call_after    # PyObjCTools.AppHelper.callAfter in the app
        self.controller = self.delegate = None
        self.error = None
        if self.why:
            print('update: Update now is off:', self.why, flush=True)

    def ready(self):
        return self.why is None and self.error is None

    def status(self):
        return {'ready': self.ready(), 'error': self.error}

    def begin(self):
        if not self.ready():
            return {'error': self.error or NOT_READY}
        self.call_after(self._begin)
        return {'started': True}

    def _begin(self):
        try:
            if self.controller is None:
                self.controller, self.delegate = _start(self.bundle)
            self.controller.checkForUpdates_(None)    # user-initiated: Sparkle shows its window and asks before installing
        except Exception as e:
            traceback.print_exc()
            self.error = f'The updater could not start ({type(e).__name__}). Use the download page instead.'


def _start(bundle):
    """Loads Sparkle from inside this app and starts one updater, with the delegate below. Raises if anything is not right."""
    import Foundation
    import objc
    framework = Foundation.NSBundle.bundleWithPath_(str(Path(bundle) / 'Contents' / 'Frameworks' / 'Sparkle.framework'))
    if framework is None or not framework.load():
        raise RuntimeError('Sparkle.framework did not load')
    controller_class = objc.lookUpClass('SPUStandardUpdaterController')
    delegate = _delegate_class(objc, Foundation).alloc().init()
    controller = controller_class.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(False, delegate, None)
    updater = controller.updater()
    if updater.respondsToSelector_(b'clearFeedURLFromUserDefaults'):
        updater.clearFeedURLFromUserDefaults()     # a feed left in user defaults would win over Info.plist (the delegate's FEED wins too)
    updater.setAutomaticallyChecksForUpdates_(False)   # stale user defaults must not turn background checks back on
    updater.setAutomaticallyDownloadsUpdates_(False)
    updater.setSendsSystemProfile_(False)
    if not updater.startUpdater_(objc.NULL):
        raise RuntimeError('Sparkle did not start')
    return controller, delegate  # Sparkle does not retain its delegate.


_DELEGATE = None


def _delegate_class(objc, Foundation):
    global _DELEGATE
    if _DELEGATE is not None:
        return _DELEGATE

    def refused(why):
        return Foundation.NSError.errorWithDomain_code_userInfo_('org.lastbook.update', 1, {'NSLocalizedDescription': why})

    class LastbookSparkleDelegate(Foundation.NSObject):
        def feedURLStringForUpdater_(self, updater):
            return FEED

        @objc.typedSelector(b'@@:@Z')
        def feedParametersForUpdater_sendingSystemProfile_(self, updater, profile):
            return []

        @objc.typedSelector(b'Z@:@qo^@')
        def updater_mayPerformUpdateCheck_error_(self, updater, check, error):
            if check == USER_INITIATED:
                return True, None
            return False, refused('Lastbook checks for updates only when you ask.')

        @objc.typedSelector(b'Z@:@@qo^@')
        def updater_shouldProceedWithUpdate_updateCheck_error_(self, updater, item, check, error):
            if check == USER_INITIATED and item_ok(item):
                return True, None
            return False, refused('This update is not a signed Lastbook app. Use the download page instead.')

        @objc.typedSelector(b'Z@:@@')
        def updater_shouldDownloadReleaseNotesForUpdate_(self, updater, item):
            return False

    _DELEGATE = LastbookSparkleDelegate
    return _DELEGATE


def configure(update, bundle, info, call_after):
    """app/shell_macos.py, at launch: hands engine/update.py the Update now path. Reads only the plist dict it is given."""
    update.NATIVE = Native(info, bundle, call_after)
    return update.NATIVE
