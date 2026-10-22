#!/usr/bin/env python3
"""DergiPark hasadı.

DergiPark'ın OAI-PMH veri kapısından bütün dergilerin kayıtlarını tarih
aralıklarıyla (aylık pencereler) çeker. Konu alanında ya da anahtar
kelimelerinde "din felsefesi" / "philosophy of religion" geçen makaleleri
data/dergipark/din_felsefesi.jsonl dosyasına yazar. Türkiye akademisi listesindeki
(content/turkiye_akademisi.yaml) kişilerin adıyla yazılmış öteki makaleler de
data/dergipark/akademisyen_makaleleri.jsonl dosyasına yazılır. Ad benzerliğinden doğan
yanlış eşleşmeler sonradan makale sayfasındaki ORCID bilgisiyle ayıklanır (orcid_topla.py).

Tarama en yeni aydan geriye doğru ilerler ve kaldığı yeri
data/dergipark/ilerleme.json dosyasında tutar. Böylece her çalışma bir
önceki çalışmanın bıraktığı yerden devam eder.

Kullanım:
  python3 scripts/dergipark_hasat.py --dakika 300            # geçmiş tarama
  python3 scripts/dergipark_hasat.py --ay 2026-09             # tek bir ayı tara
"""
import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERI = ROOT / "data" / "dergipark"
ESLESEN = VERI / "din_felsefesi.jsonl"
YAZAR = VERI / "akademisyen_makaleleri.jsonl"
ILERLEME = VERI / "ilerleme.json"

OAI = "https://dergipark.org.tr/api/public/oai/"
UA = {"User-Agent": "dinfelsefesi-hasat/1.0 (+https://dinfelsefesi.com.tr; mailto:dinfelsefesi@gmail.com)"}
BEKLEME = 1.5          # istekler arası saniye
EN_ESKI = "2005-01"    # geriye doğru taramanın son ayı

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

ARANAN = ("din felsefesi", "philosophy of religion")


def kucult(s: str) -> str:
    """Türkçe harflere duyarlı küçültme."""
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


GECERSIZ_BAYT = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
KARAKTER_REF = re.compile(rb"&#(x[0-9a-fA-F]+|[0-9]+);")


def _ref_temizle(m):
    kod = m.group(1)
    n = int(kod[1:], 16) if kod[:1] in (b"x", b"X") else int(kod)
    gecerli = n in (9, 10, 13) or 0x20 <= n <= 0xD7FF or 0xE000 <= n <= 0xFFFD or 0x10000 <= n <= 0x10FFFF
    return m.group(0) if gecerli else b" "


CIPLAK_AMP = re.compile(rb"&(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);)")


def xml_coz(veri: bytes) -> ET.Element:
    """Bazı kayıtlarda bozuk XML var (denetim karakteri, geçersiz UTF-8, kaçışsız &).
    Önce olduğu gibi, sonra temizleyerek, en son lxml'in kurtarma kipiyle çözer."""
    try:
        return ET.fromstring(veri)
    except ET.ParseError:
        pass
    temiz = veri.decode("utf-8", errors="replace").encode("utf-8")
    temiz = KARAKTER_REF.sub(_ref_temizle, GECERSIZ_BAYT.sub(b" ", temiz))
    temiz = CIPLAK_AMP.sub(b"&amp;", temiz)
    try:
        return ET.fromstring(temiz)
    except ET.ParseError as hata:
        try:
            from lxml import etree as LET
        except ImportError:
            raise hata
        kok = LET.fromstring(temiz, LET.XMLParser(recover=True, huge_tree=True))
        print(f"  uyarı: XML kurtarma kipiyle okundu ({hata})", file=sys.stderr)
        return ET.fromstring(LET.tostring(kok))


def istek(params: dict) -> ET.Element:
    url = OAI + "?" + urllib.parse.urlencode(params)
    son_hata = None
    for deneme in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                veri = r.read()
            return xml_coz(veri)
        except Exception as hata:  # noqa: BLE001
            son_hata = hata
            bekle = 10 * (deneme + 1)
            print(f"  hata: {type(hata).__name__}: {hata}; {bekle} sn sonra yeniden", file=sys.stderr)
            time.sleep(bekle)
    raise RuntimeError(f"istek başarısız ({type(son_hata).__name__}: {son_hata}): {url}")


