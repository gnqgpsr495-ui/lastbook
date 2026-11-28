/* Check for updates, in About (desktop app only). A check runs when the person presses Check for updates, or chooses
   Lastbook > Check for Updates… (the menu calls LBUpdate.fromMenu; no address starts it). It only says whether a newer version
   is on the website, and no system notification is shown. engine/update.py does the check.

   When a newer version is known, About offers Update now only where the app can update itself (a Mac build with a trusted Sparkle
   setup: can_update_now). Pressing it starts the native updater, which asks before installing and relaunches Lastbook; this page
   sends no address or file. Everywhere else, and whenever that fails, the button is Open download page (the system browser).

   Opt-in notices (watch): the sidebar's "Update available" row, shown only while "Notify me about app updates" is on (Setup,
   Settings) and a check found a newer version for this system. This page only nudges the engine (POST /api/update/auto) soon after
   it opens, every hour, and when the system says it is online again; the engine decides whether a check is due (at most one a day,
   and none at all unless the setting is on). Failures say nothing. */
(() => {
  const E = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const HOUR = 60 * 60 * 1000, FIRST = 5000, POLL = 2000;
  let timer = null, menuAsked = false, row = null, rowTimer = null;

  async function call(action) {
    const get = action === 'state' || action === 'notice';
    const r = await fetch('/api/update/' + action, get ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    return r.json();
  }

  function view(s) {
    const btn = (t) => `<button class="btn plain" data-upd="check">${t}</button>`;
    const ver = s.current ? `Version ${E(s.current)}.` : 'This copy has no version number (it was not built as an app).';
    /* The last verified notice stands in only when there is no newer verdict: nothing checked by the person yet (idle, which is
       also what an automatic check looks like here, so its failures stay quiet), or the person's own check failed (error, e.g.
       offline), where the failure is shown above the still-valid offer. up_to_date, too_old_os and not_published replace it. */
    const failed = s.state === 'error';
    const found = s.state === 'available' ? s.version : s.state === 'idle' || failed ? s.notice : null;
    const now = !!s.can_update_now;
    if (found) return `${ver}${failed ? ` <span class="upd-line" role="alert">${E(s.message)}</span>` : ''} Version ${E(found)} is available${failed ? ' (found by an earlier check)' : ''}.
      <span class="upd-line">${now ? 'Update now asks you to confirm, installs the signed update and restarts Lastbook. Your library, settings and chats stay as they are.'
                                    : 'Run the installer to update Lastbook and keep your existing library.'}</span>
      ${s.update_now_error ? `<span class="upd-line" role="alert">${E(s.update_now_error)}</span>` : ''}
      <span class="upd-actions">
        ${now ? '<button class="btn" data-upd="now">Update now</button>' : ''}
        ${s.can_open_download ? `<button class="btn${now ? ' plain' : ''}" data-upd="open">Open download page</button>` : ''}
        ${s.download_url ? `<button class="btn plain" data-upd="copy" data-url="${E(s.download_url)}"${s.can_open_download ? ' hidden' : ''}>Copy download link</button>` : ''}
        ${btn(failed ? 'Try again' : 'Check again')}
      </span>
      <span class="upd-line" data-upd-status role="status"></span>
      <span class="upd-line" data-upd-address hidden>${E(s.download_url || '')}</span>`;
    switch (s.state) {
      case 'checking': return `${ver} Checking for updates…`;
      case 'up_to_date': return `${ver} Lastbook is up to date. ${btn('Check again')}`;
      case 'not_published': return `${ver} No update information yet. ${btn('Try again')}`;
      case 'too_old_os': case 'error': return `${ver} ${E(s.message)} ${btn('Try again')}`;
      default: return `${ver} ${btn('Check for updates')}`;
    }
  }

  function paint(el, s) {
    el.innerHTML = view(s);
    clearTimeout(timer);
    if (s.state === 'checking') timer = setTimeout(() => refresh(el), 400);
    else sync('notice');     // a check of the person's own also updates the sidebar (when notices are on)
  }

  async function refresh(el) {
    if (!el.isConnected) return;
    try { paint(el, await call('state')) } catch { el.textContent = 'Lastbook could not ask about updates.' }
  }

  async function check(el) {
    try {
      const s = await call('check');
      if (s.error && !s.state) { el.textContent = s.error; return }
      paint(el, s);
    } catch { el.textContent = 'Lastbook could not ask about updates.' }
  }

  async function copyLink(button, el) {
    try {
      await navigator.clipboard.writeText(button.dataset.url);
      button.textContent = 'Link copied';
    } catch {
      const address = el.querySelector('[data-upd-address]');
      address.hidden = false;
      const range = document.createRange();
      range.selectNodeContents(address);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = 'Address selected';
    }
  }

  async function openDownload(button, el) {
    const status = el.querySelector('[data-upd-status]');
    button.disabled = true;
    status.textContent = '';
    try {
      const result = await call('open');
      if (result.opened) {
        status.textContent = 'Download page opened in your browser.';
        return;
      }
      status.textContent = result.error;
    } catch {
      status.textContent = 'Lastbook could not open the download page. Try copying the download link.';
    } finally {
      button.disabled = false;
    }
    const copy = el.querySelector('[data-upd=copy]');
    if (copy) copy.hidden = false;
  }

  async function updateNow(button, el) {
    const status = el.querySelector('[data-upd-status]');
    button.disabled = true;
    status.textContent = '';
    try {
      const result = await call('now');
      if (result.started) {
        status.textContent = 'The updater is opening. Confirm in its window to install; Lastbook restarts when it is done.';
        setTimeout(async () => {      // the updater starts on the app's side: a failure to start comes back in state
          try {
            const s = await call('state');
            if (s.update_now_error) { status.textContent = s.update_now_error; button.hidden = true }
          } catch { }
          button.disabled = false;
        }, 1500);
        return;
      }
      status.textContent = result.error || 'Lastbook could not start the update.';
      if (result.fallback) button.hidden = true;
    } catch {
      status.textContent = 'Lastbook could not start the update. Use the download page instead.';
    }
    button.disabled = false;
  }

  /* ---- the sidebar's notice */
  function showRow(n) {
    if (!row) return;
    const v = n && n.notify && n.available ? String(n.available) : '';
    row.hidden = !v;
    row.setAttribute('aria-label', v ? `Update available: version ${v}` : 'Update available');
  }
  async function sync(action) {
    if (!row) return;
    clearTimeout(rowTimer);
    try {
      const n = await call(action);
      showRow(n);
      if (n && n.notify && n.checking) rowTimer = setTimeout(() => sync('notice'), POLL);   // until the check under way has ended
    } catch { }      // quiet: the row stays as it was
  }
  const nudge = () => sync(navigator.onLine === false ? 'notice' : 'auto');

  window.LBUpdate = {
    card: () => '<div class="card"><b>Lastbook app</b><small id="updBox">…</small></div>',
    mount(root) {
      const el = root.querySelector('#updBox'); if (!el) return;
      el.addEventListener('click', e => {
        const button = e.target.closest('[data-upd]');
        if (button?.dataset.upd === 'check') check(el);
        if (button?.dataset.upd === 'copy') copyLink(button, el);
        if (button?.dataset.upd === 'open') openDownload(button, el);
        if (button?.dataset.upd === 'now') updateNow(button, el);
      });
      if (menuAsked) { menuAsked = false; return check(el) }
      refresh(el);
    },
    fromMenu() {     // Lastbook > Check for Updates…: About, then one check
      const el = document.getElementById('updBox');
      if (el && location.hash.startsWith('#/about')) return check(el);
      menuAsked = true;
      location.hash = '#/about';
    },
    watch(el) {      // app.js, in the desktop app's window only
      if (!el || row || document.documentElement.classList.contains('lb-embed')) return;   // the iPad app embeds these pages under lastbook: too: not there
      row = el;
      sync('notice');                       // what an earlier check found shows at once; no network
      setTimeout(nudge, FIRST);
      setInterval(nudge, HOUR);
      addEventListener('online', nudge);
      document.addEventListener('visibilitychange', () => { if (!document.hidden) sync('notice') });   // turned off elsewhere: gone when this window is seen again
    },
  };
})();
