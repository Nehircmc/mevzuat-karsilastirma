"""
differ.py + classifier.py (Adım 5) testleri.

Kritik özellik: yonetmelik_2019 -> yonetmelik_2023 gerçek örnek belge
çiftinde, ground_truth.json'daki HER maddenin ChangeType'ı OBJEKTİF olarak
doğrulanır -- gözle kontrol değil. Ayrıca ground_truth.json'un bilinçli
olarak içerdiği "sadece BİR fıkra değişti, madde TÜMÜYLE değişmiş
sayılmamalı" senaryoları (veri_paylasimi, veri_kalitesi) cümle-düzeyinde
doğrulanır.
"""

from __future__ import annotations

import json

import pytest

from src.analysis.classifier import (
    ClassifiedSection,
    char_similarity,
    classify_all,
    classify_content,
    is_moved,
    is_renumbered,
)
from src.analysis.differ import diff_section_match, diff_words, section_sentences
from src.analysis.section_matcher import SectionMatch, match_sections
from src.config import SAMPLES_DIR
from src.ingestion.docx_loader import DOCXLoader
from src.ingestion.pdf_loader import PDFLoader
from src.models import ChangeType, Section, TextUnit
from src.parsing.structure_parser import parse_structure

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)

_LOADERS = [
    ("pdf", PDFLoader, "yonetmelik_2019.pdf", "yonetmelik_2023.pdf"),
    ("docx", DOCXLoader, "yonetmelik_2019.docx", "yonetmelik_2023.docx"),
]


def _gercek_sections(loader_cls, filename: str, doc_id: str) -> list[Section]:
    doc = loader_cls().load(SAMPLES_DIR / filename, doc_id=doc_id)
    return parse_structure(doc)


def _unit(text: str, *, doc_id: str = "test", page_no: int | None = 1, block_index: int = 0) -> TextUnit:
    return TextUnit(
        doc_id=doc_id,
        page_no=page_no,
        block_index=block_index,
        char_start=0,
        char_end=len(text),
        heading_path=(),
        text=text,
    )


def _section(
    *,
    units: list[TextUnit],
    section_type: str = "MADDE",
    madde_no: int,
    baslik: str | None = "X",
    order_index: int = 0,
    heading_path: tuple[str, ...] = ("MADDE 1",),
    doc_id: str = "test",
) -> Section:
    return Section(
        doc_id=doc_id,
        heading_path=heading_path,
        section_type=section_type,
        madde_no=madde_no,
        baslik=baslik,
        order_index=order_index,
        units=units,
    )


