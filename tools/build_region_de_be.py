#!/usr/bin/env python3
"""Berlin (DE-BE): a self-contained offline map set with places, help points and street addresses.

  python3 tools/build_region_de_be.py fetch    # downloads the sources (about 270 MB) into derived/regions/DE-BE/source/
  python3 tools/build_region_de_be.py build    # writes the data folder derived/regions/DE-BE/data/ once it passes check
  python3 tools/build_region_de_be.py check    # validates it; exits non-zero on any failure
  python3 tools/build_region_de_be.py demo     # adds an empty library beside it, then prints the command below
  python3 server.py --data derived/regions/DE-BE/demo --no-index   # the map and the place finder, offline

Everything goes under derived/regions/DE-BE/, so no existing map set is touched. The region keeps its full ID: a bare
DE means Delaware. Plan and sources: docs/REGIONS-DE.md; what this build holds and what it lacks: docs/MAP-DE-BE.md.

This is the data half only: it runs tools/build_map.py unchanged and imports nothing from engine/ or server.py. Searching
the address index the German way (scheme de-1 below) is runtime work, offered in #79 and coordinated in #31.

Sources (all redistributable; details, dates and checksums end up in derived/regions/DE-BE/data/build.json):
  - OpenStreetMap via Geofabrik, berlin-YYMMDD-free.gpkg.zip: streets, water, land use, buildings, named places and
    points (ODbL 1.0, "© OpenStreetMap contributors").
  - Geoportal Berlin WFS (gdi.berlin.de), Datenlizenz Deutschland Zero 2.0: street addresses (adressen_rbs), hospitals,
    pharmacies, fire stations, police stations, district (Bezirk) and locality (Ortsteil) boundaries.
  Postcode areas are placed at the middle of their own addresses, so no source with an attribution duty is needed besides OSM.

The fetch step needs the network; build and check do not. Python 3.9+ standard library only.
"""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REGION = 'DE-BE'
BASE = ROOT / 'derived' / 'regions' / REGION
SOURCE = BASE / 'source'
DATA = BASE / 'data'
BBOX = (13.0883, 52.3382, 13.7605, 52.6754)     # W, S, E, N of Berlin's land area, from docs/regions-de-proposed.json
GEOFABRIK = 'https://download.geofabrik.de/europe/germany/berlin-latest-free.gpkg.zip'
WFS = 'https://gdi.berlin.de/services/wfs/'
ZERO = 'Datenlizenz Deutschland Zero 2.0 (dl-de/zero-2.0)'
PAGE = 50000

# name -> (service, layer, licence, attribution). Fetched as GeoJSON in WGS84 (EPSG:4326).
LAYERS = {
    'addresses': ('adressen_rbs', 'adressen_rbs', ZERO, 'Geoportal Berlin / Adressen Berlin (RBS)'),
    'hospitals_plan': ('krankenhaeuser', 'plankrankenhaeuser', ZERO, 'Geoportal Berlin / Krankenhäuser'),
    'hospitals_other': ('krankenhaeuser', 'weitere_krankenhaeuser', ZERO, 'Geoportal Berlin / Krankenhäuser'),
    'pharmacies': ('apotheken', 'apotheken', ZERO, 'Geoportal Berlin / Apotheken'),
    'fire_stations': ('feuerwehr', 'a_feuerwehr_standorte', ZERO, 'Geoportal Berlin / Feuerwehr'),
    'police': ('polizei', 'a_polizei_wachen', ZERO, 'Geoportal Berlin / Polizei'),
    'districts': ('alkis_bezirke', 'bezirksgrenzen', ZERO, 'Geoportal Berlin / ALKIS Bezirke'),
    'localities': ('alkis_ortsteile', 'ortsteile', ZERO, 'Geoportal Berlin / ALKIS Ortsteile'),
}
# Only the fields the build reads: the address layer has some 40 per record, which would make a 420 MB download.
FIELDS = {'addresses': 'strnam,hausnr,hausnrz,postleit,ot_name,geom'}
# Official records replace OpenStreetMap's points of these classes (one pin per facility, from the public register).
OFFICIAL = ('hospital', 'pharmacy', 'fire_station', 'police')
# Berlin's 2,000-odd street pumps (Straßenbrunnen) are mapped as water wells; the official list is not public.
# tools/build_map.py does not keep that class, so the build adds them from the same extract, the way build_map.py places
# a point: the middle of the feature's bounding box. build_map.py keeps points of any class from these three tables
# (from gis_osm_natural_free it keeps springs only).
WELL_TABLES = ('gis_osm_pois_free', 'gis_osm_pois_a_free', 'gis_osm_natural_a_free')

