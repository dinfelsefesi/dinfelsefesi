#!/usr/bin/env python3
"""YÖK Akademik ve AVESİS yayın listelerindeki DOI'lerin künye, anahtar kelime ve özetlerini okur.

Girdi: data/yok/yayinlar.json, data/avesis/yayinlar.json
Çıktı: data/orcid/doi_kunye.json (ORCID DOI'leriyle ortak önbellek; orcid_doi.py ile aynı biçim, ek olarak "ozet")

Daha önce okunan DOI'ler yeniden okunmaz; yalnızca özeti hiç sorulmamış olanlar için kayıt yenilenir.

Kullanım:
  python3 scripts/yok_doi.py
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from orcid_doi import doi_oku, doi_temiz  # noqa: E402

DOSYA = ROOT / "data/orcid/doi_kunye.json"


def main():
    doiler = set()
    for yol in ("data/yok/yayinlar.json", "data/avesis/yayinlar.json"):
        if (ROOT / yol).exists():
            for v in json.loads((ROOT / yol).read_text(encoding="utf-8")).values():
                doiler |= {doi_temiz(y.get("doi")) for y in v["yayinlar"] if y.get("doi")}
    doiler.discard("")
    kunye = json.loads(DOSYA.read_text(encoding="utf-8")).get("kunye", {}) if DOSYA.exists() else {}
    okunacak = sorted(d for d in doiler if d not in kunye or "ozet" not in kunye[d])
    print(f"{len(doiler)} DOI, okunacak: {len(okunacak)}")

    def yaz():
        DOSYA.write_text(json.dumps({"tarih": date.today().isoformat(), "kunye": kunye}, ensure_ascii=False, indent=1,
                                    sort_keys=True), encoding="utf-8")
    for i, d in enumerate(okunacak, 1):
        k = doi_oku(d)
        eski = kunye.get(d) or {}
        # önceden okunmuş kayıtta anahtar kelime varsa ve yenisinde yoksa eskisi korunur
        if eski.get("kelimeler") and not k.get("kelimeler"):
            k["kelimeler"] = eski["kelimeler"]
        kunye[d] = k
        if i % 25 == 0:
            print(f"  {i}/{len(okunacak)}")
            yaz()
        time.sleep(1)
    yaz()
    from collections import Counter
    print(Counter(v["kaynak"] for d, v in kunye.items() if d in doiler),
          sum(1 for d in doiler if kunye.get(d, {}).get("kelimeler")), "anahtar kelimeli",
          sum(1 for d in doiler if kunye.get(d, {}).get("ozet")), "özetli")


if __name__ == "__main__":
    main()
