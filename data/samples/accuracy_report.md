# Doğruluk Raporu — `data/samples/ground_truth.json`'a karşı ölçüm

**Kaynak veri:** `data/samples/yonetmelik_2019.pdf` (eski) × `data/samples/yonetmelik_2023.pdf` (yeni), `data/samples/ground_truth.json` (15 madde).

**Ölçüm yöntemi:** Kod değiştirilmeden, `src/analysis/*`, `src/parsing/*`, `src/config.py` içindeki mevcut public/modül-seviyesi fonksiyonlar doğrudan Python'dan çağrıldı (`_load_document`, `parse_structure`, `match_sections`, `classify_content`, `is_renumbered`, `char_similarity`). Bu, `src/analysis/pipeline.py:119 compare_documents()`'ın izlediği aynı boru hattıdır; sadece ara adımların (benzerlik skoru, eşleşme yöntemi) görünür olması için ayrı ayrı çağrıldı. Tüm komut çıktıları bu raporun kaynağıdır; sıfır sonuç "göz kararı" ile yazılmadı.

**Kritik metodoloji notu (RENUMBERED eşlemesi):** `src/models.py:35-38` `ChangeType` enum'unda `RENUMBERED` **yoktur** — sadece `IDENTICAL/MODIFIED/ADDED/REMOVED`. `RENUMBERED`, `src/analysis/classifier.py:96 is_renumbered()` tarafından üretilen **ayrı bir yapısal boolean bayrak**tır (`numarasi_degisti`), içerik durumundan bağımsızdır (bkz. `classifier.py` modül docstring'i, satır 16-25). Ground truth dosyası ise `change_type` alanında `"RENUMBERED"`i beşinci bir kategori gibi kullanıyor (4 örnek: `ust_yonetim_sorumlulugu`, `yururlukten_kaldirilan`, `yururluk`, `yurutme` — dördünde de metin birebir aynı, sadece numara kaymış). Bu ölçümde ground truth `RENUMBERED` → sistemin **beklenen içerik sınıfı IDENTICAL** olarak eşlendi (metin gerçekten aynı olduğu için) ve **beklenen `numarasi_degisti=True`** olarak ayrıca kontrol edildi — sistemin kendi mimarisiyle tutarlı tek doğru eşleme budur.

---

## 0) Uçtan uca çalıştırma kanıtı

```
Ground truth: 15 madde
old_sections=13 new_sections=14

[L1-only / varsayilan] eslesme=12 unmatched_old=1 unmatched_new=2
  MATCH method=NUMBER_AND_TITLE old=MADDE1('Amaç') new=MADDE1('Amaç')
  MATCH method=NUMBER_AND_TITLE old=MADDE2('Kapsam') new=MADDE2('Kapsam')
  MATCH method=NUMBER_AND_TITLE old=MADDE3('Dayanak') new=MADDE3('Dayanak')
  MATCH method=NUMBER_AND_TITLE old=MADDE4('Tanımlar') new=MADDE4('Tanımlar')
  MATCH method=NUMBER_AND_TITLE old=MADDE5('Veri Sorumluluğu') new=MADDE5('Veri Sorumluluğu')
  MATCH method=NUMBER_AND_TITLE old=MADDE6('Veri Paylaşımı') new=MADDE6('Veri Paylaşımı')
  MATCH method=NUMBER_AND_TITLE old=MADDE7('Veri Kalitesi ve Güvenliği') new=MADDE7('Veri Kalitesi ve Güvenliği')
  MATCH method=TITLE_ONLY       old=MADDE9('Birim Sorumlulukları') new=MADDE8('Birim Sorumlulukları')
  MATCH method=TITLE_ONLY       old=MADDE10('Üst Yönetim Sorumluluğu') new=MADDE9('Üst Yönetim Sorumluluğu')
  MATCH method=TITLE_ONLY       old=MADDE11('Yürürlükten Kaldırılan Mevzuat') new=MADDE12('Yürürlükten Kaldırılan Mevzuat')
  MATCH method=TITLE_ONLY       old=MADDE12('Yürürlük') new=MADDE13('Yürürlük')
  MATCH method=TITLE_ONLY       old=MADDE13('Yürütme') new=MADDE14('Yürütme')
  UNMATCHED_OLD MADDE8 'Arşivleme Esasları'
  UNMATCHED_NEW MADDE10 'Veri Yönetişim Kurulu'
  UNMATCHED_NEW MADDE11 'Açık Veri Portalı'
toplam satir = 15
```

