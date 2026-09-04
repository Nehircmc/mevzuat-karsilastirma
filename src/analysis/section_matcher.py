"""
Matcher L1 (Adım 3) + L2 (Adım 4) -- kural tabanlı ve embedding tabanlı
madde eşleştirme.

L1 iki geçişte çalışır (bkz. match_sections docstring'i): önce aynı
section_type + aynı madde_no eşleşmesi denenir (başlık çelişmiyorsa),
ardından kalanlar arasında BENZERSİZ başlık eşleşmesi aranır (RENUMBERED ve
"numarası DA metni DE değişmiş" durumlarını yakalamak için -- bkz.
data/samples/ground_truth.json: birim_sorumlulukları). L1'in eşleştiremediği
Section'lar -- hem numarası HEM başlığı değişmiş maddeler -- L2'ye
(embedding + Hungarian atama) düşer: TÜM kalan (old, new) çiftleri için
kosinüs benzerliği matrisi çıkarılır, scipy.optimize.linear_sum_assignment
ile TOPLAM benzerliği maksimize eden atama bulunur, ardından
SECTION_MATCH_MIN_COSINE_SIMILARITY eşiğinin ALTINDA kalan atamalar
reddedilir (Mimari İlke B: eşik altı bir atama "eşleşme" değil "rastgele en
yakın komşu" demektir). Hiçbir katman eşleşme üretemezse Section,
unmatched_old/unmatched_new'de bırakılır; nihai REMOVED/ADDED kararı Adım
5'e (differ) bırakılır -- "eşleşmedi" != "belgede karşılığı yok".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.config import SECTION_MATCH_MIN_COSINE_SIMILARITY
from src.models import Section


class _EmbedderLike(Protocol):
    """
    L2'nin ihtiyaç duyduğu tek davranış: metin listesini vektöre çevirmek.

    NEDEN somut Embedder sınıfı (src/analysis/embedder.py) yerine bir
    Protocol: section_matcher.py'nin testleri gerçek sentence-transformers
    modelini yüklemeye (ağır, ağ erişimi ister) ZORLANMAMALI -- testler
    aynı arayüzü uygulayan sahte/deterministik bir embedder enjekte
    edebilir. embedder.Embedder bu Protocol'ü yapısal olarak (duck typing)
    zaten karşılar, ayrıca miras almasına gerek yoktur.
    """

    def embed(self, texts: list[str]) -> np.ndarray: ...


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
    method: str  # "NUMBER_AND_TITLE" | "TITLE_ONLY" | "EMBEDDING"


@dataclass(frozen=True)
class MatchResult:
    """
    L1'in ürettiği tam sonuç: eşleşenler + her iki tarafta da eşleşmeyen artıklar.

    NEDEN unmatched_old/unmatched_new BURADA "REMOVED/ADDED" OLARAK
    ETİKETLENMİYOR: match_sections() hem L1 (yapısal) hem L2 (embedding)
    denemesinden SONRA bile burada kalanlar için kesin bir REMOVED/ADDED
    kararı VERMEZ -- bu, metin/bağlam bakımından farklı katmanların (Adım 5:
    differ) sorumluluğudur. Matcher'ın işi sadece "hangi Section'lar aynı
    maddenin iki hâli" sorusuna cevap vermektir.
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


