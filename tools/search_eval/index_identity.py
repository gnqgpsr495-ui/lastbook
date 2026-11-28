"""Content identity of a data folder's meaning index, to check that two builds hold the same passages.

    python -B tools/search_eval/index_identity.py <data folder> [<other data folder>]

The meaning index (derived/index/semantic.sqlite + vectors.f16) is built on each machine, so its files differ in their
bytes between builds: rows are written in the order documents were read, and the vectors differ in the last bits from one
processor to another. This prints what should be the same:

- passages and documents: active passages, and documents with at least one;
- text_sha256: SHA-256 over the active passages sorted by (document, page, time, text), each written as
  "doc_id<TAB>page<TAB>time<TAB>text<LF>" in UTF-8 (page and time empty when absent). Same value = same passages.

With a second folder it also counts the passages only one of them holds, and how many of those are the same text under
another page or time label. Read only: both indexes are opened immutable; the vectors are not read.
"""
import hashlib
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def passages(folder):
    path = Path(folder) / 'derived' / 'index' / 'semantic.sqlite'
    if not path.exists():
        sys.exit(f'no meaning index: {path}')
    db = sqlite3.connect(f'file:{path.as_posix()}?mode=ro&immutable=1', uri=True)
    try:
        rows = db.execute('SELECT doc_id, page, t, text FROM chunk WHERE active=1').fetchall()
        docs = db.execute('SELECT count(*) FROM docstate WHERE nchunks>0').fetchone()[0]
    finally:
        db.close()
    rows.sort(key=lambda r: (r[0], -1 if r[1] is None else r[1], -1 if r[2] is None else r[2], r[3]))
    return rows, docs


def identity(rows):
    h = hashlib.sha256()
    for doc, page, t, text in rows:
        h.update(f'{doc}\t{"" if page is None else page}\t{"" if t is None else t}\t{text}\n'.encode('utf-8'))
    return h.hexdigest()


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    found = []
    for folder in sys.argv[1:]:
        rows, docs = passages(folder)
        print(f'{folder}: passages {len(rows)}, documents {docs}, text_sha256 {identity(rows)}')
        found.append(rows)
    if len(found) == 2:
        a, b = Counter(found[0]), Counter(found[1])
        only_a, only_b = a - b, b - a
        relabel = (Counter((r[0], r[3]) for r in only_a.elements()) & Counter((r[0], r[3]) for r in only_b.elements()))
        print(f'only in the first: {sum(only_a.values())} passages in {len({r[0] for r in only_a})} documents; '
              f'only in the second: {sum(only_b.values())} in {len({r[0] for r in only_b})}; '
              f'of those, the same text under another page or time label: {sum(relabel.values())}')


if __name__ == '__main__':
    main()
