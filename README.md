# dinfelsefesi.com.tr

Din felsefesi için Türkçe başvuru sitesi: başlık haritası, terim, kişi ve eser fişleri, makale tanıtımları.

Fiş biçimleri için `content/FISLER.md` dosyasına bakın.

## Nasıl çalışır

- `content/makaleler.json` makale tanıtımlarını, `content/basliklar`, `terimler`, `kisiler`, `eserler` klasörleri fişleri tutar.
- `build.py` bunlardan `site/` klasörüne HTML sayfaları, `rss.xml`, `api/makaleler.json` ve `api/fisler.json` üretir. `TASLAK_GOSTER=1` taslak fişleri de gösterir, `NOINDEX=1` arama motorlarını kapatır.
- Site hem GitHub Pages'ta hem FTP ile hostingde (`dinfelsefesi.com.tr/yeni`) yayımlanır.
- `scripts/dergipark_hasat.py` DergiPark'tan din felsefesi makalelerini toplar (`data/dergipark`).
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

Yerelde denemek için: `pip install pyyaml`, sonra `TASLAK_GOSTER=1 python3 build.py` ve ardından `site/index.html` dosyasını açın.
