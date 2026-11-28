#!/usr/bin/env python3
"""Make the blind-labelling package for list 3 (urgency test lines).

What it does, once:
  1. reads the source list (JSON lines; the first line is a header, every other
     line has "text", "triage" (red/yellow/green), "kind", "source", ...);
  2. gives every line a random ID, 'L3-' + secrets.token_hex(4), drawn with the
     `secrets` module (OS CSPRNG), unique, carrying no order or label information;
  3. makes TWO independent shuffles with secrets.SystemRandom().shuffle (OS CSPRNG;
     not random.Random's Mersenne Twister, not a hand- or model-chosen order);
     writes list3-blind-A / list3-blind-B as .tsv (UTF-8, no BOM) and .csv
     (UTF-8 with BOM, for Excel), columns: id, text, label, note (last two empty);
  4. writes the key (id, source_line, label, group) to private/list3-key.tsv,
     which must not be published until both labellers' labels are in;
  5. writes COMMITMENT.md: SHA-256 of the key, A, B, their .csv versions, the
     source file and this script, plus the Python version.

The shuffle is unseeded on purpose: the order cannot be reproduced, only checked
(both published files are the draw). The IDs are unseeded for the same reason.
It refuses to overwrite an existing output unless --force is given.

Usage:
  python make_blind.py --source path/to/list3.jsonl [--outdir .] [--force]
"""
import argparse
import csv
import hashlib
import json
import secrets
import sys
from collections import Counter
from pathlib import Path

