"""
structure_parser.py testleri.

Kritik özellik: PDF ve DOCX'ten gerçek örnek belgeler üzerinde çıkarılan
madde numaraları/başlıkları/bölümleri, document_spec.py'den türetilen
ground_truth.json'a karşı OBJEKTİF olarak doğrulanır -- gözle kontrol değil.
"""

from __future__ import annotations

import json

import pytest

from src.config import SAMPLES_DIR
from src.ingestion.docx_loader import DOCXLoader
from src.ingestion.pdf_loader import PDFLoader
from src.models import Document, DocumentMeta, Section, TextUnit
from src.parsing.structure_parser import parse_structure

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)


def _beklenen_maddeler(year: int) -> dict[int, dict]:
    no_anahtari = f"madde_no_{year}"
    bolum_anahtari = f"bolum_{year}"
    beklenen: dict[int, dict] = {}
    for m in _GROUND_TRUTH["maddeler"]:
        no = m[no_anahtari]
        if no is not None:
            beklenen[no] = {"baslik": m["baslik"], "bolum": m[bolum_anahtari]}
    return beklenen


def _unit(text: str, **kwargs) -> TextUnit:
    defaults = dict(doc_id="test", page_no=1, block_index=0, char_start=0, heading_path=())
    defaults.update(kwargs)
    defaults["char_end"] = defaults["char_start"] + len(text)
    return TextUnit(text=text, **defaults)


def _belge(units: list[TextUnit]) -> Document:
    return Document(meta=DocumentMeta(doc_id="test", source_path="x", file_type="pdf"), units=units)


_VAKALAR = [
    (2019, PDFLoader, "yonetmelik_2019.pdf"),
    (2019, DOCXLoader, "yonetmelik_2019.docx"),
    (2023, PDFLoader, "yonetmelik_2023.pdf"),
    (2023, DOCXLoader, "yonetmelik_2023.docx"),
]


class TestGroundTruthKarsilastirmasi:
    @pytest.mark.parametrize("year,loader_cls,filename", _VAKALAR)
    def test_madde_sayisi_ve_basliklar_ground_truth_ile_esler(self, year, loader_cls, filename):
        doc = loader_cls().load(SAMPLES_DIR / filename, doc_id=f"{filename}_{year}")
        sections = parse_structure(doc)
        beklenen = _beklenen_maddeler(year)

        actual_by_no = {s.madde_no: s for s in sections}
        assert set(actual_by_no) == set(beklenen), (
            f"madde numaraları uyuşmuyor: beklenen={sorted(beklenen)} "
            f"bulunan={sorted(actual_by_no)}"
        )

        for no, exp in beklenen.items():
            section = actual_by_no[no]
            assert section.section_type == "MADDE"
            assert section.baslik == exp["baslik"], (
                f"MADDE {no} başlığı yanlış: {section.baslik!r} != {exp['baslik']!r}"
            )
            assert section.heading_path[0] == exp["bolum"], (
                f"MADDE {no} bölümü yanlış: {section.heading_path} (beklenen bölüm: {exp['bolum']!r})"
            )
            assert section.heading_path[-1] == f"MADDE {no}"
            assert section.units, f"MADDE {no} hiç gövde içeriği içermiyor"

    @pytest.mark.parametrize("year,loader_cls,filename", _VAKALAR)
    def test_order_index_belge_sirasiyla_tutarli(self, year, loader_cls, filename):
        doc = loader_cls().load(SAMPLES_DIR / filename, doc_id=f"{filename}_{year}")
        sections = parse_structure(doc)
        assert [s.order_index for s in sections] == list(range(len(sections)))


class TestSayfaSiniriBirlestirme:
    def test_veri_kalitesi_maddesi_tum_fikralari_iceriyor(self):
        doc = PDFLoader().load(SAMPLES_DIR / "yonetmelik_2019.pdf", doc_id="pdf_2019")
        sections = parse_structure(doc)
        veri_kalitesi = next(s for s in sections if s.madde_no == 7)

        joined = veri_kalitesi.joined_text
        assert "doğruluk, tutarlılık, güncellik" in joined
        assert "Veri kalitesinin sağlanmasından" in joined
        assert "Verilerin güvenliği" in joined

    def test_veri_kalitesi_maddesi_birden_fazla_sayfadan_geliyor(self):
        doc = PDFLoader().load(SAMPLES_DIR / "yonetmelik_2019.pdf", doc_id="pdf_2019")
        sections = parse_structure(doc)
        veri_kalitesi = next(s for s in sections if s.madde_no == 7)

        sayfalar = {u.page_no for u in veri_kalitesi.units}
        assert len(sayfalar) >= 2, "madde tek sayfada kalmış; sayfa bölme senaryosu test edilmiyor"