def metin(el) -> str:
    return re.sub(r"\s+", " ", html.unescape(el.text or "")).strip()


def kaydi_coz(rec: ET.Element) -> dict | None:
    bas = rec.find("oai:header", NS)
    if bas is None or bas.get("status") == "deleted":
        return None
    md = rec.find("oai:metadata/oai_dc:dc", NS)
    if md is None:
        return None
    alanlar = {}
    for el in md:
        ad = el.tag.split("}")[1]
        alanlar.setdefault(ad, []).append((el.get(XML_LANG, ""), metin(el)))
    konular = [t for _, t in alanlar.get("subject", []) if t]
    baglantilar = [t for _, t in alanlar.get("identifier", [])]
    doi = next((m.group(1) for t in baglantilar for m in [re.search(r"doi\.org/(10\.\S+)", t)] if m), "")
    return {
        "id": metin(bas.find("oai:identifier", NS)).rsplit("/", 1)[-1],
        "dergi_kume": metin(bas.find("oai:setSpec", NS)) if bas.find("oai:setSpec", NS) is not None else "",
        "kayit_tarihi": metin(bas.find("oai:datestamp", NS)),
        "baslik": {d or "?": t for d, t in alanlar.get("title", [])},
        "yazarlar": [t for _, t in alanlar.get("creator", [])],
        "konular": konular,
        "ozet": {d or "?": t for d, t in alanlar.get("description", [])},
        "tarih": [t for _, t in alanlar.get("date", [])],
        "yayinci": [t for _, t in alanlar.get("publisher", [])],
        "kaynak": [t for _, t in alanlar.get("source", [])],
        "baglanti": baglantilar,
        "doi": doi,
        "dil": [t for _, t in alanlar.get("language", [])],
    }


def ad_anahtari(ad: str) -> str:
    """Ad karşılaştırması için: Türkçe harfler sadeleştirilir, yalnızca harf ve rakam kalır."""
    s = kucult(ad).translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def akademisyenler() -> dict:
    import yaml
    kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
    return {ad_anahtari(p["ad"]): p["ad"] for p in kisiler}


AKADEMISYEN = {}


def yazar_eslesir(k: dict) -> list[str]:
    out = []
    for y in k["yazarlar"]:
        soy, _, ad = y.partition(",")
        anahtar = ad_anahtari(f"{ad} {soy}" if ad else y)
        if anahtar in AKADEMISYEN:
            out.append(AKADEMISYEN[anahtar])
    return out


def eslesir_mi(k: dict) -> list[str]:
    """Eşleşmenin nereden geldiğini döndürür: 'alan', 'anahtar' ya da ikisi."""
    nedenler = set()
    for s in k["konular"]:
        ks = kucult(s)
        for aranan in ARANAN:
            if aranan in ks:
                # Virgül içeren satırlar anahtar kelime listesidir, virgülsüz olanlar konu alanı
                nedenler.add("anahtar" if "," in s else "alan")
    return sorted(nedenler)


def pencereyi_tara(ay: str, bilinen: set, cikti, bilinen_y: set, cikti_y) -> dict:
    y, m = map(int, ay.split("-"))
    son = date(y + (m == 12), m % 12 + 1, 1)
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc",
              "from": f"{ay}-01", "until": (date.fromordinal(son.toordinal() - 1)).isoformat()}
    toplam = eslesen = yazar_eslesen = 0
    while True:
        kok = istek(params)
        hata = kok.find("oai:error", NS)
        if hata is not None:
            if hata.get("code") == "noRecordsMatch":
                break
            raise RuntimeError(f"OAI hatası: {hata.get('code')} {metin(hata)}")
        for rec in kok.iterfind("oai:ListRecords/oai:record", NS):
            k = kaydi_coz(rec)
            if not k:
                continue
            toplam += 1
            neden = eslesir_mi(k)
            if neden and k["id"] not in bilinen:
                k["eslesme"] = neden
                k["pencere"] = ay
                cikti.write(json.dumps(k, ensure_ascii=False) + "\n")
                bilinen.add(k["id"])
                eslesen += 1
            elif not neden and k["id"] not in bilinen_y:
                kim = yazar_eslesir(k)
                if kim:
                    k["akademisyen"] = kim
                    k["pencere"] = ay
                    cikti_y.write(json.dumps(k, ensure_ascii=False) + "\n")
                    bilinen_y.add(k["id"])
                    yazar_eslesen += 1
        tok = kok.find("oai:ListRecords/oai:resumptionToken", NS)
        if tok is None or not metin(tok):
            break
        params = {"verb": "ListRecords", "resumptionToken": metin(tok)}
        time.sleep(BEKLEME)
    return {"kayit": toplam, "eslesen": eslesen, "yazar_eslesen": yazar_eslesen}