EXPECTED = {"red": 199, "yellow": 78, "green": 254}
ID_PREFIX = "L3-"
COLUMNS = ["id", "text", "label", "note"]
KEY_COLUMNS = ["id", "source_line", "label", "group"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_source(path):
    """Return a list of dicts: source_line (1-based, header = line 1), text, label, group."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for n, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if "_header" in obj:
                continue
            text = " ".join(obj["text"].split())  # collapse tabs/newlines/odd spacing
            if not text:
                raise SystemExit(f"line {n}: empty text")
            kind = obj.get("kind") or []
            if isinstance(kind, str):
                kind = [kind]
            group = "+".join(kind) + "|" + str(obj.get("source", ""))
            rows.append({"source_line": n, "text": text,
                         "label": obj["triage"], "group": group})
    return rows


def check_counts(rows):
    counts = Counter(r["label"] for r in rows)
    if len(rows) != 531 or dict(counts) != EXPECTED:
        print(f"WARNING: expected 531 lines {EXPECTED}, got {len(rows)} {dict(counts)}",
              file=sys.stderr)
    return counts


def assign_ids(n):
    ids = set()
    while len(ids) < n:
        ids.add(ID_PREFIX + secrets.token_hex(4))
    ids = list(ids)
    # a set has no meaningful order, but do not rely on that: shuffle the pairing too
    secrets.SystemRandom().shuffle(ids)
    return ids


def write_tsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            for cell in r:
                if "\t" in cell or "\n" in cell or "\r" in cell:
                    raise SystemExit(f"tab/newline inside a cell: {cell!r}")
            f.write("\t".join(r) + "\n")


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True, help="list3.jsonl")
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--force", action="store_true", help="overwrite existing outputs")
    args = ap.parse_args()

    out = Path(args.outdir)
    priv = out / "private"
    targets = {
        "A_tsv": out / "list3-blind-A.tsv", "A_csv": out / "list3-blind-A.csv",
        "B_tsv": out / "list3-blind-B.tsv", "B_csv": out / "list3-blind-B.csv",
        "key": priv / "list3-key.tsv", "commit": out / "COMMITMENT.md",
    }
    existing = [str(p) for p in targets.values() if p.exists()]
    if existing and not args.force:
        raise SystemExit("refusing to overwrite (use --force):\n  " + "\n  ".join(existing))

    src = Path(args.source)
    rows = read_source(src)
    counts = check_counts(rows)
    ids = assign_ids(len(rows))
    for r, i in zip(rows, ids):
        r["id"] = i
    assert len({r["id"] for r in rows}) == len(rows)
    assert len({r["text"] for r in rows}) == len(rows), "duplicate texts"

    rng = secrets.SystemRandom()
    order_a = rows[:]
    rng.shuffle(order_a)
    order_b = rows[:]
    rng.shuffle(order_b)
    if [r["id"] for r in order_a] == [r["id"] for r in order_b]:
        raise SystemExit("A and B came out identical (probability about 1/531!); run again")

    out.mkdir(parents=True, exist_ok=True)
    priv.mkdir(exist_ok=True)
    for name, order in (("A", order_a), ("B", order_b)):
        data = [[r["id"], r["text"], "", ""] for r in order]
        write_tsv(targets[name + "_tsv"], COLUMNS, data)
        write_csv(targets[name + "_csv"], COLUMNS, data)

    key_rows = sorted(rows, key=lambda r: r["source_line"])
    write_tsv(targets["key"], KEY_COLUMNS,
              [[r["id"], str(r["source_line"]), r["label"], r["group"]] for r in key_rows])
    with open(priv / ".gitignore", "w", encoding="utf-8", newline="") as f:
        f.write("*\n")

    # read-back checks: A and B are permutations of the same lines, nothing else leaks
    def read_ids(p):
        with open(p, "r", encoding="utf-8") as f:
            return [ln.split("\t")[0] for ln in f.read().splitlines()[1:]]
    assert sorted(read_ids(targets["A_tsv"])) == sorted(read_ids(targets["B_tsv"])) \
        == sorted(r["id"] for r in rows)

    hashes = {k: sha256_file(p) for k, p in targets.items() if k != "commit"}
    script_hash = sha256_file(Path(__file__).resolve())
    src_hash = sha256_file(src)

    lines = [
        "# Commitment for the blind list 3 package",
        "",
        "Everything below was computed when the files were made. The key (which line has which",
        "of our labels) stays private until both labellers have handed in their labels. Its",
        "SHA-256 is published now, so that when the key is published later anyone can check it",
        "was not changed in between: `sha256sum list3-key.tsv` must give the value below.",
        "",
        "The key file is UTF-8, no BOM, LF line endings, one header line, then one line per",
        "item sorted by `source_line`; columns `id`, `source_line` (line number in the source",
        "file, whose first line is a header), `label` (red / yellow / green), `group` (the",
        "line kind(s) and source, joined with `+` and `|`).",
        "",
        "Note: the source labels were already visible in the public repository before this",
        "package was made (see PROTOCOL.md), so the key does not hide anything that cannot be",
        "looked up. The hash proves the key was fixed before any outside label existed and",
        "that the published IDs map to the lines as stated.",
        "",
        "| File | SHA-256 |",
        "|---|---|",
        f"| `private/list3-key.tsv` (the key, not published yet) | `{hashes['key']}` |",
        f"| `list3-blind-A.tsv` | `{hashes['A_tsv']}` |",
        f"| `list3-blind-B.tsv` | `{hashes['B_tsv']}` |",
        f"| `list3-blind-A.csv` | `{hashes['A_csv']}` |",
        f"| `list3-blind-B.csv` | `{hashes['B_csv']}` |",
        f"| source `list3.jsonl` (as in the triage branches) | `{src_hash}` |",
        f"| `make_blind.py` (the script that made these files) | `{script_hash}` |",
        "",
        f"Lines: {len(rows)} ({counts['red']} red, {counts['yellow']} yellow, {counts['green']} green).",
        f"Python: {sys.version.split()[0]} ({sys.platform}).",
        "",
        "How the randomness was drawn: the IDs with `secrets.token_hex(4)` (prefix `L3-`), and",
        "each of the two orders with one call of `secrets.SystemRandom().shuffle`, which uses",
        "the operating system's cryptographic random source. Nothing is seeded, so the draws",
        "cannot be repeated; the two published files are the record of them.",
        "",
        "Command: `python make_blind.py --source list3.jsonl`",
        "",
    ]
    with open(targets["commit"], "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))

    print(f"{len(rows)} lines {dict(counts)}")
    for k, v in hashes.items():
        print(f"{v}  {k}")
    print(f"{script_hash}  make_blind.py")
    print(f"{src_hash}  source")


if __name__ == "__main__":
    main()
