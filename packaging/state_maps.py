"""Build, check, zip, upload and list one region's detailed map (docs/SETUP-API.md, "State maps"): a US state, or a
European country ('eu-<iso>' codes, packaging/europe-countries.json). Country publishing is opt-in: only countries in
packaging/country-publication.json are offered, and each must hold real detail inside its box or it is not published.

  derived/app-build/mac-venv/bin/python3 -I -B packaging/state_maps.py CA TX eu-at ...   # one region at a time, in this order
  ... packaging/state_maps.py --order                                              # every published region, in release order
  ... packaging/state_maps.py --dry-run eu-at [--set derived/packs/maps/eu-at]      # counts and blockers only; no zip, upload or manifest

Each region: build (CA and RI are kept as built), scan, zip to derived/packs/state-zips/, upload to maps/ on the bucket,
check the public SHA-256, list it under "maps" in derived/release/manifest-v1.json and upload that, then delete the zip
and the build copy (CA and RI stay). Results go to derived/packs/state-maps.json and STATE-MAPS.md.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / 'derived/packs/maps'
ZIPS = ROOT / 'derived/packs/state-zips'
RESULTS = ROOT / 'derived/packs/state-maps.json'
LOCK = ROOT / 'derived/packs/state-maps.lock'      # one writer at a time for the manifest, results and table
CLAIMS = ROOT / 'derived/packs/state-claims'        # a worker owns a state by making its folder here
TABLE = ROOT / 'derived/packs/STATE-MAPS.md'
MANIFEST = ROOT / 'derived/release/manifest-v1.json'
BASE = 'https://downloads.lastbook.org'
KEEP = {'CA', 'RI'}
FIRST = ['CA', 'TX', 'FL', 'NY', 'PA', 'IL', 'OH', 'GA', 'NC', 'MI']
NAMES = dict(AL='Alabama', AK='Alaska', AZ='Arizona', AR='Arkansas', CA='California', CO='Colorado', CT='Connecticut', DE='Delaware',
             DC='District of Columbia', FL='Florida', GA='Georgia', HI='Hawaii', ID='Idaho', IL='Illinois', IN='Indiana', IA='Iowa', KS='Kansas',
             KY='Kentucky', LA='Louisiana', ME='Maine', MD='Maryland', MA='Massachusetts', MI='Michigan', MN='Minnesota', MS='Mississippi',
             MO='Missouri', MT='Montana', NE='Nebraska', NV='Nevada', NH='New Hampshire', NJ='New Jersey', NM='New Mexico', NY='New York',
             NC='North Carolina', ND='North Dakota', OH='Ohio', OK='Oklahoma', OR='Oregon', PA='Pennsylvania', PR='Puerto Rico', RI='Rhode Island',
             SC='South Carolina', SD='South Dakota', TN='Tennessee', TX='Texas', UT='Utah', VT='Vermont', VA='Virginia', WA='Washington',
             WV='West Virginia', WI='Wisconsin', WY='Wyoming')
COUNTRY_SETS = json.loads((ROOT / 'packaging' / 'europe-countries.json').read_text(encoding='utf-8'))['countries']
COUNTRIES = {code: c['title'] for code, c in COUNTRY_SETS.items()}
PUBLISHED_COUNTRIES = json.loads((ROOT / 'packaging' / 'country-publication.json').read_text(encoding='utf-8'))['countries']
TITLES = {**NAMES, **COUNTRIES}
INCLUDES = 'Local streets, buildings, terrain and crops, plus water, help and resource points'
ALLOWED = {f'derived/geo/{n}.sqlite' for n in ('national', 'map', 'water', 'terrain', 'buildings', 'crops', 'places')} | {
    'derived/geo/national-status.json', 'derived/geo/socal-cells.json', 'library-data/geography/resources/atlas.sqlite', 'map-set.json'}
STORED = {'derived/geo/terrain.sqlite'}     # tiles are already compressed

sys.path.insert(0, str(ROOT / 'packaging'))
sys.path.insert(0, str(ROOT / 'derived/release'))
import scan_pack as S       # noqa: E402


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def _r2():
    """The bucket client, imported only when publishing: a read-only dry run needs no credentials or release files."""
    import r2_publish
    return r2_publish


def states():
    db = sqlite3.connect(f'file:{MAPS}/source/profiles.sqlite?immutable=1', uri=True)
    have = sorted({s for (s,) in db.execute('SELECT DISTINCT state FROM zcta') if s and re.fullmatch(r'[A-Z]{2}', s)} | {'CT'})
    return FIRST + [s for s in have if s not in FIRST]


def regions():
    """Every region a map is published for, in release order: the states as states() has them, then the countries a
    person has opted in to in packaging/country-publication.json, by name. A country's code is its own ('eu-de'), never
    a state's, so the two never collide. Countries are left out by default: the detail layers are still US-only, so an
    unlisted country build would be only the low-zoom base and must not be offered as that country's detailed map."""
    return states() + sorted(PUBLISHED_COUNTRIES, key=lambda c: COUNTRIES[c])


