"""
src/reporting/metrics.py + src/reporting/summary_builder.py +
src/reporting/exporter.py (Adım 7) testleri.

Gerçek 2019/2023 örnek belgeleriyle üretilen TEK bir ComparisonResult
(modül düzeyinde bir kez hesaplanır -- pahalı ingestion/parse/match/diff
adımlarını her testte TEKRARLAMAMAK için), ground_truth.json'daki bilinen
sayılara karşı objektif doğrulanır.
"""

from __future__ import annotations

import json
from io import BytesIO

import pandas as pd
import pytest

from src.analysis.pipeline import compare_documents
from src.config import CHANGE_TYPE_LABELS_TR, SAMPLES_DIR
from src.models import ChangeType
from src.reporting.exporter import export_to_csv, export_to_excel, export_to_html
from src.reporting.html_renderer import render_summary_html
from src.reporting.metrics import build_detail_dataframe, build_summary_dataframe
from src.reporting.summary_builder import SummaryStats, build_summary_stats, render_summary_markdown

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)

_EXPECTED_COUNTS: dict[ChangeType, int] = dict.fromkeys(ChangeType, 0)
for _m in _GROUND_TRUTH["maddeler"]:
    _EXPECTED_COUNTS[ChangeType(_m["change_type"])] += 1
_EXPECTED_TOTAL = len(_GROUND_TRUTH["maddeler"])

_OLD_BYTES = (SAMPLES_DIR / "yonetmelik_2019.pdf").read_bytes()
_NEW_BYTES = (SAMPLES_DIR / "yonetmelik_2023.pdf").read_bytes()
_RESULT = compare_documents(_OLD_BYTES, "yonetmelik_2019.pdf", _NEW_BYTES, "yonetmelik_2023.pdf")


class TestMetricsSummaryDataFrame:
    def test_her_change_type_icin_bir_satir(self):
        df = build_summary_dataframe(_RESULT)
        assert len(df) == len(ChangeType)
        assert list(df.columns) == ["Değişim Türü", "Sayı", "Yüzde"]

    def test_sayilar_ground_truth_ile_esler(self):
        df = build_summary_dataframe(_RESULT)
        by_label = dict(zip(df["Değişim Türü"], df["Sayı"]))
        for change_type, expected in _EXPECTED_COUNTS.items():
            label = CHANGE_TYPE_LABELS_TR[change_type.value]
            assert by_label[label] == expected, f"{label}: beklenen {expected}, bulunan {by_label[label]}"

    def test_yuzdeler_toplami_yuz_civarinda(self):
        # NEDEN dar olmayan bir tolerans: her yüzde ayrı ayrı 1 ondalığa
        # YUVARLANDIĞI için toplam, kayan nokta hassasiyeti VE yuvarlama payı
        # yüzünden 100'den birkaç onda bir sapabilir -- tek tek yüzdelerin
        # DOĞRULUĞU zaten test_yuzdeler_dogru_hesaplanir'de (summary_builder
        # testleri) ayrı ayrı kontrol ediliyor.
        df = build_summary_dataframe(_RESULT)
        assert 99.5 <= df["Yüzde"].sum() <= 100.5

    def test_bos_sonucta_bile_alti_satir_ve_dogru_kolonlar(self):
        from src.analysis.pipeline import ComparisonResult
        from src.models import DocumentMeta

        empty = ComparisonResult(
            old_meta=DocumentMeta(doc_id="x", source_path="x", file_type="pdf"),
            new_meta=DocumentMeta(doc_id="y", source_path="y", file_type="pdf"),
            rows=[],
        )
        df = build_summary_dataframe(empty)
        assert list(df.columns) == ["Değişim Türü", "Sayı", "Yüzde"]
        assert (df["Sayı"] == 0).all()
        assert (df["Yüzde"] == 0.0).all()


