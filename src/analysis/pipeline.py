"""
Adım 6/7: TAM boru hattı orkestrasyonu -- ingestion -> structure_parser ->
match_sections -> (her eşleşen çift için) sınıflandırma (içerik durumu +
yapısal bayraklar) + diff_section_match.

NEDEN src/ui/components.py'de DEĞİL burada (analysis katmanında): hem
src/ui/components.py (Streamlit widget'ları) hem src/reporting/*.py (Excel/
CSV/HTML dışa aktarım) AYNI ComparisonResult'ı tüketir. Bu modül Streamlit'e
BAĞIMLI DEĞİLDİR (içinde `import streamlit` yoktur) -- SAF bir python
fonksiyonu olarak hem app.py'den hem doğrudan testlerden Streamlit
çalıştırmaya gerek KALMADAN çağrılabilir. reporting/ katmanının ui/
katmanına bağımlı olması (ters yön) yerine, ikisi de bu ORTAK analysis
modülüne bağımlıdır.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from src.analysis.classifier import ClassifiedSection, classify_content, is_moved, is_renumbered
from src.analysis.differ import SectionDiff, diff_section_match
from src.analysis.embedder import Embedder
from src.analysis.section_matcher import match_sections
from src.ingestion.base import CorruptDocumentError, NoTextLayerError
from src.ingestion.factory import get_loader
from src.models import ChangeType, Document, DocumentMeta
from src.parsing.structure_parser import parse_structure


@dataclass(frozen=True)
class ComparisonRow:
    """Bir Section'ın (eşleşmiş ya da açıkta kalmış) nihai karşılaştırma satırı."""

    classified: ClassifiedSection
    section_diff: SectionDiff | None  # SADECE old VE new ikisi de doluysa üretilir


@dataclass(frozen=True)
class ComparisonResult:
    old_meta: DocumentMeta
    new_meta: DocumentMeta
    rows: list[ComparisonRow]

    def counts(self) -> dict[ChangeType, int]:
        """
        İÇERİK DURUMU sayımı: her ChangeType için satır sayısı (kapalı
        kümenin TAMAMI, 0 dahil -- bkz. models.ChangeType). Bu dört değer
        HER satırı TAM OLARAK BİR kez sayar (birbirini dışlayan bir
        bölüntüdür) -- bkz. structural_counts() için BUNUN TERSİ.
        """
        counts = dict.fromkeys(ChangeType, 0)
        for row in self.rows:
            counts[row.classified.change_type] += 1
        return counts

    def structural_counts(self) -> dict[str, int]:
        """
        YAPISAL DEĞİŞİKLİK sayımı: kaç satırda numarası/yeri değişti.

        NEDEN counts()'tan AYRI ve NEDEN bu ikisi birbirini dışlamıyor:
        "numarası değişti" ve "yeri değişti" içerik durumundan BAĞIMSIZ
        olgulardır (bkz. classifier.py NEDEN notu) -- AYNI satır hem
        counts()'ta bir İÇERİK durumuna (örn. MODIFIED) hem burada bir
        veya iki YAPISAL bayrağa (RENUMBERED ve/veya MOVED) katkıda
        bulunabilir. Bu yüzden counts() + structural_counts() toplamı
        "toplam madde sayısı"nı VERMEZ -- ikisi FARKLI sorulara cevaptır.
        """
        return {
            "RENUMBERED": sum(1 for row in self.rows if row.classified.numarasi_degisti),
            "MOVED": sum(1 for row in self.rows if row.classified.yeri_degisti),
        }


