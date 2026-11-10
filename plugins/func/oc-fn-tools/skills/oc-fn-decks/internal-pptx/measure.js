#!/usr/bin/env node
/* measure.js — lay a Marp deck out in headless Chromium and record what PowerPoint needs.
 *
 * Called by render-internal-pptx.sh; not meant to be run by hand.
 *   node measure.js <marp-bare.html> <out-dir> [--keep-centring]
 * Needs NODE_PATH holding puppeteer-core, and CHROME_PATH.
 *
 * The browser does the layout, so any theme rule or custom HTML block lands where Marp puts it;
 * this records the result in slide pixels (Marp's canvas, 1280×720 for 16:9). Writes
 * <out-dir>/model.json and one PNG per raster (images, background images, SVG it cannot
 * rebuild as shapes). The repeated parts of each slide — background, logo pseudo-elements,
 * inset-shadow stripes, footer, header, page number and the title's geometry — are recorded as
 * its "chrome", from which build.js derives the slide layouts.
 *
 * What it reads, beyond plain boxes and text:
 *   - the line breaks Chromium chose, word by word, so PowerPoint breaks lines at the same
 *     words instead of re-wrapping with its own metrics (lines are told apart by the glyphs'
 *     baselines), and the empty lines that forced breaks make (`a<br><br>b`);
 *   - pseudo-elements: string content in running text; block or absolutely positioned ones
 *     (a logo, a title pill) and inline-block ones (a size bar after a label) as shapes;
 *   - inline boxes — inline-blocks with a fill, a border or a side margin and one line of plain
 *     text, or none (a source tag, a pill, a size bar), and plain inline elements with a fill, a
 *     gradient or a border (an inline `code`, a <mark>), on one line or several: their text stays
 *     in the line, highlighted in the box's fill (a gradient's mean colour) and padded to the
 *     box's width, or underlined when the box is drawn by its bottom border alone, with no shape;
 *     only an empty one (a size bar) becomes a shape;
 *   - images in running text (a list item, a table cell), placed at their own position, their
 *     width kept in the line;
 *   - other inline-blocks that carry a box, a margin or a pseudo shape, placed at their own
 *     position, the text after them indented to where its first line starts;
 *   - where each line starts, so that text with shapes drawn over it — a list, a paragraph, a
 *     box's own text — can be anchored item by item, or cut, at Chromium's y (anchorText);
 *   - where each line of a table cell sits, so that every line gets the line spacing that puts
 *     it on Chromium's baseline, and a cell's list items with their markers (tableItem);
 *   - inset box-shadows with no blur, drawn as the stripes they look like;
 *   - CSS filter and opacity on background images, applied when the image is redrawn.
 *
 * It measures with the TTFs in $OC_PPTX_FONTS — the files finish.py embeds — instead of the
 * theme's webfont, so the widths it records are the widths PowerPoint will draw. Tables keep the
 * deck's tabular figures, which PowerPoint draws proportional, a little narrower: see below. A CSS stack that opens on a generic
 * or platform-only family (monospace, ui-monospace, -apple-system…) is replaced by Courier New,
 * Arial or Times New Roman before measuring, for the same reason, and one that opens on a named
 * family that is not installed falls back to the first face the deck loads or the first generic
 * family later in it, other named families skipped.
 *
 * Non-lead slides that open with an h1/h2 are top-aligned before measuring, so a deck's titles
 * share one position and one layout. Marp centres content vertically with
 * `align-content: safe center` on the section (a block container, not flexbox). Slides that
 * open with anything else, a custom layout for instance, keep Marp's centring, as does every
 * slide with --keep-centring.
 */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const [htmlPath, outDir, ...flags] = process.argv.slice(2);
if (!outDir) { console.error('usage: measure.js <marp.html> <out-dir> [--keep-centring]'); process.exit(2); }
const KEEP_CENTRING = flags.includes('--keep-centring');

