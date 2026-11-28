r"""Score the library search against the test sets in this folder. Read-only, in-process, no model.

    set LASTBOOK_DATA=<library folder>
    python -B tools/search_eval/score.py --mode keyword --out kw.json
    python -B tools/search_eval/score.py --mode hybrid --out hy.json --rows

Options:
  --mode keyword|hybrid   keyword = the library's own index only (what the desktop app ships with no meaning model);
                          hybrid = keyword + meaning search (needs the pack's meaning index and model in derived/)
  --search hybrid|find    hybrid = assistant.hybrid(q, 8): what /api/retrieve and the chat's first search return;
                          find = server.find(q): the Library tab's search box, scored on its first 8 documents
  --sets a,b,...          any of triage, issue128, issue154, issue241, glued, conversations, lists (default: all)
  --rows                  also write every question's result (titles of the top 8) into the output
  --code <checkout>       the code to measure (default: this checkout; or set LASTBOOK_CODE)

Nothing is written into the data folder: the meaning index is opened read-only and its vector file never truncated,
and a sections build (a later module) is refused. Measures are explained in README.md and docs/TRIAGE-SEARCH.md.
"""
import argparse, json, os, re, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
K = 8
NA = 'n/a'


def load_json(name):
    return json.loads((HERE / 'data' / name).read_text(encoding='utf-8'))


