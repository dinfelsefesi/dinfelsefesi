#!/usr/bin/env python3
"""dinfelsefesi.com.tr statik site üreticisi.

Kaynaklar:
  content/makaleler.json      makale tanıtımları
  content/basliklar/*.md      ana ve alt başlıklar
  content/terimler/*.md       terim fişleri
  content/kisiler/*.md        kişi fişleri
  content/eserler/*.md        eser fişleri

Çıktı site/ klasörüne yazılır: HTML sayfaları, rss.xml ve api/*.json.
Bağımlılık: Python 3 ve PyYAML.

Ortam değişkenleri:
  SITE_URL        sitenin kök adresi
  NOINDEX=1       arama motorlarına kapalı deneme yayını
  TASLAK_GOSTER=1 taslak fişleri de "Taslak" etiketiyle göster
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

import yaml

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
OUT = ROOT / "site"
SITE_URL = os.environ.get("SITE_URL", "https://dinfelsefesi.com.tr").rstrip("/")
NOINDEX = os.environ.get("NOINDEX") == "1"
TASLAK_GOSTER = os.environ.get("TASLAK_GOSTER") == "1"
SITE_NAME = "Din Felsefesi"
SITE_TAGLINE = "Din felsefesinin başlıkları, terimleri, kişileri ve eserleri; Türkçe ve uluslararası literatürden seçilmiş tanıtımlar"
EDITOR = "Abdullah Akgül"

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

KLASOR = {"baslik": "basliklar", "terim": "terimler", "kisi": "kisiler", "eser": "eserler"}
TUR_AD = {"baslik": "Başlık", "terim": "Terim", "kisi": "Kişi", "eser": "Eser"}
ALAN_TUR = {
    "basliklar": "baslik", "ust_baslik": "baslik", "alt_basliklar": "baslik", "ilgili_basliklar": "baslik",
    "ilgili_terimler": "terim", "temel_terimler": "terim", "temel_gorusleri": "terim",
    "ilgili_kisiler": "kisi", "temel_kisiler": "kisi", "yazar": "kisi",
    "ilgili_eserler": "eser", "kaynaklar": "eser", "eserleri": "eser", "okuma_listesi": "eser",
}


# ---------------------------------------------------------------- yardımcılar

def slugify(text: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosucgiosuaiu")
    text = text.translate(table)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:80]


TR_SIRA = {c: i for i, c in enumerate("aâbcçdefgğhıiîjklmnoöprsştuüûvyz")}


def tr_anahtar(s: str):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    return [TR_SIRA.get(c, 100 + ord(c)) for c in s]


def tr_date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.day} {AYLAR[d.month - 1]} {d.year}"


def e(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def satir_ici(t) -> str:
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", e(t))


def paragraphs(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    return "".join(f"<p>{e(p)}</p>" for p in parts)


def govde(text: str) -> str:
    out = []
    for blok in re.split(r"\n\s*\n", (text or "").strip()):
        blok = blok.strip()
        if not blok:
            continue
        if blok.startswith("## "):
            out.append(f"<h2>{satir_ici(blok[3:])}</h2>")
        else:
            out.append(f"<p>{satir_ici(blok)}</p>")
    return "".join(out)


def liste(v) -> list:
    if v in (None, ""):
        return []
    if isinstance(v, dict):
        return [x for w in v.values() for x in liste(w)]
    return v if isinstance(v, list) else [v]


# ---------------------------------------------------------------- fişler

def fisleri_oku() -> dict:
    fis = {}
    for tur, klasor in KLASOR.items():
        for f in sorted((CONTENT / klasor).glob("*.md")):
            s = f.read_text(encoding="utf-8")
            parca = s[4:].split("\n---\n", 1)
            h = yaml.safe_load(parca[0].removesuffix("\n---")) or {}
            h["_govde"] = parca[1].strip() if len(parca) > 1 else ""
            h["_tur"] = tur
            if h.get("durum") != "yayinda" and not TASLAK_GOSTER:
                continue
            fis[(tur, h["kimlik"])] = h
    return fis


FIS = {}
GERI = {}
COCUK = {}


def ad(tur, h) -> str:
    return h.get("terim") or h.get("ad") or h.get("baslik") or ""


def fis_url(tur, k) -> str:
    return f"{SITE_URL}/{KLASOR[tur]}/{k}/"


def bag(tur, d) -> str:
    if (tur, d) in FIS:
        return f'<a href="{fis_url(tur, d)}">{e(ad(tur, FIS[(tur, d)]))}</a>'
    return f'<span class="duz">{e(d)}</span>'


def bag_listesi(alan, h, ayrac=", ") -> str:
    return ayrac.join(bag(ALAN_TUR[alan], d) for d in liste(h.get(alan)))


def iliskileri_kur():
    for (tur, k), h in FIS.items():
        for alan, hedef in ALAN_TUR.items():
            for d in liste(h.get(alan)):
                if (hedef, d) in FIS and (hedef, d) != (tur, k):
                    GERI.setdefault((hedef, d), set()).add((tur, k))
        if tur == "baslik" and h.get("ust_baslik"):
            COCUK.setdefault(h["ust_baslik"], []).append(k)


def soy(k) -> set:
    out = {k}
    for c in COCUK.get(k, []):
        out |= soy(c)
    return out


def bagli_fisler(k) -> set:
    hedef = soy(k)
    return {(t, kk) for (t, kk), h in FIS.items() if t != "baslik" and set(liste(h.get("basliklar"))) & hedef}


def sayim_metni(fisler) -> str:
    parca = []
    for t, a in [("terim", "terim"), ("kisi", "kişi"), ("eser", "eser")]:
        n = sum(1 for x, _ in fisler if x == t)
        if n:
            parca.append(f"{n} {a}")
    return " · ".join(parca) if parca else "Henüz fiş yok"


def taslak_etiketi(h) -> str:
    return '<span class="taslak">Taslak</span>' if h.get("durum") != "yayinda" else ""


def yol(k) -> str:
    zincir = []
    while k and ("baslik", k) in FIS:
        zincir.append(k)
        k = FIS[("baslik", k)].get("ust_baslik")
    parcalar = [f'<a href="{SITE_URL}/basliklar/">Başlıklar</a>'] + [bag("baslik", x) for x in reversed(zincir[1:])]
    return " <span aria-hidden='true'>›</span> ".join(parcalar)


# ---------------------------------------------------------------- sayfa iskeleti

CSS = """
/* Yerleşim: üstte site adı ve menü, altında tek okuma sütunu; harita ve dizinlerde
   kart ızgarası. Fişler kütüphane kataloğu kartı gibi: üst sekmede türü, altında künye. */
