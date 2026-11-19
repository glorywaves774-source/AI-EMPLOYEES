/* Kombian help assistant (external file: the CSP forbids inline scripts).
   Answers are rendered with textContent / DOM nodes only — never innerHTML. */
(function () {
  'use strict';
  var panel = document.getElementById('kombian');
  if (!panel) return;
  var fab = document.querySelector('[data-kombian-open]');
  var log = document.getElementById('kombian-log');
  var form = panel.querySelector('[data-kombian-form]');
  var input = document.getElementById('kombian-input');
  var send = panel.querySelector('.kombian-send');
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var history = [];
  var busy = false;
  var isPhone = function () { return window.matchMedia('(max-width: 760px)').matches; };
  var touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

  // ---------- open / close ----------
  function open() {
    panel.hidden = false;
    fab.setAttribute('aria-expanded', 'true');
    // Never pop the keyboard up on phones; focus the box on computers.
    if (!touch) input.focus({ preventScroll: true });
    log.scrollTop = log.scrollHeight;
  }
  function close() {
    endTyping();
    panel.hidden = true;
    fab.setAttribute('aria-expanded', 'false');
    fab.focus({ preventScroll: true });
  }
  fab.addEventListener('click', function () { panel.hidden ? open() : close(); });
  panel.addEventListener('click', function (e) {
    if (e.target.closest('[data-kombian-close]')) close();
    var s = e.target.closest('[data-kombian-ask]');
    if (s) ask(s.textContent.trim());
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) close(); });

  // ---------- typing on phones: fill the space above the keyboard ----------
  var vv = window.visualViewport;
  function fit() {
    if (!panel.classList.contains('typing') || !vv) return;
    panel.style.top = (vv.offsetTop + 8) + 'px';
    panel.style.bottom = 'auto';
    panel.style.height = Math.max(200, vv.height - 16) + 'px';
    log.scrollTop = log.scrollHeight;
  }
  function startTyping() {
    if (!isPhone()) return;
    panel.classList.add('typing'); document.body.classList.add('kombian-typing');
    setTimeout(fit, 60); setTimeout(fit, 350);
  }
  function endTyping() {
    panel.classList.remove('typing'); document.body.classList.remove('kombian-typing');
    panel.style.top = panel.style.bottom = panel.style.height = '';
  }
  input.addEventListener('focus', startTyping);
  input.addEventListener('blur', function () { setTimeout(function () { if (document.activeElement !== input) endTyping(); }, 120); });
  if (vv) { vv.addEventListener('resize', fit); vv.addEventListener('scroll', fit); }

  // grow the box with its text
  input.addEventListener('input', function () { input.style.height = 'auto'; input.style.height = Math.min(120, input.scrollHeight) + 'px'; });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : form.submit(); }
  });
  form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });

  // ---------- safe rendering ----------
  function inline(parent, text, links) {
    // **bold** and [[link:key]] markers; everything else is plain text
    var re = /\*\*([^*]+)\*\*|\[\[link:([a-z_]+)\]\]/g, last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      if (m[1] !== undefined) { var b = document.createElement('strong'); b.textContent = m[1]; parent.appendChild(b); }
      else if (links[m[2]]) {
        var a = document.createElement('a'); a.className = 'klink';
        var url = links[m[2]].url;
        a.href = /^\/[^/]/.test(url) ? url : '#'; // same-site paths only
        a.textContent = links[m[2]].label; parent.appendChild(a);
      }
      last = re.lastIndex;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }
  function render(text, links) {
    var frag = document.createDocumentFragment(), list = null, para = null;
    text.split(/\r?\n/).forEach(function (raw) {
      var line = raw.trim();
      var ol = line.match(/^\d+[.)]\s+(.*)$/), ul = line.match(/^[-*•]\s+(.*)$/);
      if (ol || ul) {
        var tag = ol ? 'OL' : 'UL';
        if (!list || list.tagName !== tag) { list = document.createElement(tag); frag.appendChild(list); }
        var li = document.createElement('li'); inline(li, (ol || ul)[1], links); list.appendChild(li); para = null;
      } else if (!line) { list = null; para = null; }
      else {
        list = null;
        if (!para) { para = document.createElement('p'); frag.appendChild(para); } else para.appendChild(document.createTextNode(' '));
        inline(para, line.replace(/^#+\s*/, ''), links);
      }
    });
    return frag;
  }
  function bubble(cls) { var d = document.createElement('div'); d.className = 'kmsg ' + cls; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }

  // ---------- asking ----------
  function ask(q) {
    q = (q || '').trim();
    if (!q || busy) return;
    if (panel.hidden) open();
    busy = true; send.disabled = true;
    var mine = bubble('kmsg-user'); var p = document.createElement('p'); p.textContent = q; mine.appendChild(p);
    input.value = ''; input.style.height = '';
    var wait = bubble('kmsg-bot'); wait.setAttribute('aria-label', 'Kombian is typing');
    var dots = document.createElement('span'); dots.className = 'kmsg-typing'; for (var i = 0; i < 3; i++) dots.appendChild(document.createElement('i')); wait.appendChild(dots);
    fetch(panel.getAttribute('data-ask-url'), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Kombian-Context': panel.getAttribute('data-context') },
      body: JSON.stringify({ question: q, history: history, context: panel.getAttribute('data-context') })
    }).then(function (r) {
      if (r.status === 429) throw new Error('You’ve asked a lot of questions in a short time. Please wait a minute and try again.');
      if (r.status === 401) throw new Error('Your session has ended. Please sign in again.');
      return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || 'Something went wrong. Please try again.'); return data; });
    }).then(function (data) {
      wait.removeAttribute('aria-label'); wait.textContent = '';
      wait.appendChild(render(data.answer || '', data.links || {}));
      log.scrollTop = Math.max(0, wait.offsetTop - log.offsetTop - 12); // show a new answer from its first line
      history.push({ role: 'user', content: q }, { role: 'assistant', content: (data.answer || '').slice(0, 600) });
      history = history.slice(-12);
    }).catch(function (err) {
      wait.removeAttribute('aria-label'); wait.textContent = ''; wait.classList.add('kmsg-error');
      var e = document.createElement('p'); e.textContent = err && err.message && !/fetch|network/i.test(err.message) ? err.message : 'Couldn’t reach Kombian. Check your connection and try again.';
      wait.appendChild(e);
    }).finally(function () { busy = false; send.disabled = false; });
  }
})();
