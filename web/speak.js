'use strict';
/* Read aloud, for when hands are busy: the system's own voices through the page's speechSynthesis. Only voices on this computer
   are used (localService): a voice that speaks through an online service would send the text off the computer, so it is never
   picked, and with no local voice the button is not shown at all. Nothing is downloaded and nothing is kept. */
const Speak = (() => {
  const synth = typeof speechSynthesis !== 'undefined' ? speechSynthesis : null;
  const MAX = 220;   // characters per utterance: long ones stop part way in some engines, so a page is spoken in short pieces
  let run = 0;       // the current reading; a newer one (or stop) makes an older one's callbacks do nothing

  const localVoices = () => (synth ? synth.getVoices() : []).filter(v => v.localService);
  function voice() {
    const all = localVoices(), want = (navigator.language || 'en').toLowerCase(), base = want.split('-')[0];
    return all.find(v => v.default && v.lang.toLowerCase().startsWith(base)) || all.find(v => v.lang.toLowerCase() === want)
      || all.find(v => v.lang.toLowerCase().startsWith(base)) || null;   // no voice in the reader's language: no reading
  }
  // Ready when the system has listed its voices (some list them a moment after the page loads).
  const ready = () => new Promise(res => {
    if (!synth) return res(false);
    if (synth.getVoices().length) return res(!!voice());
    const done = () => res(!!voice());
    synth.addEventListener('voiceschanged', done, { once: true });
    setTimeout(done, 1500);
  });

  // Text pulled from a PDF reads badly as it is: words broken across lines, bullets, page numbers on lines of their own.
  // Numbers are never changed: a dash before a digit is a minus (-18 °C), and a number alone on a line inside the page is part
  // of the text (a table cell, a quantity), so only one at the very start or end of the page is taken for a page number.
  function speakable(text) {
    return String(text || '')
      .replace(/(\p{L})[-\u00ad]\s*\n\s*(\p{Ll})/gu, '$1$2')          // recom-\nmended
      .replace(/^\s*(?:page\s+)?\d{1,4}[ \t]*(?:\n|$)/i, '')             // a page number alone on the first line
      .replace(/(?:^|\n)[ \t]*(?:page\s+)?\d{1,4}\s*$/i, '')             // ... or on the last line
      .replace(/^[ \t]*(?:[●•▪◦·∙*]+[ \t]*|[-–—]+[ \t]+(?!\d))/gm, '')   // bullets; a dash only with a space after it, no digit
      .replace(/[ \t]*\n[ \t]*\n\s*/g, '\u2029')                          // paragraphs
      .replace(/\s+/g, ' ')
      .replace(/\u2029/g, '\n')
      .trim();
  }
  function pieces(text) {
    const out = [];
    for (const para of speakable(text).split('\n')) {
      // A sentence ends at . ! ? ; : but not at a . or : between two digits (0.5 ml, 10:30), which would be read as two pieces.
      const sentences = para.match(/(?:\d[.:](?=\d)|[^.!?;:])+(?:[.!?;:]+["”’)]?|$)/g) || [];
      let cur = '';
      for (let s of sentences.map(x => x.trim()).filter(Boolean)) {
        while (s.length > MAX) {           // a very long sentence: break it at a comma or a space
          const cut = Math.max(s.lastIndexOf(', ', MAX), s.lastIndexOf(' ', MAX));
          const at = cut > MAX / 3 ? cut + 1 : MAX;
          if (cur) { out.push(cur); cur = '' }
          out.push(s.slice(0, at).trim()); s = s.slice(at).trim();
        }
        if (cur && (cur + ' ' + s).length > MAX) { out.push(cur); cur = s } else cur = cur ? cur + ' ' + s : s;
      }
      if (cur) out.push(cur);
    }
    return out.filter(p => /[\p{L}\p{N}]/u.test(p));
  }

  function stop() {
    run++;
    if (synth) synth.cancel();
  }
  // Speak the pieces one after another; onend runs only when the last one finished (not when stopped).
  function say(text, onend) {
    stop();
    const me = run, v = voice(), list = v ? pieces(text) : [];
    let i = 0;
    const next = () => {
      if (me !== run) return;
      if (i >= list.length) return onend && onend();
      const u = new SpeechSynthesisUtterance(list[i++]);
      u.voice = v; u.lang = v.lang; u.rate = 0.95;
      u.onend = next;
      u.onerror = e => { if (me === run && e.error !== 'interrupted' && e.error !== 'canceled') next() };
      synth.speak(u);
    };
    next();
    return list.length;
  }

  /* A Read aloud button: getText() gives what to read; then(), if given, runs when it has all been read (the next page). */
  function attach(btn, getText, then) {
    let on = false;
    const label = $('span', btn);
    // The name says what pressing it does, so it changes (Read aloud / Stop reading) and carries no aria-pressed: "Stop reading,
    // pressed" would say stopping is on. The look changes by shape, not colour alone: .reading swaps the speaker for a stop square,
    // which also shows in the Mac toolbar, where the button is an icon only.
    const show = v => {
      const say = v ? 'Stop reading' : 'Read aloud';
      on = v; btn.classList.toggle('reading', v); btn.title = say; btn.setAttribute('aria-label', say); if (label) label.textContent = say;
    };
    const onKey = e => { if (on && e.key === 'Escape') { stop(); show(false) } };   // Escape stops reading, as it stops an answer in Chat
    document.addEventListener('keydown', onKey);
    btn.addEventListener('click', async () => {
      if (on) { stop(); show(false); return }
      show(true);
      let text = '';
      try { text = await getText() } catch { }
      if (!on) return;   // stopped while the text was loading
      if (!say(text, () => { show(false); if (then) then() })) show(false);
    });
    ready().then(ok => { btn.hidden = !ok });
    return () => { stop(); show(false); document.removeEventListener('keydown', onKey) };
  }

  return { attach, stop, ready, _pieces: pieces, _speakable: speakable };   // _pieces, _speakable: for app/tests/test_speak.py
})();
