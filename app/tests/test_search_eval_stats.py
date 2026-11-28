#!/usr/bin/env python3
"""tools/search_eval/stats.py on made-up score.py rows: no library, no model.

  python3 -B -m unittest app.tests.test_search_eval_stats

Checks the interval and test formulas against values worked out by hand, and that questions are grouped and paired the
way score.py counts them.
"""
import json, math, random, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'search_eval'))
import stats  # noqa: E402


def row(i, colour='red', first=True, useful=5, counter=False, typo=False, q=None):
    return {'set': 'triage', 'id': f'{i:03d}', 'q': q or f'question {i}', 'colour': colour, 'counter': counter,
            'typo': typo, 'useful': useful, 'first_ok': first, 'top3_ok': first, 'covered': first,
            'cap_broken': False, 'wrong_sense_first': False, 'n_hits': 8}


class Formulas(unittest.TestCase):
    def test_wilson(self):
        lo, hi = stats.wilson(88, 131)       # worked by hand: 0.5875 to 0.7463
        self.assertAlmostEqual(lo, 0.5875, places=4)
        self.assertAlmostEqual(hi, 0.7463, places=4)
        lo, hi = stats.wilson(0, 5)          # no event in 5: from 0 up to about 43%
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.4345, places=4)
        lo, hi = stats.wilson(131, 131)
        self.assertEqual(hi, 1.0)
        self.assertGreater(lo, 0.97)

    def test_mcnemar_exact(self):
        self.assertAlmostEqual(stats.mcnemar_p(10, 2), 0.0386, places=4)   # 2 * P(X <= 2), X ~ Bin(12, 1/2)
        self.assertEqual(stats.mcnemar_p(0, 0), 1.0)
        self.assertEqual(stats.mcnemar_p(3, 3), 1.0)
        self.assertAlmostEqual(stats.mcnemar_p(5, 0), 0.0625, places=4)
        self.assertEqual(stats.mcnemar_p(1, 4), stats.mcnemar_p(4, 1))

    def test_bootstrap_is_fixed_by_seed(self):
        xs = [0, 1, 2, 3, 8, 8, 5, 4]
        a = stats.boot_mean(xs, random.Random(1))
        b = stats.boot_mean(xs, random.Random(1))
        self.assertEqual(a, b)
        self.assertLessEqual(a[0], sum(xs) / len(xs))
        self.assertGreaterEqual(a[1], sum(xs) / len(xs))
        self.assertEqual(stats.boot_mean([3, 3, 3], random.Random(1)), (3.0, 3.0))


class Grouping(unittest.TestCase):
    def test_counterexamples_and_typos_apart_as_in_score(self):
        rows = [row(0), row(1, 'green'), row(2, 'green', counter=True), row(3, typo=True)]
        g = stats.groups(rows)
        self.assertEqual(len(g['triage red']), 1)            # the typo version is not a clean red question
        self.assertEqual(len(g['triage green']), 1)          # the counterexample is not counted with its colour
        self.assertEqual(len(g['triage counterexamples']), 1)
        self.assertEqual(len(g['triage typos']), 1)
        self.assertEqual(len(g['triage clean']), 3)

    def test_lists_by_colour_with_language_for_list4(self):
        rows = [{'set': 'list4', 'id': 'list4.000', 'q': 'x', 'triage': 'red', 'lang': 'es', 'counter': False,
                 'flagged': True, 'pages_shown': True, 'n_hits': 3}]
        g = stats.groups(rows)
        self.assertIn('list4 red', g)
        self.assertIn('list4 red (es)', g)
        res = stats.one(rows, random.Random(1))
        self.assertEqual(res['list4 red']['flagged']['k'], 1)


