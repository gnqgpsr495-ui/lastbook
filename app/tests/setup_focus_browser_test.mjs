// Runs web/setup.html in a real headless Chrome or Chromium (over DevTools, no packages needed) with a stub setup API, to check
// that a background ask for the library list leaves keyboard focus on the control that had it, and the screen the person opened.
// Usage: node app/tests/setup_focus_browser_test.mjs   (exit 1 on a failed check, 2 when no browser is found; CHROME names one)
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../web');
const browser = [process.env.CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
].find(p => p && existsSync(p));
if (!browser) { console.log('skip: no Chrome or Chromium found (set CHROME)'); process.exit(2) }

const sleep = ms => new Promise(r => setTimeout(r, ms));
const pack = { id: 'small', title: 'Small', available: true, summary: 's', installed_bytes: 1e9, download_bytes: 5e8, files: [] };
const state = (packs, current = null) => ({ mode: current ? 'manage' : 'first-run', hardware: { disks: [], ai: { fits: false } },
  manifest: { packs, models: [], maps: [] }, current, found: [], recommend: { folder: '/x' }, job: null });
const library = { pack: 'small', folder: '/x/LastbookData', model: null };

// state answers: the first at once (`first`), each later one held until the test gives it
const asked = [], held = [];
let updAsks = 0;
let first = state([]);
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  const send = (type, body) => { res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' }); res.end(body) };
  if (url.pathname === '/api/setup/state') {
    asked.push(Date.now());
    if (asked.length === 1) return send('application/json', JSON.stringify(first));
    return held.push(d => send('application/json', JSON.stringify(d)));
  }
  if (url.pathname === '/api/setup/updates') { updAsks++; return send('application/json', JSON.stringify({ supported: true, notify: true })) }   // main's update-notice preference, ticked
  if (url.pathname === '/api/setup/pick') return send('application/json', JSON.stringify({ path: '/Volumes/USB', free_bytes: 64e9, disk: 'USB' }));
  if (url.pathname.startsWith('/api/')) return send('application/json', '{}');
  const file = url.pathname === '/setup.html' ? 'setup.html' : url.pathname.replace(/^\/ui\//, '');
  const p = path.join(WEB, path.normalize(file));
  if (!p.startsWith(WEB) || !existsSync(p)) { res.writeHead(404); return res.end() }
  send({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml' }[path.extname(p)] || 'application/octet-stream', readFileSync(p));
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;

const profile = mkdtempSync(path.join(os.tmpdir(), 'lastbook-focus-'));
const chrome = spawn(browser, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
let bad = 0;
const done = code => { try { chrome.kill() } catch { } server.close(); try { rmSync(profile, { recursive: true, force: true }) } catch { } process.exit(code) };
const check = (name, ok) => { if (!ok) { bad++; console.log('FAIL', name) } else console.log('ok  ', name) };
setTimeout(() => { console.log('FAIL timed out'); done(1) }, 30000).unref();

let port;
for (let i = 0; i < 100 && !port; i++) {
  await sleep(100);
  try { port = readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0] } catch { }
}
const page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let n = 0;
const waiting = new Map();
ws.addEventListener('message', e => {
  const m = JSON.parse(e.data);
  const id = m && m.id;
  if (!Number.isSafeInteger(id) || id <= 0) return;
  const resolve = waiting.get(id);
  if (typeof resolve !== 'function') return;
  waiting.delete(id);
  resolve(m);
});
const cdp = (method, params = {}) => new Promise(r => { const id = ++n; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })) });
const js = async expr => (await cdp('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result.value;
const until = async (what, test) => { for (let i = 0; i < 200; i++) { if (await test()) return true; await sleep(25) } console.log('FAIL waiting for', what); done(1) };

await cdp('Page.enable');
await cdp('Page.addScriptToEvaluateOnNewDocument', { source: 'const __st = setTimeout; window.setTimeout = (f, ms, ...a) => __st(f, Math.min(ms || 0, 50), ...a);' });
await cdp('Page.navigate', { url: `${base}/setup.html` });
await until('the first screen', () => js(`!!document.querySelector('#haveFile')`));
await js(`window.__btn = document.querySelector('#haveFile'); __btn.focus(); document.activeElement === __btn`);
await until('a background ask', () => held.length === 1);

held.shift()(state([]));                       // the same empty list again
await until('the next ask', () => held.length === 1);
check('an unchanged answer keeps focus on the same button', await js(`document.activeElement === window.__btn`));

held.shift()(state([pack]));                   // now the list is filled: the screen is drawn again
await until('the filled list', () => js(`document.querySelector('#main').innerHTML.includes('Small')`));
check('the list was drawn again', await js(`document.querySelector('#haveFile') !== window.__btn`));
check('and focus is on the new button', await js(`document.activeElement && document.activeElement.id === 'haveFile'`));
check('not on the page body', await js(`document.activeElement !== document.body`));
check('a redrawn screen keeps the update-notice preference', await js(`!!document.querySelector('#updBox') && document.querySelector('#updBox').checked`));

// wonderdawg on #199: Manage with an empty list; Copy is opened while the background ask is on its way; the filled list
// that then arrives keeps Copy on screen, and is there on going back.
asked.length = 0; held.length = 0; updAsks = 0; first = state([], library);
await cdp('Page.navigate', { url: `${base}/setup.html` });
await until('Manage', () => js(`!!document.querySelector('#copyOut')`));
const emptyManage = await js(`document.querySelector('#main').innerHTML.includes('Small')`);
await until('a background ask', () => held.length === 1);
await js(`document.querySelector('#copyOut').click()`);
await until('Copy', () => js(`!!document.querySelector('#copyGo')`));
held.shift()(state([pack], library));
await sleep(300);
check('a background answer leaves Copy on screen', await js(`!!document.querySelector('#copyGo')`));
await js(`document.querySelector('#copyBack').click()`);
await until('Manage again', () => js(`!!document.querySelector('#copyOut')`));
check('and Manage has the newer list on going back', !emptyManage && await js(`document.querySelector('#main').innerHTML.includes('Small')`));
check('with the update-notice preference still ticked', await js(`!!document.querySelector('#updBox') && document.querySelector('#updBox').checked`));
check('and updates was asked once, not again in the background', updAsks === 1);
done(bad ? 1 : 0);
