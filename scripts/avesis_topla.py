#!/usr/bin/env python3
"""Türkiye akademisi listesindeki kişilerin AVESİS (üniversite akademik veri sistemi) yayın listelerini toplar.

Girdi: content/turkiye_akademisi.yaml, data/avesis/kurumlar.yaml (üniversite -> alan adı adayları),
       data/avesis/profiller.yaml (isteğe bağlı, elle bildirilen profil adresleri: kişi adı -> tam adres)
Çıktı: data/avesis/yayinlar.json  kişi adı -> {profil, yayinlar: [{bolum, baslik, yazarlar, kaynak, yil, url, doi}]}
       data/avesis/kurum_durumu.json  üniversite -> çalışan AVESİS adresi ya da boş

Profil adresi kişinin adından türetilen birkaç adayla denenir (ör. abdullahakgul, abdullah.akgul); sayfa başlığındaki
ad listedeki adla birebir uyuşmazsa profil kabul edilmez. Önceki çalıştırmada bulunan profiller yeniden aranmaz.

Kullanım:
  python3 scripts/avesis_topla.py
"""
import json
import re
import sys
import time
from html import unescape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VERI = ROOT / "data" / "avesis"
sys.path.insert(0, str(ROOT / "scripts"))
import urllib.request  # noqa: E402

from orcid_topla import UA, al  # noqa: E402

UNVANLAR = r"(Prof\.|Doç\.|Dr\.|Öğr\.|Üyesi|Arş\.|Gör\.|Okt\.|Uzm\.)"


def ad_anahtari(s: str) -> str:
    s = (s or "").replace("İ", "i").replace("I", "ı").lower().translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    return re.sub(r"[^a-z]+", " ", s).strip()


def adaylar(ad: str) -> list:
    p = ad_anahtari(ad).split()
    out = ["".join(p), ".".join(p), "".join([p[0], p[-1]]), f"{p[0]}.{p[-1]}", "-".join(p)]
    return list(dict.fromkeys(x for x in out if x))


TANI = {"kurum": {}, "site_haritasi": {}, "bulunamayan": {}}


