"""
Ingestion katmanı testleri: PDF/DOCX'ten çıkarılan metnin kayıpsızlığı,
sayfa numaralarının doğruluğu, Türkçe karakterlerin bozulmadığı, üstbilgi/
altbilginin gövdeye sızmadığı ve iki formatın eşdeğer metin verdiği.
"""

from __future__ import annotations

import docx as docx_lib
import pymupdf
import pytest

from data.samples.document_spec import KURUM_ADI
from data.samples.generate_samples import _turkish_upper
from src.config import PAGE_NUMBER_FOOTER_PATTERN, SAMPLES_DIR
from src.ingestion.base import NoTextLayerError
from src.ingestion.docx_loader import DOCXLoader
from src.ingestion.factory import get_loader
from src.ingestion.pdf_loader import PDFLoader
from src.parsing.normalizer import normalize

PDF_2019 = SAMPLES_DIR / "yonetmelik_2019.pdf"
DOCX_2019 = SAMPLES_DIR / "yonetmelik_2019.docx"

# NEDEN büyük/küçük ayrımı yapmıyoruz: fixture metninde her özel Türkçe
# harfin HER İKİ formu da doğal olarak geçmeyebilir (örn. metinde "Ş" hiç
# geçmeyebilir, sadece "ş" geçer) -- asıl test edilmesi gereken, bu harflerin
# (hangi formda olursa olsun) kodlama sırasında BOZULMADIĞIDIR.
_TURKCE_TEMEL_HARFLER = "çğıöşü"
_HEADER_METNI = f"T.C. {_turkish_upper(KURUM_ADI)}"


def _joined_normalized_text(units) -> str:
    """Tüm birimlerin metnini sırayla birleştirip boşluk normalizasyonu uygular."""
    joined = " ".join(u.text for u in units)
    return normalize(joined).normalized


class TestPDFLoader:
    def test_provenance_alanlari_dolu(self):
        doc = PDFLoader().load(PDF_2019, doc_id="pdf_2019")
        assert doc.units, "hiç birim çıkarılmamış"
        for unit in doc.units:
            assert unit.doc_id == "pdf_2019"
            assert unit.page_no is not None and unit.page_no >= 1
            assert unit.char_end - unit.char_start == len(unit.text)

    def test_madde_metni_dogru_cikariliyor(self):
        doc = PDFLoader().load(PDF_2019, doc_id="pdf_2019")
        full_text = " ".join(u.text for u in doc.units)
        assert "MADDE 1-" in full_text
        assert "Bu Yönetmeliğin amacı" in full_text

    def test_ustbilgi_altbilgi_govdeye_sizmiyor(self):
        doc = PDFLoader().load(PDF_2019, doc_id="pdf_2019")
        for unit in doc.units:
            assert _HEADER_METNI not in unit.text
            assert not PAGE_NUMBER_FOOTER_PATTERN.match(unit.text.strip())

    def test_sayfalar_arasi_bolunen_madde_iki_sayfaya_yayilir(self):
        # NEDEN: "Veri Kalitesi ve Güvenliği" maddesi generate_samples.py'de
        # kasıtlı olarak sayfa sınırında bölündü; ingestion bunu TEK bir
        # birimde toplamamalı -- bölünmüş haliyle çıkarmalı (birleştirme
        # işi Adım 2'nin structure_parser'ına ait).
        doc = PDFLoader().load(PDF_2019, doc_id="pdf_2019")
        eslesen_sayfalar = {
            u.page_no
            for u in doc.units
            if "Kurumsal veriler, doğruluk" in u.text
            or "Veri kalitesinin sağlanmasından" in u.text
        }
        assert len(eslesen_sayfalar) >= 2, "madde aynı sayfada kalmış, sayfa bölme testi çalışmadı"

    def test_turkce_karakterler_bozulmuyor(self):
        doc = PDFLoader().load(PDF_2019, doc_id="pdf_2019")
        full_text = " ".join(u.text for u in doc.units).casefold()
        for ch in _TURKCE_TEMEL_HARFLER:
            assert ch in full_text, f"'{ch}' harfi PDF çıktısında bulunamadı"

    def test_metin_katmani_olmayan_pdf_hata_verir(self, tmp_path):
        # NEDEN: OCR/taranmış PDF'i simüle etmek için sadece bir dikdörtgen
        # içeren, hiç metin katmanı olmayan bir PDF üretiyoruz.
        taranmis_pdf = tmp_path / "taranmis.pdf"
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
        pdf.save(taranmis_pdf)
        pdf.close()

        with pytest.raises(NoTextLayerError):
            PDFLoader().load(taranmis_pdf, doc_id="taranmis")


class TestDOCXLoader:
    def test_provenance_alanlari_dolu(self):
        doc = DOCXLoader().load(DOCX_2019, doc_id="docx_2019")
        assert doc.units
        for unit in doc.units:
            assert unit.doc_id == "docx_2019"
            assert unit.page_no is None  # DOCX'te sayfa kavramı yok
            assert unit.char_end - unit.char_start == len(unit.text)

    def test_ustbilgi_altbilgi_govdeye_sizmiyor(self):
        doc = DOCXLoader().load(DOCX_2019, doc_id="docx_2019")
        for unit in doc.units:
            assert _HEADER_METNI not in unit.text
            assert "— Sayfa" not in unit.text

    def test_heading_style_ipuclari_kaydediliyor(self):
        doc = DOCXLoader().load(DOCX_2019, doc_id="docx_2019")
        styles_found = set(doc.heading_style_hints.values())
        assert "Title" in styles_found
        assert "Heading 1" in styles_found
        assert "Heading 2" in styles_found

        amac_index = next(i for i, u in enumerate(doc.units) if u.text == "Amaç")
        assert doc.heading_style_hints[amac_index] == "Heading 2"

    def test_turkce_karakterler_bozulmuyor(self):
        doc = DOCXLoader().load(DOCX_2019, doc_id="docx_2019")
        full_text = " ".join(u.text for u in doc.units).casefold()
        for ch in _TURKCE_TEMEL_HARFLER:
            assert ch in full_text, f"'{ch}' harfi DOCX çıktısında bulunamadı"

    def test_metin_katmani_olmayan_docx_hata_verir(self, tmp_path):
        bos_docx = tmp_path / "bos.docx"
        docx_lib.Document().save(bos_docx)

        with pytest.raises(NoTextLayerError):
            DOCXLoader().load(bos_docx, doc_id="bos")


class TestFactory:
    def test_uzantiya_gore_loader_secimi(self):
        assert isinstance(get_loader(PDF_2019), PDFLoader)
        assert isinstance(get_loader(DOCX_2019), DOCXLoader)

    def test_desteklenmeyen_uzanti_hata_verir(self):
        with pytest.raises(ValueError):
            get_loader("belge.doc")


class TestPDFDOCXEsdegerligi:
    def test_govde_metni_iki_formatta_esdeger(self):
        # NEDEN kritik test: PDF ve DOCX loader'ları TAMAMEN FARKLI
        # kütüphaneler ve blok/paragraf sınırları kullanır; ama aynı
        # kaynak belgeden üretildikleri için düz metin içerikleri (boşluk
        # normalizasyonundan sonra) BİREBİR aynı olmalıdır.
        pdf_doc = PDFLoader().load(PDF_2019, doc_id="pdf_2019")
        docx_doc = DOCXLoader().load(DOCX_2019, doc_id="docx_2019")

        pdf_text = _joined_normalized_text(pdf_doc.units)
        docx_text = _joined_normalized_text(docx_doc.units)

        assert pdf_text == docx_text