class Paired(unittest.TestCase):
    def test_flips_counted_and_changed_text_left_out(self):
        before = [row(i, first=i < 5) for i in range(10)] + [row(10, q='old wording')]
        after = [row(i, first=i < 8) for i in range(10)] + [row(10, q='new wording')]
        res = stats.two(before, after, random.Random(1))
        self.assertEqual(res['_matched'], 10)
        self.assertEqual(res['_text_differs'], 1)
        f = res['triage red']['first_ok']
        self.assertEqual((f['before'], f['after'], f['no_to_yes'], f['yes_to_no']), (5, 8, 3, 0))
        self.assertAlmostEqual(f['p'], 0.25, places=6)
        self.assertEqual(res['triage red']['useful']['diff'], 0.0)

    def test_command_line_needs_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'summary-only.json'
            p.write_text(json.dumps({'summary': {}}), encoding='utf-8')
            r = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'search_eval' / 'stats.py'), str(p)],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('--rows', r.stderr)

    def test_command_line_two_runs(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.json', Path(d) / 'b.json'
            a.write_text(json.dumps({'rows': [row(i, first=i < 2) for i in range(6)]}), encoding='utf-8')
            b.write_text(json.dumps({'rows': [row(i, first=i < 4) for i in range(6)]}), encoding='utf-8')
            r = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'search_eval' / 'stats.py'), str(a), str(b)],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('first_ok 2->4 (+2/-0, row p=0.5)', r.stdout)


def trow(topic, k, first, set_='triage', typo=False, useful=None):
    """A question that belongs to a topic (a cluster); useful follows first unless given."""
    r = row(k, first=first, typo=typo, useful=(5 if first else 1) if useful is None else useful)
    r.update(set=set_, topic=topic, id=f'{topic}.{k}')
    return r


