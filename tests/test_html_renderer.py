"""
src/reporting/html_renderer.py testleri.

NEDEN Streamlit'e bağımlı DEĞİL: bu modül SAF HTML string üretir (Section/
SectionDiff girdisi, str çıktısı) -- Streamlit çalıştırmaya hiç gerek yok.
"""

from __future__ import annotations

import json

import pytest

from src.analysis.differ import DiffSentence, SectionDiff, SentenceDiff, WordDiff, diff_section_match
from src.analysis.section_matcher import SectionMatch, match_sections
from src.config import CHANGE_TYPE_LABELS_TR, COLOR_PALETTE, SAMPLES_DIR
from src.ingestion.pdf_loader import PDFLoader
from src.models import ChangeType, Section, TextUnit
from src.parsing.structure_parser import parse_structure
from src.reporting.html_renderer import (
    known_palette_keys,
    render_badge,
    render_change_type_badge,
    render_full_section_html,
    render_row_header_html,
    render_section_diff_html,
    render_sentence_diff,
    render_structural_badges,
    render_word_diffs,
)


def _unit(text: str) -> TextUnit:
    return TextUnit(
        doc_id="t", page_no=1, block_index=0, char_start=0, char_end=len(text), heading_path=(), text=text
    )


def _sentence(text: str) -> DiffSentence:
    return DiffSentence(units=[_unit(text)])


def _section(text: str, *, madde_no: int = 1) -> Section:
    return Section(
        doc_id="t",
        heading_path=(f"MADDE {madde_no}",),
        section_type="MADDE",
        madde_no=madde_no,
        baslik="X",
        order_index=0,
        units=[_unit(text)],
    )


class TestRenderWordDiffs:
    def test_equal_kelimeler_siniflandirilmis_span_almaz(self):
        html = render_word_diffs([WordDiff(op="equal", old_words=("a", "b"), new_words=("a", "b"))], "old")
        assert html == "a b"
        assert "mk-diff" not in html

    def test_insert_sadece_new_tarafinda_gorunur(self):
        wd = [WordDiff(op="insert", old_words=(), new_words=("yeni", "kelime"))]
        assert render_word_diffs(wd, "old") == ""
        new_html = render_word_diffs(wd, "new")
        assert 'class="mk-diff mk-diff-added"' in new_html
        assert "yeni kelime" in new_html

    def test_delete_sadece_old_tarafinda_gorunur(self):
        wd = [WordDiff(op="delete", old_words=("eski", "kelime"), new_words=())]
        assert render_word_diffs(wd, "new") == ""
        old_html = render_word_diffs(wd, "old")
        assert 'class="mk-diff mk-diff-removed"' in old_html
        assert "eski kelime" in old_html

    def test_replace_her_iki_tarafta_da_modified_sinifiyla_gorunur(self):
        wd = [WordDiff(op="replace", old_words=("eski",), new_words=("yeni",))]
        old_html = render_word_diffs(wd, "old")
        new_html = render_word_diffs(wd, "new")
        assert 'class="mk-diff mk-diff-modified"' in old_html and "eski" in old_html
        assert 'class="mk-diff mk-diff-modified"' in new_html and "yeni" in new_html

    def test_gecersiz_side_hata_verir(self):
        with pytest.raises(ValueError):
            render_word_diffs([], "eski")


class TestRenderSentenceDiff:
    def test_equal_iki_tarafta_da_duz_metin(self):
        sd = SentenceDiff(op="equal", old=_sentence("Aynı cümle."), new=_sentence("Aynı cümle."))
        assert render_sentence_diff(sd, "old") == "Aynı cümle."
        assert render_sentence_diff(sd, "new") == "Aynı cümle."

    def test_insert_sadece_new_tarafinda_gorunur(self):
        sd = SentenceDiff(op="insert", old=None, new=_sentence("Yeni cümle."))
        assert render_sentence_diff(sd, "old") == ""
        html = render_sentence_diff(sd, "new")
        assert 'mk-diff-added' in html and "Yeni cümle." in html

    def test_delete_sadece_old_tarafinda_gorunur(self):
        sd = SentenceDiff(op="delete", old=_sentence("Silinen cümle."), new=None)
        assert render_sentence_diff(sd, "new") == ""
        html = render_sentence_diff(sd, "old")
        assert "mk-diff-removed" in html and "Silinen cümle." in html

    def test_replace_kelime_duzeyine_deler(self):
        sd = SentenceDiff(
            op="replace",
            old=_sentence("Eski metin."),
            new=_sentence("Yeni metin."),
            word_diffs=[
                WordDiff(op="replace", old_words=("Eski",), new_words=("Yeni",)),
                WordDiff(op="equal", old_words=("metin.",), new_words=("metin.",)),
            ],
        )
        assert render_sentence_diff(sd, "old") == '<span class="mk-diff mk-diff-modified">Eski</span> metin.'
        assert render_sentence_diff(sd, "new") == '<span class="mk-diff mk-diff-modified">Yeni</span> metin.'

    def test_gecersiz_side_hata_verir(self):
        sd = SentenceDiff(op="equal", old=_sentence("x"), new=_sentence("x"))
        with pytest.raises(ValueError):
            render_sentence_diff(sd, "eski")


