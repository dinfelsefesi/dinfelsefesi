# Fiş şablonları

Sitenin başvuru bölümleri dört fiş türünden oluşur. Ana başlıklar, din felsefesi literatüründeki problem alanlarıdır ve beş tematik küme altında gösterilir (Disiplin; Tanrı; Bilgi ve dil; İnsan ve değer; Din, bilim ve kültür). Yapı en fazla iki katlıdır, alt başlık yalnızca bir ana başlığın türü olan dar konular için açılır. Terim, kişi ve eser fişleri `basliklar` alanıyla bir ya da daha fazla başlığa bağlanır. Alt başlıklar ihtiyaç doğdukça eklenir. Bir alt başlığa bağlı fişler, üst başlığın sayımına da katılır. Her fiş bir Markdown dosyasıdır. Dosyanın başında `---` çizgileri arasında üst bilgi alanları, altında ise metin yer alır. Fişler birbirine `kimlik` değeriyle bağlanır. Bir listede kimlik yerine düz metin yazılırsa (ör. henüz fişi olmayan bir yazar adı) site onu bağlantısız gösterir.

Metin içi bağlantılar kendiliğinden kurulur (adı genel bir kelime olan fişlerde `otomatik_bag: false` yazılarak kapatılabilir). Bir fişin metninde başka bir fişin adı geçiyorsa (terim ve başlıklarda ekleriyle birlikte, kişilerde tam ad ya da soyadı, eserlerde başlık) ilk geçtiği yer o fişe bağlanır. Bağlantının üzerine gelindiğinde kısa bir önizleme kartı açılır.

Ortak alanlar: `tur`, `kimlik` (dosya adıyla aynı), `imza`, `durum` (`taslak` | `yayinda`), `guncelleme` (YYYY-AA-GG). Taslak fişler yayımlanmaz.

## Terim (`content/terimler/`)

Zorunlu: `terim`, `ingilizce`, `kisa_tanim`, metin (1-3 paragraf açıklama).

İsteğe bağlı: `diger_karsiliklar`, `klasik_gelenekte`, `ilgili_terimler`, `ilgili_kisiler`, `ilgili_eserler`, `basliklar`, `kaynaklar`.

`klasik_gelenekte` alanı iki parçadan oluşur: `basliklar` (klasik başlıklar, Latin harfli yazımla) ve `not` (benzerlik ve farkı açıklayan kısa metin). İçeriğinden emin olunmayan durumda alan boş bırakılır, sitede başlık görünür ama kutu boş kalır.

## Kişi (`content/kisiler/`)

Zorunlu: `ad`, `donem`, `kapsam` (`turkiye` | `uluslararasi`), `kisa_tanitim`.

İsteğe bağlı: `kurum`, `alanlar`, `basliklar`, `temel_gorusleri`, `eserleri`, `turkce_cevirileri`, `hakkinda_turkce`, `baglantilar`, metin.

Yaşayan Türk akademisyenler için yalnızca kamuya açık bilgiler kullanılır, fotoğraf konmaz.

İlişki ağı (`/ag/`) fişler arasındaki bütün bağlantılardan otomatik olarak çizilir. Güncel makaleler, etiketleri bir fişin adıyla (kişilerde soyadıyla) aynı olduğunda ağa girer.

Kişiler sayfasının "Türkiye akademisi" sekmesi (sütun başlıklarına basılarak sıralanabilir tablo) `content/turkiye_akademisi.yaml` dosyasından üretilir (ad, unvan, üniversite, fakülte, `durum: emekli`, YÖK profil kimliği, `yok_alan`). Listeye YÖK'te bilim alanı Din Felsefesi olanlar ile Felsefe ve Din Bilimleri alanında ilk anahtar kelimesi Din Felsefesi olanlar girer. Bir kişinin fişi yazıldığında listedeki adı fişe bağlanır. Ad fişteki `ad` ile aynı değilse listeye `kimlik` alanı eklenir.

## Eser (`content/eserler/`)

Zorunlu: `baslik`, `yazar`, `eser_turu` (`kitap` | `kitap-bolumu` | `makale` | `bildiri` | `tez`), `yil`, `yayin`.

İsteğe bağlı: `doi`, `baglanti` (DOI yoksa eserin çevrim içi adresi), `acik_erisim` (`evet` | `hayır` | `bilinmiyor`), `duzey` (`giris` | `ileri`), `turkce_cevirisi`, `ilgili_terimler`, `basliklar`, metin (tanıtım).

## Başlık (`content/basliklar/`)

Zorunlu: `ad`, `sira` (aynı düzeydeki başlıklar arasında gösterim sırası), `ust_baslik` (ana başlıkta boş, alt başlıkta bağlı olduğu başlığın kimliği), `ozet`.

Ana başlıkta ayrıca `kume` (`disiplin` | `tanri` | `bilgi-dil` | `insan-deger` | `din-bilim-kultur`). Kümeler yalnızca görsel ayraçtır, kendi sayfaları yoktur.

İsteğe bağlı: metin (en az iki `##` bölümü), `alt_basliklar` (fişi henüz olmayan alt başlıklar düz metin olarak yazılabilir), `temel_terimler`, `temel_kisiler`, `okuma_listesi` (`giris` ve `ileri`), `tartisma_sorulari`, `ilgili_basliklar`.
