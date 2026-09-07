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
    "render_version_metadata_widgets",
    "check_chronological_order",
    "render_comparison_direction",
    "render_metric_cards",
    "render_section_breakdown",
    "build_pdf_source_payload",
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


def render_version_metadata_widgets() -> tuple[dict, dict]:
    """
    Mimari Ek 1 (F1/F2): her belge için OPSİYONEL sürüm etiketi + yayım/
    yürürlük tarihi toplar. Bir `st.expander` içinde, VARSAYILAN kapalı --
    NEDEN: bu alanların HİÇBİRİ zorunlu değildir (bkz. check_chronological_
    order NEDEN notu), bu yüzden basit "iki dosya yükle, sonucu gör" akışı
    görsel olarak DEĞİŞMEZ; isteyen kullanıcı genişletip doldurur.

    Boş bırakılan bir metin alanı None döner (boş string DEĞİL) ki
    src/temporal.py::belge_gorunen_adi'nin kademeli düşüşü doğru çalışsın
    (boş string "" version_label OLARAK sayılmamalı).
    """
    import streamlit as st

    with st.expander("Sürüm ve tarih bilgisi (opsiyonel)"):
        st.caption(
            "Buraya girilen tarihler, hangi belgenin daha eski olduğunu "
            "doğrulamak için kullanılır -- boş bırakılırsa aşağıdaki "
            "yükleme sırası (Eski belge / Yeni belge) esas alınır."
        )
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Eski belge**")
            old_label = st.text_input(
                "Sürüm etiketi", key="mk_old_version_label", placeholder="örn. 2019 sürümü"
            )
            old_pub = st.date_input("Yayım tarihi", value=None, key="mk_old_publication_date")
            old_eff = st.date_input("Yürürlük tarihi", value=None, key="mk_old_effective_date")
        with col2:
            st.markdown("**Yeni belge**")
            new_label = st.text_input(
                "Sürüm etiketi", key="mk_new_version_label", placeholder="örn. 2023 sürümü"
            )
            new_pub = st.date_input("Yayım tarihi", value=None, key="mk_new_publication_date")
            new_eff = st.date_input("Yürürlük tarihi", value=None, key="mk_new_effective_date")

    old_meta_input = {
        "version_label": old_label or None,
        "publication_date": old_pub,
        "effective_date": old_eff,
    }
    new_meta_input = {
        "version_label": new_label or None,
        "publication_date": new_pub,
        "effective_date": new_eff,
    }
    return old_meta_input, new_meta_input


def check_chronological_order(
    old_filename: str,
    new_filename: str,
    old_meta_input: dict,
    new_meta_input: dict,
) -> tuple[bool, str | None]:
    """
    F2'nin onay mekanizmasını UI akışına bağlar: kullanıcı tarih girmişse
    VE bu tarihler yükleme sırasıyla (Eski belge = slot A) ÇELİŞİYORSA --
    ya da kendi aralarında (yayım/yürürlük) çelişiyorsa -- analiz
    BAŞLAMADAN önce açık bir onay istenmesi GEREKTİĞİNİ bildirir (bkz.
    src/temporal.py::determine_chronological_order NEDEN notu: "sessiz
    varsayımın en pahalı olduğu yer burası").

    Döner: (sürtünmesiz_devam_edilebilir, uyarı_metni). Hiç tarih
    girilmemişse ya da girilen tarihler yükleme sırasıyla TUTARLIYSA ilk
    eleman True, ikincisi None'dır -- bu durumda app.py HİÇBİR ek adım
    eklemez (mevcut basit akış BOZULMAZ).
    """
    from src.models import DocumentMeta
    from src.temporal import OrderConfidence, determine_chronological_order

    old_probe = DocumentMeta(
        doc_id="eski",
        source_path=old_filename,
        file_type="pdf",
        slot="A",
        publication_date=old_meta_input["publication_date"],
        effective_date=old_meta_input["effective_date"],
    )
    new_probe = DocumentMeta(
        doc_id="yeni",
        source_path=new_filename,
        file_type="pdf",
        slot="B",
        publication_date=new_meta_input["publication_date"],
        effective_date=new_meta_input["effective_date"],
    )
    order = determine_chronological_order(old_probe, new_probe)

    if order.confidence == OrderConfidence.CONFLICTING:
        return False, order.warning
    if (
        order.confidence in (OrderConfidence.EFFECTIVE_DATE, OrderConfidence.PUBLICATION_DATE)
        and order.older is not None
        and order.older.doc_id != "eski"
    ):
        return False, (
            "Girdiğiniz tarihlere göre 'Eski belge' olarak yüklediğiniz dosya "
            "aslında DAHA YENİ görünüyor (karşılaştırma yönü ters dönebilir). "
            "Lütfen tarihleri ya da yükleme sırasını kontrol edin."
        )
    return True, None


