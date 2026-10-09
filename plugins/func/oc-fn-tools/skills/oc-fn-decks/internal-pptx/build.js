#!/usr/bin/env node
/* build.js — turn measure.js's model into an editable PPTX with pptxgenjs.
 *
 * Called by render-internal-pptx.sh; not meant to be run by hand.
 *   node build.js <model.json> <deck.md> <out.pptx>
 * Needs NODE_PATH holding pptxgenjs.
 *
 * Geometry arrives in slide pixels and goes out in inches (96 px per inch, 0.75 pt per px).
 * Each distinct slide "chrome" — background, logo decorations, footer, header, page number,
 * title geometry and title rule — becomes one slide layout; its title is a real title
 * placeholder. Everything else is placed on the slide as native objects in paint order.
 * Text keeps the line breaks Chromium chose (measure.js records them as soft breaks), and each
 * text box gets some extra width so PowerPoint's own metrics never add a wrap of their own;
 * one-line texts do not wrap at all, nor does a box's text when the box has no room for that
 * slack. Table cells cannot grow, so their side padding is trimmed by a quarter instead.
 * A list with shapes drawn over its text is one text box per item, at Chromium's y for each.
 * Speaker notes are the `<!-- note: … -->` comments of the .md, slide by slide.
 */
const fs = require('fs');
const crypto = require('crypto');
const pptxgen = require('pptxgenjs');

const [modelPath, mdPath, outPath] = process.argv.slice(2);
if (!outPath) { console.error('usage: build.js <model.json> <deck.md> <out.pptx>'); process.exit(2); }
const model = JSON.parse(fs.readFileSync(modelPath, 'utf8'));
const md = fs.readFileSync(mdPath, 'utf8');

const X = v => v / 96;                         // px → in
const PT = v => Math.round(v * 75) / 100;      // px → pt
const R = v => Math.round(v / 2) * 2;          // layout-key rounding
const transp = a => (a != null && a < 1) ? Math.round((1 - a) * 100) : undefined;
const rasterFile = new Map(model.rasters.map(r => [r.id, r.file]));
const digest = f => crypto.createHash('md5').update(fs.readFileSync(f)).digest('hex').slice(0, 12);

// ---------------------------------------------------------------- front matter, notes
const fm = (md.match(/^---\n([\s\S]*?)\n---\n/) || [, ''])[1];
const meta = Object.fromEntries(fm.split('\n').map(l => l.match(/^(\w+):\s*(.*)$/)).filter(Boolean)
  .map(m => [m[1], m[2].replace(/^'(.*)'$/, '$1').replace(/^"(.*)"$/, '$1')]));
function notesFromMd(text) {
  const body = text.replace(/^---\n[\s\S]*?\n---\n/, '');
  const chunks = [[]];
  let fence = false;
  for (const line of body.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) fence = !fence;
    if (!fence && /^---\s*$/.test(line)) { chunks.push([]); continue; }
    chunks[chunks.length - 1].push(line);
  }
  return chunks.map(ls => [...ls.join('\n').matchAll(/<!--\s*note:\s*([\s\S]*?)-->/g)].map(m => m[1].trim()).join('\n\n'));
}
let notes = notesFromMd(md);
if (notes.length !== model.slides.length) {
  console.warn(`build.js: ${notes.length} slides in the .md, ${model.slides.length} rendered — speaker notes skipped`);
  notes = [];
}

// ---------------------------------------------------------------- deck
const pres = new pptxgen();
const W = model.slides[0].w, H = model.slides[0].h;
pres.defineLayout({ name: 'MARP', width: X(W), height: X(H) });
pres.layout = 'MARP';
if (meta.title) pres.title = meta.title;
if (meta.author) pres.author = meta.author.split(' — ')[0];
if (meta.subtitle) pres.subject = meta.subtitle;
const faces = model.slides.flatMap(s => s.items).flatMap(i => i.runs || []).map(r => r.face).filter(Boolean);
const mainFace = faces.sort((a, b) => faces.filter(f => f === b).length - faces.filter(f => f === a).length)[0] || 'Arial';
pres.theme = { headFontFace: mainFace, bodyFontFace: mainFace };