class TestHiyerarsi:
    def test_bolum_heading_pathe_yansiyor(self):
        doc = PDFLoader().load(SAMPLES_DIR / "yonetmelik_2019.pdf", doc_id="pdf_2019")
        sections = parse_structure(doc)
        veri_paylasimi = next(s for s in sections if s.madde_no == 6)
        assert veri_paylasimi.heading_path == ("İKİNCİ BÖLÜM", "MADDE 6")

    def test_gecici_madde_taniniyor(self):
        text = "GEÇİCİ MADDE 1- (1) Bu madde geçiş hükmüdür."
        doc = _belge([_unit(text)])

        sections = parse_structure(doc)

        assert len(sections) == 1
        assert sections[0].section_type == "GECICI_MADDE"
        assert sections[0].madde_no == 1
        assert sections[0].heading_path == ("GEÇİCİ MADDE 1",)
        assert sections[0].joined_text == "(1) Bu madde geçiş hükmüdür."

    def test_kisim_ve_bolum_birlikte_heading_pathe_yansiyor(self):
        units = [
            _unit("BİRİNCİ KISIM", block_index=0),
            _unit("BİRİNCİ BÖLÜM", block_index=1),
            _unit("Amaç", block_index=2),
            _unit("MADDE 1- (1) Test amacı.", block_index=3),
        ]
        doc = _belge(units)
        sections = parse_structure(doc)

        assert len(sections) == 1
        assert sections[0].heading_path == ("BİRİNCİ KISIM", "BİRİNCİ BÖLÜM", "MADDE 1")
        assert sections[0].baslik == "Amaç"

    def test_ayni_kisim_icindeki_yeni_bolum_kisimi_korur(self):
        # NEDEN: Türk mevzuat hiyerarşisi KISIM > BÖLÜM > MADDE'dir; bir
        # KISIM birden çok BÖLÜM içerebilir. Yeni bir BÖLÜM, içinde
        # bulunduğu KISIM bağlamını GEÇERSİZ KILMAMALI.
        units = [
            _unit("BİRİNCİ KISIM", block_index=0),
            _unit("BİRİNCİ BÖLÜM", block_index=1),
            _unit("MADDE 1- (1) Birinci madde.", block_index=2),
            _unit("İKİNCİ BÖLÜM", block_index=3),
            _unit("MADDE 2- (1) İkinci madde.", block_index=4),
        ]
        doc = _belge(units)
        sections = parse_structure(doc)

        assert sections[0].heading_path == ("BİRİNCİ KISIM", "BİRİNCİ BÖLÜM", "MADDE 1")
        assert sections[1].heading_path == ("BİRİNCİ KISIM", "İKİNCİ BÖLÜM", "MADDE 2")

    def test_yeni_kisim_eski_bolumu_sifirlar(self):
        # NEDEN: yeni bir KISIM, bir önceki KISIM'a ait BÖLÜM bağlamını
        # devralamaz -- o BÖLÜM artık kapsam dışıdır.
        units = [
            _unit("BİRİNCİ KISIM", block_index=0),
            _unit("BİRİNCİ BÖLÜM", block_index=1),
            _unit("MADDE 1- (1) Birinci madde.", block_index=2),
            _unit("İKİNCİ KISIM", block_index=3),
            _unit("MADDE 2- (1) İkinci madde.", block_index=4),
        ]
        doc = _belge(units)
        sections = parse_structure(doc)

        assert sections[1].heading_path == ("İKİNCİ KISIM", "MADDE 2")


class TestProvenanceIzlenebilirligi:
    @pytest.mark.parametrize("year,loader_cls,filename", _VAKALAR)
    def test_merged_birimlerin_offsetleri_orijinal_metne_geri_izlenebilir(
        self, year, loader_cls, filename
    ):
        doc = loader_cls().load(SAMPLES_DIR / filename, doc_id=f"{filename}_{year}")
        sections = parse_structure(doc)

        orijinal_by_key = {(u.doc_id, u.page_no, u.block_index): u for u in doc.units}

        for section in sections:
            for unit in section.units:
                kaynak = orijinal_by_key[(unit.doc_id, unit.page_no, unit.block_index)]
                assert kaynak.text[unit.char_start : unit.char_end] == unit.text
