"""Check that a nationwide build keeps spatial and search coverage from each extract."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from engine.setup import install
from tools import build_map, build_region_es


class BuildControl:
    def check(self):
        pass


class NationwideMap(unittest.TestCase):
    def make_extract(self, geo, title, places):
        geo.mkdir()
        with closing(sqlite3.connect(geo / 'national.sqlite')) as db, db:
            db.executescript(build_map.MAP_SCHEMA)
            for fid, (name, lon, lat) in enumerate(places, 1):
                db.execute('INSERT INTO feat VALUES (?, ?, ?, ?, ?, ?)',
                           (fid, 'place', 'city', name, 6, build_map.pack([[lon, lat]])))
                db.execute('INSERT INTO feat_idx VALUES (?, ?, ?, ?, ?, ?, ?)', (fid, lon, lon, lat, lat, 6, 30))
            db.execute("INSERT INTO poi VALUES (1, 'drinking_water', NULL, -3.7, 40.4)")
            build_region_es.build_places(db, geo / 'places.sqlite', title)

    def test_merged_extracts_keep_spatial_matches_and_search_without_boundary_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mainland, islands = root / 'mainland', root / 'islands'
            country = root / 'ES' / build_region_es.GEO
            border = ('Boundary town', -3.7, 40.4)
            self.make_extract(mainland, 'Mainland', [border, ('Madrid', -3.7, 40.42)])
            self.make_extract(islands, 'Islands', [('Las Palmas', -15.4, 28.1), border])
            country.mkdir(parents=True)

            build_region_es.nationwide_databases(country, [('mainland', mainland), ('islands', islands)], {})
            bounds = (-18, 27, 5, 44)
            entry = build_region_es.pack_map(root, 'ES', 'All of Spain', bounds, build_region_es.CONTENTS)
            lib = install.unpack(root / 'Lastbook-Map-ES.zip', root / 'unpacked', entry['installed_bytes'],
                                 BuildControl(), lambda *_: None, allowed=install.map_member)
            self.assertEqual(install.map_name(lib), 'ES')

            geo = lib / build_region_es.GEO
            with closing(sqlite3.connect(geo / 'national.sqlite')) as db:
                query = ('SELECT f.name FROM feat_idx i JOIN feat f ON f.id=i.id '
                         'WHERE i.maxx BETWEEN ? AND ? AND i.maxy BETWEEN ? AND ? ORDER BY f.name')
                self.assertEqual(db.execute(query, (-3.8, -3.6, 40.3, 40.5)).fetchall(),
                                 [('Boundary town',), ('Madrid',)])
                self.assertEqual(db.execute(query, (-15.5, -15.3, 28, 28.2)).fetchall(), [('Las Palmas',)])
                self.assertEqual(db.execute("SELECT count(*) FROM poi WHERE cls='drinking_water'").fetchone(), (1,))
            with closing(sqlite3.connect(geo / 'places.sqlite')) as db:
                query = ("SELECT p.name, p.detail FROM place_fts JOIN place p ON p.id=place_fts.rowid "
                         "WHERE place_fts MATCH ?")
                self.assertEqual(db.execute(query, ('Madrid',)).fetchall(), [('Madrid', 'Mainland')])
                self.assertEqual(db.execute(query, ('Palmas',)).fetchall(), [('Las Palmas', 'Islands')])
                self.assertEqual(db.execute(query, ('Boundary',)).fetchall(), [('Boundary town', 'Mainland')])
