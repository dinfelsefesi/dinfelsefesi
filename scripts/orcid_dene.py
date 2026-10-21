#!/usr/bin/env python3
"""ORCID için kaynak denemesi: hangi yoldan ORCID numarası güvenilir biçimde bulunabilir?
1) ORCID genel arama (ad + soyad), 2) DergiPark makale sayfası, 3) YÖK Akademik profil sayfası.
Sonuç data/orcid/deneme.json dosyasına yazılır."""
import json, re, urllib.parse, urllib.request
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "dinfelsefesi.com.tr ORCID denemesi (dinfelsefesi@gmail.com)"}


def al(url, accept=None):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as ex:  # noqa: BLE001
        return getattr(ex, "code", 0), str(ex)[:300]


kisiler = yaml.safe_load((ROOT / "content/turkiye_akademisi.yaml").read_text(encoding="utf-8"))["kisiler"]
ornek = [p for p in kisiler if p["ad"] in ("Rahim Acar", "Sait Kar", "Abdullah Akgül", "Hasan Tanrıverdi", "Kevser Çelik", "Enis Doko")]
sonuc = {"orcid_arama": [], "dergipark": None, "yok": None}
for p in ornek:
    ad, soyad = p["ad"].rsplit(" ", 1)
    q = f'given-names:"{ad}" AND family-name:"{soyad}"'
    st, govde = al("https://pub.orcid.org/v3.0/expanded-search/?q=" + urllib.parse.quote(q), "application/json")
    kayit = []
    if st == 200:
        for r in (json.loads(govde).get("expanded-result") or [])[:5]:
            kayit.append({"orcid": r.get("orcid-id"), "ad": r.get("given-names"), "soyad": r.get("family-names"),
                          "kurum": r.get("institution-name")})
    sonuc["orcid_arama"].append({"kisi": p["ad"], "universite": p.get("universite"), "durum": st, "sonuc": kayit,
                                 "hata": None if st == 200 else govde})
st, govde = al("https://dergipark.org.tr/tr/pub/tid/article/1886013")
sonuc["dergipark"] = {"durum": st, "orcid": sorted(set(re.findall(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", govde))),
                      "uzunluk": len(govde), "bas": govde[:200] if st != 200 else ""}
yok = ornek[0].get("yok") if ornek else ""
st, govde = al("https://akademik.yok.gov.tr/AkademikArama/AkademisyenGorevOgrenimBilgileri?islem=direct&authorId=" + yok)
sonuc["yok"] = {"durum": st, "orcid": sorted(set(re.findall(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", govde))), "uzunluk": len(govde),
                "bas": govde[:200] if st != 200 else ""}
if sonuc["orcid_arama"] and sonuc["orcid_arama"][0]["sonuc"]:
    oid = sonuc["orcid_arama"][0]["sonuc"][0]["orcid"]
    st, govde = al(f"https://pub.orcid.org/v3.0/{oid}/works", "application/json")
    sonuc["eserler_ornek"] = {"orcid": oid, "durum": st,
                              "sayi": len(json.loads(govde).get("group", [])) if st == 200 else 0}
(ROOT / "data/orcid").mkdir(parents=True, exist_ok=True)
(ROOT / "data/orcid/deneme.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(sonuc, ensure_ascii=False, indent=1)[:3000])
