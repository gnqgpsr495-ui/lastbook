"""Confidence intervals and paired before/after tests for score.py outputs written with --rows.

    python -B tools/search_eval/stats.py kw.json                  # one run: every rate with its 95% interval
    python -B tools/search_eval/stats.py before.json after.json   # two runs on the same questions: what changed
    options: --md (markdown tables)  --json FILE (write the numbers)  --seed N (bootstrap seed, default 1)
             --cluster-by topic|persona (what counts as one cluster, see below)

Two levels of analysis, always both.
  Row level ("exploratory, assumes rows independent"): every question is one observation.
  Clustered (the one to quote): questions on the same topic are one cluster and the clusters, not the questions, are
  resampled. A cluster is the original question with all its other phrasings and typo versions (the `topic` field of
  score.py's rows: 159 clusters over the 362 triage questions, 32 over #154's 64, 21 over #128's 52). Questions of the
  independent lists, glued messages, conversations and #241 carry no topic: each is its own cluster, so for them the
  two levels agree up to the method. With --cluster-by persona the lists' own `persona` field is used when a row has
  one (list 3 only), as a sensitivity check.

One run. For each group of questions (a set, split by colour, typo version, counterexample, conversation kind, list
colour), each yes/no measure gets its count, rate and a Wilson 95% interval; "useful of 8" gets its mean and a
percentile bootstrap 95% interval (2,000 resamples of the questions, fixed seed, so the output is the same every run).
The clustered interval is a percentile bootstrap over whole clusters (same seed, same 2,000 resamples; the rate is the
ratio of the resample's hits to its questions). The design effect is the variance of the clustered estimate divided by
the variance the row-level formula assumes (1 = clustering changes nothing, 2 = twice the variance).

Two runs. Questions are matched by set and id (a question whose text differs between the runs is left out and
counted). For a yes/no measure: how many went no -> yes and yes -> no, and the exact McNemar p (two-sided binomial
on those discordant questions only; questions that did not change carry no information about the change). For
"useful of 8": the mean paired difference with a paired bootstrap 95% interval. Clustered: the paired difference
(rate or mean) with a cluster bootstrap interval, and for yes/no measures the clustered McNemar test of Durkalski,
Palesch, Lipsitz and Rust (2003), "Analysis of clustered matched-pair data", Statistics in Medicine 22:2417-2428:
with d_i = (no -> yes) - (yes -> no) counted inside cluster i, chi-square = (sum d_i)^2 / sum (d_i^2), 1 degree of
freedom. With one question per cluster this is the usual McNemar chi-square. The p reported uses the exact
reference distribution of the same statistic (every cluster's sign flipped at random, enumerated exactly), which is the
exact McNemar test when clusters hold one question; the chi-square p is kept in the JSON as `p_asymptotic`.

Sets are tagged "held-out" (list 3, the only data that stayed unseen throughout) or "development" (everything else:
the sets the system was built and tuned on, lists 1 and 2, and list 4 once its results had been read) and reported in
separate sections, never pooled.

How to read it: a group of 5 questions gives an interval about 60 points wide; report it as "3 of 5", not 60%. Groups
under 20 questions, or under 20 clusters for the clustered figures, show counts only (no interval; the exact p-values
of the paired tests are still given). At 0% or 100% (or any measure that
never varies) the bootstrap has no spread: the clustered interval is then "n/a" and the Wilson interval is the one to read.
The p-values are not corrected for the many groups and measures: treat one measure, fixed beforehand (red questions'
first useful page, or red recall of the urgency check), as the main result and the rest as descriptive.
Standard library only.
"""
import argparse
import json
import math
import random
import sys

BINARY = ('first_ok', 'top3_ok', 'covered', 'zero_useful', 'cap_broken', 'wrong_sense_first')
LIST_BINARY = ('pages_shown', 'flagged', 'no_hits')
Z = 1.959963984540054
B = 2000


def wilson(k, n):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_p(b, c):
    """Exact two-sided McNemar: binomial(b + c, 1/2), probability of a split at least this uneven."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def boot_mean(xs, rng):
    n = len(xs)
    if n == 0:
        return (float('nan'), float('nan'))
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return (means[int(0.025 * B)], means[int(0.975 * B) - 1])


HELD_OUT = ('list3',)     # the only data that stayed unseen throughout; every other set is development data
MIN_N = 20                # fewer questions (or clusters, for the clustered figures): counts only
ROW_LABEL = 'exploratory (assumes rows independent)'
CLUSTER_LABEL = 'clustered by topic'


def status(set_name):
    return 'held-out' if set_name in HELD_OUT else 'development'


def cluster_key(r, by='topic'):
    """The cluster a question belongs to: its topic (the original question and every phrasing and typo version of it),
    else the question alone. by='persona': a list line's persona when it has one."""
    if by == 'persona' and r.get('persona'):
        return (r['set'], 'persona', r['persona'])
    if r.get('topic'):
        return (r['set'], r['topic'])
    return (r['set'], r['id'])


