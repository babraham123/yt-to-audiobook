"""The EPUB 3 with Media Overlays: chapters from the cues, and the XHTML, SMIL and package."""

import bisect
import re
import time
import xml.etree.ElementTree as ET
import zipfile

PART_SECONDS = 600
ACTIVE_CLASS = "-epub-media-overlay-active"


def chapter_starts(info, cuts, total):
    """(start on the cut clock, title) per chapter: SponsorBlock chapter segments, else the
    video's own chapters, else one every ten minutes."""
    marked = [
        (s["start_time"], s.get("title") or "")
        for s in info.get("sponsorblock_chapters") or []
        if s.get("type") == "chapter"
    ]
    own = [(c["start_time"], c.get("title") or "") for c in info.get("chapters") or []]
    found = marked or own
    if found:
        starts = sorted((cuts.shift(t), title) for t, title in found)
        if starts[0][0] > 0:
            starts.insert(0, (0.0, ""))
        return starts
    return [(float(t), "") for t in range(0, max(1, int(total)), PART_SECONDS)]


def clock(t):
    ms = round(t * 1000)
    return f"{ms // 3600000}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def minutes(t):
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02}:{t % 60:02}" if t >= 3600 else f"{t // 60}:{t % 60:02}"


def chapters(cues, starts):
    """[(title, cues)], dropping chapters a cut left without cues."""
    at = [s for s, _ in starts]
    groups = [[] for _ in starts]
    for c in cues:
        groups[max(0, bisect.bisect_right(at, c.start) - 1)].append(c)
    out = []
    for (start, title), group in zip(starts, groups):
        if group:
            out.append((title or f"{minutes(start)} to {minutes(group[-1].end)}", group))
    return out


OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
XHTML = "http://www.w3.org/1999/xhtml"
OPS = "http://www.idpf.org/2007/ops"
SMIL = "http://www.w3.org/ns/SMIL"


def sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(
        parent, tag, {k.replace("__", ":").replace("_", "-"): v for k, v in attrs.items()}
    )
    el.text = text
    return el


def xml(root, doctype=False):
    head = '<?xml version="1.0" encoding="utf-8"?>\n'
    if doctype:
        head += "<!DOCTYPE html>\n"
    return (head + ET.tostring(root, encoding="unicode") + "\n").encode()


def xhtml_doc(title, lang):
    root = ET.Element("html", {"xmlns": XHTML, "xmlns:epub": OPS, "lang": lang, "xml:lang": lang})
    head = sub(root, "head")
    sub(head, "meta", charset="utf-8")
    sub(head, "title", title)
    sub(head, "link", rel="stylesheet", type="text/css", href="../style.css")
    return root, sub(root, "body")


def build_epub(path, meta, audio, cover, parts, lang):
    """An EPUB 3 with Media Overlays: one XHTML and one SMIL per chapter, a <p> per cue and a
    <par> per <p> playing that cue's span of the one audio file."""
    vid = meta["id"]
    audio_href = f"audio/{vid}.m4a"
    files = []
    manifest = []
    spine = []
    durations = []
    toc = []
    n = 0
    for i, (title, cues) in enumerate(parts, 1):
        name = f"ch{i:03}"
        doc, body = xhtml_doc(title, lang)
        # A fragment on the textref: epubcheck 4.2 (Ubuntu's) rejects a bare file reference.
        section = sub(body, "section", epub__type="chapter", id=name)
        sub(section, "h2", title, id=f"{name}-title")
        smil = ET.Element("smil", {"xmlns": SMIL, "xmlns:epub": OPS, "version": "3.0"})
        seq = sub(
            sub(smil, "body"),
            "seq",
            id=f"{name}-seq",
            epub__textref=f"../text/{name}.xhtml#{name}",
            epub__type="chapter",
        )
        for c in cues:
            n += 1
            pid = f"cue{n:05}"
            sub(section, "p", c.text, id=pid)
            par = sub(seq, "par", id=f"par{n:05}")
            sub(par, "text", src=f"../text/{name}.xhtml#{pid}")
            sub(
                par, "audio", src=f"../{audio_href}", clipBegin=clock(c.start), clipEnd=clock(c.end)
            )
        files += [
            (f"OEBPS/text/{name}.xhtml", xml(doc, doctype=True)),
            (f"OEBPS/smil/{name}.smil", xml(smil)),
        ]
        manifest += [
            {
                "id": name,
                "href": f"text/{name}.xhtml",
                "media-type": "application/xhtml+xml",
                "media-overlay": f"{name}-smil",
            },
            {
                "id": f"{name}-smil",
                "href": f"smil/{name}.smil",
                "media-type": "application/smil+xml",
            },
        ]
        spine.append(name)
        durations.append((f"{name}-smil", sum(c.end - c.start for c in cues)))
        toc.append((f"text/{name}.xhtml", title))

    nav, body = xhtml_doc(meta["title"], lang)
    for el in nav.iter("link"):
        el.set("href", "style.css")
    ol = sub(sub(body, "nav", epub__type="toc", id="toc"), "ol")
    for href, title in toc:
        sub(sub(ol, "li"), "a", title, href=href)
    files.append(("OEBPS/nav.xhtml", xml(nav, doctype=True)))
    files.append(
        (
            "OEBPS/style.css",
            f".{ACTIVE_CLASS} {{ background-color: rgba(255, 220, 0, 0.4); }}\n".encode(),
        )
    )
    manifest += [
        {
            "id": "nav",
            "href": "nav.xhtml",
            "media-type": "application/xhtml+xml",
            "properties": "nav",
        },
        {"id": "css", "href": "style.css", "media-type": "text/css"},
        {"id": "audio", "href": audio_href, "media-type": "audio/mp4"},
    ]
    if cover:
        manifest.append(
            {
                "id": "cover-image",
                "href": f"images/cover{cover.suffix}",
                "media-type": "image/jpeg" if cover.suffix == ".jpg" else "image/png",
                "properties": "cover-image",
            }
        )

    package = ET.Element(
        "package", {"xmlns": OPF, "version": "3.0", "unique-identifier": "uid", "xml:lang": lang}
    )
    md = sub(package, "metadata", xmlns__dc=DC)
    sub(md, "dc:identifier", f"urn:youtube:{vid}", id="uid")
    sub(md, "dc:title", meta["title"])
    if meta.get("uploader"):
        sub(md, "dc:creator", meta["uploader"])
    sub(md, "dc:source", meta["url"])
    sub(md, "dc:language", lang)
    if re.match(r"^\d{8}$", meta.get("upload_date") or ""):
        d = meta["upload_date"]
        sub(md, "dc:date", f"{d[:4]}-{d[4:6]}-{d[6:]}")
    if meta.get("description"):
        sub(md, "dc:description", meta["description"])
    sub(md, "meta", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), property="dcterms:modified")
    # The total is the sum of the overlays, as EPUB checkers expect, not the file's length.
    sub(md, "meta", clock(sum(d for _, d in durations)), property="media:duration")
    for ref, d in durations:
        sub(md, "meta", clock(d), property="media:duration", refines=f"#{ref}")
    sub(md, "meta", ACTIVE_CLASS, property="media:active-class")
    if cover:
        sub(md, "meta", name="cover", content="cover-image")
    items = sub(package, "manifest")
    for item in manifest:
        ET.SubElement(items, "item", item)
    spine_el = sub(package, "spine")
    for idref in spine:
        sub(spine_el, "itemref", idref=idref)

    container = ET.Element(
        "container", {"xmlns": "urn:oasis:names:tc:opendocument:xmlns:container", "version": "1.0"}
    )
    sub(
        sub(container, "rootfiles"),
        "rootfile",
        full_path="OEBPS/package.opf",
        media_type="application/oebps-package+xml",
    )

    with zipfile.ZipFile(path, "w") as z:
        # Readers sniff the type from an uncompressed mimetype as the archive's first entry.
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", xml(container), zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/package.opf", xml(package), zipfile.ZIP_DEFLATED)
        for name, data in files:
            z.writestr(name, data, zipfile.ZIP_DEFLATED)
        # Already compressed; stored, the reader can seek in the audio without inflating it.
        z.write(audio, f"OEBPS/{audio_href}", zipfile.ZIP_STORED)
        if cover:
            z.write(cover, f"OEBPS/images/cover{cover.suffix}", zipfile.ZIP_STORED)