const runOpts = r => ({
  fontFace: r.face || undefined, fontSize: PT(r.size), bold: !!r.bold, italic: !!r.italic,
  color: r.color ? r.color.hex : undefined, transparency: r.color ? transp(r.color.alpha) : undefined,
  charSpacing: r.spacing ? PT(r.spacing) : undefined, underline: r.underline ? { style: 'sng' } : undefined,
  strike: r.strike ? 'sngStrike' : undefined, superscript: r.sup || undefined, subscript: r.sub || undefined,
  hyperlink: r.link && /^https?:|^mailto:/.test(r.link) ? { url: r.link } : undefined,
  // An inline box holding text (a tag, an inline code): its fill as a text highlight (measure.js).
  highlight: r.hl ? r.hl.hex : undefined,
});
function toRuns(runs, para) {
  const out = [];
  let soft = false;
  for (const r of runs) {
    if (r.br) { soft = true; continue; }
    const o = { ...runOpts(r), ...(para || {}) };
    if (soft && out.length) o.softBreakBefore = true;
    soft = false;
    out.push({ text: r.t, options: o });
  }
  return out;
}
const fillOf = c => c ? { color: c.hex, transparency: transp(c.alpha) } : { type: 'none' };
const lineOf = (c, w, dash, alpha) => c ? { color: c.hex, width: PT(w), dashType: dash ? 'dash' : 'solid', transparency: transp(alpha) } : { type: 'none' };

/** Half the leading CSS adds above a line, which PowerPoint puts above the text instead.
 *  CSS splits (line-height − natural height) half above and half below the glyphs; PowerPoint
 *  with exact line spacing (and LibreOffice, where this was calibrated: drift ≈ 1 px per px of
 *  extra line-height) puts all of it above, so a box must start that much higher. The natural
 *  height is measured per text item (nat), else estimated at 1.22 em of its largest run. */
function leadRaw(it) {            // (line-height − natural height) / 2, signed
  const size = Math.max(0, ...(it.runs || []).filter(r => r.t).map(r => r.size || 0));
  const nat = it.nat > 0 ? it.nat : size * 1.22;
  return nat ? (it.lh - nat) / 2 : 0;
}
/** Top-anchored text: below the natural height the renderer does not pull the first line up
 *  (CSS does, by half the deficit), so the box moves up by that half — a lift either way.
 *  A piece that is one line set in a font larger than its line-height (measure.js lineTops:
 *  `foreign`, `fg`) is the exception: there the deficit is large (8.5 px for a 1.6 em word at
 *  line-height 1.32), and LibreOffice puts all of it above the glyphs as it does extra leading
 *  (fixed spacing: the line's ascent grows by line-height − text height, so it shrinks here):
 *  measured on edge deck e19, the abs() lift left such a line 8 px above Chromium's. The box then
 *  moves down by half the deficit — the signed half-leading. Not checked in PowerPoint. */
const leadShift = it => it.fg ? leadRaw(it) : Math.abs(leadRaw(it));
/** Centred text: only extra leading displaces the glyphs; a deficit stays centred. */
const leadMid = it => Math.max(0, leadRaw(it));
/** Text-box geometry: wrap slack, anchored by the text alignment; lifted by leadShift. */
function textGeom(it) {
  const extra = Math.max(8, it.rect.w * 0.08), dy = leadShift(it);
  let x = it.rect.x;
  if (it.align === 'center') x -= extra / 2; else if (it.align === 'right') x -= extra;
  const h = Math.max(it.rect.h, it.lines * it.lh) + Math.max(0, dy);
  return { x: X(x), y: X(it.rect.y - dy), w: X(it.rect.w + extra), h: X(h) };
}
const textOpts = it => ({ ...textGeom(it), margin: 0, valign: it.valign || 'top', align: it.align === 'justify' ? 'justify' : it.align,
  lineSpacing: PT(it.lh), wrap: it.lines !== 1, fit: 'none', isTextBox: true, rtlMode: it.dir === 'rtl' || undefined });