def cluster_boot(nums, dens, rng):
    """Cluster bootstrap of several ratio statistics at once. nums[t][c], dens[t][c]: numerator and denominator of
    statistic t in cluster c (clusters in order of first appearance). Each resample draws as many whole clusters as
    there are, with replacement, and every statistic is the ratio of its sums over the drawn clusters. Returns, per
    statistic, (95% percentile interval, variance of the resampled values). With one question per cluster, the same
    seed and the same order, this draws exactly what boot_mean draws."""
    nan = float('nan')
    m = len(nums[0]) if nums else 0
    if m == 0:
        return [((nan, nan), nan) for _ in nums]
    vals = [[] for _ in nums]
    for _ in range(B):
        idx = [rng.randrange(m) for _ in range(m)]
        for t in range(len(nums)):
            d = sum(map(dens[t].__getitem__, idx))
            if d:
                vals[t].append(sum(map(nums[t].__getitem__, idx)) / d)
    out = []
    for v in vals:
        if len(v) < 2:
            out.append(((nan, nan), nan))
            continue
        v.sort()
        mean = sum(v) / len(v)
        var = sum((x - mean) ** 2 for x in v) / (len(v) - 1)
        out.append(((v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]), var))
    return out


def row_variance(xs):
    """Variance of the mean of xs if the rows were independent (the formula the row-level interval rests on)."""
    n = len(xs)
    if n < 2:
        return float('nan')
    mu = sum(xs) / n
    return sum((x - mu) ** 2 for x in xs) / (n - 1) / n


def deff(var_cluster, var_row):
    """Design effect: variance with the clusters taken into account over the variance assuming independent rows."""
    ok = var_row == var_row and var_cluster == var_cluster and var_row > 0
    return var_cluster / var_row if ok else float('nan')


def sign_flip_p(d):
    """Exact two-sided p for sum(d) when each cluster's difference d[i] is equally likely to be + or - (the null: a
    question is as likely to go no -> yes as yes -> no). Counts the 2^k sign patterns of the k non-zero clusters
    whose |sum| is at least the observed one. Same statistic as Durkalski et al.'s (sum d)^2 / sum d^2 (the
    denominator does not change when signs flip), with its exact reference distribution instead of chi-square.
    With one question per cluster it is the exact McNemar test."""
    mags = [abs(x) for x in d if x]
    obs = abs(sum(d))
    dist = {0: 1}
    for m in mags:
        nxt = {}
        for s, c in dist.items():
            nxt[s + m] = nxt.get(s + m, 0) + c
            nxt[s - m] = nxt.get(s - m, 0) + c
        dist = nxt
    tail = sum(c for s, c in dist.items() if abs(s) >= obs)
    return min(1.0, tail / 2 ** len(mags))


def durkalski(d):
    """Clustered McNemar (Durkalski, Palesch, Lipsitz, Rust 2003, Stat Med 22:2417-2428). d[i] = (no -> yes) minus
    (yes -> no) among cluster i's matched questions. chi-square = (sum d)^2 / sum d^2 on 1 degree of freedom, two-sided
    p = erfc(sqrt(chi-square / 2)); with one question per cluster this is the usual McNemar chi-square
    (b - c)^2 / (b + c). That p is asymptotic and too small when few clusters changed (5 against 0 gives 0.025, the
    exact McNemar 0.0625), so the p reported is the exact one from sign_flip_p for the same statistic.
    Returns (chi-square, exact p, asymptotic p, number of clusters with d != 0, sum d^2)."""
    s, ss = sum(d), sum(x * x for x in d)
    disc = sum(1 for x in d if x)
    if ss == 0:
        return 0.0, 1.0, 1.0, 0, 0
    chi = s * s / ss
    return chi, sign_flip_p(d), math.erfc(math.sqrt(chi / 2)), disc, ss


