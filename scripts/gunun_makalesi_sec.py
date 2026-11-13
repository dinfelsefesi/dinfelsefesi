#!/usr/bin/env python3
"""Günün makalesini kurala göre seçer ve content/makaleler.json'a ekler.

Kural (content/FISLER.md, "Günün makalesi"):
- Her ayın başındaki hasatla gelen yeni liste (en yeni aylık hasat penceresi) öne alınır. Yeni liste bitince
  sıra, DergiPark sayfasındaki yayım tarihine göre yeniden eskiye, eski makalelerle sürer (data/dergipark/yayim_tarihi.json;
  tarihi bilinmeyenlerde DergiPark kaydındaki tarih kullanılır).
- Yazarlarından en az biri content/turkiye_akademisi.yaml listesinde olmalı.
- Konusu din felsefesi başlıklarıyla eşleşmiş (durum "konulu") makaleler seçilir; kitap tanıtımı, çeviri vb. seçilmez.
- Özeti olmayan makale seçilmez.

Tanıtım metni yazılmaz. Makalenin kendi Türkçe özeti, yazarın özeti olarak olduğu gibi gösterilir.
Böylece makalede olmayan hiçbir şey sitede yer almaz. Kayıtlar "otomatik": true ile işaretlenir.

Bugünden itibaren --gun gün ilerisine kadar boş kalan günler doldurulur.
Kullanım: python3 scripts/gunun_makalesi_sec.py [--gun 10] [--deneme]
Kalan aday sayısı 14'ün altına inerse çıkış kodu 3 olur (iş akışı issue açar).
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
MAKALELER = ROOT / "content" / "makaleler.json"
AKADEMI = ROOT / "content" / "turkiye_akademisi.yaml"
BASLIKLAR = ROOT / "content" / "basliklar"
DP = ROOT / "data" / "dergipark"

TR_KUCUK_SOZ = {"ve", "ile", "için", "bir", "de", "da", "mi", "mı", "mu", "mü", "ki", "veya", "ya"}
EN_KUCUK_SOZ = {"of", "the", "in", "and", "a", "an", "on", "to", "for", "as", "from", "by", "with", "at", "or"}
UYARI_ESIGI = 14


def tr_kucuk(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def tr_buyuk_ilk(w: str) -> str:
    for i, c in enumerate(w):
        if c.isalpha():
            b = {"i": "İ", "ı": "I"}.get(c, c.upper())
            return w[:i] + b + w[i + 1:]
    return w


def bugun() -> date:
    """build.py ile aynı gün hesabı: İstanbul saatiyle 19.30'dan sonra yeni gün başlar."""
    return (datetime.now(ZoneInfo("Europe/Istanbul")) + timedelta(hours=4, minutes=30)).date()


def baslik_duzelt(t: str, dil: str) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    if not any(c.isalpha() for c in t) or t != t.upper():
        return t
    kucuk = TR_KUCUK_SOZ if dil == "tr" else EN_KUCUK_SOZ
    out, onceki = [], ""
    for i, w in enumerate(t.split(" ")):
        lw = tr_kucuk(w) if dil == "tr" else w.lower()
        if i > 0 and lw in kucuk and not onceki.endswith(":"):
            out.append(lw)
        else:
            out.append((tr_buyuk_ilk(lw) if dil == "tr" else lw[:1].upper() + lw[1:]))
        onceki = w
    return " ".join(out)


def yazar_adi(s: str) -> str:
    if "," in s:
        soyad, ad = [p.strip() for p in s.split(",", 1)]
        return f"{ad} {soyad}"
    return s.strip()


def cumleler(metin: str) -> list:
    return re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜÂÎÛ0-9\"“(])", metin.strip())


def paragraflar(metin: str, sinir: int = 750) -> str:
    out, cur = [], ""
    for c in cumleler(metin):
        if cur and len(cur) + len(c) > sinir:
            out.append(cur)
            cur = c
        else:
            cur = (cur + " " + c).strip()
    if cur:
        out.append(cur)
    return "\n\n".join(out)


def lead_yap(metin: str) -> str:
    ilk = cumleler(metin)[0]
    if len(ilk) > 260:
        ilk = ilk[:257].rsplit(" ", 1)[0] + "…"
    return ilk


