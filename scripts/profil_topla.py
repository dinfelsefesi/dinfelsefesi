#!/usr/bin/env python3
"""DergiPark profillerinden yayın listesi toplar.

Girdi: data/dergipark/profiller.yaml  kişi adı -> [DergiPark profil kısaltmaları (@...)]
       Buraya yalnızca kişinin kendisine ait olduğu doğrulanmış profiller yazılır.
Çıktı: data/dergipark/profil_makaleleri.json  kişi adı -> [makale kimliği]
       Profilde olup hasatta bulunmayan makaleler (ad farklı yazılmış olabilir) makale sayfasından okunur ve
       data/dergipark/akademisyen_makaleleri.jsonl dosyasına eklenir.

Kullanım:
  python3 scripts/profil_topla.py
"""
import json
import re
import sys
import time
from html import unescape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DP = ROOT / "data" / "dergipark"
sys.path.insert(0, str(ROOT / "scripts"))
from orcid_doi import dergipark_sayfasi  # noqa: E402
from orcid_topla import al  # noqa: E402

TABAN = "https://dergipark.org.tr"
MAKALE = re.compile(r'href="(/(?:tr|en)/pub/[^"/]+/(?:article|issue/\d+)/(\d+))"')


def profil_makaleleri(kisa: str) -> dict:
    """Profilin ana sayfası ve profildeki sekme sayfalarından makale bağlantıları: kimlik -> adres."""
    bulunan, gezilen, sira = {}, set(), [f"/tr/pub/{kisa}"]
    while sira and len(gezilen) < 40:
        yol = sira.pop(0)
        if yol in gezilen:
            continue
        gezilen.add(yol)
        html = al(TABAN + yol, deneme=2)
        time.sleep(1)
        if not html:
            continue
        for adres, mid in MAKALE.findall(html):
            bulunan.setdefault(mid, TABAN + adres)
        for h in re.findall(r'href="(/(?:tr|en)/pub/' + re.escape(kisa) + r'[^"#]*)"', unescape(html)):
            if h not in gezilen and "/tr/" in h and not re.search(r"(follow|message|login)", h):
                sira.append(h)
    print(f"{kisa}: {len(gezilen)} sayfa gezildi -> {sorted(gezilen)}")
    return bulunan


def yazar_oai(ad: str) -> str:
    p = ad.split()
    return f"{p[-1]}, {' '.join(p[:-1])}" if len(p) > 1 else ad


def main():
    profiller = yaml.safe_load((DP / "profiller.yaml").read_text(encoding="utf-8")) or {}
    kayit = DP / "akademisyen_makaleleri.jsonl"
    bilinen = set()
    for dosya in (DP / "din_felsefesi.jsonl", kayit):
        if dosya.exists():
            bilinen |= {json.loads(l)["id"] for l in dosya.read_text(encoding="utf-8").splitlines() if l.strip()}
    cikti = DP / "profil_makaleleri.json"
    sonuc = json.loads(cikti.read_text(encoding="utf-8")) if cikti.exists() else {}
    yeni = []
    for kisi, kisalar in profiller.items():
        ids = {}
        for kisa in kisalar or []:
            ids |= profil_makaleleri(kisa)
        sonuc[kisi] = sorted(ids)
        print(f"{kisi}: profilde {len(ids)} makale, {sum(1 for i in ids if i not in bilinen)} tanesi hasatta yok")
        for mid, adres in sorted(ids.items()):
            if mid in bilinen:
                continue
            s = dergipark_sayfasi(adres)
            time.sleep(1)
            if not s or not s.get("baslik"):
                continue
            kelimeler = s["kelimeler"]
            yeni.append({"id": mid, "baslik": {"tr-TR": s["baslik"]}, "yazarlar": [yazar_oai(y) for y in s["yazarlar"]],
                         "konular": [",".join(kelimeler) + ("," if len(kelimeler) == 1 else "")] if kelimeler else [],
                         "tarih": [s["yil"]], "kaynak": [s["dergi"]], "baglanti": [adres], "doi": "",
                         "akademisyen": [kisi], "pencere": "profil"})
            bilinen.add(mid)
    with kayit.open("a", encoding="utf-8") as f:
        for r in yeni:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cikti.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"hasada eklenen makale: {len(yeni)}")


if __name__ == "__main__":
    main()
