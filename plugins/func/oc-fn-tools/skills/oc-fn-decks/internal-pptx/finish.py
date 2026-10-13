#!/usr/bin/env python3
"""finish.py — last pass over the PPTX that build.js wrote.

Called by render-internal-pptx.sh; not meant to be run by hand.
    finish.py <deck.pptx> <fonts_dir>

1. **One <a:pPr> per paragraph.** pptxgenjs writes paragraph properties once per text run,
   so a paragraph mixing bold and plain runs carries several. That is invalid OOXML, and
   LibreOffice applies the last one (no bullet). The first one, written for the paragraph's
   first run, is kept. A bullet gets a font (pptxgenjs sets none, and a symbol font draws it
   small and raised) at 125 %, like a CSS marker: a disc takes the text's font; a circle or a
   square takes Arial, because the brand fonts lack those glyphs and a renderer's fallback can be
   an emoji font about twice as wide. measure.js measures the markers in the same fonts.
   (A marker takes its size, weight and colour from the first run: build.js opens an item whose
   first run is not in the item's font — an inline box, bold text — on a zero-width space that is.)
   A marker that is a no-break space is no marker: build.js writes one for text that continues an
   item after its nested list, to get the item's left margin; it becomes <a:buNone/> with no
   hanging indent, so the text starts at that margin.
2. **Nested list items hang their marker like the top level.** pptxgenjs ties a paragraph's
   hanging indent to its left margin (marL = indent × (level + 1)), so build.js picks each nested
   item's indent to put marL where Chromium starts its text; here every bulleted paragraph with
   a level gets back the hanging indent of the first top-level bulleted paragraph of its text
   body — the list's hang.
3. **Hyperlink colour.** PowerPoint draws links in the theme's hlink colour, so the theme takes
   the colour the deck gives its links.
4. **Embed the fonts the deck uses** when fonts_dir holds them, as
   <Family without spaces>-{Regular,Bold,Italic,BoldItalic}.ttf. PowerPoint reads a raw TTF
   as .fntdata. The entry slots follow the schema order (regular, bold, italic, boldItalic):
   validate.py rejects any other order.
"""
import html
import os
import re
import shutil
import sys
import tempfile
import zipfile

FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
SLOTS = [("regular", "Regular"), ("bold", "Bold"), ("italic", "Italic"), ("boldItalic", "BoldItalic")]


NBSP_BULLET = re.compile(r'<a:buSzPct val="100000"/><a:buChar char="&#x00A0;"/>')


def one_ppr(xml):
    def para(m):
        seen = []

        def keep(p):
            if seen:
                return ""
            seen.append(1)
            return p.group(0)
        p = re.sub(r"<a:pPr\b[^>]*?(?:/>|>.*?</a:pPr>)", keep, m.group(0), flags=re.S)
        if NBSP_BULLET.search(p):
            p = NBSP_BULLET.sub("<a:buNone/>", p, count=1)
            p = re.sub(r'(<a:pPr\b[^>]*?) indent="-\d+"', r'\1 indent="0"', p, count=1)
        face = re.search(r'<a:latin typeface="([^"]+)"', p)
        bu = re.search(r'<a:buChar char="([^"]*)"', p)
        if face and bu and "<a:buFont" not in p:
            disc = html.unescape(bu.group(1)) == "\u2022"
            p = re.sub(r'<a:buSzPct val="100000"/>(<a:buChar )',
                       rf'<a:buSzPct val="125000"/><a:buFont typeface="{face.group(1) if disc else "Arial"}"/>\1', p, count=1)
        return p
    return re.sub(r"<a:p>.*?</a:p>", para, xml, flags=re.S)


PPR = re.compile(r"<a:pPr\b([^>]*?)(?<!/)>(.*?)</a:pPr>", flags=re.S)
BULLET = re.compile(r"<a:bu(?:Char|AutoNum)\b")


def nested_hang(xml):
    def body(m):
        b = m.group(0)
        hang = next((ind.group(1) for pp in PPR.finditer(b)
                     if ' lvl="' not in pp.group(1) and BULLET.search(pp.group(2))
                     for ind in [re.search(r' indent="-(\d+)"', pp.group(1))] if ind), None)
        if hang is None:
            return b

        def fix(pp):
            attrs = pp.group(1)
            if ' lvl="' in attrs and BULLET.search(pp.group(2)):
                attrs = re.sub(r' indent="-\d+"', f' indent="-{hang}"', attrs)
            return f"<a:pPr{attrs}>{pp.group(2)}</a:pPr>"
        return PPR.sub(fix, b)
    return re.sub(r"<p:txBody>.*?</p:txBody>", body, xml, flags=re.S)


