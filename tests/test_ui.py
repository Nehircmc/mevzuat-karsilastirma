"""
src/ui/styles.py + src/ui/components.py + app.py (Adım 6) testleri.

Üç katman ayrı ayrı test edilir:
1) styles.py -- Streamlit'e bağımlı OLMAYAN saf CSS üretimi.
2) components.compare_documents() -- Streamlit'e bağımlı OLMAYAN saf
   orkestrasyon fonksiyonu, gerçek 2019/2023 örnek belgeleriyle
   ground_truth.json'a karşı objektif doğrulanır.
3) app.py -- streamlit.testing.v1.AppTest ile GERÇEK bir Streamlit çalıştırması
   (yükleme dahil) üzerinden uçtan uca duman (smoke) testi.
"""

from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from src.config import ASSETS_DIR, BASE_DIR, COLOR_PALETTE, SAMPLES_DIR, SOURCE_LINK_MAX_TOTAL_BYTES
from src.ingestion.base import CorruptDocumentError
from src.models import ChangeType, Section, TextUnit
from src.ui import styles
from src.ui.components import ComparisonResult, build_pdf_source_payload, compare_documents, render_source_link

_APP_PATH = BASE_DIR / "app.py"

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)

# NEDEN ground_truth.json'daki eski (6 değerli) "change_type" alanı BURADA
# İKİYE AYRIŞTIRILARAK yorumlanır (dosya DEĞİŞTİRİLMEDİ) -- bkz.
# tests/test_differ.py + tests/test_reporting.py'deki AYNI gerekçe:
# "RENUMBERED"/"MOVED" etiketi "içerik AYNI, sadece numara/yer FARKLI"
# anlamına gelir. numarasi_degisti DOĞRUDAN madde_no_2019 != madde_no_2023
# karşılaştırmasından türetilir (classifier.py::is_renumbered ile AYNI
# mantık) -- SADECE "RENUMBERED" etiketli maddelere bakmak,
# birim_sorumluluklari ("MODIFIED" etiketli ama numarası DA değişmiş) gibi
# satırları KAÇIRIRDI.
_EXPECTED_COUNTS: dict[ChangeType, int] = dict.fromkeys(ChangeType, 0)
_EXPECTED_STRUCTURAL_COUNTS = {"RENUMBERED": 0, "MOVED": 0}
for _m in _GROUND_TRUTH["maddeler"]:
    _content_type = (
        ChangeType.IDENTICAL
        if _m["change_type"] in ("IDENTICAL", "RENUMBERED", "MOVED")
        else ChangeType(_m["change_type"])
    )
    _EXPECTED_COUNTS[_content_type] += 1
    _no19, _no23 = _m["madde_no_2019"], _m["madde_no_2023"]
    if _no19 is not None and _no23 is not None and _no19 != _no23:
        _EXPECTED_STRUCTURAL_COUNTS["RENUMBERED"] += 1


class TestStylesCSSUretimi:
    def test_generate_color_css_her_change_type_icin_kural_icerir(self):
        css = styles.generate_color_css()
        for change_type in ChangeType:
            css_key = change_type.value.lower()
            assert f".mk-diff-{css_key}" in css
            assert f".mk-badge-{css_key}" in css

    def test_generate_color_css_dogru_renk_degerlerini_kullanir(self):
        css = styles.generate_color_css()
        for colors in COLOR_PALETTE.values():
            assert colors["text"] in css
            assert colors["background"] in css

    def test_load_static_css_dosyayi_okur(self):
        assert (ASSETS_DIR / "styles.css").exists(), "assets/styles.css eksik"
        content = styles.load_static_css()
        assert content.strip() != ""

    def test_build_full_css_ikisini_de_icerir(self):
        full = styles.build_full_css()
        assert styles.load_static_css().strip() in full
        assert styles.generate_color_css().strip() in full

    def test_static_css_renk_kodu_icermez(self):
        # NEDEN: renkler SADECE generate_color_css()'ten (config.py'den
        # üretilir) gelmeli -- statik dosyada elle yazılmış bir hex renk,
        # config.py'deki bir değişiklikle sessizce çelişebilecek İKİNCİ bir
        # kaynak anlamına gelir.
        content = styles.load_static_css()
        for colors in COLOR_PALETTE.values():
            assert colors["text"] not in content
            assert colors["background"] not in content


