"""TR kısaltma duyarlı cümle bölme."""

from __future__ import annotations

import re

from src.config import TR_ABBREVIATIONS
from src.models import TextUnit

_CUMLE_SONU_RE = re.compile(r"[.!?]+")
# NEDEN ayrı bir regex: config.py'deki TR_ABBREVIATIONS listesi SABİT
# kısaltmaları kapsar ama "A.", "B." gibi tek harfli kısaltmalar/liste
# işaretleri sonsuz sayıda olabilir -- genel bir desenle yakalanır.
_TEK_HARF_KISALTMA_RE = re.compile(r"^[A-ZÇĞİÖŞÜ]\.$")

_KISALTMA_KUMESI = set(TR_ABBREVIATIONS)


def _kelime_baslangicini_bul(text: str, pos: int) -> int:
    """pos'tan geriye giderek en yakın boşluğun HEMEN SONRASINI (kelime başını) bulur."""
    i = pos
    while i > 0 and not text[i - 1].isspace():
        i -= 1
    return i


def _kisaltma_mi(kelime: str) -> bool:
    return kelime in _KISALTMA_KUMESI or bool(_TEK_HARF_KISALTMA_RE.match(kelime))


def _birim_uret(unit: TextUnit, local_start: int, local_end: int) -> TextUnit:
    return TextUnit(
        doc_id=unit.doc_id,
        page_no=unit.page_no,
        block_index=unit.block_index,
        char_start=local_start,
        char_end=local_end,
        heading_path=unit.heading_path,
        text=unit.text[local_start:local_end],
    )


def split_sentences(unit: TextUnit) -> list[TextUnit]:
    """
    Bir TextUnit'in metnini TR-duyarlı biçimde cümlelere böler.

    NEDEN kısaltma kontrolü KELİME bazında (nokta bazında değil): "T.C."
    gibi birden fazla nokta içeren kısaltmalarda, her nokta ayrı ayrı değil,
    o noktanın ait olduğu TAM KELİME kısaltma listesine bakılarak
    değerlendirilir -- aksi halde "T.C." ortasındaki ilk nokta bile
    (kelimenin kendisi listede olsa dahi) yanlışlıkla cümle sonu sanılabilir.

    Üretilen her cümle, KENDİ ebeveyni olan `unit`e göre offset taşır
    (Mimari İlke A / provenance sözleşmesi).
    """
    text = unit.text
    n = len(text)
    sentences: list[TextUnit] = []
    start = 0

    for match in _CUMLE_SONU_RE.finditer(text):
        punct_end = match.end()
        word_start = _kelime_baslangicini_bul(text, match.start())
        word = text[word_start:punct_end]

        if _kisaltma_mi(word):
            continue

        # NEDEN ek güvence: gerçek bir cümle Türkçede büyük harfle başlar;
        # noktalamadan sonraki ilk harf küçükse (örn. bilinmeyen bir kısaltma
        # ya da liste öğesi devamıysa) muhtemelen hâlâ aynı cümledeyiz.
        rest = text[punct_end:].lstrip()
        if rest and rest[0].islower():
            continue

        sentence_text = text[start:punct_end]
        if sentence_text.strip():
            lstrip_count = len(sentence_text) - len(sentence_text.lstrip())
            rstrip_count = len(sentence_text) - len(sentence_text.rstrip())
            local_start = start + lstrip_count
            local_end = punct_end - rstrip_count
            sentences.append(_birim_uret(unit, local_start, local_end))
        start = punct_end

    tail = text[start:]
    if tail.strip():
        lstrip_count = len(tail) - len(tail.lstrip())
        rstrip_count = len(tail) - len(tail.rstrip())
        local_start = start + lstrip_count
        local_end = n - rstrip_count
        sentences.append(_birim_uret(unit, local_start, local_end))

    return sentences