class TestClassifyAllGroundTruthIleTamamenEsler:
    """
    En üst düzey regresyon: parse_structure -> match_sections -> classify_all
    ZİNCİRİNİN ürettiği İÇERİK durumu + YAPISAL bayraklar, ground_truth.json'daki
    HER maddeyle (madde_no bazında) BİREBİR eşleşmeli.

    NEDEN ground_truth.json'daki eski (6 değerli) "change_type" alanı BURADA
    İKİYE AYRIŞTIRILARAK yorumlanır (dosya DEĞİŞTİRİLMEDİ -- bkz. Adım 9 notu):
    ground_truth'taki "RENUMBERED" etiketi "içerik AYNI, numara FARKLI" anlamına
    gelir -- yeni modelde bu, content_status=IDENTICAL + numarasi_degisti=True
    olarak İKİ AYRI sinyale karşılık gelir. "numarası değişti mi" sorusunun
    cevabı zaten ground_truth'un KENDİ madde_no_2019/madde_no_2023 alanlarından
    DOĞRUDAN türetilebilir -- ayrı bir alan eklemeye gerek YOK.
    """

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_her_maddenin_icerik_durumu_ve_yapisal_bayraklari_ground_truth_ile_ayni(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_diff")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_diff")

        result = match_sections(old_sections, new_sections)
        classified = classify_all(result)

        # NEDEN hem 2019 HEM 2023 numarasına göre indeksleniyor: REMOVED bir
        # kayıtta sadece old (2019 no'su), ADDED'da sadece new (2023 no'su)
        # dolu -- iki ayrı anahtar uzayı gerekiyor.
        by_old_no = {c.old.madde_no: c for c in classified if c.old is not None}
        by_new_no = {c.new.madde_no: c for c in classified if c.new is not None and c.old is None}

        for m in _GROUND_TRUTH["maddeler"]:
            no_2019, no_2023 = m["madde_no_2019"], m["madde_no_2023"]
            if no_2019 is not None and no_2023 is not None:
                actual = by_old_no[no_2019]
                # "RENUMBERED"/"MOVED" etiketli maddeler İÇERİK olarak AYNIDIR
                # (bkz. sınıf NEDEN notu) -- sadece "MODIFIED"/"IDENTICAL"
                # etiketleri doğrudan içerik durumuna karşılık gelir.
                expected_content = (
                    ChangeType.IDENTICAL if m["change_type"] in ("IDENTICAL", "RENUMBERED", "MOVED")
                    else ChangeType(m["change_type"])
                )
                assert actual.change_type == expected_content, (
                    f"{m['id']}: beklenen içerik durumu {expected_content}, "
                    f"bulunan {actual.change_type} (2019 no {no_2019})"
                )
                expected_numarasi_degisti = no_2019 != no_2023
                assert actual.numarasi_degisti == expected_numarasi_degisti, (
                    f"{m['id']}: numarasi_degisti beklenen {expected_numarasi_degisti} "
                    f"(2019:{no_2019} -> 2023:{no_2023}), bulunan {actual.numarasi_degisti}"
                )
            elif no_2019 is not None:
                actual = by_old_no[no_2019]
                assert actual.change_type == ChangeType.REMOVED, f"{m['id']}: REMOVED bekleniyordu"
            else:
                actual = by_new_no[no_2023]
                assert actual.change_type == ChangeType.ADDED, f"{m['id']}: ADDED bekleniyordu"

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_classify_all_hicbir_sectioni_kaybetmez(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_diff")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_diff")

        result = match_sections(old_sections, new_sections)
        classified = classify_all(result)

        assert len(classified) == len(result.matches) + len(result.unmatched_old) + len(
            result.unmatched_new
        )
        assert len(old_sections) == sum(1 for c in classified if c.old is not None)
        assert len(new_sections) == sum(1 for c in classified if c.new is not None)


