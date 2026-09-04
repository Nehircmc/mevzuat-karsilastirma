"""
Adım 3: Matcher L1 -- kural tabanlı (numara + başlık) madde eşleştirme.

İki geçişte çalışır (bkz. match_sections docstring'i): önce aynı
section_type + aynı madde_no eşleşmesi denenir (başlık çelişmiyorsa),
ardından kalanlar arasında BENZERSİZ başlık eşleşmesi aranır (RENUMBERED ve
"numarası DA metni DE değişmiş" durumlarını yakalamak için -- bkz.
data/samples/ground_truth.json: birim_sorumlulukları). Hiçbir kural eşleşme
üretmezse Section, unmatched_old/unmatched_new'de bırakılır; nihai
REMOVED/ADDED kararı Adım 4'e (L2, embedding) bırakılır -- L1 sadece
yapısal sinyalle çalışır, "eşleşmedi" != "belgede karşılığı yok".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.models import Section


def _normalize_baslik(baslik: str) -> str:
    """
    Başlık karşılaştırması için hafif normalizasyon (casefold + boşluk sıkıştırma).

    NEDEN offset-korumalı normalizer (src/parsing/normalizer.py) KULLANILMIYOR:
    o modül orijinal metne geri-haritalama garantisi taşır (differ için
    gerekli); burada sadece iki başlığın "aynı sayılır mı" sorusuna karar
    veren tek yönlü bir karşılaştırma anahtarı üretiyoruz -- offset
    izlenebilirliği gerekmiyor.
    """
    return " ".join(baslik.casefold().split())


@dataclass(frozen=True)
class SectionMatch:
    """
    Eski (old) ve yeni (new) belgeden eşleştirilmiş bir Section çifti.

    method: eşleşmenin HANGİ kurala göre kurulduğu -- Adım 4/7'de "bu eşleşme
    ne kadar güvenilir" sorusuna kaynak gösterebilmek için tutulan kapalı küme.
    """

    old: Section
    new: Section
    method: str  # "NUMBER_AND_TITLE" | "TITLE_ONLY"


@dataclass(frozen=True)
class MatchResult:
    """
    L1'in ürettiği tam sonuç: eşleşenler + her iki tarafta da eşleşmeyen artıklar.

    NEDEN unmatched_old/unmatched_new BURADA "REMOVED/ADDED" OLARAK
    ETİKETLENMİYOR: L1 sadece yapısal (numara/başlık) sinyalle çalışır; kesin
    REMOVED/ADDED kararı, anlamsal (embedding) eşleşme denemesi başarısız
    OLDUKTAN SONRA Adım 4'te (Matcher L2) verilir.
    """

    matches: list[SectionMatch] = field(default_factory=list)
    unmatched_old: list[Section] = field(default_factory=list)
    unmatched_new: list[Section] = field(default_factory=list)


def _titles_conflict(a: Section, b: Section) -> bool:
    """
    İki Section'ın başlığı AÇIKÇA farklıysa True. Biri/ikisi de başlıksızsa
    (baslik is None) çelişki YOKTUR sayılır -- yokluk, "farklı" anlamına
    gelmez, sadece karşılaştırılamaz demektir.
    """
    if a.baslik is None or b.baslik is None:
        return False
    return _normalize_baslik(a.baslik) != _normalize_baslik(b.baslik)


def _match_by_number(
    old_sections: list[Section], new_sections: list[Section]
) -> tuple[list[SectionMatch], list[Section], list[Section]]:
    """
    Geçiş 1: aynı section_type + aynı madde_no taşıyan bir (old, new) çifti,
    başlıkları ÇELİŞMİYORSA eşleştirilir.

    NEDEN başlık çelişkisi engelleyici: bir madde eklenip/kaldırılınca
    ARADAKİ maddeler numara olarak KAYAR (örn. eski MADDE 8 kaldırılınca
    yeni MADDE 8 farklı bir maddedir) -- sadece numaraya güvenmek bu
    durumda YANLIŞ eşleşme üretir (Mimari İlke B ihlali).
    """
    matches: list[SectionMatch] = []
    unmatched_new = list(new_sections)
    unmatched_old: list[Section] = []

    for old in old_sections:
        candidate_idx = next(
            (
                i
                for i, new in enumerate(unmatched_new)
                if new.section_type == old.section_type
                and new.madde_no == old.madde_no
                and not _titles_conflict(old, new)
            ),
            None,
        )
        if candidate_idx is None:
            unmatched_old.append(old)
        else:
            new = unmatched_new.pop(candidate_idx)
            matches.append(SectionMatch(old=old, new=new, method="NUMBER_AND_TITLE"))

    return matches, unmatched_old, unmatched_new


def _match_by_unique_title(
    old_sections: list[Section], new_sections: list[Section]
) -> tuple[list[SectionMatch], list[Section], list[Section]]:
    """
    Geçiş 2: aynı section_type + normalize edilmiş başlığı, HER İKİ tarafta
    da TEK VE BENZERSİZ olan Section çiftleri eşleştirilir.

    NEDEN bu gerekli: numara kayması (RENUMBERED) ve "numarası DA metni DE
    değişmiş" durumu (bkz. ground_truth.json/birim_sorumlulukları) başlık
    aynı kaldığı sürece bu geçişle doğru eşleşir; Geçiş 1 bunu KAÇIRIR çünkü
    numaralar artık farklıdır. Bir başlık her iki tarafta da BİRDEN FAZLA
    kez geçiyorsa hangi çiftin doğru olduğu belirsizdir -- L1 bu durumda
    KESMEZ, ikisini de eşleşmemiş bırakıp L2'ye devreder.
    """

    def _key(s: Section) -> tuple[str, str] | None:
        if s.baslik is None:
            return None
        return (s.section_type, _normalize_baslik(s.baslik))

    groups_old: dict[tuple[str, str], list[Section]] = defaultdict(list)
    for s in old_sections:
        key = _key(s)
        if key is not None:
            groups_old[key].append(s)

    groups_new: dict[tuple[str, str], list[Section]] = defaultdict(list)
    for s in new_sections:
        key = _key(s)
        if key is not None:
            groups_new[key].append(s)

    matches: list[SectionMatch] = []
    matched_new_ids: set[int] = set()
    matched_old_ids: set[int] = set()

    for key, olds in groups_old.items():
        news = groups_new.get(key, [])
        if len(olds) == 1 and len(news) == 1:
            matches.append(SectionMatch(old=olds[0], new=news[0], method="TITLE_ONLY"))
            matched_old_ids.add(id(olds[0]))
            matched_new_ids.add(id(news[0]))

    unmatched_old = [s for s in old_sections if id(s) not in matched_old_ids]
    unmatched_new = [s for s in new_sections if id(s) not in matched_new_ids]
    return matches, unmatched_old, unmatched_new


def match_sections(old_sections: list[Section], new_sections: list[Section]) -> MatchResult:
    """
    Kural tabanlı (L1) Section eşleştirme. Bkz. modül docstring'i ve
    _match_by_number / _match_by_unique_title için ayrıntılı gerekçe.
    """
    matches_1, unmatched_old, unmatched_new = _match_by_number(old_sections, new_sections)
    matches_2, unmatched_old, unmatched_new = _match_by_unique_title(unmatched_old, unmatched_new)

    matches = matches_1 + matches_2
    matches.sort(key=lambda m: m.old.order_index)
    unmatched_old.sort(key=lambda s: s.order_index)
    unmatched_new.sort(key=lambda s: s.order_index)

    return MatchResult(matches=matches, unmatched_old=unmatched_old, unmatched_new=unmatched_new)