def onceki_ay(ay: str) -> str:
    y, m = map(int, ay.split("-"))
    return f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dakika", type=float, default=300, help="en fazla çalışma süresi")
    ap.add_argument("--ay", help="yalnızca bu ayı tara (YYYY-AA)")
    args = ap.parse_args()

    VERI.mkdir(parents=True, exist_ok=True)
    ilerleme = json.loads(ILERLEME.read_text(encoding="utf-8")) if ILERLEME.exists() else {"pencereler": {}}
    bilinen = set()
    if ESLESEN.exists():
        for satir in ESLESEN.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                bilinen.add(json.loads(satir)["id"])

    AKADEMISYEN.update(akademisyenler())
    bilinen_y = set()
    if YAZAR.exists():
        for satir in YAZAR.read_text(encoding="utf-8").splitlines():
            if satir.strip():
                bilinen_y.add(json.loads(satir)["id"])
    yazar_p = ilerleme.setdefault("yazar_pencereler", {})

    bitis = time.time() + args.dakika * 60
    with ESLESEN.open("a", encoding="utf-8") as cikti, YAZAR.open("a", encoding="utf-8") as cikti_y:
        if args.ay:
            sirada = [args.ay]
        else:
            bu_ay = date.today().strftime("%Y-%m")
            sirada, ay = [], bu_ay
            while ay >= EN_ESKI:
                # Bu ay ve geçen ay her çalışmada yeniden taranır (ay sonunda eklenen kayıtlar kaçmasın)
                # Akademisyen adına göre tarama sonradan eklendiği için o taramadan geçmemiş aylar da sıraya girer
                if ay not in ilerleme["pencereler"] or ay not in yazar_p or ay in (bu_ay, onceki_ay(bu_ay)):
                    sirada.append(ay)
                ay = onceki_ay(ay)
        for ay in sirada:
            if time.time() > bitis:
                print("süre doldu, sonraki çalışmada devam edilecek")
                break
            t0 = time.time()
            try:
                sonuc = pencereyi_tara(ay, bilinen, cikti, bilinen_y, cikti_y)
            except Exception as hata:  # noqa: BLE001
                cikti.flush()
                mesaj = f"{ay}: {type(hata).__name__}: {hata}"[:500]
                print(f"::warning::{mesaj}")
                ilerleme.setdefault("hatalar", {})[ay] = {"hata": mesaj, "tarih": date.today().isoformat()}
                ILERLEME.write_text(json.dumps(ilerleme, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                continue
            cikti.flush()
            cikti_y.flush()
            ilerleme.get("hatalar", {}).pop(ay, None)
            sonuc["sure_sn"] = round(time.time() - t0)
            sonuc["tarandi"] = date.today().isoformat()
            ilerleme["pencereler"][ay] = {k: v for k, v in sonuc.items() if k != "yazar_eslesen"}
            yazar_p[ay] = {"eslesen": sonuc["yazar_eslesen"], "tarandi": sonuc["tarandi"]}
            ILERLEME.write_text(json.dumps(ilerleme, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            print(f"{ay}: {sonuc['kayit']} kayıt, {sonuc['eslesen']} yeni eşleşme, {sonuc['yazar_eslesen']} akademisyen makalesi, {sonuc['sure_sn']} sn")
    kalan = [a for a in sirada if a not in yazar_p or a not in ilerleme["pencereler"]]
    print(f"toplam eşleşme: {len(bilinen)}; akademisyen makalesi: {len(bilinen_y)}; taranmamış pencere: {len(kalan)}")


if __name__ == "__main__":
    main()
