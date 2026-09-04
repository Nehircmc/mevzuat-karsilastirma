# Metodoloji

Bu belge, iki belgenin nasıl adım adım karşılaştırıldığını, hangi eşiklerin
NEDEN o değerde olduğunu ve hangi bulguların GERÇEK ölçümle kalibre
edildiğini anlatır. Tasarım kararlarının GEREKÇESİ için bkz.
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

Tüm örnekler, projenin tek doğruluk kaynağı olan
`data/samples/document_spec.py`'den üretilen "KURUMSAL VERİ YÖNETİMİ VE AÇIK
VERİ YÖNETMELİĞİ" (2019 → 2023) test belgesi çiftinden alınmıştır.

## Adım 1 — Ingestion: belge → `TextUnit`

`src/ingestion/pdf_loader.py` (PyMuPDF) ve `src/ingestion/docx_loader.py`
(python-docx), her biri kendi formatına özgü şekilde, belgeyi bloklara/
paragraflara ayırıp her birini bir `TextUnit`e (doğrudan `page_no`,
`block_index`, `char_start`, `char_end` taşıyan) çevirir.

- **Üstbilgi/altbilgi ayıklama (sadece PDF):** bir blok, hem sayfanın
  üst/alt %8'lik bandında konumlanmış HEM DE sayfaların en az %60'ında
  (normalize edilmiş olarak) tekrar ediyorsa üstbilgi/altbilgi sayılır.
  Tek bir sinyal YETERLİ değildir — gövde metni de sayfa kenarına yakın
  başlayabilir.
