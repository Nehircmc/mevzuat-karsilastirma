# Mimari

Bu belge **neden** bu şekilde inşa edildiğini anlatır. **Nasıl** çalıştığının
adım adım açıklaması için bkz. [`METHODOLOGY.md`](./METHODOLOGY.md).

Kod tabanındaki her modülün başında, o modüle özgü kararların gerekçesini
açıklayan `NEDEN` yorumları vardır — bu belge onların ÜST DÜZEY özetidir, yerini
tutmaz. Bir kararın ayrıntılı gerekçesi için ilgili dosyayı açın.

## 1. Boru hattı (pipeline)

```
İki belge (PDF/DOCX)
        │
        ▼
┌───────────────────┐   src/ingestion/          Belge → provenance'lı TextUnit
│   1. INGESTION     │   (pdf_loader, docx_loader, factory)
└───────────────────┘   OCR/taranmış PDF kapsam dışı (Onaylanmış Karar #1)
        │
        ▼
┌───────────────────┐   src/parsing/            TextUnit'ler → Section
│   2. PARSING       │   (structure_parser, sentence_splitter, normalizer)
└───────────────────┘   madde/bölüm/kısım hiyerarşisi çıkarımı
        │
        ▼
┌───────────────────┐   src/analysis/           İki belgenin Section'ları →
│   3. ANALYSIS      │   (section_matcher, embedder,   eşleşme + diff + sınıflandırma
│                     │    differ, classifier, pipeline)
└───────────────────┘
        │
        ▼
┌───────────────────┐   src/reporting/          Sonuç → DataFrame/Özet/Excel/
│   4. REPORTING     │   (metrics, summary_builder,   CSV/HTML
│                     │    html_renderer, exporter)
└───────────────────┘
        │
        ▼
┌───────────────────┐   src/ui/ + app.py        Streamlit arayüzü (ince
│   5. UI            │   (components, styles)         orkestrasyon)
└───────────────────┘
```

Her ok TEK yönlüdür ve alt katmanlar üst katmanları BİLMEZ: `ingestion`
`parsing`'i tanımaz, `analysis` `reporting`'i tanımaz. `reporting` ve `ui` ise
İKİSİ de `src/analysis/pipeline.py`'ye bağımlıdır (birbirlerine değil) — bkz.
§5.

## 2. Dört mimari ilke

Kod tabanındaki `NEDEN` yorumlarının büyük çoğunluğu, aşağıdaki dört ilkeden
birine geri sarılır. Yeni bir katkı bu ilkelerden biriyle çelişiyorsa, önce
ilkeyi mi yoksa katkıyı mı gözden geçirmek gerektiği tartışılmalı — sessizce
ihlal edilmemeli.

### İlke A — Provenance Sözleşmesi

> Hiçbir katman "düz string" ile çalışmaz. Boru hattındaki HER metin
> parçası, kaynağına (hangi belge, hangi sayfa/blok, hangi karakter aralığı)
> geri izlenebilir olmalıdır.

**Neden:** Bu bir hukuki/idari belge karşılaştırma aracıdır. Bir kullanıcı
"MADDE 6 değişti" sonucunu gördüğünde, bunun 2019 belgesinin TAM OLARAK
neresinden geldiğini doğrulayabilmelidir — aracın kendi iddiasına güvenmek
zorunda kalmamalıdır.

**Nasıl zorlanıyor:**
- `src/models.py::TextUnit` — boru hattının EN KÜÇÜK birimi; `doc_id`,
  `page_no`, `block_index`, `char_start`, `char_end` alanları ZORUNLUDUR ve
  `__post_init__` bunların iç tutarlılığını (örn. `char_end - char_start ==
  len(text)`) doğrular — sessizce yanlış bir provenance kabul EDİLMEZ.
- `src/parsing/structure_parser.py::_merge_spans` — bir madde birden fazla
  orijinal bloğa yayılsa bile (sayfa/blok sınırı), her parça KENDİ
  orijinal ofsetini korur; "uydurma birleştirme" yapılmaz.