NORM = 'de-1'
_UMLAUTS = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'})


def normalize_de(text):
    """Scheme 'de-1', stored in the index's norm column: 'Müllerstraße' -> 'muellerstr', 'Straße des 17. Juni' -> 'str des 17 juni'.

    A search over this index has to fold the query with the same rule; the rule is recorded as meta norm = de-1."""
    text = unicodedata.normalize('NFC', text).lower().translate(_UMLAUTS)
    words = re.sub(r'[^a-z0-9 ]+', ' ', text).split()
    return ' '.join(word[:-len('strasse')] + 'str' if word.endswith('strasse') else word for word in words)


def log(*args):
    print(time.strftime('%H:%M:%S'), *args, flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 22), b''):
            digest.update(chunk)
    return digest.hexdigest()


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'lastbook-region-builder'})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.geturl(), response.read()


# ------------------------------------------------------------------ fetch ----

def fetch():
    SOURCE.mkdir(parents=True, exist_ok=True)
    fetched = {'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'files': {}}
    log('Geofabrik', GEOFABRIK)
    final, data = get(GEOFABRIK)        # 'latest' redirects to the dated file; the dated name is what gets recorded
    name = final.rsplit('/', 1)[1]
    (SOURCE / 'osm.gpkg.zip').write_bytes(data)
    with zipfile.ZipFile(SOURCE / 'osm.gpkg.zip') as archive:
        readme = archive.read('README').decode('utf-8', 'replace')
    as_of = re.search(r'data as of (\S+)', readme)
    fetched['files']['osm.gpkg.zip'] = {
        'url': final, 'name': name, 'data_as_of': as_of.group(1) if as_of else None,
        'licence': 'Open Database License 1.0 (ODbL)', 'attribution': '© OpenStreetMap contributors',
        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    for key, (service, layer, licence, attribution) in LAYERS.items():
        features, matched, stamp, start = [], None, None, 0
        while True:
            params = {'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature', 'TYPENAMES': f'{service}:{layer}',
                      'OUTPUTFORMAT': 'application/json', 'SRSNAME': 'EPSG:4326', 'COUNT': PAGE, 'STARTINDEX': start}
            if key in FIELDS:
                params['PROPERTYNAME'] = FIELDS[key]
            query = urllib.parse.urlencode(params)
            page = json.loads(get(f'{WFS}{service}?{query}')[1])
            matched = page.get('numberMatched', matched)
            stamp = stamp or page.get('timeStamp')
            features += page['features']
            start += PAGE
            if not page['features'] or (isinstance(matched, int) and start >= matched):
                break
        if isinstance(matched, int) and len(features) != matched:
            raise SystemExit(f'{key}: got {len(features)} of {matched} features; run fetch again')
        ids = [f.get('id') for f in features]
        if len(set(ids)) != len(ids):      # pages must not overlap: a shifting page order would duplicate some records and drop others
            raise SystemExit(f'{key}: {len(ids) - len(set(ids))} records came twice across pages; run fetch again')
        path = SOURCE / f'{key}.geojson'
        path.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False), encoding='utf-8')
        fetched['files'][path.name] = {
            'url': f'{WFS}{service}', 'layer': f'{service}:{layer}', 'served_at': stamp, 'features': len(features),
            'licence': licence, 'attribution': attribution, 'bytes': path.stat().st_size, 'sha256': sha256(path)}
        log(key, len(features))
    (SOURCE / 'fetched.json').write_text(json.dumps(fetched, indent=1, ensure_ascii=False), encoding='utf-8')
    log('fetched', len(fetched['files']), 'files')


