/* Google Drive import with the Google Picker (drive.file scope).
   The page's CSP allows Google's picker script and frames on this page only. */
(function () {
  'use strict';
  var box = document.querySelector('[data-drive-import]');
  if (!box) return;
  var button = box.querySelector('[data-drive-pick]');
  var repoSelect = box.querySelector('[data-drive-repo]');
  var out = box.querySelector('[data-drive-result]');
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
             (document.querySelector('input[name="csrf_token"]') || {}).value || '';
  var pickerReady = null;

  function say(text, kind) {
    out.textContent = '';
    var p = document.createElement('p');
    p.className = 'small-note' + (kind === 'error' ? ' drive-error' : '');
    p.textContent = text; out.appendChild(p);
  }
  function post(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || 'Something went wrong. Please try again.'); return d; }); });
  }
  function loadPicker() {
    if (pickerReady) return pickerReady;
    pickerReady = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = 'https://apis.google.com/js/api.js'; s.async = true;
      s.onload = function () { window.gapi.load('picker', { callback: resolve, onerror: reject }); };
      s.onerror = function () { pickerReady = null; reject(new Error('Couldn’t load Google’s file picker. Check your connection and try again.')); };
      document.head.appendChild(s);
    });
    return pickerReady;
  }

  function importFiles(ids) {
    say('Importing ' + ids.length + (ids.length === 1 ? ' file' : ' files') + '… this can take a minute.');
    button.disabled = true;
    return post(box.getAttribute('data-import-url'), { repository_id: parseInt(repoSelect.value, 10), file_ids: ids })
      .then(function (d) {
        out.textContent = '';
        var head = document.createElement('p');
        head.className = 'small-note';
        head.textContent = d.imported + ' of ' + d.results.length + ' imported into “' + d.repository + '”.';
        out.appendChild(head);
        var ul = document.createElement('ul'); ul.className = 'drive-list';
        d.results.forEach(function (r) {
          var li = document.createElement('li');
          li.textContent = (r.ok ? '✓ ' : '✕ ') + r.name + (r.ok ? '' : ' — ' + r.error);
          if (!r.ok) li.className = 'drive-error';
          ul.appendChild(li);
        });
        out.appendChild(ul);
        if (d.imported) {
          var a = document.createElement('a');
          a.href = d.permissions_url; a.textContent = 'Choose which AI employees can read this folder →';
          var p = document.createElement('p'); p.appendChild(a); out.appendChild(p);
        }
      })
      .catch(function (e) { say(e.message, 'error'); })
      .finally(function () { button.disabled = false; });
  }

  button.addEventListener('click', function () {
    if (!repoSelect.value) { say('Choose a knowledge folder first.', 'error'); return; }
    button.disabled = true; say('Opening Google Drive…');
    Promise.all([post(box.getAttribute('data-token-url')), loadPicker()])
      .then(function (res) {
        var t = res[0], gp = window.google.picker;
        var view = new gp.DocsView(gp.ViewId.DOCS).setMimeTypes(t.mime_types).setIncludeFolders(true).setSelectFolderEnabled(false);
        var picker = new gp.PickerBuilder()
          .enableFeature(gp.Feature.MULTISELECT_ENABLED)
          .setMaxItems(10)
          .setDeveloperKey(t.api_key)
          .setAppId(t.app_id)
          .setOAuthToken(t.access_token)
          .setOrigin(window.location.protocol + '//' + window.location.host)
          .addView(view)
          .setTitle('Choose files to import')
          .setCallback(function (data) {
            if (data.action === gp.Action.PICKED) {
              var ids = (data.docs || []).map(function (doc) { return doc.id; }).slice(0, 10);
              importFiles(ids);
            } else if (data.action === gp.Action.CANCEL) {
              out.textContent = ''; button.disabled = false;
            }
          })
          .build();
        picker.setVisible(true);
        out.textContent = '';
      })
      .catch(function (e) { say(e.message, 'error'); button.disabled = false; });
  });
})();
