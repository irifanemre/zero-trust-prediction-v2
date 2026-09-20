"""docs/mimari-dokuman.md → PDF (WeasyPrint, CSS paged media). Kullanım: python scripts/build_pdf.py <md> <pdf>

Kapak, belge bilgileri, sayfa numaralı içindekiler, bölüm başına yeni sayfa, tekrar eden tablo başlıkları,
koşan başlık/altbilgi, PDF yer imleri, 1.1 düzeltme bloklarının vurgusu.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import markdown

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
VERSION, DATE, COMMIT = "1.2", "Eylül 2026", "0a013cc"

md_text = SRC.read_text(encoding="utf-8")

# --- ön bölüm (kapak/belge bilgileri) ile gövdeyi ayır: ilk '---' satırına kadar olan kısım ön bölümdür
head, body = md_text.split("\n---\n", 1)
title_line = head.splitlines()[0].lstrip("# ").strip()
meta = dict(re.findall(r"^\*\*(.+?):\*\*\s*(.+)$", head, flags=re.M))
intro_paras = [p.strip() for p in re.split(r"\n\s*\n", head) if p.strip() and not p.startswith("#") and not p.startswith("**")]

EXT = ["tables", "fenced_code", "sane_lists", "pymdownx.tilde", "attr_list"]


def render(md_src: str) -> str:
    return markdown.markdown(md_src, extensions=EXT, output_format="html5")


body = re.sub(r"\n## İçindekiler\n.*?\n---\n", "\n", body, count=1, flags=re.S)
body_html = render(body)

# --- başlık kimlikleri (h2/h3) + içindekiler
ids: dict[str, int] = {}


_TR = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def slug(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(_TR)).strip("-") or "b"  # ASCII: WeasyPrint href çözümü için
    n = ids.get(base, 0) + 1
    ids[base] = n
    return base if n == 1 else f"{base}-{n}"


toc_items: list[tuple[int, str, str]] = []


def _head(m: re.Match) -> str:
    level, inner = int(m.group(1)), m.group(2)
    text = html.unescape(re.sub(r"<[^>]+>", "", inner))
    hid = slug(text)
    toc_items.append((level, hid, text))
    return f'<h{level} id="{hid}">{inner}</h{level}>'


body_html = re.sub(r"<h([23])>(.*?)</h\1>", _head, body_html, flags=re.S)

# --- 1.1 / 1.2 düzeltme/not blokları vurgulanır
body_html = re.sub(r"<blockquote>\s*<p><strong>1\.([12])", r'<blockquote class="rev">\n<p><strong>1.\1', body_html)
# (blok içinde tablo ile başlayan düzeltmeler)
body_html = re.sub(
    r"<blockquote>\s*<p><strong>1\.([12]) (düzeltmesi|notu|eki|sınırı|—)",
    r'<blockquote class="rev">\n<p><strong>1.\1 \2',
    body_html,
)
# geniş ASCII diyagramlar / rapor kutuları: sarmadan, küçük punto
body_html = body_html.replace('<pre><code class="language-yaml">', '<pre class="yaml"><code>')

toc_html = "\n".join(
    f'<li class="l{level}"><a href="#{hid}"><span class="t">{html.escape(text)}</span></a></li>' for level, hid, text in toc_items
)

meta_rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{render(v)[3:-4]}</td></tr>" for k, v in meta.items())
intro_html = "".join(f"<p>{render(p)[3:-4]}</p>" for p in intro_paras)

CSS = r"""
@page {
  size: A4;
  margin: 22mm 18mm 20mm 18mm;
  @top-left { content: "Zero Trust Prediction — Mimari Dokümanı"; font: 8pt "Helvetica Neue"; color: #6b7280; }
  @top-right { content: string(chapter); font: 8pt "Helvetica Neue"; color: #6b7280; }
  @bottom-left { content: "Sürüm __VER__ · __DATE__"; font: 8pt "Helvetica Neue"; color: #6b7280; }
  @bottom-right { content: "Sayfa " counter(page) " / " counter(pages); font: 8pt "Helvetica Neue"; color: #6b7280; }
}
@page cover { margin: 0; @top-left { content: none } @top-right { content: none } @bottom-left { content: none } @bottom-right { content: none } }
@page front { @top-right { content: none } }
html { font-family: "Charter", "Georgia", serif; font-size: 10.2pt; line-height: 1.42; color: #1a1f2b; }
body { margin: 0; }
h1, h2, h3, h4 { font-family: "Avenir Next", "Helvetica Neue", sans-serif; color: #111827; line-height: 1.2; }
h2 { font-size: 17pt; font-weight: 600; margin: 0 0 10pt; padding-bottom: 5pt; border-bottom: 1.2pt solid #0f766e; string-set: chapter content(); break-before: page; break-after: avoid; bookmark-level: 1; }
h3 { font-size: 12.5pt; font-weight: 600; margin: 16pt 0 5pt; break-after: avoid; bookmark-level: 2; }
h4 { font-size: 10.5pt; margin: 12pt 0 4pt; }
p { margin: 0 0 7pt; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin: 1.5pt 0; }
a { color: #0b5c56; text-decoration: none; }
strong { font-weight: 700; }
hr { border: 0; border-top: 0.6pt solid #d1d5db; margin: 12pt 0; }
code { font-family: "Menlo", monospace; font-size: 8.3pt; background: #f1f3f6; padding: 0 2pt; border-radius: 2pt; }
pre { font-family: "Menlo", monospace; font-size: 6.9pt; line-height: 1.32; background: #f5f6f8; border: 0.5pt solid #d8dce3; border-radius: 3pt; padding: 7pt 8pt; margin: 6pt 0 10pt; white-space: pre; overflow: hidden; break-inside: avoid; }
pre.yaml { font-size: 7.4pt; white-space: pre; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 11pt; font-family: "Helvetica Neue", sans-serif; font-size: 8.3pt; line-height: 1.3; }
thead { display: table-header-group; }
th, td { border: 0.5pt solid #c9ced8; padding: 3.5pt 5pt; vertical-align: top; text-align: left; }
th { background: #e9edf2; font-weight: 600; }
tr { break-inside: avoid; }
td code, th code { font-size: 7.6pt; }
blockquote { margin: 8pt 0 11pt; padding: 6pt 10pt; border-left: 2pt solid #c9ced8; background: #f8f9fb; }
blockquote p { margin: 0 0 5pt; }
blockquote.rev { border-left-color: #0f766e; background: #eef6f4; break-inside: auto; }
blockquote.rev > p:first-child > strong:first-child { color: #0b5c56; font-family: "Helvetica Neue", sans-serif; font-size: 9pt; }
blockquote table { background: #fff; }
del { color: #6b7280; }
/* kapak */
.cover { page: cover; height: 297mm; box-sizing: border-box; padding: 36mm 24mm 24mm; position: relative; color: #111827; }
.cover .band { position: absolute; left: 0; top: 0; width: 9mm; height: 297mm; background: #0f766e; }
.cover .eyebrow { font-family: "Helvetica Neue", sans-serif; font-size: 9.5pt; letter-spacing: .14em; text-transform: uppercase; color: #0b5c56; margin: 0 0 18pt; }
.cover h1 { font-size: 30pt; font-weight: 700; margin: 0 0 8pt; letter-spacing: -.01em; }
.cover .sub { font-family: "Avenir Next", "Helvetica Neue", sans-serif; font-size: 15pt; font-weight: 500; color: #374151; margin: 0 0 34pt; }
.cover .rule { border-top: 1pt solid #0f766e; width: 60mm; margin: 0 0 20pt; }
.cover table.meta { width: auto; font-size: 9.5pt; margin: 0; }
.cover table.meta th, .cover table.meta td { border: 0; padding: 2.5pt 14pt 2.5pt 0; background: none; }
.cover table.meta th { color: #6b7280; font-weight: 500; }
.cover .foot { position: absolute; left: 24mm; right: 24mm; bottom: 20mm; font-family: "Helvetica Neue", sans-serif; font-size: 8.5pt; color: #6b7280; border-top: .5pt solid #d1d5db; padding-top: 6pt; }
/* ön bölüm */
.front { page: front; }
.front h2 { break-before: auto; }
.front table.meta th { width: 26mm; background: #f4f6f8; }
/* içindekiler */
.toc { page: front; break-before: page; }
.toc ol { list-style: none; padding: 0; margin: 0; }
.toc li { margin: 0; }
.toc li.l2 { margin-top: 5pt; font-family: "Avenir Next", "Helvetica Neue", sans-serif; font-weight: 600; font-size: 9.8pt; }
.toc li.l3 { font-size: 9pt; padding-left: 14pt; font-family: "Charter", serif; }
.toc a { display: block; overflow: hidden; color: #1a1f2b; border-bottom: .4pt dotted #cbd5e1; padding: 1.2pt 0; }
.toc a::after { content: target-counter(attr(href), page); float: right; font-family: "Helvetica Neue", sans-serif; font-size: 8.5pt; color: #6b7280; padding-left: 8pt; }
""".replace("__VER__", VERSION).replace("__DATE__", DATE)

page = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>{html.escape(title_line)}</title>
<meta name="author" content="irifanemre"><meta name="description" content="Zero Trust Prediction — Nihai Birleşik Mimari ve Uygulama Dokümanı, sürüm {VERSION}">
<style>{CSS}</style></head><body>
<section class="cover">
  <div class="band"></div>
  <p class="eyebrow">MSSP / MSOC güvenlik analitiği · UEBA + Zero Trust Prediction + Knowledge Graph</p>
  <h1>Zero Trust Prediction</h1>
  <p class="sub">Nihai Birleşik Mimari ve Uygulama Dokümanı</p>
  <div class="rule"></div>
  <table class="meta">
    <tr><th>Sürüm</th><td><strong>{VERSION}</strong> — Final 1.0 üzerine uygulama ve doğrulama düzeltmeleri</td></tr>
    <tr><th>Tarih</th><td>{DATE}</td></tr>
    <tr><th>Kapsam</th><td>{html.escape(meta.get("Kapsam", ""))}</td></tr>
    <tr><th>Referans uygulama</th><td><code>zero-trust-prediction</code> · <code>docs/mimari-dokuman.md</code> ({COMMIT})</td></tr>
    <tr><th>Doğrulama</th><td>CERT Insider Threat Test Dataset r4.2 · sentetik regresyon · 82 otomatik test</td></tr>
  </table>
  <div class="foot">Bu belge Final 1.0 metnini korur; uygulama ve CERT doğrulamasıyla değişen noktalar bölüm içinde “1.1 düzeltmesi” bloklarıyla işaretlenmiştir. Sayısal eşikler kalibrasyon başlangıç değerleridir.</div>
</section>
<section class="front">
  <h2>Belge bilgileri</h2>
  <table class="meta">{meta_rows}</table>
  {intro_html}
</section>
<section class="toc">
  <h2>İçindekiler</h2>
  <ol>{toc_html}</ol>
</section>
<section class="body">
{body_html}
</section>
</body></html>"""

html_path = OUT.with_suffix(".html")
html_path.write_text(page, encoding="utf-8")

from weasyprint import HTML  # noqa: E402

HTML(string=page, base_url=str(SRC.parent)).write_pdf(str(OUT))
print("ok", OUT, OUT.stat().st_size // 1024, "KB")
