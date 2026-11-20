/* AI Workforce website chat. Add to a site with:
   <script src="https://YOUR-APP/static/js/chat-widget.js" data-key="KEY" defer></script>
   Renders inside a shadow root so the host site's styles can't break it (and vice versa).
   Messages are shown as plain text only. */
(function () {
  var script = document.currentScript || document.querySelector('script[data-key][src*="chat-widget.js"]');
  if (!script || window.__awChatLoaded) return;
  window.__awChatLoaded = true;
  var key = script.getAttribute('data-key');
  var api = new URL(script.src, location.href).origin + '/w/' + encodeURIComponent(key);
  var store = { get: function (k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
                set: function (k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} } };
  var session = store.get('aw-chat-session') || (Math.random().toString(36).slice(2) + Date.now().toString(36));
  store.set('aw-chat-session', session);
  var history = [];
  try { history = JSON.parse(store.get('aw-chat-history') || '[]'); } catch (e) { history = []; }

  fetch(api + '/config').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(build).catch(function () { /* not enabled for this site: show nothing */ });

  function build(cfg) {
    var color = /^#[0-9a-f]{6}$/i.test(cfg.color) ? cfg.color : '#1a5fc2';
    var host = document.createElement('div');
    host.setAttribute('data-aw-chat', '');
    document.body.appendChild(host);
    var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host;
    var css = ':host{all:initial}*{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}' +
      '.fab{position:fixed;right:18px;bottom:calc(18px + env(safe-area-inset-bottom));z-index:2147483000;display:flex;align-items:center;gap:8px;border:0;border-radius:999px;padding:14px 18px;background:__C__;color:#fff;font-size:16px;font-weight:700;cursor:pointer;box-shadow:0 10px 28px -8px rgba(0,0,0,.45)}' +
      '.fab:focus-visible,.send:focus-visible,.close:focus-visible{outline:3px solid #ffbf47;outline-offset:2px}' +
      '.panel{position:fixed;right:18px;bottom:calc(84px + env(safe-area-inset-bottom));z-index:2147483000;width:min(380px,calc(100vw - 24px));height:min(560px,calc(100vh - 120px));display:none;flex-direction:column;background:#fff;color:#14213d;border-radius:20px;overflow:hidden;box-shadow:0 24px 60px -12px rgba(0,0,0,.45)}' +
      '.panel.open{display:flex}.head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;background:__C__;color:#fff}' +
      '.head b{font-size:16px}.head small{display:block;opacity:.9;font-size:12px}.close{background:transparent;border:0;color:#fff;font-size:26px;line-height:1;cursor:pointer;width:44px;height:44px}' +
      '.log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#f4f6fa}' +
      '.msg{max-width:85%;padding:10px 13px;border-radius:16px;font-size:15px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere}' +
      '.bot{align-self:flex-start;background:#fff;border:1px solid #e1e6ef}.me{align-self:flex-end;background:__C__;color:#fff}' +
      '.typing{opacity:.7;font-style:italic}form{display:flex;gap:8px;padding:10px;border-top:1px solid #e1e6ef;background:#fff}' +
      'input{flex:1;min-width:0;font-size:16px;padding:12px 14px;border:1px solid #cdd5e3;border-radius:14px;color:#14213d;background:#fff}' +
      '.send{border:0;border-radius:14px;padding:0 16px;background:__C__;color:#fff;font-size:15px;font-weight:700;cursor:pointer;min-height:44px}' +
      '.note{font-size:11px;color:#5a6478;text-align:center;padding:0 10px 8px;background:#fff}' +
      '@media (max-width:480px){.panel{right:12px;left:12px;width:auto;bottom:calc(80px + env(safe-area-inset-bottom));height:min(70vh,560px)}.fab{right:12px}}';
    var style = document.createElement('style'); style.textContent = css.split('__C__').join(color);
    root.appendChild(style);
    var fab = el('button', 'fab'); fab.type = 'button'; fab.setAttribute('aria-expanded', 'false');
    fab.textContent = '\u{1F4AC} Chat with us';
    var panel = el('div', 'panel'); panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', cfg.name);
    var head = el('div', 'head'); var title = el('div'); var b = el('b'); b.textContent = cfg.name;
    var sm = el('small'); sm.textContent = cfg.business || ''; title.appendChild(b); title.appendChild(sm);
    var close = el('button', 'close'); close.type = 'button'; close.setAttribute('aria-label', 'Close chat'); close.textContent = '×';
    head.appendChild(title); head.appendChild(close);
    var log = el('div', 'log'); log.setAttribute('aria-live', 'polite');
    var form = el('form'); var input = el('input'); input.placeholder = 'Type your question…'; input.maxLength = 600;
    input.setAttribute('aria-label', 'Your message'); input.autocomplete = 'off';
    var send = el('button', 'send'); send.type = 'submit'; send.textContent = 'Send';
    form.appendChild(input); form.appendChild(send);
    var note = el('div', 'note'); note.textContent = 'Automated assistant · answers may be incomplete. Don’t share PINs or passwords.';
    panel.appendChild(head); panel.appendChild(log); panel.appendChild(form); panel.appendChild(note);
    root.appendChild(panel); root.appendChild(fab);

    add('bot', cfg.greeting);
    history.forEach(function (t) { add(t.role === 'user' ? 'me' : 'bot', t.content); });

    function toggle(open) {
      panel.classList.toggle('open', open); fab.setAttribute('aria-expanded', String(open));
      fab.style.display = open && window.innerWidth <= 480 ? 'none' : '';
      if (open) { log.scrollTop = log.scrollHeight; if (window.innerWidth > 480) input.focus(); } else { fab.focus(); }
    }
    fab.addEventListener('click', function () { toggle(!panel.classList.contains('open')); });
    close.addEventListener('click', function () { toggle(false); });
    panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') toggle(false); });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var text = input.value.trim(); if (!text || send.disabled) return;
      input.value = ''; add('me', text); send.disabled = true;
      var wait = add('bot typing', 'Typing…');
      fetch(api + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session: session, history: history.slice(-6) }) })
        .then(function (r) { return r.json(); })
        .then(function (d) { wait.remove(); var a = d.answer || 'Sorry, please try again.'; add('bot', a);
          history.push({ role: 'user', content: text }, { role: 'assistant', content: a });
          history = history.slice(-12); store.set('aw-chat-history', JSON.stringify(history)); })
        .catch(function () { wait.remove(); add('bot', 'Sorry, I couldn’t connect. Please try again.'); })
        .then(function () { send.disabled = false; });
    });
    function add(cls, text) { var m = el('div', 'msg ' + cls); m.textContent = text; log.appendChild(m); log.scrollTop = log.scrollHeight; return m; }
  }
  function el(tag, cls) { var n = document.createElement(tag); if (cls) n.className = cls; return n; }
})();
