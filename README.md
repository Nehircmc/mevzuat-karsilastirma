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
- [ ] **Adım 4 (SIRADA): Matcher L2 — embedding + Hungarian atama + eşik kalibrasyonu**
      (L1'in `unmatched_old`/`unmatched_new` çıktısı üzerinde çalışacak;
      `SECTION_MATCH_MIN_COSINE_SIMILARITY` ve `EMBEDDING_MODEL_NAME` zaten
      `src/config.py`'de tanımlı)
- [ ] Adım 5: Differ — cümle/kelime diff + ChangeType sınıflandırma
- [ ] Adım 6: Streamlit UI
- [ ] Adım 7: Reporting — yönetici özeti + Excel/HTML dışa aktarım
- [ ] Adım 8: Performans, hata yönetimi, testler

### Adım 4'e başlarken dikkat edilecekler (Adım 3'ten notlar)

- `match_sections(old_sections, new_sections) -> MatchResult` (`src/analysis/
  section_matcher.py`), `matches: list[SectionMatch]` (`old`, `new`, `method`:
  `"NUMBER_AND_TITLE"` | `"TITLE_ONLY"`) + `unmatched_old`/`unmatched_new`
  döndürür. L1 SADECE yapısal sinyalle (numara + başlık metni) çalışır,
  embedding KULLANMAZ; `unmatched_old`/`unmatched_new` "REMOVED/ADDED"
  DEĞİLDİR — L2'nin embedding ile eşleşme denemesi başarısız olduktan SONRA
  kesin karar verilir.
- L1'in kasıtlı olarak ÇÖZMEDİĞİ (L2'ye bıraktığı) durum: hem numarası HEM
  başlığı değişen maddeler (örn. yeniden yazılmış/yeniden adlandırılmış bir
  madde) — bunlar `unmatched_old`/`unmatched_new`'de kalır, L2 embedding
  benzerliğiyle bulmalı. Mevcut `ground_truth.json` bu senaryoyu içermiyor;
  Adım 4 test verisine böyle bir örnek eklemek gerekebilir.
- Aynı başlık her iki tarafta da BİRDEN FAZLA kez geçiyorsa (örn. iki farklı
  maddenin başlığı tesadüfen aynıysa) L1 bilerek eşleştirmez (belirsizlik) —
  L2 bu durumda embedding + Hungarian atama ile karar vermeli.
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