- **Metin katmanı doğrulama:** OCR/taranmış PDF kapsam dışıdır
  (Onaylanmış Karar #1). PDF için sayfaların en az yarısında yeterli metin
  olmalı (`MIN_PAGE_RATIO_WITH_TEXT_LAYER=0.5`); DOCX için toplam karakter
  sayısı bir eşiği geçmeli. Bu doğrulama BAŞARISIZ olursa `NoTextLayerError`
  fırlatılır — sessizce boş sonuç DÖNÜLMEZ.
- **Bozuk dosya:** uzantı doğru ama içerik geçersizse (örn. bir ZIP olmayan
  `.docx`), format kütüphanesinin kendi istisnası (`pymupdf.FileDataError`,
  `docx.opc.exceptions.PackageNotFoundError`) `CorruptDocumentError`'a
  çevrilir (Adım 8, bkz. `src/ingestion/base.py`).

## Adım 2 — Parsing: `TextUnit` → `Section`

`src/parsing/structure_parser.py`, TÜM satırları belge sırasıyla tek
geçişte tarar; `KISIM_PATTERN`/`BOLUM_PATTERN`/`MADDE_PATTERN`/
`GECICI_MADDE_PATTERN` (bkz. `config.py`) ile eşleşen satırlar hiyerarşi
bağlamını (`current_kisim`, `current_bolum`) günceller, diğer satırlar açık
olan `Section`'ın gövdesine eklenir.

**Sayfa/blok-içi kırılma:** reportlab (test belgesi üretici) bazen TEK bir
paragrafı, GERÇEK bir sayfa sınırı olmadan bile, iki ayrı bloğa bölebilir
(örn. "Veri Paylaşımı" MADDE 6 fıkra 1). `structure_parser` bu durumda
maddenin gövdesini BİRDEN FAZLA orijinal `TextUnit` parçasından oluşan bir
liste olarak tutar (`Section.units`) — parçalar UYDURULARAK birleştirilmez,
her biri kendi orijinal ofsetini korur.

## Adım 3-4 — Section eşleştirme: iki belgede "aynı madde" hangisi?

### Katman 1 (L1) — yapısal, kural tabanlı

`src/analysis/section_matcher.py::match_sections`, iki geçişte çalışır:

1. **NUMBER_AND_TITLE:** aynı `section_type` + aynı `madde_no` taşıyan bir
   çift, başlıkları ÇELİŞMİYORSA eşleştirilir.

   > **Neden başlık çelişkisi kontrolü zorunlu:** bir madde eklenip/
   > kaldırılınca ARADAKİ maddeler numara olarak KAYAR. Örnek (gerçek test
   > verisi): 2019 MADDE 8 "Arşivleme Esasları" 2023'te KALDIRILDIĞINDA,
   > 2023 MADDE 8 ARTIK "Birim Sorumlulukları"dır (eskiden MADDE 9'du).
   > Sadece numaraya bakan bir eşleştirici bu ikisini YANLIŞ eşleştirirdi.
   > Başlık çelişkisi bunu engeller, gerçek karşılığı (aynı başlıklı MADDE
   > 9→8) 2. geçişe bırakır.

2. **TITLE_ONLY:** 1. geçişten arta kalanlar arasında, aynı `section_type` +
   normalize edilmiş başlığı HER İKİ TARAFTA da TEK VE BENZERSİZ olan
   çiftler eşleştirilir. Bu, RENUMBERED (numara kaymış, metin/başlık aynı)
   VE "numara DA metin DE değişmiş" (örn. yukarıdaki Birim Sorumlulukları
   örneği) durumlarını yakalar.

Bu iki geçiş, mevcut test korpusundaki 15 maddenin **12'sini** doğrudan
çözer (kalan 1'i REMOVED, 2'si ADDED olarak L1'de zaten "eşleşmemiş"
bırakılır — bunlar gerçekten karşılığı olmayan maddelerdir).

### Katman 2 (L2) — anlamsal, embedding tabanlı (isteğe bağlı)

L1'in eşleştiremediği artıklar için (varsa), `src/analysis/embedder.py`
(`paraphrase-multilingual-MiniLM-L12-v2`, disk önbellekli) ile her Section'ın
gövde metni bir vektöre çevrilir, kosinüs benzerliği matrisi çıkarılır ve
`scipy.optimize.linear_sum_assignment` (Hungarian) ile TOPLAM benzerliği
maksimize eden atama bulunur.

> **Neden Hungarian, açgözlü (greedy) DEĞİL:** greedy "her old için en
> benzer new'i al" yaklaşımı YEREL olarak iyi görünen ama KÜRESEL olarak
> yanlış bir atama üretebilir. Örnek: A hem X (0.70) hem Y (0.62) ile
> benzerse ama B SADECE X ile yüksek benzerlik (0.95) taşıyorsa, greedy A'yı
> X'e kilitleyip B'yi Y'ye (0.0) mahkûm edebilir; Hungarian bunun yerine
> A-Y + B-X toplamının (1.57) A-X + B-Y toplamından (0.28) daha iyi
> olduğunu görür ve doğru atamayı yapar (bkz.
> `tests/test_matcher.py::test_hungarian_kuresel_optimumu_secer_...`).

Eşik altındaki (`SECTION_MATCH_MIN_COSINE_SIMILARITY`) atamalar REDDEDİLİR
(bkz. Mimari İlke B).

**Kalibrasyon bulgusu (gerçek ölçüm):** gerçek modelle ölçüldüğünde, 2019
MADDE 8 "Arşivleme Esasları" (REMOVED) ile 2023 MADDE 11 "Açık Veri Portalı"
(ADDED) — TAMAMEN alakasız iki konu — kosinüs benzerliği **~0.56**
çıkıyor (ikisi de kısa, "veri"/"ilgili"/"Kurum" gibi ortak mevzuat kelime
dağarcığı paylaşan iki fıkralı maddeler olduğu için). Eşik başlangıçta
0.50 idi; bu GERÇEK yanlış pozitif ölçülünce **0.65**'e çıkarıldı (bkz.
`src/config.py::SECTION_MATCH_MIN_COSINE_SIMILARITY` NEDEN notu ve
`tests/test_matcher.py::test_arsivleme_acik_veri_portaliyla_yanlislikla_eslesmiyor`).

> **Sınırlama:** bu kalibrasyon SADECE bu bir NEGATİF örneğe dayanıyor.
> Mevcut test korpusunda L2'nin GERÇEKTEN çözmesi gereken bir POZİTİF örnek
> (hem numarası HEM başlığı değişmiş ama içerik olarak aynı madde) yok —
> çünkü korpustaki TÜM gerçek eşleşmeler zaten L1 ile çözülüyor. 0.65
> eşiğinin gerçek pozitif örnekleri de doğru yakalayıp yakalamadığı henüz
> ölçülmedi.

## Adım 5 — Differ: cümle ve kelime düzeyinde fark

`src/analysis/differ.py::diff_section_match`, eşleşen bir (old, new) çiftinin
gövde metnini cümlelere böler ve `difflib.SequenceMatcher` ile hizalar.

**Cümle bölme NEDEN `Section.units`'teki HER TextUnit'i ayrı ayrı DEĞİL,
BİRLEŞTİRİLMİŞ metin üzerinden yapılır:** Adım 2'deki sayfa/blok-içi kırılma
artığı (bkz. yukarı), tek tek TextUnit'lerde bölünseydi GERÇEK bir cümleyi
yanlışlıkla ikiye ayırırdı. `section_sentences()`, `Section.units`'i
`" "` ile birleştirip cümle sınırlarını bu BİRLEŞİK metin üzerinde arar; her
cümle sonucu (`DiffSentence`), bir VEYA DAHA FAZLA orijinal `TextUnit`
parçasından oluşabilir ama HER parça kendi karakter aralığına geri
izlenebilir kalır (Mimari İlke A).

**Cümle hizalama** dört opcode üretir: `equal` (değişmedi), `replace`
(karşılık gelen ama farklı cümle — KELİME düzeyinde tekrar diff'lenir),
`insert` (sadece yeni belgede var), `delete` (sadece eski belgede var).

**Gerçek örnek (MADDE 6, Veri Paylaşımı):**

| 2019 | 2023 |
|---|---|
| (1) Kurum verileri, ilgili birimler dışındaki kişi ve kurumlarla **paylaşılamaz**. | (1) Kurum verileri, **Veri Yönetişim Kurulunun onayı alınması kaydıyla,** ilgili birimler dışındaki kişi ve kurumlarla **paylaşılabilir**. |
| (2) Kişisel verilerin işlenmesinde ilgili mevzuat hükümlerine uyulur. | (2) Kişisel verilerin işlenmesinde ilgili mevzuat hükümlerine uyulur. |

Differ, fıkra (1)'i `replace` (kelime düzeyinde: bir `insert` + bir kelime
`replace`), fıkra (2)'yi `equal` olarak ayırt eder — TÜM madde değil,
SADECE değişen fıkra işaretlenir. Bu, `ground_truth.json`'un bilinçli olarak
test ettiği bir davranıştır (bkz. `document_spec.py`'deki `aciklama` alanı).

**Gerçek örnek (MADDE 7, Veri Kalitesi):** fıkra (1)-(3) birebir aynı
(`equal`), sadece fıkra (4) 2023'te eklenmiş (`insert`) — differ TÜM
maddeyi değil sadece eklenen fıkrayı işaretler.

## Adım 5 — Classifier: `ChangeType` kararı

`src/analysis/classifier.py::classify_match`, SADECE üç ucuz/deterministik
sinyale bakan bir karar ağacıdır (embedding'e BAĞIMLI DEĞİLDİR — L1
eşleşmelerinde embedder hiç çağrılmamış olabilir):

```
madde_no AYNI mı?
├─ EVET
│   karakter benzerliği ≥ 0.98 mi? (IDENTICAL_CHAR_SIMILARITY_THRESHOLD)
│   ├─ EVET
│   │   konum/bağlam (heading_path VEYA order_index) önemli ölçüde kaydı mı?
│   │   ├─ EVET → MOVED
│   │   └─ HAYIR → IDENTICAL
│   └─ HAYIR → MODIFIED
└─ HAYIR (numara kaymış)
    karakter benzerliği ≥ 0.995 mi? (RENUMBERED_CHAR_SIMILARITY_THRESHOLD)
    ├─ EVET → RENUMBERED
    └─ HAYIR → MODIFIED   (hem numara HEM içerik değişmiş)
```

REMOVED (L1+L2 sonrası hâlâ `unmatched_old`'da kalan) ve ADDED
(`unmatched_new`'de kalan) için sınıflandırma zaten doğrudan bellidir.

**Neden RENUMBERED eşiği (0.995) IDENTICAL eşiğinden (0.98) DAHA SIKI:**
RENUMBERED "numara değişti ama metin (neredeyse) BİREBİR aynı" iddiasıdır;
IDENTICAL eşiğiyle yetinilseydi, KÜÇÜK bir içerik değişikliği + numara
kayması birlikte olduğunda (gerçek örnek: 2019 MADDE 9 → 2023 MADDE 8
"Birim Sorumlulukları", HEM numara HEM metin değişti) yanlışlıkla "sadece
numara kaymış" (RENUMBERED) sayılırdı. Gerçek ölçüm: bu madde çifti
karakter benzerliği **0.67** — açıkça 0.995'in ÇOK altında, doğru şekilde
MODIFIED'a düşer.

**Gerçekten ölçülen benzerlik değerleri (2019 PDF vs 2023 PDF, tüm
korpus):**

| Madde | Tür | Karakter benzerliği |
|---|---|---|
| Amaç, Kapsam, Dayanak, Veri Sorumluluğu | IDENTICAL | 1.000 |
| Tanımlar | MODIFIED | 0.841 |
| Veri Paylaşımı | MODIFIED | 0.833 |
| Veri Kalitesi ve Güvenliği | MODIFIED | 0.844 |
| Birim Sorumlulukları (9→8) | MODIFIED | 0.670 |
| Üst Yönetim Sorumluluğu, Yürürlükten Kaldırılan Mevzuat, Yürürlük, Yürütme | RENUMBERED | 1.000 |

Bu tablo, 0.98/0.995 eşiklerinin bu korpusta HER durumu geniş bir marjla
(en yakın sınır durumu bile ≥0.16 fark) doğru ayırdığını gösterir.

> **Sınırlama:** MOVED dalı sadece SENTETİK testlerle doğrulandı —
> `ground_truth.json`'da gerçek bir MOVED örneği yok.

## Adım 6-7 — Sunum: UI ve dışa aktarım

Sınıflandırılmış/diff'lenmiş sonuç (`ComparisonResult`), İKİ farklı
tüketici tarafından render edilir — İKİSİ DE `src/reporting/html_renderer.py`
VE `src/reporting/summary_builder.py`'nin AYNI fonksiyonlarını kullanır (kod
tekrarı yok):

- **Streamlit UI** (`src/ui/components.py`): canlı sayfa, `st.columns` ile
  yan yana görünüm, filtre, indirme düğmeleri.
- **Bağımsız HTML** (`src/reporting/exporter.py::export_to_html`): CSS'i
  İÇİNE GÖMEN, Streamlit olmadan tarayıcıda doğrudan açılabilen tek dosya.

**Yönetici Özeti** (bkz. Mimari İlke C / "Hukuki Yorum Yok"), TAMAMEN
sayısal: toplam madde, ChangeType başına sayı+yüzde, "en çok değişiklik
görülen bölüm" (saf sayım). Serbest metin/yorum İÇERMEZ.

## Doğrulama metodolojisi

Her aşama, `data/samples/document_spec.py`'den üretilen `ground_truth.json`
cevap anahtarına karşı OBJEKTİF olarak test edilir — hiçbir sonuç "gözle
kontrol" ile onaylanmaz. `pytest -v` çalıştırıldığında 199 test, ingestion'dan
son dışa aktarıma kadar HER katmanı bu tek doğruluk kaynağına karşı doğrular.

Ayrıca UI ve hata yönetimi, `streamlit.testing.v1.AppTest` ile GERÇEK dosya
yükleme senaryoları (geçerli belge, bozuk belge, madde içermeyen belge,
desteklenmeyen uzantı) üzerinden uçtan uca test edilir; kritik akışlar
ayrıca gerçek bir Chrome tarayıcısında görsel olarak da doğrulanmıştır.

**Bu metodolojinin açıkça KABUL ETTİĞİ boşluklar** (bkz.
ARCHITECTURE.md §6): MOVED sınıflandırması ve L2'nin pozitif (gerçekten
gerekli) bir eşleşme örneği, mevcut test korpusunda TEMSİL EDİLMİYOR. Bu,
aracın bu iki senaryoda YANLIŞ çalıştığı anlamına gelmez — sadece bu iki
senaryonun HENÜZ gerçek veriyle doğrulanmadığı anlamına gelir.