:root{
  --ink:#1b2230;--ink-soft:#505a6e;--rule:#dde1e8;--paper:#fbfcfd;--panel:#f1f4f7;--card:#ffffff;
  --accent:#0f6b5f;--accent-ink:#0b5048;--accent-soft:#e3f0ed;--gold:#9c7a24;--gold-soft:#f6f0de;
  --serif:"Literata",Georgia,"Times New Roman",serif;
  --sans:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  --measure:68ch;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ink:#e6e9ef;--ink-soft:#a9b1c1;--rule:#2c3343;--paper:#11151d;--panel:#1a2030;--card:#161b26;
  --accent:#5fc3b2;--accent-ink:#8fd9cc;--accent-soft:#16302c;--gold:#d2b15c;--gold-soft:#2a2618;color-scheme:dark}}
:root[data-theme="dark"]{
  --ink:#e6e9ef;--ink-soft:#a9b1c1;--rule:#2c3343;--paper:#11151d;--panel:#1a2030;--card:#161b26;
  --accent:#5fc3b2;--accent-ink:#8fd9cc;--accent-soft:#16302c;--gold:#d2b15c;--gold-soft:#2a2618;color-scheme:dark}
*{box-sizing:border-box}
html{font-size:17px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);line-height:1.62;-webkit-font-smoothing:antialiased}
a{color:var(--accent-ink);text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.wrap{max-width:70rem;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.dar{max-width:46rem}
header.site{border-bottom:1px solid var(--rule);background:var(--card)}
header.site .wrap{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:.6rem 2rem;padding-block:1.3rem 1.1rem}
.marka{text-decoration:none;color:var(--ink);display:flex;flex-direction:column;gap:.1rem}
.marka b{font-weight:500;font-size:1.6rem;letter-spacing:-.01em;line-height:1.1}
.marka small{font-family:var(--sans);font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:var(--gold);font-weight:600}
nav.ana{display:flex;flex-wrap:wrap;gap:.3rem 1.3rem;font-family:var(--sans);font-size:.98rem}
nav.ana a{color:var(--ink-soft);text-decoration:none;padding-block:.2rem;border-bottom:2px solid transparent}
nav.ana a:hover{color:var(--ink)}
nav.ana a[aria-current="page"]{color:var(--ink);border-bottom-color:var(--accent)}
.deneme{background:var(--gold-soft);font-family:var(--sans);font-size:.85rem;color:var(--ink)}
.deneme .wrap{padding-block:.45rem}
main{padding-block:2.2rem 3.5rem}
h1{font-weight:500;font-size:2.1rem;line-height:1.18;margin:0 0 .5rem;text-wrap:balance;letter-spacing:-.01em}
h2{font-weight:600;font-size:1.25rem;line-height:1.3;margin:2rem 0 .7rem;text-wrap:balance}
.ust-etiket{font-family:var(--sans);font-size:.76rem;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-soft);margin:0 0 .45rem;font-weight:600}
.yol{font-family:var(--sans);font-size:.88rem;color:var(--ink-soft);margin:0 0 .6rem}
.yol a{color:var(--ink-soft)}
.giris{font-size:1.1rem;color:var(--ink-soft);max-width:var(--measure);margin:0 0 1.6rem}
.metin{max-width:var(--measure)}
.metin p{margin:0 0 1rem}
.metin h2{color:var(--accent-ink);font-size:1.18rem;margin-top:1.8rem}
.say{font-family:var(--sans);font-size:.86rem;color:var(--ink-soft);font-variant-numeric:tabular-nums}
.taslak{display:inline-block;font-family:var(--sans);font-size:.7rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--gold);border:1px solid currentColor;padding:.02rem .45rem;border-radius:2px;margin-left:.5rem;vertical-align:.2em}
.duz{color:var(--ink)}

/* Ana sayfa */
.acilis{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:2.5rem;align-items:end;padding-bottom:1.8rem;border-bottom:1px solid var(--rule);margin-bottom:2rem}
.acilis h1{font-size:2.4rem}
.acilis p{margin:0;color:var(--ink-soft);font-size:1.08rem;max-width:var(--measure)}
.rakamlar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.5rem;font-family:var(--sans)}
.rakamlar a{display:flex;flex-direction:column;text-decoration:none;color:var(--ink);border-top:2px solid var(--accent);padding-top:.4rem}
.rakamlar b{font-size:1.6rem;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.1}
.rakamlar span{font-size:.85rem;color:var(--ink-soft)}
.bolum-baslik{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin:2.4rem 0 1rem}
.bolum-baslik h2{margin:0;font-size:1.4rem;font-weight:500}
.bolum-baslik a{font-family:var(--sans);font-size:.92rem}

/* Başlık haritası */
.harita{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,19rem),1fr));gap:1rem}
.anakart{min-width:0;background:var(--card);border:1px solid var(--rule);padding:1rem 1.1rem 1.05rem;display:flex;flex-direction:column;gap:.45rem}
.anakart h3{margin:0;font-size:1.1rem;font-weight:600;line-height:1.3}
.anakart h3 a{color:var(--ink);text-decoration:none}
.anakart h3 a:hover{color:var(--accent)}
.anakart.bos h3{font-weight:500}
.anakart p{margin:0;font-size:.93rem;color:var(--ink-soft)}
.olcu{height:4px;background:var(--panel)}
.olcu span{display:block;height:100%;background:var(--accent)}
.altlar{list-style:none;padding:0;margin:.15rem 0 0;display:flex;flex-wrap:wrap;gap:.35rem}
.altlar li{font-family:var(--sans);font-size:.82rem;padding:.08rem .55rem;border:1px solid var(--rule);background:var(--paper)}
.altlar li.dolu{border-color:var(--accent);background:var(--accent-soft)}
.altlar li.plan .duz{color:var(--ink-soft)}
.ilgili{font-family:var(--sans);font-size:.85rem;color:var(--ink-soft)}

