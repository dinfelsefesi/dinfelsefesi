# Tez verisi (tezler.json)

Kaynak: Türkiye akademisi listesindeki (content/turkiye_akademisi.yaml) hocaların YÖK Akademik profillerindeki
"Yönetilen Tezler" listesi (`/api/tez/yurt/ici/yonetilen/<yok kimliği>`). YÖK Akademik esastır (karar: 14 Kasım 2026).
Anabilim dalı (`yer`) bilgisi Ulusal Tez Merkezi'nden tamamlanır; öğrenci adları hiçbir yere yazılmaz.

Alanlar: ad, tur ("Yüksek Lisans" | "Doktora"), yil, devam, danisman [site adları], yer, baslangic (isteğe bağlı).

## Yıl kuralı

- YÖK, devam eden tezde `yil` olarak tezin alındığı (başlangıç) yılını, tamamlanan tezde bitiş yılını verir.
  Tamamlanan tezlerin başlangıç yılı hiçbir yerde yayımlanmaz.
- Bu yüzden her taramada:
  1. Devam eden her teze `baslangic` = YÖK'teki yıl yazılır (zaten varsa dokunulmaz).
  2. Daha önce devam ederken kaydedilmiş bir tez tamamlandıysa, eski kayıttaki `baslangic` korunur,
     `yil` bitiş yılı olur, `devam` false olur. Tez adı küçük farklarla değişmiş olabilir; eşleştirmede adı
     harf dışı işaretler gözetmeden karşılaştır.
- Sitede: devam eden tez "Başlangıç 2024", başlangıcı bilinen tamamlanmış tez "2022-2025", bilinmeyen "Bitiş 2025".
- Kavram tarihi yalnız tamamlanmış tezleri sayar; başlangıç yılı biliniyorsa o yılla, bilinmiyorsa bitiş yılıyla.
