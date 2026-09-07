#!/usr/bin/env python3
"""
build-papers-pdf.py — UniDPP papers PDF builder (HTML -> PDF).

Adapted from the oimlsmart/idta-dpp pipeline (branded HTML -> PDF with a
full-bleed cover plus a paginated, footed body), with two deliberate
differences:

  1. Typographic cover. UniDPP has no organization SVGs yet, so the cover
     is set in type: a UniDPP wordmark, badge, eyebrow, title, lede, and
     a foot block carrying the date and attribution lines. When logos
     exist they can replace the wordmark block without touching the rest.

  2. Renderer. The primary path is playwright driving chromium; if
     playwright is not importable (or its browser fails to launch), a
     documented fallback shells out to a chrome/chromium binary with
     --headless --print-to-pdf. The fallback cannot emit the custom
     running footer (no footer-template support in the CLI), so the body
     is printed without page numbers there.

Usage:
    python3 build-papers-pdf.py SRC.html OUT.pdf [options]

Options:
    --badge TEXT     cover badge pill          (default: UNIDPP CONTRIBUTION)
    --eyebrow TEXT   mono eyebrow above title  (default: ISO/IEC JTC 5 · ...)
    --title TEXT     cover title; "\\n" is a line break (default: paper's <h1>)
    --lede TEXT      cover lede paragraph      (default: omitted)
    --date TEXT      date line in cover foot   (default: today)
    --attr TEXT      attribution line in cover foot
    --footer TEXT    running footer, body pages (left; page x/y on right)
    --check          verify the toolchain only; no conversion

Example:
    python3 build-papers-pdf.py an-international-framework-for-the-dpp.html \\
        pdf/an-international-framework-for-the-dpp.pdf \\
        --badge 'LIAISON CONTRIBUTION' \\
        --title 'An international framework\\nfor the Digital Product Passport' \\
        --lede 'Fourteen design invariants and a profile (lens) model.' \\
        --date 2026-09-07 \\
        --attr 'UniDPP — CalConnect · ISO/TC 154 · OIML · ELF' \\
        --footer 'UniDPP · Paper 1 of 6'

Exit status: 0 on success (or a passing --check), 1 on any failure.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

DEFAULT_BADGE = "UNIDPP CONTRIBUTION"
DEFAULT_EYEBROW = "ISO/IEC JTC 5 · DIGITAL PRODUCT PASSPORT"
DEFAULT_ATTR = "UniDPP — convened under CalConnect, multi-body stewardship"


def find_chrome():
    """Locate a chromium-family binary; honour $UNIDPP_CHROME first."""
    env = os.environ.get("UNIDPP_CHROME")
    if env and os.path.exists(env):
        return env
    for name in ("chromium", "chromium-browser", "chrome", "google-chrome",
                 "headless_shell", "chrome-headless-shell"):
        path = shutil.which(name)
        if path:
            return path
    patterns = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        os.path.expanduser(
            "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/"
            "Chromium.app/Contents/MacOS/Chromium"),
        os.path.expanduser(
            "~/Library/Caches/ms-playwright/chromium_headless_shell-*/"
            "chrome-mac/headless_shell"),
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
        os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/"
                           "chrome-linux/headless_shell"),
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern), reverse=True)
        if hits:
            return hits[0]
    return None


def merge_pdfs(parts, out):
    """Merge part PDFs into `out`; pdfunite preferred, pypdf as fallback."""
    if shutil.which("pdfunite"):
        subprocess.run(["pdfunite"] + parts + [out], check=True)
        return "pdfunite"
    try:
        from pypdf import PdfWriter
    except ImportError:
        try:
            from PyPDF2 import PdfWriter
        except ImportError:
            sys.exit("no PDF merger available: install poppler (pdfunite) or pypdf")
    writer = PdfWriter()
    for part in parts:
        writer.append(part)
    with open(out, "wb") as handle:
        writer.write(handle)
    return "pypdf"


PRINT_CSS = """
@page { size: A4; margin: 20mm 24mm 22mm 24mm; }
@page cover { margin: 0; }
html, body { background: #fff !important; }
body { background-image: none !important; }
.wrap { max-width: 100%; padding: 0; }
main.wrap { padding: 0; }
.cover {
  page: cover; page-break-after: always;
  background: linear-gradient(155deg, #060e1c 0%, #0a1628 50%, #18294a 100%);
  color: #f5efe4; margin: 0; padding: 30mm 20mm 18mm;
  width: 210mm; height: 297mm; box-sizing: border-box;
  display: flex; flex-direction: column; justify-content: space-between;
}
.cover-mark {
  font-family: 'Fraunces', serif; font-weight: 600; font-size: 26pt;
  letter-spacing: -0.01em; color: #f5efe4; margin-bottom: 2mm;
}
.cover-mark span { color: #8fb8e8; }
.cover-mark-sub {
  font-family: 'IBM Plex Mono', monospace; font-size: 7.5pt;
  letter-spacing: 0.24em; text-transform: uppercase; color: #8d9bb4;
}
.cover-draft {
  display: inline-block; align-self: flex-start;
  font-family: 'IBM Plex Mono', monospace; font-size: 9pt; font-weight: 600;
  letter-spacing: 0.18em; color: #3a2a08; background: #fde68a;
  border: 1px solid #d97706; border-radius: 3px;
  padding: 2.2mm 4mm; margin-bottom: 10mm;
}
.cover-eyebrow {
  font-family: 'IBM Plex Mono', monospace; font-size: 8.5pt;
  letter-spacing: 0.22em; color: #89b4ef; margin-bottom: 7mm;
}
.cover-title {
  font-family: 'Fraunces', serif; font-weight: 500; font-size: 34pt;
  line-height: 1.14; letter-spacing: -0.01em; margin-bottom: 9mm;
}
.cover-lede {
  font-size: 11.5pt; font-weight: 300; color: #c2cad8;
  max-width: 150mm; line-height: 1.6;
}
.cover-rule { height: 1px; background: rgba(137, 180, 239, 0.35); margin: 14mm 0 8mm; }
.cover-foot { display: flex; align-items: flex-end; gap: 8mm; }
.cover-meta { font-size: 8.5pt; color: #8d9bb4; line-height: 1.7; }
header.hero { display: none; }
section { page-break-before: always; margin-bottom: 10mm; }
section#intro, section#scope, section#announce { page-break-before: avoid; }
h2 { font-size: 17pt; page-break-after: avoid; }
h2 .no { font-size: 8pt; }
h3 { page-break-after: avoid; }
p, li { font-size: 9.8pt; }
table { page-break-inside: auto; font-size: 8.8pt; }
tr { page-break-inside: avoid; }
.callout { page-break-inside: avoid; }
footer { padding: 1.5rem 0; }
"""


def build_cover(args):
    """Typographic cover block (no org SVGs yet — wordmark stands in for logos)."""
    title = args.title.replace("\\n", "<br>")
    lede = "<p class=\"cover-lede\">%s</p>" % args.lede if args.lede else ""
    return """
<div class="cover">
<div class="cover-inner">
<div class="cover-mark">Uni<span>DPP</span><div class="cover-mark-sub">Digital Product Passport · multi-body stewardship</div></div>
<div class="cover-draft">%s</div>
<div class="cover-eyebrow">%s</div>
<h1 class="cover-title">%s</h1>
%s
<div class="cover-rule"></div>
<div class="cover-foot">
<div class="cover-meta">
<div>%s</div>
<div>%s</div>
</div>
</div>
</div>
</div>
""" % (args.badge, args.eyebrow, title, lede, args.date, args.attr)


def assemble(src, cover):
    """Split the paper into a cover-only and a body-only document."""
    head_end = src.find("</head>")
    body_open = src.find("<body>")
    body_close = src.find("</body>")
    if -1 in (head_end, body_open, body_close):
        sys.exit("error: source does not look like a complete paper (missing head/body)")
    head = src[:head_end] + "\n<style>\n" + PRINT_CSS + "\n</style>\n</head>"
    body = src[body_open + len("<body>"):body_close]
    cover_doc = head + "\n<body>\n" + cover + "\n</body>\n</html>\n"
    body_doc = head + "\n<body>\n" + body + "</body>\n</html>\n"
    return cover_doc, body_doc


FOOTER_TEMPLATE = (
    "<div style=\"font-family:'IBM Plex Sans',sans-serif;font-size:7pt;"
    "color:#6b7a92;width:100%;padding:0 24mm;display:flex;"
    "justify-content:space-between;\">"
    "<span>__FOOTER__</span>"
    "<span><span class=\"pageNumber\"></span> / <span class=\"totalPages\"></span></span>"
    "</div>"
)


def render_playwright(docs, out_base, footer_text):
    """Primary path: playwright chromium. Returns (part_pdfs, 'playwright')."""
    from playwright.sync_api import sync_playwright
    cover_doc, body_doc = docs
    cover_pdf, body_pdf = out_base + ".cover.pdf", out_base + ".body.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        cover_html = os.path.join(tmp, "cover.html")
        body_html = os.path.join(tmp, "body.html")
        with open(cover_html, "w") as handle:
            handle.write(cover_doc)
        with open(body_html, "w") as handle:
            handle.write(body_doc)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            try:
                page.goto("file://" + cover_html, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(1000)
                page.pdf(path=cover_pdf, format="A4", print_background=True)
                page.goto("file://" + body_html, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(1500)
                page.pdf(path=body_pdf, format="A4", print_background=True,
                         display_header_footer=True,
                         header_template="<div></div>",
                         footer_template=FOOTER_TEMPLATE.replace("__FOOTER__", footer_text))
            finally:
                browser.close()
    return [cover_pdf, body_pdf], "playwright"


def render_chrome(docs, out_base):
    """Fallback path: chrome --headless --print-to-pdf (no custom footer
    template in the CLI; the body prints without page numbers)."""
    chrome = find_chrome()
    if not chrome:
        sys.exit("error: playwright unavailable and no chrome/chromium binary found")
    cover_doc, body_doc = docs
    parts = []
    for name, doc in (("cover", cover_doc), ("body", body_doc)):
        html_path = "%s.%s.html" % (out_base, name)
        pdf_path = "%s.%s.pdf" % (out_base, name)
        with open(html_path, "w") as handle:
            handle.write(doc)
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
               "--print-to-pdf=" + pdf_path, "file://" + html_path]
        try:
            subprocess.run(cmd, check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            cmd = [chrome, "--headless", "--disable-gpu",
                   "--print-to-pdf=" + pdf_path, "file://" + html_path]
            subprocess.run(cmd, check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parts.append(pdf_path)
    return parts, "chrome(%s)" % os.path.basename(chrome)


def derive_title(src):
    """Fall back to the paper's own <h1> (then <title>) when --title is absent."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", src, re.S) or \
        re.search(r"<title>(.*?)</title>", src, re.S)
    if not match:
        sys.exit("error: no --title given and no <h1>/<title> found in source")
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return re.sub(r"\s+", " ", text).strip()


def toolchain_report():
    """Probe every dependency; return (lines, has_renderer, has_merger)."""
    lines = []
    has_renderer = False
    try:
        import playwright  # noqa: F401
        lines.append(("ok", "playwright importable"))
        has_renderer = True
    except Exception as exc:
        lines.append(("--", "playwright NOT importable (%s)" % exc))
    chrome = find_chrome()
    if chrome:
        lines.append(("ok", "chrome binary: %s" % chrome))
        has_renderer = True
    else:
        lines.append(("--", "no chrome/chromium binary found"))
    has_merger = False
    if shutil.which("pdfunite"):
        lines.append(("ok", "pdfunite available"))
        has_merger = True
    else:
        try:
            import pypdf  # noqa: F401
            lines.append(("ok", "pypdf importable (merge fallback)"))
            has_merger = True
        except ImportError:
            lines.append(("--", "no PDF merger (need pdfunite or pypdf)"))
    return lines, has_renderer, has_merger


def run_check():
    print("build-papers-pdf.py --check")
    lines, has_renderer, has_merger = toolchain_report()
    for status, text in lines:
        print("[%s] %s" % (status, text))
    if has_renderer and has_merger:
        print("verdict: render path available — conversion supported")
        return 0
    print("verdict: NO usable render path — install playwright "
          "(pip install playwright; playwright install chromium) or a chrome "
          "binary, plus pdfunite (poppler) or pypdf for merging")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="UniDPP papers PDF builder (HTML -> PDF, typographic cover)")
    parser.add_argument("src", nargs="?", help="source paper HTML")
    parser.add_argument("out", nargs="?", help="output PDF path")
    parser.add_argument("--badge", default=DEFAULT_BADGE,
                        help="cover badge pill (default: %(default)s)")
    parser.add_argument("--eyebrow", default=DEFAULT_EYEBROW,
                        help="mono eyebrow above the title")
    parser.add_argument("--title", default=None,
                        help="cover title; \\n is a line break (default: paper h1)")
    parser.add_argument("--lede", default="", help="cover lede paragraph")
    parser.add_argument("--date", default=time.strftime("%Y-%m-%d"),
                        help="date line in the cover foot")
    parser.add_argument("--attr", default=DEFAULT_ATTR,
                        help="attribution line in the cover foot")
    parser.add_argument("--footer", default=None,
                        help="running footer for body pages (default: UniDPP · <basename>)")
    parser.add_argument("--check", action="store_true",
                        help="verify the toolchain and exit (no conversion)")
    args = parser.parse_args()

    if args.check:
        sys.exit(run_check())
    if not args.src or not args.out:
        parser.error("SRC and OUT are required unless --check is given")

    with open(args.src, encoding="utf-8") as handle:
        src = handle.read()
    if "<body>" not in src or "</html>" not in src:
        sys.exit("error: %s is not a complete paper (needs <body> ... </html>)"
                 % args.src)
    if args.title is None:
        args.title = derive_title(src)
    if args.footer is None:
        args.footer = "UniDPP · %s" % os.path.splitext(os.path.basename(args.src))[0]

    out = os.path.abspath(args.out)
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out_base = os.path.splitext(out)[0]

    docs = assemble(src, build_cover(args))
    try:
        parts, renderer = render_playwright(docs, out_base, args.footer)
    except ImportError:
        print("note: playwright not importable — using chrome fallback "
              "(documented limitation: no running footer in fallback)")
        parts, renderer = render_chrome(docs, out_base)
    except Exception as exc:  # browser missing, launch failure, timeout
        print("note: playwright failed (%s) — trying chrome fallback" % exc)
        parts, renderer = render_chrome(docs, out_base)

    merger = merge_pdfs(parts, out)
    for part in parts:
        os.remove(part)
    for leftover in glob.glob(out_base + ".*.html"):
        os.remove(leftover)
    print("PDF: %s (renderer=%s, merger=%s)" % (out, renderer, merger))


if __name__ == "__main__":
    main()
