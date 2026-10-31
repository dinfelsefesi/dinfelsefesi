#!/usr/bin/env python3
"""ORCID kayıtlarındaki DOI'li eserleri DergiPark makaleleriyle aynı sözlükle başlıklara ayırır.

Girdi: data/orcid/eserler.json, data/orcid/doi_kunye.json, data/orcid/orcid.json, content/turkiye_akademisi.yaml,
       data/dergipark/din_felsefesi.jsonl (zaten listede olan eserleri ayıklamak için), data/dergipark/sozluk.yaml,
       data/orcid/elle_tasnif.yaml (DOI'ye göre tek tek düzeltmeler)
Çıktı: data/orcid/eser_sinif.json  DOI -> {baslik, yazarlar, sahipler, dergi, yil, tur, basliklar, ilgili, durum, ...}

Durumlar: konulu (en az bir başlığa girdi, sitede ağa ve eser listelerine girer), konusuz (anahtar kelimesi
hiçbir başlığa uymadı, yalnızca akademisyen sayfasında kalır), kelime-yok, kapsam-disi (elle çıkarıldı).

Kullanım:
  python3 scripts/orcid_siniflandir.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VERI = ROOT / "data" / "orcid"
sys.path.insert(0, str(ROOT / "scripts"))
import dergipark_siniflandir as dps  # noqa: E402
from orcid_doi import doi_temiz  # noqa: E402
from orcid_topla import kisalt  # noqa: E402

TANITIM_IPUCU = {"Kitap Tanıtımı", "Kitap İncelemesi", "Kitap Değerlendirmesi", "Kitap Kritiği", "Book Review"}
CEVIRI_IPUCU = {"Çeviri", "Tercüme", "Translation"}
TANITIM_BASLIK = re.compile(r"^\s*(book\s+review|review\s+of|kitap\s+(tan[ıi]t[ıi]m[ıi]|de[ğg]erlendirme(si)?|incelemesi))\b"
                            r"|,\s*(19|20)\d\d\s*,?\s*\d+\s*(s|ss|sy|pp|p|sayfa|pages)\b\.?|,\s*(written|edited)\s+by\b"
                            # "Yazar: ..." ya da sonda "(Şehir: Yayınevi, Yıl)" künyesi (31.10.2026, Ricoeur tanıtımı)
                            r"|\b(yazar(lar)?|author)\s*:|\(\s*[^():]{2,40}:\s*[^()]{2,80},\s*(19|20)\d\d\s*\)\s*\.?\s*$", re.I)


def kelime_basliklari(kelimeler, kurallar, genel):
    haric = {dps.katla("din felsefesi"), dps.katla("philosophy of religion")}
    out, eslesen = set(), []
    for k in (dps.katla(x) for x in kelimeler):
        if not k or k in haric or any(dps.eslesir(g, k) for g in genel):
            continue
        for b, kaliplar in kurallar.items():
            if any(dps.eslesir(kal, k) for kal in kaliplar):
                out.add(b)
                eslesen.append(f"{k} → {b}")
    for b in list(out):
        if b in dps.UST:
            out.add(dps.UST[b])
    return out, eslesen


def main():
    eserler = json.loads((VERI / "eserler.json").read_text(encoding="utf-8"))["eserler"]
    kunye = json.loads((VERI / "doi_kunye.json").read_text(encoding="utf-8"))["kunye"]
    orcid_kayit = json.loads((VERI / "orcid.json").read_text(encoding="utf-8")).get("orcid", {})
    kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
    elle_dosya = VERI / "elle_tasnif.yaml"
    elle = {doi_temiz(k): v for k, v in (yaml.safe_load(elle_dosya.read_text(encoding="utf-8")) or {}).items()} \
        if elle_dosya.exists() else {}
    _, kurallar, genel = dps.yukle()

    # ORCID -> listedeki kişi(ler)
    sahip = {}
    for p in kisiler:
        oid = p.get("orcid") or orcid_kayit.get(kisalt(p["ad"]))
        if oid:
            sahip.setdefault(oid, []).append(p["ad"])

    # DergiPark listesinde zaten olanlar: DOI, makale kimliği ya da başlık eşleşmesi
    # Akademisyen adıyla bulunan ve yazarı doğrulanmış DergiPark makaleleri de sayılır (akademisyen_siniflandir.py)
    dp_doi, dp_id, dp_ad = set(), set(), set()
    ak_dosya = ROOT / "data/dergipark/akademisyen_sinif.json"
    dogrulanan = set(json.loads(ak_dosya.read_text(encoding="utf-8"))) if ak_dosya.exists() else set()
    satirlar = (ROOT / "data/dergipark/din_felsefesi.jsonl").read_text(encoding="utf-8").splitlines()
    if (ROOT / "data/dergipark/akademisyen_makaleleri.jsonl").exists():
        satirlar += [l for l in (ROOT / "data/dergipark/akademisyen_makaleleri.jsonl").read_text(encoding="utf-8").splitlines()
                     if l.strip() and json.loads(l)["id"] in dogrulanan]
    for l in satirlar:
        if not l.strip():
            continue
        r = json.loads(l)
        dp_id.add(str(r["id"]))
        for b in r.get("baglanti") or []:
            if "doi.org" in b:
                dp_doi.add(doi_temiz(b))
        for t in (r.get("baslik") or {}).values():
            dp_ad.add(kisalt(t))

    tum = {}
    for oid, ws in eserler.items():
        for w in ws:
            d = doi_temiz(w.get("doi"))
            if not d:
                continue
            x = tum.setdefault(d, {"orcid": w, "sahipler": []})
            x["sahipler"] += [a for a in sahip.get(oid, []) if a not in x["sahipler"]]

    sonuc, say = {}, Counter()
    for d, x in sorted(tum.items()):
        w, k = x["orcid"], kunye.get(d) or {}
        baslik = (k.get("baslik") or w["baslik"]).strip()
        sayfa_id = (re.findall(r"/(\d{4,})(?:[/?#]|$)", k.get("sayfa") or "") or [""])[-1]
        if d in dp_doi or kisalt(baslik) in dp_ad or kisalt(w["baslik"]) in dp_ad or (sayfa_id and sayfa_id in dp_id):
            say["dergipark-listesinde"] += 1
            continue
        # OpenAlex'in konu kümesi adları (topics/concepts) çok geniş olduğundan yalnızca anahtar kelimeler kullanılır
        kelimeler = list(k.get("kelimeler") or [])
        basliklar, eslesen = kelime_basliklari(kelimeler, kurallar, genel)
        # DergiPark sayfasında makale türü etiketi ilk sırada geçer; sonrakiler menü ve dergi bölüm adlarıdır
        ipucu = set((k.get("tur_ipucu") or [])[:1])
        tur = ""
        if w.get("tur") == "book":
            tur = "kitap"
        elif w.get("tur") == "book-chapter":
            tur = "kitap-bolumu"
        elif w.get("tur") == "book-review" or TANITIM_BASLIK.search(baslik) or ipucu & TANITIM_IPUCU:
            tur = "kitap-tanitimi"
        elif w.get("tur") == "translation" or ipucu & CEVIRI_IPUCU:
            tur = "ceviri"
        durum = "konulu" if basliklar else ("kelime-yok" if not kelimeler else "konusuz")
        e_ = elle.get(d) or {}
        if e_.get("tur") is not None:
            tur = e_["tur"]
        karar = e_.get("karar")
        if karar == "kapsam-disi":
            durum, basliklar = "kapsam-disi", set()
        elif isinstance(karar, list):
            basliklar = set(karar) | {dps.UST[b] for b in karar if b in dps.UST}
            durum = "konulu" if basliklar else durum
        elif karar:
            basliklar |= {karar} | ({dps.UST[karar]} if karar in dps.UST else set())
            durum = "konulu"
        tanitim = tur in ("kitap-tanitimi", "ceviri")
        sonuc[d] = {
            "baslik": e_.get("baslik") or baslik, "yazarlar": k.get("yazarlar") or [], "sahipler": x["sahipler"],
            "dergi": (k.get("dergi") or w.get("dergi") or "").strip(), "yil": str(k.get("yil") or w.get("yil") or ""),
            "tur": tur, "basliklar": [] if tanitim else sorted(basliklar), "ilgili": sorted(basliklar) if tanitim else [],
            "durum": durum, "kelimeler": kelimeler, "eslesen": eslesen, "kaynak": k.get("kaynak") or "",
            "elle": bool(e_),
        }
        say[durum] += 1
    (VERI / "eser_sinif.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(dict(say))


if __name__ == "__main__":
    main()
