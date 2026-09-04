"""
Adım 5: ChangeType sınıflandırma -- kapalı sözlük (Mimari İlke C).

Bir MatchResult'taki (bkz. section_matcher.py) HER Section'a (eşleşmiş veya
açıkta kalmış) tam olarak BİR ChangeType atar. Karar ağacı SADECE üç sinyale
dayanır: madde_no eşitliği, karakter benzerliği (difflib.SequenceMatcher,
normalize edilmiş metin üzerinde) ve konum/hiyerarşi kayması (order_index +
heading_path). NEDEN embedding/kosinüs benzerliği KULLANILMIYOR: L1
eşleşmelerinin çoğunda (bkz. Adım 3/4) hiç embedding hesaplanmamış olabilir
(embedder isteğe bağlıdır) -- sınıflandırma bu OPSİYONEL veriye bağımlı
olursa, embedder verilmeyen çağrılarda sessizce eksik/yanlış çalışırdı.
Karakter benzerliği ucuz, deterministik ve HER ZAMAN mevcuttur.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from src.analysis.section_matcher import MatchResult, SectionMatch
from src.config import (
    IDENTICAL_CHAR_SIMILARITY_THRESHOLD,
    MOVED_MIN_POSITION_DELTA,
    RENUMBERED_CHAR_SIMILARITY_THRESHOLD,
)
from src.models import ChangeType, Section
from src.parsing.normalizer import normalize


def char_similarity(old_text: str, new_text: str) -> float:
    """difflib.SequenceMatcher.ratio(), normalize edilmiş metinler üzerinde (0.0-1.0)."""
    return SequenceMatcher(None, normalize(old_text).normalized, normalize(new_text).normalized).ratio()


def _moved(old: Section, new: Section) -> bool:
    """
    "Taşınmış" sinyali: madde_no AYNI kalsa bile içinde bulunduğu
    KISIM/BÖLÜM bağlamı DEĞİŞTİYSE ya da belgedeki sırası önemli ölçüde
    kaydıysa (bkz. config.py MOVED_MIN_POSITION_DELTA NEDEN notu).

    NEDEN heading_path[:-1] (SON eleman -- "MADDE N"/"GEÇİCİ MADDE N"
    etiketi -- HARİÇ): heading_path'in son elemanı zaten madde_no'nun
    kendisidir (aynı bilgiyi iki kez karşılaştırmamak için atılır); KISIM/
    BÖLÜM zinciri budur.
    """
    if old.heading_path[:-1] != new.heading_path[:-1]:
        return True
    return abs(new.order_index - old.order_index) >= MOVED_MIN_POSITION_DELTA


def classify_match(match: SectionMatch) -> ChangeType:
    """
    Eşleşmiş bir (old, new) Section çiftine ChangeType atar.

    Karar ağacı:
    1) madde_no AYNI:
       a) karakter benzerliği >= IDENTICAL_CHAR_SIMILARITY_THRESHOLD (0.98):
          konum/bağlam da kaymışsa MOVED, değilse IDENTICAL.
       b) aksi halde MODIFIED.
    2) madde_no FARKLI (numara kaymış):
       a) karakter benzerliği >= RENUMBERED_CHAR_SIMILARITY_THRESHOLD (0.995,
          IDENTICAL eşiğinden bile DAHA SIKI -- bkz. config.py NEDEN notu):
          RENUMBERED.
       b) aksi halde MODIFIED (hem numara HEM içerik değişmiş -- bkz.
          ground_truth.json/birim_sorumlulukları: "RENUMBERED değil MODIFIED
          olarak sınıflandırılmalı çünkü metin de değişti").
    """
    similarity = char_similarity(match.old.joined_text, match.new.joined_text)

    if match.old.madde_no == match.new.madde_no:
        if similarity >= IDENTICAL_CHAR_SIMILARITY_THRESHOLD:
            return ChangeType.MOVED if _moved(match.old, match.new) else ChangeType.IDENTICAL
        return ChangeType.MODIFIED

    if similarity >= RENUMBERED_CHAR_SIMILARITY_THRESHOLD:
        return ChangeType.RENUMBERED
    return ChangeType.MODIFIED


@dataclass(frozen=True)
class ClassifiedSection:
    """
    Bir Section'ın nihai sınıflandırma sonucu -- eşleşmiş bir çift için
    old/new İKİSİ de dolu, REMOVED için sadece old, ADDED için sadece new
    doludur (üçü de aynı anda None OLAMAZ, en az biri her zaman dolu).
    """

    change_type: ChangeType
    old: Section | None
    new: Section | None

    def __post_init__(self) -> None:
        if self.old is None and self.new is None:
            raise ValueError("ClassifiedSection: old ve new AYNI ANDA None olamaz")


def classify_all(result: MatchResult) -> list[ClassifiedSection]:
    """
    Bir MatchResult'taki TÜM Section'ları (eşleşmiş + açıkta kalmış)
    sınıflandırır. Döndürülen liste, girdideki toplam Section sayısını
    KORUR (hiçbir Section sessizce düşürülmez) -- bkz. tests/test_differ.py
    kapsam/tamlık testleri.
    """
    classified = [
        ClassifiedSection(change_type=classify_match(m), old=m.old, new=m.new)
        for m in result.matches
    ]
    classified.extend(
        ClassifiedSection(change_type=ChangeType.REMOVED, old=s, new=None)
        for s in result.unmatched_old
    )
    classified.extend(
        ClassifiedSection(change_type=ChangeType.ADDED, old=None, new=s)
        for s in result.unmatched_new
    )
    return classified
