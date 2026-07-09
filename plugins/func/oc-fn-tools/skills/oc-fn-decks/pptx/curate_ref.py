#!/usr/bin/env python3
"""Curate the official Opencell slide template into a pandoc reference doc.

Takes the marketing-owned template .pptx and produces a reference .pptx that
pandoc's --reference-doc understands:
  1. renames the seven layouts pandoc addresses to their required English names;
  2. rewires the cover layout so pandoc's Title Slide fills it (ctrTitle placed
     below the Opencell logo, white text on the red background; subtitle retyped);
  3. embeds the brand fonts (Montserrat, Playfair Display) so generated decks
     render identically on machines without them.

Usage: curate_ref.py <source.pptx> <output-ref.pptx> [fonts_dir]
       fonts_dir must hold: Montserrat-{Regular,Italic,Bold,BoldItalic}.ttf
                            PlayfairDisplay-{Regular,Italic,Bold,BoldItalic}.ttf
       (omit fonts_dir to skip embedding)
"""
import os
import re
import shutil
import sys
import tempfile
import zipfile

# template layout name -> pandoc-required name (matching is case-insensitive,
# but English-only: unrenamed layouts silently fall back to pandoc's default design)
RENAMES = {
    "Introduction 25/10/24": "Title Slide",
    "Vide": "Blank",
    "Titre et contenu 25/10/24": "Title and Content",
    "Deux contenus 25/10/24": "Two Content",
    "Comparaison": "Comparison",
    "Contenu avec légende": "Content with Caption",
    # template's example slide 2 uses this photo layout as its section divider
    "1_image gauche mur_31/10/24": "Section Header",
}

# Cover geometry (EMU), read from the template: logo "Graphique 5" sits at
# x=812786, y=1163039..1732206; the subtitle placeholder starts at y=3527066.
CTR_TITLE = (
    '<p:sp><p:nvSpPr><p:cNvPr id="90" name="Title 90"/>'
    '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    '<p:nvPr><p:ph type="ctrTitle"/></p:nvPr></p:nvSpPr>'
    '<p:spPr><a:xfrm><a:off x="812786" y="1900000"/>'
    '<a:ext cx="9792621" cy="1500000"/></a:xfrm></p:spPr>'
    '<p:txBody><a:bodyPr anchor="t"/>'
    '<a:lstStyle><a:lvl1pPr algn="l"><a:defRPr sz="4000" b="1">'
    '<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
    '</a:defRPr></a:lvl1pPr></a:lstStyle>'
    '<a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
)

FONT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
FONT_FACES = [
    ("Montserrat", "Montserrat-{}.ttf"),
    ("Playfair Display", "PlayfairDisplay-{}.ttf"),
]
STYLES = [("regular", "Regular"), ("italic", "Italic"),
          ("bold", "Bold"), ("boldItalic", "BoldItalic")]


def rename_layouts(root):
    renamed = {}
    for f in sorted(os.listdir(os.path.join(root, "ppt/slideLayouts"))):
        if not f.endswith(".xml"):
            continue
        p = os.path.join(root, "ppt/slideLayouts", f)
        xml = open(p, encoding="utf-8").read()
        m = re.search(r'<p:cSld name="([^"]*)"', xml)
        if m and m.group(1) in RENAMES:
            new = RENAMES[m.group(1)]
            open(p, "w", encoding="utf-8").write(
                xml.replace(f'<p:cSld name="{m.group(1)}"', f'<p:cSld name="{new}"', 1))
            renamed[m.group(1)] = (f, new)
    missing = set(RENAMES) - set(renamed)
    if missing:
        sys.exit(f"FATAL: source template lacks expected layouts: {missing} "
                 "(template revision drifted — re-check the mapping)")
    return renamed


def set_xfrm(sp, x, y, cx, cy):
    sp = re.sub(r'<a:off x="-?\d+" y="-?\d+"/>', f'<a:off x="{x}" y="{y}"/>', sp, count=1)
    return re.sub(r'<a:ext cx="\d+" cy="\d+"/>', f'<a:ext cx="{cx}" cy="{cy}"/>', sp, count=1)


