#!/usr/bin/env python3
"""Türkiye akademisi listesindeki kişilerin unvan değişikliklerini izler.

Girdi: content/turkiye_akademisi.yaml (YÖK Akademik'teki unvan), data/avesis/yayinlar.json (AVESİS'teki güncel unvan)
Çıktı: data/akademi/unvan_gecmisi.json  kişi adı -> {unvan, kaynaklar: {kaynak: unvan}, degisiklikler: [{tarih, onceki, yeni, kaynak}]}

Her kaynağın (YÖK, AVESİS) son gördüğü unvan ayrı tutulur. Bir kaynakta unvan yükseldiğinde değişiklik o günün tarihiyle
kaydedilir (tarih, değişikliğin sitede fark edildiği gündür; unvanın alındığı gün değildir). Bir kaynağın ilk kaydı
başlangıçtır. Unvanın gerilemesi kaydedilmez.
AVESİS toplamasından sonra çalışır; YÖK listesi elle güncellendiğinde de çalıştırılmalıdır.
"""
import json
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOSYA = ROOT / "data/akademi/unvan_gecmisi.json"
SIRA = {"Arş. Gör.": 1, "Öğr. Gör.": 1, "Arş. Gör. Dr.": 2, "Öğr. Gör. Dr.": 2, "Dr.": 2, "Dr. Öğr. Üyesi": 3,
        "Doç. Dr.": 4, "Prof. Dr.": 5}


def main():
    kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
    av_d = ROOT / "data/avesis/yayinlar.json"
    avesis = json.loads(av_d.read_text(encoding="utf-8")) if av_d.exists() else {}
    gecmis = json.loads(DOSYA.read_text(encoding="utf-8")) if DOSYA.exists() else {}
    bugun = date.today().isoformat()
    yeni = 0
    for p in kisiler:
        ad = p["ad"]
        g = gecmis.setdefault(ad, {"kaynaklar": {}, "degisiklikler": []})
        g.setdefault("kaynaklar", {})
        for kaynak, unvan in (("YÖK Akademik", p.get("unvan") or ""), ("AVESİS", (avesis.get(ad) or {}).get("unvan") or "")):
            if not unvan:
                continue
            onceki = g["kaynaklar"].get(kaynak)
            # Kaynaklar unvanı farklı biçimlerde yazabildiği (ör. YÖK'te "Arş. Gör.", AVESİS'te "Arş. Gör. Dr.") ve farklı
            # hızlarda güncellendiği için değişiklik yalnızca aynı kaynağın önceki kaydıyla karşılaştırılarak aranır.
            # Bir kaynağın ilk kaydı başlangıçtır, değişiklik sayılmaz.
            if onceki and SIRA.get(unvan, 0) > SIRA.get(onceki, 0) and not any(
                    d["yeni"] == unvan for d in g["degisiklikler"]):
                g["degisiklikler"].append({"tarih": bugun, "onceki": onceki, "yeni": unvan, "kaynak": kaynak})
                yeni += 1
                print(f"  {ad}: {onceki} -> {unvan} ({kaynak})")
            g["kaynaklar"][kaynak] = unvan
        g["unvan"] = max(g["kaynaklar"].values(), key=lambda u: SIRA.get(u, 0), default="")
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    DOSYA.write_text(json.dumps(gecmis, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(gecmis)} kişi, yeni unvan değişikliği: {yeni}")


if __name__ == "__main__":
    main()
