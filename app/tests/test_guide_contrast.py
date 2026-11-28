"""Guide colours used as text, and the toolbar search's focus ring, measured as WCAG contrast (#237).

Each guide has one colour (TC in web/app.js). Where that colour is the colour of small text, web/app.css mixes it toward
black in light mode and toward white in dark mode. This reads the colours and the mixes from the two files and works out
the contrast the browser would draw, so a new guide colour or a changed card colour that falls under the line fails here.

    python3 -B -m unittest app.tests.test_guide_contrast
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT = 4.5      # WCAG 2.2 SC 1.4.3: text under 18.66px bold
MARK = 3.0      # SC 1.4.11: a focus mark against what is next to it


def linear(hex_):
    """'#rrggbb' as linear-light red, green, blue."""
    h = hex_.lstrip('#')
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))]


def gamma(rgb):
    return [min(1.0, max(0.0, 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)) for c in rgb]


def drawn(rgb):
    """The colour as a screen shows it: rounded to 8 bits a channel."""
    return linear('#%02x%02x%02x' % tuple(round(c * 255) for c in gamma(rgb)))


def contrast(a, b):
    la, lb = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] for c in (drawn(a), drawn(b)))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def oklab(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s]


def from_oklab(lab):
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s]


def mix_oklab(a, share, b):
    """color-mix(in oklab, a share, b)"""
    x, y = oklab(a), oklab(b)
    return from_oklab([x[i] * share + y[i] * (1 - share) for i in range(3)])


def mix_srgb(a, share, b):
    """color-mix(in srgb, a share, b)"""
    x, y = gamma(a), gamma(b)
    return linear('#%02x%02x%02x' % tuple(round((x[i] * share + y[i] * (1 - share)) * 255) for i in range(3)))


class Sheet:
    """What this test needs from web/app.css and web/app.js."""

    def __init__(self):
        self.css = (ROOT / 'web' / 'app.css').read_text(encoding='utf-8')
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.guides = dict(re.findall(r"(\w+): '(#[0-9a-fA-F]{6})'", re.search(r'const TC = \{(.*?)\};', js, re.S).group(1)))
        self.guides['(no guide)'] = re.search(r"TC\[id\] \|\| '(#[0-9a-fA-F]{6})'", js).group(1)
        dark = self.css.index('/* dark mode: the guide colours are dark inks')
        self.dark = self.css[dark:self.css.index('\n}', dark)]

    def tokens(self, opening):
        """The colour tokens of the block that starts with `opening`, as {name: '#rrggbb'}."""
        start = self.css.index(opening)
        return dict(re.findall(r'--([\w-]+):(#[0-9a-fA-F]{6})\b', self.css[start:self.css.index('}', start)]))

    def looks(self):
        """Each look the app has: its name, whether it is dark, and its tokens."""
        mac = self.tokens(':root{')
        mac_dark = {**mac, **self.tokens('@media (prefers-color-scheme:dark){:root{')}
        win = {**mac, **self.tokens('html.plat-win{')}
        win_dark = {**mac_dark, **self.tokens('@media (prefers-color-scheme:dark){html.plat-win{')}
        return [('Mac light', False, mac), ('Mac dark', True, mac_dark), ('Windows light', False, win), ('Windows dark', True, win_dark)]

    def rule(self, selector, where=None):
        where = self.css if where is None else where
        m = re.search(r'(?:^|[},\n])\s*' + re.escape(selector) + r'(?:,[^{]*)?\{([^}]*)\}', where)
        if not m:
            raise AssertionError(f'no rule for {selector}')
        return m.group(1)

    def colour(self, body, prop, guide, tok):
        """The value of `prop` in a rule's body, worked out for one guide colour."""
        value = re.search(r'(?:^|;)' + prop + r':([^;]+)', body).group(1).strip()
        mix = re.fullmatch(r'color-mix\(in (oklab|srgb),var\(--tc\) (\d+)%,(#[0-9a-fA-F]{3,6}|var\(--[\w-]+\))\)', value)
        if mix:
            return (mix_oklab if mix.group(1) == 'oklab' else mix_srgb)(guide, int(mix.group(2)) / 100, self.named(mix.group(3), tok))
        return guide if value == 'var(--tc)' else self.named(value, tok)

    @staticmethod
    def named(value, tok):
        if value.startswith('var(--'):
            value = tok[value[6:-1]]
        if len(value) == 4:
            value = '#' + ''.join(c * 2 for c in value[1:])
        return linear(value)


class GuideColoursAsText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Sheet()

    def each(self):
        for look, dark, tok in self.s.looks():
            for name, hex_ in self.s.guides.items():
                yield look, dark, tok, name, linear(hex_)

    def body(self, selector, dark):
        """The rule that decides a selector's colours: the dark-mode one where there is one, else the ordinary one."""
        if dark:
            return self.s.rule(':root ' + selector, self.s.dark)
        return self.s.rule(selector)

    def test_the_files_were_read(self):
        self.assertGreaterEqual(len(self.s.guides), 15)
        self.assertEqual([tok['paper'] for _, _, tok in self.s.looks()], ['#f5f5f7', '#28282a', '#ffffff', '#2d2d2d'])

    def test_step_count_on_a_skill_card(self):
        for look, dark, tok, name, guide in self.each():
            with self.subTest(look=look, guide=name):
                ink = self.s.colour(self.body('.skill .steps', dark), 'color', guide, tok)
                self.assertGreaterEqual(contrast(ink, linear(tok['paper'])), TEXT)

    def test_number_of_a_route_step(self):
        """The number sits on a tint of the guide colour over the card, so it is measured against that tint."""
        for look, dark, tok, name, guide in self.each():
            with self.subTest(look=look, guide=name):
                ink = self.s.colour(self.body('.step::before', dark), 'color', guide, tok)
                tint = self.s.colour(self.s.rule('.step::before'), 'background', guide, tok)
                self.assertGreaterEqual(contrast(ink, tint), TEXT)

    def test_tick_of_a_practised_step(self):
        for look, dark, tok, name, guide in self.each():
            with self.subTest(look=look, guide=name):
                body = self.body('.step.done::before', dark)
                self.assertGreaterEqual(contrast(self.s.colour(body, 'color', guide, tok), self.s.colour(body, 'background', guide, tok)), TEXT)

    def test_the_plain_guide_colour_would_not_pass(self):
        """What this guards against: Power systems' amber as it is, on a light card, and Repair's slate on a dark one."""
        looks = {look: tok for look, _, tok in self.s.looks()}
        self.assertLess(contrast(linear(self.s.guides['energy']), linear(looks['Mac light']['paper'])), TEXT)
        self.assertLess(contrast(linear(self.s.guides['repair']), linear(looks['Mac dark']['paper'])), TEXT)


class ToolbarSearchFocus(unittest.TestCase):
    def test_the_ring_is_clear_against_the_toolbar(self):
        """On a Mac the ring is the field's only focus mark (the outline is taken off), so it needs 3:1 against the toolbar."""
        s = Sheet()
        ring = re.search(r'box-shadow:0 0 0 3px ([^;}]+)', s.rule('.plat-mac .top-search input:focus')).group(1)
        self.assertEqual(ring, 'var(--focus)')      # a part-transparent ring was 2.0:1 in light and 2.7:1 in dark
        for look, _, tok in s.looks()[:2]:
            with self.subTest(look=look):
                self.assertGreaterEqual(contrast(linear(tok['focus']), linear(tok['bg'])), MARK)


if __name__ == '__main__':
    unittest.main()
