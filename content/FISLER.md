# Fiş şablonları

Sitenin başvuru bölümleri dört fiş türünden oluşur. Her fiş bir Markdown dosyasıdır. Dosyanın başında `---` çizgileri arasında üst bilgi alanları, altında ise metin yer alır. Fişler birbirine `kimlik` değeriyle bağlanır. Bir listede kimlik yerine düz metin yazılırsa (ör. henüz fişi olmayan bir yazar adı) site onu bağlantısız gösterir.

Ortak alanlar: `tur`, `kimlik` (dosya adıyla aynı), `imza`, `durum` (`taslak` | `yayinda`), `guncelleme` (YYYY-AA-GG). Taslak fişler yayımlanmaz.

## Terim (`content/terimler/`)

Zorunlu: `terim`, `ingilizce`, `kisa_tanim`, metin (1-3 paragraf açıklama).

İsteğe bağlı: `diger_karsiliklar`, `klasik_gelenekte`, `ilgili_terimler`, `ilgili_kisiler`, `ilgili_eserler`, `konu`, `kaynaklar`.

`klasik_gelenekte` alanı üç parçadan oluşur:

- `iliski`: `terim-karsiligi` (kavram aynı ya da çok yakın), `ilgili-tartisma` (konu ortak, soru farklı) veya `karsiligi-yok` (problem modern bağlamda doğmuş)
- `basliklar`: klasik başlıklar, Latin harfli yazımla
- `not`: benzerlik ve farkı açıklayan kısa metin

## Kişi (`content/kisiler/`)

Zorunlu: `ad`, `donem`, `kapsam` (`turkiye` | `uluslararasi`), `kisa_tanitim`.

İsteğe bağlı: `kurum`, `alanlar`, `temel_gorusleri`, `eserleri`, `turkce_cevirileri`, `hakkinda_turkce`, `baglantilar`, metin.

Yaşayan Türk akademisyenler için yalnızca kamuya açık bilgiler kullanılır, fotoğraf konmaz.

## Eser (`content/eserler/`)

Zorunlu: `baslik`, `yazar`, `eser_turu` (`kitap` | `makale` | `kitap-bolumu` | `tez`), `yil`, `yayin`.

İsteğe bağlı: `doi`, `acik_erisim`, `duzey` (`giris` | `ileri`), `turkce_cevirisi`, `ilgili_terimler`, `konu`, metin (tanıtım).

## Konu dosyası (`content/konular/`)

Zorunlu: `baslik`, `duzey`, `sira`, `ozet`, metin (en az iki `##` bölümü).

İsteğe bağlı: `temel_terimler`, `temel_kisiler`, `okuma_listesi` (`giris` ve `ileri`), `tartisma_sorulari`, `ilgili_konular`.
