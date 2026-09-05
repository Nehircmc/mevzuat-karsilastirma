"""
Adım 7: karşılaştırma sonuçlarını Excel (.xlsx), CSV ve bağımsız (Streamlit'siz
de açılabilen) HTML dosyası olarak dışa aktarır.

NEDEN hepsi bytes DÖNDÜRÜR, dosyaya YAZMAZ: Streamlit'in st.download_button()'ı
bellek-içi bayt dizisi bekler (bkz. src/ui/components.py::render_download_
buttons) -- bu modül DİSKE bağımlı olmadan hem UI'dan hem testlerden
çağrılabilir kalır (Adım 6'daki compare_documents() ile AYNI gerekçe).
"""

from __future__ import annotations

from io import BytesIO

from src.analysis.pipeline import ComparisonResult
from src.reporting.html_renderer import render_row_body_html, render_row_header_html, render_summary_html
from src.reporting.metrics import build_detail_dataframe, build_structural_dataframe, build_summary_dataframe
from src.reporting.summary_builder import build_summary_stats

# NEDEN utf-8-sig (BOM'lu): Excel, BOM olmadan bir UTF-8 CSV'yi Türkçe
# karakterleri (ç, ş, ğ, ı, ö, ü) BOZUK gösterir -- BOM, Excel'e dosyanın
# UTF-8 olduğunu AÇIKÇA bildirir.
_CSV_ENCODING = "utf-8-sig"


def export_to_excel(result: ComparisonResult) -> bytes:
    """
    ÜÇ sayfalı bir Excel dosyası üretir: "Detay" (madde madde, her iki
    boyutu -- İÇERİK durumu + YAPISAL bayraklar -- sütun olarak taşır),
    "Özet" (İÇERİK durumu sayım+yüzde) ve "Yapısal" (Numarası/Yeri
    Değişti sayımı -- İÇERİK durumundan BAĞIMSIZ, bkz.
    build_structural_dataframe NEDEN notu).

    NEDEN "Detay" İLK sayfa VE AÇILIŞTA SEÇİLİ (eskiden "Özet" ilkti,
    kullanıcı geri bildirimi: "Excel indirince sadece oranlar
    gözüküyor"): "Özet" SADECE üç sütun (Değişim Türü, Sayı, Yüzde)
    içerir -- dosya açıldığında ilk (ve aktif) sekme bu olursa, kullanıcı
    asıl aradığı madde madde karşılaştırmanın (Detay sekmesi) VAR
    OLDUĞUNU fark etmeden dosyayı "sadece sayı/yüzde içeriyor" sanıp
    kapatabilir. Sekme SIRASI ile AÇILIŞTA GÖRÜNEN sekme kasıtlı olarak
    AYNI (Detay) yapılır -- biri diğerinden FARKLI olsaydı ("sekme
    sırasında ilk Özet ama açılışta Detay seçili" gibi) bu da kafa
    karıştırıcı olurdu.
    """
    import pandas as pd

    summary_df = build_summary_dataframe(result)
    structural_df = build_structural_dataframe(result)
    detail_df = build_detail_dataframe(result)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        detail_df.to_excel(writer, sheet_name="Detay", index=False)
        summary_df.to_excel(writer, sheet_name="Özet", index=False)
        structural_df.to_excel(writer, sheet_name="Yapısal", index=False)
        writer.book.active = writer.book.sheetnames.index("Detay")
    return buffer.getvalue()


def export_to_csv(result: ComparisonResult) -> bytes:
    """Detay tablosunu (madde madde) TEK bir CSV dosyası olarak üretir."""
    detail_df = build_detail_dataframe(result)
    return detail_df.to_csv(index=False).encode(_CSV_ENCODING)


def export_to_html(result: ComparisonResult) -> bytes:
    """
    Yönetici Özeti + TÜM maddelerin yan yana renkli karşılaştırmasını TEK
    BAŞINA (Streamlit çalıştırmadan, tarayıcıda doğrudan açılabilen) bir
    HTML dosyasına gömer.

    NEDEN CSS DOSYA İÇİNE GÖMÜLÜ (ayrı bir .css dosyasına link VERİLMİYOR):
    dışa aktarılan dosya kullanıcının bilgisayarında TEK BAŞINA taşınabilir
    olmalı -- yanında assets/styles.css'i de göndermeye gerek KALMADAN
    renkler doğru görünmeli.
    """
    from src.ui.styles import build_full_css

    stats = build_summary_stats(result)
    summary_html = render_summary_html(stats)

    row_blocks: list[str] = []
    empty_marker = '<span class="mk-empty-side">(karşılığı yok)</span>'
    for row in result.rows:
        c = row.classified
        header_html = render_row_header_html(
            c.old, c.new, c.change_type,
            numarasi_degisti=c.numarasi_degisti,
            yeri_degisti=c.yeri_degisti,
        )
        old_html, new_html = render_row_body_html(c.old, c.new, c.change_type, row.section_diff)
        row_blocks.append(
            f'<div class="mk-row">{header_html}'
            '<div class="mk-side-by-side">'
            f'<div class="mk-column">{old_html or empty_marker}</div>'
            f'<div class="mk-column">{new_html or empty_marker}</div>'
            "</div></div>"
        )

    css = build_full_css()
    body = summary_html + "\n" + "\n".join(row_blocks)
    html_doc = (
        "<!doctype html>\n"
        '<html lang="tr">\n<head>\n<meta charset="utf-8">\n'
        "<title>Mevzuat Karşılaştırma Raporu</title>\n"
        f"<style>\n{css}\n</style>\n</head>\n<body>\n"
        f'<div class="mk-standalone-page">\n{body}\n</div>\n'
        "</body>\n</html>\n"
    )
    return html_doc.encode("utf-8")