COVERAGE = ('roads', 'help points', 'water points', 'terrain tiles', 'buildings', 'crops', 'place names')


def country_box(code):
    """A country's box as build_packs.country_box makes it: the extract envelope plus the same 0.15 degree margin."""
    w, s, e, n = COUNTRY_SETS[code]['box']
    return w - .15, s - .15, e + .15, n + .15


def _tile_ranges(code, zooms):
    import build_packs as BP
    box = country_box(code)
    return {z: BP.tile_range(box, z) for z in zooms}


def _z_clause(ranges):
    """An OR of per-zoom tile windows, so a tile row at any written zoom is checked at that zoom's own grid."""
    parts, args = [], []
    for z, (x0, x1, y0, y1) in ranges.items():
        parts.append('(z=? AND x BETWEEN ? AND ? AND y BETWEEN ? AND ?)')
        args += [z, x0, x1, y0, y1]
    return ' OR '.join(parts), tuple(args)


def coverage_queries(code):
    """One count per detail layer, each restricted to rows inside this country's box. A stray row or a neighbour's
    detail outside the box never counts. Roads are real road features only: the national `feat` table also holds
    place names, so a bare `minz>8` would report 1,076 Vienna place points as 1,076 streets even with zero roads."""
    w, s, e, n = country_box(code)
    lonlat = 'lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?'
    terrain_z, terrain_args = _z_clause(_tile_ranges(code, range(8, 13)))
    x0, x1, y0, y1 = _tile_ranges(code, [14])[14]
    return {
        'roads': ('national.sqlite',
                  "SELECT count(*) FROM feat f JOIN feat_idx i ON i.id=f.id WHERE f.layer='road' AND "
                  'i.maxx>=? AND i.minx<=? AND i.maxy>=? AND i.miny<=?', (w, e, s, n)),
        'help points': ('national.sqlite', f'SELECT count(*) FROM poi WHERE {lonlat}', (w, e, s, n)),
        'water points': ('water.sqlite', f'SELECT count(*) FROM resource WHERE {lonlat}', (w, e, s, n)),
        'terrain tiles': ('terrain.sqlite', f'SELECT count(*) FROM tile WHERE z>7 AND ({terrain_z})', terrain_args),
        'buildings': ('buildings.sqlite',
                      f'SELECT (SELECT count(*) FROM bldg WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?)'
                      f' + (SELECT count(*) FROM bldg_socal WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?)'
                      f' + (SELECT count(*) FROM bldg_osm WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?)',
                      (x0, x1, y0, y1) * 3),
        'crops': ('crops.sqlite', f'SELECT count(*) FROM resource WHERE {lonlat}', (w, e, s, n)),
        'place names': ('places.sqlite', f"SELECT count(*) FROM place WHERE source='OpenStreetMap' AND {lonlat}", (w, e, s, n)),
    }


def coverage_counts(d, code):
    """How much real detail a built country set holds inside its box, per layer. The base map supplies low-zoom
    roads and terrain and no pins; a US-only source snapshot gives zero here for a European country even though
    the scan passes."""
    d = Path(d)
    queries = coverage_queries(code)
    counts = {}
    for name in COVERAGE:
        file, query, args = queries[name]
        try:
            db = sqlite3.connect(f'file:{d / "derived/geo" / file}?immutable=1', uri=True)
            try:
                counts[name] = db.execute(query, args).fetchone()[0]
            finally:
                db.close()
        except sqlite3.Error:
            counts[name] = 0
    return counts


def country_coverage(d, code):
    """The detail layers that hold nothing inside this country's box. Empty means the coverage check passed."""
    return {name: n for name, n in coverage_counts(d, code).items() if not n}


