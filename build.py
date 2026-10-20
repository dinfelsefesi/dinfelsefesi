#!/usr/bin/env python3
"""dinfelsefesi.com.tr statik site üreticisi.

content/makaleler.json dosyasını okur, site/ klasörüne HTML, RSS ve JSON üretir.
Bağımlılık yok, yalnızca Python 3 standart kütüphanesi.
"""
import html
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).parent
CONTENT = ROOT / "content" / "makaleler.json"
OUT = ROOT / "site"
SITE_URL = os.environ.get("SITE_URL", "https://dinfelsefesi.com.tr").rstrip("/")
# Deneme yayınlarında arama motorlarının sayfaları listelememesi için
NOINDEX = os.environ.get("NOINDEX") == "1"
SITE_NAME = "Din Felsefesi"
SITE_TAGLINE = "İngilizce din felsefesi literatüründen yeni makalelerin Türkçe tanıtımı"
EDITOR = "Abdullah Akgül"

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def slugify(text: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosucgiosuaiu")
    text = text.translate(table)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:80]


def tr_date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.day} {AYLAR[d.month - 1]} {d.year}"


def e(s: str) -> str:
    return html.escape(s or "", quote=True)


def paragraphs(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join(f"<p>{e(p)}</p>" for p in parts)


CSS = """
:root{
  --ink:#1c2333;--ink-soft:#4a5368;--rule:#d9dde5;--paper:#ffffff;--panel:#f3f5f8;
  --accent:#0f6b5f;--accent-ink:#0b5048;--gold:#a9872f;
  --measure:66ch;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ink:#e6e9ef;--ink-soft:#aab2c2;--rule:#2d3444;--paper:#12161f;--panel:#1a2030;
    --accent:#5fc3b2;--accent-ink:#8fd9cc;--gold:#d2b15c;
  }
}
*{box-sizing:border-box}
html{font-size:17px}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Literata",Georgia,"Times New Roman",serif;line-height:1.6;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent-ink);text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.wrap{max-width:52rem;margin:0 auto;padding:0 16px}
header.site{padding:2.6rem 0 1.6rem;border-bottom:1px solid var(--rule)}
header.site .name{font-size:2.3rem;font-weight:500;letter-spacing:-.01em;margin:0;line-height:1.1}
header.site .name a{color:inherit;text-decoration:none}
header.site .tag{margin:.5rem 0 0;color:var(--ink-soft);font-size:1rem;max-width:var(--measure)}
nav.top{margin-top:1.1rem;font-size:.95rem}
nav.top a{margin-right:1.2rem}
main{padding:1.8rem 0 3rem}
.entry{display:grid;grid-template-columns:7.5rem 1fr;gap:0 1.5rem;
  padding:1.6rem 0;border-bottom:1px solid var(--rule)}
.entry time{color:var(--ink-soft);font-size:.92rem;padding-top:.35rem;font-variant-numeric:tabular-nums}
.entry h2{margin:0;font-size:1.35rem;font-weight:500;line-height:1.3}
.entry h2 a{color:inherit;text-decoration:none}
.entry h2 a:hover{color:var(--accent)}
.entry .orig{margin:.3rem 0 0;color:var(--ink-soft);font-size:.95rem;font-style:italic}
.entry .meta{margin:.35rem 0 0;color:var(--ink-soft);font-size:.92rem}
.entry .lead{margin:.7rem 0 0;max-width:var(--measure)}
.entry .more{display:inline-block;margin-top:.5rem;font-size:.95rem}
@media (max-width:640px){
  html{font-size:16px}
  .entry{grid-template-columns:1fr;gap:.2rem}
  header.site .name{font-size:1.9rem}
}
article.single h1{font-size:1.9rem;font-weight:500;line-height:1.2;margin:0 0 .4rem;max-width:var(--measure)}
article.single .orig{font-style:italic;color:var(--ink-soft);margin:0 0 1rem;max-width:var(--measure)}
.box{background:var(--panel);border-left:3px solid var(--gold);padding:.9rem 1.1rem;margin:1.2rem 0;
  font-size:.95rem;max-width:var(--measure)}
.box dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:.25rem 1rem}
.box dt{color:var(--ink-soft)}
.box dd{margin:0}
article.single .body{max-width:var(--measure)}
article.single .body p{margin:0 0 1rem}
article.single h3{font-size:1.05rem;font-weight:600;margin:1.6rem 0 .5rem;color:var(--accent-ink)}
.tags{margin-top:1.4rem;font-size:.9rem;color:var(--ink-soft)}
.tags span{display:inline-block;margin-right:.8rem}
footer.site{border-top:1px solid var(--rule);padding:1.4rem 0 2.4rem;color:var(--ink-soft);font-size:.9rem}
footer.site p{margin:.3rem 0;max-width:var(--measure)}
.empty{color:var(--ink-soft);max-width:var(--measure)}
"""


def page(title: str, body: str, desc: str = SITE_TAGLINE, canonical: str = "") -> str:
    canon = f'<link rel="canonical" href="{e(canonical)}">' if canonical else ""
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{'<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""}
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{canon}
<link rel="alternate" type="application/rss+xml" title="{e(SITE_NAME)}" href="{SITE_URL}/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="site">
  <h1 class="name"><a href="{SITE_URL}/">{e(SITE_NAME)}</a></h1>
  <p class="tag">{e(SITE_TAGLINE)}</p>
  <nav class="top"><a href="{SITE_URL}/">Son makaleler</a><a href="{SITE_URL}/hakkinda/">Hakkında</a><a href="{SITE_URL}/rss.xml">RSS</a></nav>
</header>
<main>
{body}
</main>
<footer class="site">
  <p>Editör: {e(EDITOR)}. Tanıtımlar özgün makalelerin yerini tutmaz, her kayıt kaynağına bağlantı verir.</p>
  <p>Tüm kayıtlar makine okunabilir biçimde: <a href="{SITE_URL}/api/makaleler.json">api/makaleler.json</a></p>
</footer>
</div>
</body>
</html>"""


def entry_url(m: dict) -> str:
    return f"{SITE_URL}/makale/{m['slug']}/"


def render_index(items: list[dict]) -> str:
    if not items:
        return page(SITE_NAME, '<p class="empty">Henüz kayıt yok. İlk tanıtımlar yakında eklenecek.</p>')
    rows = []
    for m in items:
        rows.append(f"""
<section class="entry">
  <time datetime="{e(m['date'])}">{tr_date(m['date'])}</time>
  <div>
    <h2><a href="{entry_url(m)}">{e(m['title_tr'])}</a></h2>
    <p class="orig">{e(m['title_en'])}</p>
    <p class="meta">{e(m['authors'])} · {e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</p>
    <p class="lead">{e(m['lead'])}</p>
    <a class="more" href="{entry_url(m)}">Tanıtımı oku</a>
  </div>
</section>""")
    return page(SITE_NAME, "".join(rows), canonical=SITE_URL + "/")


def render_single(m: dict) -> str:
    oa = {"evet": "Açık erişim", "hayır": "Abonelik gerekli"}.get(m.get("open_access", ""), "")
    link = m.get("doi") and f"https://doi.org/{m['doi']}" or m.get("url", "")
    body = f"""
<article class="single">
  <p class="meta"><time datetime="{e(m['date'])}">{tr_date(m['date'])}</time></p>
  <h1>{e(m['title_tr'])}</h1>
  <p class="orig">{e(m['title_en'])}</p>
  <div class="box"><dl>
    <dt>Yazar</dt><dd>{e(m['authors'])}</dd>
    <dt>Dergi</dt><dd>{e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</dd>
    <dt>Kaynak</dt><dd><a href="{e(link)}" rel="noopener">{e(link)}</a>{(' · ' + oa) if oa else ''}</dd>
  </dl></div>
  <div class="body">
    {paragraphs(m['summary_tr'])}
    <h3>Neden önemli</h3>
    {paragraphs(m['why_tr'])}
  </div>
  <div class="tags">{''.join(f'<span>#{e(t)}</span>' for t in m.get('tags', []))}</div>
</article>"""
    return page(f"{m['title_tr']} · {SITE_NAME}", body, desc=m["lead"], canonical=entry_url(m))


ABOUT = f"""
<article class="single">
  <h1>Hakkında</h1>
  <div class="body">
    <p>{SITE_NAME}, İngilizce din felsefesi dergilerinde yayımlanan yeni makaleleri düzenli olarak tarar ve her birini Türkçe bir tanıtımla sunar. Amaç, Türkçe okurun güncel tartışmaları zamanında ve kaynağına giderek izleyebilmesidir.</p>
    <p>Tanıtımlar makalenin iddiasını, yöntemini ve literatürdeki yerini aktarır; makalenin yerine geçmez. Her kayıtta özgün metne bağlantı bulunur.</p>
    <p>Editör: {EDITOR}, Erciyes Üniversitesi İlahiyat Fakültesi, Din Felsefesi.</p>
  </div>
</article>"""


def main() -> None:
    items = json.loads(CONTENT.read_text(encoding="utf-8"))
    for m in items:
        m.setdefault("slug", slugify(m["title_tr"]))
    items.sort(key=lambda m: m["date"], reverse=True)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "makale").mkdir(parents=True)
    (OUT / "api").mkdir()
    (OUT / "hakkinda").mkdir()

    (OUT / "index.html").write_text(render_index(items), encoding="utf-8")
    (OUT / "hakkinda" / "index.html").write_text(page(f"Hakkında · {SITE_NAME}", ABOUT), encoding="utf-8")
    for m in items:
        d = OUT / "makale" / m["slug"]
        d.mkdir()
        (d / "index.html").write_text(render_single(m), encoding="utf-8")

    (OUT / "api" / "makaleler.json").write_text(
        json.dumps([{**m, "url": entry_url(m)} for m in items], ensure_ascii=False, indent=1),
        encoding="utf-8")

    now = format_datetime(datetime.now(timezone.utc))
    rss_items = "".join(f"""
<item>
<title>{e(m['title_tr'])}</title>
<link>{entry_url(m)}</link>
<guid>{entry_url(m)}</guid>
<pubDate>{format_datetime(datetime.strptime(m['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc))}</pubDate>
<description>{e(m['lead'])}</description>
</item>""" for m in items)
    (OUT / "rss.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>{e(SITE_NAME)}</title>
<link>{SITE_URL}/</link>
<description>{e(SITE_TAGLINE)}</description>
<language>tr</language>
<lastBuildDate>{now}</lastBuildDate>{rss_items}
</channel></rss>
""", encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    cname = ROOT / "CNAME"
    if cname.exists():
        shutil.copy(cname, OUT / "CNAME")
    print(f"{len(items)} kayıt, çıktı: {OUT}")


if __name__ == "__main__":
    main()
