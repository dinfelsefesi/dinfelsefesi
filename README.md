# dinfelsefesi.com.tr

İngilizce din felsefesi literatüründen yeni makalelerin Türkçe tanıtımı.

## Nasıl çalışır

- `content/makaleler.json` tek içerik kaynağıdır. Her kayıt bir makale tanıtımıdır.
- `build.py` bu dosyadan `site/` klasörüne HTML sayfaları, `rss.xml` ve `api/makaleler.json` üretir.
- `main` dalına her gönderimde GitHub Actions siteyi derler ve GitHub Pages'ta yayımlar.
- `CNAME` dosyası eklenirse özel alan adı kullanılır.

## Kayıt biçimi

```json
{
  "date": "2026-10-15",
  "title_tr": "Türkçe başlık",
  "title_en": "Original English title",
  "authors": "Ad Soyad",
  "journal": "Religious Studies",
  "year": "2026",
  "doi": "10.1017/...",
  "url": "",
  "open_access": "evet | hayır | bilinmiyor",
  "lead": "Tek cümlelik giriş (liste sayfasında görünür).",
  "summary_tr": "Tanıtım metni. Boş satırla ayrılmış paragraflar.",
  "why_tr": "Neden önemli, bir iki paragraf.",
  "tags": ["kötülük problemi", "teizm"]
}
```

Yerelde denemek için: `python3 build.py` ve ardından `site/index.html` dosyasını açın.
