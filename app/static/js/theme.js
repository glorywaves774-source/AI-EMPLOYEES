/* Runs synchronously in <head> (before first paint) so the page never
   flashes the wrong theme. Follows the device setting until the person
   chooses; the choice is kept in localStorage and a cookie. */
(function () {
  var choice = null;
  try { choice = localStorage.getItem('theme'); } catch (e) {}
  if (!choice) {
    var m = document.cookie.match(/(?:^|;\s*)theme=(light|dark)/);
    if (m) choice = m[1];
  }
  if (choice !== 'light' && choice !== 'dark') {
    choice = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  var root = document.documentElement;
  root.setAttribute('data-theme', choice);
  root.setAttribute('data-bs-theme', choice);
  var standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
  if (standalone) root.classList.add('standalone');
})();
