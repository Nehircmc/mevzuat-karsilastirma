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
- [ ] **Adım 3 (SIRADA): Matcher L1 — kural tabanlı eşleme** (madde/bölüm
      numarası + başlık regex'i ile 2019/2023 Section'larını eşleştirme;
      `src/analysis/section_matcher.py` + `tests/test_matcher.py`)
- [ ] Adım 4: Matcher L2 — embedding + Hungarian atama + eşik kalibrasyonu
- [ ] Adım 5: Differ — cümle/kelime diff + ChangeType sınıflandırma
- [ ] Adım 6: Streamlit UI
- [ ] Adım 7: Reporting — yönetici özeti + Excel/HTML dışa aktarım
- [ ] Adım 8: Performans, hata yönetimi, testler

### Adım 3'e başlarken dikkat edilecekler (Adım 2'den notlar)

- `structure_parser.parse_structure()` her belge için `list[Section]` üretiyor
  (`doc_id, heading_path, section_type, madde_no, baslik, order_index, units`).
  L1 eşleştirici muhtemelen önce `madde_no` + `section_type` üzerinden
  doğrudan eşleştirmeyi deneyecek (RENUMBERED/aynı-numara durumları), eşleşmeyenler
  L2'ye (embedding) düşecek.
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
