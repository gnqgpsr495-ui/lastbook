#!/usr/bin/env python3
"""Madeira (PT-30): a self-contained offline map set with places, help points and street addresses.

  python3 tools/build_region_pt_30.py fetch    # downloads the sources (about 1.03 GB) into derived/regions/PT-30/source/
  python3 tools/build_region_pt_30.py build    # builds derived/regions/PT-30/data.new/ and swaps it into data/ after check
  python3 tools/build_region_pt_30.py check    # validates data/; exits non-zero on any failure
  python3 tools/build_region_pt_30.py demo     # adds an empty library beside it, then prints the command below
  python3 server.py --data derived/regions/PT-30/demo --no-index   # the map, place and address search, offline

Everything goes under derived/regions/PT-30/, so no existing map set is touched. A build never rewrites a good
output: it stages into data.new/, checks the staging, and only then replaces data/, so a rebuild that fails or
stops leaves the last good data/ (with its build.json) as it was. The region keeps its full ID:
PT-30 is the ISO 3166-2:PT code, the NUTS II code and the former district of Madeira — they coincide. Plan and
sources: docs/REGIONS-PT.md; what this build holds and what it lacks: docs/MAP-PT-30.md.

Sources (all redistributable; details, dates and checksums end up in data/build.json):
  - OpenStreetMap via Geofabrik, portugal-YYMMDD-free.gpkg.zip: streets, water, land use, buildings, named places
    and points (ODbL 1.0, "© OpenStreetMap contributors"). Geofabrik publishes no Madeira subregion, so the country
    extract is downloaded once and cut to the region box here.
  - OpenAddresses pt_addresses.csv.zip: 5,911,139 street addresses for Portugal from the INE address register,
    distributed via OpenAddresses (CC BY 4.0, "Instituto Nacional de Estatística, I.P."); the 130,271 Madeira rows
    are the ones kept. Measured against the same upload in docs/REGIONS-PT.md.
  - CAOP 2025, Região Autónoma da Madeira (DGT, CAOP_RAM_2025-gpkg.zip, CC BY 4.0, "Direção-Geral do
    Território"; the register is a high-value dataset under Regulation (EU) 2023/138): the official NUTS II
    polygon that fixes the region box, plus the 11 municipios and 54 freguesias for the place finder.

The fetch step needs the network; build and check do not. Python 3.9+ standard library only.
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
import math
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGION = 'PT-30'
NORM = 'pt-1'
BASE = ROOT / 'derived' / 'regions' / REGION
SOURCE = BASE / 'source'
DATA = BASE / 'data'
GEO = DATA / 'derived' / 'geo'
# W,S,E,N of Madeira's land area: the exact WGS84 extent of the official CAOP 2025 NUTS II polygon (RAM),
# every vertex converted from EPSG:5016 (PTRA08 / UTM zone 28N) and rounded outward to 6 dp. Porto Santo's
# north tip is what moves the north edge 0.024° past the GISCO 1:3M approximation in docs/regions-pt-proposed.json.
BBOX = (-17.265938, 30.028778, -15.853671, 33.128161)
MARGIN = 0.15     # the same margin a US state box carries, per docs/REGIONS-PT.md
CUTBOX = (BBOX[0] - MARGIN, BBOX[1] - MARGIN, BBOX[2] + MARGIN, BBOX[3] + MARGIN)
GEOFABRIK = 'https://download.geofabrik.de/europe/portugal-latest-free.gpkg.zip'
ADDRESSES = 'https://data.openaddresses.io/cache/uploads/jeffdefacto/2026-02-23-921i3/pt_addresses.csv.zip'
CAOP = 'https://geo2.dgterritorio.gov.pt/caop/CAOP_RAM_2025-gpkg.zip'
ADDRESSES_TOTAL = 5911139      # rows in the full CSV, checked at fetch
ADDRESS_EXPECTED = 130271      # Madeira rows inside the box, as measured in docs/REGIONS-PT.md
FREGUESIAS_EXPECTED = 54
MUNICIPIOS_EXPECTED = 11
# Map tables the existing tools/build_map.py reads; the cut keeps only rows inside CUTBOX. Extra columns are
# the ones build_map.py selects beyond (geom, fclass, name).
MAP_TABLES = {
    'gis_osm_water_a_free': (), 'gis_osm_natural_a_free': (), 'gis_osm_protected_areas_a_free': (),
    'gis_osm_landuse_a_free': (), 'gis_osm_waterways_free': (), 'gis_osm_railways_free': (),
    'gis_osm_roads_free': ('ref',), 'gis_osm_buildings_a_free': (), 'gis_osm_places_free': ('population',),
    'gis_osm_pois_free': (), 'gis_osm_pois_a_free': (), 'gis_osm_natural_free': (),
}
# The INE register writes street names uppercase with an abbreviated leading type. pt-1 is the normalisation
# rule shared by the index and its future search path: lowercase, accents folded, and the leading street type
# spelled out so a person can type Rua, R, Rua de... or the abbreviation and land on the same key.
STREET_TYPES = {
    'R': 'rua', 'AV': 'avenida', 'TV': 'travessa', 'BC': 'beco', 'LG': 'largo', 'ESTR': 'estrada',
    'ER': 'estrada regional', 'EM': 'estrada municipal', 'CAM': 'caminho', 'CM': 'caminho municipal',
    'CS': 'canal', 'SIT': 'sitio', 'SITIO': 'sitio', 'VR': 'viela', 'IMP': 'impasse', 'ENT': 'entrada',
    'RAMP': 'rampa', 'AZ': 'azinhaga', 'BR': 'bairro', 'CC': 'centro comercial', 'LAD': 'ladeira',
    'ESCNH': 'escadinhas', 'ESC': 'escada', 'URB': 'urbanizacao', 'PCT': 'percurso', 'AL': 'alameda',
    'LEV': 'levada', 'ARRM': 'arruamento', 'Estrada': 'estrada', 'Rua': 'rua', 'Avenida': 'avenida',
    'Calçada': 'calcada', 'Travessa': 'travessa', 'Beco': 'beco', 'Largo': 'largo', 'Jardim': 'jardim',
    'Complexo': 'complexo', 'Parque': 'parque',
}
FOLD = str.maketrans({'ç': 'c', 'Ç': 'c', 'ã': 'a', 'á': 'a', 'â': 'a', 'à': 'a', 'é': 'e', 'ê': 'e',
                      'í': 'i', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ú': 'u', 'Á': 'a', 'Ã': 'a', 'É': 'e',
                      'Í': 'i', 'Ó': 'o', 'Ô': 'o', 'Õ': 'o', 'Ú': 'u', 'À': 'a', 'Â': 'a', 'Ê': 'e'})
# Name abbreviations the INE register uses in any position of a street name.
NAME_ABBREV = {'s': 'sao', 'sta': 'santa', 'sto': 'santo', 'd': 'de', 'da': 'de', 'do': 'de',
               'dr': 'doutor', 'dra': 'doutora', 'cmdt': 'comandante'}
# The street-type table folded the way queries arrive: a person types lowercase as often as not.
STREET_TYPES_FOLDED = {k.translate(FOLD).lower(): v for k, v in STREET_TYPES.items()}


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


def download(url, path):
    """Stream a large file to disk; returns the final (dated) URL."""
    request = urllib.request.Request(url, headers={'User-Agent': 'lastbook-region-builder'})
    with urllib.request.urlopen(request, timeout=300) as response, open(path, 'wb') as out:
        shutil.copyfileobj(response, out, 1 << 22)
        return response.geturl()


# --------------------------------------------------------------- the pt-1 rule ----

def normalize_pt(text):
    """pt-1: composed (NFC), lowercased, accents folded, spaces collapsed. Composing first is what
    folds the separated accents a Mac or iOS paste can carry ('Sa' + combining tilde), the way de-1
    does. The leading street type expands ('R DE SANTA MARIA', 'Rua de Santa Maria' and
    'r de santa maria' share one key); name abbreviations expand in any position, so
    'CAM S JOSE' and 'Caminho São José' share one too."""
    folded = [w.translate(FOLD).lower() for w in unicodedata.normalize('NFC', text).split()]
    if folded and folded[0] in STREET_TYPES_FOLDED:
        folded[0] = STREET_TYPES_FOLDED[folded[0]]
    return ' '.join(NAME_ABBREV.get(w, w) for w in folded)


def address_num(house):
    """The stored house label: leading zeros come off only a plain numeral ('007' becomes '7'), so
    the register's other labels stay as people read them on the door ('0E', '5 1J' — stripping
    their zero would leave a fragment a query can never reach). An all-zero label stays as written."""
    stripped = house.lstrip('0')
    return stripped if stripped.isdigit() else house


# ------------------------------------------------------------------- fetch ----

def csv_rows(path):
    """Stream rows from a zip holding one CSV, without reading it into memory."""
    with zipfile.ZipFile(path) as archive:
        member = next(n for n in archive.namelist() if n.endswith('.csv'))
        with archive.open(member) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8', newline=''))
            for row in reader:
                yield row


def csv_count(path):
    with zipfile.ZipFile(path) as archive:
        member = next(n for n in archive.namelist() if n.endswith('.csv'))
        with archive.open(member) as stream:
            reader = io.TextIOWrapper(stream, encoding='utf-8', newline='')
            return sum(1 for _ in reader) - 1


def fetch():
    SOURCE.mkdir(parents=True, exist_ok=True)
    previous = {}
    old = SOURCE / 'fetched.json'
    if old.exists():
        previous = json.loads(old.read_text(encoding='utf-8')).get('files', {})
    fetched = {'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'files': {}}

    def plan(name, url):
        """A file already on disk with the same SHA-256 as the last fetch is kept; a new one is downloaded."""
        path = SOURCE / name
        if path.exists() and name in previous and path.stat().st_size == previous[name].get('bytes') \
                and sha256(path) == previous[name].get('sha256'):
            log('keeping', name, '(unchanged since the last fetch)')
            return False
        log('downloading', name, url)
        return download(url, path)

    def save():
        """fetched.json lands after every file, so an interrupted fetch keeps what already arrived."""
        (SOURCE / 'fetched.json').write_text(json.dumps(fetched, indent=1, ensure_ascii=False), encoding='utf-8')

    final = plan('osm.gpkg.zip', GEOFABRIK)
    if final:     # a fresh download: the dated URL is what download() already followed, so no second request
        name = final.rsplit('/', 1)[1]
        with zipfile.ZipFile(SOURCE / 'osm.gpkg.zip') as archive:
            readme = archive.read('README').decode('utf-8', 'replace')
        as_of = re.search(r'data as of (\S+)', readme)
        fetched['files']['osm.gpkg.zip'] = {
            'url': final, 'name': name, 'data_as_of': as_of.group(1) if as_of else None,
            'licence': 'Open Database License 1.0 (ODbL)', 'attribution': '© OpenStreetMap contributors',
            'bytes': (SOURCE / 'osm.gpkg.zip').stat().st_size, 'sha256': sha256(SOURCE / 'osm.gpkg.zip')}
    else:
        fetched['files']['osm.gpkg.zip'] = previous['osm.gpkg.zip']
    save()
    final = plan('pt_addresses.csv.zip', ADDRESSES)
    if final:
        rows = csv_count(SOURCE / 'pt_addresses.csv.zip')
        if rows != ADDRESSES_TOTAL:
            raise SystemExit(f'addresses: got {rows:,} rows, expected {ADDRESSES_TOTAL:,}; the upload changed — re-measure before building')
        fetched['files']['pt_addresses.csv.zip'] = {
            'url': ADDRESSES, 'upload': '2026-02-23', 'rows_total': rows,
            'licence': 'CC BY 4.0', 'attribution': 'Instituto Nacional de Estatística, I.P., via OpenAddresses',
            'bytes': (SOURCE / 'pt_addresses.csv.zip').stat().st_size, 'sha256': sha256(SOURCE / 'pt_addresses.csv.zip')}
    else:
        fetched['files']['pt_addresses.csv.zip'] = previous['pt_addresses.csv.zip']
    save()
    final = plan('caop_ram.zip', CAOP)
    if final:
        fetched['files']['caop_ram.zip'] = {
            'url': CAOP, 'version': 'CAOP2025', 'data_as_of': '2026-02-02',
            'licence': 'CC BY 4.0', 'attribution': 'Direção-Geral do Território',
            'note': 'high-value dataset under Regulation (EU) 2023/138',
            'bytes': (SOURCE / 'caop_ram.zip').stat().st_size, 'sha256': sha256(SOURCE / 'caop_ram.zip')}
    else:
        fetched['files']['caop_ram.zip'] = previous['caop_ram.zip']
    save()
    log('fetched', len(fetched['files']), 'files')


# ------------------------------------------------------------------ helpers ----

def wkb_envelope(blob):
    """The min/max of a Geofabrik geometry: its GPKG header envelope when present, else the WKB itself.
    Envelope codes: 1 = minx,maxx,miny,maxy; 2 = that plus M bounds; 3 = Z bounds; 4 = Z and M bounds."""
    flags = blob[3]
    env = (flags >> 1) & 7
    if env:
        vals = struct.unpack_from('<%dd' % {1: 4, 2: 6, 3: 6, 4: 10}[env], blob, 8)[:4]
        return min(vals[0], vals[1]), max(vals[0], vals[1]), min(vals[2], vals[3]), max(vals[2], vals[3])
    bo = '<' if blob[8] == 1 else '>'     # no envelope: the WKB's own byte-order byte starts at 8
    off = 8
    box = [math.inf, -math.inf, math.inf, -math.inf]

    def ring(o):
        n = struct.unpack_from(bo + 'I', blob, o)[0]
        o += 4
        for _ in range(n):
            x, y = struct.unpack_from(bo + 'dd', blob, o)
            o += 16
            box[0] = min(box[0], x); box[1] = max(box[1], x)
            box[2] = min(box[2], y); box[3] = max(box[3], y)
        return o

    def walk(o):
        t = struct.unpack_from(bo + 'I', blob, o + 1)[0] % 1000
        o += 5
        if t == 1:
            x, y = struct.unpack_from(bo + 'dd', blob, o)
            box[0] = min(box[0], x); box[1] = max(box[1], x)
            box[2] = min(box[2], y); box[3] = max(box[3], y)
            return o + 16
        if t == 2 or t == 3:
            n = struct.unpack_from(bo + 'I', blob, o)[0]
            o += 4
            for _ in range(n):
                o = ring(o)
            return o
        if t in (4, 5, 6, 7):
            n = struct.unpack_from(bo + 'I', blob, o)[0]
            o += 4
            for _ in range(n):
                o = walk(o)
            return o
        raise ValueError('geometry type %d' % t)
    walk(off)
    return box[0], box[1], box[2], box[3]


def inside(box, west, south, east, north):
    return not (box[1] < west or box[0] > east or box[3] < south or box[2] > north)


def utm28n_to_wgs84(x, y):
    """Inverse of UTM zone 28N on GRS80 (EPSG:5016), the CAOP RAM projection; standard Krüger series,
    about 1 mm at this scale. Verified against pyproj when this tool was written."""
    a = 6378137.0
    f = 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0 = 0.9996
    lon0 = math.radians(-15.0)
    x -= 500000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) \
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu) \
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    c1 = ep2 * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(phi1)
    return math.degrees(lon), math.degrees(lat)


def open_caop():
    gpkg = SOURCE / 'caop_ram.gpkg'
    if not gpkg.exists():
        with zipfile.ZipFile(SOURCE / 'caop_ram.zip') as archive:
            member = next(n for n in archive.namelist() if n.endswith('.gpkg'))
            with archive.open(member) as src, open(gpkg, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1 << 22)
    return sqlite3.connect(f'file:{gpkg}?mode=ro', uri=True)


def caop_ring_points(blob):
    """The largest ring (by true polygon area) of each polygon of a CAOP geometry blob, as (area,
    coords) with coords in EPSG:5016 metres. CAOP geometries are Multipolygon/Polygon."""
    flags = blob[3]
    off = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 80}[(flags >> 1) & 7]
    bo = '<' if blob[off] == 1 else '>'     # the WKB's own byte-order byte, after the envelope
    polys = []

    def ring(o):
        n = struct.unpack_from(bo + 'I', blob, o)[0]
        o += 4
        coords = list(struct.unpack_from(bo + '%dd' % (2 * n), blob, o))
        return o + 16 * n, coords

    def shoelace(coords):
        xs, ys = coords[0::2], coords[1::2]
        a = 0.0
        for j in range(len(xs) - 1):
            a += xs[j] * ys[j + 1] - xs[j + 1] * ys[j]
        return abs(a) / 2

    def walk(o):
        t = struct.unpack_from(bo + 'I', blob, o + 1)[0] % 1000
        o += 5
        if t == 3:
            nr = struct.unpack_from(bo + 'I', blob, o)[0]
            o += 4
            best = None
            for _ in range(nr):
                o, coords = ring(o)
                a = shoelace(coords)
                if best is None or a > best[0]:
                    best = (a, coords)
            polys.append(best)
            return o
        if t in (4, 5, 6, 7):
            n = struct.unpack_from(bo + 'I', blob, o)[0]
            o += 4
            for _ in range(n):
                o = walk(o)
            return o
        raise ValueError('geometry type %d' % t)
    walk(off)
    return polys


PARTICLES = {'da', 'das', 'de', 'do', 'dos', 'e'}


def _cap(word):
    """Upper the first alphabetic character, lower the rest: '(SÉ)' -> '(Sé)', keeping accents."""
    out, seen = [], False
    for ch in word:
        if ch.isalpha():
            out.append(ch.upper() if not seen else ch.lower())
            seen = True
        else:
            out.append(ch)
    return ''.join(out)


def pt_title(text):
    """Portuguese title case: particles stay lowercase unless they lead ('Achadas da Cruz', 'São Pedro')."""
    return ' '.join(_cap(w) if i == 0 or w.lower() not in PARTICLES else w.lower()
                    for i, w in enumerate(text.split()))


def caop_centroid(blob, anchor=None):
    """Centroid of the ring that should carry the place-finder label, in WGS84 (lon, lat): the ring
    nearest the anchor when one is given (a freguesia's parent município), else the largest ring by
    true area. The choice matters where a freguesia spans islands — Funchal (Sé) holds downtown Funchal
    plus the Selvagens, which are larger in land area and carry more coastline vertices than the
    downtown ring they belong with. The ring is closed (first point equals last), so consecutive pairs
    cover the whole polygon."""
    rings = caop_ring_points(blob)

    def centroid_of(coords):
        xs, ys = coords[0::2], coords[1::2]
        cx = cy = a = 0.0
        for j in range(len(xs) - 1):
            cross = xs[j] * ys[j + 1] - xs[j + 1] * ys[j]
            cx += (xs[j] + xs[j + 1]) * cross
            cy += (ys[j] + ys[j + 1]) * cross
            a += cross
        if not a:
            return utm28n_to_wgs84(sum(xs) / len(xs), sum(ys) / len(ys))
        return utm28n_to_wgs84(cx / (3 * a), cy / (3 * a))

    if anchor is None:
        chosen = max(rings, key=lambda p: p[0])
    else:
        chosen = min(rings, key=lambda p: (centroid_of(p[1])[0] - anchor[0]) ** 2
                     + (centroid_of(p[1])[1] - anchor[1]) ** 2)
    return centroid_of(chosen[1])


# -------------------------------------------------------------------- build ----

def cut_map(fetched):
    """Copy the Geofabrik country tables' rows inside the region box into work/cut.gpkg; tools/build_map.py
    then runs on it unchanged. The envelope each row carries in its GPKG header decides the cut."""
    osm = fetched['files']['osm.gpkg.zip']
    cut = BASE / 'work' / 'cut.gpkg'
    cut.parent.mkdir(parents=True, exist_ok=True)
    if cut.exists():
        cut.unlink()
    log('extracting the Geofabrik archive')
    gpkg = BASE / 'work' / 'portugal.gpkg'
    with zipfile.ZipFile(SOURCE / 'osm.gpkg.zip') as archive:
        member = next(n for n in archive.namelist() if n.endswith('.gpkg'))
        if not (gpkg.exists() and gpkg.stat().st_size == archive.getinfo(member).file_size):
            with archive.open(member) as src, open(gpkg, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1 << 22)
    west, south, east, north = CUTBOX
    src = sqlite3.connect(f'file:{gpkg}?mode=ro', uri=True)
    dst = sqlite3.connect(cut)
    kept = {}
    try:
        dst.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;')
        source_tables = {row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, extra in MAP_TABLES.items():
            cols = ['geom', 'fclass', 'name'] + list(extra)
            create = ','.join(cols)
            dst.execute(f'CREATE TABLE {table} ({create})')
            if table not in source_tables:
                kept[table] = {'rows_in_extract': 0, 'kept_in_box': 0}
                log(table, 'absent from this extract')
                continue
            present = {c[1] for c in src.execute(f'PRAGMA table_info({table})')}
            # a Geofabrik file may drop a column its other files carry (the Portugal extract's protected areas
            # have no name): the cut table keeps the shape build_map.py expects, with NULL where the source has none
            sel = ','.join(c if c in present else f'NULL AS {c}' for c in cols)
            insert = f'INSERT INTO {table} VALUES ({",".join("?" * len(cols))})'
            total = kept_n = 0
            batch = []
            for row in src.execute(f'SELECT {sel} FROM {table}'):
                total += 1
                if row[0] is None:
                    continue
                box = wkb_envelope(row[0])
                if inside(box, west, south, east, north):
                    kept_n += 1
                    batch.append(row)
                    if len(batch) >= 50000:     # kept rows go down in blocks, so a big region never pools in memory
                        dst.executemany(insert, batch)
                        batch = []
            dst.executemany(insert, batch)
            dst.commit()
            kept[table] = {'rows_in_extract': total, 'kept_in_box': kept_n}
            log(table, f'{kept_n:,} of {total:,} rows')
    finally:
        src.close()
        dst.close()
    gpkg.unlink()
    return {'cut': kept}


def build_map(fetched, geo):
    """The region map through the existing tools/build_map.py; meta is corrected to what this build holds."""
    national = geo / 'national.sqlite'
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_map.py'), str(BASE / 'work' / 'cut.gpkg'), str(national)],
                   check=True, stdout=subprocess.DEVNULL)
    osm = fetched['files']['osm.gpkg.zip']
    db = sqlite3.connect(national)
    try:
        db.executemany('INSERT OR REPLACE INTO meta VALUES (?,?)', [
            ('source', f"OpenStreetMap contributors, via Geofabrik {osm['name']} (ODbL 1.0), cut to the region box"),
            ('data_as_of', osm['data_as_of'] or ''),
            ('bounds', ','.join(map(str, BBOX))),
            ('region', REGION),
            ('help_points', 'all classes: OpenStreetMap (ODbL 1.0)'),
        ])
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
        meta = sqlite3.connect(f'file:{national}?mode=ro', uri=True)
        empty.executemany('INSERT INTO meta VALUES (?,?)', meta.execute(
            "SELECT key,value FROM meta WHERE key IN ('source','data_as_of','bounds','help_points','region')").fetchall())
        meta.close()
        empty.commit()
    finally:
        empty.close()
    db = sqlite3.connect(f'file:{national}?mode=ro', uri=True)
    try:
        roads = db.execute("SELECT count(*) FROM feat WHERE layer='road'").fetchone()[0]
        pois = dict(db.execute('SELECT cls,count(*) FROM poi GROUP BY cls').fetchall())
    finally:
        db.close()
    return {'roads': roads, 'pois': pois}


def build_addresses(fetched, geo):
    """The address sidecar from the INE register rows inside the region box. Rows whose house field does not
    start with a number (rural doors registered without one, or with a word instead) stay out of the index and
    are counted; their streets still appear in the place finder."""
    path = geo / 'addresses' / f'{REGION}.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    counts = {'kept': 0, 'skipped_without_number': 0, 'skipped_without_point': 0, 'total_in_box': 0}
    west, south, east, north = BBOX
    try:
        db.executescript('PRAGMA page_size=8192; PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;'
                         'CREATE TABLE addr(num TEXT, street TEXT, norm TEXT, city TEXT, state TEXT, zip TEXT, lat REAL, lon REAL, district TEXT);'
                         'CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);')
        rows = []
        for row in csv_rows(SOURCE / 'pt_addresses.csv.zip'):
            try:
                lon, lat = float(row['lon']), float(row['lat'])
            except ValueError:
                counts['skipped_without_point'] += 1
                continue
            if not (west <= lon <= east and south <= lat <= north):
                continue
            counts['total_in_box'] += 1
            street = (row['street'] or '').strip()
            house = (row['house'] or '').strip()
            if not house or not street or not house[0].isdigit():
                counts['skipped_without_number'] += 1
                continue
            counts['kept'] += 1
            rows.append((address_num(house), street, normalize_pt(street), (row['city'] or '').strip(),
                         REGION, (row['postcode'] or '').replace('-', ''), round(lat, 6), round(lon, 6), ''))
        db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?,?)', rows)
        db.execute('CREATE INDEX addr_norm ON addr(norm, num)')
        db.execute('CREATE INDEX addr_zip ON addr(zip)')
        info = fetched['files']['pt_addresses.csv.zip']
        db.executemany('INSERT INTO meta VALUES (?,?)', [
            ('region', REGION), ('norm', NORM), ('count', str(counts['kept'])),
            ('source', 'Instituto Nacional de Estatística, I.P., via OpenAddresses (CC BY 4.0)'),
            ('served', info.get('upload') or ''), ('built', time.strftime('%Y-%m-%dT%H:%M:%S')),
            ('postcodes', 'PT postcodes NNNN-NNN; stored without the hyphen'),
        ])
        db.commit()
    finally:
        db.close()
    if counts['total_in_box'] != ADDRESS_EXPECTED:
        raise SystemExit(f'addresses: {counts["total_in_box"]:,} inside the box, expected {ADDRESS_EXPECTED:,} — '
                         'the data moved; re-measure')
    return counts


def build_places(fetched, geo):
    """The place finder: municipios and freguesias from the CAOP, postcode areas and streets from the addresses,
    and named OpenStreetMap places and points."""
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

        caop = open_caop()
        muni = []
        anchors = {}
        for (name, geom) in caop.execute('SELECT municipio, geom FROM ram_municipios'):
            lon, lat = caop_centroid(geom)
            anchors[name] = (lon, lat)
            muni.append((pt_title(name), 'município', 'Madeira', lat, lon, 1, 'Direção-Geral do Território (CAOP 2025)'))
        add('municipio', muni)
        freg = []
        for (name, city, parent, geom) in caop.execute('SELECT freguesia, designacao_simplificada, municipio, geom FROM ram_freguesias'):
            # a freguesia that spans islands (Funchal (Sé) holds the Selvagens) gets the ring nearest its
            # município's centroid, so the label lands where the settlement is
            lon, lat = caop_centroid(geom, anchor=anchors.get(parent))
            label = (city or name or '').strip()
            freg.append((pt_title(label), 'freguesia', 'Madeira', lat, lon, 2, 'Direção-Geral do Território (CAOP 2025)'))
        add('freguesia', freg)
        caop.close()
        # One entry per postcode prefix (the CP4 area people search) and per street, at the middle point of
        # each: '9050' or 'R FERNÃO ORNELAS' finds the area or the street without a house number.
        streets, postcodes = {}, {}
        for row in csv_rows(SOURCE / 'pt_addresses.csv.zip'):
            try:
                lon, lat = float(row['lon']), float(row['lat'])
            except ValueError:
                continue
            if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
                continue
            code = (row['postcode'] or '').replace('-', '')[:4]
            if code:
                postcodes.setdefault(code, []).append((lon, lat))
            street = (row['street'] or '').strip()
            if street:
                streets.setdefault((street, (row['city'] or '').strip()), []).append((lon, lat))
        rows = []
        for code, points in sorted(postcodes.items()):
            points.sort()
            lon, lat = points[len(points) // 2]
            rows.append((code, 'postcode area', 'Madeira', lat, lon, 2, 'Instituto Nacional de Estatística, I.P.'))
        add('postcode', rows)
        rows = []
        for (street, where), points in sorted(streets.items()):
            points.sort()
            lon, lat = points[len(points) // 2]
            rows.append((street, 'street', f'{where}, Madeira' if where else 'Madeira', lat, lon, 3,
                         'Instituto Nacional de Estatística, I.P.'))
        add('street', rows)
        national = sqlite3.connect(f"file:{geo / 'national.sqlite'}?mode=ro", uri=True)
        add('osm_point', [(name, cls.replace('_', ' '), 'Madeira (OpenStreetMap)', lat, lon, 4, 'OpenStreetMap')
                          for cls, name, lon, lat in national.execute("SELECT cls,name,lon,lat FROM poi WHERE name IS NOT NULL AND name<>''")])
        rows = []
        for cls, name, geom in national.execute("SELECT cls,name,geom FROM feat WHERE layer='place' AND name IS NOT NULL"):
            _, _, x, y = struct.unpack_from('<iiii', geom)
            rows.append((name, cls, 'Madeira (OpenStreetMap)', y / 1e6, x / 1e6, 1, 'OpenStreetMap'))
        add('osm_place', rows)
        national.close()
        db.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
        db.commit()
        db.execute('VACUUM')
    finally:
        db.close()
    if counts['municipio'] != MUNICIPIOS_EXPECTED or counts['freguesia'] != FREGUESIAS_EXPECTED:
        raise SystemExit(f"places: {counts['municipio']} municipios / {counts['freguesia']} freguesias, expected "
                         f'{MUNICIPIOS_EXPECTED}/{FREGUESIAS_EXPECTED}')
    return {'places': counts}


def build():
    """Builds into data.new/ beside the previous output and puts it in place of data/ only once it passes
    check, so a rebuild that fails or stops leaves the last good data/ (with its build.json) as it was."""
    if not (SOURCE / 'fetched.json').exists():
        raise SystemExit(f'no fetched.json in {SOURCE}; run the fetch step first')
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
    log('map cut (OpenStreetMap to the region box)')
    counts.update(cut_map(fetched))
    log('map (tools/build_map.py)')
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
              'note': 'map-set.json lists the map files; the address index is a separate sidecar, as for US states. '
                      'The region box is the official CAOP 2025 NUTS II extent (CC BY 4.0, Direção-Geral do Território).'}
    (staging / 'build.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    log('built in', round(time.time() - started), 's;', json.dumps({k: v for k, v in counts.items() if k != 'cut'}, ensure_ascii=False))
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


# ------------------------------------------------------------------- check ----

# Sample addresses stay empty until a runtime path can search a pt-1 index (see #31); the checked fixtures
# live in docs/MAP-PT-30.md, each a register row sitting on the OSM road of the same name.
SAMPLE_ADDRESSES = []


def check(root=None):
    """The built data folder, wherever it is (staging or in place): file hashes as built, SQLite integrity,
    the counts the sources fix, and the place finder. Returns the list of failed checks; each result prints."""
    root = root if root is not None else DATA
    geo = root / 'derived' / 'geo'
    failures = []

    def expect(ok, what):
        print(('ok    ' if ok else 'FAIL  ') + what)
        if not ok:
            failures.append(what)
    report_path = root / 'build.json'
    if not report_path.exists() and root == BASE / 'data':
        # only the live map can fall back: a surviving output from a previous builder keeps its report
        # beside data/, not inside it, until a successful rebuild replaces it. A staging folder without
        # its own report has nothing to read — validating it against the live map's report would check
        # the wrong files against the wrong hashes.
        report_path = BASE / 'build.json'
    if not report_path.exists():
        raise SystemExit(f'no build.json in {root}; run the build step first')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    for rel, info in report['outputs'].items():
        f = root / rel
        expect(f.is_file() and f.stat().st_size == info['bytes'] and sha256(f) == info['sha256'], f'{rel}: size and SHA-256 as built')
    map_set = json.loads((root / 'map-set.json').read_text(encoding='utf-8'))
    expect(map_set['name'] == REGION, f"map-set.json name is {REGION}")
    expect(all((root / rel).stat().st_size == size for rel, size in map_set['files'].items()), 'map-set.json sizes match the files')
    for rel in [*map_set['files'], f'derived/geo/addresses/{REGION}.sqlite']:
        db = sqlite3.connect(f'file:{root / rel}?mode=ro', uri=True)
        expect(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', f'{rel}: SQLite integrity')
        db.close()
    west, south, east, north = BBOX
    nat = sqlite3.connect(f"file:{geo / 'national.sqlite'}?mode=ro", uri=True)
    roads = nat.execute("SELECT count(*) FROM feat WHERE layer='road'").fetchone()[0]
    expect(roads > 5000, f'streets drawn from OpenStreetMap: {roads:,} road features')
    for cls, low in (('hospital', 1), ('pharmacy', 20), ('fire_station', 2), ('police', 2)):
        n = nat.execute('SELECT count(*) FROM poi WHERE cls=?', (cls,)).fetchone()[0]
        expect(n >= low, f'help points {cls}: {n:,} (expected at least {low:,})')
    outside = nat.execute('SELECT count(*) FROM poi WHERE lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?',
                          (west - MARGIN, east + MARGIN, south - MARGIN, north + MARGIN)).fetchone()[0]
    expect(outside == 0, f'every help point within PT-30 plus the 0.15° margin ({outside} outside)')
    nat.close()
    addr = sqlite3.connect(f"file:{geo / 'addresses' / (REGION + '.sqlite')}?mode=ro", uri=True)
    n, bad_zip, outside, no_norm = addr.execute(
        "SELECT count(*), sum(CAST(substr(zip,1,4) AS INTEGER) NOT BETWEEN 9000 AND 9400),"
        " sum(lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?),"
        " sum(norm IS NULL OR norm='') FROM addr", (west, east, south, north)).fetchone()
    expect(n + report['counts']['skipped_without_number'] == ADDRESS_EXPECTED,
           f'addresses in the box: {n:,} indexed + {report["counts"]["skipped_without_number"]:,} without a number '
           f'= the {ADDRESS_EXPECTED:,} measured in docs/REGIONS-PT.md')
    expect(n == report['counts']['kept'], f'sidecar rows equal the build report ({n:,})')
    expect(not bad_zip, f'every address has a Madeira postcode 9000-9400 ({bad_zip} without)')
    expect(not outside, f'every address inside the official CAOP box ({outside} outside)')
    expect(not no_norm, f'every address carries its pt-1 key ({no_norm} without)')
    # the pt-1 key is the folded, expanded spelling of the source text: check a sample row by row
    mismatch = sum(1 for street, norm in addr.execute('SELECT street, norm FROM addr LIMIT 500') if norm != normalize_pt(street))
    expect(mismatch == 0, f'pt-1 keys match normalize_pt on a 500-row sample ({mismatch} differ)')
    avenida = addr.execute("SELECT count(*) FROM addr WHERE norm LIKE 'avenida arriaga%'").fetchone()[0]
    expect(avenida > 0, f'the abbreviated street type expands in the pt-1 key ({avenida} rows on Avenida Arriaga)')
    # the house label is the register's own: a leading-zero strip that ate a letter ('0E' -> 'E') would leave
    # a fragment no query reaches, and a plain numeral keeps no leading zero ('007' is stored as '7')
    fragments, padded = addr.execute(
        "SELECT sum(num NOT GLOB '[0-9]*'),"
        " sum(num LIKE '0%' AND num GLOB '*[1-9]*' AND num NOT GLOB '*[^0-9]*') FROM addr").fetchone()
    expect(not fragments, f'every house label keeps the register spelling ({fragments} reduced to a fragment)')
    expect(not padded, f'a plain numeral label has its leading zeros off ({padded} still padded)')
    addr.close()
    places = sqlite3.connect(f"file:{geo / 'places.sqlite'}?mode=ro", uri=True)
    for name, kind in (('Funchal', 'município'), ('Porto Santo', 'município'), ('Funchal (Sé)', 'freguesia'),
                       ('Câmara de Lobos', 'freguesia'), ('9000', 'postcode area')):
        hit = places.execute('SELECT count(*) FROM place_fts f JOIN place p ON p.id=f.rowid WHERE place_fts MATCH ? AND p.name=? AND p.kind=?',
                             (f'"{name}"', name, kind)).fetchone()[0]
        expect(hit > 0, f'place finder has {kind} "{name}"')
    places.close()
    if SAMPLE_ADDRESSES:
        sys.path.insert(0, str(ROOT))
        from engine.address_search import find_addresses
        for query, street, number in SAMPLE_ADDRESSES:
            found = find_addresses(query, geo)
            expect(bool(found) and found[0]['name'] == f'{street} {number}', f'address search "{query}" -> {found[0]["name"] if found else "nothing"}')
        expect(find_addresses('Rua Fernão Ornelas 99999', geo) == [], 'an unknown house number returns nothing, never a guess')
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


def check_cli():
    failures = check()
    if failures:
        raise SystemExit(f'{len(failures)} check(s) failed')
    print('all checks passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('step', choices=('fetch', 'build', 'check', 'demo'))
    step = parser.parse_args().step
    {'fetch': fetch, 'build': build, 'check': check_cli, 'demo': demo}[step]()


if __name__ == '__main__':
    main()
