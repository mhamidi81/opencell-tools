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
 *   - inline-blocks that carry a box, a margin or a pseudo shape, placed at their own position;
 *   - inset box-shadows with no blur, drawn as the stripes they look like;
 *   - CSS filter and opacity on background images, applied when the image is redrawn.
 *
 * It measures with the TTFs in $OC_PPTX_FONTS — the files finish.py embeds — instead of the
 * theme's webfont, so the widths it records are the widths PowerPoint will draw.
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
      return t ? { t: transform(t, cs), ...fontOf(cs) } : null;
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
    const positioned = el => {
      const cs = getComputedStyle(el);
      if (!/^inline-(block|flex|grid|table)$/.test(cs.display)) return false;
      if (boxOf(cs, rel(el.getBoundingClientRect()))) return true;
      if (px(cs.marginLeft) || px(cs.marginRight)) return true;
      return ['::before', '::after'].some(w => { const p = getComputedStyle(el, w); return hasContent(p) && p.display === 'inline-block' && (col(p.backgroundColor) || p.backgroundImage !== 'none'); });
    };

    // ---- text runs, with Chromium's line breaks
    const runsOf = (nodes, skipLists, lhPx) => {
      const runs = [];
      let prevTop = null;
      const tol = (lhPx || 16) * k * 0.5;
      const walk = list => {
        for (const ch of list) {
          if (ch.nodeType === 3) {
            const cs = getComputedStyle(ch.parentElement), link = ch.parentElement.closest('a')?.href || null;
            const f = fontOf(cs), raw = ch.nodeValue;
            if (/^pre/.test(cs.whiteSpace)) {
              raw.split('\n').forEach((line, i) => { if (i) runs.push({ br: true }); if (line) runs.push({ t: transform(line, cs), ...f, link }); });
              continue;
            }
            const re = /(\s+)|(\S+)/g, range = document.createRange();
            let m;
            while ((m = re.exec(raw))) {
              if (m[1]) { runs.push({ t: ' ', ...f, link }); continue; }
              range.setStart(ch, m.index); range.setEnd(ch, m.index + m[2].length);
              const rs = range.getClientRects();
              let word = m[2];
              if (rs.length) {
                if (prevTop !== null && rs[0].top > prevTop + tol) runs.push({ br: true, soft: true });
                if (rs[rs.length - 1].top > rs[0].top + tol) {
                  // Broken inside the word: find the first character on a later line.
                  let cut = 1;
                  for (; cut < word.length; cut++) {
                    range.setStart(ch, m.index + cut); range.setEnd(ch, m.index + cut + 1);
                    const c = range.getClientRects()[0];
                    if (c && c.top > rs[0].top + tol) break;
                  }
                  runs.push({ t: transform(word.slice(0, cut), cs), ...f, link }, { br: true, soft: true });
                  word = word.slice(cut);
                }
                prevTop = rs[rs.length - 1].top;
              }
              runs.push({ t: transform(word, cs), ...f, link });
            }
          } else if (ch.nodeType === 1) {
            const tag = ch.tagName.toLowerCase();
            if (skipLists && (tag === 'ul' || tag === 'ol')) continue;
            const cs = getComputedStyle(ch);
            if (cs.display === 'none') continue;
            if (tag === 'br') { runs.push({ br: true }); prevTop = null; continue; }
            const b = pseudoString(ch, '::before'); if (b) runs.push(b);
            walk(ch.childNodes);
            const a = pseudoString(ch, '::after'); if (a) runs.push(a);
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
          if (out.length && !out[out.length - 1].br) out[out.length - 1].t = out[out.length - 1].t.replace(/ +$/, '');
          if (out.length && !out[out.length - 1].br) out.push({ br: true });
          atStart = true; continue;
        }
        let t = r.t;
        if (atStart || (out.length && / $/.test(out[out.length - 1].t || ''))) t = t.replace(/^ +/, '');
        if (!t) continue;
        const last = out[out.length - 1];
        const same = last && !last.br && ['face', 'size', 'bold', 'italic', 'spacing', 'underline', 'strike', 'sup', 'sub', 'link']
          .every(key => last[key] === r[key]) && (last.color && last.color.hex) === (r.color && r.color.hex);
        if (same) last.t += t; else out.push({ ...r, t });
        atStart = false;
      }
      while (out.length && out[out.length - 1].br) out.pop();
      if (out.length) out[out.length - 1].t = out[out.length - 1].t.replace(/ +$/, '');
      return out.filter(r => r.br || r.t);
    };
    const linesOf = runs => 1 + runs.filter(r => r.br).length;
    const textItem = (el, cs, nodes) => {
      const lh = lineHeight(cs);
      const runs = runsOf(nodes || el.childNodes, false, lh);
      const b = pseudoString(el, '::before'), a = pseudoString(el, '::after');
      if (b) runs.unshift(b);
      if (a) runs.push(a);
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
      const lines = linesOf(runs), nat = tight.h - (lines - 1) * lh;
      // A rect taken from the glyph box starts half a leading below its line box: move it up,
      // so every text rect starts where CSS starts the line.
      if (nodes) rect = { ...rect, y: rect.y - (lh - nat) / 2, h: lines * lh };
      return { type: 'text', rect, tight, runs, align: al, lh, lines, nat, valign: 'top', dir: cs.direction };
    };
    const inlineDecor = (root, out) => {    // pseudo shapes on inline descendants (inside tables, lists)
      for (const d of root.querySelectorAll('*')) for (const w of ['::before', '::after']) {
        const p = getComputedStyle(d, w);
        if (hasContent(p) && p.display === 'inline-block') { const bx = pseudoBox(d, w); if (bx) out.push(...bx); }
      }
    };

    // ---- lists, tables, SVG
    const listItem = (el, level, paras) => {
      const ordered = el.tagName.toLowerCase() === 'ol';
      const lcs = getComputedStyle(el);
      let n = ordered ? (el.start || 1) : 0;
      for (const li of el.children) {
        if (li.tagName.toLowerCase() !== 'li') continue;
        const cs = getComputedStyle(li), lh = lineHeight(cs);
        const type = cs.listStyleType;
        paras.push({ runs: runsOf(li.childNodes, true, lh), level, lh,
          bullet: type === 'none' ? null : ordered ? { type: 'number', start: n } :
            { char: { disc: '•', circle: '◦', square: '▪' }[type] || '•' },
          indent: px(lcs.paddingLeft), after: px(cs.marginBottom), before: px(cs.marginTop),
          align: align(cs.textAlign), marker: col(cs.color) });
        n++;
        for (const sub of li.children) {
          const t = sub.tagName.toLowerCase();
          if (t === 'ul' || t === 'ol') listItem(sub, level + 1, paras);
        }
      }
      return paras;
    };
    const tableItem = el => {
      const rows = [...el.rows];
      const grid = rows.map(tr => [...tr.cells].map(td => {
        const cs = getComputedStyle(td);
        const side = s => {
          const w = px(cs[`border${s}Width`]), c = col(cs[`border${s}Color`]);
          return w > 0 && c && cs[`border${s}Style`] !== 'none' ? { w, c } : null;
        };
        return { runs: runsOf(td.childNodes, false, lineHeight(cs)), lh: lineHeight(cs), align: align(cs.textAlign),
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
        const t = textItem(el, cs), deco = [];
        emitBox(boxOf(cs, rect), cs, deco);
        chrome.title = { text: t, deco };
        if (before) out.push(...before);
        if (after) out.push(...after);
        return;
      }
      if (tag === 'img') { out.push(raster({ kind: 'img', src: el.currentSrc || el.src, w: rect.w, h: rect.h, fit: cs.objectFit, css: { filter: cs.filter, opacity: cs.opacity } }, rect)); return; }
      if (tag === 'svg') { out.push(...svgItems(el)); return; }
      const box = boxOf(cs, rect);
      if (tag === 'table') {
        emitBox(box, cs, out); if (before) out.push(...before);
        out.push(tableItem(el)); inlineDecor(el, out);
        if (after) out.push(...after); return;
      }
      if (tag === 'ul' || tag === 'ol') {
        emitBox(box, cs, out);
        const paras = listItem(el, 0, []);
        if (paras.some(p => p.runs.length)) out.push({ type: 'list', rect, paras });
        inlineDecor(el, out);
        return;
      }
      const inlineOnly = [...el.querySelectorAll('*')].every(d => {
        const t = d.tagName.toLowerCase();
        return t !== 'img' && t !== 'svg' && t !== 'table' && (t === 'br' || (isInline(getComputedStyle(d)) && !positioned(d)));
      });
      if (inlineOnly && (el.textContent.trim() || pseudoString(el, '::before') || pseudoString(el, '::after'))) {
        const t = textItem(el, cs);
        if (box && !box.bgImg && t) {
          box.text = t;
          box.pad = [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)];
          box.valign = Math.abs(t.tight.y + t.tight.h / 2 - (rect.y + rect.h / 2)) < 2 ? 'middle' : 'top';
          if (before) out.push(...before);
          out.push(box);
        } else {
          emitBox(box, cs, out);
          if (before) out.push(...before);
          if (t) out.push(t);
        }
        if (after) out.push(...after);
        return;
      }
      emitBox(box, cs, out);
      if (before) out.push(...before);
      let group = [];
      const flush = () => {
        if (group.some(n => (n.textContent || '').trim())) { const t = textItem(el, cs, group); if (t) out.push(t); }
        group = [];
      };
      for (const ch of el.childNodes) {
        if (ch.nodeType === 3) { group.push(ch); continue; }
        if (ch.nodeType !== 1) continue;
        const t = ch.tagName.toLowerCase();
        if (t === 'br') { flush(); continue; }
        if (t !== 'img' && t !== 'svg' && isInline(getComputedStyle(ch)) && !positioned(ch) && !ch.querySelector('img,svg')
            && [...ch.querySelectorAll('*')].every(d => !positioned(d))) { group.push(ch); continue; }
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
    const blank = await browser.newPage();
    await blank.setViewport({ width: 1600, height: 1200, deviceScaleFactor: 2 });
    const blankFile = path.join(outDir, 'blank.html');
    fs.writeFileSync(blankFile, '<!doctype html><html><body style="margin:0;background:transparent"></body></html>');
    await blank.goto('file://' + path.resolve(blankFile), { waitUntil: 'load' });
    for (const r of model.rasters) {
      r.file = path.join(outDir, `raster-${r.id}.png`);
      if (r.kind === 'element') {
        const el = await page.$(r.selector);
        await el.screenshot({ path: r.file });
        continue;
      }
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
