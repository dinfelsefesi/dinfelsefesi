#!/usr/bin/env python3
"""DergiPark makalelerinin yayımlanma tarihini (makale sayfasındaki citation_publication_date) toplar.
OAI kayıtlarındaki tarih çoğu zaman gönderilme tarihidir; sitede makalenin yayımlandığı ay gösterilmek istendiği için
her makalenin kendi sayfasına bir kez bakılır. Bulunan tarihler bir daha sorulmaz.
Girdi: data/dergipark/din_felsefesi.jsonl, akademisyen_makaleleri.jsonl (yalnızca akademisyen_sinif.json'daki doğrulanmış kayıtlar)
Çıktı: data/dergipark/yayim_tarihi.json  {makale kimliği: "YYYY-AA-GG" ya da "" (sayfada tarih yok)}
Kullanım: python3 scripts/yayim_tarihi.py [--dakika 40]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DP = ROOT / "data" / "dergipark"
sys.path.insert(0, str(ROOT / "scripts"))
from orcid_topla import al  # noqa: E402

CIKTI = DP / "yayim_tarihi.json"


def kayitlar():
    sinif_d = DP / "akademisyen_sinif.json"
    sinif = json.loads(sinif_d.read_text(encoding="utf-8")) if sinif_d.exists() else {}
    for ad, sadece_sinif in (("din_felsefesi.jsonl", False), ("akademisyen_makaleleri.jsonl", True)):
        d = DP / ad
        if not d.exists():
            continue
        for satir in d.read_text(encoding="utf-8").splitlines():
            if not satir.strip():
                continue
            r = json.loads(satir)
            if sadece_sinif and r["id"] not in sinif:
                continue
            url = next((b for b in r.get("baglanti") or [] if "dergipark.org.tr" in b), "")
            if url:
                yield r["id"], re.sub(r"/en/pub/", "/tr/pub/", url)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dakika", type=float, default=40)
    a = ap.parse_args()
    bitis = time.time() + a.dakika * 60
    sonuc = json.loads(CIKTI.read_text(encoding="utf-8")) if CIKTI.exists() else {}
    yeni = bos = hata = 0
    for kimlik, url in kayitlar():
        if sonuc.get(kimlik):
            continue
        if time.time() > bitis:
            print("Süre doldu, kalanlar bir sonraki çalıştırmada.")
            break
        html = al(url, deneme=2)
        if html is None:
            hata += 1
            continue
        m = re.search(r'<meta\s+name="citation_publication_date"\s+content="(\d{4}-\d{2}-\d{2})', html) or \
            re.search(r'<meta\s+name="citation_date"\s+content="(\d{4}-\d{2}-\d{2})', html)
        sonuc[kimlik] = m.group(1) if m else ""
        yeni += bool(m)
        bos += not m
        time.sleep(1.2)
        if (yeni + bos) % 50 == 0:
            CIKTI.write_text(json.dumps(dict(sorted(sonuc.items())), ensure_ascii=False, indent=0), encoding="utf-8")
    CIKTI.write_text(json.dumps(dict(sorted(sonuc.items())), ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Yeni tarih: {yeni}, tarihsiz sayfa: {bos}, ulaşılamayan: {hata}, toplam kayıt: {len(sonuc)}")


if __name__ == "__main__":
    main()
