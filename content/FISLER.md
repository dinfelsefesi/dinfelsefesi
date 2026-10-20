# Fiş şablonları

Sitenin başvuru bölümleri dört fiş türünden oluşur. Ana başlıklar, din felsefesi literatüründeki en genel problem alanlarıdır. Terim, kişi ve eser fişleri bir ya da daha fazla ana başlığa bağlanır, alt başlıklar ihtiyaç doğdukça eklenir. Her fiş bir Markdown dosyasıdır. Dosyanın başında `---` çizgileri arasında üst bilgi alanları, altında ise metin yer alır. Fişler birbirine `kimlik` değeriyle bağlanır. Bir listede kimlik yerine düz metin yazılırsa (ör. henüz fişi olmayan bir yazar adı) site onu bağlantısız gösterir.

Ortak alanlar: `tur`, `kimlik` (dosya adıyla aynı), `imza`, `durum` (`taslak` | `yayinda`), `guncelleme` (YYYY-AA-GG). Taslak fişler yayımlanmaz.

## Terim (`content/terimler/`)

Zorunlu: `terim`, `ingilizce`, `kisa_tanim`, metin (1-3 paragraf açıklama).

İsteğe bağlı: `diger_karsiliklar`, `klasik_gelenekte`, `ilgili_terimler`, `ilgili_kisiler`, `ilgili_eserler`, `ana_baslik`, `kaynaklar`.

`klasik_gelenekte` alanı iki parçadan oluşur: `basliklar` (klasik başlıklar, Latin harfli yazımla) ve `not` (benzerlik ve farkı açıklayan kısa metin). İçeriğinden emin olunmayan durumda alan boş bırakılır, sitede başlık görünür ama kutu boş kalır.

## Kişi (`content/kisiler/`)

Zorunlu: `ad`, `donem`, `kapsam` (`turkiye` | `uluslararasi`), `kisa_tanitim`.

İsteğe bağlı: `kurum`, `alanlar`, `ana_basliklar` (birden fazla olabilir), `temel_gorusleri`, `eserleri`, `turkce_cevirileri`, `hakkinda_turkce`, `baglantilar`, metin.

Yaşayan Türk akademisyenler için yalnızca kamuya açık bilgiler kullanılır, fotoğraf konmaz.

## Eser (`content/eserler/`)

Zorunlu: `baslik`, `yazar`, `eser_turu` (`kitap` | `makale` | `kitap-bolumu` | `tez`), `yil`, `yayin`.

İsteğe bağlı: `doi`, `acik_erisim`, `duzey` (`giris` | `ileri`), `turkce_cevirisi`, `ilgili_terimler`, `ana_baslik`, metin (tanıtım).

## Başlık (`content/basliklar/`)

Zorunlu: `ad`, `ust_baslik` (ana başlıkta boş, alt başlıkta bağlı olduğu ana başlığın kimliği), `ozet`, metin (en az iki `##` bölümü).

İsteğe bağlı: `alt_basliklar`, `temel_terimler`, `temel_kisiler`, `okuma_listesi` (`giris` ve `ileri`), `tartisma_sorulari`, `ilgili_basliklar`.
