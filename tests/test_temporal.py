"""
Mimari Ek 1 testleri -- F2 (tarih tahmini), F3 (görünen ad),
F6 (yasak hukukî fiil taraması).

NEDEN her ChangeType şablonunun TARANMASI (TestYasakHukukiFiiller): F6'nın
"sistem hukukî yorum yapmamalıdır" ilkesi, bir geliştiricinin ileride
config.py'ye "mülga edilmiştir" gibi bir şablon EKLEMESİNİ engelleyen tek
şey bu testtir -- kod incelemesi bunu kaçırabilir, otomatik tarama kaçırmaz.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.config import (
    CHANGE_TYPE_SENTENCE_TEMPLATES,
    YASAK_HUKUKI_SONUC_IFADELERI,
)
from src.models import DocumentMeta
from src.temporal import (
    belge_gorunen_adi,
    guess_date_from_filename,
    guess_date_from_metadata,
    kaynak_atifi,
    suggest_publication_date,
)


def _meta(**kwargs) -> DocumentMeta:
    base = {"doc_id": "d", "source_path": "x.pdf", "file_type": "pdf"}
    base.update(kwargs)
    return DocumentMeta(**base)


# --------------------------------------------------------------------------
# F2 -- tarih tahmini (dosya adı / üstveri)
# --------------------------------------------------------------------------


class TestTarihTahmini:
    def test_dosya_adindan_tam_tarih(self):
        assert guess_date_from_filename("yonetmelik_14.11.2019.pdf") == date(2019, 11, 14)

    def test_dosya_adindan_sadece_yil(self):
        assert guess_date_from_filename("yonetmelik_2019.pdf") == date(2019, 1, 1)

    def test_dosya_adinda_tarih_yoksa_none(self):
        assert guess_date_from_filename("yonetmelik_son_hali.pdf") is None

    def test_pdf_ustveri_tarihinden_cikarim(self):
        assert guess_date_from_metadata("D:20191114093000+03'00'") == date(2019, 11, 14)

    def test_ustveri_dosya_adindan_ONCELIKLIDIR(self):
        oneri = suggest_publication_date("yonetmelik_2023.pdf", metadata_created="D:20191114000000")
        assert oneri.suggested_date == date(2019, 11, 14)
        assert oneri.source == "metadata"

    def test_ustveri_yoksa_dosya_adina_duser(self):
        oneri = suggest_publication_date("yonetmelik_2019.pdf")
        assert oneri.suggested_date == date(2019, 1, 1)
        assert oneri.source == "filename"


# --------------------------------------------------------------------------
# F3 -- görünen ad (kademeli düşüş)
# --------------------------------------------------------------------------


class TestGorunenAd:
    def test_kademe_1_surum_etiketi(self):
        meta = _meta(slot="A", version_label="2019 sürümü", source_path="x.pdf")
        assert belge_gorunen_adi(meta) == "Belge A (2019 sürümü)"

    def test_kademe_2_yalnizca_tarih(self):
        meta = _meta(slot="B", effective_date=date(2019, 11, 14), source_path="x.pdf")
        assert belge_gorunen_adi(meta) == "Belge B (14.11.2019)"

    def test_kademe_3_dosya_adi(self):
        meta = _meta(slot="A", source_path="data/samples/yonetmelik_v1.pdf")
        assert belge_gorunen_adi(meta) == "Belge A (yonetmelik_v1.pdf)"


# --------------------------------------------------------------------------
# F7 -- kaynak atıfı
# --------------------------------------------------------------------------


class TestKaynakAtifi:
    def test_sayfa_ile_atif(self):
        meta = _meta(slot="B", version_label="2023 sürümü", source_path="x.pdf")
        assert kaynak_atifi(meta, "MADDE 5", 3) == "Belge B (2023 sürümü), MADDE 5, s. 3"

    def test_sayfasiz_atif(self):
        meta = _meta(slot="A", version_label="2019 sürümü", source_path="x.docx")
        assert kaynak_atifi(meta, "MADDE 5") == "Belge A (2019 sürümü), MADDE 5"


# --------------------------------------------------------------------------
# F6 -- yasak hukukî fiil taraması
# --------------------------------------------------------------------------


class TestYasakHukukiFiiller:
    @pytest.mark.parametrize("change_type,sablon", CHANGE_TYPE_SENTENCE_TEMPLATES.items())
    def test_sablonda_yasak_fiil_gecmez(self, change_type, sablon):
        for yasak in YASAK_HUKUKI_SONUC_IFADELERI:
            assert yasak not in sablon, (
                f"{change_type} şablonu yasak hukukî sonuç ifadesi içeriyor: {yasak!r}"
            )