# ------------------------------------------------------------------ build ----

def features(key):
    return json.loads((SOURCE / f'{key}.geojson').read_text(encoding='utf-8'))['features']


def point(geometry):
    """A point for a point, multipoint or polygon: polygons use the area-weighted centre of their largest ring."""
    kind, coords = geometry['type'], geometry['coordinates']
    if kind == 'Point':
        return coords[0], coords[1]
    if kind == 'MultiPoint':
        return coords[0][0], coords[0][1]
    rings = [polygon[0] for polygon in coords] if kind == 'MultiPolygon' else [coords[0]]

    def centre(ring):
        area = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
            cross = x0 * y1 - x1 * y0
            area += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        return abs(area), (cx / (3 * area), cy / (3 * area)) if area else ring[0]
    return max((centre(ring) for ring in rings), key=lambda found: found[0])[1]


def wkb_coords(blob, offset=0):
    """([(x, y), ...], end offset) of a 2D WKB geometry, read as tools/build_map.py reads it (wkb_parts)."""
    order = '<' if blob[offset] == 1 else '>'
    kind = struct.unpack_from(order + 'I', blob, offset + 1)[0] % 1000
    offset += 5
    if kind == 1:
        return [struct.unpack_from(order + 'dd', blob, offset)], offset + 16
    if kind in (2, 3):
        rings = 1
        if kind == 3:
            rings = struct.unpack_from(order + 'I', blob, offset)[0]
            offset += 4
        coords = []
        for _ in range(rings):
            count = struct.unpack_from(order + 'I', blob, offset)[0]
            flat = struct.unpack_from(order + '%dd' % (2 * count), blob, offset + 4)
            coords += zip(flat[0::2], flat[1::2])
            offset += 4 + 16 * count
        return coords, offset
    if kind in (4, 5, 6, 7):
        members = struct.unpack_from(order + 'I', blob, offset)[0]
        offset += 4
        coords = []
        for _ in range(members):
            part, offset = wkb_coords(blob, offset)
            coords += part
        return coords, offset
    raise ValueError('WKB geometry type %d' % kind)


def gpkg_middle(blob):
    """The middle of a GeoPackage geometry's bounding box: where tools/build_map.py puts a point (its poi rows)."""
    envelope = (blob[3] >> 1) & 7
    coords, _ = wkb_coords(blob, 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[envelope])
    xs, ys = [x for x, _ in coords], [y for _, y in coords]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def water_wells(gpkg):
    """(name, lon, lat) of every OpenStreetMap water well in the extract, from the tables build_map.py reads points from."""
    src = sqlite3.connect(f'file:{gpkg}?mode=ro', uri=True)
    wells = []
    try:
        for table in WELL_TABLES:
            for blob, name in src.execute(f"SELECT geom,name FROM {table} WHERE fclass='water_well'"):
                if blob is None:
                    continue
                try:
                    wells.append((name, *gpkg_middle(blob)))
                except (ValueError, IndexError, struct.error):     # as in build_map.py: an unreadable geometry is skipped
                    continue
    finally:
        src.close()
    return wells


def official_points():
    """(cls, name, lon, lat) of the Geoportal records that replace OpenStreetMap's points of the OFFICIAL classes."""
    for key, cls, name_of in (
            ('hospitals_plan', 'hospital', lambda p: p.get('kkh_standort') or p.get('kkh')),
            ('hospitals_other', 'hospital', lambda p: p.get('name')),
            ('pharmacies', 'pharmacy', lambda p: p.get('aponame')),
            ('fire_stations', 'fire_station', lambda p: p.get('wach_name')),
            ('police', 'police', lambda p: f"Polizei {p['langbezeichnung']}" if p.get('langbezeichnung') else None)):
        for feature in features(key):
            lon, lat = point(feature['geometry'])
            yield cls, name_of(feature['properties']), lon, lat


