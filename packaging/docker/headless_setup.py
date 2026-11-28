#!/usr/bin/env python3
"""Headless first-run setup and library upgrade for the server version, with no window.

Drives engine/setup/api.py's Setup exactly as the setup screen does, so downloads go through engine/setup/download.py
(allow-listed hosts, pinned roots, SHA-256 against the manifest), zips are checked before unpacking, and a library is
switched in with one rename. A job that stops (container restart, network) is picked up again on the next run.

  headless_setup.py install [--pack all] [--map ST]       first run: build $LASTBOOK_DATA
  headless_setup.py stage --into DIR [--pack all] [--map ST]   build a fresh library in DIR/LastbookData beside the open one,
                                                          with the open one's state map and address search
  headless_setup.py status                                the manifest's packs, and what is installed
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, os.environ.get('LASTBOOK_APP', '/opt/lastbook'))
from engine.setup import api, install  # noqa: E402
from engine.setup.manifest import Manifest  # noqa: E402

DATA = Path(os.environ.get('LASTBOOK_DATA', '/data/LastbookData'))
SETTINGS = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'Lastbook'
STAMP = 'docker-pack.json'      # ours, beside the library: the manifest entry it was installed from


def manifest():
    """The published manifest, fetched now: a source checkout carries no bundled copy, and a saved job's plan is rebuilt from it."""
    m = Manifest()
    m._fetch()
    if m.source != 'fetched':
        sys.exit('could not fetch the manifest from downloads.lastbook.org')
    return m


def log(*a):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


def progress(job):
    parts = []
    for it in job.get('items', []):
        done, total = it.get('bytes_done') or 0, it.get('bytes_total') or 0
        pct = f'{100 * done / total:.1f}%' if total else '-'
        rate = f' {it["rate_bps"] / 1e6:.0f} MB/s' if it.get('rate_bps') else ''
        parts.append(f'{it["title"]}: {it["state"]} {pct}{rate}')
    return f'[{job["state"]}] ' + '; '.join(parts)


def ours(job, target, pack_id, map_id=None, address_id=None):
    """Whether a saved job is the one asked for now: the same target folder, pack and map, and the address search if one is named.
    Setup keeps one job in its settings folder whatever it was for: a finished first install whose library was never opened, or
    a stage into another folder, must not stand in for this one."""
    items = {i.get('kind'): i.get('id') for i in job.get('items', [])}
    return (job.get('folder') == str(target) and items.get('pack') == pack_id and items.get('map') == map_id
            and (not address_id or items.get('addresses') == address_id))


def run(setup, start, target, pack_id, map_id=None, address_id=None):
    """Starts (or resumes) the job and waits for it. Returns the finished job, or exits on failure."""
    job = setup.public_job()
    if job and not ours(job, target, pack_id, map_id, address_id):
        what = ', '.join(f'{i.get("kind")} {i.get("id")}' for i in job.get('items', []))
        if job['state'] not in ('done', 'failed'):
            sys.exit(f'setup has an unfinished job for {job.get("folder")} ({what}), not this one. Run the command that started it to '
                     f'finish it, or delete {SETTINGS / "setup" / "job.json"} to drop it, then run this again.')
        log(f'the saved {job["state"]} job was for {job.get("folder")} ({what}); starting a new one')
        job = None
    if job and job['state'] == 'paused':
        log('resuming the saved job')
        setup.resume()
    elif job and job['state'] == 'failed':
        log('retrying the saved job:', job.get('error'))
        setup.retry()
    elif job and job['state'] in api.ACTIVE:
        setup._run()
    elif not job or job['state'] != 'done':
        out = start()
        if isinstance(out, dict) and out.get('error'):
            sys.exit(f'setup refused: {out["error"]}')
    last = 0
    while True:
        job = setup.public_job()
        if job['state'] in ('done', 'failed'):
            break
        if time.time() - last > 60:
            log(progress(job))
            last = time.time()
        time.sleep(5)
    log(progress(job))
    if job['state'] == 'failed':
        sys.exit(f'setup failed: {job.get("error")}')
    return job


def stamp(lib, pack):
    install._write_json(Path(lib) / STAMP, {'id': pack['id'], 'files': pack['files'], 'revision': pack.get('revision', ''),
                                            'installed': time.strftime('%Y-%m-%dT%H:%M:%S')})


