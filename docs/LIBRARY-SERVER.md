# Survival Guide — a task-first front end for the offline library

A new way into the Survival & Rebuilding Library (`library-data/` → the real collection). It starts from
what a person needs ("Someone is hurt", "Get safe drinking water", "Power is out", map of nearby help),
then shows a few hand-picked pages with exact page numbers and the source's own limits, then the full
manuals, videos and encyclopedias. It runs entirely from this computer.

## Run it

```bash
python3 server.py
```

Then open http://127.0.0.1:8890/ (or double-click **Open Survival Guide.command**, which uses the library's
bundled Python). `python3 server.py --lan` also serves phones on the same Wi-Fi (no internet needed).

The previous interface on port 8879 is untouched and keeps running separately.

## Ask the library (local DeepSeek assistant)

- Model: `deepseek-v4.1-flash` at `http://127.0.0.1:19443` (called only by the server; override with
  `SURVIVAL_MODEL_BASE`, which must be a loopback address). The 19442 gateway is not used.
- A model server chosen in *Library and local AI* (Ollama, llama.cpp; loopback only, no key yet) is saved in `setup.json` and
  used instead, by the desktop app and the server version alike (`docs/SETUP-API.md`, `server-models`).
- Every question is first searched with the shared retriever; the model then gets five read-only tools:
  `search_library`, `read_pages`, `view_page` (sends the page image — verified the model reads it),
  `get_timed_transcript`, `lookup_place`. Tools accept catalog ids only: no paths, URLs or shell input.
  Source text is wrapped as untrusted reference data.
- Citations (`[S3]`) are checked against what the tools actually returned; unknown keys are removed and
  reported. Sentences without a citation are shown dotted as the model's own wording; "Not found in the
  library", "Sources disagree" and "own reasoning" sections are styled separately.
- If the model is down, the Ask tab says so and lists the best-matching pages instead; all browsing works.
- Other local DeepSeek clients can use the same tools: `GET /api/tools` (OpenAI-style schemas) and
  `POST /api/tool/<name>` with JSON arguments. Hybrid passages: `GET /api/retrieve?q=…&k=8&kind=any|manual|video`.

## Optional local AI in the desktop app (`llm_local.py`)

The Lastbook desktop app can write answers with **Gemma 4 26B A4B** (Unsloth `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`,
16,947,541,728 bytes, SHA-256 `f2c28b3d…3f293f`, revision `c099eb48`), running on the same computer. The server
version above keeps using the model server at `SURVIVAL_MODEL_BASE` unless started with `LASTBOOK_LOCAL_AI=1`.

- **Runner:** `packaging/llm/lastbook_llm.cpp`, our own small program on llama.cpp b12032 (the build the small-model
  evaluation used). It speaks JSON lines on standard input and output and opens no socket or port. It holds no RPC
  backend and none of llama.cpp's common library except the memory fitting (`common/fit.cpp`, the same as llama-server's
  default `--fit`) and its log. Build it with `bash packaging/llm/build_llm_macos.sh`, which refuses a binary with
  network calls or a folder of this Mac in it. Prompts go in as segments: Gemma's template markup with special tokens
  read, library and user text with them never read, so a document cannot start a turn of its own.
- **Finding the model:** the file in `LastbookData/models/`, `LastbookData/`, Downloads, Documents or Desktop. It is
  checked once (size, then SHA-256, about 10 s on this Mac), then `lastbook-llm --measure` asks llama.cpp where it fits.
  It is offered when the computer's memory holds the measured need plus 2.5 GiB. On a Mac GPU and CPU share that memory;
  on Windows only the part not placed on the graphics card counts. There is no fixed 32 GB rule.
- **Measured here** (Apple M3 Ultra, 16k context): 16.9 GiB on the GPU plus 0.8 GiB host. Loading takes 1.5 s, and an
  answer with sources takes about 5–12 s. The process holds about 17.4 GB resident.
- **Lifecycle:** it starts when someone asks and stops after 15 minutes unused, when turned off (About page), and when the
  app quits or dies (the closed pipe ends it, plus a kill-on-close job object on Windows). A crash while answering
  shows a plain error, and the next question starts it again.
- **Limits:** text only (no `view_page`: the local model is not given page images). Its answers were graded in the
  one-question evaluation (`derived/small-models/RECOMMENDATION.md`): 0–1 dangerous of 60, depending on the reader. The
  app's full loop, with follow-up searches and follow-up questions, has been tried but not graded.

## Retrieval service (`retrieval.py`)

Keyword search = the library's own FTS5/BM25 `search.sqlite` (read only). Meaning-based search =
BAAI bge-small-en-v1.5 (ONNX, from the official BAAI Hugging Face repo) run locally with onnxruntime.
Results are fused with reciprocal-rank fusion, lightly weighted by source type, with an exact
equipment-model boost. Index files: `derived/index/semantic.sqlite` + `vectors.f16` (append-only).
It updates incrementally: the server re-checks the catalog every 5 minutes and embeds only new or
changed documents and transcripts (single writer, file lock). Build/refresh by hand:

```bash
library-data/runtime/macos-arm64/python/bin/python3 retrieval.py
```

What it cannot read is reported in the app (About page, `/api/assistant/status`): videos without
captions (most of them), scanned PDFs without text, pictures inside videos, raw GIS files.

## Sharing with phones on the same network

```bash
library-data/runtime/macos-arm64/python/bin/python3 server.py --lan
```

Prints a one-time link `http://<this-mac>:8890/?key=…`; opening it sets a cookie. Without the key other
devices get 403. Network clients only get the app, its APIs, encyclopedias and library content folders
(no worker state, logs, databases or directory listings). Loopback behaves exactly as before. Delete
`derived/lan-key` to change the key. Nothing is exposed beyond the local network by this server.

## Runtime dependencies (all local)

The library's bundled Python 3.12 (`library-data/runtime/...`), the library's own `tools/library.py`
and vendored packages (libzim, bs4), poppler `pdftoppm` (page images), and in `derived/pylib`:
onnxruntime, tokenizers, numpy. The model server at 19443 is needed only for Ask. No internet.

## What's where

| Path | What it is |
|---|---|
| `server.py` | Small server. Imports `library-data/tools/library.py` and subclasses its `Handler`, so every original file URL, `/api/search`, `/api/collection-search`, `/zim/...`, and video range requests behave exactly as on 8879. Adds read-only endpoints (topics, plain-language search, page images/text, transcripts, browse, map tiles, nearby help, place finder). |
| `web/` | The app: `index.html`, `app.css`, `app.js`, `chat.js`, `map.js`, `sw.js`. No build step, no external fonts/scripts. |
| `retrieval.py`, `assistant.py` | Shared retrieval service and the assistant (tools, streaming, citation checks). |
| `content/topics/*.json` | 14 curated guides (8 urgent needs, 6 learning tracks), ~720 references, each checked against the page it cites. Format: `content/SCHEMA.md`. |
| `content/gaps.json` | What curators looked for and did not find, plus places where sources disagree. Shown on each guide. |
| `tools/libq.py` | Read-only helper for curators (search, read a page, find titles, encyclopedia lookup). |
| `tools/validate_topics.py` | Checks every curated id/page/encyclopedia path against a data folder (`--data` or `LASTBOOK_DATA`). Reads the ZIM files directly; no server needed. |
| `tools/build_map.py`, `tools/build_coast.py`, `tools/build_places.py` | Build the offline map and place finder into `derived/geo/` from library geography files (read only). |
| `derived/` | Generated data: `geo/map.sqlite` (1.7 GB, SoCal streets/buildings/water/help points), `geo/places.sqlite` (ZIP codes, towns, named places), `geo/socal.gpkg` (extracted copy), `cache/` (rendered PDF pages), `buildenv/` (pyosmium, build-time only). |

## Rebuilding derived data

```bash
cd /path/to/lastbook
unzip -o library-data/geography/openstreetmap/socal-latest-free.gpkg.zip -d derived/geo
library-data/runtime/macos-arm64/python/bin/python3 tools/build_map.py derived/geo/socal.gpkg derived/geo/map.sqlite
derived/buildenv/bin/python tools/build_coast.py library-data/geography/openstreetmap/socal-latest.osm.pbf derived/geo/map.sqlite
python3 tools/build_places.py
```

## How it stays correct as the library grows

- Nothing in `library-data` is written. Source details (publisher, edition, pages, video length, transcript)
  are read live from `catalog.json`, which the server reloads when the indexer rewrites it.
- Search runs on the library's own `search.sqlite` full-text index, so new downloads appear automatically.
  Queued downloads are not in the catalog and never show up as if they were available.
- Curated guides reference catalog ids. Re-run `tools/validate_topics.py` after big catalog changes.

## Integrating into the main library (port 8879) — not done, by design

`library.py`'s `write_index()` copies `library-data/app/index.html` to the root `index.html` on every rebuild,
so dropping files there alone would not work: this app needs the extra endpoints in `server.py`. Two options:

1. **Keep it separate (current, recommended).** Run `server.py` on 8890; it already serves all original files
   and APIs. Link it from the old site if wanted.
2. **Merge.** Add to the end of `library.py`, just before `if __name__ == '__main__':`, a guarded import such as
   `try: import survival_guide_ext; Handler = survival_guide_ext.extend(Handler)` and move `server.py`'s handler
   methods into that module, with `web/` copied to `library-data/app/` and `content/` + `derived/` reachable from it.
   Because `write_index()` regenerates `index.html` from `app/index.html`, the app's `index.html` would then
   survive re-indexing. This changes the shared server and should be done by whoever owns it.