def in_berlin():
    """A test inside(lon, lat) for Berlin's boundary: the union of its twelve districts from the Geoportal.

    The extract and the map's box also hold a strip of Brandenburg. Brandenburg surrounds Berlin and reaches far beyond
    the 0.15° margin that check allows around the box, so a point outside this boundary is in Brandenburg."""
    rings = []
    for feature in features('districts'):
        geometry = feature['geometry']
        polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
        for ring in (ring for polygon in polygons for ring in polygon):
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            rings.append((min(xs), min(ys), max(xs), max(ys), [(p[0], p[1]) for p in ring]))

    def inside(lon, lat):
        # Even-odd over every ring: the districts do not overlap, and a hole in one counts as outside.
        crossings = False
        for west, south, east, north, ring in rings:
            if west <= lon <= east and south <= lat <= north:
                for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
                    if (y0 > lat) != (y1 > lat) and lon < (x1 - x0) * (lat - y0) / (y1 - y0) + x0:
                        crossings = not crossings
        return crossings
    return inside


def region_of(inside, lon, lat):
    return 'Berlin' if inside(lon, lat) else 'Brandenburg'


def replace_official(db, inside):
    """Puts the Geoportal's records in place of OpenStreetMap's points of the OFFICIAL classes inside Berlin.

    The Geoportal lists Berlin's facilities only, so OpenStreetMap's beyond the city boundary (a hospital in Woltersdorf,
    the pharmacies of Teltow) stay. Returns how many OpenStreetMap points each class gave up."""
    marks = ','.join('?' * len(OFFICIAL))
    replaced = [(row_id, cls) for row_id, cls, lon, lat in db.execute(
        f'SELECT id,cls,lon,lat FROM poi WHERE cls IN ({marks})', OFFICIAL) if inside(lon, lat)]
    db.executemany('DELETE FROM poi WHERE id=?', [(row_id,) for row_id, _ in replaced])
    db.executemany('INSERT INTO poi(cls,name,lon,lat) VALUES (?,?,?,?)', official_points())
    counts = {}
    for _, cls in replaced:
        counts[cls] = counts.get(cls, 0) + 1
    return counts


def build_map(fetched, geo):
    """OpenStreetMap through the existing map builder into national.sqlite; map.sqlite stays empty, as in a US state map."""
    osm = fetched['files']['osm.gpkg.zip']
    gpkg = BASE / 'work' / 'osm.gpkg'
    gpkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE / 'osm.gpkg.zip') as archive:
        member = next(n for n in archive.namelist() if n.endswith('.gpkg'))
        with archive.open(member) as src, open(gpkg, 'wb') as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
    national = geo / 'national.sqlite'
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_map.py'), str(gpkg), str(national)],
                   check=True, stdout=subprocess.DEVNULL)
    wells = water_wells(gpkg)
    db = sqlite3.connect(national)
    try:
        # build_map.py writes the Southern California metadata; this map's own source, date and box replace it.
        db.executemany('INSERT OR REPLACE INTO meta VALUES (?,?)', [
            ('source', f"OpenStreetMap contributors, via Geofabrik {osm['name']} (ODbL 1.0)"),
            ('data_as_of', osm['data_as_of'] or ''), ('bounds', ','.join(map(str, BBOX)))])
        replaced = replace_official(db, in_berlin())
        db.executemany('INSERT INTO poi(cls,name,lon,lat) VALUES (?,?,?,?)',
                       [('water_well', name, lon, lat) for name, lon, lat in wells])
        db.execute("INSERT OR REPLACE INTO meta VALUES ('help_points', ?)", (
            'hospital, pharmacy, fire_station, police inside Berlin: Geoportal Berlin (dl-de/zero-2.0), replacing '
            'OpenStreetMap; those beyond the city boundary, water_well (street pumps) and all other classes: '
            'OpenStreetMap (ODbL 1.0)',))
        db.execute("INSERT OR REPLACE INTO meta VALUES ('region', ?)", (REGION,))
        db.commit()
        db.execute('VACUUM')
    finally:
        db.close()
    empty = sqlite3.connect(geo / 'map.sqlite')
    try:
        empty.executescript('''CREATE TABLE feat(id INTEGER PRIMARY KEY, layer TEXT, cls TEXT, name TEXT, minz INTEGER, geom BLOB);
          CREATE VIRTUAL TABLE feat_idx USING rtree(id, minx, maxx, miny, maxy, minz, maxz);
          CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);
          CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);''')
        # The app reads the map's source and data date from this file's meta (server.py map_info), so it carries them too.
        meta = sqlite3.connect(f'file:{national}?mode=ro', uri=True)
        empty.executemany('INSERT INTO meta VALUES (?,?)', meta.execute(
            "SELECT key,value FROM meta WHERE key IN ('source','data_as_of','bounds','help_points','region')").fetchall())
        meta.close()
        empty.commit()
    finally:
        empty.close()
    gpkg.unlink()
    return {'osm_points_replaced_by_official': replaced, 'water_wells': len(wells)}



