"""Checks the country coverage guard against the real bounded Vienna source fixture, not only synthetic rows.

  python3 -B packaging/test_country_coverage_realdata.py

The fixture `prototypes/at-9-vienna-fixture/fixture/national.sqlite` is real BEV/OSM source data: 1,082 named
place features and zero road features. `national.sqlite` is copied into a temporary map-set layout and counted
through `state_maps.coverage_counts` for Austria (`eu-at`), whose box contains Vienna. No network, no bucket and
no real upload.
"""
import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIXTURE = ROOT / 'prototypes/at-9-vienna-fixture/fixture'
CODE = 'eu-at'
VIENNA = (16.3738, 48.2082)      # inside Austria's box
BERLIN = (13.4050, 52.5200)      # a neighbour's detail, outside Austria's box


def load_state_maps():
    real = sys.modules.get('r2_publish')
    fake = types.ModuleType('r2_publish')
    fake.MULTIPART_OVER = fake.PART = 1
    fake.Context = object
    sys.modules['r2_publish'] = fake
    try:
        spec = importlib.util.spec_from_file_location('state_maps_realdata', HERE / 'state_maps.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if real is None:
            del sys.modules['r2_publish']
        else:
            sys.modules['r2_publish'] = real


SM = load_state_maps()


def fixture_set(root):
    """A minimal map-set root holding the real fixture DBs; layers the fixture does not carry are absent."""
    geo = Path(root) / 'derived/geo'
    geo.mkdir(parents=True)
    for name in ('national.sqlite', 'places.sqlite'):
        shutil.copy2(FIXTURE / name, geo / name)
    return Path(root)


def add_feature(path, feature_id, layer, lon, lat, minz=12):
    db = sqlite3.connect(path)
    try:
        db.execute('INSERT INTO feat(id, layer, cls, name, minz) VALUES(?, ?, ?, ?, ?)', (feature_id, layer, 'test', 'Test', minz))
        db.execute('INSERT INTO feat_idx(id, minx, maxx, miny, maxy, minz, maxz) VALUES(?, ?, ?, ?, ?, ?, ?)',
                   (feature_id, lon, lon, lat, lat, minz, 30))
        db.commit()
    finally:
        db.close()


@unittest.skipUnless((FIXTURE / 'national.sqlite').exists(), 'Vienna source fixture is not present')
class RealViennaFixture(unittest.TestCase):
    def test_fixture_is_real_and_has_zero_roads(self):
        db = sqlite3.connect(f'file:{FIXTURE / "national.sqlite"}?immutable=1', uri=True)
        try:
            layers = dict(db.execute('SELECT layer, count(*) FROM feat GROUP BY layer'))
            high_zoom = db.execute('SELECT count(*) FROM feat WHERE minz>8').fetchone()[0]
            roads = db.execute("SELECT count(*) FROM feat WHERE layer='road'").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(roads, 0)
        self.assertEqual(layers, {'place': 1082})
        self.assertEqual(high_zoom, 1076)

    def test_real_place_points_are_not_counted_as_roads(self):
        with tempfile.TemporaryDirectory() as d:
            root = fixture_set(d)
            counts = SM.coverage_counts(root, CODE)
            self.assertEqual(counts['roads'], 0)
            self.assertEqual(counts['help points'], 2344)
            self.assertEqual(counts['place names'], 567)
            self.assertIn('roads', SM.country_coverage(root, CODE))

    def test_stray_neighbour_road_outside_the_box_does_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            root = fixture_set(d)
            add_feature(root / 'derived/geo/national.sqlite', 9001, 'road', *BERLIN)
            self.assertEqual(SM.coverage_counts(root, CODE)['roads'], 0)

    def test_real_road_inside_the_box_counts(self):
        with tempfile.TemporaryDirectory() as d:
            root = fixture_set(d)
            add_feature(root / 'derived/geo/national.sqlite', 9002, 'road', *VIENNA)
            self.assertEqual(SM.coverage_counts(root, CODE)['roads'], 1)

    def test_allowlist_stays_empty(self):
        text = (HERE / 'country-publication.json').read_text(encoding='utf-8')
        self.assertEqual(json.loads(text)['countries'], {})

    def test_refusal_comes_before_zip_upload_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            maps = Path(d) / 'maps'
            root = fixture_set(maps / CODE)
            calls = []
            old = (SM.MAPS, SM.scan, SM.web_text, SM.subprocess.run, SM.shutil.disk_usage, SM.make_zip, SM.upload,
                   SM.list_in_manifest, SM.PUBLISHED_COUNTRIES, SM.log)
            try:
                SM.MAPS = maps
                SM.scan = lambda d, code: ([], {})
                SM.web_text = lambda d: ([], {})
                SM.subprocess.run = lambda *a, **k: None
                SM.shutil.disk_usage = lambda p: types.SimpleNamespace(free=40e9)
                SM.make_zip = lambda *a, **k: calls.append('zip') or sys.exit('zip was called')
                SM.upload = lambda *a, **k: calls.append('upload') or sys.exit('upload was called')
                SM.list_in_manifest = lambda *a, **k: calls.append('manifest') or sys.exit('manifest was called')
                SM.log = lambda *a: None
                SM.PUBLISHED_COUNTRIES = {CODE: {}}          # opted in, yet the set has no roads
                with self.assertRaises(SystemExit) as e:
                    SM.one_state(object(), CODE, {})
                self.assertIn('no roads detail inside the country box', str(e.exception))
                self.assertEqual(calls, [])
            finally:
                (SM.MAPS, SM.scan, SM.web_text, SM.subprocess.run, SM.shutil.disk_usage, SM.make_zip, SM.upload,
                 SM.list_in_manifest, SM.PUBLISHED_COUNTRIES, SM.log) = old


if __name__ == '__main__':
    unittest.main()
