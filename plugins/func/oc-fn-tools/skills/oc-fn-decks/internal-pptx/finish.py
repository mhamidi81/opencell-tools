#!/usr/bin/env python3
"""finish.py — last pass over the PPTX that build.js wrote.

Called by render-internal-pptx.sh; not meant to be run by hand.
    finish.py <deck.pptx> <fonts_dir>

1. **One <a:pPr> per paragraph.** pptxgenjs writes paragraph properties once per text run,
   so a paragraph mixing bold and plain runs carries several. That is invalid OOXML, and
   LibreOffice applies the last one (no bullet). The first one, written for the paragraph's
   first run, is kept. A bullet also gets the text's font (pptxgenjs sets none, and a symbol
   font draws it small and raised).
2. **Hyperlink colour.** PowerPoint draws links in the theme's hlink colour, so the theme takes
   the colour the deck gives its links.
3. **Embed the fonts the deck uses** when fonts_dir holds them, as
   <Family without spaces>-{Regular,Bold,Italic,BoldItalic}.ttf. PowerPoint reads a raw TTF
   as .fntdata. The entry slots follow the schema order (regular, bold, italic, boldItalic):
   validate.py rejects any other order.
"""
import os
import re
import shutil
import sys
import tempfile
import zipfile

FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
SLOTS = [("regular", "Regular"), ("bold", "Bold"), ("italic", "Italic"), ("boldItalic", "BoldItalic")]


def one_ppr(xml):
    def para(m):
        seen = []

        def keep(p):
            if seen:
                return ""
            seen.append(1)
            return p.group(0)
        p = re.sub(r"<a:pPr\b[^>]*?(?:/>|>.*?</a:pPr>)", keep, m.group(0), flags=re.S)
        # A bullet without a font is drawn in a symbol font (small and raised in LibreOffice):
        # give it the font of the paragraph's text, a little larger, like a CSS disc.
        face = re.search(r'<a:latin typeface="([^"]+)"', p)
        if face and "<a:buChar" in p and "<a:buFont" not in p:
            p = re.sub(r'<a:buSzPct val="100000"/>(<a:buChar )',
                       rf'<a:buSzPct val="125000"/><a:buFont typeface="{face.group(1)}"/>\1', p, count=1)
        return p
    return re.sub(r"<a:p>.*?</a:p>", para, xml, flags=re.S)


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
                    open(p, "w", encoding="utf-8").write(one_ppr(xml))
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