def country_opt_in_blockers(code):
    """Why a country may not be published at all, or [] if it is opted in. Needs no built set, so an explicit publish
    request can be refused before the build starts or the publishing client is opened."""
    if code not in PUBLISHED_COUNTRIES:
        return ['publishing a country is opt-in: add it to packaging/country-publication.json only after its source snapshot passes the coverage check']
    return []


def country_publish_blockers(d, code):
    """Why a country set may not be published, or [] if its opt-in and coverage are both in order."""
    blockers = country_opt_in_blockers(code)
    if blockers:
        return blockers
    missing = country_coverage(d, code)
    return [f'no {name} detail inside the country box' for name in missing]


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while b := f.read(1 << 24):
            h.update(b)
    return h.hexdigest()


def scan(d, code):
    """The scan_pack rules that apply to a map set, and the map-set rules: only the listed files, nothing about the household's area."""
    terms = S.read_terms(str(ROOT / 'derived/packs/private-terms.txt'))
    if not terms:
        sys.exit('no private terms')
    sc = S.Scan(d, terms, {}, None)
    sc.done_early = set()
    files = sc.walk()
    rels = [p.relative_to(d).as_posix() for p in files]
    fails = []
    if set(rels) != ALLOWED:
        fails.append(f'files differ from the contract: extra {sorted(set(rels) - ALLOWED)} missing {sorted(ALLOWED - set(rels))}')
    for p, rel in zip(files, rels):
        st = os.lstat(p)
        if rel == 'map-set.json':
            info = sc.load_json(rel, rels, 'map-set')
            if not isinstance(info, dict) or info.get('name') != code or set(info) - {'name', 'files', 'bytes', 'seconds'}:
                fails.append('map-set.json does not name the region')
            continue
        sc.name_rules(rel, st, p.is_symlink())
        if rel.endswith('.json'):
            sc.load_json(rel, rels, 'status')
            data = p.read_bytes()
            if rel.endswith('national-status.json') and set(json.loads(data)) - {'state', 'stage', 'features'}:
                fails.append('status fields')
            if rel.endswith('socal-cells.json') and json.loads(data) != []:
                fails.append('socal-cells.json is not empty')
        else:
            sc.inspect_map(rel, p)
            db = sqlite3.connect(f'file:{p}?immutable=1', uri=True)
            for t in ('meta', 'metadata'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone():
                    for row in db.execute(f'SELECT * FROM "{t}"'):
                        for x in row:
                            if isinstance(x, str) and (S.HOUSEHOLD.search(x.encode()) or S.USER_PATH.search(x.encode()) or S.LAN.search(x.encode())):
                                fails.append(f'{rel}: {t} names the household, a local path or a LAN address')
            if rel.endswith('/map.sqlite'):
                n = sum(db.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in ('feat', 'poi', 'meta'))
                if n:
                    fails.append('map.sqlite (the household area map) is not empty')
            if rel.endswith('/buildings.sqlite'):     # every footprint table holds only tiles inside this region's box: no area beyond the region rule
                import build_packs as BP
                x0, x1, y0, y1 = BP.tile_range(BP.region_box(MAPS / 'source', code), 14)
                for t in ('bldg', 'bldg_socal', 'bldg_osm'):
                    if db.execute(f'SELECT count(*) FROM {t} WHERE x NOT BETWEEN ? AND ? OR y NOT BETWEEN ? AND ?', (x0, x1, y0, y1)).fetchone()[0]:
                        fails.append(f'{t} rows outside the state box')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('done','done_socal')").fetchone():
                fails.append(f'{rel}: build progress tables left in')
            db.close()
    for rule, paths in sc.fails.items():
        fails.append(f'{rule}: {paths[:5]}')
    return fails, sc.listed


def web_text(d):
    """Scripts in the text the map shows fail. Web addresses there (a marina's website, a shop's page) are third-party text the Map shows as
    plain words, never as links, as in the Medium pack; they are counted for the report, not removed."""
    fails, notes = [], {}
    for p in d.rglob('*.sqlite'):
        db = sqlite3.connect(f'file:{p}?immutable=1', uri=True)
        virt = [v for (v,) in db.execute("SELECT name FROM sqlite_master WHERE sql LIKE 'CREATE VIRTUAL%'")]
        for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql NOT LIKE 'CREATE VIRTUAL%'").fetchall():
            if any(t.startswith(v + '_') for v in virt):
                continue
            for (c, ctype) in [(r[1], (r[2] or '').upper()) for r in db.execute(f'PRAGMA table_info("{t}")')]:
                if 'BLOB' in ctype or c in ('geom', 'data', 'tile', 'img', 'source'):     # source holds citation addresses as text, as in the Medium pack
                    continue
                q = f'SELECT count(*) FROM "{t}" WHERE typeof("{c}")=\'text\' AND '
                n = db.execute(q + f'("{c}" LIKE \'%<script%\' OR "{c}" LIKE \'%javascript:%\')').fetchone()[0]
                if n:
                    fails.append(f'{p.relative_to(d)}: {t}.{c} script {n}')
                n = db.execute(q + f'("{c}" LIKE \'%http:%\' OR "{c}" LIKE \'%https:%\' OR "{c}" LIKE \'%www.%\')').fetchone()[0]
                if n:
                    notes[f'{p.relative_to(d).name}:{t}.{c}'] = n
        db.close()
    return fails, notes


def make_zip(d, out):
    tmp = out.with_suffix('.partial')
    with zipfile.ZipFile(tmp, 'w', allowZip64=True) as z:
        for rel in sorted(ALLOWED):
            how = zipfile.ZIP_STORED if rel in STORED else zipfile.ZIP_DEFLATED
            zi = zipfile.ZipInfo(rel, date_time=(2026, 11, 12, 0, 0, 0))
            zi.compress_type = how
            zi.external_attr = 0o644 << 16
            with open(d / rel, 'rb') as src, z.open(zi, 'w', force_zip64=True) as dst:
                while b := src.read(1 << 24):
                    dst.write(b)
    with zipfile.ZipFile(tmp) as z:
        names = {i.filename: i.file_size for i in z.infolist()}
    if names != {rel: (d / rel).stat().st_size for rel in ALLOWED}:
        sys.exit('zip does not hold exactly the set')
    os.replace(tmp, out)


def upload(ctx, path, key):
    """r2_publish.upload_file, with a key under maps/."""
    R = _r2()
    size = path.stat().st_size
    ctype = 'application/zip'
    if size <= R.MULTIPART_OVER:
        st, _, out = R.s3(ctx, 'PUT', key, body=path.read_bytes(), headers={'content-type': ctype})
        if st != 200:
            sys.exit(f'{key}: HTTP {st} {out[:300]!r}')
        return
    st, _, out = R.s3(ctx, 'POST', key, {'uploads': ''}, headers={'content-type': ctype})
    uid = R.tag(out.decode(), 'UploadId')
    if st != 200 or not uid:
        sys.exit(f'{key}: could not start, HTTP {st}')
    count = (size + R.PART - 1) // R.PART
    import concurrent.futures

    def one(n):
        with open(path, 'rb') as f:
            f.seek((n - 1) * R.PART)
            data = f.read(R.PART)
        s, hd, body = R.s3(ctx, 'PUT', key, {'partNumber': str(n), 'uploadId': uid}, body=data)
        if s != 200:
            raise RuntimeError(f'part {n}: HTTP {s} {body[:200]!r}')
        return n, hd.get('ETag') or hd.get('etag')
    done = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            for n, etag in pool.map(one, range(1, count + 1)):
                done[n] = etag
                if len(done) % 10 == 0 or len(done) == count:
                    log(f'  {key}: part {len(done)}/{count}')
    except Exception:
        R.s3(ctx, 'DELETE', key, {'uploadId': uid})
        raise
    xml = '<CompleteMultipartUpload>' + ''.join(f'<Part><PartNumber>{n}</PartNumber><ETag>{done[n]}</ETag></Part>' for n in sorted(done)) + '</CompleteMultipartUpload>'
    st, _, out = R.s3(ctx, 'POST', key, {'uploadId': uid}, body=xml.encode())
    if st != 200 or b'<Error>' in out:
        sys.exit(f'{key}: could not finish, HTTP {st} {out[:300]!r}')


def public_sha(url):
    h = hashlib.sha256()
    n = 0
    req = urllib.request.Request(url + f'?v={int(time.time())}', headers={'User-Agent': 'curl/8.7.1', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=120) as r:
        while b := r.read(1 << 22):
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def list_in_manifest(ctx, entry):
    R = _r2()
    m = json.loads(MANIFEST.read_text())
    packs, models = json.dumps(m['packs']), json.dumps(m.get('models'))
    maps = [x for x in m.get('maps', []) if x['id'] != entry['id']] + [entry]
    order = {s: i for i, s in enumerate(regions())}
    m['maps'] = sorted(maps, key=lambda x: order.get(x['id'], 999))
    assert json.dumps(m['packs']) == packs and json.dumps(m.get('models')) == models
    tmp = MANIFEST.with_suffix('.maps-tmp')
    tmp.write_text(json.dumps(m, indent=1) + '\n')
    os.replace(tmp, MANIFEST)
    data = MANIFEST.read_bytes()
    st, _, out = R.s3(ctx, 'PUT', 'manifest-v1.json', body=data, headers={'content-type': 'application/json; charset=utf-8'})
    if st != 200:
        sys.exit(f'manifest upload HTTP {st}')
    for _ in range(10):
        got, _n = public_sha(f'{BASE}/manifest-v1.json')
        if got == hashlib.sha256(data).hexdigest():
            return
        time.sleep(3)
    sys.exit('public manifest does not match')


def write_table(res):
    rows = ['# State and country maps', '', 'One detailed map per state or European country, for first-run setup (docs/SETUP-API.md, "State maps"). Built by `packaging/state_maps.py`;',
            'each zip was scanned, uploaded, checked by its public SHA-256 and then listed under `maps` in `manifest-v1.json`.', '',
            '| Region | Zip size | Installed size | SHA-256 | URL |', '|---|---:|---:|---|---|']
    order = {s: i for i, s in enumerate(regions())}
    for code in sorted(res, key=lambda c: order.get(c, 999)):
        r = res[code]
        rows.append(f"| {code} {TITLES.get(code, '')} | {r['size'] / 1e9:.2f} GB ({r['size']:,}) | {r['installed_bytes'] / 1e9:.2f} GB ({r['installed_bytes']:,}) | `{r['sha256']}` | {r['url']} |")
    TABLE.write_text('\n'.join(rows) + '\n')


def one_state(ctx, code, res):
    d = MAPS / code
    t0 = time.time()
    if code in KEEP:
        if not (d / 'map-set.json').exists():
            sys.exit(f'{code} should be built already')
    else:
        while shutil.disk_usage(ROOT).free < 35e9:      # other workers' zips are deleted as they finish
            log(code, 'waiting for disk space')
            time.sleep(120)
        log(code, 'building')
        subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'packaging/build_packs.py'), 'map', code], check=True, stdout=subprocess.DEVNULL)
    fails, listed = scan(d, code)
    wf, web = web_text(d)
    fails += wf
    if fails:
        sys.exit(f'{code} scan failed: {fails}')
    log(code, 'scan passed', dict((k, len(v)) for k, v in listed.items()))
    blockers = country_publish_blockers(d, code) if code in COUNTRIES else []
    if blockers:
        sys.exit(f'{code}: not publishing: {blockers}')
    coverage = coverage_counts(d, code) if code in COUNTRIES else None
    installed = sum((d / rel).stat().st_size for rel in ALLOWED)
    ZIPS.mkdir(exist_ok=True)
    z = ZIPS / f'Lastbook-Map-{code}.zip'
    make_zip(d, z)
    sha, size = sha_file(z), z.stat().st_size
    log(code, 'zipped', size)
    key = f'maps/{z.name}'
    upload(ctx, z, key)
    url = f'{BASE}/{key}'
    got, n = public_sha(url)
    if got != sha or n != size:
        sys.exit(f'{code}: public copy differs ({got} {n})')
    log(code, 'public copy verified')
    entry = {'id': code, 'title': TITLES.get(code, code), 'kind': 'state' if code in NAMES else 'country', 'installed_bytes': installed, 'available': True, 'includes': INCLUDES,
             'files': [{'name': z.name, 'url': url, 'size': size, 'sha256': sha, 'kind': 'zip'}]}
    with open(LOCK, 'a') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        list_in_manifest(ctx, entry)
        res.clear()
        res.update(json.loads(RESULTS.read_text()) if RESULTS.exists() else {})
        res[code] = {'size': size, 'installed_bytes': installed, 'sha256': sha, 'url': url, 'web_address_text': web, 'seconds': round(time.time() - t0)}
        if coverage is not None:
            res[code]['coverage'] = coverage
        tmp = RESULTS.with_suffix('.tmp')
        tmp.write_text(json.dumps(res, indent=1) + '\n')
        os.replace(tmp, RESULTS)
        write_table(res)
    log(code, 'listed')
    z.unlink()
    if code not in KEEP:
        shutil.rmtree(d)