class TestCompareDocumentsGercekOrnekBelgelerle:
    """
    compare_documents() Streamlit'siz, doğrudan çağrılabilen SAF bir
    fonksiyondur -- gerçek 2019/2023 örnek belgeleriyle ground_truth.json'a
    karşı objektif doğrulanır.
    """

    @pytest.mark.parametrize(
        "dosya_2019,dosya_2023",
        [
            ("yonetmelik_2019.pdf", "yonetmelik_2023.pdf"),
            ("yonetmelik_2019.docx", "yonetmelik_2023.docx"),
        ],
    )
    def test_degisim_turu_sayimlari_ground_truth_ile_esler(self, dosya_2019, dosya_2023):
        old_bytes = (SAMPLES_DIR / dosya_2019).read_bytes()
        new_bytes = (SAMPLES_DIR / dosya_2023).read_bytes()

        result = compare_documents(old_bytes, dosya_2019, new_bytes, dosya_2023)

        assert isinstance(result, ComparisonResult)
        counts = result.counts()
        for change_type in ChangeType:
            assert counts[change_type] == _EXPECTED_COUNTS.get(change_type, 0), (
                f"{change_type}: beklenen {_EXPECTED_COUNTS.get(change_type, 0)}, bulunan {counts[change_type]}"
            )
        assert sum(counts.values()) == len(_GROUND_TRUTH["maddeler"])

    def test_eslesen_satirlarda_section_diff_dolu_acikta_kalanlarda_none(self):
        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()

        result = compare_documents(old_bytes, "yonetmelik_2019.pdf", new_bytes, "yonetmelik_2023.pdf")

        for row in result.rows:
            has_both = row.classified.old is not None and row.classified.new is not None
            assert (row.section_diff is not None) == has_both

    def test_meta_dogru_atanir(self):
        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()

        result = compare_documents(old_bytes, "yonetmelik_2019.pdf", new_bytes, "yonetmelik_2023.pdf")

        assert result.old_meta.file_type == "pdf"
        assert result.new_meta.file_type == "pdf"

    def test_satirlar_belge_sirasina_gore_siralanir(self):
        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()

        result = compare_documents(old_bytes, "yonetmelik_2019.pdf", new_bytes, "yonetmelik_2023.pdf")

        order_keys = [
            r.classified.old.order_index if r.classified.old else r.classified.new.order_index
            for r in result.rows
        ]
        assert order_keys == sorted(order_keys)

    def test_desteklenmeyen_uzanti_hata_verir(self):
        with pytest.raises(ValueError):
            compare_documents(b"veri", "belge.txt", b"veri", "belge2.txt")

    def test_bozuk_pdf_corrupt_document_error_verir_ve_dosya_adini_gosterir(self):
        # NEDEN (Adım 8): _load_document, loader'ın GEÇİCİ dosya yolunu
        # (örn. /tmp/tmpXXXX.pdf) kullanıcının YÜKLEDİĞİ gerçek dosya adıyla
        # değiştirmeli -- hem daha anlaşılır hem sunucunun iç dosya
        # sistemini SIZDIRMAZ.
        with pytest.raises(CorruptDocumentError) as exc_info:
            compare_documents(
                b"bu gecerli bir PDF degil", "benim-yonetmeligim.pdf",
                b"onemli degil", "de-yuklenmeyecek.pdf",
            )
        assert str(exc_info.value) == (
            "'benim-yonetmeligim.pdf' bir PDF olarak açılamadı; "
            "dosya bozuk, boş ya da geçersiz olabilir."
        )


def _section_sayfa(sayfa_no: int | None, madde_no: int = 1) -> Section:
    unit = TextUnit(
        doc_id="t", page_no=sayfa_no, block_index=0, char_start=0, char_end=1,
        heading_path=(), text="x",
    )
    return Section(
        doc_id="t", heading_path=("MADDE 1",), section_type="MADDE",
        madde_no=madde_no, baslik="X", order_index=0, units=[unit],
    )


