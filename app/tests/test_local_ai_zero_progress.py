"""Regression checks for local AI's explicit 0% startup state."""
import json
import queue
import re
import threading
import unittest
from pathlib import Path
from unittest import mock

from llm_local import Local

ROOT = Path(__file__).resolve().parents[2]
CHAT = ROOT / "web" / "chat.js"
LOADER = ROOT / "llm_local.py"
INDEX = ROOT / "web" / "index.html"


class LocalAiZeroProgressTests(unittest.TestCase):
    def test_zero_percent_is_not_treated_as_missing_progress(self):
        source = CHAT.read_text(encoding="utf-8")
        self.assertIn("m.state === 'starting' && m.pct != null ? Math.max", source)
        self.assertIn("l.pct != null ? ' ' + l.pct + '%' : '…'", source)
        self.assertIn("m.state === 'starting' && m.pct != null ? ` ${m.pct}%` : ''", source)
        self.assertNotIn("m.state === 'starting' && m.pct ? ", source)
        self.assertNotIn("l.pct ? ' ' + l.pct", source)

    def test_initial_unknown_progress_and_shipped_first_load_wording(self):
        loader = LOADER.read_text(encoding="utf-8")
        source = CHAT.read_text(encoding="utf-8")
        self.assertIn("self.state, self.pct, self.message = 'loading', None, ''", loader)
        self.assertIn("Local AI available · your first question loads it and may take a while", source)
        self.assertIn("if self.proc is proc:", loader)
    def test_runner_zero_percent_event_is_retained(self):
        # Execute the real reader, rather than depending on how it spells an
        # assignment. Inspect state before the fake process reaches EOF.
        local = object.__new__(Local)
        local.lock = threading.RLock()
        local.pct = None
        local.state = 'loading'
        local.proc = None
        local.furthest = 0
        local.t_progress = 0
        local.failed_loads = 0
        local.message = ''
        events = queue.Queue()

        class Process:
            def __init__(self):
                self.stdout = self.lines()

            def lines(self):
                yield json.dumps({'ev': 'progress', 'p': 0})
                self_owner.assertEqual(local.pct, 0)
                yield json.dumps({'ev': 'progress', 'p': 5})
                self_owner.assertEqual(local.pct, 5)

            def wait(self):
                return 0

        self_owner = self
        proc = Process()
        local.proc = proc
        local._read(proc, events)
        self.assertEqual(local.furthest, 5)
        self.assertEqual(events.get_nowait(), {'ev': 'exit', 'code': 0})

    def test_chat_asset_version_bumped(self):
        index = INDEX.read_text(encoding="utf-8")
        asset = re.search(r'<script src="/ui/chat\.js\?v=(\d+)"></script>', index)
        self.assertIsNotNone(asset)
        self.assertGreaterEqual(int(asset.group(1)), 15)

    def test_chat_asset_version_check_keeps_the_minimum(self):
        # Later chat changes must not fail this check, but an old or unversioned script must.
        for version, accepted in ((14, False), (15, True), (16, True), (100, True),
                                  (None, False), ('invalid', False)):
            with self.subTest(version=version):
                query = '' if version is None else f'?v={version}'
                index = f'<script src="/ui/chat.js{query}"></script>'
                with mock.patch.object(Path, 'read_text', return_value=index):
                    if accepted:
                        self.test_chat_asset_version_bumped()
                    else:
                        with self.assertRaises(AssertionError):
                            self.test_chat_asset_version_bumped()

    def test_unknown_progress_still_uses_starting_ellipsis(self):
        source = CHAT.read_text(encoding="utf-8")
        self.assertIn("l.pct != null ? ' ' + l.pct + '%' : '…'", source)
        self.assertIn("pct === null ? ' run' : ''", source)
        self.assertIn("Starting the local AI", source)


if __name__ == "__main__":
    unittest.main()
