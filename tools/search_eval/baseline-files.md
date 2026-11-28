# Files behind `baseline-main.json`

Every file the baseline in [`baseline-main.json`](baseline-main.json) was measured with, so that a rerun can check it is
measuring the same thing. SHA-256 of the file's bytes, size in bytes. Measured 2026-11-22.

## Code

| What | Identity |
|---|---|
| Search code | upstream `main` at `f41b6ce` (`server.py`, `assistant.py`, `retrieval.py`, `engine/`) |
| Scorer and test sets | this branch's `tools/search_eval/` |
| Python | 3.14.10 on Windows 10 (x86-64), onnxruntime 1.32.0 (CPU), tokenizers 0.23.3, numpy 2.5.4 |

## Library pack

The published Medium pack, installed by setup, which checks the zip against the SHA-256 in
`https://downloads.lastbook.org/manifest-v1.json` (published 2026-11-13) before unpacking it.

| File | Bytes | SHA-256 |
|---|---|---|
| `Lastbook-Medium.zip` (as published) | 67,492,034,038 | `e4ef75afd584dd174bfb34468a41a9c7c5e6907d5b37bb722aa9b5435876068a` |
| `pack.json` (`built` 2026-11-12, `snapshot` 20261102-025617) | 422 | `ffd357a2ebf3f3995d32052159d590ca82d511d7fa59d0537c0ce28c549dfc56` |
| `pack-manifest.tsv` (SHA-256 of every pack file) | 8,571,707 | `19cd173b7ee9ecb77fd6405ca55ce8d02093d3a79e67a614a8cb799d7ea80961` |
| `library-data/catalog.json` | 9,569,961 | `abc7631a8a5466f851730fef12742ac8ee8d89b21bd19314ab15328023ab4568` |
| `library-data/search.sqlite` (keyword index) | 746,516,480 | `198c2af919c7ffee13e95cabd66d7a831c93077bf443dcc35a2892cb0eeefffe` |

`catalog.json` and `search.sqlite` match their rows in `pack-manifest.tsv`. `search.sqlite` had the same SHA-256 before
and after every run.

## Meaning model (hybrid only)

Not part of the pack. The files in `derived/models/bge-small-en-v1.5/` are Hugging Face's
[BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) at revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`.

| File | Bytes | SHA-256 |
|---|---|---|
| `model.onnx` (the repository's `onnx/model.onnx`) | 133,093,490 | `828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35` |
| `tokenizer.json` (git blob `688882a7`, the repository's own) | 711,396 | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |

## Meaning index (hybrid only)

Built from the pack above by main's own indexer (`python retrieval.py`, `main` `f41b6ce`, CPU), in an empty
`derived/index/`. The index is built on each machine, so its files are not the same bytes from one build to another; use
[`index_identity.py`](index_identity.py) to compare the passages it holds.

| Identity | Value |
|---|---|
| Passages / documents | 338,910 / 7,849 |
| `text_sha256` (`index_identity.py`) | `938e417e3d0d173e95e96ead7db5fb31afdf904057b1fc5179ba041cf996037a` |
| `vectors.f16`, this build (260,282,880 bytes) | `9fa0ce68f24d8c6a22c68652d9a0221a58546e3fc99ec4c7da6079dea74585a6` |
| `semantic.sqlite`, this build (376,561,664 bytes) | `dcd91022e080db82e2fac68001b60316560badcf6e9ffd9910ef6aa779455444` |

The same indexer run on a GPU (onnxruntime-gpu 1.32, CUDA) gave the same `text_sha256`. Its vectors differ from the CPU
build's in the last bits: the lowest cosine between the two vectors of a passage was 0.999998, and the largest single
difference was 0.00049, one or two steps of float16 rounding. On the 3,258 questions below, no yes/no measure changed
between the two builds; 66 questions (2%) showed some of their 8 pages in another order (pages with nearly equal
scores), and 2 changed their useful count by one, one up and one down. A rebuild on other hardware should therefore
reproduce the measures, but not always the exact page order. Keyword mode reproduces exactly.

`main` at 6dd3080 (1.1.16, 2026-11-23), which changed `assistant.py`, gave the same 8 pages as f41b6ce for all 3,258
questions in both modes, on the same pack and index.

## Test sets

| File | Bytes | SHA-256 |
|---|---|---|
| `data/conversations.json` | 13,597 | `a5e6efca9ca777cf9cfa58c799a7c0590240243cb48e46fbf7981653d38e06c3` |
| `data/glued.json` | 7,980 | `99e8ae7f6d54747a59edd819e61963c4766796203e18252397be9c82413fbec1` |
| `data/issue128.json` | 6,827 | `ce2040c3f7000badded67f57f4e516cfaefa17389e4bf4a8cc6c47557013ec89` |
| `data/issue154.json` | 10,312 | `de64f217cd29c4ad324d4e75f87296d50dd436d8113da2d1191d9d0808f886ad` |
| `data/issue241.json` | 6,680 | `09144e31bca7f4cecc92162ae2a73a90934207f8992e49dd8e7aa810cbe24247` |
| `data/patterns.json` | 10,096 | `99dcbab3b963ac612be423065eec0b5104467d9caa29ba88b4bad29e04905611` |
| `data/triage.json` | 43,635 | `241dcafbbb5e7f8c963cef0444ff9f861833fe1fd9d62526d7cc607d5546231d` |
| `lists/list1.jsonl` | 149,351 | `4b6c83c5f65e2917113b4d942d037d5b4fb342fb2c61f67bace565de698126d8` |
| `lists/list2.jsonl` | 141,727 | `6025c9102704fb80d7be46997b8d001fc580f03504d9da8eb7499a9ccb13bf8e` |
| `lists/list3.jsonl` | 149,670 | `29774df65c94b7e78ef4ebfd12915d58c35c2f1b77d6e8581bc8585d6396586b` |
| `lists/list4.jsonl` | 273,725 | `80b773939cfe887e567065a275e51dd7d05ece117de4c18ccb4120438539f6a6` |

## Rerun and check

From the repository root, with the pack installed in `<data folder>`, the model files above in
`<data folder>/derived/models/bge-small-en-v1.5/`, and (hybrid only) the index built once with `python retrieval.py`:

```
set LASTBOOK_DATA=<data folder>                                   # export LASTBOOK_DATA=... on Linux and macOS
python -B tools/search_eval/index_identity.py <data folder>       # expect text_sha256 938e417e...
python -B tools/search_eval/score.py --mode keyword --rows --out kw.json
python -B tools/search_eval/score.py --mode hybrid  --rows --out hy.json
python -B tools/search_eval/stats.py kw.json                      # every rate with its 95% interval
```

Expected: the summaries in `kw.json` equal `runs.keyword` in `baseline-main.json` exactly (all but `seconds`); for
`hy.json`, see the paragraph on rebuilds above. The keyword run takes about 10 minutes, hybrid about 30, the index build
about 4 hours on 14 CPU threads (minutes on a GPU).