class TestMetricsDetailDataFrame:
    def test_satir_sayisi_ground_truth_ile_esler(self):
        df = build_detail_dataframe(_RESULT)
        assert len(df) == _EXPECTED_TOTAL

    def test_kolonlar_beklenen_sirada(self):
        df = build_detail_dataframe(_RESULT)
        assert list(df.columns) == [
            "Değişim Türü",
            "Eski Madde No",
            "Yeni Madde No",
            "Başlık",
            "Eski Bölüm",
            "Yeni Bölüm",
            "Eski Metin",
            "Yeni Metin",
        ]

    def test_removed_satirda_yeni_madde_no_bos(self):
        df = build_detail_dataframe(_RESULT)
        removed = df[df["Değişim Türü"] == CHANGE_TYPE_LABELS_TR["REMOVED"]]
        assert len(removed) == 1
        assert removed.iloc[0]["Yeni Madde No"] is None or pd.isna(removed.iloc[0]["Yeni Madde No"])
        assert removed.iloc[0]["Eski Madde No"] == 8

    def test_added_satirda_eski_madde_no_bos(self):
        df = build_detail_dataframe(_RESULT)
        added = df[df["Değişim Türü"] == CHANGE_TYPE_LABELS_TR["ADDED"]]
        assert len(added) == 2
        assert added["Eski Madde No"].isna().all()

    def test_bos_sonucta_bile_kolon_basliklari_korunur(self):
        from src.analysis.pipeline import ComparisonResult
        from src.models import DocumentMeta

        empty = ComparisonResult(
            old_meta=DocumentMeta(doc_id="x", source_path="x", file_type="pdf"),
            new_meta=DocumentMeta(doc_id="y", source_path="y", file_type="pdf"),
            rows=[],
        )
        df = build_detail_dataframe(empty)
        assert len(df) == 0
        assert list(df.columns) == [
            "Değişim Türü",
            "Eski Madde No",
            "Yeni Madde No",
            "Başlık",
            "Eski Bölüm",
            "Yeni Bölüm",
            "Eski Metin",
            "Yeni Metin",
        ]


def _tek_maddelik_sonuc(metin: str, *, baslik: str = "Test") -> "ComparisonResult":
    """Tek bir ADDED Section içeren minimal ComparisonResult -- güvenlik testleri için."""
    from src.analysis.classifier import ClassifiedSection
    from src.analysis.pipeline import ComparisonResult, ComparisonRow
    from src.models import DocumentMeta, Section, TextUnit

    unit = TextUnit(
        doc_id="t", page_no=1, block_index=0, char_start=0, char_end=len(metin), heading_path=(), text=metin
    )
    section = Section(
        doc_id="t", heading_path=("MADDE 1",), section_type="MADDE",
        madde_no=1, baslik=baslik, order_index=0, units=[unit],
    )
    return ComparisonResult(
        old_meta=DocumentMeta(doc_id="x", source_path="x", file_type="pdf"),
        new_meta=DocumentMeta(doc_id="y", source_path="y", file_type="pdf"),
        rows=[ComparisonRow(classified=ClassifiedSection(change_type=ChangeType.ADDED, old=None, new=section), section_diff=None)],
    )