// ---------------------------------------------------------------- layouts from chrome
const layouts = new Map();
function chromeKey(c) {
  const t = c.title && c.title.text;
  return JSON.stringify({
    bg: c.bg && c.bg.hex,
    decor: c.decor.map(d => d.type === 'image' ? ['i', digest(rasterFile.get(d.raster)), R(d.rect.x), R(d.rect.y), R(d.rect.w)]
      : ['b', R(d.rect.x), R(d.rect.y), R(d.rect.w), R(d.rect.h), d.fill && d.fill.hex]),
    footer: c.footer && [c.footer.runs.map(r => r.t || '\n').join(''), R(c.footer.rect.x), R(c.footer.rect.y)],
    header: c.header && [c.header.runs.map(r => r.t || '\n').join(''), R(c.header.rect.x), R(c.header.rect.y)],
    page: c.pagenum && [R(c.pagenum.rightPx), R(c.pagenum.bottom), c.pagenum.size],
    title: t && [R(t.rect.x), R(t.rect.y), R(t.rect.w), t.align, t.runs[0] && [t.runs[0].face, t.runs[0].size, t.runs[0].bold]],
    tdeco: c.title && c.title.deco.map(d => [d.type, R(d.rect.x), R(d.rect.y), R(d.rect.w), R(d.rect.h)]),
  });
}
function decoObjects(d) {
  if (d.type === 'image') return [{ image: { x: X(d.rect.x), y: X(d.rect.y), w: X(d.rect.w), h: X(d.rect.h), path: rasterFile.get(d.raster) } }];
  const objs = [];
  if (d.fill || d.line) objs.push({ rect: { x: X(d.rect.x), y: X(d.rect.y), w: X(d.rect.w), h: X(d.rect.h), fill: fillOf(d.fill),
    line: d.line ? lineOf(d.line.c, d.line.w, d.line.dash) : { type: 'none' } } });
  for (const s of sideRects(d)) objs.push({ rect: { ...s.geom, fill: { color: s.color }, line: { type: 'none' } } });
  for (const s of d.stripes || []) objs.push({ rect: { x: X(s.x), y: X(s.y), w: X(s.w), h: X(s.h), fill: fillOf(s.c), line: { type: 'none' } } });
  return objs;
}
function textObject(it) {
  const f = it.runs.find(r => r.t) || {};
  return { text: { text: it.runs.map(r => r.br ? '\n' : r.t).join(''), options: { ...textOpts(it), ...runOpts(f), hyperlink: undefined, highlight: undefined } } };
}
function layoutFor(slide, idx) {
  const c = slide.chrome, key = chromeKey(c);
  if (layouts.has(key)) return layouts.get(key);
  const name = `Marp ${slide.cls.split(/\s+/).filter(x => x && x !== 'marpit').join(' ') || 'content'} ${layouts.size + 1}`.replace(/&/g, '&amp;');
  const objects = [];
  for (const d of c.decor) objects.push(...decoObjects(d));
  if (c.title) for (const d of c.title.deco) objects.push(...decoObjects(d));
  if (c.header) objects.push(textObject(c.header));
  if (c.footer) objects.push(textObject(c.footer));
  if (c.title && c.title.text) {
    const t = c.title.text, f = t.runs.find(r => r.t) || {};
    objects.push({ placeholder: { options: { name: 'title', type: 'title', ...textGeom({ ...t, lines: 2 }),
      h: X(Math.max(t.rect.h, t.lh * t.lines)), margin: 0, valign: 'top', align: t.align, ...runOpts(f), hyperlink: undefined, highlight: undefined }, text: '' } });
  }
  const def = { title: name, background: c.bg ? { color: c.bg.hex } : { color: 'FFFFFF' }, objects };
  if (c.pagenum) {
    const p = c.pagenum, w = 80;
    def.slideNumber = { x: X(W - p.rightPx - w), y: X(H - p.bottom - p.lh), w: X(w), h: X(p.lh), fontFace: p.face,
      fontSize: PT(p.size), color: p.color ? p.color.hex : undefined, align: 'right', margin: 0 };
  }
  pres.defineSlideMaster(def);
  layouts.set(key, name);
  return name;
}