class TestHtmlKacirma:
    def test_ozel_karakterler_kacirilir(self):
        sd = SentenceDiff(op="equal", old=_sentence("<script>alert(1)</script> & \"veri\""), new=_sentence("x"))
        html = render_sentence_diff(sd, "old")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html

    def test_word_diff_kacirma(self):
        wd = [WordDiff(op="insert", old_words=(), new_words=("<b>vurgu</b>",))]
        html = render_word_diffs(wd, "new")
        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    def test_full_section_html_kacirma(self):
        section = _section("Kurum & Kuruluş <önemli>")
        html = render_full_section_html(section, ChangeType.REMOVED)
        assert "<önemli>" not in html
        assert "&lt;önemli&gt;" in html


class TestRenderFullSectionHtml:
    def test_removed_kirmizi_sinif_alir(self):
        html = render_full_section_html(_section("Kaldırılan madde metni."), ChangeType.REMOVED)
        assert 'mk-diff-removed' in html
        assert "Kaldırılan madde metni." in html

    def test_added_yesil_sinif_alir(self):
        html = render_full_section_html(_section("Eklenen madde metni."), ChangeType.ADDED)
        assert "mk-diff-added" in html

    def test_identical_sinifsiz_duz_metin(self):
        html = render_full_section_html(_section("Metin."), ChangeType.IDENTICAL)
        assert "mk-diff" not in html
        assert html == "Metin."


class TestRenderChangeTypeBadge:
    @pytest.mark.parametrize("change_type", list(ChangeType))
    def test_her_change_type_icin_dogru_sinif_ve_turkce_etiket(self, change_type):
        html = render_change_type_badge(change_type)
        assert f'mk-badge-{change_type.value.lower()}' in html
        assert CHANGE_TYPE_LABELS_TR[change_type.value] in html

    def test_known_palette_keys_icerik_durumu_ve_yapisal_bayraklari_kapsar(self):
        # NEDEN eşitlik DEĞİL alt küme kontrolü: COLOR_PALETTE artık 6
        # anahtar taşıyor -- 4'ü ChangeType (İÇERİK durumu), 2'si
        # ("RENUMBERED"/"MOVED") YAPISAL bayrak anahtarı (bkz. config.py
        # NEDEN notu, classifier.py) -- ikisi ARTIK aynı küme değil.
        assert {ct.value for ct in ChangeType} <= known_palette_keys()
        assert {"RENUMBERED", "MOVED"} <= known_palette_keys()
        assert known_palette_keys() == set(COLOR_PALETTE.keys())