DRY_RUN_USAGE = 'usage: state_maps.py --dry-run [eu-xx ...] [--set DIR]'


def dry_run_args(args):
    """Parse --dry-run's arguments: country codes plus at most one --set DIR. One folder can only describe one
    country's set, so --set with several codes is refused. A repeated or incomplete --set, or an unknown option, is
    refused with the usage rather than read as a country code."""
    codes, where, i = [], None, 0
    while i < len(args):
        arg = args[i]
        if arg == '--set' or arg.startswith('--set='):
            if where is not None:
                raise ValueError('--set may be given only once; ' + DRY_RUN_USAGE)
            if arg == '--set':
                if i + 1 == len(args) or not args[i + 1] or args[i + 1].startswith('-'):
                    raise ValueError('--set needs a folder; ' + DRY_RUN_USAGE)
                where = args[i + 1]
                i += 2
            else:
                where = arg.split('=', 1)[1]
                if not where:
                    raise ValueError('--set needs a folder; ' + DRY_RUN_USAGE)
                i += 1
        elif arg.startswith('-'):
            raise ValueError(f'unknown option {arg!r}; ' + DRY_RUN_USAGE)
        elif not arg:
            raise ValueError('empty country code; ' + DRY_RUN_USAGE)
        else:
            codes.append(arg)
            i += 1
    if where is not None and len(codes) > 1:
        raise ValueError('one --set folder cannot describe more than one country; ' + DRY_RUN_USAGE)
    return codes, where


