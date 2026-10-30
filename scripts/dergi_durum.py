#!/usr/bin/env python3
"""Dergiler sayfası için gece taraması.

data/dergiler/dergiler.yaml listesindeki her derginin DergiPark ana sayfasını okur ve şunları
data/dergiler/durum.json dosyasına yazar:
  - makale gönderiminin açık ya da kapalı olduğu, durumun değiştiği tarih ve varsa açılacak tarih
  - yayın modeli (ör. "Süreli Yayın (Haziran - Aralık)")
  - DergiPark'ın verdiği ortalama süreler (ön kontrol, değerlendirme, yayım; gün)
--dizin verilirse ayrıca her derginin Dizinler sayfası okunur: TR Dizin, DOAJ, ESCI, Scopus.

Bir dergi okunamazsa (bağlantı hatası, sayfa düzeni değişmiş) o derginin önceki bilgisi silinmez;
yalnızca hata kaydedilir. Sitede her bilginin hangi tarihte okunduğu görünür.

Kullanım:
  python3 scripts/dergi_durum.py            # yalnızca ana sayfalar
  python3 scripts/dergi_durum.py --dizin    # ana sayfalar ve dizin sayfaları
  python3 scripts/dergi_durum.py --kod tasavvur --dosya sayfa.html   # kaydedilmiş bir sayfayı dener
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LISTE = ROOT / "data" / "dergiler" / "dergiler.yaml"
DURUM = ROOT / "data" / "dergiler" / "durum.json"
UA = {"User-Agent": "dinfelsefesi.com.tr dergi durumu (+https://dinfelsefesi.com.tr/dergiler/; dinfelsefesi@gmail.com)"}
BEKLEME = 1.5
TR = timezone(timedelta(hours=3))


def getir(url: str) -> tuple[str, str]:
    """Sayfayı indirir; (son adres, html) döner. İki kez daha dener."""
    son_hata = None
    for deneme in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.geturl(), r.read().decode("utf-8", "replace")
        except Exception as ex:  # noqa: BLE001
            son_hata = ex
            time.sleep(5 * (deneme + 1))
    raise RuntimeError(str(son_hata))


def temiz(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def ana_sayfa_oku(sayfa: str) -> dict:
    """Derginin ana sayfasından durum bilgilerini çıkarır. Dergi başlığı bulunamazsa ValueError."""
    m = re.search(r'<h1 class="journal-title">(.*?)</h1>', sayfa, re.S)
    if not m:
        raise ValueError("dergi başlığı bulunamadı (sayfa düzeni değişmiş ya da dergi DergiPark'tan ayrılmış olabilir)")
    s = {"baslik": temiz(m.group(1))}
    m = re.search(r"Yayın Modeli:\s*([^<]+?)\s*<", sayfa)
    if m:
        s["yayin_modeli"] = temiz(m.group(1))
    m = re.search(r"Makale Gönderimine (Açık|Kapalı)\s*</h3>(.{0,600})", sayfa, re.S)
    if m:
        s["gonderim"] = "acik" if m.group(1) == "Açık" else "kapali"
        t = re.search(r"(\d\d\.\d\d\.\d{4})(?:\s+\d\d:\d\d)?", m.group(2))
        if t:
            s["gonderim_tarih"] = t.group(1)
    m = re.search(r"Makale Gönderimine Açılacak Tarih</span>\s*<span[^>]*>\s*(\d\d\.\d\d\.\d{4})", sayfa)
    if m:
        s["acilis"] = m.group(1)
    sureler = {}
    for ad, anahtar in (("Ön Kontrol Süresi", "on_kontrol"), ("Değerlendirme Süresi", "degerlendirme"), ("Yayım Süresi", "yayim")):
        m = re.search(re.escape(ad) + r".{0,1500}?font-\[var\(--font-head\)\]\">\s*(\d+)\s*gün", sayfa, re.S)
        if m:
            sureler[anahtar] = int(m.group(1))
    if sureler:
        s["sureler"] = sureler
    return s


DIZIN_DESEN = {
    "trdizin": re.compile(r"tr\s*dizin|ulakb", re.I),
    "doaj": re.compile(r"\bdoaj\b|directory of open access", re.I),
    "esci": re.compile(r"emerging sources|\besci\b", re.I),
    "scopus": re.compile(r"\bscopus\b", re.I),
}


def dizin_sayfasi_oku(sayfa: str) -> dict | None:
    """Dizinler sayfasındaki tablolarda adı geçen dizinleri okur. Tablo yoksa None (bilinmiyor) döner."""
    adlar = re.findall(r'<td class="p-3 align-middle">\s*<a[^>]*>\s*(.*?)\s*</a>', sayfa, re.S)
    adlar = [temiz(a) for a in adlar if temiz(a)]
    if not adlar:
        return None
    return {"liste": adlar, **{k: any(d.search(a) for a in adlar) for k, d in DIZIN_DESEN.items()}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dizin", action="store_true", help="dizin sayfalarını da oku")
    ap.add_argument("--kod", help="yalnızca bu dergi")
    ap.add_argument("--dosya", help="indirmek yerine bu HTML dosyasını oku (deneme için)")
    a = ap.parse_args()

    if a.dosya:
        sayfa = Path(a.dosya).read_text(encoding="utf-8")
        sonuc = dizin_sayfasi_oku(sayfa) if a.dizin else ana_sayfa_oku(sayfa)
        print(json.dumps(sonuc, ensure_ascii=False, indent=1))
        return

    dergiler = yaml.safe_load(LISTE.read_text(encoding="utf-8")) or []
    eski = json.loads(DURUM.read_text(encoding="utf-8")) if DURUM.exists() else {}
    kayit = eski.get("dergiler", {})
    simdi = datetime.now(TR)
    bugun = simdi.date().isoformat()
    tamam = hata = 0
    for d in dergiler:
        kod = d["kod"]
        if a.kod and kod != a.kod:
            continue
        if d.get("dergipark_disi"):
            continue
        k = dict(kayit.get(kod, {}))
        try:
            son, sayfa = getir(f"https://dergipark.org.tr/tr/pub/{kod}")
            yeni = ana_sayfa_oku(sayfa)
            # Bir önceki okumada bulunan ama bu sayfada artık olmayan alanlar (ör. açılacak tarih) silinir
            for alan in ("yayin_modeli", "gonderim", "gonderim_tarih", "acilis", "sureler"):
                k.pop(alan, None)
            k.update(yeni)
            k["okundu"] = bugun
            k.pop("hata", None)
            if not son.rstrip("/").endswith(f"/pub/{kod}"):
                k["yonlendi"] = son
            else:
                k.pop("yonlendi", None)
            tamam += 1
        except Exception as ex:  # noqa: BLE001
            k["hata"] = f"{bugun}: {ex}"[:300]
            hata += 1
            print(f"uyarı: {kod}: {ex}", file=sys.stderr)
        time.sleep(BEKLEME)
        if a.dizin:
            try:
                _, sayfa = getir(f"https://dergipark.org.tr/tr/pub/{kod}/indexes")
                dz = dizin_sayfasi_oku(sayfa)
                if dz is not None:
                    k["dizin"] = {**dz, "okundu": bugun}
            except Exception as ex:  # noqa: BLE001
                print(f"uyarı: {kod} dizinler: {ex}", file=sys.stderr)
            time.sleep(BEKLEME)
        kayit[kod] = k

    cikti = {"tarama": simdi.isoformat(timespec="minutes"), "dergiler": dict(sorted(kayit.items()))}
    if a.dizin:
        cikti["dizin_tarama"] = simdi.isoformat(timespec="minutes")
    elif eski.get("dizin_tarama"):
        cikti["dizin_tarama"] = eski["dizin_tarama"]
    DURUM.write_text(json.dumps(cikti, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{tamam} dergi okundu, {hata} dergi okunamadı")
    # Dergilerin yarısından fazlası okunamadıysa sayfa düzeni değişmiş olabilir: iş başarısız görünsün
    if tamam + hata and hata > (tamam + hata) / 2:
        sys.exit(1)


if __name__ == "__main__":
    main()