class TestRenderStructuralBadges:
    """
    YAPISAL bayraklar (numarasi_degisti/yeri_degisti) İÇERİK durumundan
    BAĞIMSIZ rozetlerdir -- bkz. classifier.py NEDEN notu.
    """

    def test_ikisi_de_false_ise_bos_string(self):
        assert render_structural_badges(numarasi_degisti=False, yeri_degisti=False) == ""

    def test_sadece_numarasi_degisti(self):
        html = render_structural_badges(numarasi_degisti=True, yeri_degisti=False)
        assert "mk-badge-renumbered" in html
        assert CHANGE_TYPE_LABELS_TR["RENUMBERED"] in html
        assert "mk-badge-moved" not in html

    def test_sadece_yeri_degisti(self):
        html = render_structural_badges(numarasi_degisti=False, yeri_degisti=True)
        assert "mk-badge-moved" in html
        assert CHANGE_TYPE_LABELS_TR["MOVED"] in html
        assert "mk-badge-renumbered" not in html

    def test_ikisi_de_true_ise_iki_rozet_de_gorunur(self):
        html = render_structural_badges(numarasi_degisti=True, yeri_degisti=True)
        assert "mk-badge-renumbered" in html
        assert "mk-badge-moved" in html

    def test_render_badge_yapisal_anahtarla_da_calisir(self):
        # NEDEN: render_badge, ChangeType.value İLE de düz bir yapısal
        # bayrak anahtarıyla ("RENUMBERED"/"MOVED") DA çalışan tek bir
        # genel rozet fonksiyonudur (bkz. html_renderer.py NEDEN notu);
        # render_change_type_badge SADECE bunun ChangeType'a özel bir
        # sarmalayıcısıdır.
        assert render_change_type_badge(ChangeType.MODIFIED) == render_badge("MODIFIED")
        html = render_badge("MOVED")
        assert "mk-badge-moved" in html
        assert CHANGE_TYPE_LABELS_TR["MOVED"] in html


class TestRenderRowHeaderHtml:
    def _section(self, madde_no: int, baslik: str) -> Section:
        return Section(
            doc_id="t", heading_path=(f"MADDE {madde_no}",), section_type="MADDE",
            madde_no=madde_no, baslik=baslik, order_index=0, units=[],
        )

    def test_yapisal_bayrak_yoksa_sadece_icerik_rozeti_gorunur(self):
        old = self._section(1, "Amaç")
        html = render_row_header_html(old, old, ChangeType.IDENTICAL)
        assert "mk-badge-identical" in html
        assert "mk-badge-renumbered" not in html
        assert "mk-badge-moved" not in html

    def test_numarasi_degisti_ise_ikinci_rozet_de_eklenir(self):
        old = self._section(12, "Yürürlük")
        new = self._section(13, "Yürürlük")
        html = render_row_header_html(old, new, ChangeType.IDENTICAL, numarasi_degisti=True)
        assert "mk-badge-identical" in html
        assert "mk-badge-renumbered" in html

    def test_hem_icerik_hem_iki_yapisal_rozet_birlikte_gorunebilir(self):
        old = self._section(9, "Birim Sorumlulukları")
        new = self._section(8, "Birim Sorumlulukları")
        html = render_row_header_html(
            old, new, ChangeType.MODIFIED, numarasi_degisti=True, yeri_degisti=True
        )
        assert "mk-badge-modified" in html
        assert "mk-badge-renumbered" in html
        assert "mk-badge-moved" in html

    def test_baslik_kaciriliyor(self):
        old = self._section(1, "<script>alert(1)</script>")
        html = render_row_header_html(old, old, ChangeType.IDENTICAL)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestGercekOrnekBelgedeDiffRenderi:
    """ground_truth.json'daki bilinen senaryoların gerçek belgeler üzerinde doğru render edildiğini doğrular."""

    def _match(self, no: int) -> SectionMatch:
        doc19 = PDFLoader().load(SAMPLES_DIR / "yonetmelik_2019.pdf", doc_id="p19_html")
        doc23 = PDFLoader().load(SAMPLES_DIR / "yonetmelik_2023.pdf", doc_id="p23_html")
        result = match_sections(parse_structure(doc19), parse_structure(doc23))
        return next(m for m in result.matches if m.old.madde_no == no)

    def test_veri_paylasimi_fikra_1_modified_fikra_2_sinifsiz(self):
        section_diff = diff_section_match(self._match(6))
        old_html, new_html = render_section_diff_html(section_diff)

        assert "mk-diff-modified" in old_html
        assert "mk-diff-modified" in new_html
        assert "mk-diff-added" in new_html  # eklenen cümlecik
        assert "(2) Kişisel verilerin işlenmesinde ilgili mevzuat hükümlerine uyulur." in old_html
        assert "mk-diff" not in old_html.split("(2)")[1]  # fıkra (2) kısmı sınıfsız

    def test_identical_madde_hicbir_span_icermez(self):
        section_diff = diff_section_match(self._match(1))  # Amaç
        old_html, new_html = render_section_diff_html(section_diff)
        assert "<span" not in old_html
        assert "<span" not in new_html
        assert old_html == new_html
