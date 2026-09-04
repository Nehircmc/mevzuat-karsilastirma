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
- [ ] **Adım 5 (SIRADA): Differ** — cümle/kelime diff + ChangeType sınıflandırma
      (`SectionMatch` çiftleri üzerinde çalışacak; `IDENTICAL_COSINE_SIMILARITY_THRESHOLD`,
      `RENUMBERED_CHAR_SIMILARITY_THRESHOLD`, `MOVED_MIN_POSITION_DELTA` zaten
      `src/config.py`'de tanımlı)
- [ ] Adım 6: Streamlit UI
- [ ] Adım 7: Reporting — yönetici özeti + Excel/HTML dışa aktarım
- [ ] Adım 8: Performans, hata yönetimi, testler

### Adım 5'e başlarken dikkat edilecekler (Adım 4'ten notlar)

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
