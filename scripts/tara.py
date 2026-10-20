#!/usr/bin/env python3
"""Dergi tarayıcı.

Crossref üzerinden seçili din felsefesi dergilerinin son makalelerini çeker,
sitede zaten bulunan ve daha önce aday listesine girmiş olanları eler,
yenileri content/adaylar.json dosyasına ekler.

Kullanım: python3 scripts/tara.py [--gun 14]
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKALELER = ROOT / "content" / "makaleler.json"
ADAYLAR = ROOT / "content" / "adaylar.json"
MAILTO = "dinfelsefesi@gmail.com"

# Dergi adı -> ISSN listesi, anahtar kelime filtresi gerekip gerekmediği
DERGILER = {
    "Religious Studies": (["0034-4125", "1469-901X"], False),
    "International Journal for Philosophy of Religion": (["0020-7047", "1572-8684"], False),
    "Faith and Philosophy": (["0739-7046"], False),
    "Sophia": (["0038-1527", "1873-930X"], False),
    "European Journal for Philosophy of Religion": (["1689-8311"], False),
    "Journal of Analytic Theology": (["2330-2380"], False),
    "Philosophia Christi": (["1529-1634"], False),
    "TheoLogica": (["2593-0265"], False),
    "Religions": (["2077-1444"], True),
    "Open Theology": (["2300-6579"], True),
}

# Geniş kapsamlı dergiler için felsefi içerik süzgeci
ANAHTAR = re.compile(
    r"philosoph|theis|atheis|\bgod\b|divine|problem of evil|theodic|epistem|"
    r"argument|ontolog|metaphys|kal[aā]m|mu[ʿ']tazil|ash[ʿ']ar|avicenna|ghaz[aā]l|"
    r"worship|prayer|liturg|religious experience|mystic|miracle|omnipot|omniscien|"
    r"free will|providence|afterlife|resurrection|faith and reason|rational",
    re.I,
)


def temizle(metin: str) -> str:
    metin = re.sub(r"<[^>]+>", " ", metin or "")
    metin = html.unescape(metin)
    metin = re.sub(r"^\s*abstract\s*[:.]?\s*", "", metin, flags=re.I)
    return re.sub(r"\s+", " ", metin).strip()


def tarih(item: dict) -> str:
    for alan in ("published-online", "published-print", "published", "created"):
        p = item.get(alan, {}).get("date-parts", [[None]])[0]
        if p and p[0]:
            y, m, d = (list(p) + [1, 1])[:3]
            return f"{y:04d}-{m:02d}-{d:02d}"
    return ""


def sorgula(issn: str, baslangic: str) -> list[dict]:
    q = urllib.parse.urlencode({
        "filter": f"issn:{issn},from-pub-date:{baslangic},type:journal-article",
        "rows": 100, "sort": "published", "order": "desc", "mailto": MAILTO,
    })
    req = urllib.request.Request(
        f"https://api.crossref.org/works?{q}",
        headers={"User-Agent": f"dinfelsefesi-tarayici/1.0 (mailto:{MAILTO})"})
    for deneme in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["message"]["items"]
        except Exception as hata:  # noqa: BLE001
            print(f"  {issn}: {hata} (deneme {deneme + 1})", file=sys.stderr)
            time.sleep(5 * (deneme + 1))
    return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=14, help="kaç gün geriye bakılacak")
    args = ap.parse_args()
    baslangic = (date.today() - timedelta(days=args.gun)).isoformat()

    yayimlanan = {m.get("doi", "").lower() for m in json.loads(MAKALELER.read_text(encoding="utf-8"))}
    adaylar = json.loads(ADAYLAR.read_text(encoding="utf-8")) if ADAYLAR.exists() else []
    bilinen = yayimlanan | {a["doi"].lower() for a in adaylar}

    yeni = []
    for dergi, (issnler, suzgec) in DERGILER.items():
        gorulen = set()
        for issn in issnler:
            for it in sorgula(issn, baslangic):
                doi = it.get("DOI", "").lower()
                if not doi or doi in bilinen or doi in gorulen:
                    continue
                gorulen.add(doi)
                baslik = temizle(" ".join(it.get("title", [])))
                ozet = temizle(it.get("abstract", ""))
                if not baslik or baslik.lower().startswith(("correction", "erratum", "book review", "editorial")):
                    continue
                if suzgec and not ANAHTAR.search(baslik + " " + ozet):
                    continue
                yazarlar = ", ".join(
                    " ".join(x for x in (a.get("given"), a.get("family")) if x)
                    for a in it.get("author", []))
                lisans = " ".join(l.get("URL", "") for l in it.get("license", []))
                yeni.append({
                    "doi": doi,
                    "title_en": baslik,
                    "authors": yazarlar,
                    "journal": dergi,
                    "date": tarih(it),
                    "open_access": "evet" if "creativecommons" in lisans else "bilinmiyor",
                    "abstract": ozet,
                    "durum": "yeni",
                    "eklendi": date.today().isoformat(),
                })
            time.sleep(1)
        print(f"{dergi}: {len(gorulen)} aday", file=sys.stderr)

    yeni.sort(key=lambda a: a["date"], reverse=True)
    adaylar = yeni + adaylar
    ADAYLAR.write_text(json.dumps(adaylar, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(yeni)} yeni aday eklendi, toplam {len(adaylar)}")


if __name__ == "__main__":
    main()
