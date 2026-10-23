#!/usr/bin/env python3
"""Türkiye akademisi listesindeki kişilerin adıyla bulunan öteki DergiPark makalelerini doğrular ve başlıklara ayırır.

Girdi: data/dergipark/akademisyen_makaleleri.jsonl (dergipark_hasat.py), data/orcid/makale_yazar.json ve
       makale_profil.json (orcid_topla.py, makale sayfalarındaki yazar bilgisi), data/orcid/orcid.json, eserler.json,
       content/turkiye_akademisi.yaml, data/dergipark/sozluk.yaml,
       data/dergipark/akademisyen_elle.yaml (makale kimliğine göre elle kararlar),
       data/orcid/elle_tasnif.yaml (DOI'ye göre elle kararlar, aynı makale ORCID'den de geldiyse)
Çıktı: data/dergipark/akademisyen_sinif.json  makale kimliği -> {akademisyenler, basliklar, ilgili, tur, durum, ...}

Yazar doğrulaması. Ad benzerliği yetmez; makalenin o kişiye ait olduğu şu kanıtlardan biriyle kabul edilir:
  0. makale kişinin DergiPark profilinde listeleniyor (data/dergipark/profiller.yaml, profil_topla.py),
  1. makalenin DOI'si kişinin ORCID kaydında var,
  2. makale sayfasında yazarın ORCID numarası kişininkiyle aynı (farklıysa makale başkasınındır),
  3. sayfadaki DergiPark profili, kişiye ait olduğu başka bir makaleyle kanıtlanmış profille aynı,
  4. sayfadaki yazar kurumu kişinin YÖK'teki üniversitesiyle aynı.
Kanıt bulunamayan makaleler alınmaz.

Durumlar: konulu (ağa ve eser listelerine girer), konusuz / kelime-yok / kapsam-disi (yalnızca akademisyen sayfasında).
Elle "yazar: dogru" başka kanıt bulunamayan makaleyi kişiye bağlar (ad ve konu açıkça kişiyi gösteriyorsa).
Elle karar "yanlis-kisi" makaleyi tamamen çıkarır (DergiPark sayfasında başka bir kişinin ORCID'i ya da profili bağlanmış olabiliyor).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DP = ROOT / "data" / "dergipark"
OR = ROOT / "data" / "orcid"
sys.path.insert(0, str(ROOT / "scripts"))
import dergipark_siniflandir as dps  # noqa: E402
from orcid_doi import doi_temiz  # noqa: E402
from orcid_siniflandir import TANITIM_BASLIK, kelime_basliklari  # noqa: E402
from orcid_topla import kisalt  # noqa: E402

KURUM_GENEL = re.compile(r"(universitesi|university|universite|ilahiyat|fakultesi|faculty|of|theology|divinity|egitim|"
                         r"bilimler|sosyal|enstitusu|islami|islamic|-)")


def kurum_anahtari(s: str) -> set:
    return {w for w in KURUM_GENEL.sub(" ", kisalt(s)).split() if len(w) > 3}


def oku_json(yol, anahtar=None):
    if not yol.exists():
        return {}
    v = json.loads(yol.read_text(encoding="utf-8"))
    return v.get(anahtar, {}) if anahtar else v


def oku_yaml(yol):
    return (yaml.safe_load(yol.read_text(encoding="utf-8")) or {}) if yol.exists() else {}


def main():
    kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
    orcid_kayit = oku_json(OR / "orcid.json", "orcid")
    orcid = {p["ad"]: (p.get("orcid") or orcid_kayit.get(kisalt(p["ad"]), "")) for p in kisiler}
    universite = {p["ad"]: p.get("universite", "") for p in kisiler}
    eserler = oku_json(OR / "eserler.json", "eserler")
    orcid_doi = {ad: {doi_temiz(w["doi"]) for w in eserler.get(o, []) if w.get("doi")} for ad, o in orcid.items() if o}
    sayfa = oku_json(OR / "makale_yazar.json")
    profil = oku_json(OR / "makale_profil.json")
    elle = {str(k): v for k, v in oku_yaml(DP / "akademisyen_elle.yaml").items()}
    elle_doi = {doi_temiz(k): v for k, v in oku_yaml(OR / "elle_tasnif.yaml").items()}
    _, kurallar, genel = dps.yukle()
    makaleler = [json.loads(l) for l in (DP / "akademisyen_makaleleri.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    def giris(r, ad):
        return next((y for y in sayfa.get(r["id"], []) if kisalt(y["ad"]) == kisalt(ad)), None)

    def profili(r, ad):
        return next((h for n, h in profil.get(r["id"], {}).items() if kisalt(n) == kisalt(ad)), None)

    # 1) Yazar doğrulaması (iki tur: ilk turda kanıtlanan profiller ikinci turda kullanılır)
    # Elle bildirilen, kişiye ait olduğu bilinen DergiPark profilleri ve bu profillerde listelenen makaleler
    profiller = {ad: {str(h) for h in hs or []} for ad, hs in oku_yaml(DP / "profiller.yaml").items()}
    for ad, hs in oku_json(DP / "profil_bulunan.json").items():
        profiller.setdefault(ad, set()).update(hs)
    profil_listesi = {ad: set(ids) for ad, ids in oku_json(DP / "profil_makaleleri.json").items()}
    karar = {}
    for _ in range(2):
        for r in makaleler:
            for ad in r.get("akademisyen") or []:
                if karar.get((r["id"], ad), ("",))[0] in ("dogru", "yanlis"):
                    continue
                g, h, o = giris(r, ad), profili(r, ad), orcid.get(ad)
                d = doi_temiz(r.get("doi") or "")
                if (elle.get(r["id"]) or {}).get("yazar") == "dogru":
                    s = ("dogru", "elle")
                elif r["id"] in profil_listesi.get(ad, set()):
                    s = ("dogru", "profil-listesi")
                elif d and d in orcid_doi.get(ad, set()):
                    s = ("dogru", "orcid-kaydi")
                elif g and g["orcid"] and o:
                    s = ("dogru", "orcid") if g["orcid"] == o else ("yanlis", "orcid-farkli")
                elif g and g["orcid"]:
                    s = ("belirsiz", "kisinin-orcidi-bilinmiyor")
                elif h and h in profiller.get(ad, set()):
                    s = ("dogru", "profil")
                elif g and g["kurum"] and kurum_anahtari(g["kurum"]) & kurum_anahtari(universite.get(ad, "")):
                    s = ("dogru", "kurum")
                else:
                    s = ("belirsiz", "kanit-yok")
                karar[(r["id"], ad)] = s
                if s[0] == "dogru" and h:
                    profiller.setdefault(ad, set()).add(h)

    # 2) Başlıklara ayırma (DergiPark din felsefesi makaleleriyle aynı sözlük)
    sonuc, say = {}, Counter()
    for r in makaleler:
        kim = [ad for ad in r.get("akademisyen") or [] if karar[(r["id"], ad)][0] == "dogru"]
        if (elle.get(r["id"]) or {}).get("karar") == "yanlis-kisi":  # sayfadaki ORCID/profil bilgisi yanlış bağlanmış
            kim = []
        say["dogrulanan" if kim else "dogrulanamayan"] += 1
        if not kim:
            continue
        kelimeler = dps.anahtar_kelimeler(r)
        basliklar, eslesen = kelime_basliklari(kelimeler, kurallar, genel)
        baslik = r["baslik"].get("tr-TR") or next(iter(r["baslik"].values()), "")
        tur = "kitap-tanitimi" if any(TANITIM_BASLIK.search(t) for t in r["baslik"].values()) else ""
        durum = "konulu" if basliklar else ("kelime-yok" if not kelimeler else "konusuz")
        e_ = elle.get(r["id"]) or elle_doi.get(doi_temiz(r.get("doi") or "")) or {}
        if e_.get("tur") is not None:
            tur = e_["tur"]
        k_ = e_.get("karar")
        if k_ == "kapsam-disi":
            durum, basliklar = "kapsam-disi", set()
        elif isinstance(k_, list):
            basliklar = set(k_) | {dps.UST[b] for b in k_ if b in dps.UST}
            durum = "konulu" if basliklar else durum
        elif k_:
            basliklar |= {k_} | ({dps.UST[k_]} if k_ in dps.UST else set())
            durum = "konulu"
        tanitim = tur in ("kitap-tanitimi", "ceviri")
        sonuc[r["id"]] = {"akademisyenler": kim, "kanit": {ad: karar[(r["id"], ad)][1] for ad in kim},
                          "basliklar": [] if tanitim else sorted(basliklar), "ilgili": sorted(basliklar) if tanitim else [],
                          "tur": tur, "durum": durum, "eslesen": eslesen, "baslik": baslik, "elle": bool(e_)}
        say[durum] += 1
    (DP / "akademisyen_sinif.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(dict(say), Counter(v[1] for v in karar.values()))


if __name__ == "__main__":
    main()
