"""
Streamlit giriş noktası.

NEDEN bu dosyada İŞ MANTIĞI YOK (Mimari İlke D, bkz.
src/ingestion/base.py::DocumentLoader NEDEN notu): app.py SADECE src/
modüllerini (src/ui/components.py, src/ui/styles.py) orkestre eder --
ingestion/parsing/matching/diffing/sınıflandırma ayrıntılarını BİLMEZ.
Belge okuma, eşleştirme, sınıflandırma ve diff'in TAMAMI
components.compare_documents() içinde; bu dosyada sadece o fonksiyonun
girdisi (yüklenen dosyalar) toplanır ve çıktısı (ComparisonResult) render
edilir.
"""

from __future__ import annotations

import streamlit as st

from src.ingestion.base import CorruptDocumentError, NoTextLayerError
from src.ui import components, styles

st.set_page_config(page_title="Mevzuat Karşılaştırma", layout="wide")
styles.inject()

st.title("Mevzuat Karşılaştırma")
st.caption(
    "İki mevzuat/stratejik plan/politika belgesini (PDF/DOCX) karşılaştırın; "
    "ortak, değişen, yeni eklenen ve kaldırılan maddeleri kaynak göstererek görün."
)

old_file, new_file = components.render_upload_widgets()
old_meta_input, new_meta_input = components.render_version_metadata_widgets()

use_embedder = st.checkbox(
    "Gelişmiş (embedding tabanlı) eşleştirmeyi etkinleştir",
    value=False,
    help=(
        "Sadece numarası VE başlığı birlikte değişen maddeler için gerekir "
        "(kural tabanlı eşleştirme bunları bulamaz); ilk kullanımda bir "
        "dil modeli indirilir ve karşılaştırma daha uzun sürer."
    ),
    key="mk_use_embedder",
)

if old_file is None or new_file is None:
    st.info("Karşılaştırmaya başlamak için her iki belgeyi de yükleyin.")
else:
    # NEDEN burada, spinner'dan ÖNCE: F2'nin onay mekanizması analiz
    # BAŞLAMADAN devreye girmeli -- tarihler çelişiyorsa/yükleme sırasıyla
    # UYUŞMUYORSA kullanıcı AÇIKÇA onaylamadan compare_documents HİÇ
    # ÇAĞRILMAZ (bkz. components.check_chronological_order NEDEN notu).
    proceed, order_warning = components.check_chronological_order(
        old_file.name, new_file.name, old_meta_input, new_meta_input
    )
    if not proceed:
        st.warning(order_warning)
        order_confirmed = st.checkbox(
            "Yükleme sırasını (Eski belge / Yeni belge) yine de bu şekilde "
            "kullanmak istediğimi onaylıyorum.",
            key="mk_order_override_confirm",
        )
        if not order_confirmed:
            st.stop()

    with st.spinner("Belgeler karşılaştırılıyor..."):
        try:
            result = components.compare_documents(
                old_file.getvalue(),
                old_file.name,
                new_file.getvalue(),
                new_file.name,
                use_embedder=use_embedder,
                old_version_label=old_meta_input["version_label"],
                old_publication_date=old_meta_input["publication_date"],
                old_effective_date=old_meta_input["effective_date"],
                new_version_label=new_meta_input["version_label"],
                new_publication_date=new_meta_input["publication_date"],
                new_effective_date=new_meta_input["effective_date"],
            )
        except NoTextLayerError as exc:
            st.error(f"Belge okunamadı: {exc}")
            st.stop()
        except CorruptDocumentError as exc:
            st.error(f"Belge bozuk veya geçersiz: {exc}")
            st.stop()
        except ValueError as exc:
            st.error(f"Belge işlenemedi: {exc}")
            st.stop()
        except Exception as exc:
            # NEDEN son bir genel yakalama: kullanıcıya ASLA çıplak bir
            # Python traceback'i gösterilmemeli (hem korkutucu hem de
            # sunucunun iç dosya yollarını/kütüphane sürümlerini sızdırır)
            # -- öngörülemeyen (yukarıdaki üç türün dışında kalan) her hata
            # burada tutarlı, anlaşılır bir mesaja dönüştürülür.
            st.error(f"Beklenmeyen bir hata oluştu, belgeler karşılaştırılamadı: {exc}")
            st.stop()

    if not result.rows:
        st.warning(
            "Belgelerde tanınabilir bir MADDE/GEÇİCİ MADDE yapısı bulunamadı. "
            "Belgenin standart madde numaralandırması ('MADDE 1', 'MADDE 2' vb.) "
            "içerdiğinden emin olun."
        )
        st.stop()

    components.render_comparison_direction(result)
    components.render_metric_cards(result)
    row_matches_bolum_filter = components.render_section_breakdown(result)
    components.render_executive_summary(result)

    st.divider()
    components.render_download_buttons(result)
    st.divider()

    row_matches_type_filter = components.render_change_type_filter()

    st.divider()

    visible_rows = [
        row for row in result.rows if row_matches_type_filter(row) and row_matches_bolum_filter(row)
    ]
    if not visible_rows:
        st.warning("Seçili filtrelerle eşleşen madde yok.")

    # NEDEN belge başına BİR KEZ (satır başına DEĞİL): build_pdf_source_payload
    # her çağrıldığında TÜM PDF'i base64'e çevirir -- aynı sonuç TÜM
    # satırlara PAYLAŞILARAK geçirilir (bkz. components.py::
    # render_side_by_side NEDEN notu).
    old_link_count = sum(1 for row in result.rows if row.classified.old is not None)
    new_link_count = sum(1 for row in result.rows if row.classified.new is not None)
    old_pdf_base64 = components.build_pdf_source_payload(
        old_file.getvalue(), result.old_meta.file_type, link_count=old_link_count
    )
    new_pdf_base64 = components.build_pdf_source_payload(
        new_file.getvalue(), result.new_meta.file_type, link_count=new_link_count
    )

    for row in visible_rows:
        components.render_side_by_side(row, old_pdf_base64=old_pdf_base64, new_pdf_base64=new_pdf_base64)
        st.divider()
