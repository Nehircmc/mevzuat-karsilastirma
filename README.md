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
- [x] Adım 7: Reporting — `src/reporting/metrics.py` (DataFrame'ler) +
      `src/reporting/summary_builder.py` (ŞABLON tabanlı Yönetici Özeti,
      serbest metin YOK — Mimari İlke C) + `src/reporting/exporter.py`
      (Excel/.xlsx + CSV + bağımsız HTML dışa aktarım) + `app.py`/
      `components.py`'ye Yönetici Özeti paneli ve indirme düğmeleri
      entegre edildi. Orkestrasyon (`compare_documents`) `src/ui/
      components.py`'den `src/analysis/pipeline.py`'ye TAŞINDI (hem `ui`
      hem `reporting` ORTAK bu modüle bağımlı, `reporting`'in `ui`'ye
      bağımlı olması gibi ters bir katman ilişkisi önlendi). 35 yeni test
      (`tests/test_reporting.py`) + entegrasyon testleri, toplam 193 test
      geçiyor; tarayıcıda görsel olarak da doğrulandı.
- [ ] **Adım 8 (SIRADA): Performans, hata yönetimi, testler**

### Adım 8'e başlarken dikkat edilecekler (Adım 7'den notlar)

- `src/analysis/pipeline.py::compare_documents(...) -> ComparisonResult`
  TAM boru hattının TEK giriş noktasıdır — hem `src/ui/components.py` hem
  `src/reporting/*.py` bunu tüketir, ikisi de kendi başına boru hattını
  TEKRAR ÇALIŞTIRMAZ.
- `src/reporting/summary_builder.py::build_summary_stats(result) ->
  SummaryStats` SAF sayısal hesaplama, `render_summary_markdown(stats)`
  (Streamlit paneli için) ve `html_renderer.render_summary_html(stats)`
  (bağımsız HTML dışa aktarım için) AYNI `SummaryStats`ı İKİ farklı
  biçimde (Markdown/HTML) render eder — sayı hesaplama mantığı TEK yerde.
  "En çok değişen bölüm" istatistiği SAYISAL bir agregasyondur (yorum
  DEĞİL) — eşitlikte belgedeki İLK GÖRÜLME SIRASI belirleyici (deterministik).
- `src/reporting/exporter.py::export_to_html()` ürettiği dosya `assets/
  styles.css`'teki `.mk-standalone-page`/`.mk-side-by-side`/`.mk-row`
  sınıflarına SARILIR — bu sınıflar Streamlit'in canlı DOM'unda hiç
  YOKTUR, bu yüzden AYNI CSS dosyası her iki yere de (canlı sayfa +
  bağımsız dosya) çakışmadan enjekte edilebiliyor.
- Excel için `openpyxl`, CSV için `utf-8-sig` (BOM'lu, Excel'in Türkçe
  karakterleri bozmadan açması için) kullanılıyor.
- **ÖNEMLİ SINIRLAMA (Adım 4/5'ten devam eden, hâlâ çözülmedi):**
  `ground_truth.json`'da gerçek bir MOVED örneği VE L2'nin gerçekten
  çözmesi gereken pozitif bir embedding örneği YOK. Adım 8'de veya
  gerçek belgelerle kullanılmaya başlanmadan önce `document_spec.py`'ye
  bu iki senaryo eklenip ilgili eşikler/mantık yeniden gözden geçirilmeli.
- Uygulamayı çalıştırmak için: `streamlit run app.py` (bkz. "Uygulamayı
  Çalıştırma" bölümü). `ground_truth.json` (`data/samples/`) hâlâ TEK
  doğruluk kaynağı; her yeni katmanı gözle değil buna karşı objektif
  skorla test edin.