/* Listeler */
.liste{list-style:none;margin:0;padding:0;border-top:1px solid var(--rule)}
.liste li{padding:.95rem 0;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:minmax(0,15rem) minmax(0,1fr);gap:.2rem 1.5rem}
.liste .ad{font-weight:600}
.liste .alt-ad{display:block;font-weight:400;font-style:italic;color:var(--ink-soft);font-size:.92rem}
.liste .aciklama{color:var(--ink-soft);font-size:.96rem}
.harf{font-family:var(--sans);font-weight:600;color:var(--gold);font-size:.95rem;margin:1.6rem 0 .3rem}
.makale{padding:1.3rem 0;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:7.5rem minmax(0,1fr);gap:0 1.5rem}
.makale time{color:var(--ink-soft);font-family:var(--sans);font-size:.88rem;padding-top:.3rem;font-variant-numeric:tabular-nums}
.makale h3{margin:0;font-size:1.2rem;font-weight:500;line-height:1.35}
.makale h3 a{color:var(--ink);text-decoration:none}
.makale h3 a:hover{color:var(--accent)}
.makale .orij{margin:.25rem 0 0;color:var(--ink-soft);font-style:italic;font-size:.94rem}
.makale .kunye{margin:.3rem 0 0;font-family:var(--sans);color:var(--ink-soft);font-size:.88rem}
.makale .ozet{margin:.6rem 0 0;max-width:var(--measure)}

/* Fiş sayfası */
.fis-duzen{display:grid;grid-template-columns:minmax(0,1fr) 18rem;gap:2.6rem;align-items:start}
.kart{background:var(--card);border:1px solid var(--rule);border-top:3px solid var(--accent);padding:1.4rem 1.6rem 1.2rem;min-width:0}
.kart .alt-ad{margin:-.2rem 0 1rem;color:var(--ink-soft);font-style:italic;font-size:1.05rem}
.kart .kisa{font-weight:500;font-size:1.05rem;max-width:var(--measure)}
.klasik{background:var(--gold-soft);padding:.85rem 1.05rem;margin:1.2rem 0;max-width:var(--measure);font-size:.96rem}
.klasik .bas{font-style:italic;margin:0 0 .4rem}
.klasik p{margin:0}
.klasik.bos{background:transparent;border:1px dashed var(--rule);min-height:3.6rem}
dl.kunye{margin:1.3rem 0 0;display:grid;gap:.45rem;font-size:.95rem;padding-top:1rem;border-top:1px solid var(--rule)}
dl.kunye div{display:grid;grid-template-columns:9.5rem minmax(0,1fr);gap:1rem}
dl.kunye dt{color:var(--ink-soft);font-family:var(--sans);font-size:.86rem;padding-top:.1rem}
dl.kunye dd{margin:0;min-width:0}
.imza{font-family:var(--sans);font-size:.8rem;color:var(--ink-soft);margin:1.2rem 0 0}
aside.yan{background:var(--panel);padding:1.1rem 1.2rem;font-size:.94rem;border-top:3px solid var(--gold);position:sticky;top:calc(env(safe-area-inset-top,0px) + 1rem)}
aside.yan h2{font-family:var(--sans);font-size:.76rem;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-soft);margin:0 0 .45rem;font-weight:600}
aside.yan ul{list-style:none;margin:0 0 1.1rem;padding:0;display:grid;gap:.3rem}
aside.yan ul:last-child{margin-bottom:0}
aside.yan .tur-k{font-family:var(--sans);font-size:.7rem;color:var(--ink-soft);text-transform:uppercase;letter-spacing:.05em;margin-right:.35rem}
.sorular{padding-left:1.3rem;max-width:var(--measure)}.sorular li{margin-bottom:.5rem}
.kutu{background:var(--panel);border-left:3px solid var(--gold);padding:.9rem 1.1rem;margin:1.2rem 0;font-size:.95rem;max-width:var(--measure)}
.kutu dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:.25rem 1rem}
.kutu dt{color:var(--ink-soft)}.kutu dd{margin:0}
.etiketler{margin-top:1.4rem;font-family:var(--sans);font-size:.88rem;color:var(--ink-soft);display:flex;flex-wrap:wrap;gap:.3rem .9rem}
/* Eserler sayfası */
.tur-secici{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1rem}
.tur-secici button{font-family:var(--sans);font-size:.9rem;padding:.3rem .8rem;border:1px solid var(--rule);background:var(--card);color:var(--ink);cursor:pointer;border-radius:999px}
.tur-secici button[aria-pressed="true"]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.tur-secici button[aria-pressed="true"] .say{color:inherit;opacity:.75}
.baslik-gezinti ul{list-style:none;margin:0 0 1.6rem;padding:0;display:flex;flex-wrap:wrap;gap:.4rem}
.baslik-gezinti li{font-family:var(--sans);font-size:.86rem;padding:.15rem .6rem;border:1px solid var(--rule);background:var(--card)}
.baslik-gezinti li.dolu{border-color:var(--accent);background:var(--accent-soft)}
.baslik-gezinti li.plan{color:var(--ink-soft)}
.baslik-gezinti a{text-decoration:none;color:var(--ink)}
.eser-bolum{border-top:2px solid var(--ink);padding-top:.4rem;margin-top:2rem;scroll-margin-top:1rem}
.eser-bolum h2{margin:.2rem 0 .6rem;font-size:1.3rem;font-weight:500;display:flex;align-items:baseline;gap:.7rem}
.eser-bolum h2 a,.eser-bolum h3 a{color:var(--ink);text-decoration:none}
.eser-bolum h3{font-family:var(--sans);font-size:.8rem;letter-spacing:.07em;text-transform:uppercase;color:var(--accent-ink);margin:1.1rem 0 .3rem;font-weight:600}
.eser-bolum h3 a{color:var(--accent-ink)}
.aciklama-kisa{font-family:var(--sans);font-size:.92rem;color:var(--ink-soft);margin:0 0 .6rem;max-width:62ch}
ul.eserler{list-style:none;margin:0;padding:0;columns:2 26rem;column-gap:2.5rem}
ul.eserler li{break-inside:avoid;padding:.5rem 0;border-bottom:1px solid var(--rule)}
.eser-ad{font-weight:600;color:var(--ink);text-decoration:none;font-size:.98rem;line-height:1.4}
.eser-ad:hover{color:var(--accent)}
.eser-bilgi a.dis{font-weight:600}
.ae{display:inline-block;font-family:var(--sans);font-size:.72rem;font-weight:600;color:var(--accent-ink);background:var(--accent-soft);padding:.02rem .4rem;border-radius:2px}
.eser-bilgi{display:block;font-family:var(--sans);font-size:.84rem;color:var(--ink-soft);margin-top:.15rem}
footer.site{border-top:1px solid var(--rule);background:var(--card);color:var(--ink-soft);font-family:var(--sans);font-size:.88rem}
footer.site .wrap{padding-block:1.4rem 2.2rem;display:grid;gap:.3rem}
footer.site p{margin:0;max-width:var(--measure)}
@media (max-width:760px){
  html{font-size:16px}
  .acilis,.fis-duzen{grid-template-columns:1fr;gap:1.5rem}
  .acilis h1{font-size:2rem}
  aside.yan{position:static}
  .liste li,.makale,dl.kunye div{grid-template-columns:1fr;gap:.15rem}
  .kart{padding:1.1rem 1.1rem 1rem}
}
"""

MENU = [("basliklar", "Başlıklar"), ("terimler", "Terimler"), ("kisiler", "Kişiler"),
        ("eserler", "Eserler"), ("guncel", "Güncel"), ("hakkinda", "Hakkında")]


def page(title: str, body: str, aktif: str = "", desc: str = SITE_TAGLINE, canonical: str = "") -> str:
    canon = f'<link rel="canonical" href="{e(canonical)}">' if canonical else ""
    robots = '<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""
    menu = "".join(
        f'<a href="{SITE_URL}/{k}/"{" aria-current=\"page\"" if k == aktif else ""}>{a}</a>' for k, a in MENU)
    deneme = ('<div class="deneme"><div class="wrap">Deneme sürümü. İçerikler taslak hâlindedir ve '
              'henüz yayımlanmamıştır.</div></div>') if (NOINDEX or TASLAK_GOSTER) else ""
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{robots}
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{canon}
<link rel="alternate" type="application/rss+xml" title="{e(SITE_NAME)}" href="{SITE_URL}/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="site"><div class="wrap">
  <a class="marka" href="{SITE_URL}/"><small>dinfelsefesi.com.tr</small><b>{e(SITE_NAME)}</b></a>
  <nav class="ana" aria-label="Ana menü">{menu}</nav>
</div></header>
{deneme}
<main><div class="wrap">
{body}
</div></main>
<footer class="site"><div class="wrap">
  <p>Editör: {e(EDITOR)}. Tanıtımlar özgün eserlerin yerini tutmaz, her kayıt kaynağına bağlantı verir.</p>
  <p>Kayıtlar makine okunabilir biçimde de sunulmaktadır: <a href="{SITE_URL}/api/makaleler.json">makaleler</a>, <a href="{SITE_URL}/api/fisler.json">fişler</a>.</p>
</div></footer>
</body>
</html>"""


