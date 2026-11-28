"""Puts the pinned Sparkle.framework into a built Lastbook.app, for Update now (app/update_macos.py). Downloads nothing.

  python -I -B sparkle_framework.py ARCHIVE Lastbook.app

ARCHIVE is the official Sparkle-<version>.tar.xz, fetched by hand; its SHA-256 must equal sparkle.lock.json's, or nothing changes.
Only Sparkle.framework and its LICENSE (as Contents/Resources/LICENSE-Sparkle.txt) are taken from it. Its XPC services go (Lastbook is not sandboxed: Sparkle's sandboxing guide), its binaries are
thinned to arm64 (scan_package_macos.py's rule), then each part is signed again, inside out as Sparkle's docs list, with the same
ad-hoc identity build_app_macos.sh uses for everything else, and the app last. A Developer ID release re-signs the whole app the same way.
"""
import hashlib
import json
import plistlib
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

LOCK = Path(__file__).resolve().with_name('sparkle.lock.json')
LICENSE = 'LICENSE-Sparkle.txt'
IDENTITY = '-'    # ad-hoc, as the rest of the build; never a certificate here


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def verify(archive, lock):
    if not lock.get('version') or len(lock.get('sha256', '')) != 64:
        raise SystemExit('sparkle.lock.json has no pinned version and sha256: fill them from the official release first')
    if Path(archive).name != lock['archive'].format(version=lock['version']):
        raise SystemExit(f'{Path(archive).name} is not the pinned {lock["archive"].format(version=lock["version"])}')
    got = sha256(archive)
    if got != lock['sha256'].lower():
        raise SystemExit(f'Sparkle archive SHA-256 {got} is not the pinned {lock["sha256"]}')


def extract(archive, into):
    with tarfile.open(archive, 'r:xz') as t:
        members = [m for m in t.getmembers() if m.name.removeprefix('./').startswith('Sparkle.framework/') or m.name.removeprefix('./') == 'LICENSE']
        if not any(m.name.removeprefix('./') == 'LICENSE' and m.isfile() for m in members):
            raise SystemExit('no LICENSE in the archive')
        if len(members) < 2:
            raise SystemExit('no Sparkle.framework in the archive')
        t.extractall(into, members=members, filter='data')    # no absolute paths, no links out, no device files
    return Path(into) / 'Sparkle.framework'


def run(*args):
    subprocess.run(list(args), check=True)       # argument lists only: no shell


def prepare(fw):
    version = fw / 'Versions' / 'Current'
    xpc = version / 'XPCServices'
    if xpc.exists():
        run('/bin/rm', '-rf', str(xpc.resolve()))
    if (fw / 'XPCServices').is_symlink():
        (fw / 'XPCServices').unlink()
    for p in sorted(fw.rglob('*')):
        if p.is_file() and not p.is_symlink() and p.read_bytes()[:4] in (b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe'):
            if 'arm64' not in subprocess.run(['lipo', '-archs', str(p)], capture_output=True, text=True).stdout.split():
                raise SystemExit(f'no arm64 in {p}')
            if p.read_bytes()[:4] == b'\xca\xfe\xba\xbe':
                thin = p.with_name(p.name + '.arm64')
                run('lipo', str(p), '-thin', 'arm64', '-output', str(thin))
                thin.chmod(p.stat().st_mode)
                thin.replace(p)
    for part in (version / 'Autoupdate', version / 'Updater.app', fw):
        run('codesign', '--force', '--sign', IDENTITY, '--options', 'runtime', str(part))


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    archive, app = Path(sys.argv[1]), Path(sys.argv[2])
    verify(archive, json.loads(LOCK.read_text(encoding='utf-8')))
    dest = app / 'Contents' / 'Frameworks' / 'Sparkle.framework'
    if dest.exists():
        raise SystemExit(f'{dest} already exists')
    with tempfile.TemporaryDirectory() as tmp:
        fw = extract(archive, tmp)
        prepare(fw)
        run('/usr/bin/ditto', str(fw), str(dest))       # keeps the framework's symlinks
        (app / 'Contents' / 'Resources').mkdir(parents=True, exist_ok=True)
        (app / 'Contents' / 'Resources' / LICENSE).write_bytes((fw.parent / 'LICENSE').read_bytes())   # MIT: ship its notice
    set_bundle_version(app)
    run('codesign', '--force', '--sign', IDENTITY, str(app))     # the app's seal now covers the framework
    print(f'Sparkle {json.loads(LOCK.read_text())["version"]} added to {app}')


def set_bundle_version(app):
    """Sparkle compares CFBundleVersion; the spec writes only CFBundleShortVersionString (its version=), so copy that one value."""
    plist = app / 'Contents' / 'Info.plist'
    info = plistlib.loads(plist.read_bytes())
    version = info.get('CFBundleShortVersionString')
    if not isinstance(version, str) or not version:
        raise SystemExit('Info.plist has no CFBundleShortVersionString')
    info['CFBundleVersion'] = version
    plist.write_bytes(plistlib.dumps(info))


if __name__ == '__main__':
    main()