class TestDifferGercekOrnekFikraDuzeyi:
    """
    ground_truth.json'daki "sadece BİR fıkra değişti" senaryolarının, differ
    tarafından CÜMLE düzeyinde doğru ayrıştırıldığını doğrular.
    """

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_veri_paylasimi_sadece_fikra_1_replace_fikra_2_equal(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN kritik: ground_truth aciklaması -- "fıkra (1) hem cümle içi
        # ekleme HEM DE anlamın tersine dönmesi içeriyor; fıkra (2) ise
        # birebir aynı kalıyor -- differ'ın TÜM maddeyi değil sadece fıkra
        # (1)'i değişmiş sayması gerekir."
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_vp")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_vp")
        result = match_sections(old_sections, new_sections)
        match = next(m for m in result.matches if m.old.madde_no == 6)

        section_diff = diff_section_match(match)

        assert not section_diff.is_identical
        ops = [(sd.op, sd.old.text if sd.old else None) for sd in section_diff.sentence_diffs]
        fikra_1 = next(sd for sd in section_diff.sentence_diffs if sd.old and sd.old.text.startswith("(1)"))
        fikra_2 = next(sd for sd in section_diff.sentence_diffs if sd.old and sd.old.text.startswith("(2)"))
        assert fikra_1.op == "replace", f"fıkra (1) replace olmalıydı, ops={ops}"
        assert fikra_2.op == "equal", f"fıkra (2) equal olmalıydı, ops={ops}"

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_veri_paylasimi_kelime_duzeyinde_ekleme_ve_anlam_degisimi(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_vp2")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_vp2")
        result = match_sections(old_sections, new_sections)
        match = next(m for m in result.matches if m.old.madde_no == 6)

        section_diff = diff_section_match(match)
        fikra_1 = next(sd for sd in section_diff.sentence_diffs if sd.old and sd.old.text.startswith("(1)"))

        insert_ops = [wd for wd in fikra_1.word_diffs if wd.op == "insert"]
        assert any("Kurulunun" in wd.new_words for wd in insert_ops), "eklenen cümlecik bulunamadı"

        changed_word_ops = [wd for wd in fikra_1.word_diffs if wd.op != "equal" and wd.op != "insert"]
        assert any(
            "paylaşılamaz." in wd.old_words and "paylaşılabilir." in wd.new_words
            for wd in changed_word_ops
        ), "anlamı tersine çeviren kelime değişimi (paylaşılamaz->paylaşılabilir) bulunamadı"

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_veri_kalitesi_sadece_fikra_4_insert_digerleri_equal(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN kritik: "UZUN madde, fıkra (1)-(3) birebir aynı, sadece
        # fıkra (4) eklenmiş -- differ tüm maddeyi değişmiş saymamalı."
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_vk")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_vk")
        result = match_sections(old_sections, new_sections)
        match = next(m for m in result.matches if m.old.madde_no == 7)

        section_diff = diff_section_match(match)

        assert not section_diff.is_identical
        ops = [sd.op for sd in section_diff.sentence_diffs]
        assert ops == ["equal", "equal", "equal", "insert"], f"beklenmeyen op dizisi: {ops}"
        eklenen = next(sd for sd in section_diff.sentence_diffs if sd.op == "insert")
        assert eklenen.old is None
        assert "(4)" in eklenen.new.text

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_identical_madde_tum_cumleler_equal(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_id")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_id")
        result = match_sections(old_sections, new_sections)
        match = next(m for m in result.matches if m.old.madde_no == 1)  # Amaç

        section_diff = diff_section_match(match)

        assert section_diff.is_identical
        assert section_diff.sentence_diffs  # boş olmamalı
        # NEDEN: "equal" olarak hizalanan cümleler için word_diffs hiç
        # hesaplanmaz (bkz. diff_sentences), boş kalması beklenir.
        assert all(sd.word_diffs == [] for sd in section_diff.sentence_diffs)

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_renumbered_madde_metni_de_identical(self, fmt, loader_cls, dosya_2019, dosya_2023):
        # NEDEN: "numarası değişti" bayrağı SADECE numara değişimini ifade
        # eder, İÇERİK durumu (metnin sentence-diff düzeyinde birebir aynı
        # kalması) BAĞIMSIZ olarak ayrıca IDENTICAL olmalı.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_ren")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_ren")
        result = match_sections(old_sections, new_sections)
        match = next(m for m in result.matches if m.old.madde_no == 12)  # Yürürlük -> 13

        section_diff = diff_section_match(match)

        assert section_diff.is_identical
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_renumbered(match) is True


class TestDiffWords:
    def test_tamamen_ayni_cumlede_hepsi_equal(self):
        diffs = diff_words("Bu bir test cümlesidir.", "Bu bir test cümlesidir.")
        assert len(diffs) == 1
        assert diffs[0].op == "equal"

    def test_kelime_eklenmesi_insert_olarak_isaretlenir(self):
        diffs = diff_words("Kurum verileri paylaşılamaz.", "Kurum verileri kesinlikle paylaşılamaz.")
        insert_ops = [d for d in diffs if d.op == "insert"]
        assert len(insert_ops) == 1
        assert insert_ops[0].new_words == ("kesinlikle",)

    def test_kelime_degisimi_replace_olarak_isaretlenir(self):
        diffs = diff_words("Veri paylaşılamaz.", "Veri paylaşılabilir.")
        replace_ops = [d for d in diffs if d.op == "replace"]
        assert len(replace_ops) == 1
        assert replace_ops[0].old_words == ("paylaşılamaz.",)
        assert replace_ops[0].new_words == ("paylaşılabilir.",)