class Clustered(unittest.TestCase):
    def test_cluster_bootstrap_equals_row_bootstrap_when_clusters_are_single_questions(self):
        xs = [0, 1, 2, 3, 8, 8, 5, 4, 1, 0, 2, 7]
        row_ci = stats.boot_mean(xs, random.Random(1))
        (ci, var), = stats.cluster_boot([xs], [[1] * len(xs)], random.Random(1))
        self.assertEqual(ci, row_ci)
        self.assertGreater(var, 0)

    def test_duplicated_rows_make_the_clustered_interval_wider(self):
        # 30 topics, each asked twice with the same result: 60 rows, but only 30 independent observations
        rows = [trow(f't{i}', j, first=i % 2 == 0) for i in range(30) for j in range(2)]
        g = stats.one(rows, random.Random(1))['triage clean']
        f = g['first_ok']
        self.assertEqual((g['n'], g['clusters'], f['k']), (60, 30, 30))
        row_w = f['ci'][1] - f['ci'][0]
        cl_w = f['cluster']['ci'][1] - f['cluster']['ci'][0]
        self.assertGreater(cl_w, 1.15 * row_w)
        self.assertGreater(f['cluster']['deff'], 1.5)       # two identical copies: variance twice as large
        self.assertLess(f['cluster']['deff'], 2.6)
        # the same questions as single clusters: no widening
        solo = [trow(f't{i}', 0, first=i % 2 == 0) for i in range(60)]
        f1 = stats.one(solo, random.Random(1))['triage clean']['first_ok']
        self.assertLess(abs(f1['cluster']['deff'] - 1), 0.25)

    def test_typo_version_is_in_its_originals_cluster(self):
        rows = [trow('fire', 0, True), trow('fire', 1, False, typo=True), trow('fire', 2, True, typo=True), trow('burn', 0, True)]
        keys = [stats.cluster_key(r) for r in rows]
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[1], keys[2])
        self.assertNotEqual(keys[0], keys[3])
        self.assertEqual(stats.one(rows, random.Random(1))['triage typos']['clusters'], 1)
        lst = {'set': 'list3', 'id': 'list3.001', 'q': 'x', 'triage': 'red', 'persona': 'teen'}
        self.assertEqual(stats.cluster_key(lst)[1], 'list3.001')           # lists: the line alone by default
        self.assertEqual(stats.cluster_key(lst, 'persona')[2], 'teen')

    def test_fewer_than_20_clusters_counts_only(self):
        rows = [trow(f't{i}', j, first=j == 0) for i in range(8) for j in range(3)]    # 24 rows, 8 clusters
        g = stats.one(rows, random.Random(1))['triage clean']
        self.assertEqual((g['n'], g['clusters']), (24, 8))
        self.assertIsNone(g['first_ok']['cluster']['ci'])
        self.assertEqual(g['first_ok']['cluster']['n_clusters'], 8)

    def test_clustered_mcnemar_by_hand(self):
        # Cluster differences d = (no -> yes) - (yes -> no): +2, +1, -1, 0.
        # sum d = 2, sum d^2 = 6, chi-square = 4/6; asymptotic p = erfc(sqrt(1/3)) = 0.4142.
        # Exact: signs of |d| = (2, 1, 1) give sums 4, 2, 2, 0, 0, -2, -2, -4; |sum| >= 2 in 6 of 8: p = 0.75.
        chi, p, pa, disc, ss = stats.durkalski([2, 1, -1, 0])
        self.assertAlmostEqual(chi, 4 / 6, places=9)
        self.assertAlmostEqual(pa, math.erfc(math.sqrt(1 / 3)), places=9)
        self.assertAlmostEqual(pa, 0.4142, places=3)
        self.assertEqual((p, disc, ss), (0.75, 3, 6))
        # one question per cluster: the exact McNemar test, and the usual chi-square
        d = [1] * 10 + [-1] * 2 + [0] * 5
        chi, p, pa, disc, ss = stats.durkalski(d)
        self.assertAlmostEqual(p, stats.mcnemar_p(10, 2), places=12)
        self.assertAlmostEqual(chi, (10 - 2) ** 2 / 12, places=9)
        self.assertAlmostEqual(stats.sign_flip_p([1] * 5), stats.mcnemar_p(5, 0), places=12)

    def test_clustered_mcnemar_is_less_certain_when_changes_come_in_clusters(self):
        # 12 changes no -> yes, all inside 3 topics (4 each), the other 22 topics unchanged: not like 12 independent ones
        before = [trow(f't{i}', j, first=False) for i in range(25) for j in range(4)]
        after = [trow(f't{i}', j, first=i < 3) for i in range(25) for j in range(4)]
        g = stats.two(before, after, random.Random(1))['triage clean']['first_ok']
        self.assertEqual((g['no_to_yes'], g['yes_to_no']), (12, 0))
        self.assertLess(g['p'], 0.001)                              # row level: 12 against 0
        self.assertAlmostEqual(g['cluster']['p'], 0.25, places=9)   # clustered: 3 clusters of 4, all the same way
        self.assertEqual(g['cluster']['clusters_changed'], 3)
        self.assertAlmostEqual(g['cluster']['deff_mcnemar'], 4.0, places=9)    # sum d^2 = 48 over b + c = 12

    def test_output_carries_the_labels_and_keeps_held_out_apart(self):
        held = [trow(f'h{i}', 0, first=i < 10, set_='list3') for i in range(30)]
        for r in held:
            r.update(triage='red', pages_shown=r['first_ok'], n_hits=8)
        dev = [trow(f't{i}', j, first=i % 3 > 0) for i in range(25) for j in range(2)]
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / 'a.json'
            a.write_text(json.dumps({'rows': held + dev}), encoding='utf-8')
            out = {}
            for flag in ([], ['--md']):
                r = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / 'search_eval' / 'stats.py'), str(a),
                                    '--json', str(Path(d) / 'o.json')] + flag, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(r.returncode, 0, r.stderr)
                out[bool(flag)] = r.stdout
            for text in out.values():
                self.assertIn('exploratory (assumes rows independent)', text)
                self.assertIn('held-out (list3)', text)
                self.assertIn('development (triage)', text)
                self.assertLess(text.index('held-out'), text.index('development'))
                self.assertIn('clusters=', text)
                self.assertIn('deff', text)
            self.assertIn('### held-out', out[True])
            res = json.loads((Path(d) / 'o.json').read_text(encoding='utf-8'))
            self.assertEqual(res['_labels']['row_level'], 'exploratory (assumes rows independent)')
            self.assertEqual(res['list3 red']['status'], 'held-out')
            self.assertEqual(res['triage red']['status'], 'development')
            self.assertEqual(res['triage red']['clusters'], 25)
        # separate sections, never one pooled line
        self.assertEqual([k for k, _ in stats.sections(stats.one(held + dev, random.Random(1)))], ['held-out', 'development'])


if __name__ == '__main__':
    unittest.main()
