"""PDF keyboard navigation in the off-screen Mac shell, using a three-page fixture.

Run with the macOS requirements installed: python -B app/tests/mac_reader_keys.py
"""
import json
import sys
import tempfile
import time
from pathlib import Path

import pypdfium2
import mac_driver


def make_library(data):
    lib = data / 'library-data'
    (lib / 'documents').mkdir(parents=True)
    pdf_path = lib / 'documents/test.pdf'
    pdf = pypdfium2.PdfDocument.new()
    try:
        for _ in range(3):
            pdf.new_page(300, 400).close()
        pdf.save(pdf_path)
    finally:
        pdf.close()
    (lib / 'catalog.json').write_text(json.dumps([{
        'id': 'test-pdf', 'kind': 'pdf', 'title': 'Test document',
        'path': 'documents/test.pdf', 'pages': 3,
    }]), encoding='utf-8')
    (lib / 'text').mkdir()
    (lib / 'text/test-pdf.txt').write_text('First page\fSecond page\fThird page', encoding='utf-8')


def press(run, key, selector=None, *, alt=False, shift=False, page=None):
    return run.js(f"""
      const selector = {json.dumps(selector)};
      if (selector) document.querySelector(selector).focus();
      const target = document.activeElement;
      target.dispatchEvent(new KeyboardEvent('keydown', {{
        key: {json.dumps(key)}, bubbles: true, cancelable: true, altKey: {json.dumps(alt)},
        shiftKey: {json.dumps(shift)}
      }}));
      const page = {json.dumps(None if page is None else str(page))};
      if (page !== null) await until(() => document.querySelector('#pg')?.value === page, 1500);
      await sleep(100);
      return {{ page: document.querySelector('#pg')?.value, focus: document.activeElement?.id,
                hash: location.hash }};
    """)


def check(run):
    deadline = time.monotonic() + 20
    while (loaded := run.js("return document.readyState === 'complete' && typeof reader === 'function'", timeout=3)) is not True:
        assert time.monotonic() < deadline, loaded
        time.sleep(0.1)
    run.go('#/read/test-pdf?p=1&from=%23%2Flibrary', '#pg')
    assert run.js("return document.activeElement.id") == 'pageTop'
    first = press(run, 'ArrowLeft', page=1)
    assert first == {'page': '1', 'focus': 'pageTop', 'hash': '#/read/test-pdf?p=1&from=%23%2Flibrary'}, first

    second = press(run, 'ArrowRight', page=2)
    assert second == {'page': '2', 'focus': 'pageTop', 'hash': '#/read/test-pdf?p=2&view=page&from=%23%2Flibrary'}, second
    third = press(run, 'ArrowRight', page=3)
    assert third['page'] == '3', third
    assert press(run, 'ArrowRight', page=3) == third
    assert press(run, 'ArrowLeft', '#pg', page=3)['page'] == '3'

    run.go('#/read/test-pdf?p=3&view=text', '.pagetext')
    modified = press(run, 'ArrowLeft', alt=True, page=3)
    assert modified['page'] == '3', modified
    text = press(run, 'ArrowLeft', page=2)
    assert text['hash'] == '#/read/test-pdf?p=2&view=text', text
    run.go('#/read/test-pdf?p=2&view=text', '.pagetext')
    assert run.js("return document.activeElement.id") == 'pageTop'
    for key in ('ArrowRight', 'ArrowLeft'):
        selecting = press(run, key, shift=True, page=2)    # Shift+Arrow is left for selecting text
        assert selecting['hash'] == '#/read/test-pdf?p=2&view=text', selecting

    run.go('#/about', '#main h1')
    about = run.js("return location.hash")
    assert press(run, 'ArrowLeft')['hash'] == about


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='lastbook-reader-') as folder:
        mac_driver.DATA = Path(folder) / 'LastbookData'
        mac_driver.PY = Path(sys.executable)
        make_library(mac_driver.DATA)
        run = mac_driver.Run('reader-keys')
        try:
            check(run)
            print('PDF keyboard navigation passed', flush=True)
        finally:
            run.stop()