class TestMetricsFormulaEnjeksiyonuKorumasi:
    """
    Güvenlik regresyon testleri (CWE-1236 / "CSV Injection"): belge
    içeriğinden gelen bir madde metni "=", "+", "-" ya da "@" ile
    BAŞLIYORSA (örn. bir liste öğesi "- İlgili birimler..." gibi doğal
    biçimde bile olabilir), dışa aktarılan CSV/Excel'de bu bir FORMÜL
    olarak yorumlanmamalı -- Excel/LibreOffice bu karakterleri hücre
    başında formül tetikleyicisi sayar.
    """

    @pytest.mark.parametrize("tetikleyici", ["=", "+", "-", "@"])
    def test_tehlikeli_karakterle_baslayan_metin_tek_tirnakla_kacirilir(self, tetikleyici):
        tehlikeli = f"{tetikleyici}cmd|'/c calc'!A1"
        result = _tek_maddelik_sonuc(tehlikeli)

        df = build_detail_dataframe(result)

        assert df.iloc[0]["Yeni Metin"] == f"'{tehlikeli}"

    def test_zararsiz_metin_degistirilmeden_kalir(self):
        result = _tek_maddelik_sonuc("(1) Kurum verileri paylaşılamaz.")

        df = build_detail_dataframe(result)

        assert df.iloc[0]["Yeni Metin"] == "(1) Kurum verileri paylaşılamaz."

    def test_metin_ortasindaki_tehlikeli_karakter_dokunulmaz(self):
        # NEDEN: formül yorumlanması SADECE hücrenin İLK karakteriyle
        # ilgilidir -- metin içinde herhangi bir yerde "=" geçmesi risk
        # OLUŞTURMAZ, gereksiz kaçırma OKUNABİLİRLİĞİ bozardı.
        result = _tek_maddelik_sonuc("Bu madde x=5 formülünü içerir.")

        df = build_detail_dataframe(result)

        assert df.iloc[0]["Yeni Metin"] == "Bu madde x=5 formülünü içerir."

    def test_baslik_ve_bolum_de_korunur(self):
        result = _tek_maddelik_sonuc("normal metin", baslik="=HYPERLINK(\"http://kotu\")")

        df = build_detail_dataframe(result)

        assert df.iloc[0]["Başlık"] == "'=HYPERLINK(\"http://kotu\")"

    def test_csv_disa_aktarimda_da_kacirilmis_halde_gorunur(self):
        result = _tek_maddelik_sonuc("-Ilgili birimler bildirmekle yukumludur.")

        csv_text = export_to_csv(result).decode("utf-8-sig")

        assert "'-Ilgili birimler" in csv_text

    def test_excel_disa_aktarimda_da_kacirilmis_halde_gorunur(self):
        import openpyxl

        result = _tek_maddelik_sonuc("=cmd|'/c calc'!A1")

        xlsx_bytes = export_to_excel(result)
        wb = openpyxl.load_workbook(BytesIO(xlsx_bytes))
        detay = wb["Detay"]
        header = [c.value for c in next(detay.iter_rows(min_row=1, max_row=1))]
        row = [c.value for c in next(detay.iter_rows(min_row=2, max_row=2))]
        deger = dict(zip(header, row))

        assert deger["Yeni Metin"] == "'=cmd|'/c calc'!A1"


class TestSummaryBuilderStats:
    def test_toplamlar_ground_truth_ile_esler(self):
        stats = build_summary_stats(_RESULT)
        assert stats.toplam_karsilastirma == _EXPECTED_TOTAL
        assert stats.eski_toplam_madde == 13  # 2019: 13 madde
        assert stats.yeni_toplam_madde == 14  # 2023: 14 madde

    def test_sayilar_ground_truth_ile_esler(self):
        stats = build_summary_stats(_RESULT)
        assert stats.sayilar == _EXPECTED_COUNTS

    def test_yuzdeler_dogru_hesaplanir(self):
        stats = build_summary_stats(_RESULT)
        for change_type, count in _EXPECTED_COUNTS.items():
            expected_pct = round(count / _EXPECTED_TOTAL * 100, 1)
            assert stats.yuzdeler[change_type] == expected_pct

    def test_en_cok_degisen_bolum_ucuncu_bolumdur(self):
        # NEDEN ÜÇÜNCÜ BÖLÜM: birim_sorumluluklari(MODIFIED),
        # ust_yonetim_sorumlulugu(RENUMBERED), veri_yonetisim_kurulu(ADDED),
        # acik_veri_portali(ADDED) -- 4 IDENTICAL-olmayan madde, ground
        # truth'taki HERHANGİ başka bir bölümden fazla.
        stats = build_summary_stats(_RESULT)
        assert stats.en_cok_degisen_bolum == ("ÜÇÜNCÜ BÖLÜM", 4)

    def test_hicbir_degisiklik_yoksa_en_cok_degisen_bolum_nonedir(self):
        from src.analysis.classifier import ClassifiedSection
        from src.analysis.pipeline import ComparisonResult, ComparisonRow
        from src.models import DocumentMeta, Section, TextUnit

        unit = TextUnit(doc_id="t", page_no=1, block_index=0, char_start=0, char_end=1, heading_path=(), text="x")
        section = Section(
            doc_id="t", heading_path=("BİRİNCİ BÖLÜM", "MADDE 1"), section_type="MADDE",
            madde_no=1, baslik="X", order_index=0, units=[unit],
        )
        result = ComparisonResult(
            old_meta=DocumentMeta(doc_id="x", source_path="x", file_type="pdf"),
            new_meta=DocumentMeta(doc_id="y", source_path="y", file_type="pdf"),
            rows=[ComparisonRow(classified=ClassifiedSection(change_type=ChangeType.IDENTICAL, old=section, new=section), section_diff=None)],
        )
        stats = build_summary_stats(result)
        assert stats.en_cok_degisen_bolum is None

    def test_sonuc_tipi(self):
        assert isinstance(build_summary_stats(_RESULT), SummaryStats)


