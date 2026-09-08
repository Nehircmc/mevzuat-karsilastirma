"""
Eşleşmiş bir madde çiftinde (SectionMatch) geçen tarih/süre ifadelerinin
DEĞİŞİMİNİ tespit eder -- "içerik durumu" (ChangeType) VE "yapısal
bayraklar" (numarasi_degisti/yeri_degisti) İLE AYNI ilkeyle, ÜÇÜNCÜ BAĞIMSIZ
bir boyut olarak (bkz. classifier.py NEDEN notu): bir madde HEM "MODIFIED"
HEM "içinde bir tarih değişmiş" olabilir, bu iki olgu birbirine KARIŞMAZ.

NEDEN kendi cümle hizalamasını YENİDEN YAPMIYOR (differ.py::diff_sentences'ı
TEKRAR ÇAĞIRMIYOR, SectionDiff'i GİRDİ olarak alıyor): differ.py'nin
ZATEN ürettiği, ground_truth.json'a karşı doğrulanmış cümle hizalaması TEK
kaynak olarak kullanılır -- iki AYRI SequenceMatcher geçişinin (biri
differ.py'de, biri burada) birbirinden SESSİZCE SAPMASI (örn. biri bir
cümle çiftini "replace" sayarken diğeri "delete+insert" sayması) riski
budur.

NEDEN "replace" cümle çiftlerinde bir GÜVEN EŞİĞİ var (bkz. config.py::
TEMPORAL_CHANGE_MIN_SENTENCE_SIMILARITY): differ.py'nin kendi "replace
bloğu" eşleştirmesi POZİSYONELDİR (bkz. o modülün NEDEN notu: "bu
alt-dizideki cümleler arasında zaten en iyi bir hizalama ipucu YOK") --
madde büyük ölçüde YENİDEN YAZILMIŞSA, eski/yeni cümleler ALAKASIZ olabilir
ama HER İKİSİ DE tesadüfen bir tarih/süre içerebilir. Bu durumda "X ifadesi
Y'ye değişti" diye EŞLEŞTİRMEK yanlış bir nedensellik iddia eder (bkz. görev
geçmişi -- sentetik VE gerçek PDF testleriyle doğrulanan risk). Cümle
çiftinin KELİME benzerlik oranı eşiğin altındaysa, eşleştirme iddiası
TERK EDİLİR: ifadeler BAĞIMSIZ iki olgu (kaldırıldı / eklendi) olarak
raporlanır -- veri KAYBOLMAZ, sadece ispatlanmamış bir X->Y iddiası
YAPILMAZ.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from src.analysis.differ import DiffSentence, SectionDiff
from src.analysis.section_matcher import SectionMatch
from src.config import TEMPORAL_CHANGE_MIN_SENTENCE_SIMILARITY
from src.parsing.temporal_expressions import TemporalExpression, find_temporal_expressions


@dataclass(frozen=True)
class TemporalChange:
    """
    Bir madde çiftinde tespit edilen TEK bir tarih/süre değişikliği.

    `old`/`new` İKİSİ de doluysa ("X ifadesi Y'ye değişti") bu YÜKSEK
    GÜVENLE eşleştirilmiş bir değişikliktir; sadece BİRİ doluysa (diğeri
    None) bu BAĞIMSIZ bir olgudur -- "kaldırıldı" (old dolu) ya da
    "eklendi" (new dolu), aralarında bir eşleştirme İDDİA EDİLMEZ (bkz.
    modül NEDEN notu). old_sentence/new_sentence provenance (sayfa no)
    içindir -- DiffSentence.units üzerinden erişilir (ClassifiedSection
    ile AYNI sözleşme: old ve new AYNI ANDA None OLAMAZ).
    """

    match: SectionMatch
    old: TemporalExpression | None
    new: TemporalExpression | None
    old_sentence: DiffSentence | None
    new_sentence: DiffSentence | None

    def __post_init__(self) -> None:
        if self.old is None and self.new is None:
            raise ValueError("TemporalChange: old ve new AYNI ANDA None olamaz")

    @property
    def paired(self) -> bool:
        """True: eşleştirilmiş değişiklik ("X -> Y"). False: bağımsız olgu."""
        return self.old is not None and self.new is not None


def _word_similarity(old_text: str, new_text: str) -> float:
    """
    İki cümle metni arasında KELİME benzerlik oranı -- classifier.py::
    char_similarity İLE AYNI teknik (SequenceMatcher.ratio(), kelime
    dizisi üzerinde), sadece BÜTÜN madde yerine TEK bir cümle çiftine
    ölçeklenmiş. Burada normalize() KULLANILMAZ (differ.py::
    _normalized_key'in aksine) -- amaç KARŞILAŞTIRMA anahtarı üretmek
    DEĞİL, iki cümlenin genel olarak AYNI KONUDAN mı bahsettiğini kaba
    biçimde ölçmektir; ham kelime dizisi bunun için yeterlidir.
    """
    return SequenceMatcher(None, old_text.split(), new_text.split()).ratio()


def _diff_within_sentence_pair(
    match: SectionMatch, old_sentence: DiffSentence, new_sentence: DiffSentence
) -> list[TemporalChange]:
    old_exprs = find_temporal_expressions(old_sentence.text)
    new_exprs = find_temporal_expressions(new_sentence.text)
    if not old_exprs and not new_exprs:
        return []

    old_keys = [(e.kind, e.normalized_value) for e in old_exprs]
    new_keys = [(e.kind, e.normalized_value) for e in new_exprs]
    if old_keys == new_keys:
        # ifadeler AYNI -- cümlenin BAŞKA bir kısmı değişmiş, tarih/süre
        # açısından bir değişiklik YOK.
        return []

    if _word_similarity(old_sentence.text, new_sentence.text) < TEMPORAL_CHANGE_MIN_SENTENCE_SIMILARITY:
        return [
            TemporalChange(match=match, old=e, new=None, old_sentence=old_sentence, new_sentence=None)
            for e in old_exprs
        ] + [
            TemporalChange(match=match, old=None, new=e, old_sentence=None, new_sentence=new_sentence)
            for e in new_exprs
        ]

    # Yüksek güven: ifadeleri KENDİ ARALARINDA hizala -- differ.py::
    # diff_words İLE AYNI desen (kelime yerine tarih/süre ifadesi dizisi).
    changes: list[TemporalChange] = []
    matcher = SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                changes.append(
                    TemporalChange(
                        match=match, old=old_exprs[i1 + k], new=new_exprs[j1 + k],
                        old_sentence=old_sentence, new_sentence=new_sentence,
                    )
                )
            for oi in range(i1 + paired, i2):
                changes.append(
                    TemporalChange(match=match, old=old_exprs[oi], new=None, old_sentence=old_sentence, new_sentence=None)
                )
            for ni in range(j1 + paired, j2):
                changes.append(
                    TemporalChange(match=match, old=None, new=new_exprs[ni], old_sentence=None, new_sentence=new_sentence)
                )
        elif tag == "delete":
            for oi in range(i1, i2):
                changes.append(
                    TemporalChange(match=match, old=old_exprs[oi], new=None, old_sentence=old_sentence, new_sentence=None)
                )
        elif tag == "insert":
            for ni in range(j1, j2):
                changes.append(
                    TemporalChange(match=match, old=None, new=new_exprs[ni], old_sentence=None, new_sentence=new_sentence)
                )
    return changes


def diff_temporal_expressions(section_diff: SectionDiff) -> list[TemporalChange]:
    """
    Bir SectionDiff'teki (bkz. differ.py::diff_section_match) TÜM cümle
    hizalama adımlarını gezip tarih/süre değişikliklerini toplar --
    üst düzey giriş noktası (differ.py::diff_section_match İLE AYNI
    konumda, pipeline.py'nin çağırdığı fonksiyon).
    """
    match = section_diff.match
    changes: list[TemporalChange] = []
    for sd in section_diff.sentence_diffs:
        if sd.op == "equal":
            continue
        if sd.op == "delete":
            for e in find_temporal_expressions(sd.old.text):
                changes.append(TemporalChange(match=match, old=e, new=None, old_sentence=sd.old, new_sentence=None))
        elif sd.op == "insert":
            for e in find_temporal_expressions(sd.new.text):
                changes.append(TemporalChange(match=match, old=None, new=e, old_sentence=None, new_sentence=sd.new))
        elif sd.op == "replace":
            changes.extend(_diff_within_sentence_pair(match, sd.old, sd.new))
    return changes