def yaz(yol_: str, icerik: str):
    p = OUT / yol_ / "index.html" if yol_ else OUT / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(icerik, encoding="utf-8")


# ---------------------------------------------------------------- makaleler

def entry_url(m: dict) -> str:
    return f"{SITE_URL}/makale/{m['slug']}/"


def makale_satiri(m: dict) -> str:
    return f"""<article class="makale">
  <time datetime="{e(m['date'])}">{tr_date(m['date'])}</time>
  <div>
    <h3><a href="{entry_url(m)}">{e(m['title_tr'])}</a></h3>
    <p class="orij">{e(m['title_en'])}</p>
    <p class="kunye">{e(m['authors'])} · {e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</p>
    <p class="ozet">{e(m['lead'])}</p>
  </div>
</article>"""


def render_makaleler(items) -> str:
    body = ('<p class="ust-etiket">Güncel</p><h1>Yeni makaleler</h1>'
            '<p class="giris">Din felsefesi dergilerinde yayımlanan yeni makalelerin Türkçe tanıtımları.</p>'
            + "".join(makale_satiri(m) for m in items))
    return page(f"Güncel · {SITE_NAME}", body, "guncel", canonical=f"{SITE_URL}/guncel/")


def render_makale(m: dict) -> str:
    oa = {"evet": "Açık erişim", "hayır": "Abonelik gerekli"}.get(m.get("open_access", ""), "")
    link = m.get("doi") and f"https://doi.org/{m['doi']}" or m.get("url", "")
    body = f"""
<article class="dar">
  <p class="yol"><a href="{SITE_URL}/guncel/">Güncel</a> <span aria-hidden="true">›</span> <time datetime="{e(m['date'])}">{tr_date(m['date'])}</time></p>
  <h1>{e(m['title_tr'])}</h1>
  <p class="giris"><em>{e(m['title_en'])}</em></p>
  <div class="kutu"><dl>
    <dt>Yazar</dt><dd>{e(m['authors'])}</dd>
    <dt>Dergi</dt><dd>{e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</dd>
    <dt>Kaynak</dt><dd><a href="{e(link)}" rel="noopener">{e(link)}</a>{(' · ' + oa) if oa else ''}</dd>
  </dl></div>
  <div class="metin">
    {paragraphs(m['summary_tr'])}
    <h2>Neden önemli</h2>
    {paragraphs(m.get('why_tr', ''))}
  </div>
  <div class="etiketler">{''.join(f'<span>#{e(t)}</span>' for t in m.get('tags', []))}</div>
</article>"""
    return page(f"{m['title_tr']} · {SITE_NAME}", body, "guncel", desc=m["lead"], canonical=entry_url(m))


# ---------------------------------------------------------------- başlıklar

def ana_basliklar():
    return sorted([k for (t, k), h in FIS.items() if t == "baslik" and not h.get("ust_baslik")],
                  key=lambda k: FIS[("baslik", k)].get("sira", 99))


def alt_dolu(a) -> bool:
    """Alt başlığın fişi var ve ona bağlı içerik ya da metin bulunuyorsa dolu sayılır."""
    return ("baslik", a) in FIS and bool(bagli_fisler(a) or FIS[("baslik", a)].get("_govde"))


