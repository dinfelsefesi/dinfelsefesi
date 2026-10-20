"""Geçici deneme 4: kayıtlarda anahtar kelime alanı."""
import re, urllib.request
UA = {"User-Agent": "dinfelsefesi-deneme/1.0 (mailto:dinfelsefesi@gmail.com)"}
OAI = "https://dergipark.org.tr/api/public/oai/"
def al(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", "replace")
for fmt in ["oai_dc", "oai_mods"]:
    r = al(OAI + f"?verb=ListRecords&metadataPrefix={fmt}&from=2026-10-01&until=2026-10-02")
    parts = r.split("<record>")
    print(f"=== {fmt}: {len(parts)-1} kayıt; sayfalama: {re.findall(r'<resumptionToken[^>]*>', r)[:1]}")
    if len(parts) > 1:
        print(parts[1].split("</record>")[0][:2200])
    print("subject:", re.findall(r"<(?:dc:subject|mods:topic|topic)[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</", r, re.S)[:15])
