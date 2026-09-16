# Mevzuat Karşılaştırma

İki mevzuat/stratejik plan/politika belgesini (PDF/DOCX) madde madde
karşılaştıran, ortak/değişen/kaldırılan/yeni eklenen bölümleri kaynak
göstererek sunan bir belge analiz aracı.

## Özellikler

- **PDF/DOCX içe aktarma** — kaynak sayfa/konum bilgisini (provenance)
  koruyarak metni ayrıştırır.
- **Madde/bölüm eşleştirme** — kural tabanlı (aynı numara/başlık) ve
  embedding tabanlı (anlamsal benzerlik + Hungarian atama) iki katmanlı
  eşleştirme; yeniden numaralanan veya yeri değişen maddeleri de yakalar.
- **Cümle/kelime düzeyinde diff** — değişen maddelerde tam olarak neyin
  değiştiğini vurgular.
- **İçerik durumu ve yapısal değişiklik ayrımı** — bir madde aynı anda hem
  içerik hem numara/yer değiştirebilir; bu iki boyut birbirinden bağımsız
  raporlanır.
- **Tarihsel/sayısal değişiklik tespiti** — maddeler içindeki tarih/süre
  ifadelerinin değişimini üçüncü, bağımsız bir boyut olarak işaretler.
- **Yönetici özeti ve dışa aktarım** — Excel (.xlsx), CSV ve bağımsız HTML
  raporu; CSV/Excel formül enjeksiyonuna (CWE-1236) karşı korumalı.
- **Streamlit arayüzü** — yükleme, ChangeType filtresi, renkli yan yana
  karşılaştırma görünümü.

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Kullanım

**Uygulamayı çalıştırma:**

```bash
streamlit run app.py
```

Tarayıcıda açılan sayfada eski ve yeni belgeyi (PDF/DOCX) yükleyin;
madde/bölüm bazında renkli yan yana karşılaştırma otomatik oluşur.

**Test belgelerini üretme:**

```bash
python -m data.samples.generate_samples
```

**Testleri çalıştırma:**

```bash
pytest -v
```

## Proje Yapısı

```
src/
  ingestion/   PDF/DOCX yükleme -> provenance'lı metin
  parsing/     Madde/bölüm hiyerarşisi, cümle bölme, normalizasyon
  analysis/    Eşleştirme (kural + embedding), diff, sınıflandırma,
               tarihsel değişiklik tespiti, boru hattı orkestrasyonu
  reporting/   Metrikler, yönetici özeti, Excel/CSV/HTML dışa aktarım
  ui/          Streamlit bileşenleri ve stil
data/samples/  Sentetik test belgeleri ve ground_truth.json
tests/         320 test
```

## Dokümantasyon

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — mimari ilkeler, katman
  sınırları, güvenlik bulguları ve gerekçeleri.
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — eşleştirme/diff/
  sınıflandırma algoritmasının adım adım işleyişi ve gerçek kalibrasyon
  bulguları.

## Durum

Proje tamamlandı, 320 test geçiyor. `data/samples/ground_truth.json` tek
doğruluk kaynağıdır; yeni değişiklikler gözle değil buna karşı objektif
skorla değerlendirilir. Bilinen sınırlamalar için
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §7'ye bakın.
