#!/usr/bin/env python3
"""Türkiye akademisi listesindeki kişilerin ORCID numaralarını ve ORCID kayıtlarındaki eserleri toplar.

ORCID numarası yalnızca DergiPark makale sayfalarından alınır: DergiPark her makalenin sayfasında
yazarın adını, kurumunu ve ORCID numarasını birlikte verir (citation_author / citation_author_orcid).
İsimle ORCID araması yapılmaz, çünkü aynı adı taşıyan farklı kişiler karışabilir.
Bir kişi için farklı makalelerde iki ayrı ORCID görülürse numara atanmaz, "celiskiler" listesine yazılır.

Çıktılar (data/orcid/):
  makale_yazar.json  makale kimliği -> [{ad, kurum, orcid}]  (sayfası bir kez okunan makaleler yeniden okunmaz)
  orcid.json         kişi kısaltması -> ORCID, ayrıca çelişkiler
  eserler.json       ORCID -> ORCID kaydındaki eserler (her çalıştırmada yenilenir)
"""
import json
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VERI = ROOT / "data" / "orcid"
UA = {"User-Agent": "dinfelsefesi.com.tr (dinfelsefesi@gmail.com)"}
ORCID_DESEN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def kisalt(ad: str) -> str:
    """build.py'deki slugify(tr_kucuk(ad)) ile aynı sonucu verir."""
    s = (ad or "").replace("İ", "i").replace("I", "ı").lower()
    s = s.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80]


def al(url, accept=None, deneme=3):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    for i in range(deneme):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as ex:  # noqa: BLE001
            if i == deneme - 1:
                print(f"  hata: {url}: {ex}", file=sys.stderr)
                return None
            time.sleep(3 * (i + 1))


def yazarlar_sayfadan(html: str) -> list:
    """citation_author etiketlerini sırayla okur; her yazara ardından gelen kurum ve ORCID eklenir."""
    out = []
    for ad_, deger in re.findall(r'<meta name="(citation_author(?:_institution|_orcid)?)" content="([^"]*)"', html):
        deger = unescape(deger).strip()
        if ad_ == "citation_author":
            out.append({"ad": deger, "kurum": "", "orcid": ""})
        elif out and ad_ == "citation_author_institution":
            out[-1]["kurum"] = deger
        elif out and ad_ == "citation_author_orcid" and ORCID_DESEN.match(deger):
            out[-1]["orcid"] = deger
    return out


def main():
    VERI.mkdir(parents=True, exist_ok=True)
    kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
    liste = {kisalt(p["ad"]): p for p in kisiler}
    makaleler = [json.loads(l) for ad_ in ("din_felsefesi.jsonl", "akademisyen_makaleleri.jsonl")
                 if (ROOT / "data/dergipark" / ad_).exists()
                 for l in (ROOT / "data/dergipark" / ad_).read_text(encoding="utf-8").splitlines() if l.strip()]

    # 1) Listedeki bir kişinin yazar olduğu makalelerin sayfalarını oku (önceden okunanlar atlanır)
    dosya = VERI / "makale_yazar.json"
    onbellek = json.loads(dosya.read_text(encoding="utf-8")) if dosya.exists() else {}
    profil_dosya = VERI / "makale_profil.json"  # makale -> {yazar adı: DergiPark profil adresi}
    profiller = json.loads(profil_dosya.read_text(encoding="utf-8")) if profil_dosya.exists() else {}
    okunacak = []
    for r in makaleler:
        adlar = [f"{y.partition(',')[2].strip()} {y.partition(',')[0].strip()}".strip() for y in r.get("yazarlar") or []]
        if r["id"] not in onbellek and any(kisalt(a) in liste for a in adlar):
            url = next((b for b in r.get("baglanti") or [] if "dergipark.org.tr" in b), None)
            if url:
                okunacak.append((r["id"], url.replace("/en/pub/", "/tr/pub/")))
    print(f"{len(okunacak)} makale sayfası okunacak")
    for i, (mid, url) in enumerate(okunacak, 1):
        html = al(url)
        if html is not None:
            onbellek[mid] = yazarlar_sayfadan(html)
            profiller[mid] = {unescape(ad_).strip(): yol for yol, ad_ in
                              re.findall(r'href="/(?:tr|en)/pub/(@[^"/?#]+)"[^>]*>\s*([^<]+?)\s*<', html)}
        if i % 25 == 0:
            print(f"  {i}/{len(okunacak)}")
            dosya.write_text(json.dumps(onbellek, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            profil_dosya.write_text(json.dumps(profiller, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        time.sleep(1)
    dosya.write_text(json.dumps(onbellek, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    profil_dosya.write_text(json.dumps(profiller, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    # 2) Kişi -> ORCID (tek ve çelişkisiz olanlar)
    # Kişinin ORCID'i yalnızca din felsefesi makalelerinden çıkarılır; akademisyen adıyla bulunan öteki
    # makalelerde aynı adı taşıyan başka kişiler olabilir (bu makaleler ORCID'le sonradan doğrulanır).
    df_id = {json.loads(l)["id"] for l in (ROOT / "data/dergipark/din_felsefesi.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    gorulen = {}
    for mid_, yazarlar in onbellek.items():
        if mid_ not in df_id:
            continue
        for y in yazarlar:
            k = kisalt(y["ad"])
            if k in liste and y["orcid"]:
                gorulen.setdefault(k, set()).add(y["orcid"])
    atanan = {k: next(iter(v)) for k, v in gorulen.items() if len(v) == 1}
    celiski = {k: sorted(v) for k, v in gorulen.items() if len(v) > 1}
    # Listeye elle yazılan ORCID (YÖK Akademik kaydından) önce gelir; eserleri de onunla çekilir
    for k, p in liste.items():
        if p.get("orcid"):
            atanan[k] = p["orcid"]
            celiski.pop(k, None)
    (VERI / "orcid.json").write_text(json.dumps({"tarih": date.today().isoformat(), "kaynak": "DergiPark makale sayfaları",
                                                 "orcid": dict(sorted(atanan.items())), "celiskiler": celiski},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ORCID atanan: {len(atanan)}, çelişkili: {len(celiski)}")

    # 3) ORCID kaydındaki eserler
    eserler = {}
    for k, oid in sorted(atanan.items()):
        govde = al(f"https://pub.orcid.org/v3.0/{oid}/works", "application/json")
        if govde is None:
            continue
        liste_ = []
        for grup in json.loads(govde).get("group") or []:
            ozet = (grup.get("work-summary") or [{}])[0]
            baslik = ((ozet.get("title") or {}).get("title") or {}).get("value") or ""
            if not baslik:
                continue
            dergi = (ozet.get("journal-title") or {}).get("value") or ""
            yil = (((ozet.get("publication-date") or {}).get("year")) or {}).get("value") or ""
            doi = ""
            for x in ((ozet.get("external-ids") or {}).get("external-id") or []):
                if (x.get("external-id-type") or "").lower() == "doi":
                    doi = (x.get("external-id-value") or "").strip()
                    break
            url = ((ozet.get("url") or {}) or {}).get("value") or ""
            liste_.append({"baslik": baslik.strip(), "tur": ozet.get("type") or "", "dergi": dergi.strip(),
                           "yil": str(yil), "doi": doi, "url": url})
        eserler[oid] = liste_
        time.sleep(0.5)
    (VERI / "eserler.json").write_text(json.dumps({"tarih": date.today().isoformat(), "eserler": eserler},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ORCID eser listesi alınan kişi: {len(eserler)}")


if __name__ == "__main__":
    main()
