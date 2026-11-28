"""Large, synthetic offline reading-catalog regression fixture.

No installed pack or redistributed content is required.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools.export_reading_catalog import export


class LargeReadingCatalogTests(unittest.TestCase):
    def test_five_thousand_titles_export_without_loss_or_unsafe_markup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog.json"
            output = root / "reading-catalog.html"
            records = [
                {
                    "kind": ("pdf", "html", "pptx")[i % 3],
                    "title": f"Title {i:05d} <&>",
                    "collection": f"Collection {i % 17:02d}",
                    "publisher": 'Publisher "sample"',
                }
                for i in range(5000)
            ]
            records.extend([
                {"kind": "video", "title": "Excluded video"},
                {"kind": ["pdf"], "title": "Malformed kind"},
                {"kind": "pdf", "title": ""},
            ])
            source.write_text(json.dumps(records), encoding="utf-8")

            self.assertEqual(export(source, output), 5000)
            page = output.read_text(encoding="utf-8")
            self.assertEqual(page.count("<tr><td>"), 5000)
            self.assertEqual(page.count("&lt;&amp;&gt;"), 5000)
            self.assertNotIn("Title 00000 <&>", page)
            self.assertNotIn("Excluded video", page)
            self.assertNotIn("Malformed kind", page)
            self.assertIn("Title 00000 &lt;&amp;&gt;", page)
            self.assertIn("Title 04999 &lt;&amp;&gt;", page)
            self.assertLess(page.index("Title 00000"), page.index("Title 00017"))
            self.assertIn('id="q"', page)
            self.assertIn('id="type"', page)
            self.assertIn('id="letter"', page)
            self.assertIn("r.cells[2].textContent===type.value", page)
            self.assertIn("title.charAt(0).toLocaleUpperCase()===letter.value", page)
            self.assertIn("n+' of '+rs.length+' titles'", page)

    def test_repeated_export_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog.json"
            first, second = root / "first.html", root / "second.html"
            records = [
                {"kind": "pdf", "title": f"Guide {i:05d}", "collection": "Guides"}
                for i in range(5000, 0, -1)
            ]
            source.write_text(json.dumps(records), encoding="utf-8")
            self.assertEqual(export(source, first), 5000)
            self.assertEqual(export(source, second), 5000)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
