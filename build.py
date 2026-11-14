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
import math
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import yaml
from urllib.parse import quote

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
OUT = ROOT / "site"
SITE_URL = os.environ.get("SITE_URL", "https://dinfelsefesi.com.tr").rstrip("/")
# Ziyaret sayacı (GoatCounter): çerez kullanmaz, kişisel veri tutmaz. Yalnızca asıl adres için derlenen sitede çalışır.
SAYAC = ('\n<script data-goatcounter="https://dinfelsefesi.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'
         if SITE_URL == "https://dinfelsefesi.com.tr" else "")
NOINDEX = os.environ.get("NOINDEX") == "1"
# Akademisyen sayfaları (ve ağ sayfaları) bu tarihten itibaren arama motorlarına açılır ve site haritasına girer.
# Günlük derleme o günün akşamı yeni hâli yayımlar.
AKADEMI_DIZIN_TARIHI = date(2026, 10, 31)
AKADEMI_ACIK = datetime.now(timezone(timedelta(hours=3))).date() >= AKADEMI_DIZIN_TARIHI
TASLAK_GOSTER = os.environ.get("TASLAK_GOSTER") == "1"
SITE_NAME = "Din Felsefesi"
SITE_TAGLINE = "Din felsefesinin başlıkları, terimleri, kişileri ve eserleri; Türkçe ve uluslararası literatürden seçilmiş tanıtımlar"
EDITOR = "Abdullah Akgül"
ILETISIM = "dinfelsefesi@gmail.com"
YIL = datetime.now().year
X_HESABI = "dinfelsefesi_tr"

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


def tr_kucuk(s: str) -> str:
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


_ARA_KATLA = str.maketrans({**{c: "a" for c in "âäāàá"}, **{c: "e" for c in "êēëè"}, **{c: "i" for c in "îïīì"},
                            **{c: "o" for c in "ôōò"}, **{c: "u" for c in "ûūù"}, **{c: None for c in "'`´‘’ʻʼʽʾʿ"}})


def ara_norm(s: str) -> str:
    """Arama için: küçük harf, şapkalı/uzatmalı ünlüler düz harfe, kesme ve ayn/hemze işaretleri atılır."""
    return tr_kucuk(s).translate(_ARA_KATLA)


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


HARF = "A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû"
BAG_DIZINI = []   # (desen, tur, kimlik), iliskileri_kur sonrasında doldurulur


def bag_dizini_kur():
    adaylar = []
    soyadlar = {}
    for (t, k), h in FIS.items():
        if t == "kisi":
            soyadlar.setdefault(ad(t, h).split()[-1], []).append(k)
    for (t, k), h in FIS.items():
        adi = ad(t, h)
        if h.get("otomatik_bag") is False:  # genel bir kelime olan adlar (ör. Özgürlük) metinde kendiliğinden bağlanmaz
            continue
        if t in ("terim", "baslik"):
            adaylar.append((adi, t, k, True))
        elif t == "kisi":
            adaylar.append((adi, t, k, False))
            soy_ = adi.split()[-1]
            if len(soyadlar[soy_]) == 1:
                adaylar.append((soy_, t, k, False))
        elif t == "eser":
            adaylar.append((adi, t, k, False))
    adaylar.sort(key=lambda x: -len(x[0]))
    BAG_DIZINI.clear()
    for metin, t, k, kucuk_harf in adaylar:
        govde_ = re.escape(e(metin)).replace("\\ ", "\\s+")
        ek = f"[{HARF}]*" if t in ("terim", "baslik") else ""
        desen = re.compile(f"(?<![{HARF}])({govde_}{ek})(?![{HARF}])", re.IGNORECASE if kucuk_harf else 0)
        BAG_DIZINI.append((desen, t, k, tr_kucuk(metin) if t in ("terim", "baslik") else f"{t}/{k}"))


def metne_bag(html_: str, kendi=None, kullanilan=None) -> str:
    """Metinde geçen fiş adlarının sayfadaki ilk geçtiği yeri fişe bağlar. Etiketlerin içine dokunmaz."""
    if kullanilan is None:
        kullanilan = set()
    parcalar = re.split(r"(<[^>]+>)", html_)
    kendi_ad = tr_kucuk(ad(kendi[0], FIS[kendi])) if kendi in FIS else None
    for desen, t, k, anahtar in BAG_DIZINI:
        if (t, k) == kendi or (t, k) in kullanilan or anahtar in kullanilan or anahtar == kendi_ad:
            continue
        for i in range(0, len(parcalar), 2):
            if i > 0 and parcalar[i - 1].startswith("<a"):
                continue
            m = desen.search(parcalar[i])
            if m:
                bas, son = parcalar[i][:m.start(1)], parcalar[i][m.end(1):]
                parcalar[i:i + 1] = [bas, f'<a class="ic-bag" href="{fis_url(t, k)}">', m.group(1), "</a>", son]
                kullanilan.update({(t, k), anahtar})
                break
    return "".join(parcalar)


def arguman_html(blok: str) -> str:
    """Fiş metnindeki argüman kutusu. Biçim (arada boş satır olmadan):
    ::: argüman Başlık
    1. Öncül            (numaralı satırlar öncül ya da ara sonuçtur)
    S. Sonuç
    not: Kısa açıklama  (isteğe bağlı)
    kaynak: Künye
    :::"""
    satirlar = [x.strip() for x in blok.strip().splitlines()]
    baslik = satirlar[0][len("::: argüman"):].strip()
    ogeler, kaynak, notlar = [], "", []
    for x in satirlar[1:]:
        if not x or x == ":::":
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", x)
        if m:
            ogeler.append(f'<li><span class="arg-no">{m.group(1)}</span><span>{satir_ici(m.group(2))}</span></li>')
        elif x.startswith("S. "):
            ogeler.append(f'<li class="arg-sonuc"><span class="arg-no">Sonuç</span><span>{satir_ici(x[3:])}</span></li>')
        elif x.startswith("kaynak:"):
            kaynak = x[7:].strip()
        elif x.startswith("not:"):
            notlar.append(x[4:].strip())
    return (f'<figure class="arguman"><figcaption><span class="arg-tur">Argüman</span> {satir_ici(baslik)}</figcaption>'
            f'<ol>{"".join(ogeler)}</ol>'
            + "".join(f'<p class="arg-not">{satir_ici(n)}</p>' for n in notlar)
            + (f'<p class="arg-kaynak">{satir_ici(kaynak)}</p>' if kaynak else "") + "</figure>")


def govde(text: str, kendi=None) -> str:
    kullanilan = set()
    out = []
    for blok in re.split(r"\n\s*\n", (text or "").strip()):
        blok = blok.strip()
        if not blok:
            continue
        if blok.startswith("## "):
            out.append(f"<h2>{satir_ici(blok[3:])}</h2>")
        elif blok.startswith("::: argüman"):
            out.append(arguman_html(blok))
        else:
            out.append(f"<p>{metne_bag(satir_ici(blok), kendi, kullanilan) if kendi else satir_ici(blok)}</p>")
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
    if tur == "kisi" and slugify(str(d)) in akademi_verisi():  # fişi olmayan Türkiye akademisi üyesi: akademisyen sayfası
        return f'<a href="{akademi_url(slugify(str(d)))}">{e(d)}</a>'
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
    # "Taslak" etiketi yalnızca deneme yayınında görünür; asıl sitede gösterilmez (31.10.2026)
    return '<span class="taslak">Taslak</span>' if NOINDEX and h.get("durum") != "yayinda" else ""


def yol(k) -> str:
    zincir = []
    while k and ("baslik", k) in FIS:
        zincir.append(k)
        k = FIS[("baslik", k)].get("ust_baslik")
    parcalar = [f'<a href="{SITE_URL}/basliklar/">Başlıklar</a>'] + [bag("baslik", x) for x in reversed(zincir[1:])]
    return " <span aria-hidden='true'>›</span> ".join(parcalar)


# ---------------------------------------------------------------- sayfa iskeleti

CSS = """
/* Yerleşim: bir kitap sayfası. Açık gri zemin, koyu gri yazı. Renkler logodan gelir: lâcivert (#23446e)
   ve tezhip altını (#c9a14a). Logo altını yalnızca süs çizgilerinde kullanılır; yazıda okunurluk için
   daha koyu bir altın tonu (--gold) kullanılır. Tek tema (açık). */
:root{
  --ink:#22262c;--ink-soft:#5c6370;--rule:#dcdfe5;--paper:#f3f4f6;--panel:#e9ecf0;--card:#fbfbfc;
  --accent:#23446e;--accent-ink:#1d3a5f;--accent-soft:#e6ebf2;--gold:#86641e;--gold-logo:#c9a14a;--gold-soft:#e8ebf0;
  --display:"EB Garamond","Garamond","Georgia",serif;
  --serif:"Literata",Georgia,"Times New Roman",serif;
  --sans:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  --measure:66ch;
  color-scheme:light;
}
*{box-sizing:border-box}
html{font-size:16px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);line-height:1.55;-webkit-font-smoothing:antialiased}
/* Kısa sayfalarda alt bilgi ekranın altına yaslanır */
body{min-height:100vh;min-height:100dvh;display:flex;flex-direction:column}
body>main{flex:1 0 auto}
a{color:var(--accent-ink);text-decoration-thickness:1px;text-decoration-color:color-mix(in srgb,var(--gold-logo) 70%,transparent);text-underline-offset:3px}
a:hover{text-decoration-color:currentColor}
a:hover{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.wrap{max-width:70rem;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.dar{max-width:46rem}
header.site{background:var(--paper);border-top:4px solid var(--accent);border-bottom:1px solid var(--gold-logo);
  position:sticky;top:0;z-index:60;transition:transform .25s ease,box-shadow .2s ease}
html{scroll-padding-top:4.5rem}
/* aşağı inildiğinde şerit incelir: küçük logo, alt yazı gizli */
body.ust-ince header.site{box-shadow:0 2px 8px rgba(35,68,110,.08)}
body.ust-ince header.site .wrap{padding-block:.45rem .4rem}
body.ust-ince .marka-logo{width:30px;height:30px}
body.ust-ince .marka b{font-size:1.3rem}
body.ust-ince .marka small{display:none}
header.site .wrap,.marka-logo,.marka b{transition:padding .2s ease,width .2s ease,height .2s ease,font-size .2s ease}
/* telefonda aşağı inerken gizlenir, yukarı kaydırılınca geri gelir */
@media (max-width:760px){body.ust-gizli header.site{transform:translateY(-110%)}}
@media (prefers-reduced-motion:reduce){header.site,header.site .wrap,.marka-logo,.marka b{transition:none}}
header.site .wrap{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.6rem 2rem;padding-block:1.3rem 1.1rem}
.marka{text-decoration:none;color:var(--ink);display:flex;align-items:center;gap:.75rem}
.marka-yazi{display:flex;flex-direction:column;gap:.1rem}
.marka-logo{width:44px;height:44px;flex:none}
.marka b{font-family:var(--display);font-weight:500;font-size:1.75rem;line-height:1.05}
.marka small{order:2;font-style:italic;font-size:.86rem;color:var(--ink-soft)}
nav.ana{display:flex;flex-wrap:wrap;gap:.3rem 1.4rem;font-family:var(--display);font-size:1.04rem}
nav.ana a{color:var(--ink-soft);text-decoration:none;padding-block:.2rem;border-bottom:2px solid transparent}
nav.ana a:hover{color:var(--ink)}
nav.ana a[aria-current="page"]{color:var(--accent);border-bottom-color:var(--gold-logo)}
/* telefonda menü tek satır: "Ana sayfa" gizlenir (logo ve site adı zaten ana sayfaya götürür) */
@media (max-width:760px){nav.ana{flex-wrap:nowrap;gap:.3rem min(1.05rem,1.7vw);font-size:min(1.04rem,3.55vw);overflow-x:auto;scrollbar-width:none;width:100%;justify-content:safe center}nav.ana::-webkit-scrollbar{display:none}
  nav.ana a.m-ana{display:none}nav.ana a{white-space:nowrap}}
nav.ana a:hover{border-bottom-color:color-mix(in srgb,var(--gold-logo) 45%,transparent)}
.deneme{background:var(--gold-soft);font-style:italic;font-size:.88rem;color:var(--ink-soft)}
.deneme .wrap{padding-block:.45rem}
main{padding-block:2.2rem 3.5rem}
h1{font-family:var(--display);font-weight:500;font-size:2.15rem;line-height:1.12;margin:0 0 .6rem;text-wrap:balance}
h2{font-family:var(--display);font-weight:500;font-size:1.4rem;line-height:1.25;margin:1.7rem 0 .45rem;text-wrap:balance}
.ust-etiket{font-style:italic;font-size:.95rem;color:var(--gold);margin:0 0 .35rem}
.yol{font-style:italic;font-size:.92rem;color:var(--ink-soft);margin:0 0 .6rem}
.yol a{color:var(--ink-soft)}
.giris{font-size:1.02rem;line-height:1.5;color:var(--ink-soft);max-width:var(--measure);margin:0 0 1.5rem}
.metin{max-width:var(--measure)}
.metin p{margin:0 0 .8rem}
.metin h2{color:var(--ink);font-size:1.3rem;margin-top:1.6rem}
.metin > h2:first-child + p::first-letter,.metin > p:first-child::first-letter{font-family:var(--display);float:left;font-size:3.4em;line-height:.82;padding:.06em .1em 0 0;color:var(--gold)}
.say{font-style:italic;font-size:.9rem;color:var(--ink-soft);font-variant-numeric:oldstyle-nums}
.say.ayri{display:block;margin-top:.4rem}
.taslak{display:inline-block;font-family:var(--serif);font-style:italic;font-size:.8rem;font-weight:400;color:var(--gold);border:1px solid currentColor;padding:.02rem .45rem;border-radius:2px;margin-left:.5rem;vertical-align:.2em}
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
.anakart h3{margin:0;font-family:var(--display);font-size:1.25rem;font-weight:500;line-height:1.25}
.anakart h3 a{color:var(--ink);text-decoration:none}
.anakart h3 a:hover{color:var(--accent)}
.anakart.bos h3{font-weight:500}
.anakart p{margin:0;font-size:.93rem;color:var(--ink-soft)}
/* Kart süsü: üstte altın çizgi, sağ altta logodaki kemerin silik izi; üzerine gelince hafifçe kalkar */
.anakart{border-top:3px solid var(--gold-logo);background:var(--card) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='12 10 40 44'%3E%3Cpath d='M20.5 50V31A19 19 0 0 1 32 13.5 19 19 0 0 1 43.5 31V50M15.5 50h33' fill='none' stroke='%23c9a14a' stroke-opacity='.22' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M31.4 23.5c2.4 4.4 6.6 7.4 6.6 13.4a6 6 0 0 1-12 0c0-3.6 1.9-6 3.9-8.1.2 2.1 1 3.5 2.3 4 .9-3 .3-6.4-.8-9.3z' fill='%23c9a14a' fill-opacity='.14'/%3E%3C/svg%3E") no-repeat right .9rem bottom .8rem/2.6rem auto;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
.anakart:hover{transform:translateY(-2px);border-top-color:var(--accent);box-shadow:0 16px 30px -22px rgba(20,30,50,.5)}
.anakart .ilgili{padding-right:2.8rem}
@media (prefers-reduced-motion:reduce){.anakart{transition:none}.anakart:hover{transform:none}}
.olcu{height:4px;background:var(--panel)}
.olcu span{display:block;height:100%;background:var(--accent)}
.altlar{list-style:none;padding:0;margin:.15rem 0 0;display:flex;flex-wrap:wrap;gap:.35rem}
.altlar li{font-family:var(--serif);font-size:.82rem;padding:.08rem .55rem;border:1px solid var(--rule);background:var(--paper)}
.altlar li.dolu{border-color:var(--accent);background:var(--accent-soft)}
.altlar li.plan .duz{color:var(--ink-soft)}
.ilgili{font-style:italic;font-size:.88rem;color:var(--ink-soft)}
/* Argüman kutuları (fiş metinlerinde) */
.arguman{margin:1.5rem 0 1.7rem;background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--gold-logo);border-radius:10px;padding:.95rem 1.2rem 1rem;max-width:var(--measure)}
.arguman figcaption{font-family:var(--display);font-size:1.12rem;color:var(--ink);margin-bottom:.55rem;line-height:1.3}
.arg-tur{display:inline-block;font-family:var(--sans);font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;color:var(--gold);border:1px solid var(--gold-logo);border-radius:999px;padding:.08rem .5rem;margin-right:.45rem;vertical-align:.18em}
.arguman ol{list-style:none;margin:0;padding:0}
.arguman li{display:grid;grid-template-columns:3.1rem 1fr;gap:.5rem;padding:.32rem 0;border-top:1px dashed var(--rule);font-size:.97rem;line-height:1.45}
.arguman li:first-child{border-top:0}
.arg-no{font-family:var(--sans);font-size:.85rem;font-weight:600;color:var(--accent);text-align:right;padding-top:.1rem}
.arguman li.arg-sonuc{border-top:1px solid var(--accent);margin-top:.15rem;padding-top:.45rem;font-weight:500}
.arguman li.arg-sonuc .arg-no{color:var(--gold);font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}
.arg-not{margin:.6rem 0 0;font-size:.9rem;color:var(--ink-soft)}
.arg-kaynak{margin:.5rem 0 0;font-size:.84rem;font-style:italic;color:var(--ink-soft)}
@media (max-width:520px){.arguman{padding:.8rem .85rem}.arguman li{grid-template-columns:2.9rem 1fr;gap:.4rem}.arguman li.arg-sonuc .arg-no{font-size:.7rem}}

/* Listeler */
.liste{list-style:none;margin:0;padding:0;border-top:1px solid var(--rule)}
.liste li{padding:.75rem 0;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:minmax(0,15rem) minmax(0,1fr);gap:.2rem 1.5rem}
.liste .ad{font-weight:600}
.liste .alt-ad{display:block;font-weight:400;font-style:italic;color:var(--ink-soft);font-size:.92rem}
.liste .ad a{font-family:var(--display);font-size:1.1rem;font-weight:500}
.liste .aciklama{color:var(--ink-soft);font-size:.96rem}
.harf{font-family:var(--display);color:var(--gold);font-size:1.4rem;margin:1.8rem 0 .2rem}
.makale{padding:1.3rem 0;border-bottom:1px solid var(--rule);display:grid;grid-template-columns:7.5rem minmax(0,1fr);gap:0 1.5rem}
.makale time{color:var(--gold);font-style:italic;font-size:.92rem;padding-top:.35rem}
.makale h3{margin:0;font-family:var(--display);font-size:1.25rem;font-weight:500;line-height:1.3}
.makale h3 a{color:var(--ink);text-decoration:none}
.makale h3 a:hover{color:var(--accent)}
.makale .orij{margin:.25rem 0 0;color:var(--ink-soft);font-style:italic;font-size:.94rem}
.makale .kunye{margin:.3rem 0 0;color:var(--ink-soft);font-size:.92rem}
.makale .ozet{margin:.6rem 0 0;max-width:var(--measure)}

/* Fiş sayfası */
.fis-duzen{display:grid;grid-template-columns:minmax(0,1fr) 18rem;gap:2.6rem;align-items:start}
.kart{background:var(--card);border:1px solid var(--rule);box-shadow:0 1px 0 var(--rule),0 12px 30px -24px rgba(20,30,50,.35);padding:1.6rem 1.8rem 1.3rem;min-width:0}
.kart .alt-ad{margin:-.2rem 0 1rem;color:var(--ink-soft);font-style:italic;font-size:1.05rem}
.kart .kisa{font-weight:500;font-size:1.05rem;max-width:var(--measure)}
.klasik{background:var(--gold-soft);padding:.85rem 1.05rem;margin:1.2rem 0;max-width:var(--measure);font-size:.96rem}
.klasik .bas{font-style:italic;margin:0 0 .4rem}
.klasik p{margin:0}
.klasik.bos{background:transparent;border:1px dashed var(--rule);min-height:3.6rem}
dl.kunye{margin:1.3rem 0 0;display:grid;gap:.45rem;font-size:.95rem;padding-top:1rem;border-top:1px solid var(--rule)}
dl.kunye div{display:grid;grid-template-columns:9.5rem minmax(0,1fr);gap:1rem}
dl.kunye dt{color:var(--ink-soft);font-style:italic;font-size:.92rem;padding-top:.05rem}
dl.kunye dd{margin:0;min-width:0}
.imza{font-style:italic;font-size:.88rem;color:var(--ink-soft);margin:1.3rem 0 0;text-align:right}
aside.yan{background:transparent;padding:.2rem 0 .2rem 1.3rem;font-size:.95rem;border-left:1px solid var(--gold);position:sticky;top:calc(env(safe-area-inset-top,0px) + 1rem)}
aside.yan h2{font-family:var(--display);font-style:italic;font-size:1.15rem;color:var(--gold);margin:0 0 .35rem;font-weight:500}
aside.yan ul{list-style:none;margin:0 0 1.1rem;padding:0;display:grid;gap:.3rem}
aside.yan ul:last-child{margin-bottom:0}
aside.yan .tur-k{font-style:italic;font-size:.82rem;color:var(--ink-soft);margin-right:.35rem}
.sorular{padding-left:1.3rem;max-width:var(--measure)}.sorular li{margin-bottom:.5rem}
.kutu{background:var(--card);border:1px solid var(--rule);padding:.9rem 1.1rem;margin:1.2rem 0;font-size:.95rem;max-width:var(--measure)}
.kutu dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:.25rem 1rem}
.kutu dt{color:var(--ink-soft)}.kutu dd{margin:0}
.etiketler{margin-top:1.4rem;font-family:var(--sans);font-size:.88rem;color:var(--ink-soft);display:flex;flex-wrap:wrap;gap:.3rem .9rem}
/* Eserler sayfası */
.tur-secici{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1.6rem}
.tur-secici button{font-family:var(--serif);font-size:.95rem;padding:.3rem .9rem;border:1px solid var(--rule);background:var(--card);color:var(--ink);cursor:pointer;border-radius:999px}
.tur-secici button[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.tur-secici button[aria-pressed="true"] .say{color:inherit;opacity:.75}
.tez-sec button{font-family:var(--sans);font-size:.82rem;padding:.25rem .7rem;border-radius:6px}
.tez-sec{margin-bottom:.5rem}
@media(max-width:640px){.tez-sec{flex-wrap:nowrap;gap:.3rem}.tez-sec button{font-size:.78rem;padding:.25rem .5rem;white-space:nowrap}.tez-sec .say{font-size:.78rem}}
.baslik-gezinti ul{list-style:none;margin:0 0 1rem;padding:0;display:flex;flex-wrap:wrap;gap:.4rem}
.baslik-gezinti li{font-size:.92rem;padding:.12rem .65rem;border:1px solid var(--rule);background:var(--card);border-radius:999px}
.baslik-gezinti li.dolu{border-color:var(--accent);background:var(--accent-soft)}
.baslik-gezinti li.plan{color:var(--ink-soft)}
.baslik-gezinti a{text-decoration:none;color:var(--ink)}
.eser-bolum{border-top:1px solid var(--gold-logo);padding-top:.4rem;margin-top:2rem;scroll-margin-top:1rem}
.eser-bolum h2{margin:.3rem 0 .6rem;font-size:1.4rem;font-weight:500;display:flex;align-items:baseline;gap:.7rem}
.eser-bolum h2 a,.eser-bolum h3 a{color:var(--ink);text-decoration:none}
.eser-bolum h3{font-family:var(--display);font-style:italic;font-size:1.15rem;color:var(--gold);margin:1.2rem 0 .3rem;font-weight:500}
.eser-bolum h3 a{color:var(--accent-ink)}
.aciklama-kisa{font-family:var(--sans);font-size:.84rem;line-height:1.5;color:var(--ink-soft);margin:0 0 .8rem;max-width:52rem}
/* açıklama notları gövde metninden ayrılsın: farklı yazı ailesi, küçük punto ve başta bilgi işareti */
/* not işareti: logonun renklerinde (lâcivert zemin, altın ünlem) küçük bir yuvarlak */
.aciklama-kisa::before{content:"!";display:inline-block;width:1.25em;height:1.25em;line-height:1.25em;margin-right:.45em;
  border-radius:50%;background:var(--accent);color:var(--gold-logo);font-family:var(--display);font-weight:700;font-style:normal;
  font-size:.92em;text-align:center;vertical-align:.08em}
.sekmeler{margin-top:.4rem}
.sekmeler button{font-size:1rem;padding:.45rem 1.1rem}
@media(max-width:640px){.sekmeler{flex-wrap:nowrap;gap:.3rem}.sekmeler button{font-size:.82rem;padding:.35rem .5rem;white-space:nowrap}.sekmeler .say{font-size:.78rem}}
.sekme-bolum{margin-top:1rem}
.eser-sekme{border-top:0;margin-top:.6rem;padding-top:0}
.eser-sekme h2.sekme-ad{display:none}
.m-arac{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 1rem;margin:.6rem 0 .9rem}
.m-arac .k-ara{margin:0}
.m-sec select{font:inherit;font-size:.95rem;color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:999px;padding:.4rem .8rem;max-width:18rem}
table.makaleler td.m-yazar{width:15%;font-size:.92rem}
table.makaleler td.m-makale a{color:var(--ink);text-decoration:none;font-weight:500}
table.makaleler td.m-makale a:hover{color:var(--accent);text-decoration:underline}
table.makaleler td.m-yil{white-space:nowrap;font-variant-numeric:tabular-nums}
table.makaleler td.m-konu{width:20%;font-size:.88rem;font-style:italic}
.m-dergi{display:block;font-size:.86rem;font-style:italic;color:var(--ink-soft);margin-top:.15rem}
.m-kaynak{display:inline-block;font-size:.7rem;letter-spacing:.03em;color:var(--accent);border:1px solid currentColor;border-radius:6px;padding:0 .35rem;margin-left:.35rem;vertical-align:.1em;opacity:.8}
.m-tur{display:inline-block;font-size:.75rem;font-style:italic;color:var(--gold);border:1px solid currentColor;border-radius:6px;padding:0 .4rem;margin-left:.35rem;vertical-align:.1em}
table.kisiler tbody tr:target{background:var(--accent-soft)}
.k-makale{font-size:.85rem;white-space:nowrap}
.tr-makaleler{margin-top:2rem}
.tr-makaleler .m-liste{list-style:none;padding:0;margin:.4rem 0 .6rem;max-width:var(--measure)}
.tr-makaleler .m-liste li{padding:.45rem 0;border-bottom:1px solid var(--rule)}
.tr-makaleler .m-liste a{color:var(--ink);text-decoration:none}
.tr-makaleler .m-liste a:hover{color:var(--accent);text-decoration:underline}
.tr-makaleler h3{font-family:var(--display);font-style:italic;font-weight:500;color:var(--gold);font-size:1.1rem;margin:1.2rem 0 .2rem}
.m-hepsi{margin:.3rem 0 0;font-size:.95rem}
.m-yil-tel{display:none}
/* Akademisyen sayfasının künyesi: kartvizit */
.kartvizit{position:relative;display:flex;gap:1.4rem;align-items:flex-start;width:fit-content;max-width:100%;margin:.4rem 0 1.3rem;
  padding:1.5rem 1.7rem 1.3rem;background:#fff;border:1px solid var(--accent);border-radius:14px;
  box-shadow:6px 6px 0 color-mix(in srgb,var(--gold-logo) 55%,transparent),0 18px 34px -24px rgba(20,30,50,.45)}
.kv-monogram{flex:none;width:4.2rem;height:4.2rem;border-radius:50%;background:var(--accent);color:var(--gold-logo);
  display:flex;align-items:center;justify-content:center;font-family:var(--display);font-size:1.6rem;letter-spacing:.04em}
.kv-govde{min-width:0}
.kv-unvan{margin:0;font-style:italic;font-size:.92rem;color:var(--gold)}
.kartvizit h1{margin:.1rem 0 .45rem;font-size:2rem;line-height:1.15;padding-right:2.6rem}  /* uzun adlar logonun altına girmesin */
.kv-kurum{margin:0;font-size:.98rem;color:var(--ink-soft);line-height:1.5}
.kv-bag{margin:.9rem 0 0;padding-top:.7rem;border-top:1px solid var(--gold-logo);display:flex;flex-wrap:wrap;gap:.3rem 1.4rem;font-style:italic;font-size:.92rem}
.kv-bag a{white-space:nowrap}
.kv-logo{position:absolute;top:1rem;right:1.7rem;width:34px;height:34px;border-radius:8px;opacity:.9}  /* sağ kenarı içerikle (ORCID satırı) aynı hizada */
@media (max-width:560px){.kartvizit{flex-direction:column;gap:.9rem;padding:1.2rem 1.2rem 1.1rem;box-shadow:4px 4px 0 color-mix(in srgb,var(--gold-logo) 55%,transparent)}
  .kv-monogram{width:3.4rem;height:3.4rem;font-size:1.3rem}.kartvizit h1{font-size:1.65rem}}
.akademi-not{margin-top:1.6rem;font-size:.8rem}
.guncel .gn-ay{font-family:var(--sans);font-size:.95rem;color:var(--gold);font-weight:400;margin-left:.5rem}
.gn-izgara{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.6fr);gap:1.4rem;align-items:stretch}
.gn-kart{background:var(--card);border:1px solid var(--rule);box-shadow:0 1px 0 var(--rule),0 14px 30px -22px rgba(20,30,50,.4);border-top:3px solid var(--accent);border-radius:4px;padding:1rem 1.15rem 1.1rem;display:flex;flex-direction:column}
.gn-kart.gn-tebrik{border-top-color:var(--gold-logo)}
.gn-kart h3{font-family:var(--display);font-weight:500;font-size:1.25rem;margin:0 0 .6rem}
.gn-liste{list-style:none;margin:0;padding:0}
.gn-liste li{padding:.5rem 0;border-top:1px solid var(--rule);line-height:1.35}
.gn-liste li:first-child{border-top:0;padding-top:0}
.gn-liste a{font-family:var(--display);font-size:1.05rem}
.gn-alt,.gn-konu{display:block;font-family:var(--sans);font-size:.8rem;color:var(--ink-soft);margin-top:.15rem}
.gn-alt a{font-family:inherit;font-size:inherit}  /* künyedeki yazar bağlantıları başlık boyutunda olmasın */
.gn-konu{color:var(--gold)}
.gn-tur{display:inline-block;font-family:var(--sans);font-size:.72rem;letter-spacing:.04em;text-transform:uppercase;color:var(--gold);margin-right:.5rem}
.gn-bos{font-style:italic;color:var(--ink-soft);margin:.2rem 0 .6rem}
.gn-not{margin:.8rem 0 0}
.gn-tebrik-soz{font-family:var(--display);font-style:italic;font-size:1.08rem;line-height:1.4;color:var(--gold);text-align:center;
  margin:.1rem 0 .9rem;padding:.55rem .6rem;border-top:1px solid var(--gold-logo);border-bottom:1px solid var(--gold-logo)}
.gn-tebrik-soz span span{font-style:normal}
.gn-liste li.gn-tb{display:flex;align-items:center;justify-content:space-between;gap:.7rem}
.kutla{flex:none;display:inline-flex;align-items:center;gap:.3rem;font-family:var(--sans);font-size:.78rem;line-height:1;
  padding:.32rem .6rem;border:1px solid var(--gold-logo);border-radius:999px;background:transparent;color:var(--accent-ink);cursor:pointer}
.kutla:hover{background:color-mix(in srgb,var(--gold-logo) 14%,transparent)}
.kutla .k-sayi{font-weight:700}
.kutla.kutlandi{background:var(--accent);border-color:var(--accent);color:#fff;cursor:default}
.kutla.kutlandi .k-sayi{color:var(--gold-logo)}
.gn-hepsi{font-family:var(--sans);font-size:.88rem;margin:auto 0 0;padding-top:.6rem}
.gn-yollar{display:flex;flex-wrap:wrap;gap:.5rem 1.8rem;justify-content:center;font-family:var(--display);font-size:1.15rem;margin:2.2rem 0 1rem}
@media (min-width:901px){.gn-izgara .gn-tebrik-soz{display:grid;align-items:center;min-height:calc(2.8em + 1.1rem + 2px);box-sizing:border-box}}
@media (max-width:900px){.gn-izgara{grid-template-columns:1fr}}
.onceki-gunler{list-style:none;margin:.4rem 0 0;padding:0;max-width:52rem}
.onceki-gunler li{display:grid;grid-template-columns:7.5rem minmax(0,1fr);column-gap:1rem;padding:.55rem 0;border-top:1px solid var(--rule)}
.onceki-gunler li:first-child{border-top:0}
.onceki-gunler .og-tarih{font-family:var(--sans);font-size:.82rem;color:var(--gold);padding-top:.15rem}
.onceki-gunler a{font-family:var(--display);font-size:1.08rem;line-height:1.3}
.onceki-gunler .og-yazar{grid-column:2;font-size:.85rem;color:var(--ink-soft)}
.og-hepsi{margin:.6rem 0 0;font-style:italic}
@media (max-width:560px){.onceki-gunler li{grid-template-columns:1fr}.onceki-gunler .og-yazar{grid-column:1}}
.akademi-metin{max-width:none}  /* yayın paneli yan sütuna kadar uzanır */
.akademi-metin .yayin-panel{margin-top:0}
.aciklama-kisa.akademi-not{max-width:none;margin:1rem 0 0}  /* sayfa genişliğinde, yan sütunun altına da uzanır */
/* kişi sayfası yayın paneli: kartvizitten daha sakin bir kart */
.yayin-panel{background:var(--card);border:1px solid color-mix(in srgb,var(--gold-logo) 35%,var(--rule));border-radius:10px;
  box-shadow:0 2px 10px rgba(35,68,110,.06);padding:1rem 1.2rem 1.1rem;margin-top:1.4rem}
.yp-bas{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:.3rem 1rem}
.yp-bas h2{margin:0}
.yp-sirala{display:flex;align-items:baseline;gap:.15rem .6rem;font-family:var(--sans);font-size:.8rem;color:var(--ink-soft)}
.yp-sirala button{font:inherit;background:none;border:0;padding:.1rem .15rem;color:var(--ink-soft);cursor:pointer;border-bottom:1px solid transparent}
.yp-sirala button[aria-pressed="true"]{color:var(--accent-ink);border-bottom-color:var(--gold-logo)}
.yp-sirala .ok{display:inline-block;min-width:.7em;margin-left:.15em}
.yp-sekme{margin:.7rem 0 .3rem}
.yp-sekme button{font-size:.88rem;padding:.2rem .75rem}
.yayin-liste{list-style:none;margin:.4rem 0 0;padding:0;counter-reset:yayin}
/* Geniş ekranda yayın panelinin alt kenarı ekranın alt kenarında biter (yüksekliği yayın JS'i verir); liste uzunsa çerçevenin içinde kayar.
   Yayını az olanla çok olanın paneli böylece aynı boyda olur. Dar ekranda sayfa olağan biçimde akar. */
@media (min-width:761px){
  .yayin-panel.boylu{display:flex;flex-direction:column}
  .yayin-panel.boylu .yayin-liste{flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;
    scrollbar-color:color-mix(in srgb,var(--gold-logo) 60%,transparent) transparent;padding-right:.4rem;border-top:1px solid var(--rule)}
}
.yayin-liste li{counter-increment:yayin;position:relative;padding:.6rem 0 .6rem 2.1rem;border-top:1px solid var(--rule)}
.yayin-liste li:first-child{border-top:0}
.yayin-liste li::before{content:counter(yayin) ".";position:absolute;left:0;top:.62rem;width:1.6rem;text-align:right;
  font-family:var(--sans);font-size:.85rem;color:var(--gold)}
.yayin-liste .eser-ad{font-weight:600}
.yayin-liste .eser-bilgi{display:block}
.yt{display:inline-block;font-family:var(--sans);font-size:.68rem;font-weight:600;letter-spacing:.03em;text-transform:uppercase;
  padding:.05rem .4rem;border-radius:4px;margin-right:.45rem;vertical-align:.12em;border:1px solid currentColor;color:var(--ink-soft)}
.yt-kitap{background:var(--accent);border-color:var(--accent);color:#fff}
.yt-kitap-bolumu{color:var(--accent)}
.yt-makale{color:var(--gold)}
.yt-bildiri,.yt-tez{color:var(--accent-ink)}
.calisanlar{margin-top:2rem}
ul.calisan-liste{list-style:none;padding:0;margin:.4rem 0 0;display:flex;flex-wrap:wrap;gap:.35rem .5rem;max-width:var(--measure)}
ul.calisan-liste li{font-size:.92rem;padding:.12rem .65rem;border:1px solid var(--rule);background:var(--card);border-radius:999px}
ul.calisan-liste li a{text-decoration:none;color:var(--ink)}
ul.calisan-liste li a:hover{color:var(--accent)}
aside.yan ul.calisan-liste.dikey{flex-direction:column;align-items:flex-start;gap:.3rem}
.calisan-devam{margin-top:.55rem;max-width:var(--measure)}
.calisan-devam summary{cursor:pointer;font-family:var(--sans);font-size:.88rem;color:var(--accent);list-style:none;display:inline-block;border-bottom:1px solid var(--gold-logo)}
.calisan-devam summary::-webkit-details-marker{display:none}
.calisan-devam summary::after{content:" ↓"}
.calisan-devam[open] summary::after{content:" ↑"}
.calisan-devam[open] summary{margin-bottom:.2rem}
@media (max-width:520px){ul.calisan-liste{gap:.3rem .35rem}ul.calisan-liste li{font-size:.84rem;padding:.06rem .5rem}}
.k-ara{display:flex;align-items:center;gap:.6rem;font-style:italic;font-size:.95rem;color:var(--ink-soft);margin:.8rem 0 .9rem}
.k-ara input{font:inherit;font-style:normal;font-size:.98rem;color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:999px;padding:.4rem .9rem;width:min(100%,22rem)}
.k-ara input:focus{outline:2px solid var(--accent);outline-offset:1px}
.anakart[hidden],.harita[hidden],h2.kume-ad[hidden]{display:none}
.tablo-kap{overflow-x:auto}
table.kisiler{width:100%;border-collapse:collapse;font-size:.95rem}
button.sirala{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:.3rem}
button.sirala:hover{color:var(--ink)}
button.sirala:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
th[aria-sort="ascending"] button.sirala,th[aria-sort="descending"] button.sirala{color:var(--ink)}
.ok::after{content:"↕";opacity:.35;font-size:.9em}
th[aria-sort="ascending"] .ok::after{content:"▲";opacity:1;font-size:.7em}
th[aria-sort="descending"] .ok::after{content:"▼";opacity:1;font-size:.7em}
button.sirala[aria-sort="ascending"] .ok::after{content:"▲";opacity:1;font-size:.7em}
button.sirala[aria-sort="descending"] .ok::after{content:"▼";opacity:1;font-size:.7em}
table.kisiler th{text-align:left;font-style:italic;font-size:.95rem;color:var(--ink-soft);font-weight:400;padding:.4rem .7rem .4rem 0;border-bottom:1px solid var(--gold-logo)}
table.kisiler td{padding:.55rem .7rem .55rem 0;border-bottom:1px solid var(--rule);vertical-align:top}
table.kisiler td.k-ad{font-weight:600}
table.kisiler tbody tr:hover{background:var(--panel)}
.emekli{display:inline-block;font-style:italic;font-size:.8rem;font-weight:400;color:var(--gold);border:1px solid currentColor;padding:0 .35rem;border-radius:2px;margin-left:.3rem}
.gizli{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
ul.eserler{list-style:none;margin:0;padding:0;columns:2 26rem;column-gap:2.5rem}
.secim-etiket{margin:1rem 0 .35rem;font-family:var(--sans);font-size:.72rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--gold)}
.secim-ayrac{border-top:1px solid color-mix(in srgb,var(--gold-logo) 45%,var(--rule));padding-top:.8rem;margin-top:.9rem}
label.secim-etiket{display:block}
h2.eser-grup{font-size:1.25rem;font-weight:500;margin:1.6rem 0 .3rem;padding-bottom:.25rem;border-bottom:1px solid var(--gold-logo)}
h2.eser-grup[hidden],.eser-grup-not[hidden],ul.eser-liste[hidden]{display:none}
.eser-grup-say{font-family:var(--sans);font-size:.8rem;font-style:italic;color:var(--ink-soft);font-weight:400}
.eser-grup-not{margin:.2rem 0 .3rem;font-size:.9rem;font-style:italic;color:var(--ink-soft)}
.eser-konu-kap{position:relative;max-width:26rem;margin:0 0 .4rem}
.eser-konu-kap::after{content:"";position:absolute;right:1rem;top:50%;width:.5rem;height:.5rem;border-right:2px solid var(--accent);border-bottom:2px solid var(--accent);transform:translateY(-70%) rotate(45deg);pointer-events:none}
select.eser-konu-sec{appearance:none;-webkit-appearance:none;width:100%;font:inherit;font-family:var(--display);font-size:1.02rem;color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:999px;padding:.5rem 2.6rem .5rem 1rem;cursor:pointer}
input.eser-konu-sec{appearance:none;-webkit-appearance:none;width:100%;font:inherit;font-family:var(--display);font-size:1.02rem;color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:999px;padding:.5rem 1rem}
.eser-ara-kap::after{display:none}
.eser-ara-etiket{margin-top:.7rem}
.tez-liste{list-style:none;padding:0;margin:.2rem 0 0}
.tez-liste li{padding:.75rem 0;border-bottom:1px solid var(--rule)}
.tez-liste li[hidden]{display:none}
.tez-ad{margin:0 0 .15rem;font-family:var(--display);font-size:1.08rem;font-weight:500;color:var(--ink)}
.tez-kunye,.tez-yer{margin:0;font-size:.92rem;color:var(--ink-soft)}
.tez-yer{font-style:italic;font-size:.86rem}
.tez-ust{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:.25rem 1rem}
.tez-ust .tez-ad{flex:1 1 20rem;min-width:0}
.tez-rozetler{display:inline-flex;flex-shrink:0;gap:.35rem;align-items:center;padding-top:.2rem}
.tz-r{display:inline-block;font-family:var(--sans);font-size:.68rem;font-weight:600;letter-spacing:.03em;text-transform:uppercase;line-height:1.3;padding:.08rem .5rem;border:1px solid;border-radius:4px;white-space:nowrap;cursor:default}
.tz-yl{color:var(--accent-ink);border-color:var(--accent);background:var(--accent-soft)}
.tz-dr{color:#fff;border-color:var(--accent);background:var(--accent)}
.tz-tamam{color:#a84a14;border-color:#a84a14;background:#fff}
.tz-devam{color:#fff;border-color:#a84a14;background:#a84a14}
.yayin-liste .tez-rozetler{margin-left:.5rem;padding-top:0;vertical-align:.1em}
.tez-durum-etiket{margin-top:.7rem}
select.eser-konu-sec:focus,input.eser-konu-sec:focus{outline:2px solid var(--accent);outline-offset:1px}
.kt-cizim-kap{max-width:52rem;border:1px solid var(--rule);background:var(--card);border-radius:8px;padding:.8rem .9rem .6rem;margin:1.2rem 0 1.4rem}
.kt-secili{display:flex;flex-wrap:wrap;align-items:center;gap:.35rem .7rem;min-height:1.9rem;font-family:var(--sans);font-size:.85rem;color:var(--ink-soft)}
.kt-cip{font-family:var(--sans);font-size:.84rem;background:none;border:1px solid;border-radius:6px;padding:.15rem .55rem;cursor:pointer}
.kt-bag{font-size:.78rem;color:var(--ink-soft)}
.kt-cizim{width:100%;height:auto;display:block;margin:.4rem 0 .2rem;font-family:var(--sans)}
.kt-izgara{stroke:var(--rule);stroke-width:1}
.kt-eksen{fill:var(--ink-soft)}
.kt-silik{fill:var(--ink);opacity:.04}
.kt-imlec{stroke:var(--ink-soft);stroke-width:1;stroke-dasharray:3 3}
.kt-ipucu{font-family:var(--sans);font-size:.82rem;color:var(--ink-soft);min-height:2.4em;margin:.2rem 0 .5rem}
.kt-ipucu span{white-space:nowrap}
.kt-ayar{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem .8rem}.kt-ayar .secim-etiket{margin:0}.kt-ayar .tur-secici{margin:0}
.kt-kaynak button,.kt-liste button{font-family:var(--sans);font-size:.82rem;padding:.25rem .7rem;border-radius:6px}
.kt-not{font-family:var(--sans);font-size:.82rem;color:var(--ink-soft);margin:.2rem 0 .6rem}
.kt-tablo-kap{overflow-x:auto}
.kt-suruyor{color:var(--ink-soft);font-size:.78rem}
.kt-tablo{border-collapse:collapse;font-family:var(--sans);font-size:.88rem;width:100%;max-width:44rem}
.kt-tablo th,.kt-tablo td{text-align:left;padding:.35rem .6rem;border-bottom:1px solid var(--rule);white-space:nowrap}
.kt-tablo th{font-weight:600;color:var(--ink-soft);font-size:.8rem}
.kt-sec{font:inherit;background:none;border:0;padding:0;color:var(--accent);cursor:pointer;border-bottom:1px solid var(--gold-logo)}
.eser-arac{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 1.2rem;margin:0 0 .4rem}
.eser-arac .tur-secici,.eser-arac .k-ara{margin:0}
/* tür seçicisi konu düğmelerinden ayrışsın: düz yazı, köşeli, küçük */
.eser-tur-sec button{font-family:var(--sans);font-size:.82rem;padding:.25rem .7rem;border-radius:6px}
.eser-ust{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:.3rem 1.5rem;max-width:52rem;margin:.7rem 0 .2rem;border-bottom:1px solid var(--gold-logo);padding-bottom:.3rem}
.eser-sayi{font-style:italic;font-size:.9rem;color:var(--ink-soft);margin:0}
.eser-sirala{display:flex;gap:1rem;align-items:baseline;font-style:italic;font-size:.92rem;color:var(--ink-soft)}
.eser-sirala button.sirala{color:var(--ink-soft)}
.eser-sirala button[aria-sort="ascending"],.eser-sirala button[aria-sort="descending"]{color:var(--ink)}
.eser-tur-sec button[hidden]{display:none}
ul.eser-liste{list-style:none;margin:0;padding:0;max-width:52rem}
ul.eser-liste li{padding:.55rem 0;border-bottom:1px solid var(--rule)}
ul.eser-liste li[hidden]{display:none}
.eser-konu{font-style:italic}
ul.eserler li{break-inside:avoid;padding:.5rem 0;border-bottom:1px solid var(--rule)}
.eser-ad{font-weight:600;color:var(--ink);text-decoration:none;font-size:.98rem;line-height:1.4}
.eser-ad:hover{color:var(--accent)}
.eser-bilgi a.dis{font-weight:600}
.rozet{display:inline-block;font-family:var(--sans);font-style:normal;font-size:.68rem;font-weight:600;letter-spacing:.04em;color:var(--ink-soft);border:1px solid var(--rule);background:var(--card);padding:.02rem .42rem;border-radius:6px;vertical-align:.12em;margin-left:.35rem}
.rozet.ae-rozet{color:var(--accent-ink);background:var(--accent-soft);border-color:transparent;letter-spacing:0}
.ae{display:inline-block;font-family:var(--sans);font-size:.72rem;font-weight:600;color:var(--accent-ink);background:var(--accent-soft);padding:.02rem .4rem;border-radius:2px}
.eser-bilgi{display:block;font-size:.9rem;color:var(--ink-soft);margin-top:.15rem}
footer.site{border-top:1px solid var(--gold-logo);box-shadow:inset 0 -4px 0 var(--accent);background:var(--paper);color:var(--ink-soft);font-style:italic;font-size:.82rem}
footer.site .wrap{padding-block:1rem 1.3rem;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:.3rem 2rem}
footer.site p{margin:0}
footer.site a{color:var(--ink-soft)}
footer.site .iletisim a{text-decoration:none}
footer.site .iletisim .adres{text-decoration:underline;text-decoration-thickness:1px;text-decoration-color:color-mix(in srgb,var(--gold-logo) 70%,transparent);text-underline-offset:3px}
footer.site .simge{font-style:normal;margin-right:.3em}
@media (max-width:560px){
  /* telefonda sayfa altı ortalı, küçük ve düz yazıyla iki satır */
  footer.site .wrap{flex-direction:column;align-items:center;gap:.25rem;text-align:center;padding-block:.8rem 1rem}
  footer.site{font-family:var(--sans);font-style:normal;font-size:.7rem;letter-spacing:-.005em}
  footer.site .alan{display:none}  /* site adı telefonda tekrar edilmez, satır kısalsın */
}
footer.site a:hover{color:var(--accent-ink)}
.atif{margin:1.2rem 0 0;padding:.45rem .7rem;border:1px solid var(--rule);border-radius:8px;font-family:"Times New Roman",Times,serif;font-size:.8rem;line-height:1.35;max-width:var(--measure);background:transparent;color:var(--ink-soft)}
.atif .ust-etiket{display:inline;font-family:inherit;font-size:inherit;font-style:italic;color:var(--ink-soft);margin:0 .3rem 0 0}
.atif p{display:inline;margin:0}
.atif .atif-metin{color:var(--ink);word-break:break-word}
.kunye-kopyala{font:inherit;font-style:italic;font-size:.82rem;background:none;border:0;padding:0;margin-left:.3rem;color:var(--accent-ink);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.atif button{font:inherit;font-style:italic;margin-left:.4rem;background:none;border:0;padding:0;color:var(--accent-ink);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
/* Yumuşak köşeler: büyük kutular 14px, küçük etiketler 6px */
.okuma,.kart,.anakart,.kutu,.klasik,.klasik.bos{border-radius:14px}
.okuma,.kart{overflow:hidden}
.taslak,.emekli,.ae{border-radius:6px;padding-inline:.45rem}
.altlar li{border-radius:999px}
table.kisiler tbody tr:hover td:first-child{border-radius:8px 0 0 8px}
table.kisiler tbody tr:hover td:last-child{border-radius:0 8px 8px 0}
/* Hakkında */
.hakkinda h1{margin-bottom:.5rem}
.hk-giris{margin:0 0 1.4rem;font-size:.95rem;line-height:1.5;max-width:none;color:var(--ink)}
.hk-izgara{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem 1.8rem;border-top:1px solid var(--rule);padding-top:.9rem}
.hk-izgara h2{font-size:1.08rem;margin:0 0 .2rem}
.hk-izgara p{margin:0;font-size:.88rem;line-height:1.45;color:var(--ink-soft)}
@media (max-width:980px){.hk-izgara{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.hk-izgara{grid-template-columns:1fr}}
/* Önizleme kartı */
.onizleme{position:absolute;z-index:50;width:min(22rem,calc(100vw - 16px));background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:.8rem 1rem .85rem;box-shadow:0 18px 40px -24px rgba(20,30,50,.5);pointer-events:none;font-size:.92rem;line-height:1.45}
.onizleme p{margin:0}
.onizleme-tur{font-style:italic;color:var(--gold);font-size:.85rem}
.onizleme-ad{font-family:var(--display);font-size:1.25rem;color:var(--ink);line-height:1.2;margin-top:.1rem!important}
.onizleme-alt{font-style:italic;color:var(--ink-soft);font-size:.86rem;margin-top:.1rem!important}
.onizleme-metin{color:var(--ink);margin-top:.45rem!important}
a.ic-bag{text-decoration-style:dotted}
/* İlişki ağı */
.ag-arac{display:flex;flex-wrap:wrap;align-items:center;gap:.6rem 1.4rem;margin:0 0 .8rem}
.ag-arac .tur-secici,.ag-arac .k-ara{margin:0}
.ag-tur button[aria-pressed="false"]{opacity:.45;background:var(--card);color:var(--ink);border-color:var(--rule)}
.ag-tur button[aria-pressed="true"]{background:var(--card);color:var(--ink);border-color:var(--ink-soft)}
.nokta{display:inline-block;width:.7em;height:.7em;border-radius:50%;margin-right:.45em;vertical-align:.02em;background:var(--renk)}
.ag-panel ol.ag-makaleler{list-style:none;padding:0;margin:0;display:grid;gap:.35rem;font-size:.9rem}
.ag-panel ol.ag-makaleler a{color:var(--ink);text-decoration:none}
.ag-panel ol.ag-makaleler a:hover{color:var(--accent);text-decoration:underline}
.ag-panel ol.ag-makaleler span{color:var(--ink-soft);font-style:italic}
.ag-sifirla{font:inherit;font-style:italic;font-size:.95rem;color:var(--accent-ink);background:none;border:0;cursor:pointer;text-decoration:underline;text-underline-offset:3px;padding:0}
.ag-kap{position:relative;border:1px solid var(--rule);border-radius:14px;background:var(--card);overflow:hidden}
.ag-tuval{height:min(72vh,700px);min-height:420px;cursor:grab}
.ag-tuval:active{cursor:grabbing}
.ag-tuval svg{display:block;width:100%;height:100%}
.ag-tuval.ag-yukleniyor{background:repeating-linear-gradient(90deg,transparent 0 40%,rgba(0,0,0,.03) 50%,transparent 60% 100%);background-size:200% 100%;animation:ag-yuk 1.2s linear infinite}
@keyframes ag-yuk{to{background-position:-200% 0}}
.ag-baglar line{stroke:#c3c9d2;stroke-width:1.1px;transition:opacity .2s}
.ag-baglar line.vurgu{stroke:#8a6a2c;stroke-width:1.8px}
.ag-baglar line.soluk{opacity:.18}
.ag-dugum{cursor:pointer;transition:opacity .2s}
.ag-dugum circle{stroke:var(--card);stroke-width:2px}
.ag-dugum.secili circle{stroke:var(--ink);stroke-width:2.5px}
.ag-dugum.merkez circle{stroke:var(--accent);stroke-width:3px}
.ag-dugum.merkez text{font-weight:700}
.ag-dugum:focus,.ag-dugum:focus-visible{outline:none}
.ag-dugum:focus-visible circle{stroke:var(--accent);stroke-width:3px}
.ag-dugum text{font-family:var(--serif);fill:var(--ink);text-anchor:middle;paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round;pointer-events:none;opacity:0;transition:opacity .2s}
.ag-dugum text.goster{opacity:1}
.ag-dugum.soluk{opacity:.18}
.ag-dugum.gizli,.ag-baglar line.gizli{display:none}
.ag-panel{position:absolute;top:1rem;right:1rem;width:min(22rem,calc(100% - 2rem));max-height:calc(100% - 2rem);overflow:auto;background:var(--paper);border:1px solid var(--rule);border-radius:12px;padding:1.1rem 1.2rem 1rem;box-shadow:0 14px 34px -22px rgba(20,30,50,.45)}
.ag-panel h2{margin:0 2rem .4rem 0;font-size:1.45rem}
.ag-tutamak{display:none}
.ag-panel .ag-aciklama{margin:0 0 .6rem;font-size:.95rem;color:var(--ink-soft)}
.ag-panel .ag-ac{font-style:italic}
.ag-panel h3{font-family:var(--display);font-style:italic;font-weight:500;font-size:1.05rem;color:var(--gold);margin:1rem 0 .3rem}
.ag-panel ul{list-style:none;margin:0;padding:0;display:grid;gap:.15rem}
.ag-panel li button{font:inherit;font-size:.93rem;text-align:left;background:none;border:0;padding:.15rem 0;color:var(--accent-ink);cursor:pointer}
.ag-panel li button:hover{text-decoration:underline}
.ag-kapat{position:absolute;top:.5rem;right:.6rem;font:inherit;font-size:1.5rem;line-height:1;background:none;border:0;color:var(--ink-soft);cursor:pointer;padding:.2rem .4rem}
.ag-ipucu{position:absolute;left:1rem;bottom:.6rem;margin:0;font-style:italic;font-size:.85rem;color:var(--ink-soft);pointer-events:none}
.ag-git{display:inline-block;margin-top:1rem;font-style:italic}
.baslik-karsilik{margin:-.4rem 0 .8rem;font-family:var(--sans);font-size:.88rem;color:var(--ink-soft)}
.ag-basliklar{margin:1.2rem 0 0;font-family:var(--sans);font-size:.84rem;line-height:1.9;color:var(--ink-soft)}
.ag-basliklar span{font-weight:600;margin-right:.3rem}
/* Ana sayfa: karşılama, okumaya başlangıç, içindekiler */
.karsilama{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:2rem 4rem;align-items:center;padding-block:1rem 1rem}
.karsilama h1{font-size:2.55rem;margin-bottom:.8rem}
.karsilama p{font-size:1.04rem;line-height:1.5;color:var(--ink-soft);margin:0 0 .8rem}
.karsilama .durum-satiri{font-style:italic;font-size:.98rem}
.karsilama .karsilama-git{display:flex;flex-wrap:wrap;gap:.4rem 1.6rem;font-family:var(--display);font-size:1.2rem;margin-top:1.1rem}
.susleme{display:flex;align-items:center;gap:1rem;color:var(--gold-logo);margin:2.4rem 0 1.4rem}
.susleme::before,.susleme::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,transparent,var(--gold-logo))}
.susleme::after{background:linear-gradient(90deg,var(--gold-logo),transparent)}
.susleme span{font-family:var(--display);font-size:1.3rem;line-height:1}
.okuma{background:var(--card);border:1px solid var(--rule);padding:1.7rem 1.9rem 1.5rem;box-shadow:0 14px 34px -28px rgba(20,30,50,.4)}
.okuma .ust-etiket{margin-bottom:.4rem}
.okuma h2{margin:0 0 .6rem;font-size:1.6rem}
.okuma h2 a{color:var(--ink);text-decoration:none}
.okuma .ozet{font-style:italic;color:var(--ink-soft);margin:0}
.okuma .alinti{margin:0;font-size:.97rem;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}
.okuma .alinti::first-letter{font-family:var(--display);float:left;font-size:3.4em;line-height:.82;padding:.06em .1em 0 0;color:var(--gold)}
.okuma.gunun{border-top:3px solid var(--gold-logo)}
.okuma.gunun h2{font-size:1.45rem;line-height:1.25}
.okuma .orij{margin:0 0 .25rem;font-style:italic;color:var(--ink-soft);font-size:.9rem}
.okuma .kunye{margin:0 0 .7rem;color:var(--ink-soft);font-size:.88rem}
.okuma.gunun .alinti::first-letter{float:none;font-size:inherit;padding:0;color:inherit;font-family:inherit}
.okuma .gunun-git{display:flex;flex-wrap:wrap;gap:.3rem 1.4rem;margin:.9rem 0 0;font-style:italic;font-size:.95rem}
.x-paylas{font-style:italic}
.paylas{margin:1.2rem 0 0}
.gun-adi{display:block;font-size:.85em;color:var(--ink-soft)}
.okuma .devam{display:inline-block;margin-top:.8rem;font-style:italic}
.icindekiler{list-style:none;margin:0;padding:0;columns:2 24rem;column-gap:3.5rem;counter-reset:bas}
.icindekiler li{break-inside:avoid;display:grid;grid-template-columns:2.2rem minmax(0,1fr);gap:0 .4rem;padding:.9rem 0 1rem;border-bottom:1px solid var(--rule)}
.icindekiler .no{font-family:var(--display);font-size:1.3rem;color:var(--gold);line-height:1.25;font-variant-numeric:oldstyle-nums}
.icindekiler h3{margin:0;font-family:var(--display);font-weight:500;font-size:1.25rem;line-height:1.25}
.icindekiler h3 a{color:var(--ink);text-decoration:none}
.icindekiler h3 a:hover{color:var(--accent)}
.icindekiler p{margin:.2rem 0 0;color:var(--ink-soft);font-size:.93rem}
.icindekiler .altlar-metin{margin-top:.35rem;font-size:.95rem;font-style:italic;color:var(--ink-soft)}
.icindekiler .altlar-metin a{font-style:normal}
.icindekiler .say{display:block;margin-top:.25rem}
.icindekiler li.kume-ad{display:block;padding:1.2rem 0 .2rem;border-bottom:1px solid var(--gold-logo);break-after:avoid;font-style:italic;color:var(--gold);font-size:.95rem}
.icindekiler li.kume-ad:first-child{padding-top:0}
h2.kume-ad{font-family:var(--display);font-style:italic;font-weight:500;font-size:1.15rem;color:var(--gold);margin:2rem 0 .7rem;padding-bottom:.25rem;border-bottom:1px solid var(--gold-logo)}
h2.kume-ad:first-of-type{margin-top:1.2rem}
@media (max-width:760px){
  html{font-size:16px}
  .acilis,.fis-duzen,.karsilama{grid-template-columns:1fr;gap:1.5rem}
  .okuma{padding:1.4rem 1.2rem}
  .karsilama h1{font-size:2.05rem}
  h1{font-size:1.85rem}
  aside.yan{border-left:0;border-top:1px solid var(--gold);padding:1rem 0 0}
  .acilis h1{font-size:2rem}
  aside.yan{position:static}
  .liste li,.makale,dl.kunye div{grid-template-columns:1fr;gap:.15rem}
  .kart{padding:1.1rem 1.1rem 1rem}
  /* Telefonda bilgi paneli ekranın altından açılan bir kart olur; ağın altında kaybolmaz. */
  .ag-panel{position:fixed;top:auto;left:0;right:0;bottom:0;width:auto;max-height:60vh;z-index:30;border-radius:16px 16px 0 0;border-width:1px 0 0;padding:.3rem 1.1rem calc(1rem + env(safe-area-inset-bottom));box-shadow:0 -12px 30px -18px rgba(20,30,50,.5);transition:max-height .25s}
  /* kapalı kart: yalnızca türü, adı ve açıklamanın başı görünür; tutamağa dokununca açılır */
  .ag-panel.kapali{max-height:7.4rem;overflow:hidden}
  .ag-tutamak{display:block;width:100%;background:none;border:0;padding:.35rem 0 .55rem;cursor:pointer}
  .ag-tutamak::before{content:"";display:block;width:2.6rem;height:4px;border-radius:2px;background:var(--rule);margin:0 auto}
  body.ag-panel-acik main{padding-bottom:9rem}
  .ag-tuval{height:62vh;min-height:360px}
  .ag-ipucu{display:none}
  table.kisiler thead{display:block}
  table.makaleler td.m-yazar,table.makaleler td.m-konu{width:auto}
  table.makaleler td.m-yazar{font-style:italic;color:var(--ink-soft)}
  table.makaleler td.m-yil{display:none}
  .m-yil-tel{display:inline}
  table.kisiler thead tr{display:flex;flex-wrap:wrap;gap:.2rem 1rem;padding:0 0 .4rem;border-bottom:1px solid var(--gold)}
  table.kisiler thead th{display:block;border:0;padding:0}
  table.kisiler thead th:last-child{display:none}
  table.kisiler,table.kisiler tbody,table.kisiler tr,table.kisiler td{display:block;width:100%}
  table.kisiler tr{padding:.6rem 0;border-bottom:1px solid var(--rule)}
  table.kisiler td{border:0;padding:.05rem 0}
  table.kisiler td.k-ad{font-size:1.02rem}
  table.kisiler tr[hidden]{display:none}
}
"""