def embed(root, fonts_dir):
    parts = [os.path.join(dp, f) for d in ("slides", "slideLayouts", "slideMasters")
             for dp, _, fs in os.walk(os.path.join(root, "ppt", d)) for f in fs if f.endswith(".xml")]
    used = set()
    for p in parts:
        used |= set(re.findall(r'<a:latin typeface="([^"+][^"]*)"', open(p, encoding="utf-8").read()))
    entries, rels, done = [], [], []
    rid, fno = 9000, 0
    for face in sorted(used):
        files = [os.path.join(fonts_dir, f"{face.replace(' ', '')}-{suffix}.ttf") for _, suffix in SLOTS]
        if not all(os.path.exists(f) for f in files):
            continue
        os.makedirs(os.path.join(root, "ppt", "fonts"), exist_ok=True)
        slots = []
        for (slot, _), src in zip(SLOTS, files):
            fno += 1
            rid += 1
            shutil.copy(src, os.path.join(root, "ppt", "fonts", f"font{fno}.fntdata"))
            rels.append(f'<Relationship Id="rId{rid}" Type="{FONT_REL}" Target="fonts/font{fno}.fntdata"/>')
            slots.append(f'<p:{slot} r:id="rId{rid}"/>')
        entries.append(f'<p:embeddedFont><p:font typeface="{face}"/>{"".join(slots)}</p:embeddedFont>')
        done.append(face)
    if not entries:
        return done
    ct = os.path.join(root, "[Content_Types].xml")
    xml = open(ct, encoding="utf-8").read()
    if "fntdata" not in xml:
        xml = xml.replace("<Default", '<Default Extension="fntdata" ContentType="application/x-fontdata"/><Default', 1)
        open(ct, "w", encoding="utf-8").write(xml)
    rp = os.path.join(root, "ppt", "_rels", "presentation.xml.rels")
    xml = open(rp, encoding="utf-8").read()
    open(rp, "w", encoding="utf-8").write(xml.replace("</Relationships>", "".join(rels) + "</Relationships>", 1))
    pp = os.path.join(root, "ppt", "presentation.xml")
    xml = open(pp, encoding="utf-8").read()
    if "embedTrueTypeFonts" not in xml:
        xml = xml.replace("<p:presentation ", '<p:presentation embedTrueTypeFonts="1" ', 1)
    m = re.search(r"<p:notesSz[^/]*/>", xml)       # CT_Presentation: embeddedFontLst follows notesSz
    if not m:
        sys.exit("finish.py: notesSz not found in presentation.xml")
    xml = xml.replace(m.group(0), m.group(0) + "<p:embeddedFontLst>" + "".join(entries) + "</p:embeddedFontLst>", 1)
    open(pp, "w", encoding="utf-8").write(xml)
    return done


def link_colour(root):
    """Set the theme's hyperlink colours to the colour the deck gives its links.

    PowerPoint paints hyperlinks in the theme's hlink colour, whatever the run says.
    """
    seen = {}
    for dp, _, fs in os.walk(os.path.join(root, "ppt", "slides")):
        for f in fs:
            if f.endswith(".xml"):
                xml = open(os.path.join(dp, f), encoding="utf-8").read()
                for rpr in re.findall(r"<a:rPr\b[^>]*>(?:(?!</a:rPr>).)*<a:hlinkClick\b(?:(?!</a:rPr>).)*</a:rPr>", xml, flags=re.S):
                    m = re.search(r'<a:solidFill><a:srgbClr val="([0-9A-F]{6})"', rpr)
                    if m:
                        seen[m.group(1)] = seen.get(m.group(1), 0) + 1
    if not seen:
        return None
    hexval = max(seen, key=seen.get)
    for dp, _, fs in os.walk(os.path.join(root, "ppt", "theme")):
        for f in fs:
            p = os.path.join(dp, f)
            xml = open(p, encoding="utf-8").read()
            for tag in ("hlink", "folHlink"):
                xml = re.sub(rf"<a:{tag}>.*?</a:{tag}>", f'<a:{tag}><a:srgbClr val="{hexval}"/></a:{tag}>', xml, flags=re.S)
            open(p, "w", encoding="utf-8").write(xml)
    return hexval


def main():
    deck, fonts_dir = sys.argv[1], sys.argv[2]
    tmp = tempfile.mkdtemp(prefix="ocpptx-")
    try:
        with zipfile.ZipFile(deck) as z:
            z.extractall(tmp)
        for d in ("slides", "slideLayouts", "slideMasters"):
            base = os.path.join(tmp, "ppt", d)
            for f in os.listdir(base) if os.path.isdir(base) else []:
                if f.endswith(".xml"):
                    p = os.path.join(base, f)
                    xml = open(p, encoding="utf-8").read()
                    open(p, "w", encoding="utf-8").write(nested_hang(one_ppr(xml)))
        done = embed(tmp, fonts_dir)
        link = link_colour(tmp)
        with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(tmp, "[Content_Types].xml"), "[Content_Types].xml")
            for root, _, files in os.walk(tmp):
                for f in sorted(files):
                    rel = os.path.relpath(os.path.join(root, f), tmp)
                    if rel != "[Content_Types].xml":
                        z.write(os.path.join(root, f), rel)
        print(f"finished {os.path.basename(deck)}: fonts embedded: {', '.join(done) or 'none'}"
              + (f"; links #{link}" if link else ""))
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