Bu, `use_embedder=False` (uygulamanın **varsayılan** davranışı, `app.py:32-41`) ile elde edilen L1-sadece (kural tabanlı) eşleşmedir.

---

## 1) Madde-madde karşılaştırma tablosu (sistem vs. ground truth)

| id | GT change_type | Beklenen (eşlenmiş) | Üretilen | Benzerlik skoru | numarasi_değişti (beklenen/üretilen) | Eşleşme yöntemi | Sonuç |
|---|---|---|---|---|---|---|---|
| amac | IDENTICAL | IDENTICAL | IDENTICAL | 1.0000 | False/False | NUMBER_AND_TITLE | ✅ |
| kapsam | IDENTICAL | IDENTICAL | IDENTICAL | 1.0000 | False/False | NUMBER_AND_TITLE | ✅ |
| dayanak | IDENTICAL | IDENTICAL | IDENTICAL | 1.0000 | False/False | NUMBER_AND_TITLE | ✅ |
| tanimlar | MODIFIED | MODIFIED | MODIFIED | 0.8632 | False/False | NUMBER_AND_TITLE | ✅ |
| veri_sorumlulugu | IDENTICAL | IDENTICAL | IDENTICAL | 1.0000 | False/False | NUMBER_AND_TITLE | ✅ |
| veri_paylasimi | MODIFIED | MODIFIED | MODIFIED | 0.8095 | False/False | NUMBER_AND_TITLE | ✅ |
| veri_kalitesi | MODIFIED | MODIFIED | MODIFIED | 0.8052 | False/False | NUMBER_AND_TITLE | ✅ |
| arsivleme | REMOVED | REMOVED | REMOVED | — (eşleşmedi) | False/False | UNMATCHED | ✅ |
| birim_sorumluluklari | MODIFIED | MODIFIED | MODIFIED | 0.6800 | **False/True*** | TITLE_ONLY | ✅ |
| ust_yonetim_sorumlulugu | RENUMBERED | IDENTICAL | IDENTICAL | 1.0000 | True/True | TITLE_ONLY | ✅ |
| veri_yonetisim_kurulu | ADDED | ADDED | ADDED | — (eşleşmedi) | False/False | UNMATCHED | ✅ |
| acik_veri_portali | ADDED | ADDED | ADDED | — (eşleşmedi) | False/False | UNMATCHED | ✅ |
| yururlukten_kaldirilan | RENUMBERED | IDENTICAL | IDENTICAL | 1.0000 | True/True | TITLE_ONLY | ✅ |
| yururluk | RENUMBERED | IDENTICAL | IDENTICAL | 1.0000 | True/True | TITLE_ONLY | ✅ |
| yurutme | RENUMBERED | IDENTICAL | IDENTICAL | 1.0000 | True/True | TITLE_ONLY | ✅ |

