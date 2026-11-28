"""Checks the country-publishing guard in state_maps.py without the source layers or the bucket.

  python3 -B packaging/test_state_maps.py

The build side is exercised with small SQLite files: one base-only set (what a US-only source snapshot yields for a
European country) and one with a row in every detailed layer, placed inside the country's box. No network, no derived
source, nothing written outside the temporary folder.
"""
import hashlib
import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = 'eu-at'
INSIDE = (16.37, 48.21)          # Vienna, inside Austria's box
OUTSIDE = (13.40, 52.50)         # Berlin, outside Austria's box


def load_state_maps():
    """state_maps.py imports r2_publish from the release folder, which is not part of this repository."""
    real = sys.modules.get('r2_publish')
    fake = types.ModuleType('r2_publish')
    fake.MULTIPART_OVER = fake.PART = 1
    fake.Context = object
    sys.modules['r2_publish'] = fake
    try:
        spec = importlib.util.spec_from_file_location('state_maps_under_test', HERE / 'state_maps.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if real is None:
            del sys.modules['r2_publish']
        else:
            sys.modules['r2_publish'] = real


SM = load_state_maps()
FEAT = 'CREATE TABLE IF NOT EXISTS feat(id INTEGER PRIMARY KEY, layer TEXT, cls TEXT, name TEXT, minz INTEGER, geom BLOB)'
FEAT_IDX = 'CREATE VIRTUAL TABLE IF NOT EXISTS feat_idx USING rtree(id, minx, maxx, miny, maxy, minz, maxz)'


def tile_at(zoom, box_code=CODE):
    """The top-left tile of the country's box at this zoom, a legitimate row inside the box."""
    x0, _x1, y0, _y1 = SM._tile_ranges(box_code, [zoom])[zoom]
    return x0, y0


def make_set(root, detailed):
    geo = Path(root) / 'derived/geo'
    geo.mkdir(parents=True)

    def make(name, schema, rows=()):
        db = sqlite3.connect(geo / name)
        try:
            for sql in schema:
                db.execute(sql)
            for sql, values in rows:
                db.execute(sql, values)
            db.commit()
        finally:
            db.close()

    make('national.sqlite', [FEAT, FEAT_IDX, 'CREATE TABLE IF NOT EXISTS poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL)'],
         [('INSERT INTO feat VALUES(?, ?, ?, ?, ?, NULL)', (1, 'place', 'city', 'Base place', 8))])
    make('water.sqlite', ['CREATE TABLE IF NOT EXISTS resource(id INTEGER PRIMARY KEY, lon REAL, lat REAL)'])
    make('terrain.sqlite', ['CREATE TABLE IF NOT EXISTS tile(z INTEGER, x INTEGER, y INTEGER, PRIMARY KEY(z, x, y))'])
    make('buildings.sqlite', ['CREATE TABLE IF NOT EXISTS bldg(x INTEGER, y INTEGER)', 'CREATE TABLE IF NOT EXISTS bldg_socal(x INTEGER, y INTEGER)', 'CREATE TABLE IF NOT EXISTS bldg_osm(x INTEGER, y INTEGER)'])
    make('crops.sqlite', ['CREATE TABLE IF NOT EXISTS resource(id INTEGER PRIMARY KEY, lon REAL, lat REAL)'])
    make('places.sqlite', ['CREATE TABLE IF NOT EXISTS place(id INTEGER PRIMARY KEY, source TEXT, lon REAL, lat REAL)'])
    if detailed:
        lon, lat = INSIDE
        tx, ty = tile_at(8)
        bx, by = tile_at(14)
        make('national.sqlite', [FEAT, FEAT_IDX, 'CREATE TABLE IF NOT EXISTS poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL)'],
             [('INSERT INTO feat VALUES(?, ?, ?, ?, ?, NULL)', (2, 'road', 'residential', 'Test street', 12)),
              ('INSERT INTO feat_idx VALUES(?, ?, ?, ?, ?, ?, ?)', (2, lon, lon, lat, lat, 12, 30)),
              ('INSERT INTO poi(id, cls, name, lon, lat) VALUES(?, ?, ?, ?, ?)', (3, 'pharmacy', 'Test', lon, lat))])
        make('water.sqlite', ['CREATE TABLE IF NOT EXISTS resource(id INTEGER PRIMARY KEY, lon REAL, lat REAL)'],
             [('INSERT INTO resource VALUES(?, ?, ?)', (4, lon, lat))])
        make('terrain.sqlite', ['CREATE TABLE IF NOT EXISTS tile(z INTEGER, x INTEGER, y INTEGER, PRIMARY KEY(z, x, y))'],
             [('INSERT INTO tile VALUES(?, ?, ?)', (8, tx, ty))])
        make('buildings.sqlite', ['CREATE TABLE IF NOT EXISTS bldg(x INTEGER, y INTEGER)', 'CREATE TABLE IF NOT EXISTS bldg_socal(x INTEGER, y INTEGER)', 'CREATE TABLE IF NOT EXISTS bldg_osm(x INTEGER, y INTEGER)'],
             [('INSERT INTO bldg VALUES(?, ?)', (bx, by))])
        make('crops.sqlite', ['CREATE TABLE IF NOT EXISTS resource(id INTEGER PRIMARY KEY, lon REAL, lat REAL)'],
             [('INSERT INTO resource VALUES(?, ?, ?)', (5, lon, lat))])
        make('places.sqlite', ['CREATE TABLE IF NOT EXISTS place(id INTEGER PRIMARY KEY, source TEXT, lon REAL, lat REAL)'],
             [('INSERT INTO place VALUES(?, ?, ?, ?)', (6, 'OpenStreetMap', lon, lat))])


def tree_state(root):
    """Every path under root with its contents' hash, so a test can prove a dry run wrote nothing."""
    root = Path(root)
    state = {}
    for p in sorted(root.rglob('*')):
        state[p.relative_to(root).as_posix()] = (
            p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
    return state


def artifact_state():
    """The files publishing would write, if they happen to exist in this checkout."""
    state = {}
    for name in ('ZIPS', 'RESULTS', 'TABLE', 'MANIFEST'):
        p = getattr(SM, name)
        if p.is_dir():
            state[name] = ('dir', tree_state(p))
        elif p.exists():
            state[name] = ('file', p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
        else:
            state[name] = None
    return state


class CountryPublishing(unittest.TestCase):
    def setUp(self):
        self.old = SM.PUBLISHED_COUNTRIES
        self.old_states = SM.states

    def tearDown(self):
        SM.PUBLISHED_COUNTRIES = self.old
        SM.states = self.old_states

    def test_base_only_build_fails_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=False)
            self.assertEqual(set(SM.country_coverage(d, CODE)), set(SM.COVERAGE))

    def test_detail_in_every_layer_passes_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            self.assertEqual(SM.country_coverage(d, CODE), {})
            self.assertTrue(all(SM.coverage_counts(d, CODE).values()))

    def test_detail_outside_the_country_box_does_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            geo = Path(d) / 'derived/geo'
            db = sqlite3.connect(geo / 'national.sqlite')
            lon, lat = OUTSIDE
            db.execute('INSERT INTO feat VALUES(?, ?, ?, ?, ?, NULL)', (9, 'road', 'motorway', 'Elsewhere', 12))
            db.execute('INSERT INTO feat_idx VALUES(?, ?, ?, ?, ?, ?, ?)', (9, lon, lon, lat, lat, 12, 30))
            db.execute('INSERT INTO poi(id, cls, name, lon, lat) VALUES(?, ?, ?, ?, ?)', (10, 'pharmacy', 'Elsewhere', lon, lat))
            db.commit()
            db.close()
            db = sqlite3.connect(geo / 'water.sqlite')
            db.execute('INSERT INTO resource VALUES(?, ?, ?)', (11, lon, lat))
            db.commit()
            db.close()
            counts = SM.coverage_counts(d, CODE)
            self.assertEqual(counts['roads'], 1)
            self.assertEqual(counts['help points'], 1)
            self.assertEqual(counts['water points'], 1)

    def test_place_points_are_not_roads(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=False)
            geo = Path(d) / 'derived/geo'
            db = sqlite3.connect(geo / 'national.sqlite')
            lon, lat = INSIDE
            for i in range(20):
                db.execute('INSERT INTO feat VALUES(?, ?, ?, ?, ?, NULL)', (100 + i, 'place', 'locality', 'Place', 14))
                db.execute('INSERT INTO feat_idx VALUES(?, ?, ?, ?, ?, ?, ?)', (100 + i, lon, lon, lat, lat, 14, 30))
            db.commit()
            db.close()
            self.assertEqual(SM.coverage_counts(d, CODE)['roads'], 0)

    def test_missing_layer_counts_as_no_detail(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            (Path(d) / 'derived/geo/buildings.sqlite').unlink()
            self.assertIn('buildings', SM.country_coverage(d, CODE))

    def test_country_must_be_opted_in_before_coverage_is_even_considered(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            SM.PUBLISHED_COUNTRIES = {}
            self.assertTrue(SM.country_publish_blockers(d, CODE))
            SM.PUBLISHED_COUNTRIES = {CODE: {}}
            self.assertEqual(SM.country_publish_blockers(d, CODE), [])

    def test_opted_in_but_base_only_country_is_still_refused(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=False)
            SM.PUBLISHED_COUNTRIES = {CODE: {}}
            blockers = SM.country_publish_blockers(d, CODE)
            self.assertTrue(blockers)
            self.assertIn('no roads detail inside the country box', blockers)

    def test_regions_leave_countries_out_until_listed(self):
        SM.states = lambda: ['CA']
        SM.PUBLISHED_COUNTRIES = {}
        self.assertEqual(SM.regions(), ['CA'])
        SM.PUBLISHED_COUNTRIES = {CODE: {}}
        self.assertEqual(SM.regions(), ['CA', CODE])

    def test_publication_allowlist_stays_empty(self):
        self.assertEqual(json.loads((HERE / 'country-publication.json').read_text(encoding='utf-8'))['countries'], {})


class CliCase(unittest.TestCase):
    def _cli(self, args):
        old = sys.argv
        out, err = io.StringIO(), io.StringIO()
        try:
            sys.argv = ['state_maps.py'] + args
            with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                SM.main()
        finally:
            sys.argv = old
        return caught.exception.code, out.getvalue(), err.getvalue()


class ExplicitPublish(CliCase):
    def test_disabled_country_is_refused_before_build_and_publishing_client(self):
        built = []
        old = SM._r2, SM.subprocess.run, SM.PUBLISHED_COUNTRIES
        SM._r2 = lambda: self.fail('the publishing client was opened for an unpublished country')
        SM.subprocess.run = lambda *a, **k: built.append(a)
        SM.PUBLISHED_COUNTRIES = {}
        try:
            code, out, err = self._cli([CODE])
        finally:
            SM._r2, SM.subprocess.run, SM.PUBLISHED_COUNTRIES = old
        self.assertEqual(built, [])
        self.assertEqual(out, '')
        self.assertIn(CODE, str(code))
        self.assertIn('publishing a country is opt-in', str(code))

    def test_opted_in_country_still_proceeds_to_the_publishing_run(self):
        seen = []

        class Client:
            def Context(self):
                return 'ctx'

        old = SM._r2, SM.one_state, SM.PUBLISHED_COUNTRIES, SM.RESULTS
        old_argv = sys.argv
        SM._r2 = lambda: Client()
        SM.one_state = lambda ctx, code, res: seen.append((ctx, code))
        SM.PUBLISHED_COUNTRIES = {CODE: {}}
        try:
            with tempfile.TemporaryDirectory() as d:
                SM.RESULTS = Path(d) / 'results.json'
                sys.argv = ['state_maps.py', CODE]
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    SM.main()
        finally:
            sys.argv = old_argv
            SM._r2, SM.one_state, SM.PUBLISHED_COUNTRIES, SM.RESULTS = old
        self.assertEqual(seen, [('ctx', CODE)])


class DryRun(CliCase):
    def test_ri_is_rejected_before_any_coverage_query(self):
        old = SM.coverage_counts
        SM.coverage_counts = lambda *a, **k: self.fail('coverage was counted for a non-country code')
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = SM.dry_run(['RI'])
        finally:
            SM.coverage_counts = old
        self.assertEqual(rc, 1)
        record = json.loads(out.getvalue())
        self.assertEqual(record['region'], 'RI')
        self.assertEqual(record['coverage'], {})
        self.assertEqual(record['publish_blockers'], ['RI is not a country code'])

    def test_documented_cli_reads_set_folder_after_code_without_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            fixture, artifacts = tree_state(d), artifact_state()
            p = subprocess.run([sys.executable, '-I', '-B', str(HERE / 'state_maps.py'), '--dry-run', CODE, '--set', d],
                               cwd=HERE.parent, capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stderr)
            self.assertNotIn('Traceback', p.stderr)
            record = json.loads(p.stdout)
            self.assertEqual(record['region'], CODE)
            self.assertEqual(record['set'], str(Path(d)))
            self.assertTrue(all(record['coverage'].values()))
            self.assertTrue(record['publish_blockers'])          # the allowlist is still empty
            self.assertEqual(tree_state(d), fixture)
            self.assertEqual(artifact_state(), artifacts)

    def test_set_may_come_before_the_code_or_with_an_equals_sign(self):
        self.assertEqual(SM.dry_run_args(['--set', 'one', CODE]), ([CODE], 'one'))
        self.assertEqual(SM.dry_run_args([CODE, '--set=one']), ([CODE], 'one'))
        self.assertEqual(SM.dry_run_args([CODE]), ([CODE], None))

    def test_cli_rejects_a_repeated_set_with_usage(self):
        old = SM.coverage_counts
        SM.coverage_counts = lambda *a, **k: self.fail('a parse error must not count coverage')
        try:
            code, out, err = self._cli(['--dry-run', CODE, '--set', 'one', '--set', 'two'])
        finally:
            SM.coverage_counts = old
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('--set may be given only once', err)
        self.assertIn('usage:', err)

    def test_cli_rejects_a_set_without_a_folder_with_usage(self):
        code, out, err = self._cli(['--dry-run', '--set'])
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('--set needs a folder', err)
        self.assertIn('usage:', err)

    def test_cli_rejects_a_missing_folder_with_usage(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = self._cli(['--dry-run', CODE, '--set', str(Path(d) / 'missing')])
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('--set folder not found', err)
        self.assertIn('usage:', err)

    def test_cli_rejects_an_unknown_option_with_usage(self):
        code, out, err = self._cli(['--dry-run', CODE, '--bogus'])
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('unknown option', err)
        self.assertIn('usage:', err)

    def test_set_before_dry_run_is_refused_before_the_publishing_client(self):
        opened = []
        old = SM._r2
        SM._r2 = lambda: opened.append('r2')
        try:
            with tempfile.TemporaryDirectory() as d:
                code, out, err = self._cli(['--set', d, '--dry-run', CODE])
        finally:
            SM._r2 = old
        self.assertEqual(code, 2)
        self.assertEqual(opened, [])
        self.assertEqual(out, '')
        self.assertIn('--dry-run must be given first', err)
        self.assertIn('usage:', err)

    def test_one_set_folder_for_several_countries_is_refused_before_publishing(self):
        opened, counts = [], []
        old_r2, old_coverage = SM._r2, SM.coverage_counts
        SM._r2 = lambda: opened.append('r2')
        SM.coverage_counts = lambda *a, **k: counts.append(a) or {}
        try:
            with tempfile.TemporaryDirectory() as d:
                code, out, err = self._cli(['--dry-run', CODE, 'eu-de', '--set', d])
        finally:
            SM._r2, SM.coverage_counts = old_r2, old_coverage
        self.assertEqual(code, 2)
        self.assertEqual(opened, [])
        self.assertEqual(counts, [])
        self.assertEqual(out, '')
        self.assertIn('one --set folder cannot describe more than one country', err)
        self.assertIn('usage:', err)

    def test_bare_dry_run_with_empty_allowlist_reports_no_countries_checked(self):
        old_countries, old_r2, old_coverage = SM.PUBLISHED_COUNTRIES, SM._r2, SM.coverage_counts
        SM.PUBLISHED_COUNTRIES = {}
        SM._r2 = lambda: self.fail('a bare dry run must not open the publishing client')
        SM.coverage_counts = lambda *a, **k: self.fail('a bare dry run has no country to check')
        try:
            code, out, err = self._cli(['--dry-run'])
        finally:
            SM.PUBLISHED_COUNTRIES, SM._r2, SM.coverage_counts = old_countries, old_r2, old_coverage
        self.assertEqual(code, 0)
        self.assertIn('no countries checked', out)
        self.assertEqual(err, '')

    def test_valid_dry_run_still_works_without_the_publishing_client(self):
        with tempfile.TemporaryDirectory() as d:
            make_set(d, detailed=True)
            opened = []
            old = SM._r2
            SM._r2 = lambda: opened.append('r2')
            try:
                code, out, err = self._cli(['--dry-run', CODE, '--set', d])
            finally:
                SM._r2 = old
        self.assertEqual(opened, [])
        self.assertEqual(code, 1)                  # the allowlist is still empty
        self.assertNotIn('Traceback', err)
        record = json.loads(out)
        self.assertEqual(record['region'], CODE)
        self.assertEqual(record['set'], str(Path(d)))
        self.assertTrue(all(record['coverage'].values()))
        self.assertTrue(record['publish_blockers'])


if __name__ == '__main__':
    unittest.main()
