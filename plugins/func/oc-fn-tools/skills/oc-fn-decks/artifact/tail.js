// oc-fn-decks artifact lane — theme switch, part 2. Runs after the slides are in the DOM.
//
// The effective theme follows page.css's precedence, read from the same two attributes: this
// page's switch ([data-oc-theme], remembered) wins, then claude.ai's theme setting
// ([data-theme="dark"], stamped by the viewer). A dark OS setting alone is ignored — light is
// the default for Opencell pages.
//
// Never read it back from the computed color-scheme. On claude.ai in its dark theme it stayed
// dark after the switch chose light, though the published page alone resolves it to light, so
// the viewer sets it too. The switch then read "dark" forever: the ground turned light, the
// slides stayed dark, and the button could not go back (reported 2026-10-28).
//
// Marp scopes every slide rule to its own container, so a slide cannot see an attribute on
// the root. The dark slide variant (slides.css, compiled by Marp with the theme) keys on a
// class instead: `oc-dark` on each <section>, mirrored here from the effective theme.
(function () {
  var r = document.documentElement, b = document.getElementById('oc-theme-toggle');
  function isDark() {
    var v = r.getAttribute('data-oc-theme');
    return v === 'dark' || (v !== 'light' && r.getAttribute('data-theme') === 'dark');
  }
  function sync() {
    var d = isDark();
    var s = document.querySelectorAll('svg[data-marpit-svg] > foreignObject > section');
    for (var i = 0; i < s.length; i++) s[i].classList.toggle('oc-dark', d);
    if (b) {
      var l = d ? 'Switch to light theme' : 'Switch to dark theme';
      b.setAttribute('aria-label', l); b.title = l;
    }
  }
  if (b) b.addEventListener('click', function (e) {
    e.stopPropagation();
    var v = isDark() ? 'light' : 'dark';
    r.setAttribute('data-oc-theme', v);
    try { localStorage.setItem('oc-theme', v); } catch (_) {}
    sync();
  });
  new MutationObserver(sync).observe(r, { attributes: true, attributeFilter: ['data-theme', 'data-oc-theme'] });
  sync();
})();