class TestBuildPdfSourcePayload:
    """
    build_pdf_source_payload -- "mümkünse" ilkesi (bkz. components.py
    NEDEN notu): PDF DEĞİLSE, gerçek bir PDF DEĞİLSE ya da toplam bayt
    bütçesi (dosya boyutu × satır sayısı) AŞILIRSA None döner, özellik
    ZORLA uygulanmaz.
    """

    _GERCEK_PDF_BYTES = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()

    def test_gecerli_pdf_base64_payload_uretir(self):
        import base64

        payload = build_pdf_source_payload(self._GERCEK_PDF_BYTES, "pdf", link_count=1)
        assert payload is not None
        assert base64.b64decode(payload) == self._GERCEK_PDF_BYTES

    def test_docx_icin_none_doner(self):
        # NEDEN: DOCX akış tabanlıdır, PDF görüntüleme kavramı YOKTUR
        # (bkz. models.py::TextUnit NEDEN notu).
        assert build_pdf_source_payload(self._GERCEK_PDF_BYTES, "docx", link_count=1) is None

    def test_gercek_pdf_olmayan_baytlar_icin_none_doner(self):
        # NEDEN: dosya adı ".pdf" ile bitse bile İÇERİK "%PDF" imzasıyla
        # BAŞLAMIYORSA (dosya adı uzantısına GÜVENMEYEN, savunma amaçlı
        # ikinci bir kontrol) None dönmeli.
        assert build_pdf_source_payload(b"bu bir PDF degil", "pdf", link_count=1) is None

    def test_link_count_sifirsa_none_doner(self):
        assert build_pdf_source_payload(self._GERCEK_PDF_BYTES, "pdf", link_count=0) is None

    def test_toplam_boyut_butceyi_asarsa_none_doner(self):
        # NEDEN: base64 payload HER satırda TEKRARLANIR (bkz. config.py::
        # SOURCE_LINK_MAX_TOTAL_BYTES NEDEN notu) -- dosya boyutu × satır
        # sayısı bütçeyi aşınca özellik ZORLA uygulanmaz, None döner.
        link_count = SOURCE_LINK_MAX_TOTAL_BYTES // len(self._GERCEK_PDF_BYTES) + 1
        assert build_pdf_source_payload(self._GERCEK_PDF_BYTES, "pdf", link_count=link_count) is None

    def test_butce_siniri_icindeyse_payload_uretilir(self):
        link_count = max(1, SOURCE_LINK_MAX_TOTAL_BYTES // len(self._GERCEK_PDF_BYTES) - 1)
        assert build_pdf_source_payload(self._GERCEK_PDF_BYTES, "pdf", link_count=link_count) is not None


class TestRenderSourceLink:
    """
    render_source_link -- bkz. components.py NEDEN notu: `data:` URI'lerin
    AKSİNE, `blob:` URL'ler Chrome'un PDF görüntüleyicisinde `#page=N`
    fragment'ını GÜVENİLİR uygular; bu yüzden payload bir `<script>`
    İÇİNE gömülür ve döndürülen `(html, needs_iframe)` çiftindeki
    `needs_iframe=True`, çağırana bu html'in `st.iframe` ile render
    edilmesi (React'in `<script>`'i ÇALIŞTIRMADIĞI `st.markdown` ile
    DEĞİL, bkz. NEDEN notu) gerektiğini söyler.
    """

    def test_pdf_base64_varsa_tiklanabilir_baglanti_uretir(self):
        section = _section_sayfa(8)
        html, needs_iframe = render_source_link(section, "QUFBQQ==")
        assert needs_iframe is True
        assert "Belgede görüntüle · Sayfa 8" in html
        # NEDEN bu JavaScript çağrıları BİRLİKTE ARANIYOR: `blob:` URL
        # ÜÇ adımda oluşturulur -- base64 çöz (atob), Blob'a sar, ObjectURL
        # üret -- HERHANGİ biri eksikse teknik ÇALIŞMAZ. addEventListener
        # KULLANILIYOR (bir onclick ÖZNİTELİĞİ DEĞİL) çünkü bu html bir
        # <script> içinde GERÇEKTEN ÇALIŞIYOR (bkz. NEDEN notu).
        assert "<script>" in html
        assert "addEventListener('click'" in html
        assert "atob('QUFBQQ==')" in html
        assert "new Blob(" in html
        assert "URL.createObjectURL(blob)" in html
        assert "#page=8'" in html
        assert "window.open(" in html

    def test_pdf_base64_yoksa_duz_sayfa_metni_uretir(self):
        section = _section_sayfa(8)
        html, needs_iframe = render_source_link(section, None)
        assert needs_iframe is False
        assert html == '<span class="mk-source-page">Sayfa 8</span>'
        assert "<a" not in html

    def test_sayfa_no_yoksa_bos_string(self):
        # NEDEN: DOCX'te page_no HER ZAMAN None'dır (bkz. models.py NEDEN
        # notu) -- olmayan bir sayfa bilgisi UYDURULMAMALI.
        section = _section_sayfa(None)
        assert render_source_link(section, "QUFBQQ==") == ("", False)

    def test_section_none_ise_bos_string(self):
        # NEDEN: REMOVED bir satırda new=None, ADDED bir satırda old=None --
        # olmayan taraf için hiçbir şey render EDİLMEMELİ.
        assert render_source_link(None, "QUFBQQ==") == ("", False)


class TestAppUctanUcaDumanTesti:
    """streamlit.testing.v1.AppTest ile app.py'nin GERÇEK bir çalıştırmasını simüle eder."""

    def test_baslangicta_hata_yok_ve_yukleme_alanlari_dogru_anahtarlarla_mevcut(self):
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        assert not at.exception
        assert at.title[0].value == "Mevzuat Karşılaştırma"
        uploader_keys = {u.key for u in at.get("file_uploader")}
        assert uploader_keys == {"mk_old_uploader", "mk_new_uploader"}
        assert at.get("checkbox")[0].key == "mk_use_embedder"
        assert any("her iki belgeyi de yükleyin" in i.value for i in at.get("info"))

    def test_iki_belge_yuklendiginde_metrikler_ground_truth_ile_esler(self):
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        assert not at.exception
        metric_by_label = {m.label: int(m.value) for m in at.get("metric")}
        from src.config import CHANGE_TYPE_LABELS_TR

        # NEDEN 4+2=6 metrik kartı bekleniyor: render_metric_cards İKİ AYRI
        # grup render eder -- İÇERİK durumu (4) ve YAPISAL değişiklikler (2),
        # bkz. components.py NEDEN notu.
        for change_type, expected in _EXPECTED_COUNTS.items():
            label = CHANGE_TYPE_LABELS_TR[change_type.value]
            assert metric_by_label[label] == expected, f"{label}: beklenen {expected}, bulunan {metric_by_label[label]}"
        for key, expected in _EXPECTED_STRUCTURAL_COUNTS.items():
            label = CHANGE_TYPE_LABELS_TR[key]
            assert metric_by_label[label] == expected, f"{label}: beklenen {expected}, bulunan {metric_by_label[label]}"
        assert len(metric_by_label) == 6

        assert at.get("multiselect")[0].key == "mk_change_type_filter"
        # NEDEN: filtre varsayılan olarak TÜM türleri seçili göstermeli --
        # aksi halde kullanıcı ilk açılışta bazı maddeleri SESSİZCE kaçırır.
        # NEDEN altı seçenek: İÇERİK (4) + YAPISAL (2) etiketleri TEK bir
        # filtrede birleştirilir (bkz. components.py::render_change_type_filter
        # NEDEN notu) -- görsel olarak Adım 7'deki filtreyle AYNI sayıda
        # seçenek, ama "Numarası/Yeri Değişti" artık İÇERİK durumundan
        # BAĞIMSIZ bir VEYA koşulu olarak çalışır.
        from src.config import CHANGE_TYPE_LABELS_TR

        expected_labels = {CHANGE_TYPE_LABELS_TR[ct.value] for ct in ChangeType} | {
            CHANGE_TYPE_LABELS_TR["RENUMBERED"],
            CHANGE_TYPE_LABELS_TR["MOVED"],
        }
        assert set(at.multiselect(key="mk_change_type_filter").options) == expected_labels
        assert set(at.multiselect(key="mk_change_type_filter").value) == set(
            at.multiselect(key="mk_change_type_filter").options
        )

    def test_filtre_numarasi_degisti_secilince_icerigi_ayni_kalan_ve_hem_icerigi_hem_numarasi_degisen_madde_birlikte_gorunur(
        self,
    ):
        # NEDEN kritik: Adım 9'un TAM konusu -- "Numarası Değişti" filtresi
        # SEÇİLDİĞİNDE hem SADECE numarası değişen maddeler (örn. Yürürlük)
        # hem HEM İÇERİĞİ HEM NUMARASI değişen maddeler (Birim Sorumlulukları)
        # görünmeli (VEYA mantığı, bkz. components.py NEDEN notu); hiçbir
        # yapısal değişikliği olmayan bir madde (Amaç) GÖRÜNMEMELİ.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        from src.config import CHANGE_TYPE_LABELS_TR

        at.multiselect(key="mk_change_type_filter").set_value([CHANGE_TYPE_LABELS_TR["RENUMBERED"]])
        at.run(timeout=30)

        assert not at.exception
        visible_text = "\n".join(m.value for m in at.get("markdown"))
        assert "Yürürlük" in visible_text
        assert "Birim Sorumlulukları" in visible_text
        assert "Amaç" not in visible_text

    def test_iki_belge_yuklendiginde_yonetici_ozeti_ve_indirme_dugmeleri_gorunur(self):
        # NEDEN (Adım 7): Yönetici Özeti paneli VE Excel/CSV/HTML indirme
        # düğmeleri app.py'ye entegre edildi -- bu, o entegrasyonun GERÇEKTEN
        # çalıştığını (sadece izole exporter/summary_builder testlerinin
        # değil) uçtan uca doğrular.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        assert not at.exception
        summary_markdown = "\n".join(m.value for m in at.get("markdown"))
        assert "Yönetici Özeti" in summary_markdown
        assert "### İçerik Durumu" in summary_markdown
        assert "### Yapısal Değişiklikler" in summary_markdown
        assert (
            f"{_EXPECTED_STRUCTURAL_COUNTS['RENUMBERED']} maddede madde numarası değişikliği tespit edildi."
            in summary_markdown
        )
        assert "ÜÇÜNCÜ BÖLÜM" in summary_markdown

        download_keys = {b.key for b in at.get("download_button")}
        assert download_keys == {"mk_download_excel", "mk_download_csv", "mk_download_html"}

    def test_bolum_dokumu_ve_en_fazla_degisiklik_gorunur(self):
        # NEDEN: "Bölümlere Göre Değişiklikler" paneli (bkz.
        # components.render_section_breakdown) app.py'ye entegre edildi --
        # bu, entegrasyonun GERÇEKTEN çalıştığını (izole metrics.py
        # testlerinin ötesinde) uçtan uca doğrular.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        assert not at.exception
        visible_markdown = "\n".join(m.value for m in at.get("markdown"))
        assert "Bölümlere Göre Değişiklikler" in visible_markdown
        assert "En fazla değişiklik:" in visible_markdown and "ÜÇÜNCÜ BÖLÜM (4 madde)" in visible_markdown

        dataframes = at.get("dataframe")
        assert len(dataframes) == 1
        breakdown_df = dataframes[0].value
        assert list(breakdown_df["Bölüm"]) == ["BİRİNCİ BÖLÜM", "İKİNCİ BÖLÜM", "ÜÇÜNCÜ BÖLÜM", "DÖRDÜNCÜ BÖLÜM"]
        assert breakdown_df.set_index("Bölüm").loc["BİRİNCİ BÖLÜM"].to_dict() == {
            "Değişmedi": 3, "Değişti": 1, "Yeni Eklendi": 0, "Kaldırıldı": 0,
        }

        selectbox = at.selectbox(key="mk_bolum_filter")
        assert selectbox.value == "(Tümü)"
        assert selectbox.options == ["(Tümü)", "BİRİNCİ BÖLÜM", "İKİNCİ BÖLÜM", "ÜÇÜNCÜ BÖLÜM", "DÖRDÜNCÜ BÖLÜM"]

    def test_bolum_secilince_sadece_o_bolume_ait_maddeler_gorunur(self):
        # NEDEN kritik: kullanıcı geri bildiriminin TAM konusu -- bir bölüm
        # seçildiğinde SADECE o bölüme ait maddeler görünmeli, mevcut
        # Değişim Türü filtresiyle (VE mantığıyla) UYUMLU çalışmalı.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        at.selectbox(key="mk_bolum_filter").set_value("İKİNCİ BÖLÜM")
        at.run(timeout=30)

        assert not at.exception
        visible_text = "\n".join(m.value for m in at.get("markdown"))
        # İKİNCİ BÖLÜM'e ait maddeler (satır BAŞLIKLARI, "MADDE N —" ile):
        assert "MADDE 5 — Veri Sorumluluğu" in visible_text
        assert "MADDE 6 — Veri Paylaşımı" in visible_text
        assert "MADDE 7 — Veri Kalitesi ve Güvenliği" in visible_text
        assert "MADDE 8 — Arşivleme Esasları" in visible_text
        # NEDEN "MADDE N —" ÖNEKİYLE aranıyor (sadece başlık metniyle DEĞİL):
        # Yönetici Özeti'nin "Öne Çıkan Değişiklikler" listesi (bkz.
        # summary_builder.py) satır FİLTRESİNDEN BAĞIMSIZ olarak HER ZAMAN
        # görünür -- "Birim Sorumlulukları" gibi bir başlık SADECE metin
        # olarak arandığında orada da eşleşir, YANLIŞ POZİTİF verir.
        assert "MADDE 1 —" not in visible_text  # Amaç (BİRİNCİ BÖLÜM)
        assert "MADDE 9 —" not in visible_text  # Birim Sorumlulukları (ÜÇÜNCÜ BÖLÜM)
        assert "MADDE 12 —" not in visible_text  # Yürürlük (DÖRDÜNCÜ BÖLÜM)

    def test_pdf_karsilastirmasinda_kaynak_baglantisi_gorunur(self):
        # NEDEN: kullanıcı geri bildiriminin TAM konusu -- her madde için
        # "Belgede görüntüle · Sayfa N" tıklanabilir bağlantısı app.py'ye
        # entegre edildi; örnek belgeler küçük olduğu için (bkz.
        # SOURCE_LINK_MAX_TOTAL_BYTES bütçesi) bağlantı ÜRETİLMELİ, düz
        # metne DÜŞMEMELİ.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        assert not at.exception
        # NEDEN "iframe" widget'ları aranıyor (st.markdown DEĞİL): tıklanabilir
        # bağlantı artık bir <script> ÇALIŞTIRAN bağımsız bir <iframe>'de
        # render ediliyor (bkz. components.py::render_source_link NEDEN
        # notu) -- st.markdown içindeki HTML React tarafından yeniden
        # yorumlanır ve onclick/script ÇALIŞTIRMAZ.
        iframe_srcdocs = [el.proto.srcdoc for el in at.get("iframe")]
        assert iframe_srcdocs, "hiç iframe (kaynak bağlantısı) üretilmedi"
        # MADDE 1 (Amaç) her iki belgede de 1. sayfada (bkz. script çıktısı).
        assert any("Belgede görüntüle · Sayfa 1" in s and "#page=1'" in s for s in iframe_srcdocs)
        # NEDEN blob: tabanlı JavaScript'i ARANIYOR (href="data:..." DEĞİL):
        # bkz. components.py::render_source_link NEDEN notu -- `data:`
        # URI'ler Chrome'da #page=N'i güvenilir uygulamadığı için `blob:`
        # tekniğine geçildi (tarayıcıda test edilerek doğrulandı).
        assert all("URL.createObjectURL(blob)" in s for s in iframe_srcdocs)

    def test_iframe_sayisi_sadece_var_olan_taraflar_icin_uretilir(self):
        # NEDEN kritik: kullanıcının AÇIKÇA istediği kural -- REMOVED bir
        # satırda (new=None) SADECE eski, ADDED bir satırda (old=None)
        # SADECE yeni belge bağlantısı görünmeli. Her satır İÇİN AYRI bir
        # <iframe> üretildiğinden (bkz. render_side_by_side), toplam iframe
        # sayısı old/new taraf DOLU olan satır sayılarının TOPLAMINA eşit
        # olmalı -- 15+15=30 DEĞİL (bu, REMOVED/ADDED satırlarda KARŞILIĞI
        # OLMAYAN tarafa da bağlantı üretildiği anlamına gelirdi).
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload("yonetmelik_2019.pdf", old_bytes, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("yonetmelik_2023.pdf", new_bytes, "application/pdf")
        at.run(timeout=60)

        assert not at.exception
        # eski belgede 13, yeni belgede 14 madde var (bkz.
        # TestSummaryBuilderStats::test_toplamlar_ground_truth_ile_esler) --
        # REMOVED (1 madde) SADECE eski, ADDED (2 madde) SADECE yeni
        # tarafta bağlantı üretir; 13+14=27, 15+15=30 DEĞİL.
        assert len(at.get("iframe")) == 13 + 14

    def test_docx_karsilastirmasinda_kaynak_baglantisi_gorunmez(self):
        # NEDEN: DOCX akış tabanlıdır, sayfa/PDF görüntüleme kavramı YOKTUR
        # (bkz. models.py::TextUnit NEDEN notu) -- özellik "mümkünse"
        # ilkesiyle SESSİZCE devre dışı kalmalı, hatalı/uydurma bir sayfa
        # bilgisi GÖSTERİLMEMELİ (ne iframe ne "Sayfa N" metni).
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        old_bytes = (SAMPLES_DIR / "yonetmelik_2019.docx").read_bytes()
        new_bytes = (SAMPLES_DIR / "yonetmelik_2023.docx").read_bytes()
        at.file_uploader(key="mk_old_uploader").upload(
            "yonetmelik_2019.docx", old_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        at.file_uploader(key="mk_new_uploader").upload(
            "yonetmelik_2023.docx", new_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        at.run(timeout=60)

        assert not at.exception
        assert len(at.get("iframe")) == 0
        visible_html = "\n".join(m.value for m in at.get("markdown"))
        assert 'class="mk-source-page"' not in visible_html
        assert 'class="mk-source-page"' not in visible_html

    def test_yukleme_alanlari_sadece_pdf_docx_kabul_eder(self):
        # NEDEN: st.file_uploader(type=["pdf","docx"]) kısıtlaması WIDGET
        # DÜZEYİNDE uygulanıyor -- desteklenmeyen bir uzantı app.py'nin iş
        # mantığına HİÇ ULAŞAMADAN reddedilmeli (compare_documents()'ın
        # ValueError'ı, bkz. TestCompareDocumentsGercekOrnekBelgelerle,
        # zaten bu kontrolü ALT KATMANDA doğruluyor; burada asıl doğrulanan
        # widget'ın kısıtlamayı GERÇEKTEN uyguladığıdır).
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        at.file_uploader(key="mk_old_uploader").upload("belge.txt", b"metin", "text/plain")
        at.run(timeout=30)

        assert at.exception
        assert "Invalid file extension" in at.exception[0].value

    def test_bozuk_pdf_yuklenince_traceback_degil_temiz_hata_gosterir(self):
        # NEDEN (Adım 8, kritik): doğru uzantılı ama İÇERİĞİ bozuk bir dosya
        # -- düzeltilmeden önce bu, kullanıcıya çıplak bir Python traceback'i
        # (ve sunucunun geçici dosya yolunu) sızdırırdı. app.py artık
        # CorruptDocumentError'ı yakalayıp temiz bir st.error göstermeli.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        at.file_uploader(key="mk_old_uploader").upload(
            "bozuk.pdf", b"bu gecerli bir PDF degil, bozuk baytlar", "application/pdf"
        )
        at.file_uploader(key="mk_new_uploader").upload(
            "bozuk2.pdf", b"bu da bozuk", "application/pdf"
        )
        at.run(timeout=30)

        assert not at.exception
        errors = [e.value for e in at.get("error")]
        assert any("bozuk.pdf" in e for e in errors)
        assert not any("/tmp" in e or "/var" in e for e in errors)

    def test_madde_yapisi_olmayan_belgede_uyari_gosterir(self):
        # NEDEN: metin katmanı VAR (NoTextLayerError tetiklenmez) ama hiçbir
        # "MADDE N" kalıbı YOK -- kullanıcı sessizce boş bir sonuç görüp
        # "karşılaştırma başarılı, hiç fark yok" yanılgısına düşmemeli.
        at = AppTest.from_file(str(_APP_PATH))
        at.run(timeout=30)

        import pymupdf

        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Bu belge hicbir madde numaralandirmasi icermeyen duz bir metindir. " * 5)
        content = pdf.tobytes()
        pdf.close()

        at.file_uploader(key="mk_old_uploader").upload("maddesiz1.pdf", content, "application/pdf")
        at.file_uploader(key="mk_new_uploader").upload("maddesiz2.pdf", content, "application/pdf")
        at.run(timeout=30)

        assert not at.exception
        warnings = [w.value for w in at.get("warning")]
        assert any("MADDE" in w for w in warnings)
        assert not at.get("metric")  # metrik kartları hiç render edilmemeli
