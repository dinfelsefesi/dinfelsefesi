#!/usr/bin/env python3
"""DergiPark'taki bütün dergilerin listesi.

DergiPark'ın OAI-PMH veri kapısındaki ListSets cevabını sayfa sayfa okur ve her derginin kısa adını
(dergipark.org.tr/tr/pub/KOD) ve adını data/dergiler/dergipark_dergileri.json dosyasına yazar.
Dergiler sayfasına eklenecek ilahiyat dergilerini belirlemek için kullanılır.

Kullanım: python3 scripts/dergipark_dergi_listesi.py
"""
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CIKTI = ROOT / "data" / "dergiler" / "dergipark_dergileri.json"
OAI = "https://dergipark.org.tr/api/public/oai/"
UA = {"User-Agent": "dinfelsefesi.com.tr dergi listesi (+https://dinfelsefesi.com.tr/dergiler/; dinfelsefesi@gmail.com)"}
NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}


def getir(params: dict) -> ET.Element:
    url = OAI + "?" + urllib.parse.urlencode(params)
    for deneme in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return ET.fromstring(r.read())
        except Exception as ex:  # noqa: BLE001
            if deneme == 3:
                raise
            print(f"uyarı: {ex}, yeniden deneniyor")
            time.sleep(10 * (deneme + 1))


def main() -> None:
    dergiler = {}
    params = {"verb": "ListSets"}
    sayfa = 0
    while True:
        kok = getir(params)
        for s in kok.iterfind(".//oai:set", NS):
            kod = (s.findtext("oai:setSpec", "", NS) or "").strip()
            ad = (s.findtext("oai:setName", "", NS) or "").strip()
            if kod:
                dergiler[kod] = ad
        sayfa += 1
        jeton = kok.find(".//oai:resumptionToken", NS)
        if jeton is None or not (jeton.text or "").strip():
            break
        params = {"verb": "ListSets", "resumptionToken": jeton.text.strip()}
        time.sleep(1.5)
    CIKTI.write_text(json.dumps(dict(sorted(dergiler.items())), ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"{sayfa} sayfa, {len(dergiler)} dergi")


if __name__ == "__main__":
    main()
