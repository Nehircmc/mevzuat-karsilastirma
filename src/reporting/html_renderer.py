"""
Adım 6: cümle/kelime diff sonuçlarını renkli HTML'e çevirir.

NEDEN sınıf (class) tabanlı, INLINE stil DEĞİL: renkler TEK KAYNAK olan
src/config.py::COLOR_PALETTE'ten src/ui/styles.py::generate_color_css() ile
üretilip SAYFAYA BİR KEZ enjekte edilir (bkz. styles.py); bu modül sadece
`.mk-diff-<key>` sınıflarını üretir. Inline stil kullanılsaydı her span aynı
renk bilgisini TEKRAR taşırdı (hem şişkinlik hem de olası tutarsızlık
kaynağı).

NEDEN HER metin html.escape() İLE KAÇIRILIYOR: gövde metni gerçek belge
içeriğidir (kullanıcının yüklediği PDF/DOCX'ten) -- "<", ">", "&" gibi
karakterler içerebilir; kaçırılmazsa hem HTML yapısı BOZULUR hem de
(yüklenen belge içeriği başka bir kullanıcıya gösteriliyorsa) bir HTML
enjeksiyonu oluşabilir.
"""

from __future__ import annotations

from html import escape as _escape

from src.analysis.differ import SectionDiff, SentenceDiff, WordDiff
from src.config import CHANGE_TYPE_LABELS_TR, COLOR_PALETTE
from src.models import ChangeType, Section

# NEDEN sadece bu üçü: cümle/kelime düzeyinde vurgulama SADECE "bu parça
# eklendi/silindi/değişti" diyebilir -- IDENTICAL/MOVED/RENUMBERED tüm bir
# Section'ın SINIFI'dır (bkz. render_change_type_badge), tek bir kelime/
# cümle parçasının etiketi OLAMAZ.
_DIFF_CSS_KEYS = {
    "insert": "added",
    "delete": "removed",
    "replace": "modified",
}


def _css_key(change_type_value: str) -> str:
    return change_type_value.lower()


def _span(text: str, css_key: str | None) -> str:
    """Metni kaçırır (escape) ve (varsa) bir `.mk-diff-<css_key>` span'ine sarar."""
    escaped = _escape(text)
    if not escaped:
        return ""
    if css_key is None:
        return escaped
    return f'<span class="mk-diff mk-diff-{css_key}">{escaped}</span>'


def render_word_diffs(word_diffs: list[WordDiff], side: str) -> str:
    """
    Bir "replace" olarak hizalanmış cümle çiftinin KELİME düzeyinde diff'ini,
    verilen tarafa ("old" | "new") göre render eder.

    NEDEN "insert" sadece "new" tarafında, "delete" sadece "old" tarafında
    görünür: bir kelime insert'i tanım gereği SADECE yeni metinde vardır (old
    tarafında gösterecek bir şey yok), delete'in tam tersi.
    """
    if side not in ("old", "new"):
        raise ValueError(f"side 'old' veya 'new' olmalı, alınan: {side!r}")

    parts: list[str] = []
    for wd in word_diffs:
        if wd.op == "equal":
            words = wd.old_words if side == "old" else wd.new_words
            parts.append(_span(" ".join(words), None))
        elif wd.op == "insert":
            if side == "new":
                parts.append(_span(" ".join(wd.new_words), "added"))
        elif wd.op == "delete":
            if side == "old":
                parts.append(_span(" ".join(wd.old_words), "removed"))
        elif wd.op == "replace":
            words = wd.old_words if side == "old" else wd.new_words
            parts.append(_span(" ".join(words), "modified"))
        else:  # pragma: no cover - difflib bu dört etiket dışında bir şey üretmez
            raise AssertionError(f"beklenmeyen word diff opcode'u: {wd.op!r}")
    return " ".join(p for p in parts if p)


def render_sentence_diff(sentence_diff: SentenceDiff, side: str) -> str:
    """Tek bir SentenceDiff'i verilen tarafa göre render eder (boş olabilir, örn. old tarafında bir 'insert')."""
    if side not in ("old", "new"):
        raise ValueError(f"side 'old' veya 'new' olmalı, alınan: {side!r}")

    if sentence_diff.op == "equal":
        sentence = sentence_diff.old if side == "old" else sentence_diff.new
        return _span(sentence.text, None) if sentence else ""

    if sentence_diff.op == "insert":
        if side != "new" or sentence_diff.new is None:
            return ""
        return _span(sentence_diff.new.text, _DIFF_CSS_KEYS["insert"])

    if sentence_diff.op == "delete":
        if side != "old" or sentence_diff.old is None:
            return ""
        return _span(sentence_diff.old.text, _DIFF_CSS_KEYS["delete"])

    if sentence_diff.op == "replace":
        return render_word_diffs(sentence_diff.word_diffs, side)

    raise AssertionError(f"beklenmeyen sentence diff opcode'u: {sentence_diff.op!r}")  # pragma: no cover


def render_section_diff_html(section_diff: SectionDiff) -> tuple[str, str]:
    """Bir SectionDiff'in TAMAMINI (old_html, new_html) çifti olarak render eder (yan yana görünüm için)."""
    old_parts = [render_sentence_diff(sd, "old") for sd in section_diff.sentence_diffs]
    new_parts = [render_sentence_diff(sd, "new") for sd in section_diff.sentence_diffs]
    old_html = " ".join(p for p in old_parts if p)
    new_html = " ".join(p for p in new_parts if p)
    return old_html, new_html


def render_full_section_html(section: Section, change_type: ChangeType) -> str:
    """
    Karşılığı OLMAYAN (SectionDiff üretilemeyen) bir Section'ı -- REMOVED
    (sadece eski tarafta) veya ADDED (sadece yeni tarafta) -- TÜM metnini
    tek bir renkte render eder.
    """
    if change_type == ChangeType.REMOVED:
        css_key = "removed"
    elif change_type == ChangeType.ADDED:
        css_key = "added"
    else:
        css_key = None
    return _span(section.joined_text, css_key)


def render_change_type_badge(change_type: ChangeType) -> str:
    """Bir ChangeType için Türkçe etiketli, renkli bir rozet (badge) span'i üretir."""
    css_key = _css_key(change_type.value)
    label = CHANGE_TYPE_LABELS_TR[change_type.value]
    return f'<span class="mk-badge mk-badge-{css_key}">{_escape(label)}</span>'


def known_palette_keys() -> frozenset[str]:
    """COLOR_PALETTE'teki tüm anahtarları döndürür (testler için -- kapsam tamlığı kontrolü)."""
    return frozenset(COLOR_PALETTE.keys())
