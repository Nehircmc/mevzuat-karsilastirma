"""
Mimari Ek 1 testleri -- F2 (kronolojik sıra + onay), F3 (görünen ad),
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
    ConfirmedOrder,
    OrderConfidence,
    OrderNotConfirmedError,
    belge_gorunen_adi,
    confirm_order,
    determine_chronological_order,
    guess_date_from_filename,
    guess_date_from_metadata,
    kaynak_atifi,
    require_confirmed_order,
    suggest_publication_date,
)


def _meta(**kwargs) -> DocumentMeta:
    base = {"doc_id": "d", "source_path": "x.pdf", "file_type": "pdf"}
    base.update(kwargs)
    return DocumentMeta(**base)


# --------------------------------------------------------------------------
# F2 -- determine_chronological_order
# --------------------------------------------------------------------------


class TestKronolojikSira:
    def test_effective_date_e_gore_dogru_siralama(self):
        eski = _meta(doc_id="a", effective_date=date(2020, 1, 1))
        yeni = _meta(doc_id="b", effective_date=date(2023, 9, 1))

        sonuc = determine_chronological_order(yeni, eski)  # kasıtlı ters sıra

        assert sonuc.confidence == OrderConfidence.EFFECTIVE_DATE
        assert sonuc.older.doc_id == "a"
        assert sonuc.newer.doc_id == "b"
        assert sonuc.warning is None

    def test_effective_date_eksikken_publication_date_e_dusme(self):
        eski = _meta(doc_id="a", publication_date=date(2019, 11, 14))
        yeni = _meta(doc_id="b", publication_date=date(2023, 6, 1))

        sonuc = determine_chronological_order(eski, yeni)

        assert sonuc.confidence == OrderConfidence.PUBLICATION_DATE
        assert sonuc.older.doc_id == "a"
        assert sonuc.newer.doc_id == "b"

    def test_effective_date_esitse_publication_date_e_dusme(self):
        # NEDEN: effective_date AYIRT EDİCİ değilse (iki belge de aynı gün
        # yürürlüğe girmişse) bu, F2'nin "yoksa publication_date'e düş"
        # kuralının bir uzantısıdır -- ayırt edici olmayan bir eşitlik de
        # "yok" ile aynı muameleyi görmeli.
        ortak_yururluk = date(2024, 1, 1)
        eski = _meta(
            doc_id="a", effective_date=ortak_yururluk, publication_date=date(2023, 1, 1)
        )
        yeni = _meta(
            doc_id="b", effective_date=ortak_yururluk, publication_date=date(2023, 6, 1)
        )

        sonuc = determine_chronological_order(eski, yeni)

        assert sonuc.confidence == OrderConfidence.PUBLICATION_DATE
        assert sonuc.older.doc_id == "a"
        assert sonuc.newer.doc_id == "b"

    def test_celisen_sira_uyari_uretir(self):
        # a: yayımda ÖNCE ama yürürlükte SONRA -- çelişki.
        a = _meta(doc_id="a", publication_date=date(2019, 1, 1), effective_date=date(2024, 1, 1))
        b = _meta(doc_id="b", publication_date=date(2020, 1, 1), effective_date=date(2021, 1, 1))

        sonuc = determine_chronological_order(a, b)

        assert sonuc.confidence == OrderConfidence.CONFLICTING
        assert sonuc.older is None
        assert sonuc.newer is None
        assert sonuc.warning is not None

    def test_tarih_yokken_varsayim_yapilmaz(self):
        a = _meta(doc_id="a")
        b = _meta(doc_id="b")

        sonuc = determine_chronological_order(a, b)

        assert sonuc.confidence == OrderConfidence.UNKNOWN
        assert sonuc.older is None
        assert sonuc.newer is None
        assert sonuc.warning is not None


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
# F2 -- onay mekanizması (tahminden ayrı)
# --------------------------------------------------------------------------


class TestOnayMekanizmasi:
    def test_onaysiz_siparisle_analiz_baslamaz(self):
        with pytest.raises(OrderNotConfirmedError):
            require_confirmed_order(None)

    def test_onaylanmis_sira_kabul_edilir(self):
        a = _meta(doc_id="a")
        b = _meta(doc_id="b")
        onay = confirm_order(older=a, newer=b)

        assert isinstance(onay, ConfirmedOrder)
        assert require_confirmed_order(onay) is onay

    def test_ayni_belge_older_newer_olamaz(self):
        a = _meta(doc_id="a")
        with pytest.raises(ValueError):
            confirm_order(older=a, newer=a)


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