// ---------------------------------------------------------------- slide items
function sideRects(b) {
  if (!b.sides) return [];
  const { x, y, w, h } = b.rect, [t, r, bo, l] = b.sides, out = [];
  if (t) out.push({ color: t.c.hex, geom: { x: X(x), y: X(y), w: X(w), h: X(t.w) } });
  if (bo) out.push({ color: bo.c.hex, geom: { x: X(x), y: X(y + h - bo.w), w: X(w), h: X(bo.w) } });
  if (l) out.push({ color: l.c.hex, geom: { x: X(x), y: X(y), w: X(l.w), h: X(h) } });
  if (r) out.push({ color: r.c.hex, geom: { x: X(x + w - r.w), y: X(y), w: X(r.w), h: X(h) } });
  return out;
}
/** How far a cell's text moves once cellMargin() trims its side padding: a shape drawn over the
 *  table in a cell's text (an empty inline box, an image) moves with it. */
function cellShift(c) {
  if (!c) return 0;
  const [l, r] = c.pad.map(p => p * (1 - CELL_SIDE));
  return c.align === 'right' ? r : c.align === 'center' ? (r - l) / 2 : -l;
}
function addBox(slide, b) {
  const shape = b.radius > 0 ? pres.shapes.ROUNDED_RECTANGLE : pres.shapes.RECTANGLE;
  if (b.cell) b = { ...b, rect: { ...b.rect, x: b.rect.x + cellShift(b.cell) } };
  const geom = { x: X(b.rect.x), y: X(b.rect.y), w: X(b.rect.w), h: X(b.rect.h) };
  const style = { fill: fillOf(b.fill), line: b.line ? lineOf(b.line.c, b.line.w, b.line.dash) : { type: 'none' },
    rectRadius: b.radius > 0 ? X(Math.min(b.radius, b.rect.h / 2, b.rect.w / 2)) : undefined };
  if (b.text) {
    const t = b.text, [pt, pr, pb, pl] = b.pad, dy = b.valign === 'middle' ? leadMid(t) : leadShift(t);
    // Lift the text by dy: a centred block moves up by half of what is added below it.
    const top = b.valign === 'middle' ? pt : Math.max(0, pt - dy), bottom = b.valign === 'middle' ? pb + 2 * dy : pb;
    // Side insets: the text needs some slack against PowerPoint's own wrapping, so the insets
    // add up to three quarters of the side padding. Centred text takes it from both sides.
    // Left-aligned text starts exactly where Chromium starts it — border and padding included,
    // since shapes drawn over it (an empty inline box, an image) sit at Chromium's positions —
    // and the right inset gives up the slack; right-aligned text mirrors that.
    const bw = i => (b.line ? b.line.w : (b.sides && b.sides[i] ? b.sides[i].w : 0));
    const slackTotal = (pl + pr) * 0.75;
    let mL = pl * 0.75, mR = pr * 0.75;
    // A rounded rectangle's text area is itself inset by 0.29289 × its corner radius on every
    // side (the roundRect preset's text rectangle, which PowerPoint and LibreOffice both apply),
    // on top of the insets: take that back where it moves the text — the sides, and the top of
    // top-anchored text (it cancels out of a centred block).
    const il = b.radius > 0 ? 0.29289 * Math.min(b.radius, b.rect.h / 2, b.rect.w / 2) : 0;
    let wrap = t.lines !== 1;
    if (t.align === 'left' || t.align === 'justify' || t.align === 'right') {
      const left = t.align !== 'right';
      // Chromium's content box on the side the text is anchored to, and on the other side.
      let near = left ? (t.rect ? t.rect.x - b.rect.x : bw(3) + pl) : (t.rect ? b.rect.x + b.rect.w - (t.rect.x + t.rect.w) : bw(1) + pr);
      const far = left ? bw(1) + pr : bw(3) + pl;
      let other = Math.max(0, slackTotal - near);
      // With little padding or border on the far side (a fit-content note with a left border and
      // no right padding), that inset clamps to 0 and the text area is barely wider than
      // Chromium's lines, if at all: a line PowerPoint draws a little wider wraps again and
      // spills out of the box. Below a floor of slack, text whose every line break is recorded
      // stops wrapping instead — a line drawn wider runs that much into the far side, where a
      // wrap would add a whole line. Two kinds of text keep wrapping and get the floor back by
      // starting that much nearer their edge: justified text (unwrapped, it is no longer
      // justified) and text with a break Chromium made that the model does not carry (`free`:
      // pre-wrap, a pseudo-element string).
      const slack = far - Math.max(other, il), floor = 2 + 0.01 * (b.rect.w - near - far);
      if (wrap && near > slackTotal && slack < floor) {
        if (t.align === 'justify' || t.runs.some(r => r.free)) near = Math.max(0, near - (floor - slack));
        else wrap = false;
      }
      [mL, mR] = left ? [near, other] : [other, near];
    } else if (t.align === 'center' && wrap && !t.runs.some(r => r.free)) {
      // Centred text takes its slack from both sides; with too little padding and border to give
      // it (a fit-content label with no padding), it stops wrapping on the same floor, and a line
      // drawn wider runs out evenly on both sides.
      const side = bw(1) + pr + bw(3) + pl;
      if (side - Math.max(mL, il) - Math.max(mR, il) < 2 + 0.01 * (b.rect.w - side)) wrap = false;
    }
    const ins = (v, cut) => PT(Math.max(0, v - (cut ? il : 0)));
    const vCut = b.valign !== 'middle';
    slide.addText(toRuns(t.runs), { shape, ...geom, ...style,
      margin: [ins(mL, true), ins(mR, true), ins(bottom, vCut), ins(top, vCut)],
      align: t.align, valign: b.valign, lineSpacing: PT(t.lh), wrap, fit: 'none' });
  } else if (b.fill || b.line) {
    slide.addShape(shape, { ...geom, ...style });
  }
  for (const s of sideRects(b)) slide.addShape(pres.shapes.RECTANGLE, { ...s.geom, fill: { color: s.color }, line: { type: 'none' } });
  for (const s of b.stripes || []) slide.addShape(pres.shapes.RECTANGLE, { x: X(s.x), y: X(s.y), w: X(s.w), h: X(s.h),
    fill: fillOf(s.c), line: { type: 'none' } });
}
function addList(slide, it) {
  // CSS hangs the marker just left of the text, inside the list's left padding; pptxgenjs ties
  // the hanging indent to the left margin. So the box starts where the marker hangs, and the
  // hang is about one em of the items' font — of the item, not of its first run, which can be
  // a smaller inline box. It is never narrower than the widest marker of the list plus a
  // quarter em: a marker wider than its hang pushes the text right in LibreOffice and to the
  // next tab stop in PowerPoint.
  const first = it.paras.find(p => p.runs.some(r => r.t));
  const size = first ? (first.font && first.font.size) || (first.runs.find(r => r.t) || {}).size || 16 : 16;
  const pad = first ? first.indent : 0;
  const hang = Math.max(Math.min(pad, Math.max(12, size * 1.05)),
    ...it.paras.filter(p => p.bullet && p.mw).map(p => p.mw + 0.25 * ((p.font && p.font.size) || size)));
  // Nested items: CSS indents each level by its own list's padding, pptxgenjs by one more hang
  // (marL = indent × (level + 1)). Each nested item's indent is chosen so that marL lands on the
  // text start Chromium measured; finish.py then sets its hanging indent back to the list's hang.
  const left = first && first.x != null ? first.x - hang : (it.rect.x + pad - hang);
  if (it.split) { addListItems(slide, it, hang); return; }
  const runs = [];
  it.paras.forEach((p, i) => {
    const marL = p.level && p.x != null ? Math.max(hang, p.x - left) / (p.level + 1) : hang;
    const para = { align: p.align, lineSpacing: PT(p.lh), paraSpaceAfter: PT(p.after) || undefined, paraSpaceBefore: PT(p.before) || undefined,
      indentLevel: p.level || undefined,
      bullet: p.bullet ? bulletOf(p, marL)
        // Text continuing an item after its nested list starts at the item's text, with no marker:
        // a no-break space as the marker gets that margin from pptxgenjs, and finish.py turns it
        // into no marker.
        : p.cont ? { characterCode: '00A0', indent: PT(marL) } : false };
    const rs = toRuns(p.runs);
    markerFont(p, rs);
    // An empty item still shows its marker, as in Chromium.
    if (!rs.length) rs.push(p.bullet && p.font ? markerRun(p) : { text: '', options: {} });
    Object.assign(rs[0].options, para);
    if (i < it.paras.length - 1) rs[rs.length - 1].options.breakLine = true;
    runs.push(...rs);
  });
  const lh = it.paras[0] ? it.paras[0].lh : 20;
  const dy = first ? leadShift({ runs: first.runs, lh: first.lh }) : 0;
  // The wrap slack goes on the right, unless every item is centred (half of it on each side) or
  // right-aligned (all of it on the left): the text then lands where Chromium centres or aligns it.
  const extra = Math.max(8, it.rect.w * 0.08), als = new Set(it.paras.filter(p => p.runs.some(r => r.t)).map(p => p.align));
  const shift = als.size !== 1 ? 0 : als.has('center') ? extra / 2 : als.has('right') ? extra : 0;
  slide.addText(runs, { x: X(left - shift), y: X(it.rect.y - dy), w: X(it.rect.x + it.rect.w - left + extra),
    h: X(it.rect.h), margin: 0, valign: 'top',
    lineSpacing: PT(lh), fit: 'none', isTextBox: true });
}
/** A marker takes its font, size, weight and colour from the paragraph's first run. When that
 *  run is not in the item's own font — an inline box's pad or highlighted text, a bold or
 *  coloured opening — the item opens on a zero-width space in its own font, as CSS draws the
 *  marker in the li's font. */