def harita_html() -> str:
    anas = ana_basliklar()
    en_cok = max([len(bagli_fisler(k)) for k in anas] + [1])
    kartlar = []
    for k in anas:
        h = FIS[("baslik", k)]
        b = bagli_fisler(k)
        altlar = "".join(
            f"<li class='{'dolu' if alt_dolu(a) else 'plan'}'>{bag('baslik', a)}</li>"
            for a in liste(h.get("alt_basliklar")))
        ilg = bag_listesi("ilgili_basliklar", h)
        kartlar.append(f"""<article class="anakart{' bos' if not b else ''}">
  <h3><a href="{fis_url('baslik', k)}">{e(h['ad'])}</a></h3>
  <p>{satir_ici(h.get('ozet'))}</p>
  <div class="olcu" role="img" aria-label="{len(b)} fiş"><span style="width:{round(100 * len(b) / en_cok)}%"></span></div>
  <span class="say">{sayim_metni(b)}</span>
  {f'<ul class="altlar">{altlar}</ul>' if altlar else ''}
  {f'<span class="ilgili">İlgili: {ilg}</span>' if ilg else ''}
</article>""")
    return f'<div class="harita">{"".join(kartlar)}</div>'


def fis_grubu(fisler, tur, baslik) -> str:
    secili = sorted([k for t, k in fisler if t == tur], key=lambda k: tr_anahtar(ad(tur, FIS[(tur, k)])))
    if not secili:
        return ""
    return f"<h2>{baslik}</h2><ul>" + "".join(f"<li>{bag(tur, k)}</li>" for k in secili) + "</ul>"


def render_baslik(k) -> str:
    h = FIS[("baslik", k)]
    b = bagli_fisler(k)
    ok = h.get("okuma_listesi") or {}
    yan = "".join([
        f"<h2>Alt başlıklar</h2><ul>{''.join(f'<li>{bag("baslik", a)}</li>' for a in liste(h.get('alt_basliklar')))}</ul>" if liste(h.get("alt_basliklar")) else "",
        fis_grubu(b, "terim", "Terimler"),
        fis_grubu(b, "kisi", "Kişiler"),
        (f"<h2>Okuma listesi · giriş</h2><ul>{''.join(f'<li>{bag("eser", x)}</li>' for x in liste(ok.get('giris')))}</ul>" if liste(ok.get("giris")) else ""),
        (f"<h2>Okuma listesi · ileri</h2><ul>{''.join(f'<li>{bag("eser", x)}</li>' for x in liste(ok.get('ileri')))}</ul>" if liste(ok.get("ileri")) else ""),
        fis_grubu(b, "eser", "Eserler") if not ok else "",
        (f"<h2>İlgili başlıklar</h2><ul>{''.join(f'<li>{bag("baslik", x)}</li>' for x in liste(h.get('ilgili_basliklar')))}</ul>" if liste(h.get("ilgili_basliklar")) else ""),
    ])
    sorular = "".join(f"<li>{satir_ici(s)}</li>" for s in liste(h.get("tartisma_sorulari")))
    metin = govde(h["_govde"])
    if not metin:
        metin = ('<p class="giris">Başlığın tanıtım metni henüz yazılmadı. '
                 'Başlığa bağlı fişler yandaki listede yer almaktadır.</p>' if b else
                 '<p class="giris">Bu başlık için henüz fiş eklenmedi.</p>')
    body = f"""
<p class="yol">{yol(k)}</p>
<h1>{e(h['ad'])}{taslak_etiketi(h)}</h1>
<p class="giris">{satir_ici(h.get('ozet'))} <span class="say">{sayim_metni(b)}</span></p>
<div class="fis-duzen">
  <div class="metin">{metin}{f'<h2>Tartışma soruları</h2><ol class="sorular">{sorular}</ol>' if sorular else ''}</div>
  <aside class="yan">{yan or '<h2>Fişler</h2><p>Henüz fiş yok.</p>'}</aside>
</div>"""
    return page(f"{h['ad']} · {SITE_NAME}", body, "basliklar", desc=h.get("ozet") or SITE_TAGLINE,
                canonical=fis_url("baslik", k))


def render_basliklar() -> str:
    body = ('<p class="ust-etiket">Başlıklar</p><h1>Din felsefesinin başlıkları</h1>'
            '<p class="giris">Ana başlıklar din felsefesi literatürünün en genel problem alanlarını gösterir. '
            'Çubuklar her başlığa bağlı fiş sayısını, çerçeveli alt başlıklar içeriği hazır olanları gösterir.</p>'
            + harita_html())
    return page(f"Başlıklar · {SITE_NAME}", body, "basliklar", canonical=f"{SITE_URL}/basliklar/")


# ---------------------------------------------------------------- fiş sayfaları

def satir(etiket, icerik) -> str:
    return f"<div><dt>{etiket}</dt><dd>{icerik}</dd></div>" if icerik else ""


def geri_yan(tur, k) -> str:
    sira = list(KLASOR)
    g = sorted(GERI.get((tur, k), set()), key=lambda x: (sira.index(x[0]), tr_anahtar(ad(x[0], FIS[x]))))
    if not g:
        return ""
    oge = "".join(f'<li><span class="tur-k">{TUR_AD[t]}</span>{bag(t, kk)}</li>' for t, kk in g)
    return f"<h2>Bu fişe bağlananlar</h2><ul>{oge}</ul>"


def eser_baglantisi(h) -> str:
    if h.get("doi"):
        return f"https://doi.org/{h['doi']}"
    return h.get("baglanti") or ""


def kunye_html(h) -> str:
    yazarlar = ", ".join(bag("kisi", y) for y in liste(h.get("yazar")))
    doi = h.get("doi")
    d = f" doi:{e(doi)}" if doi else ""
    return f"{yazarlar}, <em>{e(h['baslik'])}</em>. {e(h['yayin'])}.{d}"