- `src/analysis/differ.py::_span_to_units` — cümle bölme, `Section.units`'i
  tek tek değil BİRLEŞTİRİLMİŞ metin üzerinden yapar (bkz. §"Sayfa-içi
  kırılma" METHODOLOGY.md), ama sonuç cümle yine de kendi orijinal
  TextUnit parçalarına geri izlenebilir kalır.
- `src/reporting/html_renderer.py` — her span `html.escape()` ile kaçırılır;
  gösterilen HER karakter, gerçek belge içeriğinden (uydurma değil) gelir.

### İlke B — Eşik Altı Bir Atama "Eşleşme" Değildir

> Bir benzerlik skoru (karakter benzerliği, kosinüs benzerliği) belirli bir
> eşiğin altındaysa, sonuç "rastgele en yakın komşu"dur — zorla bir eşleşmeye
> DÖNÜŞTÜRÜLMEZ.

**Neden:** Hungarian atama (`scipy.optimize.linear_sum_assignment`) HER
zaman TAM bir eşleştirme üretir — matristeki en kötü çift bile "en iyi kalan
seçenek" olduğu için seçilir. Eşik kontrolü olmadan, iki TAMAMEN alakasız
madde (örn. "Arşivleme Esasları" ve "Açık Veri Portalı") zorla eşleştirilip
YANLIŞ bir "bu iki madde aynı" iddiası üretilebilir.

**Nasıl zorlanıyor:**
- `src/config.py::SECTION_MATCH_MIN_COSINE_SIMILARITY` (0.65) —
  `src/analysis/section_matcher.py::_match_by_embedding` bu eşiğin altındaki
  atamaları REDDEDER, ilgili Section'ları `unmatched_old`/`unmatched_new`'de
  bırakır.
- `src/config.py::IDENTICAL_CHAR_SIMILARITY_THRESHOLD` (0.98) —
  `src/analysis/classifier.py::classify_content` bunun ALTINDAKİ bir
  benzerliği "eşleşme değil, bu iki metin FARKLI" (MODIFIED) sayar; ÜSTÜNDE
  kalanı IDENTICAL sayar. Adım 9'dan önce ayrıca bir
  `RENUMBERED_CHAR_SIMILARITY_THRESHOLD` (0.995, IDENTICAL'dan DAHA SIKI)
  vardı -- numara AYRI bir yapısal bayrağa taşınınca (bkz. İlke C notu)
  bu ikinci eşiğin ayırt ettiği durum ARTIK anlamsızlaştı ve kaldırıldı.
- Bu ilkenin GERÇEK bir bulguyla doğrulanmış hâli için bkz.
  METHODOLOGY.md'deki "Arşivleme Esasları / Açık Veri Portalı" kalibrasyon
  örneği — eşik 0.50 iken bu ilke ihlal ediliyordu, 0.65'e çıkarılarak
  düzeltildi.

### İlke C — Kapalı Sözlük, Yorum Yok (ve "Hukuki Yorum Yok")

> Analiz katmanı, `ChangeType` enum'unun (`IDENTICAL, MODIFIED, ADDED,
> REMOVED`) DIŞINDA bir İÇERİK durumu üretemez. Raporlama katmanı SERBEST
> METİN üretmez — SADECE bu kapalı kümenin ve YAPISAL bayrakların
> (`numarasi_degisti`, `yeri_degisti`) sayımlarını SABİT şablonlara
> yerleştirir.

**Neden İÇERİK durumu (`ChangeType`) ve YAPISAL bayraklar İKİ AYRI kapalı
küme (Adım 9'da ayrıştırıldı):** `MOVED`/`RENUMBERED` başlangıçta
`ChangeType`'ın üyesiydi. Bu, bir maddenin HEM numarası HEM içeriği
değiştiğinde (bkz. ground_truth.json/birim_sorumlulukları) YAPISAL olguyu
SESSİZCE KAYBEDİYORDU -- satır sadece `MODIFIED` sayılıyor, "numarası da
değişti" bilgisi HİÇBİR YERDE görünmüyordu (kullanıcı panelinde "Değişti: 4"
ile "Numarası Değişti: 4" yan yana görününce de bu, iki bağımsız sayı gibi
DEĞİL, örtüşen/karışık bir sınıflandırma gibi okunuyordu). Şimdi HER Section
İKİ BAĞIMSIZ soruya cevap taşır: "içeriği değişti mi" (`ChangeType`) ve
"numarası/konumu değişti mi" (bool bayraklar) -- ikisi AYNI ANDA true
olabilir, biri diğerini MASKELEMEZ. Bkz. `src/analysis/classifier.py` modül
NEDEN notu ve METHODOLOGY.md'nin Adım 5 bölümü.

**Neden (genel):** "Yorum yok" ilkesi TİP SİSTEMİYLE zorlanır, iyi niyetle
değil — `ChangeType(str, Enum)` dışında bir string, hiçbir katmanda
ChangeType TÜRÜNDE bir değer olarak KABUL EDİLMEZ.

**Neden ("Hukuki Yorum Yok" — bu ilkenin bu proje için özel bir uzantısı):**
Bu araç HUKUKİ/İDARİ belgeleri karşılaştırıyor. Bir maddenin metninin
DEĞİŞTİĞİNİ söylemek OBJEKTİF bir gözlemdir (difflib bunu mekanik olarak
tespit eder); bu değişikliğin hukuken "önemli", "vatandaş lehine/aleyhine"
ya da "dikkat çekici" olduğunu söylemek ise bir YORUMDUR — ve bu yorum,
metni gerçekten anlayan bir hukukçunun işidir, bir difflib/embedding
boru hattının değil. Bu proje BİLEREK bu sınırı aşmaz:
- `src/reporting/summary_builder.py` "Yönetici Özeti" TAMAMEN SABİT
  şablonlara (`f"- **{label}**: {count} madde (%{pct})"` gibi) sayı
  yerleştirir; "önemli değişiklik", "dikkat edilmesi gereken" gibi
  YORUM İÇEREN hiçbir ifade YOKTUR.
- "En çok değişiklik ... bölümünde görüldü" istatistiği bile SAF bir
  SAYISAL AGREGASYONDUR (bölüm başına IDENTICAL-olmayan madde sayımı),
  hangi değişikliğin "daha önemli" olduğuna dair bir YARGI DEĞİLDİR.
- Hiçbir LLM/NLP metin üretim çağrısı YOKTUR — özet, difflib'in kendi
  ürettiği yapısal sayımlardan DETERMİNİSTİK olarak türetilir (aynı
  girdi → HER ZAMAN birebir aynı çıktı, bkz.
  `tests/test_reporting.py::test_deterministik_iki_cagri_ayni_sonucu_verir`).

**Nasıl zorlanıyor (kod):**
- `src/models.py::ChangeType` — kapalı enum (4 üye), `str`'den türer
  (Excel/JSON dışa aktarımda doğrudan okunabilir string olarak serileşir).
- `src/analysis/classifier.py::classify_content` — SADECE karakter
  benzerliğine dayanan, madde_no'dan TAMAMEN BAĞIMSIZ, DETERMİNİSTİK bir
  karar; `is_renumbered`/`is_moved` de kendi SADE sinyallerine (numara
  eşitliği, konum/heading_path) dayanan AYRI, bağımsız fonksiyonlardır --
  hiçbirinde "serbest" bir dal yoktur.
- `src/reporting/summary_builder.py::SummaryStats` — özetin dayandığı TÜM
  sayılar, metin ÜRETİMİNDEN (render_summary_markdown/html) AYRI bir
  dataclass'ta tutulur; bu ayrım "hangi sayılar" ile "nasıl yazılır"
  sorularını birbirinden bağımsız kılar ve ikincisinin asla BİRİNCİSİNİN
  dışına çıkamayacağını görünür kılar.

### İlke D — Orkestrasyon Katmanında İş Mantığı Yok

> `app.py`, hangi kütüphanenin PDF/DOCX okuduğunu, eşleştirmenin nasıl
> çalıştığını ya da bir ChangeType'ın nasıl hesaplandığını BİLMEZ. SADECE
> `src/` modüllerinin fonksiyonlarını ÇAĞIRIR ve sonucu render eder.

**Neden:** Orkestrasyon katmanı (giriş noktası) sık değişmemeli ve test
edilmesi ZOR olan bir katman (gerçek bir Streamlit çalıştırması) OLMAMALI.
İş mantığı `src/` altında SAF fonksiyonlarda yaşarsa, hem Streamlit
çalıştırmadan test edilebilir HEM DE gelecekte farklı bir arayüze (CLI,
FastAPI) taşınabilir.

**Nasıl zorlanıyor:**
- `src/ingestion/base.py::DocumentLoader` — soyut arayüz; `factory.py`
  `app.py`'nin somut formatı (PDF/DOCX) hiç BİLMEDEN doğru loader'ı seçmesini
  sağlar.
- `src/analysis/pipeline.py::compare_documents` — TÜM boru hattını
  (ingestion → parsing → matching → classification → diff) çalıştıran TEK
  giriş noktası; içinde `import streamlit` YOKTUR, SAF bir Python
  fonksiyonudur. `app.py` bunu ÇAĞIRIR, İÇİNİ BİLMEZ.
- `src/reporting/exporter.py` — Excel/CSV/HTML üretim mantığı SAF
  fonksiyonlardır (bytes döndürür); `app.py`/`components.py` sadece bu
  bytes'ları `st.download_button`'a VERİR, NASIL üretildiğini bilmez.
- `app.py`'nin kendisi ~80 satırdır ve `if`/`for` dışında hesaplama
  İÇERMEZ — sadece widget çağrıları ve `try/except` hata yönlendirmesi.

**Neden `compare_documents`/`ComparisonResult` `src/ui/`de değil
`src/analysis/pipeline.py`de yaşıyor:** Adım 7'de reporting katmanı da AYNI
sonuca ihtiyaç duyunca, `reporting`'in `ui`'ye bağımlı olması (katman
sırasını TERSİNE çeviren bir ilişki) yerine ikisi de bu ORTAK analiz
modülüne bağımlı kılındı — bkz. `src/analysis/pipeline.py` modül
docstring'i.

## 3. Üç katmanlı süzgeç: "Bu iki madde aynı mı, ve nasıl değişti?"

İki belge arasında bir maddenin karşılığını bulmak VE nasıl değiştiğine
karar vermek, TEK bir algoritma değil, ÜÇ farklı sinyal türünün SIRAYLA
uygulandığı bir SÜZGEÇTİR — her katman bir öncekinin ÇÖZEMEDİĞİNİ dener,
hiçbiri diğerinin işini TEKRAR ETMEZ:

```
                     ┌─────────────────────────────────────┐
Katman 1  (YAPISAL)  │ section_matcher.py — L1              │
"Aynı numara/başlık   │ madde_no + section_type (+ başlık    │  hızlı, ücretsiz,
mı taşıyor?"          │ çelişki koruması)                    │  ağ/model gerekmez
                     └─────────────────────────────────────┘
                                     │ eşleşmeyenler
                                     ▼
                     ┌─────────────────────────────────────┐
Katman 2  (ANLAMSAL)  │ section_matcher.py — L2 + embedder.py│
"Numarası/başlığı      │ kosinüs benzerliği + Hungarian atama │  isteğe bağlı,
değişmiş olsa bile      │ (eşik altı reddedilir, bkz. İlke B)  │  model indirir
İÇERİK aynı mı?"       └─────────────────────────────────────┘
                                     │
                                     ▼ (eşleşen HER çift için)
                     ┌─────────────────────────────────────┐
Katman 3  (METİNSEL)  │ classifier.py                        │
"Eşleşen bu çiftin      │ difflib karakter benzerliği (İÇERİK) │  ucuz, deterministik,
İÇERİĞİ mi, NUMARASI    │ + numara eşitliği/konum (YAPISAL,     │  embedding'e BAĞIMLI
mı, İKİSİ Mİ değişti?"  │ BAĞIMSIZ bayraklar)                   │  DEĞİL
                     └─────────────────────────────────────┘
```

Bu üç katmanın birbirinden AYRI tutulmasının nedeni: Katman 1 ve 2 "hangi
Section hangi Section'a karşılık geliyor" sorusuna (bir `SectionMatch`
üretir); Katman 3 ise BAŞKA bir soruya cevap verir -- ve bu soru TEK bir
cevap DEĞİL, İKİ BAĞIMSIZ cevaptır: "içeriği IDENTICAL mi MODIFIED mi"
(`classify_content`) VE "numarası/konumu değişti mi"
(`is_renumbered`/`is_moved`, bkz. İlke C). Eşleşme bulma ile sınıflandırmayı
TEK bir adımda birleştirmek, "eşleşme bulma" ile "değişikliği sınıflandırma"
mantığını birbirine KARIŞTIRIRDI — oysa bunlar bağımsız test edilebilir,
bağımsız kalibre edilebilir kararlardır (bkz. METHODOLOGY.md).

Ayrıntılı algoritma açıklaması ve gerçek kalibrasyon bulguları için bkz.
[`METHODOLOGY.md`](./METHODOLOGY.md).

## 4. Dizin haritası

| Dizin | Sorumluluk | Bağımlı olduğu |
|---|---|---|
| `src/models.py` | Provenance sözleşmesi (`TextUnit`, `Document`, `Section`, `ChangeType`) — Mimari İlke A/C'nin TİP DÜZEYİNDE karşılığı | (hiçbiri) |
| `src/config.py` | TÜM eşikler/regex'ler/renkler TEK yerde | `models.py`'ye BAĞIMLI DEĞİL (dairesel bağımlılık riski) |
| `src/ingestion/` | PDF/DOCX → `TextUnit` | `models.py` |
| `src/parsing/` | `TextUnit`'ler → `Section` (hiyerarşi, cümle bölme, normalizasyon) | `ingestion` (loader çıktısını girdi alır) |
| `src/analysis/` | İki belgenin `Section`'ları → eşleşme + diff + sınıflandırma; `pipeline.py` TÜMÜNÜ orkestre eder | `parsing` |
| `src/reporting/` | Sonuç → DataFrame/Özet/Excel/CSV/HTML | `analysis/pipeline.py` (ui'ye DEĞİL) |
| `src/ui/` | Streamlit widget'ları + CSS | `analysis/pipeline.py`, `reporting/*` |
| `app.py` | İnce orkestrasyon (İlke D) | `src/ui/` |
| `data/samples/` | TEK KAYNAK test korpusu (`document_spec.py` → PDF/DOCX + `ground_truth.json`) | — |
| `tests/` | Her katman `ground_truth.json`'a karşı OBJEKTİF test edilir | tümü |

## 5. Test felsefesi

- **Tek doğruluk kaynağı:** `data/samples/document_spec.py`, hem örnek
  belgeleri (PDF+DOCX) HEM DE `ground_truth.json`'u AYNI tanımdan türetir
  (`generate_samples.py`). Belgeler ve doğru cevap ayrı ayrı elle
  yazılsaydı, aralarında sessizce tutarsızlık oluşabilir ve testler
  gerçek hataları değil bu tutarsızlığı ölçerdi.
- **Gözle değil, sayıyla doğrulama:** Her katmanın testleri, çıktısını
  `ground_truth.json`'daki sayısal/yapısal beklentilerle KARŞILAŞTIRIR
  (örn. "MADDE 6'nın fıkra (1)'i `replace`, fıkra (2)'si `equal` olmalı").
- **Gerçek entegrasyon, sahte'ye tercih edilir — ama HER ZAMAN değil:**
  `TestGercekEmbedderEntegrasyonu` gerçek `sentence-transformers` modelini
  kullanır (yavaş, ağ gerektirir); `TestL2EmbeddingHungarianAtama` SAHTE
  bir embedder kullanır (hızlı, deterministik) — algoritmanın kendisi
  (Hungarian atama, eşik mantığı) modelin doğruluğundan BAĞIMSIZ test
  edilir.
- **Uçtan uca UI testleri gerçek yükleme içerir:**
  `streamlit.testing.v1.AppTest` ile gerçek PDF/DOCX baytları yüklenip
  TAM uygulama akışı (yükleme → karşılaştırma → metrik → özet → indirme
  düğmeleri) doğrulanır — sadece izole birim testleri değil.

## 6. Güvenlik

Proje tamamlandıktan sonra tüm kod tabanı üzerinde bir güvenlik taraması
yapıldı (kod deseni araması + `pip-audit` bağımlılık taraması + hedefli
sızma denemeleri). Bulunanlar:

| Vektör | Durum | Not |
|---|---|---|
| CSV/Excel formül enjeksiyonu (CWE-1236) | **Bulundu, düzeltildi** | `src/reporting/metrics.py::_neutralize_formula_prefix` — bkz. aşağı |
| HTML/XSS (diff render) | Sorun yok | `html_renderer.py` HER metni `html.escape()` ile kaçırır (bkz. İlke A); `TestHtmlKacirma` bunu doğrular |
| Path traversal (yüklenen dosya adı → geçici dosya) | Sorun yok | `pathlib.Path.suffix` yol ayracı (`/`) İÇEREN bir değer ASLA döndürmez — `../../evil.pdf` gibi bir ad sadece `.pdf` sonekini verir |
| Bilinen CVE'li bağımlılık | Sorun yok | `pip-audit --strict`, kurulu TÜM paketlerde "No known vulnerabilities found" |
| Sunucu iç dosya yolu sızıntısı | Sorun yok (Adım 8'de düzeltildi) | `_load_document`, hata mesajlarındaki geçici dosya yolunu kullanıcının yüklediği gerçek dosya adıyla değiştirir |
| Kod enjeksiyonu (`eval`/`exec`/`pickle`/`subprocess`) | Kullanılmıyor | Kod tabanında bu API'lerin hiçbiri yok |
| Sabit kodlanmış sır/kimlik bilgisi | Yok | Deseni taranan tüm dosyalarda bulunamadı |
| Geçici dosya izinleri | Güvenli | `tempfile.NamedTemporaryFile` `0600` (sadece sahibi okur/yazar) oluşturur |

**CSV/Excel formül enjeksiyonu ayrıntısı:** bir madde metni (kullanıcının
yüklediği belgeden gelir) doğal biçimde `-` ile başlayan bir liste öğesi
olabilir (örn. `"- İlgili birimler bildirmekle yükümlüdür."`). Bu metin
`export_to_csv`/`export_to_excel` ile dışa aktarılıp Excel/LibreOffice'te
açıldığında, hücre başındaki `=`, `+`, `-`, `@` karakterleri bir FORMÜL
başlangıcı sayılabilir — bu, kötü niyetli (ya da sadece tesadüfi) bir
belge metninin bir hesap tablosu formülüne DÖNÜŞMESİ anlamına gelir.
`_neutralize_formula_prefix`, bu dört karakterle başlayan hücrelerin
başına bir tek tırnak (`'`) ekleyerek düz metin yorumunu ZORLAR (bkz.
`tests/test_reporting.py::TestMetricsFormulaEnjeksiyonuKorumasi`).

**Değerlendirilip ölçek olarak DÜŞÜK bulunan, izlenen konular:**
- `data/cache/embeddings/` (bkz. `embedder.py`) yüklenen belge metninden
  türetilen embedding vektörlerini SÜRESİZ diskte tutar (sha256 anahtarlı).
  Vektörler orijinal metne kolayca geri çevrilemez, ama gizli belgelerle
  çalışan bir DAĞITIMDA bu dizin periyodik olarak temizlenmeli.
- `requirements.txt` alt sınır (`>=`) kullanıyor, ÜST sınır/tam sürüm
  YOK — tekrarlanabilirlik açısından (güvenlik açığı değil) gelecekte
  `pip install` farklı bir sürüm çekebilir; üretime alınacaksa `pip
  freeze` ile kilitlenmesi düşünülebilir.

## 7. Bilinen sınırlamalar

Bu bölüm BİLEREK burada — "her şey mükemmel çalışıyor" izlenimi vermek
yerine, HANGİ senaryoların GERÇEK veriyle DOĞRULANMADIĞINI açıkça
belirtmek, Mimari İlke C'nin ("yorum yok, sadece doğrulanmış gerçek")
bu belgeye uygulanmış hâlidir:

- **"Yeri değişti" bayrağı** (`classifier.py::is_moved`) sadece SENTETİK
  testlerle doğrulandı — `ground_truth.json`'da gerçek bir örneği yok
  (regülasyon metninde bir maddenin numarası SABİT kalıp sadece bölümünün
  değiştiği senaryo nadirdir ve mevcut test korpusunda temsil edilmiyor).
- **L2 (embedding) pozitif örneği yok** — mevcut test korpusundaki HER
  gerçek eşleşme L1 (kural tabanlı) ile çözülüyor; L2'nin GERÇEKTEN
  çözmesi gereken "hem numarası HEM başlığı değişmiş ama aynı madde"
  senaryosu için elimizde sadece bir NEGATİF kalibrasyon örneği var (bkz.
  METHODOLOGY.md).
- **Performans** gerçek büyük ölçekli (yüzlerce sayfa) belgelerle test
  edilmedi — mevcut korpus küçük (13-14 madde); `.streamlit/config.toml`
  ile yükleme boyutu 50MB'a sınırlandı ama bu ampirik bir ölçüme değil,
  makul bir varsayıma dayanıyor.