def load_list(name):
    rows, head = [], None
    with open(HERE / 'lists' / name, encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if '_header' in r:
                head = r['_header']
            else:
                rows.append(r)
    return head, rows


RX = {k: re.compile(v, re.I) for k, v in load_json('patterns.json')['patterns'].items()}


# ---------------------------------------------------------------- the cases --
def topic_cases(data):
    """Every phrasing as one case; typo versions as their own cases, tied to the topic's first phrasing."""
    out, pre = [], data.get('id_prefix', '')
    for i, t in enumerate(data['topics']):
        for j, q in enumerate(t['qs']):
            out.append(dict(t, q=q, id=f'{pre}{i:03d}.{j}', typo=False))
        for j, q in enumerate(t['typos']):
            out.append(dict(t, q=q, id=f'{pre}{i:03d}.t{j}', typo=True))
    return out


def cases154(data):
    out = []
    for i, c in enumerate(data['cases']):
        for typo, q in ((False, c['q']), (True, c['typo'])):
            out.append(dict(c, q=q, id=f'154.{i:02d}' + ('.t' if typo else ''), typo=typo, topic='154: ' + c['q']))
    return out


def cases241(data):
    return [dict(c, id=f'241.{i:02d}', typo=False, topic='241: ' + c['q']) for i, c in enumerate(data['cases'])]


# ------------------------------------------------------------- the scoring --
def text(h):
    return (h.get('title') or '') + ' ' + (h.get('excerpt') or '')


def matches(keys, t):
    return any(RX[k].search(t) for k in keys)


def score(c, hits):
    """One case against its top 8. See README.md for what each measure means."""
    ts = [text(h) for h in hits[:K]]
    need, ctx_keys, nf = c['need'], c.get('context') or [], c.get('not_first') or []
    useful = sum(1 for t in ts if matches(need, t))
    first = ts[0] if ts else ''
    # a counterexample fails when the first page is about the emergency word and not the real topic
    # (the brake manual says "bleed" too, and is the right answer)
    wrong_sense = bool(ts) and matches(nf, first) and not matches(need, first)
    first_ok = bool(ts) and bool(RX[need[0]].search(first)) and not wrong_sense
    ctx = sum(1 for t in ts if ctx_keys and matches(ctx_keys, t) and not matches(need, t))
    return {'useful': useful, 'first_ok': first_ok, 'top3_ok': any(matches(need, t) for t in ts[:3]),
            'covered': all(any(RX[k].search(t) for t in ts) for k in need), 'cap_broken': ctx / K > 0.5,
            'wrong_sense_first': wrong_sense, 'n_hits': len(ts)}


def agg(rows):
    n = len(rows)
    if not n:
        return {'n': 0}
    return {'n': n, 'useful_mean': round(sum(r['useful'] for r in rows) / n, 2),
            'first_ok': sum(r['first_ok'] for r in rows), 'top3_ok': sum(r['top3_ok'] for r in rows),
            'covered': sum(r['covered'] for r in rows), 'zero_useful': sum(r['useful'] == 0 for r in rows),
            'cap_broken': sum(r['cap_broken'] for r in rows), 'wrong_sense_first': sum(r['wrong_sense_first'] for r in rows)}


def by_colour(rows):
    """Clean questions by colour (counterexamples apart), counterexamples, typo versions."""
    clean = [r for r in rows if not r['typo']]
    out = {'all_clean': agg(clean), 'counterexamples': agg([r for r in clean if r['counter']]), 'typos': agg([r for r in rows if r['typo']])}
    for col in ('red', 'yellow', 'green'):
        out[col] = agg([r for r in clean if r['colour'] == col and not r['counter']])
    return out


# ---------------------------------------------------------------- the engine --
def start(code, mode):
    """Import the code under test with every write into the data folder turned off."""
    if not os.environ.get('LASTBOOK_DATA'):
        raise SystemExit('set LASTBOOK_DATA to the library folder to measure against')
    os.environ.pop('LASTBOOK_LOCAL_AI', None)    # no local model: the search alone is measured
    sys.path.insert(0, str(code))
    import retrieval
    if mode == 'keyword':
        retrieval.AVAILABLE = False
    try:     # long pages in sections (a later module): never build the sections file during a measurement
        from engine import sections

        def refuse(*a, **k):
            raise OSError('search_eval: sections build refused (read-only run)')
        sections.build = refuse
    except ImportError:
        pass
    from engine.paths import ro_uri as plain_ro

    def ro_uri(path):
        # immutable when no write-ahead log is pending: SQLite then does not even touch the -shm file
        wal = Path(str(path) + '-wal')
        return plain_ro(path) + ('&immutable=1' if not wal.exists() or wal.stat().st_size == 0 else '')
    retrieval.ro_uri = ro_uri    # the meaning index's own read connections
    retrieval.Index._db = lambda self: sqlite3.connect(ro_uri(self.db_path), uri=True, timeout=60, isolation_level=None,
                                                        check_same_thread=False)
    load = retrieval.Index._load
    retrieval.Index._load = lambda self, truncate=True, db=None: load(self, False, db)
    import server, assistant
    server.catalog()
    index = None
    if mode == 'hybrid':
        if not retrieval.AVAILABLE:
            raise SystemExit('hybrid asked for, but no meaning model in this data folder (derived/models/bge-small-en-v1.5)')
        index = retrieval.Index(server.catalog, server.trust, server.library.DB)
    server.INDEX = index
    assistant.init(server, index)
    state = index.status.get('state') if index else 'off'
    if mode == 'hybrid' and not (index and index.status.get('chunks')):
        raise SystemExit(f'hybrid asked for, but the meaning index is empty (state {state})')
    return server, assistant, {'state': state, 'chunks': index.status.get('chunks') if index else 0}


def searcher(server, assistant, how):
    if how == 'hybrid':
        return lambda q: assistant.hybrid(q[:300], K)     # the chat cuts the question at 300 characters

    def find(q):
        res = server.find(q[:300]).get('results', [])[:K]
        return [{'title': r['title'], 'excerpt': ' '.join(re.sub(r'<[^>]+>', '', h['snippet']) for h in r.get('hits', []))}
                for r in res]
    return find


def urgency(assistant):
    """The urgency check, when the code has one (on main it has none: reported as n/a)."""
    fn = getattr(assistant, 'is_danger', None)
    return (lambda q: bool(fn(q))) if fn else None


def pages_shown(hits):
    """On main the chat shows every page it finds. A module that may ask before answering must say here what it shows."""
    return bool(hits)


# ---------------------------------------------------------------- the sets --
def run_topics(name, cases, search, rows_out):
    rows = []
    for c in cases:
        hits = search(c['q'])
        r = score(c, hits)
        r.update(set=name, id=c['id'], q=c['q'], topic=c['topic'], colour=c['colour'], typo=c['typo'], counter=bool(c['not_first']),
                 group=c.get('group'))
        rows.append(r)
        rows_out.append(dict(r, titles=[f"{h.get('title')} p.{h.get('page')}" for h in hits[:K]],
                             _texts=[text(h) for h in hits[:K]]))
    return rows


def run_triage(search, rows_out):
    return by_colour(run_topics('triage', topic_cases(load_json('triage.json')), search, rows_out))


def run_128(search, rows_out):
    return by_colour(run_topics('issue128', topic_cases(load_json('issue128.json')), search, rows_out))


def run_154(search, rows_out):
    cs = cases154(load_json('issue154.json'))
    rows = run_topics('issue154', cs, search, rows_out)
    out = by_colour(rows)
    # #154's own count: hits of 8 whose title + excerpt match the question's own topic regex
    for typo in (False, True):
        tot = 0
        for c, r in zip(cs, rows_out[-len(cs):]):
            if c['typo'] == typo:
                tot += sum(1 for t in r['_texts'] if re.search(c['pat154'], t, re.I))
        out['useful154_typos' if typo else 'useful154'] = f'{tot} of {8 * len(cs) // 2}'
    return out


def run_241(search, rows_out):
    rows = run_topics('issue241', cases241(load_json('issue241.json')), search, rows_out)
    return {'all': agg(rows), 'emergency': agg([r for r in rows if r['group'] == 'emergency']),
            'counter': agg([r for r in rows if r['group'] == 'counter'])}


def run_glued(search, rows_out):
    rows = []
    for i, c in enumerate(load_json('glued.json')['cases']):
        hits = search(c['q'])
        r = {'set': 'glued', 'id': f'glued.{i:02d}', 'q': c['q'], 'kind': c['kind'], 'n_hits': len(hits)}
        if c['need']:
            r.update(score(dict(c, context=[], not_first=[]), hits))
        rows.append(r)
        rows_out.append(dict(r, titles=[f"{h.get('title')} p.{h.get('page')}" for h in hits[:K]]))
    out = {}
    for kind in sorted({r['kind'] for r in rows}):
        rs = [r for r in rows if r['kind'] == kind]
        scored = [r for r in rs if 'useful' in r]
        out[kind] = {'n': len(rs), 'with_need': len(scored), 'first_ok': sum(r['first_ok'] for r in scored),
                     'top3_ok': sum(r['top3_ok'] for r in scored), 'zero_useful': sum(r['useful'] == 0 for r in scored),
                     'no_hits': sum(r['n_hits'] == 0 for r in rs)}
    return out


def run_convos(search, assistant, rows_out):
    """Scored on the last message. On main the chat searches the newest user message alone."""
    turn_hits = getattr(assistant, 'turn_hits', None)
    rows = []
    for i, c in enumerate(load_json('conversations.json')['conversations']):
        last, kind = c['turns'][-1]
        if turn_hits:   # the conversation module (a later PR) searches with what came before
            msgs = []
            for j, (m, _) in enumerate(c['turns']):
                msgs.append({'role': 'user', 'content': m})
                if j < len(c['turns']) - 1:
                    msgs.append({'role': 'assistant', 'content': ''})
            hits = turn_hits(msgs, None, True)[0]
        else:
            hits = search(last)
        r = score(dict(c, not_first=[]), hits)
        r.update(set='conversations', id=f'conv.{i:02d}', q=' | '.join(m for m, _ in c['turns']), kind=kind,
                 noise=any(k == 'noise' for _, k in c['turns']))
        rows.append(r)
        rows_out.append(dict(r, titles=[f"{h.get('title')} p.{h.get('page')}" for h in hits[:K]]))
    out = {'all': agg(rows), 'with_noise': agg([r for r in rows if r['noise']]),
           'path': 'turn_hits' if turn_hits else 'last message alone'}
    for kind in ('follow', 'add', 'correct', 'new'):
        out[kind] = agg([r for r in rows if r['kind'] == kind])
    return out


def run_lists(search, urgent, rows_out):
    out = {}
    for n in (1, 2, 3, 4):
        head, rows = load_list(f'list{n}.jsonl')
        res = []
        for i, r in enumerate(rows):
            hits = search(r['text'])
            kinds = r.get('kind') or []
            rec = {'set': f'list{n}', 'id': f'list{n}.{i:03d}', 'q': r['text'], 'triage': r['triage'],
                   'counter': 'counterexample' in kinds, 'mild': 'mild' in kinds, 'lang': r.get('lang', 'en'),
                   'flagged': urgent(r['text']) if urgent else None, 'pages_shown': pages_shown(hits), 'n_hits': len(hits)}
            if r.get('persona'):    # lists 3 and 4: the line's persona, for stats.py --cluster-by persona
                rec['persona'] = r['persona']
            res.append(rec)
            rows_out.append(dict(rec, titles=[f"{h.get('title')} p.{h.get('page')}" for h in hits[:3]]))

        def count(rs):
            return {'n': len(rs), 'flagged_urgent': sum(x['flagged'] for x in rs) if urgent else NA,
                    'pages_shown': sum(x['pages_shown'] for x in rs), 'no_hits': sum(x['n_hits'] == 0 for x in rs)}
        s = {c: count([x for x in res if x['triage'] == c]) for c in ('red', 'yellow', 'green')}
        s['green_counterexamples'] = count([x for x in res if x['triage'] == 'green' and x['counter']])
        s['green_mild'] = count([x for x in res if x['triage'] == 'green' and x['mild']])
        if n == 4:
            for lang in ('en', 'es'):
                pick = [x for x in res if x['lang'].startswith(lang)]
                s['lang_' + lang] = {c: count([x for x in pick if x['triage'] == c]) for c in ('red', 'yellow', 'green')}
        s['header'] = {k: head[k] for k in ('lines', 'red', 'yellow', 'green')}
        out[f'list{n}'] = s
    return out


SETS = ('triage', 'issue128', 'issue154', 'issue241', 'glued', 'conversations', 'lists')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--mode', choices=('keyword', 'hybrid'), default='keyword')
    ap.add_argument('--search', choices=('hybrid', 'find'), default='hybrid')
    ap.add_argument('--sets', default=','.join(SETS))
    ap.add_argument('--out', required=True)
    ap.add_argument('--rows', action='store_true')
    ap.add_argument('--code', default=os.environ.get('LASTBOOK_CODE') or str(HERE.parents[1]))
    a = ap.parse_args()
    sets = [s for s in a.sets.split(',') if s]
    bad = set(sets) - set(SETS)
    if bad:
        raise SystemExit(f'unknown sets: {sorted(bad)}')
    t0 = time.time()
    server, assistant, semantic = start(Path(a.code).resolve(), a.mode)
    search = searcher(server, assistant, a.search)
    urgent = urgency(assistant)
    rows_out = []
    summary = {'mode': a.mode, 'search': a.search, 'semantic': semantic, 'urgency_check': bool(urgent)}
    for s in sets:
        t1 = time.time()
        if s == 'triage':
            summary[s] = run_triage(search, rows_out)
        elif s == 'issue128':
            summary[s] = run_128(search, rows_out)
        elif s == 'issue154':
            summary[s] = run_154(search, rows_out)
        elif s == 'issue241':
            summary[s] = run_241(search, rows_out)
        elif s == 'glued':
            summary[s] = run_glued(search, rows_out)
        elif s == 'conversations':
            summary[s] = run_convos(search, assistant, rows_out)
        elif s == 'lists':
            summary[s] = run_lists(search, urgent, rows_out)
        print(s, round(time.time() - t1, 1), 's', flush=True)
    summary['seconds'] = round(time.time() - t0, 1)
    out = {'summary': summary}
    if a.rows:
        out['rows'] = [{k: v for k, v in r.items() if k != '_texts'} for r in rows_out]
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False)[:2000])


if __name__ == '__main__':
    main()
