"""Geçici: eser fişleri için Crossref'te DOI ara."""
import glob, json, urllib.parse, urllib.request, yaml
UA = {"User-Agent": "dinfelsefesi/1.0 (mailto:dinfelsefesi@gmail.com)"}
for f in sorted(glob.glob("content/eserler/*.md")):
    h = yaml.safe_load(open(f, encoding="utf-8").read()[4:].split("\n---\n")[0])
    yazar = " ".join(h["yazar"]) if isinstance(h["yazar"], list) else h["yazar"]
    q = urllib.parse.urlencode({"query.bibliographic": f'{h["baslik"]} {h["yil"]}', "query.author": yazar.replace("-", " "),
                                "rows": 3, "mailto": "dinfelsefesi@gmail.com"})
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request("https://api.crossref.org/works?" + q, headers=UA), timeout=60))
        for it in r["message"]["items"]:
            yil = (it.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0]
            print(h["kimlik"], "|", it.get("DOI"), "|", (it.get("title") or [""])[0][:90], "|", yil, "|", it.get("type"), "|",
                  ", ".join(a.get("family", "") for a in it.get("author", [])[:3]), "| skor", round(it.get("score", 0)))
    except Exception as e:
        print(h["kimlik"], "HATA", e)
    print()
