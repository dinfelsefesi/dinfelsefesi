"""Geçici deneme: DergiPark'tan anahtar kelime bilgisi alınabiliyor mu?"""
import json, re, urllib.parse, urllib.request
UA = {"User-Agent": "dinfelsefesi-deneme/1.0 (mailto:dinfelsefesi@gmail.com)"}
def al(url, n=600):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            b = r.read().decode("utf-8", "replace")
            print(f"[{r.status}] {r.geturl()}"); return b
    except Exception as e:
        print(f"[HATA] {url}: {e}"); return ""

print("=== 1. OAI uç noktası adayları")
for u in ["https://dergipark.org.tr/api/public/oai/?verb=Identify",
          "https://dergipark.org.tr/oai/?verb=Identify",
          "https://dergipark.org.tr/tr/oai?verb=Identify"]:
    print(al(u)[:300].replace("\n", " "))

print("=== 2. Crossref: 'din felsefesi' sorgusu")
q = urllib.parse.urlencode({"query.bibliographic": "din felsefesi", "filter": "from-pub-date:2025-01-01,type:journal-article",
                            "rows": 40, "mailto": "dinfelsefesi@gmail.com"})
b = al("https://api.crossref.org/works?" + q)
items = json.loads(b)["message"]["items"] if b else []
print(len(items), "kayıt;", sum(1 for i in items if i.get("subject")), "subject alanlı;",
      sum(1 for i in items if "dergipark" in json.dumps(i.get("link", [])) or "dergipark" in i.get("resource", {}).get("primary", {}).get("URL", "")), "DergiPark bağlantılı")
for i in items[:8]:
    print(" ", i.get("DOI"), "|", (i.get("title") or [""])[0][:70], "|", i.get("resource", {}).get("primary", {}).get("URL", ""))

print("=== 3. Makale sayfasında anahtar kelime etiketi")
for i in items[:5]:
    url = i.get("resource", {}).get("primary", {}).get("URL", "")
    if not url: continue
    h = al(url)
    kw = re.findall(r'<meta[^>]+name="(?:citation_keywords|keywords|DC\.Subject)"[^>]*content="([^"]*)"', h)
    print("  anahtar kelimeler:", kw[:3])
