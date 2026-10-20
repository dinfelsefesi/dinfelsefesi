"""Geçici: YÖK Akademik'te 'din felsefesi' araması yapılabiliyor mu?"""
import re, urllib.parse, urllib.request, http.cookiejar
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", "Mozilla/5.0 (dinfelsefesi.com.tr; mailto:dinfelsefesi@gmail.com)")]
def al(url):
    try:
        with op.open(url, timeout=60) as r:
            b = r.read().decode("utf-8", "replace"); print(f"[{r.status}] {r.geturl()[:160]} ({len(b)} bayt)"); return b
    except Exception as e:
        print(f"[HATA] {url[:160]}: {e}"); return ""
kok = al("https://akademik.yok.gov.tr/AkademikArama/")
print("formlar:", re.findall(r'<form[^>]*action="([^"]*)"', kok)[:5])
print("input adları:", sorted(set(re.findall(r'<input[^>]*name="([^"]+)"', kok)))[:20])
print("captcha ipucu:", bool(re.search(r"captcha|recaptcha|doğrulama", kok, re.I)))
for u in ["https://akademik.yok.gov.tr/AkademikArama/AkademisyenArama?islem=direct&aramaTerim=din+felsefesi",
          "https://akademik.yok.gov.tr/AkademikArama/view/searchResultviewListAuthor.jsp?islem=direct&aramaTerim=din+felsefesi",
          "https://akademik.yok.gov.tr/AkademikArama/AkademikArama?islem=direct&aramaTerim=din%20felsefesi"]:
    h = al(u)
    if h:
        print("  sonuç ipucu:", re.findall(r"(\d+)\s*(?:sonuç|kayıt|Akademisyen)", h)[:5])
        print("  profil bağlantıları:", len(set(re.findall(r'AkademisyenGorevOgrenimBilgileri[^"\']*', h))), re.findall(r'href="([^"]*AkademisyenGorev[^"]*)"', h)[:2])
        print("  metin:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))[:700])