def same_pack(lib, pack, map_id=None, address_id=None):
    """None if the library at `lib` holds exactly this pack (and map and address search), else why not. Setup's own pack.json
    names the pack and, for a pack with revisions, its content revision, which setup checks when it unpacks. A pack without
    revisions (All) keeps the same file names from one release to the next, so only the SHA-256s in our stamp, written
    after an install we made, tell its releases apart; without one it cannot be shown to match."""
    lib = Path(lib)
    try:
        meta = json.loads((lib / 'pack.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'it has no readable pack.json'
    if meta.get('name') != pack['id']:
        return f'it holds the {meta.get("name")!r} pack, not {pack["id"]!r}'
    if pack.get('revision'):
        if meta.get('content_revision') != pack['revision']:
            return f'it holds revision {meta.get("content_revision")!r}, not {pack["revision"]!r}'
    else:
        try:
            ours = json.loads((lib / STAMP).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return f'the {pack["id"]!r} pack has no revisions and this library has no {STAMP} to show which release it is'
        if [f.get('sha256') for f in ours.get('files', [])] != [f['sha256'] for f in pack['files']]:
            return f'{STAMP} records another release of {pack["id"]!r}'
    if map_id and install.map_name(lib) != map_id:
        return f'its map is {install.map_name(lib)!r}, not {map_id!r}'
    if address_id and not (lib / 'derived' / 'geo' / 'addresses' / f'{address_id}.sqlite').is_file():
        return f'it has no {address_id} address search'
    return None


def cmd_install(a):
    if install.is_library(DATA):
        log(f'{DATA} is already a library; nothing to do')
        return
    setup = api.Setup('first-run', SETTINGS, DATA.parent, manifest=manifest())
    pack = setup.manifest.pack(a.pack)
    if not pack:
        sys.exit(f'no pack {a.pack!r} in the manifest')
    log(f'installing {pack["title"]} ({sum(f["size"] for f in pack["files"]) / 1e9:.0f} GB download) into {DATA}')
    run(setup, lambda: setup.start(a.pack, folder=str(DATA.parent), map_id=a.map), DATA, a.pack, a.map)
    lib, note = api.startup(SETTINGS)       # what app/main.py does before it opens a library
    api.opened(SETTINGS, DATA, note)
    if not install.is_library(DATA):
        sys.exit(f'setup finished but {DATA} is not a library')
    stamp(DATA, pack)
    log('library installed')


def cmd_stage(a):
    """A new copy of the pack, beside the open library. The caller swaps it in while the server is stopped."""
    into = Path(a.into)
    setup = api.Setup('manage', SETTINGS, DATA.parent, current=DATA, manifest=manifest())
    pack = setup.manifest.pack(a.pack)
    if not pack:
        sys.exit(f'no pack {a.pack!r} in the manifest')
    target = into / install.DATA_NAME
    # A separate target skips setup's own carry-over of the open library's state map and address search, so name
    # them. The state map only for the same pack, as setup does (another pack brings its own maps: All has the whole
    # US), unless --map asks for one; the address search always.
    cur = setup.current_info() or {}
    same = cur.get('pack') == pack['id']
    map_id = a.map or (cur.get('map') if same and cur.get('map') not in (None, 'base', 'us') else None)
    have = cur.get('address_indexes') or []
    address_id = None if a.map else map_id if map_id in have else next(iter(have), None)   # None: setup uses the map's own
    if len(have) > 1:
        log(f'only one address search moves with a pack; keeping {address_id}, not {", ".join(x for x in have if x != address_id)}')
    installed = False
    if install.is_library(target):
        why = same_pack(target, pack, map_id, address_id)
        if why:      # never relabel what is there: it stays as it is, and nothing is downloaded over it
            sys.exit(f'{target} is already a library, but not this one: {why}. Move it away or delete it, then stage again.')
        log(f'{target} already holds {pack["title"]}' + (f' revision {pack["revision"]}' if pack.get('revision') else '') + '; using it')
    else:
        log(f'staging {pack["title"]} into {target}' + (f' with the {map_id} map' if map_id else '')
            + (f' and {address_id} address search' if address_id else ''))
        run(setup, lambda: setup.start(a.pack, folder=str(into), map_id=map_id, address_id=address_id), target, a.pack, map_id, address_id)
        lib, note = api.startup(SETTINGS)   # the finished job only stages the rename into `target`; this makes it
        api.opened(SETTINGS, target, note)
        installed = True
    if not install.is_library(target):
        sys.exit(f'setup finished but {target} is not a library')
    key = DATA / 'derived' / 'lan-key'      # links holding the access key keep working after the swap
    if key.is_file() and not (target / 'derived' / 'lan-key').exists():
        (target / 'derived').mkdir(parents=True, exist_ok=True)
        shutil.copy2(key, target / 'derived' / 'lan-key')
    if installed or not (target / STAMP).exists():
        stamp(target, pack)  # setup just installed it, or a reused one whose revision pack.json shows
    log('staged')


def cmd_status(a):
    m = manifest()
    try:
        here = json.loads((DATA / STAMP).read_text())
    except (OSError, ValueError):
        here = None
    packs = {p['id']: p for p in m.current.get('packs', [])}
    out = {'installed': here, 'latest': packs.get((here or {}).get('id') or a.pack)}
    if here and out['latest']:
        out['update_available'] = [f['sha256'] for f in here['files']] != [f['sha256'] for f in out['latest']['files']] \
            or here.get('revision', '') != out['latest'].get('revision', '')
    print(json.dumps(out, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('install')
    p.add_argument('--pack', default=os.environ.get('LASTBOOK_PACK', 'small'))
    p.add_argument('--map', default=os.environ.get('LASTBOOK_MAP') or None)
    p = sub.add_parser('stage')
    p.add_argument('--into', required=True)
    p.add_argument('--pack', default=os.environ.get('LASTBOOK_PACK', 'small'))
    p.add_argument('--map', default=None, help='a state map other than the one the open library has')
    p = sub.add_parser('status')
    p.add_argument('--pack', default=os.environ.get('LASTBOOK_PACK', 'small'))
    a = ap.parse_args()
    {'install': cmd_install, 'stage': cmd_stage, 'status': cmd_status}[a.cmd](a)


if __name__ == '__main__':
    main()
