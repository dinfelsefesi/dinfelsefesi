#!/usr/bin/env python3
"""YÖK Akademik ve AVESİS listelerinde DOI'si olmayan makaleleri adlarıyla OpenAlex'te ve DergiPark'ta arar.

Bulunan makalenin DOI'si, sayfası, anahtar kelimeleri ve özeti kaydedilir; build.py konuyu bu anahtar kelimelerden bulur.
Aranacak makaleler build.py'nin kendi listesinden alınır: konusu belli olmayan, sitede başka bir kayıtla yer almayan
ve yerel DergiPark taramalarında bulunmayan DOI'siz makaleler. Bir kez aranan makale yeniden aranmaz.

Eşleşme ölçütü: ad aynı ya da kelimelerin büyük kısmı ortak, yıl en çok bir yıl farklı ve sayfa sahibinin soyadı
yazarlar arasında geçiyor.

Çıktı: data/yok/baslik_arama.json  kimlik -> {durum, doi, sayfa, baslik, kelimeler, ozet, kaynak}

Kullanım:
  TASLAK_GOSTER=1 python3 scripts/yok_baslik_ara.py
"""
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TASLAK_GOSTER", "1")
import build as b  # noqa: E402
from orcid_doi import al, dergipark_sayfasi, doi_oku, doi_temiz  # noqa: E402

DOSYA = ROOT / "data/yok/baslik_arama.json"


def adaylar() -> list:
    b.FIS = b.fisleri_oku()
    b.iliskileri_kur()
    b.bag_dizini_kur()
    sitede = [(b.baslik_anahtari(m["baslik"]), m["yil"], b.soyadlar(m["yazarlar"])) for m in b.dp_veri()]
    yerel = set()
    for f in ("data/dergipark/akademisyen_makaleleri.jsonl", "data/dergipark/din_felsefesi.jsonl"):
        for satir in (ROOT / f).read_text(encoding="utf-8").splitlines():
            if satir.strip():
                yerel |= {b.baslik_anahtari(t) for t in json.loads(satir)["baslik"].values()}
    out, gor = [], set()
    for v in b.avesis_veri().values():
        for y in v["yayinlar"]:
            if y["konular"] or y["doi"] or y["tur"] != "makale":
                continue
            a = (b.baslik_anahtari(y["baslik"]), y["yil"])
            if a in gor or a[0] in yerel or b.baslik_esit(y["baslik"], y["yil"], sitede, y["yazarlar"]):
                continue
            gor.add(a)
            out.append(y)
    return out


def ayni(y: dict, basliklar: list, yil: str, yazarlar: list) -> bool:
    if y["yil"] and yil and abs(int(y["yil"]) - int(yil)) > 1:
        return False
    soy = b.ad_anahtari(y["sahip"]).split("-")[-1]
    if not any(soy in b.ad_anahtari(a).split("-") for a in yazarlar):
        return False
    k, w = b.baslik_anahtari(y["baslik"]), b.kelimeler_(y["baslik"])
    for t in basliklar:
        if not t:
            continue
        k2, w2 = b.baslik_anahtari(t), b.kelimeler_(t)
        if k == k2 or (len(min(k, k2, key=len)) >= 25 and (k in k2 or k2 in k)):
            return True
        if len(w) >= 3 and len(w2) >= 3 and len(w & w2) / max(len(w), len(w2)) >= 0.8:
            return True
    return False


def openalex_ara(y: dict):
    t = re.sub(r"[^\w\s]", " ", y["baslik"])[:200]
    f = "title.search:" + t
    if y["yil"]:
        f += f",publication_year:{int(y['yil']) - 1}-{int(y['yil']) + 1}"
    govde = al("https://api.openalex.org/works?per-page=5&filter=" + urllib.parse.quote(f, safe=":,-") +
               "&mailto=dinfelsefesi@gmail.com", deneme=2)
    try:
        sonuc = json.loads(govde or "{}").get("results") or []
    except ValueError:
        return None
    for r in sonuc:
        yazarlar = [((a.get("author") or {}).get("display_name") or "") for a in r.get("authorships") or []]
        if ayni(y, [r.get("title") or ""], str(r.get("publication_year") or ""), yazarlar):
            return r
    return None


TANI = Counter()


def dergipark_ara(y: dict):
    html = al("https://dergipark.org.tr/tr/search?section=articles&q=" + urllib.parse.quote(y["baslik"][:150]), deneme=2)
    if html is None:
        TANI["dp-hata"] += 1
        return None
    linkler = list(dict.fromkeys(re.findall(
        r'href="(https://dergipark\.org\.tr/(?:tr|en)/pub/[^/"]+/(?:issue/\d+/\d+|article/\d+))"', html)))
    TANI["dp-sonuclu" if linkler else "dp-sonucsuz"] += 1
    for u in linkler[:3]:
        time.sleep(1)
        dp = dergipark_sayfasi(u)
        if dp and ayni(y, dp.get("basliklar") or [dp.get("baslik")], dp.get("yil") or "", dp.get("yazarlar") or []):
            return dp
    return None


def main():
    kayit = json.loads(DOSYA.read_text(encoding="utf-8")).get("kayit", {}) if DOSYA.exists() else {}
    liste = [y for y in adaylar() if y["kimlik"] not in kayit]
    print(f"aranacak: {len(liste)}")

    def yaz():
        DOSYA.write_text(json.dumps({"tarih": date.today().isoformat(), "tani": dict(TANI), "kayit": kayit},
                                    ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    for i, y in enumerate(liste, 1):
        e = {"durum": "bulunamadi", "baslik": y["baslik"], "sahip": y["sahip"]}
        r = openalex_ara(y)
        if r:
            doi = doi_temiz(r.get("doi") or "")
            sayfa = ((r.get("primary_location") or {}).get("landing_page_url")) or ""
            if doi:
                k = doi_oku(doi)
                e.update(durum="openalex", doi=doi, sayfa=k.get("sayfa") or sayfa, kelimeler=k.get("kelimeler") or [],
                         ozet=k.get("ozet") or "", kaynak=k.get("kaynak"))
            elif "dergipark" in sayfa:
                dp = dergipark_sayfasi(sayfa)
                e.update(durum="openalex", sayfa=sayfa, kelimeler=dp.get("kelimeler") or [], ozet=dp.get("ozet") or "",
                         kaynak="dergipark")
            else:
                e.update(durum="openalex", sayfa=sayfa, kelimeler=[x.get("display_name", "") for x in r.get("keywords") or []],
                         kaynak="openalex")
            TANI["openalex"] += 1
        else:
            time.sleep(1)
            dp = dergipark_ara(y)
            if dp:
                e.update(durum="dergipark", sayfa=dp["sayfa"], kelimeler=dp.get("kelimeler") or [], ozet=dp.get("ozet") or "",
                         kaynak="dergipark")
                TANI["dergipark"] += 1
        kayit[y["kimlik"]] = e
        if i % 25 == 0:
            print(f"  {i}/{len(liste)} {dict(TANI)}")
            yaz()
        time.sleep(1)
    yaz()
    print(dict(TANI), Counter(v["durum"] for v in kayit.values()))


if __name__ == "__main__":
    main()
