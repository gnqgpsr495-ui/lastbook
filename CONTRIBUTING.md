# Contributing to Lastbook

Thank you for helping. Lastbook is meant for the day the internet is gone, so what matters most is that it works offline,
stays correct, and never sends anything anywhere.

## Set up

1. Clone the repository and make a virtual environment with Python 3.11 or later.
2. Install the requirements for your platform: `packaging/requirements_macos.txt` (Mac) or
   `packaging/requirements_app.txt` (Windows). On Linux, use `packaging/linux/requirements_linux.txt` in a virtual
   environment made with `--system-site-packages`, and start the app with `packaging/linux/run_source_linux.sh` so videos
   play. The README's "Run from source" section lists the packages it needs.
3. Get a data folder: run `python app/main.py` and let setup download the Small pack, or unzip a pack from lastbook.org.
   Point the app at it with `--data` or `LASTBOOK_DATA`.

The README explains the layout and how to build the apps.

## Test

```bash
python3 -B -m unittest app.tests.test_readable app.tests.test_bridge app.tests.test_setup app.tests.test_data_folder app.tests.test_what_ships app.tests.test_update app.tests.test_address_search app.tests.test_topic_search app.tests.test_chat_steps app.tests.test_validate_topics app.tests.test_libq app.tests.test_video_transcripts app.tests.test_video_moments app.tests.test_video_watched app.tests.test_library_extract app.tests.test_shell_macos app.tests.test_run_source_linux app.tests.test_i18n_catalogs app.tests.test_page_tables
```

Run these before you open a pull request (`test_topic_search`, `test_video_moments` and `test_video_watched` need Node and are skipped without it; `test_shell_macos` needs a Mac with PyObjC and is skipped elsewhere; `test_run_source_linux` needs bash and is skipped on Windows). If you change the packaging, also run the build for your platform: it ends
with a package scan, and that scan must pass. If you change a guide in `content/`, run `tools/validate_topics.py`
against a library, so every id, page and encyclopedia path it cites still exists:

```bash
python3 tools/validate_topics.py --data /path/to/LastbookData      # or set LASTBOOK_DATA
```

It reads the library's files directly and needs no server. `tools/libq.py` takes the same `--data` and finds and reads
the page you mean to cite: `python3 tools/libq.py --data /path/to/LastbookData search "boil water"`.

For translation changes, update the UTF-8 JSON in `translations/desktop/`. Run
`python3 -B packaging/i18n_catalogs.py` and commit the two generated web
assets. Run the localization engine tests with
`node --test app/tests/i18n_core_test.cjs`. For web or packaging changes to
this feature, see the browser and native checks. [Localization guide](docs/i18n.md)
The browser and Linux checks use optional development tools (Playwright, `python3-pyatspi`, `xdotool`). They are
not installed by the requirements files, are never packaged, and are listed with their licences in
`THIRD_PARTY_NOTICES.md`.

## Rules that keep Lastbook what it is

**No network.** The app opens no port. Setup downloads and app update checks use
`engine/setup/download.py` and reach only the hosts in `ALLOWED_HOSTS`.

- No telemetry, analytics, crash reporting, fonts or scripts from the web. App update checks
  (`engine/update.py`) use only `downloads.lastbook.org`. The person can check manually or opt into daily notices.
  Notices default to off. **Open download page** opens the official download page only when the person selects it.
  **Update now** (Mac builds with a pinned Sparkle and its public key only: `docs/UPDATE-NOW-MAC.md`) starts Sparkle on that click,
  never before. Sparkle does not check or download in the background.
- Our own pages (`web/`) contain no web address. The build fails if they do. The desktop **Open GitHub** action hands the fixed project repository address to the system browser after a user click. Lastbook makes no request for that action.
- A new dependency must work fully offline, and must not open a socket or start a server. Say in the pull request what
  it is, its licence, and why it is needed, and add it to `THIRD_PARTY_NOTICES.md`.
- The local AI runner stays socket-free: no RPC backend, no HTTP server, no download code.

**General wording, no household.** Lastbook began as one household's library. The shipped guides use general wording, and
nothing shared may name a real person's home, street, coordinates, machines or accounts.

- Write guides for any reader in any place. Name a region only when the source is about that region.
- Never commit `web/home-area.json`, a private word list, real coordinates of a home, user or machine names, LAN
  addresses, keys or tokens. Test paths use placeholders such as `/path/to/lastbook` and `C:\Users\you\app-test`.
- To keep your own words out of a build, put them in a local copy of `packaging/ship_edits.json` (`forbidden`) and do not
  commit it.

**Sources first.** A guide card points at a real page of a real source in the library, with its page number. If the
library does not cover something, record that in `content/gaps.json` instead of writing advice from memory.

**Text the project keeps as UTF-8 is read and written as UTF-8.** On Windows, Python before 3.15 uses the
system's locale encoding for text unless told otherwise or UTF-8 Mode is on (often cp1252), so code that works on a Mac or
Linux can stop there with `UnicodeDecodeError: 'charmap' codec ...` (#170, #290). Python 3.15 turns UTF-8 Mode on by
default ([PEP 686](https://peps.python.org/pep-0686/)), but Lastbook supports 3.11 and later, so say the encoding
anyway. On 3.15 or later the failure no longer shows up, so to check a change, run it with `PYTHONUTF8=0` or on an
older Python.

- For the project's own text files (Python, `web/`, `content/`, JSON and Markdown), pass `encoding='utf-8'` to `open()`,
  `Path.read_text()` and `Path.write_text()`. Binary reads (`'rb'`, `read_bytes()`) take no encoding.
- For a subprocess known to print UTF-8, such as Node in the tests, pass `encoding='utf-8'` with `text=True`. Other
  programs may use another encoding: check what yours prints before choosing one.
- Don't rely on `PYTHONUTF8=1` or `python -X utf8` being set: other people's computers don't have it.
- AI coding agents often leave the encoding out. If you use one, give it this rule (in its instructions file, for
  example `AGENTS.md` or `CLAUDE.md`) and check its changes for it.

**Plain words.** Interface text is short, concrete and calm. Many readers will be stressed, tired, or reading in a second
language.

## Pull requests

- Keep each change small and about one thing, and say what you checked and how.
- Screenshots help for any change you can see, in light and dark mode, on Mac and on Windows if you can.
- Be ready to explain anything that touches setup, the bridge, the scans or the downloader. These keep people's libraries
  safe and their computers private.

## Reporting a security or privacy problem

Do not open a public issue. Email hello@lastbook.org with what you found and how to reproduce it.

## Code of conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
