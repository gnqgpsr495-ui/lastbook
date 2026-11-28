#!/usr/bin/env python3
"""Build the place finder and the help points from an OpenStreetMap extract for any region.

The map set shipped with Lastbook is Southern California, built from the US government gazetteers and one
Geofabrik extract. This tool does the same job from a single .osm.pbf for any region: towns, villages,
islands and named places go into `places.sqlite` (with the FTS index the place finder reads), and hospitals,
clinics, pharmacies, police, fire stations, drinking water, shelters, camp sites, fuel and supermarkets go
into the `poi` table of `national.sqlite`, which the map draws and the assistant can cite.

Every region writes into its own directory (`derived/geo/regions/<region>/` by default), holding one
`places.sqlite` and one `national.sqlite`. Nothing outside that directory is read or written, so a regional
build can never truncate the shared US databases — `--fresh` only clears the region's own two files.

Names in other languages (`name:zh`, `name:ru`, …) are kept in the place's `detail` column, which is
indexed too, so a person can search in their own language. A place with a Chinese name gets it in front
of the detail: `悉尼 · Australia (OpenStreetMap)`.

  python3 tools/build_places_region.py australia-latest.osm.pbf --region Australia
  python3 tools/build_places_region.py new-zealand-latest.osm.pbf --region 'New Zealand' \\
      --bbox 166,-48,179,-34

`--bbox` is west,south,east,north in degrees — longitude first, the order a Geofabrik country box and a
GeoJSON envelope use, so a region's box can be passed straight through. Write it as `--bbox=...` when the
first number is negative.

`--no-poi` writes only `places.sqlite`. A region map built by the map pipeline already fills the `poi` table
from the same extract; in that case the place finder is the only thing missing.

Reads the .pbf, never writes it.
"""
import argparse
from contextlib import closing
import re
import sqlite3
import sys
from pathlib import Path

import osmium

HERE = Path(__file__).resolve().parents[1]

PLACE = {'city': 1, 'town': 2, 'village': 3, 'hamlet': 4, 'suburb': 5, 'quarter': 5, 'neighbourhood': 5,
         'locality': 4, 'isolated_dwelling': 5, 'farm': 5, 'island': 4, 'islet': 5, 'archipelago': 4}
AMENITY = {'hospital', 'clinic', 'doctors', 'dentist', 'pharmacy', 'police', 'fire_station',
           'shelter', 'toilets', 'fuel', 'ranger_station', 'community_centre', 'social_facility',
           'water_point'}
SHOP = {'supermarket', 'convenience', 'hardware', 'doityourself'}
ZH = ('name:zh', 'name:zh-Hans', 'name:zh-Hant')


def local_name(tags):
    """The first name in another language, Chinese first: it goes in front of the detail line."""
    for key in ZH + ('name:en', 'name:ru', 'name:es', 'name:fr', 'name:ar'):
        v = tags.get(key)
        if v:
            return v
    return ''


def poi_class(tags):
    """The `cls` value the map draws, or None.

    The class has to say what the thing is, not what it is nearest to: an ambulance station is not a fire
    station, and a firefighting water tank is not drinking water. Classes the map has no layer for
    (`water_tank`, `water_point`, `ambulance_station`) are kept in the data anyway — a layer can be added
    later, but a wrong class cannot be taken back once somebody is looking for a drink.
    """
    a = tags.get('amenity')
    if a == 'drinking_water':
        # `drinking_water=no` on a tap or water point means exactly that: it is water, not a drink.
        return 'water_point' if tags.get('drinking_water') == 'no' else 'drinking_water'
    if a in AMENITY:
        if a == 'shelter':
            # amenity=shelter is a bus shelter in much of the world. A real refuge is either tagged as one,
            # or carries a name; an anonymous shelter with no type is street furniture.
            kind = tags.get('shelter_type')
            if kind not in ('weather_shelter', 'basic_hut') and (kind or not tags.get('name')):
                return None
        return a
    e = tags.get('emergency')
    if e in ('ambulance_station', 'water_tank'):
        return e
    s = tags.get('shop')
    if s in SHOP:
        return 'supermarket' if s in ('supermarket', 'convenience') else s
    if tags.get('tourism') in ('alpine_hut', 'wilderness_hut', 'camp_site'):
        return 'camp_site' if tags.get('tourism') == 'camp_site' else 'shelter'
    return None


