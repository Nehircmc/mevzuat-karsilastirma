# Mevzuat Karşılaştırma

İki mevzuat/stratejik plan/politika belgesini (PDF/DOCX) karşılaştırarak
ortak, farklı, değişen ve yeni eklenen bölümleri kaynak göstererek sunan
belge analiz aracı.

Mimari kararlar ve yol haritası için proje geliştirme geçmişine bakınız.
Detaylı mimari doküman `docs/ARCHITECTURE.md` içinde (ilerleyen adımlarda
yazılacaktır).

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Test Belgelerini Üretme

```bash
python -m data.samples.generate_samples
```

## Testleri Çalıştırma

```bash
pytest -v
```

## Uygulamayı Çalıştırma

```bash
streamlit run app.py
```

Tarayıcıda açılan sayfada eski ve yeni belgeyi (PDF/DOCX) yükleyin;
madde/bölüm bazında renkli yan yana karşılaştırma otomatik oluşur.

## Durum

- [x] Adım 0: İskelet, requirements, config.py
- [x] Adım 1: Ingestion (PDF/DOCX -> provenance'lı TextUnit) — 22 test geçiyor
- [x] Adım 2: Structure parser (madde/bölüm hiyerarşisi) + cümle bölme — 51 test geçiyor
- [x] Adım 3: Matcher L1 — kural tabanlı eşleme (`src/analysis/section_matcher.py`,
      iki geçiş: aynı numara + çelişmeyen başlık, sonra benzersiz başlık eşleşmesi
      RENUMBERED için) — 21 yeni test, toplam 72 test geçiyor
- [x] Adım 4: Matcher L2 — embedding (`src/analysis/embedder.py`, disk önbellekli
      sentence-transformers sarmalayıcı) + Hungarian atama
      (`scipy.optimize.linear_sum_assignment`) + eşik kalibrasyonu
      (`SECTION_MATCH_MIN_COSINE_SIMILARITY` 0.50 → **0.65**, gerçek bir yanlış
      pozitif ölçümüyle kalibre edildi, bkz. aşağıdaki not) — 15 yeni test,
      toplam 87 test geçiyor
- [x] Adım 5: Differ (`src/analysis/differ.py`: Section'ın BİRLEŞTİRİLMİŞ gövde
      metni üzerinden cümle bölme + difflib.SequenceMatcher ile cümle/kelime
      hizalama) + Classifier (`src/analysis/classifier.py`: kapalı ChangeType
      sözlüğüne karakter-benzerliği + numara + konum sinyaliyle atama) —
      31 yeni test, toplam 118 test geçiyor
- [x] Adım 6: Streamlit UI — `app.py` (ince orkestrasyon, iş mantığı yok) +
      `src/ui/components.py` (yükleme, metrik kartları, ChangeType filtresi,
      yan yana görünüm + Streamlit'siz `compare_documents()` orkestrasyonu) +
      `src/ui/styles.py`/`assets/styles.css` (renk `COLOR_PALETTE`'ten
      üretilir, düzen statik dosyada) + `src/reporting/html_renderer.py`
      (cümle/kelime diff'lerini renkli HTML'e çevirir) — 39 yeni test
      (`streamlit.testing.v1.AppTest` ile gerçek yükleme dahil uçtan uca
      test edildi + tarayıcıda görsel olarak doğrulandı), toplam 157 test
      geçiyor
- [ ] **Adım 7 (SIRADA): Reporting** — yönetici özeti + Excel/HTML dışa aktarım
- [ ] Adım 8: Performans, hata yönetimi, testler

### Adım 7'ye başlarken dikkat edilecekler (Adım 6'dan notlar)

- `src/ui/components.py::compare_documents(old_bytes, old_filename, new_bytes,
  new_filename, use_embedder=False) -> ComparisonResult` TAM boru hattını
  (ingestion → structure_parser → match_sections → classify_match +
  diff_section_match) çalıştıran, Streamlit'e BAĞIMLI OLMAYAN saf bir
  fonksiyondur — Adım 7'nin Excel/HTML dışa aktarımı da muhtemelen AYNI
  `ComparisonResult`i (satır: `ClassifiedSection` + opsiyonel `SectionDiff`)
  tüketmeli, tekrar boru hattı çalıştırmamalı.
- `src/reporting/html_renderer.py` SINIF tabanlı HTML üretir (`mk-diff-<key>`,
  `mk-badge-<key>`), INLINE stil değil — renkler SADECE `src/ui/styles.py::
  generate_color_css()` ile `config.COLOR_PALETTE`'ten üretilir. Adım 7'nin
  HTML dışa aktarımı bu HTML'i yeniden kullanabilir AMA çıktı dosyası
  KENDİ BAŞINA (Streamlit'siz) açıldığında da renklerin görünmesi için
  `styles.build_full_css()`'i `<style>` olarak GÖMMESİ gerekir (Streamlit
  ortamı olmadan `st.markdown` enjeksiyonu çalışmaz).
- `app.py` bilerek İŞ MANTIĞI BARINDIRMIYOR (Mimari İlke D, bkz.
  `src/ingestion/base.py::DocumentLoader` NEDEN notu) — sadece
  `components.py`/`styles.py` fonksiyonlarını çağırıyor. Adım 7 için de aynı
  ilke geçerli: bir "Excel'e aktar" düğmesi eklenirse, üretim mantığı
  `src/reporting/` altında SAF bir fonksiyonda olmalı, `app.py`'de değil.
- **Streamlit sürüm notu:** `st.file_uploader(type=["pdf","docx"])` kısıtlaması
  artık (streamlit 1.63) WIDGET DÜZEYİNDE uygulanıyor — desteklenmeyen bir
  uzantı `app.py`'nin kodu HİÇ ÇALIŞMADAN reddediliyor (bkz.
  `test_yukleme_alanlari_sadece_pdf_docx_kabul_eder`). `app.py`'deki
  `except ValueError` bloğu bu yüzden normal kullanımda ERİŞİLEMEZ durumda
  (savunma amaçlı bırakıldı) — asıl ValueError testi
  `compare_documents()`'ı DOĞRUDAN çağıran birim testinde (bkz.
  `tests/test_ui.py::TestCompareDocumentsGercekOrnekBelgelerle::
  test_desteklenmeyen_uzanti_hata_verir`).