def value(r, m):
    if m == 'zero_useful':
        return r.get('useful') == 0 if 'useful' in r else None
    if m == 'no_hits':
        return r.get('n_hits') == 0
    v = r.get(m)
    return None if v is None else bool(v)


def groups(rows):
    """(name, rows) for every group reported; a row can be in several groups."""
    out = {}

    def add(name, r):
        out.setdefault(name, []).append(r)
    for r in rows:
        s = r['set']
        if s.startswith('list'):
            add(f'{s} {r["triage"]}', r)
            if r['triage'] == 'green' and r.get('counter'):
                add(f'{s} green counterexamples', r)
            if s == 'list4':
                add(f'{s} {r["triage"]} ({r.get("lang", "en")[:2]})', r)
            continue
        if s == 'glued':
            if 'useful' in r:
                add(f'glued {r["kind"]}', r)
            continue
        if s == 'conversations':
            add('conversations all', r)
            add(f'conversations {r["kind"]}', r)
            continue
        if r.get('typo'):
            add(f'{s} typos', r)
            continue
        add(f'{s} clean', r)
        if r.get('counter'):          # as score.py's by_colour: counterexamples apart, not in their colour
            add(f'{s} counterexamples', r)
        elif r.get('colour'):
            add(f'{s} {r["colour"]}', r)
    return out


def measures(rs):
    if rs and rs[0]['set'].startswith('list'):
        return [m for m in LIST_BINARY if any(r.get(m) is not None for r in rs) or m == 'no_hits'], False
    return list(BINARY), True


def pct(x):
    return 'nan' if x != x else f'{100 * x:.0f}'


def labels(by):
    what = ('the original question and all its other phrasings and typo versions (rows without a topic: the question '
            'alone)') if by == 'topic' else "the list line's persona (rows without one: the line alone)"
    return {'row_level': ROW_LABEL, 'clustered': f'cluster bootstrap, one cluster = {what}',
            'held_out_sets': list(HELD_OUT), 'other_sets': 'development', 'min_n': MIN_N}


def one(rows, rng, crng=None, by='topic'):
    """Per group: row-level figures (Wilson, bootstrap of the questions) and clustered figures (bootstrap of clusters,
    a separate random stream so the row-level numbers do not depend on it)."""
    crng = crng or random.Random(1)
    res = {'_labels': labels(by)}
    for name, rs in sorted(groups(rows).items()):
        ms, has_useful = measures(rs)
        keys = list(dict.fromkeys(cluster_key(r, by) for r in rs))
        pos = {k: i for i, k in enumerate(keys)}
        K = len(keys)
        g = {'n': len(rs), 'clusters': K, 'set': rs[0]['set'], 'status': status(rs[0]['set']),
             'counts_only': len(rs) < MIN_N}
        stat = []                      # (key, cluster numerators, cluster denominators, variance if rows independent)
        for m in ms:
            vv = [(value(r, m), pos[cluster_key(r, by)]) for r in rs]
            vv = [(v, c) for v, c in vv if v is not None]
            if not vv:
                continue
            vals = [v for v, _ in vv]
            k = sum(vals)
            lo, hi = wilson(k, len(vals))
            g[m] = {'k': k, 'n': len(vals), 'rate': k / len(vals), 'ci': [lo, hi]}
            num, den = [0] * K, [0] * K
            for v, c in vv:
                num[c] += v
                den[c] += 1
            stat.append((m, num, den, row_variance([int(v) for v in vals])))
        if has_useful:
            u = [r['useful'] for r in rs]
            g['useful'] = {'mean': sum(u) / len(u), 'ci': list(boot_mean(u, rng))}
            num, den = [0] * K, [0] * K
            for r in rs:
                num[pos[cluster_key(r, by)]] += r['useful']
                den[pos[cluster_key(r, by)]] += 1
            stat.append(('useful', num, den, row_variance(u)))
        run = len(rs) >= MIN_N and K >= MIN_N and stat
        boots = cluster_boot([x[1] for x in stat], [x[2] for x in stat], crng) if run else [None] * len(stat)
        for (key, num, den, var_row), b in zip(stat, boots):
            c = {'n_clusters': sum(1 for d in den if d), 'ci': None, 'deff': None}
            if b and b[1] > 0:       # no spread at 0% or 100% (or all equal): the percentile bootstrap says nothing
                c['ci'], c['deff'] = list(b[0]), deff(b[1], var_row)
            g[key]['cluster'] = c
        res[name] = g
    return res


