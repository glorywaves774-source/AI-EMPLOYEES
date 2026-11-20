/* Theme toggle, phone menu (slide-in drawer) and installed-app Back button.
   External file only: the Content-Security-Policy forbids inline scripts. */
(function () {
  'use strict';
  var root = document.documentElement;

  // ---------- Light / dark toggle ----------
  function current() { return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }
  function paintToggles() {
    var dark = current() === 'dark';
    document.querySelectorAll('[data-theme-toggle]').forEach(function (b) {
      b.setAttribute('aria-pressed', dark ? 'true' : 'false');
      var label = b.querySelector('.tl'); if (label) label.textContent = dark ? 'Light mode' : 'Dark mode';
      var icon = b.querySelector('.ti'); if (icon) icon.textContent = dark ? '☀' : '☾';
      b.setAttribute('title', dark ? 'Switch to light mode' : 'Switch to dark mode');
    });
  }
  function setTheme(t) {
    root.setAttribute('data-theme', t);
    root.setAttribute('data-bs-theme', t);
    try { localStorage.setItem('theme', t); } catch (e) {}
    document.cookie = 'theme=' + t + '; Max-Age=31536000; Path=/; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
    paintToggles();
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-theme-toggle]');
    if (b) { e.preventDefault(); setTheme(current() === 'dark' ? 'light' : 'dark'); }
  });
  // Follow device changes until the person has chosen.
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var follow = function (ev) {
      var chosen = null; try { chosen = localStorage.getItem('theme'); } catch (x) {}
      if (!chosen && !/(?:^|;\s*)theme=/.test(document.cookie)) { root.setAttribute('data-theme', ev.matches ? 'dark' : 'light'); root.setAttribute('data-bs-theme', ev.matches ? 'dark' : 'light'); paintToggles(); }
    };
    if (mq.addEventListener) mq.addEventListener('change', follow); else if (mq.addListener) mq.addListener(follow);
  }
  paintToggles();

  // ---------- Phone menu ----------
  var drawer = document.getElementById('drawer');
  var scrim = document.getElementById('drawer-scrim');
  var opener = document.querySelector('[data-menu-open]');
  var lastFocus = null;

  function isOpen() { return drawer && drawer.classList.contains('open'); }
  function show() {
    if (!drawer || isOpen()) return;
    lastFocus = document.activeElement;
    drawer.hidden = false; scrim.hidden = false;
    // next frame so the slide transition runs
    requestAnimationFrame(function () { drawer.classList.add('open'); scrim.classList.add('open'); });
    document.body.classList.add('no-scroll');
    drawer.setAttribute('aria-hidden', 'false');
    if (opener) opener.setAttribute('aria-expanded', 'true');
    // Android Back closes the menu instead of leaving the page.
    try { history.pushState({ drawer: true }, ''); } catch (e) {}
    var first = drawer.querySelector('a, button'); if (first) first.focus({ preventScroll: true });
  }
  function hide(fromHistory) {
    if (!isOpen()) return;
    drawer.classList.remove('open'); scrim.classList.remove('open');
    document.body.classList.remove('no-scroll');
    drawer.setAttribute('aria-hidden', 'true');
    if (opener) opener.setAttribute('aria-expanded', 'false');
    setTimeout(function () { if (!isOpen()) { drawer.hidden = true; scrim.hidden = true; } }, 260);
    if (!fromHistory && history.state && history.state.drawer) { try { history.back(); } catch (e) {} }
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }
  if (drawer) {
    document.addEventListener('click', function (e) {
      if (e.target.closest('[data-menu-open]')) { e.preventDefault(); show(); return; }
      if (e.target.closest('[data-menu-close]') || e.target === scrim) { e.preventDefault(); hide(false); return; }
      var link = e.target.closest('#drawer a[href]');
      if (link && isOpen() && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        // Replace the menu's history entry so choosing a page never leaves an extra Back step.
        e.preventDefault();
        location.replace(link.href);
      }
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && isOpen()) hide(false); });
    window.addEventListener('popstate', function () { if (isOpen()) hide(true); });
    // If the page is restored with a stale menu entry, drop it.
    window.addEventListener('pageshow', function () { if (history.state && history.state.drawer && !isOpen()) { try { history.back(); } catch (e) {} } });
  }

  // ---------- Selects that save on change ----------
  // (Inline onchange handlers are blocked by the CSP, so this lives here.)
  document.addEventListener('change', function (e) {
    var sel = e.target.closest('select[data-autosubmit]');
    if (sel && sel.form) { if (sel.form.requestSubmit) sel.form.requestSubmit(); else sel.form.submit(); }
  });

  // ---------- Read-only fields that select their text (e.g. invitation links) ----------
  document.addEventListener('focusin', function (e) {
    if (e.target.matches && e.target.matches('input[data-select-on-focus], textarea[data-select-on-focus]')) { e.target.select(); }
  });

  // ---------- Installed-app Back button ----------
  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-app-back]')) { e.preventDefault(); history.back(); }
  });
})();