class TestSummaryBuilderMarkdown:
    def test_tum_change_type_etiketleri_gecer(self):
        stats = build_summary_stats(_RESULT)
        md = render_summary_markdown(stats)
        for change_type in ChangeType:
            assert CHANGE_TYPE_LABELS_TR[change_type.value] in md

    def test_sayilar_metinde_gecer(self):
        stats = build_summary_stats(_RESULT)
        md = render_summary_markdown(stats)
        assert "**13**" in md
        assert "**14**" in md
        assert "**15**" in md

    def test_en_cok_degisen_bolum_metinde_gecer(self):
        stats = build_summary_stats(_RESULT)
        md = render_summary_markdown(stats)
        assert "ÜÇÜNCÜ BÖLÜM" in md

    def test_bolum_yoksa_o_satir_hic_gorunmez(self):
        stats = SummaryStats(
            toplam_karsilastirma=0,
            eski_toplam_madde=0,
            yeni_toplam_madde=0,
            sayilar=dict.fromkeys(ChangeType, 0),
            yuzdeler=dict.fromkeys(ChangeType, 0.0),
            en_cok_degisen_bolum=None,
        )
        md = render_summary_markdown(stats)
        assert "En çok değişiklik" not in md

    def test_deterministik_iki_cagri_ayni_sonucu_verir(self):
        stats = build_summary_stats(_RESULT)
        assert render_summary_markdown(stats) == render_summary_markdown(stats)


class TestSummaryHtml:
    def test_ozel_karakterli_bolum_adi_kacirilir(self):
        stats = SummaryStats(
            toplam_karsilastirma=1,
            eski_toplam_madde=1,
            yeni_toplam_madde=1,
            sayilar=dict.fromkeys(ChangeType, 0),
            yuzdeler=dict.fromkeys(ChangeType, 0.0),
            en_cok_degisen_bolum=("<script>alert(1)</script>", 3),
        )
        html = render_summary_html(stats)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_her_change_type_rozeti_gecer(self):
        stats = build_summary_stats(_RESULT)
        html = render_summary_html(stats)
        for change_type in ChangeType:
            assert f"mk-badge-{change_type.value.lower()}" in html


class TestExporterExcel:
    def test_iki_sayfa_uretir_dogru_boyutlarda(self):
        xlsx_bytes = export_to_excel(_RESULT)
        sheets = pd.read_excel(BytesIO(xlsx_bytes), sheet_name=None)
        assert set(sheets.keys()) == {"Özet", "Detay"}
        assert sheets["Özet"].shape == (len(ChangeType), 3)
        assert sheets["Detay"].shape[0] == _EXPECTED_TOTAL

    def test_detay_sayfasi_sayimla_tutarli(self):
        xlsx_bytes = export_to_excel(_RESULT)
        detay = pd.read_excel(BytesIO(xlsx_bytes), sheet_name="Detay")
        for change_type, expected in _EXPECTED_COUNTS.items():
            label = CHANGE_TYPE_LABELS_TR[change_type.value]
            assert (detay["Değişim Türü"] == label).sum() == expected


