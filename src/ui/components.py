"""
Adım 6: Streamlit UI bileşenleri -- belge yükleme, karşılaştırma orkestrasyonu,
metrik kartları, ChangeType filtresi ve yan yana (side-by-side) görünüm.

NEDEN orkestrasyon (compare_documents) burada, app.py'de DEĞİL: Mimari İlke D
(bkz. src/ingestion/base.py::DocumentLoader NEDEN notu) -- app.py sadece bu
modülün fonksiyonlarını ÇAĞIRIR, format/iş mantığı BİLMEZ. compare_documents()
Streamlit'e bağımlı DEĞİLDİR (içinde `import streamlit` YOKTUR) -- SAF bir
python fonksiyonu olarak hem app.py'den hem doğrudan testlerden (bkz.
tests/test_ui.py) Streamlit çalıştırmaya gerek KALMADAN çağrılabilir. Sadece
render_* fonksiyonları (gerçek widget'lar) Streamlit'e bağımlıdır.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.analysis.classifier import ClassifiedSection, classify_match
from src.analysis.differ import SectionDiff, diff_section_match
from src.analysis.embedder import Embedder
from src.analysis.section_matcher import match_sections
from src.config import CHANGE_TYPE_LABELS_TR
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
    bellek-içi bir bayt dizisi verir; bu köprü SADECE burada (UI katmanında)
    gereklidir, ingestion katmanı bundan HABERSİZDİR.
    """
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)
    try:
        loader = get_loader(tmp_path)
        return loader.load(tmp_path, doc_id=doc_id)
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
    # gösterilmesi gerektiği) raporlama katmanının (Adım 7) inceliği,
    # burası sadece MAKUL bir varsayılan sunuyor.
    rows.sort(key=lambda r: r.classified.old.order_index if r.classified.old else r.classified.new.order_index)

    return ComparisonResult(old_meta=old_doc.meta, new_meta=new_doc.meta, rows=rows)


def render_upload_widgets() -> tuple[object | None, object | None]:
    """İki belge için yükleme alanlarını (eski | yeni) render eder, yüklenen dosyaları döndürür."""
    import streamlit as st

    col1, col2 = st.columns(2)
    with col1:
        old_file = st.file_uploader(
            "Eski belge (örn. 2019)", type=["pdf", "docx"], key="mk_old_uploader"
        )
    with col2:
        new_file = st.file_uploader(
            "Yeni belge (örn. 2023)", type=["pdf", "docx"], key="mk_new_uploader"
        )
    return old_file, new_file


def render_metric_cards(result: ComparisonResult) -> None:
    """Her ChangeType için bir metrik kartı (sayım) render eder."""
    import streamlit as st

    counts = result.counts()
    cols = st.columns(len(ChangeType))
    for col, change_type in zip(cols, ChangeType):
        with col:
            st.metric(CHANGE_TYPE_LABELS_TR[change_type.value], counts[change_type])


def render_change_type_filter() -> list[ChangeType]:
    """ChangeType'a göre çok seçmeli bir filtre çubuğu render eder; seçili türleri döndürür."""
    import streamlit as st

    options = list(ChangeType)
    label_by_type = {ct: CHANGE_TYPE_LABELS_TR[ct.value] for ct in options}
    type_by_label = {label: ct for ct, label in label_by_type.items()}

    selected_labels = st.multiselect(
        "Değişim türüne göre filtrele",
        options=list(label_by_type.values()),
        default=list(label_by_type.values()),
        key="mk_change_type_filter",
    )
    return [type_by_label[label] for label in selected_labels]


def render_side_by_side(row: ComparisonRow) -> None:
    """Tek bir ComparisonRow'u (başlık + rozet + yan yana renkli metin) render eder."""
    import streamlit as st

    from src.reporting.html_renderer import (
        render_change_type_badge,
        render_full_section_html,
        render_section_diff_html,
    )

    c = row.classified
    madde_no = c.old.madde_no if c.old else c.new.madde_no
    baslik = (c.old.baslik if c.old else c.new.baslik) or ""
    badge_html = render_change_type_badge(c.change_type)
    st.markdown(
        f'<div class="mk-section-header"><strong>MADDE {madde_no} — {baslik}</strong> {badge_html}</div>',
        unsafe_allow_html=True,
    )

    if row.section_diff is not None:
        old_html, new_html = render_section_diff_html(row.section_diff)
    else:
        old_html = render_full_section_html(c.old, c.change_type) if c.old else ""
        new_html = render_full_section_html(c.new, c.change_type) if c.new else ""

    empty_marker = '<span class="mk-empty-side">(karşılığı yok)</span>'
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="mk-column">{old_html or empty_marker}</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="mk-column">{new_html or empty_marker}</div>', unsafe_allow_html=True)