def ring_centroid(points):
    """Area-weighted centroid of a closed ring of (lon, lat); mean of the points when the ring is degenerate."""
    pts = points[:-1] if len(points) > 1 and points[0] == points[-1] else points
    if len(pts) < 3:
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else None
    twice, cx, cy = 0.0, 0.0, 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        f = x1 * y2 - x2 * y1
        twice += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(twice) < 1e-12:  # a line or a zero-area sliver
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return cx / (3 * twice), cy / (3 * twice)


def area_centroid(area):
    """Centroid of an osmium Area (closed way or multipolygon): the biggest outer ring, at its area centre."""
    best, best_area = None, -1.0
    for ring in area.outer_rings():
        pts = [(n.lon, n.lat) for n in ring]  # NodeRef carries the location when locations=True
        if len(pts) < 2:
            continue
        a = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2
        if a > best_area:
            best, best_area = pts, a
    return ring_centroid(best) if best else None


class Extract(osmium.SimpleHandler):
    def __init__(self, region, bbox):
        super().__init__()
        self.region = region
        self.bbox = bbox  # (west, south, east, north) or None
        self.places, self.pois = [], []

    def inside(self, lat, lon):
        if not self.bbox:
            return True
        west, south, east, north = self.bbox
        return south <= lat <= north and west <= lon <= east

    def add_place(self, tags, name, lat, lon):
        rank = PLACE.get(tags.get('place'))
        if not (rank and name):
            return False
        local = local_name(tags)
        detail = (local + ' · ' if local and local != name else '') + f'{self.region} (OpenStreetMap)'
        self.places.append((name, tags.get('place'), detail, lat, lon, rank, 'OpenStreetMap'))
        return True

    def add_poi(self, tags, name, lat, lon):
        cls = poi_class(tags)
        if cls:
            # Unnamed help points are kept: an unnamed water tank or clinic is still worth knowing about.
            self.pois.append((cls, name or '', lon, lat))
        return bool(cls)

    def node(self, n):
        t = n.tags
        if not t:
            return
        lat, lon = n.location.lat, n.location.lon
        if not self.inside(lat, lon):
            return
        name = t.get('name') or local_name(t)
        if not self.add_place(t, name, lat, lon):
            self.add_poi(t, name, lat, lon)

    def area(self, a):
        """Closed ways and multipolygons: hospitals, clinics and campuses are usually mapped as areas."""
        t = a.tags
        if not t:
            return
        c = area_centroid(a)
        if not c:
            return
        lon, lat = c
        if not self.inside(lat, lon):
            return
        name = t.get('name') or local_name(t)
        if not self.add_place(t, name, lat, lon):
            self.add_poi(t, name, lat, lon)


def region_dir(name):
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'region'
    return HERE / 'derived' / 'geo' / 'regions' / slug


def ours(path, region):
    """Check ownership read-only; never adopt another tool's or another region's database."""
    if not path.exists():
        return True
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            meta = dict(db.execute('SELECT key,value FROM build_meta'))
        return meta.get('builder') == 'build_places_region' and meta.get('region') == region
    except sqlite3.Error:
        return False