def _load_document(file_bytes: bytes, filename: str, doc_id: str) -> Document:
    """
    Yüklenen dosya baytlarını GEÇİCİ bir dosyaya yazıp uygun loader'ı
    (factory.get_loader) çağırır.

    NEDEN geçici dosya gerekli: DocumentLoader sözleşmesi bir DOSYA YOLU
    bekler, bellek-içi baytları DEĞİL -- PyMuPDF/python-docx ikisi de dosya
    yolu tabanlı API'ler kullanır (Adım 1). Streamlit'in file_uploader'ı ise
    bellek-içi bir bayt dizisi verir; bu köprü SADECE burada gereklidir,
    ingestion katmanı bundan HABERSİZDİR.
    """
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)
    try:
        loader = get_loader(tmp_path)
        return loader.load(tmp_path, doc_id=doc_id)
    except (NoTextLayerError, CorruptDocumentError) as exc:
        # NEDEN mesaj YENİDEN yazılıyor: loader'lar hata mesajlarında
        # kendilerine verilen `path`i (burada GEÇİCİ dosya yolu, örn.
        # /tmp/tmpXXXX.pdf) kullanır -- kullanıcıya bunun yerine YÜKLEDİĞİ
        # dosyanın kendi adı gösterilmeli (hem daha anlaşılır hem sunucunun
        # iç dosya sistemi düzenini SIZDIRMAZ). str.replace() güvenlidir:
        # loader'lar `path`i HER ZAMAN str(tmp_path) ile birebir aynı
        # biçimde interpolate eder (bkz. pdf_loader.py/docx_loader.py).
        message = str(exc).replace(str(tmp_path), filename)
        raise type(exc)(message) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def compare_documents(
    old_bytes: bytes,
    old_filename: str,
    new_bytes: bytes,
    new_filename: str,
    *,
    use_embedder: bool = False,
    old_version_label: str | None = None,
    old_publication_date: date | None = None,
    old_effective_date: date | None = None,
    new_version_label: str | None = None,
    new_publication_date: date | None = None,
    new_effective_date: date | None = None,
) -> ComparisonResult:
    """
    TAM boru hattı: ingestion -> structure_parser -> match_sections ->
    (her eşleşen çift için) classify_content/is_renumbered/is_moved +
    diff_section_match.

    NEDEN classify_all() (classifier.py) yerine bu üçü döngü içinde
    çağrılıyor: diff_section_match() de AYNI SectionMatch nesnesine
    ihtiyaç duyar (bkz. differ.py) -- classify_all()'ın döndürdüğü
    ClassifiedSection bunu SAKLAMAZ (sadece old/new Section'ları taşır).
    Aynı eşleşme üzerinde iki AYRI geçiş yapıp sonra eşleştirmeye çalışmak
    yerine, TEK geçişte hem sınıflandırma hem diff üretilir.

    old_version_label/old_publication_date/old_effective_date (ve new_*)
    Mimari Ek 1 (F1)'in OPSİYONEL girdileridir -- hiçbiri verilmezse
    davranış AYNEN eskisi gibi kalır (geriye dönük uyumlu). NEDEN slot
    HER ZAMAN "A"/"B" olarak atanır (bu parametreler boş olsa BİLE):
    slot kullanıcının YÜKLEME sırasına bağlıdır, sürüm etiketi/tarih
    girilip girilmediğinden BAĞIMSIZDIR (bkz. src/temporal.py::
    belge_gorunen_adi) -- bu sayede görünen ad HER ZAMAN "Belge A/B"
    önekini taşır, en kötü ihtimalle dosya adına düşer.

    NEDEN source_path BURADA da (old_filename/new_filename ile) ÜZERİNE
    YAZILIYOR: _load_document, DocumentMeta.source_path'i loader'a verilen
    GEÇİCİ dosya yoluna (`/tmp/tmpXXXXXX.pdf`) göre doldurur -- bu,
    belge_gorunen_adi'nin F3 kademe-3 düşüşünde (sürüm etiketi/tarih
    YOKSA dosya adına düşülür) kullanıcıya ANLAMSIZ bir geçici dosya adı
    göstermesine yol açardı. Gerçek yükleme adı (old_filename/new_filename)
    burada tekrar yazılarak görünen ad HER ZAMAN kullanıcının yüklediği
    dosyanın adını taşır.
    """
    old_doc = _load_document(old_bytes, old_filename, doc_id="eski")
    new_doc = _load_document(new_bytes, new_filename, doc_id="yeni")
    old_doc.meta = replace(
        old_doc.meta,
        source_path=old_filename,
        slot="A",
        version_label=old_version_label,
        publication_date=old_publication_date,
        effective_date=old_effective_date,
    )
    new_doc.meta = replace(
        new_doc.meta,
        source_path=new_filename,
        slot="B",
        version_label=new_version_label,
        publication_date=new_publication_date,
        effective_date=new_effective_date,
    )

    old_sections = parse_structure(old_doc)
    new_sections = parse_structure(new_doc)

    embedder = Embedder() if use_embedder else None
    match_result = match_sections(old_sections, new_sections, embedder=embedder)

    rows: list[ComparisonRow] = []
    for m in match_result.matches:
        section_diff = diff_section_match(m)
        change_type = classify_content(m)
        # NEDEN classify_content()'in IDENTICAL kararı BURADA section_diff'e
        # KARŞI doğrulanıyor (kalite kontrolünde bulundu): classify_content
        # TÜM madde metninin karakter benzerlik ORANINA (bkz.
        # IDENTICAL_CHAR_SIMILARITY_THRESHOLD) bakar -- ÇOK UZUN bir maddede
        # (örn. onlarca fıkra) TEK bir cümlelik gerçek bir değişiklik, oran
        # üzerinde İHMAL EDİLEBİLİR bir etki yaratır (örn. 13.790 karakterlik
        # bir maddede 1 cümlelik değişiklik oranı %99,88'de bırakır -- eşiğin
        # ÜSTÜNDE). Sonuç: rozet "Değişmedi" derken section_diff aynı satırda
        # gerçek bir "replace" cümlesi TAŞIYABİLİRDİ -- kullanıcıya YANLIŞ
        # NEGATİF bir izlenim verirdi. section_diff'in cümle hizalaması
        # normalize edilmiş metne dayandığından (bkz. differ.py::_normalized_
        # key) whitespace/noktalama GÜRÜLTÜSÜNÜ zaten doğru yok sayar; bu
        # yüzden burada bulunan HERHANGİ bir "equal" DIŞI opcode, uzunluktan
        # BAĞIMSIZ, GERÇEK bir içerik farkına işaret eder. NEDEN SADECE
        # IDENTICAL -> MODIFIED yönünde (tersi DEĞİL): mevcut char-similarity
        # eşiği gerçek verilerle KALİBRE EDİLMİŞTİR (bkz. docs/METHODOLOGY.md)
        # -- bu düzeltme onu DEĞİŞTİRMEZ, sadece TEK YÖNLÜ bir güvenlik ağı
        # ekler; zaten MODIFIED olan bir satırı asla IDENTICAL'a ÇEVİRMEZ.
        if change_type == ChangeType.IDENTICAL and any(
            sd.op != "equal" for sd in section_diff.sentence_diffs
        ):
            change_type = ChangeType.MODIFIED
        rows.append(
            ComparisonRow(
                classified=ClassifiedSection(
                    change_type=change_type,
                    old=m.old,
                    new=m.new,
                    numarasi_degisti=is_renumbered(m),
                    yeri_degisti=is_moved(m),
                ),
                section_diff=section_diff,
            )
        )
    for s in match_result.unmatched_old:
        rows.append(
            ComparisonRow(
                classified=ClassifiedSection(change_type=ChangeType.REMOVED, old=s, new=None),
                section_diff=None,
            )
        )
    for s in match_result.unmatched_new:
        rows.append(
            ComparisonRow(
                classified=ClassifiedSection(change_type=ChangeType.ADDED, old=None, new=s),
                section_diff=None,
            )
        )

    # NEDEN old.order_index (yoksa new.order_index) ile sıralanıyor: nihai
    # görünüm KABACA belge sırasını izlemeli -- kesin/birleşik bir sıralama
    # (örn. ADDED bir maddenin TAM olarak hangi eski madde ile bitişik
    # gösterilmesi gerektiği) raporlama katmanının inceliği, burası sadece
    # MAKUL bir varsayılan sunuyor.
    rows.sort(key=lambda r: r.classified.old.order_index if r.classified.old else r.classified.new.order_index)

    return ComparisonResult(old_meta=old_doc.meta, new_meta=new_doc.meta, rows=rows)