def render_fis(tur, k) -> str:
    h = FIS[(tur, k)]
    basliklar = satir("Başlık", bag_listesi("basliklar", h))
    if tur == "terim":
        bas = f"<h1>{e(h['terim'])}{taslak_etiketi(h)}</h1><p class='alt-ad'>{e(h['ingilizce'])}</p>"
        kg = h.get("klasik_gelenekte") or {}
        kb = ", ".join(e(x) for x in liste(kg.get("basliklar")))
        notu = kg.get("not") or ""
        kg_html = (f"<aside class='klasik{'' if (kb or notu) else ' bos'}'><p class='ust-etiket'>Klasik gelenekte</p>"
                   + (f"<p class='bas'>{kb}</p>" if kb else "") + (f"<p>{satir_ici(notu)}</p>" if notu else "") + "</aside>")
        dl = "".join([
            satir("Diğer karşılıklar", ", ".join(e(x) for x in liste(h.get("diger_karsiliklar")))),
            satir("İlgili terimler", bag_listesi("ilgili_terimler", h)),
            satir("İlgili kişiler", bag_listesi("ilgili_kisiler", h)),
            satir("İlgili eserler", bag_listesi("ilgili_eserler", h)),
            satir("Kaynaklar", bag_listesi("kaynaklar", h)), basliklar])
        ic = f"<p class='kisa'>{satir_ici(h['kisa_tanim'])}</p><div class='metin'>{govde(h['_govde'])}</div>{kg_html}"
        desc = h["kisa_tanim"]
    elif tur == "kisi":
        kurum = f" · {e(h['kurum'])}" if h.get("kurum") else ""
        bas = f"<h1>{e(h['ad'])}{taslak_etiketi(h)}</h1><p class='alt-ad'>{e(h['donem'])}{kurum}</p>"
        dl = "".join([
            satir("Alanlar", ", ".join(e(x) for x in liste(h.get("alanlar")))),
            satir("Temel görüşleri", bag_listesi("temel_gorusleri", h)),
            satir("Eserleri", bag_listesi("eserleri", h)),
            satir("Türkçe çevirileri", "<br>".join(satir_ici(x) for x in liste(h.get("turkce_cevirileri")))),
            basliklar])
        ic = f"<p class='kisa'>{satir_ici(h['kisa_tanitim'])}</p><div class='metin'>{govde(h['_govde'])}</div>"
        desc = h["kisa_tanitim"]
    else:
        duzey = {"giris": "giriş düzeyi", "ileri": "ileri düzey"}.get(h.get("duzey"), "")
        bas = (f"<h1>{e(h['baslik'])}{taslak_etiketi(h)}</h1>"
               f"<p class='alt-ad'>{e(h['eser_turu']).capitalize()} · {e(h['yil'])}{' · ' + duzey if duzey else ''}</p>")
        hedef = eser_baglantisi(h)
        erisim = ""
        if hedef:
            erisim = f'<a href="{e(hedef)}" rel="noopener">{e(hedef)}</a>'
            if h.get("acik_erisim") == "evet":
                erisim += ' <span class="ae">Açık erişim</span>'
        dl = "".join([satir("Künye", kunye_html(h)), satir("Erişim", erisim),
                      satir("Türkçe çevirisi", satir_ici(h.get("turkce_cevirisi"))),
                      satir("İlgili terimler", bag_listesi("ilgili_terimler", h)), basliklar])
        ic = f"<div class='metin'>{govde(h['_govde'])}</div>"
        desc = re.sub(r"\s+", " ", h["_govde"])[:200]
    yan = geri_yan(tur, k)
    body = f"""
<p class="yol"><a href="{SITE_URL}/{KLASOR[tur]}/">{ {'terim': 'Terimler', 'kisi': 'Kişiler', 'eser': 'Eserler'}[tur] }</a></p>
<div class="fis-duzen">
  <article class="kart"><p class="ust-etiket">{TUR_AD[tur]}</p>{bas}{ic}<dl class="kunye">{dl}</dl>
    <p class="imza">{e(h.get('imza'))} · son güncelleme {tr_date(str(h['guncelleme']))}</p></article>
  {f'<aside class="yan">{yan}</aside>' if yan else ''}
</div>"""
    return page(f"{ad(tur, h)} · {SITE_NAME}", body, KLASOR[tur], desc=desc, canonical=fis_url(tur, k))


def render_dizin(tur) -> str:
    kimlikler = sorted([k for (t, k) in FIS if t == tur], key=lambda k: tr_anahtar(ad(tur, FIS[(tur, k)])))
    basliklar = {"terim": ("Terimler", "Din felsefesi terimlerinin Türkçe ve İngilizce karşılıkları, kısa tanımları ve bağlantıları."),
                 "kisi": ("Kişiler", "Din felsefesi literatürüne katkı vermiş düşünürler ve araştırmacılar."),
                 "eser": ("Eserler", "Din felsefesinin temel kitap ve makaleleri, Türkçe çevirileri ve düzeyleriyle.")}[tur]
    satirlar, son_harf = [], ""
    for k in kimlikler:
        h = FIS[(tur, k)]
        adi = ad(tur, h)
        if tur == "terim":
            harf = adi[:1].upper().replace("i", "İ")
            if harf != son_harf:
                satirlar.append(f'</ul><p class="harf">{e(harf)}</p><ul class="liste">')
                son_harf = harf
            satirlar.append(f'<li><span class="ad">{bag(tur, k)}<span class="alt-ad">{e(h["ingilizce"])}</span></span>'
                            f'<span class="aciklama">{satir_ici(h["kisa_tanim"])}</span></li>')
        elif tur == "kisi":
            continue
        else:
            yazar = ", ".join(bag("kisi", y) for y in liste(h.get("yazar")))
            satirlar.append(f'<li><span class="ad">{bag(tur, k)}<span class="alt-ad">{yazar} · {e(h["yil"])}</span></span>'
                            f'<span class="aciklama">{e(h["yayin"])}{" · Türkçesi: " + satir_ici(h["turkce_cevirisi"]) if h.get("turkce_cevirisi") else ""}</span></li>')
    icerik = f'<ul class="liste">{"".join(satirlar)}</ul>'.replace('<ul class="liste"></ul>', "")
    if tur == "kisi":
        icerik = kisi_bolumleri(kimlikler)
    elif not kimlikler:
        icerik = '<p class="giris">Henüz fiş eklenmedi.</p>'
    body = f'<p class="ust-etiket">{basliklar[0]}</p><h1>{basliklar[0]}</h1><p class="giris">{basliklar[1]} <span class="say">{len(kimlikler)} fiş</span></p>{icerik}'
    return page(f"{basliklar[0]} · {SITE_NAME}", body, KLASOR[tur], canonical=f"{SITE_URL}/{KLASOR[tur]}/")

