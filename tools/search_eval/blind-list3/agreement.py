#!/usr/bin/env python3
"""Agreement between two blind labellers of list 3, and our labels against the consensus.

Pure Python 3, no dependencies. All files are read and written as UTF-8
(a BOM in .csv files saved by Excel is accepted).

Label files (.tsv or .csv, one header line) need the columns `id` and `label`;
the label is red / yellow / green (case does not matter; r / y / g also work).
Other columns (text, note) are ignored when reading, except that `text` is copied
into the disagreement file.

Usage:
  python agreement.py --a A-filled.tsv --b B-filled.tsv [--outdir results]
      percent agreement, Cohen's kappa (unweighted and linearly weighted), the 3x3 table,
      and results/disagreements.tsv for the adjudicator (the two labels and the line only)
  python agreement.py --a ... --b ... --adjudication adjudicated.tsv
      adds the consensus (agreed label, or the adjudicator's `final_label`) and writes
      results/consensus.tsv and results/adjudications.tsv (both original labels recorded)
  python agreement.py ... --adjudication adjudicated.tsv --key list3-key.tsv [--flags flags.tsv]
      scores OUR original labels against the consensus; with --flags (columns id, flagged
      = 0/1, e.g. whether the search called the line urgent) also red recall and the
      share of consensus-green lines flagged.
  python agreement.py --selftest

Confidence intervals: percentile bootstrap over lines, 2,000 resamples, fixed seed
(--seed, default 20261124), 95 %. Primary statistic: linearly weighted kappa
(red/yellow/green are ordered); unweighted kappa and raw percent agreement are always
reported next to it, plus kappa for red versus not red.
"""
import argparse
import csv
import io
import math
import os
import random
import sys
import tempfile

LABELS = ["red", "yellow", "green"]
IDX = {l: i for i, l in enumerate(LABELS)}
ALIASES = {"r": "red", "y": "yellow", "g": "green"}
N_BOOT = 2000


# ---------------------------------------------------------------- reading / writing
def norm_label(x):
    x = (x or "").strip().lower()
    return ALIASES.get(x, x)