def two(before, after, rng, crng=None, by='topic'):
    crng = crng or random.Random(1)
    a = {(r['set'], r['id']): r for r in before}
    b = {(r['set'], r['id']): r for r in after}
    keys = [k for k in a if k in b]
    differ = [k for k in keys if a[k].get('q') != b[k].get('q')]
    keys = [k for k in keys if k not in set(differ)]
    pairs = [(a[k], b[k]) for k in keys]
    res = {'_labels': labels(by), '_matched': len(keys), '_text_differs': len(differ),
           '_only_before': len(set(a) - set(b)), '_only_after': len(set(b) - set(a))}
    by_group = groups([p[1] for p in pairs])
    lookup = {id(p[1]): p for p in pairs}
    for name, rs in sorted(by_group.items()):
        ps = [lookup[id(r)] for r in rs]
        ms, has_useful = measures(rs)
        ck = [cluster_key(y, by) for _, y in ps]
        pos = {k: i for i, k in enumerate(dict.fromkeys(ck))}
        cid = [pos[k] for k in ck]
        K = len(pos)
        g = {'n': len(ps), 'clusters': K, 'set': rs[0]['set'], 'status': status(rs[0]['set']),
             'counts_only': len(ps) < MIN_N}
        stat = []                      # (key, cluster numerators of the difference, denominators, row variance)
        for m in ms:
            vv = [(value(x, m), value(y, m), c) for (x, y), c in zip(ps, cid)]
            vv = [(x, y, c) for x, y, c in vv if x is not None and y is not None]
            if not vv:
                continue
            up = sum(1 for x, y, _ in vv if not x and y)
            down = sum(1 for x, y, _ in vv if x and not y)
            g[m] = {'before': sum(x for x, _, _ in vv), 'after': sum(y for _, y, _ in vv), 'n': len(vv),
                    'no_to_yes': up, 'yes_to_no': down, 'p': mcnemar_p(up, down)}
            d, den = [0] * K, [0] * K
            for x, y, c in vv:
                d[c] += int(y) - int(x)
                den[c] += 1
            chi, pc, pa, disc, ss = durkalski(d)
            n_cl = sum(1 for t in den if t)
            g[m]['cluster'] = {'n_clusters': n_cl, 'clusters_changed': disc, 'chi2': chi,
                               'p_asymptotic': pa, 'p': pc,
                               'deff_mcnemar': ss / (up + down) if up + down else None, 'diff_ci': None, 'deff': None}
            stat.append((m, d, den, row_variance([int(y) - int(x) for x, y, _ in vv])))
        if has_useful:
            dd = [y['useful'] - x['useful'] for x, y in ps]
            g['useful'] = {'before': sum(x['useful'] for x, _ in ps) / len(ps),
                           'after': sum(y['useful'] for _, y in ps) / len(ps),
                           'diff': sum(dd) / len(dd), 'ci': list(boot_mean(dd, rng)),
                           'cluster': {'n_clusters': K, 'ci': None, 'deff': None}}
            num, den = [0] * K, [0] * K
            for t, c in zip(dd, cid):
                num[c] += t
                den[c] += 1
            stat.append(('useful', num, den, row_variance(dd)))
        run = len(ps) >= MIN_N and K >= MIN_N and stat
        boots = cluster_boot([x[1] for x in stat], [x[2] for x in stat], crng) if run else [None] * len(stat)
        for (key, num, den, var_row), bt in zip(stat, boots):
            if bt and bt[1] > 0:
                c = g[key]['cluster']
                c['ci' if key == 'useful' else 'diff_ci'] = list(bt[0])
                c['deff'] = deff(bt[1], var_row)
        res[name] = g
    return res


def fmt_ci(ci, f):
    return 'n/a' if not ci else f'[{f(ci[0])}-{f(ci[1])}]'


def fmt_deff(d):
    return 'n/a' if d is None or d != d else f'{d:.2f}'


def sections(res):
    """Group names under 'held-out' and 'development' (never pooled), held-out first."""
    out = {'held-out': [], 'development': []}
    for name, g in res.items():
        if not name.startswith('_'):
            out[g['status']].append((name, g))
    return [(k, v) for k, v in out.items() if v]


def head(md, st, lab):
    set_names = sorted({g['set'] for _, g in st[1]})
    text = (f'{st[0]} ({", ".join(set_names)}): row-level figures are {lab["row_level"]}; '
            f'clustered figures: {lab["clustered"]}')
    print(('\n### ' if md else '\n== ') + text + ('' if md else ' =='))