KAPSAM = [("turkiye", "Türkiye akademisi",
           "Türkiye'deki üniversitelerde din felsefesi alanında çalışan akademisyenler. Bilgiler kamuya açık kaynaklardan alınır."),
          ("uluslararasi", "Uluslararası literatür",
           "Din felsefesi literatüründe etkili olmuş düşünürler ve araştırmacılar.")]


def kisi_bolumleri(kimlikler) -> str:
    bolumler = []
    for kod, baslik_, aciklama in KAPSAM:
        uyan = [k for k in kimlikler if FIS[("kisi", k)].get("kapsam", "uluslararasi") == kod]
        satirlar = []
        for k in uyan:
            h = FIS[("kisi", k)]
            alt = h.get("kurum") if kod == "turkiye" and h.get("kurum") else h.get("donem")
            satirlar.append(f'<li><span class="ad">{bag("kisi", k)}<span class="alt-ad">{e(alt)}</span></span>'
                            f'<span class="aciklama">{satir_ici(h["kisa_tanitim"])}</span></li>')
        liste_ = f'<ul class="liste">{"".join(satirlar)}</ul>' if satirlar else '<p class="giris">Fişler hazırlanıyor.</p>'
        bolumler.append(f'<section class="eser-bolum" id="{kod}"><h2>{e(baslik_)} <span class="say">{len(uyan)} kişi</span></h2>'
                        f'<p class="aciklama-kisa">{e(aciklama)}</p>{liste_}</section>')
    return "".join(bolumler)


TUR_SIRA = {"kitap": 0, "kitap-bolumu": 1, "makale": 2, "bildiri": 3, "tez": 4}
TUR_COGUL = [("kitap", "Kitaplar"), ("kitap-bolumu", "Kitap bölümleri"), ("makale", "Makaleler"),
             ("bildiri", "Bildiriler"), ("tez", "Tezler")]


def tur_secici(eserler) -> str:
    sayi = {t: sum(1 for k in eserler if FIS[("eser", k)].get("eser_turu") == t) for t, _ in TUR_COGUL}
    dugmeler = [f'<button type="button" data-secim="" aria-pressed="true">Tümü <span class="say">{len(eserler)}</span></button>']
    for t, a in TUR_COGUL:
        if sayi[t]:
            dugmeler.append(f'<button type="button" data-secim="{t}" aria-pressed="false">{a} <span class="say">{sayi[t]}</span></button>')
    return f'<div class="tur-secici" role="group" aria-label="Eser türü">{"".join(dugmeler)}</div>'


TUR_SECICI_JS = """<script>
(function(){
  var d=document.querySelectorAll('.tur-secici button');
  function uygula(t){
    d.forEach(function(b){b.setAttribute('aria-pressed', b.dataset.secim===t?'true':'false');});
    document.querySelectorAll('ul.eserler li').forEach(function(li){li.hidden = !!t && li.dataset.tur!==t;});
    document.querySelectorAll('ul.eserler').forEach(function(ul){
      var bos=!ul.querySelector('li:not([hidden])'); ul.hidden=bos;
      var h=ul.previousElementSibling; if(h && h.tagName==='H3'){h.hidden=bos;}
    });
    document.querySelectorAll('.eser-bolum').forEach(function(s){s.hidden=!s.querySelector('ul.eserler:not([hidden])');});
  }
  d.forEach(function(b){b.addEventListener('click',function(){uygula(b.dataset.secim);});});
})();
</script>"""


def eser_satiri(k) -> str:
    h = FIS[("eser", k)]
    yazar = ", ".join(bag("kisi", y) for y in liste(h.get("yazar")))
    bilgi = [yazar, e(h.get("yil")), e(str(h.get("eser_turu", "")).capitalize())]
    duzey = {"giris": "giriş düzeyi", "ileri": "ileri düzey"}.get(h.get("duzey"))
    if duzey:
        bilgi.append(duzey)
    if h.get("turkce_cevirisi"):
        bilgi.append("Türkçesi var")
    hedef = eser_baglantisi(h)
    if hedef:
        etiket = "DOI" if h.get("doi") else "Bağlantı"
        bilgi.append(f'<a class="dis" href="{e(hedef)}" rel="noopener">{etiket}</a>')
    if h.get("acik_erisim") == "evet":
        bilgi.append('<span class="ae">Açık erişim</span>')
    return (f'<li data-tur="{e(h.get("eser_turu", ""))}"><a class="eser-ad" href="{fis_url("eser", k)}">{e(h["baslik"])}</a>'
            f'<span class="eser-bilgi">{" · ".join(x for x in bilgi if x)}</span></li>')


