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
 * one-line texts do not wrap at all. Table cells cannot grow, so their side padding is trimmed
 * by a quarter instead.
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
 *  (CSS does, by half the deficit), so the box moves up by that half — a lift either way. */
const leadShift = it => Math.abs(leadRaw(it));
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
  return { text: { text: it.runs.map(r => r.br ? '\n' : r.t).join(''), options: { ...textOpts(it), ...runOpts(f), hyperlink: undefined } } };
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
      h: X(Math.max(t.rect.h, t.lh * t.lines)), margin: 0, valign: 'top', align: t.align, ...runOpts(f), hyperlink: undefined }, text: '' } });
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
function addBox(slide, b) {
  const shape = b.radius > 0 ? pres.shapes.ROUNDED_RECTANGLE : pres.shapes.RECTANGLE;
  const geom = { x: X(b.rect.x), y: X(b.rect.y), w: X(b.rect.w), h: X(b.rect.h) };
  const style = { fill: fillOf(b.fill), line: b.line ? lineOf(b.line.c, b.line.w, b.line.dash) : { type: 'none' },
    rectRadius: b.radius > 0 ? X(Math.min(b.radius, b.rect.h / 2, b.rect.w / 2)) : undefined };
  if (b.text) {
    const t = b.text, [pt, pr, pb, pl] = b.pad, dy = b.valign === 'middle' ? leadMid(t) : leadShift(t);
    // Lift the text by dy: a centred block moves up by half of what is added below it.
    const top = b.valign === 'middle' ? pt : Math.max(0, pt - dy), bottom = b.valign === 'middle' ? pb + 2 * dy : pb;
    slide.addText(toRuns(t.runs), { shape, ...geom, ...style,
      margin: [PT(pl * 0.75), PT(pr * 0.75), PT(Math.max(0, bottom)), PT(Math.max(0, top))],
      align: t.align, valign: b.valign, lineSpacing: PT(t.lh), wrap: t.lines !== 1, fit: 'none' });
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
  // hang is about one em of the list's font.
  const first = it.paras.find(p => p.runs.some(r => r.t));
  const size = first ? (first.runs.find(r => r.t) || {}).size || 16 : 16;
  const pad = first ? first.indent : 0, hang = Math.min(pad, Math.max(12, size * 1.05));
  const runs = [];
  it.paras.forEach((p, i) => {
    const para = { align: p.align, lineSpacing: PT(p.lh), paraSpaceAfter: PT(p.after) || undefined, paraSpaceBefore: PT(p.before) || undefined,
      indentLevel: p.level || undefined,
      bullet: p.bullet ? (p.bullet.type === 'number' ? { type: 'number', numberStartAt: p.bullet.start, indent: PT(hang) }
        : { characterCode: p.bullet.char.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'), indent: PT(hang) }) : false };
    const rs = toRuns(p.runs);
    if (!rs.length) rs.push({ text: '', options: {} });
    Object.assign(rs[0].options, para);
    if (i < it.paras.length - 1) rs[rs.length - 1].options.breakLine = true;
    runs.push(...rs);
  });
  const lh = it.paras[0] ? it.paras[0].lh : 20;
  const dy = first ? leadShift({ runs: first.runs, lh: first.lh }) : 0;
  slide.addText(runs, { x: X(it.rect.x + pad - hang), y: X(it.rect.y - dy), w: X(it.rect.w - pad + hang + Math.max(8, it.rect.w * 0.08)),
    h: X(it.rect.h), margin: 0, valign: 'top',
    lineSpacing: PT(lh), fit: 'none', isTextBox: true });
}
/** Cell margins, TRBL in pt: sides trimmed by a quarter (a cell cannot grow), the top lifted by
 *  leadShift (the bottom takes it back), and never under 1 pt on top — pptxgenjs ignores the
 *  whole margin then. */
function cellMargin(c) {
  const [t, r, b, l] = c.pad;
  if (c.valign === 'middle') {     // a centred block moves up by half of what is added below it
    const dy = leadMid(c);
    return [Math.max(1, PT(t)), Math.max(1, PT(r * 0.75)), Math.max(1, PT(b + 2 * dy)), Math.max(1, PT(l * 0.75))];
  }
  const dy = leadShift(c);
  return [Math.max(1, PT(t - dy)), Math.max(1, PT(r * 0.75)), Math.max(1, PT(b + dy)), Math.max(1, PT(l * 0.75))];
}
function addTable(slide, t) {
  const rows = t.grid.map(r => r.map(c => ({
    text: toRuns(c.runs).length ? toRuns(c.runs) : '',
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
    else if (it.type === 'image') slide.addImage({ path: rasterFile.get(it.raster), x: X(it.rect.x), y: X(it.rect.y), w: X(it.rect.w), h: X(it.rect.h) });
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
