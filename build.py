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


def govde(text: str, kendi=None) -> str:
    kullanilan = set()
    out = []
    for blok in re.split(r"\n\s*\n", (text or "").strip()):
        blok = blok.strip()
        if not blok:
            continue
        if blok.startswith("## "):
            out.append(f"<h2>{satir_ici(blok[3:])}</h2>")
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
/* Yerleşim: bir kitap sayfası. Fildişi kâğıt, mürekkep rengi yazı; vurgu rengi lâcivert,
   ikinci renk tezhip altını. Başlıklar içindekiler gibi, yan sütunlar hâşiye gibi. Tek tema (açık). */
:root{
  --ink:#2b2621;--ink-soft:#6a5f53;--rule:#e2d9c8;--paper:#f8f4ec;--panel:#f1eadc;--card:#fcfaf5;
  --accent:#2a4f7f;--accent-ink:#22426b;--accent-soft:#e7ecf2;--gold:#9a7428;--gold-soft:#f2e8d0;
  --display:"EB Garamond","Garamond","Georgia",serif;
  --serif:"Literata",Georgia,"Times New Roman",serif;
  --sans:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  --measure:66ch;
  color-scheme:light;
}
*{box-sizing:border-box}
html{font-size:16px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent-ink);text-decoration-thickness:1px;text-decoration-color:color-mix(in srgb,var(--accent) 35%,transparent);text-underline-offset:3px}
a:hover{text-decoration-color:currentColor}
a:hover{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.wrap{max-width:70rem;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.dar{max-width:46rem}
header.site{background:var(--paper);border-bottom:3px double var(--rule)}
header.site .wrap{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.6rem 2rem;padding-block:1.3rem 1.1rem}
.marka{text-decoration:none;color:var(--ink);display:flex;align-items:center;gap:.75rem}
.marka-yazi{display:flex;flex-direction:column;gap:.1rem}
.marka-logo{width:44px;height:44px;flex:none}
.marka b{font-family:var(--display);font-weight:500;font-size:1.75rem;line-height:1.05}
.marka small{order:2;font-style:italic;font-size:.86rem;color:var(--ink-soft)}
nav.ana{display:flex;flex-wrap:wrap;gap:.3rem 1.4rem;font-family:var(--display);font-size:1.04rem}
nav.ana a{color:var(--ink-soft);text-decoration:none;padding-block:.2rem;border-bottom:2px solid transparent}
nav.ana a:hover{color:var(--ink)}
nav.ana a[aria-current="page"]{color:var(--ink);border-bottom-color:var(--gold)}
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
.olcu{height:4px;background:var(--panel)}
.olcu span{display:block;height:100%;background:var(--accent)}
.altlar{list-style:none;padding:0;margin:.15rem 0 0;display:flex;flex-wrap:wrap;gap:.35rem}
.altlar li{font-family:var(--serif);font-size:.82rem;padding:.08rem .55rem;border:1px solid var(--rule);background:var(--paper)}
.altlar li.dolu{border-color:var(--accent);background:var(--accent-soft)}
.altlar li.plan .duz{color:var(--ink-soft)}
.ilgili{font-style:italic;font-size:.88rem;color:var(--ink-soft)}

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
.kart{background:var(--card);border:1px solid var(--rule);box-shadow:0 1px 0 var(--rule),0 12px 30px -24px rgba(60,40,10,.35);padding:1.6rem 1.8rem 1.3rem;min-width:0}
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
.baslik-gezinti ul{list-style:none;margin:0 0 1rem;padding:0;display:flex;flex-wrap:wrap;gap:.4rem}
.baslik-gezinti li{font-size:.92rem;padding:.12rem .65rem;border:1px solid var(--rule);background:var(--card);border-radius:999px}
.baslik-gezinti li.dolu{border-color:var(--accent);background:var(--accent-soft)}
.baslik-gezinti li.plan{color:var(--ink-soft)}
.baslik-gezinti a{text-decoration:none;color:var(--ink)}
.eser-bolum{border-top:1px solid var(--gold);padding-top:.4rem;margin-top:2rem;scroll-margin-top:1rem}
.eser-bolum h2{margin:.3rem 0 .6rem;font-size:1.4rem;font-weight:500;display:flex;align-items:baseline;gap:.7rem}
.eser-bolum h2 a,.eser-bolum h3 a{color:var(--ink);text-decoration:none}
.eser-bolum h3{font-family:var(--display);font-style:italic;font-size:1.15rem;color:var(--gold);margin:1.2rem 0 .3rem;font-weight:500}
.eser-bolum h3 a{color:var(--accent-ink)}
.aciklama-kisa{font-size:1rem;color:var(--ink-soft);margin:0 0 .7rem;max-width:62ch}
.sekmeler{margin-top:.4rem}
.sekmeler button{font-size:1rem;padding:.45rem 1.1rem}
.sekme-bolum{margin-top:1rem}
.k-ara{display:flex;align-items:center;gap:.6rem;font-style:italic;font-size:.95rem;color:var(--ink-soft);margin:.8rem 0 .9rem}
.k-ara input{font:inherit;font-style:normal;font-size:.98rem;color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:999px;padding:.4rem .9rem;width:min(100%,22rem)}
.k-ara input:focus{outline:2px solid var(--accent);outline-offset:1px}
.tablo-kap{overflow-x:auto}
table.kisiler{width:100%;border-collapse:collapse;font-size:.95rem}
button.sirala{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:.3rem}
button.sirala:hover{color:var(--ink)}
button.sirala:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
th[aria-sort="ascending"] button.sirala,th[aria-sort="descending"] button.sirala{color:var(--ink)}
.ok::after{content:"↕";opacity:.35;font-size:.9em}
th[aria-sort="ascending"] .ok::after{content:"▲";opacity:1;font-size:.7em}
th[aria-sort="descending"] .ok::after{content:"▼";opacity:1;font-size:.7em}
table.kisiler th{text-align:left;font-style:italic;font-size:.95rem;color:var(--ink-soft);font-weight:400;padding:.4rem .7rem .4rem 0;border-bottom:1px solid var(--gold)}
table.kisiler td{padding:.55rem .7rem .55rem 0;border-bottom:1px solid var(--rule);vertical-align:top}
table.kisiler td.k-ad{font-weight:600}
table.kisiler td.k-yok{font-style:italic;font-size:.9rem;white-space:nowrap}
table.kisiler tbody tr:hover{background:var(--panel)}
.emekli{display:inline-block;font-style:italic;font-size:.8rem;font-weight:400;color:var(--gold);border:1px solid currentColor;padding:0 .35rem;border-radius:2px;margin-left:.3rem}
.gizli{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
ul.eserler{list-style:none;margin:0;padding:0;columns:2 26rem;column-gap:2.5rem}
ul.eserler li{break-inside:avoid;padding:.5rem 0;border-bottom:1px solid var(--rule)}
.eser-ad{font-weight:600;color:var(--ink);text-decoration:none;font-size:.98rem;line-height:1.4}
.eser-ad:hover{color:var(--accent)}
.eser-bilgi a.dis{font-weight:600}
.rozet{display:inline-block;font-family:var(--sans);font-style:normal;font-size:.68rem;font-weight:600;letter-spacing:.04em;color:var(--ink-soft);border:1px solid var(--rule);background:var(--card);padding:.02rem .42rem;border-radius:6px;vertical-align:.12em;margin-left:.35rem}
.rozet.ae-rozet{color:var(--accent-ink);background:var(--accent-soft);border-color:transparent;letter-spacing:0}
.ae{display:inline-block;font-family:var(--sans);font-size:.72rem;font-weight:600;color:var(--accent-ink);background:var(--accent-soft);padding:.02rem .4rem;border-radius:2px}
.eser-bilgi{display:block;font-size:.9rem;color:var(--ink-soft);margin-top:.15rem}
footer.site{border-top:3px double var(--rule);background:var(--paper);color:var(--ink-soft);font-style:italic;font-size:.82rem}
footer.site .wrap{padding-block:1rem 1.3rem;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:.3rem 2rem}
footer.site p{margin:0}
footer.site a{color:var(--ink-soft)}
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
.onizleme{position:absolute;z-index:50;width:min(22rem,calc(100vw - 16px));background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:.8rem 1rem .85rem;box-shadow:0 18px 40px -24px rgba(60,40,10,.5);pointer-events:none;font-size:.92rem;line-height:1.45}
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
.nokta{display:inline-block;width:.7em;height:.7em;border-radius:50%;margin-right:.45em;vertical-align:.02em}
.ag-sifirla{font:inherit;font-style:italic;font-size:.95rem;color:var(--accent-ink);background:none;border:0;cursor:pointer;text-decoration:underline;text-underline-offset:3px;padding:0}
.ag-kap{position:relative;border:1px solid var(--rule);border-radius:14px;background:var(--card);overflow:hidden}
.ag-tuval{height:min(72vh,700px);min-height:420px;cursor:grab}
.ag-tuval:active{cursor:grabbing}
.ag-tuval svg{display:block;width:100%;height:100%}
.ag-baglar line{stroke:#cdbfa6;stroke-width:1.1px;transition:opacity .2s}
.ag-baglar line.vurgu{stroke:#8a6a2c;stroke-width:1.8px}
.ag-baglar line.soluk{opacity:.18}
.ag-dugum{cursor:pointer;transition:opacity .2s}
.ag-dugum circle{stroke:var(--card);stroke-width:2px}
.ag-dugum.secili circle{stroke:var(--ink);stroke-width:2.5px}
.ag-dugum:focus-visible{outline:none}
.ag-dugum:focus-visible circle{stroke:var(--accent);stroke-width:3px}
.ag-dugum text{font-family:var(--serif);fill:var(--ink);text-anchor:middle;paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round;pointer-events:none;opacity:0;transition:opacity .2s}
.ag-dugum text.goster{opacity:1}
.ag-dugum.soluk{opacity:.18}
.ag-dugum.gizli,.ag-baglar line.gizli{display:none}
.ag-panel{position:absolute;top:1rem;right:1rem;width:min(22rem,calc(100% - 2rem));max-height:calc(100% - 2rem);overflow:auto;background:var(--paper);border:1px solid var(--rule);border-radius:12px;padding:1.1rem 1.2rem 1rem;box-shadow:0 14px 34px -22px rgba(60,40,10,.45)}
.ag-panel h2{margin:0 2rem .4rem 0;font-size:1.45rem}
.ag-panel .ag-aciklama{margin:0 0 .6rem;font-size:.95rem;color:var(--ink-soft)}
.ag-panel .ag-ac{font-style:italic}
.ag-panel h3{font-family:var(--display);font-style:italic;font-weight:500;font-size:1.05rem;color:var(--gold);margin:1rem 0 .3rem}
.ag-panel ul{list-style:none;margin:0;padding:0;display:grid;gap:.15rem}
.ag-panel li button{font:inherit;font-size:.93rem;text-align:left;background:none;border:0;padding:.15rem 0;color:var(--accent-ink);cursor:pointer}
.ag-panel li button:hover{text-decoration:underline}
.ag-kapat{position:absolute;top:.5rem;right:.6rem;font:inherit;font-size:1.5rem;line-height:1;background:none;border:0;color:var(--ink-soft);cursor:pointer;padding:.2rem .4rem}
.ag-ipucu{position:absolute;left:1rem;bottom:.6rem;margin:0;font-style:italic;font-size:.85rem;color:var(--ink-soft);pointer-events:none}
.ag-git{display:inline-block;margin-top:1rem;font-style:italic}
/* Ana sayfa: karşılama, okumaya başlangıç, içindekiler */
.karsilama{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:2rem 4rem;align-items:center;padding-block:1rem 1rem}
.karsilama h1{font-size:2.55rem;margin-bottom:.8rem}
.karsilama p{font-size:1.04rem;line-height:1.5;color:var(--ink-soft);margin:0 0 .8rem}
.karsilama .durum-satiri{font-style:italic;font-size:.98rem}
.karsilama .karsilama-git{display:flex;flex-wrap:wrap;gap:.4rem 1.6rem;font-family:var(--display);font-size:1.2rem;margin-top:1.1rem}
.susleme{display:flex;align-items:center;gap:1rem;color:var(--gold);margin:2.4rem 0 1.4rem}
.susleme::before,.susleme::after{content:"";flex:1;height:1px;background:var(--rule)}
.susleme span{font-family:var(--display);font-size:1.3rem;line-height:1}
.okuma{background:var(--card);border:1px solid var(--rule);padding:1.7rem 1.9rem 1.5rem;box-shadow:0 14px 34px -28px rgba(60,40,10,.4)}
.okuma .ust-etiket{margin-bottom:.4rem}
.okuma h2{margin:0 0 .6rem;font-size:1.6rem}
.okuma h2 a{color:var(--ink);text-decoration:none}
.okuma .ozet{font-style:italic;color:var(--ink-soft);margin:0}
.okuma .alinti{margin:0;font-size:.97rem;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}
.okuma .alinti::first-letter{font-family:var(--display);float:left;font-size:3.4em;line-height:.82;padding:.06em .1em 0 0;color:var(--gold)}
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
.icindekiler li.kume-ad{display:block;padding:1.2rem 0 .2rem;border-bottom:1px solid var(--gold);break-after:avoid;font-style:italic;color:var(--gold);font-size:.95rem}
.icindekiler li.kume-ad:first-child{padding-top:0}
h2.kume-ad{font-family:var(--display);font-style:italic;font-weight:500;font-size:1.15rem;color:var(--gold);margin:2rem 0 .7rem;padding-bottom:.25rem;border-bottom:1px solid var(--rule)}
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
  .ag-panel{position:static;width:auto;max-height:none;border-radius:0;border-width:1px 0 0;box-shadow:none}
  .ag-tuval{height:62vh;min-height:360px}
  .ag-ipucu{display:none}
  table.kisiler thead{display:block}
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
        ("eserler", "Eserler"), ("ag", "Ağ"), ("hakkinda", "Hakkında")]


GORSELLER = []   # (dosya yolu, üst yazı, başlık, alt yazı): derleme sonunda üretilir


def paylasim_gorseli(ad_: str, ust: str, baslik_: str, alt: str = "") -> str:
    GORSELLER.append((f"paylas/{ad_}.png", ust, baslik_, alt))
    return f"{SITE_URL}/paylas/{ad_}.png"


def page(title: str, body: str, aktif: str = "", desc: str = SITE_TAGLINE, canonical: str = "",
         gorsel: str = "", og_tur: str = "website") -> str:
    canon = f'<link rel="canonical" href="{e(canonical)}">' if canonical else ""
    og_baslik = title.removesuffix(f" · {SITE_NAME}")
    og = (f'<meta property="og:site_name" content="{e(SITE_NAME)}"><meta property="og:locale" content="tr_TR">'
          f'<meta property="og:type" content="{og_tur}"><meta property="og:title" content="{e(og_baslik)}">'
          f'<meta property="og:description" content="{e(desc)}">'
          + (f'<meta property="og:url" content="{e(canonical)}">' if canonical else "")
          + f'<meta property="og:image" content="{e(gorsel or SITE_URL + "/paylas/site.png")}">'
          f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
          f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@{X_HESABI}">'
          f'<meta name="google-site-verification" content="google08c007317a4ad095">')
    robots = '<meta name="robots" content="noindex,nofollow">' if NOINDEX else ""
    menu = "".join(
        f'<a href="{SITE_URL}/{k + "/" if k else ""}"{" aria-current=\"page\"" if k == aktif else ""}>{a}</a>' for k, a in MENU)
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
{og}
<link rel="icon" href="{SITE_URL}/static/img/favicon.svg" type="image/svg+xml">
<link rel="icon" href="{SITE_URL}/favicon.ico" sizes="48x48">
<link rel="apple-touch-icon" href="{SITE_URL}/static/img/apple-touch-icon.png">
<meta name="theme-color" content="#f8f4ec">
<link rel="alternate" type="application/rss+xml" title="{e(SITE_NAME)}" href="{SITE_URL}/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;1,400;1,500&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
<script src="{SITE_URL}/static/js/onizleme.js" data-veri="{SITE_URL}/api/onizleme.json" defer></script>
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
  <p>© {YIL} <a href="{SITE_URL}/">dinfelsefesi.com.tr</a> · Din felsefesi için Türkçe başvuru kaynağı</p>
  <p>Düzeltme ve öneriler için: <a href="mailto:{ILETISIM}">{ILETISIM}</a> · X: <a href="https://x.com/{X_HESABI}" rel="noopener">@{X_HESABI}</a></p>
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


GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def bugun() -> str:
    from zoneinfo import ZoneInfo
    return os.environ.get("BUGUN") or datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()


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
    <p class="orij">{e(m['title_en'])}{rozetler(m)}</p>
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
  <p class="paylas">{paylas_dugmesi(m)}</p>
</article>{ATIF_JS}"""
    gorsel = paylasim_gorseli(f"makale-{m['slug']}", f"Günün makalesi · {tr_date(m['gun'])}", m["title_tr"],
                              f"{m.get('authors', '')} · {m.get('journal', '')}{', ' + str(m['year']) if m.get('year') else ''}")
    return page(f"{m['title_tr']} · {SITE_NAME}", body, "", desc=m["lead"], canonical=entry_url(m), gorsel=gorsel, og_tur="article")


# ---------------------------------------------------------------- başlıklar

# Ana başlıklar bu tematik kümelerde gösterilir. Kümeler yalnızca görsel ayraçtır, kendi sayfaları yoktur.
KUMELER = [("tanri", "Tanrı"), ("bilgi-dil", "Bilgi ve dil"), ("insan-deger", "İnsan ve değer"),
           ("din-bilim-kultur", "Din, bilim ve kültür"), ("disiplin", "Disiplin")]


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
    metin = govde(h["_govde"], ("baslik", k))
    if not metin:
        metin = ('<p class="giris">Başlığın tanıtım metni henüz yazılmadı. '
                 'Başlığa bağlı fişler yandaki listede yer almaktadır.</p>' if b else
                 '<p class="giris">Bu başlık için henüz fiş eklenmedi.</p>')
    body = f"""
<p class="yol">{yol(k)}</p>
<h1>{e(h['ad'])}{taslak_etiketi(h)}</h1>
<p class="giris">{satir_ici(h.get('ozet'))}<span class="say ayri">{sayim_metni(b)}</span></p>
<div class="fis-duzen">
  <div class="metin">{metin}{f'<h2>Tartışma soruları</h2><ol class="sorular">{sorular}</ol>' if sorular else ''}{atif_kutusu(h['ad'], fis_url("baslik", k), h.get("guncelleme"))}</div>
  <aside class="yan">{yan or '<h2>Fişler</h2><p>Henüz fiş yok.</p>'}{ag_baglantisi("baslik", k)}</aside>
</div>{ATIF_JS}"""
    gorsel = paylasim_gorseli(f"baslik-{k}", "Başlık", h["ad"], "")
    return page(f"{h['ad']} · {SITE_NAME}", body, "basliklar", desc=h.get("ozet") or SITE_TAGLINE,
                canonical=fis_url("baslik", k), gorsel=gorsel, og_tur="article")


def render_basliklar() -> str:
    body = ('<p class="ust-etiket">Başlıklar</p><h1>Din felsefesinin başlıkları</h1>'
            '<p class="giris">Ana başlıklar din felsefesi literatürünün problem alanlarını gösterir ve beş tematik küme altında sıralanır. '
            'Çubuklar her başlığa bağlı fiş sayısını, çerçeveli alt başlıklar içeriği hazır olanları gösterir.</p>'
            + harita_html())
    return page(f"Başlıklar · {SITE_NAME}", body, "basliklar", canonical=f"{SITE_URL}/basliklar/")


# ---------------------------------------------------------------- fiş sayfaları

def satir(etiket, icerik) -> str:
    return f"<div><dt>{etiket}</dt><dd>{icerik}</dd></div>" if icerik else ""


def atif_kutusu(baslik_, url, guncelleme=None) -> str:
    gun = f" Son güncelleme {tr_date(str(guncelleme))}." if guncelleme else ""
    return (f'<div class="atif"><p class="ust-etiket">Atıf:</p>'
            f'<p class="atif-metin">"{e(baslik_)}". <i>dinfelsefesi.com.tr</i>, ed. {e(EDITOR)}.{gun} '
            f'Erişim <span class="atif-erisim">[tarih]</span>. {e(url)}</p>'
            f'<button type="button" class="atif-kopyala">kopyala</button></div>')


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
    return f'<a class="ag-git" href="{SITE_URL}/ag/?odak={tur}/{k}">İlişki ağında göster →</a>'


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
    <p class="imza">{e(h.get('imza'))} · son güncelleme {tr_date(str(h['guncelleme']))}</p>{atif_kutusu(ad(tur, h), fis_url(tur, k), h.get("guncelleme")) if tur != "eser" else ""}</article>
  {f'<aside class="yan">{yan}</aside>' if yan else ''}
</div>{ATIF_JS}"""
    gorsel = paylasim_gorseli(f"{tur}-{k}", TUR_AD[tur], ad(tur, h), str(h.get("ingilizce") or h.get("donem") or ""))
    return page(f"{ad(tur, h)} · {SITE_NAME}", body, KLASOR[tur], desc=desc, canonical=fis_url(tur, k), gorsel=gorsel, og_tur="article")


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
YOK_PROFIL = "https://akademik.yok.gov.tr/AkademikArama/AkademisyenGorevOgrenimBilgileri?islem=direct&authorId="


UNVAN_SIRA = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2, "Öğr. Gör.": 3, "Arş. Gör.": 4}


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
        ad_html = bag("kisi", kim) if kim and ("kisi", kim) in FIS else e(p["ad"])
        durum = ' <span class="emekli">Emekli</span>' if p.get("durum") == "emekli" else ""
        yok = f'<a class="dis" href="{YOK_PROFIL}{e(p["yok"])}" rel="noopener" target="_blank">YÖK</a>' if p.get("yok") else ""
        ara = tr_kucuk(" ".join([p["ad"], p.get("universite", ""), p.get("fakulte", "")]))
        satirlar.append(f'<tr data-ara="{e(ara)}" data-unvan="{UNVAN_SIRA.get(p.get("unvan"), 9)}"><td class="k-ad" data-etiket="Ad Soyad">{ad_html}</td>'
                        f'<td data-etiket="Unvan">{e(p.get("unvan"))}{durum}</td>'
                        f'<td data-etiket="Üniversite">{e(p.get("universite"))}</td>'
                        f'<td data-etiket="Fakülte">{e(p.get("fakulte"))}</td><td class="k-yok">{yok}</td></tr>')
    tarih = tr_date(str(veri.get("tarih"))) if veri.get("tarih") else ""
    ust = (f'<p class="aciklama-kisa">Türkiye\'deki üniversitelerde din felsefesi alanında çalışan öğretim elemanları. '
           f'Liste, YÖK Akademik\'te bilim alanı olarak Din Felsefesi\'ni işaretlemiş ya da Felsefe ve Din Bilimleri alanında '
           f'ilk anahtar kelimesi Din Felsefesi olan akademisyenlerden oluşmaktadır'
           f'{" (" + tarih + ")" if tarih else ""}. Unvan ve kurum bilgileri YÖK\'teki kayda göredir.</p>'
           '<label class="k-ara"><span>Ara</span><input type="search" id="kisi-ara" placeholder="Ad, üniversite ya da fakülte" autocomplete="off"></label>')
    tablo = ('<div class="tablo-kap"><table class="kisiler"><thead><tr>'
             + "".join(f'<th aria-sort="{"ascending" if i == 0 else "none"}"><button type="button" class="sirala" data-sutun="{i}">{b}<span class="ok" aria-hidden="true"></span></button></th>'
                       for i, b in enumerate(["Ad Soyad", "Unvan", "Üniversite", "Fakülte"])) +
             f'<th><span class="gizli">YÖK profili</span></th></tr></thead><tbody>{"".join(satirlar)}</tbody></table></div>'
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
    var kucuk=function(s){return s.replace(/I/g,'ı').replace(/İ/g,'i').toLowerCase();};
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
            f'<nav class="baslik-gezinti" aria-label="Başlıklar"><ul>{"".join(gezinti)}</ul></nav>'
            f'{tur_secici(eserler)}'
            + ("".join(bolumler) or '<p class="giris">Henüz eser fişi eklenmedi.</p>'))
    return page(f"Eserler · {SITE_NAME}", body + TUR_SECICI_JS, "eserler", canonical=f"{SITE_URL}/eserler/")


# ---------------------------------------------------------------- ilişki ağı

AG_TURLER = [("baslik", "Başlık", "#2a4f7f"), ("terim", "Terim", "#a5802f"), ("kisi", "Kişi", "#3f6b4f"),
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
        dugumler.append({"id": mid, "ad": m["title_tr"], "tur": "makale", "turAd": tur_ad["makale"],
                         "url": entry_url(m), "aciklama": m.get("lead", "")})
        baglar |= {(mid, x) for x in hedefler}
    return {"turler": [{"kod": k, "ad": a, "renk": r} for k, a, r in AG_TURLER],
            "dugumler": dugumler, "baglar": sorted(baglar)}


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
    return v


def render_ag(items) -> str:
    v = ag_verisi(items)
    say = {k: sum(1 for d in v["dugumler"] if d["tur"] == k) for k, _, _ in AG_TURLER}
    dugmeler = "".join(f'<button type="button" data-tur="{k}" aria-pressed="true"><span class="nokta" style="background:{r}"></span>{e(a)} <span class="say">{say[k]}</span></button>'
                       for k, a, r in AG_TURLER if say[k])
    veri = json.dumps(v, ensure_ascii=False).replace("</", "<\\/")
    body = f"""<p class="ust-etiket">Ağ</p><h1>İlişki ağı</h1>
<p class="giris">Başlıklar, terimler, kişiler, eserler ve güncel makaleler arasındaki bağlantılar. Noktanın büyüklüğü bağlantı sayısını gösterir. Üzerine gelindiğinde komşuları belirginleşir, tıklandığında ayrıntıları açılır.</p>
<div class="ag-arac">
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
<script src="{SITE_URL}/static/js/ag.js"></script>"""
    return page(f"İlişki ağı · {SITE_NAME}", body, "ag", canonical=f"{SITE_URL}/ag/")


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
    adres = f"https://x.com/intent/post?text={quote(metin)}&url={quote(entry_url(m))}&via={X_HESABI}"
    return f'<a class="x-paylas" href="{e(adres)}" target="_blank" rel="noopener">X\'te paylaş</a>'


def gunun_makalesi_html(items) -> str:
    if not items:
        return okuma_baslangici()
    m = items[0]
    return f"""<aside class="okuma gunun" aria-label="Günün makalesi">
  <p class="ust-etiket">Günün makalesi · {e(gun_metni(m['gun']))}</p>
  <h2><a href="{entry_url(m)}">{e(m['title_tr'])}</a></h2>
  <p class="orij">{e(m['title_en'])}{rozetler(m)}</p>
  <p class="kunye">{e(m['authors'])} · {e(m['journal'])}{', ' + e(m['year']) if m.get('year') else ''}</p>
  <p class="alinti">{e(m['lead'])}</p>
  <p class="gunun-git"><a href="{entry_url(m)}">Tanıtımı okuyun →</a> <a href="{SITE_URL}/gunun-makalesi/">Önceki günlerin makaleleri →</a> {paylas_dugmesi(m)}</p>
</aside>"""


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
  <p>Din felsefesinin temel problemleri, terimleri, düşünürleri ve eserleri birbirine bağlı fişlerle sunulmaktadır. Her ana başlık bir okuma metniyle açılır. Terimler, kişiler ve eserler bu metinlere bağlanır, yeni çalışmalar da düzenli olarak tanıtılır.</p>
  <p class="durum-satiri">{durum}</p>
  <p class="karsilama-git"><a href="{SITE_URL}/basliklar/">Başlıklara göz atın →</a> <a href="{SITE_URL}/ag/">İlişki ağını açın →</a></p>
  </div>
  {gunun_makalesi_html(items)}
</section>
<div class="susleme" aria-hidden="true"><span>❦</span></div>
<div class="bolum-baslik"><h2>Başlıklar</h2><a href="{SITE_URL}/basliklar/">Başlık haritası</a></div>
{icindekiler_html()}
<div class="susleme" aria-hidden="true"><span>❦</span></div>
{f'''<div class="bolum-baslik"><h2>Önceki günlerin makaleleri</h2><a href="{SITE_URL}/gunun-makalesi/">Bütün günler</a></div>
{"".join(makale_satiri(m) for m in items[1:5])}''' if len(items) > 1 else ""}
"""
    gorsel = (paylasim_gorseli(f"makale-{items[0]['slug']}", f"Günün makalesi · {tr_date(items[0]['gun'])}", items[0]["title_tr"],
                               f"{items[0].get('authors', '')} · {items[0].get('journal', '')}") if items else "")
    return page(SITE_NAME, body, "", canonical=SITE_URL + "/", gorsel=gorsel)


ABOUT = f"""
<article class="hakkinda">
  <h1>Hakkında</h1>
  <p class="hk-giris">{SITE_NAME}, din felsefesine dair Türkçe bir başvuru kaynağı olarak hazırlanmaktadır. Sitede din felsefesi literatürünün ana başlıkları, bu başlıklara bağlı terimler, düşünürler ve eserler birbirine bağlantılı fişler hâlinde yer almaktadır. Ayrıca her gün din felsefesi dergilerinde yayımlanmış bir makale Türkçe tanıtımıyla öne çıkarılmaktadır. Tanıtımlar makalenin iddiasını, yöntemini ve literatürdeki yerini aktarır, makalenin yerine geçmez. Her kayıtta özgün metne bağlantı bulunur.</p>
  <div class="hk-izgara">
    <section><h2>Editörlük</h2><p>{EDITOR}, Erciyes Üniversitesi İlahiyat Fakültesi, Din Felsefesi Anabilim Dalı.</p></section>
    <section><h2>Atıf</h2><p>Başlık, terim ve kişi fişlerinin sonunda o sayfaya özel bir atıf satırı yer almaktadır. Eser fişlerinde ve makale tanıtımlarında eserin kendi künyesine atıf yapılması önerilir. Sitenin atıf biçimi: "Fişin adı". <i>dinfelsefesi.com.tr</i>, ed. {EDITOR}. Son güncelleme. Erişim tarihi. Adres.</p></section>
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

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    items = gunleri_ata(items)
    yaz("", render_ana(items))
    yaz("gunun-makalesi", render_makaleler(items))
    yaz("guncel", yonlendirme(f"{SITE_URL}/gunun-makalesi/"))
    # Eski WordPress adresleri yeni sayfalara yönlendirilir
    for eski, yeni in {"kotuluk-problemi": "basliklar/kotuluk-problemi", "dini-tecrube": "basliklar/dini-tecrube",
                       "tanrinin-varligi-problemi": "basliklar/tanrinin-varliginin-delilleri",
                       "category/din-felsefe-iliskisi": "basliklar"}.items():
        yaz(eski, yonlendirme(f"{SITE_URL}/{yeni}/"))
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
    yaz("ag", render_ag(items))
    yaz("hakkinda", page(f"Hakkında · {SITE_NAME}", ABOUT, "hakkinda", canonical=f"{SITE_URL}/hakkinda/"))

    (OUT / "api").mkdir()
    (OUT / "api" / "makaleler.json").write_text(
        json.dumps([{**m, "url": entry_url(m)} for m in items], ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "api" / "onizleme.json").write_text(json.dumps(onizleme_verisi(items), ensure_ascii=False), encoding="utf-8")
    (OUT / "api" / "fisler.json").write_text(json.dumps(
        [{k: v for k, v in h.items() if not k.startswith("_")} | {"tur": t, "url": fis_url(t, kk), "metin": h["_govde"]}
         for (t, kk), h in FIS.items()], ensure_ascii=False, indent=1, default=str), encoding="utf-8")

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
AddDefaultCharset utf-8
<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresByType image/png "access plus 30 days"
  ExpiresByType application/javascript "access plus 7 days"
</IfModule>
""", encoding="utf-8")
    (OUT / "404.html").write_text(page(f"Sayfa bulunamadı · {SITE_NAME}",
        f'<h1>Sayfa bulunamadı</h1><p class="giris">Aradığınız sayfa taşınmış ya da kaldırılmış olabilir. '
        f'<a href="{SITE_URL}/">Ana sayfaya</a> dönebilir ya da <a href="{SITE_URL}/basliklar/">başlıklara</a> göz atabilirsiniz.</p>'),
        encoding="utf-8")
    if (ROOT / "static" / "img" / "favicon.ico").exists():
        shutil.copy(ROOT / "static" / "img" / "favicon.ico", OUT / "favicon.ico")
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
