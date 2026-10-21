#!/usr/bin/env python3
"""DergiPark din felsefesi makalelerini anahtar kelimelerine göre başlıklara ayırır.

Girdi: data/dergipark/din_felsefesi.jsonl ve data/dergipark/sozluk.yaml
Çıktı: data/dergipark/siniflandirma.json (makale başına başlıklar ve özet sayılar)

Kullanım:
  python3 scripts/dergipark_siniflandir.py
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VERI = ROOT / "data" / "dergipark"
UST = {"kotuluk-problemi": "teizme-yonelik-itirazlar", "tanrinin-sifatlari": "tanri-tasavvurlari",
       "tanri-alem-iliskisi": "tanri-tasavvurlari", "dini-tecrube": "din-epistemolojisi"}


def katla(s: str) -> str:
    """Eşleştirme için: Türkçe küçük harf, şapkasız, ı ile i aynı sayılır."""
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    s = s.replace("ı", "i").replace("’", "'").replace("‘", "'")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip(" .;:-–")


def anahtar_kelimeler(r: dict) -> list[str]:
    out = []
    for s in r.get("konular", []):
        if "," in s:
            out += [x.strip() for x in s.split(",") if x.strip()]
    return out


def eslesir(kalip: str, kelime: str) -> bool:
    if kalip.endswith("$"):
        return kelime == kalip[:-1]
    return kelime.startswith(kalip) or (" " + kalip) in kelime or ("-" + kalip) in kelime


def yukle():
    makaleler = [json.loads(l) for l in (VERI / "din_felsefesi.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    sozluk = yaml.safe_load((VERI / "sozluk.yaml").read_text(encoding="utf-8"))
    kurallar = {b: [katla(k) + ("$" if str(k).endswith("$") else "") for k in ks]
                for b, ks in sozluk["basliklar"].items()}
    kurallar = {b: [k.replace("$$", "$") for k in ks] for b, ks in kurallar.items()}
    genel = [katla(k) + ("$" if str(k).endswith("$") else "") for k in sozluk.get("genel", [])]
    genel = [k.replace("$$", "$") for k in genel]
    return makaleler, kurallar, genel


def yil(r: dict) -> str:
    return (r.get("tarih") or [""])[0][:4]


def siniflandir():
    makaleler, kurallar, genel = yukle()
    haric = {katla("din felsefesi"), katla("philosophy of religion")}
    sonuc, kelime_say, kelime_baslik, kalip_say = [], Counter(), defaultdict(set), Counter()
    for r in makaleler:
        kelimeler = [katla(k) for k in anahtar_kelimeler(r)]
        basliklar = set()
        for k in kelimeler:
            if k in haric:
                continue
            kelime_say[k] += 1
            if any(eslesir(g, k) for g in genel):
                kelime_baslik[k].add("(genel)")
                continue
            for b, kaliplar in kurallar.items():
                for kal in kaliplar:
                    if eslesir(kal, k):
                        basliklar.add(b)
                        kelime_baslik[k].add(b)
                        kalip_say[(b, kal)] += 1
                        break
        for b in list(basliklar):
            if b in UST:
                basliklar.add(UST[b])
        sonuc.append({"id": r["id"], "yil": yil(r), "basliklar": sorted(basliklar)})
    return makaleler, sonuc, kelime_say, kelime_baslik, kalip_say, kurallar


def main():
    makaleler, sonuc, kelime_say, kelime_baslik, kalip_say, _ = siniflandir()
    baslik_say = Counter(b for s in sonuc for b in s["basliklar"])
    bos = sum(1 for s in sonuc if not s["basliklar"])
    (VERI / "siniflandirma.json").write_text(json.dumps(
        {"makale": len(sonuc), "siniflandirilamayan": bos, "baslik_sayilari": dict(baslik_say.most_common()),
         "makaleler": sonuc}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(sonuc)} makale, {bos} sınıflandırılamadı")
    for b, n in baslik_say.most_common():
        print(f"  {n:4d}  {b}")


if __name__ == "__main__":
    main()