def house(properties):
    number = (properties.get('hausnr') or '').strip().lstrip('0')
    suffix = (properties.get('hausnrz') or '').strip().upper()
    return f'{number}{suffix}' if number else ''


def build_addresses(fetched, geo):
    path = geo / 'addresses' / f'{REGION}.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.executescript('PRAGMA page_size=8192; PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;'
                         'CREATE TABLE addr(num TEXT, street TEXT, norm TEXT, city TEXT, state TEXT, zip TEXT, lat REAL, lon REAL, district TEXT);'
                         'CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);')
        rows, skipped = [], 0
        for feature in features('addresses'):
            p = feature['properties']
            num, street = house(p), (p.get('strnam') or '').strip()
            if not num or not street or not feature.get('geometry'):
                skipped += 1
                continue
            lon, lat = feature['geometry']['coordinates'][:2]
            rows.append((num, street, normalize_de(street), 'Berlin', REGION, (p.get('postleit') or '').strip(),
                         round(lat, 6), round(lon, 6), (p.get('ot_name') or '').strip()))
        db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?,?)', rows)
        db.execute('CREATE INDEX addr_norm ON addr(norm, num)')
        db.execute('CREATE INDEX addr_zip ON addr(zip)')     # '10117 Berlin' is checked against the postcodes
        info = fetched['files']['addresses.geojson']
        db.executemany('INSERT INTO meta VALUES (?,?)', [
            ('region', REGION), ('norm', NORM), ('count', str(len(rows))),
            ('source', 'Geoportal Berlin (dl-de/zero-2.0)'), ('served', info.get('served_at') or ''),
            ('built', time.strftime('%Y-%m-%dT%H:%M:%S'))])
        db.commit()
    finally:
        db.close()
    return {'addresses': len(rows), 'address_records_without_house_number': skipped}


