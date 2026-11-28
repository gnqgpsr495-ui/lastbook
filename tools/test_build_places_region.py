#!/usr/bin/env python3
"""Tests for tools/build_places_region.py.

  python3 tools/test_build_places_region.py

Needs pyosmium (a build-time dependency already used by tools/build_coast.py). Builds from a tiny OSM file,
so it runs without any library or data folder. Everything is written under a temporary directory.
"""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

OSM = '''<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" lat="-33.8700" lon="151.2100">
    <tag k="place" v="city"/><tag k="name" v="Sydney"/><tag k="name:zh" v="悉尼"/>
  </node>
  <node id="5" lat="-33.9100" lon="151.2500">
    <tag k="place" v="village"/><tag k="name" v="Nowhere"/><tag k="name:zh" v="诺威尔"/>
  </node>
  <node id="6" lat="-20.0000" lon="140.0000">
    <tag k="place" v="town"/><tag k="name" v="Outside"/><tag k="name:zh" v="外面"/>
  </node>
  <node id="2" lat="-33.8800" lon="151.2200">
    <tag k="amenity" v="hospital"/><tag k="name" v="St Vincent's Hospital"/>
  </node>
  <node id="3" lat="-33.8900" lon="151.2300">
    <tag k="amenity" v="shelter"/><tag k="shelter_type" v="public_transport"/><tag k="name" v="Bus shelter"/>
  </node>
  <node id="4" lat="-33.9000" lon="151.2400">
    <tag k="amenity" v="pharmacy"/><tag k="name" v="Chemist Warehouse"/>
  </node>
  <node id="7" lat="-33.9200" lon="151.2600">
    <tag k="amenity" v="drinking_water"/><tag k="drinking_water" v="no"/><tag k="name" v="Rinse tap"/>
  </node>
  <node id="8" lat="-33.9300" lon="151.2700">
    <tag k="emergency" v="water_tank"/><tag k="name" v="CFA tank"/>
  </node>
  <node id="9" lat="-33.9400" lon="151.2800">
    <tag k="emergency" v="ambulance_station"/><tag k="name" v="Ambulance NSW"/>
  </node>
  <node id="10" lat="-33.9500" lon="151.2900">
    <tag k="amenity" v="fuel"/>
  </node>
  <node id="11" lat="-33.9600" lon="151.3000">
    <tag k="amenity" v="shelter"/>
  </node>
  <node id="12" lat="-33.9700" lon="151.3100">
    <tag k="amenity" v="shelter"/><tag k="shelter_type" v="weather_shelter"/>
  </node>
  <node id="13" lat="-33.9800" lon="151.3200">
    <tag k="amenity" v="shelter"/><tag k="name" v="Rotunda"/>
  </node>
  <node id="21" lat="-33.8000" lon="151.1000"/><node id="22" lat="-33.8000" lon="151.1200"/>
  <node id="23" lat="-33.8200" lon="151.1200"/><node id="24" lat="-33.8200" lon="151.1000"/>
  <way id="30"><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="24"/><nd ref="21"/>
    <tag k="amenity" v="hospital"/><tag k="name" v="Closed Way Hospital"/>
  </way>
  <node id="31" lat="-33.6000" lon="151.3000"/><node id="32" lat="-33.6000" lon="151.3200"/>
  <node id="33" lat="-33.6200" lon="151.3200"/><node id="34" lat="-33.6200" lon="151.3000"/>
  <way id="40"><nd ref="31"/><nd ref="32"/><nd ref="33"/><nd ref="34"/><nd ref="31"/></way>
  <relation id="50"><member type="way" ref="40" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="amenity" v="clinic"/><tag k="name" v="MP Clinic"/>
  </relation>
</osm>
'''


def build(osm, out, bbox=None, fresh=False, no_poi=False):
    cmd = [sys.executable, str(HERE / 'build_places_region.py'), str(osm), '--region', 'Australia', '--out', str(out)]
    if bbox is not None:
        cmd += [f'--bbox={bbox}']  # the '=' form keeps a leading minus from looking like an option
    if fresh:
        cmd.append('--fresh')
    if no_poi:
        cmd.append('--no-poi')
    return subprocess.run(cmd, capture_output=True, text=True)


class BuildPlacesRegionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='lastbook-places-')
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.osm = self.tmp / 'sample.osm'
        self.osm.write_text(OSM, encoding='utf-8')
        self.out = self.tmp / 'regions' / 'australia'

    def place_rows(self):
        db = sqlite3.connect(self.out / 'places.sqlite')
        try:
            return db.execute('SELECT name,kind,detail,lat,lon,rank,source FROM place ORDER BY name').fetchall()
        finally:
            db.close()

    def poi_rows(self):
        db = sqlite3.connect(self.out / 'national.sqlite')
        try:
            return db.execute('SELECT cls,name,lon,lat FROM poi ORDER BY cls, name').fetchall()
        finally:
            db.close()

    def test_region(self):
        r = build(self.osm, self.out, bbox='140,-40,155,-25')
        assert r.returncode == 0, r.stderr

        places = self.place_rows()
        assert [p[0] for p in places] == ['Nowhere', 'Sydney'], places  # Outside is outside the bbox
        sydney = next(p for p in places if p[0] == 'Sydney')
        assert sydney[1] == 'city' and sydney[5] == 1, sydney  # kind and rank as the place finder expects
        assert sydney[2].startswith('悉尼 · Australia (OpenStreetMap)'), sydney[2]
        assert abs(sydney[3] + 33.87) < 1e-6 and abs(sydney[4] - 151.21) < 1e-6, sydney

        # the place finder queries the FTS index with a prefix match; other-language names must be findable
        pdb = sqlite3.connect(self.out / 'places.sqlite')
        hit = pdb.execute('SELECT p.name FROM place_fts f JOIN place p ON p.id=f.rowid '
                          'WHERE place_fts MATCH ? ORDER BY p.rank', ('"悉尼"*',)).fetchall()
        assert [h[0] for h in hit] == ['Sydney'], hit
        hit = pdb.execute('SELECT p.name FROM place_fts f JOIN place p ON p.id=f.rowid WHERE place_fts MATCH ?',
                          ('"Nowh"*',)).fetchall()
        assert [h[0] for h in hit] == ['Nowhere'], hit
        pdb.close()

        poi = self.poi_rows()
        # a bus shelter is not a refuge; a fire tank is not a drink; an ambulance station is not a fire station
        assert [p[0] for p in poi] == ['ambulance_station', 'clinic', 'fuel', 'hospital', 'hospital',
                                       'pharmacy', 'shelter', 'shelter', 'water_point', 'water_tank'], poi
        classes = {(p[0], p[1]) for p in poi}
        assert ('water_point', 'Rinse tap') in classes, classes      # drinking_water=no is not drinking water
        assert ('water_tank', 'CFA tank') in classes, classes        # firefighting water keeps its own class
        assert ('ambulance_station', 'Ambulance NSW') in classes, classes
        assert ('fuel', '') in classes, classes                      # unnamed help points are kept
        assert ('hospital', "St Vincent's Hospital") in classes, classes
        # polygons: the closed way and the multipolygon both land at their area centre
        # shelters: anonymous street furniture goes, a weather shelter and a named rotunda stay
        assert ('shelter', '') in classes and ('shelter', 'Rotunda') in classes, classes
        assert len([p for p in poi if p[0] == 'shelter']) == 2, poi
        assert ('hospital', 'Closed Way Hospital') in classes, classes
        assert ('clinic', 'MP Clinic') in classes, classes
        closed = next(p for p in poi if p[1] == 'Closed Way Hospital')
        assert abs(closed[2] - 151.11) < 1e-6 and abs(closed[3] + 33.81) < 1e-6, closed
        multi = next(p for p in poi if p[1] == 'MP Clinic')
        assert abs(multi[2] - 151.31) < 1e-6 and abs(multi[3] + 33.61) < 1e-6, multi

    def test_bbox_is_west_south_east_north(self):
        # the order the region specs use: a box round Sydney keeps it, and drops the town at -20/140
        r = build(self.osm, self.out, bbox='151,-33.89,151.4,-33.85')
        assert r.returncode == 0, r.stderr
        assert [p[0] for p in self.place_rows()] == ['Sydney'], self.place_rows()

        # the old latitude-first order must be refused, not silently accepted
        bad = build(self.osm, self.tmp / 'wrong', bbox='-33,150,-35,152')
        assert bad.returncode != 0 and 'west,south,east,north' in bad.stderr, bad.stderr
        assert not (self.tmp / 'wrong' / 'places.sqlite').exists()

        # A valid box outside the extract matches nothing: say so.
        empty = build(self.osm, self.tmp / 'empty', bbox='-10,-10,10,10')
        assert empty.returncode == 0 and 'west,south,east,north' in empty.stderr, empty.stderr

    def test_invalid_bbox_preserves_existing_outputs(self):
        assert build(self.osm, self.out).returncode == 0
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        boxes = ('nan,nan,nan,nan', 'nan,-40,155,-25', '140,nan,155,-25',
                 '140,-40,nan,-25', '140,-40,155,nan', '-inf,-90,180,90',
                 '-180,-90,inf,90', '-180,-inf,180,90', '-180,-90,180,inf',
                 '-181,-90,180,90', '-180,-91,180,90', '-180,-90,181,90',
                 '-180,-90,180,91', '155,-40,140,-25', '140,-25,155,-40',
                 '-40,140,-25,155', '1,2,3', 'west,south,east,north', '')
        for bbox in boxes:
            with self.subTest(bbox=bbox):
                r = build(self.osm, self.out, bbox=bbox, fresh=True)
                self.assertNotEqual(r.returncode, 0, r.stderr)
                self.assertIn('west,south,east,north', r.stderr)
                self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()}, before)
                # Reject the bbox before trying to read even a missing input.
                r = build(self.tmp / 'missing.osm', self.tmp / 'new', bbox=bbox)
                self.assertIn('west,south,east,north', r.stderr)
                self.assertFalse((self.tmp / 'new').exists())
        r = build(self.osm, self.out, bbox='-180,-90,180,90')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.place_rows()), 3)

    def test_unowned_outputs_are_never_adopted(self):
        for filename in ('places.sqlite', 'national.sqlite'):
            for fresh, no_poi in ((False, False), (True, False), (False, True), (True, True)):
                if filename == 'national.sqlite' and no_poi:
                    continue  # --no-poi never opens national.sqlite
                with self.subTest(filename=filename, fresh=fresh, no_poi=no_poi):
                    out = self.tmp / f'{filename}-{fresh}-{no_poi}'
                    out.mkdir()
                    db = sqlite3.connect(out / filename)
                    db.executescript("CREATE TABLE water(name TEXT); INSERT INTO water VALUES ('US reservoir');")
                    db.close()
                    before = {p.name: p.read_bytes() for p in out.iterdir()}
                    r = build(self.osm, out, fresh=fresh, no_poi=no_poi)
                    self.assertNotEqual(r.returncode, 0, r.stderr)
                    self.assertIn('did not', r.stderr)
                    self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, before)

        # Check both outputs before touching either, even if one is already ours.
        assert build(self.osm, self.out).returncode == 0
        db = sqlite3.connect(self.out / 'national.sqlite')
        db.execute('DROP TABLE build_meta')
        db.commit()
        db.close()
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        for fresh in (False, True):
            r = build(self.osm, self.out, fresh=fresh)
            self.assertNotEqual(r.returncode, 0, r.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()}, before)

    def test_other_regions_outputs_are_never_reused(self):
        assert build(self.osm, self.out).returncode == 0
        db = sqlite3.connect(self.out / 'places.sqlite')
        db.execute("UPDATE build_meta SET value='New Zealand' WHERE key='region'")
        db.commit()
        db.close()
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        for fresh in (False, True):
            r = build(self.osm, self.out, fresh=fresh)
            self.assertNotEqual(r.returncode, 0, r.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()}, before)

    def test_rerun_adds_no_duplicates(self):
        assert build(self.osm, self.out).returncode == 0
        first = (len(self.place_rows()), len(self.poi_rows()))
        assert build(self.osm, self.out).returncode == 0
        assert (len(self.place_rows()), len(self.poi_rows())) == first, 'a second run of the same region duplicated rows'
        # and a second region in another directory starts empty
        other = self.tmp / 'regions' / 'new-zealand'
        assert build(self.osm, other).returncode == 0
        assert (other / 'places.sqlite').exists()

    def test_shared_databases_are_never_touched(self):
        base = self.tmp / 'geo'
        base.mkdir(parents=True)
        ndb = sqlite3.connect(base / 'national.sqlite')
        ndb.executescript('CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);\n'
                          'CREATE TABLE water(id INTEGER PRIMARY KEY, name TEXT);\n'
                          "INSERT INTO water(name) VALUES ('US reservoir');")
        ndb.commit()
        ndb.close()
        (base / 'map.sqlite').write_bytes(b'not really a database')
        before = {p.name: p.read_bytes() for p in base.iterdir()}

        # --fresh in a directory that holds the shared files must refuse and change nothing
        r = build(self.osm, base, fresh=True)
        assert r.returncode != 0 and 'did not' in r.stderr, r.stderr
        assert {p.name: p.read_bytes() for p in base.iterdir()} == before, 'the shared databases were modified'

        # building a region next to them leaves them alone too
        assert build(self.osm, base / 'regions' / 'australia', fresh=True).returncode == 0
        assert {p.name: p.read_bytes() for p in base.iterdir() if p.is_file()} == before

    def test_no_poi_writes_places_only(self):
        r = build(self.osm, self.out, no_poi=True)
        assert r.returncode == 0, r.stderr
        assert (self.out / 'places.sqlite').exists()
        assert not (self.out / 'national.sqlite').exists(), '--no-poi must not create the poi database'
        assert [p[0] for p in self.place_rows()] == ['Nowhere', 'Outside', 'Sydney'], self.place_rows()

    def test_fresh_clears_only_its_own_files(self):
        assert build(self.osm, self.out).returncode == 0
        assert (self.out / 'places.sqlite').exists()
        assert build(self.osm, self.out, fresh=True).returncode == 0
        assert (self.out / 'places.sqlite').exists()
        db = sqlite3.connect(self.out / 'places.sqlite')
        row = db.execute("SELECT value FROM build_meta WHERE key='region'").fetchone()
        db.close()
        assert row and row[0] == 'Australia', row


if __name__ == '__main__':
    unittest.main(verbosity=2)