class TestSentenceBolmeSayfaSinirindaBirlesir:
    """
    NEDEN bu test grubu VAR: Adım 2'nin bıraktığı kritik not -- PDF'te
    reportlab bazen TEK bir cümleyi, sayfa/blok SINIRI olmadan bile, iki
    ayrı TextUnit'e bölebiliyor. section_sentences() bunu Section.units'i
    TEK TEK değil BİRLEŞTİRİLMİŞ metin üzerinden işleyerek engellemeli.
    """

    def test_iki_ayri_textunitten_gelen_yapay_bolunme_tek_cumle_kalir(self):
        # NEDEN nokta YOK ortada: gerçek bir cümle sonu değil, sadece bir
        # kelimenin ortasından (yapay olarak) iki TextUnit'e bölünmüş.
        u1 = _unit("Bu madde birinci ve", block_index=0)
        u2 = _unit("ikinci parçadan oluşur.", block_index=1)  # farklı blok, aynı gerçek cümle
        section = _section(units=[u1, u2], madde_no=1)

        sentences = section_sentences(section)

        assert len(sentences) == 1
        assert sentences[0].text == "Bu madde birinci ve ikinci parçadan oluşur."

    def test_boyle_bir_cumlenin_provenance_i_iki_orijinal_unitten_gelir(self):
        u1 = _unit("Bu madde birinci ve", block_index=0)
        u2 = _unit("ikinci parçadan oluşur.", block_index=1)
        section = _section(units=[u1, u2], madde_no=1)

        sentences = section_sentences(section)
        fragments = sentences[0].units

        assert len(fragments) == 2
        assert fragments[0].block_index == 0
        assert fragments[1].block_index == 1
        # NEDEN: her parçanın metni, KENDİ orijinal unit'inin char_start/
        # char_end aralığından GERİ okunabilmeli (Mimari İlke A).
        assert u1.text[fragments[0].char_start : fragments[0].char_end] == fragments[0].text
        assert u2.text[fragments[1].char_start : fragments[1].char_end] == fragments[1].text

    def test_gercek_sinir_iceren_iki_cumle_dogru_ayrilir(self):
        u1 = _unit("Birinci cümle burada biter.", block_index=0)
        u2 = _unit("İkinci cümle burada başlar.", block_index=1)
        section = _section(units=[u1, u2], madde_no=1)

        sentences = section_sentences(section)

        assert [s.text for s in sentences] == [
            "Birinci cümle burada biter.",
            "İkinci cümle burada başlar.",
        ]


