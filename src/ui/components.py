"""
Adım 6/7: Streamlit UI bileşenleri -- belge yükleme, metrik kartları,
ChangeType filtresi, yan yana (side-by-side) görünüm, Yönetici Özeti paneli
ve Excel/CSV/HTML indirme düğmeleri.

NEDEN karşılaştırma orkestrasyonu (compare_documents) BURADA DEĞİL, artık
src/analysis/pipeline.py'de: hem bu modül hem src/reporting/*.py (Adım 7)
AYNI ComparisonResult'ı tüketiyor -- reporting katmanının ui katmanına
bağımlı olması (ters yön) yerine ikisi de ORTAK analysis modülüne bağımlı
(bkz. pipeline.py NEDEN notu). Bu modüldeki fonksiyonlar SADECE render_*
(gerçek Streamlit widget'ları); iş mantığı/hesaplama YOKTUR.
"""

from __future__ import annotations

from src.analysis.pipeline import ComparisonResult, ComparisonRow, compare_documents
from src.config import CHANGE_TYPE_LABELS_TR
from src.models import ChangeType

__all__ = [
    "ComparisonResult",
    "ComparisonRow",
    "compare_documents",
    "render_upload_widgets",
    "render_metric_cards",
    "render_change_type_filter",
    "render_side_by_side",
    "render_executive_summary",
    "render_download_buttons",
]


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

    from src.reporting.html_renderer import render_row_body_html, render_row_header_html

    c = row.classified
    st.markdown(render_row_header_html(c.old, c.new, c.change_type), unsafe_allow_html=True)

    old_html, new_html = render_row_body_html(c.old, c.new, c.change_type, row.section_diff)

    empty_marker = '<span class="mk-empty-side">(karşılığı yok)</span>'
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="mk-column">{old_html or empty_marker}</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="mk-column">{new_html or empty_marker}</div>', unsafe_allow_html=True)


def render_executive_summary(result: ComparisonResult) -> None:
    """Yönetici Özeti panelini (bkz. src/reporting/summary_builder.py) render eder."""
    import streamlit as st

    from src.reporting.summary_builder import build_summary_stats, render_summary_markdown

    stats = build_summary_stats(result)
    st.markdown(render_summary_markdown(stats))


def render_download_buttons(result: ComparisonResult) -> None:
    """Excel (.xlsx), CSV ve bağımsız HTML dışa aktarım düğmelerini render eder."""
    import streamlit as st

    from src.reporting.exporter import export_to_csv, export_to_excel, export_to_html

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "Excel indir (.xlsx)",
            data=export_to_excel(result),
            file_name="mevzuat_karsilastirma.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="mk_download_excel",
        )
    with col2:
        st.download_button(
            "CSV indir",
            data=export_to_csv(result),
            file_name="mevzuat_karsilastirma.csv",
            mime="text/csv",
            key="mk_download_csv",
        )
    with col3:
        st.download_button(
            "HTML rapor indir",
            data=export_to_html(result),
            file_name="mevzuat_karsilastirma.html",
            mime="text/html",
            key="mk_download_html",
        )