def show_one(res, md):
    sep = ' | ' if md else '  '
    for st in sections(res):
        head(md, st, res['_labels'])
        for name, g in st[1]:
            cells = [f'{name} (n={g["n"]}, clusters={g["clusters"]})']
            small = g['counts_only']
            if 'useful' in g:
                u = g['useful']
                two_dec = '{:.2f}'.format
                cells.append(f'useful {u["mean"]:.2f}' if small else
                             f'useful {u["mean"]:.2f} row {fmt_ci(u["ci"], two_dec)}, clustered '
                             f'{fmt_ci(u["cluster"]["ci"], two_dec)} deff {fmt_deff(u["cluster"]["deff"])}')
            for m, v in g.items():
                if isinstance(v, dict) and 'k' in v:
                    cell = f'{m} {v["k"]}/{v["n"]}'
                    if not small:
                        cl = v['cluster']
                        cell += (f' {pct(v["rate"])}% row [{pct(v["ci"][0])}-{pct(v["ci"][1])}], clustered '
                                 f'{fmt_ci(cl["ci"], pct)} deff {fmt_deff(cl["deff"])}')
                    cells.append(cell)
            print(('| ' if md else '') + sep.join(cells) + (' |' if md else ''))
    print('Groups under 20 questions (or 20 clusters, for clustered figures): counts only. Clustered n/a: no spread (0% or 100%). deff = variance with '
          'clusters / variance if rows were independent.')


def show_two(res, md, alpha=0.05):
    print(f'matched {res["_matched"]} questions; text differs {res["_text_differs"]}, only before '
          f'{res["_only_before"]}, only after {res["_only_after"]} (left out)')
    sep = ' | ' if md else '  '
    for st in sections(res):
        head(md, st, res['_labels'])
        for name, g in st[1]:
            cells = [f'{name} (n={g["n"]}, clusters={g["clusters"]})']
            small = g['counts_only']
            if 'useful' in g:
                u = g['useful']
                c = u['cluster']
                cell = f'useful {u["before"]:.2f}->{u["after"]:.2f} diff {u["diff"]:+.2f}'
                if not small:
                    cell += (f' row [{u["ci"][0]:+.2f} to {u["ci"][1]:+.2f}], clustered '
                             + ('n/a' if not c['ci'] else f'[{c["ci"][0]:+.2f} to {c["ci"][1]:+.2f}]')
                             + f' deff {fmt_deff(c["deff"])}')
                cells.append(cell)
            for m, v in g.items():
                if isinstance(v, dict) and 'no_to_yes' in v:
                    c = v['cluster']
                    mark = ' *' if v['p'] < alpha else ''
                    cell = f'{m} {v["before"]}->{v["after"]} (+{v["no_to_yes"]}/-{v["yes_to_no"]}, row p={v["p"]:.3g}){mark}'
                    if c['p'] is None:
                        cell += ' clustered p n/a'
                    else:
                        cell += (f' clustered p={c["p"]:.3g}{" *" if c["p"] < alpha else ""} '
                                 f'({c["clusters_changed"]} clusters changed, deff {fmt_deff(c["deff_mcnemar"])})')
                    cells.append(cell)
            print(('| ' if md else '') + sep.join(cells) + (' |' if md else ''))
    print('* p < 0.05, uncorrected for the number of groups and measures. Row p: exact McNemar, exploratory (assumes '
          'rows independent). Clustered p: Durkalski et al. 2003 statistic with its exact sign-flip distribution. '
          'Groups under 20 questions or clusters: no intervals (the exact p-values are still given).')


def load(path):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    if 'rows' not in d:
        sys.exit(f'{path}: no per-question rows; run score.py with --rows')
    return d['rows']


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('runs', nargs='+', help='one or two score.py outputs written with --rows')
    ap.add_argument('--md', action='store_true')
    ap.add_argument('--json')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--cluster-by', choices=('topic', 'persona'), default='topic')
    a = ap.parse_args()
    if len(a.runs) > 2:
        ap.error('one or two runs')
    rng, crng = random.Random(a.seed), random.Random(a.seed)
    if len(a.runs) == 1:
        res = one(load(a.runs[0]), rng, crng, a.cluster_by)
        show_one(res, a.md)
    else:
        res = two(load(a.runs[0]), load(a.runs[1]), rng, crng, a.cluster_by)
        show_two(res, a.md)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=1)


if __name__ == '__main__':
    main()