function markerFont(p, rs) {
  const r0 = p.runs.find(r => r.t), f = p.font;
  if (p.bullet && f && r0 && (r0.pad || r0.hl || ['face', 'size', 'bold', 'italic'].some(k => r0[k] !== f[k])
      || (r0.color && r0.color.hex) !== (f.color && f.color.hex))) {
    rs.unshift({ text: '\u200b', options: runOpts({ ...f, spacing: 0, underline: false, strike: false, link: null }) });
  }
}
/** The marker of list paragraph p, hanging `indent` px (pptxgenjs bullet options). */
const bulletOf = (p, indent) => p.bullet.type === 'number' ? { type: 'number', numberStartAt: p.bullet.start, indent: PT(indent) }
  : { characterCode: p.bullet.char.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'), indent: PT(indent) };
/** A zero-width space in the item's own font: a paragraph needs a character for PowerPoint to draw
 *  its marker, and the marker takes that character's font, size, weight and colour. */
const markerRun = p => ({ text: '\u200b', options: runOpts({ ...p.font, spacing: 0, underline: false, strike: false, link: null }) });
/** A list with overlays drawn over its text (measure.js: `split`): one text box per item, at the
 *  y Chromium gave the item, so PowerPoint's tighter line pitch cannot pile up down the list.
 *  An item cut further (`cuts`) continues in a box of its own at each cut, with no marker, at the
 *  item's text position, as does the text after an item's nested list (`cont`). An item whose
 *  pitch is uneven (`uneven`: a taller line, a loose item's paragraph margin) is anchored on its
 *  glyphs, so each of its boxes is lifted as a plain line of the item's font — of a larger font
 *  for a cut at a line set in one (`nat`). Each box hangs its marker like the whole list would
 *  (same hang), at level 0 — a nested item is placed by its box, not by an indent level — and an
 *  item with no marker starts at its own text position. The right edge is the list's, with the
 *  usual slack. A centred or right-aligned item is laid out over its own content box instead,
 *  with the slack split evenly (centred) or on the left (right-aligned), so its text lands where
 *  Chromium centres or aligns it; its marker, which Chromium hangs at the content box's left edge
 *  whatever the alignment, is then a box of its own there. So is the marker of an item with no
 *  text of its own: an empty item, or one that opens on its nested list, whose marker Chromium
 *  draws on the first nested item's line (measure.js: `markerOnly`). */
function addListItems(slide, it, hang) {
  const right = it.rect.x + it.rect.w + Math.max(8, it.rect.w * 0.08);
  const markerBox = (p, y, dy) => {
    const rs = [markerRun(p)];
    Object.assign(rs[0].options, { align: 'left', lineSpacing: PT(p.lh), bullet: bulletOf(p, hang) });
    slide.addText(rs, { x: X(p.x - hang), y: X(y - dy), w: X(hang + 8), h: X(p.lh + dy), margin: 0, valign: 'top',
      lineSpacing: PT(p.lh), wrap: false, fit: 'none', isTextBox: true });
  };
  for (const p of it.paras) {
    const plainDy = p.font ? leadShift({ runs: [{ t: ' ', size: p.font.size }], lh: p.lh }) : 0;
    if (!p.runs.some(r => r.t)) { if (p.bullet && p.y != null) markerBox(p, p.y, plainDy); continue; }
    const lines = [[]];
    for (const r of p.runs) if (r.br) lines.push([]); else lines[lines.length - 1].push(r);
    const cuts = p.cuts || [{ line: 0, y: p.y }];
    const dy = p.uneven ? plainDy : leadShift({ runs: p.runs, lh: p.lh });     // as for the list kept whole
    const side = (p.align === 'center' || p.align === 'right') && p.w > 0;
    cuts.forEach((c, j) => {
      const end = j + 1 < cuts.length ? cuts[j + 1].line : lines.length, n = end - c.line;
      const cdy = c.nat ? leadShift({ runs: [], lh: p.lh, nat: c.nat, fg: true }) : dy;
      const runs = [];
      lines.slice(c.line, end).forEach((l, i) => { if (i) runs.push({ br: true }); runs.push(...l); });
      const marker = j === 0 && p.bullet;
      const rs = toRuns(runs);
      if (!rs.length) return;
      if (side) {
        if (marker) markerBox(p, c.y, dy);
        const e = Math.max(8, p.w * 0.08), x = p.align === 'center' ? p.x - e / 2 : p.x - e;
        Object.assign(rs[0].options, { align: p.align, lineSpacing: PT(p.lh), bullet: false });
        slide.addText(rs, { x: X(x), y: X(c.y - cdy), w: X(p.w + e), h: X(n * p.lh + Math.max(0, cdy)), margin: 0, valign: 'top',
          lineSpacing: PT(p.lh), wrap: n !== 1, fit: 'none', isTextBox: true });
        return;
      }
      const x = marker ? p.x - hang : p.x;
      if (marker) markerFont(p, rs);
      Object.assign(rs[0].options, { align: p.align, lineSpacing: PT(p.lh), bullet: marker ? bulletOf(p, hang) : false });
      slide.addText(rs, { x: X(x), y: X(c.y - cdy), w: X(right - x), h: X(n * p.lh + Math.max(0, cdy)), margin: 0, valign: 'top',
        lineSpacing: PT(p.lh), wrap: n !== 1, fit: 'none', isTextBox: true });
    });
  }
}
/** Cell margins, TRBL in pt: sides trimmed by a quarter (a cell cannot grow), the top lifted by
 *  leadShift (the bottom takes it back), and never under 1 pt on top — pptxgenjs ignores the
 *  whole margin then. A centred cell is lifted by leadMid: with exact spacing (measure.js: `exact`)
 *  the block is as tall as Chromium's, so the row has no room for more margin and the lift comes
 *  off the top; with single spacing a centred block moves up by half of what is added below it. */
const CELL_SIDE = 0.75;
function cellMargin(c) {
  const [t, r, b, l] = c.pad;
  if (c.valign === 'middle' && !c.exact) {
    const dy = leadMid(c);
    return [Math.max(1, PT(t)), Math.max(1, PT(r * CELL_SIDE)), Math.max(1, PT(b + 2 * dy)), Math.max(1, PT(l * CELL_SIDE))];
  }
  const dy = c.valign === 'middle' ? leadMid(c) : leadShift(c);
  return [Math.max(1, PT(t - dy)), Math.max(1, PT(r * CELL_SIDE)), Math.max(1, PT(b + dy)), Math.max(1, PT(l * CELL_SIDE))];
}
function addTable(slide, t) {
  // A cell (measure.js: `exact`) is laid out at Chromium's line-height (exact spacing), as a text
  // box is: with the renderer's single spacing — about 1.22 em in Montserrat where the opencell
  // theme sets 1.45 — its lines sat about 16 % of a line-height closer together than in Marp. A
  // cell with a run in a larger font keeps single spacing, which makes room for that line.
  const rows = t.grid.map(r => r.map(c => ({
    text: toRuns(c.runs).length ? toRuns(c.runs, c.exact ? { lineSpacing: PT(c.lh) } : undefined) : '',
    options: {
      fill: c.fill ? { color: c.fill.hex } : undefined, align: c.align, valign: c.valign,
      margin: cellMargin(c),
      border: c.border.map(b => b ? { type: 'solid', pt: PT(b.w), color: b.c.hex } : { type: 'none' }),
      colspan: c.colspan > 1 ? c.colspan : undefined, rowspan: c.rowspan > 1 ? c.rowspan : undefined,
    },
  })));
  const w = t.colW.reduce((a, b) => a + b, 0);
  slide.addTable(rows, { x: X(t.x), y: X(t.y), w: X(w), colW: t.colW.map(X), rowH: t.rowH.map(X), autoPage: false });
}
function addLine(slide, l) {
  const x = Math.min(l.a.x, l.b.x), y = Math.min(l.a.y, l.b.y);
  slide.addShape(pres.shapes.LINE, { x: X(x), y: X(y), w: X(Math.abs(l.b.x - l.a.x)), h: X(Math.abs(l.b.y - l.a.y)),
    flipH: (l.b.x < l.a.x) !== (l.b.y < l.a.y) && l.b.x !== l.a.x && l.b.y !== l.a.y ? true : undefined,
    line: lineOf(l.stroke.c, l.stroke.w, l.stroke.dash, l.stroke.alpha) });
}
function addPoly(slide, p) {
  const xs = p.points.map(q => q.x), ys = p.points.map(q => q.y);
  const x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(1, Math.max(...xs) - x0), h = Math.max(1, Math.max(...ys) - y0);
  const points = p.points.map((q, i) => ({ x: X(q.x - x0), y: X(q.y - y0), ...(i === 0 ? { moveTo: true } : {}) }));
  if (p.closed) points.push({ close: true });
  slide.addShape(pres.shapes.CUSTOM_GEOMETRY, { x: X(x0), y: X(y0), w: X(w), h: X(h), points,
    fill: p.fill ? fillOf({ hex: p.fill.c.hex, alpha: p.fill.alpha }) : { type: 'none' },
    line: p.stroke ? lineOf(p.stroke.c, p.stroke.w, p.stroke.dash, p.stroke.alpha) : { type: 'none' } });
}

model.slides.forEach((s, i) => {
  const slide = pres.addSlide({ masterName: layoutFor(s, i) });
  if (s.chrome.title && s.chrome.title.text) slide.addText(toRuns(s.chrome.title.text.runs), { placeholder: 'title' });
  for (const it of s.items) {
    if (it.type === 'box') addBox(slide, it);
    else if (it.type === 'text') slide.addText(toRuns(it.runs), textOpts(it));
    else if (it.type === 'list') addList(slide, it);
    else if (it.type === 'table') addTable(slide, it);
    // An image in a table cell (measure.js: `cell`) moves with the cell's text, like an empty inline box.
    else if (it.type === 'image') slide.addImage({ path: rasterFile.get(it.raster), x: X(it.rect.x + cellShift(it.cell)), y: X(it.rect.y), w: X(it.rect.w), h: X(it.rect.h) });
    else if (it.type === 'line') addLine(slide, it);
    else if (it.type === 'poly') addPoly(slide, it);
    else if (it.type === 'shape') {
      const shape = it.shape === 'ellipse' ? pres.shapes.OVAL : (it.radius > 0 ? pres.shapes.ROUNDED_RECTANGLE : pres.shapes.RECTANGLE);
      slide.addShape(shape, { x: X(it.rect.x), y: X(it.rect.y), w: X(it.rect.w), h: X(it.rect.h),
        fill: it.fill ? fillOf({ hex: it.fill.c.hex, alpha: it.fill.alpha }) : { type: 'none' },
        line: it.stroke ? lineOf(it.stroke.c, it.stroke.w, it.stroke.dash, it.stroke.alpha) : { type: 'none' },
        rectRadius: it.radius > 0 ? X(it.radius) : undefined });
    }
  }
  if (notes[i]) slide.addNotes(notes[i]);
});

pres.writeFile({ fileName: outPath }).then(() =>
  console.log(`built ${model.slides.length} slides on ${layouts.size} layout(s) → ${outPath}`));