`*` `birim_sorumluluklari` ground truth'ta `RENUMBERED` alanı taşımıyor ama madde_no_2019=9→madde_no_2023=8 olduğu için `numarasi_degisti` **beklenen** True'dur — ground truth açıklama metni ("hem numarası HEM metni değişmiş") bunu doğruluyor, sistem bunu doğru yakaladı (`numarasi_degisti=True` VE `change_type=MODIFIED` aynı anda — tam da `classifier.py`'nin ayrı boyut tasarımının test ettiği kritik durum).

Ham veri: `data/samples/eslestirme_l1.json` olarak da kaydedildi (bkz. Ek dosyalar).

---

## 2) Karışıklık matrisi (Confusion Matrix)

Satır = ground truth (beklenen), sütun = sistemin ürettiği. Varsayılan (`use_embedder=False`) çalıştırma, n=15.

| beklenen \ üretilen | IDENTICAL | MODIFIED | ADDED | REMOVED |
|---|---|---|---|---|
| **IDENTICAL** | 8 | 0 | 0 | 0 |
| **MODIFIED** | 0 | 4 | 0 | 0 |
| **ADDED** | 0 | 0 | 2 | 0 |
| **REMOVED** | 0 | 0 | 0 | 1 |

Köşegen dışı hücrelerin tamamı 0 — **hiçbir tip başka bir tiple karıştırılmadı** (bu örnek çift + varsayılan yapılandırmada).

---

## 3) Precision / Recall / Genel doğruluk

| ChangeType | Precision | Recall | n (gt) |
|---|---|---|---|
| IDENTICAL | 1.000 | 1.000 | 8 |
| MODIFIED | 1.000 | 1.000 | 4 |
| ADDED | 1.000 | 1.000 | 2 |
| REMOVED | 1.000 | 1.000 | 1 |

**Genel doğruluk: 15/15 = %100.00** (varsayılan yapılandırma, `use_embedder=False`).

Bu sonucu tek başına "sistem kusursuz" diye okumayın — n=15 çok küçük bir örneklem ve bu belge çifti **bilinçli olarak** sistemin test edilmesi için tasarlanmış sentetik bir korpus (`data/samples/generate_samples.py`); madde 6'daki eşik taraması bu iddiaya önemli bir çekince ekliyor.

---

## 4) İki pahalı hata tipi — ayrı rapor

### Hata A: RENUMBERED'ı MODIFIED sanmak (metin aynıyken "değişti" demek)

**Varsayılan yapılandırmada (`use_embedder=False`): 0/4 — hiç oluşmadı.**

4 RENUMBERED madde (`ust_yonetim_sorumlulugu`, `yururlukten_kaldirilan`, `yururluk`, `yurutme`) sistemin ürettiği çıktıda dördü de `IDENTICAL` (+ `numarasi_degisti=True`) olarak doğru sınıflandırıldı. Kod yolu: `section_matcher.py:141 _match_by_unique_title()` madde numarasından bağımsız, sadece başlıkla eşleştirdiği için numara kayması `classify_content()`'e hiç karışmıyor; `classify_content()` (`classifier.py:79`) madde_no'ya zaten hiç bakmıyor (bilinçli tasarım, satır 85-90'daki NEDEN notu).

### Hata B: ADDED/REMOVED'ı MODIFIED sanmak (olmayan bir eşleşme kurmak)

**Varsayılan yapılandırmada (`use_embedder=False`): 0/3 — hiç oluşmadı** (`arsivleme`=REMOVED, `veri_yonetisim_kurulu`=ADDED, `acik_veri_portali`=ADDED, üçü de doğru).

**Ancak bu hata GERÇEKTEN üretilebiliyor** — embedder açık (`use_embedder=True`, L2 katmanı devrede) VE eşik yeterince düşükken:

```
t=0.50  dogruluk=13/15=0.8667  EMBEDDING_eslesme_sayisi=2
       hata: arsivleme beklenen=REMOVED uretilen=MODIFIED
       hata: acik_veri_portali beklenen=ADDED uretilen=MODIFIED
t=0.55  dogruluk=13/15=0.8667  EMBEDDING_eslesme_sayisi=2
       hata: arsivleme beklenen=REMOVED uretilen=MODIFIED
       hata: acik_veri_portali beklenen=ADDED uretilen=MODIFIED
```

Ölçülen tam kosinüs benzerliği (`src/analysis/section_matcher.py:196 _match_by_embedding()` içindeki matris, doğrudan sorgulandı):

```
old MADDE8 'Arşivleme Esasları'      <-> new MADDE10 'Veri Yönetişim Kurulu'  cosine=0.477970
old MADDE8 'Arşivleme Esasları'      <-> new MADDE11 'Açık Veri Portalı'      cosine=0.562352
```

Eşik 0.5624'ün altındayken (t=0.50, t=0.55) "Arşivleme Esasları" (REMOVED olmalı) ile "Açık Veri Portalı" (ADDED olmalı) — **tamamen alakasız iki konu** — yanlışlıkla eşleştirilip tek bir MODIFIED satırına dönüşüyor; hem gerçek bir REMOVED hem gerçek bir ADDED kayboluyor. Bu, `config.py:142-154`'teki NEDEN notunun anlattığı, geliştiricinin daha önce bizzat ölçüp belgelediği yanlış pozitiftir — bağımsız olarak burada da doğrulandı.

---

## 5) Yanlış sınıflandırılan maddeler + benzerlik skorları

**Varsayılan yapılandırma (`use_embedder=False`): 0 madde yanlış sınıflandırıldı.** Liste boş.

**Embedder açık + eşik ≤ 0.55 yapılandırmasında** (üretim varsayılanı DEĞİL, sadece madde 6 taraması için):

| id | beklenen | üretilen | benzerlik skoru | not |
|---|---|---|---|---|
| arsivleme | REMOVED | MODIFIED | cosine=0.5624 (embedding), char_similarity=hesaplanmadı çünkü yanlış eşleşen çiftin içerik metni tamamen farklı | yanlış pozitif eşleşme |
| acik_veri_portali | ADDED | MODIFIED | cosine=0.5624 (aynı yanlış çift) | yanlış pozitif eşleşme |

---

## 6) Eşik taraması: `SECTION_MATCH_MIN_COSINE_SIMILARITY`, 0.50–0.85

Bu proje eşiklerinden **sadece `SECTION_MATCH_MIN_COSINE_SIMILARITY`** (`config.py:155`, embedding tabanlı L2 eşleşme eşiği) bu belge çiftinde davranışı etkiliyor — `IDENTICAL_CHAR_SIMILARITY_THRESHOLD` (0.98, IDENTICAL/MODIFIED sınırı) 0.50-0.85 aralığının dışında olduğu için o eşik ayrıca tarandı ama bu aralıkta anlamlı değil (bkz. not sonda). Tarama, L2 katmanını gerçekten devreye sokmak için `embedder=Embedder()` ile (varsayılan `use_embedder=False` DEĞİL) yapıldı — `match_sections(..., embedder=embedder, min_similarity=t)` doğrudan çağrılarak, `config.py` değiştirilmeden.

| t (SECTION_MATCH_MIN_COSINE_SIMILARITY) | Doğruluk | Doğru/Toplam | L2 (EMBEDDING) eşleşme sayısı | Hata |
|---|---|---|---|---|
| 0.50 | %86.67 | 13/15 | 2 | arsivleme→MODIFIED, acik_veri_portali→MODIFIED |
| 0.55 | %86.67 | 13/15 | 2 | arsivleme→MODIFIED, acik_veri_portali→MODIFIED |
| **0.60** | **%100.00** | **15/15** | **0** | — |
| **0.65 (mevcut)** | **%100.00** | **15/15** | **0** | — |
| 0.70 | %100.00 | 15/15 | 0 | — |
| 0.75 | %100.00 | 15/15 | 0 | — |
| 0.80 | %100.00 | 15/15 | 0 | — |
| 0.85 | %100.00 | 15/15 | 0 | — |

**Kırılma noktası:** 0.5624 (yanlış çiftin ölçülen kosinüs benzerliği) — bu değerin üstündeki HERHANGİ bir eşik (0.60'tan itibaren taranan tüm değerler) bu korpusta %100 doğruluk veriyor.

### Mevcut değer (0.65) bu veride en iyisi mi, yoksa tahminle mi seçildi?

**Cevap: İkisi de tam değil — daha kesin söylemek gerekirse: 0.65, bu veride "en iyi" değil, "yeterince iyi ve rastgele değil" bir değer; ve veri bunu ayırt edecek güçte değil.**

- **Tahminle seçilmedi:** `config.py:142-154`'teki NEDEN notu, geliştiricinin gerçek bir yanlış pozitifi (arsivleme↔acik_veri_portali, ~0.56) **ölçüp** eski eşiği (0.50) bu yüzden 0.65'e yükselttiğini açıkça belgeliyor. Bu ölçüm bu raporda bağımsız olarak DOĞRULANDI (0.562352, dokümandaki "~0.56" ile örtüşüyor).
- **Ama "bu veride en iyisi" de değil, çünkü:** 0.60 ile 0.85 arasındaki HİÇBİR değer bu korpusta 0.65'ten farklı sonuç vermiyor (hepsi %100). Bunun nedeni, korpusta **L2/embedding katmanının gerçekten çözmesi gereken TEK BİR pozitif örnek bile olmaması** — 15 maddenin tamamı zaten L1 (kural tabanlı, numara+başlık) ile doğru eşleşiyor (bkz. bölüm 0 çıktısı: `unmatched_old=1, unmatched_new=2`, ve bunlar gerçekten de REMOVED/ADDED'dır, L2'nin "kurtarması" gereken gizli bir eşleşme değil). Yani eşik, bu veri setinde sadece TEK bir negatif örneğe karşı kalibre edilmiş; pozitif yönde hiç sınanmamış. **Bu, kodun kendi yorumunda da itiraf ediliyor** (`config.py:150-154`): *"bu kalibrasyon şu an SADECE bu negatif örneğe dayanıyor -- ground_truth.json'da L2'nin GERÇEKTEN çözmesi gereken (hem numarası HEM başlığı değişmiş) bir POZİTİF örnek YOK; gerçek belgelerle kullanılmaya başlandığında bu değer yeniden gözden geçirilmeli."*
- **Sonuç:** 0.65, ölçülmüş bir güvenlik marjıyla seçilmiş makul bir değer, ama bu veri seti eşiğin üst sınırını (0.86'dan yukarısı, ya da true-positive senaryosunda ne kadar YÜKSEK olursa gerçek bir yeniden-numaralanmış+yeniden-yazılmış maddeyi de reddetmeye başlayacağı) test edemiyor çünkü öyle bir örnek yok. Doğruluk sayısı tek başına "0.65 optimaldir" demeye yetmiyor — sadece "0.60-0.85 arası bu korpusta birbirinden ayırt edilemiyor" diyebiliyoruz.

**Not — `IDENTICAL_CHAR_SIMILARITY_THRESHOLD` (0.98) neden 0.50-0.85 aralığında taranmadı:** Bu eşik `classify_content()` (`classifier.py:79`) içinde IDENTICAL/MODIFIED kararını verir ve mevcut değeri (0.98) istenen aralığın (0.50-0.85) tamamen dışındadır — aralığı 0.50-0.85 olarak tarasaydık, MODIFIED eşiği daima "her ölçülen benzerlik ≥ t" koşulunu sağlayacağından TÜM eşleşen çiftler (MODIFIED olanlar dahil) yanlışlıkla IDENTICAL'a düşerdi — bu, istenen aralığın `SECTION_MATCH_MIN_COSINE_SIMILARITY`'yi hedeflediğini doğruluyor (o eşiğin mevcut değeri de 0.65, tam bu aralığın içinde).

---

## Sonuç özeti

| Soru | Bulgu |
|---|---|
| Varsayılan yapılandırmada genel doğruluk | **%100 (15/15)** |
| Hata A (RENUMBERED→MODIFIED) | **0/4**, varsayılanda hiç oluşmuyor |
| Hata B (ADDED/REMOVED→MODIFIED) | **0/3 varsayılanda**, ama embedder açık + eşik ≤0.55 iken **2/3** oluşuyor (ölçülen kosinüs=0.5624) |
| Mevcut eşik (0.65) veriye göre en iyi mi? | Ölçülmüş bir negatif örneğe karşı güvenlik marjıyla seçilmiş, doğru yönde; ama bu korpus 0.60-0.85 arasını AYIRT EDEMİYOR (hepsi %100) çünkü hiç pozitif L2 test örneği yok — kodun kendi NEDEN notu bunu itiraf ediyor |

## Ek dosyalar (bu raporun ham verisi)

- `data/samples/eslestirme_l1.json` — madde-madde eşleştirme tablosu (JSON)
- `data/samples/esik_taramasi.json` — eşik taraması ham sonuçları (JSON)

*Kod değiştirilmedi. Bu rapor `src/analysis/classifier.py`, `src/analysis/section_matcher.py`, `src/analysis/embedder.py`, `src/parsing/structure_parser.py`, `src/config.py` içindeki mevcut fonksiyonların doğrudan (script üzerinden) çağrılmasıyla üretildi.*
