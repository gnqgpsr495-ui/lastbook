"""Watched markers, resume prompts, and Continue watching list consistency.

Runs the shipped JavaScript in Node with in-memory Storage and mock held items.
No browser, library, model or network is needed. Browser checks are separate.
"""
import shutil
import subprocess
import unittest
from pathlib import Path


class VideoWatched(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the video watched tests')
    def test_watched_state_consistency_and_resumable_list(self):
        result = subprocess.run(
            [shutil.which('node'), str(Path(__file__).with_name('video_watched_test.mjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"checks":8', result.stdout)


if __name__ == '__main__':
    unittest.main()
