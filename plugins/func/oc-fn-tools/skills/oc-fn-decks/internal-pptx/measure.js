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
 *     words instead of re-wrapping with its own metrics;
 *   - pseudo-elements: string content in running text; block or absolutely positioned ones
 *     (a logo, a title pill) and inline-block ones (a size bar after a label) as shapes;
 *   - inline boxes — inline-blocks with a fill, a border or a side margin and one line of plain
 *     text, or none (a source tag, a pill, a size bar), and plain inline elements with a fill or
 *     a border (an inline `code`, a <mark>), on one line or several: their text stays in the
 *     line, highlighted in the box's fill and padded to the box's width, with no shape; only an
 *     empty one (a size bar) becomes a shape;
 *   - images in running text (a list item, a table cell), placed at their own position, their
 *     width kept in the line;
 *   - other inline-blocks that carry a box, a margin or a pseudo shape, placed at their own
 *     position, the text after them indented to where its first line starts;
 *   - where each line starts, so that text with shapes drawn over it — a list, a paragraph, a
 *     box's own text — can be anchored item by item, or cut, at Chromium's y (anchorText);
 *   - inset box-shadows with no blur, drawn as the stripes they look like;
 *   - CSS filter and opacity on background images, applied when the image is redrawn.
 *
 * It measures with the TTFs in $OC_PPTX_FONTS — the files finish.py embeds — instead of the
 * theme's webfont, and with proportional figures in tables (PowerPoint has no tabular ones), so
 * the widths it records are the widths PowerPoint will draw. A CSS stack that opens on a generic
 * or platform-only family (monospace, ui-monospace, -apple-system…) is replaced by Courier New,
 * Arial or Times New Roman before measuring, for the same reason.
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
    sup: cs.verticalAlign === 'super', sub: cs.verticalAlign === 'sub',
  });
  // Glyphs of one family and size sit at the same height on a line, whatever their weight: the
  // key lineTops() compares lines by.
  const fontKey = f => `${f.face}|${f.size}`;
  const transform = (t, cs) => cs.textTransform === 'uppercase' ? t.toLocaleUpperCase('fr')
    : cs.textTransform === 'lowercase' ? t.toLocaleLowerCase('fr')
    : cs.textTransform === 'capitalize' ? t.replace(/(^|\s)(\S)/g, (m, s, c) => s + c.toLocaleUpperCase('fr')) : t;
  const isInline = cs => /^inline/.test(cs.display) || cs.display === 'contents';
  const align = a => ({ start: 'left', end: 'right', justify: 'justify', '-webkit-left': 'left', '-webkit-center': 'center', '-webkit-right': 'right' }[a] || a);
  const hasContent = cs => cs.content && cs.content !== 'none' && cs.content !== 'normal' && cs.display !== 'none';
  const SVG_OK = new Set(['svg', 'g', 'line', 'rect', 'circle', 'ellipse', 'polyline', 'polygon', 'text', 'tspan', 'title', 'desc']);

  let rasterId = 0;
  const rasters = [];
  const slides = [];

  const contents = [...document.querySelectorAll('section')].filter(s =>
    !s.parentElement.closest('section') && (!s.dataset.marpitAdvancedBackground || s.dataset.marpitAdvancedBackground === 'content'));

  for (const sec of contents) {
    const S = sec.getBoundingClientRect();
    const W = sec.offsetWidth, H = sec.offsetHeight, k = S.width / W;
    const rel = r => ({ x: (r.left - S.left) / k, y: (r.top - S.top) / k, w: r.width / k, h: r.height / k });
    const secCs = getComputedStyle(sec);
    const secBg = col(secCs.backgroundColor);

    const raster = (spec, rect) => { spec.id = ++rasterId; rasters.push(spec); return { type: 'image', rect, raster: spec.id }; };
    const bgRaster = (cs, rect) => raster({ kind: 'bg', w: rect.w, h: rect.h, css: {
      backgroundImage: cs.backgroundImage, backgroundSize: cs.backgroundSize, backgroundPosition: cs.backgroundPosition,
      backgroundRepeat: cs.backgroundRepeat, filter: cs.filter, opacity: cs.opacity } }, rect);
    const contentRect = (el, cs) => {
      const r = rel(el.getBoundingClientRect());
      const l = px(cs.borderLeftWidth) + px(cs.paddingLeft), t = px(cs.borderTopWidth) + px(cs.paddingTop);
      return { x: r.x + l, y: r.y + t, w: r.w - l - px(cs.borderRightWidth) - px(cs.paddingRight),
               h: r.h - t - px(cs.borderBottomWidth) - px(cs.paddingBottom) };
    };
    // Where a glyph of font f sits in a plain line of that font at line-height lh: its top below
    // the line's top (`off`) and its height (`h`), slide px. Measured on a probe line, because
    // Chromium rounds the ascent, the descent and the half-leading, so it is not computed.
    const plain = new Map();
    const plainLine = (f, lh) => {
      const key = [f.face, f.size, f.bold, f.italic, lh].join('|');
      if (!plain.has(key)) {
        const d = document.createElement('div');
        d.style.cssText = `position:absolute;left:0;top:0;margin:0;padding:0;border:0;white-space:nowrap;`
          + `font-family:"${f.face}";font-size:${f.size}px;font-weight:${f.bold ? 700 : 400};`
          + `font-style:${f.italic ? 'italic' : 'normal'};line-height:${lh}px`;
        d.textContent = 'x';
        sec.appendChild(d);
        const r = document.createRange();
        r.selectNodeContents(d);
        const g = r.getClientRects()[0], b = d.getBoundingClientRect();
        plain.set(key, g ? { off: (g.top - b.top) / k, h: g.height / k } : { off: 0, h: 0 });
        d.remove();
      }
      return plain.get(key);
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
    const emitBox = (b, cs, out) => {
      if (!b) return;
      if (b.bgImg) out.push(bgRaster(cs, b.rect));
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
      return t ? { t: transform(t, cs), ...fontOf(cs), free: /\s/.test(t) || undefined } : null;
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
    // a highlighted span: a fill or a border. On one line it is an inline box like the others;
    // broken across lines, its text is highlighted the same way, line after line, its padding at
    // its two ends (runsOf: `sliced`).
    const flatBox = (el, cs) => cs.display === 'inline' && cs.backgroundImage === 'none' && !!boxOf(cs, rel(el.getBoundingClientRect()));
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
      return { ...g, t: '\u00a0', underline: false, strike: false, spacing: w - nb, pad: true, link: null };
    };
    // Plain spacing of w px, or none when it is under a third of a pixel (or negative: a box's
    // highlighted padding came out wider than its CSS padding plus border, see hlPad).
    const gapRuns = (f, w) => w >= 0.3 ? [padOf(f, w)] : [];
    // The highlight an inline box's text takes: its CSS background colour, composited over the
    // backgrounds behind it when translucent (a lead slide's inline code is white at 15 % over a
    // dark ground), since a highlight has no transparency. Null when the box has no fill \u2014 a box
    // drawn by its border alone (a dashed tag) is plain text in its own colour.
    const highlightOf = (el, cs) => {
      const c = col(cs.backgroundColor);
      if (!c || cs.backgroundImage !== 'none') return null;
      const layers = [c];
      for (let p = el.parentElement; p && c.alpha < 1; p = p.parentElement) {
        const q = col(getComputedStyle(p).backgroundColor);
        if (q) { layers.push(q); if (q.alpha >= 1) break; }
        if (p === sec) break;
      }
      let rgb = [255, 255, 255];
      for (const l of layers.reverse()) {
        const v = [0, 2, 4].map(i => parseInt(l.hex.slice(i, i + 2), 16));
        rgb = rgb.map((x, i) => x * (1 - l.alpha) + v[i] * l.alpha);
      }
      return { hex: rgb.map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase() };
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
    // Advance of a list marker as PowerPoint draws it (finish.py): a disc in the item's font at
    // 125 %, a circle or a square in Arial at 125 % (the brand fonts lack them, and a renderer's
    // fallback can be an emoji font twice as wide), a number with its period in the item's font.
    const markerWidth = (bu, f) => {
      const disc = bu.char === '\u2022', size = bu.type === 'number' ? f.size : f.size * 1.25;
      nbspCtx.font = `${f.italic ? 'italic ' : ''}${f.bold ? 700 : 400} ${size}px "${bu.type === 'number' || disc ? f.face : 'Arial'}"`;
      return nbspCtx.measureText(bu.type === 'number' ? `${bu.start}.` : bu.char).width;
    };

    // ---- text runs, with Chromium's line breaks
    // `boxes`, when given, collects the shapes met on the way: empty inline boxes, images.
    // Each line break also records where Chromium put the glyphs of the line it opens (`g`: for
    // each font met on that line, fontKey → [top, height] of its first glyph rect, slide px), and
    // the returned array's `head` does so for the first line: lineTops() turns them into the top
    // of each line box, so text can be anchored line by line (see anchorText).
    const runsOf = (nodes, skipLists, lhPx, boxes) => {
      const runs = [], head = {};
      let prevTop = null;
      const tol = (lhPx || 16) * k * 0.5;
      const mark = (r, f) => {
        if (!r || f.sup || f.sub) return;
        let line = head;
        for (let i = runs.length - 1; i >= 0; i--) if (runs[i].br) { line = runs[i].g || (runs[i].g = {}); break; }
        const key = fontKey(f);
        if (!line[key]) line[key] = [(r.top - S.top) / k, r.height / k, f.bold, f.italic];
      };
      const padRun = padOf;
      // An element with no glyphs of its own on the line — an empty inline box, an image — gives
      // no glyph top to compare with the words', so the top the line's text has is inferred from
      // its box. A box on the baseline (the default, or raised by a length) ends its margin box
      // there, one ascent (≈ 0.95 em of the parent's font) below the text's top; any other
      // alignment is read from the box's middle. A new line opens before it when it is lower.
      const emptyAt = (el, cs) => {
        const bb = el.getBoundingClientRect(), em = px(getComputedStyle(el.parentElement).fontSize) * k;
        const va = cs.verticalAlign, raise = /px$/.test(va) ? px(va) : va === 'baseline' ? 0 : null;
        const top = raise !== null ? bb.bottom + (px(cs.marginBottom) + raise) * k - 0.95 * em
          : (bb.top + bb.bottom) / 2 - 0.6 * em;
        if (prevTop !== null && top > prevTop + tol) runs.push({ br: true, soft: true });
        prevTop = top;
      };
      // An image in running text (a list item, a table cell, a title): a pad run as wide as its
      // margin box keeps its place in the line, and the image is drawn at its own position, with
      // the empty inline boxes (behind the text, or over a table).
      const imageRuns = (el, cs) => {
        const r = rel(el.getBoundingClientRect());
        if (!r.w || !r.h) return;
        emptyAt(el, cs);
        runs.push(padRun(fontOf(getComputedStyle(el.parentElement)), r.w + px(cs.marginLeft) + px(cs.marginRight)));
        if (boxes) boxes.push(raster({ kind: 'img', src: el.currentSrc || el.src, w: r.w, h: r.h, fit: cs.objectFit,
          css: { filter: cs.filter, opacity: cs.opacity } }, r));
      };
      // A box that holds text is highlighted text: its text keeps its own colour, weight and size,
      // highlighted in the box's fill, between highlighted no-break spaces that stand for its
      // padding (hlPad), one run with the label; its border and margins are plain spacing, wide
      // enough that the text after it starts where Chromium put it. No border, no rounded corners:
      // a highlight draws neither. A box with no fill is plain text in its colour.
      const labelRuns = (inner, cs, link, hl, room) => {
        // The box's own text: not the pads or the text of an inline box nested in it, which keeps
        // its own highlight.
        const own = x => x.t && !x.pad && !x.hl;
        const texts = inner.filter(own), a0 = texts[0], z = texts[texts.length - 1];
        if (!a0) return { label: inner, left: px(cs.paddingLeft), right: px(cs.paddingRight) };
        const L = hl ? hlPad(a0, px(cs.paddingLeft), room[0], 'left') : { t: '', w: 0 };
        const Rr = hl ? hlPad(z, px(cs.paddingRight), room[1], 'right') : { t: '', w: 0 };
        const label = inner.map(x => own(x) ? { ...x, link: x.link || link, hl: hl || undefined } : x);
        // Their own runs, in the label's font: the merge at the end of runsOf folds them into it.
        if (L.t) label.unshift({ ...a0, t: L.t, link: a0.link || link, hl, free: undefined });
        if (Rr.t) label.push({ ...z, t: Rr.t, link: z.link || link, hl, free: undefined });
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
          // text: its line is then the line of its border box.
          const top = (rs[0] || el.getBoundingClientRect()).top;
          if (prevTop !== null && top > prevTop + tol) runs.push({ br: true, soft: true });
          prevTop = top;
          const { label, left, right } = labelRuns(inner, cs, link, highlightOf(el, cs), [outL, outR]);
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
            const f = fontOf(cs), raw = ch.nodeValue;
            if (/^pre/.test(cs.whiteSpace)) {
              // Only the newlines are recorded: pre-wrap and pre-line text can wrap besides (free).
              // pre and pre-wrap keep their spaces, a code block's indentation first (`keep`).
              const free = cs.whiteSpace !== 'pre' || undefined, keep = cs.whiteSpace !== 'pre-line' || undefined;
              raw.split('\n').forEach((line, i) => { if (i) runs.push({ br: true }); if (line) runs.push({ t: transform(line, cs), ...f, link, free, keep }); });
              continue;
            }
            const re = /(\s+)|(\S+)/g, range = document.createRange();
            let m;
            while ((m = re.exec(raw))) {
              if (m[1]) { runs.push({ t: ' ', ...f, link }); continue; }
              range.setStart(ch, m.index); range.setEnd(ch, m.index + m[2].length);
              const rs = range.getClientRects();
              let word = m[2], free;
              if (rs.length) {
                if (prevTop !== null && rs[0].top > prevTop + tol) runs.push({ br: true, soft: true });
                mark(rs[0], f);
                if (rs[rs.length - 1].top > rs[0].top + tol) {
                  // Broken inside the word, as often as Chromium broke it (a long URL or path can
                  // take several lines): cut it before each character that starts a later line.
                  let from = 0, top = rs[0].top, cuts = 0;
                  for (let i = 1; i < word.length; i++) {
                    range.setStart(ch, m.index + i); range.setEnd(ch, m.index + i + 1);
                    const c = range.getClientRects()[0];
                    if (!c || c.top <= top + tol) continue;
                    runs.push({ t: transform(word.slice(from, i), cs), ...f, link }, { br: true, soft: true });
                    mark(c, f);
                    from = i; top = c.top; cuts++;
                  }
                  word = word.slice(from);
                  // Belt and braces: should a line of the word go unrecorded (no glyph rect where
                  // it starts), its last piece keeps wrapping on its own (`free`, see build.js).
                  let lines = 1;
                  for (let i = 1, t0 = rs[0].top; i < rs.length; i++) if (rs[i].top > t0 + tol) { lines++; t0 = rs[i].top; }
                  if (lines > cuts + 1) free = true;
                }
                prevTop = rs[rs.length - 1].top;
              }
              runs.push({ t: transform(word, cs), ...f, link, free });
            }
          } else if (ch.nodeType === 1) {
            const tag = ch.tagName.toLowerCase();
            if (skipLists && (tag === 'ul' || tag === 'ol')) continue;
            const cs = getComputedStyle(ch);
            if (cs.display === 'none') continue;
            if (tag === 'br') { runs.push({ br: true }); prevTop = null; continue; }
            if (tag === 'img') { imageRuns(ch, cs); continue; }
            if (inlineBox(ch)) { inlineBoxRuns(ch, cs); continue; }
            // A plain inline element with a box broken across lines (flatBox): highlighted text
            // like an inline box on one line (labelRuns), every line of it — its left padding,
            // border and margin open it, on the line its first glyph is on, and the right ones
            // close it.
            const sliced = flatBox(ch, cs), sf = sliced && fontOf(cs);
            if (sliced) {
              const w = document.createTreeWalker(ch, NodeFilter.SHOW_TEXT), g = document.createRange();
              for (let t = w.nextNode(); t; t = w.nextNode()) {
                const i = t.nodeValue.search(/\S/);
                if (i < 0) continue;
                g.setStart(t, i); g.setEnd(t, i + 1);
                const c = g.getClientRects()[0];
                if (c) { if (prevTop !== null && c.top > prevTop + tol) runs.push({ br: true, soft: true }); prevTop = c.top; }
                break;
              }
            }
            const start = runs.length;
            const b = pseudoString(ch, '::before'); if (b) runs.push(b);
            walk(ch.childNodes);
            const a = pseudoString(ch, '::after'); if (a) runs.push(a);
            if (sliced) {
              const outL = px(cs.marginLeft) + px(cs.borderLeftWidth), outR = px(cs.marginRight) + px(cs.borderRightWidth);
              const { label, left, right } = labelRuns(runs.splice(start), cs, null, highlightOf(ch, cs), [outL, outR]);
              runs.push(...gapRuns(sf, outL + left), ...label, ...gapRuns(sf, outR + right));
            }
            if (!isInline(cs) && ch.nextSibling) { runs.push({ br: true }); prevTop = null; }
          }
        }
      };
      walk(nodes);
      // collapse spaces across run boundaries; trim at paragraph and line edges; merge alike runs
      const out = [];
      let atStart = true;
      for (const r of runs) {
        if (r.br) {
          const last = out[out.length - 1];
          if (last && !last.br) { last.t = last.t.replace(/ +$/, ''); out.push(r.g ? { br: true, g: r.g } : { br: true }); }
          else if (last && last.br && r.g) last.g = r.g;
          else if (!last && r.g) for (const q in r.g) if (!head[q]) head[q] = r.g[q];   // a leading break is dropped
          atStart = true; continue;
        }
        let t = r.t;
        if (!r.keep && (atStart || (out.length && / $/.test(out[out.length - 1].t || '')))) t = t.replace(/^ +/, '');
        if (!t) continue;
        const last = out[out.length - 1];
        const same = last && !last.br && !last.pad && !r.pad && ['face', 'size', 'bold', 'italic', 'spacing', 'underline', 'strike', 'sup', 'sub', 'link']
          .every(key => last[key] === r[key]) && (last.color && last.color.hex) === (r.color && r.color.hex)
          && (last.hl && last.hl.hex) === (r.hl && r.hl.hex);
        if (same) { last.t += t; if (r.free) last.free = true; } else out.push({ ...r, t });
        atStart = false;
      }
      while (out.length && out[out.length - 1].br) out.pop();
      if (out.length) out[out.length - 1].t = out[out.length - 1].t.replace(/ +$/, '');
      const res = out.filter(r => r.br || r.t);
      res.head = head;
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
    // before when there are none (a line that opens on an inline box and holds nothing else), or
    // when a glyph would be less than half a line below it. A line set entirely in a larger font
    // (no glyph of the block's font) is a plain line of that font instead: it starts where such a
    // line would for its glyphs to land on Chromium's, and is lifted as one (`foreign`: line →
    // the height of a glyph of that font). The result carries `uneven` when the pitch is not
    // even — a taller line, a paragraph margin in a loose list item, a first line anchored on its
    // glyphs, a line in a larger font — and `nat`, the height of a glyph of the block's font,
    // which a piece of such text is lifted by (build.js leadShift) instead of the whole text's.
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
      if (!t || !rects.length || t.lines < 2) return [t];
      const tops = lineTops(t.runs, t.rect.y, t.lh, font, t.glyphs);
      if (tops.length !== t.lines) return [t];
      if (t.align === 'justify' || t.runs.some(r => r.free)) {
        return [tops[0] !== t.rect.y && !tops.foreign.has(0) ? { ...t, rect: { ...t.rect, y: tops[0] }, nat: tops.nat } : t];
      }
      const cuts = cutsOf(tops, rects, t.lh);
      if (cuts.length < 2) return [t];
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
    const scaleOf = el => {
      const host = el.closest('[data-auto-scaling]');
      const as = host && host.shadowRoot && host.shadowRoot.querySelector('marp-auto-scaling');
      const svg = as && as.shadowRoot && as.shadowRoot.querySelector('svg');
      const vb = svg && svg.viewBox && svg.viewBox.baseVal;
      const s = vb && vb.width ? svg.getBoundingClientRect().width / k / vb.width : 1;
      return s > 0 && Math.abs(s - 1) > 0.002 ? s : 1;
    };
    const textItem = (el, cs, nodes, boxes) => {
      let lh = lineHeight(cs);
      const runs = runsOf(nodes || el.childNodes, false, lh, boxes);
      const hasBox = runs.some(r => r.pad || r.hl);      // inline boxes (pads, highlights), images
      const b = pseudoString(el, '::before'), a = pseudoString(el, '::after');
      if (b) runs.unshift(b);
      if (a) runs.push(a);
      const sc = scaleOf(el);
      if (sc !== 1) {
        for (const r of runs) if (r.size) { r.size *= sc; if (r.spacing) r.spacing *= sc; }
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
      // A run of text that starts mid-line — after something placed on its own, such as an
      // inline-block holding an image — and wraps: its box starts at the left edge of its later
      // lines, so its first line is indented by a pad run to where Chromium started it, instead
      // of being drawn over whatever comes before it on that line.
      if (nodes && (al === 'left' || al === 'justify')) {
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
          for (const c of n.childNodes) { const x = startOf(c); if (x !== null) return x; }
          return null;
        };
        for (const n of nodes) { first = startOf(n); if (first !== null) break; }
        const off = first !== null ? (first - S.left) / k - rect.x : 0;
        // A leading inline box's left margin lies outside the range's rect: widen the rect to it.
        if (off < -0.5) rect = { ...rect, x: rect.x + off, w: rect.w - off };
        if (off > 1 && f) runs.unshift(padOf(f, off));
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
        let top = Infinity, natH = 0;
        for (const n of nodes || [el]) {
          const texts = [];
          if (n.nodeType === 3) texts.push(n);
          else if (n.nodeType === 1) { const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT); while (w.nextNode()) texts.push(w.currentNode); }
          for (const t of texts) {
            if (!/\S/.test(t.nodeValue) || insideBox(t)) continue;
            const g = document.createRange();
            g.selectNodeContents(t);
            for (const r of g.getClientRects()) if (r.width) { top = Math.min(top, r.top); natH = Math.max(natH, r.height); }
          }
        }
        // Only when that text is on the first line: a line can hold nothing but an inline box.
        const y = (top - S.top) / k;
        if (natH && y - tight.y < lh * 0.75) { top0 = y; nat = natH / k; fromGlyphs = true; }
      }
      // A rect taken from the glyph box starts half a leading below its line box: move it up,
      // so every text rect starts where CSS starts the line.
      if (nodes) rect = { ...rect, y: top0 - (lh - nat) / 2, h: lines * lh };
      else if (fromGlyphs) rect = { ...rect, y: top0 - (lh - nat) / 2 };
      return { type: 'text', rect, tight, runs, align: al, lh, lines, nat, valign: 'top', dir: cs.direction,
        glyphs: !!nodes || fromGlyphs || undefined };
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
        const loose = prevLoose || blockMargin(li.firstElementChild, 'marginTop');
        prevLoose = blockMargin(li.lastElementChild, 'marginBottom');
        // Sibling items' vertical margins collapse in CSS (the gap is the larger of the two);
        // PowerPoint adds space-after and space-before, so the second keeps only the excess.
        // When something else comes in between (see gapAfter), the gap is measured instead.
        let before = prevAfter === null ? px(cs.marginTop) : Math.max(0, px(cs.marginTop) - prevAfter);
        prevAfter = px(cs.marginBottom);
        const type = cs.listStyleType, font = fontOf(cs);
        const bullet = type === 'none' ? null : ordered ? { type: 'number', start: n } :
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
        const y = blockTop(conts ? parts[0].nodes : [...li.childNodes]) ?? c.y;
        // An item that opens directly on its nested list has no line of its own: Chromium draws
        // its marker on the first nested item's line (`markerOnly`, placed by visit).
        const markerOnly = !!(bullet && parts[0].sub && !texty(parts[0].nodes)) || undefined;
        // Right after a nested list (prevOwn is not the last paragraph), the gap is measured; so
        // it is between loose siblings, where the paragraphs' margins make it.
        if (paras.length && (level > 0 && prevOwn === null || prevOwn !== null && (prevOwn !== paras.length - 1 || loose))) before = gapAfter(paras[paras.length - 1], y);
        paras.push({ runs, level, lh, bullet, font, mw: bullet ? markerWidth(bullet, font) : 0,
          indent: px(lcs.paddingLeft), x: c.x, w: c.w, after: conts || parts[0].sub ? 0 : px(cs.marginBottom), before,
          align: align(cs.textAlign), y, tops: lineTops(runs, y, lh, font), markerOnly });
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
              after: 0, before: gapAfter(paras[paras.length - 1], top), align: align(cs.textAlign), y: top, tops: lineTops(rs, top, lh, font) });
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
        const lh = lineHeight(cs), font = fontOf(cs);
        const runs = runsOf(td.childNodes, false, lh, mine);
        for (const b of mine) b.cell = { align: al, pad: [pl, pr] };
        boxes.push(...mine);
        // A cell takes exact line spacing at its own line-height (build.js), so its lines sit as
        // far apart as in Marp — unless a run in it is set in a font more than 10 % larger than
        // the cell's: Chromium makes that line taller, by about the same 10 % of a line-height or
        // more, and at the cell's exact pitch it would be drawn over the line above. Such a cell
        // keeps the renderer's single spacing, which grows the line for its font. Other uneven
        // pitches are left to exact spacing: an inline code makes its line 1.5 px taller (edge
        // deck e27), not worth lines 16 % closer together, and a gap such as a paragraph margin
        // is lost either way, without any overlap. A cell with an image is exact in any case, since
        // the image is drawn at Chromium's y.
        const exact = mine.some(b => b.type === 'image') || !runs.some(r => r.t && r.size > font.size * 1.1);
        return { runs, lh, exact: exact || undefined, align: align(cs.textAlign),
          valign: { middle: 'middle', bottom: 'bottom' }[cs.verticalAlign] || 'top',
          fill: col(cs.backgroundColor) || col(getComputedStyle(tr).backgroundColor),
          pad: [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)],
          border: ['Top', 'Right', 'Bottom', 'Left'].map(side), colspan: td.colSpan, rowspan: td.rowSpan,
          w: rel(td.getBoundingClientRect()).w };
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
      if (!flat) { svg.dataset.p2x = String(rasterId + 1); return [raster({ kind: 'element', selector: `[data-p2x="${rasterId + 1}"]` }, r)]; }
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
    if (secCs.backgroundImage !== 'none') chrome.decor.push(bgRaster(secCs, { x: 0, y: 0, w: W, h: H }));
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
        const boxes = [], t = textItem(el, cs, undefined, boxes), deco = [];
        emitBox(boxOf(cs, rect), cs, deco);
        chrome.title = { text: t, deco };
        if (before) out.push(...before);
        out.push(...boxes);
        if (after) out.push(...after);
        return;
      }
      if (tag === 'img') { out.push(raster({ kind: 'img', src: el.currentSrc || el.src, w: rect.w, h: rect.h, fit: cs.objectFit, css: { filter: cs.filter, opacity: cs.opacity } }, rect)); return; }
      if (tag === 'svg') { out.push(...svgItems(el)); return; }
      const box = boxOf(cs, rect);
      if (tag === 'table') {
        emitBox(box, cs, out); if (before) out.push(...before);
        const boxes = [];
        out.push(tableItem(el, boxes), ...boxes); inlineDecor(el, out);
        if (after) out.push(...after); return;
      }
      if (tag === 'ul' || tag === 'ol') {
        emitBox(box, cs, out);
        // A right-to-left list is drawn as one text box, left to right, with no empty inline box or
        // image over it: drawn one box per item, they would sit at Chromium's x, far from where
        // their place in the text lands.
        const rtl = cs.direction === 'rtl';
        const boxes = [], paras = listItem(el, 0, [], boxes), decor = [];
        inlineDecor(el, decor);
        if (!rtl) out.push(...boxes);
        // A list with overlays is drawn one text box per item, each at the y Chromium gave it
        // (anchorText); an item is cut further where cutsOf says. Without overlays it stays whole.
        const rects = [...(rtl ? [] : boxes), ...decor].map(b => b.rect).filter(Boolean);
        const split = !rtl && rects.length > 0;
        for (const p of paras) {
          const mine = rects.filter(r => { const cy = r.y + r.h / 2; return cy >= p.tops[0] && cy < p.tops[p.tops.length - 1] + p.lh; });
          const cuts = split && p.tops.length >= 2 && p.align !== 'justify' && !p.runs.some(r => r.free) ? cutsOf(p.tops, mine, p.lh) : [0];
          // A cut at a line in a larger font carries that font's glyph height (`nat`, see lineTops).
          if (split && (cuts.length > 1 || p.tops.foreign.has(0))) p.cuts = cuts.map(i => ({ line: i, y: p.tops[i], nat: p.tops.foreign.get(i) }));
          // Uneven text is anchored on its glyphs (lineTops), and lifted as plain lines (build.js).
          if (split) { p.y = p.tops[0]; if (p.tops.uneven) p.uneven = true; } else delete p.y;
          delete p.tops;
        }
        // An item that opens on its nested list (markerOnly): drawn one box per item, its marker
        // goes on the first nested item's line, as in Chromium; in a list kept whole, which cannot
        // put two paragraphs on one line, it is left out (its marker with it) and its space before
        // goes to that nested item.
        for (let i = paras.length - 2; i >= 0; i--) {
          const p = paras[i];
          if (!p.markerOnly) continue;
          if (split) p.y = paras[i + 1].y;
          else { paras[i + 1].before = Math.max(paras[i + 1].before, p.before); paras.splice(i, 1); }
        }
        if (paras.some(p => p.runs.length)) out.push({ type: 'list', rect, paras, split: split || undefined });
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
        if (box && !box.bgImg && t && pieces.length > 1) {
          // A box whose own text must be cut (a KPI tile, a card, with a size bar or an image in
          // its text): the box is drawn bare, and its text goes in pieces over it, with those
          // shapes behind the text as anywhere else.
          emitBox(box, cs, out);
          if (before) out.push(...before);
          out.push(...boxes, ...pieces);
        } else if (box && !box.bgImg && t) {
          box.text = t;
          box.pad = [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)];
          box.valign = Math.abs(t.tight.y + t.tight.h / 2 - (rect.y + rect.h / 2)) < 2 ? 'middle' : 'top';
          if (before) out.push(...before);
          out.push(box, ...boxes);
        } else {
          emitBox(box, cs, out);
          if (before) out.push(...before);
          if (t) out.push(...boxes, ...pieces);
        }
        if (after) out.push(...after);
        return;
      }
      emitBox(box, cs, out);
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
  return { slides, rasters };
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
    // Measure tables with the figures PowerPoint will draw, too. DrawingML has no OpenType
    // features, so tabular figures (Marp's default theme sets `font-variant: tabular-nums` on
    // tables) come out proportional — narrower in Montserrat — and anything placed after a number
    // on the measured line, such as an inline box, would end up to the right of its text. A cell
    // can then break at other words than in the Marp HTML, and a vertically centred slide moves
    // with the table's height.
    await page.addStyleTag({ content: 'section table, section table * { font-variant-numeric: normal !important; }' });
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
      const own = new Set([...document.fonts].map(f => f.family.replace(/^["']|["']$/g, '').toLowerCase()));
      const safe = ff => {
        const first = (ff || '').split(',')[0].trim().replace(/^["']|["']$/g, '').toLowerCase();
        return KIND[first] && !own.has(first) ? FACE[KIND[first]] : null;
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
    fs.writeFileSync(path.join(outDir, 'model.json'), JSON.stringify(model));
    console.log(`measured ${model.slides.length} slides, ${model.rasters.length} rasters`);
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
