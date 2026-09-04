"""
section_matcher.py (Adım 3 -- Matcher L1) testleri.

Kritik özellik: yonetmelik_2019 -> yonetmelik_2023 gerçek örnek belge
çiftinde çıkarılan eşleşmeler, ground_truth.json'a karşı OBJEKTİF olarak
doğrulanır. ground_truth.json bilinçli olarak şu tuzakları içeriyor:
- aynı madde_no'nun İKİ FARKLI maddeye ait olması (2019 MADDE 8 "Arşivleme
  Esasları" kaldırılınca 2023 MADDE 8 "Birim Sorumlulukları" olur) --
  saf numara eşleştirmesi bunu YANLIŞ eşleştirir, L1 başlık çelişkisiyle
  bunu engellemeli.
- numarası kayan ama metni/başlığı aynı kalan maddeler (RENUMBERED) --
  L1 bunları başlık eşliğiyle yakalamalı.
"""

from __future__ import annotations

import json

import pytest

from src.analysis.section_matcher import MatchResult, SectionMatch, match_sections
from src.config import SAMPLES_DIR
from src.ingestion.docx_loader import DOCXLoader
from src.ingestion.pdf_loader import PDFLoader
from src.models import Section
from src.parsing.structure_parser import parse_structure

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)


def _section(
    *,
    section_type: str = "MADDE",
    madde_no: int | None,
    baslik: str | None,
    order_index: int = 0,
    doc_id: str = "test",
) -> Section:
    heading_label = f"{'GEÇİCİ MADDE' if section_type == 'GECICI_MADDE' else 'MADDE'} {madde_no}"
    return Section(
        doc_id=doc_id,
        heading_path=(heading_label,),
        section_type=section_type,
        madde_no=madde_no,
        baslik=baslik,
        order_index=order_index,
        units=[],
    )


_LOADERS = [
    ("pdf", PDFLoader, "yonetmelik_2019.pdf", "yonetmelik_2023.pdf"),
    ("docx", DOCXLoader, "yonetmelik_2019.docx", "yonetmelik_2023.docx"),
]


def _gercek_sections(loader_cls, filename: str, doc_id: str) -> list[Section]:
    doc = loader_cls().load(SAMPLES_DIR / filename, doc_id=doc_id)
    return parse_structure(doc)


