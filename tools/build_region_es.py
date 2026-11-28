#!/usr/bin/env python3
"""Build regional and nationwide Spain map ZIPs and an archive catalog.

  python3 tools/build_region_es.py fetch
  python3 tools/build_region_es.py build

Only fetch uses the network. Outputs stay in derived/regions/spain/.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import struct
import sys
import tempfile
import urllib.request
import zipfile
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.setup import install  # noqa: E402
from tools import build_map  # noqa: E402

OUT = ROOT / 'derived' / 'regions' / 'spain'
SOURCE = OUT / 'source'
# Geofabrik retains the first-of-month snapshots longer than daily extracts.
DATE = '2026-11-01'
GEOFABRIK = 'https://download.geofabrik.de'
OSM = 'OpenStreetMap'
CREDIT = '© OpenStreetMap contributors (ODbL 1.0) · Extents: Obra derivada de BDLJE CC-BY 4.0 ign.es · Natural Earth'
CONTENTS = 'Streets, buildings, water, named places and help points'
GEO = Path('derived/geo')
PLACE_SCHEMA = """CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT, lat REAL, lon REAL, rank INTEGER, source TEXT);
  CREATE VIRTUAL TABLE place_fts USING fts5(name, detail, content='place', content_rowid='id', tokenize='unicode61');"""

# Official extents from IGN's INSPIRE administrative units, as measured in Lastbook PR #82.
# Geofabrik extracts may also include a strip of adjacent coverage.
REGIONS = {
    'ES-AN': ('Andalucía', 'europe/spain/andalucia', (-7.5230, 35.9376, -1.6301, 38.7291),
              '5311e57efde1629bb800b6964c3e0e44b4a06bf1fb9b250402427ec6fe5b7926'),
    'ES-AR': ('Aragón', 'europe/spain/aragon', (-2.1737, 39.8468, 0.7713, 42.9244),
              '6021dc7b959f47f1eb99acab1a609d51c047b63f6163c24e3c9b5654a566588b'),
    'ES-AS': ('Asturias', 'europe/spain/asturias', (-7.1825, 42.8825, -4.5105, 43.6665),
              '761304a3c7a9786766cffdc58f5ed4b7733a67a37172dc46b439ccdb954dffde'),
    'ES-IB': ('Illes Balears', 'europe/spain/islas-baleares', (1.1572, 38.6404, 4.3278, 40.0946),
              'a845d80a98f017d0012719976d0e8d73488be394f23cf5b15f153a6431a3e26b'),
    'ES-CN': ('Canarias', 'africa/canary-islands', (-18.1612, 27.6377, -13.3350, 29.4165),
              '0e4f76a412df560aab73c002f9a5c6987cf9b3f66c3672904a2ce80d13a3829b'),
    'ES-CB': ('Cantabria', 'europe/spain/cantabria', (-4.8518, 42.7580, -3.1496, 43.5137),
              'cc2ea11dde4f21ee77570a2d495d9b20733056a507d352c30cbe49f5cbbcd6ee'),
    'ES-CL': ('Castilla y León', 'europe/spain/castilla-y-leon', (-7.0771, 40.0819, -1.7754, 43.2382),
              'c9ff844623938c353afc8e892711b5fb0ece807f3d4fa1f32aaba7834afd2369'),
    'ES-CM': ('Castilla-La Mancha', 'europe/spain/castilla-la-mancha', (-5.4062, 38.0218, -0.9158, 41.3276),
              'c76487395e5437d40863369681b77f05cad2e49c6ea109a76a7b0cd93abbd04b'),
    'ES-CT': ('Cataluña / Catalunya', 'europe/spain/cataluna', (0.1591, 40.5230, 3.3326, 42.8614),
              '730571858f2e307549e4e292078d755117c147fa248b2bccb963b4208aa6900e'),
    'ES-VC': ('Comunitat Valenciana', 'europe/spain/valencia', (-1.5288, 37.8438, 0.6903, 40.7886),
              '613b5c3fc912b477d0ae5627bc9d71bf7a07442ce43672c33ddbe2ba7758c5f8'),
    'ES-EX': ('Extremadura', 'europe/spain/extremadura', (-7.5413, 37.9410, -4.6476, 40.4867),
              '2ef28de30950407afc3e5dcd4557c1c6794e90da86c5aa211ec9473f83ab76c4'),
    'ES-GA': ('Galicia', 'europe/spain/galicia', (-9.3015, 41.8072, -6.7340, 43.7924),
              'b7bf9c35e0a18d54a73c691f4f228eed14c6365a644f5291e22ca74db3293c0f'),
    'ES-MD': ('Comunidad de Madrid', 'europe/spain/madrid', (-4.5791, 39.8847, -3.0530, 41.1658),
              '77ea8c5c49711e51fb32a4eb7824e3a1ceec6c5d3e0b8d28211322baed95d87e'),
    'ES-MC': ('Región de Murcia', 'europe/spain/murcia', (-2.3442, 37.3738, -0.6480, 38.7551),
              '3068855d29ffe2fb0e34365353d5d8459ce6d6b996500cc14d7cb23fbca4573c'),
    'ES-NC': ('Navarra', 'europe/spain/navarra', (-2.5001, 41.9099, -0.7241, 43.3148),
              'a5d9173bf321ae3e4244c3e2b39eff5f72a107debc54e41ce0f7ad0f6b6be3a5'),
    'ES-PV': ('País Vasco / Euskadi', 'europe/spain/pais-vasco', (-3.4503, 42.4724, -1.7293, 43.4572),
              'd4d02514a6425cafcd219d6fcbe9ab145b16bc17e1d8b0979e1e703c2ee50c1a'),
    'ES-RI': ('La Rioja', 'europe/spain/la-rioja', (-3.1343, 41.9190, -1.6787, 42.6443),
              '4dce37f27c550df8fa9a81afb26c7f7d5d0c8e034ee37862544fc478e3f47b25'),
    'ES-CE': ('Ceuta', 'europe/spain/ceuta', (-5.3821, 35.8707, -5.2783, 35.9180),
              'd6fc1d46b6ea1b5da37112cc2ca0693086d19d9ecbce330414fc0bcd7c7d3d19'),
    'ES-ML': ('Melilla', 'europe/spain/melilla', (-2.9703, 35.2655, -2.9232, 35.3203),
              'a81325f16e3ce46f34a4ba45fd62c9ef419699d15875813d08aa642ac783be55'),
}


def source_url(region_path):
    snapshot = DATE[2:].replace('-', '')
    return f'{GEOFABRIK}/{region_path}-{snapshot}-free.gpkg.zip'


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def fetch(region_path, expected):
    url = source_url(region_path)
    source = SOURCE / url.rsplit('/', 1)[-1]
    if source.is_file() and sha256(source) == expected:
        return
    print(f'Fetching {url}', flush=True)
    with tempfile.TemporaryDirectory(dir=SOURCE) as work:
        staged = Path(work) / source.name
        with urllib.request.urlopen(url, timeout=90) as response, staged.open('wb') as f:
            shutil.copyfileobj(response, f, 1024 * 1024)
        if sha256(staged) != expected:
            raise ValueError(f'{source.name} does not match the pinned SHA-256.')
        staged.replace(source)


def build_places(national, dest, title):
    with closing(sqlite3.connect(dest)) as db, db:
        db.executescript(PLACE_SCHEMA)
        add = 'INSERT INTO place(name,kind,detail,lat,lon,rank,source) VALUES (?,?,?,?,?,?,?)'
        for cls, name, geom in national.execute("SELECT cls,name,geom FROM feat WHERE layer='place' AND name<>''"):
            _, _, x, y = struct.unpack_from('<iiii', geom)
            db.execute(add, (name, cls.replace('_', ' '), title, y / build_map.Q, x / build_map.Q, 1, OSM))
        for cls, name, lon, lat in national.execute("SELECT cls,name,lon,lat FROM poi WHERE name<>''"):
            db.execute(add, (name, cls.replace('_', ' '), title, lat, lon, 4, OSM))
        db.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")


def region_databases(gpkg, geo, title, metadata):
    national_path = geo / 'national.sqlite'
    with closing(sqlite3.connect(gpkg.as_uri() + '?mode=ro', uri=True)) as source, \
            closing(sqlite3.connect(national_path)) as national:
        features = build_map.build(source, national, metadata)
        layers = {row[0] for row in national.execute('SELECT DISTINCT layer FROM feat')}
        if not {'road', 'bldg', 'place'} <= layers or not national.execute('SELECT 1 FROM poi LIMIT 1').fetchone():
            raise ValueError(f'{title}: the extract lacks roads, buildings, places or help points.')
        build_places(national, geo / 'places.sqlite', title)
    finish_databases(geo, metadata, features)


def merge_region(national, places, geo):
    for db, name in ((national, 'national.sqlite'), (places, 'places.sqlite')):
        db.execute('ATTACH DATABASE ? AS region', ((geo / name).as_uri() + '?mode=ro',))
    with national, places:
        offset = national.execute('SELECT COALESCE(MAX(id), 0) FROM feat').fetchone()[0]
        national.execute('INSERT OR IGNORE INTO feat SELECT id+?,layer,cls,name,minz,geom FROM region.feat', (offset,))
        # R-tree IDs must match the remapped features, excluding the boundary duplicates skipped above.
        national.execute('''INSERT INTO feat_idx
            SELECT f.id,i.minx,i.maxx,i.miny,i.maxy,i.minz,i.maxz
            FROM region.feat_idx i JOIN feat f ON f.id=i.id+?''', (offset,))
        national.execute('INSERT OR IGNORE INTO poi(cls,name,lon,lat) SELECT cls,name,lon,lat FROM region.poi')
        places.execute('''INSERT OR IGNORE INTO place(name,kind,detail,lat,lon,rank,source)
            SELECT name,kind,detail,lat,lon,rank,source FROM region.place''')
    for db in (national, places):
        db.execute('DETACH DATABASE region')


def nationwide_databases(geo, extracts, metadata):
    # Keep country builds on disk and reclaim the duplicate-check indexes before packaging.
    with closing(sqlite3.connect(geo / 'national.sqlite', uri=True)) as national, \
            closing(sqlite3.connect(geo / 'places.sqlite', uri=True)) as places:
        for db, schema in ((national, build_map.MAP_SCHEMA), (places, PLACE_SCHEMA)):
            db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA auto_vacuum=FULL;' + schema)
        national.executescript("""CREATE UNIQUE INDEX feat_identity ON feat(layer,cls,COALESCE(name,''),geom);
          CREATE UNIQUE INDEX poi_identity ON poi(cls,COALESCE(name,''),lon,lat);""")
        places.execute('CREATE UNIQUE INDEX place_identity ON place(name,kind,lat,lon,rank,source)')
        for region, path in extracts:
            print(f'Adding {region} to All of Spain', flush=True)
            merge_region(national, places, path)
        with national, places:
            national.executescript('DROP INDEX feat_identity; DROP INDEX poi_identity; CREATE INDEX poi_cls ON poi(cls,lon,lat);')
            national.executemany('INSERT INTO meta VALUES (?,?)', metadata.items())
            places.execute('DROP INDEX place_identity')
            places.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
        features = national.execute('SELECT COUNT(*) FROM feat').fetchone()[0]
    finish_databases(geo, metadata, features)


def finish_databases(geo, metadata, features):
    with closing(sqlite3.connect(geo / 'map.sqlite')) as empty, empty:
        # Tiles require both the base schema and the national layer used for regional features.
        empty.executescript(build_map.MAP_SCHEMA)
        empty.executemany('INSERT INTO meta VALUES (?,?)', metadata.items())
    (geo / 'national-status.json').write_text(json.dumps({'state': 'complete', 'stage': 'ready', 'features': features}))
    (geo / 'socal-cells.json').write_text('[]')


def build_region(work, code, title, region_path, bounds, expected):
    url = source_url(region_path)
    source = SOURCE / url.rsplit('/', 1)[-1]
    if not source.is_file() or sha256(source) != expected:
        raise ValueError(f'{source.name} is missing or has changed. Run fetch first.')
    print(f'Building {title} ({code})', flush=True)
    geo = work / code / GEO
    geo.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        gpkg = Path(tmp) / 'source.gpkg'
        with zipfile.ZipFile(source) as z, z.open(region_path.rsplit('/', 1)[-1] + '.gpkg') as entry, gpkg.open('wb') as f:
            shutil.copyfileobj(entry, f, 1024 * 1024)
        region_databases(gpkg, geo, title, {
            'source': url, 'source_sha256': expected, 'data_as_of': DATE, 'credit': CREDIT,
        })
    return pack_map(work, code, title, bounds, CONTENTS)


def build_nationwide(work):
    code = 'ES'
    geo = work / code / GEO
    geo.mkdir(parents=True)
    sources = {source_url(path): digest for _, path, _, digest in REGIONS.values()}
    nationwide_databases(geo, ((region, work / region / GEO) for region in REGIONS), {
        'source': 'OpenStreetMap via Geofabrik regional GeoPackages',
        'source_extracts': json.dumps(sources), 'data_as_of': DATE, 'credit': CREDIT,
    })
    west, south, east, north = zip(*(region[2] for region in REGIONS.values()))
    bounds = (min(west), min(south), max(east), max(north))
    return pack_map(work, code, 'All of Spain', bounds, '17 autonomous communities, Ceuta and Melilla · ' + CONTENTS)


def pack_map(work, code, title, bounds, includes):
    data = work / code
    files = {p.relative_to(data).as_posix(): p.stat().st_size for p in sorted((data / GEO).iterdir())}
    info = {'name': code, 'title': title, 'country': 'ES', 'bounds': bounds, 'credit': CREDIT, 'data_as_of': DATE,
            'files': files, 'bytes': sum(files.values())}
    receipt = data / 'map-set.json'
    receipt.write_text(json.dumps(info, ensure_ascii=False) + '\n', encoding='utf-8')
    install.check_map(data)
    total = info['bytes'] + receipt.stat().st_size
    archive = work / f'Lastbook-Map-{code}.zip'
    timestamp = date.fromisoformat(DATE).timetuple()[:6]
    with zipfile.ZipFile(archive, 'w') as z:
        for rel in (*files, 'map-set.json'):
            item = zipfile.ZipInfo(rel, timestamp)
            item.compress_type = zipfile.ZIP_DEFLATED
            with (data / rel).open('rb') as src, z.open(item, 'w', force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    if install.check_zip(archive, total, install.map_member)[1] != total:
        raise ValueError(f'{archive.name} unpacked size disagrees with the catalog.')
    file = {'name': archive.name, 'size': archive.stat().st_size, 'sha256': sha256(archive), 'kind': 'zip'}
    print(f'{file["name"]}: {file["size"]:,} bytes', flush=True)
    return {'id': code, 'title': title, 'kind': 'region', 'available': True, 'installed_bytes': total,
            'includes': includes, 'files': [file]}


def build_catalog():
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        work = Path(tmp)
        maps = [build_region(work, code, *region) for code, region in REGIONS.items()]
        maps.insert(0, build_nationwide(work))
        catalog = work / 'manifest-v1.json'
        catalog.write_text(json.dumps({'version': 1, 'published': DATE, 'maps': maps}, indent=2) + '\n', encoding='utf-8')
        for entry in maps:
            archive = entry['files'][0]['name']
            (work / archive).replace(OUT / archive)
        catalog.replace(OUT / catalog.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('fetch', 'build'))
    args = parser.parse_args()
    SOURCE.mkdir(parents=True, exist_ok=True)
    try:
        if args.action == 'fetch':
            for _, region_path, _, expected in REGIONS.values():
                fetch(region_path, expected)
        else:
            build_catalog()
    except (OSError, ValueError, zipfile.BadZipFile, sqlite3.Error, install.Refused) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