def fix_caption_layout(root, renamed):
    """Restack "Content with Caption" — pandoc's pick for text-then-table slides.

    The template's "Contenu avec légende" was designed for a one-word title
    (huge centered box, left) and a small visual (half-width column, right):
    a real slide title wraps onto the caption text and a real table gets
    squeezed. Rebuild it as a full-width stack: the "Title and Content"
    title band, a caption strip under it, the content below.
    """
    tc_file = renamed["Titre et contenu 25/10/24"][0]
    tc_xml = open(os.path.join(root, "ppt/slideLayouts", tc_file), encoding="utf-8").read()
    title_sp = next((m.group(0) for m in re.finditer(r"<p:sp>.*?</p:sp>", tc_xml, re.S)
                     if '<p:ph type="title"' in m.group(0)), None)
    if not title_sp:
        sys.exit("FATAL: no title placeholder on 'Titre et contenu' — layout changed")

    def restack(m):
        sp = m.group(0)
        if '<p:ph type="title"' in sp:
            return title_sp                                  # full-width top band
        if 'idx="2"' in sp:
            return set_xfrm(sp, 838201, 980000, 10515600, 1050000)   # caption strip
        if 'idx="11"' in sp:
            return set_xfrm(sp, 838201, 2150000, 10515600, 3430000)  # content, full width
        return sp

    cwc = os.path.join(root, "ppt/slideLayouts", renamed["Contenu avec légende"][0])
    xml = re.sub(r"<p:sp>.*?</p:sp>", restack,
                 open(cwc, encoding="utf-8").read(), flags=re.S)
    open(cwc, "w", encoding="utf-8").write(xml)


def fix_cover(root, renamed):
    cover = os.path.join(root, "ppt/slideLayouts", renamed["Introduction 25/10/24"][0])
    xml = open(cover, encoding="utf-8").read()
    xml, n = re.subn(r'<p:ph type="body" sz="quarter" idx="29"/>',
                     '<p:ph type="subTitle" idx="1"/>', xml, count=1)
    if n != 1:
        sys.exit("FATAL: cover subtitle placeholder not found — layout structure changed")
    xml = xml.replace("</p:spTree>", CTR_TITLE + "</p:spTree>", 1)
    open(cover, "w", encoding="utf-8").write(xml)


def embed_fonts(root, fonts_dir):
    os.makedirs(os.path.join(root, "ppt/fonts"), exist_ok=True)
    entries, rels = [], []
    rid, fno = 9000, 0
    for typeface, pattern in FONT_FACES:
        slots = []
        for slot, suffix in STYLES:
            src = os.path.join(fonts_dir, pattern.format(suffix))
            if not os.path.exists(src):
                sys.exit(f"FATAL: missing font file {src}")
            fno += 1
            rid += 1
            shutil.copy(src, os.path.join(root, f"ppt/fonts/font{fno}.fntdata"))
            rels.append(f'<Relationship Id="rId{rid}" Type="{FONT_REL_TYPE}" '
                        f'Target="fonts/font{fno}.fntdata"/>')
            slots.append(f'<p:{slot} r:id="rId{rid}"/>')
        entries.append(f'<p:embeddedFont><p:font typeface="{typeface}"/>'
                       + "".join(slots) + "</p:embeddedFont>")

    ct = os.path.join(root, "[Content_Types].xml")
    xml = open(ct, encoding="utf-8").read()
    if "fntdata" not in xml:
        xml = xml.replace("<Default", '<Default Extension="fntdata" '
                          'ContentType="application/x-fontdata"/><Default', 1)
        open(ct, "w", encoding="utf-8").write(xml)

    rp = os.path.join(root, "ppt/_rels/presentation.xml.rels")
    xml = open(rp, encoding="utf-8").read()
    open(rp, "w", encoding="utf-8").write(
        xml.replace("</Relationships>", "".join(rels) + "</Relationships>", 1))

    pp = os.path.join(root, "ppt/presentation.xml")
    xml = open(pp, encoding="utf-8").read()
    if "embedTrueTypeFonts" not in xml:
        xml = xml.replace("<p:presentation ", '<p:presentation embedTrueTypeFonts="1" ', 1)
    # CT_Presentation sequence: embeddedFontLst follows notesSz
    m = re.search(r"<p:notesSz[^/]*/>", xml)
    if not m:
        sys.exit("FATAL: notesSz not found in presentation.xml")
    lst = "<p:embeddedFontLst>" + "".join(entries) + "</p:embeddedFontLst>"
    xml = xml.replace(m.group(0), m.group(0) + lst, 1)
    open(pp, "w", encoding="utf-8").write(xml)


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    fonts_dir = sys.argv[3] if len(sys.argv) == 4 else None

    tmp = tempfile.mkdtemp(prefix="ocref-")
    try:
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        renamed = rename_layouts(tmp)
        fix_cover(tmp, renamed)
        fix_caption_layout(tmp, renamed)
        if fonts_dir:
            embed_fonts(tmp, fonts_dir)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(tmp, "[Content_Types].xml"), "[Content_Types].xml")
            for walk_root, _, files in os.walk(tmp):
                for f in sorted(files):
                    rel = os.path.relpath(os.path.join(walk_root, f), tmp)
                    if rel != "[Content_Types].xml":
                        z.write(os.path.join(walk_root, f), rel)
        for old, (fname, new) in sorted(renamed.items()):
            print(f"  {fname}: {old!r} -> {new!r}")
        print(f"wrote {out} ({os.path.getsize(out):,} bytes; "
              f"fonts {'embedded' if fonts_dir else 'NOT embedded'})")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