def _cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(len(a), len(b)) şeklinde kosinüs benzerliği matrisi üretir."""
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return a_norm @ b_norm.T


def _match_by_embedding(
    old_sections: list[Section],
    new_sections: list[Section],
    embedder: _EmbedderLike,
    min_similarity: float,
) -> tuple[list[SectionMatch], list[Section], list[Section]]:
    """
    Geçiş 3 (L2): L1'in eşleştiremediği Section'lar arasında, anlamsal
    (embedding) benzerlik + Hungarian (optimum atama) algoritmasıyla eşleşme
    aranır.

    NEDEN Hungarian (scipy.optimize.linear_sum_assignment) ve GÖZGÜR
    (greedy) "her old için en benzer new'i al" DEĞİL: greedy yaklaşım yerel
    olarak iyi görünen ama KÜRESEL olarak yanlış bir atama üretebilir --
    örn. old_A hem new_X hem new_Y ile yüksek benzerlik taşıyorsa ama
    new_X, old_B için TEK uygun aday ise, greedy old_A'yı new_X'e kilitleyip
    old_B'yi açıkta bırakabilir. Hungarian TÜM matris üzerinde TOPLAM
    benzerliği maksimize eden atamayı bulur, bu tür kilitlenmeleri önler.

    NEDEN section_type çapraz eşleşmesi ENGELLENİYOR (MADDE <-> GECICI_MADDE):
    bu iki numara uzayı bağımsızdır (bkz. config.py GECICI_MADDE_PATTERN
    NEDEN notu); anlamsal olarak benzer metinler bile yanlışlıkla eşleşmemeli
    -- bu yüzden çapraz hücreler Hungarian'a girmeden ÖNCE -1.0 (en düşük
    olası kosinüs benzerliğinden bile düşük) yapılır, böylece optimizasyon
    bu hücreleri ancak BAŞKA hiçbir seçenek yoksa seçer ve eşik testi zaten
    onu SONRADAN eler.

    NEDEN min_similarity eşiğinin ALTINDAKİ atamalar reddediliyor: Hungarian
    HER old'a bir new atamaya ÇALIŞIR (matris kare değilse min(n_old, n_new)
    kadar) -- bu, "hiçbir new gerçekten bu old'a karşılık gelmiyor" durumunda
    bile zorla bir eşleşme üretir. Eşik altı bir atama "eşleşme" değil
    "rastgele en yakın komşu" demektir (Mimari İlke B); böyle çiftler
    unmatched bırakılmalı ki nihai ADDED/REMOVED kararı yanlış bir eşleşmeyle
    gizlenmesin.
    """
    if not old_sections or not new_sections:
        return [], list(old_sections), list(new_sections)

    old_vecs = embedder.embed([s.joined_text for s in old_sections])
    new_vecs = embedder.embed([s.joined_text for s in new_sections])
    sim_matrix = _cosine_similarity_matrix(old_vecs, new_vecs)

    for i, old in enumerate(old_sections):
        for j, new in enumerate(new_sections):
            if old.section_type != new.section_type:
                sim_matrix[i, j] = -1.0

    row_ind, col_ind = linear_sum_assignment(-sim_matrix)

    matches: list[SectionMatch] = []
    matched_old_idx: set[int] = set()
    matched_new_idx: set[int] = set()
    for i, j in zip(row_ind, col_ind):
        if sim_matrix[i, j] < min_similarity:
            continue
        matches.append(SectionMatch(old=old_sections[i], new=new_sections[j], method="EMBEDDING"))
        matched_old_idx.add(i)
        matched_new_idx.add(j)

    unmatched_old = [s for i, s in enumerate(old_sections) if i not in matched_old_idx]
    unmatched_new = [s for j, s in enumerate(new_sections) if j not in matched_new_idx]
    return matches, unmatched_old, unmatched_new


def match_sections(
    old_sections: list[Section],
    new_sections: list[Section],
    embedder: _EmbedderLike | None = None,
    min_similarity: float = SECTION_MATCH_MIN_COSINE_SIMILARITY,
) -> MatchResult:
    """
    Section eşleştirme: L1 (kural tabanlı, her zaman çalışır) + isteğe bağlı
    L2 (embedding + Hungarian, sadece bir `embedder` verilirse çalışır).

    NEDEN embedder isteğe bağlı (None varsayılan): L2, sentence-transformers
    modelinin YÜKLENMESİNİ (ağ erişimi + saniyeler) gerektirir -- L1'i test
    eden veya sadece yapısal eşleşmeyle yetinen bir çağıran bu maliyeti
    ÖDEMEMELİ. `embedder=None` iken davranış tamamen Adım 3'teki L1 ile
    AYNIDIR (geriye dönük uyumluluk).

    Bkz. _match_by_number / _match_by_unique_title / _match_by_embedding
    için katman katman ayrıntılı gerekçe.
    """
    matches_1, unmatched_old, unmatched_new = _match_by_number(old_sections, new_sections)
    matches_2, unmatched_old, unmatched_new = _match_by_unique_title(unmatched_old, unmatched_new)

    matches_3: list[SectionMatch] = []
    if embedder is not None:
        matches_3, unmatched_old, unmatched_new = _match_by_embedding(
            unmatched_old, unmatched_new, embedder, min_similarity
        )

    matches = matches_1 + matches_2 + matches_3
    matches.sort(key=lambda m: m.old.order_index)
    unmatched_old.sort(key=lambda s: s.order_index)
    unmatched_new.sort(key=lambda s: s.order_index)

    return MatchResult(matches=matches, unmatched_old=unmatched_old, unmatched_new=unmatched_new)
