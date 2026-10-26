#!/usr/bin/env python3
"""Türkiye akademisi listesindeki kişilerin unvan değişikliklerini izler.

Girdi: content/turkiye_akademisi.yaml (YÖK Akademik'teki unvan), data/avesis/yayinlar.json (AVESİS'teki güncel unvan)
Çıktı: data/akademi/unvan_gecmisi.json  kişi adı -> {unvan, kaynak, tarih, degisiklikler: [{tarih, onceki, yeni, kaynak}]}

Bir kişinin bilinen unvanından daha yüksek bir unvan görüldüğünde değişiklik o günün tarihiyle kaydedilir (tarih,
değişikliğin sitede fark edildiği gündür; unvanın alındığı gün değildir). Kaynaklar arasındaki gecikme yüzünden
unvanın gerilemesi kaydedilmez. İlk çalıştırmada her kişinin o günkü unvanı başlangıç olarak yazılır.
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
        adaylar = [(p.get("unvan") or "", "YÖK Akademik"), ((avesis.get(ad) or {}).get("unvan") or "", "AVESİS")]
        unvan, kaynak = max(adaylar, key=lambda x: SIRA.get(x[0], 0))
        if not unvan:
            continue
        g = gecmis.get(ad)
        if not g:
            gecmis[ad] = {"unvan": unvan, "kaynak": kaynak, "tarih": bugun, "degisiklikler": []}
        elif SIRA.get(unvan, 0) > SIRA.get(g["unvan"], 0):
            g["degisiklikler"].append({"tarih": bugun, "onceki": g["unvan"], "yeni": unvan, "kaynak": kaynak})
            g.update(unvan=unvan, kaynak=kaynak, tarih=bugun)
            yeni += 1
            print(f"  {ad}: {g['degisiklikler'][-1]['onceki']} -> {unvan} ({kaynak})")
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    DOSYA.write_text(json.dumps(gecmis, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(gecmis)} kişi, yeni unvan değişikliği: {yeni}")


if __name__ == "__main__":
    main()
