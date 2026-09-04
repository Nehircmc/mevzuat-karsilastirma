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
    with st.spinner("Belgeler karşılaştırılıyor..."):
        try:
            result = components.compare_documents(
                old_file.getvalue(),
                old_file.name,
                new_file.getvalue(),
                new_file.name,
                use_embedder=use_embedder,
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

    components.render_metric_cards(result)
    components.render_executive_summary(result)

    st.divider()
    components.render_download_buttons(result)
    st.divider()

    selected_types = components.render_change_type_filter()

    st.divider()

    visible_rows = [row for row in result.rows if row.classified.change_type in selected_types]
    if not visible_rows:
        st.warning("Seçili filtrelerle eşleşen madde yok.")
    for row in visible_rows:
        components.render_side_by_side(row)
        st.divider()
