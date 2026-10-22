#!/usr/bin/env python3
"""ORCID kayıtlarındaki DOI'li eserlerin künye ve anahtar kelimelerini toplar.

Girdi: data/orcid/eserler.json (orcid_topla.py çıktısı)
Çıktı: data/orcid/doi_kunye.json  DOI -> {baslik, yazarlar, dergi, yil, kelimeler, tur_ipucu, kaynak, sayfa}

Her DOI için önce OpenAlex kaydı okunur. Eserin sayfası DergiPark'taysa anahtar kelimeler
DergiPark sayfasından alınır, çünkü yazarın kendi verdiği kelimeler oradadır. DergiPark dışındaki
eserlerde OpenAlex'in anahtar kelimeleri ve konu adları kullanılır. Önceden okunan DOI'ler yeniden okunmaz.

Kullanım:
  python3 scripts/orcid_doi.py
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERI = ROOT / "data" / "orcid"
sys.path.insert(0, str(ROOT / "scripts"))
from orcid_topla import UA, al  # noqa: E402

TUR_KALIP = re.compile(r"Araştırma Makalesi|Derleme|Kitap Tanıtımı|Kitap İncelemesi|Kitap Değerlendirmesi|Kitap Kritiği|"
                       r"Çeviri|Tercüme|Book Review|Translation|Research Article|Review Article|Editoryal|Söyleşi|Interview")


def doi_temiz(d: str) -> str:
    d = (d or "").strip().lower()
    return re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d).removeprefix("doi:").strip()


def yonlendir(url: str) -> str:
    """DOI adresinin vardığı sayfa (yalnızca adres)."""
    try:
        req = urllib.request.Request(url, headers=UA, method="HEAD")
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.geturl()
    except Exception:  # noqa: BLE001
        return ""


def openalex(doi: str):
    govde = al("https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="/"), deneme=2)
    if not govde:
        return None
    try:
        return json.loads(govde)
    except ValueError:
        return None


def dergipark_sayfasi(url: str) -> dict:
    url = re.sub(r"/en/(pub|doi)/", r"/tr/\1/", url)
    html = al(url, deneme=2)
    if not html:
        return {}
    meta = {}
    for ad_, deger in re.findall(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"', html):
        meta.setdefault(ad_, []).append(unescape(deger).strip())
    kelimeler = []
    for k in meta.get("citation_keywords", []) + meta.get("DC.Subject", []) + meta.get("keywords", []):
        kelimeler += [x.strip() for x in re.split(r"[;,]", k) if x.strip()]
    kelimeler += [unescape(x).strip() for x in re.findall(r'section=keyword[^"]*"[^>]*>\s*([^<]+?)\s*<', html)]
    return {
        "baslik": (meta.get("citation_title") or [""])[0],
        "yazarlar": meta.get("citation_author", []),
        "dergi": (meta.get("citation_journal_title") or [""])[0],
        "yil": ((meta.get("citation_publication_date") or meta.get("citation_date") or [""])[0])[:4],
        "kelimeler": list(dict.fromkeys(kelimeler)),
        "tur_ipucu": list(dict.fromkeys(TUR_KALIP.findall(html))),
        "sayfa": url,
    }


def main():
    eserler = json.loads((VERI / "eserler.json").read_text(encoding="utf-8"))["eserler"]
    dosya = VERI / "doi_kunye.json"
    kunye = json.loads(dosya.read_text(encoding="utf-8")).get("kunye", {}) if dosya.exists() else {}
    doiler = sorted({doi_temiz(w["doi"]) for ws in eserler.values() for w in ws if w.get("doi")} - {""})
    yeni = [d for d in doiler if d not in kunye]
    print(f"{len(doiler)} DOI, okunacak: {len(yeni)}")
    for i, d in enumerate(yeni, 1):
        k = {"baslik": "", "yazarlar": [], "dergi": "", "yil": "", "kelimeler": [], "konu_adlari": [],
             "tur_ipucu": [], "oa_tur": "", "dil": "", "kaynak": "", "sayfa": ""}
        oa = openalex(d)
        if oa:
            k["baslik"] = oa.get("title") or ""
            k["yazarlar"] = [((a.get("author") or {}).get("display_name") or "") for a in oa.get("authorships") or []]
            loc = oa.get("primary_location") or {}
            k["dergi"] = ((loc.get("source") or {}).get("display_name")) or ""
            k["yil"] = str(oa.get("publication_year") or "")
            k["kelimeler"] = [x.get("display_name", "") for x in oa.get("keywords") or []]
            k["konu_adlari"] = [x.get("display_name", "") for x in oa.get("topics") or []] + \
                               [x.get("display_name", "") for x in oa.get("concepts") or [] if (x.get("score") or 0) >= 0.4]
            k["oa_tur"] = oa.get("type") or ""
            k["dil"] = oa.get("language") or ""
            k["sayfa"] = loc.get("landing_page_url") or ""
            k["kaynak"] = "openalex"
        if "dergipark" not in k["sayfa"]:
            hedef = yonlendir("https://doi.org/" + d)
            if "dergipark" in hedef:
                k["sayfa"] = hedef
        if "dergipark" in k["sayfa"]:
            dp = dergipark_sayfasi(k["sayfa"])
            if dp:
                for alan in ("baslik", "dergi", "yil"):
                    k[alan] = dp[alan] or k[alan]
                k["yazarlar"] = dp["yazarlar"] or k["yazarlar"]
                if dp["kelimeler"]:
                    k["kelimeler"] = dp["kelimeler"]
                k["tur_ipucu"] = dp["tur_ipucu"]
                k["sayfa"] = dp["sayfa"]
                k["kaynak"] = "dergipark"
        if not k["kaynak"]:
            k["kaynak"] = "bulunamadi"
        kunye[d] = k
        if i % 25 == 0:
            print(f"  {i}/{len(yeni)}")
            dosya.write_text(json.dumps({"tarih": date.today().isoformat(), "kunye": kunye}, ensure_ascii=False, indent=1,
                                        sort_keys=True), encoding="utf-8")
        time.sleep(1)
    dosya.write_text(json.dumps({"tarih": date.today().isoformat(), "kunye": kunye}, ensure_ascii=False, indent=1,
                                sort_keys=True), encoding="utf-8")
    from collections import Counter
    print(Counter(v["kaynak"] for v in kunye.values()))


if __name__ == "__main__":
    main()