- Uygulamayı çalıştırmak için: `streamlit run app.py` (bkz. bu dosyanın
  "Uygulamayı Çalıştırma" bölümü).
- **ÖNEMLİ SINIRLAMA (Adım 5'ten devam eden not):** `ground_truth.json`'da
  hâlâ gerçek bir MOVED örneği ve L2'nin gerçekten çözmesi gereken pozitif
  bir embedding örneği yok (bkz. Adım 4/5 notları) — bu, Adım 7'nin yönetici
  özetinde "kaç madde MOVED/embedding ile bulundu" gibi bir istatistik
  gösterilecekse gerçek veriyle doğrulanamayacağı anlamına gelir.

### Adım 6'dan önceki notlar (Adım 5'ten)

- `diff_section_match(match: SectionMatch) -> SectionDiff` (`src/analysis/
  differ.py`), `sentence_diffs: list[SentenceDiff]` döndürür (`op`: `"equal"` |
  `"replace"` | `"delete"` | `"insert"`; `"replace"` için `word_diffs:
  list[WordDiff]` de dolu). `SectionDiff.is_identical` tüm cümlelerin `"equal"`
  olup olmadığını söyler. Cümle bölme, `Section.units`'teki HER TextUnit'i AYRI
  AYRI değil `section_sentences()` ile BİRLEŞTİRİLMİŞ metin üzerinden çalışır
  (Adım 2'nin PDF sayfa-içi kırılma notunu çözer) — bir cümle birden fazla
  orijinal TextUnit'ten geliyorsa (`DiffSentence.units`), her parça KENDİ
  orijinal char_start/char_end'ine geri izlenebilir.
- `classify_match(match: SectionMatch) -> ChangeType` (`src/analysis/
  classifier.py`) SADECE karakter benzerliği (difflib, normalize edilmiş
  metin) + `madde_no` eşitliği + `heading_path`/`order_index` konum sinyaliyle
  çalışır — embedding/kosinüs benzerliği KULLANMAZ (L1 eşleşmelerinde embedder
  hiç çağrılmamış olabilir, sınıflandırma bu opsiyonel veriye bağımlı
  olmamalı). `classify_all(result: MatchResult) -> list[ClassifiedSection]`
  hem eşleşenleri (IDENTICAL/MODIFIED/RENUMBERED/MOVED) hem
  unmatched_old/unmatched_new'i (REMOVED/ADDED) TEK bir listede toplar; hiçbir
  Section sessizce kaybolmaz (`test_classify_all_hicbir_sectioni_kaybetmez`).
- **ÖNEMLİ SINIRLAMA (Adım 4'ten devam eden not):** `ground_truth.json`'da
  gerçek bir MOVED örneği YOK — `_moved()` mantığı (heading_path bağlamı veya
  `MOVED_MIN_POSITION_DELTA` kadar pozisyon kayması) sadece SENTETİK testlerle
  doğrulandı, gerçek belge verisiyle değil. Aynı şekilde L2'nin gerçekten
  çözmesi gereken pozitif bir embedding örneği de hâlâ yok (bkz. Adım 4 notu).
  Reporting'e (Adım 7) geçmeden önce document_spec.py'ye MOVED + L2-pozitif
  örnekleri eklemek düşünülmeli.
- `src/parsing/sentence_splitter.py`'ye `find_sentence_spans(text: str) ->
  list[tuple[int,int]]` eklendi (saf string, TextUnit'ten bağımsız) —
  `split_sentences(unit)` VE `differ.section_sentences()` AYNI kısaltma-duyarlı
  cümle sınırı mantığını buradan paylaşıyor (tek kaynak, Adım 1'in
  document_spec.py ilkesiyle aynı gerekçe).

- `match_sections(old_sections, new_sections, embedder=None, min_similarity=...) ->
  MatchResult`. `embedder` verilmezse (varsayılan `None`) davranış SADECE L1
  (Adım 3) ile aynıdır — sentence-transformers hiç yüklenmez. `embedder=Embedder()`
  verilirse L1'in eşleştiremediği artıklar arasında kosinüs benzerliği +
  Hungarian atama (L2) denenir; `method` alanı `"NUMBER_AND_TITLE"` |
  `"TITLE_ONLY"` | `"EMBEDDING"` olabilir.
- **Kritik kalibrasyon bulgusu:** gerçek modelle (`paraphrase-multilingual-MiniLM-L12-v2`)
  ölçüldüğünde, 2019 MADDE 8 "Arşivleme Esasları" (REMOVED) ile 2023 MADDE 11
  "Açık Veri Portalı" (ADDED) — TAMAMEN alakasız iki madde — kosinüs benzerliği
  ~0.56 çıkıyor (kısa, ortak mevzuat kelime dağarcığı paylaşan iki fıkralı
  maddeler oldukları için). Eski eşik (0.50) bunu YANLIŞLIKLA eşleştirirdi;
  eşik 0.65'e çıkarıldı (bkz. `src/config.py` NEDEN notu ve
  `tests/test_matcher.py::TestGercekEmbedderEntegrasyonu::test_arsivleme_acik_veri_portaliyla_yanlislikla_eslesmiyor`).
  **ÖNEMLİ SINIRLAMA:** bu kalibrasyon SADECE bu bir negatif örneğe dayanıyor —
  `ground_truth.json`'da L2'nin gerçekten çözmesi GEREKEN (hem numarası HEM
  başlığı değişmiş ama içerik olarak aynı madde olan) bir POZİTİF örnek YOK.
  Adım 5/gerçek belgeler öncesi, document_spec.py'ye böyle bir örnek eklenip
  eşiğin hem pozitif hem negatif veriyle yeniden kalibre edilmesi düşünülmeli.
- `src/analysis/embedder.py`: `Embedder.embed(texts) -> np.ndarray`, model
  TEMBEL yüklenir (ilk `embed()` çağrısında), sonuçlar `data/cache/embeddings/
  <model_adı>/<sha256>.npy` altında disk önbelleğe alınır (metin+model bazlı;
  farklı model = farklı alt dizin, eski önbellek asla yanlışlıkla okunmaz).
- `section_matcher.py` içindeki `_EmbedderLike` (Protocol) sayesinde testler
  gerçek modeli yüklemeden (hızlı, ağ gerektirmeyen) sahte/deterministik bir
  embedder enjekte edebiliyor — `TestL2EmbeddingHungarianAtama` gerçek modelden
  BAĞIMSIZ, `TestGercekEmbedderEntegrasyonu` ise gerçek modeli kullanıyor
  (ilk çalıştırmada ağ + model indirimi gerektirir, sonrasında hem HuggingFace
  hem embedding önbelleği sayesinde hızlıdır).
- PDF'te reportlab bazen TEK bir paragrafın satır kaydırmasını sayfa
  SINIRI olmadan bile iki ayrı bloğa bölebiliyor (örn. "Veri Paylaşımı"
  madde 6, fıkra 1). `structure_parser` bunları doğru offsetlerle ayrı
  TextUnit olarak tutuyor (uydurma birleştirme yok) ama bu, cümle bölmenin
  HER TextUnit'i ayrı ayrı değil, `Section.joined_text` (ya da normalize
  edilmiş birleşik metin) üzerinde çalıştırılması gerektiği anlamına
  geliyor — aksi halde tek bir gerçek cümle, differ'da (Adım 5) yanlışlıkla
  iki parçaya bölünmüş görünür.
- `ground_truth.json` (`data/samples/`) hâlâ tek doğruluk kaynağı;
  matcher/differ'ı gözle değil buna karşı objektif skorla test edin.
