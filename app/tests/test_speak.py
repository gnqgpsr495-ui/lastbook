"""Read aloud (web/speak.js): text pulled from a PDF is cleaned so it reads as sentences, then split into short pieces that
engines speak reliably, losing no words. Runs speak.js under Node. Needs Node on PATH; skipped without it. Never packaged."""
import json, re, shutil, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which('node')
RUN = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const Speak = new Function('$', 'navigator', src + '\nreturn Speak;')(() => null, { language: 'en-US' });
const out = JSON.parse(process.argv[2]).map(t => ({ clean: Speak._speakable(t), pieces: Speak._pieces(t) }));
process.stdout.write(JSON.stringify(out));
"""
# Shaped like the text tools/libq.py gives for a manual page: a running head, a page number alone, bullets, a word broken
# across lines, and a long sentence.
PAGE = """     NEW WHERE THERE IS NO DOCTOR: ADVANCE CHAPTERS
10   FIRST AID


   Tourniquets
   Use a tourniquet only as a last resort, when you are willing to risk the loss
   of an arm or leg in order to save a person's life.
      Use tourniquets only when:
   ··A limb is cut off or is so mangled that it clearly cannot be saved.
   ●  Heavy bleeding that does not slow down from an arm or leg with
      direct pressure. (Have you tried pressing harder first?)
   Other chemicals are not recom-
   mended and should not be used.
   """ + 'This sentence goes on and on, ' * 12 + """and ends here.

                                                                      27
"""


def words(s):
    return re.findall(r"[\w']+", s)


@unittest.skipUnless(NODE, 'needs Node')
class Speakable(unittest.TestCase):
    def run_js(self, *texts):
        r = subprocess.run([NODE, '-e', RUN, str(ROOT / 'web/speak.js'), json.dumps(texts)], capture_output=True, text=True, encoding='utf-8', check=True)
        return json.loads(r.stdout)

    def test_cleaned_for_listening(self):
        (got,) = self.run_js(PAGE)
        clean = got['clean']
        self.assertIn('recommended and should not be used', clean)        # the broken word is whole again
        self.assertNotIn('··', clean)
        self.assertNotIn('●', clean)
        self.assertNotRegex(clean, r'(^|\n)\s*27\s*($|\n)')                # the page number alone is gone
        self.assertIn('Use a tourniquet only as a last resort, when you are willing to risk the loss of an arm', clean)   # lines joined

    def test_pieces_are_short_and_lose_nothing(self):
        (got,) = self.run_js(PAGE)
        self.assertTrue(got['pieces'])
        self.assertTrue(all(len(p) <= 220 for p in got['pieces']), [len(p) for p in got['pieces']])
        self.assertEqual(words(' '.join(got['pieces'])), words(got['clean']))
        self.assertIn('(Have you tried pressing harder first?)', ' '.join(got['pieces']))

    def test_numbers_are_kept(self):
        # A first-aid library: a reading must never change a number.
        minus, alone, decimal, time, bullet = self.run_js('Keep below\n-18 °C', 'Mix\n10\ndrops per litre', 'Give 0.5 ml.',
                                                          'Take it at 10:30 each day.', 'Do this:\n- 2 tablets\n– wash hands')
        self.assertIn('-18', minus['clean'])
        self.assertIn('10', alone['clean'])
        self.assertIn('Mix 10 drops per litre', ' '.join(alone['pieces']))
        self.assertTrue(any('0.5' in p for p in decimal['pieces']), decimal['pieces'])
        self.assertEqual(decimal['pieces'], ['Give 0.5 ml.'])
        self.assertEqual(time['pieces'], ['Take it at 10:30 each day.'])
        self.assertIn('- 2 tablets', bullet['clean'])                     # a dash before a digit is not taken for a bullet
        self.assertIn('wash hands', bullet['clean'])
        self.assertNotIn('–', bullet['clean'])                            # a dash bullet before words still goes

    def test_page_number_only_at_the_ends(self):
        first, last, inside = self.run_js('12\nBoil water for one minute.', 'Boil water for one minute.\n  Page 12  \n',
                                          'Boil water for\n1\nminute.')
        self.assertEqual(first['clean'], 'Boil water for one minute.')
        self.assertEqual(last['clean'], 'Boil water for one minute.')
        self.assertEqual(inside['clean'], 'Boil water for 1 minute.')

    def test_nothing_to_say(self):
        a, b = self.run_js('', '   12   \n\n  ●  \n')
        self.assertEqual(a['pieces'], [])
        self.assertEqual(b['pieces'], [])

    def test_other_scripts(self):
        (got,) = self.run_js('Agua segura: hiérvala un minuto. Después, déjela enfriar.')
        self.assertEqual(got['pieces'], ['Agua segura: hiérvala un minuto. Después, déjela enfriar.'])



BUTTON = r"""
// Speak.attach on a stand-in button, with one local voice: click, what the button says and shows, then Escape.
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const keys = [], spoken = [];
let cancels = 0;
const document = { addEventListener: (t, f) => t === 'keydown' && keys.push(f), removeEventListener: (t, f) => { const i = keys.indexOf(f); if (i >= 0) keys.splice(i, 1) } };
const voice = { localService: true, default: true, lang: 'en-US' };
const speechSynthesis = { getVoices: () => [voice], speak: u => spoken.push(u.text), cancel: () => cancels++, addEventListener() {} };
class SpeechSynthesisUtterance { constructor(t) { this.text = t } }
const attrs = {}, classes = new Set(), label = { textContent: 'Read aloud' };
let onclick = null;
const btn = { hidden: true, title: '', setAttribute: (k, v) => attrs[k] = String(v), removeAttribute: k => delete attrs[k],
              classList: { toggle: (c, on) => on ? classes.add(c) : classes.delete(c) }, addEventListener: (t, f) => onclick = f };
