"""
Adım 5: eşleşen Section çiftleri arasında cümle ve kelime seviyesinde diff.

Çalışma sırası, bir Section'ın gövde metnini üretir (bkz. _joined_with_unit_bounds),
bu BİRLEŞTİRİLMİŞ metin üzerinde cümle sınırlarını bulur (find_sentence_spans),
cümle DİZİLERİNİ difflib.SequenceMatcher ile hizalar (equal/replace/insert/delete),
ve "replace" olarak hizalanan her cümle çiftini KELİME seviyesinde tekrar
difflib.SequenceMatcher'a sokar.

NEDEN cümle bölme Section.units'teki HER TextUnit'i AYRI AYRI değil,
BİRLEŞTİRİLMİŞ metin üzerinde çalışır (bkz. _joined_with_unit_bounds): PDF'te
reportlab bazen TEK bir paragrafın satır kaydırmasını sayfa/blok SINIRI
olmadan bile iki ayrı TextUnit'e bölebiliyor (bkz. README "Adım 3'e
başlarken" notu, örn. "Veri Paylaşımı" madde 6 fıkra 1). Eğer her TextUnit
ayrı ayrı cümlelere bölünseydi, bu tür bir yapay bölünme gerçek bir cümleyi
yanlışlıkla İKİ parçaya ayırır ve differ, GERÇEKTE değişmemiş bir cümleyi
"kısmen değişti" sanırdı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from src.analysis.section_matcher import SectionMatch
from src.models import Section, TextUnit
from src.parsing.normalizer import normalize
from src.parsing.sentence_splitter import find_sentence_spans


@dataclass(frozen=True)
class DiffSentence:
    """
    Bir Section içindeki TEK bir cümle -- Section'ın kendisi gibi (bkz.
    models.Section), provenance'ı bir VEYA DAHA FAZLA orijinal TextUnit
    parçasından oluşan bir units listesiyle taşır. NEDEN birden fazla
    olabilir: modül docstring'indeki sayfa/blok-içi kırılma senaryosunda,
    TEK bir gerçek cümle iki farklı orijinal TextUnit'ten gelen metinlerin
    birleşiminden oluşabilir.
    """

    units: list[TextUnit]

    @property
    def text(self) -> str:
        return " ".join(u.text for u in self.units)


@dataclass(frozen=True)
class WordDiff:
    """
    İki cümle arasındaki kelime düzeyinde TEK bir difflib opcode'u.

    op: "equal" | "replace" | "delete" | "insert" -- difflib.SequenceMatcher
    opcode etiketleriyle BİREBİR aynı (kapalı küme, ekstra bir çeviri
    katmanı gerektirmiyor).
    """

    op: str
    old_words: tuple[str, ...]
    new_words: tuple[str, ...]


@dataclass(frozen=True)
class SentenceDiff:
    """
    Bir cümle hizalama adımı: "equal" ise old/new AYNI cümledir (ikisi de
    dolu); "replace" ise old/new FARKLI ama karşılık gelen cümlelerdir
    (ikisi de dolu, word_diffs doldurulur); "delete" sadece old'da,
    "insert" sadece new'de vardır (diğeri None).
    """

    op: str  # "equal" | "replace" | "delete" | "insert"
    old: DiffSentence | None
    new: DiffSentence | None
    word_diffs: list[WordDiff] = field(default_factory=list)


@dataclass(frozen=True)
class SectionDiff:
    """Bir SectionMatch için üretilen TAM cümle-diff sonucu."""

    match: SectionMatch
    sentence_diffs: list[SentenceDiff]

    @property
    def is_identical(self) -> bool:
        """TÜM cümleler "equal" ise (kelime kelime birebir aynıysa) True."""
        return all(sd.op == "equal" for sd in self.sentence_diffs)


def _joined_with_unit_bounds(section: Section) -> tuple[str, list[tuple[TextUnit, int, int]]]:
    """
    Section.joined_text ile AYNI birleştirilmiş metni üretir (units'i " "
    ile birleştirir) VE her unit'in bu birleştirilmiş metin içindeki
    [start, end) aralığını döndürür -- NEDEN: bu aralıklar sayesinde
    birleştirilmiş metindeki HERHANGİ bir [start, end) aralığı (bir cümle,
    bir kelime diff'i), _span_to_units() ile orijinal TextUnit'lere GERİ
    izlenebilir (Mimari İlke A).
    """
    parts: list[str] = []
    bounds: list[tuple[TextUnit, int, int]] = []
    pos = 0
    for i, unit in enumerate(section.units):
        if i > 0:
            parts.append(" ")
            pos += 1
        start = pos
        parts.append(unit.text)
        pos += len(unit.text)
        bounds.append((unit, start, pos))
    return "".join(parts), bounds


def _span_to_units(
    bounds: list[tuple[TextUnit, int, int]], start: int, end: int
) -> list[TextUnit]:
    """
    Birleştirilmiş metindeki [start, end) aralığını, üst üste düştüğü HER
    unit için kendi char_start/char_end'ine göre doğru ofsetli bir TextUnit
    parçasına çevirir (birden fazla unit'e yayılıyorsa birden fazla parça
    döner -- bkz. DiffSentence NEDEN notu).
    """
    fragments: list[TextUnit] = []
    for unit, u_start, u_end in bounds:
        overlap_start = max(start, u_start)
        overlap_end = min(end, u_end)
        if overlap_start >= overlap_end:
            continue
        local_start = unit.char_start + (overlap_start - u_start)
        local_end = unit.char_start + (overlap_end - u_start)
        fragments.append(
            TextUnit(
                doc_id=unit.doc_id,
                page_no=unit.page_no,
                block_index=unit.block_index,
                char_start=local_start,
                char_end=local_end,
                heading_path=unit.heading_path,
                text=unit.text[overlap_start - u_start : overlap_end - u_start],
            )
        )
    return fragments


def section_sentences(section: Section) -> list[DiffSentence]:
    """
    Bir Section'ı, BİRLEŞTİRİLMİŞ gövde metni üzerinden (tek tek TextUnit
    değil, bkz. modül docstring'i) cümlelere böler.
    """
    joined, bounds = _joined_with_unit_bounds(section)
    return [
        DiffSentence(units=_span_to_units(bounds, start, end))
        for start, end in find_sentence_spans(joined)
    ]


def _normalized_key(text: str) -> str:
    """
    Cümle KARŞILAŞTIRMASI için normalize edilmiş anahtar (bkz.
    src/parsing/normalizer.py). NEDEN: olağan boşluk/tırnak/tire
    varyantları (örn. PDF'te " -" vs DOCX'te "-") gerçek bir içerik
    farkı DEĞİLDİR -- normalize edilmemiş karşılaştırma bunları
    yanlışlıkla "replace" sayardı. Görüntülenen METİN (DiffSentence.text)
    HER ZAMAN orijinal kalır; sadece KARŞILAŞTIRMA anahtarı normalize edilir.
    """
    return normalize(text).normalized


def diff_words(old_text: str, new_text: str) -> list[WordDiff]:
    """İki cümle metni arasında KELİME seviyesinde difflib opcode listesi üretir."""
    old_words = old_text.split()
    new_words = new_text.split()
    matcher = SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    return [
        WordDiff(op=tag, old_words=tuple(old_words[i1:i2]), new_words=tuple(new_words[j1:j2]))
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ]


def diff_sentences(
    old_sentences: list[DiffSentence], new_sentences: list[DiffSentence]
) -> list[SentenceDiff]:
    """
    İki cümle listesini difflib.SequenceMatcher ile hizalar. "replace" olarak
    hizalanan bloklar POZİSYONA göre 1:1 eşleştirilir (bkz. aşağıdaki NEDEN);
    fazlalık kalan taraf delete/insert olarak işaretlenir.

    NEDEN "replace" bloğu içinde pozisyonel (1:1, en kısa uzunluk kadar)
    eşleştirme: difflib zaten bu bloğu iki tarafta da BAŞKA bir eşleşme
    (equal/tam eşleşme) BULAMADIĞI için "replace" olarak işaretledi -- yani
    bu alt-dizideki cümleler arasında zaten "en iyi" bir hizalama ipucu YOK.
    Pozisyonel eşleştirme, ground_truth.json'daki gerçek örneklerle uyumludur
    (örn. veri_paylasimi fıkra (1) DEĞİŞTİ, fıkra (2) AYNI kaldığından zaten
    "equal" bloğuna düşer ve BURAYA hiç girmez) ve basit/öngörülebilirdir.
    """
    old_keys = [_normalized_key(s.text) for s in old_sentences]
    new_keys = [_normalized_key(s.text) for s in new_sentences]
    matcher = SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)

    results: list[SentenceDiff] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for oi, ni in zip(range(i1, i2), range(j1, j2)):
                results.append(
                    SentenceDiff(op="equal", old=old_sentences[oi], new=new_sentences[ni])
                )
        elif tag == "replace":
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                oi, ni = i1 + k, j1 + k
                word_diffs = diff_words(old_sentences[oi].text, new_sentences[ni].text)
                results.append(
                    SentenceDiff(
                        op="replace",
                        old=old_sentences[oi],
                        new=new_sentences[ni],
                        word_diffs=word_diffs,
                    )
                )
            for oi in range(i1 + paired, i2):
                results.append(SentenceDiff(op="delete", old=old_sentences[oi], new=None))
            for ni in range(j1 + paired, j2):
                results.append(SentenceDiff(op="insert", old=None, new=new_sentences[ni]))
        elif tag == "delete":
            for oi in range(i1, i2):
                results.append(SentenceDiff(op="delete", old=old_sentences[oi], new=None))
        elif tag == "insert":
            for ni in range(j1, j2):
                results.append(SentenceDiff(op="insert", old=None, new=new_sentences[ni]))
        else:  # pragma: no cover - difflib bu dört etiket dışında bir şey üretmez
            raise AssertionError(f"beklenmeyen difflib opcode etiketi: {tag!r}")

    return results


def diff_section_match(match: SectionMatch) -> SectionDiff:
    """Bir SectionMatch için TAM cümle+kelime diff'i üretir (üst düzey giriş noktası)."""
    old_sentences = section_sentences(match.old)
    new_sentences = section_sentences(match.new)
    return SectionDiff(match=match, sentence_diffs=diff_sentences(old_sentences, new_sentences))
