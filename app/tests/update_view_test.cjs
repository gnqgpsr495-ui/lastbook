// About's update box (web/update.js) with stand-in DOM and fetch: which button shows, and that only a click asks for Update now.
//   node app/tests/update_view_test.cjs
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'update.js'), 'utf8');

function box(state) {
  const asked = [];
  let onClick = null;
  const el = {
    innerHTML: '', textContent: '', isConnected: true,
    addEventListener: (_, fn) => { onClick = fn },
    querySelector: sel => ({ textContent: '', hidden: true, sel }),
  };
  const root = { querySelector: () => el };
  const ctx = {
    window: {}, location: { hash: '' }, navigator: {}, setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0,
    addEventListener: () => {}, document: { documentElement: { classList: { contains: () => false } }, addEventListener: () => {} },
    fetch: async (url, opts) => { asked.push([url, opts?.method || 'GET']); return { json: async () => (url.endsWith('/now') ? { started: true } : state) } },
  };
  vm.runInNewContext(SRC, ctx);
  return { LB: ctx.window.LBUpdate, el, root, asked, click: (upd) => onClick({ target: { closest: () => ({ dataset: { upd }, disabled: false, hidden: false }) } }) };
}

const tick = () => new Promise(r => setImmediate(r));
const offer = { state: 'available', version: '1.2.0', current: '1.1.15', download_url: 'https://lastbook.org/download/', can_open_download: true };

(async () => {
  // a trusted Mac build: Update now first, the download page beside it
  let b = box({ ...offer, can_update_now: true });
  b.LB.mount(b.root); await tick(); await tick();
  assert.match(b.el.innerHTML, /data-upd="now">Update now</);
  assert.match(b.el.innerHTML, /data-upd="open">Open download page</);
  assert.ok(!b.asked.some(([u]) => u.endsWith('/now')), 'nothing asks for Update now before the click');
  b.click('now'); await tick(); await tick();
  assert.deepStrictEqual(b.asked.filter(([u]) => u.endsWith('/now')), [['/api/update/now', 'POST']]);

  // Windows, Linux, or a Mac build without Sparkle: the download page only, clearly named
  b = box({ ...offer, can_update_now: false });
  b.LB.mount(b.root); await tick(); await tick();
  assert.doesNotMatch(b.el.innerHTML, /Update now/);
  assert.match(b.el.innerHTML, /<button class="btn" data-upd="open">Open download page</);

  // Sparkle failed to start: its error, and the download page
  b = box({ ...offer, can_update_now: false, update_now_error: 'The updater could not start (RuntimeError). Use the download page instead.' });
  b.LB.mount(b.root); await tick(); await tick();
  assert.match(b.el.innerHTML, /role="alert">The updater could not start/);
  assert.match(b.el.innerHTML, /Open download page/);
  console.log('update view: ok');
})().catch(e => { console.error(e); process.exit(1) });