const Speak = new Function('$', 'navigator', 'document', 'speechSynthesis', 'SpeechSynthesisUtterance', src + '\nreturn Speak;')(
  () => label, { language: 'en-US' }, document, speechSynthesis, SpeechSynthesisUtterance);
const look = () => ({ name: attrs['aria-label'], title: btn.title, label: label.textContent, pressed: 'aria-pressed' in attrs, reading: classes.has('reading') });
(async () => {
  const leave = Speak.attach(btn, async () => 'Boil water for one minute.');
  await new Promise(r => setTimeout(r, 10));
  const out = { shown: !btn.hidden };
  await onclick(); out.on = look(); out.spoken = spoken.slice();
  keys.forEach(f => f({ key: 'Enter' })); out.after_enter = look();
  keys.forEach(f => f({ key: 'Escape' })); out.after_escape = look(); out.cancels = cancels;
  leave(); out.listeners_left = keys.length;
  process.stdout.write(JSON.stringify(out));
})();
"""


@unittest.skipUnless(NODE, 'needs Node')
class Button(unittest.TestCase):
    """The #117 accessibility review: the button's name says what it does, with no aria-pressed ("Stop reading, pressed"); its look
    changes by class (a stop square, also in the icon-only toolbar); Escape stops reading; leaving the page removes the key listener."""

    def test_name_look_and_escape(self):
        r = subprocess.run([NODE, '-e', BUTTON, str(ROOT / 'web' / 'speak.js')], check=True, capture_output=True, text=True, encoding='utf-8')
        out = json.loads(r.stdout)
        self.assertTrue(out['shown'])
        self.assertEqual(out['on'], {'name': 'Stop reading', 'title': 'Stop reading', 'label': 'Stop reading', 'pressed': False, 'reading': True})
        self.assertEqual(out['spoken'], ['Boil water for one minute.'])
        self.assertTrue(out['after_enter']['reading'])                  # other keys leave it reading
        self.assertEqual(out['after_escape'], {'name': 'Read aloud', 'title': 'Read aloud', 'label': 'Read aloud', 'pressed': False, 'reading': False})
        self.assertGreaterEqual(out['cancels'], 2)                      # once before speaking, once on Escape
        self.assertEqual(out['listeners_left'], 0)

    def test_the_page_shows_what_it_only_said(self):
        """A page with no text, or one that could not be fetched, is shown in a toast (role=status), not only spoken; and after
        reading goes on to the next page by itself, focus returns to the button."""
        app = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("toast('This page has no text that can be read aloud.')", app)
        self.assertIn("toast('This page could not be read aloud. Try again.')", app)
        self.assertIn('focusAfterRoute = sb;', app)
        self.assertNotIn('data-speak hidden aria-pressed', app)
        css = (ROOT / 'web' / 'app.css').read_text(encoding='utf-8')
        self.assertIn('[data-speak].reading .i-stop{display:inline', css)


if __name__ == '__main__':
    unittest.main()