def dene(url: str):
    """(gövde, hata) çifti; hata ayıklama için hatanın kendisi de döner."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            return r.read().decode("utf-8", "replace"), ""
    except Exception as ex:  # noqa: BLE001
        return "", f"{type(ex).__name__}: {ex}"[:200]


def kurum_adresi(u: str, alanlar) -> str:
    hatalar = []
    for a in alanlar:
        for yol in ("/robots.txt", "/"):
            govde, hata = dene(f"https://avesis.{a}{yol}")
            time.sleep(0.5)
            if govde and ("User-agent" in govde or "AVES" in govde):
                return f"https://avesis.{a}"
            hatalar.append(f"avesis.{a}{yol}: {hata or 'AVESİS sayfası değil'}")
    TANI["kurum"][u] = hatalar
    return ""


_SITEMAP = {}


def sitemap_kullanicilari(kok: str) -> set:
    """Kurumun site haritasındaki tek parçalı adresler (kişi profilleri); kurum başına bir kez okunur."""
    if kok in _SITEMAP:
        return _SITEMAP[kok]
    out = set()
    dizin = al(kok + "/sitemap_index.xml", deneme=1) or al(kok + "/sitemap.xml", deneme=1) or ""
    haritalar = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", dizin)
    alt = [h for h in haritalar if h.endswith(".xml")]
    print(f"  {kok}: site haritası {len(alt)} parça: {', '.join(h.rsplit('/', 1)[-1] for h in alt[:12])}")
    secili = [h for h in alt if re.search(r"user|person|kisi|profil|akademisyen|researcher|people", h, re.I)] or alt
    for h in secili[:40]:
        govde = al(h, deneme=1) or ""
        time.sleep(0.5)
        for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", govde):
            m = re.match(re.escape(kok) + r"/([A-Za-z0-9._-]+)/?$", u.strip())
            if m:
                out.add(m.group(1))
    if not alt:
        out |= {m.group(1) for u in haritalar for m in [re.match(re.escape(kok) + r"/([A-Za-z0-9._-]+)/?$", u)] if m}
    print(f"  {kok}: {len(out)} profil adresi")
    TANI["site_haritasi"][kok] = {"parca": [h.rsplit("/", 1)[-1] for h in alt][:30], "profil": len(out)}
    _SITEMAP[kok] = out
    return out


def sitemap_adaylari(kok: str, ad: str) -> list:
    p = ad_anahtari(ad).split()
    ilk, son = p[0], p[-1]
    # kullanıcı adında soyadı geçmeli; ad ya tam ya da baş harfiyle (ör. racar, msrecber) yer almalı
    tam = [u for u in sorted(sitemap_kullanicilari(kok)) if son in u.lower() and any(x in u.lower() for x in p[:-1])]
    bas = [u for u in sorted(sitemap_kullanicilari(kok)) if son in u.lower() and u.lower()[:1] == ilk[:1] and u not in tam]
    return tam + bas


def profil_dogrula(adres: str, ad: str) -> bool:
    html = al(adres, deneme=1)
    time.sleep(0.7)
    if not html:
        return False
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if not m or "AVESİS" not in unescape(m.group(1)) and "AVESIS" not in unescape(m.group(1)):
        return False
    bas = unescape(m.group(1)).split("|")[0]
    bas = re.sub(UNVANLAR, " ", bas)
    return ad_anahtari(bas) == ad_anahtari(ad)


def metin(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def yayinlar(html: str, kok: str) -> list:
    """Yayın sayfasındaki bölümler (Makaleler, Bildiriler, Kitaplar...) ve her bölümdeki yayınlar."""
    olaylar = [(m.start(), "bolum", metin(m.group(1))) for m in re.finditer(r'<div class="item-head">\s*<span>([^<]+)</span>', html)]
    olaylar += [(m.start(), "yayin", m.start()) for m in re.finditer(r'<div class="pub-item', html)]
    if not any(t == "yayin" for _, t, _ in olaylar):  # özgeçmiş biçimli tema: bölümler h2, yayınlar cv-item
        olaylar = [(m.start(), "bolum", metin(m.group(1))) for m in
                   re.finditer(r'<div class="cv-section-title">\s*<h2[^>]*>([^<]+)</h2>', html)]
        olaylar += [(m.start(), "cv", m.start()) for m in re.finditer(r'<div class="cv-item"', html)]
    olaylar.sort()
    out, bolum = [], ""
    for i, (konum, tur, deger) in enumerate(olaylar):
        if tur == "bolum":
            bolum = deger
            continue
        son = olaylar[i + 1][0] if i + 1 < len(olaylar) else len(html)
        parca = html[konum:son]
        if tur == "cv":
            b = re.search(r'<a[^>]*href="(/yayin/[^"]+)"[^>]*>\s*<h3>.*?<strong>(.*?)</strong>', parca, re.S)
            if not b:
                continue
            h4 = re.search(r"<h4>(.*?)</h4>", parca, re.S)
            yazarlar = [metin(a) for a in re.findall(r"<a class='authorsRichText'[^>]*>(.*?)</a>", h4.group(1) if h4 else "", re.S)]
            h5 = re.search(r"<h5>(.*?)</h5>", parca, re.S)
            ic = re.sub(r'<span style="margin-left:5px">.*?</a>\s*</span>', " ", h5.group(1) if h5 else "", flags=re.S)
            kaynak = re.sub(r"\s+,", ",", metin(ic))
            donem = re.search(r'<p class="period">\s*(\d{4})', parca)
            yil = donem.group(1) if donem else (re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", kaynak) or [""])[-1]
            doi = (re.findall(r'href="https?://(?:dx\.)?doi\.org/([^"]+)"', parca) or [""])[0]
            out.append({"bolum": bolum, "baslik": metin(b.group(2)), "yazarlar": yazarlar, "kaynak": kaynak, "yil": yil,
                        "url": kok + b.group(1), "doi": unescape(doi)})
            continue
        b = re.search(r'<h3 class="title">\s*<a[^>]*href="([^"]+)"[^>]*>.*?<strong>(.*?)</strong>', parca, re.S)
        if not b:
            continue
        atiflar = re.findall(r'<div class="citation"[^>]*>(.*?)</div>', parca, re.S)
        yazarlar = [metin(a) for a in re.findall(r"<a class='authorsRichText'[^>]*>(.*?)</a>", parca, re.S)]
        kaynak = re.sub(r"\s+,", ",", metin(atiflar[1])) if len(atiflar) > 1 else ""
        yil = (re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", kaynak) or [""])[-1]
        doi = (re.findall(r'href="https?://(?:dx\.)?doi\.org/([^"]+)"', parca) or [""])[0]
        out.append({"bolum": bolum, "baslik": metin(b.group(2)), "yazarlar": yazarlar, "kaynak": kaynak, "yil": yil,
                    "url": kok + b.group(1) if b.group(1).startswith("/") else b.group(1), "doi": unescape(doi)})
    return out


def main():
    VERI.mkdir(parents=True, exist_ok=True)
    kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
    kurumlar = yaml.safe_load((VERI / "kurumlar.yaml").read_text(encoding="utf-8")) or {}
    elle = yaml.safe_load((VERI / "profiller.yaml").read_text(encoding="utf-8")) or {} if (VERI / "profiller.yaml").exists() else {}
    durum_d, cikti_d = VERI / "kurum_durumu.json", VERI / "yayinlar.json"
    durum = json.loads(durum_d.read_text(encoding="utf-8")) if durum_d.exists() else {}
    onceki = json.loads(cikti_d.read_text(encoding="utf-8")) if cikti_d.exists() else {}

    for u in sorted({p.get("universite", "") for p in kisiler} - {""}):
        if not durum.get(u):  # bulunamayanlar her çalıştırmada yeniden denenir
            durum[u] = kurum_adresi(u, kurumlar.get(u) or [])
            print(f"{u}: {durum[u] or 'AVESİS yok'}")
    durum_d.write_text(json.dumps(durum, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    sonuc, bulunan = {}, 0
    for p in kisiler:
        ad = p["ad"]
        profil = elle.get(ad) or (onceki.get(ad) or {}).get("profil") or ""
        kurum = durum.get(p.get("universite", ""), "")
        kurumlar_ = [kurum] + [durum.get(u, "") for u in p.get("onceki_kurumlar") or []]
        if not profil:
            for k in [x for x in kurumlar_ if x]:
                for a in adaylar(ad):
                    if profil_dogrula(f"{k}/{a}", ad):
                        profil = f"{k}/{a}"
                        break
                if profil:
                    break
            for k in [x for x in kurumlar_ if x and not profil]:
                for a in sitemap_adaylari(k, ad)[:8]:
                    if a not in adaylar(ad) and profil_dogrula(f"{k}/{a}", ad):
                        profil = f"{k}/{a}"
                        break
                if profil:
                    break
        if not profil:
            if any(kurumlar_):
                TANI["bulunamayan"][ad] = [x for x in kurumlar_ if x]
            continue
        html = al(profil.rstrip("/") + "/yayinlar", deneme=2)
        time.sleep(1)
        if not html:
            if ad in onceki:
                sonuc[ad] = onceki[ad]
            continue
        kok = re.match(r"https?://[^/]+", profil).group(0)
        sonuc[ad] = {"profil": profil, "yayinlar": yayinlar(html, kok)}
        bulunan += 1
        print(f"  {ad}: {profil} ({len(sonuc[ad]['yayinlar'])} yayın)")
    cikti_d.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (VERI / "tani.json").write_text(json.dumps(TANI, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"AVESİS profili bulunan kişi: {bulunan} / {len(kisiler)}")


if __name__ == "__main__":
    main()
