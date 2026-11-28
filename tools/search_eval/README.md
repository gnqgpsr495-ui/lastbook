# Library search test sets and scorer

A measuring tool, like the other scripts in `tools/`: it is not run by the unit tests. It scores what the library search
returns for a few thousand invented questions and messages, so a change to the search can be measured before and after.
It complements #241's tests, which check the guide search (`web/words.js`), and #302's emergency fallback.

The formulas, constants and how each number in the triage-based search proposal was measured are in
[docs/TRIAGE-SEARCH.md](../../docs/TRIAGE-SEARCH.md). `baseline-main.json` is the baseline recorded on `main`.

## What is here

| File | What it is |
|---|---|
| `data/patterns.json` | The pattern table: 157 regexes by key (`CPR`, `CHOKE`, `BLEED`, ...). A test case names keys; a page is useful if its title + excerpt matches one |
| `data/triage.json` | The triage set: 159 topics, 253 questions plus 109 typo versions (362). Red = act now, yellow = injury or illness without a danger sign, green = how-to; 22 counterexamples ("how to bleed the brakes") |
| `data/issue128.json` | #128's (and #126's) example questions, with its reviewer's counterexamples: 52 |
| `data/issue154.json` | Issue #154's 32 questions, each with a typo version, and #154's own topic regex |
| `data/issue241.json` | #241's 21 guide-search questions, scored here on the library's pages |
| `data/glued.json` | 48 messages typed with no spaces, keyboard mash, autocorrect slips, long real words |
| `data/conversations.json` | 52 conversations (follow-up, added danger, correction, new emergency, noise) |
| `lists/list1.jsonl` ... `list3.jsonl` | Three independent lists (690, 606, 531 messages), written by AI agents of one model family told not to open any project file, labelled red / yellow / green |
| `lists/list4.jsonl` | A fourth list (832 messages, 525 in Spanish) from Qwen3.5-9B, run locally |
| `score.py` | The scorer |
| `stats.py` | 95% intervals for one run; paired before/after tests for two runs on the same questions (needs `--rows`) |
| `index_identity.py` | Which passages a data folder's meaning index holds, as one SHA-256, to compare two builds |
| `baseline-main.json`, `baseline-files.md` | The baseline on `main`, and every file it was measured with (pack, model, index, test sets) |
| `blind-list3/` | List 3 without its labels, in two random orders, for independent blind relabelling: instructions, protocol, the key's SHA-256 (`COMMITMENT.md`), and `agreement.py` (kappa, adjudication) |

Each list's first line is a header: who wrote it, its size and colour counts, and for which fixes it is no longer blind.
The independent lists have no `need` patterns, so they measure urgency and pages shown, not which page comes first.

## How to run

From the repository root, with a library folder (a copy of a library pack; it is only read):

```
set LASTBOOK_DATA=<library folder>                  # export LASTBOOK_DATA=... on Linux and macOS
python -B tools/search_eval/score.py --mode keyword --out kw.json
python -B tools/search_eval/score.py --mode hybrid --out hy.json
```

- `--mode keyword` uses the library's own index only; `hybrid` adds meaning search (needs the pack's meaning model and index in `derived/`).
- `--search hybrid` (default) scores `assistant.hybrid(q, 8)`, what `/api/retrieve` and the chat's first search return; `--search find`
  scores the Library tab's search box (`server.find`), its first 8 documents.
- `--sets triage,lists` runs some sets only; `--rows` also writes every question's top 8; `--code <checkout>` measures another checkout.