def build_places(fetched, geo):
    """The place finder: districts, localities, postcode areas, street names, the named official help points, and named
    OpenStreetMap places and points. Each row names the source it came from."""
    path = geo / 'places.sqlite'
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    counts = {}
    try:
        db.executescript('''CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT, lat REAL, lon REAL, rank INTEGER, source TEXT);
          CREATE VIRTUAL TABLE place_fts USING fts5(name, detail, content='place', content_rowid='id', tokenize='unicode61');''')
        insert = 'INSERT INTO place(name,kind,detail,lat,lon,rank,source) VALUES (?,?,?,?,?,?,?)'

        def add(kind, rows):
            db.executemany(insert, rows)
            counts[kind] = len(rows)
        add('district', [(f['properties']['namgem'], 'district (Bezirk)', 'Berlin', *point(f['geometry'])[::-1], 1, 'Geoportal Berlin')
                         for f in features('districts')])
        add('locality', [(f['properties']['nam'], 'locality (Ortsteil)', 'Berlin', *point(f['geometry'])[::-1], 1, 'Geoportal Berlin')
                         for f in features('localities')])
        # One entry per postcode and per street and locality, at the middle house of each: "10117" or "Oranienstraße"
        # finds the area or the street without a house number.
        streets, postcodes = {}, {}
        for f in features('addresses'):
            p = f['properties']
            street, where, code = (p.get('strnam') or '').strip(), (p.get('ot_name') or '').strip(), (p.get('postleit') or '').strip()
            if f.get('geometry'):
                if street:
                    streets.setdefault((street, where), []).append(f['geometry']['coordinates'][:2])
                if code:
                    postcodes.setdefault(code, []).append(f['geometry']['coordinates'][:2])
        rows = []
        for code, points in sorted(postcodes.items()):
            points.sort()
            lon, lat = points[len(points) // 2]
            rows.append((code, 'postcode area', 'Berlin', lat, lon, 2, 'Geoportal Berlin'))
        add('postcode', rows)
        rows = []
        for (street, where), points in streets.items():
            points.sort()
            lon, lat = points[len(points) // 2]
            rows.append((street, 'street', f'{where}, Berlin' if where else 'Berlin', lat, lon, 3, 'Geoportal Berlin'))
        add('street', rows)
        # national.sqlite holds the official help points in place of OpenStreetMap's inside Berlin (build_map), so they
        # are taken from their own records here, labelled Geoportal Berlin; every other point there is OpenStreetMap's.
        # Each OpenStreetMap row names where it is: the extract reaches a few kilometres into Brandenburg.
        official = list(official_points())
        add('official_point', [(name, cls.replace('_', ' '), 'Berlin (Geoportal)', lat, lon, 4, 'Geoportal Berlin')
                               for cls, name, lon, lat in official if name])
        official = set(official)
        inside = in_berlin()
        national = sqlite3.connect(f"file:{geo / 'national.sqlite'}?mode=ro", uri=True)
        add('osm_point', [(name, cls.replace('_', ' '), f'{region_of(inside, lon, lat)} (OpenStreetMap)', lat, lon, 4, 'OpenStreetMap')
                          for cls, name, lon, lat in national.execute(
                              "SELECT cls,name,lon,lat FROM poi WHERE name IS NOT NULL AND name<>''")
                          if (cls, name, lon, lat) not in official])
        rows = []
        for cls, name, geom in national.execute("SELECT cls,name,geom FROM feat WHERE layer='place' AND name IS NOT NULL"):
            _, _, x, y = struct.unpack_from('<iiii', geom)
            rows.append((name, cls, f'{region_of(inside, x / 1e6, y / 1e6)} (OpenStreetMap)', y / 1e6, x / 1e6, 1, 'OpenStreetMap'))
        add('osm_place', rows)
        national.close()
        db.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
        db.commit()
        db.execute('VACUUM')
    finally:
        db.close()
    return {'places': counts}


def build():
    """Builds into data.new/ beside the previous output and puts it in place of data/ only once it passes check, so a
    rebuild that fails or stops leaves the last good data/ (with its build.json) as it was."""
    fetched = json.loads((SOURCE / 'fetched.json').read_text(encoding='utf-8'))
    data, staging, previous = BASE / 'data', BASE / 'data.new', BASE / 'data.old'
    if previous.exists() and not data.exists():
        previous.rename(data)         # an earlier build stopped between the two renames at the end
    for leftover in (staging, previous):
        if leftover.exists():
            shutil.rmtree(leftover)
    geo = staging / 'derived' / 'geo'
    geo.mkdir(parents=True)
    started = time.time()
    counts = {}
    log('map (OpenStreetMap)')
    counts.update(build_map(fetched, geo))
    log('addresses')
    counts.update(build_addresses(fetched, geo))
    log('places')
    counts.update(build_places(fetched, geo))
    map_files = {f.relative_to(staging).as_posix(): f.stat().st_size for f in sorted(geo.glob('*.sqlite'))}
    (staging / 'map-set.json').write_text(json.dumps({'name': REGION, 'files': map_files, 'bytes': sum(map_files.values()),
                                                   'seconds': round(time.time() - started)}, indent=1), encoding='utf-8')
    outputs = {}
    for f in sorted(staging.rglob('*')):
        if f.is_file():
            outputs[f.relative_to(staging).as_posix()] = {'bytes': f.stat().st_size, 'sha256': sha256(f)}
    report = {'region': REGION, 'built': time.strftime('%Y-%m-%dT%H:%M:%S'), 'bbox': BBOX, 'sources': fetched,
              'counts': counts, 'outputs': outputs,
              'note': 'map-set.json lists the map files; the address index is a separate sidecar, as for US states.'}
    (staging / 'build.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    log('built in', round(time.time() - started), 's;', json.dumps(counts, ensure_ascii=False))
    failures = check(staging)
    if failures:
        raise SystemExit(f'{len(failures)} check(s) failed: {data} is unchanged; the failed build is in {staging}')
    if data.exists():
        data.rename(previous)
    try:
        staging.rename(data)
    except OSError:
        if previous.exists():
            previous.rename(data)
        raise
    if previous.exists():
        shutil.rmtree(previous)
    (BASE / 'build.json').unlink(missing_ok=True)     # where earlier versions of this builder wrote the report
    log('in place:', data)


# ------------------------------------------------------------------ check ----

SAMPLE_ADDRESSES = [   # (street, house number, postcode, locality); public buildings, checked against the source
    ('Unter den Linden', '77', '10117', 'Mitte'),                  # Hotel Adlon
    ('Platz der Republik', '1', '10557', 'Tiergarten'),            # Reichstag building
    ('Straße des 17. Juni', '135', '10623', 'Charlottenburg'),     # TU Berlin; the 17 belongs to the street name
]


def check(data=DATA):
    """The data only: nothing here imports engine/ or server.py, so this says nothing about how the app searches it.

    Returns what failed; build runs it on the new folder before putting it in place."""
    failures = []
    geo = data / 'derived' / 'geo'

    def expect(ok, what):
        print(('ok    ' if ok else 'FAIL  ') + what)
        if not ok:
            failures.append(what)
    report = json.loads((data / 'build.json').read_text(encoding='utf-8'))
    for rel, info in report['outputs'].items():
        f = data / rel
        expect(f.is_file() and f.stat().st_size == info['bytes'] and sha256(f) == info['sha256'], f'{rel}: size and SHA-256 as built')
    map_set = json.loads((data / 'map-set.json').read_text(encoding='utf-8'))
    expect(map_set['name'] == REGION, f"map-set.json name is {REGION}")
    expect(all((data / rel).stat().st_size == size for rel, size in map_set['files'].items()), 'map-set.json sizes match the files')
    for rel in [*map_set['files'], f'derived/geo/addresses/{REGION}.sqlite']:
        db = sqlite3.connect(f'file:{data / rel}?mode=ro', uri=True)
        expect(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', f'{rel}: SQLite integrity')
        db.close()
    west, south, east, north = BBOX
    nat = sqlite3.connect(f"file:{geo / 'national.sqlite'}?mode=ro", uri=True)
    roads = nat.execute("SELECT count(*) FROM feat WHERE layer='road'").fetchone()[0]
    expect(roads > 50000, f'streets drawn from OpenStreetMap: {roads:,} road features')
    for cls, low in (('hospital', 100), ('pharmacy', 600), ('fire_station', 90), ('police', 30), ('water_well', 1500)):
        n = nat.execute('SELECT count(*) FROM poi WHERE cls=?', (cls,)).fetchone()[0]
        expect(n >= low, f'help points {cls}: {n:,} (expected at least {low:,})')
    outside = nat.execute('SELECT count(*) FROM poi WHERE lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?',
                          (west - .15, east + .15, south - .15, north + .15)).fetchone()[0]
    expect(outside == 0, f'every help point within Berlin plus the 0.15° margin ({outside} outside)')
    nat.close()
    inside = in_berlin()
    beyond = [name for _, name, lon, lat in official_points() if not inside(lon, lat)]
    expect(not beyond, f'every Geoportal help point inside the city boundary ({len(beyond)} beyond it{": " + ", ".join(map(str, beyond[:3])) if beyond else ""})')
    addr = sqlite3.connect(f"file:{geo / 'addresses' / (REGION + '.sqlite')}?mode=ro", uri=True)
    n, bad_zip, outside, border = addr.execute(
        "SELECT count(*), sum(zip NOT GLOB '[0-9][0-9][0-9][0-9][0-9]'), sum(lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?),"
        " sum(zip NOT GLOB '1[0-4][0-9][0-9][0-9]') FROM addr", (west, east, south, north)).fetchone()
    expect(n > 350000, f'addresses: {n:,}')
    expect(not bad_zip, f'every address has a five-digit postcode ({bad_zip} without)')
    # A few houses on the city edge (Schmöckwitz, Rahnsdorf) officially carry a Brandenburg postcode: report, not fail.
    expect(border < 100, f'{border} addresses with a postcode outside 10xxx-14xxx (Berlin houses on the Brandenburg border)')
    expect(not outside, f'every address inside the Berlin box ({outside} outside)')
    meta = dict(addr.execute('SELECT key,value FROM meta'))
    expect(meta.get('region') == REGION and meta.get('norm') == NORM, f"index meta: region {meta.get('region')}, norm {meta.get('norm')}")
    expect(meta.get('count') == str(n), f"index meta count {meta.get('count')} matches its {n:,} rows")
    wrong = [street for street, norm in addr.execute('SELECT DISTINCT street,norm FROM addr') if normalize_de(street) != norm]
    expect(not wrong, f'every stored street key follows scheme {NORM} ({len(wrong)} do not{": " + ", ".join(wrong[:3]) if wrong else ""})')
    for street, number, postcode, locality in SAMPLE_ADDRESSES:
        found = addr.execute('SELECT zip,district FROM addr WHERE norm=? AND num=?', (normalize_de(street), number)).fetchall()
        expect(found == [(postcode, locality)], f'index has {street} {number}, {postcode} {locality} exactly once ({found})')
    addr.close()
    places = sqlite3.connect(f"file:{geo / 'places.sqlite'}?mode=ro", uri=True)
    for name, kind in (('Kreuzberg', 'locality (Ortsteil)'), ('Friedrichshain-Kreuzberg', 'district (Bezirk)'), ('10117', 'postcode area'),
                       ('Oranienstraße', 'street')):
        hit = places.execute('SELECT count(*) FROM place_fts f JOIN place p ON p.id=f.rowid WHERE place_fts MATCH ? AND p.name=? AND p.kind=?',
                             (f'"{name}"', name, kind)).fetchone()[0]
        expect(hit > 0, f'place finder has {kind} "{name}"')
    kinds = {cls.replace('_', ' ') for cls in OFFICIAL}
    rows = places.execute('SELECT name,kind,detail,source,lon,lat FROM place').fetchall()
    places.close()
    official = [row for row in rows if row[1] in kinds and inside(row[4], row[5])]
    other = sum(row[3] != 'Geoportal Berlin' for row in official)
    expect(len(official) >= 800 and not other,
           f'place finder labels its {len(official):,} official help points in Berlin Geoportal Berlin ({other} labelled otherwise)')
    # A row beyond the boundary is in Brandenburg (see in_berlin): it may stay on the map, but must not claim Berlin.
    claims = [row[0] for row in rows if not inside(row[4], row[5]) and ('Berlin' in row[2] or row[3] == 'Geoportal Berlin')]
    expect(not claims, f'place finder names Berlin only inside the city boundary ({len(claims)} rows beyond it do{": " + ", ".join(claims[:3]) if claims else ""})')
    if not failures:
        print('all checks passed (data only; German address search in the app is not checked here, see #79)')
    return failures


def demo():
    """A data folder for trying the map on its own: the app also needs a library, so this adds an empty one.

    The map files stay in data/ (what a map download would hold); demo/ links to them."""
    folder = BASE / 'demo'
    (folder / 'library-data').mkdir(parents=True, exist_ok=True)
    (folder / 'library-data' / 'catalog.json').write_text('[]\n', encoding='utf-8')
    link = folder / 'derived'
    if not link.exists():
        try:
            link.symlink_to(Path('..') / 'data' / 'derived', target_is_directory=True)
        except OSError:       # Windows without symlink rights: a copy works the same
            shutil.copytree(DATA / 'derived', link)
    print(f'python3 server.py --data {folder.relative_to(ROOT)} --no-index')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('step', choices=('fetch', 'build', 'check', 'demo'))
    step = parser.parse_args().step
    if step == 'check':
        failures = check()
        if failures:
            raise SystemExit(f'{len(failures)} check(s) failed')
    else:
        {'fetch': fetch, 'build': build, 'demo': demo}[step]()


if __name__ == '__main__':
    main()