class TestGroundTruthKarsilastirmasi:
    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_eslesen_ciftler_ground_truth_ile_ayni(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        actual_pairs = {(m.old.madde_no, m.new.madde_no) for m in result.matches}
        expected_pairs = {
            (m["madde_no_2019"], m["madde_no_2023"])
            for m in _GROUND_TRUTH["maddeler"]
            if m["madde_no_2019"] is not None and m["madde_no_2023"] is not None
        }
        assert actual_pairs == expected_pairs

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_kaldirilan_madde_unmatched_old_da(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        expected_removed_no = {
            m["madde_no_2019"]
            for m in _GROUND_TRUTH["maddeler"]
            if m["madde_no_2019"] is not None and m["madde_no_2023"] is None
        }
        assert {s.madde_no for s in result.unmatched_old} == expected_removed_no

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_eklenen_madde_unmatched_new_de(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        expected_added_no = {
            m["madde_no_2023"]
            for m in _GROUND_TRUTH["maddeler"]
            if m["madde_no_2023"] is not None and m["madde_no_2019"] is None
        }
        assert {s.madde_no for s in result.unmatched_new} == expected_added_no

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_renumbered_madde_title_only_ile_esleniyor(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN: "Yürürlük"/"Yürütme" gibi numarası kayan ama başlığı/metni
        # aynı kalan maddeler, NUMBER_AND_TITLE geçişinde YAKALANAMAZ (farklı
        # numara) -- TITLE_ONLY geçişiyle bulunmalı.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        renumbered_no_2019 = {
            m["madde_no_2019"]
            for m in _GROUND_TRUTH["maddeler"]
            if m["change_type"] == "RENUMBERED"
        }
        for match in result.matches:
            if match.old.madde_no in renumbered_no_2019:
                assert match.method == "TITLE_ONLY", (
                    f"MADDE {match.old.madde_no}: RENUMBERED madde TITLE_ONLY ile "
                    f"eşleşmeliydi, {match.method} ile eşleşti"
                )

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_ayni_numarali_farkli_madde_baslik_celismesiyle_engellenir(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN (kritik test): 2019 MADDE 8 "Arşivleme Esasları" kaldırılınca
        # 2023 MADDE 8 "Birim Sorumlulukları" olur -- saf numara eşleştirmesi
        # bu ikisini YANLIŞ eşleştirir. L1 bunu başlık çelişkisiyle
        # engellemeli ve gerçek karşılığı (2023 MADDE 9, aynı başlık) bulmalı.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        birim_match = next(m for m in result.matches if m.old.baslik == "Birim Sorumlulukları")
        assert birim_match.old.madde_no == 9
        assert birim_match.new.madde_no == 8
        assert birim_match.method == "TITLE_ONLY"

        arsivleme = next(s for s in result.unmatched_old if s.baslik == "Arşivleme Esasları")
        assert arsivleme.madde_no == 8


class TestSentetikKenarDurumlari:
    def test_ayni_numara_ayni_baslik_number_and_title_ile_esler(self):
        old = [_section(madde_no=1, baslik="Amaç", order_index=0)]
        new = [_section(madde_no=1, baslik="Amaç", order_index=0)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "NUMBER_AND_TITLE"
        assert not result.unmatched_old
        assert not result.unmatched_new

    def test_ayni_numara_farkli_baslik_eslesmez(self):
        old = [_section(madde_no=8, baslik="Arşivleme Esasları", order_index=0)]
        new = [_section(madde_no=8, baslik="Birim Sorumlulukları", order_index=0)]

        result = match_sections(old, new)

        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == new

    def test_farkli_numara_ayni_baslik_title_only_ile_esler(self):
        old = [_section(madde_no=12, baslik="Yürürlük", order_index=11)]
        new = [_section(madde_no=13, baslik="Yürürlük", order_index=12)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "TITLE_ONLY"
        assert result.matches[0].old.madde_no == 12
        assert result.matches[0].new.madde_no == 13

    def test_baslik_buyuk_kucuk_harf_ve_bosluk_farkina_duyarsiz(self):
        old = [_section(madde_no=1, baslik="  Amaç  ", order_index=0)]
        new = [_section(madde_no=2, baslik="AMAÇ", order_index=0)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "TITLE_ONLY"

    def test_baslik_yoksa_sadece_numaraya_gore_esler(self):
        old = [_section(madde_no=1, baslik=None, order_index=0)]
        new = [_section(madde_no=1, baslik=None, order_index=0)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "NUMBER_AND_TITLE"

    def test_iki_tarafta_da_tekrar_eden_baslik_belirsizse_eslesmez(self):
        # NEDEN: aynı başlık her iki tarafta da BİRDEN FAZLA kez geçiyorsa
        # hangi çiftin doğru olduğu belirsizdir -- L1 KESMEZ.
        old = [
            _section(madde_no=1, baslik="Genel Hükümler", order_index=0),
            _section(madde_no=2, baslik="Genel Hükümler", order_index=1),
        ]
        new = [
            _section(madde_no=3, baslik="Genel Hükümler", order_index=0),
            _section(madde_no=4, baslik="Genel Hükümler", order_index=1),
        ]

        result = match_sections(old, new)

        assert result.matches == []
        assert len(result.unmatched_old) == 2
        assert len(result.unmatched_new) == 2

    def test_gecici_madde_normal_madde_ile_ayni_numara_olsa_bile_karismaz(self):
        old = [
            _section(section_type="MADDE", madde_no=1, baslik="Amaç", order_index=0),
            _section(section_type="GECICI_MADDE", madde_no=1, baslik=None, order_index=1),
        ]
        new = [
            _section(section_type="GECICI_MADDE", madde_no=1, baslik=None, order_index=0),
        ]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].old.section_type == "GECICI_MADDE"
        assert result.unmatched_old == [old[0]]

    def test_bos_listeler_hersey_unmatched(self):
        old = [_section(madde_no=1, baslik="Amaç", order_index=0)]
        result = match_sections(old, [])
        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == []

    def test_sonuc_tipleri(self):
        result = match_sections([], [])
        assert isinstance(result, MatchResult)
        assert result.matches == []

    def test_matches_old_order_indexe_gore_sirali(self):
        old = [
            _section(madde_no=3, baslik="Üçüncü", order_index=2),
            _section(madde_no=1, baslik="Birinci", order_index=0),
            _section(madde_no=2, baslik="İkinci", order_index=1),
        ]
        new = [
            _section(madde_no=3, baslik="Üçüncü", order_index=2),
            _section(madde_no=1, baslik="Birinci", order_index=0),
            _section(madde_no=2, baslik="İkinci", order_index=1),
        ]

        result = match_sections(old, new)

        assert [m.old.order_index for m in result.matches] == [0, 1, 2]

    def test_section_match_dataclass_alanlari(self):
        old = _section(madde_no=1, baslik="Amaç", order_index=0)
        new = _section(madde_no=1, baslik="Amaç", order_index=0)
        m = SectionMatch(old=old, new=new, method="NUMBER_AND_TITLE")
        assert m.old is old
        assert m.new is new
        assert m.method == "NUMBER_AND_TITLE"
