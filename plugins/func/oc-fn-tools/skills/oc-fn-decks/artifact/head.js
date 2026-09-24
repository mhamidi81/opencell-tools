// oc-fn-decks artifact lane — runs before the stylesheets are parsed.
//
// 1. Theme switch, part 1: a remembered choice paints first time, with no light→dark flash.
//    localStorage is per viewer AND per artifact (each artifact has its own origin) and can
//    throw or come back empty: the page is correct without it. Light stays the default.
(function () {
  try {
    var v = localStorage.getItem('oc-theme');
    if (v === 'dark' || v === 'light') document.documentElement.setAttribute('data-oc-theme', v);
  } catch (e) {}
})();

// 2. 24-hour presenter clock, whatever the viewer's locale (the oc-fn-decks locale rule).
//    Marp's presenter view calls toLocaleTimeString() with no arguments; only those calls change.
(function () {
  var orig = Date.prototype.toLocaleTimeString;
  Date.prototype.toLocaleTimeString = function (locales, options) {
    if (locales == null && options == null) {
      return orig.call(this, 'fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    }
    return orig.call(this, locales, options);
  };
})();
