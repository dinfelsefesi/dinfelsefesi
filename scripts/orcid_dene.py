#!/usr/bin/env python3
"""DergiPark makale sayfasının yazar/ORCID bölümünü incelemek için örnek kaydeder (geçici)."""
import re, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "dinfelsefesi.com.tr (dinfelsefesi@gmail.com)"}
out = []
for url in ["https://dergipark.org.tr/tr/pub/gifad/article/1283765", "https://dergipark.org.tr/tr/pub/tid/article/1886013"]:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        h = r.read().decode("utf-8", "replace")
    out.append(f"===== {url} ({len(h)})")
    for m in re.finditer(r"orcid", h, re.I):
        out.append(h[max(0, m.start() - 900): m.start() + 300].replace("\n", " "))
        out.append("-----")
(ROOT / "data/orcid").mkdir(parents=True, exist_ok=True)
(ROOT / "data/orcid/ornek.txt").write_text("\n".join(out), encoding="utf-8")
