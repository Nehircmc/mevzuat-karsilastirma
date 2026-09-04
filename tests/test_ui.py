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

from src.config import ASSETS_DIR, BASE_DIR, COLOR_PALETTE, SAMPLES_DIR
from src.models import ChangeType
from src.ui import styles
from src.ui.components import ComparisonResult, compare_documents

_APP_PATH = BASE_DIR / "app.py"

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)

_EXPECTED_COUNTS: dict[ChangeType, int] = {}
for _m in _GROUND_TRUTH["maddeler"]:
    _EXPECTED_COUNTS[ChangeType(_m["change_type"])] = (
        _EXPECTED_COUNTS.get(ChangeType(_m["change_type"]), 0) + 1
    )


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

        for change_type, expected in _EXPECTED_COUNTS.items():
            label = CHANGE_TYPE_LABELS_TR[change_type.value]
            assert metric_by_label[label] == expected, f"{label}: beklenen {expected}, bulunan {metric_by_label[label]}"

        assert at.get("multiselect")[0].key == "mk_change_type_filter"
        # NEDEN: filtre varsayılan olarak TÜM türleri seçili göstermeli --
        # aksi halde kullanıcı ilk açılışta bazı maddeleri SESSİZCE kaçırır.
        assert set(at.multiselect(key="mk_change_type_filter").value) == set(
            at.multiselect(key="mk_change_type_filter").options
        )

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
        assert "ÜÇÜNCÜ BÖLÜM" in summary_markdown

        download_keys = {b.key for b in at.get("download_button")}
        assert download_keys == {"mk_download_excel", "mk_download_csv", "mk_download_html"}

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
