#!/usr/bin/env python3
"""YÖK Akademik ve AVESİS listelerinde DOI'si olmayan makaleleri adlarıyla OpenAlex'te ve TR Dizin'de arar.

DergiPark'ın arama sayfası otomatik isteklerde doğrulama (CAPTCHA) sayfasına yönlendirdiği için DergiPark'ta arama
yapılmaz. DergiPark'taki makaleler zaten OAI-PMH hasadıyla (dergipark_hasat.py) yazar adına göre toplanmaktadır.

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


def trdizin_ara(y: dict):
    """TR Dizin'in açık arama servisinde adla arar; dergi makalelerinin iki dildeki adları, özetleri ve varsa anahtar
    kelimeleri buradadır."""
    q = re.sub(r"[^\w\s]", " ", y["baslik"])[:200]
    govde = al("https://search.trdizin.gov.tr/api/defaultSearch/publication/?order=relevance-DESC&page=1&limit=5&q=" +
               urllib.parse.quote(q), deneme=2)
    try:
        sonuc = ((json.loads(govde or "{}").get("hits") or {}).get("hits")) or []
    except ValueError:
        return None
    for h in sonuc:
        r = h.get("_source") or {}
        ozetler = r.get("abstracts") or []
        basliklar = [a.get("title") or "" for a in ozetler] + [r.get("orderTitle") or ""]
        yazarlar = [a.get("inPublicationName") or "" for a in r.get("authors") or []]
        if not ayni(y, basliklar, str(r.get("publicationYear") or ""), yazarlar):
            continue
        kelimeler = []
        for a in ozetler:
            k = a.get("keywords")
            if k and k != "None":
                kelimeler += [x.strip() for x in re.split(r"[;,]", k) if x.strip()]
        ozet = max((a.get("abstract") or "" for a in ozetler), key=len, default="")
        tr = next((a.get("abstract") for a in ozetler if a.get("language") == "TUR" and a.get("abstract")), "")
        return {"durum": "trdizin", "doi": doi_temiz(r.get("doi") or ""), "sayfa": f"https://search.trdizin.gov.tr/tr/yayin/detay/{r.get('id')}",
                "kelimeler": list(dict.fromkeys(kelimeler)), "ozet": tr or ozet, "kaynak": "trdizin",
                "dergi": (r.get("journal") or {}).get("name") or ""}
    return None


TANI = Counter()
HATALAR = []


def main():
    kayit = json.loads(DOSYA.read_text(encoding="utf-8")).get("kayit", {}) if DOSYA.exists() else {}
    # Daha önce bulunamayan makaleler TR Dizin'de bir kez daha aranır
    liste = [y for y in adaylar() if y["kimlik"] not in kayit or
             (kayit[y["kimlik"]]["durum"] == "bulunamadi" and not kayit[y["kimlik"]].get("trdizin_bakildi"))]
    print(f"aranacak: {len(liste)}")

    def yaz():
        DOSYA.write_text(json.dumps({"tarih": date.today().isoformat(), "tani": dict(TANI), "hatalar": HATALAR[:20], "kayit": kayit},
                                    ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    for i, y in enumerate(liste, 1):
        e = kayit.get(y["kimlik"]) or {"durum": "bulunamadi", "baslik": y["baslik"], "sahip": y["sahip"]}
        try:
            r = openalex_ara(y) if y["kimlik"] not in kayit else None
        except Exception as ex:  # noqa: BLE001
            TANI["openalex-hata"] += 1
            HATALAR.append(f"{y['baslik'][:60]}: {type(ex).__name__}: {ex}"[:300])
            r = None
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
        if e["durum"] == "bulunamadi":
            time.sleep(1)
            try:
                t = trdizin_ara(y)
            except Exception as ex:  # noqa: BLE001  tek bir kayıttaki beklenmedik veri bütün işi durdurmasın
                TANI["trdizin-hata"] += 1
                HATALAR.append(f"{y['baslik'][:60]}: {type(ex).__name__}: {ex}"[:300])
                t = None
            e["trdizin_bakildi"] = True
            if t:
                if t["doi"]:  # TR Dizin kaydındaki DOI'nin anahtar kelimeleri DergiPark ya da OpenAlex'ten okunur
                    try:
                        k = doi_oku(t["doi"])
                    except Exception:  # noqa: BLE001
                        k = {}
                    t["kelimeler"] = t["kelimeler"] or k.get("kelimeler") or []
                    t["ozet"] = t["ozet"] or k.get("ozet") or ""
                e.update(t)
                TANI["trdizin"] += 1
        kayit[y["kimlik"]] = e
        if i % 25 == 0:
            print(f"  {i}/{len(liste)} {dict(TANI)}")
            yaz()
        time.sleep(1)
    yaz()
    print(dict(TANI), Counter(v["durum"] for v in kayit.values()))


if __name__ == "__main__":
    main()