def open_dbs(out, fresh, region, want_poi=True):
    """Open (or create) the region's files. Never touches anything else in `out`."""
    out.mkdir(parents=True, exist_ok=True)
    places, national = out / 'places.sqlite', out / 'national.sqlite'
    mine = (places, national) if want_poi else (places,)
    # Validate both targets before opening either for writing, even without --fresh.
    foreign = [p.name for p in mine if not ours(p, region)]
    others = [p.name for p in out.glob('*.sqlite') if p not in mine] if fresh else []
    if foreign or others:
        sys.exit(f'{out} holds databases this tool did not create for region {region!r} '
                 f'({", ".join(sorted(set(foreign + others)))}). Pass --out with a region-owned directory.')
    if fresh:
        for f in mine:
            f.unlink(missing_ok=True)
    pdb = sqlite3.connect(places)
    pdb.executescript('''CREATE TABLE IF NOT EXISTS place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT,
        lat REAL, lon REAL, rank INTEGER, source TEXT);
      CREATE VIRTUAL TABLE IF NOT EXISTS place_fts USING fts5(name, detail, content='place', content_rowid='id',
        tokenize='unicode61');''')
    unique(pdb, 'place', 'name,kind,lat,lon')
    if not want_poi:
        pdb.executescript('CREATE TABLE IF NOT EXISTS build_meta(key TEXT PRIMARY KEY, value TEXT);')
        pdb.execute('INSERT OR REPLACE INTO build_meta VALUES (?,?)', ('region', region))
        pdb.execute('INSERT OR REPLACE INTO build_meta VALUES (?,?)', ('builder', 'build_places_region'))
        return pdb, None
    ndb = sqlite3.connect(national)
    ndb.executescript('CREATE TABLE IF NOT EXISTS poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);')
    unique(ndb, 'poi', 'cls,name,lon,lat')
    for db in (pdb, ndb):
        db.executescript('CREATE TABLE IF NOT EXISTS build_meta(key TEXT PRIMARY KEY, value TEXT);')
        db.executemany('INSERT OR REPLACE INTO build_meta VALUES (?,?)',
                       [('builder', 'build_places_region'), ('region', region)])
    return pdb, ndb


def unique(db, table, cols):
    """A key so running the same region twice adds no duplicates (older files may already hold some)."""
    try:
        db.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {table}_key ON {table}({cols})')
    except sqlite3.IntegrityError:
        db.execute(f'DELETE FROM {table} WHERE rowid NOT IN (SELECT min(rowid) FROM {table} GROUP BY {cols})')
        db.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {table}_key ON {table}({cols})')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pbf', help='.osm.pbf for the region (Geofabrik, BBBike, …)')
    ap.add_argument('--region', required=True, help='plain name for the detail line, e.g. Australia')
    ap.add_argument('--out', help='directory for this region (default derived/geo/regions/<region>)')
    ap.add_argument('--bbox', help='west,south,east,north to keep only part of the extract; '
                                   'write --bbox=-179,-48,-166,-34 when the first number is negative')
    ap.add_argument('--fresh', action='store_true', help="delete this region's own files first")
    ap.add_argument('--no-poi', action='store_true',
                    help='write places.sqlite only (a region map already fills the poi table)')
    a = ap.parse_args()

    bbox = None
    if a.bbox is not None:
        try:
            bbox = tuple(float(x) for x in a.bbox.split(','))
            if len(bbox) != 4:
                raise ValueError
        except ValueError:
            sys.exit('--bbox needs four numbers: west,south,east,north')
        west, south, east, north = bbox
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            sys.exit(f'--bbox is west,south,east,north — longitude must be in [-180,180], latitude in [-90,90], '
                     f'west <= east and south <= north; all values must be finite; got {a.bbox}')

    h = Extract(a.region, bbox)
    h.apply_file(a.pbf, locations=True)
    out = Path(a.out) if a.out else region_dir(a.region)
    pdb, ndb = open_dbs(out, a.fresh, a.region, want_poi=not a.no_poi)
    pdb.executemany('INSERT OR IGNORE INTO place(name,kind,detail,lat,lon,rank,source) VALUES (?,?,?,?,?,?,?)',
                    h.places)
    pdb.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
    pdb.commit()
    if ndb is not None:
        ndb.executemany('INSERT OR IGNORE INTO poi(cls,name,lon,lat) VALUES (?,?,?,?)', h.pois)
        ndb.commit()
    if bbox and not (h.places or h.pois):
        print('warning: nothing matched --bbox — it is west,south,east,north (lon first), not lat,lon',
              file=sys.stderr)
    taught = '' if ndb is not None else '  (poi skipped)'
    print(f'places {len(h.places)}  poi {len(h.pois)}{taught}  → {out / "places.sqlite"}')


if __name__ == '__main__':
    main()