def dry_run(codes, where=None):
    """Report each country's real coverage and its publish blockers. Codes are checked before any coverage query, so
    a state such as RI gets a clear blocker instead of a lookup failure. Reads the built set only: no zip, no upload,
    no manifest, no bucket credentials. Exits 1 if any code would not be published."""
    codes = list(codes)
    if not codes:
        print('no countries checked: packaging/country-publication.json lists none')
        return 0
    unknown = {code for code in codes if code not in COUNTRIES}
    ok = not unknown
    for code in codes:
        d = Path(where) if where else MAPS / code
        if code in unknown:
            counts, blockers = {}, [f'{code} is not a country code']
        else:
            counts = coverage_counts(d, code)
            blockers = country_publish_blockers(d, code)
        print(json.dumps({'region': code, 'set': str(d), 'coverage': counts, 'publish_blockers': blockers}, ensure_ascii=False, sort_keys=True))
        ok = ok and not blockers
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if any(arg == '--dry-run' or arg.startswith('--dry-run=') for arg in args) and args[:1] != ['--dry-run']:
        print('--dry-run must be given first; ' + DRY_RUN_USAGE, file=sys.stderr)
        sys.exit(2)
    if args[:1] == ['--dry-run']:
        try:
            codes, where = dry_run_args(args[1:])
            if where is not None and not Path(where).is_dir():
                raise ValueError(f'--set folder not found: {where}; ' + DRY_RUN_USAGE)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            sys.exit(2)
        sys.exit(dry_run(codes or sorted(PUBLISHED_COUNTRIES, key=lambda c: COUNTRIES[c]), where))
    todo = regions() if args == ['--order'] else ([] if args[:1] == ['--worker'] else args)
    for code in todo:
        blockers = country_opt_in_blockers(code) if code in COUNTRIES else []
        if blockers:
            sys.exit(f'{code}: not publishing: {blockers}')
    ctx = _r2().Context()
    if args[:1] == ['--worker']:
        """Take the next unclaimed region in release order until none is left. A failed region is written down and left claimed, for a person to look at."""
        name = args[1]
        CLAIMS.mkdir(exist_ok=True)
        for code in regions():
            res = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
            if code in res:
                continue
            try:
                os.mkdir(CLAIMS / code)
            except FileExistsError:
                continue
            (CLAIMS / code / 'worker').write_text(name)
            log(name, 'took', code)
            try:
                one_state(ctx, code, res)
            except BaseException as e:      # sys.exit and crashes alike
                (CLAIMS / code / 'failed').write_text(f'{e.__class__.__name__}: {e}')
                log(name, code, 'FAILED', e)
                if isinstance(e, KeyboardInterrupt):
                    raise
        log(name, 'no states left')
        return
    res = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    for code in todo:
        if code in res:
            continue
        one_state(ctx, code, res)
    log('done', len(res), 'regions')


if __name__ == '__main__':
    main()