def basliklar_adlari() -> dict:
    ad = {}
    for p in BASLIKLAR.glob("*.md"):
        m = re.search(r"^kimlik:\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        n = re.search(r"^ad:\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        if m and n:
            ad[m.group(1).strip()] = n.group(1).strip().strip("'\"")
    return ad


def anahtar_kelimeler(konular: list) -> list:
    """Kayıtta Türkçe satır genellikle önce, İngilizce satır sonra gelir. Türkçe satır ayırt edilemiyorsa etiket verilmez."""
    satirlar = [k for k in konular if "," in k]
    tr = [k for k in satirlar if "philosophy of religion" not in k.lower()]
    if len(satirlar) >= 2 and tr:
        secili = tr[0]
    elif len(satirlar) == 1 and "din felsefesi" in satirlar[0].lower():
        secili = satirlar[0]
    else:
        return []
    return [k.strip().rstrip(".") for k in secili.split(",") if k.strip() and tr_kucuk(k.strip()) != "din felsefesi"][:4]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=10, help="bugünden kaç gün ilerisine kadar doldurulsun")
    ap.add_argument("--deneme", action="store_true", help="dosyaya yazma, yalnız göster")
    a = ap.parse_args()

    items = json.loads(MAKALELER.read_text(encoding="utf-8"))
    raw_sonu = "\n" if MAKALELER.read_text(encoding="utf-8").endswith("\n") else ""
    sinif = json.loads((DP / "akademisyen_sinif.json").read_text(encoding="utf-8"))
    yayim = json.loads((DP / "yayim_tarihi.json").read_text(encoding="utf-8"))
    liste = {tr_kucuk(p["ad"]) for p in (yaml.safe_load(AKADEMI.read_text(encoding="utf-8")) or {}).get("kisiler") or []}
    bas_ad = basliklar_adlari()

    satirlar, kaynak_b = {}, set()
    for ad_, b_ in (("din_felsefesi.jsonl", True), ("akademisyen_makaleleri.jsonl", False)):
        for l in (DP / ad_).read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                satirlar.setdefault(r["id"], r)
                if b_:
                    kaynak_b.add(r["id"])
    # Anahtar kelimesinde "din felsefesi" geçen makaleler (siniflandirma.json); kitap tanıtımı/çeviri türleri dışarıda
    sf = json.loads((DP / "siniflandirma.json").read_text(encoding="utf-8"))
    anahtar_ids = {x["id"] for x in sf["makaleler"]}
    yturu = set(str(k) for k in (yaml.safe_load((DP / "yayin_turu.yaml").read_text(encoding="utf-8")) or {}))

    # Daha önce kullanılanlar: DergiPark kimliği, DOI ya da başlıkla eşleşir
    kullanilan, kimlik_of = set(), {}
    for n, m in enumerate(items):
        for k, r in satirlar.items():
            baglar = r.get("baglanti") or []
            if (m.get("url") and f"/article/{k}" in m["url"]) or (m.get("doi") and (m["doi"] == r.get("doi") or any(m["doi"] in b for b in baglar))) \
                    or tr_kucuk(m["title_tr"]) == tr_kucuk(r["baslik"].get("tr-TR", "")):
                kullanilan.add(k)
                kimlik_of[n] = k

    # Her ayın başındaki hasatla gelen yeni liste: en yeni aylık hasat penceresindeki makaleler öne alınır.
    # Yeni liste bitince sıra, yayım tarihine göre yeniden eskiye, eski makalelerden sürer.
    pencereler = [r.get("pencere") for r in satirlar.values() if re.fullmatch(r"\d{4}-\d{2}", str(r.get("pencere") or ""))]
    yeni_pencere = max(pencereler) if pencereler else ""

    def yeni_mi(k) -> int:
        return 1 if k in satirlar and yeni_pencere and satirlar[k].get("pencere") == yeni_pencere else 0

    adaylar, adaylar_v = [], {}
    for k, r in satirlar.items():
        if k in kullanilan:
            continue
        if k in kaynak_b:
            if k not in anahtar_ids or k in yturu:
                continue
            yazarlar_ = [tr_kucuk(yazar_adi(y)) for y in r.get("yazarlar") or []]
            if not any(y in liste for y in yazarlar_):
                continue
            v = {"basliklar": next((x["basliklar"] for x in sf["makaleler"] if x["id"] == k), [])}
            if not v["basliklar"]:  # sitenin başlıklarından hiçbirine bağlanmamış ("konusuz") makale seçilmez
                continue
        else:
            v = sinif.get(k)
            if not v or v.get("durum") != "konulu" or v.get("tur"):
                continue
            if not any(tr_kucuk(ad) in liste for ad in v.get("akademisyenler") or []):
                continue
        ozet = ((r.get("ozet") or {}).get("tr-TR") or "").strip()
        if not ozet or not r["baslik"].get("tr-TR"):
            continue
        tarih = yayim.get(k) or (r.get("tarih") or [""])[0]
        if not tarih:
            continue
        adaylar.append((tarih[:10], k))
        adaylar_v[k] = v
    adaylar.sort(key=lambda x: (yeni_mi(x[1]), x[0]), reverse=True)
    print(f"aday: {len(adaylar)}, kullanılmış: {len(kullanilan)}, yeni liste (pencere {yeni_pencere}): {sum(yeni_mi(k) for _, k in adaylar)}")

    b = bugun()
    sabit_son = (b + timedelta(days=1)).isoformat()  # bugün ve yarın değişmez (yarının sayfası ve görseli önceden yayımlanır)
    sabit = [m for m in items if (m.get("gun") or "") <= sabit_son]
    kuyruk = [m for m in items if (m.get("gun") or "") > sabit_son]
    kuyruk_kimlik = {id(m): kimlik_of.get(n) for n, m in enumerate(items)}
    dolu = {m["gun"] for m in sabit}
    gunler = [(b + timedelta(days=i)).isoformat() for i in range(0, 400)]
    gunler = [g for g in gunler if g not in dolu]
    bos = [g for g in gunler if g <= (b + timedelta(days=a.gun)).isoformat()]
    yeniler, kimlikler = [], {}
    for tarih, k in adaylar[:len(bos)]:
        r, v = satirlar[k], adaylar_v[k]
        dil = (r.get("dil") or ["tr"])[0]
        tr_b = baslik_duzelt(r["baslik"]["tr-TR"], "tr")
        en_b = baslik_duzelt(r["baslik"].get("en-US", ""), "en")
        ozet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r["ozet"]["tr-TR"])).strip()
        baglar = r.get("baglanti") or []
        url = next((x for x in baglar if "dergipark.org.tr" in x), baglar[0] if baglar else "")
        dergi = re.sub(r"\s+No\.?\s*\d+.*$", "", (r.get("kaynak") or [""])[0]).strip()
        dergi = re.sub(r",\s*Vol\.?\s*\d+.*$", "", dergi).strip()
        adlar = [bas_ad[x] for x in v.get("basliklar") or [] if x in bas_ad]
        if adlar:
            why = "Makale, anahtar kelimeleri bakımından sitedeki " + (adlar[0] if len(adlar) == 1 else ", ".join(adlar[:-1]) + " ve " + adlar[-1]) \
                  + (" başlığıyla" if len(adlar) == 1 else " başlıklarıyla") + " ilişkilendirilmiştir."
        else:
            why = ""
        m_ = {
            "date": tarih, "title_tr": tr_b, "title_en": en_b, "lang": dil,
            "authors": ", ".join(yazar_adi(y) for y in r["yazarlar"]), "journal": dergi, "year": tarih[:4],
            "doi": r.get("doi") or "", "url": "" if r.get("doi") else url, "open_access": "evet",
            "lead": lead_yap(ozet), "summary_tr": paragraflar(ozet), "why_tr": why,
            "tags": anahtar_kelimeler(r.get("konular") or []), "otomatik": True,
        }
        yeniler.append(m_)
        kimlikler[id(m_)] = k
    kuyruk_kimlik.update(kimlikler)

    def anahtar(m):
        return (yeni_mi(kuyruk_kimlik.get(id(m))), m["date"])

    # Kuyruk (yarından sonrası): önce yeni liste, sonra yayım tarihine göre yeniden eskiye. Boş günlere sırayla dağıtılır.
    # Sığmayan otomatik kayıtlar havuza döner (yeniden üretilir); elle yazılmış tanıtımlar hiçbir zaman atılmaz.
    secilen, geri = [], []
    for m in sorted(kuyruk + yeniler, key=anahtar, reverse=True):
        if len(secilen) < len(bos) or not m.get("otomatik"):
            secilen.append(m)
        else:
            geri.append(m)
    adaylar = [x for x in adaylar if x[1] not in {kuyruk_kimlik[id(m)] for m in secilen if id(m) in kimlikler}]
    # yeniler arasından seçilemeyenler zaten adaylar listesinde kalır
    assert len(secilen) <= len(gunler)
    for m, g in zip(secilen, gunler):
        if m.get("gun") != g:
            print(f"{g}  {m['date']}  {'YENİ ' if yeni_mi(kuyruk_kimlik.get(id(m))) else '     '}{m['title_tr'][:68]}")
        m["gun"] = g
    kuyruk = secilen
    items = sabit + kuyruk

    kalan = len(adaylar)
    print(f"kuyruk: {len(kuyruk)}, kalan aday: {kalan}")
    if not a.deneme:
        MAKALELER.write_text(json.dumps(items, ensure_ascii=False, indent=1) + raw_sonu, encoding="utf-8")
    return 3 if kalan < UYARI_ESIGI else 0


if __name__ == "__main__":
    sys.exit(main())