/* Runs inside the page. Everything it needs is defined inside it. */
function extract() {
  const px = v => parseFloat(v) || 0;
  const col = c => {
    const m = /rgba?\(([^)]+)\)/.exec(c || '');
    if (!m) return null;
    const [r, g, b, a = 1] = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    if (a === 0) return null;
    return { hex: [r, g, b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase(), alpha: a };
  };
  const family = ff => (ff || '').split(',')[0].trim().replace(/^["']|["']$/g, '');
  const lineHeight = cs => cs.lineHeight === 'normal' ? px(cs.fontSize) * 1.22 : px(cs.lineHeight);
  const fontOf = cs => ({
    face: family(cs.fontFamily), size: px(cs.fontSize), bold: (parseInt(cs.fontWeight, 10) || 400) >= 600,
    italic: cs.fontStyle === 'italic', color: col(cs.color),
    spacing: cs.letterSpacing === 'normal' ? 0 : px(cs.letterSpacing),
    underline: cs.textDecorationLine.includes('underline'), strike: cs.textDecorationLine.includes('line-through'),
  });
  // How far a text's glyphs sit above the baseline of their line, px (below it when negative): the
  // shift of each `display: inline` element from the text up to its block or inline box — its
  // vertical-align (super: a third of the parent's font size plus 1 px, sub: a fifth plus 1 px,
  // as Blink computes them; a length; a percentage of its line-height) plus its relative offset.
  // Marp's default theme, which `opencell` imports, moves <sup> and <sub> by the offset alone
  // (`position: relative; vertical-align: baseline; top: -.5em` or `bottom: -.25em`), so reading
  // vertical-align only left them on the baseline, about 5 px below Chromium's <sup>. `own`: a
  // pseudo-element's style, inside el. Undefined under a third of a pixel, so runs compare alike.
  const riseOf = (el, own) => {
    const shift = (cs, pcs) => {
      const va = cs.verticalAlign, f = px(pcs.fontSize);
      // A relative offset given by `bottom` alone comes back resolved into `top` as well.
      return (cs.position === 'relative' ? -px(cs.top) : 0) + (va === 'super' ? f / 3 + 1 : va === 'sub' ? -(f / 5 + 1)
        : /px$/.test(va) ? px(va) : /%$/.test(va) ? px(va) / 100 * lineHeight(cs) : 0);
    };
    let rise = own ? shift(own, getComputedStyle(el)) : 0;
    for (let e = el; e && e.parentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display !== 'inline') break;
      rise += shift(cs, getComputedStyle(e.parentElement));
    }
    return Math.abs(rise) >= 0.3 ? rise : undefined;
  };
  // Glyphs of one family and size sit at the same height on a line, whatever their weight: the
  // key lineTops() compares lines by.
  const fontKey = f => `${f.face}|${f.size}`;
  // text-transform: capitalize as Chromium applies it, which is not word by word on spaces: it
  // capitalizes after a /, a . or a -, not after an apostrophe or an underscore, and a letter
  // that continues the text before it (foo<b>bar</b>) stays as it is. Rather than emulate its
  // word boundaries, Chromium transforms the text itself, read back through innerText, which
  // applies text-transform. `before`: the character the text follows on its line (a space when
  // none). Should the result not keep the text's length, every word after a space is
  // capitalized instead.
  const capitalize = (t, before) => {
    const b = before || ' ', d = document.createElement('div');
    d.style.cssText = 'position:absolute;left:-10000px;top:0;white-space:pre;text-transform:capitalize';
    d.textContent = b + t;
    document.body.appendChild(d);
    const c = d.innerText;
    d.remove();
    return c.length === b.length + t.length ? c.slice(b.length)
      : t.replace(/(^|\s)(\S)/g, (m, s, x, i) => s + (i || /\s/.test(b) ? x.toLocaleUpperCase('fr') : x));
  };
  const transform = (t, cs, before) => cs.textTransform === 'uppercase' ? t.toLocaleUpperCase('fr')
    : cs.textTransform === 'lowercase' ? t.toLocaleLowerCase('fr')
    : cs.textTransform === 'capitalize' ? capitalize(t, before) : t;
  const isInline = cs => /^inline/.test(cs.display) || cs.display === 'contents';
  const align = a => ({ start: 'left', end: 'right', justify: 'justify', '-webkit-left': 'left', '-webkit-center': 'center', '-webkit-right': 'right' }[a] || a);
  const hasContent = cs => cs.content && cs.content !== 'none' && cs.content !== 'normal' && cs.display !== 'none';
  const SVG_OK = new Set(['svg', 'g', 'line', 'rect', 'circle', 'ellipse', 'polyline', 'polygon', 'text', 'tspan', 'title', 'desc']);

  let rasterId = 0, elSeq = 0;
  const rasters = [];
  const slides = [];
  // Highlights composited over a background image (highlightOf): resolved once the rasters exist.
  const blends = [];
  const elId = el => el.dataset.p2b || (el.dataset.p2b = String(++elSeq));

  const contents = [...document.querySelectorAll('section')].filter(s =>
    !s.parentElement.closest('section') && (!s.dataset.marpitAdvancedBackground || s.dataset.marpitAdvancedBackground === 'content'));

  for (const sec of contents) {
    const S = sec.getBoundingClientRect();
    const W = sec.offsetWidth, H = sec.offsetHeight, k = S.width / W;
    const rel = r => ({ x: (r.left - S.left) / k, y: (r.top - S.top) / k, w: r.width / k, h: r.height / k });
    const secCs = getComputedStyle(sec);
    const secBg = col(secCs.backgroundColor);

    const raster = (spec, rect) => { spec.id = ++rasterId; rasters.push(spec); return { type: 'image', rect, raster: spec.id }; };
    // The alt text an image carries into the PPTX: an <img>'s alt, a rasterised SVG's aria-label
    // or <title>. Background images (a logo, a ![bg]) have none, as in the HTML.
    const altOf = el => ((el.tagName.toLowerCase() === 'img' ? el.getAttribute('alt')
      : el.getAttribute('aria-label') || (el.querySelector(':scope > title') || {}).textContent) || '').trim() || undefined;
    // `el`: the element the background belongs to, so a highlight over it can sample its colour.
    const bgRaster = (cs, rect, el) => raster({ kind: 'bg', w: rect.w, h: rect.h, el: el ? elId(el) : undefined, css: {
      backgroundImage: cs.backgroundImage, backgroundSize: cs.backgroundSize, backgroundPosition: cs.backgroundPosition,
      backgroundRepeat: cs.backgroundRepeat, filter: cs.filter, opacity: cs.opacity } }, rect);
    const contentRect = (el, cs) => {
      const r = rel(el.getBoundingClientRect());
      const l = px(cs.borderLeftWidth) + px(cs.paddingLeft), t = px(cs.borderTopWidth) + px(cs.paddingTop);
      return { x: r.x + l, y: r.y + t, w: r.w - l - px(cs.borderRightWidth) - px(cs.paddingRight),
               h: r.h - t - px(cs.borderBottomWidth) - px(cs.paddingBottom) };
    };
    // Where a glyph of font f sits in a plain line of that font at line-height lh: its top below
    // the line's top (`off`), its height (`h`) and its baseline below the line's top (`base`),
    // slide px. Measured on a probe line, because Chromium rounds the ascent, the descent and the
    // half-leading, so it is not computed. The baseline is the bottom of an empty inline-block.
    const plain = new Map();
    const plainLine = (f, lh) => {
      const key = [f.face, f.size, f.bold, f.italic, lh].join('|');
      if (!plain.has(key)) {
        const d = document.createElement('div');
        d.style.cssText = `position:absolute;left:0;top:0;margin:0;padding:0;border:0;white-space:nowrap;`
          + `font-family:"${f.face}";font-size:${f.size}px;font-weight:${f.bold ? 700 : 400};`
          + `font-style:${f.italic ? 'italic' : 'normal'};line-height:${lh}px`;
        d.textContent = 'x';
        const z = document.createElement('span');
        z.style.cssText = 'display:inline-block;width:0;height:0;margin:0;padding:0;border:0;vertical-align:baseline';
        d.appendChild(z);
        sec.appendChild(d);
        const r = document.createRange();
        r.selectNodeContents(d.firstChild);
        const g = r.getClientRects()[0], b = d.getBoundingClientRect();
        plain.set(key, g ? { off: (g.top - b.top) / k, h: g.height / k, base: (z.getBoundingClientRect().bottom - b.top) / k } : { off: 0, h: 0, base: 0 });
        d.remove();
      }
      return plain.get(key);
    };
    // How far the baseline of font f sits below the top of its glyph rects, client px: every glyph
    // rect of one face and size is as tall, so a rect's baseline is its top plus this. Measured on
    // a probe line, as plainLine is: an empty inline-block sits with its bottom on the baseline.
    const ascents = new Map();
    const ascentOf = f => {
      const key = [f.face, f.size, f.bold, f.italic].join('|');
      if (!ascents.has(key)) {
        const d = document.createElement('div'), z = document.createElement('span');
        d.style.cssText = `position:absolute;left:0;top:0;margin:0;padding:0;border:0;white-space:nowrap;`
          + `font-family:"${f.face}";font-size:${f.size}px;font-weight:${f.bold ? 700 : 400};`
          + `font-style:${f.italic ? 'italic' : 'normal'}`;
        z.style.cssText = 'display:inline-block;width:0;height:0;margin:0;padding:0;border:0;vertical-align:baseline';
        d.append('x', z);
        sec.appendChild(d);
        const r = document.createRange();
        r.selectNodeContents(d.firstChild);
        const g = r.getClientRects()[0];
        ascents.set(key, g ? z.getBoundingClientRect().bottom - g.top : 0);
        d.remove();
      }
      return ascents.get(key);
    };

    // ---- decoration: fill, borders, radius, inset-shadow stripes
    const stripesOf = (cs, rect) => {
      const out = [];
      if (!cs.boxShadow || cs.boxShadow === 'none') return out;
      const re = /(rgba?\([^)]*\))\s+(-?[\d.]+)px\s+(-?[\d.]+)px(?:\s+(-?[\d.]+)px)?(?:\s+(-?[\d.]+)px)?\s+inset/g;
      let m;
      while ((m = re.exec(cs.boxShadow))) {
        const c = col(m[1]), dx = +m[2], dy = +m[3], blur = +(m[4] || 0), spread = +(m[5] || 0);
        if (!c || blur || spread) continue;
        if (dx > 0) out.push({ c, x: rect.x, y: rect.y, w: dx, h: rect.h });
        if (dx < 0) out.push({ c, x: rect.x + rect.w + dx, y: rect.y, w: -dx, h: rect.h });
        if (dy > 0) out.push({ c, x: rect.x, y: rect.y, w: rect.w, h: dy });
        if (dy < 0) out.push({ c, x: rect.x, y: rect.y + rect.h + dy, w: rect.w, h: -dy });
      }
      return out;
    };
    const boxOf = (cs, rect, keepSlideFill) => {
      const fill = col(cs.backgroundColor);
      const bgImg = cs.backgroundImage !== 'none';
      const sides = ['Top', 'Right', 'Bottom', 'Left'].map(s => {
        const w = px(cs[`border${s}Width`]), c = col(cs[`border${s}Color`]), st = cs[`border${s}Style`];
        return w > 0 && c && st !== 'none' && st !== 'hidden' ? { w, c, dash: st === 'dashed' || st === 'dotted' } : null;
      });
      const any = sides.some(Boolean), stripes = stripesOf(cs, rect);
      const sameAsSlide = !keepSlideFill && fill && secBg && fill.hex === secBg.hex && fill.alpha === secBg.alpha;
      if (!(fill && !sameAsSlide) && !bgImg && !any && !stripes.length) return null;
      const s0 = sides[0];
      const uniform = sides.every(b => b && b.w === s0.w && b.c.hex === s0.c.hex && b.dash === s0.dash);
      return { type: 'box', rect, fill: sameAsSlide ? null : fill, line: uniform ? s0 : null,
               sides: uniform || !any ? null : sides, stripes: stripes.length ? stripes : null,
               radius: px(cs.borderTopLeftRadius), bgImg };
    };
    const emitBox = (b, cs, out, el) => {
      if (!b) return;
      if (b.bgImg) out.push(bgRaster(cs, b.rect, el));
      if (b.fill || b.line || b.sides || b.stripes || b.text) out.push(b);
    };

    // ---- pseudo-elements
    const pseudoString = (el, which) => {       // inline string content, part of the text run
      const cs = getComputedStyle(el, which);
      if (!hasContent(cs) || !cs.content.startsWith('"') || cs.position === 'absolute' || !/^inline$/.test(cs.display)) return null;
      if (col(cs.backgroundColor) || cs.backgroundImage !== 'none') return null;
      const t = cs.content.slice(1, -1).replace(/\\"/g, '"');
      // Its glyphs have no client rects, so a line break Chromium makes inside it is not
      // recorded: `free` says so, and the text then keeps wrapping on its own (see build.js).
      if (!t) return null;
      const f = fontOf(cs), d = decoOf(el);
      return { t: transform(t, cs), ...f, underline: f.underline || d.underline, strike: f.strike || d.strike, rise: riseOf(el, cs), free: /\s/.test(t) || undefined };
    };
    // A pseudo-element's computed width/height is its content box unless box-sizing says
    // otherwise: its padding and border come on top.
    const outerSize = cs => cs.boxSizing === 'border-box' ? { w: px(cs.width), h: px(cs.height) } : {
      w: px(cs.width) + px(cs.paddingLeft) + px(cs.paddingRight) + px(cs.borderLeftWidth) + px(cs.borderRightWidth),
      h: px(cs.height) + px(cs.paddingTop) + px(cs.paddingBottom) + px(cs.borderTopWidth) + px(cs.borderBottomWidth) };
    const blockPseudoHeight = (el, which) => {   // space a static block pseudo takes in el's flow
      const cs = getComputedStyle(el, which);
      if (!hasContent(cs) || cs.position === 'absolute' || cs.position === 'fixed' || isInline(cs)) return 0;
      return outerSize(cs).h + px(cs.marginTop) + px(cs.marginBottom);
    };
    const pseudoBox = (el, which) => {
      const cs = getComputedStyle(el, which);
      if (!hasContent(cs)) return null;
      const { w, h } = outerSize(cs);
      const str = cs.content.startsWith('"') ? cs.content.slice(1, -1).replace(/\\"/g, '"') : '';
      if (!w || !h) return null;
      let x, y;
      if (cs.position === 'absolute' || cs.position === 'fixed') {
        let cb = el;
        while (cb !== sec && getComputedStyle(cb).position === 'static') cb = cb.parentElement;
        const cbCs = getComputedStyle(cb), cr = rel(cb.getBoundingClientRect());
        const bx = cr.x + px(cbCs.borderLeftWidth), by = cr.y + px(cbCs.borderTopWidth);
        const bw = cr.w - px(cbCs.borderLeftWidth) - px(cbCs.borderRightWidth);
        const bh = cr.h - px(cbCs.borderTopWidth) - px(cbCs.borderBottomWidth);
        x = cs.left !== 'auto' ? bx + px(cs.left) : bx + bw - px(cs.right) - w;
        y = cs.top !== 'auto' ? by + px(cs.top) : by + bh - px(cs.bottom) - h;
      } else if (!isInline(cs)) {
        const c = contentRect(el, getComputedStyle(el));
        x = c.x + px(cs.marginLeft);
        y = which === '::before' ? c.y + px(cs.marginTop) : c.y + c.h - h - px(cs.marginBottom);
      } else if (cs.display === 'inline-block') {
        // Anchored to el's own text: after its last line box, or before its first.
        const range = document.createRange();
        range.selectNodeContents(el);
        const rects = [...range.getClientRects()].filter(r => r.width || r.height);
        if (!rects.length) return null;
        const r = rel(which === '::after' ? rects[rects.length - 1] : rects[0]);
        x = which === '::after' ? r.x + r.w + px(cs.marginLeft) : r.x - w - px(cs.marginRight);
        y = r.y + (r.h - h) / 2;
      } else return null;
      const rect = { x, y, w, h }, out = [];
      const b = boxOf(cs, rect, true);
      if (b && str) {
        b.text = { runs: [{ t: transform(str, cs), ...fontOf(cs) }], align: align(cs.textAlign), lh: lineHeight(cs), lines: 1, valign: 'top' };
        b.pad = [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)];
        b.valign = 'middle';
      }
      emitBox(b, cs, out);
      return out.length ? out : null;
    };

    // ---- inline-blocks that need their own position
    const pseudoShape = el => ['::before', '::after'].some(w => { const p = getComputedStyle(el, w); return hasContent(p) && p.display === 'inline-block' && (col(p.backgroundColor) || p.backgroundImage !== 'none'); });
    const positioned = el => {
      const cs = getComputedStyle(el);
      if (!/^inline-(block|flex|grid|table)$/.test(cs.display)) return false;
      if (boxOf(cs, rel(el.getBoundingClientRect()))) return true;
      if (px(cs.marginLeft) || px(cs.marginRight)) return true;
      return pseudoShape(el);
    };
    // An inline box: a positioned inline-block that stays in the text flow — a source tag, a pill,
    // a size bar — because it holds one line of plain inline text, or nothing. runsOf() keeps its
    // text in the line as highlighted text (see inlineBoxRuns): no shape is drawn for it, because
    // a shape over flowing text never sat on its words in PowerPoint (Stéphane, 2026-10-09). Only
    // an empty one (a size bar, a swatch) is still a shape, placed at its measured position.
    // Placing a box on its own instead would split the paragraph around it: the text after it
    // would start a box of its own, and when that text wraps, its first line lands on top of the
    // paragraph's start.
    // A plain inline element (display: inline) that draws a box — an inline `code` span, a <mark>,
    // a highlighted span: a fill, a gradient or a border. On one line it is an inline box like the
    // others; broken across lines, its text is highlighted the same way, line after line, its
    // padding at its two ends (runsOf: `sliced`). A gradient is highlighted in its mean colour
    // (highlightOf); a background image with a url() in it is not a box here, and its text stays
    // plain, as does gradient text (a gradient clipped to the glyphs, `background-clip: text`).
    // Only a gradient that covers its box (no size set, or 100 %, or repeated both ways): a
    // gradient sized to a stripe (a gradient underline, a marker sweep) is no fill, and stays
    // plain text, as one colour over the whole box would tint it.
    // Layer by layer (a background of several gradients lists their sizes and repeats, comma
    // separated): the box is covered when one layer covers it.
    const covers = cs => {
      const sizes = cs.backgroundSize.split(/,\s*/), reps = cs.backgroundRepeat.split(/,\s*/);
      return sizes.some((z, i) => /^(auto|auto auto|cover|contain|100%|100% auto|auto 100%|100% 100%)$/.test(z)
        || /^(repeat|round|space)( (repeat|round|space))?$/.test(reps[i] || reps[reps.length - 1]));
    };
    const gradientOnly = cs => cs.backgroundImage !== 'none' && !/url\(/.test(cs.backgroundImage)
      && !/text/.test(cs.backgroundClip || '') && !/text/.test(cs.webkitBackgroundClip || '') && covers(cs);
    // Underline and line-through as CSS draws them on a text: an ancestor's decoration reaches it
    // (computed text-decoration-line is not inherited, so a <b> in an underlined link reads none),
    // up to an inline-block, which a decoration from outside does not enter.
    const decoOf = el => {
      const d = { underline: false, strike: false };
      for (let e = el; e && e !== sec.parentElement; e = e.parentElement) {
        const cs = getComputedStyle(e);
        if (cs.textDecorationLine.includes('underline')) d.underline = true;
        if (cs.textDecorationLine.includes('line-through')) d.strike = true;
        // Nor does a decoration reach into an inline-block, a float or a positioned box.
        if (/^inline-(block|flex|grid|table)$/.test(cs.display) || cs.float !== 'none' || /^(absolute|fixed)$/.test(cs.position)) break;
      }
      return d;
    };
    const flatBox = (el, cs) => cs.display === 'inline' && (cs.backgroundImage === 'none' || gradientOnly(cs))
      && !!boxOf(cs, rel(el.getBoundingClientRect()));
    // Left and right margin plus padding of a plain inline element that draws no box, each 0 when
    // under a third of a pixel or negative (not reproduced).
    const sideGap = (el, cs) => cs.display !== 'inline' || flatBox(el, cs) ? [0, 0]
      : ['Left', 'Right'].map(s => { const w = px(cs[`margin${s}`]) + px(cs[`border${s}Width`]) + px(cs[`padding${s}`]); return w >= 0.3 ? w : 0; });
    const inlineBox = el => {
      const cs = getComputedStyle(el);
      if (flatBox(el, cs)) {
        if (pseudoShape(el) || el.getClientRects().length !== 1 || !(el.textContent.trim() || pseudoString(el, '::before') || pseudoString(el, '::after'))) return false;
      } else if (!/^inline-(block|flex)$/.test(cs.display) || !positioned(el) || pseudoShape(el) || cs.backgroundImage !== 'none') return false;
      if ([...el.querySelectorAll('*')].some(d => /^(img|svg|table|br)$/i.test(d.tagName) || !isInline(getComputedStyle(d)) || positioned(d))) return false;
      const range = document.createRange();
      range.selectNodeContents(el);
      const rs = [...range.getClientRects()].filter(r => r.width || r.height);
      return rs.every(r => Math.abs(r.top - rs[0].top) < lineHeight(cs) * k * 0.5);    // one line, or empty
    };
    const nbspCtx = document.createElement('canvas').getContext('2d');
    // Advance of a no-break space in a run's font: the pad runs that stand for an inline box's
    // margin and border (and its padding, when it has no fill to highlight), an empty box or an
    // image are one no-break space, letter-spaced to the width they replace.
    const nbspWidth = f => {
      nbspCtx.font = `${f.italic ? 'italic ' : ''}${f.bold ? 700 : 400} ${f.size}px "${f.face}"`;
      return nbspCtx.measureText('\u00a0').width;
    };
    // A pad run: one no-break space in font f, letter-spaced to w px. A pad narrower than the
    // space itself (a monospace space is 0.6 em wide, an inline code's padding 0.4 em) would need
    // a negative letter-spacing, which LibreOffice ignores (seen 2026-10-09: the text after an
    // inline code sat the difference to the right): it is a smaller no-break space instead, never
    // under 1 pt.
    const padOf = (f, w) => {
      let g = f, nb = nbspWidth(f);
      if (w < nb && nb > 0) { g = { ...f, size: Math.max(4 / 3, f.size * w / nb) }; nb = nbspWidth(g); }
      return { ...g, t: '\u00a0', underline: false, strike: false, spacing: w - nb, pad: true, link: null, rise: undefined };
    };
    // Plain spacing of w px, or none when it is under a third of a pixel (or negative: a box's
    // highlighted padding came out wider than its CSS padding plus border, see hlPad).
    const gapRuns = (f, w) => w >= 0.3 ? [padOf(f, w)] : [];
    // The highlight an inline box's text takes: its CSS background colour, composited over the
    // backgrounds behind it when translucent (a lead slide's inline code is white at 15 % over a
    // dark ground), since a highlight has no transparency. Null when the box has no fill \u2014 a box
    // drawn by its border alone (a dashed tag) is plain text in its own colour. When the layers
    // reach an element painted with a background image (a Marp _backgroundImage gradient), the
    // image may show through: its colour under the box is sampled from its raster once the
    // rasters are drawn (`blend`, resolved after extract) and composited over the colours below
    // it — its own background colour, which CSS paints under the image, and its ancestors' —
    // since an image can be transparent there (a gradient to transparent, a corner logo); the
    // layers above go on top. The hex computed here ignores the image, and stands in should its
    // raster be missing (an image on a table cell or a list item, which the lane does not draw).
    // A box filled with a gradient of its own (an inline span: flatBox) is highlighted in the
    // gradient's mean colour, sampled the same way from a raster of its own background drawn for
    // this only, over its background colour and the ones behind it (edge deck n1, 2026-10-13: such
    // a span came out as plain text with no fill, and white text on it was invisible). One colour
    // cannot draw the gradient itself.
    const highlightOf = (el, cs) => {
      const c = col(cs.backgroundColor), own = cs.backgroundImage !== 'none';
      if (own ? !gradientOnly(cs) : !c) return null;
      // Whether an image behind a gradient of the box's own can show through it: a translucent
      // colour comes back as rgba(), transparent, or CSS Color 4's `/ alpha` (color-mix, oklch).
      const see = own && !(c && c.alpha >= 1) && /rgba\(|transparent|\/\s*(0?\.\d+|0)\s*\)/.test(cs.backgroundImage);
      // CSS paints a box's background colour under its own gradient: below it, not over it.
      const layers = c && !own ? [c] : [], below = c && own ? [c] : [];
      let under = null;
      if (own || c.alpha < 1) for (let p = el.parentElement; p; p = p.parentElement) {
        const pcs = getComputedStyle(p), q = col(pcs.backgroundColor);
        // A gradient of the box's own over a background image would need both sampled, one over
        // the other: such a box stays plain text, readable as in Chromium, rather than take a
        // highlight blended over white.
        if (own && see && pcs.backgroundImage !== 'none' && pcs.display !== 'inline') return null;
        if (!own && !under && pcs.backgroundImage !== 'none' && pcs.display !== 'inline') under = p;
        if (q) { (under || own ? below : layers).push(q); if (q.alpha >= 1) break; }
        if (p === sec) break;
      }
      const over = (rgb, ls) => {
        for (const l of [...ls].reverse()) {
          const v = [0, 2, 4].map(i => parseInt(l.hex.slice(i, i + 2), 16));
          rgb = rgb.map((x, i) => x * (1 - l.alpha) + v[i] * l.alpha);
        }
        return rgb;
      };
      const hexOf = rgb => rgb.map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
      const base = over([255, 255, 255], below);
      const hl = { hex: hexOf(over(base, layers)) };
      if (own) {
        const r = rel(el.getBoundingClientRect());
        bgRaster(cs, r, el);
        hl.blend = blends.length + 1;
        blends.push({ id: hl.blend, el: elId(el), rect: r, box: r, base: hexOf(base), layers });
      } else if (under) {
        hl.blend = blends.length + 1;
        blends.push({ id: hl.blend, el: elId(under), rect: rel(under.getBoundingClientRect()), box: rel(el.getBoundingClientRect()),
          base: hexOf(base), layers });
      }
      return hl;
    };
    // A box drawn by its bottom border alone (a span underlined by a border): its text is
    // underlined in the border's colour, in the nearest style a text underline has — a heavy line
    // from 1.5 px, dashed or dotted as the border. The underline runs just under the baseline,
    // where the border runs under the box's padding, below the descenders (edge deck e25,
    // 2026-10-13: such a span had lost its line).
    const ruleOf = cs => {
      const side = s => px(cs[`border${s}Width`]) > 0 && col(cs[`border${s}Color`]) && !/^(none|hidden)$/.test(cs[`border${s}Style`]);
      if (!side('Bottom') || ['Top', 'Right', 'Left'].some(side)) return null;
      const st = cs.borderBottomStyle, heavy = px(cs.borderBottomWidth) >= 1.5 ? 'Heavy' : '';
      const style = st === 'dashed' ? `dash${heavy}` : st === 'dotted' ? `dotted${heavy}` : st === 'double' ? 'dbl' : heavy ? 'heavy' : 'sng';
      return { style, color: col(cs.borderBottomColor).hex };
    };
    // A highlighted box's padding: spaces in the label's own font and letter-spacing, in the
    // combination that comes nearest the CSS padding (`w` px) but is never wider than the padding
    // plus `room` (the border and margin outside it, which stay plain spacing and absorb the
    // difference, so the text after the box keeps Chromium's position). They go into the label's
    // own run: a highlight split over two runs shows a seam where they meet (LibreOffice). The
    // spaces are no-break spaces (U+00A0), plus thin (U+2009) and hair (U+200A) spaces in the
    // faces whose embedded TTF holds them, for a finer width. Those two allow a line break after
    // them, and the brand fonts lack a word joiner to prevent it, so they go on the outer side:
    // first on the left, last on the right. A renderer that wraps a line on its own (the lines
    // are broken where Chromium broke them, so it should not) may then leave a few pixels of the
    // left padding at the end of the line before the box.
    const FINE = { Montserrat: ['\u2009', '\u200a'], 'Playfair Display': ['\u2009'] };
    const hlPad = (f, w, room, side) => {
      const adv = c => { nbspCtx.font = `${f.italic ? 'italic ' : ''}${f.bold ? 700 : 400} ${f.size}px "${f.face}"`; return nbspCtx.measureText(c).width + (f.spacing || 0); };
      const kinds = ['\u00a0', ...(FINE[f.face] || [])].map(c => ({ c, w: adv(c) })).filter(k => k.w > 0);
      let best = { n: [], w: 0, d: w };
      const each = (i, n, sum) => {
        if (i === kinds.length) {
          const d = Math.abs(sum - w), cnt = n.reduce((a, b) => a + b, 0);
          if (sum <= w + room + 0.3 && (d < best.d - 0.05 || (Math.abs(d - best.d) <= 0.05 && cnt < best.n.reduce((a, b) => a + b, 0)))) best = { n: [...n], w: sum, d };
          return;
        }
        for (let m = 0; m <= 3; m++) { n[i] = m; each(i + 1, n, sum + m * kinds[i].w); }
      };
      if (w > 0) each(0, [], 0);
      const fine = kinds.slice(1).map((k, i) => k.c.repeat(best.n[i + 1] || 0)).join(''), nb = '\u00a0'.repeat(best.n[0] || 0);
      return { t: side === 'left' ? fine + nb : nb + fine, w: best.w };
    };
    // The DrawingML numbering scheme (buAutoNum) of a numbered list's CSS list-style-type, each
    // with the period CSS puts after the number. A type DrawingML has no scheme for (a language's
    // own numerals, decimal-leading-zero) is drawn in arabic numerals.
    const NUMBERING = { decimal: 'arabicPeriod', 'lower-roman': 'romanLcPeriod', 'upper-roman': 'romanUcPeriod',
      'lower-alpha': 'alphaLcPeriod', 'lower-latin': 'alphaLcPeriod', 'upper-alpha': 'alphaUcPeriod', 'upper-latin': 'alphaUcPeriod' };
    // Number n as the scheme draws it, so that the marker measured is the one drawn. Past z, the
    // letter is taken to repeat (aa, bb…, as Word numbers) where CSS goes on with ab, ac…; not
    // checked in PowerPoint.
    const numeral = (n, scheme) => {
      if (n < 1 || !/^(roman|alpha)/.test(scheme)) return String(n);
      let s = '';
      if (scheme.startsWith('alpha')) s = String.fromCharCode(97 + (n - 1) % 26).repeat(Math.ceil(n / 26));
      else for (const [v, r] of [[1000, 'm'], [900, 'cm'], [500, 'd'], [400, 'cd'], [100, 'c'], [90, 'xc'], [50, 'l'], [40, 'xl'], [10, 'x'], [9, 'ix'], [5, 'v'], [4, 'iv'], [1, 'i']])
        for (; n >= v; n -= v) s += r;
      return /Uc/.test(scheme) ? s.toUpperCase() : s;
    };
    // Advance of a list marker as PowerPoint draws it (finish.py), at the item's size: a disc in
    // Playfair Display, whose bullet is about as large as Chromium's disc and sits as high (the
    // other faces' are smaller, or sit higher when scaled up), a circle or a square in Arial (the
    // brand fonts lack them, and a renderer's fallback can be an emoji font twice as wide), a
    // number with its period in the item's font, in its list's numbering scheme (iv. is wider
    // than 4.).
    const markerWidth = (bu, f) => {
      const face = bu.type === 'number' ? f.face : bu.char === '\u2022' ? 'Playfair Display' : 'Arial';
      nbspCtx.font = `${f.italic ? 'italic ' : ''}${f.bold ? 700 : 400} ${f.size}px "${face}"`;
      return nbspCtx.measureText(bu.type === 'number' ? `${numeral(bu.start, bu.scheme)}.` : bu.char).width;
    };

    // ---- text runs, with Chromium's line breaks
    // `boxes`, when given, collects the shapes met on the way: empty inline boxes, images.
    // Each line break also records where Chromium put the glyphs of the line it opens (`g`: for
    // each font met on that line, fontKey → [top, height] of its first glyph rect, slide px), and
    // the returned array's `head` does so for the first line: lineTops() turns them into the top
    // of each line box, so text can be anchored line by line (see anchorText).
    const runsOf = (nodes, skipLists, lhPx, boxes) => {
      const runs = [], head = {}, headBox = {};
      // Chromium's lines are found by baselines: a glyph whose baseline is more than half a line
      // below the last one met opens a new line (a soft break). Not by tops: on one line, a word in
      // a larger font starts higher than the words after it, by the difference of their ascents,
      // which passes half a line from about 1.75 em at the opencell line-height: « Grande ligne »
      // broke after its 1.8 em word (edge decks v1, v2). Glyphs on one line share a baseline,
      // short of a vertical-align.
      let prevBase = null;
      // The character the next text follows on its line, which decides whether capitalize
      // starts a word on its first letter (transform): none at the start, after a break or a
      // block; a space after an inline box or an image.
      let prevCh = null;
      const tol = (lhPx || 16) * k * 0.5;
      const baseOf = (r, f) => r.top + ascentOf(f) + (f.rise || 0) * k;
      const lineAt = b => {
        if (prevBase !== null && b > prevBase + tol) runs.push({ br: true, soft: true });
        prevBase = b;
      };
      // The baseline of an element's first glyph, or null when it has none on the page.
      const firstBase = el => {
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), g = document.createRange();
        for (let t = w.nextNode(); t; t = w.nextNode()) {
          const i = t.nodeValue.search(/\S/);
          if (i < 0) continue;
          g.setStart(t, i); g.setEnd(t, i + 1);
          const c = g.getClientRects()[0];
          return c ? baseOf(c, { ...fontOf(getComputedStyle(t.parentElement)), rise: riseOf(t.parentElement) }) : null;
        }
        return null;
      };
      const mark = (r, f) => {
        if (!r || f.rise) return;
        let line = head;
        for (let i = runs.length - 1; i >= 0; i--) if (runs[i].br) { line = runs[i].g || (runs[i].g = {}); break; }
        const key = fontKey(f);
        if (!line[key]) line[key] = [(r.top - S.top) / k, r.height / k, f.bold, f.italic];
      };
      // The glyphs of an inline box's label (a tag, an inline code) are recorded apart, from the
      // box's own runsOf (`gb`, and the result's `headBox`): lineTops() compares lines by the
      // text's own glyphs, which a label — raised, in another font — would mislead. A table cell
      // falls back on them for a line that holds nothing else (tableItem).
      const markBox = h => {
        let line = headBox;
        for (let i = runs.length - 1; i >= 0; i--) if (runs[i].br) { line = runs[i].gb || (runs[i].gb = {}); break; }
        for (const q in h || {}) if (!line[q]) line[q] = h[q];
      };
      const padRun = padOf;
      // An element with no glyphs of its own on the line — an empty inline box, an image — gives
      // no glyph to take a baseline from, so the line's baseline is inferred from its box. A box
      // on the baseline (the default, or raised by a length) ends its margin box there; any other
      // alignment is read from the box's middle, taken as 0.35 em of the parent's font above the
      // baseline. A new line opens before it when it is lower.
      const emptyAt = (el, cs) => {
        const bb = el.getBoundingClientRect(), em = px(getComputedStyle(el.parentElement).fontSize) * k;
        const va = cs.verticalAlign, raise = /px$/.test(va) ? px(va) : va === 'baseline' ? 0 : null;
        lineAt(raise !== null ? bb.bottom + (px(cs.marginBottom) + raise) * k : (bb.top + bb.bottom) / 2 + 0.35 * em);
      };
      // An image in running text (a list item, a table cell, a title): a pad run as wide as its
      // margin box keeps its place in the line, and the image is drawn at its own position, with
      // the empty inline boxes (behind the text, or over a table).
      const imageRuns = (el, cs) => {
        const r = rel(el.getBoundingClientRect());
        if (!r.w || !r.h) return;
        emptyAt(el, cs);
        runs.push(padRun(fontOf(getComputedStyle(el.parentElement)), r.w + px(cs.marginLeft) + px(cs.marginRight)));
        if (boxes) boxes.push(raster({ kind: 'img', src: el.currentSrc || el.src, w: r.w, h: r.h, fit: cs.objectFit, alt: altOf(el),
          css: { filter: cs.filter, opacity: cs.opacity } }, r));
      };
      // A box that holds text is highlighted text: its text keeps its own colour, weight and size,
      // highlighted in the box's fill, between highlighted no-break spaces that stand for its
      // padding (hlPad), one run with the label; its border and margins are plain spacing, wide
      // enough that the text after it starts where Chromium put it. No border, no rounded corners:
      // a highlight draws neither. A box with no fill is plain text in its colour. A box drawn by
      // its bottom border alone is underlined in that border's colour instead (ruleOf), its
      // padding with it, as the border runs under the padding too.
      const labelRuns = (inner, cs, link, hl, room) => {
        // The box's own text: not the pads or the text of an inline box nested in it, which keeps
        // its own highlight.
        const own = x => x.t && !x.pad && !x.hl;
        const texts = inner.filter(own), a0 = texts[0], z = texts[texts.length - 1];
        if (!a0) return { label: inner, left: px(cs.paddingLeft), right: px(cs.paddingRight) };
        const rule = ruleOf(cs), line = rule ? { underline: true, rule } : {};
        const L = hl || rule ? hlPad(a0, px(cs.paddingLeft), room[0], 'left') : { t: '', w: 0 };
        const Rr = hl || rule ? hlPad(z, px(cs.paddingRight), room[1], 'right') : { t: '', w: 0 };
        const label = inner.map(x => own(x) ? { ...x, link: x.link || link, hl: hl || undefined, ...line } : x);
        // Their own runs, in the label's font: the merge at the end of runsOf folds them into it.
        // The padding is underlined only by a bottom border (`rule`), not by its label's link.
        if (L.t) label.unshift({ ...a0, t: L.t, link: a0.link || link, hl, free: undefined, underline: false, strike: false, ...line });
        if (Rr.t) label.push({ ...z, t: Rr.t, link: z.link || link, hl, free: undefined, underline: false, strike: false, ...line });
        return { label, left: px(cs.paddingLeft) - L.w, right: px(cs.paddingRight) - Rr.w };
      };
      const inlineBoxRuns = (el, cs) => {
        const f = fontOf(cs), link = el.closest('a')?.href || null;
        const range = document.createRange();
        range.selectNodeContents(el);
        const rs = [...range.getClientRects()].filter(r => r.width || r.height);
        const r = rel(el.getBoundingClientRect());
        const outL = px(cs.marginLeft) + px(cs.borderLeftWidth), outR = px(cs.marginRight) + px(cs.borderRightWidth);
        const inner = rs.length ? runsOf(el.childNodes, false, lineHeight(cs)) : [];
        const b = pseudoString(el, '::before'), a = pseudoString(el, '::after');
        if (b) inner.unshift(b);
        if (a) inner.push(a);
        if (inner.some(x => x.t)) {
          // A box that starts a line: the soft break goes before its left pad, not after it.
          // A box whose only text is a ::before / ::after string has no client rects of its own
          // text: its baseline is then where its content box puts a line of its font.
          let base = firstBase(el);
          if (base === null) {
            const bb = el.getBoundingClientRect();
            base = bb.top + (px(cs.borderTopWidth) + px(cs.paddingTop) + plainLine(f, lineHeight(cs)).off) * k + ascentOf(f);
          }
          lineAt(base);
          markBox(inner.head);
          const { label, left, right } = labelRuns(inner, cs, link, highlightOf(el, cs), [outL, outR]);
          // In an inline-block, a link's text is underlined only where its own CSS says so: a
          // link's underline does not reach into it (CSS does not carry text decorations into
          // atomic inlines), and a link inside it draws none unless styled to. pptxgenjs underlines
          // every hyperlink it is not told otherwise about, so a tag in a link, or a link in a tag,
          // had its highlighted padding underlined (edge decks n1 and v1, 2026-10-13). Such runs
          // keep the link and say so (`atomic`, see build.js).
          if (!flatBox(el, cs)) for (const x of label) if (x.link && !x.underline) x.atomic = true;
          runs.push(...gapRuns(f, outL + left), ...label, ...gapRuns(f, outR + right));
          return;
        }
        // Empty: a bar, a swatch. It stays a shape, at its measured position.
        emptyAt(el, cs);
        runs.push(padRun(f, r.w + px(cs.marginLeft) + px(cs.marginRight)));
        const box = boxOf(cs, r);
        if (boxes && box && !box.bgImg) boxes.push(box);
      };
      const walk = list => {
        for (const ch of list) {
          if (ch.nodeType === 3) {
            const cs = getComputedStyle(ch.parentElement), link = ch.parentElement.closest('a')?.href || null;
            const f = { ...fontOf(cs), rise: riseOf(ch.parentElement), ...decoOf(ch.parentElement) }, raw = ch.nodeValue;
            // The text is transformed whole, then cut: a word Chromium broke inside keeps one
            // capital (capitalize), where transforming each piece gave every piece one. Should
            // the transform change the text's length, each piece is transformed on its own.
            const T = transform(raw, cs, prevCh), whole = T.length === raw.length;
            const cut = (a, b) => whole ? T.slice(a, b) : transform(raw.slice(a, b), cs, a ? raw[a - 1] : prevCh);
            if (raw) prevCh = raw[raw.length - 1];
            if (/^pre/.test(cs.whiteSpace)) {
              // Only the newlines are recorded: pre-wrap and pre-line text can wrap besides (free).
              // pre and pre-wrap keep their spaces, a code block's indentation first (`keep`).
              const free = cs.whiteSpace !== 'pre' || undefined, keep = cs.whiteSpace !== 'pre-line' || undefined;
              let at = 0;
              raw.split('\n').forEach((line, i) => {
                if (i) runs.push({ br: true, hard: true });
                if (line) runs.push({ t: cut(at, at + line.length), ...f, link, free, keep });
                at += line.length + 1;
              });
              // The line this text ends on: its last glyph's baseline (none after a final newline).
              // A text of spaces only (between two tags) leaves the line as it was.
              const j = raw.search(/\S\s*$/);
              if (j >= 0 || raw.includes('\n')) {
                prevBase = null;
                if (j >= 0 && !/\n/.test(raw.slice(j))) { const g = document.createRange(); g.setStart(ch, j); g.setEnd(ch, j + 1); const c = g.getClientRects()[0]; if (c) prevBase = baseOf(c, f); }
              }
              continue;
            }
            const re = /(\s+)|(\S+)/g, range = document.createRange();
            let m;
            while ((m = re.exec(raw))) {
              if (m[1]) { runs.push({ t: ' ', ...f, link }); continue; }
              range.setStart(ch, m.index); range.setEnd(ch, m.index + m[2].length);
              const rs = range.getClientRects();
              let from = 0, free;
              if (rs.length) {
                if (prevBase !== null && baseOf(rs[0], f) > prevBase + tol) runs.push({ br: true, soft: true });
                mark(rs[0], f);
                if (rs[rs.length - 1].top > rs[0].top + tol) {
                  // Broken inside the word, as often as Chromium broke it (a long URL or path can
                  // take several lines): cut it before each character that starts a later line.
                  let top = rs[0].top, cuts = 0;
                  for (let i = 1; i < m[2].length; i++) {
                    range.setStart(ch, m.index + i); range.setEnd(ch, m.index + i + 1);
                    const c = range.getClientRects()[0];
                    if (!c || c.top <= top + tol) continue;
                    runs.push({ t: cut(m.index + from, m.index + i), ...f, link }, { br: true, soft: true });
                    mark(c, f);
                    from = i; top = c.top; cuts++;
                  }
                  // Belt and braces: should a line of the word go unrecorded (no glyph rect where
                  // it starts), its last piece keeps wrapping on its own (`free`, see build.js).
                  let lines = 1;
                  for (let i = 1, t0 = rs[0].top; i < rs.length; i++) if (rs[i].top > t0 + tol) { lines++; t0 = rs[i].top; }
                  if (lines > cuts + 1) free = true;
                }
                prevBase = baseOf(rs[rs.length - 1], f);
              }
              runs.push({ t: cut(m.index + from, m.index + m[2].length), ...f, link, free });
            }
          } else if (ch.nodeType === 1) {
            const tag = ch.tagName.toLowerCase();
            if (skipLists && (tag === 'ul' || tag === 'ol')) continue;
            const cs = getComputedStyle(ch);
            if (cs.display === 'none') continue;
            // A forced break (`hard`), unlike the others, still makes a line when it follows one
            // (`a<br><br>b`: an empty line, see the merge below).
            if (tag === 'br') { runs.push({ br: true, hard: true }); prevBase = null; prevCh = null; continue; }
            if (tag === 'img') { imageRuns(ch, cs); prevCh = ' '; continue; }
            if (inlineBox(ch)) { inlineBoxRuns(ch, cs); prevCh = ' '; continue; }
            // A plain inline element with a box broken across lines (flatBox): highlighted text
            // like an inline box on one line (labelRuns), every line of it — its left padding,
            // border and margin open it, on the line its first glyph is on, and the right ones
            // close it.
            const sliced = flatBox(ch, cs), sf = sliced && fontOf(cs);
            // A plain inline element's side margins and padding (an <i> with a margin-left): plain
            // spacing before and after its text (`gap` pads). The left one goes on the line of the
            // element's first fragment, which is not its first glyph's when the line breaks at a
            // space just inside it: the margin then ends the line before. One that draws a box
            // (sliced, or an inline box) carries them through labelRuns instead.
            const [gl, gr] = sideGap(ch, cs);
            if (!sliced && gl) {
              const fr = [...ch.getClientRects()].find(r => r.width || r.height);
              // A fragment's rect is its border box: its glyphs start below its top padding and border.
              if (fr) lineAt(baseOf(fr, { ...fontOf(cs), rise: riseOf(ch) }) + (px(cs.paddingTop) + px(cs.borderTopWidth)) * k);
            }
            if (sliced) { const base = firstBase(ch); if (base !== null) lineAt(base); }
            if (gl) runs.push({ ...padOf(fontOf(cs), gl), gap: true });
            if (!isInline(cs)) prevCh = null;
            const start = runs.length;
            const b = pseudoString(ch, '::before'); if (b) runs.push(b);
            walk(ch.childNodes);
            const a = pseudoString(ch, '::after'); if (a) runs.push(a);
            if (gr) runs.push({ ...padOf(fontOf(cs), gr), gap: true });
            if (sliced) {
              const outL = px(cs.marginLeft) + px(cs.borderLeftWidth), outR = px(cs.marginRight) + px(cs.borderRightWidth);
              const { label, left, right } = labelRuns(runs.splice(start), cs, null, highlightOf(ch, cs), [outL, outR]);
              runs.push(...gapRuns(sf, outL + left), ...label, ...gapRuns(sf, outR + right));
            }
            if (!isInline(cs) && ch.nextSibling) { runs.push({ br: true }); prevBase = null; prevCh = null; }
          }
        }
      };
      walk(nodes);
      // collapse spaces across run boundaries; trim at paragraph and line edges; merge alike runs.
      // A break right after a break makes an empty line when it is forced (`hard`: a <br>, a
      // newline in preformatted text), as in Chromium: `a<br><br>b` is three lines. Any other — the
      // end of a block, which ends the line it is on and opens none — merges into the one before.
      const out = [];
      let atStart = true;
      // Trailing spaces go at a line's end, through the margins (`gap`) that close it.
      const trimEnd = () => {
        let i = out.length - 1;
        while (i >= 0 && out[i].gap) i--;
        if (i >= 0 && !out[i].br) out[i].t = out[i].t.replace(/ +$/, '');
      };
      const brOf = r => ({ br: true, hard: r.hard, g: r.g, gb: r.gb });
      for (const r of runs) {
        if (r.br) {
          const last = out[out.length - 1];
          if (last && !last.br) { trimEnd(); out.push(brOf(r)); }
          else if (last && last.br && r.hard) out.push(brOf(r));
          else if (last && last.br) { if (r.g) last.g = r.g; if (r.gb) last.gb = r.gb; }
          else if (!last) {     // a leading break is dropped
            for (const q in r.g || {}) if (!head[q]) head[q] = r.g[q];
            for (const q in r.gb || {}) if (!headBox[q]) headBox[q] = r.gb[q];
          }
          atStart = true; continue;
        }
        // A margin at a line's start leaves it a line start: the space after it still collapses.
        if (r.gap) { out.push({ ...r }); continue; }
        let t = r.t;
        // A space after a space collapses, even with an element's margin in between (`gap`).
        let prev = out.length - 1;
        while (prev >= 0 && out[prev].gap && !r.gap) prev--;
        if (!r.keep && (atStart || (prev >= 0 && !out[prev].br && / $/.test(out[prev].t || '')))) t = t.replace(/^ +/, '');
        if (!t) continue;
        const last = out[out.length - 1];
        const same = last && !last.br && !last.pad && !r.pad && ['face', 'size', 'bold', 'italic', 'spacing', 'underline', 'strike', 'rise', 'link', 'atomic']
          .every(key => last[key] === r[key]) && (last.color && last.color.hex) === (r.color && r.color.hex)
          && (last.hl && `${last.hl.hex}|${last.hl.blend}`) === (r.hl && `${r.hl.hex}|${r.hl.blend}`) && JSON.stringify(last.rule) === JSON.stringify(r.rule);
        if (same) { last.t += t; if (r.free) last.free = true; } else out.push({ ...r, t });
        atStart = false;
      }
      // The last break ends the last line and opens none (`a<br>` is one line); the breaks before
      // it, which only forced breaks leave, are empty lines (`a<br><br>` is two).
      if (out.length && out[out.length - 1].br) out.pop();
      trimEnd();
      const res = out.filter(r => r.br || r.t);
      res.head = head;
      res.headBox = headBox;
      return res;
    };
    const linesOf = runs => 1 + runs.filter(r => r.br).length;
    // ---- anchoring text under overlays
    // Shapes drawn over flowing text (empty inline boxes such as a size bar, images, pseudo-element
    // bars — not inline boxes holding text, which are highlighted text) sit at Chromium's
    // coordinates, but the renderer lays the text out with its own line pitch: PowerPoint draws
    // exact line spacing about 4 % tighter than Chromium and LibreOffice (one screenshot, Obeya
    // slide 3, 2026-10-08), so text drifts up against the shapes, line after line. Text under
    // overlays is therefore anchored at Chromium's own y: a list is drawn one text box per item,
    // and a paragraph is cut into pieces wherever an overlay sits two lines or more below the top
    // of the piece it would be in, so no overlay is ever more than one line from its anchor.
    // Line tops are where a plain line of the block's own font would start for its glyphs to land
    // where Chromium put them — the y a renderer that keeps an exact pitch needs to be given.
    // Line 0 starts at top0, unless a larger font in it made Chromium's line taller, which lowers
    // its glyphs: it then starts where a plain line holding them would — placed as top0 was: from
    // the line box (plainLine), or, when top0 was itself taken from the glyphs (`glyphs`: a text
    // item's tight or glyph rect, see textItem), half the leading above them. A later line
    // is as far below an earlier one as its glyphs are below that line's glyphs of the same font
    // and size (the block's own, else any other they share), and one line-height below the line
    // before when there are none (a line that opens on an inline box and holds nothing else, an
    // empty line), or when a glyph would be less than half a line below it. A line set entirely
    // in a larger font (no glyph of the block's font) is a plain line of that font instead: it
    // starts where such a line would for its glyphs to land on Chromium's, and is lifted as one
    // (`foreign`: line → the height of a glyph of that font). The result carries `uneven` when
    // the pitch is not even — a taller line, a paragraph margin in a loose list item, a first
    // line anchored on its glyphs, a line in a larger font — and `nat`, the height of a glyph of
    // the block's font, which a piece of such text is lifted by (build.js leadShift) instead of
    // the whole text's.
    const lineTops = (runs, top0, lh, font, glyphs) => {
      const key = fontKey(font), pl = plainLine(font, lh);
      const L = [runs.head || {}, ...runs.filter(r => r.br).map(r => r.g || {})];
      const foreign = new Map();
      const larger = l => {
        if (l[key]) return null;
        let best = null;
        for (const q in l) if (+q.split('|')[1] > font.size && (!best || +q.split('|')[1] > +best.split('|')[1])) best = q;
        if (!best) return null;
        const p = plainLine({ face: best.split('|')[0], size: +best.split('|')[1], bold: l[best][2], italic: l[best][3] }, lh);
        return { top: l[best][0] - p.off, nat: p.h };
      };
      let a0 = top0, uneven = false;
      const f0 = larger(L[0]);
      if (f0) { a0 = f0.top; foreign.set(0, f0.nat); }
      else if (L[0][key]) {
        const e = L[0][key][0] - (glyphs ? (lh - L[0][key][1]) / 2 : pl.off);
        if (Math.abs(e - top0) > 1) { a0 = e; uneven = true; }
      }
      const tops = [a0];
      for (let i = 1; i < L.length; i++) {
        const prev = tops[i - 1], fi = larger(L[i]);
        let own = null;
        if (fi) { own = fi.top; foreign.set(i, fi.nat); }
        else if (L[i][key] && L[0][key]) own = a0 + (L[i][key][0] - L[0][key][0]);
        else for (let j = i - 1; j >= 0 && own === null; j--) {
          if (foreign.has(j)) continue;
          const q = L[i][key] && L[j][key] ? key : Object.keys(L[i]).find(q => L[j][q]);
          if (q) own = tops[j] + (L[i][q][0] - L[j][q][0]);
        }
        // No earlier line to measure from (the lines above are all in a larger font): from its own
        // glyphs, as a plain line of the block's font.
        if (own === null && L[i][key]) own = L[i][key][0] - pl.off;
        const top = own !== null && own > prev + lh * 0.5 ? own : prev + lh;
        if (Math.abs(top - prev - lh) > 1) uneven = true;
        tops.push(top);
      }
      if (foreign.size) uneven = true;
      return Object.assign(tops, { uneven, nat: pl.h, foreign });
    };
    // The lines a text must be cut before. Where the pitch breaks (a line more than 1 px off one
    // line-height below the line before), a renderer that keeps an exact pitch would draw every
    // later line off by that much: a piece starts there. A line in a larger font (lineTops:
    // `foreign`) is a piece of its own, lifted as a line of that font. And an overlay belongs to
    // the last line whose top is above its middle, and opens a new piece when it is two lines or
    // more below the piece's first line.
    const cutsOf = (tops, rects, lh) => {
      const lines = new Set(rects.map(r => {
        const cy = r.y + r.h / 2;
        let i = 0;
        while (i + 1 < tops.length && tops[i + 1] <= cy) i++;
        return i;
      }));
      const cuts = [0], fg = tops.foreign || new Map();
      for (let i = 1; i < tops.length; i++) {
        if (Math.abs(tops[i] - tops[i - 1] - lh) > 1 || fg.has(i) || fg.has(i - 1)
          || (lines.has(i) && i - cuts[cuts.length - 1] >= 2)) cuts.push(i);
      }
      return cuts;
    };
    // Text with no shape over it is cut only where its pitch drifts visibly: where a renderer
    // that keeps an exact pitch from the piece's first line would put a line more than DRIFT px
    // off Chromium's (a line in a larger font, a loose item's paragraph margin, a line beside a
    // tall inline-block), and at a line in a larger font (`foreign`), which is a piece of its
    // own. Smaller unevenness — an inline code makes its line about 1.5 px taller — is left to
    // add up to DRIFT before it cuts, so a text box is not split for a pixel. Under shapes the
    // tighter rule of cutsOf holds.
    const DRIFT = 2;
    const driftCuts = (tops, lh) => {
      const cuts = [0], fg = tops.foreign || new Map();
      for (let i = 1; i < tops.length; i++) {
        const c = cuts[cuts.length - 1];
        if (fg.has(i) || fg.has(i - 1) || Math.abs(tops[i] - (tops[c] + (i - c) * lh)) > DRIFT) cuts.push(i);
      }
      return cuts;
    };
    // Whether text with no shape over it needs anchoring: cuts, or a first line that starts more
    // than DRIFT px from where the text would start it (a larger font on the first line).
    // Not gated on lineTops' `uneven`, which needs one step of more than 1 px: steady steps under
    // a pixel add up too. Text cut for drift is uneven, and its pieces are lifted as plain lines.
    const drifts = (tops, y0, lh) => {
      const d = tops.length > 0 && (driftCuts(tops, lh).length > 1 || tops.foreign.has(0) || Math.abs(tops[0] - y0) > DRIFT);
      if (d) tops.uneven = true;
      return d;
    };
    const splitLines = runs => {
      const lines = [[]];
      for (const r of runs) if (r.br) lines.push([]); else lines[lines.length - 1].push(r);
      return lines;
    };
    const joinLines = (lines, from, to) => {
      const out = [];
      lines.slice(from, to).forEach((l, i) => { if (i) out.push({ br: true }); out.push(...l); });
      return out;
    };
    // A text item with overlays, cut where cutsOf says: each piece starts at its own line's top,
    // and the pieces of uneven text are lifted as plain lines of the block's font (nat).
    // Justified text (a cut would end a line unjustified) and text whose breaks are not all
    // recorded (free) stay whole — anchored on their first line all the same: when a larger font
    // made it taller, the text starts where that line's glyphs need it to, and so do the lines
    // below it when the rest of the pitch is even.
    const anchorText = (t, rects, font) => {
      if (!t || t.lines < 2) return [t];
      const tops = lineTops(t.runs, t.rect.y, t.lh, font, t.glyphs);
      if (tops.length !== t.lines) return [t];
      // With no shape over it, text is anchored only where its pitch drifts (driftCuts).
      if (!rects.length && !drifts(tops, t.rect.y, t.lh)) return [t];
      const first = tops[0] !== t.rect.y && !tops.foreign.has(0) ? { ...t, rect: { ...t.rect, y: tops[0] }, nat: tops.nat } : t;
      if (t.align === 'justify' || t.runs.some(r => r.free)) return [first];
      const cuts = rects.length ? cutsOf(tops, rects, t.lh) : driftCuts(tops, t.lh);
      if (cuts.length < 2) return [rects.length ? t : first];
      const lines = splitLines(t.runs);
      return cuts.map((c, j) => {
        const end = j + 1 < cuts.length ? cuts[j + 1] : lines.length, n = end - c;
        const nat = tops.foreign.has(c) ? { nat: tops.foreign.get(c), fg: true } : tops.uneven && tops.nat ? { nat: tops.nat } : {};
        return { ...t, runs: joinLines(lines, c, end), lines: n, rect: { ...t.rect, y: tops[c], h: n * t.lh }, piece: j, ...nat };
      });
    };
    // Marp shrinks a code block (or a `fit` heading) that would not fit, by drawing it in an SVG
    // whose viewBox is its natural size (auto-scaling: the element carrying data-auto-scaling holds
    // a <marp-auto-scaling> in its shadow DOM). Computed styles keep the unscaled sizes, so its
    // text is scaled by the SVG's width over its viewBox's.
    // Justified text: the room Chromium's own lines leave before they are stretched — the least,
    // over every line but the last, between where the line's glyphs end when it is not justified
    // and `right`, the edge they are stretched to (slide px; undefined for one line). Justified
    // lines fill whatever text box they get, so build.js gives such text only the wrap slack this
    // room does not already cover. Line breaks do not depend on the alignment, so the lines are
    // the same, set flush left for the measure.
    const justifyRoom = (el, nodes, right, lh, one) => {
      const was = el.style.getPropertyValue('text-align'), prio = el.style.getPropertyPriority('text-align');
      el.style.setProperty('text-align', 'left', 'important');
      const ends = [], tol = lh * k * 0.5, g = document.createRange();
      for (const n of nodes || [el]) {
        const w = n.nodeType === 1 ? document.createTreeWalker(n, NodeFilter.SHOW_TEXT) : null;
        for (let t = w ? w.nextNode() : n; t; t = w ? w.nextNode() : null) {
          if (t.nodeType !== 3 || !/\S/.test(t.nodeValue)) continue;
          g.selectNodeContents(t);
          for (const r of g.getClientRects()) {
            if (!r.width) continue;
            const line = ends.find(l => Math.abs(l.top - r.top) < tol);
            if (line) line.right = Math.max(line.right, r.right); else ends.push({ top: r.top, right: r.right });
          }
        }
        // An inline box, an image or an inline element with a right padding, border or margin
        // ends its line at its margin edge, not at its last glyph: that space is no room.
        for (const e of n.nodeType === 1 ? [...(n === el ? [] : [n]), ...n.querySelectorAll('*')] : []) {
          const ecs = getComputedStyle(e), mr = px(ecs.marginRight);
          if (!/^inline/.test(ecs.display) && e.tagName.toLowerCase() !== 'img') continue;
          if (ecs.display === 'inline' && !(px(ecs.paddingRight) + px(ecs.borderRightWidth) + mr) && e.tagName.toLowerCase() !== 'img') continue;
          const rs = [...e.getClientRects()].filter(r => r.width);
          rs.forEach((r, i) => {
            const right = r.right + (i === rs.length - 1 ? mr * k : 0), line = ends.find(l => Math.abs(l.top - r.top) < tol);
            if (line) line.right = Math.max(line.right, right);
          });
        }
      }
      if (was) el.style.setProperty('text-align', was, prio); else el.style.removeProperty('text-align');
      ends.sort((a, b) => a.top - b.top);
      // One line is the last one, never stretched: its room is what it leaves to the edge. A line
      // holding a much larger run can read as two by its glyph tops (`one` says it is one).
      if (ends.length && (one || ends.length === 1)) return Math.max(0, right - (Math.max(...ends.map(l => l.right)) - S.left) / k);
      return ends.length > 1 ? Math.max(0, Math.min(...ends.slice(0, -1).map(l => right - (l.right - S.left) / k))) : undefined;
    };
    const scaleOf = el => {
      const host = el.closest('[data-auto-scaling]');
      const as = host && host.shadowRoot && host.shadowRoot.querySelector('marp-auto-scaling');
      const svg = as && as.shadowRoot && as.shadowRoot.querySelector('svg');
      const vb = svg && svg.viewBox && svg.viewBox.baseVal;
      const s = vb && vb.width ? svg.getBoundingClientRect().width / k / vb.width : 1;
      return s > 0 && Math.abs(s - 1) > 0.002 ? s : 1;
    };
    const textItem = (el, cs, nodes, boxes, keepRaised) => {
      let lh = lineHeight(cs);
      const runs = runsOf(nodes || el.childNodes, false, lh, boxes);
      // Inline boxes (pads, highlights), images, an element's margins (gap pads: its padding is in
      // its border box) and raised or lowered runs (their glyph rects are moved) all stretch the
      // range's rect past the line's glyphs: the text is then placed from its glyphs.
      const hasBox = runs.some(r => r.pad || r.hl || r.rise);
      const b = pseudoString(el, '::before'), a = pseudoString(el, '::after');
      if (b) runs.unshift(b);
      if (a) runs.push(a);
      const sc = scaleOf(el);
      if (sc !== 1) {
        for (const r of runs) if (r.size) { r.size *= sc; if (r.spacing) r.spacing *= sc; if (r.rise) r.rise *= sc; }
        lh *= sc;
      }
      if (!runs.some(r => r.t)) return null;
      const range = document.createRange();
      if (nodes) { range.setStartBefore(nodes[0]); range.setEndAfter(nodes[nodes.length - 1]); } else range.selectNodeContents(el);
      const tight = rel(range.getBoundingClientRect());
      let rect = nodes ? tight : contentRect(el, cs);
      if (!nodes) {
        const top = blockPseudoHeight(el, '::before'), bottom = blockPseudoHeight(el, '::after');
        rect = { ...rect, y: rect.y + top, h: Math.max(lh, rect.h - top - bottom) };
      }
      const al = align(cs.textAlign);
      if (al === 'left' || al === 'justify') rect = { ...rect, w: rect.x + rect.w - tight.x, x: tight.x };
      // A ::before string is drawn before the first glyph but lies outside the range's rect: on
      // one line, the text starts at the content box (plus its indent), where the string starts.
      if (b && !nodes && (al === 'left' || al === 'justify')) {
        const cx = contentRect(el, cs).x + px(cs.textIndent);
        if (cx < rect.x - 0.5) rect = { ...rect, w: rect.w + rect.x - cx, x: cx };
      }
      // A run of text that starts mid-line — after something placed on its own, such as an
      // inline-block holding an image — and wraps: its box starts at the left edge of its later
      // lines, so its first line is indented by a pad run to where Chromium started it, instead
      // of being drawn over whatever comes before it on that line.
      // Any left-aligned text whose first line opens on an inline box or on an element with a left
      // margin (a gap pad) starts at that margin's edge, outside the range's rect: the rect is
      // widened to it (startOf).
      if (al === 'left' || al === 'justify') {
        const f = runs.find(r => r.t);
        // Where the group's first line starts: the first glyph drawn (a leading space is
        // collapsed away), or the margin edge of an inline box met first — its runs already
        // carry its own left margin, border and padding as a pad run, so measuring from the
        // glyph inside it would count them twice.
        let first = null;
        const startOf = n => {
          if (n.nodeType === 3) {
            if (!/\S/.test(n.nodeValue)) return null;
            const g = document.createRange(), i = n.nodeValue.search(/\S/);
            g.setStart(n, i); g.setEnd(n, i + 1);
            const c = g.getClientRects()[0];
            return c ? c.left : null;
          }
          if (n.nodeType !== 1 || getComputedStyle(n).display === 'none') return null;
          if (inlineBox(n)) return n.getBoundingClientRect().left - px(getComputedStyle(n).marginLeft) * k;
          // An element whose margin and padding are gap pads (runsOf): from its margin edge.
          if (sideGap(n, getComputedStyle(n))[0] && n.getClientRects()[0]) return n.getClientRects()[0].left - px(getComputedStyle(n).marginLeft) * k;
          for (const c of n.childNodes) { const x = startOf(c); if (x !== null) return x; }
          return null;
        };
        for (const n of nodes || el.childNodes) { first = startOf(n); if (first !== null) break; }
        const off = first !== null ? (first - S.left) / k - rect.x : 0;
        // A leading inline box's left margin lies outside the range's rect: widen the rect to it.
        if (off < -0.5) rect = { ...rect, x: rect.x + off, w: rect.w - off };
        if (nodes && off > 1 && f) runs.unshift(padOf(f, off));
      }
      // Where the glyphs are. An inline box can stick out of its line's glyphs, and its baseline
      // alignment can move them inside the line box (in a one-line legend, to its top), so with
      // inline boxes the text is placed from the glyphs of the text outside them.
      let lines = linesOf(runs);
      // Text with breaks the runs do not carry (`free`: pre-wrap) has more lines than breaks:
      // count the lines its glyphs sit on.
      if (runs.some(r => r.free)) {
        const tops = [], tol = lh * k * 0.5, g = document.createRange();
        for (const n of nodes || [el]) {
          const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT);
          for (let t = n.nodeType === 3 ? n : w.nextNode(); t; t = n.nodeType === 3 ? null : w.nextNode()) {
            g.selectNodeContents(t);
            for (const r of g.getClientRects()) if (r.width && !tops.some(y => Math.abs(y - r.top) < tol)) tops.push(r.top);
          }
        }
        lines = Math.max(lines, tops.length);
      }
      let top0 = tight.y, nat = tight.h - (lines - 1) * lh, fromGlyphs = false;
      if (hasBox) {
        const insideBox = t => { for (let p = t.parentElement; p && p !== el; p = p.parentElement) if (inlineBox(p)) return true; return false; };
        let top = Infinity, natH = 0, rTop = Infinity;
        for (const n of nodes || [el]) {
          const texts = [];
          if (n.nodeType === 3) texts.push(n);
          else if (n.nodeType === 1) { const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT); while (w.nextNode()) texts.push(w.currentNode); }
          for (const t of texts) {
            // Raised or lowered text (a <sup>) is not where its line's glyphs are: left out too.
            // (The title keeps its raised glyphs' top, never their height, and only beside plain
            // text: its placeholder has no exact spacing, and LibreOffice deepens its line for the
            // raised run, which that higher top roughly makes up for.)
            const raised = riseOf(t.parentElement);
            if (!/\S/.test(t.nodeValue) || insideBox(t) || (raised && !keepRaised)) continue;
            const g = document.createRange();
            g.selectNodeContents(t);
            for (const r of g.getClientRects()) if (r.width) {
              if (raised) { if (raised > 0) rTop = Math.min(rTop, r.top); } else { top = Math.min(top, r.top); natH = Math.max(natH, r.height); }
            }
          }
        }
        if (natH) top = Math.min(top, rTop);
        // Only when that text is on the first line: a line can hold nothing but an inline box.
        const y = (top - S.top) / k;
        if (natH && y - tight.y < lh * 0.75) { top0 = y; nat = natH / k; fromGlyphs = true; }
        // A title whose only plain text is boxed (inline code, a tag) beside a superscript: from
        // the superscript's top, a line-height tall, rather than the content box, which leaves out
        // what LibreOffice adds to its line for the raised run.
        else if (!natH && rTop < Infinity && (rTop - S.top) / k - tight.y < lh * 0.75) { top0 = (rTop - S.top) / k; nat = lh; fromGlyphs = true; }
      }
      // A rect taken from the glyph box starts half a leading below its line box: move it up,
      // so every text rect starts where CSS starts the line.
      if (nodes) rect = { ...rect, y: top0 - (lh - nat) / 2, h: lines * lh };
      else if (fromGlyphs) rect = { ...rect, y: top0 - (lh - nat) / 2 };
      return { type: 'text', rect, tight, runs, align: al, lh, lines, nat, valign: 'top', dir: cs.direction,
        glyphs: !!nodes || fromGlyphs || undefined,
        room: al === 'justify' && lines > 1 ? justifyRoom(el, nodes, rect.x + rect.w, lh) : undefined };
    };
    const inlineDecor = (root, out) => {    // pseudo shapes on inline descendants (inside tables, lists)
      for (const d of root.querySelectorAll('*')) for (const w of ['::before', '::after']) {
        const p = getComputedStyle(d, w);
        if (hasContent(p) && p.display === 'inline-block') { const bx = pseudoBox(d, w); if (bx) out.push(...bx); }
      }
    };

    // ---- lists, tables, SVG
    // Space before a paragraph that does not simply follow its previous sibling item — the first
    // item of a nested list, the item after one that ended on its nested list, the text after a
    // nested list: the gap Chromium leaves between the previous paragraph's last line and this
    // paragraph's first line (top), less the previous paragraph's space after, which PowerPoint
    // adds to it. Margins of the nested list itself collapse into that gap in CSS.
    const gapAfter = (prev, top) => Math.max(0, top - (prev.tops[prev.tops.length - 1] + prev.lh) - prev.after);
    const listItem = (el, level, paras, boxes) => {
      const ordered = el.tagName.toLowerCase() === 'ol';
      const lcs = getComputedStyle(el);
      let n = ordered ? (el.start || 1) : 0, prevAfter = null, prevOwn = null, prevLoose = false;
      // A block in an item with a vertical margin (a loose list's <p>): its margins, not the
      // item's, set the gap between sibling items.
      const blockMargin = (e, side) => !!e && !/^(ul|ol)$/i.test(e.tagName) && !isInline(getComputedStyle(e)) && px(getComputedStyle(e)[side]) > 0;
      for (const li of el.children) {
        if (li.tagName.toLowerCase() !== 'li') continue;
        const cs = getComputedStyle(li), lh = lineHeight(cs);
        // A right-to-left item is aligned on its right edge by default: CSS's `start` is the right.
        const al = cs.direction === 'rtl' && /^(start|end)$/.test(cs.textAlign) ? { start: 'right', end: 'left' }[cs.textAlign] : align(cs.textAlign);
        const loose = prevLoose || blockMargin(li.firstElementChild, 'marginTop');
        prevLoose = blockMargin(li.lastElementChild, 'marginBottom');
        // Sibling items' vertical margins collapse in CSS (the gap is the larger of the two);
        // PowerPoint adds space-after and space-before, so the second keeps only the excess.
        // When something else comes in between (see gapAfter), the gap is measured instead.
        let before = prevAfter === null ? px(cs.marginTop) : Math.max(0, px(cs.marginTop) - prevAfter);
        prevAfter = px(cs.marginBottom);
        // A numbered item keeps its list's numbering scheme: Marp's default theme, which opencell
        // imports, numbers a nested <ol> in lower-roman and one nested deeper in lower-alpha.
        const type = cs.listStyleType, font = fontOf(cs);
        const bullet = type === 'none' ? null : ordered ? { type: 'number', start: n, scheme: NUMBERING[type] || 'arabicPeriod' } :
          { char: { disc: '•', circle: '◦', square: '▪' }[type] || '•' };
        const c = contentRect(li, cs);
        // Where a part of the item starts, so that build.js can anchor it on its own (see
        // anchorText): the top of the block that holds its first text when that is a paragraph
        // inside the item (a loose list); null when the text sits in the item itself.
        const blockTop = nodes => {
          for (const n0 of nodes) {
            const w = n0.nodeType === 1 ? document.createTreeWalker(n0, NodeFilter.SHOW_TEXT) : null;
            for (let t = w ? w.nextNode() : n0; t; t = w ? w.nextNode() : null) {
              if (t.nodeType !== 3 || !/\S/.test(t.nodeValue) || t.parentElement.closest('ul,ol') !== el) continue;
              let b = t.parentElement;
              while (b !== li && isInline(getComputedStyle(b))) b = b.parentElement;
              return b !== li ? contentRect(b, getComputedStyle(b)).y + blockPseudoHeight(b, '::before') : null;
            }
          }
          return null;
        };
        // Text after a nested list (`<li>a <ul>…</ul> b</li>`) comes after that list's items, as
        // Chromium draws it: a paragraph of its own with no marker (`cont`), at the item's text
        // position. The item's bottom margin then goes after its last part.
        const parts = [{ nodes: [] }];
        for (const ch of li.childNodes) {
          if (ch.nodeType === 1 && /^(ul|ol)$/i.test(ch.tagName)) { parts[parts.length - 1].sub = ch; parts.push({ nodes: [] }); }
          else parts[parts.length - 1].nodes.push(ch);
        }
        const texty = ns => ns.some(n => n.nodeType === 3 ? /\S/.test(n.nodeValue)
          : n.nodeType === 1 && ((n.textContent || '').trim() || holdsInlineBox(n)));
        const conts = parts.slice(1).some(p => texty(p.nodes));
        const runs = runsOf(conts ? parts[0].nodes : li.childNodes, true, lh, boxes);
        // An item's ::before string (an arrow in a list-style: none list) opens its text.
        const lb = pseudoString(li, '::before');
        if (lb) runs.unshift(lb);
        const y = blockTop(conts ? parts[0].nodes : [...li.childNodes]) ?? c.y;
        // An item that opens directly on its nested list has no line of its own: Chromium draws
        // its marker on the first nested item's line (`markerOnly`, placed by visit).
        // With or without a marker; not an item whose ::before string Chromium draws on a line of its own.
        const markerOnly = !!(parts[0].sub && !texty(parts[0].nodes) && !lb) || undefined;
        // Right after a nested list (prevOwn is not the last paragraph), the gap is measured; so
        // it is between loose siblings, where the paragraphs' margins make it.
        if (paras.length && (level > 0 && prevOwn === null || prevOwn !== null && (prevOwn !== paras.length - 1 || loose))) before = gapAfter(paras[paras.length - 1], y);
        // A justified item takes only the slack its lines need, as justified text does (textItem).
        const room = al === 'justify' ? justifyRoom(li, parts[0].nodes, c.x + c.w, lh, linesOf(runs) === 1) : undefined;
        paras.push({ runs, level, lh, bullet, font, mw: bullet ? markerWidth(bullet, font) : 0,
          indent: px(lcs.paddingLeft), x: c.x, w: c.w, after: conts || parts[0].sub ? 0 : px(cs.marginBottom), before,
          align: al, y, tops: lineTops(runs, y, lh, font), markerOnly, inside: cs.listStylePosition === 'inside' || undefined, room });
        prevOwn = paras.length - 1;
        n++;
        let last = paras[paras.length - 1];
        // In document order: text, nested list, text, nested list… Each text after a nested list
        // is measured from the list before it (gapAfter).
        for (let i = 0; i < parts.length; i++) {
          if (conts && i && texty(parts[i].nodes)) {
            const rs = runsOf(parts[i].nodes, true, lh, boxes), h = rs.head && rs.head[fontKey(font)];
            const after = parts[i - 1].sub;
            let top = blockTop(parts[i].nodes);
            if (top === null) top = h ? h[0] - plainLine(font, lh).off
              : rel(after.getBoundingClientRect()).y + rel(after.getBoundingClientRect()).h + px(getComputedStyle(after).marginBottom);
            paras.push(last = { runs: rs, level, lh, bullet: null, cont: true, font, mw: 0, indent: px(lcs.paddingLeft), x: c.x, w: c.w,
              after: 0, before: gapAfter(paras[paras.length - 1], top), align: al, y: top, tops: lineTops(rs, top, lh, font),
              room: al === 'justify' ? justifyRoom(li, parts[i].nodes, c.x + c.w, lh, linesOf(rs) === 1) : undefined });
          }
          if (parts[i].sub) listItem(parts[i].sub, level + 1, paras, boxes);
        }
        // The item's bottom margin goes after its last part; after its nested list, it is measured
        // into the next item's space before instead.
        if (conts) last.after = texty(parts[parts.length - 1].nodes) ? px(cs.marginBottom) : 0;
      }
      return paras;
    };
    const tableItem = (el, boxes) => {
      const rows = [...el.rows];
      const grid = rows.map(tr => [...tr.cells].map(td => {
        const cs = getComputedStyle(td);
        const side = s => {
          const w = px(cs[`border${s}Width`]), c = col(cs[`border${s}Color`]);
          return w > 0 && c && cs[`border${s}Style`] !== 'none' ? { w, c } : null;
        };
        // Shapes over a cell (an empty inline box, an image) note its alignment and side padding:
        // build.js trims that padding, which moves the cell's text, and moves them along with it.
        const mine = [], al = align(cs.textAlign), pl = px(cs.paddingLeft), pr = px(cs.paddingRight);
        const lh = lineHeight(cs), font = fontOf(cs), c = contentRect(td, cs), cell = rel(td.getBoundingClientRect());
        // The cell's paragraphs: its text outside lists is one (its blocks and <br>s are lines of
        // it), and each list item is one of its own, with its marker and its text position (`mx`,
        // from the content box's left edge), nested items included, as in a list (listItem).
        const paras = [];
        let group = [];
        const flush = () => {
          const runs = group.length ? runsOf(group, false, lh, mine) : [];
          if (runs.length) paras.push({ runs, lh, font });
          group = [];
        };
        // The narrowest hang a list's markers fit in (`least`: its widest marker plus a quarter em,
        // as in addList) is the list's, so that its items hang alike ("1." is narrower than "2.").
        const list = l => {
          const ordered = l.tagName.toLowerCase() === 'ol', lcs = getComputedStyle(l), items = [];
          let n = ordered ? (l.start || 1) : 0;
          for (const li of l.children) {
            if (li.tagName.toLowerCase() !== 'li') continue;
            const ics = getComputedStyle(li), f = fontOf(ics), type = ics.listStyleType;
            const bullet = type === 'none' ? null : ordered ? { type: 'number', start: n, scheme: NUMBERING[type] || 'arabicPeriod' }
              : { char: { disc: '•', circle: '◦', square: '▪' }[type] || '•' };
            // As in listItem: the item's text before its first nested list is its own paragraph,
            // and text after a nested list a paragraph of its own with no marker, after that
            // list's items — in document order, as Chromium draws them.
            const parts = [{ nodes: [] }];
            for (const ch of li.childNodes) {
              if (ch.nodeType === 1 && /^(ul|ol)$/i.test(ch.tagName)) { parts[parts.length - 1].sub = ch; parts.push({ nodes: [] }); }
              else parts[parts.length - 1].nodes.push(ch);
            }
            const base = { lh: lineHeight(ics), font: f, indent: px(lcs.paddingLeft), mx: contentRect(li, ics).x - c.x };
            const it = { ...base, runs: runsOf(parts[0].nodes, true, base.lh, mine), bullet, mw: bullet ? markerWidth(bullet, f) : 0 };
            const lb = pseudoString(li, '::before');
            if (lb) it.runs.unshift(lb);
            // An item that opens on its nested list has no line of its own: it is left out, its
            // marker with it (a cell cannot put two paragraphs on one line).
            if (!(parts[0].sub && !it.runs.some(r => r.t))) { paras.push(it); items.push(it); }
            n++;
            parts.forEach((pt, i) => {
              if (i && pt.nodes.length) {
                const runs = runsOf(pt.nodes, true, base.lh, mine);
                if (runs.some(r => r.t)) paras.push({ ...base, runs, bullet: null, mw: 0 });
              }
              if (pt.sub && getComputedStyle(pt.sub).display !== 'none') list(pt.sub);
            });
          }
          const least = Math.max(0, ...items.map(it => it.mw + 0.25 * it.font.size));
          for (const it of items) it.least = least;
        };
        for (const ch of td.childNodes) {
          if (ch.nodeType === 1 && /^(ul|ol)$/i.test(ch.tagName) && getComputedStyle(ch).display !== 'none') { flush(); list(ch); }
          else group.push(ch);
        }
        flush();
        for (const b of mine) b.cell = { align: al, pad: [pl, pr] };
        boxes.push(...mine);
        // Each line at Chromium's baseline. A cell is not cut like other text (anchorText): its
        // lines take exact spacing line by line (`sp`, build.js), each measured from the line
        // before, so that every line lands where Chromium put it — a line holding a larger font,
        // after a paragraph or list-item margin, after an empty line. With exact spacing a line's
        // baseline sits its spacing below the end of the line before, less the line's largest
        // descent (LibreOffice puts the extra leading above the glyphs, and a deficit too), so a
        // line's spacing is the distance between the two baselines plus the difference of their
        // descents. Where the pitch stays within DRIFT px of the line-height, as for text with no
        // shape over it, the line keeps its paragraph's line-height: an inline code that makes its
        // line 1.5 px taller (edge deck e27) does not split a paragraph. Until 2026-10-13 a cell
        // had one line spacing: its paragraph margins were lost, and a cell with a larger font fell
        // back to single spacing, its lines about 16 % of a line-height closer than in Marp and
        // its row 5 px taller (edge deck v2, row 1: 104 px for 99).
        // A line's baseline and largest descent (and glyph height), from the glyphs recorded on it
        // (runsOf: `head`, `g`), or from its inline boxes' labels when it holds nothing else (a
        // tag alone, an inline code: `headBox`, `gb`); null when there are none. Its descent is
        // never less than the paragraph's own font's, as in CSS, where every line holds a strut in
        // that font: a line without a glyph of it gets one in the PPTX, a zero-width space (see
        // below). Renderers disagree on some faces' descent: a cell holding only an inline code
        // sat 2–3 px low in LibreOffice (ocskills deck, slide 2), which fits Courier New's OS/2
        // typo descent, 0.19 em, where Chromium takes its hhea one, 0.30 em (read from the font's
        // tables). The strut's descent, in the brand font, is the larger one, and is the same in
        // both.
        const lineAt = ([g, gb], p) => {
          const all = { ...(gb || {}), ...(g || {}) }, keys = Object.keys(all);
          if (!keys.length) return null;
          const mine = Object.keys(g || {}).length ? g : all;
          const own = mine[fontKey(p.font)] ? fontKey(p.font) : Object.keys(mine).reduce((a, b) => +b.split('|')[1] > +a.split('|')[1] ? b : a);
          const st = plainLine(p.font, p.lh);
          let desc = st.off + st.h - st.base, h = 0, base = 0;
          for (const q of keys) {
            const m = plainLine({ face: q.split('|')[0], size: +q.split('|')[1], bold: all[q][2], italic: all[q][3] }, p.lh);
            desc = Math.max(desc, m.off + m.h - m.base); h = Math.max(h, m.h);
            if (q === own) base = all[q][0] + m.base - m.off;
          }
          return { base, desc, h };
        };
        // `top`: where the text block starts; `bot`: where the renderer ends its last line so far.
        // A line that holds no larger font and needs more than its line-height (after a margin, an
        // empty line) keeps its line-height and gets the rest as space before (`bf`), as CSS
        // spaces it: a list item after a margin stays one paragraph.
        let top = null, bot = null, blind = false;
        const lineGlyphs = p => [[p.runs.head, p.runs.headBox], ...p.runs.filter(r => r.br).map(r => [r.g, r.gb])];
        const anyGlyph = paras.some(p => lineGlyphs(p).some(g => lineAt(g, p)));
        for (const p of paras) {
          const G = [[p.runs.head, p.runs.headBox], ...p.runs.filter(r => r.br).map(r => [r.g, r.gb])], L = G.map(g => lineAt(g, p));
          // The strut: a zero-width space in the paragraph's font opens each line that has no glyph
          // of it, so that the renderer gives that line the font's descent, as Chromium does.
          const zw = { ...p.font, t: '\u200b', spacing: 0, underline: false, strike: false, link: null };
          let li = 0;
          p.runs = p.runs.flatMap((r, i) => {
            const open = i === 0 || p.runs[i - 1].br;
            if (r.br) li++;
            return open && !r.br && !(G[li][0] && G[li][0][fontKey(p.font)]) ? [zw, r] : [r];
          });
          const pl0 = plainLine(p.font, p.lh), larger = m => m && m.h > pl0.h + 0.5;
          p.bf = L.map(() => 0);
          p.sp = L.map((m, i) => {
            if (bot === null) {
              // The first line: at its line-height, or at the height of its glyphs when a larger
              // font makes them taller (a KPI figure), so that no renderer has to draw them above
              // the text's top.
              const s = larger(m) ? Math.max(p.lh, m.h) : p.lh;
              // A cell with no glyph recorded on any line (a ::before icon alone, a raised run
              // alone) says nothing of where Chromium put the block: it keeps its padding as margins
              // and the renderer aligns it, top, middle or bottom, as before 2026-10-13. One whose
              // first line alone has none (an image or an icon over a caption) is placed from its
              // guessed first line, as before too.
              if (!m && !anyGlyph) blind = true;
              // A first line with no glyph (an icon, a <sup>) over lines that have some is placed
              // from the first of those, a line-height per line above it, wherever the cell's
              // alignment put the block; from the content box's top only when its paragraph has
              // none (its glyphs are in a later paragraph, or nowhere).
              // The line just above that one ends where that line's own height starts (a line in a
              // larger font, a KPI figure, is taller than a line-height). A top-aligned cell keeps
              // the content box's top, which is right there and keeps a paragraph margin between
              // the two, unless the glyph-less line holds a larger run (a 40 px icon), which needs
              // its room below the top.
              const i0 = m ? 0 : L.findIndex(x => x);
              const big0 = (() => { for (const r of p.runs) { if (r.br) return false; if (r.t && r.size > p.font.size * 1.1) return true; } return false; })();
              const back = i0 > 0 && (cs.verticalAlign !== 'top' || big0);
              // (A larger line's box: its glyphs plus its share of the leading, at the cell's pitch.)
              const h0 = i0 > 0 && larger(L[i0]) ? Math.max(p.lh, (L[i0].h + L[i0].h / pl0.h * p.lh) / 2) : p.lh;
              bot = m ? m.base + m.desc : back ? L[i0].base + L[i0].desc - h0 - (i0 - 1) * p.lh : c.y + (p.lh + pl0.h) / 2;
              top = bot - s;
              return s;
            }
            let s = p.lh;
            if (m && Math.abs(m.base + m.desc - bot - p.lh) > DRIFT && m.base + m.desc - bot > p.lh * 0.5) s = m.base + m.desc - bot;
            bot += s;
            if (s > p.lh && !larger(m)) { p.bf[i] = s - p.lh; return p.lh; }
            return s;
          });
        }
        // Vertical margins (`vm`, px) that put the text block [top, bot] where Chromium put it,
        // whatever the alignment: top-aligned, the top margin is the block's distance to the
        // cell's top; bottom-aligned, the bottom one is; centred, the two differ by twice the
        // block's offset from the cell's middle. The top margin is never under 1 pt (pptxgenjs
        // reads the margins in inches below that), and the margins leave the block its room with
        // half a pixel to spare: a renderer grows a row whose text does not fit.
        const PT1 = 4 / 3, vt = { middle: 'middle', bottom: 'bottom' }[cs.verticalAlign] || 'top';
        let vm = [px(cs.paddingTop), px(cs.paddingBottom)];
        if (top !== null && !blind) {
          // Too little room above the block for that 1 pt (a first line whose leading reaches the
          // cell's top: Marp's default theme sets 1.5 × 29 px in a 6 px padding, edge deck e31):
          // the first line's spacing gives up the difference, which leaves its glyphs in place.
          if (top - cell.y < PT1 + 0.25) { const d = PT1 + 0.25 - (top - cell.y); paras[0].sp[0] -= d; top += d; }
          const above = top - cell.y, below = cell.y + cell.h - bot;
          if (vt === 'top') vm = [above, Math.max(0, Math.min(vm[1], below - 0.5))];
          else if (vt === 'bottom') vm = [Math.max(PT1, Math.min(vm[0], above - 0.5)), Math.max(0, below)];
          else {
            const d = above - below, m = Math.max(d >= 0 ? Math.max(0, PT1 - d) : PT1, Math.min(vm[0], vm[1], above - 0.5, below - 0.5));
            vm = d >= 0 ? [m + d, m] : [m, m - d];
          }
        }
        return { paras, lh, vm, align: al, valign: vt,
          fill: col(cs.backgroundColor) || col(getComputedStyle(tr).backgroundColor),
          pad: [px(cs.paddingTop), pr, px(cs.paddingBottom), pl],
          border: ['Top', 'Right', 'Bottom', 'Left'].map(side), colspan: td.colSpan, rowspan: td.rowSpan, w: cell.w };
      }));
      const ref = grid.find(r => r.every(c => c.colspan === 1)) || grid[0];
      const first = rel(rows[0].cells[0].getBoundingClientRect());
      return { type: 'table', x: first.x, y: first.y, colW: ref.map(c => c.w),
               rowH: rows.map(tr => rel(tr.getBoundingClientRect()).h), grid };
    };
    const svgItems = svg => {
      const all = [svg, ...svg.querySelectorAll('*')];
      const flat = all.every(n => {
        if (!SVG_OK.has(n.tagName.toLowerCase())) return false;
        const m = n.getScreenCTM && n.getScreenCTM();
        return !m || (Math.abs(m.b) < 1e-6 && Math.abs(m.c) < 1e-6);
      });
      const r = rel(svg.getBoundingClientRect());
      if (!flat) { svg.dataset.p2x = String(rasterId + 1); return [raster({ kind: 'element', selector: `[data-p2x="${rasterId + 1}"]`, alt: altOf(svg) }, r)]; }
      const out = [];
      const pt = (n, x, y) => { const p = new DOMPoint(x, y).matrixTransform(n.getScreenCTM()); return { x: (p.x - S.left) / k, y: (p.y - S.top) / k }; };
      const paint = n => {
        const cs = getComputedStyle(n), sc = n.getScreenCTM().a / k;
        const stroke = col(cs.stroke), sw = px(cs.strokeWidth) * sc;
        const fill = col(cs.fill), fo = +cs.fillOpacity, so = +cs.strokeOpacity, op = +cs.opacity;
        return { stroke: stroke && sw > 0 ? { c: stroke, w: sw, dash: cs.strokeDasharray !== 'none', alpha: so * op } : null,
                 fill: fill ? { c: fill, alpha: fo * op } : null };
      };
      for (const n of all.slice(1)) {
        const tag = n.tagName.toLowerCase();
        if (tag === 'line') {
          const a = pt(n, n.x1.baseVal.value, n.y1.baseVal.value), b = pt(n, n.x2.baseVal.value, n.y2.baseVal.value);
          const p = paint(n);
          if (p.stroke) out.push({ type: 'line', a, b, stroke: p.stroke });
        } else if (tag === 'rect' || tag === 'circle' || tag === 'ellipse') {
          const p = paint(n);
          if (p.fill || p.stroke) out.push({ type: 'shape', shape: tag === 'rect' ? 'rect' : 'ellipse', rect: rel(n.getBoundingClientRect()),
            radius: tag === 'rect' ? (n.rx.baseVal.value * n.getScreenCTM().a / k) : 0, ...p });
        } else if (tag === 'polyline' || tag === 'polygon') {
          const p = paint(n);
          const pts = [...n.points].map(q => pt(n, q.x, q.y));
          if ((p.fill && tag === 'polygon') || p.stroke) out.push({ type: 'poly', points: pts, closed: tag === 'polygon',
            fill: tag === 'polygon' ? p.fill : null, stroke: p.stroke });
        } else if (tag === 'text') {
          const cs = getComputedStyle(n), sc = n.getScreenCTM().a / k;
          const t = n.textContent.replace(/\s+/g, ' ').trim();
          if (!t) continue;
          const f = fontOf(cs), anchor = cs.textAnchor;
          out.push({ type: 'text', rect: rel(n.getBoundingClientRect()), lines: 1, svg: true, valign: 'top',
            align: anchor === 'middle' ? 'center' : anchor === 'end' ? 'right' : 'left', lh: f.size * sc * 1.22,
            runs: [{ t, ...f, size: f.size * sc, color: col(cs.fill) || f.color }] });
        }
      }
      return out;
    };

    // ---- chrome: background, section pseudo-elements and stripes, page number
    const chrome = { bg: secBg, decor: [], footer: null, header: null, pagenum: null, title: null };
    if (secCs.backgroundImage !== 'none') chrome.decor.push(bgRaster(secCs, { x: 0, y: 0, w: W, h: H }, sec));
    for (const s of stripesOf(secCs, { x: 0, y: 0, w: W, h: H })) chrome.decor.push({ type: 'box', rect: { x: s.x, y: s.y, w: s.w, h: s.h }, fill: s.c });
    for (const which of ['::before', '::after']) {
      const pcs = getComputedStyle(sec, which);
      if (which === '::after' && sec.dataset.marpitPagination !== undefined && pcs.content !== 'none') {
        chrome.pagenum = { rightPx: px(pcs.right), bottom: px(pcs.bottom), ...fontOf(pcs), lh: lineHeight(pcs) };
        continue;
      }
      const d = pseudoBox(sec, which);
      if (d) chrome.decor.push(...d);
    }

    // ---- shapes in running text — empty inline boxes, images (runsOf: `boxes`): behind a text
    // box, which is transparent, or over what would hide them, a table cell's fill or the box
    // that carries the text. They hold no text, so either way nothing is covered.
    const needsOwnPlace = d => positioned(d) && !inlineBox(d);
    const holdsInlineBox = n => n.nodeType === 1 && (inlineBox(n) || [...n.querySelectorAll('*')].some(inlineBox));

    // ---- the walk, in paint order
    const items = [];
    const titleEl = sec.classList.contains('lead') ? null : [...sec.children].find(c => /^h[12]$/i.test(c.tagName)) || null;
    const visit = (el, out) => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return;
      const tag = el.tagName.toLowerCase();
      if ((tag === 'footer' || tag === 'header') && el.parentElement === sec) { chrome[tag] = textItem(el, cs); return; }
      const rect = rel(el.getBoundingClientRect());
      if (!rect.w && !rect.h) return;
      const before = pseudoBox(el, '::before'), after = pseudoBox(el, '::after');
      if (el === titleEl) {
        const boxes = [], t = textItem(el, cs, undefined, boxes, true), deco = [];
        emitBox(boxOf(cs, rect), cs, deco, el);
        chrome.title = { text: t, deco };
        if (before) out.push(...before);
        out.push(...boxes);
        if (after) out.push(...after);
        return;
      }
      if (tag === 'img') { out.push(raster({ kind: 'img', src: el.currentSrc || el.src, w: rect.w, h: rect.h, fit: cs.objectFit, alt: altOf(el), css: { filter: cs.filter, opacity: cs.opacity } }, rect)); return; }
      if (tag === 'svg') { out.push(...svgItems(el)); return; }
      const box = boxOf(cs, rect);
      if (tag === 'table') {
        emitBox(box, cs, out, el); if (before) out.push(...before);
        const boxes = [];
        out.push(tableItem(el, boxes), ...boxes); inlineDecor(el, out);
        if (after) out.push(...after); return;
      }
      if (tag === 'ul' || tag === 'ol') {
        emitBox(box, cs, out, el);
        // A right-to-left list is drawn as one text box of right-to-left paragraphs (build.js), with
        // no empty inline box or image over it: its script is drawn in a fallback font (the brand
        // fonts have no Arabic or Hebrew) whose widths are not Chromium's, so a shape placed at
        // Chromium's x would sit away from its place in the text.
        const rtl = cs.direction === 'rtl';
        const boxes = [], paras = listItem(el, 0, [], boxes), decor = [];
        inlineDecor(el, decor);
        if (!rtl) out.push(...boxes);
        // A list with overlays is drawn one text box per item, each at the y Chromium gave it
        // (anchorText); an item is cut further where cutsOf says. Without overlays it stays whole.
        const rects = [...(rtl ? [] : boxes), ...decor].map(b => b.rect).filter(Boolean);
        // A list with no shape over it is drawn one box per item too when an item's pitch drifts
        // (driftCuts): a line in a larger font, a loose item's paragraphs, a tall inline-block.
        // Kept whole, everything below such a line would sit higher than in Chromium.
        // Every item is tried (drifts marks its tops uneven), not only up to the first that drifts.
        const uneven = !rtl && !rects.length && paras.map(p => p.runs.length > 0 && drifts(p.tops, p.y, p.lh)).some(Boolean);
        // So is a list a single text box cannot draw as Chromium does: one with a centred or
        // right-aligned item, whose marker Chromium hangs at the list's left edge whatever the
        // alignment (in one text box it sits next to the text, and a centred item among left-aligned
        // ones is shifted by the wrap slack), and one with an item that opens on its nested list,
        // whose marker goes on the first nested item's line (two paragraphs cannot share a line).
        const sided = paras.some(p => p.runs.some(r => r.t) && (p.align === 'center' || p.align === 'right'));
        const split = !rtl && (rects.length > 0 || uneven || sided || paras.some(p => p.markerOnly && p.bullet));
        for (const p of paras) {
          const mine = rects.filter(r => { const cy = r.y + r.h / 2; return cy >= p.tops[0] && cy < p.tops[p.tops.length - 1] + p.lh; });
          const cuts = split && p.tops.length >= 2 && p.align !== 'justify' && !p.runs.some(r => r.free)
            ? (rects.length ? cutsOf(p.tops, mine, p.lh) : driftCuts(p.tops, p.lh)) : [0];
          // A cut at a line in a larger font carries that font's glyph height (`nat`, see lineTops).
          if (split && (cuts.length > 1 || p.tops.foreign.has(0))) p.cuts = cuts.map(i => ({ line: i, y: p.tops[i], nat: p.tops.foreign.get(i) }));
          // Uneven text is anchored on its glyphs (lineTops), and lifted as plain lines (build.js).
          if (split) { p.y = p.tops[0]; if (p.tops.uneven) p.uneven = true; } else delete p.y;
          delete p.tops;
        }
        // An item that opens on its nested list (markerOnly): its marker goes on the first nested
        // item's line, as in Chromium. Only a right-to-left list keeps such an item in one text
        // box, which cannot put two paragraphs on one line: it is left out there (its marker with
        // it) and its space before goes to that nested item.
        for (let i = paras.length - 2; i >= 0; i--) {
          const p = paras[i];
          if (!p.markerOnly) continue;
          if (split) p.y = paras[i + 1].y;
          else { paras[i + 1].before = Math.max(paras[i + 1].before, p.before); paras.splice(i, 1); }
        }
        if (paras.some(p => p.runs.length)) out.push({ type: 'list', rect, paras, split: split || undefined, rtl: rtl || undefined });
        out.push(...decor);
        return;
      }
      const inlineOnly = [...el.querySelectorAll('*')].every(d => {
        const t = d.tagName.toLowerCase();
        return t !== 'img' && t !== 'svg' && t !== 'table' && (t === 'br' || (isInline(getComputedStyle(d)) && !needsOwnPlace(d)));
      });
      if (inlineOnly && (el.textContent.trim() || pseudoString(el, '::before') || pseudoString(el, '::after') || holdsInlineBox(el))) {
        const boxes = [], t = textItem(el, cs, undefined, boxes);
        const pieces = anchorText(t, boxes.map(b => b.rect), fontOf(cs));
        if (box && !box.bgImg && t && (pieces.length > 1 || pieces[0] !== t)) {
          // A box whose own text must be cut (a KPI tile, a card, with a size bar or an image in
          // its text) or anchored on its first line (a large figure opening a card): the box is
          // drawn bare, and its text goes in pieces over it, with those shapes behind the text as
          // anywhere else.
          emitBox(box, cs, out, el);
          if (before) out.push(...before);
          out.push(...boxes, ...pieces);
        } else if (box && !box.bgImg && t) {
          box.text = t;
          box.pad = [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)];
          box.valign = Math.abs(t.tight.y + t.tight.h / 2 - (rect.y + rect.h / 2)) < 2 ? 'middle' : 'top';
          if (before) out.push(...before);
          out.push(box, ...boxes);
        } else {
          emitBox(box, cs, out, el);
          if (before) out.push(...before);
          if (t) out.push(...boxes, ...pieces);
        }
        if (after) out.push(...after);
        return;
      }
      emitBox(box, cs, out, el);
      if (before) out.push(...before);
      let group = [];
      const flush = () => {
        if (group.some(n => (n.textContent || '').trim() || holdsInlineBox(n))) {
          const boxes = [], t = textItem(el, cs, group, boxes);
          if (t) out.push(...boxes, ...anchorText(t, boxes.map(b => b.rect), fontOf(cs)));
        }
        group = [];
      };
      for (const ch of el.childNodes) {
        if (ch.nodeType === 3) { group.push(ch); continue; }
        if (ch.nodeType !== 1) continue;
        const t = ch.tagName.toLowerCase();
        if (t === 'br') { flush(); continue; }
        if (t !== 'img' && t !== 'svg' && isInline(getComputedStyle(ch)) && !needsOwnPlace(ch) && !ch.querySelector('img,svg')
            && [...ch.querySelectorAll('*')].every(d => !needsOwnPlace(d))) { group.push(ch); continue; }
        flush();
        visit(ch, out);
      }
      flush();
      if (after) out.push(...after);
    };
    for (const ch of sec.children) visit(ch, items);
    slides.push({ w: W, h: H, cls: sec.className, chrome, items });
  }
  return { slides, rasters, blends };
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH, headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--font-render-hinting=none'],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 2 });
    await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'networkidle0', timeout: 180000 });
    // Measure with the font files PowerPoint will get (embedded by finish.py), not the theme's
    // webfont: metrics differ between versions, and a line or pill sized on one font overflows
    // on the other. Later @font-face rules win over the theme's @import for the same face.
    const fontsDir = process.env.OC_PPTX_FONTS;
    if (fontsDir && fs.existsSync(fontsDir)) {
      const faces = [];
      for (const f of fs.readdirSync(fontsDir)) {
        const m = /^(.+)-(Regular|Italic|Bold|BoldItalic)\.ttf$/.exec(f);
        if (!m) continue;
        const family = m[1].replace(/([a-z])([A-Z])/g, '$1 $2');
        const weight = /Bold/.test(m[2]) ? 700 : 400, style = /Italic/.test(m[2]) ? 'italic' : 'normal';
        faces.push(`@font-face{font-family:'${family}';src:url('file://${path.resolve(fontsDir, f)}');font-weight:${weight};font-style:${style}}`);
        faces.push(`@font-face{font-family:'${family}';src:url('file://${path.resolve(fontsDir, f)}');font-weight:${weight === 700 ? '600 1000' : '1 599'};font-style:${style}}`);
      }
      if (faces.length) await page.addStyleTag({ content: faces.join('\n') });
    }
    // Tables are measured with the deck's own figures. Marp's default theme sets tabular figures
    // (`font-variant-numeric: tabular-nums`) on tables, and DrawingML has no OpenType features, so
    // PowerPoint draws them proportional — narrower in Montserrat. Measured proportional, the
    // narrower numbers changed the automatic column widths and any cell could break at other
    // words than the Marp HTML (the Obeya A3 lost a line in row 6; a number split from its unit on
    // slide 4). Measured tabular, columns, breaks and row heights are Marp's, and a line holding
    // figures only ends a little short in the PPTX: the line breaks are fixed, so it never wraps
    // again. What does not follow is a shape placed after a number in a cell (an image, an empty
    // inline box): it sits at Chromium's x, that much right of the text before it. Tags and inline
    // code are highlighted text, so they move with their words.
    // And measure with a face PowerPoint will find. A run's font is the first family of its CSS
    // stack, and a stack that opens on a generic family (monospace, sans-serif, system-ui) or a
    // platform-only one (ui-monospace, -apple-system, Menlo, Consolas, Segoe UI) names no face
    // PowerPoint or LibreOffice can resolve: they fall back to a proportional font of their own,
    // while Chromium measured whatever its own fallback found. Marp's default theme opens its code
    // stack on ui-monospace (code, pre, samp, tt, kbd) and its body stack on -apple-system. Such
    // a stack is replaced, before measuring, by one named face with the same metrics everywhere:
    // Courier New, Arial or Times New Roman (on Linux, fontconfig resolves them to the metric-
    // compatible Liberation fonts; Windows and macOS ship them). A face the page loads itself
    // (@font-face) is left alone.
    // A stack that opens on a named family that is not installed (a deck's own `Lato, "Avenir
    // Next", …, sans-serif` on a machine without them) is the same problem one step earlier:
    // Chromium skips it and measures the next family it has, while the PPTX would name the
    // missing one and each renderer would substitute its own. Such a stack falls back to the first
    // family later in it that every renderer resolves alike: a face the page loads, or a generic
    // or platform-only one, replaced as above. Other named families are skipped, installed or not:
    // one installed where the deck is measured (Trebuchet MS, DejaVu Sans) need not be where the
    // PPTX is opened. A stack with neither is drawn in Times New Roman, Chromium's default face.
    await page.evaluate(() => {
      const KIND = {
        monospace: 'mono', 'ui-monospace': 'mono', 'sfmono-regular': 'mono', 'sf mono': 'mono', menlo: 'mono',
        monaco: 'mono', consolas: 'mono', 'liberation mono': 'mono', 'dejavu sans mono': 'mono', 'cascadia code': 'mono',
        'cascadia mono': 'mono', 'lucida console': 'mono',
        'sans-serif': 'sans', 'system-ui': 'sans', 'ui-sans-serif': 'sans', '-apple-system': 'sans',
        blinkmacsystemfont: 'sans', 'segoe ui': 'sans', 'sf pro text': 'sans', 'sf pro display': 'sans',
        serif: 'serif', 'ui-serif': 'serif',
      };
      const FACE = { mono: '"Courier New", monospace', sans: 'Arial, sans-serif', serif: '"Times New Roman", serif' };
      // Other generic keywords, which PowerPoint has no face for (see safe).
      const GENERIC = new Set(['cursive', 'fantasy', 'emoji', 'math', 'fangsong', 'ui-rounded']);
      const own = new Set([...document.fonts].map(f => f.family.replace(/^["']|["']$/g, '').toLowerCase()));
      // Whether Chromium has a local family: document.fonts.check() is true for any family with no
      // @font-face, so the family is tried in front of two different generic fallbacks instead.
      // A missing family leaves both widths at the fallback's; an installed one cannot match both.
      const probe = document.createElement('canvas').getContext('2d');
      const SAMPLE = 'mmmmmmmmmmlli1WQ@#.,AaBbYyÉé';
      const widthIn = stack => { probe.font = `40px ${stack}`; return probe.measureText(SAMPLE).width; };
      const bare = { monospace: widthIn('monospace'), serif: widthIn('serif') };
      const installed = new Map();
      const drawn = fam => {
        if (!installed.has(fam)) installed.set(fam, ['monospace', 'serif'].some(g =>
          Math.abs(widthIn(`"${fam.replace(/["\\]/g, '')}", ${g}`) - bare[g]) > 0.01));
        return installed.get(fam);
      };
      const quoted = f => KIND[f.toLowerCase()] || GENERIC.has(f.toLowerCase()) ? f : `"${f.replace(/["\\]/g, '')}"`;
      const safe = ff => {
        const fams = (ff || '').split(',').map(s => s.trim().replace(/^["']|["']$/g, '')).filter(Boolean);
        for (let i = 0; i < fams.length; i++) {
          const f = fams[i].toLowerCase();
          if (KIND[f] && !own.has(f)) return FACE[KIND[f]];
          // cursive, fantasy, emoji…: no face PowerPoint finds by that name. One Chromium resolves
          // is measured and drawn in Times New Roman; one it does not resolve is skipped, as
          // Chromium skips it.
          if (GENERIC.has(f) && !own.has(f)) {
            if (['monospace', 'serif'].some(g => Math.abs(widthIn(`${f}, ${g}`) - bare[g]) > 0.01)) return FACE.serif;
            continue;
          }
          if (!i && (own.has(f) || drawn(fams[i]))) return null;
          if (i && own.has(f)) return fams.slice(i).map(quoted).join(', ');
        }
        return fams.length ? FACE.serif : null;
      };
      // Document order: a stack set on a parent is inherited, so only elements with a stack of
      // their own are changed after it. Pseudo-elements get a rule of their own.
      const rules = [];
      let n = 0;
      for (const el of document.querySelectorAll('section, section *')) {
        const f = safe(getComputedStyle(el).fontFamily);
        if (f && el.style) el.style.setProperty('font-family', f, 'important');
        for (const w of ['::before', '::after']) {
          const p = getComputedStyle(el, w), pf = p.content && p.content !== 'none' && p.content !== 'normal' && safe(p.fontFamily);
          if (!pf) continue;
          if (!el.dataset.p2f) el.dataset.p2f = String(++n);
          rules.push(`[data-p2f="${el.dataset.p2f}"]${w}{font-family:${pf} !important}`);
        }
      }
      if (rules.length) { const s = document.createElement('style'); s.textContent = rules.join('\n'); document.head.appendChild(s); }
    });
    if (!KEEP_CENTRING) await page.evaluate(() => {
      for (const s of document.querySelectorAll('section:not(.lead)')) {
        const first = [...s.children].find(c => !/^(header|footer)$/i.test(c.tagName));
        if (first && /^h[12]$/i.test(first.tagName)) {
          s.style.setProperty('align-content', 'start', 'important');
          s.style.setProperty('justify-content', 'flex-start', 'important');
        }
      }
    });
    await page.evaluate(async () => { await document.fonts.ready; });
    const model = await page.evaluate(extract);

    // Rasters: an element screenshot, or a replica on a transparent page (keeps alpha). The
    // replica page is a local file, so file:// images load; each image is awaited explicitly.
    // Element screenshots come first, while the deck is still the front tab: once the replica
    // page is opened, the deck is a background tab, which headless Chromium stops painting, and
    // a screenshot of it waits for a frame (and scrollIntoViewIfNeeded for an IntersectionObserver
    // callback) that never comes — the render then hangs until the protocol times out.
    await page.bringToFront();
    for (const r of model.rasters.filter(x => x.kind === 'element')) {
      r.file = path.join(outDir, `raster-${r.id}.png`);
      const el = await page.$(r.selector);
      await el.screenshot({ path: r.file });
    }
    const blank = await browser.newPage();
    await blank.setViewport({ width: 1600, height: 1200, deviceScaleFactor: 2 });
    const blankFile = path.join(outDir, 'blank.html');
    fs.writeFileSync(blankFile, '<!doctype html><html><body style="margin:0;background:transparent"></body></html>');
    await blank.goto('file://' + path.resolve(blankFile), { waitUntil: 'load' });
    for (const r of model.rasters.filter(x => x.kind !== 'element')) {
      r.file = path.join(outDir, `raster-${r.id}.png`);
      const w = Math.max(1, Math.round(r.w)), h = Math.max(1, Math.round(r.h));
      const fx = r.css ? `filter:${r.css.filter || 'none'};opacity:${r.css.opacity || 1};` : '';
      const inner = r.kind === 'img'
        ? `<img src="${r.src}" style="display:block;width:${w}px;height:${h}px;object-fit:${r.fit || 'fill'};${fx}">`
        : `<div style="width:${w}px;height:${h}px;${fx}background-image:${r.css.backgroundImage.replace(/"/g, "'")};background-size:${r.css.backgroundSize};background-position:${r.css.backgroundPosition};background-repeat:${r.css.backgroundRepeat}"></div>`;
      const url = r.kind === 'bg' ? ((/url\(["']?(.*?)["']?\)/.exec(r.css.backgroundImage) || [])[1] || null) : null;
      await blank.evaluate(async (html, u) => {
        document.body.innerHTML = html;
        const imgs = [...document.images];
        if (u) { const im = new Image(); im.src = u; imgs.push(im); }
        await Promise.all(imgs.map(i => i.decode().catch(() => {})));
      }, inner, url);
      const el = await blank.$('body > *');
      await el.screenshot({ path: r.file, omitBackground: true });
    }
    // Highlights over a background image (highlightOf: `blend`): the image's mean colour under the
    // box, read from its raster (a data URL, so the canvas is not tainted), composited over the
    // colours below the image (`base`) as far as the raster is transparent, then the box's
    // translucent layers over that. Canvas pixels are not premultiplied: each is weighted by its
    // alpha before averaging, so a half-transparent pixel counts for half its colour.
    if (model.blends.length) {
      const done = new Map();
      for (const b of model.blends) {
        const r = model.rasters.find(x => x.el === b.el && x.file && fs.existsSync(x.file));
        if (!r) continue;
        const src = 'data:image/png;base64,' + fs.readFileSync(r.file).toString('base64');
        done.set(b.id, await blank.evaluate(async (src, b) => {
          const im = new Image(); im.src = src; await im.decode();
          const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
          const g = c.getContext('2d'); g.drawImage(im, 0, 0);
          const sx = im.naturalWidth / b.rect.w, sy = im.naturalHeight / b.rect.h;
          const x0 = Math.max(0, Math.floor((b.box.x - b.rect.x) * sx)), y0 = Math.max(0, Math.floor((b.box.y - b.rect.y) * sy));
          const x1 = Math.min(c.width, Math.ceil((b.box.x + b.box.w - b.rect.x) * sx)), y1 = Math.min(c.height, Math.ceil((b.box.y + b.box.h - b.rect.y) * sy));
          if (x1 <= x0 || y1 <= y0) return null;
          const d = g.getImageData(x0, y0, x1 - x0, y1 - y0).data, sum = [0, 0, 0, 0];
          for (let i = 0; i < d.length; i += 4) {
            for (let k = 0; k < 3; k++) sum[k] += d[i + k] * d[i + 3] / 255;
            sum[3] += d[i + 3];
          }
          const n = d.length / 4, a = sum[3] / n / 255;
          const base = [0, 2, 4].map(i => parseInt(b.base.slice(i, i + 2), 16));
          let rgb = [0, 1, 2].map(k => Math.min(255, Math.max(0, sum[k] / n + base[k] * (1 - a))));
          for (const l of [...b.layers].reverse()) {
            const v = [0, 2, 4].map(i => parseInt(l.hex.slice(i, i + 2), 16));
            rgb = rgb.map((x, i) => x * (1 - l.alpha) + v[i] * l.alpha);
          }
          return rgb.map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
        }, src, b));
      }
      const fix = o => {
        if (Array.isArray(o)) { o.forEach(fix); return; }
        if (!o || typeof o !== 'object') return;
        if (o.hl && o.hl.blend) o.hl = { hex: done.get(o.hl.blend) || o.hl.hex };
        for (const k in o) fix(o[k]);
      };
      fix(model.slides);
    }
    fs.writeFileSync(path.join(outDir, 'model.json'), JSON.stringify(model));
    console.log(`measured ${model.slides.length} slides, ${model.rasters.length} rasters`);
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