Nothing is written into the library folder. A full keyword run takes a few minutes, hybrid about half an hour.
To check a rerun against the baseline, see [baseline-files.md](baseline-files.md#rerun-and-check).

## Statistics

```
python -B tools/search_eval/stats.py kw.json                   # one run
python -B tools/search_eval/stats.py before.json after.json    # a change, on the same questions
python -B tools/search_eval/stats.py kw.json --md --json out.json   # markdown, and the numbers as JSON
```

Every figure is given twice, and the two are not the same kind of result.

- **Row level: exploratory (assumes rows independent).** Each question is one observation. This is wrong for part of
  the data: a question, its other phrasings and its typo versions are about one topic and tend to be answered alike,
  and several questions on one topic are correlated. Row-level intervals are then too narrow and row-level p-values
  too small. They are kept because they are what the earlier reports used, and the output labels them as exploratory.
- **Clustered (the one to quote).** The unit that is resampled or permuted is the cluster, not the question. A cluster
  is the original question with all its other phrasings and typo versions: the `topic` field of the rows `score.py
  --rows` writes (checked: every typo version carries its original's topic; 159 clusters over the 362 triage
  questions, 21 over #128's 52, 32 over #154's 64). Sets that carry no topic (the four lists, #241, glued messages,
  conversations) have one question per cluster, so for them the clustered test is the row-level test and only the
  interval method differs. The lists' `persona` field (lists 3 and 4) is a coarser grouping, available as a
  sensitivity check with `--cluster-by persona`; it is not the default because a persona is a writing style, not a
  topic. The cluster count is printed for every group (`clusters=`).

What is computed:

- **One run:** each yes/no measure as a count, a rate and its Wilson 95% interval (row level), and a clustered 95%
  interval; `useful_mean` with a percentile bootstrap 95% interval of the questions (row level) and of the clusters
  (clustered). Both bootstraps use 2,000 resamples and seed 1, so the output is the same every time. The clustered
  rate is the number of hits over the number of questions in the resampled clusters. The design effect (`deff`) is the
  variance of the clustered estimate divided by the variance the row-level formula assumes: 1 means clustering changes
  nothing, 2 means the variance is twice as large. At 0% or 100% the bootstrap has no spread and the clustered interval
  is given as n/a (read the Wilson interval there).
- **Two runs:** questions are paired by set and id. For a yes/no measure: how many went no → yes and yes → no, the
  exact McNemar p (row level), and the clustered p. The clustered test is the clustered McNemar statistic of Durkalski,
  Palesch, Lipsitz and Rust (2003), "Analysis of clustered matched-pair data", Statistics in Medicine 22: 2417-2428:
  with d<sub>i</sub> = (no → yes) − (yes → no) counted inside cluster i, the statistic is (Σd<sub>i</sub>)² / Σd<sub>i</sub>²,
  which for one question per cluster is the usual McNemar chi-square. The p reported uses the exact distribution of
  that statistic when every cluster's sign is flipped at random (all 2<sup>k</sup> patterns enumerated), which for
  one question per cluster is the exact McNemar p; the chi-square approximation is in the JSON as `p_asymptotic`. Its
  `deff_mcnemar` is Σd<sub>i</sub>² over the number of changed questions. For the means: the paired difference with a bootstrap
  interval of the questions and of the clusters; for rates, the paired difference with a cluster-bootstrap interval.
- **Small groups:** a group with under 20 questions, or under 20 clusters for the clustered figures, shows counts only
  (no interval; 3 of 5 is 23–88%). The exact p-values of the paired tests are still printed.
- **Development and held-out.** Every set is tagged. `held-out` is list 3, the only data that stayed unseen throughout
  (nothing was changed because of it). `development` is everything else: the case files the system was built on,
  lists 1 and 2 (built against, or partly used for fixes), and list 4 (read once its results were in). They are
  printed in separate sections, held-out first, and never pooled. Results from the development sets say how the system
  does on what it was tuned on; only the held-out section is evidence about unseen questions.
- **Reading it:** the p-values are not corrected for the number of groups and measures. One measure is the main
  result, fixed before a change is measured: red questions' `first_ok` for a ranking change, red recall for the urgency
  check. The rest are descriptive.
- **Against a target:** a claim such as "undertriage under 5%" holds when the lower end of red recall's interval is at
  or above 95%, not its rate alone. With Wilson's interval that needs at least 73 red lines with no miss, 110 with one
  miss, 142 with two. Each line on the lists is its own cluster, so this reading is the row-level one.

## What the measures mean

For the sets with patterns, on the first 8 results:

| Measure | Meaning |
|---|---|
| `useful_mean` | mean number of the 8 that match any of the question's needs |
| `first_ok` | questions whose first result matches the most urgent need (and, for a counterexample, is not about the emergency sense of the word) |
| `top3_ok` | questions with a useful page in the first 3 |
| `covered` | questions where every need appears somewhere in the 8 |
| `zero_useful` | questions with no useful page at all |
| `cap_broken` | questions where more than half the 8 match only the setting (the flood around the wire) and no need |
| `wrong_sense_first` | counterexamples whose first result is about the emergency sense ("bleed" in a first-aid book for "bleed the brakes") |
| `useful154` | #154's own count: pages of 8 matching each question's own topic regex, summed over its 32 questions |

Counts are reported for clean questions by colour, counterexamples and typo versions separately. Conversations are scored on the last
message; on `main` the chat searches that message alone.

For the independent lists, by colour (green also as counterexamples and mild lines; list 4 also by language):

| Measure | Meaning |
|---|---|
| `flagged_urgent` | lines the urgency check (`assistant.is_danger`) flags. `main` has none, so it is `n/a` until that module arrives |
| `pages_shown` | lines for which the chat would show pages. On `main` that is every line whose search finds something |
| `no_hits` | lines whose search finds nothing |

Red recall = red flagged / red lines; undertriage = 1 - red recall; overtriage = green flagged / green lines.