def read_table(path):
    """Return (list of dict rows). .csv is comma or semicolon separated, else tab."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        data = f.read()
    if path.lower().endswith(".csv"):
        first = data.split("\n", 1)[0]
        delim = ";" if first.count(";") > first.count(",") else ","
    else:
        delim = "\t"
    rd = csv.DictReader(io.StringIO(data, newline=""), delimiter=delim)
    rd.fieldnames = [(h or "").strip().lower() for h in rd.fieldnames or []]
    return [{k: (v or "").strip() for k, v in row.items() if k is not None} for row in rd]


def read_labels(path, col="label"):
    rows = read_table(path)
    out, texts, bad, dup = {}, {}, [], []
    for r in rows:
        i = r.get("id", "")
        if not i:
            continue
        lab = norm_label(r.get(col, ""))
        if i in out:
            dup.append(i)
        if lab == "":
            continue  # not labelled yet
        if lab not in IDX:
            bad.append((i, r.get(col, "")))
            continue
        out[i] = lab
        texts[i] = r.get("text", "")
    if dup:
        raise SystemExit(f"{path}: duplicate ids, e.g. {dup[:3]}")
    if bad:
        raise SystemExit(f"{path}: {len(bad)} labels are not red/yellow/green, e.g. {bad[:5]}")
    return out, texts, len(rows)


def write_tsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in r) + "\n")


# ---------------------------------------------------------------- statistics
def table_of(pairs, k=3):
    t = [[0] * k for _ in range(k)]
    for a, b in pairs:
        t[a][b] += 1
    return t


def kappa_from_table(t, weighted):
    k = len(t)
    n = sum(map(sum, t))
    if n == 0:
        return float("nan")
    rows = [sum(t[i]) / n for i in range(k)]
    cols = [sum(t[i][j] for i in range(k)) / n for j in range(k)]
    # linear agreement weights: 1 on the diagonal, 1 - |i-j|/(k-1) off it; identity if unweighted
    def w(i, j):
        return 1.0 - abs(i - j) / (k - 1) if weighted else (1.0 if i == j else 0.0)
    po = sum(w(i, j) * t[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k))
    if abs(1 - pe) < 1e-12:
        return float("nan")  # no variation: kappa undefined
    return (po - pe) / (1 - pe)


def percent_agree(t):
    n = sum(map(sum, t))
    return sum(t[i][i] for i in range(len(t))) / n if n else float("nan")


def collapse_red(t):
    """3x3 -> 2x2, red vs not red."""
    r = [[t[0][0], sum(t[0][1:])],
         [sum(t[i][0] for i in (1, 2)), sum(t[i][j] for i in (1, 2) for j in (1, 2))]]
    return r


def bootstrap(pairs, stat, seed, n_boot=N_BOOT):
    """Percentile 95 % interval of stat(table) over resampled lines."""
    rng = random.Random(seed)
    n = len(pairs)
    vals = []
    for _ in range(n_boot):
        t = [[0] * 3 for _ in range(3)]
        for _ in range(n):
            a, b = pairs[rng.randrange(n)]
            t[a][b] += 1
        v = stat(t)
        if not math.isnan(v):
            vals.append(v)
    if len(vals) < n_boot * 0.9:
        return (float("nan"), float("nan"))
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
    return lo, hi


def summarize(pairs, seed):
    t = table_of(pairs)
    stats = {
        "n": len(pairs),
        "table": t,
        "percent": (percent_agree(t), *bootstrap(pairs, percent_agree, seed)),
        "kappa_weighted": (kappa_from_table(t, True),
                           *bootstrap(pairs, lambda x: kappa_from_table(x, True), seed)),
        "kappa": (kappa_from_table(t, False),
                  *bootstrap(pairs, lambda x: kappa_from_table(x, False), seed)),
        "kappa_red": (kappa_from_table(collapse_red(t), False),
                      *bootstrap(pairs, lambda x: kappa_from_table(collapse_red(x), False), seed)),
    }
    return stats


def fmt(v, pct=False):
    if any(isinstance(x, float) and math.isnan(x) for x in v):
        return "undefined"
    if pct:
        return f"{100*v[0]:.1f}% (95% CI {100*v[1]:.1f}-{100*v[2]:.1f}%)"
    return f"{v[0]:.3f} (95% CI {v[1]:.3f}-{v[2]:.3f})"


def report(title, s, row_name, col_name):
    out = [f"== {title}  (n = {s['n']})",
           f"percent agreement          : {fmt(s['percent'], True)}",
           f"weighted kappa (PRIMARY)   : {fmt(s['kappa_weighted'])}   linear weights, red-yellow-green ordered",
           f"unweighted kappa           : {fmt(s['kappa'])}",
           f"kappa, red vs not red      : {fmt(s['kappa_red'])}",
           f"intervals: percentile bootstrap over lines, {N_BOOT} resamples",
           "",
           f"rows = {row_name}, columns = {col_name}",
           "            " + "".join(f"{l:>8}" for l in LABELS) + "   total"]
    for i, l in enumerate(LABELS):
        out.append(f"{l:<12}" + "".join(f"{c:>8}" for c in s["table"][i]) + f"{sum(s['table'][i]):>8}")
    out.append(f"{'total':<12}" + "".join(f"{sum(s['table'][i][j] for i in range(3)):>8}" for j in range(3))
               + f"{s['n']:>8}")
    return "\n".join(out)


# ---------------------------------------------------------------- main workflow
def run(a_path, b_path, outdir, adj_path=None, key_path=None, flags_path=None, seed=20261124):
    os.makedirs(outdir, exist_ok=True)
    la, ta, na = read_labels(a_path)
    lb, tb, nb = read_labels(b_path)
    ids = sorted(set(la) & set(lb))
    lines = []
    if len(la) < na or len(lb) < nb:
        lines.append(f"NOTE: unlabelled lines: A {na - len(la)}, B {nb - len(lb)} (left out)")
    only = (set(la) ^ set(lb))
    if only:
        lines.append(f"NOTE: {len(only)} ids are labelled in one file only (left out)")
    if not ids:
        raise SystemExit("no ids labelled in both files")
    texts = {i: (ta.get(i) or tb.get(i) or "") for i in ids}

    pairs = [(IDX[la[i]], IDX[lb[i]]) for i in ids]
    s = summarize(pairs, seed)
    lines.append(report("labeller 1 (A) vs labeller 2 (B)", s, "labeller 1", "labeller 2"))

    # for the adjudicator: only the line and the two labels, in colour order so that
    # it cannot be told which labeller gave which; never our own label
    dis = [i for i in ids if la[i] != lb[i]]
    rows = []
    for i in dis:
        x, y = sorted((la[i], lb[i]), key=lambda l: IDX[l])
        rows.append([i, texts[i], x, y, "", ""])
    write_tsv(os.path.join(outdir, "disagreements.tsv"),
              ["id", "text", "label_1", "label_2", "final_label", "note"], rows)
    lines.append(f"\ndisagreements: {len(dis)} -> disagreements.tsv (id, text, the two labels, empty final_label)")

    consensus = None
    if adj_path:
        adj, _, _ = read_labels(adj_path, "final_label")
        consensus, how, missing = {}, {}, []
        for i in ids:
            if la[i] == lb[i]:
                consensus[i], how[i] = la[i], "agreed"
            elif i in adj:
                consensus[i], how[i] = adj[i], "adjudicated"
            else:
                missing.append(i)
        extra = [i for i in adj if i in consensus and how[i] == "agreed"]
        if extra:
            lines.append(f"NOTE: {len(extra)} adjudicated ids were not disagreements (ignored)")
        if missing:
            lines.append(f"NOTE: {len(missing)} disagreements have no adjudication yet (left out of the consensus)")
        write_tsv(os.path.join(outdir, "consensus.tsv"),
                  ["id", "consensus", "how", "label_A", "label_B"],
                  [[i, consensus[i], how[i], la[i], lb[i]] for i in ids if i in consensus])
        write_tsv(os.path.join(outdir, "adjudications.tsv"),
                  ["id", "label_A", "label_B", "final_label"],
                  [[i, la[i], lb[i], consensus[i]] for i in ids if how.get(i) == "adjudicated"])
        cnt = {l: sum(1 for v in consensus.values() if v == l) for l in LABELS}
        lines.append(f"consensus: {len(consensus)} lines ({cnt['red']} red, {cnt['yellow']} yellow, "
                     f"{cnt['green']} green); adjudicated {sum(1 for h in how.values() if h == 'adjudicated')}"
                     " -> consensus.tsv, adjudications.tsv")

    if key_path:
        if consensus is None:
            raise SystemExit("--key needs --adjudication (the consensus to score against)")
        key = {r["id"]: norm_label(r.get("label")) for r in read_table(key_path)}
        common = [i for i in consensus if i in key]
        pr = [(IDX[key[i]], IDX[consensus[i]]) for i in common]
        sk = summarize(pr, seed)
        lines.append("\n" + report("OUR original labels vs the consensus", sk, "our label", "consensus"))
        t = sk["table"]
        for l, name in (("red", "red"),):
            c = sum(t[i][0] for i in range(3))
            lines.append(f"\nconsensus-red lines {c}; of those we had labelled red {t[0][0]} "
                         f"({100*t[0][0]/c:.1f}%)" if c else "")
        # each labeller against the consensus (for context)
        for name, lab in (("A", la), ("B", lb)):
            p = [(IDX[lab[i]], IDX[consensus[i]]) for i in consensus]
            lines.append(f"labeller {name} vs consensus: percent {100*percent_agree(table_of(p)):.1f}%, "
                         f"weighted kappa {kappa_from_table(table_of(p), True):.3f}")
        if flags_path:
            fl = {r["id"]: r.get("flagged", "").strip().lower() in ("1", "true", "yes", "y")
                  for r in read_table(flags_path)}
            cons_ids = [i for i in consensus if i in fl]
            for lab, what in (("red", "red recall"), ("green", "green flagged")):
                sel = [i for i in cons_ids if consensus[i] == lab]
                if sel:
                    hit = sum(fl[i] for i in sel)
                    lo, hi = wilson(hit, len(sel))
                    lines.append(f"{what} against the consensus: {hit}/{len(sel)} = {100*hit/len(sel):.1f}% "
                                 f"(Wilson 95% CI {100*lo:.1f}-{100*hi:.1f}%)")
    text = "\n".join(lines)
    with open(os.path.join(outdir, "agreement-report.txt"), "w", encoding="utf-8", newline="") as f:
        f.write(text + "\n")
    return text, s


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


# ---------------------------------------------------------------- self-test
def selftest():
    # 1. hand-computed binary example: [[20,5],[10,15]] -> po .7, pe .5, kappa .4
    assert abs(kappa_from_table([[20, 5], [10, 15]], False) - 0.4) < 1e-12
    # 2. perfect agreement = 1, and only-diagonal 3x3 with all weights
    t = [[10, 0, 0], [0, 5, 0], [0, 0, 20]]
    assert kappa_from_table(t, False) == 1.0 and kappa_from_table(t, True) == 1.0
    # 3. weighted kappa penalises red<->green more than red<->yellow
    near = [[8, 2, 0], [0, 10, 0], [0, 0, 10]]
    far = [[8, 0, 2], [0, 10, 0], [0, 0, 10]]
    assert kappa_from_table(near, True) > kappa_from_table(far, True)
    assert abs(kappa_from_table(near, False) - kappa_from_table(far, False)) < 1e-12
    # 4. no variation -> undefined
    assert math.isnan(kappa_from_table([[30, 0, 0], [0, 0, 0], [0, 0, 0]], False))

    # 5. synthetic end-to-end run, with non-ASCII text, through real files
    rng = random.Random(7)
    n = 400
    truth = [rng.choices(LABELS, [0.37, 0.15, 0.48])[0] for _ in range(n)]

    def noisy(lab, p):
        if rng.random() > p:
            return lab
        return rng.choice([l for l in LABELS if l != lab])
    A = [noisy(l, 0.12) for l in truth]
    B = [noisy(l, 0.12) for l in truth]
    ours = [noisy(l, 0.08) for l in truth]
    ids = [f"L3-{i:08x}" for i in rng.sample(range(1 << 32), n)]
    texts = [f"línea {i} niño ñandú, dolor de pecho" for i in range(n)]
    with tempfile.TemporaryDirectory() as d:
        def w(name, header, rows, bom=False):
            p = os.path.join(d, name)
            enc = "utf-8-sig" if bom else "utf-8"
            with open(p, "w", encoding=enc, newline="") as f:
                if name.endswith(".csv"):
                    cw = csv.writer(f, lineterminator="\r\n")
                    cw.writerow(header)
                    cw.writerows(rows)
                else:
                    f.write("\t".join(header) + "\n")
                    for r in rows:
                        f.write("\t".join(r) + "\n")
            return p
        # B is shuffled and given as an Excel-style csv with capitals and a few blanks
        order = list(range(n))
        rng.shuffle(order)
        pa = w("A.tsv", ["id", "text", "label", "note"],
               [[ids[i], texts[i], A[i], ""] for i in range(n)])
        pb = w("B.csv", ["id", "text", "label", "note"],
               [[ids[i], texts[i], B[i].capitalize(), "n"] for i in order], bom=True)
        pk = w("key.tsv", ["id", "source_line", "label", "group"],
               [[ids[i], str(i + 2), ours[i], "x"] for i in range(n)])
        out = os.path.join(d, "out")
        rep, s = run(pa, pb, out, seed=1)
        t = s["table"]
        assert sum(map(sum, t)) == n
        assert abs(s["percent"][0] - sum(t[i][i] for i in range(3)) / n) < 1e-12
        k, lo, hi = s["kappa_weighted"]
        assert lo < k < hi and 0.5 < k < 0.95, (k, lo, hi)
        # the interval must be reproducible with the same seed
        assert run(pa, pb, out, seed=1)[1]["kappa"] == s["kappa"]
        # disagreements file: right count, no key labels, colour-ordered pairs, UTF-8 text kept
        dis = read_table(os.path.join(out, "disagreements.tsv"))
        expect = sum(1 for i in range(n) if A[i] != B[i])
        assert len(dis) == expect and all(IDX[r["label_1"]] < IDX[r["label_2"]] for r in dis)
        assert all("ñandú" in r["text"] for r in dis)
        assert set(dis[0].keys()) == {"id", "text", "label_1", "label_2", "final_label", "note"}
        # adjudicate every disagreement with the truth, then score ours
        byid = {ids[i]: truth[i] for i in range(n)}
        pj = w("adj.tsv", ["id", "final_label"], [[r["id"], byid[r["id"]]] for r in dis])
        rep2, _ = run(pa, pb, out, adj_path=pj, key_path=pk, seed=1)
        cons = {r["id"]: r["consensus"] for r in read_table(os.path.join(out, "consensus.tsv"))}
        assert len(cons) == n
        assert sum(1 for i in ids if cons[i] == byid[i]) > 0.9 * n
        adjs = read_table(os.path.join(out, "adjudications.tsv"))
        assert len(adjs) == expect and all("label_a" in r and "label_b" in r for r in adjs)
        assert "OUR original labels vs the consensus" in rep2
        # flags: flag every red line -> recall 100 %
        pf = w("flags.tsv", ["id", "flagged"], [[i, "1" if cons[i] == "red" else "0"] for i in ids])
        rep3, _ = run(pa, pb, out, adj_path=pj, key_path=pk, flags_path=pf, seed=1)
        assert "red recall against the consensus" in rep3 and "100.0%" in rep3
        # a bad label is refused
        pbad = w("bad.tsv", ["id", "label"], [[ids[0], "orange"]])
        try:
            read_labels(pbad)
            raise AssertionError("bad label accepted")
        except SystemExit:
            pass
    print(rep)
    print("\nSELFTEST OK (python " + sys.version.split()[0]
          + ", PYTHONUTF8=" + os.environ.get("PYTHONUTF8", "unset") + ")")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--adjudication")
    ap.add_argument("--key")
    ap.add_argument("--flags")
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--seed", type=int, default=20261124)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.a and args.b):
        ap.error("--a and --b are required (or --selftest)")
    text, _ = run(args.a, args.b, args.outdir, args.adjudication, args.key, args.flags, args.seed)
    print(text)


if __name__ == "__main__":
    main()