MENU = [("", "Ana sayfa"), ("basliklar", "Başlıklar"), ("terimler", "Terimler"), ("kisiler", "Kişiler"),
        ("eserler", "Eserler"), ("dergiler", "Dergiler"), ("ag", "Ağ"), ("hakkinda", "Hakkında")]
TEZ_DOSYA = ROOT / "data" / "tez" / "tezler.json"
if TEZ_DOSYA.exists():
    MENU.insert([k for k, _ in MENU].index("eserler") + 1, ("tezler", "Tezler"))


GORSELLER = []   # (dosya yolu, üst yazı, başlık, alt yazı): derleme sonunda üretilir


def surum(yol_: str) -> str:
    """Betik ve dosya adreslerine içerik özetini ekler (?v=...). Dosya değişince adres de değişir,
    tarayıcılar eski kopyayı önbellekten kullanmaz."""
    import hashlib
    try:
        return hashlib.md5((ROOT / yol_).read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


def paylasim_gorseli(ad_: str, ust: str, baslik_: str, alt: str = "") -> str:
    GORSELLER.append((f"paylas/{ad_}.png", ust, baslik_, alt))
    return f"{SITE_URL}/paylas/{ad_}.png"


def ld(veri: dict) -> str:
    """schema.org yapılandırılmış verisi (JSON-LD). Arama motorları sayfanın ne olduğunu buradan okur."""
    veri = {"@context": "https://schema.org", **veri}
    return ('<script type="application/ld+json">' + json.dumps(veri, ensure_ascii=False).replace("</", "<\\/") + '</script>')


def ld_yayinci() -> dict:
    return {"@type": "Organization", "name": "dinfelsefesi.com.tr", "url": SITE_URL + "/",
            "logo": SITE_URL + "/static/img/logo-512.png?v=" + surum("static/img/logo-512.png")}


# Bazı dergilerin DOI'leri artık çalışmayan eski adreslere yönleniyor. Beytulhikme DergiPark'tan ayrılıp yayıncı
# değiştirince eski makaleler archived.beytulhikme.org adresine taşındı; 10.18491/beytulhikme.N DOI'si ise hâlâ
# kapanmış www.beytulhikme.org sayfasına gidiyor. Sayfalardaki bağlantı bu yüzden arşivdeki adrese çevrilir.
_OLU_DOI = [(re.compile(r'https://doi\.org/10\.18491/beytulhikme\.(\d+)\b', re.I),
             r'https://archived.beytulhikme.org/DergiTamDetay.aspx?ID=\1')]


def doi_baglanti_duzelt(h: str) -> str:
    for desen, yerine in _OLU_DOI:
        h = desen.sub(yerine, h)
    return h


def page(title: str, body: str, aktif: str = "", desc: str = SITE_TAGLINE, canonical: str = "",
         gorsel: str = "", og_tur: str = "website", jsonld: dict | None = None, dizinleme: bool = True) -> str:
    body = doi_baglanti_duzelt(body)
    canon = f'<link rel="canonical" href="{e(canonical)}">' if canonical else ""
    if jsonld:
        canon += ld(jsonld)
    og_baslik = title.removesuffix(f" · {SITE_NAME}")
    og = (f'<meta property="og:site_name" content="{e(SITE_NAME)}"><meta property="og:locale" content="tr_TR">'
          f'<meta property="og:type" content="{og_tur}"><meta property="og:title" content="{e(og_baslik)}">'
          f'<meta property="og:description" content="{e(desc)}">'
          + (f'<meta property="og:url" content="{e(canonical)}">' if canonical else "")
          + f'<meta property="og:image" content="{e(gorsel or SITE_URL + "/paylas/site.png")}">'
          f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
          f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@{X_HESABI}">'
          f'<meta name="twitter:title" content="{e(og_baslik)}"><meta name="twitter:description" content="{e(desc)}">'
          f'<meta name="twitter:image" content="{e(gorsel or SITE_URL + "/paylas/site.png")}">'
          f'<meta name="google-site-verification" content="google08c007317a4ad095">')
    robots = ('<meta name="robots" content="noindex,nofollow">' if NOINDEX
              else '<meta name="robots" content="noindex,follow">' if not dizinleme else "")
    menu = "".join(
        f'<a href="{SITE_URL}/{k + "/" if k else ""}"{" class=\"m-ana\"" if not k else ""}{" aria-current=\"page\"" if k == aktif else ""}>{a}</a>' for k, a in MENU)
    if NOINDEX:
        deneme = ('<div class="deneme"><div class="wrap">Deneme sürümü. İçerikler taslak hâlindedir ve '
                  'henüz yayımlanmamıştır.</div></div>')
    else:  # yayındaki sitede şerit yok (31.10.2026); iletişim adresi alt bilgide ve Hakkında sayfasında
        deneme = ""
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{robots}
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{canon}
{og}
<link rel="icon" href="{SITE_URL}/static/img/favicon.svg" type="image/svg+xml">
<link rel="icon" href="{SITE_URL}/favicon.ico" sizes="48x48">
<link rel="icon" href="{SITE_URL}/static/img/icon-192.png?v={surum('static/img/icon-192.png')}" sizes="192x192" type="image/png">
<link rel="apple-touch-icon" href="{SITE_URL}/static/img/apple-touch-icon.png?v={surum('static/img/apple-touch-icon.png')}">
<meta name="theme-color" content="#f3f4f6">
<link rel="alternate" type="application/rss+xml" title="{e(SITE_NAME)}" href="{SITE_URL}/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;1,400;1,500&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
<script src="{SITE_URL}/static/js/onizleme.js?v={surum('static/js/onizleme.js')}" data-veri="{SITE_URL}/api/onizleme.json" defer></script>{SAYAC}
</head>
<body>
<header class="site"><div class="wrap">
  <a class="marka" href="{SITE_URL}/"><img class="marka-logo" src="{SITE_URL}/static/img/logo.svg" alt="" width="44" height="44"><span class="marka-yazi"><b>{e(SITE_NAME)}</b><small>Türkçe başvuru kaynağı</small></span></a>
  <nav class="ana" aria-label="Ana menü">{menu}</nav>
</div></header>
{deneme}
<main><div class="wrap">
{body}
</div></main>
<footer class="site"><div class="wrap">
  <p>© {YIL} <span class="alan"><a href="{SITE_URL}/">dinfelsefesi.com.tr</a> · </span>Din felsefesi için Türkçe başvuru kaynağı</p>
  <p class="iletisim"><a href="mailto:{ILETISIM}"><span class="simge" aria-hidden="true">✉</span><span class="gizli">E-posta: </span><span class="adres">{ILETISIM}</span></a> · <a href="https://x.com/{X_HESABI}" rel="noopener"><span class="simge" aria-hidden="true">𝕏</span><span class="gizli">X: </span><span class="adres">@{X_HESABI}</span></a></p>
</div></footer>
<script>
(function(){{var b=document.body,son=window.scrollY,tel=window.matchMedia('(max-width:760px)');
function bak(){{var y=window.scrollY;
  /* iki eşik: şerit incelince sayfa kısalır ve kaydırma konumu geriye itilebilir; tek eşikte şerit titrerdi */
  if(y>90)b.classList.add('ust-ince');else if(y<20)b.classList.remove('ust-ince');
  if(tel.matches){{if(y>son+4&&y>140)b.classList.add('ust-gizli');else if(y<son-4||y<140)b.classList.remove('ust-gizli')}}
  else b.classList.remove('ust-gizli');son=y}}
window.addEventListener('scroll',bak,{{passive:true}});bak()}})();
</script>
</body>
</html>"""


SAYFALAR = []  # site haritasına girecek sayfalar (yönlendirmeler hariç)


def yaz(yol_: str, icerik: str):
    p = OUT / yol_ / "index.html" if yol_ else OUT / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(icerik, encoding="utf-8")
    if 'http-equiv="refresh"' not in icerik:
        SAYFALAR.append(yol_)


# ---------------------------------------------------------------- makaleler

def entry_url(m: dict) -> str:
    return f"{SITE_URL}/makale/{m['slug']}/"


GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def bugun() -> str:
    """Günün makalesi için 'bugün'. Yeni günün makalesi İstanbul saatiyle akşam 19.30'dan itibaren yayımlanır
    (gece derlemesi 19.47'de başlar); bu yüzden saate 4,5 saat eklenerek gün hesaplanır."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    return os.environ.get("BUGUN") or (datetime.now(ZoneInfo("Europe/Istanbul")) + timedelta(hours=4, minutes=30)).date().isoformat()


def gunleri_ata(items) -> list:
    """Her tanıtımın bir 'gun'ü vardır; olmayanlara son atanmış günden sonraki günler sırayla verilir.
    Bugüne kadar gelmiş olanlar yeniden eskiye doğru döndürülür."""
    from datetime import date, timedelta
    atanmis = [m["gun"] for m in items if m.get("gun")]
    son = date.fromisoformat(max(atanmis)) if atanmis else date.fromisoformat(bugun()) - timedelta(days=1)
    for m in items:
        if not m.get("gun"):
            son += timedelta(days=1)
            m["gun"] = son.isoformat()
    b = bugun()
    return sorted([m for m in items if m["gun"] <= b], key=lambda m: m["gun"], reverse=True)


def gun_metni(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{tr_date(iso)}, {GUN_ADLARI[d.weekday()]}"


def makale_dili(m: dict) -> str:
    return (m.get("lang") or ("en" if m.get("title_en") else "tr")).lower()


def rozetler(m: dict) -> str:
    dil = makale_dili(m)
    r = f' <span class="rozet" title="Makalenin dili: {"Türkçe" if dil == "tr" else "İngilizce" if dil == "en" else dil.upper()}">{e(dil.upper())}</span>'
    if m.get("open_access") == "evet":
        r += ' <span class="rozet ae-rozet">Açık erişim</span>'
    return r


def makale_satiri(m: dict) -> str:
    return f"""<article class="makale">
  <time datetime="{e(m['gun'])}">{tr_date(m['gun'])}<span class="gun-adi">{GUN_ADLARI[datetime.strptime(m['gun'], "%Y-%m-%d").weekday()]}</span></time>
  <div>
    <h3><a href="{entry_url(m)}">{e(m['title_tr'])}</a></h3>
    <p class="orij">{e(m.get('title_en', ''))}{rozetler(m)}</p>
    <p class="kunye">{e(m['authors'])} · {e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</p>
    <p class="ozet">{e(m['lead'])}</p>
  </div>
</article>"""


def render_makaleler(items) -> str:
    body = ('<p class="ust-etiket">Günün makalesi</p><h1>Günün makaleleri</h1>'
            '<p class="giris">Her gün din felsefesi dergilerinde yayımlanmış bir makale, Türkçe tanıtımıyla öne çıkarılır. '
            'Önceki günlerin makaleleri aşağıda, öne çıkarıldıkları günle birlikte yer almaktadır.</p>'
            + "".join(makale_satiri(m) for m in items))
    return page(f"Günün makaleleri · {SITE_NAME}", body, "", canonical=f"{SITE_URL}/gunun-makalesi/")


def yonlendirme(hedef: str) -> str:
    return (f'<!doctype html><meta charset="utf-8"><title>Taşındı</title>'
            f'<meta http-equiv="refresh" content="0; url={hedef}"><link rel="canonical" href="{hedef}">'
            f'<p><a href="{hedef}">{hedef}</a></p>')


def render_makale(m: dict) -> str:
    oa = {"evet": "Açık erişim", "hayır": "Abonelik gerekli"}.get(m.get("open_access", ""), "")
    link = m.get("doi") and f"https://doi.org/{m['doi']}" or m.get("url", "")
    body = f"""
<article class="dar">
  <p class="yol"><a href="{SITE_URL}/gunun-makalesi/">Günün makaleleri</a> <span aria-hidden="true">›</span> <time datetime="{e(m['gun'])}">{gun_metni(m['gun'])}</time></p>
  <h1>{e(m['title_tr'])}</h1>
  {('<p class="giris"><em>' + e(m['title_en']) + '</em></p>') if m.get('title_en') else ''}
  <div class="kutu"><dl>
    <dt>Yazar</dt><dd>{e(m['authors'])}</dd>
    <dt>Dergi</dt><dd>{e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</dd>
    <dt>Kaynak</dt><dd><a href="{e(link)}" rel="noopener">{"DOI" if m.get("doi") else "DergiPark" if "dergipark.org.tr" in link else "Makalenin sayfası"}</a>{(' · ' + oa) if oa else ''}</dd>
  </dl></div>
  <div class="metin">
    {'<p class="kunye">Makalenin kendi Türkçe özeti</p>' if m.get('otomatik') else ''}
    {paragraphs(m['summary_tr'])}
    {('<h2>Neden önemli</h2>' + paragraphs(m.get('why_tr', ''))) if m.get('why_tr') else ''}
  </div>
  <div class="etiketler">{''.join(f'<span>#{e(t)}</span>' for t in m.get('tags', []))}</div>
  <p class="paylas">{paylas_dugmesi(m)}</p>
</article>{ATIF_JS}"""
    gorsel = paylasim_gorseli(f"makale-{m['slug']}", f"Günün makalesi · {tr_date(m['gun'])}", m["title_tr"],
                              f"{m.get('authors', '')} · {m.get('journal', '')}{', ' + str(m['year']) if m.get('year') else ''}")
    kaynak = {"@type": "ScholarlyArticle", "name": m.get("title_en") or m["title_tr"],
              "author": [{"@type": "Person", "name": a.strip()} for a in re.split(r",| ve | and ", m.get("authors", "")) if a.strip()]}
    if m.get("journal"):
        kaynak["isPartOf"] = {"@type": "Periodical", "name": m["journal"]}
    if m.get("year"):
        kaynak["datePublished"] = str(m["year"])
    if m.get("doi"):
        kaynak["sameAs"] = f"https://doi.org/{m['doi']}"
    elif m.get("url"):
        kaynak["sameAs"] = m["url"]
    jl = {"@type": "Article", "headline": m["title_tr"], "description": m["lead"], "url": entry_url(m), "inLanguage": "tr",
          "datePublished": m.get("gun") or m.get("date"), "publisher": ld_yayinci(), "image": gorsel, "about": kaynak}
    return page(f"{m['title_tr']} · {SITE_NAME}", body, "", desc=m["lead"], canonical=entry_url(m), gorsel=gorsel,
                og_tur="article", jsonld=jl)


# ---------------------------------------------------------------- başlıklar

# Ana başlıklar bu tematik kümelerde gösterilir. Kümeler yalnızca görsel ayraçtır, kendi sayfaları yoktur.
KUMELER = [("disiplin", "Disiplin"), ("tanri", "Tanrı"), ("bilgi-dil", "Bilgi ve dil"), ("insan-deger", "İnsan ve değer"),
           ("din-bilim-kultur", "Din, bilim ve kültür")]


def kumeli_basliklar():
    """[(küme adı, [ana başlık kimlikleri])]; kümesi belirtilmemiş başlıklar sona eklenir."""
    anas = ana_basliklar()
    out = []
    for kk, kad in KUMELER:
        ks = [k for k in anas if FIS[("baslik", k)].get("kume") == kk]
        if ks:
            out.append((kad, ks))
    kalan = [k for k in anas if FIS[("baslik", k)].get("kume") not in dict(KUMELER)]
    if kalan:
        out.append(("Diğer", kalan))
    return out


def ana_basliklar():
    return sorted([k for (t, k), h in FIS.items() if t == "baslik" and not h.get("ust_baslik")],
                  key=lambda k: FIS[("baslik", k)].get("sira", 99))


def alt_dolu(a) -> bool:
    """Alt başlığın fişi var ve ona bağlı içerik ya da metin bulunuyorsa dolu sayılır."""
    return ("baslik", a) in FIS and bool(bagli_fisler(a) or FIS[("baslik", a)].get("_govde"))


def harita_html() -> str:
    anas = ana_basliklar()
    en_cok = max([len(bagli_fisler(k)) for k in anas] + [1])
    bolumler = []
    for kad, ks in kumeli_basliklar():
        bolumler.append(f'<h2 class="kume-ad">{e(kad)}</h2>' + harita_kartlari(ks, en_cok))
    return "".join(bolumler)


def harita_kartlari(anas, en_cok) -> str:
    kartlar = []
    for k in anas:
        h = FIS[("baslik", k)]
        b = bagli_fisler(k)
        altlar = "".join(
            f"<li class='{'dolu' if alt_dolu(a) else 'plan'}'>{bag('baslik', a)}</li>"
            for a in liste(h.get("alt_basliklar")))
        ilg = bag_listesi("ilgili_basliklar", h)
        ara = " ".join([h["ad"], re.sub(r"<[^>]+>", "", satir_ici(h.get("ozet"))), *liste(h.get("alt_basliklar")),
                        *(FIS[("baslik", a)]["ad"] for a in liste(h.get("alt_basliklar")) if ("baslik", a) in FIS)])
        kartlar.append(f"""<article class="anakart{' bos' if not b else ''}" data-ara="{e(ara)}">
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
        fis_grubu(b, "eser", "Eserler") if not ok else
        fis_grubu({(x, y) for x, y in b if not (x == "eser" and y in set(liste(ok.get("giris"))) | set(liste(ok.get("ileri"))))},
                  "eser", "Başlığa bağlı diğer eserler"),
        (f"<h2>İlgili başlıklar</h2><ul>{''.join(f'<li>{bag("baslik", x)}</li>' for x in liste(h.get('ilgili_basliklar')))}</ul>" if liste(h.get("ilgili_basliklar")) else ""),
    ])
    sorular = "".join(f"<li>{satir_ici(s)}</li>" for s in liste(h.get("tartisma_sorulari")))
    metin = govde(h["_govde"], ("baslik", k))
    if not metin:
        metin = ('<p class="giris">Başlığın tanıtım metni henüz yazılmadı. '
                 'Başlığa bağlı fişler yandaki listede yer almaktadır.</p>' if b else
                 '<p class="giris">Bu başlık için henüz fiş eklenmedi.</p>')
    body = f"""
<p class="yol">{yol(k)}</p>
<h1>{e(h['ad'])}{taslak_etiketi(h)}</h1>
{f'<p class="baslik-karsilik">{" · ".join(x for x in [("İng. " + e(h["ingilizce"])) if h.get("ingilizce") else "", ("Diğer adı: " + ", ".join(e(str(a)) for a in liste(h.get("diger_adlari")))) if liste(h.get("diger_adlari")) else ""] if x)}</p>' if h.get("ingilizce") or h.get("diger_adlari") else ""}
<p class="giris">{satir_ici(h.get('ozet'))}<span class="say ayri">{sayim_metni(b)}</span></p>
<div class="fis-duzen">
  <div class="metin">{metin}{f'<h2>Tartışma soruları</h2><ol class="sorular">{sorular}</ol>' if sorular else ''}{baslik_makaleleri(k)}{baslik_calisanlari(k)}</div>
  <aside class="yan">{yan or '<h2>Fişler</h2><p>Henüz fiş yok.</p>'}<a class="ag-git" href="{ag_adresi('baslik', k)}">Bu başlığın ağı →</a></aside>
</div>"""
    gorsel = paylasim_gorseli(f"baslik-{k}", "Başlık", h["ad"], "")
    jl = {"@type": "Article" if h.get("_govde") else "WebPage", "headline": h["ad"], "name": h["ad"],
          "description": h.get("ozet") or "", "url": fis_url("baslik", k), "inLanguage": "tr",
          "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_URL + "/"}, "publisher": ld_yayinci(),
          "image": gorsel}
    if h.get("guncelleme"):
        jl["dateModified"] = str(h["guncelleme"])
    return page(f"{h['ad']} · {SITE_NAME}", body, "basliklar", desc=h.get("ozet") or SITE_TAGLINE,
                canonical=fis_url("baslik", k), gorsel=gorsel, og_tur="article", jsonld=jl)


BASLIK_SEC_JS = """<script>
(function(){var g=document.getElementById('baslik-sec');if(!g)return;
g.addEventListener('change',function(){if(g.value)location.href=g.value});
window.addEventListener('pageshow',function(){g.value=''});
})();
</script>"""


def baslik_secici() -> str:
    """Eserler sayfasındaki konu listesiyle aynı düzen: kümelere ayrılmış başlıklar, alt başlıklar girintili. Seçilen başlığın sayfası açılır."""
    oge = ['<option value="">Bir başlık seçin</option>']
    for kad, ks in kumeli_basliklar():
        oge.append(f'<optgroup label="{e(kad)}">')
        for k in ks:
            oge.append(f'<option value="{fis_url("baslik", k)}">{e(FIS[("baslik", k)]["ad"])}</option>')
            for c in sorted(COCUK.get(k, []), key=lambda x: FIS[("baslik", x)].get("sira", 99)):
                oge.append(f'<option value="{fis_url("baslik", c)}">\u00a0\u00a0\u00a0{e(FIS[("baslik", c)]["ad"])}</option>')
        oge.append('</optgroup>')
    return (f'<label class="secim-etiket" for="baslik-sec">Başlık</label>'
            f'<div class="eser-konu-kap"><select id="baslik-sec" class="eser-konu-sec">{"".join(oge)}</select></div>')


def render_basliklar() -> str:
    body = ('<p class="ust-etiket">Başlıklar</p><h1>Din felsefesinin başlıkları</h1>'
            '<p class="giris">Ana başlıklar din felsefesi literatürünün problem alanlarını gösterir ve beş tematik küme altında sıralanır. '
            'Çubuklar her başlığa bağlı fiş sayısını, çerçeveli alt başlıklar içeriği hazır olanları gösterir.</p>'
            + baslik_secici() + harita_html() + BASLIK_SEC_JS)
    return page(f"Başlıklar · {SITE_NAME}", body, "basliklar", canonical=f"{SITE_URL}/basliklar/")


# ---------------------------------------------------------------- fiş sayfaları

def satir(etiket, icerik) -> str:
    return f"<div><dt>{etiket}</dt><dd>{icerik}</dd></div>" if icerik else ""


ATIF_JS = """<script>
(function(){
  var A=["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"], d=new Date();
  document.querySelectorAll('.atif-erisim').forEach(function(s){s.textContent=d.getDate()+' '+A[d.getMonth()]+' '+d.getFullYear();});
  document.querySelectorAll('.atif-kopyala').forEach(function(b){
    b.addEventListener('click',function(){
      var t=b.parentNode.querySelector('.atif-metin').innerText.trim(), eski=b.textContent;
      var tamam=function(){b.textContent='Kopyalandı';setTimeout(function(){b.textContent=eski;},1800);};
      if(navigator.clipboard){navigator.clipboard.writeText(t).then(tamam,function(){sec(b);});}else{sec(b);}
    });
  });
  function sec(b){var r=document.createRange();r.selectNodeContents(b.parentNode.querySelector('.atif-metin'));var s=getSelection();s.removeAllRanges();s.addRange(r);}
})();
</script>"""


def ag_baglantisi(tur, k) -> str:
    if tur == "terim":
        return f'<a class="ag-git" href="{ag_adresi(tur, k)}">Bu terimin ağı →</a>'
    if tur == "kisi":
        return f'<a class="ag-git" href="{ag_adresi(tur, k)}">Bu kişinin ağı →</a>'
    return f'<a class="ag-git" href="{SITE_URL}/ag/?odak={tur}/{k}">İlişki ağında göster →</a>'


def geri_yan(tur, k) -> str:
    sira = list(KLASOR)
    g = sorted(GERI.get((tur, k), set()), key=lambda x: (sira.index(x[0]), tr_anahtar(ad(x[0], FIS[x]))))
    if not g:
        return ""
    oge = "".join(f'<li><span class="tur-k">{TUR_AD[t]}</span>{bag(t, kk)}</li>' for t, kk in g)
    return f"<h2>Bu fişe bağlananlar</h2><ul>{oge}</ul>"


def fis_ld(tur, k, h, desc) -> dict:
    url = fis_url(tur, k)
    if tur == "terim":
        jl = {"@type": "DefinedTerm", "name": h["terim"], "description": h.get("kisa_tanim") or desc, "url": url,
              "inLanguage": "tr", "inDefinedTermSet": {"@type": "DefinedTermSet", "name": "Din felsefesi terimleri",
                                                        "url": f"{SITE_URL}/terimler/"}}
        if h.get("ingilizce"):
            jl["alternateName"] = h["ingilizce"]
        return jl
    if tur == "kisi":
        jl = {"@type": "Person", "name": h["ad"], "description": h.get("kisa_tanitim") or desc, "url": url}
        bag_ = [b.get("url") if isinstance(b, dict) else b for b in liste(h.get("baglantilar"))]
        bag_ = [b for b in bag_ if isinstance(b, str) and b.startswith("http")]
        if bag_:
            jl["sameAs"] = bag_
        return {"@type": "ProfilePage", "url": url, "mainEntity": jl}
    # eser
    tip = {"kitap": "Book", "kitap-bolumu": "Chapter", "makale": "ScholarlyArticle", "bildiri": "ScholarlyArticle",
           "tez": "Thesis"}.get(h.get("eser_turu"), "CreativeWork")
    jl = {"@type": tip, "name": h["baslik"], "url": url,
          "author": [{"@type": "Person", "name": ad("kisi", FIS[("kisi", y)]) if ("kisi", y) in FIS else str(y)}
                     for y in liste(h.get("yazar"))]}
    if h.get("yil"):
        jl["datePublished"] = str(h["yil"])
    if h.get("yayin"):
        jl["publisher" if tip == "Book" else "isPartOf"] = {"@type": "Organization" if tip == "Book" else "CreativeWork",
                                                           "name": str(h["yayin"])}
    hedef = eser_baglantisi(h)
    if hedef:
        jl["sameAs"] = hedef
    return jl


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
        ic = f"<p class='kisa'>{satir_ici(h['kisa_tanim'])}</p><div class='metin'>{govde(h['_govde'], (tur, k))}</div>{kg_html}"
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
        ic = f"<p class='kisa'>{satir_ici(h['kisa_tanitim'])}</p><div class='metin'>{govde(h['_govde'], (tur, k))}</div>"
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
        kunye_ = (f'<span class="atif-metin kunye-metin">{kunye_html(h)}</span> '
                  f'<button type="button" class="atif-kopyala kunye-kopyala">kopyala</button>')
        dl = "".join([satir("Künye", kunye_), satir("Erişim", erisim),
                      satir("Türkçe çevirisi", satir_ici(h.get("turkce_cevirisi"))),
                      satir("İlgili terimler", bag_listesi("ilgili_terimler", h)), basliklar])
        ic = f"<div class='metin'>{govde(h['_govde'], (tur, k))}</div>"
        desc = re.sub(r"\s+", " ", h["_govde"])[:200]
    yan = geri_yan(tur, k) + ag_baglantisi(tur, k)
    body = f"""
<p class="yol"><a href="{SITE_URL}/{KLASOR[tur]}/">{ {'terim': 'Terimler', 'kisi': 'Kişiler', 'eser': 'Eserler'}[tur] }</a></p>
<div class="fis-duzen">
  <article class="kart"><p class="ust-etiket">{TUR_AD[tur]}</p>{bas}{ic}<dl class="kunye">{dl}</dl>
    <p class="imza">{e(h.get('imza'))} · son güncelleme {tr_date(str(h['guncelleme']))}</p></article>
  {f'<aside class="yan">{yan}</aside>' if yan else ''}
</div>{ATIF_JS}"""
    gorsel = paylasim_gorseli(f"{tur}-{k}", TUR_AD[tur], ad(tur, h), str(h.get("ingilizce") or h.get("donem") or ""))
    return page(f"{ad(tur, h)} · {SITE_NAME}", body, KLASOR[tur], desc=desc, canonical=fis_url(tur, k), gorsel=gorsel,
                og_tur="article", jsonld=fis_ld(tur, k, h, desc))


def render_dizin(tur) -> str:
    kimlikler = sorted([k for (t, k) in FIS if t == tur], key=lambda k: tr_anahtar(ad(tur, FIS[(tur, k)])))
    basliklar = {"terim": ("Terimler", "Din felsefesi terimlerinin Türkçe ve İngilizce karşılıkları, kısa tanımları ve bağlantıları."),
                 "kisi": ("Kişiler", "Türkiye akademisinde ve uluslararası literatürde din felsefesi alanında çalışan düşünürler ve araştırmacılar."),
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
    say = "" if tur == "kisi" else f' <span class="say">{len(kimlikler)} fiş</span>'
    body = f'<p class="ust-etiket">{basliklar[0]}</p><h1>{basliklar[0]}</h1><p class="giris">{basliklar[1]}{say}</p>{icerik}'
    return page(f"{basliklar[0]} · {SITE_NAME}", body, KLASOR[tur], canonical=f"{SITE_URL}/{KLASOR[tur]}/")

KAPSAM = [("turkiye", "Türkiye akademisi"), ("uluslararasi", "Uluslararası akademi")]
YOK_PROFIL = "https://akademik.yok.gov.tr/academician-details?authorGuidId="


UNVAN_SIRA = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2, "Öğr. Gör. Dr.": 3, "Öğr. Gör.": 4, "Arş. Gör. Dr.": 5, "Arş. Gör.": 6}


def turkiye_listesi() -> tuple[str, int]:
    dosya = CONTENT / "turkiye_akademisi.yaml"
    if not dosya.exists():
        return '<p class="giris">Liste hazırlanıyor.</p>', 0
    veri = yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}
    kisiler = veri.get("kisiler") or []
    fis_ad = {FIS[(t, k)]["ad"]: k for (t, k) in FIS if t == "kisi"}
    satirlar = []
    kisiler = sorted(kisiler, key=lambda p: tr_anahtar(p['ad']))
    for p in kisiler:
        kim = p.get("kimlik") or fis_ad.get(p["ad"])
        ad_html = bag("kisi", kim) if kim and ("kisi", kim) in FIS else f'<a href="{akademi_url(slugify(p["ad"]))}">{e(p["ad"])}</a>'
        durum = ' <span class="emekli">Emekli</span>' if p.get("durum") == "emekli" else ""
        ara = ara_norm(" ".join([p["ad"], p.get("universite", ""), p.get("fakulte", "")]))
        satirlar.append(f'<tr id="k-{slugify(p["ad"])}" data-ara="{e(ara)}" data-unvan="{UNVAN_SIRA.get(p.get("unvan"), 9)}"><td class="k-ad" data-etiket="Ad Soyad">{ad_html}</td>'
                        f'<td data-etiket="Unvan">{e(p.get("unvan"))}{durum}</td>'
                        f'<td data-etiket="Üniversite">{e(p.get("universite"))}</td>'
                        f'<td data-etiket="Fakülte">{e(p.get("fakulte"))}</td></tr>')
    tarih = tr_date(str(veri.get("tarih"))) if veri.get("tarih") else ""
    ust = (f'<p class="aciklama-kisa">Türkiye\'deki üniversitelerde din felsefesi alanında çalışan öğretim elemanları. '
           f'Liste, YÖK Akademik\'te bilim alanı olarak İlahiyat Temel Alanı\'nda Din Felsefesi\'ni işaretlemiş akademisyenler ile '
           f'İlahiyat Temel Alanı\'nda Felsefe ve Din Bilimleri ya da Sosyal, Beşeri ve İdari Bilimler Temel Alanı\'nda Felsefe alanında '
           f'ilk anahtar kelimesi Din Felsefesi olan akademisyenlerden oluşmaktadır'
           f'{" (" + tarih + ")" if tarih else ""}. Unvan ve kurum bilgileri YÖK\'teki kayda göredir.'
           f'{" Bu ölçütlere uymayan ama alanın öncülerinden olan " + str(sum(1 for p in kisiler if p.get("elle"))) + " isim listeye elle eklenmiştir." if any(p.get("elle") for p in kisiler) else ""}</p>'
           '<label class="k-ara"><span>Ara</span><input type="search" id="kisi-ara" placeholder="Ad, üniversite ya da fakülte" autocomplete="off"></label>')
    tablo = ('<div class="tablo-kap"><table class="kisiler"><thead><tr>'
             + "".join(f'<th aria-sort="{"ascending" if i == 0 else "none"}"><button type="button" class="sirala" data-sutun="{i}">{b}<span class="ok" aria-hidden="true"></span></button></th>'
                       for i, b in enumerate(["Ad Soyad", "Unvan", "Üniversite", "Fakülte"])) +
             f'</tr></thead><tbody>{"".join(satirlar)}</tbody></table></div>'
             '<p class="giris k-bos" hidden>Aramaya uyan kişi bulunamadı.</p>')
    return ust + tablo, len(kisiler)


def kisi_bolumleri(kimlikler) -> str:
    tr_html, tr_say = turkiye_listesi()
    uyan = [k for k in kimlikler if FIS[("kisi", k)].get("kapsam", "uluslararasi") == "uluslararasi"]
    satirlar = [f'<li><span class="ad">{bag("kisi", k)}<span class="alt-ad">{e(FIS[("kisi", k)].get("donem"))}</span></span>'
                f'<span class="aciklama">{satir_ici(FIS[("kisi", k)]["kisa_tanitim"])}</span></li>' for k in uyan]
    ul_html = ('<p class="aciklama-kisa">Din felsefesi literatüründe etkili olmuş düşünürler ve araştırmacılar.</p>'
               + (f'<ul class="liste">{"".join(satirlar)}</ul>' if satirlar else '<p class="giris">Fişler hazırlanıyor.</p>'))
    sayilar = {"turkiye": tr_say, "uluslararasi": len(uyan)}
    icerik = {"turkiye": tr_html, "uluslararasi": ul_html}
    dugmeler = "".join(f'<button type="button" data-sekme="{kod}" aria-pressed="{"true" if i == 0 else "false"}">{e(ad_)} '
                       f'<span class="say">{sayilar[kod]}</span></button>' for i, (kod, ad_) in enumerate(KAPSAM))
    bolumler = "".join(f'<section class="eser-bolum sekme-bolum" id="{kod}"><h2>{e(ad_)} <span class="say">{sayilar[kod]} kişi</span></h2>'
                       f'{icerik[kod]}</section>' for kod, ad_ in KAPSAM)
    return f'<div class="tur-secici sekmeler" role="group" aria-label="Kişi grubu">{dugmeler}</div>{bolumler}{KISI_JS}'


KISI_JS = """<script>
(function(){
  var d=document.querySelectorAll('.sekmeler button'), b=document.querySelectorAll('.sekme-bolum');
  function ac(kod){
    d.forEach(function(x){x.setAttribute('aria-pressed', x.dataset.sekme===kod?'true':'false');});
    b.forEach(function(s){s.hidden = s.id!==kod;});
  }
  d.forEach(function(x){x.addEventListener('click',function(){ac(x.dataset.sekme); try{history.replaceState(null,'','#'+x.dataset.sekme);}catch(_){}});});
  ac(location.hash==='#uluslararasi'?'uluslararasi':'turkiye');
  var tb=document.querySelector('table.kisiler tbody');
  if(tb){
    var ths=document.querySelectorAll('table.kisiler thead th[aria-sort]');
    var metin=function(r,i){return (r.cells[i].innerText||'').replace(/Emekli/,'').trim();};
    var kar=function(a,b){return a.localeCompare(b,'tr',{sensitivity:'base'});};
    document.querySelectorAll('button.sirala').forEach(function(btn){
      btn.addEventListener('click',function(){
        var i=+btn.dataset.sutun, th=btn.parentNode, yon=th.getAttribute('aria-sort')==='ascending'?-1:1;
        ths.forEach(function(t){t.setAttribute('aria-sort','none');});
        th.setAttribute('aria-sort',yon===1?'ascending':'descending');
        var r=[].slice.call(tb.rows);
        r.sort(function(a,b){
          var f = i===1 ? (+a.dataset.unvan)-(+b.dataset.unvan) : kar(metin(a,i),metin(b,i));
          return f*yon || kar(metin(a,0),metin(b,0));
        });
        r.forEach(function(x){tb.appendChild(x);});
      });
    });
  }
  var g=document.getElementById('kisi-ara');
  if(g){
    var kucuk=function(s){return s.replace(/I/g,'ı').replace(/İ/g,'i').toLowerCase().replace(/[âäāàá]/g,'a').replace(/[êēëè]/g,'e').replace(/[îïīì]/g,'i').replace(/[ôōò]/g,'o').replace(/[ûūù]/g,'u').replace(/[\'`´‘’ʻʼʽʾʿ]/g,'');};
    g.addEventListener('input',function(){
      var q=kucuk(g.value.trim()), n=0;
      document.querySelectorAll('table.kisiler tbody tr').forEach(function(r){var v=!q||r.dataset.ara.indexOf(q)>-1; r.hidden=!v; if(v)n++;});
      document.querySelector('.k-bos').hidden = n>0;
    });
  }
})();
</script>"""


TUR_SIRA = {"kitap": 0, "kitap-bolumu": 1, "makale": 2, "bildiri": 3, "tez": 4}
TUR_COGUL = [("kitap", "Kitaplar"), ("kitap-bolumu", "Kitap bölümleri"), ("makale", "Makaleler"),
             ("bildiri", "Bildiriler"), ("tez", "Tezler")]


# Eserler sayfası: eser fişleri ve DergiPark'taki Türkçe makaleler tek listede, konuya ve türe göre süzülür.
ESER_TURLERI = [("kitap", "Kitaplar"), ("kitap-bolumu", "Kitap bölümleri"), ("makale", "Makaleler"),
                ("bildiri", "Bildiriler"), ("tez", "Tezler"), ("kitap-tanitimi", "Kitap tanıtımları"),
                ("ceviri", "Tercümeler"), ("soylesi", "Söyleşiler")]
DP_TUR_ESER = {"": "makale", "kitap-tanitimi": "kitap-tanitimi", "ceviri": "ceviri",
               "ceviri-degerlendirmesi": "ceviri", "soylesi": "soylesi", "kitap": "kitap", "kitap-bolumu": "kitap-bolumu",
               "bildiri": "bildiri", "tez": "tez"}


def atalar(b) -> set:
    out = set()
    while b and ("baslik", b) in FIS:
        out.add(b)
        b = FIS[("baslik", b)].get("ust_baslik")
    return out


def eser_ogeleri() -> list:
    """Eserler sayfasındaki bütün öğeler: önce eser fişleri, ardından DergiPark makaleleri (yeniden eskiye)."""
    ogeler = []
    fisler = sorted([k for (t, k) in FIS if t == "eser"],
                    key=lambda k: (TUR_SIRA.get(FIS[("eser", k)].get("eser_turu"), 9), str(FIS[("eser", k)].get("yil", "")),
                                   tr_anahtar(FIS[("eser", k)]["baslik"])))
    akademi_adlari = {tr_kucuk(p["ad"]) for p in (yaml.safe_load((CONTENT / "turkiye_akademisi.yaml").read_text(encoding="utf-8")) or {}).get("kisiler") or []}
    for k in fisler:
        h = FIS[("eser", k)]
        yazarlar_ = [ad("kisi", FIS[("kisi", y)]) if ("kisi", y) in FIS else str(y) for y in liste(h.get("yazar"))]
        if not any(tr_kucuk(y) in akademi_adlari for y in yazarlar_):
            continue  # yabancı klasikler eserler listesine girmez; fişleri başlık sayfalarından ve kendi adreslerinden okunur
        konu = set()
        for b in liste(h.get("basliklar")):
            konu |= atalar(b)
        yazar_ad = [ad("kisi", FIS[("kisi", y)]) if ("kisi", y) in FIS else str(y) for y in liste(h.get("yazar"))]
        ogeler.append({"html": eser_satiri(k), "tur": h.get("eser_turu", ""), "konu": konu, "grup": "temel",
                       "yil": str(h.get("yil") or ""), "yazar": yazar_ad[0] if yazar_ad else "", "ad": h["baslik"],
                       "ara": ara_norm(" ".join([h["baslik"], " ".join(yazar_ad), str(h.get("yayin") or "")]))})
    for m in dp_veri():
        yazar, dergi = dp_kunye(m)
        tur = DP_TUR_ESER[m["tur"]]
        konu = set(m["konular"] or m["ilgili"])
        etiket = f' <span class="m-tur">{e(DP_TUR_AD[m["tur"]])}</span>' if m["tur"] else ""
        etiket += kaynak_isareti(m)
        konu_ad = ", ".join(FIS[("baslik", b)]["ad"] for b in sorted(konu, key=lambda x: FIS[("baslik", x)].get("sira", 99))
                            if ("baslik", b) in FIS and not FIS[("baslik", b)].get("ust_baslik"))
        html_ = (eser_adi(m["baglanti"], m["baslik"]) + f'{etiket}'
                 f'<span class="eser-bilgi">{yazar + " · " if yazar else ""}{dergi}, {e(m["yil"])}'
                 + (f'<span class="eser-konu"> · {e(konu_ad)}</span>' if konu_ad else "") + '</span>')
        ogeler.append({"html": html_, "tur": tur, "konu": konu, "grup": "tr",
                       "yil": m["yil"], "yazar": m["yazarlar"][0] if m["yazarlar"] else "", "ad": m["baslik"],
                       "ara": ara_norm(" ".join([m["baslik"], " ".join(m["yazarlar"]), m["dergi"]]))})
    return ogeler


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
    return (f'<a class="eser-ad" href="{fis_url("eser", k)}">{e(h["baslik"])}</a>'
            f'<span class="eser-bilgi">{" · ".join(x for x in bilgi if x)}</span>')


def tez_tr_baslik(t: str) -> str:
    """Ulusal Tez Merkezi'nde büyük harfle yazılan kurum adlarını Türkçe başlık biçimine çevirir."""
    kucuk = {"ve", "ile", "için"}
    out = []
    for n, w in enumerate(t.split()):
        lw = tr_kucuk(w)
        out.append(lw if n and lw in kucuk else (("İ" if lw[:1] == "i" else "I" if lw[:1] == "ı" else lw[:1].upper()) + lw[1:]))
    return " ".join(out)


def tez_rozetleri(t: dict) -> str:
    """Tezin türü (YL/DR) ve durumu (Tamamlandı/Devam ediyor) için renkli kutucuklar."""
    dr = t["tur"] == "Doktora"
    tur = ('<span class="tz-r tz-dr" title="Doktora">DR</span>' if dr else '<span class="tz-r tz-yl" title="Yüksek lisans">YL</span>')
    durum = ('<span class="tz-r tz-devam" title="Tez hazırlanmakta ya da işlemi devam etmektedir">Devam ediyor</span>' if t["devam"]
             else '<span class="tz-r tz-tamam" title="Tez onaylanmış ve Tez Merkezi\'ne kaydedilmiştir">Tamamlandı</span>')
    return f'<span class="tez-rozetler">{tur}{durum}</span>'



# ---------------------------------------------------------------- Kavram tarihi (14 Kasım 2026)
KAVRAM_DOSYA = CONTENT / "kavramlar.yaml"
_KV_KATLA = str.maketrans({"ı": "i", "â": "a", "î": "i", "û": "u", "Â": "a", "Î": "i", "Û": "u", "'": "", "’": "", "‘": "", "`": "", "´": "",
                           "ʻ": "", "ʼ": "", "ʾ": "", "ʿ": ""})


def kv_norm(s: str) -> str:
    """Kavram aramasında başlık ve anahtar kelimelerin ortak biçimi: Türkçe küçük harf, düzeltme ve kesme işaretsiz,
    harf ve rakam dışındaki her şey boşluk."""
    s = tr_kucuk(str(s or "")).translate(_KV_KATLA)
    return " " + re.sub(r"[^0-9a-zçğıöşü]+", " ", s).strip() + " "


def kv_desen(kaliplar) -> re.Pattern:
    parcalar = []
    for k in kaliplar:
        tam = k.endswith("$")
        k = kv_norm(k[:-1] if tam else k).strip()
        parcalar.append(" " + re.escape(k) + (" " if tam else ""))
    return re.compile("|".join(parcalar))


def kavram_kayitlari() -> list:
    """Kavram sayımına giren çalışmalar: (yıl, başlık metni, başlık+anahtar kelime metni).
    Kitap tanıtımları dışarıda kalır, çünkü başlıkları tanıtılan kitabın adıdır."""
    kayit = []
    for o in eser_ogeleri():
        if o.get("grup") != "temel" or not str(o.get("yil", "")).isdigit():
            continue
        kayit.append((int(o["yil"]), kv_norm(o["ad"]), kv_norm(o["ad"])))
    for m in dp_veri():
        if DP_TUR_ESER.get(m["tur"]) == "kitap-tanitimi" or not str(m.get("yil", "")).isdigit():
            continue
        b = kv_norm(m["baslik"])
        kayit.append((int(m["yil"]), b, b + kv_norm(" | ".join(m.get("kelimeler") or []))))
    if TEZ_DOSYA.exists():
        for t in json.loads(TEZ_DOSYA.read_text(encoding="utf-8")):
            if str(t.get("yil", "")).isdigit():
                b = kv_norm(t["ad"])
                kayit.append((int(t["yil"]), b, b))
    return kayit


def kavram_verisi() -> dict:
    tanim = yaml.safe_load(KAVRAM_DOSYA.read_text(encoding="utf-8")) or {}
    kayit = kavram_kayitlari()
    son = max(y for y, _, _ in kayit)
    ilk = 2000
    yillar = list(range(ilk, son + 1))
    n = [sum(1 for y, _, _ in kayit if y == yil) for yil in yillar]
    n_once = sum(1 for y, _, _ in kayit if y < ilk)
    kavramlar = []
    for grup, anahtar in (("kavram", "kavramlar"), ("dusunur", "dusunurler")):
        for k in tanim.get(anahtar) or []:
            d = kv_desen(k["kaliplar"])
            b = [0] * len(yillar)
            t = [0] * len(yillar)
            for y, bas, tam in kayit:
                if y < ilk:
                    continue
                i = y - ilk
                if d.search(bas):
                    b[i] += 1
                if d.search(tam):  # başlık ya da anahtar kelime: çalışma başına en çok bir
                    t[i] += 1
            kavramlar.append({"ad": k["ad"], "grup": grup, "ara": k.get("ara") or k["ad"], "b": b, "t": t})
    return {"yillar": yillar, "n": n, "n_once": n_once, "toplam": len(kayit), "kavramlar": kavramlar,
            "anahtarli": sum(1 for _, bas, tam in kayit if bas != tam)}


def yilin_kavramlari(v: dict, pencere: int = 3, en_az: int = 5, en_az_n: int = 60) -> list:
    """Her yıl için, önceki üç yılın oranına göre beklenenden en çok yükselen kavram.
    Ölçüt: (gözlenen − beklenen) / √(beklenen + 1). Bu, yalnızca sık geçen genel kavramları değil
    o yıl öne çıkan kavramı seçer; çok az çalışmaya dayanan sıçramalar alt sınırlarla elenir."""
    sonuc = []
    for i, yil in enumerate(v["yillar"]):
        if i < pencere or v["n"][i] < en_az_n:
            continue
        on = sum(v["n"][i - pencere:i])
        en = None
        for k in v["kavramlar"]:
            if k["grup"] != "kavram":
                continue
            c = k["t"][i]
            if c < en_az:
                continue
            p = sum(k["t"][i - pencere:i]) / on if on else 0
            bek = v["n"][i] * p
            skor = (c - bek) / math.sqrt(bek + 1)
            if en is None or skor > en[0]:
                en = (skor, k["ad"], c, round(100 * c / v["n"][i], 1), round(100 * p, 1), k["ara"])
        if en:
            sonuc.append({"yil": yil, "ad": en[1], "c": en[2], "oran": en[3], "once": en[4], "n": v["n"][i], "ara": en[5]})
    return sonuc


def render_kavram_tarihi() -> str:
    v = kavram_verisi()
    yk = yilin_kavramlari(v)
    def dugmeler(grup):
        ks = sorted([k for k in v["kavramlar"] if k["grup"] == grup], key=lambda k: tr_anahtar(k["ad"]))
        return "".join(f'<button type="button" data-ad="{e(k["ad"])}" aria-pressed="false">{e(k["ad"])} '
                       f'<span class="say">{sum(k["t"])}</span></button>' for k in ks)
    tablo = "".join(
        f'<tr><td>{r["yil"]}{" <span class=\"kt-suruyor\">(yıl sürüyor)</span>" if str(r["yil"]) == bugun()[:4] else ""}</td><td><button type="button" class="kt-sec" data-ad="{e(r["ad"])}">{e(r["ad"])}</button></td>'
        f'<td>{r["c"]} / {r["n"]}</td><td>%{str(r["oran"]).replace(".", ",")}</td><td>%{str(r["once"]).replace(".", ",")}</td></tr>'
        for r in reversed(yk))
    veri = json.dumps({"y": v["yillar"], "n": v["n"],
                       "k": [{"a": k["ad"], "r": k["ara"], "b": k["b"], "t": k["t"]} for k in v["kavramlar"]]},
                      ensure_ascii=False, separators=(",", ":"))
    body = (
        '<p class="ust-etiket">Kavram tarihi</p><h1>Kavram tarihi</h1>'
        '<p class="aciklama-kisa">Türkiye\'de yayımlanan din felsefesi çalışmalarında kavramların ve düşünürlerin yıllar içindeki yeri. '
        f'Sayım, sitedeki <a href="{SITE_URL}/eserler/">eserlerin</a> ve <a href="{SITE_URL}/tezler/">tezlerin</a> başlıklarına ve, '
        'bulunduğu yerde, yazarların verdiği anahtar kelimelere dayanır. Değerler, o yılki çalışmaların yüzde kaçında kavramın geçtiğini gösterir. '
        'Yöntem ve sınırlılıklar sayfanın sonunda açıklanmıştır. Düzeltme önerileri için: '
        f'<a href="mailto:{ILETISIM}">{ILETISIM}</a></p>'
        '<div class="kt-cizim-kap"><div class="kt-secili" aria-live="polite"></div>'
        '<svg class="kt-cizim" viewBox="0 0 720 320" role="img" aria-label="Seçili kavramların yıllara göre oranı"></svg>'
        '<p class="kt-ipucu"></p>'
        '<div class="kt-ayar"><span class="secim-etiket">Kaynak</span><div class="tur-secici kt-kaynak" role="group" aria-label="Sayım kaynağı">'
        '<button type="button" data-k="t" aria-pressed="true">Başlık ve anahtar kelime</button>'
        '<button type="button" data-k="b" aria-pressed="false">Yalnız başlık</button></div></div></div>'
        '<p class="secim-etiket secim-ayrac">Kavramlar</p><p class="kt-not">En çok dört kavram birlikte çizilir. Sayılar, 2000 sonrası toplam çalışma sayısıdır.</p>'
        f'<div class="tur-secici kt-liste" role="group" aria-label="Kavramlar">{dugmeler("kavram")}</div>'
        f'<p class="secim-etiket">Düşünürler</p><div class="tur-secici kt-liste" role="group" aria-label="Düşünürler">{dugmeler("dusunur")}</div>'
        '<h2 id="yilin-kavrami">Yılın kavramı</h2>'
        '<p>Her yıl için, önceki üç yıla göre başlıklarda en belirgin yükseliş gösteren kavram. Bu, o yıl en sık geçen kavram değildir; '
        '“Din ve ahlak” gibi her yıl sık geçen kavramlar yükseliş göstermedikçe öne çıkmaz. Kavram adına basıldığında eğrisi yukarıda çizilir.</p>'
        '<div class="kt-tablo-kap"><table class="kt-tablo"><thead><tr><th>Yıl</th><th>Kavram</th><th>Çalışma</th><th>Oran</th><th>Önceki üç yıl</th></tr></thead>'
        f'<tbody>{tablo}</tbody></table></div>'
        '<h2 id="yontem">Yöntem</h2>'
        f'<p><strong>Kaynak.</strong> Sayım, sitede listelenen {v["toplam"]} çalışmaya dayanır: eserler sayfasındaki kitap, kitap bölümü, makale, bildiri ve tercümeler '
        'ile tezler sayfasındaki yüksek lisans ve doktora tezleri. Kitap tanıtımları, başlıkları tanıtılan kitabın adı olduğu için sayıma girmez. '
        f'Çizim 2000 yılından başlar; daha önceki {v["n_once"]} çalışma, yıllık değer veremeyecek kadar az olduğundan dışarıda bırakılmıştır.</p>'
        '<p><strong>Kavram listesi.</strong> Aranabilen kavramlar serbest kelimeler değil, din felsefesinin yerleşik problem ve kavramlarından '
        'derlenmiş kapalı bir listedir. Her kavram, Türkçe ve İngilizce karşılıklarını ve ek almış biçimlerini kapsayan kalıplarla tanımlanır '
        '(örneğin “kötülük problemi” kavramı teodise ve theodicy kelimelerini de içerir). Liste ve kalıplar sitenin kaynak dosyalarında açıktır.</p>'
        '<p><strong>Sayım birimi.</strong> Birim çalışmadır. Bir kavram, başlıkta ya da anahtar kelimelerde kaç kez ve kaç farklı biçimde geçerse geçsin, '
        'bir çalışma için en çok bir kez sayılır.</p>'
        f'<p><strong>Anahtar kelimeler.</strong> Anahtar kelime yalnızca DergiPark ve ORCID gibi kaynaklardan alınan {v["anahtarli"]} çalışmada bulunur; kitaplarda, '
        'bildirilerin çoğunda ve tezlerde yoktur. Anahtar kelimesi olan çalışmalar bu yüzden kavramlara biraz daha kolay girer. '
        '“Yalnız başlık” seçeneği bu farkı ortadan kaldırır; iki eğri arasındaki fark büyükse sonucu ihtiyatla okumak gerekir.</p>'
        '<p><strong>Oran ve düzeltme.</strong> Yıllık çalışma sayısı 2000\'lerin başında birkaç düzine iken son yıllarda birkaç yüze çıkmıştır. '
        'Bu nedenle ham sayı yerine oran kullanılır: bir kavramın o yıl geçtiği çalışma sayısı, o yılki bütün çalışmaların sayısına bölünür. '
        'Küçük yıllardaki dalgalanmayı azaltmak için her nokta, o yıl ile önceki ve sonraki yılın toplamından hesaplanır (üç yıllık kayan pencere). '
        'Çalışma sayısı 60\'ın altındaki yıllar çizimde silik gösterilir.</p>'
        '<p><strong>Sınırlılıklar.</strong> Sayım tam metinlere değil başlık ve anahtar kelimelere dayanır, yani yazarların öne çıkardığı kavramı ölçer. '
        'Liste Türkiye\'deki din felsefesi literatürünün tamamı değil, sitenin derlediği kısmıdır; tezler, hocaları sitedeki listede yer alan danışmanların '
        'yönettiği tezlerle sınırlıdır. İçinde bulunulan yılın verisi eksiktir.</p>'
        f'<script>var KT={veri};</script>' + KAVRAM_JS)
    return page(f"Kavram tarihi · {SITE_NAME}", body, "eserler", canonical=f"{SITE_URL}/kavram-tarihi/",
                desc="Türkiye'deki din felsefesi çalışmalarında kavramların ve düşünürlerin yıllar içindeki yeri.")


KAVRAM_JS = """<script>
(function(){
  var R=['#1f3f6e','#a84a14','#2f6b4f','#7a3f86'], sec=[], kay='t', svg=document.querySelector('.kt-cizim'), ip=document.querySelector('.kt-ipucu');
  var W=720,H=320,L=44,Rr=12,T=14,B=34, Y=KT.y, N=KT.n, by={};
  KT.k.forEach(function(k){by[k.a]=k;});
  function seri(k){return Y.map(function(_,i){var c=0,n=0;for(var j=i-1;j<=i+1;j++){if(j<0||j>=Y.length)continue;c+=k[kay][j];n+=N[j];}return {v:n?100*c/n:0,c:k[kay][i],n:N[i]};});}
  function x(i){return L+(W-L-Rr)*i/(Y.length-1);}
  function ns(t,a){var e=document.createElementNS('http://www.w3.org/2000/svg',t);for(var k in a)e.setAttribute(k,a[k]);return e;}
  function ciz(){
    while(svg.firstChild)svg.removeChild(svg.firstChild);
    var olc=W/Math.max(280,svg.getBoundingClientRect().width||W); svg.style.fontSize=Math.min(20,Math.max(10,12.5*olc))+'px';
    var ss=sec.map(function(a){return seri(by[a]);}), mx=0;
    ss.forEach(function(s){s.forEach(function(p){if(p.v>mx)mx=p.v;});});
    var ust=mx<=2?2:mx<=5?5:mx<=10?10:mx<=15?15:mx<=20?20:Math.ceil(mx/10)*10, adim=ust<=5?1:ust<=10?2:ust<=20?5:10;
    function y(v){return T+(H-T-B)*(1-v/ust);}
    for(var v=0;v<=ust+1e-9;v+=adim){svg.appendChild(ns('line',{x1:L,x2:W-Rr,y1:y(v),y2:y(v),'class':'kt-izgara'}));
      var t=ns('text',{x:L-6,y:y(v)+4,'text-anchor':'end','class':'kt-eksen'});t.textContent='%'+v;svg.appendChild(t);}
    Y.forEach(function(yl,i){if(N[i]<60)svg.appendChild(ns('rect',{x:x(i)-(W-L-Rr)/(Y.length-1)/2,y:T,width:(W-L-Rr)/(Y.length-1),height:H-T-B,'class':'kt-silik'}));
      if(yl%5===0||i===Y.length-1){var t=ns('text',{x:x(i),y:H-B+18,'text-anchor':'middle','class':'kt-eksen'});t.textContent=yl;svg.appendChild(t);}});
    ss.forEach(function(s,si){var d='';s.forEach(function(p,i){d+=(i?'L':'M')+x(i).toFixed(1)+' '+y(p.v).toFixed(1);});
      svg.appendChild(ns('path',{d:d,fill:'none',stroke:R[si],'stroke-width':2.2,'stroke-linejoin':'round'}));});
    var cizgi=ns('line',{y1:T,y2:H-B,'class':'kt-imlec',visibility:'hidden'});svg.appendChild(cizgi);
    var alan=ns('rect',{x:L,y:T,width:W-L-Rr,height:H-T-B,fill:'transparent'});svg.appendChild(alan);
    function goster(ev){var r=svg.getBoundingClientRect(),px=(ev.touches?ev.touches[0].clientX:ev.clientX)-r.left,sx=px*W/r.width;
      var i=Math.max(0,Math.min(Y.length-1,Math.round((sx-L)/(W-L-Rr)*(Y.length-1))));
      cizgi.setAttribute('x1',x(i));cizgi.setAttribute('x2',x(i));cizgi.setAttribute('visibility','visible');
      ip.innerHTML='<b>'+Y[i]+'</b> · '+N[i]+' çalışma'+(sec.length?' · ':'')+sec.map(function(a,si){var p=ss[si][i];
        return '<span style="color:'+R[si]+'">'+a+': '+p.c+' çalışma, %'+p.v.toFixed(1).replace('.',',')+'</span>';}).join(' · ');}
    alan.addEventListener('mousemove',goster);alan.addEventListener('touchstart',goster,{passive:true});alan.addEventListener('touchmove',goster,{passive:true});
    alan.addEventListener('mouseleave',function(){cizgi.setAttribute('visibility','hidden');ipsifir();});
    var sl=document.querySelector('.kt-secili');sl.innerHTML='';
    sec.forEach(function(a,si){var b=document.createElement('button');b.type='button';b.className='kt-cip';b.style.borderColor=R[si];b.style.color=R[si];
      b.innerHTML='<span>'+a+'</span> <span aria-hidden="true">×</span>';b.title='Çizimden çıkar';b.onclick=function(){degis(a);};sl.appendChild(b);
      var k=by[a];['eserler','tezler'].forEach(function(s){var l=document.createElement('a');l.className='kt-bag';l.href='/'+s+'/?ara='+encodeURIComponent(k.r);l.textContent=s==='eserler'?'Eserlerde ara':'Tezlerde ara';sl.appendChild(l);});});
    if(!sec.length)sl.textContent='Aşağıdan bir kavram seçin.';
    document.querySelectorAll('.kt-liste button').forEach(function(b){b.setAttribute('aria-pressed',sec.indexOf(b.dataset.ad)>-1?'true':'false');});
    ipsifir(); yazUrl();
  }
  function ipsifir(){ip.textContent='Değerleri görmek için çizimin üzerinde gezinin.';}
  function degis(a){var i=sec.indexOf(a);if(i>-1)sec.splice(i,1);else{if(sec.length>=4)sec.shift();sec.push(a);}ciz();}
  function yazUrl(){var p=new URLSearchParams();if(sec.length)p.set('k',sec.join('|'));if(kay==='b')p.set('kaynak','baslik');
    try{history.replaceState(null,'',location.pathname+(p.toString()?'?'+p:''));}catch(_){}}
  document.querySelectorAll('.kt-liste button').forEach(function(b){b.addEventListener('click',function(){degis(b.dataset.ad);});});
  document.querySelectorAll('.kt-sec').forEach(function(b){b.addEventListener('click',function(){sec=[b.dataset.ad];ciz();window.scrollTo({top:svg.getBoundingClientRect().top+scrollY-120,behavior:'smooth'});});});
  var kb=document.querySelectorAll('.kt-kaynak button');
  kb.forEach(function(b){b.addEventListener('click',function(){kay=b.dataset.k;kb.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});ciz();});});
  var p=new URLSearchParams(location.search);
  sec=(p.get('k')||'Kötülük problemi|Dinî tecrübe|Yapay zekâ ve teknoloji').split('|').filter(function(a){return by[a];}).slice(0,4);
  if(p.get('kaynak')==='baslik'){kay='b';kb.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.k==='b'?'true':'false');});}
  ciz();
  var rz;window.addEventListener('resize',function(){clearTimeout(rz);rz=setTimeout(ciz,150);});
})();
</script>"""


def render_tezler() -> str:
    tezler = json.loads(TEZ_DOSYA.read_text(encoding="utf-8"))
    tezler.sort(key=lambda t: (t["yil"], t["ad"]), reverse=True)
    satirlar = []
    for t in tezler:
        durum = "devam" if t["devam"] else "tamam"
        hocalar = ", ".join(akademisyen_bag(h) for h in t["danisman"])
        parcalar = t["yer"].split(" / ")
        yer = tez_tr_baslik(parcalar[0]) + (", " + tez_tr_baslik(parcalar[2]) if len(parcalar) > 2 else "")
        ara = ara_norm(" ".join([t["ad"], " ".join(t["danisman"]), yer]))
        satirlar.append(
            f'<li data-tur="{e(t["tur"])}" data-durum="{durum}" data-yil="{e(t["yil"])}" data-ad="{e(t["ad"])}" '
            f'data-danisman="{e(t["danisman"][0])}" data-ara="{e(ara)}">'
            f'<div class="tez-ust"><p class="tez-ad">{e(t["ad"])}</p>{tez_rozetleri(t)}</div>'
            f'<p class="tez-kunye">{e(t["yil"])} · Danışman: {hocalar}</p><p class="tez-yer">{e(yer)}</p></li>')
    def dugme(alan, deger, ad):
        return f'<button type="button" data-{alan}="{deger}" aria-pressed="{"true" if not deger else "false"}">{ad} <span class="say"></span></button>'
    turler = "".join([dugme("tur", "", "Tümü"), dugme("tur", "Yüksek Lisans", "Yüksek lisans"), dugme("tur", "Doktora", "Doktora")])
    durumlar = "".join([dugme("durum", "", "Tümü"), dugme("durum", "devam", "Devam ediyor"), dugme("durum", "tamam", "Tamamlandı")])
    siralama = ('<div class="eser-sirala" role="group" aria-label="Sıralama"><span>Sırala</span>'
                + "".join(f'<button type="button" class="sirala" data-alan="{k}" aria-sort="none">{a}<span class="ok" aria-hidden="true"></span></button>'
                          for k, a in [("yil", "Yıl"), ("danisman", "Danışman"), ("ad", "Tez adı")]) + '</div>')
    body = (f'<p class="ust-etiket">Tezler</p><h1>Tezler</h1>'
            f'<p class="aciklama-kisa">Listedeki akademisyenlerin danışmanlığını yaptığı ya da yürüttüğü yüksek lisans ve doktora tezleri. '
            f'Kayıtlar, akademisyenlerin YÖK Akademik profillerinde yer alan yönetilen tezler listesinden alınmış ve YÖK Ulusal Tez Merkezi kayıtlarıyla karşılaştırılmıştır. '
            f'Öğrenci adları yazılmaz. Danışman adıyla ya da tez adında geçen bir kelimeyle arama yapılabilir. '
            f'Tez konularının yıllar içindeki seyri <a href="{SITE_URL}/kavram-tarihi/">Kavram tarihi</a> sayfasında izlenebilir. '
            f'Düzeltme önerileri için: <a href="mailto:{ILETISIM}">{ILETISIM}</a></p>'
            '<label class="secim-etiket" for="tez-ara">Ara</label>'
            '<div class="eser-konu-kap eser-ara-kap"><input type="search" id="tez-ara" class="eser-konu-sec" placeholder="Tez adı, danışman ya da üniversite" autocomplete="off"></div>'
            f'<p class="secim-etiket secim-ayrac">Tür</p><div class="tur-secici tez-sec" data-grup="tur" role="group" aria-label="Tez türü">{turler}</div>'
            f'<p class="secim-etiket tez-durum-etiket">Durum</p><div class="tur-secici tez-sec" data-grup="durum" role="group" aria-label="Tez durumu">{durumlar}</div>'
            f'<div class="eser-ust"><p class="eser-sayi"><span id="tez-say"></span></p>{siralama}</div>'
            f'<ul class="eser-liste tez-liste">{"".join(satirlar)}</ul>'
            f'<p class="giris eser-bos" hidden>Seçime uyan tez bulunamadı.</p>')
    return page(f"Tezler · {SITE_NAME}", body + TEZ_JS, "tezler", canonical=f"{SITE_URL}/tezler/")


TEZ_JS = """<script>
(function(){
  var lis=[].slice.call(document.querySelectorAll('ul.tez-liste > li')), ul=document.querySelector('ul.tez-liste');
  var g=document.getElementById('tez-ara'), sb=document.querySelectorAll('.eser-sirala button');
  var f={tur:'',durum:''}, alan='yil', yon=-1;
  var kucuk=function(s){return s.replace(/I/g,'ı').replace(/İ/g,'i').toLowerCase().replace(/[âäāàá]/g,'a').replace(/[êēëè]/g,'e').replace(/[îïīì]/g,'i').replace(/[ôōò]/g,'o').replace(/[ûūù]/g,'u').replace(/[\'`´‘’ʻʼʽʾʿ]/g,'');};
  var kar=function(a,b){return a.localeCompare(b,'tr',{sensitivity:'base'});};
  function uygula(yaz){
    var q=kucuk(g.value.trim()), n=0, say={tur:{'':0},durum:{'':0}};
    lis.forEach(function(li){
      var ara=!q||li.dataset.ara.indexOf(q)>-1;
      var tu=!f.tur||li.dataset.tur===f.tur, du=!f.durum||li.dataset.durum===f.durum;
      say.tur['']++; say.tur[li.dataset.tur]=(say.tur[li.dataset.tur]||0)+1;
      if(tu){say.durum['']++; say.durum[li.dataset.durum]=(say.durum[li.dataset.durum]||0)+1;}
      li.hidden=!(ara&&tu&&du); if(!li.hidden)n++;
    });
    ['tur','durum'].forEach(function(k){
      document.querySelectorAll('[data-grup="'+k+'"] button').forEach(function(b){
        b.querySelector('.say').textContent=say[k][b.dataset[k]]||0;
        b.setAttribute('aria-pressed',b.dataset[k]===f[k]?'true':'false');
      });
    });
    document.getElementById('tez-say').textContent=n+' tez';
    document.querySelector('.eser-bos').hidden=n>0;
    if(yaz){var p=new URLSearchParams(); if(g.value.trim())p.set('ara',g.value.trim()); if(f.tur)p.set('tur',f.tur); if(f.durum)p.set('durum',f.durum);
      history.replaceState(null,'',location.pathname+(p.toString()?'?'+p.toString():''));}
  }
  function sirala(){
    var a=lis.slice().sort(function(x,y){
      var r=alan==='yil'?(+x.dataset.yil)-(+y.dataset.yil):kar(x.dataset[alan],y.dataset[alan]);
      return (r||kar(x.dataset.ad,y.dataset.ad))*yon; });
    a.forEach(function(li){ul.appendChild(li);});
    sb.forEach(function(b){var ok=b.dataset.alan===alan; b.setAttribute('aria-sort',ok?(yon>0?'ascending':'descending'):'none'); b.querySelector('.ok').textContent=ok?(yon>0?'↑':'↓'):'';});
  }
  document.querySelectorAll('.tez-sec').forEach(function(grp){grp.addEventListener('click',function(ev){
    var b=ev.target.closest('button'); if(!b)return; f[grp.dataset.grup]=b.dataset[grp.dataset.grup]; uygula(true);});});
  sb.forEach(function(b){b.addEventListener('click',function(){ if(alan===b.dataset.alan){yon=-yon;}else{alan=b.dataset.alan;yon=alan==='yil'?-1:1;} sirala();});});
  g.addEventListener('input',function(){uygula(true);});
  var p=new URLSearchParams(location.search); g.value=p.get('ara')||''; f.tur=p.get('tur')||''; f.durum=p.get('durum')||'';
  sirala(); uygula(false);
})();
</script>"""


def render_eserler() -> str:
    ogeler = eser_ogeleri()
    def satir_(i, o):
        return (f'<li data-tur="{e(o["tur"])}" data-konu=" {e(" ".join(sorted(o["konu"])))} " data-ara="{e(o["ara"])}" '
                f'data-sira="{i}" data-yil="{e(o["yil"])}" data-yazar="{e(o["yazar"])}" data-ad="{e(o["ad"])}">{o["html"]}</li>')
    temel = "".join(satir_(i, o) for i, o in enumerate(ogeler) if o.get("grup") == "temel")
    turkce = "".join(satir_(i, o) for i, o in enumerate(ogeler) if o.get("grup") != "temel")
    satirlar = "".join(f'<li data-tur="{e(o["tur"])}" data-konu=" {e(" ".join(sorted(o["konu"])))} " data-ara="{e(o["ara"])}" '
                       f'data-sira="{i}" data-yil="{e(o["yil"])}" data-yazar="{e(o["yazar"])}" data-ad="{e(o["ad"])}">{o["html"]}</li>'
                       for i, o in enumerate(ogeler))
    konular = ['<option value="">Bütün konular</option>']
    for kad, ks in kumeli_basliklar():
        konular.append(f'<optgroup label="{e(kad)}">')
        for k in ks:
            konular.append(f'<option value="{k}">{e(FIS[("baslik", k)]["ad"])}</option>')
            for c in sorted(COCUK.get(k, []), key=lambda x: FIS[("baslik", x)].get("sira", 99)):
                konular.append(f'<option value="{c}">\u00a0\u00a0\u00a0{e(FIS[("baslik", c)]["ad"])}</option>')
        konular.append('</optgroup>')
    turler = ['<button type="button" data-tur="" aria-pressed="true">Tümü <span class="say"></span></button>']
    turler += [f'<button type="button" data-tur="{t}" aria-pressed="false">{a} <span class="say"></span></button>'
               for t, a in ESER_TURLERI]
    siralama = ('<div class="eser-sirala" role="group" aria-label="Sıralama"><span>Sırala</span>'
                + "".join(f'<button type="button" class="sirala" data-alan="{k}" aria-sort="none">{a}<span class="ok" aria-hidden="true"></span></button>'
                          for k, a in [("yil", "Yıl"), ("yazar", "Yazar"), ("ad", "Eser adı")]) + '</div>')
    tarih = dp_tarama_tarihi()
    body = (f'<p class="ust-etiket">Eserler</p><h1>Eserler</h1>'
            f'<p class="aciklama-kisa">Türkiye akademisindeki din felsefecilerinin eserleri ile Türkiye\'de yayımlanan din felsefesi çalışmaları. '
            f'Liste, sitede fişi bulunan eserlerden, DergiPark\'ta anahtar kelimelerinde din felsefesi geçen makalelerden, hocaların ORCID kayıtlarındaki DOI\'li çalışmalardan '
            f've AVESİS ya da YÖK Akademik sayfalarında yer alıp konusu açıkça bir başlığa giren yayınlardan oluşur. '
            f'Bir konu seçildiğinde o konudaki bütün eserler listelenir. Sitede fişi bulunan eserler başta yer alır, '
            f'makaleler yeniden eskiye sıralanır. Makalelerin konuları anahtar kelimelerine göre atanmıştır'
            f'{" (son tarama " + tr_date(tarih) + ")" if tarih else ""}. '
            f'Kavramların yıllar içindeki seyri <a href="{SITE_URL}/kavram-tarihi/">Kavram tarihi</a> sayfasında izlenebilir. '
            f'Düzeltme önerileri için: <a href="mailto:{ILETISIM}">{ILETISIM}</a></p>'
            f'<label class="secim-etiket" for="eser-konu">Konu</label><div class="eser-konu-kap"><select id="eser-konu" class="eser-konu-sec">{"".join(konular)}</select></div>'
            '<label class="secim-etiket eser-ara-etiket" for="eser-ara">Başlık ara</label>'
            '<div class="eser-konu-kap eser-ara-kap"><input type="search" id="eser-ara" class="eser-konu-sec" placeholder="Başlık, yazar ya da dergi" autocomplete="off"></div>'
            f'<p class="secim-etiket secim-ayrac">Eser türü</p>'
            f'<div class="eser-arac"><div class="tur-secici eser-tur-sec" role="group" aria-label="Eser türü">{"".join(turler)}</div></div>'
            f'<div class="eser-ust"><p class="eser-sayi"><span id="eser-say"></span></p>{siralama}</div>'
            f'<ul class="eser-liste">{temel}{turkce}</ul>'
            f'<p class="giris eser-bos" hidden>Seçime uyan eser bulunamadı.</p>')
    return page(f"Eserler · {SITE_NAME}", body + ESER_JS, "eserler", canonical=f"{SITE_URL}/eserler/")


ESER_JS = """<script>
(function(){
  var uls=[].slice.call(document.querySelectorAll('ul.eser-liste')), lis=[].slice.call(document.querySelectorAll('ul.eser-liste > li'));
  var ks=document.getElementById('eser-konu'), tb=document.querySelectorAll('.eser-tur-sec button');
  var sb=document.querySelectorAll('.eser-sirala button');
  var g=document.getElementById('eser-ara');
  var konu='', tur='', alan='', yon=1;
  var kucuk=function(s){return s.replace(/I/g,'ı').replace(/İ/g,'i').toLowerCase().replace(/[âäāàá]/g,'a').replace(/[êēëè]/g,'e').replace(/[îïīì]/g,'i').replace(/[ôōò]/g,'o').replace(/[ûūù]/g,'u').replace(/[\'`´‘’ʻʼʽʾʿ]/g,'');};
  var kar=function(a,b){return a.localeCompare(b,'tr',{sensitivity:'base'});};
  function uygula(yaz){
    var q=kucuk(g.value.trim()), n=0, ts={'':0};
    lis.forEach(function(li){
      var uy=(!q||li.dataset.ara.indexOf(q)>-1)&&(!konu||li.dataset.konu.indexOf(' '+konu+' ')>-1);
      if(uy){ ts['']++; ts[li.dataset.tur]=(ts[li.dataset.tur]||0)+1; }
      var v=uy&&(!tur||li.dataset.tur===tur);
      li.hidden=!v; if(v)n++;
    });
    ks.value=konu; if(ks.value!==konu){ks.value='';}
    tb.forEach(function(b){
      var c=ts[b.dataset.tur]||0; b.querySelector('.say').textContent=c;
      b.hidden = !c && b.dataset.tur!=='' && b.dataset.tur!==tur;
      b.setAttribute('aria-pressed', b.dataset.tur===tur?'true':'false');
    });
    document.getElementById('eser-say').textContent=n+' eser';
    uls.forEach(function(u){var c=[].filter.call(u.children,function(li){return !li.hidden;}).length, h=u.previousElementSibling, nt=null;
      if(h&&h.classList.contains('eser-grup-not')){nt=h; h=h.previousElementSibling;}
      u.hidden=!c; if(nt)nt.hidden=!c; if(h&&h.classList.contains('eser-grup')){h.hidden=!c; h.querySelector('.eser-grup-say').textContent=c;}});
    document.querySelector('.eser-bos').hidden=n>0;
    if(yaz){
      var p=new URLSearchParams(); if(konu)p.set('konu',konu); if(tur)p.set('tur',tur); if(g.value.trim())p.set('ara',g.value.trim());
      if(alan){p.set('sirala',alan); if(yon<0)p.set('yon','azalan');}
      try{history.replaceState(null,'',location.pathname+(p.toString()?'?'+p:''));}catch(_){}
    }
  }
  function sirala(){
    var r=lis.slice();
    r.sort(function(a,b){
      if(!alan) return (+a.dataset.sira)-(+b.dataset.sira);
      var ab=!a.dataset[alan], bb=!b.dataset[alan];
      if(ab!==bb) return ab?1:-1;  // bilgisi olmayanlar her iki yönde de sona
      var f = alan==='yil' ? (+a.dataset.yil||0)-(+b.dataset.yil||0) : kar(a.dataset[alan],b.dataset[alan]);
      return f*yon || kar(a.dataset.ad,b.dataset.ad);
    });
    r.forEach(function(x){x.parentNode.appendChild(x);});
    sb.forEach(function(b){b.setAttribute('aria-sort', b.dataset.alan===alan ? (yon>0?'ascending':'descending') : 'none');});
  }
  ks.addEventListener('change',function(){konu=ks.value; tur=''; uygula(true);});
  tb.forEach(function(b){b.addEventListener('click',function(){tur=b.dataset.tur; uygula(true);});});
  sb.forEach(function(b){b.addEventListener('click',function(){
    if(alan===b.dataset.alan){yon=-yon;} else {alan=b.dataset.alan; yon = alan==='yil' ? -1 : 1;}
    sirala(); uygula(true);
  });});
  g.addEventListener('input',function(){uygula(true);});
  var p=new URLSearchParams(location.search);
  konu=p.get('konu')||''; tur=p.get('tur')||''; g.value=p.get('ara')||'';
  alan=p.get('sirala')||''; yon = p.get('yon')==='azalan' ? -1 : 1;
  if(alan) sirala();
  uygula(false);
})();
</script>"""


# ---------------------------------------------------------------- Türkçe makaleler (DergiPark)

DP_DIZIN = ROOT / "data" / "dergipark"
DP_TUR_AD = {"kitap-tanitimi": "Kitap tanıtımı", "ceviri": "Çeviri", "ceviri-degerlendirmesi": "Çeviri değerlendirmesi",
             "soylesi": "Söyleşi", "kitap": "Kitap", "kitap-bolumu": "Kitap bölümü", "bildiri": "Bildiri", "tez": "Tez"}
_DP = None
_DP_LISTE_DIGER = []
KUCUK_KELIME = {"ve", "ile", "veya", "ya", "da", "de", "ki", "mi", "mı", "mu", "mü", "a", "an", "the", "of", "and", "or",
                "in", "on", "at", "to", "for", "from", "by", "with", "as", "der", "die", "das"}


def harf_duzelt(t: str, dil: str) -> str:
    """Tamamı büyük harfle kaydedilmiş başlıkları başlık düzenine çevirir. Diğer başlıklara dokunmaz."""
    t = unicodedata.normalize("NFC", (t or "").replace("İ", "İ")).strip()
    if t.upper() != t or not re.search(r"[A-ZÇĞİÖŞÜ]{3}", t):
        return t
    turkce = dil.startswith("tr")
    kucuk = (lambda s: s.replace("I", "ı").replace("İ", "i").lower()) if turkce else (lambda s: s.replace("İ", "i").lower())
    buyuk1 = (lambda s: ("İ" if s[0] == "i" else s[0].upper()) + s[1:]) if turkce else (lambda s: s[0].upper() + s[1:])
    out, onceki = [], ""
    for i, w in enumerate(t.split(" ")):
        ilk = i == 0 or onceki.endswith((":", "?", ".", "!", "–"))
        onceki = w
        if re.fullmatch(r"[IVXLC]+[.,:]?", w):
            out.append(w)
            continue
        m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", w)
        on, govde, son = m.groups()
        if not govde:
            out.append(w)
            continue
        parca = re.split(r"(['’])", govde, maxsplit=1)
        kok, ek = kucuk(parca[0]), kucuk("".join(parca[1:]))
        kokler = re.split(r"([-/])", kok)
        for j in range(0, len(kokler), 2):
            p = kokler[j]
            if not p:
                continue
            if j and len(p) == 1 and kokler[j - 1] == "-":  # izafet: İhvân-ı, Vahdet-i
                continue
            if ilk and j == 0 or p not in KUCUK_KELIME:
                kokler[j] = buyuk1(p)
        out.append(on + "".join(kokler) + ek + son)
    return " ".join(out)


def ad_anahtari(ad_: str) -> str:
    """Yazar adlarını eşleştirmek için: büyük-küçük harf ve Türkçe harf farkları gözetilmez (Tüfenkçi = Tüfenkci)."""
    return slugify(tr_kucuk(ad_))


def dp_veri() -> list:
    """DergiPark taramasındaki makaleler, sınıflandırmasıyla birlikte. Kapsam dışı makaleler alınmaz."""
    global _DP
    if _DP is not None:
        return _DP
    _DP = []
    if not (DP_DIZIN / "din_felsefesi.jsonl").exists():
        return _DP
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import dergipark_siniflandir as dps
    makaleler, sonuc, *_ = dps.siniflandir()
    duzeltme = yaml.safe_load((DP_DIZIN / "baslik_duzeltme.yaml").read_text(encoding="utf-8")) or {} \
        if (DP_DIZIN / "baslik_duzeltme.yaml").exists() else {}
    sinif = {x["id"]: x for x in sonuc}
    global _DP_LISTE_DIGER
    _DP_LISTE_DIGER = []
    liste_ = akademisyen_dizini()
    elle_d = DP_DIZIN / "akademisyen_elle.yaml"
    elle = {str(k): v for k, v in ((yaml.safe_load(elle_d.read_text(encoding="utf-8")) or {}) if elle_d.exists() else {}).items()}
    from orcid_siniflandir import kelime_basliklari
    _, kurallar, genel = dps.yukle()
    for r in makaleler:
        x = sinif.get(r["id"]) or {}
        if x.get("durum") == "kapsam-disi":
            continue
        if x.get("durum") == "anahtar-kelime-yok":
            # Konu alanı Din Felsefesi olup anahtar kelimesinde din felsefesi geçmeyen makaleler listeye girmez.
            # Yazarı Türkiye akademisi listesindeyse kişinin makalesi sayılır ve öteki makaleleri gibi sınıflandırılır.
            if not any(ad_anahtari(y) in liste_ for y in dp_kaydi(r, {}, duzeltme, dps)["yazarlar"]):
                continue
            e_ = elle.get(str(r["id"])) or {}
            if e_.get("karar") == "yanlis-kisi":
                continue
            basliklar, _e = kelime_basliklari(dps.anahtar_kelimeler(r), kurallar, genel)
            if isinstance(e_.get("karar"), list):
                basliklar = set(e_["karar"]) | {dps.UST[b] for b in e_["karar"] if b in dps.UST}
            if basliklar and e_.get("karar") != "kapsam-disi":
                _DP.append(dp_kaydi(r, {"basliklar": sorted(basliklar), "ilgili_basliklar": [], "yayin_turu": e_.get("tur") or ""},
                                    duzeltme, dps) | {"kaynak": "dergipark-akademisyen"})
            else:
                _DP_LISTE_DIGER.append(dp_kaydi(r, {}, duzeltme, dps))
            continue
        _DP.append(dp_kaydi(r, x, duzeltme, dps))
    # Türkiye akademisi listesindeki kişilerin öteki DergiPark makaleleri: yazarı doğrulanmış ve konusu belli olanlar
    for r, x in akademisyen_dp():
        if x["durum"] == "konulu":
            _DP.append(dp_kaydi(r, {"basliklar": x["basliklar"], "ilgili_basliklar": x["ilgili"], "yayin_turu": x["tur"]},
                                duzeltme, dps) | {"kaynak": "dergipark-akademisyen"})
    _DP += orcid_eserleri()
    _DP += avesis_eserleri(_DP)
    _DP.sort(key=lambda m: (m["tarih"], m["id"]), reverse=True)
    return _DP


_AK_DP = None


def akademisyen_dp() -> list:
    """(DergiPark kaydı, doğrulama ve sınıflandırma sonucu) çiftleri; yalnızca yazarı doğrulanmış makaleler."""
    global _AK_DP
    if _AK_DP is None:
        _AK_DP = []
        kayit, sinif = DP_DIZIN / "akademisyen_makaleleri.jsonl", DP_DIZIN / "akademisyen_sinif.json"
        if kayit.exists() and sinif.exists():
            s = json.loads(sinif.read_text(encoding="utf-8"))
            for l in kayit.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    r = json.loads(l)
                    if r["id"] in s:
                        _AK_DP.append((r, s[r["id"]]))
    return _AK_DP


_LISTE_ADLARI = None


def yazar_adi(y: str) -> str:
    """Türkiye akademisi listesindeki kişiler listedeki yazılışıyla; büyük harfle kaydedilmiş adlar başlık düzeninde."""
    global _LISTE_ADLARI
    if _LISTE_ADLARI is None:
        dosya = CONTENT / "turkiye_akademisi.yaml"
        kisiler = (yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}).get("kisiler") or [] if dosya.exists() else []
        _LISTE_ADLARI = {ad_anahtari(p["ad"]): p["ad"] for p in kisiler}
    if ad_anahtari(y) in _LISTE_ADLARI:
        return _LISTE_ADLARI[ad_anahtari(y)]
    return " ".join(harf_duzelt(p, "tr-TR") if len(p) > 1 and p.isupper() else p for p in y.split())


_YAYIM = None


def yayim_tarihi(kimlik) -> str:
    """Makalenin DergiPark sayfasındaki yayımlanma tarihi (scripts/yayim_tarihi.py); bilinmiyorsa boş."""
    global _YAYIM
    if _YAYIM is None:
        d = ROOT / "data" / "dergipark" / "yayim_tarihi.json"
        _YAYIM = json.loads(d.read_text(encoding="utf-8")) if d.exists() else {}
    return _YAYIM.get(str(kimlik)) or ""


def ay_yil(tarih: str) -> str:
    """'2026-06-28' -> 'Haziran 2026'."""
    try:
        return f"{AYLAR[int(tarih[5:7]) - 1]} {tarih[:4]}"
    except (ValueError, IndexError):
        return tarih[:4]


def dp_kaydi(r, x, duzeltme, dps) -> dict:
    """DergiPark OAI kaydını sitedeki makale biçimine çevirir."""
    basliklar = r.get("baslik") or {}
    dil = "tr-TR" if "tr-TR" in basliklar else next(iter(basliklar), "")
    ham = basliklar.get(dil, "")
    # büyük harfle kaydedilmiş başlıkta Türkçeye özgü harf yoksa İngilizce kurallarıyla küçültülür (I -> i)
    baslik = duzeltme.get(r["id"]) or harf_duzelt(ham, dil if re.search(r"[ÇĞİÖŞÜÂÎÛçğıöşü]", ham) else "en-US")
    kaynak = (r.get("kaynak") or [""])[0]
    dergi = re.split(r",?\s*(?:Vol\.|No\.)", kaynak)[0].rstrip(", ")
    cs = kaynak[len(dergi):]
    mc = re.search(r"Vol\.\s*(\S+)", cs)
    ms_ = re.search(r"No\.\s*(.+)", cs)
    cilt_sayi = ", ".join(x for x in [f"C. {mc.group(1)}" if mc and mc.group(1) not in ("0", "00") and not re.fullmatch(r"(19|20)\d\d", mc.group(1)) else "",
                                       f"S. {ms_.group(1).strip()}" if ms_ and ms_.group(1).strip()[:1].isdigit() else ""] if x)
    baglanti = r.get("baglanti") or []
    doi = next((b for b in baglanti if "doi.org" in b), "")
    yazarlar = []
    for y in r.get("yazarlar") or []:
        soy_, _, ad_ = y.partition(",")
        yazarlar.append(yazar_adi(f"{ad_.strip()} {soy_.strip()}".strip() if ad_ else y.strip()))
    return {
        "id": r["id"], "baslik": baslik, "yazarlar": yazarlar, "dergi": dergi.strip(), "cilt_sayi": cilt_sayi,
        # OAI kaydındaki tarih çoğunlukla gönderilme tarihidir; makale sayfasından okunan yayım tarihi önce gelir
        "yil": (yayim_tarihi(r["id"]) or (r.get("tarih") or [""])[0] or "")[:4],
        "tarih": yayim_tarihi(r["id"]) or (r.get("tarih") or [""])[0] or "", "yayim": bool(yayim_tarihi(r["id"])),
        "baglanti": doi or (baglanti[0] if baglanti else ""), "doi": bool(doi),
        "konular": [] if x.get("yayin_turu") else list(x.get("basliklar") or []),
        "ilgili": list(x.get("ilgili_basliklar") or []), "tur": x.get("yayin_turu") or "",
        "kelimeler": dps.anahtar_kelimeler(r),
    }


ORCID_ISARET = ' <span class="m-kaynak" title="ORCID kaydından">ORCID</span>'
AVESIS_ISARET = ' <span class="m-kaynak" title="AVESİS sayfasından">AVESİS</span>'
KISISEL_ISARET = ' <span class="m-kaynak" title="Yazarın kişisel sitesinden">Kişisel site</span>'
YOK_ISARET = ' <span class="m-kaynak" title="YÖK Akademik kaydından">YÖK</span>'


def orcid_eserleri() -> list:
    """ORCID kayıtlarındaki DOI'li eserlerden, anahtar kelimeleri bir başlığa uyanlar (scripts/orcid_siniflandir.py).
    DergiPark listesinde zaten bulunanlar orada ayıklanmıştır. Yazar listesinde akademisyenin adı listedeki yazılışıyla yer alır."""
    dosya = ROOT / "data/orcid/eser_sinif.json"
    if not dosya.exists():
        return []
    out = []
    for doi, x in json.loads(dosya.read_text(encoding="utf-8")).items():
        if x["durum"] != "konulu":
            continue
        yazarlar = []
        for y in (y.strip() for y in x["yazarlar"] if y.strip()):
            esit = next((s for s in x["sahipler"] if ad_anahtari(s) == ad_anahtari(y)), None)
            yazarlar.append(esit or (harf_duzelt(y, "tr-TR" if re.search(r"[ÇĞİÖŞÜ]", y) else "en-US") if y.isupper() else y))
        for s in x["sahipler"]:
            if s in yazarlar:
                continue
            soy_ = slugify(s.split()[-1])
            i = next((i for i, y in enumerate(yazarlar) if y.split() and slugify(y.split()[-1]) == soy_), None)
            if i is None:
                yazarlar.append(s)
            else:
                yazarlar[i] = s
        baslik = x["baslik"]
        if baslik.isupper():
            baslik = harf_duzelt(baslik, "tr-TR" if re.search(r"[ÇĞİÖŞÜÂÎÛ]", baslik) else "en-US")
        tanitim = x["tur"] in ("kitap-tanitimi", "ceviri")
        out.append({
            "id": "orcid-" + slugify(doi), "baslik": baslik, "yazarlar": yazarlar, "dergi": x["dergi"], "cilt_sayi": "",
            "yil": x["yil"], "tarih": x["yil"], "baglanti": "https://doi.org/" + doi, "doi": True,
            "konular": [] if tanitim else list(x["basliklar"]), "ilgili": list(x["ilgili"]), "tur": x["tur"],
            "kelimeler": x["kelimeler"], "kaynak": "orcid",
        })
    return out


_AVESIS = None


def avesis_tur(bolum: str, baslik: str = "", kaynak: str = "") -> str:
    if re.match(r"\s*(kitap\s+(değerlendirme|tanıtım|inceleme|kritiği)|book\s+review)", tr_kucuk(baslik)):
        return "kitap-tanitimi"
    b = tr_kucuk(bolum)
    if b.startswith("kitap") and re.search(r"\bss?\.\s*\d+\s*[-–]\s*\d+", kaynak or ""):
        return "kitap-bolumu"  # AVESİS'in Kitaplar bölümünde sayfa aralığı olanlar kitap bölümüdür
    for anahtar, tur in (("bildiri", "bildiri"), ("bölüm", "kitap-bolumu"), ("kitap", "kitap"), ("makale", "makale"), ("tez", "tez")):
        if anahtar in b:
            return tur
    return "diger"


def buyuk_duzelt(t: str) -> str:
    """Tamamı ya da neredeyse tamamı büyük harfle yazılmış adları düzeltir ('ve', 'ile' gibi küçük kelimeler olsa da)."""
    harfler = [c for c in t if c.isalpha()]
    if len(harfler) < 8 or sum(c.isupper() for c in harfler) / len(harfler) < 0.85:
        return t
    if re.search(r"[ÇĞİÖŞÜÂÎÛçğıöşü]", t):
        return harf_duzelt(t.replace("i", "İ").upper(), "tr-TR")
    return harf_duzelt(t.upper(), "en-US")


def avesis_kunye(kaynak: str, yil: str) -> str:
    """AVESİS künye satırı: dizin etiketleri, sayfa aralığı ve yıl çıkarılır (yıl ayrıca yazılır)."""
    k = re.sub(r"(\s*\([^()]*\))+\s*$", "", kaynak or "").strip()
    k = re.sub(r",\s*ss?\.\s*[\divxlc]+(\s*[-–]\s*[\divxlc]+)?(?=,|$)", "", k)
    if yil:
        k = re.sub(r",[^,]*\b" + re.escape(yil) + r"\s*,?\s*$", "", k)
    k = re.sub(r",\s*Editör\b", "", k)
    k = ", ".join(buyuk_duzelt(p_.strip()) for p_ in re.sub(r"(,\s*)+", ",", k).split(","))
    k = re.sub(r"\bcilt\.\s*", "cilt ", k)
    k = re.sub(r"\bsa\.\s*", "sayı ", k)
    return re.sub(r"\s+,", ",", k).strip(" ,")


def yok_kunye(kaynak: str, yil: str, bolum: str) -> str:
    """YÖK Akademik liste satırı: dizin etiketleri ve baskı/sayfa sayısı çıkarılır. Kitap bölümlerinde YÖK yalnızca kitabın
    adını verdiği için künye 'kitabın içinde, ss. ...' diye başlar."""
    k = re.sub(r"\s*\((Uluslararası|Ulusal)\b.*$", "", kaynak or "")  # YÖK etiketleri (iç içe parantez içerebilir)
    k = re.sub(r"\s*\([^()]*\)\s*$", "", k)
    sayfa = (re.findall(r"Bölüm sayfa:\s*([\d\s\-–]+)", k) or [""])[0].strip(" -–")
    ed = (re.findall(r"Editör:\s*([^,]+(?:,\s*[^,:]+)*?)(?=,\s*(?:Basım|Sayfa|Bölüm)|$)", k) or [""])[0].strip()
    k = re.sub(r",?\s*(Editör|Basım sayısı|Sayfa sayısı|Bölüm sayfa):[^,]*(?:,\s*[^,:]+(?=,|$))*", "", k)
    k = re.sub(r",?\s*\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}", "", k)  # bildiri tarihleri
    if yil:
        k = re.sub(r",\s*" + re.escape(yil) + r"\s*$", "", k.strip())
    k = ", ".join(buyuk_duzelt(x.strip()) for x in k.split(",") if x.strip())
    if "bölüm" in tr_kucuk(bolum):
        return ", ".join(x for x in ["kitabın içinde" + (f", ss. {sayfa}" if sayfa else ""), k,
                                     f"ed. {buyuk_duzelt(ed)}" if ed else ""] if x)
    return k


def kisisel_kunye(kaynak: str, yil: str) -> str:
    """Kişisel sitedeki künye: yıl (ayrıca yazılır), baskı notları ve sondaki nokta çıkarılır."""
    k = re.sub(r"\s*\(\s*\d+\.\s*bask[ıi]\s*\)", "", kaynak or "", flags=re.I)
    k = re.sub(r"\s*\(Satış yerini.*?\)", "", k)
    k = re.sub(r";\s*(19|20)\d\d\b", "", k)  # sonraki baskıların yılı
    if yil:
        k = re.sub(r",\s*" + re.escape(yil) + r"(?=[\s,.;)]|$)", "", k, count=1)
        k = re.sub(r"\s+" + re.escape(yil) + r"\b", "", k, count=1)
    return re.sub(r"\s+,", ",", k).strip(" .,;")


def avesis_veri() -> dict:
    """AVESİS yayın listeleri (scripts/avesis_topla.py): kişinin adres kısaltması -> yayınlar.
    Elle başlığa bağlananlar (data/avesis/elle_tasnif.yaml, yayın kimliğine göre) 'konular' alanını taşır."""
    global _AVESIS
    if _AVESIS is not None:
        return _AVESIS
    _AVESIS = {}
    elle_d = ROOT / "data/avesis/elle_tasnif.yaml"
    elle = {str(k): v for k, v in ((yaml.safe_load(elle_d.read_text(encoding="utf-8")) or {}) if elle_d.exists() else {}).items()}
    import dergipark_siniflandir as dps
    from orcid_siniflandir import kelime_basliklari
    _, kurallar, genel = dps.yukle()
    kd = ROOT / "data/orcid/doi_kunye.json"
    kunye = json.loads(kd.read_text(encoding="utf-8")).get("kunye", {}) if kd.exists() else {}
    kaynaklar = []
    for yol, kaynak in (("data/avesis/yayinlar.json", "avesis"), ("data/kisisel/yayinlar.json", "kisisel"),
                        ("data/yok/yayinlar.json", "yok")):
        if (ROOT / yol).exists():
            kaynaklar += [(ad_, x, kaynak) for ad_, x in json.loads((ROOT / yol).read_text(encoding="utf-8")).items()]
    # YÖK Akademik listesi herkes için okunur: kişinin yayın listesinin esası odur. Aynı yayın AVESİS'te ya da başka bir
    # kaynakta da varsa sitede onun kaydı gösterilir (bağlantı, bölüm adı, anahtar kelime); YÖK'te olup olmadığı ayrıca tutulur.
    # DOI'si olmayan makaleler adlarıyla OpenAlex'te ve DergiPark'ta aranır (scripts/yok_baslik_ara.py); bulunanın DOI'si
    # ya da sayfası bağlantı olur, anahtar kelimeleri konuyu bulmakta kullanılır
    ap_ = ROOT / "data/yok/baslik_arama.json"
    arama = {k: v for k, v in (json.loads(ap_.read_text(encoding="utf-8")).get("kayit", {}) if ap_.exists() else {}).items()
             if v.get("durum") != "bulunamadi"}
    hd = ROOT / "data/yok/hatali_doi.yaml"
    hatali = (yaml.safe_load(hd.read_text(encoding="utf-8")) or {}) if hd.exists() else {}
    for ad_, x, kaynak in kaynaklar:
        soyad = ad_anahtari(ad_).split("-")[-1]
        ogeler = []
        # Aynı DOI kişinin birden çok yayınına verilmişse DOI yalnızca adı DOI kaydının adıyla örtüşen yayında kalır
        doi_say = Counter((y.get("doi") or "").lower() for y in x["yayinlar"] if y.get("doi"))
        for y in x["yayinlar"]:
            d_ = (y.get("doi") or "").lower()
            if d_ and ("xxx" in d_ or any(baslik_anahtari(h) in baslik_anahtari(y["baslik"]) for h in hatali.get(ad_, [])) or
                       doi_say[d_] > 1 and baslik_anahtari((kunye.get(d_) or {}).get("baslik") or "") != baslik_anahtari(y["baslik"])):
                y = dict(y, doi="")
            if kaynak == "avesis":
                kimlik = (re.findall(r"/yayin/([0-9a-f-]{36})", y["url"]) or [y["url"]])[0]
            elif kaynak == "yok":
                kimlik = "yok-" + (re.findall(r"[?&]id=([^&]+)", y["url"]) or [slugify(y["baslik"])[:60]])[0]
            else:  # kişisel sitedeki listeler: kimlik addan ve yıldan türetilir
                kimlik = "kisisel-" + slugify(y["baslik"])[:60] + "-" + (y["yil"] or "")
            e_ = elle.get(kimlik) or {}
            if e_.get("karar") == "yanlis-kisi" or haric_mi(ad_, y["baslik"]):
                continue
            # AVESİS yazarları "Soyad A." biçiminde yazar; sayfa sahibi listedeki tam adıyla yazılır
            if kaynak == "yok":  # YÖK yazarları "AD SOYAD" biçiminde büyük harfle yazar
                yazarlar = [ad_ if ad_anahtari(a).split("-")[-1:] == [soyad] else buyuk_duzelt(a) for a in y["yazarlar"]]
            else:
                yazarlar = [ad_ if ad_anahtari(a).split("-")[:1] == [soyad] else a for a in y["yazarlar"] if "(Editör)" not in a]
            if ad_ not in yazarlar:
                yazarlar.append(ad_)
            karar = e_.get("karar")
            konular = sorted(set(karar) | {dps.UST[b] for b in karar if b in dps.UST}) if isinstance(karar, list) else []
            # DOI'si olan yayınlarda konu, yazarın verdiği anahtar kelimelerden (DergiPark ya da OpenAlex) sözlükle bulunur;
            # anahtar kelimeler bir başlığa uymazsa adına bakılarak verilen elle karar geçerli kalır
            bulunan = arama.get(kimlik) if not y.get("doi") else None
            if bulunan and bulunan.get("doi"):
                y = dict(y, doi=bulunan["doi"])
            kelimeler = (kunye.get((y.get("doi") or "").lower()) or {}).get("kelimeler") or \
                ((bulunan or {}).get("kelimeler") or [])
            # Sözlük DergiPark'taki din felsefesi makaleleri için kurulmuştur; YÖK ve AVESİS listelerinde genel felsefe
            # yayınları da bulunduğundan ("etik", "epistemoloji", "dil" gibi kelimeler tek başına yetmez) anahtar kelimeyle
            # yerleştirme yalnızca adında ya da anahtar kelimelerinde dinle ilgili açık bir işaret olan yayında yapılır (özetler
            # dine geçerken değinebildiği için işaret sayılmaz)
            if kelimeler and not e_.get("kesin") and din_isareti(y["baslik"], kelimeler):
                bul, _ = kelime_basliklari(kelimeler, kurallar, genel)
                if bul:
                    konular = sorted(bul)
            baslik = e_.get("baslik") or buyuk_duzelt(baslik_temizle(y["baslik"], ad_))
            ogeler.append({"kimlik": kimlik, "sahip": ad_, "baslik": baslik, "yazarlar": yazarlar, "yil": y["yil"],
                           "tur": e_.get("tur") or avesis_tur(y["bolum"], y["baslik"], y["kaynak"]), "kunye": avesis_kunye(y["kaynak"], y["yil"]) if kaynak == "avesis" else
                           yok_kunye(y["kaynak"], y["yil"], y["bolum"]) if kaynak == "yok" else kisisel_kunye(y["kaynak"], y["yil"]),
                           "baglanti": f'https://doi.org/{y["doi"]}' if y.get("doi") else
                           (bulunan or {}).get("sayfa") or (y["url"] if kaynak == "avesis" else ""), "doi": bool(y.get("doi")),
                           "konular": konular, "kaynak": kaynak, "kelimeler": kelimeler})
        v_ = _AVESIS.setdefault(slugify(ad_), {"profil": x["profil"], "yayinlar": [], "yok_var": False})
        v_["yayinlar"] += ogeler
        if kaynak == "yok":
            v_["yok_var"] = True
    return _AVESIS


def eser_adi(baglanti: str, baslik: str, sinif: str = "eser-ad") -> str:
    """Eserin adı; eserin kendisine ya da kendi sayfasına giden bir adres varsa bağlantılı. YÖK Akademik'in yayın
    ayrıntı adresleri oturuma bağlı olduğu ve kişisel sitelerdeki adresler yalnızca liste sayfası olduğu için bu
    kayıtlarda bağlantı verilmez (hocanın sayfasına götüren bir bağlantı esere ulaştırmaz)."""
    c = f' class="{sinif} dis"' if sinif else ' class="dis"'
    if baglanti:
        return f'<a{c} href="{e(baglanti)}" rel="noopener" target="_blank">{e(baslik)}</a>'
    return f'<span class="{sinif or "eser-ad"}">{e(baslik)}</span>'


_DIN_ISARET = re.compile(
    r"\b(din|dinî|dini|dinin|dine|dinde|dinden|dinler\w*|dinsel\w*|dindar\w*|religio\w*|tanrı\w*|allah\w*|god|god's|gods|"
    r"divine|divinity|ilah\w*|ilâh\w*|ulûhiyy\w*|uluhiyy\w*|theolog\w*|teoloj\w*|theis\w*|teiz\w*|teist\w*|deiz\w*|deis\w*|"
    r"ateiz\w*|ateist\w*|atheis\w*|agnosti\w*|iman\w*|îman\w*|faith|kutsal\w*|sacred|numinous|vahiy\w*|vahy\w*|revelation|"
    r"peygamber\w*|prophet\w*|nübüvv\w*|kelam\w*|kelâm\w*|kalam|tasavvuf\w*|sufi\w*|mistisizm\w*|mystic\w*|ahiret\w*|"
    r"afterlife|eskatoloj\w*|eschatolog\w*|ölümsüzlük\w*|immortality|resurrection|teodise\w*|theodic\w*|ibadet\w*|worship|"
    r"ritüel\w*|ritual\w*|yaratılış\w*|creation|fıtrat\w*|fitra\w*|sensus|mucize\w*|miracle\w*|kurtuluş|salvation)\b")


def din_isareti(*metinler) -> bool:
    """Yayının adında, anahtar kelimelerinde ya da özetinde dinle ilgili açık bir kelime var mı."""
    m = " ".join(" ".join(x) if isinstance(x, list) else (x or "") for x in metinler)
    return bool(_DIN_ISARET.search(m.replace("İ", "i").replace("I", "ı").lower()))


_SAPKA = {"a": "â", "i": "î", "ı": "î", "u": "û", "A": "Â", "I": "Î", "İ": "Î", "U": "Û"}


def baslik_temizle(t: str, sahip: str = "") -> str:
    """Kayıtlardaki bozuk yazılışları düzeltir: ünsüze kaymış şapka (F̂ar̂ab̂ı -> Fârâbî), başa eklenmiş yazar adı ve yıl
    ('Oktay A S 2008 ...', 'OKTAY Ayşe Sıdıka ...'), baştaki ve sondaki tırnaklar."""
    t = unicodedata.normalize("NFD", (t or "").replace("İ", "I\u0307"))
    t = re.sub(r"([b-df-hj-np-tv-zB-DF-HJ-NP-TV-Z][\u0300-\u036f]*)\u0302([aiıuAIU]?)\u0302?",
               lambda m: m.group(1) + (_SAPKA.get(m.group(2), m.group(2))), t)
    t = re.sub(r"(?<=[b-df-hj-np-tv-zB-DF-HJ-NP-TV-Z])\u0302", "", t)
    t = unicodedata.normalize("NFC", t).strip()
    t = re.sub(r"(['’])xx", r"\1", t)
    t = re.sub(r"(?<=\w)\s*[\"”]\s*,\s.*$", "", t)  # başlığın arkasına eklenmiş künye: '...Görüşleri", Son Dönem ...'

    if sahip:
        p_ = sahip.split()
        soy, adlar = re.escape(p_[-1]), r"\s+".join(re.escape(x) for x in p_[:-1])
        t = re.sub(rf"^(?i:{soy})[\s,]+(?:(?i:{adlar})|(?:[A-ZÇĞİÖŞÜ]\.?[\s,]+){{1,3}}|(?:[A-ZÇĞİÖŞÜ]\.){{1,3}}|[A-ZÇĞİÖŞÜ]{{1,3}}(?=[\s,.]))[\s,]*(?:(?:19|20)\d\d[\s,]+)?", "", t)
    return t.strip(" \"'“”‘’,").strip()


def baslik_anahtari(t: str) -> str:
    k = slugify(baslik_temizle(t)).replace("-", "")
    _KELIME.setdefault(k, kelimeler_(t))
    _CILTLER.setdefault(k, {w for w in slugify(baslik_temizle(t)).split("-") if _CILT.match(w)})
    return k


BAGLAC = {"and", "the", "for", "with", "from", "into", "ile", "icin", "bir", "veya", "olarak", "uzerine", "uzerinden",
          "acisindan", "baglaminda", "gore", "der", "die", "das", "und", "des"}


def kelimeler_(t: str) -> set:
    return {w for w in slugify(baslik_temizle(t)).split("-") if len(w) >= 3 and w not in BAGLAC}


_CILT = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|x|[1-9])$")
_CILTLER = {}


def cilt_no(anahtar: str) -> set:
    """Adın içindeki cilt numaraları (I, II, III ya da 1, 2, 3): 'Okumalar I' ile 'Okumalar II' ayrı eserlerdir."""
    return _CILTLER.get(anahtar, set())


def cilt_farkli(a: str, b: str) -> bool:
    """İki adda da cilt numarası var ve numaralar farklıysa ayrı eserdir; numarası olmayan kopya aynı eser sayılabilir."""
    ca, cb = cilt_no(a), cilt_no(b)
    return bool(ca and cb and ca != cb)


def yil_uzak(a, b) -> bool:
    """İki yıl arasında beşten fazla yıl varsa adları benzese de ayrı eserdir (ör. 2018'deki makale ile 2025'teki kitap)."""
    try:
        return abs(int(str(a)[:4]) - int(str(b)[:4])) > 5
    except (TypeError, ValueError):
        return False


def kelime_ortak(a: set, b_anahtar: str) -> bool:
    """Kelimelerin büyük çoğunluğu ortaksa aynı yayın sayılır (bildiri ve makale gibi aynı çalışmanın künyesi eklenmiş kopyaları)."""
    b = _KELIME.get(b_anahtar)
    if not b or len(a) < 5 or len(b) < 5 or min(len(a), len(b)) / max(len(a), len(b)) < 0.6:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.8


_KELIME = {}


def soyadlar(yazarlar) -> set:
    """Yazar listesindeki soyadları ('Soyad A.' ya da 'Ad Soyad' biçimleri)."""
    out = set()
    for a in yazarlar or []:
        a = re.sub(r"\(.*?\)", "", a).strip()
        p_ = ad_anahtari(a).split("-")
        if not p_ or not p_[0]:
            continue
        out.add(p_[0] if re.search(r"\b[A-ZÇĞİÖŞÜ]\.$", a) else p_[-1])
    return out


def baslik_esit(a: str, yil: str, kayitlar: list, yazarlar=None) -> bool:
    """Aynı yayın mı: adlar (harf dışı işaretler gözetilmeden) aynıysa; biri ötekinin içinde geçiyorsa (kayıtlarda
    başlığın arkasına künye eklenmiş olabiliyor, 25 harften uzun adlar için); ya da yıl aynı ve adlardan biri ötekinin
    alt başlıksız biçimiyse (ör. 'Kemâl Yolculuğu' ile 'Kemâl Yolculuğu: Gazâlî Düşüncesinde Dinî Tecrübe')."""
    k = baslik_anahtari(a)
    a = kelimeler_(a)
    soy = soyadlar(yazarlar) if yazarlar else set()
    for b, y, *ek in kayitlar:
        if k == b:
            # "Din Felsefesi" gibi kısa ve genel adlar farklı yıllarda ya da farklı yazarlarca yazılmış farklı eserlerdir
            if len(k) < 25 and ((yil and y and str(yil) != str(y)) or (soy and ek and ek[0] and not soy & ek[0])):
                continue
            return True
        kisa, uzun = sorted((k, b), key=len)
        if len(kisa) >= 20 and kisa in uzun:
            return True
        if kelime_ortak(a, b) and not yil_uzak(yil, y) and not cilt_farkli(k, b):
            return True
        if yil and str(y) == str(yil) and len(kisa) >= 12 and uzun.startswith(kisa):
            return True
    return False


_YOK_KUME = {}


def yok_kumesi(slug: str):
    """Kişinin YÖK Akademik listesi: (ad anahtarı, yıl) kayıtları ve kitap bölümleri için (kitap adı anahtarı, yıl).
    YÖK verisi yoksa None."""
    if slug not in _YOK_KUME:
        v = avesis_veri().get(slug) or {}
        if not v.get("yok_var"):
            _YOK_KUME[slug] = None
        else:
            ys = [y for y in v["yayinlar"] if y["kaynak"] == "yok"]
            _YOK_KUME[slug] = ([(baslik_anahtari(y["baslik"]), y["yil"]) for y in ys],
                               [(baslik_anahtari(y["baslik"]), y["yil"]) for y in ys if y["tur"] == "kitap-bolumu"])
    return _YOK_KUME[slug]


def bolum_esit(kitap_anahtari: str, yil: str, kunye: str, yil2: str) -> bool:
    """YÖK'teki kitap bölümü (adı yerine kitabın adı yazılır) başka bir kaynaktaki bölümle aynı mı: kitap adı öteki kaydın
    künyesinde geçiyor ve yıl tutuyor."""
    return len(kitap_anahtari) >= 8 and str(yil) == str(yil2) and kitap_anahtari in baslik_anahtari(kunye or "")


def yokta_mi(slug: str, baslik: str, yil: str, tur: str = "", kunye: str = ""):
    """Yayın kişinin YÖK listesinde var mı. YÖK verisi olmayan kişide None döner."""
    k = yok_kumesi(slug)
    if k is None:
        return None
    kayitlar, bolumler = k
    if baslik_esit(baslik, yil, kayitlar):
        return True
    return tur == "kitap-bolumu" and any(bolum_esit(b, y, kunye, yil) for b, y in bolumler)


def kayit_yokta(m: dict) -> bool:
    """Genel listelerdeki bir kayıt yazarlarından birinin YÖK listesinde var mı."""
    if m.get("kaynak") == "yok":
        return True
    for y in m["yazarlar"]:
        s_ = slugify(y)
        if s_ in akademi_verisi() and yokta_mi(s_, m["baslik"], m["yil"], DP_TUR_ESER.get(m["tur"], ""), m["dergi"]):
            return True
    return False


def kaynak_isareti(m: dict) -> str:
    """Genel listelerde kaynak işareti: yalnızca YÖK'te bulunmayan ve DergiPark taramasından gelmeyen kayıtlar işaretlenir."""
    if m.get("kaynak") not in ("orcid", "avesis", "kisisel") or kayit_yokta(m):
        return ""
    return {"orcid": ORCID_ISARET, "avesis": AVESIS_ISARET, "kisisel": KISISEL_ISARET}[m["kaynak"]]


def avesis_eserleri(onceki: list) -> list:
    """AVESİS'ten gelip elle bir başlığa bağlanan yayınlar; sitede zaten bulunanlar (DergiPark, ORCID, eser fişleri) alınmaz."""
    kayitlar = [(baslik_anahtari(m["baslik"]), m["yil"], soyadlar(m["yazarlar"])) for m in onceki] + \
        [(baslik_anahtari(h["baslik"]), str(h.get("yil") or "")) for (t, k), h in FIS.items() if t == "eser"]
    out, eklenen = [], {}
    for v in avesis_veri().values():
        for y in v["yayinlar"]:
            if not y["konular"]:
                continue
            onceki_ = eklenen.get((baslik_anahtari(y["baslik"]), y["yil"]))
            if onceki_ and soyadlar(onceki_["yazarlar"]) & soyadlar(y["yazarlar"]):  # aynı yayın ortak yazarın AVESİS listesinde de var: onun adı da tam yazılır
                if y["sahip"] not in onceki_["yazarlar"]:
                    soy = ad_anahtari(y["sahip"]).split("-")[-1]
                    i_ = next((i_ for i_, a in enumerate(onceki_["yazarlar"]) if ad_anahtari(a).split("-")[0] == soy), None)
                    if i_ is None:
                        onceki_["yazarlar"].append(y["sahip"])
                    else:
                        onceki_["yazarlar"][i_] = y["sahip"]
                continue
            if baslik_esit(y["baslik"], y["yil"], kayitlar, y["yazarlar"]):
                continue
            kayitlar.append((baslik_anahtari(y["baslik"]), y["yil"], soyadlar(y["yazarlar"])))
            tur = y["tur"] if y["tur"] in DP_TUR_ESER else ""  # makale ve "diğer yayınlar" makale sayılır
            tanitim = tur in ("kitap-tanitimi", "ceviri")
            out.append({"id": "avesis-" + y["kimlik"], "baslik": y["baslik"], "yazarlar": list(y["yazarlar"]), "dergi": y["kunye"],
                        "cilt_sayi": "", "yil": y["yil"], "tarih": y["yil"], "baglanti": y["baglanti"], "doi": y["doi"],
                        "konular": [] if tanitim else y["konular"], "ilgili": y["konular"] if tanitim else [], "tur": tur,
                        "kelimeler": y.get("kelimeler") or [], "kaynak": y["kaynak"]})
            eklenen[(baslik_anahtari(y["baslik"]), y["yil"])] = out[-1]
    return out


def dp_tarama_tarihi() -> str:
    try:
        p = json.loads((DP_DIZIN / "ilerleme.json").read_text(encoding="utf-8"))
        return max(v.get("tarandi", "") for v in p["pencereler"].values())
    except Exception:
        return ""


def akademisyen_dizini() -> dict:
    """Türkiye akademisi listesindeki adların eşleştirme anahtarı -> satır kimliği."""
    dosya = CONTENT / "turkiye_akademisi.yaml"
    if not dosya.exists():
        return {}
    kisiler = (yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}).get("kisiler") or []
    return {ad_anahtari(p["ad"]): "k-" + slugify(p["ad"]) for p in kisiler}


def dp_yazar_sayilari() -> dict:
    say = {}
    for m in dp_veri():
        for y in m["yazarlar"]:
            say[ad_anahtari(y)] = say.get(ad_anahtari(y), 0) + 1
    return say


def dp_kunye(m, yazar_bag=True) -> str:
    yazar = ", ".join(akademisyen_bag(y) if yazar_bag else e(y) for y in m["yazarlar"])
    dergi = e(m["dergi"]) + (f", {e(m['cilt_sayi'])}" if m["cilt_sayi"] else "")
    return yazar, dergi


def baslik_makaleleri(k) -> str:
    """Başlık sayfasındaki Türkçe makaleler bölümü: en yeni beş makale ve listenin tamamına bağlantı."""
    veri = dp_veri()
    hedef = soy(k)
    ms = [m for m in veri if set(m["konular"]) & hedef]
    tc = [m for m in veri if m["tur"] and set(m["ilgili"]) & hedef]
    if not ms and not tc:
        return ""

    def satir(m):
        yazar, dergi = dp_kunye(m)
        tur = f' <span class="m-tur">{e(DP_TUR_AD[m["tur"]])}</span>' if m["tur"] else ""
        tur += kaynak_isareti(m)
        return ("<li>" + eser_adi(m["baglanti"], m["baslik"], "") + f'{tur}'
                f'<span class="m-dergi">{yazar} · {dergi}, {e(m["yil"])}</span></li>')
    out = '<section class="tr-makaleler"><h2>Türkiye akademisinden çalışmalar</h2>'
    if ms:
        out += (f'<ul class="m-liste">{"".join(satir(m) for m in ms[:5])}</ul>'
                f'<p class="m-hepsi"><a href="{SITE_URL}/eserler/?konu={k}">Bu başlıktaki bütün eserler ({len(ms)} çalışma) →</a></p>')
    if tc:
        out += f'<h3>Kitap tanıtımları ve çeviriler</h3><ul class="m-liste">{"".join(satir(m) for m in tc)}</ul>'
    return out + '</section>'





# ---------------------------------------------------------------- akademisyen sayfaları

_AKADEMI = None


def akademi_url(slug: str) -> str:
    return f"{SITE_URL}/kisiler/akademi/{slug}/"


def akademi_verisi() -> dict:
    """Türkiye akademisi listesindeki her kişi için: liste kaydı, DergiPark makaleleri, başlık sayıları,
    ortak yazarlar ve makale başlığında adı geçen düşünür fişleri. Anahtar: kişinin adres kısaltması (slug)."""
    global _AKADEMI
    if _AKADEMI is not None:
        return _AKADEMI
    _AKADEMI = {}
    dosya = CONTENT / "turkiye_akademisi.yaml"
    if not dosya.exists():
        return _AKADEMI
    kisiler = (yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}).get("kisiler") or []
    orcid_dosya, eser_dosya = ROOT / "data/orcid/orcid.json", ROOT / "data/orcid/eserler.json"
    orcidler = json.loads(orcid_dosya.read_text(encoding="utf-8")).get("orcid", {}) if orcid_dosya.exists() else {}
    orcid_eser = json.loads(eser_dosya.read_text(encoding="utf-8")).get("eserler", {}) if eser_dosya.exists() else {}
    anahtar = {}
    for p in kisiler:
        slug = slugify(p["ad"])
        oid = p.get("orcid") or orcidler.get(slug, "")  # listeye elle yazılan ORCID önce gelir
        _AKADEMI[slug] = {"p": p, "orcid": oid,
                          "orcid_kaynak": "YÖK Akademik kaydından" if p.get("orcid") else "DergiPark makale sayfalarından",
                          "orcid_eser": orcid_eser.get(oid, []) if oid else [],
                          "makaleler": [], "dp_diger": [], "kitaplar": [], "baslik": {}, "ortak": {}, "dusunur": {}}
        anahtar[ad_anahtari(p["ad"])] = slug
    soyad_say = {}
    for (t, k), h in FIS.items():
        if t == "kisi":
            soyad_say[ad(t, h).split()[-1]] = soyad_say.get(ad(t, h).split()[-1], 0) + 1
    dusunur = []
    for (t, k), h in FIS.items():
        if t == "kisi" and h.get("kapsam", "uluslararasi") == "uluslararasi":
            adlar = [ad(t, h)] + ([ad(t, h).split()[-1]] if soyad_say[ad(t, h).split()[-1]] == 1 else [])
            dusunur.append((k, re.compile("|".join(f"(?<![{HARF}]){re.escape(a)}(?![{HARF}])" for a in adlar))))
    # sitede fişi bulunan eserleri (yazar alanında adı listedeki yazılışıyla geçenler)
    for (t, k), h in FIS.items():
        if t == "eser":
            for y in liste(h.get("yazar")):
                s_ = anahtar.get(ad_anahtari(str(y)))
                if s_ and ("kisi", y) not in FIS:
                    _AKADEMI[s_]["kitaplar"].append(k)
                    for b in liste(h.get("basliklar")):
                        if ("baslik", b) in FIS:
                            _AKADEMI[s_]["baslik"][b] = _AKADEMI[s_]["baslik"].get(b, 0) + 1
    veri = dp_veri()
    import dergipark_siniflandir as dps
    # yazarı doğrulanmış ama hiçbir başlığa girmeyen DergiPark makaleleri yalnızca kişinin sayfasında listelenir
    for r, x in akademisyen_dp():
        if x["durum"] != "konulu":
            m = dp_kaydi(r, {}, {}, dps)
            for ad_ in x["akademisyenler"]:
                if slugify(ad_) in _AKADEMI:
                    _AKADEMI[slugify(ad_)]["dp_diger"].append(m)
    # din felsefesi taramasında anahtar kelimesi bir başlığa uymayan, yazarı listede olan makaleler
    for m in _DP_LISTE_DIGER:
        for y in m["yazarlar"]:
            if ad_anahtari(y) in anahtar:
                _AKADEMI[anahtar[ad_anahtari(y)]]["dp_diger"].append(m)
    for m in veri:
        uyeler = list(dict.fromkeys(anahtar[ad_anahtari(y)] for y in m["yazarlar"] if ad_anahtari(y) in anahtar))
        for s in uyeler:
            v = _AKADEMI[s]
            v["makaleler"].append(m)
            for b in (m["konular"] or m["ilgili"]):
                if ("baslik", b) in FIS:
                    v["baslik"][b] = v["baslik"].get(b, 0) + 1
            for k, desen in dusunur:
                if desen.search(m["baslik"]):
                    v["dusunur"][k] = v["dusunur"].get(k, 0) + 1
            for o in uyeler:
                if o != s:
                    v["ortak"][o] = v["ortak"].get(o, 0) + 1
    return _AKADEMI


def akademisyen_bag(ad_: str) -> str:
    """Makale listelerindeki yazar adı: Türkiye akademisinde ise kişinin sayfasına bağlanır."""
    s = slugify(ad_)
    v = akademi_verisi().get(s)
    if v and ad_anahtari(v["p"]["ad"]) == ad_anahtari(ad_):
        return f'<a href="{akademi_url(s)}">{e(ad_)}</a>'
    return e(ad_)


def baslik_calisanlari(k) -> str:
    """Başlık sayfasındaki 'Türkiye'de bu konuda çalışanlar' bölümü (DergiPark makalelerine göre)."""
    hedef = soy(k)
    say = []
    for s, v in akademi_verisi().items():
        n = sum(1 for m in v["makaleler"] if set(m["konular"]) & hedef)
        if n:
            say.append((n, s, v))
    if not say:
        return ""
    say.sort(key=lambda x: (-x[0], tr_anahtar(x[2]["p"]["ad"])))
    def oge(n, s, v):
        return f'<li><a href="{akademi_url(s)}">{e(v["p"]["ad"])}</a> <span class="say">{n}</span></li>'
    ILK = 12  # ilk 12 kişi görünür, kalanlar "Diğer N kişi" açılır kutusundadır
    ust = "".join(oge(*x) for x in say[:ILK])
    devam = (f'<details class="calisan-devam"><summary>Diğer {len(say) - ILK} kişiyi göster</summary>'
             f'<ul class="calisan-liste">{"".join(oge(*x) for x in say[ILK:])}</ul></details>') if len(say) > ILK else ""
    return (f'<section class="calisanlar"><h2>Türkiye\'de bu konuda çalışanlar</h2>'
            f'<p class="aciklama-kisa">Türkiye akademisi listesindeki akademisyenler, bu başlığa giren çalışmalarının sayısıyla (DergiPark taraması, ORCID kaydındaki DOI\'li yayınlar, AVESİS ve YÖK Akademik sayfaları).</p>'
            f'<ul class="calisan-liste">{ust}</ul>{devam}</section>')


ORCID_TUR = {"journal-article": "Makale", "book": "Kitap", "book-chapter": "Kitap bölümü", "conference-paper": "Bildiri",
             "conference-abstract": "Bildiri özeti", "dissertation-thesis": "Tez", "edited-book": "Editörlü kitap",
             "translation": "Çeviri", "book-review": "Kitap tanıtımı", "encyclopedia-entry": "Ansiklopedi maddesi",
             "review": "Değerlendirme", "preprint": "Ön baskı", "other": "Diğer"}


def haric_mi(ad_: str, baslik: str) -> bool:
    """ORCID ya da AVESİS kaydına yanlışlıkla girmiş, kişiye ait olmayan eser mi (data/haric.yaml: kişi adı -> ad parçaları)."""
    global _HARIC
    if _HARIC is None:
        d = ROOT / "data/haric.yaml"
        _HARIC = (yaml.safe_load(d.read_text(encoding="utf-8")) or {}) if d.exists() else {}
    return any(baslik_anahtari(x) in baslik_anahtari(baslik) for x in _HARIC.get(ad_, []))


_HARIC = None


def diger_yayin_ogeleri(v) -> list:
    """Kişinin din felsefesi başlıklarına girmeyen yayınları: yazarı doğrulanmış öteki DergiPark makaleleri, ORCID kaydındaki
    ve AVESİS sayfasındaki eserler. Sitede zaten bulunanlar ve kaynaklar arasında tekrar edenler DOI ve adla ayıklanır."""
    doiler = {m["baglanti"].lower().removeprefix("https://doi.org/") for m in v["makaleler"] if m["doi"]}
    kayitlar = [(baslik_anahtari(m["baslik"]), m["yil"]) for m in v["makaleler"]] + \
        [(baslik_anahtari(FIS[("eser", k)]["baslik"]), str(FIS[("eser", k)].get("yil") or "")) for k in v["kitaplar"]]
    sahip = v["p"]["ad"]
    ogeler = []
    for m in sorted(v["dp_diger"], key=lambda m: m["tarih"], reverse=True):
        d = m["baglanti"].lower().removeprefix("https://doi.org/") if m["doi"] else ""
        if (d and d in doiler) or baslik_esit(m["baslik"], m["yil"], kayitlar):
            continue
        kayitlar.append((baslik_anahtari(m["baslik"]), m["yil"]))
        if d:
            doiler.add(d)
        dergi = e(m["dergi"]) + (f", {e(m['cilt_sayi'])}" if m["cilt_sayi"] else "")
        ogeler.append({"grup": "diger", "tur": "makale", "yil": m["yil"], "ad": m["baslik"], "kaynak": "dergipark", "kunye": m["dergi"],
                       "html": eser_adi(m["baglanti"], m["baslik"]) +
                               f'<span class="eser-bilgi">{dergi}, {e(m["yil"])}</span>'})
    # ORCID kayıtlarında künyesi eksiksiz olanlar önce gelsin (aynı eserin bozuk yazılmış kopyaları sonra ayıklanır)
    for w in sorted(v["orcid_eser"], key=lambda w: (bool(w["doi"]), bool(w["yil"]), w["yil"] or "0"), reverse=True):
        baslik = buyuk_duzelt(baslik_temizle(w["baslik"], sahip))
        if haric_mi(sahip, baslik):
            continue
        if (w["doi"] and w["doi"].lower() in doiler) or baslik_esit(baslik, w["yil"], kayitlar):
            continue
        kayitlar.append((baslik_anahtari(baslik), w["yil"]))
        hedef = f'https://doi.org/{w["doi"]}' if w["doi"] else w["url"]
        if hedef and "akademik.yok.gov.tr" in hedef:  # eski YÖK adresleri eserin kendisine götürmez; bağlantı verilmez
            hedef = ""
        bas = (f'<a class="eser-ad dis" href="{e(hedef)}" rel="noopener" target="_blank">{e(baslik)}</a>' if hedef
               else f'<span class="eser-ad">{e(baslik)}</span>')
        bilgi = ", ".join(x for x in [e(baslik_temizle(w["dergi"])), e(w["yil"])] if x)
        ogeler.append({"grup": "diger", "tur": ORCID_YAYIN_TUR.get(w["tur"], "diger"), "yil": w["yil"] or "", "ad": baslik,
                       "kaynak": "orcid", "kunye": w["dergi"], "html": f'{bas}<span class="eser-bilgi">{bilgi}</span>'})
    # AVESİS ve kişisel site kayıtları YÖK kayıtlarından önce gelir; aynı yayının YÖK kopyası ayıklanır
    ays = (avesis_veri().get(slugify(v["p"]["ad"])) or {}).get("yayinlar", [])
    for y in sorted(ays, key=lambda y: (y["kaynak"] != "yok", y["yil"] or "0"), reverse=True):
        if y["konular"] or baslik_esit(y["baslik"], y["yil"], kayitlar):
            continue
        if y["kaynak"] == "yok" and y["tur"] == "kitap-bolumu":
            kb = baslik_anahtari(y["baslik"])
            if any(o["tur"] == "kitap-bolumu" and bolum_esit(kb, y["yil"], o.get("kunye", ""), o["yil"]) for o in ogeler) or \
               any(bolum_esit(kb, y["yil"], m["dergi"], m["yil"]) for m in v["makaleler"]):
                continue
        kayitlar.append((baslik_anahtari(y["baslik"]), y["yil"]))
        bilgi = ", ".join(x for x in [e(y["kunye"]), e(y["yil"])] if x)
        ogeler.append({"grup": "diger", "tur": y["tur"] if y["tur"] in YAYIN_TUR_AD else "diger", "yil": y["yil"], "ad": y["baslik"],
                       "kaynak": y["kaynak"], "kunye": y["kunye"],
                       "html": eser_adi(y["baglanti"], y["baslik"]) +
                               f'<span class="eser-bilgi">{bilgi}</span>'})
    return ogeler


# Kişi sayfasındaki yayın listesinde tür etiketleri
YAYIN_TUR_AD = {"kitap": "Kitap", "kitap-bolumu": "Kitap bölümü", "makale": "Makale", "bildiri": "Bildiri", "tez": "Tez",
                "kitap-tanitimi": "Tanıtım", "ceviri": "Çeviri", "soylesi": "Söyleşi", "diger": "Diğer"}
YAYIN_TUR_SIRA = {k: i for i, k in enumerate(YAYIN_TUR_AD)}
ORCID_YAYIN_TUR = {"journal-article": "makale", "book": "kitap", "edited-book": "kitap", "book-chapter": "kitap-bolumu",
                   "conference-paper": "bildiri", "conference-abstract": "bildiri", "dissertation-thesis": "tez",
                   "translation": "ceviri", "book-review": "kitap-tanitimi", "review": "kitap-tanitimi"}
DP_YAYIN_TUR = {"": "makale", "kitap-tanitimi": "kitap-tanitimi", "ceviri": "ceviri", "ceviri-degerlendirmesi": "ceviri",
                "soylesi": "soylesi", "kitap": "kitap", "kitap-bolumu": "kitap-bolumu", "bildiri": "bildiri", "tez": "tez"}


KAYNAK_SIRA = {"yok": 0, "avesis": 1, "kisisel": 2, "orcid": 3, "dergipark": 4, "fis": 5}
KAYNAK_AD = {"avesis": "AVESİS", "kisisel": "Kişisel site", "orcid": "ORCID", "dergipark": "DergiPark"}


def yok_tarihi() -> str:
    d = ROOT / "data/yok/bilgi.yaml"
    return str((yaml.safe_load(d.read_text(encoding="utf-8")) or {}).get("tarih") or "") if d.exists() else ""


def kisi_tezleri(slug: str) -> list:
    """Kişinin danışmanlığındaki tezler (data/tez/tezler.json). Dosya yoksa ya da kişide tez yoksa boş liste."""
    if not TEZ_DOSYA.exists():
        return []
    global _TEZ_ONBELLEK
    if _TEZ_ONBELLEK is None:
        _TEZ_ONBELLEK = json.loads(TEZ_DOSYA.read_text(encoding="utf-8"))
    return [t for t in _TEZ_ONBELLEK if any(slugify(h) == slug for h in t["danisman"])]


_TEZ_ONBELLEK = None


def tez_satiri(t: dict, gizli: bool = True) -> str:
    parcalar = t["yer"].split(" / ")
    yer = tez_tr_baslik(parcalar[0]) + (", " + tez_tr_baslik(parcalar[2]) if len(parcalar) > 2 else "")
    return (f'<li data-grup="tez" data-yil="{e(t["yil"])}" data-ad="{e(tr_kucuk(t["ad"]))}" data-tur="98" data-kaynak="9"{" hidden" if gizli else ""}>'
            f'<span class="yt yt-tez">Tez</span><span class="eser-ad">{e(t["ad"])}</span>{tez_rozetleri(t)}'
            f'<span class="eser-bilgi">{e(t["yil"])} · {e(yer)}</span></li>')


def yayin_paneli(ogeler, slug: str = "", tezler=None, kisi_ad: str = "") -> str:
    """Kişi sayfasındaki yayın listesi: sekmeler (din felsefesi / diğer / tümü), sıralama, numara ve tür etiketi.
    Liste kişinin YÖK Akademik kaydına dayanır: YÖK'tekiler önce gelir, YÖK'te olmayanlar geldikleri kaynakla işaretlenir."""
    tezler = tezler or []
    if not ogeler and not tezler:
        return ""
    yok_var = yok_kumesi(slug) is not None if slug else False
    for o in ogeler:
        if yok_var and yokta_mi(slug, o["ad"], o["yil"], o["tur"], o.get("kunye", "")):
            o["kaynak"] = "yok"
        k = o.get("kaynak", "fis")
        o["sira"] = KAYNAK_SIRA.get(k, 5)
        if k in KAYNAK_AD and yok_var:
            isaret = f' <span class="m-kaynak" title="YÖK Akademik kaydında yok; kaynak: {KAYNAK_AD[k]}">{KAYNAK_AD[k]}</span>'
            o["html"] = o["html"].replace('<span class="eser-bilgi">', isaret + '<span class="eser-bilgi">', 1)
    say = {"df": sum(1 for o in ogeler if o["grup"] == "df"), "diger": sum(1 for o in ogeler if o["grup"] == "diger")}
    ilk = "df" if say["df"] else ("tumu" if ogeler else "tez")
    sekmeler = "".join(f'<button type="button" data-grup="{k}" aria-pressed="{"true" if k == ilk else "false"}">{a} <span class="say">{n}</span></button>'
                       for k, a, n in [("df", "Din felsefesi", say["df"]), ("diger", "Diğer", say["diger"]), ("tumu", "Tümü", len(ogeler)),
                                       ("tez", "Tezler", len(tezler))] if n)
    ilk_alan = "kaynak" if yok_var else "yil"
    alanlar = ([("kaynak", "Kaynak")] if yok_var else []) + [("yil", "Yıl"), ("ad", "Ad"), ("tur", "Tür")]
    siralama = ('<div class="yp-sirala" role="group" aria-label="Sıralama"><span>Sırala</span>'
                + "".join(f'<button type="button" data-alan="{k}" aria-pressed="{"true" if k == ilk_alan else "false"}">{a}<span class="ok" aria-hidden="true">{"↓" if k == "yil" == ilk_alan else ""}</span></button>'
                          for k, a in alanlar) + '</div>')
    ogeler = sorted(ogeler, key=lambda o: (o["yil"] or "0"), reverse=True)
    if yok_var:
        ogeler = sorted(ogeler, key=lambda o: o["sira"])
    satirlar = "".join(
        f'<li data-grup="{o["grup"]}" data-yil="{e(o["yil"])}" data-ad="{e(tr_kucuk(o["ad"]))}" data-tur="{YAYIN_TUR_SIRA.get(o["tur"], 99)}" data-kaynak="{o["sira"]}"'
        f'{" hidden" if o["grup"] != ilk and not (ilk == "tumu") else ""}>'
        f'<span class="yt yt-{o["tur"]}">{YAYIN_TUR_AD.get(o["tur"], "Diğer")}</span>{o["html"]}</li>'
        for o in ogeler)
    satirlar += "".join(tez_satiri(t, ilk != "tez") for t in sorted(tezler, key=lambda t: (t["yil"], t["ad"]), reverse=True))
    notlar = ('<p class="aciklama-kisa yp-not" data-not="df">Konusu anahtar kelimelerine ya da adına göre din felsefesi başlıklarına bağlanan yayınlar.</p>'
              '<p class="aciklama-kisa yp-not" data-not="diger" hidden>DergiPark\'taki öteki makaleler, ORCID kaydındaki ve AVESİS ya da YÖK Akademik sayfasındaki yayınlar. '
              'Bunlar din felsefesi başlıklarına bağlanmamıştır.</p>')
    if tezler:
        notlar += (f'<p class="aciklama-kisa yp-not" data-not="tez"{"" if ilk == "tez" else " hidden"}>Hocanın danışmanlığını yaptığı ya da yürüttüğü yüksek lisans ve doktora tezleri '
                   f'(YÖK Ulusal Tez Merkezi). Öğrenci adları yazılmaz, bu tezler hocanın kendi yayını sayılmaz. '
                   f'<a href="{SITE_URL}/tezler/?ara={quote(kisi_ad)}">Tezler sayfasında bu danışmanla ara</a></p>')
    if yok_var:
        disarida = sum(1 for o in ogeler if o["sira"] > 0)
        notlar = (f'<p class="aciklama-kisa yp-kaynak-not">Liste hocanın YÖK Akademik kaydına dayanır (YÖK taraması {tr_date(yok_tarihi())}). '
                  + (f'YÖK\'te bulunmayan {disarida} yayın listenin sonunda, geldiği kaynağın adıyla işaretlenmiştir. ' if disarida else '')
                  + 'Yayının kendisine ya da kendi sayfasına ulaşılabildiğinde adı bağlantılıdır.</p>' + notlar)
    baslik = (f'<h2 data-yayin="1"{" hidden" if ilk == "tez" else ""}>Yayınları <span class="say">{len(ogeler)}</span></h2>'
              + (f'<h2 data-tez="1"{"" if ilk == "tez" else " hidden"}>Danışmanlığındaki tezler <span class="say">{len(tezler)}</span></h2>' if tezler else ""))
    return (f'<section class="yayin-panel"><div class="yp-bas">{baslik}{siralama}</div>'
            f'<div class="tur-secici yp-sekme" role="group" aria-label="Yayın grubu">{sekmeler}</div>{notlar}'
            f'<ol class="yayin-liste">{satirlar}</ol></section>' + YAYIN_JS)


YAYIN_JS = """<script>
(function(){var p=document.querySelector('.yayin-panel');if(!p)return;var ol=p.querySelector('.yayin-liste');
var lis=[].slice.call(ol.children);var ilkb=p.querySelector('.yp-sirala button[aria-pressed="true"]');
var alan=ilkb?ilkb.dataset.alan:'yil',yon=(alan==='yil')?-1:1;
function grup(g){p.querySelectorAll('.yp-sekme button').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.grup===g)});
lis.forEach(function(li){li.hidden=g==='tumu'?li.dataset.grup==='tez':li.dataset.grup!==g});
p.querySelectorAll('.yp-not').forEach(function(n){n.hidden=(g==='tumu'||n.dataset.not!==g)});
var tz=g==='tez';p.querySelectorAll('h2[data-yayin]').forEach(function(h){h.hidden=tz});p.querySelectorAll('h2[data-tez]').forEach(function(h){h.hidden=!tz});
p.querySelectorAll('.yp-sirala button').forEach(function(b){if(b.dataset.alan==='kaynak'||b.dataset.alan==='tur')b.hidden=tz});
if(tz&&(alan==='kaynak'||alan==='tur')){alan='';sirala('yil')}}
function ad(x,y){return x.dataset.ad.localeCompare(y.dataset.ad,'tr')}
function yil(x,y){return (x.dataset.yil||'0').localeCompare(y.dataset.yil||'0')}
function sirala(a){
  /* aynı düğmeye yeniden basılınca yön değişir; yıl önce yeniden eskiye, ad ve tür önce artan */
  if(a===alan){yon=-yon}else{alan=a;yon=(a==='yil')?-1:1}
  p.querySelectorAll('.yp-sirala button').forEach(function(b){var on=b.dataset.alan===a;b.setAttribute('aria-pressed',on);
    b.querySelector('.ok').textContent=on?(yon>0?'↑':'↓'):''});
  lis.sort(function(x,y){var r;
    if(a==='yil')r=yon*yil(x,y)||ad(x,y);
    else if(a==='kaynak')r=yon*((+x.dataset.kaynak)-(+y.dataset.kaynak))||-yil(x,y)||ad(x,y);
    else if(a==='tur')r=yon*((+x.dataset.tur)-(+y.dataset.tur))||-yil(x,y)||ad(x,y);
    else r=yon*ad(x,y);
    return r});
  lis.forEach(function(li){ol.appendChild(li)})}
p.querySelectorAll('.yp-sekme button').forEach(function(b){b.addEventListener('click',function(){grup(b.dataset.grup)})});
function boy(){if(window.innerWidth<=760){p.classList.remove('boylu');p.style.height='';return}
  p.classList.add('boylu');var ust=p.getBoundingClientRect().top+window.scrollY;
  p.style.height=Math.max(320,window.innerHeight-ust-16)+'px';ol.scrollTop=0}
boy();window.addEventListener('resize',boy);
p.querySelectorAll('.yp-sirala button').forEach(function(b){b.addEventListener('click',function(){sirala(b.dataset.alan)})});
})();
</script>"""


def bas_harfler(ad_: str) -> str:
    parca = [x for x in ad_.split() if x]
    harf = lambda w: {"i": "İ", "ı": "I"}.get(w[0], w[0].upper())
    return (harf(parca[0]) + (harf(parca[-1]) if len(parca) > 1 else "")) if parca else ""


def render_akademisyen(s: str) -> str:
    v = akademi_verisi()[s]
    p = v["p"]
    emekli = ' <span class="emekli">Emekli</span>' if p.get("durum") == "emekli" else ""
    kurum = " · ".join(e(x) for x in [p.get("unvan"), p.get("universite"), p.get("fakulte")] if x)
    baglar = []
    if p.get("yok"):
        baglar.append(f'<a class="dis" href="{YOK_PROFIL}{e(p["yok"])}" rel="noopener" target="_blank">YÖK Akademik profili ↗</a>')
    if v["orcid"]:
        baglar.append(f'<a class="dis" href="https://orcid.org/{e(v["orcid"])}" rel="noopener" target="_blank">ORCID {e(v["orcid"])} ↗</a>')
    ana = [(b, n) for b, n in v["baslik"].items() if not FIS[("baslik", b)].get("ust_baslik")]
    alt = [(b, n) for b, n in v["baslik"].items() if FIS[("baslik", b)].get("ust_baslik")]
    sira = lambda x: (-x[1], FIS[("baslik", x[0])].get("sira", 99))
    konular = "".join(f'<li><a href="{fis_url("baslik", b)}">{e(FIS[("baslik", b)]["ad"])}</a> <span class="say">{n}</span></li>'
                      for b, n in sorted(ana, key=sira) + sorted(alt, key=sira))
    ogeler = []
    for k in v["kitaplar"]:
        h = FIS[("eser", k)]
        # kişi sayfasında eser fişine değil, varsa eserin kendi adresine (DOI, yayınevi, açık erişim) gidilir
        hedef = eser_baglantisi(h)
        ad_html = (f'<a class="eser-ad dis" href="{e(hedef)}" rel="noopener" target="_blank">{e(h["baslik"])}</a>' if hedef
                   else f'<span class="eser-ad">{e(h["baslik"])}</span>')
        ogeler.append({"grup": "df", "tur": h.get("eser_turu", "kitap"), "yil": str(h.get("yil") or ""), "ad": h["baslik"],
                       "kaynak": "fis", "kunye": str(h.get("yayin") or ""),
                       "html": ad_html + f'<span class="eser-bilgi">{e(h.get("yayin") or h.get("yil") or "")}</span>'})
    for m in v["makaleler"]:
        yazar = ", ".join(akademisyen_bag(y) if slugify(y) != s else e(y) for y in m["yazarlar"])
        dergi = e(m["dergi"]) + (f", {e(m['cilt_sayi'])}" if m["cilt_sayi"] else "")
        konu = ", ".join(bag("baslik", b) for b in (m["konular"] or m["ilgili"]) if ("baslik", b) in FIS and not FIS[("baslik", b)].get("ust_baslik"))
        ogeler.append({"grup": "df", "tur": DP_YAYIN_TUR.get(m["tur"], "makale"), "yil": m["yil"], "ad": m["baslik"],
                       "kaynak": {None: "dergipark", "dergipark-akademisyen": "dergipark"}.get(m.get("kaynak"), m.get("kaynak")),
                       "kunye": m["dergi"],
                       "html": eser_adi(m["baglanti"], m["baslik"]) +
                               f'<span class="eser-bilgi">{yazar} · {dergi}, {e(m["yil"])}'
                               + (f'<span class="eser-konu"> · {konu}</span>' if konu else "") + '</span>'})
    ogeler += diger_yayin_ogeleri(v)
    yan = []
    if konular:
        yan.append(f'<h2>Çalıştığı başlıklar</h2><ul class="calisan-liste">{konular}</ul>')
    if v["dusunur"]:
        yan.append('<h2>Makalelerinde adı geçen düşünürler</h2><ul>' +
                   "".join(f'<li>{bag("kisi", k)}</li>' for k in sorted(v["dusunur"], key=lambda k: tr_anahtar(ad("kisi", FIS[("kisi", k)])))) + '</ul>')
    if v["ortak"]:
        yan.append('<h2>Ortak yazarları</h2><ul>' +
                   "".join(f'<li><a href="{akademi_url(o)}">{e(akademi_verisi()[o]["p"]["ad"])}</a></li>'
                           for o in sorted(v["ortak"], key=lambda o: tr_anahtar(akademi_verisi()[o]["p"]["ad"]))) + '</ul>')
    if v["makaleler"] or v["kitaplar"]:
        kid = ag_kisi_kimligi(p)
        yan.append(f'<a class="ag-git" href="{ag_adresi(*kid.split("/", 1))}">Bu kişinin ağı →</a>')
    tarih = dp_tarama_tarihi()
    metin = yayin_paneli(ogeler, s, kisi_tezleri(s), p.get("ad") or v.get("ad") or "") or '<p class="giris">DergiPark taramasında, ORCID kaydında, AVESİS\'te ve YÖK Akademik\'te bu kişiye bağlanabilen bir yayın bulunamadı.</p>'
    # Listeye elle eklenen kişilerde kısa tanıtım ve hakkında yazılanlar listeden gelir (yalnızca kamuya açık bilgiler)
    tanitim = "".join(f"<p>{satir_ici(x.strip())}</p>" for x in (p.get("tanitim") or "").split("\n\n") if x.strip())
    tanitim = f'<div class="akademi-tanitim">{tanitim}</div>' if tanitim else ""
    hakkinda = "".join(f'<li>{satir_ici(x["kunye"])}' + (f' <a class="dis" href="{e(x["baglanti"])}" rel="noopener" target="_blank">↗</a>'
                                                           if x.get("baglanti") else "") + "</li>" for x in p.get("hakkinda") or [])
    hakkinda = f'<section class="akademi-hakkinda"><h2>Hakkında yazılanlar</h2><ul>{hakkinda}</ul></section>' if hakkinda else ""
    body = f"""
<p class="yol"><a href="{SITE_URL}/kisiler/">Kişiler</a> <span aria-hidden="true">›</span> Türkiye akademisi</p>
<section class="kartvizit" aria-label="Künye">
  <div class="kv-monogram" aria-hidden="true">{e(bas_harfler(p["ad"]))}</div>
  <div class="kv-govde">
    <p class="kv-unvan">{e(p.get("unvan") or "")}{emekli}</p>
    <h1>{e(p["ad"])}</h1>
    <p class="kv-kurum">{"<br>".join(e(x) for x in [p.get("universite"), p.get("fakulte")] if x)}</p>
    {f'<p class="kv-bag">{"".join(f"<span>{b}</span>" for b in baglar)}</p>' if baglar else ''}
  </div>
  <img class="kv-logo" src="{SITE_URL}/static/img/logo.svg" alt="" width="34" height="34">
</section>
<div class="fis-duzen">
  <div class="metin akademi-metin">{tanitim}{metin}{hakkinda}
  </div>
  <aside class="yan">{"".join(yan)}</aside>
</div>
<p class="aciklama-kisa akademi-not">{"Listeye elle eklenmiştir. " + ("Tanıtım, unvan" if p.get("tanitim") else "Unvan") + " ve kurum bilgisi " + e(p.get("kurum_kaynagi") or "kamuya açık kaynaklara") + " göre, makaleler ve başlıklar" if p.get("elle") else "Unvan ve kurum bilgisi YÖK Akademik kaydına, makaleler ve başlıklar"} DergiPark taramasına{" (" + tr_date(tarih) + ")" if tarih else ""}, ORCID kaydındaki DOI'li yayınlara ve AVESİS ya da YÖK Akademik sayfasına göredir. Çalışmaların konuları anahtar kelimelerine göre atanmıştır; AVESİS ve YÖK'ten gelen yayınlardan anahtar kelimesine ulaşılamayanlarınki adlarına bakılarak elle verilmiştir.{" ORCID numarası " + v["orcid_kaynak"] + " alınmıştır." if v["orcid"] and not p.get("elle") else ""} Düzeltme için: <a href="mailto:{ILETISIM}">{ILETISIM}</a></p>"""
    desc = f'{p["ad"]}, {p.get("unvan", "")}, {p.get("universite", "")}. Din felsefesi alanındaki makaleleri ve çalıştığı konular.'
    kisi = {"@type": "Person", "name": p["ad"], "url": akademi_url(s)}
    if p.get("unvan"):
        kisi["honorificPrefix"] = p["unvan"]
    if p.get("universite"):
        kisi["affiliation"] = {"@type": "CollegeOrUniversity", "name": p["universite"]}
    ayni = ([f"{YOK_PROFIL}{p['yok']}"] if p.get("yok") else []) + ([f"https://orcid.org/{v['orcid']}"] if v["orcid"] else [])
    if ayni:
        kisi["sameAs"] = ayni
    konular = [FIS[("baslik", b)]["ad"] for b in v["baslik"] if not FIS[("baslik", b)].get("ust_baslik")]
    if konular:
        kisi["knowsAbout"] = konular
    jl = {"@type": "ProfilePage", "url": akademi_url(s), "inLanguage": "tr", "mainEntity": kisi}
    # Akademisyen sayfaları arama motorlarına kapalıdır: genel aramalarda sitenin yerine tek tek kişilerin sayfaları
    # çıkmasın, yaşayan kişiler hakkında otomatik derlenmiş sayfalar aramalarda öne geçmesin. Sayfalar site içinde açıktır.
    return page(f'{p["ad"]} · {SITE_NAME}', body, "kisiler", desc=desc, canonical=akademi_url(s), jsonld=jl, dizinleme=AKADEMI_ACIK)


# ---------------------------------------------------------------- ilişki ağı

AG_TURLER = [("baslik", "Başlık", "#23446e"), ("terim", "Terim", "#c9a14a"), ("kisi", "Kişi", "#3f6b4f"),
             ("eser", "Eser", "#7a4a6b"), ("makale", "Makale tanıtımı", "#7b8794")]


def kisa_aciklama(t, h) -> str:
    metin = h.get("kisa_tanim") or h.get("ozet") or h.get("kisa_tanitim") or ""
    if t == "eser":
        yazar = ", ".join(ad("kisi", FIS[("kisi", y)]) if ("kisi", y) in FIS else str(y) for y in liste(h.get("yazar")))
        metin = " · ".join(x for x in [yazar, str(h.get("yil") or ""), str(h.get("yayin") or "")] if x)
    return re.sub(r"[*_`]", "", re.sub(r"\s+", " ", str(metin))).strip()


def ag_verisi(items) -> dict:
    dugumler, baglar = [], set()
    tur_ad = {k: a for k, a, _ in AG_TURLER}
    for (t, k), h in FIS.items():
        dugumler.append({"id": f"{t}/{k}", "ad": ad(t, h), "tur": t, "turAd": tur_ad[t],
                         "url": fis_url(t, k), "aciklama": kisa_aciklama(t, h)})
        for alan, hedef in ALAN_TUR.items():
            for d in liste(h.get(alan)):
                if (hedef, d) in FIS and (hedef, d) != (t, k):
                    baglar.add(tuple(sorted([f"{t}/{k}", f"{hedef}/{d}"])))
    # Makale tanıtımları: etiketi bir fişin adıyla (kişilerde soyadıyla) aynı olanlara bağlanır
    adlar = {}
    for (t, k), h in FIS.items():
        adlar.setdefault(tr_kucuk(ad(t, h)), set()).add(f"{t}/{k}")
        if t == "kisi":
            adlar.setdefault(tr_kucuk(ad(t, h).split()[-1]), set()).add(f"{t}/{k}")
    for m in items:
        hedefler = {x for etk in m.get("tags", []) for x in adlar.get(tr_kucuk(etk), set())}
        if not hedefler:
            continue
        mid = f"makale/{m['slug']}"
        # makale tanıtımları ağda eser olarak sayılır (süzgeçte ayrı bir düğme açmaz)
        dugumler.append({"id": mid, "ad": m["title_tr"], "tur": "eser", "turAd": tur_ad["makale"], "tanitim": True,
                         "url": entry_url(m), "aciklama": m.get("lead", "")})
        baglar |= {(mid, x) for x in hedefler}
    for d in dugumler:
        if d["tur"] == "kisi":
            d["suz"] = "kisi"
    tr_dugum, tr_bag = ag_turkiye_akademisi()
    # fişi olan Türkiye akademisi üyeleri tek düğümde birleşir (fişin bağlantısı ve makale listesi birlikte)
    var = {d["id"]: d for d in dugumler}
    for d in tr_dugum:
        if d["id"] in var:
            var[d["id"]].update({k: v for k, v in d.items() if k in ("makaleler", "tumu")})
        else:
            dugumler.append(d)
    return {"turler": [{"kod": k, "ad": a, "renk": r} for k, a, r in AG_TURLER],
            "dugumler": dugumler, "baglar": [list(b) for b in sorted(baglar)] + tr_bag}


def ag_kisi_kimligi(p) -> str:
    """Listedeki kişinin ağdaki düğüm kimliği: kişi fişi varsa fişin düğümü, yoksa akademisyen düğümü."""
    if p.get("kimlik") and ("kisi", p["kimlik"]) in FIS:
        return f"kisi/{p['kimlik']}"
    return f"kisi-tr/{slugify(p['ad'])}"


def ag_turkiye_akademisi() -> tuple[list, list]:
    """DergiPark'taki Türkçe makaleler eser düğümü olarak ağa girer. Her makale konu başlıklarına,
    Türkiye akademisi listesindeki yazarlarına ve başlığında adı geçen düşünür fişlerine bağlanır."""
    dosya = CONTENT / "turkiye_akademisi.yaml"
    if not dosya.exists() or not dp_veri():
        return [], []
    kisiler = (yaml.safe_load(dosya.read_text(encoding="utf-8")) or {}).get("kisiler") or []
    liste_ = {ad_anahtari(p["ad"]): p for p in kisiler}
    # makale başlığında aranacak düşünür adları (tam ad ya da başka fişte bulunmayan soyadı)
    soyad_say = {}
    for (t, k), h in FIS.items():
        if t == "kisi":
            soyad_say[ad(t, h).split()[-1]] = soyad_say.get(ad(t, h).split()[-1], 0) + 1
    dusunur = []
    for (t, k), h in FIS.items():
        if t == "kisi" and h.get("kapsam", "uluslararasi") == "uluslararasi":
            adlar = [ad(t, h)] + ([ad(t, h).split()[-1]] if soyad_say[ad(t, h).split()[-1]] == 1 else [])
            desen = re.compile("|".join(f"(?<![{HARF}]){re.escape(a)}(?![{HARF}])" for a in adlar))
            dusunur.append((f"kisi/{k}", desen))
    # terim fişleri: adı makalenin anahtar kelimelerinde ya da başlığında (ekleriyle) geçerse bağlanır
    terimler = [(f"terim/{k}", re.compile(f"(?<![{HARF}]){re.escape(tr_kucuk(ad(t, h)))}[{HARF}]*(?![{HARF}])"))
                for (t, k), h in FIS.items() if t == "terim"]
    makaleler, dp_dugum, baglar, dolayli = {}, [], [], {}
    for m in dp_veri():
        mid = f"dp/{m['id']}"
        uyeler = [ad_anahtari(y) for y in m["yazarlar"] if ad_anahtari(y) in liste_]
        kenar = [f"baslik/{b}" for b in (m["konular"] or m["ilgili"]) if ("baslik", b) in FIS]
        kenar += [ag_kisi_kimligi(liste_[a]) for a in uyeler]
        kenar += [did for did, desen in dusunur if desen.search(m["baslik"])]
        metin = tr_kucuk(m["baslik"] + " | " + " | ".join(m["kelimeler"]))
        kenar += [tid for tid, desen in terimler if desen.search(metin)]
        for a in uyeler:
            makaleler.setdefault(a, []).append(m)
            # makaleler gizlendiğinde kişinin hangi başlık ve terimlerle çalıştığı dolaylı bağlarla görünür
            for x in dict.fromkeys(kenar):
                if x.startswith(("baslik/", "terim/")):
                    anahtar = (ag_kisi_kimligi(liste_[a]), x)
                    dolayli[anahtar] = dolayli.get(anahtar, 0) + 1
        if not kenar:
            continue
        tur = DP_TUR_ESER[m["tur"]]
        dp_dugum.append({"id": mid, "ad": m["baslik"], "tur": "eser", "turAd": DP_TUR_AD.get(m["tur"], "Makale") + ({"orcid": " (ORCID)", "avesis": " (AVESİS)", "kisisel": " (kişisel site)"}.get(m.get("kaynak"), "") if kaynak_isareti(m) else ""),
                         "url": m["baglanti"], "dis": True, "kucuk": True,
                         "aciklama": " · ".join(x for x in [", ".join(m["yazarlar"]), m["dergi"], m["yil"]] if x)})
        baglar += [[mid, x] for x in dict.fromkeys(kenar)]
    # fişi olan kitaplar: yazar alanında listedeki bir kişinin adı geçiyorsa kişiye bağlanır
    for (t, k), h in FIS.items():
        if t != "eser":
            continue
        for y in liste(h.get("yazar")):
            a = ad_anahtari(str(y))
            if a in liste_ and ("kisi", y) not in FIS:
                kid = ag_kisi_kimligi(liste_[a])
                makaleler.setdefault(a, [])
                baglar.append([f"eser/{k}", kid])
                for b in liste(h.get("basliklar")):
                    if ("baslik", b) in FIS:
                        dolayli[(kid, f"baslik/{b}")] = dolayli.get((kid, f"baslik/{b}"), 0) + 1
    dugumler = []
    for a, ms in makaleler.items():
        p = liste_[a]
        aciklama = " · ".join(x for x in [p.get("unvan", ""), p.get("universite", "")] if x)
        dugumler.append({
            "id": ag_kisi_kimligi(p), "ad": p["ad"], "tur": "kisi", "turAd": "Kişi",
            "suz": "kisi-tr", "url": akademi_url(slugify(p['ad'])), "aciklama": aciklama,
            "tumu": f"{SITE_URL}/eserler/?ara={quote(tr_kucuk(p['ad']))}",
            "makaleler": [{"b": m["baslik"], "y": m["yil"], "u": m["baglanti"]} for m in ms]})
    baglar += [[a, b, n, "d"] for (a, b), n in dolayli.items()]
    return dugumler + dp_dugum, baglar


def kisalt_metin(t: str, n: int = 230) -> str:
    t = re.sub(r"[*_`#]", "", re.sub(r"\s+", " ", t or "")).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def onizleme_verisi(items) -> dict:
    from urllib.parse import urlparse
    v = {}
    for (t, k), h in FIS.items():
        if t == "eser":
            alt, metin = kisa_aciklama(t, h), ilk_paragraf(h.get("_govde"))
        elif t == "terim":
            alt, metin = h.get("ingilizce", ""), h.get("kisa_tanim", "")
        elif t == "kisi":
            alt, metin = str(h.get("donem") or ""), h.get("kisa_tanitim", "")
        else:
            alt, metin = "", h.get("ozet", "")
        v[urlparse(fis_url(t, k)).path] = {"t": TUR_AD[t], "ad": ad(t, h), "alt": str(alt), "a": kisalt_metin(metin)}
    for m in items:
        v[urlparse(entry_url(m)).path] = {"t": "Makale tanıtımı", "ad": m["title_tr"],
                                          "alt": f'{m.get("authors", "")} · {m.get("journal", "")}', "a": kisalt_metin(m.get("lead", ""))}
    for s_, d in akademi_verisi().items():
        p = d["p"]
        konular = [FIS[("baslik", b)]["ad"] for b, _ in sorted(d["baslik"].items(), key=lambda x: -x[1])
                   if not FIS[("baslik", b)].get("ust_baslik")][:4]
        metin = (f'{len(d["makaleler"])} makale. Çalıştığı başlıklar: {", ".join(konular)}.' if d["makaleler"] and konular
                 else f'{len(d["makaleler"])} makale.' if d["makaleler"] else "")
        v[urlparse(akademi_url(s_)).path] = {"t": "Türkiye akademisi", "ad": p["ad"],
                                             "alt": " · ".join(x for x in [p.get("unvan", ""), p.get("universite", "")] if x), "a": metin}
    return v


_AG = None


def ag_tam(items) -> dict:
    global _AG
    if _AG is None:
        _AG = ag_verisi(items)
    return _AG


def ag_alt_veri(v: dict, k: str, tur_: str = "baslik") -> dict:
    """Bir başlığın ya da terimin ağı: kendisi (başlıkta alt başlıklarıyla), ona doğrudan bağlı fişler ve eserler
    (makaleler dahil), bu eserleri yazan Türkiye akademisyenleri. Komşu başlıklar kenarda görünür, onlardan öteye geçilmez."""
    merkez = {f"{tur_}/{k}"}
    bekleyen = [k] if tur_ == "baslik" else []
    while bekleyen:
        for a in liste(FIS[("baslik", bekleyen.pop())].get("alt_basliklar")):
            if ("baslik", a) in FIS and f"baslik/{a}" not in merkez:
                merkez.add(f"baslik/{a}")
                bekleyen.append(a)
    komsu = {}
    for b in v["baglar"]:
        if len(b) > 3:  # dolaylı bağlar seçimde kullanılmaz
            continue
        komsu.setdefault(b[0], set()).add(b[1])
        komsu.setdefault(b[1], set()).add(b[0])
    tur = {d["id"]: d for d in v["dugumler"]}
    secili = set(merkez)
    for m in merkez:
        secili |= komsu.get(m, set())
    # eserlerin yazarları (Türkiye akademisi) ve fişi olan düşünürler de ağa girer; kişi ağında eserlerin
    # bağlı olduğu başlık, terim ve ortak yazarlar da alınır (kişinin çalışma haritası)
    for x in list(secili):
        if tur.get(x, {}).get("tur") == "eser":
            secili |= {y for y in komsu.get(x, set()) if tur_ in ("kisi", "kisi-tr") or tur.get(y, {}).get("tur") == "kisi"}
    dugumler = [dict(tur[x], merkez=True) if x in merkez else tur[x] for x in secili if x in tur]
    baglar = [b for b in v["baglar"] if b[0] in secili and b[1] in secili
              and not (b[0] not in merkez and b[1] not in merkez and tur.get(b[0], {}).get("tur") == "baslik"
                       and tur.get(b[1], {}).get("tur") == "baslik")]
    return {"turler": v["turler"], "dugumler": dugumler, "baglar": baglar, "alt": True}


def ag_araci(v: dict, ek_say: dict | None = None) -> str:
    cogul = {"baslik": "Başlıklar", "terim": "Terimler", "kisi": "Kişiler", "eser": "Eserler", "makale": "Makale tanıtımları"}
    say = {k: sum(1 for d in v["dugumler"] if d["tur"] == k) + (ek_say or {}).get(k, 0) for k, _, _ in AG_TURLER}
    dugmeler = "".join(f'<button type="button" data-tur="{k}" aria-pressed="true"><span class="nokta" style="--renk:{r}"></span>{e(cogul.get(k, a))} <span class="say">{say[k]}</span></button>'
                       for k, a, r in AG_TURLER if say[k])
    veri = json.dumps(v, ensure_ascii=False).replace("</", "<\\/")
    return f"""<div class="ag-arac">
  <div class="tur-secici ag-tur" role="group" aria-label="Gösterilecek türler">{dugmeler}</div>
  <label class="k-ara"><span>Ara</span><input type="search" id="ag-ara" placeholder="Bir ad yazın" autocomplete="off"></label>
  <button type="button" class="ag-sifirla" id="ag-sifirla">Görünümü sıfırla</button>
</div>
<div class="ag-kap">
  <div id="ag" class="ag-tuval"></div>
  <aside id="ag-panel" class="ag-panel" hidden></aside>
  <p class="ag-ipucu">Yakınlaştırmak için fare tekerleğini, kaydırmak için sürüklemeyi kullanabilirsiniz.</p>
</div>
<script id="ag-veri" type="application/json">{veri}</script>
<script src="{SITE_URL}/static/js/d3-7.9.0.min.js"></script>
<script src="{SITE_URL}/static/js/ag.js?v={surum('static/js/ag.js')}"></script>"""


def baslik_ag_listesi(haric: str = "") -> str:
    ogeler = []
    for kad, ks in kumeli_basliklar():
        for k in ks:
            for x in [k] + sorted(COCUK.get(k, []), key=lambda c: FIS[("baslik", c)].get("sira", 99)):
                if x != haric:
                    ogeler.append(f'<a href="{SITE_URL}/ag/{x}/">{e(FIS[("baslik", x)]["ad"])}</a>')
    return '<p class="ag-basliklar"><span>Başlıkların ağları:</span> ' + " · ".join(ogeler) + "</p>"


def render_ag(items) -> str:
    # makaleler (küçük noktalar) ayrı dosyaya yazılır ve "Eserler" düğmesiyle istenince yüklenir
    v = ag_tam(items)
    agir = {d["id"] for d in v["dugumler"] if d.get("kucuk")}
    hafif = {"turler": v["turler"], "dugumler": [d for d in v["dugumler"] if d["id"] not in agir],
             "baglar": [b for b in v["baglar"] if b[0] not in agir and b[1] not in agir], "ek": f"{SITE_URL}/ag/eserler.json"}
    ek = {"dugumler": [d for d in v["dugumler"] if d["id"] in agir],
          "baglar": [b for b in v["baglar"] if b[0] in agir or b[1] in agir]}
    (OUT / "ag").mkdir(parents=True, exist_ok=True)
    (OUT / "ag" / "eserler.json").write_text(json.dumps(ek, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    body = f"""<p class="ust-etiket">Ağ</p><h1>İlişki ağı</h1>
<p class="giris">Başlıklar, terimler, kişiler, eserler ve güncel makaleler arasındaki bağlantılar. Noktanın büyüklüğü bağlantı sayısını gösterir. Üzerine gelindiğinde komşuları belirginleşir, tıklandığında ayrıntıları açılır. DergiPark'taki makaleler, hocaların ORCID kayıtlarındaki DOI'li çalışmaları, AVESİS ve YÖK Akademik sayfalarındaki yayınları (küçük noktalar) konu başlıklarına, terimlere, yazarlarına ve başlığında adı geçen düşünürlere bağlanır. Bir kişi seçildiğinde eserleri üzerinden çalıştığı başlık ve terimler görünür. Sayfa sade ve hızlı açılsın diye eserler ve terimler kapalı gelir. Düğmelerine basılarak açılırlar; "Eserler" açıldığında makaleler de yüklenir.</p>
{ag_araci(hafif, {"eser": len(agir)})}
{baslik_ag_listesi()}
{terim_ag_listesi()}"""
    return page(f"İlişki ağı · {SITE_NAME}", body, "ag", canonical=f"{SITE_URL}/ag/")


def terim_ag_listesi(haric: str = "") -> str:
    ogeler = [f'<a href="{SITE_URL}/ag/{KLASOR["terim"]}/{k}/">{e(ad("terim", h))}</a>'
              for (t, k), h in sorted(FIS.items(), key=lambda x: tr_anahtar(ad(x[0][0], x[1]))) if t == "terim" and k != haric]
    return '<p class="ag-basliklar"><span>Terimlerin ağları:</span> ' + " · ".join(ogeler) + "</p>" if ogeler else ""


def ag_adresi(tur_, k) -> str:
    if tur_ == "baslik":
        return f"{SITE_URL}/ag/{k}/"
    if tur_ == "kisi-tr":
        return f"{SITE_URL}/ag/kisiler/akademi/{k}/"
    return f"{SITE_URL}/ag/{KLASOR[tur_]}/{k}/"


def render_alt_ag(items, tur_, k) -> str:
    if tur_ == "kisi-tr":
        ad_, url_ = akademi_verisi()[k]["p"]["ad"], akademi_url(k)
    else:
        h = FIS[(tur_, k)]
        ad_, url_ = ad(tur_, h), fis_url(tur_, k)
    v = ag_alt_veri(ag_tam(items), k, tur_)
    liste_ = ""
    if tur_ == "baslik":
        aciklama = (f'Bu başlığa{" ve alt başlıklarına" if liste(h.get("alt_basliklar")) else ""} bağlı terimler, kişiler, eserler ve makaleler '
                    'ile bu çalışmaları yazan Türkiye akademisyenleri. Komşu başlıklar kenarda görünür.')
        liste_, tanim = baslik_ag_listesi(k), "başlığına"
    elif tur_ == "terim":
        aciklama = ('Bu terimin geçtiği başlıklar, ilgili terimler, kişiler ve eserler ile adında ya da anahtar kelimelerinde '
                    'terim geçen makaleler ve bunları yazan Türkiye akademisyenleri.')
        liste_, tanim = terim_ag_listesi(k), "terimine"
    else:
        aciklama = ('Kişinin sitedeki eserleri ve makaleleri, bunların bağlı olduğu başlık ve terimler, başlıklarında adı geçen düşünürler '
                    've ortak yazarlar.')
        tanim = "kişisine"
    odak = f"kisi-tr/{k}" if tur_ == "kisi-tr" else f"{tur_}/{k}"
    body = f"""<p class="yol"><a href="{SITE_URL}/ag/">İlişki ağı</a> › <a href="{url_}">{e(ad_)}</a></p>
<h1>{e(ad_)} · İlişki ağı</h1>
<p class="aciklama-kisa">{aciklama} Bütün alanın ağı için <a href="{SITE_URL}/ag/?odak={odak}">genel ağa</a> bakılabilir.</p>
{ag_araci(v)}
{liste_}"""
    return page(f"{ad_} · İlişki ağı · {SITE_NAME}", body, "ag", desc=f"{ad_} {tanim} bağlı kavram, kişi ve eserlerin ağı.",
                canonical=ag_adresi(tur_, k), dizinleme=AKADEMI_ACIK or tur_ != "kisi-tr")


# ---------------------------------------------------------------- dergiler

DERGI_DIZIN = ROOT / "data" / "dergiler"
DIZIN_ADLARI = [("doaj", "DOAJ"), ("trdizin", "TR Dizin"), ("esci", "ESCI"), ("scopus", "Scopus")]
AY_KISA = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]

DERGI_CSS = """
/* Dergiler sayfası */
.d-arac{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 1.4rem;margin:0 0 .4rem}
.d-arac .tur-secici,.d-arac .k-ara{margin:0}
.d-arac .tur-secici button{font-family:var(--sans);font-size:.84rem;padding:.25rem .75rem;border-radius:6px}
.d-arac select{font:inherit;font-family:var(--sans);font-size:.88rem;color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:.3rem .6rem}
.d-arac label.d-sec{display:flex;align-items:center;gap:.5rem;font-style:italic;font-size:.92rem;color:var(--ink-soft)}
ul.d-liste{list-style:none;margin:0;padding:0;max-width:60rem;counter-reset:dergi}
ul.d-liste>li{counter-increment:dergi}
.d-ad-satir::before{content:counter(dergi) ".";font-family:var(--sans);font-size:.85rem;font-weight:600;color:var(--gold);min-width:1.9rem;margin-right:.15rem}
.d-sayi-kisa{display:none}
ul.d-liste>li{display:grid;grid-template-columns:minmax(0,1fr) 6.5rem;gap:.35rem 1.5rem;padding:1rem 0;border-bottom:1px solid var(--rule)}
ul.d-liste>li[hidden]{display:none}
.d-ad{font-family:var(--display);font-size:1.22rem;font-weight:500;line-height:1.25;color:var(--ink);text-decoration:none}
.d-ad:hover{color:var(--accent)}
.d-ad-satir{display:flex;flex-wrap:wrap;align-items:baseline;gap:.2rem .1rem}
.d-ad-satir .rozet{margin-left:.3rem}
.rozet.d-var{color:var(--gold);background:color-mix(in srgb,var(--gold-logo) 14%,var(--card));border-color:color-mix(in srgb,var(--gold-logo) 55%,transparent)}
.rozet.d-bilinmez{border-style:dashed}
.d-sahip{font-family:var(--sans);font-size:.84rem;color:var(--ink-soft);margin:.1rem 0 0}
.d-bilgi{display:grid;grid-template-columns:6.2rem minmax(0,1fr);gap:.3rem 1rem;margin:.55rem 0 0;font-family:var(--sans);font-size:.86rem;align-items:baseline}
.d-bilgi dt{font-size:.68rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--gold)}
.d-bilgi dd{margin:0;min-width:0;color:var(--ink)}
.d-aylar{display:inline-grid;grid-template-columns:repeat(12,2.15rem);gap:2px;vertical-align:middle;margin-right:.6rem}
.d-aylar span{font-size:.62rem;text-align:center;padding:.08rem 0;background:var(--panel);color:var(--ink-soft);border-radius:2px}
.d-aylar span.on{background:var(--accent);color:#fff;font-weight:600}
.d-aylar.surekli span{background:var(--accent-soft);color:var(--accent-ink)}
.d-durum{display:inline-block;font-size:.74rem;font-weight:600;letter-spacing:.03em;padding:.02rem .5rem;border-radius:999px;margin-right:.45rem}
.d-durum.acik{background:#dfeee4;color:#2f6b4a}
.d-durum.kapali{background:#f6e1df;color:#a3352c}
.d-not{color:var(--ink-soft);font-style:italic}
.d-sayi{text-align:right;font-family:var(--sans)}
.d-sayi b{display:block;font-family:var(--display);font-weight:500;font-size:2rem;line-height:1;color:var(--accent-ink);font-variant-numeric:tabular-nums}
.d-sayi small{display:block;font-size:.72rem;line-height:1.3;color:var(--ink-soft);margin-top:.2rem}
.d-sayi.sifir b{color:var(--rule)}
.d-sayi small.d-hoca{color:var(--gold);margin-top:.25rem}
details.d-makaleler{grid-column:1/-1;font-family:var(--sans);font-size:.86rem}
details.d-makaleler summary{cursor:pointer;color:var(--accent-ink);width:max-content;max-width:100%}
details.d-makaleler ol{list-style:none;margin:.4rem 0 0;padding:0 0 0 .9rem;border-left:2px solid var(--gold-soft);display:grid;gap:.35rem}
details.d-makaleler li{font-family:var(--serif);font-size:.92rem;line-height:1.4}
details.d-makaleler li .yil{font-family:var(--sans);font-size:.78rem;color:var(--gold);margin-right:.4rem;font-variant-numeric:tabular-nums}
details.d-makaleler li a{color:var(--ink);text-decoration:none}
details.d-makaleler li a:hover{color:var(--accent);text-decoration:underline}
details.d-makaleler li .yazar{display:block;font-size:.82rem;font-style:italic;color:var(--ink-soft)}
.d-konular{margin:.35rem 0 0;font-style:italic;color:var(--ink-soft)}
.d-sirala{flex-wrap:wrap;gap:.2rem 1rem}
.d-sirala button{white-space:nowrap}
@media (max-width:640px){
  ul.d-liste>li{grid-template-columns:minmax(0,1fr)}
  .d-sayi{display:none}
  .d-sayi-kisa{display:flex;flex-wrap:wrap;align-items:baseline;gap:.25rem .5rem;margin:.3rem 0 0;font-family:var(--sans);font-size:.86rem;color:var(--ink-soft)}
  .d-sayi-kisa b{font-family:var(--display);font-weight:500;font-size:1.3rem;line-height:1;color:var(--accent-ink)}
  .d-sayi-kisa.sifir b{color:var(--rule)}
  .d-sayi-kisa span::before{content:"· ";color:var(--rule)}
  .d-bilgi{grid-template-columns:minmax(0,1fr)}
  .d-bilgi dt{margin-top:.25rem}
  .d-aylar{grid-template-columns:repeat(12,minmax(0,1fr));display:grid;margin:0 0 .2rem}
}
"""
CSS += DERGI_CSS


def tr_gun(s: str) -> str:
    """'01.02.2027' biçimindeki tarihi '1 Şubat 2027' yapar."""
    m = re.fullmatch(r"(\d\d)\.(\d\d)\.(\d{4})", s or "")
    return f"{int(m.group(1))} {AYLAR[int(m.group(2)) - 1]} {m.group(3)}" if m else (s or "")


def yayin_aylari(model: str) -> tuple[list, bool]:
    surekli = "sürekli" in tr_kucuk(model or "")
    m = re.search(r"\(([^)]*)\)", model or "")
    aylar = []
    if m:
        for p in m.group(1).split("-"):
            p = tr_kucuk(p.strip())
            for i, a in enumerate(AYLAR):
                if tr_kucuk(a) == p:
                    aylar.append(i)
    return aylar, surekli


def dergi_verisi() -> tuple[list, dict]:
    liste_d = DERGI_DIZIN / "dergiler.yaml"
    if not liste_d.exists():
        return [], {}
    dergiler = yaml.safe_load(liste_d.read_text(encoding="utf-8")) or []
    durum_d = DERGI_DIZIN / "durum.json"
    durum = json.loads(durum_d.read_text(encoding="utf-8")) if durum_d.exists() else {}
    # DergiPark makaleleri: derginin kodu makale adresinden okunur, eski kodlar güncel dergiye bağlanır
    kod_eslesme = {}
    for d in dergiler:
        kod_eslesme[d["kod"]] = d["kod"]
        for o in d.get("onceki_kodlar") or []:
            kod_eslesme[o] = d["kod"]
    id_kod = {}
    for jl in (DP_DIZIN / "din_felsefesi.jsonl", DP_DIZIN / "akademisyen_makaleleri.jsonl"):
        if not jl.exists():
            continue
        for satir_ in jl.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(satir_)
            except ValueError:
                continue
            for b in r.get("baglanti") or []:
                m = re.search(r"dergipark\.org\.tr/\w+/pub/([^/]+)/", b)
                if m:
                    id_kod[r["id"]] = m.group(1)
                    break
    # Tek sayım: anahtar kelimesinde din felsefesi geçen araştırma makaleleri ile Türkiye akademisindeki din felsefesi
    # öğretim elemanlarının (yazarlığı doğrulanmış) bütün araştırma makaleleri. Kapsam dışı sayılanlar, kitap tanıtımları
    # ve çeviriler girmez; aynı makale bir kez sayılır.
    makale, gorulen = {}, set()
    for m in dp_veri():
        if m.get("tur") or m.get("kaynak") not in (None, "dergipark-akademisyen"):
            continue
        kod = kod_eslesme.get(id_kod.get(m["id"], ""))
        if kod and m["id"] not in gorulen:
            gorulen.add(m["id"])
            makale.setdefault(kod, []).append(m)
    for r, x in akademisyen_dp():
        if x.get("durum") == "kapsam-disi" or x.get("tur") or r["id"] in gorulen:
            continue
        kod = kod_eslesme.get(id_kod.get(r["id"], ""))
        if not kod:
            continue
        gorulen.add(r["id"])
        tarih = yayim_tarihi(r["id"]) or ((r.get("tarih") or [""])[0] or "")[:10]
        bag_ = next((b for b in r.get("baglanti") or [] if "dergipark.org.tr" in b), (r.get("baglanti") or [""])[0])
        makale.setdefault(kod, []).append({
            "id": r["id"], "baslik": (r.get("baslik") or {}).get("tr-TR") or next(iter((r.get("baslik") or {}).values()), ""),
            "yazarlar": [yazar_adi(" ".join(reversed([p_.strip() for p_ in y.split(",", 1)]))) for y in r.get("yazarlar") or []],
            "tarih": tarih, "yil": tarih[:4], "baglanti": bag_, "konular": x.get("basliklar") or []})
    return [d | {"_makaleler": makale.get(d["kod"], []), "_hoca": [],
                 "_durum": (durum.get("dergiler") or {}).get(d["kod"], {})}
            for d in dergiler], durum


def dergi_satiri(d: dict, ana_ad: dict, esik: int) -> str:
    du = d["_durum"]
    # Derginin güncel adı DergiPark sayfasından okunur
    if du.get("baslik") and not du.get("yonlendi") and not d.get("ad_elle"):
        d = d | {"ad": du["baslik"], "onceki_adlar": [x for x in d.get("onceki_adlar") or []
                                                      if tr_kucuk(x) != tr_kucuk(du["baslik"])]}
    dizin = dict(d.get("dizin") or {})
    if du.get("dizin") and not d.get("dizin_elle"):
        dizin = {k: du["dizin"].get(k, False) for k, _ in DIZIN_ADLARI}
    rozet_ = "".join(
        f'<span class="rozet{" d-var" if dizin.get(k) else " d-bilinmez" if dizin.get(k) is None else ""}"'
        f'{" title=\"Bilgi alınamadı\"" if dizin.get(k) is None else ""}>{a}{" ?" if dizin.get(k) is None else ""}</span>'
        for k, a in DIZIN_ADLARI if dizin.get(k) is not False)
    model = du.get("yayin_modeli") or d.get("yayin_modeli") or ""
    aylar, surekli = yayin_aylari(model)
    if surekli:
        serit = '<span class="d-aylar surekli" aria-hidden="true">' + "".join(f"<span>{a}</span>" for a in AY_KISA) + "</span>"
    elif aylar:
        serit = '<span class="d-aylar" aria-hidden="true">' + "".join(
            f'<span{" class=\"on\"" if i in aylar else ""}>{a}</span>' for i, a in enumerate(AY_KISA)) + "</span>"
    else:
        serit = ""
    bilgi = []
    if model:
        bilgi.append(("Yayın", f'{serit}<span>{e(model)}</span>'))
    gd = du.get("gonderim") if not d.get("dergipark_disi") else ""
    if gd == "acik":
        bilgi.append(("Gönderim", '<span class="d-durum acik">Açık</span>'
                      + (f'{e(tr_gun(du["gonderim_tarih"]))} tarihinde açıldı' if du.get("gonderim_tarih") else "")))
    elif gd == "kapali":
        ek = (f'{e(tr_gun(du["acilis"]))} tarihinde açılacak' if du.get("acilis")
              else f'{e(tr_gun(du["gonderim_tarih"]))} tarihinde kapandı' if du.get("gonderim_tarih") else "")
        bilgi.append(("Gönderim", f'<span class="d-durum kapali">Kapalı</span>{ek}'))
    if d.get("kabul_donemi"):
        bilgi.append(("Kabul", e(d["kabul_donemi"])))
    s = du.get("sureler") or {}
    if s.get("degerlendirme") or s.get("yayim"):
        parca = [f"değerlendirme {s['degerlendirme']} gün" if s.get("degerlendirme") else "",
                 f"kabulden yayıma {s['yayim']} gün" if s.get("yayim") else ""]
        bilgi.append(("Süre", "Ortalama " + ", ".join(p for p in parca if p)))
    if d.get("ucret"):
        bilgi.append(("Ücret", e(d["ucret"])))
    if d.get("dergipark_disi"):
        bilgi.append(("Not", '<span class="d-not">' + e(d.get("dis_not") or "Dergi DergiPark'tan ayrılıp kendi sitesine taşınmıştır.") + '</span>'))
    if d.get("onceki_adlar"):
        bilgi.append(("Önceki adı", '<span class="d-not">' + e("; ".join(d["onceki_adlar"])) + "</span>"))
    mk = sorted(d["_makaleler"], key=lambda m: (m["tarih"], m["id"]), reverse=True)
    son5 = sum(1 for m in mk if m["yil"].isdigit() and int(m["yil"]) >= esik)
    konu_say = {}
    for m in mk:
        for k in m.get("konular") or []:
            if k in ana_ad:
                konu_say[k] = konu_say.get(k, 0) + 1
    konular = sorted(konu_say.items(), key=lambda x: (-x[1], tr_anahtar(ana_ad[x[0]])))[:4]

    def mak_li(m):
        return (f'<li><span class="yil">{e(m["yil"])}</span><a href="{e(m["baglanti"])}" rel="noopener">{e(m["baslik"])}</a>'
                f'<span class="yazar">{e(", ".join(m["yazarlar"]))}</span></li>')
    makaleler = ""
    if mk:
        satirlar = "".join(mak_li(m) for m in mk)
        konu_html = ('<p class="d-konular">En çok: ' + ", ".join(
            f'<a href="{SITE_URL}/basliklar/{k}/">{e(ana_ad[k])}</a> ({n})' for k, n in konular) + "</p>") if konular else ""
        makaleler = (f'<details class="d-makaleler"><summary>Din felsefesi makaleleri ({len(mk)})</summary>'
                     f'{konu_html}<ol>{satirlar}</ol></details>') + makaleler
    elif konular:
        makaleler = ('<p class="d-konular" style="grid-column:1/-1;font-family:var(--sans);font-size:.86rem">En çok: ' + ", ".join(
            f'<a href="{SITE_URL}/basliklar/{k}/">{e(ana_ad[k])}</a> ({n})' for k, n in konular) + "</p>") + makaleler
    ara = ara_norm(" ".join([d["ad"], d.get("sahip") or "", d["kod"], " ".join(d.get("onceki_adlar") or [])]))
    ad_html = (f'<a class="d-ad" href="{e(d["link"])}" rel="noopener">{e(d["ad"])}</a>' if d.get("link") else f'<span class="d-ad">{e(d["ad"])}</span>')
    data = (f'data-ara="{e(ara)}" data-ad="{e(d["ad"])}" data-df="{len(mk)}" data-son5="{son5}" '
            f'data-dizin=" {" ".join(k for k, _ in DIZIN_ADLARI if dizin.get(k))} " data-gonderim="{gd or ""}" '
            f'data-aylar=" {" ".join(str(i) for i in aylar)}{" surekli" if surekli else ""} " '
            f'data-sure="{s.get("degerlendirme") or ""}"')
    return (f'<li {data}><div><div class="d-ad-satir">{ad_html}{rozet_}</div>'
            + (f'<p class="d-sahip">{e(d["sahip"])}</p>' if d.get("sahip") else "")
            + f'<p class="d-sayi-kisa{" sifir" if not mk else ""}"><b>{len(mk)}</b> din felsefesi makalesi'
            + (f'<span>son beş yılda {son5}</span>' if mk else "") + '</p>'
            + ('<dl class="d-bilgi">' + "".join(f"<dt>{a}</dt><dd>{v}</dd>" for a, v in bilgi) + "</dl>" if bilgi else "")
            + f'</div><div class="d-sayi{" sifir" if not mk else ""}"><b>{len(mk)}</b><small>din felsefesi makalesi</small>'
            + (f"<small>son beş yılda {son5}</small>" if mk else "")
            + f"</div>{makaleler}</li>")


def render_dergiler() -> str:
    dergiler, durum = dergi_verisi()
    esik = YIL - 4
    ana_ad = {k: FIS[("baslik", k)]["ad"] for k in ana_basliklar()}
    satirlar = "".join(dergi_satiri(d, ana_ad, esik) for d in
                       sorted(dergiler, key=lambda d: (-len(d["_makaleler"]), tr_anahtar(d["ad"]))))
    toplam = sum(len(d["_makaleler"]) for d in dergiler)
    tarama = (durum.get("tarama") or "")[:10]
    dizinler = "".join(f'<button type="button" data-dizin="{k}" aria-pressed="false">{a}</button>' for k, a in DIZIN_ADLARI)
    aylar = '<option value="">Fark etmez</option>' + "".join(
        f'<option value="{i}">{a} sayısı olanlar</option>' for i, a in enumerate(AYLAR)) + '<option value="surekli">Sürekli yayın</option>'
    siralama = ('<div class="eser-sirala d-sirala" role="group" aria-label="Sıralama"><span>Sırala</span>'
                + "".join(f'<button type="button" class="sirala" data-alan="{k}" aria-sort="{"descending" if k == "df" else "none"}">{a}'
                          f'<span class="ok" aria-hidden="true"></span></button>'
                          for k, a in [("df", "Makale sayısı"), ("son5", "Son beş yıl"), ("sure", "Değerlendirme süresi"), ("ad", "Ad")])
                + "</div>")
    body = (f'<p class="ust-etiket">Dergiler</p><h1>Türkiye\'de din felsefesi makalesi yayımlayan dergiler</h1>'
            f'<p class="giris">Her derginin dizinleri, yayın ayları, '
            f'makale gönderim durumu ve yayımladığı din felsefesi makaleleri bir arada gösterilir.</p>'
            f'<p class="aciklama-kisa">Gönderim durumu, yayın modeli, ortalama süreler ve dizinler her akşam derginin DergiPark sayfasından okunur'
            f'{" (son okuma " + tr_date(tarama) + ")" if tarama else ""}. Dizin bilgisi derginin kendi beyanıdır. '
            f'Kabul dönemleri dergilerin duyurularından elle derlenmiştir; başvurudan önce derginin sayfasına bakınız. '
            f'Büyük rakam, derginin DergiPark\'ta yayımladığı din felsefesi makalelerini gösterir ({len(dergiler)} dergide toplam {toplam}). '
            f'Anahtar kelimelerinde din felsefesi geçen araştırma makaleleri ile Türkiye\'deki din felsefesi öğretim elemanlarının makaleleri birlikte sayılır. '
            f'Kitap tanıtımı ve çeviriler sayılmaz. '
            f'Düzeltme ve dergi önerileri için: <a href="mailto:{ILETISIM}">{ILETISIM}</a></p>'
            f'<p class="secim-etiket">Ara ve süz</p>'
            f'<div class="d-arac"><label class="k-ara"><span>Ara</span><input type="search" id="dergi-ara" placeholder="Dergi, kurum ya da eski ad" autocomplete="off"></label>'
            f'<div class="tur-secici d-dizin-sec" role="group" aria-label="Dizin">{dizinler}</div></div>'
            f'<div class="d-arac"><div class="tur-secici d-gonderim-sec" role="group" aria-label="Gönderim">'
            f'<button type="button" data-gonderim="" aria-pressed="true">Bütün dergiler</button>'
            f'<button type="button" data-gonderim="acik" aria-pressed="false">Gönderime açık</button>'
            f'<button type="button" data-gonderim="kapali" aria-pressed="false">Gönderime kapalı</button></div>'
            f'<label class="d-sec">Yayın ayı <select id="dergi-ay">{aylar}</select></label></div>'
            f'<div class="eser-ust" style="max-width:60rem"><p class="eser-sayi"><span id="dergi-say"></span></p>{siralama}</div>'
            f'<ul class="d-liste">{satirlar}</ul><p class="giris d-bos" hidden>Seçime uyan dergi bulunamadı. Bir süzgeci kaldırmayı deneyin.</p>')
    gorsel = paylasim_gorseli("dergiler", "dinfelsefesi.com.tr", "Türkiye'de din felsefesi makalesi yayımlayan dergiler",
                              "Dizinler, yayın ayları, gönderim durumu ve makaleler")
    return page(f"Dergiler · {SITE_NAME}", body + DERGI_JS, "dergiler", canonical=f"{SITE_URL}/dergiler/",
                desc="Türkiye'de din felsefesi makalesi yayımlayan dergiler: dizinler, yayın ayları, gönderim durumu ve yayımlanan makaleler.",
                gorsel=gorsel)


DERGI_JS = """<script>
(function(){
  var ul=document.querySelector('ul.d-liste'), lis=[].slice.call(ul.children);
  var g=document.getElementById('dergi-ara'), ay=document.getElementById('dergi-ay');
  var db=document.querySelectorAll('.d-dizin-sec button'), gb=document.querySelectorAll('.d-gonderim-sec button');
  var sb=document.querySelectorAll('.eser-sirala button');
  var dizin=[], gonderim='', alan='df', yon=-1;
  var kucuk=function(s){return s.replace(/I/g,'ı').replace(/İ/g,'i').toLowerCase().replace(/[âäāàá]/g,'a').replace(/[êēëè]/g,'e').replace(/[îïīì]/g,'i').replace(/[ôōò]/g,'o').replace(/[ûūù]/g,'u').replace(/[\'`´‘’ʻʼʽʾʿ]/g,'');};
  var kar=function(a,b){return a.localeCompare(b,'tr',{sensitivity:'base'});};
  function uygula(yaz){
    var q=kucuk(g.value.trim()).split(/\\s+/).filter(Boolean), a=ay.value, n=0;
    lis.forEach(function(li){
      var v=q.every(function(p){return li.dataset.ara.indexOf(p)>-1;})
        && dizin.every(function(k){return li.dataset.dizin.indexOf(' '+k+' ')>-1;})
        && (!gonderim||li.dataset.gonderim===gonderim)
        && (!a||li.dataset.aylar.indexOf(' '+a+' ')>-1);
      li.hidden=!v; if(v)n++;
    });
    db.forEach(function(b){b.setAttribute('aria-pressed', dizin.indexOf(b.dataset.dizin)>-1?'true':'false');});
    gb.forEach(function(b){b.setAttribute('aria-pressed', b.dataset.gonderim===gonderim?'true':'false');});
    document.getElementById('dergi-say').textContent=n+' dergi';
    document.querySelector('.d-bos').hidden=n>0;
    if(yaz){
      var p=new URLSearchParams(); if(g.value.trim())p.set('ara',g.value.trim()); if(dizin.length)p.set('dizin',dizin.join(','));
      if(gonderim)p.set('gonderim',gonderim); if(a)p.set('ay',a);
      if(alan!=='df'||yon>0){p.set('sirala',alan); if(yon<0)p.set('yon','azalan');}
      try{history.replaceState(null,'',location.pathname+(p.toString()?'?'+p:''));}catch(_){}
    }
  }
  function sirala(){
    var r=lis.slice();
    r.sort(function(x,y){
      if(alan==='ad') return kar(x.dataset.ad,y.dataset.ad)*yon;
      var bx=x.dataset[alan]==='', by=y.dataset[alan]==='';
      if(bx!==by) return bx?1:-1;  // bilgisi olmayanlar her iki yönde de sona
      return ((+x.dataset[alan]||0)-(+y.dataset[alan]||0))*yon || ((+y.dataset.df)-(+x.dataset.df)) || kar(x.dataset.ad,y.dataset.ad);
    });
    r.forEach(function(x){ul.appendChild(x);});
    sb.forEach(function(b){b.setAttribute('aria-sort', b.dataset.alan===alan ? (yon>0?'ascending':'descending') : 'none');});
  }
  db.forEach(function(b){b.addEventListener('click',function(){
    var i=dizin.indexOf(b.dataset.dizin); if(i>-1)dizin.splice(i,1); else dizin.push(b.dataset.dizin); uygula(true);});});
  gb.forEach(function(b){b.addEventListener('click',function(){gonderim=b.dataset.gonderim; uygula(true);});});
  sb.forEach(function(b){b.addEventListener('click',function(){
    if(alan===b.dataset.alan){yon=-yon;} else {alan=b.dataset.alan; yon=(alan==='ad'||alan==='sure')?1:-1;}
    sirala(); uygula(true);
  });});
  g.addEventListener('input',function(){uygula(true);});
  ay.addEventListener('change',function(){uygula(true);});
  var p=new URLSearchParams(location.search);
  g.value=p.get('ara')||''; dizin=(p.get('dizin')||'').split(',').filter(Boolean); gonderim=p.get('gonderim')||''; ay.value=p.get('ay')||'';
  if(p.get('sirala')){alan=p.get('sirala'); yon=p.get('yon')==='azalan'?-1:1; sirala();}
  uygula(false);
})();
</script>"""


# ---------------------------------------------------------------- ana sayfa ve hakkında

def ilk_paragraf(md: str) -> str:
    for parca in re.split(r"\n\s*\n", md or ""):
        parca = parca.strip()
        if parca and not parca.startswith(("#", "-", "*", ">", "|")):
            return re.sub(r"\s+", " ", parca)
    return ""


def okuma_baslangici() -> str:
    adaylar = [k for (t, k), h in FIS.items() if t == "baslik" and ilk_paragraf(h.get("_govde"))]
    if not adaylar:
        return ""
    k = max(adaylar, key=lambda x: len(FIS[("baslik", x)]["_govde"]))
    h = FIS[("baslik", k)]
    return f"""<aside class="okuma" aria-label="Okumaya başlangıç">
  <p class="ust-etiket">Okumaya buradan başlayabilirsiniz</p>
  <h2><a href="{fis_url('baslik', k)}">{e(h['ad'])}</a></h2>
  <p class="alinti">{satir_ici(ilk_paragraf(h['_govde']))}</p>
  <a class="devam" href="{fis_url('baslik', k)}">Metnin devamını okuyun →</a>
</aside>"""


def icindekiler_html() -> str:
    satirlar = []
    for kad, ks in kumeli_basliklar():
        satirlar.append(f'<li class="kume-ad">{e(kad)}</li>')
        for k in ks:
            h = FIS[("baslik", k)]
            b = bagli_fisler(k)
            altlar = " · ".join(bag("baslik", a) for a in liste(h.get("alt_basliklar")))
            satirlar.append(f"""<li><span class="no">{e(h.get('sira', ''))}</span><div>
  <h3><a href="{fis_url('baslik', k)}">{e(h['ad'])}</a></h3>
  <p>{satir_ici(h.get('ozet'))}</p>
  {f'<p class="altlar-metin">{altlar}</p>' if altlar else ''}
  {f'<span class="say">{sayim_metni(b)}</span>' if b else ''}
</div></li>""")
    return f'<ul class="icindekiler">{"".join(satirlar)}</ul>'


def paylas_dugmesi(m: dict) -> str:
    from urllib.parse import quote
    metin = f"Günün makalesi: {m['title_tr']} ({m.get('authors', '')}, {m.get('journal', '')}) #dinfelsefesi"
    adres = f"https://x.com/intent/post?text={quote(metin)}&url={quote(entry_url(m))}"  # "via" eklenmez: bağlantı metnin sonunda kalınca X onu gizleyip yalnızca kartı gösterir
    return f'<a class="x-paylas" href="{e(adres)}" target="_blank" rel="noopener">X\'te paylaş</a>'


def gunun_makalesi_html(items) -> str:
    if not items:
        return okuma_baslangici()
    m = items[0]
    return f"""<aside class="okuma gunun" aria-label="Günün makalesi">
  <p class="ust-etiket">Günün makalesi · {e(gun_metni(m['gun']))}</p>
  <h2><a href="{entry_url(m)}">{e(m['title_tr'])}</a></h2>
  <p class="orij">{e(m.get('title_en', ''))}{rozetler(m)}</p>
  <p class="kunye">{e(m['authors'])} · {e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</p>
  <p class="alinti">{e(m['lead'])}</p>
  <p class="gunun-git"><a href="{entry_url(m)}">Tanıtımı okuyun →</a> <a href="{SITE_URL}/gunun-makalesi/">Önceki günlerin makaleleri →</a> {paylas_dugmesi(m)}</p>
</aside>"""


def onceki_gunler_html(items) -> str:
    """Ana sayfada önceki günlerin makaleleri: yalnızca tarih ve Türkçe başlıkla son beş gün, tamamı ayrı sayfada."""
    if len(items) < 2:
        return ""
    satirlar = "".join(f'<li><span class="og-tarih">{e(tr_date(m["gun"]))}</span>'
                       f'<a href="{entry_url(m)}">{e(m["title_tr"])}</a>'
                       f'<span class="og-yazar">{e(m.get("authors", ""))}</span></li>' for m in items[1:6])
    return (f'<div class="bolum-baslik"><h2>Önceki günlerin makaleleri</h2></div>'
            f'<ul class="onceki-gunler">{satirlar}</ul>'
            f'<p class="og-hepsi"><a href="{SITE_URL}/gunun-makalesi/">Bütün günlerin makaleleri ({len(items) - 1}) →</a></p>')


# Doktora tamamlama unvandan çıkarılmaz (kaynaklar "Arş. Gör." ile "Arş. Gör. Dr." ayrımını tutarlı yazmıyor);
# YÖK Tez Merkezi'nden doğrulanıp content/akademi_tebrik.yaml dosyasına elle yazılır.
UNVAN_ADI = {"Öğr. Gör.": "öğretim görevlisi oldu", "Dr. Öğr. Üyesi": "Dr. Öğretim Üyesi oldu", "Doç. Dr.": "doçent oldu",
             "Prof. Dr.": "profesör oldu"}


# "Kutla" düğmesi: sayılar hosting'deki küçük bir PHP dosyasında tutulur (api/kutla.php). Aynı tarayıcı bir kişiyi bir kez
# kutlar (tarayıcıda işaretlenir), sunucu da aynı adresten gelen ikinci kutlamayı saymaz (adres yalnızca özetlenmiş hâliyle
# tutulur). PHP çalışmayan bir sunucuda (GitHub Pages) düğmeler hiç görünmez.
KUTLA_JS = """<script>
(function(){var d=[].slice.call(document.querySelectorAll('.kutla'));if(!d.length)return;var u='/api/kutla.php';
function oku(k){try{return localStorage.getItem('kutla:'+k)}catch(e){return null}}
function yaz(k){try{localStorage.setItem('kutla:'+k,'1')}catch(e){}}
var jt;try{jt=localStorage.getItem('kutla-jeton')}catch(e){}
if(!jt||!/^[a-f0-9]{32}$/.test(jt)){jt='';for(var i=0;i<32;i++)jt+='0123456789abcdef'[Math.floor(Math.random()*16)];try{localStorage.setItem('kutla-jeton',jt)}catch(e){}}
function goster(b,n){var s=b.querySelector('.k-sayi');if(n>0){s.textContent=n;s.hidden=false}
  if(oku(b.dataset.id)){b.classList.add('kutlandi');b.setAttribute('aria-pressed','true');b.querySelector('.k-yazi').textContent='Kutladınız'}}
fetch(u+'?ids='+d.map(function(b){return b.dataset.id}).join(','),{cache:'no-store'}).then(function(r){
  if(!r.ok||(r.headers.get('content-type')||'').indexOf('json')<0)throw 0;return r.json()}).then(function(j){
  d.forEach(function(b){b.hidden=false;goster(b,(j.sayilar||{})[b.dataset.id]||0);
    b.addEventListener('click',function(){if(oku(b.dataset.id))return;yaz(b.dataset.id);
      var s=b.querySelector('.k-sayi');goster(b,(parseInt(s.textContent,10)||0)+1);
      fetch(u+'?id='+encodeURIComponent(b.dataset.id)+'&j='+jt,{method:'POST'}).then(function(r){return r.json()}).then(function(k){
        if(k&&k.sayi)goster(b,k.sayi)}).catch(function(){})})})}).catch(function(){});
})();
</script>"""

KUTLA_PHP = r"""<?php
// Ana sayfadaki "Kutla" düğmelerinin sayaçları. GET ?ids=a,b,c sayıları verir; POST ?id=a bir kutlama ekler.
// Her tarayıcı rastgele bir jeton taşır; aynı jetonla aynı kişiye ikinci kutlama sayılmaz. Kötüye kullanıma karşı
// aynı internet adresinden bir kişiye en çok 30 kutlama sayılır (kampüs ve mobil ağlarda çok kişi tek adresi paylaşır).
// Jeton ve adres yalnızca geri çevrilemeyen özet olarak tutulur.
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$kimlik = function ($s) { return preg_match('/^[a-z0-9-]{1,100}$/', $s) ? $s : null; };
$klasor = dirname(__DIR__, 2) . '/kutla-veri';          // public_html'in dışında: site yüklemesi silmez
if (!is_dir($klasor)) { @mkdir($klasor, 0755, true); }
if (!is_dir($klasor) || !is_writable($klasor)) {
    $klasor = dirname(__DIR__) . '/.kutla';              // olmazsa site içinde, web'e kapalı bir klasör
    if (!is_dir($klasor)) { @mkdir($klasor, 0755, true); }
    @file_put_contents($klasor . '/.htaccess', "Require all denied\nDeny from all\n");
}
$dosya = $klasor . '/sayilar.json';
$fp = @fopen($dosya, 'c+');
if (!$fp) { http_response_code(500); echo '{"hata":"kayit"}'; exit; }
flock($fp, LOCK_EX);
$veri = json_decode(stream_get_contents($fp), true);
if (!is_array($veri)) { $veri = ['sayilar' => []]; }
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $id = $kimlik($_GET['id'] ?? '');
    if ($id === null) { flock($fp, LOCK_UN); http_response_code(400); echo '{}'; exit; }
    $jeton = preg_match('/^[a-f0-9]{32}$/', $_GET['j'] ?? '') ? $_GET['j'] : '';
    $iz = substr(hash('sha256', 'j|' . $jeton . '|' . $id . '|dinfelsefesi-kutla'), 0, 16);
    $ip = substr(hash('sha256', 'a|' . ($_SERVER['REMOTE_ADDR'] ?? '') . '|' . $id . '|dinfelsefesi-kutla'), 0, 16);
    $izler = $veri['jetonlar'][$id] ?? [];
    $ipler = $veri['adresler'][$id] ?? [];
    if ($jeton !== '' && !in_array($iz, $izler, true) && ($ipler[$ip] ?? 0) < 30) {
        $veri['sayilar'][$id] = ($veri['sayilar'][$id] ?? 0) + 1;
        $izler[] = $iz;
        $veri['jetonlar'][$id] = array_slice($izler, -5000);
        $ipler[$ip] = ($ipler[$ip] ?? 0) + 1;
        $veri['adresler'][$id] = array_slice($ipler, -5000, null, true);
        unset($veri['izler']);
        ftruncate($fp, 0); rewind($fp);
        fwrite($fp, json_encode($veri));
        fflush($fp);
    }
    flock($fp, LOCK_UN);
    echo json_encode(['id' => $id, 'sayi' => $veri['sayilar'][$id] ?? 0]);
    exit;
}
flock($fp, LOCK_UN);
$cikti = [];
foreach (explode(',', $_GET['ids'] ?? '') as $s) {
    $id = $kimlik($s);
    if ($id !== null) { $cikti[$id] = $veri['sayilar'][$id] ?? 0; }
}
echo json_encode(['sayilar' => $cikti]);
"""


def tebrikler() -> list:
    """Akademide son unvan değişiklikleri. İki kaynaktan gelir: (1) unvan_gecmisi.json'da son 90 günde fark edilen
    yükselmeler (scripts/unvan_izle.py), (2) AVESİS 'Deneyim' kutusunda güncel unvanının başlangıç yılı bu yıl olanlar."""
    from datetime import date, timedelta
    bugun_ = date.fromisoformat(bugun())
    liste_ = {p["ad"]: p for p in (yaml.safe_load((CONTENT / "turkiye_akademisi.yaml").read_text(encoding="utf-8")) or {}).get("kisiler") or []}
    out, gor = [], set()
    gd = ROOT / "data/akademi/unvan_gecmisi.json"
    gecmis = json.loads(gd.read_text(encoding="utf-8")) if gd.exists() else {}
    for ad_, g in gecmis.items():
        for d in g.get("degisiklikler") or []:
            if ad_ in liste_ and date.fromisoformat(d["tarih"]) >= bugun_ - timedelta(days=90) and d["yeni"] in UNVAN_ADI:
                t = date.fromisoformat(d["tarih"])
                out.append({"ad": ad_, "unvan": d["yeni"], "zaman": f"{AYLAR[t.month - 1]} {t.year}", "sira": d["tarih"],
                            "kaynak": d["kaynak"]})
                gor.add((ad_, d["yeni"]))
    av_d = ROOT / "data/avesis/yayinlar.json"
    avesis = json.loads(av_d.read_text(encoding="utf-8")) if av_d.exists() else {}
    for ad_, v in avesis.items():
        d = next((x for x in v.get("deneyim") or [] if not x.get("bitis")), None)
        if d:  # Deneyim kutusunda unvan uzun da yazılabiliyor
            d = d | {"unvan": {"Araştırma Görevlisi Dr.": "Arş. Gör. Dr.", "Öğretim Görevlisi Dr.": "Öğr. Gör. Dr.",
                               "Doktor Öğretim Üyesi": "Dr. Öğr. Üyesi", "Doçent": "Doç. Dr.", "Profesör": "Prof. Dr."}.get(d["unvan"], d["unvan"])}
        if (ad_ in liste_ and d and d["baslangic"] == str(bugun_.year) and d["unvan"] in UNVAN_ADI
                and (ad_, d["unvan"]) not in gor and d["unvan"] == v.get("unvan")):
            out.append({"ad": ad_, "unvan": d["unvan"], "zaman": d["baslangic"], "sira": d["baslangic"] + "-00", "kaynak": "AVESİS"})
    td = CONTENT / "akademi_tebrik.yaml"
    tv = (yaml.safe_load(td.read_text(encoding="utf-8")) or {}) if td.exists() else {}
    for d in tv.get("unvan") or []:  # YÖK Akademik görevlerinden elle doğrulanan yükselmeler
        if d.get("ad") in liste_ and str(d.get("yil")) == str(bugun_.year) and d.get("unvan") in UNVAN_ADI \
                and (d["ad"], d["unvan"]) not in gor:
            out.append({"ad": d["ad"], "unvan": d["unvan"], "zaman": str(d["yil"]), "sira": str(d["yil"]) + "-00",
                        "kaynak": "YÖK Akademik"})
            gor.add((d["ad"], d["unvan"]))
    for d in tv.get("doktora") or []:
        if d.get("ad") in liste_ and str(d.get("yil")) == str(bugun_.year):
            out.append({"ad": d["ad"], "unvan": "doktora", "zaman": str(d["yil"]), "sira": str(d["yil"]) + "-00",
                        "kaynak": "YÖK Tez Merkezi", "tez": d.get("tez", ""), "tez_univ": d.get("universite", "")})
    # Önce yıla, sonra unvanın büyüklüğüne göre (profesör, doçent, Dr. Öğretim Üyesi, doktora), aynı düzeyde ada göre
    duzey = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2, "Öğr. Gör.": 3, "doktora": 4}
    out.sort(key=lambda x: (-int(x["sira"][:4]), duzey.get(x["unvan"], 9), tr_anahtar(x["ad"])))
    return [x | {"p": liste_[x["ad"]]} for x in out]


def akademide_bu_ay_html() -> str:
    from datetime import date
    bugun_ = date.fromisoformat(bugun())
    # Tebrikler
    tb = tebrikler()
    if tb:
        def kutla_kimligi(x):
            return slugify(f'{x["ad"]}-{"doktora" if x["unvan"] == "doktora" else x["unvan"]}-{x["zaman"][:4]}')

        def kutla_dugmesi(x):
            return (f'<button type="button" class="kutla" data-id="{kutla_kimligi(x)}" hidden '
                    f'aria-label="{e(x["ad"])} için kutla"><span aria-hidden="true">👏</span> <span class="k-yazi">Kutla</span>'
                    f'<b class="k-sayi" hidden></b></button>')
        satir = "".join(
            (f'<li class="gn-tb"><div><a href="{akademi_url(slugify(x["ad"]))}">{e(x["ad"])}</a> doktorasını tamamladı'
             f'<span class="gn-alt"><i>{e(x["tez"])}</i> · {e(x["tez_univ"])}</span></div>{kutla_dugmesi(x)}</li>')
            if x["unvan"] == "doktora" else
            (f'<li class="gn-tb"><div><a href="{akademi_url(slugify(x["ad"]))}">{e(x["ad"])}</a> {e(UNVAN_ADI[x["unvan"]])}'
             f'<span class="gn-alt">{e(x["p"].get("universite") or "")}</span></div>{kutla_dugmesi(x)}</li>')
            for x in tb[:10])
        tebrik = (f'<p class="gn-tebrik-soz"><span><span aria-hidden="true">🎓</span> {bugun_.year} yılında yeni unvan alan ve '
                  f'doktorasını tamamlayan hocalarımızı tebrik ederiz <span aria-hidden="true">🎉</span></span></p>'
                  f'<ul class="gn-liste">{satir}</ul><p class="aciklama-kisa gn-not">Bilgiler YÖK Akademik ve AVESİS '
                  f'kayıtlarındandır; eksik gördüğünüzü bildirebilirsiniz.</p>' + KUTLA_JS)
    else:
        tebrik = ('<p class="gn-bos">Bu dönemde kayda geçen bir unvan değişikliği yok.</p>'
                  '<p class="aciklama-kisa gn-not">Unvanlar AVESİS (ayda bir) ve YÖK Akademik kayıtlarından, doktoralar YÖK kayıtlarından izlenir. '
                  'Doktorasını tamamlayan, doçent ve profesör olan hocalar burada tebrik edilir.</p>')
    # Son yayımlanan çalışmalar: yayım günü bilinen, bir başlığa bağlı çalışmalar
    yayim_var = any(m.get("yayim") for m in dp_veri())  # yayım tarihleri henüz toplanmadıysa eski davranış
    yayin = [m for m in dp_veri() if (m.get("yayim") if yayim_var else len(str(m.get("tarih") or "")) >= 10)
             and (m["konular"] or m["ilgili"])]
    yayin.sort(key=lambda m: m["tarih"], reverse=True)
    # Bu ay ya da geçen ay en az üç çalışma yayımlandıysa yalnızca o ayın çalışmaları gösterilir ve başlıkta ay yazar
    yayin_ayi = ""
    if yayim_var:
        gecen = (bugun_.replace(day=1) - timedelta(days=1))
        for y_, a_ in ((bugun_.year, bugun_.month), (gecen.year, gecen.month)):
            o_ay = [m for m in yayin if m["tarih"][:7] == f"{y_}-{a_:02d}"]
            if len(o_ay) >= 3:
                yayin, yayin_ayi = o_ay, f"{AYLAR[a_ - 1]} {y_}"
                break
    satir = ""
    for m in yayin[:6]:
        yazar, dergi = dp_kunye(m)
        konu = ", ".join(FIS[("baslik", b)]["ad"] for b in (m["konular"] or m["ilgili"])
                         if ("baslik", b) in FIS and not FIS[("baslik", b)].get("ust_baslik"))[:80]
        satir += (f'<li>{eser_adi(m["baglanti"], m["baslik"], "")}<span class="gn-alt">{yazar} · {dergi} · '
                  f'{e(ay_yil(m["tarih"]))}</span>' + (f'<span class="gn-konu">{e(konu)}</span>' if konu else "") + '</li>')
    soz_ = (f'<p class="gn-tebrik-soz"><span><span aria-hidden="true">📚</span> {yayin_ayi}\'da makalesi yayımlanan '
            f'hocalarımızı tebrik ederiz <span aria-hidden="true">👏</span></span></p>') if yayin_ayi else ""
    yayinlar_ = (soz_ + f'<ul class="gn-liste">{satir}</ul><p class="gn-hepsi"><a href="{SITE_URL}/eserler/">Bütün çalışmalar →</a></p>'
                 if satir else '<p class="gn-bos">Henüz kayıt yok.</p>')
    return (f'<section class="guncel" aria-labelledby="gn-bas"><div class="bolum-baslik"><h2 id="gn-bas">Akademi Güncel</h2></div>'
            f'<div class="gn-izgara">'
            f'<section class="gn-kart gn-tebrik"><h3>Tebrikler <span class="gn-ay">{bugun_.year}</span></h3>{tebrik}</section>'
            f'<section class="gn-kart"><h3>Son yayımlanan çalışmalar{f" <span class=\"gn-ay\">{yayin_ayi}</span>" if yayin_ayi else ""}</h3>{yayinlar_}</section>'
            f'</div></section>')


def render_ana(items) -> str:
    say = {t: sum(1 for (x, _) in FIS if x == t) for t in KLASOR}
    tr_dosya = CONTENT / "turkiye_akademisi.yaml"
    tr_say = len((yaml.safe_load(tr_dosya.read_text(encoding="utf-8")) or {}).get("kisiler") or []) if tr_dosya.exists() else 0
    durum = (f'Şimdilik {len(ana_basliklar())} ana başlık, {say["terim"]} terim, {say["kisi"]} düşünür ve {say["eser"]} eser fişi yer almaktadır'
             + (f'. Türkiye akademisi listesinde {tr_say} akademisyen bulunmaktadır.' if tr_say else '.'))
    body = f"""
<section class="karsilama">
  <div class="karsilama-metin">
  <h1>Din felsefesi için Türkçe başvuru kaynağı</h1>
  <p>Din felsefesinin temel problemleri birer okuma metniyle ele alınır, terimler, düşünürler ve eserler de bu metinlere bağlı fişlerle sunulur. Sitede ayrıca Türkiye'deki <a href="{SITE_URL}/kisiler/">din felsefesi akademisyenlerinin</a> listesi, din felsefesi makalesi yayımlayan <a href="{SITE_URL}/dergiler/">dergiler</a> ve DergiPark'ta yayımlanmış <a href="{SITE_URL}/eserler/">çalışmalar</a> yer alır. <a href="{SITE_URL}/gunun-makalesi/">Günün makalesi</a> bölümünde her gün bir makale, kendi özetine dayanan kısa bir tanıtımla öne çıkarılır.</p>
  <p class="durum-satiri">{durum}</p>
  <p class="karsilama-git"><a href="{SITE_URL}/basliklar/">Başlıklara göz atın →</a> <a href="{SITE_URL}/ag/">İlişki ağını açın →</a></p>
  </div>
  {gunun_makalesi_html(items)}
</section>
<div class="susleme" aria-hidden="true"><span>❦</span></div>
{akademide_bu_ay_html()}

"""
    # Ana sayfanın paylaşım görseli sitenin genel kartıdır (bağlantı paylaşıldığında sitenin kendisi tanıtılır).
    gorsel = f"{SITE_URL}/paylas/site.png"
    jl = {"@type": "WebSite", "name": SITE_NAME, "alternateName": "dinfelsefesi.com.tr", "url": SITE_URL + "/",
          "inLanguage": "tr", "description": "Din felsefesi için Türkçe başvuru kaynağı", "publisher": ld_yayinci(),
          "editor": {"@type": "Person", "name": EDITOR, "url": "https://abdullahakgul.com",
                     "sameAs": ["https://orcid.org/0000-0001-9660-9424"]}}
    return page(f"{SITE_NAME} · Türkçe Başvuru Kaynağı", body, "", canonical=SITE_URL + "/", gorsel=gorsel, jsonld=jl,
                desc="Din felsefesinin başlıkları, terimleri, kişileri ve eserleri. Türkiye'deki din felsefesi akademisyenleri, "
                     "DergiPark'taki din felsefesi makaleleri ve her gün bir makale tanıtımı.")


ABOUT = f"""
<article class="hakkinda">
  <h1>Hakkında</h1>
  <p class="hk-giris">{SITE_NAME}, din felsefesine dair Türkçe bir başvuru kaynağı olarak hazırlanmaktadır. Sitede din felsefesi literatürünün ana başlıkları, bu başlıklara bağlı terimler, düşünürler ve eserler birbirine bağlantılı fişler hâlinde yer almaktadır. Ayrıca her gün din felsefesi dergilerinde yayımlanmış bir makale Türkçe tanıtımıyla öne çıkarılmaktadır. Tanıtımlar makalenin iddiasını, yöntemini ve literatürdeki yerini aktarır, makalenin yerine geçmez. Her kayıtta özgün metne bağlantı bulunur.</p>
  <div class="hk-izgara">
    <section><h2>Editörlük</h2><p><a href="https://abdullahakgul.com" rel="noopener">{EDITOR}</a>, Erciyes Üniversitesi İlahiyat Fakültesi, Din Felsefesi Anabilim Dalı.</p></section>
    <section><h2>Atıf</h2><p>Eser fişlerinde ve makale tanıtımlarında eserin kendi künyesine atıf yapılması önerilir. Sitedeki bir fişe atıf için önerilen biçim: "Fişin adı". <i>dinfelsefesi.com.tr</i>, ed. {EDITOR}. Son güncelleme. Erişim tarihi. Adres.</p></section>
    <section><h2>Düzeltme ve öneriler</h2><p>Fişlerdeki bir yanlış ya da eksik, Türkiye akademisi listesine dair bir düzeltme veya yeni bir öneri için: <a href="mailto:{ILETISIM}">{ILETISIM}</a></p></section>
    <section><h2>Veriler</h2><p>Kayıtlar yazılımların okuyabileceği biçimde de sunulmaktadır: <a href="{SITE_URL}/api/fisler.json">fişler</a>, <a href="{SITE_URL}/api/makaleler.json">makale tanıtımları</a>.</p></section>
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
    bag_dizini_kur()

    # Günün makalesi kuralı (6 Kasım 2026): yazarlarından en az biri Türkiye akademisi listesinde olmalı.
    # Henüz yayımlanmamış (bugünden sonraki) tanıtımlar denetlenir; uymayan varsa derleme uyarı verir.
    akademi_adlari_ = {tr_kucuk(p["ad"]) for p in (yaml.safe_load((CONTENT / "turkiye_akademisi.yaml").read_text(encoding="utf-8")) or {}).get("kisiler") or []}
    bugun_k = bugun()
    for m in items:
        if (m.get("gun") or "") >= bugun_k and not any(tr_kucuk(y.strip()) in akademi_adlari_ for y in re.split(r",| ve ", m.get("authors", ""))):
            print(f"UYARI: {m['gun']} günün makalesinin yazarı Türkiye akademisi listesinde değil: {m.get('authors')}", file=sys.stderr)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    tum_ogeler = list(items)
    items = gunleri_ata(items)
    yaz("", render_ana(items))
    yaz("gunun-makalesi", render_makaleler(items))
    yaz("guncel", yonlendirme(f"{SITE_URL}/gunun-makalesi/"))
    # Eski WordPress adresleri yeni sayfalara yönlendirilir
    for eski, yeni in {"terimler/kotuluk-problemi": "basliklar/kotuluk-problemi",  # terim fişi başlıkla birleştirildi (25.10.2026)
                       "ag/terimler/kotuluk-problemi": "ag/kotuluk-problemi",
                       "kotuluk-problemi": "basliklar/kotuluk-problemi", "dini-tecrube": "basliklar/dini-tecrube",
                       "tanrinin-varligi-problemi": "basliklar/tanrinin-varliginin-delilleri",
                       "category/din-felsefe-iliskisi": "basliklar"}.items():
        yaz(eski, yonlendirme(f"{SITE_URL}/{yeni}/"))
    for m in items:
        yaz(f"makale/{m['slug']}", render_makale(m))
    # Yarının makale sayfası ve paylaşım görseli bir gün önceden yayımlanır (bağlantı verilmez, arama motorlarına kapalı).
    # Gece derlemesi gecikse de paylaşım bağlantısı X tarafından ilk okunduğunda sayfa ve görsel hazır olur.
    from datetime import date, timedelta
    yarin = (date.fromisoformat(bugun()) + timedelta(days=1)).isoformat()
    for m in tum_ogeler:
        if m.get("gun") == yarin:
            yaz(f"makale/{m['slug']}", render_makale(m).replace("<head>", '<head>\n<meta name="robots" content="noindex">', 1))
            if f"makale/{m['slug']}" in SAYFALAR:  # site haritasına girmez
                SAYFALAR.remove(f"makale/{m['slug']}")
    yaz("basliklar", render_basliklar())
    for (t, k) in FIS:
        if t == "baslik":
            yaz(f"basliklar/{k}", render_baslik(k))
        else:
            yaz(f"{KLASOR[t]}/{k}", render_fis(t, k))
    for t in ("terim", "kisi"):
        yaz(KLASOR[t], render_dizin(t))
    yaz("eserler", render_eserler())
    if TEZ_DOSYA.exists():
        yaz("tezler", render_tezler())
    if KAVRAM_DOSYA.exists():
        yaz("kavram-tarihi", render_kavram_tarihi())
    yaz("dergiler", render_dergiler())
    for s_ in akademi_verisi():
        yaz(f"kisiler/akademi/{s_}", render_akademisyen(s_))
    yaz("ag", render_ag(items))
    ag_kimlikleri = {d["id"] for d in ag_tam(items)["dugumler"]}
    for (t, k) in list(FIS):
        if t in ("baslik", "terim", "kisi") and f"{t}/{k}" in ag_kimlikleri:
            yaz(ag_adresi(t, k).removeprefix(SITE_URL + "/").strip("/"), render_alt_ag(items, t, k))
    for s_ in akademi_verisi():
        if f"kisi-tr/{s_}" in ag_kimlikleri:
            yaz(ag_adresi("kisi-tr", s_).removeprefix(SITE_URL + "/").strip("/"), render_alt_ag(items, "kisi-tr", s_))
    yaz("hakkinda", page(f"Hakkında · {SITE_NAME}", ABOUT, "hakkinda", canonical=f"{SITE_URL}/hakkinda/"))

    (OUT / "api").mkdir()
    (OUT / "api" / "kutla.php").write_text(KUTLA_PHP, encoding="utf-8")
    (OUT / "api" / "makaleler.json").write_text(
        json.dumps([{**m, "url": entry_url(m)} for m in items], ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "api" / "onizleme.json").write_text(json.dumps(onizleme_verisi(items), ensure_ascii=False), encoding="utf-8")
    (OUT / "api" / "fisler.json").write_text(json.dumps(
        [{k: v for k, v in h.items() if not k.startswith("_")} | {"tur": t, "url": fis_url(t, kk), "metin": h["_govde"]}
         for (t, kk), h in FIS.items()], ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    # Site haritası ve robots.txt. Deneme yayınında (NOINDEX) sayfalar yine taranabilir ama "noindex" etiketi
    # yüzünden dizine eklenmez; yayına geçildiğinde yalnızca NOINDEX kapatılır.
    harita = "".join(f"<url><loc>{e(SITE_URL + '/' + (y + '/' if y else ''))}</loc></url>" for y in SAYFALAR
                     if AKADEMI_ACIK or not y.startswith(("kisiler/akademi/", "ag/kisiler/akademi/")))
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{harita}</urlset>\n', encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")

    now = format_datetime(datetime.now(timezone.utc))
    rss_items = "".join(f"""
<item>
<title>{e(m['title_tr'])}</title>
<link>{entry_url(m)}</link>
<guid>{entry_url(m)}</guid>
<pubDate>{format_datetime(datetime.strptime(m['gun'], '%Y-%m-%d').replace(tzinfo=timezone.utc))}</pubDate>
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
    try:
        from paylasim_gorseli import kart
        kart(OUT / "paylas" / "site.png", "dinfelsefesi.com.tr", "Din felsefesi için Türkçe başvuru kaynağı",
             "Başlıklar, terimler, düşünürler, eserler ve günün makalesi")
        for yol_, ust, bas, alt in dict.fromkeys(GORSELLER):
            if not (OUT / yol_).exists():
                kart(OUT / yol_, ust, bas, alt)
    except ImportError:
        print("uyarı: Pillow yok, paylaşım görselleri üretilmedi")
    (OUT / ".htaccess").write_text("""# dinfelsefesi.com.tr (durağan site)
# Eski WordPress döneminden kalan sunucu önbelleği kullanılmasın
<IfModule LiteSpeed>
CacheLookup off
</IfModule>
RewriteEngine On
RewriteCond %{HTTPS} off [OR]
RewriteCond %{HTTP_HOST} ^www\\. [NC]
RewriteRule ^ https://dinfelsefesi.com.tr%{REQUEST_URI} [L,R=301]
# Eski deneme adresi /yeni/... yeni yerine yönlendirilir
RewriteRule ^yeni/?(.*)$ /$1 [L,R=301]
ErrorDocument 404 /404.html
<Files ".yayin-ozeti">
  Require all denied
</Files>
AddDefaultCharset utf-8
<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresByType image/png "access plus 30 days"
  ExpiresByType application/javascript "access plus 7 days"
  ExpiresByType text/html "access plus 0 seconds"
  ExpiresByType application/json "access plus 0 seconds"
</IfModule>
# Sayfalar ve veri dosyaları her açılışta sunucuya sorulur; betikler sürüm ekiyle (?v=) yenilenir.
<IfModule mod_headers.c>
  <FilesMatch "\\.(html|json|xml)$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
</IfModule>
""", encoding="utf-8")
    (OUT / "404.html").write_text(page(f"Sayfa bulunamadı · {SITE_NAME}",
        f'<h1>Sayfa bulunamadı</h1><p class="giris">Aradığınız sayfa taşınmış ya da kaldırılmış olabilir. '
        f'<a href="{SITE_URL}/">Ana sayfaya</a> dönebilir ya da <a href="{SITE_URL}/basliklar/">başlıklara</a> göz atabilirsiniz.</p>'),
        encoding="utf-8")
    if (ROOT / "static" / "img" / "favicon.ico").exists():
        shutil.copy(ROOT / "static" / "img" / "favicon.ico", OUT / "favicon.ico")
    # IndexNow anahtarı: Bing ve Yandex'e değişen sayfaları bildirmek için (yükleme adımı kullanır)
    (OUT / "0b0b3770c369e042989bc277c26645c1.txt").write_text("0b0b3770c369e042989bc277c26645c1", encoding="utf-8")
    (OUT / "google08c007317a4ad095.html").write_text("google-site-verification: google08c007317a4ad095.html", encoding="utf-8")
    if (ROOT / "static").exists():
        shutil.copytree(ROOT / "static", OUT / "static")
    (OUT / ".nojekyll").write_text("")
    cname = ROOT / "CNAME"
    if cname.exists():
        shutil.copy(cname, OUT / "CNAME")
    print(f"{len(items)} makale, {len(FIS)} fiş, çıktı: {OUT}")


if __name__ == "__main__":
    main()