class TestClassifierSentetikKenarDurumlari:
    """
    classify_content (İÇERİK durumu) + is_renumbered/is_moved (YAPISAL
    bayraklar) BAĞIMSIZ boyutlardır -- bkz. classifier.py NEDEN notu. Bu
    testler her fonksiyonu AYRI AYRI doğrular, AYRICA ikisinin AYNI ANDA
    True olabildiğini (birim_sorumlulukları senaryosu) özellikle test eder.
    """

    def _match(self, old: Section, new: Section) -> SectionMatch:
        return SectionMatch(old=old, new=new, method="NUMBER_AND_TITLE")

    def test_identical_ayni_numara_ayni_metin(self):
        old = _section(units=[_unit("Aynı metin.")], madde_no=1, order_index=0)
        new = _section(units=[_unit("Aynı metin.")], madde_no=1, order_index=0)
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_renumbered(match) is False
        assert is_moved(match) is False

    def test_modified_ayni_numara_farkli_metin(self):
        old = _section(units=[_unit("Eski içerik burada tamamen farklı bir şey anlatıyor.")], madde_no=1, order_index=0)
        new = _section(units=[_unit("Yeni içerik burada bambaşka bir konudan bahsediyor.")], madde_no=1, order_index=0)
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.MODIFIED
        assert is_renumbered(match) is False

    def test_sadece_numarasi_degisen_madde_icerik_olarak_identical_sayilir(self):
        # NEDEN kritik: eski modelde bu durum ayrı bir "RENUMBERED"
        # ChangeType'ıydı; yeni modelde İÇERİK durumu IDENTICAL'dır
        # (metin GERÇEKTEN değişmedi), numarasi_degisti bayrağı bunu AYRICA
        # işaretler -- ikisi BİRLİKTE "sadece numarası değişti" anlamını verir.
        old = _section(units=[_unit("Değişmeyen madde metni.")], madde_no=12, order_index=11)
        new = _section(units=[_unit("Değişmeyen madde metni.")], madde_no=13, order_index=12)
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_renumbered(match) is True

    def test_hem_numarasi_hem_icerigi_degisen_madde_ikisi_de_true(self):
        # NEDEN kritik (bu testin varlığı BİZZAT Adım 9'un konusu): bkz.
        # ground_truth.json/birim_sorumlulukları -- eski modelde numara
        # değişimi SESSİZCE KAYBOLUYORDU (satır sadece MODIFIED
        # sayılıyordu). Yeni modelde HER İKİ sinyal de AYRI AYRI true olmalı.
        old = _section(units=[_unit("Eski içerik burada tamamen farklı bir şey anlatıyor.")], madde_no=9, order_index=8)
        new = _section(units=[_unit("Yeni içerik burada bambaşka bir konudan bahsediyor.")], madde_no=8, order_index=7)
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.MODIFIED
        assert is_renumbered(match) is True

    def test_yeri_degisen_madde_farkli_bolum_icerik_identical_sayilir(self):
        old = _section(
            units=[_unit("Değişmeyen madde metni.")],
            madde_no=1,
            order_index=0,
            heading_path=("BİRİNCİ BÖLÜM", "MADDE 1"),
        )
        new = _section(
            units=[_unit("Değişmeyen madde metni.")],
            madde_no=1,
            order_index=0,
            heading_path=("İKİNCİ BÖLÜM", "MADDE 1"),
        )
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_moved(match) is True
        assert is_renumbered(match) is False

    def test_yeri_degisen_madde_buyuk_pozisyon_kaymasi(self):
        old = _section(units=[_unit("Değişmeyen madde metni.")], madde_no=1, order_index=0)
        new = _section(units=[_unit("Değişmeyen madde metni.")], madde_no=1, order_index=5)
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_moved(match) is True

    def test_kucuk_pozisyon_kaymasi_yeri_degisti_tetiklemez(self):
        # NEDEN: MOVED_MIN_POSITION_DELTA=3 -- eşiğin ALTINDAKİ kaymalar
        # (belge başına bir madde eklenmesi gibi doğal kaymalar) "yeri
        # değişti" sayılmamalı, yoksa bu bayrak anlamsızlaşır.
        old = _section(units=[_unit("Değişmeyen madde metni.")], madde_no=1, order_index=0)
        new = _section(units=[_unit("Değişmeyen madde metni.")], madde_no=1, order_index=2)
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_moved(match) is False

    def test_numarasi_hem_yeri_degisen_madde_ikisi_de_true(self):
        # NEDEN: bu iki bayrak da BİRBİRİNDEN bağımsızdır -- bir madde AYNI
        # ANDA hem numarası hem bölümü değişmiş olabilir.
        old = _section(
            units=[_unit("Değişmeyen madde metni.")],
            madde_no=5,
            order_index=4,
            heading_path=("BİRİNCİ BÖLÜM", "MADDE 5"),
        )
        new = _section(
            units=[_unit("Değişmeyen madde metni.")],
            madde_no=6,
            order_index=4,
            heading_path=("İKİNCİ BÖLÜM", "MADDE 6"),
        )
        match = self._match(old, new)
        assert classify_content(match) == ChangeType.IDENTICAL
        assert is_renumbered(match) is True
        assert is_moved(match) is True

    def test_removed_ve_added_classify_all_ile(self):
        from src.analysis.section_matcher import MatchResult

        removed = _section(units=[_unit("Kaldırılan madde.")], madde_no=8, order_index=7)
        added = _section(units=[_unit("Yeni eklenen madde.")], madde_no=10, order_index=9)
        result = MatchResult(matches=[], unmatched_old=[removed], unmatched_new=[added])

        classified = classify_all(result)

        assert len(classified) == 2
        removed_c = next(c for c in classified if c.change_type == ChangeType.REMOVED)
        added_c = next(c for c in classified if c.change_type == ChangeType.ADDED)
        assert removed_c.old is removed and removed_c.new is None
        assert added_c.new is added and added_c.old is None

    def test_classified_section_ikisi_de_none_ise_hata_verir(self):
        with pytest.raises(ValueError):
            ClassifiedSection(change_type=ChangeType.REMOVED, old=None, new=None)

    def test_char_similarity_ozdes_metin_bir(self):
        assert char_similarity("aynı metin.", "aynı metin.") == 1.0

    def test_char_similarity_bosluk_farki_normalize_ile_yok_sayilir(self):
        # NEDEN: normalize() çoklu boşluğu tek boşluğa indirger -- karakter
        # benzerliği bu YÜZEYSEL farktan etkilenmemeli.
        assert char_similarity("aynı   metin.", "aynı metin.") == 1.0
