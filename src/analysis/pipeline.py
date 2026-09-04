"""
Adım 6/7: TAM boru hattı orkestrasyonu -- ingestion -> structure_parser ->
match_sections -> (her eşleşen çift için) classify_match + diff_section_match.

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
from dataclasses import dataclass
from pathlib import Path

from src.analysis.classifier import ClassifiedSection, classify_match
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
        """Her ChangeType için satır sayısı (kapalı kümenin TAMAMI, 0 dahil -- bkz. models.ChangeType)."""
        counts = dict.fromkeys(ChangeType, 0)
        for row in self.rows:
            counts[row.classified.change_type] += 1
        return counts


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
) -> ComparisonResult:
    """
    TAM boru hattı: ingestion -> structure_parser -> match_sections ->
    (her eşleşen çift için) classify_match + diff_section_match.

    NEDEN classify_all() (classifier.py) yerine classify_match() döngü
    içinde çağrılıyor: diff_section_match() de AYNI SectionMatch nesnesine
    ihtiyaç duyar (bkz. differ.py) -- classify_all()'ın döndürdüğü
    ClassifiedSection bunu SAKLAMAZ (sadece old/new Section'ları taşır).
    Aynı eşleşme üzerinde iki AYRI geçiş yapıp sonra eşleştirmeye çalışmak
    yerine, TEK geçişte hem sınıflandırma hem diff üretilir.
    """
    old_doc = _load_document(old_bytes, old_filename, doc_id="eski")
    new_doc = _load_document(new_bytes, new_filename, doc_id="yeni")

    old_sections = parse_structure(old_doc)
    new_sections = parse_structure(new_doc)

    embedder = Embedder() if use_embedder else None
    match_result = match_sections(old_sections, new_sections, embedder=embedder)

    rows: list[ComparisonRow] = []
    for m in match_result.matches:
        rows.append(
            ComparisonRow(
                classified=ClassifiedSection(change_type=classify_match(m), old=m.old, new=m.new),
                section_diff=diff_section_match(m),
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