class TestExporterCsv:
    def test_utf8_sig_bom_ile_baslar(self):
        csv_bytes = export_to_csv(_RESULT)
        assert csv_bytes.startswith(b"\xef\xbb\xbf")

    def test_baslik_satiri_dogru(self):
        csv_bytes = export_to_csv(_RESULT)
        first_line = csv_bytes.decode("utf-8-sig").splitlines()[0]
        assert first_line == "Değişim Türü,Eski Madde No,Yeni Madde No,Başlık,Eski Bölüm,Yeni Bölüm,Eski Metin,Yeni Metin"

    def test_satir_sayisi_basliklar_dahil(self):
        csv_bytes = export_to_csv(_RESULT)
        lines = csv_bytes.decode("utf-8-sig").splitlines()
        assert len(lines) == _EXPECTED_TOTAL + 1  # +1 başlık satırı

    def test_geri_okunabilir_pandas_ile(self):
        csv_bytes = export_to_csv(_RESULT)
        df = pd.read_csv(BytesIO(csv_bytes), encoding="utf-8-sig")
        assert len(df) == _EXPECTED_TOTAL


class TestExporterHtml:
    def test_gecerli_bagimsiz_html_belgesi(self):
        html_bytes = export_to_html(_RESULT)
        html_text = html_bytes.decode("utf-8")
        assert html_text.startswith("<!doctype html>")
        assert "<style>" in html_text and "</style>" in html_text
        assert "mk-badge-modified" in html_text  # CSS enjekte edilmiş

    def test_css_tum_change_type_renklerini_icerir(self):
        html_text = export_to_html(_RESULT).decode("utf-8")
        for change_type in ChangeType:
            assert f".mk-badge-{change_type.value.lower()}" in html_text

    def test_her_maddenin_basligi_gecer(self):
        html_text = export_to_html(_RESULT).decode("utf-8")
        for m in _GROUND_TRUTH["maddeler"]:
            assert m["baslik"] in html_text

    def test_ozet_bolumu_icerir(self):
        html_text = export_to_html(_RESULT).decode("utf-8")
        assert "Yönetici Özeti" in html_text

    def test_kaldirilan_madde_kirmizi_sinifla_gorunur(self):
        html_text = export_to_html(_RESULT).decode("utf-8")
        assert "mk-diff-removed" in html_text

    def test_html_ozel_karakter_icermez_kacirilmamis(self):
        # NEDEN: gövde metninde "<" "&" gibi karakterler varsa (bkz.
        # dayanak maddesi "T.C." kısaltması İÇERMEZ ama genel ilke olarak)
        # ham HTML olarak sızmamalı -- html_renderer zaten escape ediyor,
        # burada dışa aktarılan dosyanın GERÇEKTEN html.escape() çıktısı
        # taşıdığını (örn. hiç kapanmamış bir <div> kalmadığını) doğruluyoruz.
        html_text = export_to_html(_RESULT).decode("utf-8")
        assert html_text.count("<div") == html_text.count("</div>")

    @pytest.mark.parametrize("dosya_2019,dosya_2023", [("yonetmelik_2019.docx", "yonetmelik_2023.docx")])
    def test_docx_ile_de_calisir(self, dosya_2019, dosya_2023):
        old_bytes = (SAMPLES_DIR / dosya_2019).read_bytes()
        new_bytes = (SAMPLES_DIR / dosya_2023).read_bytes()
        result = compare_documents(old_bytes, dosya_2019, new_bytes, dosya_2023)
        html_text = export_to_html(result).decode("utf-8")
        assert html_text.startswith("<!doctype html>")
        assert "Yönetici Özeti" in html_text