def render_eserler() -> str:
    eserler = [k for (t, k) in FIS if t == "eser"]
    def sirala(ks):
        return sorted(ks, key=lambda k: (TUR_SIRA.get(FIS[("eser", k)].get("eser_turu"), 9),
                                         str(FIS[("eser", k)].get("yil", "")), tr_anahtar(FIS[("eser", k)]["baslik"])))
    anas = ana_basliklar()
    gezinti, bolumler, yerlesen = [], [], set()
    for a in anas:
        hedef = soy(a)
        ilgili = [k for k in eserler if set(liste(FIS[("eser", k)].get("basliklar"))) & hedef]
        n = len(ilgili)
        gezinti.append(f'<li class="{"dolu" if n else "plan"}">'
                       + (f'<a href="#{a}">{e(FIS[("baslik", a)]["ad"])}</a> <span class="say">{n}</span>' if n
                          else f'<span>{e(FIS[("baslik", a)]["ad"])}</span>') + '</li>')
        if not n:
            continue
        ic = []
        dogrudan = [k for k in ilgili if a in liste(FIS[("eser", k)].get("basliklar"))]
        if dogrudan:
            ic.append(f'<ul class="eserler">{"".join(eser_satiri(k) for k in sirala(dogrudan))}</ul>')
        for alt in sorted(COCUK.get(a, []), key=lambda x: FIS[("baslik", x)].get("sira", 99)):
            altdaki = [k for k in ilgili if set(liste(FIS[("eser", k)].get("basliklar"))) & soy(alt)]
            if altdaki:
                ic.append(f'<h3><a href="{fis_url("baslik", alt)}">{e(FIS[("baslik", alt)]["ad"])}</a></h3>'
                          f'<ul class="eserler">{"".join(eser_satiri(k) for k in sirala(altdaki))}</ul>')
        yerlesen |= set(ilgili)
        bolumler.append(f'<section class="eser-bolum" id="{a}"><h2><a href="{fis_url("baslik", a)}">{e(FIS[("baslik", a)]["ad"])}</a> '
                        f'<span class="say">{n} eser</span></h2>{"".join(ic)}</section>')
    kalan = [k for k in eserler if k not in yerlesen]
    if kalan:
        bolumler.append(f'<section class="eser-bolum"><h2>Başlığı belirlenmemiş eserler</h2>'
                        f'<ul class="eserler">{"".join(eser_satiri(k) for k in sirala(kalan))}</ul></section>')
    body = (f'<p class="ust-etiket">Eserler</p><h1>Eserler</h1>'
            f'<p class="giris">Din felsefesinin temel kitap ve makaleleri, ait oldukları başlıklara göre. '
            f'Her başlığın altında eserler türe ve yayın yılına göre sıralanır. <span class="say">{len(eserler)} eser</span></p>'
            f'{tur_secici(eserler)}'
            f'<nav class="baslik-gezinti" aria-label="Başlıklar"><ul>{"".join(gezinti)}</ul></nav>'
            + ("".join(bolumler) or '<p class="giris">Henüz eser fişi eklenmedi.</p>'))
    return page(f"Eserler · {SITE_NAME}", body + TUR_SECICI_JS, "eserler", canonical=f"{SITE_URL}/eserler/")


# ---------------------------------------------------------------- ana sayfa ve hakkında

def render_ana(items) -> str:
    say = {t: sum(1 for (x, _) in FIS if x == t) for t in KLASOR}
    rakam = "".join(f'<a href="{SITE_URL}/{yol_}/"><b>{n}</b><span>{a}</span></a>' for yol_, n, a in [
        ("basliklar", len(ana_basliklar()), "ana başlık"), ("terimler", say["terim"], "terim"),
        ("kisiler", say["kisi"], "kişi"), ("eserler", say["eser"], "eser")])
    body = f"""
<section class="acilis">
  <div><h1>Din felsefesi için Türkçe başvuru kaynağı</h1>
  <p>Din felsefesinin temel problemleri, terimleri, düşünürleri ve eserleri birbirine bağlı fişlerle sunulmaktadır. Uluslararası ve Türkçe literatürdeki yeni çalışmalar düzenli olarak taranmakta ve tanıtılmaktadır.</p></div>
  <div class="rakamlar">{rakam}</div>
</section>
<div class="bolum-baslik"><h2>Başlık haritası</h2><a href="{SITE_URL}/basliklar/">Bütün başlıklar</a></div>
{harita_html()}
<div class="bolum-baslik"><h2>Güncel</h2><a href="{SITE_URL}/guncel/">Bütün tanıtımlar</a></div>
{''.join(makale_satiri(m) for m in items[:5])}
"""
    return page(SITE_NAME, body, "", canonical=SITE_URL + "/")


ABOUT = f"""
<article class="dar">
  <p class="ust-etiket">Hakkında</p>
  <h1>Hakkında</h1>
  <div class="metin">
    <p>{SITE_NAME}, din felsefesine dair Türkçe bir başvuru kaynağı olarak hazırlanmaktadır. Sitede din felsefesi literatürünün ana başlıkları, bu başlıklara bağlı terimler, düşünürler ve eserler birbirine bağlantılı fişler hâlinde yer almaktadır.</p>
    <p>Sitede ayrıca uluslararası din felsefesi dergilerinde yayımlanan yeni makalelerin Türkçe tanıtımları sunulmaktadır. Tanıtımlar makalenin iddiasını, yöntemini ve literatürdeki yerini aktarır, makalenin yerine geçmez. Her kayıtta özgün metne bağlantı bulunur.</p>
    <h2>Editörlük</h2>
    <p>Editör: {EDITOR}, Erciyes Üniversitesi İlahiyat Fakültesi, Din Felsefesi Anabilim Dalı.</p>
  </div>
</article>"""


# ---------------------------------------------------------------- derleme

def main() -> None:
    global FIS
    items = json.loads((CONTENT / "makaleler.json").read_text(encoding="utf-8"))
    for m in items:
        m.setdefault("slug", slugify(m["title_tr"]))
    items.sort(key=lambda m: m["date"], reverse=True)

    FIS = fisleri_oku()
    iliskileri_kur()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    yaz("", render_ana(items))
    yaz("guncel", render_makaleler(items))
    for m in items:
        yaz(f"makale/{m['slug']}", render_makale(m))
    yaz("basliklar", render_basliklar())
    for (t, k) in FIS:
        if t == "baslik":
            yaz(f"basliklar/{k}", render_baslik(k))
        else:
            yaz(f"{KLASOR[t]}/{k}", render_fis(t, k))
    for t in ("terim", "kisi"):
        yaz(KLASOR[t], render_dizin(t))
    yaz("eserler", render_eserler())
    yaz("hakkinda", page(f"Hakkında · {SITE_NAME}", ABOUT, "hakkinda", canonical=f"{SITE_URL}/hakkinda/"))

    (OUT / "api").mkdir()
    (OUT / "api" / "makaleler.json").write_text(
        json.dumps([{**m, "url": entry_url(m)} for m in items], ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "api" / "fisler.json").write_text(json.dumps(
        [{k: v for k, v in h.items() if not k.startswith("_")} | {"tur": t, "url": fis_url(t, kk), "metin": h["_govde"]}
         for (t, kk), h in FIS.items()], ensure_ascii=False, indent=1, default=str), encoding="utf-8")

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
    print(f"{len(items)} makale, {len(FIS)} fiş, çıktı: {OUT}")


if __name__ == "__main__":
    main()