def render_comparison_direction(result: ComparisonResult) -> None:
    """
    F4: karşılaştırma yönünü, cümle içine gömülmeden, AYRI ve AÇIK biçimde
    belirtir. F3'ün TEK görünen ad fonksiyonunu (belge_gorunen_adi) kullanır
    ki başka hiçbir yerde farklı bir isimlendirme oluşmasın (bkz.
    src/temporal.py NEDEN notu).
    """
    import streamlit as st

    from src.temporal import belge_gorunen_adi

    eski_ad = belge_gorunen_adi(result.old_meta)
    yeni_ad = belge_gorunen_adi(result.new_meta)
    st.caption(f"Karşılaştırma yönü: {eski_ad} → {yeni_ad}")


def render_metric_cards(result: ComparisonResult) -> None:
    """
    İki AYRI grupta metrik kartları render eder: İÇERİK DURUMU (4 kart --
    Değişmedi/Değişti/Yeni Eklendi/Kaldırıldı) ve YAPISAL DEĞİŞİKLİKLER (2
    kart -- Numarası Değişti/Bölümü Değişti).

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


def build_pdf_source_payload(file_bytes: bytes, file_type: str, *, link_count: int) -> str | None:
    """
    Kullanıcının KENDİ yüklediği bir PDF'in baytlarını base64'e çevirir --
    bkz. render_source_link (bu payload'ın tarayıcıda `blob:` URL'e
    çevrilerek `#page=N` ile ilgili sayfada nasıl açıldığı).

    NEDEN `blob:` URL (eskiden `data:` URI denendi, bkz. GEÇMİŞ NOT):
    Chrome'un yerleşik PDF görüntüleyicisi `#page=N` sayfa fragment'ını
    `data:application/pdf;base64,...` URI'leri için GÜVENİLİR biçimde
    UYGULAMAZ (kullanıcı geri bildirimi: link açılıyor ama ilgili
    sayfaya ULAŞILMIYOR) -- `blob:` URL'ler ise normal kaynak yükleme
    hattından geçtiği için PDF görüntüleyici URL'nin fragment'ını DOĞRU
    okur. `blob:` bir URL'in oluşturulması `URL.createObjectURL()`
    çağrısı GEREKTİRİR -- bu SADECE JavaScript'te yapılabilir, bu yüzden
    bu fonksiyon artık HAZIR bir URL değil, render_source_link'in
    onclick JavaScript'ine gömdüğü HAM base64 payload'ı döndürür.

    NEDEN sunucu tarafında bir statik dosya/URL YERİNE (base64 payload'ı
    `blob:`'a client-side çevirmek YERİNE): Streamlit'in statik dosya
    sunumu (enableStaticServing) kimlik doğrulaması YAPMAZ -- bir
    kullanıcının yüklediği (gizli olabilecek bir mevzuat taslağı gibi)
    belgeyi bir URL üzerinden erişilebilir kılmak, o URL'yi bilen/tahmin
    eden BAŞKA bir kullanıcıya SIZDIRIRDI. Bu payload SADECE bu tarayıcı
    sekmesinin kendi belleğinde yaşar -- sunucuda YENİ bir erişim yüzeyi
    AÇILMAZ, hiçbir dosya diske YAZILMAZ; tam olarak bu session'ın zaten
    bellekte tuttuğu baytlar, aynı session'a geri sunulur.

    None döner (çağıran taraf bu durumda SADECE düz "Sayfa N" metnini
    gösterir, ÖZELLİK ZORLA uygulanmaz -- bkz. render_source_link):
    - `file_type` "pdf" DEĞİLSE (DOCX akış tabanlıdır, sayfa/PDF
      görüntüleme kavramı YOKTUR, bkz. models.py::TextUnit NEDEN notu);
    - baytlar GERÇEKTEN bir PDF DEĞİLSE ("%PDF" imzasıyla BAŞLAMIYORSA --
      dosya adı UZANTISINA güvenmeyen, savunma amaçlı bir ikinci kontrol);
    - `len(file_bytes) * link_count`, SOURCE_LINK_MAX_TOTAL_BYTES'i
      AŞIYORSA (bkz. config.py NEDEN notu -- bu payload HER satırda
      TEKRARLANDIĞI için toplam boyut satır sayısıyla ÇARPILARAK büyür).
    """
    import base64

    if file_type != "pdf":
        return None
    if not file_bytes.startswith(b"%PDF"):
        return None
    if link_count <= 0 or len(file_bytes) * link_count > SOURCE_LINK_MAX_TOTAL_BYTES:
        return None
    return base64.b64encode(file_bytes).decode("ascii")


def render_source_link(section: Section | None, pdf_base64: str | None) -> tuple[str, bool]:
    """
    Bir Section'ın kaynak satırının HTML'ini üretir -- "mümkünse" ilkesi
    (bkz. build_pdf_source_payload NEDEN notu) ÜÇ kademeli. Döndürülen
    `(html, needs_iframe)` çiftindeki `needs_iframe`, ÇAĞIRANA (bkz.
    render_side_by_side) bu html'in `st.markdown` YERİNE `st.iframe` ile
    render edilmesi GEREKTİĞİNİ söyler:

    1. `pdf_base64` VARSA VE sayfa numarası biliniyorsa: `(html, True)` --
       html KENDİ KENDİNE YETEN bir mini belgedir (tıklanabilir bağlantı
       + `<script>`), SADECE bir `<iframe>` İÇİNDE (`st.iframe`) ÇALIŞIR
       (bkz. aşağıdaki NEDEN notu).
    2. `pdf_base64` YOKSA (DOCX, PDF-olmayan bayt, veya boyut bütçesi
       aşıldıysa) AMA sayfa numarası biliniyorsa: `(html, False)` -- düz
       "Sayfa N" metni, `st.markdown` ile render edilir.
    3. Sayfa numarası da BİLİNMİYORSA (DOCX'te her zaman, ya da PDF'te
       provenance eksikse): `("", False)` -- hiçbir şey render EDİLMEZ,
       olmayan bir bilgi UYDURULMAZ.

    NEDEN `st.iframe` GEREKLİ (`st.markdown` YETMEZ -- TARAYICIDA TEST
    EDİLEREK doğrulandı): Streamlit'in `st.markdown(unsafe_allow_
    html=True)` çıktısı React TARAFINDAN YENİDEN YORUMLANIR -- bir
    `onclick="..."` HTML özniteliği React'e STRING olarak ulaşır, React
    ise bir olay işleyicisinin (`onClick`) bir FONKSİYON olmasını ZORUNLU
    kılar ve string değer verildiğinde ÇALIŞMAZ, konsola "Minified React
    error #231" basar (ilk denemede BÖYLE BAŞARISIZ OLDU -- link
    açılıyordu ama tıklama HİÇ İŞLEMİYORDU). Aynı nedenle (React'in
    HTML'i ayrıştırıp KENDİ ağacına çevirmesi) `<script>` etiketleri de
    ÇALIŞMAZ. `st.iframe` İSE (ham bir HTML string verildiğinde) içeriği
    BAĞIMSIZ bir `<iframe>`'e yazar -- React'İN HİÇ KARIŞMADIĞI,
    tarayıcının HTML'i sıradan biçimde ayrıştırıp `<script>`'i GERÇEKTEN
    ÇALIŞTIRDIĞI bir belgedir (eski `st.components.v1.html` de aynı işi
    görürdü ama Streamlit bunu `st.iframe` lehine KULLANIMDAN
    KALDIRDI).

    NEDEN `blob:` URL (`data:` URI DEĞİL -- İLK sürüm `data:` kullanıyordu):
    Chrome'un yerleşik PDF görüntüleyicisi `#page=N` sayfa fragment'ını
    `data:application/pdf;base64,...` URI'leri için GÜVENİLİR biçimde
    UYGULAMAZ (kullanıcı geri bildirimi: link açılıyor ama ilgili
    sayfaya ULAŞILMIYOR) -- `blob:` URL'ler normal kaynak yükleme
    hattından geçtiği için fragment'ı DOĞRU okur (TARAYICIDA TEST
    EDİLEREK doğrulandı: açılan sekmenin URL'i `blob:...#page=N` olarak
    GÖRÜLDÜ). `blob:` bir URL'in oluşturulması `URL.createObjectURL()`
    GEREKTİRİR -- bu SADECE JavaScript'te yapılabilir, bu yüzden
    GERÇEKTEN ÇALIŞAN bir `<script>`'e ihtiyaç vardır (yukarıdaki NEDEN
    notu).

    NEDEN base64 payload'ı DOĞRUDAN bir JS string literaline gömülüyor
    (kaçırma/escape İHTİYACI OLMADAN): base64 alfabesi
    (`A-Za-z0-9+/=`) `"`, `'`, `<`, `>` KARAKTERLERİNİ HİÇ İÇERMEZ.

    NEDEN Section'ın İLK unit'inin sayfa numarası: bir madde sayfa
    sınırında bölünmüşse (bkz. models.py::Section NEDEN notu) "kaynağa
    git" sorusunun doğal cevabı, maddenin BAŞLADIĞI sayfadır.
    """
    if section is None:
        return "", False
    sayfa_no = next((u.page_no for u in section.units if u.page_no is not None), None)
    if sayfa_no is None:
        return "", False
    if pdf_base64:
        html = (
            "<div style=\"font-family:-apple-system,'Segoe UI',Roboto,Helvetica,"
            "Arial,sans-serif;font-size:13px;\">"
            f'<a href="#" id="mk-src-link" style="color:#4EA1FF;">'
            f"Belgede görüntüle · Sayfa {sayfa_no}</a></div>"
            '<script>document.getElementById("mk-src-link")'
            ".addEventListener('click', function(e) {"
            "e.preventDefault();"
            f"var bin=atob('{pdf_base64}');"
            "var arr=new Uint8Array(bin.length);"
            "for(var i=0;i<bin.length;i++){arr[i]=bin.charCodeAt(i);}"
            "var blob=new Blob([arr],{type:'application/pdf'});"
            "var url=URL.createObjectURL(blob);"
            f"window.open(url+'#page={sayfa_no}','_blank','noopener,noreferrer');"
            "});</script>"
        )
        return html, True
    return f'<span class="mk-source-page">Sayfa {sayfa_no}</span>', False


def render_side_by_side(
    row: ComparisonRow,
    *,
    old_pdf_base64: str | None = None,
    new_pdf_base64: str | None = None,
) -> None:
    """
    Tek bir ComparisonRow'u (başlık + rozet + yan yana renkli metin +
    varsa kaynak bağlantısı/sayfası) render eder.

    NEDEN old_pdf_base64/new_pdf_base64 PARAMETRE (her satırda YENİDEN
    HESAPLANMIYOR): build_pdf_source_payload her çağrıldığında TÜM PDF'i
    base64'e çevirir -- bu, app.py'de SATIR BAŞINA DEĞİL, belge başına
    BİR KEZ çağrılır, sonuç (aynı base64 payload) TÜM satırlara
    PAYLAŞILARAK geçirilir.
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
    old_source_html, old_needs_iframe = render_source_link(c.old, old_pdf_base64)
    new_source_html, new_needs_iframe = render_source_link(c.new, new_pdf_base64)

    empty_marker = '<span class="mk-empty-side">(karşılığı yok)</span>'
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="mk-column">{old_html or empty_marker}</div>', unsafe_allow_html=True)
        if old_source_html:
            if old_needs_iframe:
                st.iframe(old_source_html, height=26)
            else:
                st.markdown(old_source_html, unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="mk-column">{new_html or empty_marker}</div>', unsafe_allow_html=True)
        if new_source_html:
            if new_needs_iframe:
                st.iframe(new_source_html, height=26)
            else:
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
