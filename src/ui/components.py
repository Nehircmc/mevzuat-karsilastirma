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

from collections.abc import Callable

from src.analysis.pipeline import ComparisonResult, ComparisonRow, compare_documents
from src.config import CHANGE_TYPE_LABELS_TR, SOURCE_LINK_MAX_TOTAL_BYTES
from src.models import ChangeType, Section

__all__ = [
    "ComparisonResult",
    "ComparisonRow",
    "compare_documents",
    "render_upload_widgets",
    "render_metric_cards",
    "render_section_breakdown",
    "build_pdf_source_uri",
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
    """
    İki AYRI grupta metrik kartları render eder: İÇERİK DURUMU (4 kart --
    Değişmedi/Değişti/Yeni Eklendi/Kaldırıldı) ve YAPISAL DEĞİŞİKLİKLER (2
    kart -- Numarası Değişti/Yeri Değişti).

    NEDEN İKİ AYRI grup (TEK bir satırda 6 kart DEĞİL): bu iki boyut
    BAĞIMSIZDIR -- aynı madde HEM bir içerik durumuna HEM bir yapısal
    bayrağa katkıda bulunabilir (bkz. classifier.py NEDEN notu). Hepsini
    TEK bir satırda göstermek, "6 kartın toplamı = toplam madde sayısı"
    yanlış izlenimini verirdi; oysa içerik durumu TEK BAŞINA zaten toplam
    madde sayısına eşittir (bkz. ComparisonResult.counts() NEDEN notu),
    yapısal sayılar ise BUNA EK, bağımsız bir bilgidir.
    """
    import streamlit as st

    counts = result.counts()
    st.markdown("##### İçerik Durumu")
    cols = st.columns(len(ChangeType))
    for col, change_type in zip(cols, ChangeType):
        with col:
            st.metric(CHANGE_TYPE_LABELS_TR[change_type.value], counts[change_type])

    structural = result.structural_counts()
    st.markdown("##### Yapısal Değişiklikler")
    cols2 = st.columns(2)
    with cols2[0]:
        st.metric(CHANGE_TYPE_LABELS_TR["RENUMBERED"], structural["RENUMBERED"])
    with cols2[1]:
        st.metric(CHANGE_TYPE_LABELS_TR["MOVED"], structural["MOVED"])


def render_section_breakdown(result: ComparisonResult) -> Callable[[ComparisonRow], bool]:
    """
    Bölüm bazlı İÇERİK DURUMU dökümünü (bkz. metrics.build_section_breakdown)
    ve "en fazla değişiklik" öne çıkanını render eder; seçilen bölüme göre
    filtreleyen bir YÜKLEM (predicate) döndürür.

    NEDEN bir liste/DataFrame DEĞİL bir yüklem döndürülüyor:
    render_change_type_filter İLE AYNI desen -- app.py bu ikisini VE (AND)
    ile birleştirip görünür satırları belirler, "hangi satır hangi bölüme
    ait" kararı app.py'ye (orkestrasyon katmanı, Mimari İlke D) SIZMAZ.

    NEDEN "en fazla değişiklik" burada summary_builder.SummaryStats.
    en_cok_degisen_bolumler'DEN okunuyor, bu modülün KENDİ tablosundan
    (build_section_breakdown, SADECE içerik durumu) yeniden HESAPLANMIYOR:
    ikisi FARKLI tanımlar kullanır (en_cok_degisen_bolumler içerik VEYA
    yapısal HERHANGİ bir değişikliği sayar, bkz. summary_builder.py NEDEN
    notu) -- aynı panelde iki farklı "en çok değişen bölüm" sayısı
    göstermek KAFA KARIŞTIRICI olurdu; Yönetici Özeti'ndeki İLE AYNI,
    TEK bir tanım kullanılır.

    NEDEN st.selectbox (tıklanabilir tablo satırları DEĞİL): mevcut
    render_change_type_filter da AYNI şekilde bir seçim widget'ı (st.
    multiselect) + yüklem desenini kullanıyor -- tutarlı bir etkileşim
    biçimi, ve streamlit.testing.v1.AppTest ile DETERMİNİSTİK test
    edilebilir (bkz. tests/test_ui.py).
    """
    import streamlit as st

    from src.reporting.metrics import BOLUMSUZ_ETIKETI, build_section_breakdown
    from src.reporting.summary_builder import build_summary_stats

    st.markdown("##### Bölümlere Göre Değişiklikler")

    stats = build_summary_stats(result)
    if stats.en_cok_degisen_bolumler:
        sayi = stats.en_cok_degisen_bolumler[0][1]
        bolumler_metni = ", ".join(bolum for bolum, _ in stats.en_cok_degisen_bolumler)
        st.markdown(f"**En fazla değişiklik:** {bolumler_metni} ({sayi} madde)")

    breakdown = build_section_breakdown(result)
    st.dataframe(breakdown, hide_index=True, use_container_width=True)

    bolum_options = ["(Tümü)", *breakdown["Bölüm"].tolist()]
    selected = st.selectbox("Bölüme göre filtrele", bolum_options, key="mk_bolum_filter")

    def matches_bolum(row: ComparisonRow) -> bool:
        if selected == "(Tümü)":
            return True
        c = row.classified
        section = c.old or c.new
        bolum = " > ".join(section.heading_path[:-1]) or BOLUMSUZ_ETIKETI
        return bolum == selected

    return matches_bolum


def render_change_type_filter() -> Callable[[ComparisonRow], bool]:
    """
    İÇERİK durumu (4) + YAPISAL bayrak (2) etiketlerini TEK bir çok seçmeli
    filtrede sunar (görsel olarak Adım 7'deki filtreyle AYNI -- altı etiket,
    hepsi varsayılan seçili); bir SATIRIN gösterilip gösterilmeyeceğine
    karar veren bir YÜKLEM (predicate) fonksiyonu döndürür.

    NEDEN bir liste DEĞİL bir yüklem döndürülüyor: içerik durumu ile
    yapısal bayraklar BAĞIMSIZ boyutlar olduğu için bir satır AYNI ANDA
    hem seçili bir içerik etiketine hem seçili bir yapısal etikete
    uyabilir (VEYA mantığı) -- örn. "Değişti" VE "Numarası Değişti" ikisi
    de seçiliyse, HEM içeriği HEM numarası değişen bir satır (bkz.
    ground_truth.json/birim_sorumlulukları) gösterilmeli; bu iki AYRI
    listeyi (`row.change_type in secili_icerikler`) satır satır VE/VEYA
    ile birleştirmek app.py'ye TAŞINSAYDI orkestrasyon katmanına iş
    mantığı sızardı (Mimari İlke D) -- bu yüzden karar burada, tek bir
    fonksiyonda kapatılıyor.
    """
    import streamlit as st

    content_options: list[tuple[ChangeType, str]] = [(ct, CHANGE_TYPE_LABELS_TR[ct.value]) for ct in ChangeType]
    structural_options: list[tuple[str, str]] = [
        ("RENUMBERED", CHANGE_TYPE_LABELS_TR["RENUMBERED"]),
        ("MOVED", CHANGE_TYPE_LABELS_TR["MOVED"]),
    ]
    label_by_key: dict[ChangeType | str, str] = dict(content_options + structural_options)
    key_by_label = {label: key for key, label in label_by_key.items()}

    selected_labels = st.multiselect(
        "Değişim türüne göre filtrele",
        options=list(label_by_key.values()),
        default=list(label_by_key.values()),
        key="mk_change_type_filter",
    )
    selected_keys = {key_by_label[label] for label in selected_labels}

    def matches_filter(row: ComparisonRow) -> bool:
        c = row.classified
        if c.change_type in selected_keys:
            return True
        if c.numarasi_degisti and "RENUMBERED" in selected_keys:
            return True
        if c.yeri_degisti and "MOVED" in selected_keys:
            return True
        return False

    return matches_filter


def build_pdf_source_uri(file_bytes: bytes, file_type: str, *, link_count: int) -> str | None:
    """
    Kullanıcının KENDİ yüklediği bir PDF'in baytlarını, tarayıcıda
    doğrudan (yeni sekmede, `#page=N` ile ilgili sayfada) açılabilecek
    bir `data:` URI'ye çevirir -- bkz. render_source_link (bu URI'nin her
    satırda nasıl kullanıldığı).

    NEDEN sunucu tarafında bir statik dosya/URL YERİNE `data:` URI:
    Streamlit'in statik dosya sunumu (enableStaticServing) kimlik
    doğrulaması YAPMAZ -- bir kullanıcının yüklediği (gizli olabilecek
    bir mevzuat taslağı gibi) belgeyi bir URL üzerinden erişilebilir
    kılmak, o URL'yi bilen/tahmin eden BAŞKA bir kullanıcıya SIZDIRIRDI.
    `data:` URI ise SADECE bu tarayıcı sekmesinin kendi DOM'unda yaşar --
    sunucuda YENİ bir erişim yüzeyi AÇILMAZ, hiçbir dosya diske YAZILMAZ;
    tam olarak bu session'ın zaten bellekte tuttuğu baytlar, aynı
    session'a geri sunulur.

    None döner (çağıran taraf bu durumda SADECE düz "Sayfa N" metnini
    gösterir, ÖZELLİK ZORLA uygulanmaz -- bkz. render_source_link):
    - `file_type` "pdf" DEĞİLSE (DOCX akış tabanlıdır, sayfa/PDF
      görüntüleme kavramı YOKTUR, bkz. models.py::TextUnit NEDEN notu);
    - baytlar GERÇEKTEN bir PDF DEĞİLSE ("%PDF" imzasıyla BAŞLAMIYORSA --
      dosya adı UZANTISINA güvenmeyen, savunma amaçlı bir ikinci kontrol);
    - `len(file_bytes) * link_count`, SOURCE_LINK_MAX_TOTAL_BYTES'i
      AŞIYORSA (bkz. config.py NEDEN notu -- bu URI HER satırda
      TEKRARLANDIĞI için toplam boyut satır sayısıyla ÇARPILARAK büyür).
    """
    import base64

    if file_type != "pdf":
        return None
    if not file_bytes.startswith(b"%PDF"):
        return None
    if link_count <= 0 or len(file_bytes) * link_count > SOURCE_LINK_MAX_TOTAL_BYTES:
        return None
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return f"data:application/pdf;base64,{encoded}"


def render_source_link(section: Section | None, pdf_uri: str | None) -> str:
    """
    Bir Section'ın kaynak satırının HTML'ini üretir -- "mümkünse" ilkesi
    (bkz. build_pdf_source_uri NEDEN notu) ÜÇ kademeli:

    1. `pdf_uri` VARSA VE sayfa numarası biliniyorsa: tıklanabilir
       "Belgede görüntüle · Sayfa N" bağlantısı (yeni sekmede, ilgili
       sayfada açılır).
    2. `pdf_uri` YOKSA (DOCX, PDF-olmayan bayt, veya boyut bütçesi
       aşıldıysa) AMA sayfa numarası biliniyorsa: düz "Sayfa N" metni.
    3. Sayfa numarası da BİLİNMİYORSA (DOCX'te her zaman, ya da PDF'te
       provenance eksikse): boş string -- hiçbir şey render EDİLMEZ,
       olmayan bir bilgi UYDURULMAZ.

    NEDEN Section'ın İLK unit'inin sayfa numarası: bir madde sayfa
    sınırında bölünmüşse (bkz. models.py::Section NEDEN notu) "kaynağa
    git" sorusunun doğal cevabı, maddenin BAŞLADIĞI sayfadır.
    """
    if section is None:
        return ""
    sayfa_no = next((u.page_no for u in section.units if u.page_no is not None), None)
    if sayfa_no is None:
        return ""
    if pdf_uri:
        return (
            f'<a class="mk-source-link" href="{pdf_uri}#page={sayfa_no}" '
            f'target="_blank" rel="noopener noreferrer">Belgede görüntüle · Sayfa {sayfa_no}</a>'
        )
    return f'<span class="mk-source-page">Sayfa {sayfa_no}</span>'


def render_side_by_side(
    row: ComparisonRow,
    *,
    old_pdf_uri: str | None = None,
    new_pdf_uri: str | None = None,
) -> None:
    """
    Tek bir ComparisonRow'u (başlık + rozet + yan yana renkli metin +
    varsa kaynak bağlantısı/sayfası) render eder.

    NEDEN old_pdf_uri/new_pdf_uri PARAMETRE (her satırda YENİDEN
    HESAPLANMIYOR): build_pdf_source_uri her çağrıldığında TÜM PDF'i
    base64'e çevirir -- bu, app.py'de SATIR BAŞINA DEĞİL, belge başına
    BİR KEZ çağrılır, sonuç (aynı `data:` URI) TÜM satırlara PAYLAŞILARAK
    geçirilir.
    """
    import streamlit as st

    from src.reporting.html_renderer import render_row_body_html, render_row_header_html

    c = row.classified
    header_html = render_row_header_html(
        c.old, c.new, c.change_type,
        numarasi_degisti=c.numarasi_degisti,
        yeri_degisti=c.yeri_degisti,
    )
    st.markdown(header_html, unsafe_allow_html=True)

    old_html, new_html = render_row_body_html(c.old, c.new, c.change_type, row.section_diff)
    old_source_html = render_source_link(c.old, old_pdf_uri)
    new_source_html = render_source_link(c.new, new_pdf_uri)

    empty_marker = '<span class="mk-empty-side">(karşılığı yok)</span>'
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="mk-column">{old_html or empty_marker}</div>', unsafe_allow_html=True)
        if old_source_html:
            st.markdown(old_source_html, unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="mk-column">{new_html or empty_marker}</div>', unsafe_allow_html=True)
        if new_source_html:
            st.markdown(new_source_html, unsafe_allow_html=True)


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
