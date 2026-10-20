"""Geçici deneme 3: veri kapısı kayıtlarında anahtar kelime var mı, ölçek ne?"""
import re, urllib.request
UA = {"User-Agent": "dinfelsefesi-deneme/1.0 (mailto:dinfelsefesi@gmail.com)"}
OAI = "https://dergipark.org.tr/api/public/oai/"
def al(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", "replace")
print("=== Biçimler"); print(re.findall(r"<metadataPrefix>([^<]+)", al(OAI + "?verb=ListMetadataFormats")))
r = al(OAI + "?verb=ListRecords&metadataPrefix=oai_dc&from=2026-10-01&until=2026-10-01")
rec = r.split("<record>")[1].split("</record>")[0]
print("=== Ham kayıt örneği"); print(rec[:2500])
print("=== Sayfalama"); print(re.findall(r"<resumptionToken[^>]*>", r)[:1])
print("=== subject (CDATA dahil) örnekleri")
print(re.findall(r"<dc:subject[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</dc:subject>", r, re.S)[:12])
