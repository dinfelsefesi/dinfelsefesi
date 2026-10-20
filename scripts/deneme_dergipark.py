"""Geçici deneme 2: DergiPark'ta anahtar kelimeyle arama ve veri kapısının ölçeği."""
import re, urllib.parse, urllib.request, time
UA = {"User-Agent": "dinfelsefesi-deneme/1.0 (mailto:dinfelsefesi@gmail.com)"}
def al(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            b = r.read().decode("utf-8", "replace"); print(f"[{r.status}] {r.geturl()[:150]} ({len(b)} bayt)"); return b
    except Exception as e:
        print(f"[HATA] {url[:150]}: {e}"); return ""
OAI = "https://dergipark.org.tr/api/public/oai/"

print("=== A. Site araması")
for q in ['"din felsefesi"', 'din felsefesi']:
    for u in [f"https://dergipark.org.tr/tr/search?q={urllib.parse.quote(q)}&section=articles",
              f"https://dergipark.org.tr/tr/search?q={urllib.parse.quote(q)}&section=article&filter%5Bkeywords%5D={urllib.parse.quote('din felsefesi')}"]:
        h = al(u)
        if not h: continue
        toplam = re.findall(r"([\d\.]+)\s*(?:sonuç|result|kayıt)", h, re.I)[:3]
        links = sorted(set(re.findall(r'href="(https://dergipark\.org\.tr/tr/pub/[^/"]+/article/\d+)"', h)))
        print("  toplam ipucu:", toplam, "| makale bağlantısı:", len(links), links[:3])
        print("  sayfa parçası:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))[2000:2600])
        time.sleep(2)

print("=== B. Veri kapısı: dergi kümeleri (sets) sayısı")
h = al(OAI + "?verb=ListSets"); n = h.count("<setSpec>"); tok = re.findall(r"completeListSize=\"(\d+)\"", h)
print("  ilk sayfadaki küme:", n, "| toplam:", tok, "| örnek:", re.findall(r"<setSpec>([^<]+)</setSpec>\s*<setName>([^<]+)", h)[:5])

print("=== C. Tek dergide kayıtlar ve anahtar kelime alanı")
sets = re.findall(r"<setSpec>([^<]+)</setSpec>", h)
for s in sets[:2]:
    r = al(OAI + f"?verb=ListRecords&metadataPrefix=oai_dc&set={s}")
    print("  küme", s, "| kayıt:", r.count("<record>"), "| toplam:", re.findall(r"completeListSize=\"(\d+)\"", r),
          "| subject örnek:", re.findall(r"<dc:subject[^>]*>([^<]+)</dc:subject>", r)[:6])
print("=== D. Tarihe göre toplu çekim (bütün dergiler, bir gün)")
r = al(OAI + "?verb=ListRecords&metadataPrefix=oai_dc&from=2026-10-01&until=2026-10-02")
print("  kayıt:", r.count("<record>"), "| toplam:", re.findall(r"completeListSize=\"(\d+)\"", r), "| hata:", re.findall(r"<error[^>]*>([^<]*)", r)[:1])
