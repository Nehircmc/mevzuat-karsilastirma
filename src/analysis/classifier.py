"""
Adım 5 (Adım 9'da yeniden tasarlandı): sınıflandırma -- kapalı sözlük
(Mimari İlke C), İKİ BAĞIMSIZ boyut olarak.

Bir MatchResult'taki (bkz. section_matcher.py) HER Section'a (eşleşmiş veya
açıkta kalmış) İKİ AYRI şey atanır:

1. İÇERİK DURUMU (change_type, ChangeType -- IDENTICAL/MODIFIED/ADDED/
   REMOVED): "bu maddenin METNİ değişti mi?" sorusunun kapalı sözlükle
   cevabı. SADECE karakter benzerliğine (difflib) dayanır, madde_no'dan
   BAĞIMSIZDIR.
2. YAPISAL BAYRAKLAR (numarasi_degisti, yeri_degisti -- bool): "bu
   maddenin NUMARASI/KONUMU değişti mi?" sorularının cevabı. İÇERİK
   durumundan BAĞIMSIZDIR -- İKİSİ DE aynı anda True olabilir.

NEDEN bu ikisi AYRI (eskiden MOVED/RENUMBERED de birer ChangeType üyesiydi):
bir madde HEM numarası HEM içeriği değişmiş olabilir (bkz.
ground_truth.json/birim_sorumlulukları: 2019 MADDE 9 -> 2023 MADDE 8, HEM
numara HEM metin değişti). Eski modelde bu durumda YAPISAL olgu (numara
değişti) SESSİZCE KAYBOLUYORDU -- satır sadece MODIFIED sayılıyor, "numarası
da değişti" bilgisi hiçbir yerde görünmüyordu. Şimdi her satır İKİSİNİ de
taşıyor: change_type=MODIFIED VE numarasi_degisti=True aynı anda mümkün.
Toplama/sayım tarafında da bu ayrım korunmalı -- "kaç madde İÇERİK olarak
değişti" ile "kaç maddenin NUMARASI değişti" birbirinden bağımsız, farklı
sayılardır ve TOPLANMAZ (bkz. src/analysis/pipeline.py::ComparisonResult).

NEDEN embedding/kosinüs benzerliği KULLANILMIYOR: L1 eşleşmelerinin
çoğunda (bkz. Adım 3/4) hiç embedding hesaplanmamış olabilir (embedder
isteğe bağlıdır) -- sınıflandırma bu OPSİYONEL veriye bağımlı olursa,
embedder verilmeyen çağrılarda sessizce eksik/yanlış çalışırdı. Karakter
benzerliği ucuz, deterministik ve HER ZAMAN mevcuttur.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from src.analysis.section_matcher import MatchResult, SectionMatch
from src.config import IDENTICAL_CHAR_SIMILARITY_THRESHOLD, MOVED_MIN_POSITION_DELTA
from src.models import ChangeType, Section
from src.parsing.normalizer import normalize


def char_similarity(old_text: str, new_text: str) -> float:
    """
    difflib.SequenceMatcher.ratio(), normalize edilmiş metinlerin KELİME
    dizileri üzerinde (0.0-1.0) -- isim "char_similarity" olsa da (kapalı
    çağıran kod/testlerle uyum için korunuyor) KARAKTER değil KELİME
    dizisi üzerinde çalışır (bkz. NEDEN notu, kalite kontrolünde bulundu).

    NEDEN KELİME dizisi, HAM KARAKTER dizisi DEĞİL (eskiden öyleydi):
    difflib.SequenceMatcher'ın Ratcliff-Obershelp algoritması, İKİ UZUN
    (onlarca bin karakterlik) VE BİRBİRİNE ÇOK BENZER metin üzerinde HAM
    KARAKTER dizisiyle çalıştırıldığında PATOLOJİK biçimde YAVAŞLAR --
    gerçek ölçüm: 1200 fıkralı (~104.000 karakter), aralarında sadece ~400
    fıkranın değiştiği bir madde çiftinde karakter dizisiyle **130 saniye**
    sürüyordu (find_longest_match içinde milyonlarca gereksiz karşılaştırma),
    KELİME dizisiyle (aynı metin, ~13.200 kelime) **0.3 saniyede** biter --
    aynı belge boyutunda tüm karşılaştırma tek başına dakikalarca sürdüğü
    için Streamlit arayüzü DONMUŞ görünürdü. Kelime dizisi HEM çok daha AZ
    elemanlıdır (ortalama kelime uzunluğu ~8 karakter) HEM difflib'in
    "autojunk" sezgisi tekrar eden yaygın kelimeleri (örn. "ve", "bir")
    daha etkili biçimde eler.

    NEDEN eşik kalibrasyonu (IDENTICAL_CHAR_SIMILARITY_THRESHOLD=0.98)
    BOZULMUYOR: gerçek 2019/2023 örnek korpusundaki TÜM eşleşen maddeler
    üzerinde kelime-düzeyi ORAN, karakter-düzeyi ORANLA AYNI IDENTICAL/
    MODIFIED kararını üretir (sıfır fark, elle doğrulandı) -- bu fonksiyon
    zaten normalize edilmiş metin üzerinde çalıştığından (whitespace/
    noktalama gürültüsü elenir), kelime düzeyine geçiş sadece PERFORMANSI
    değiştirir, KARARI değil.
    """
    old_words = normalize(old_text).normalized.split()
    new_words = normalize(new_text).normalized.split()
    return SequenceMatcher(None, old_words, new_words).ratio()


def classify_content(match: SectionMatch) -> ChangeType:
    """
    Eşleşmiş bir (old, new) çiftin İÇERİK DURUMU -- SADECE metin
    benzerliğine dayanır, madde_no'dan TAMAMEN BAĞIMSIZDIR (numara
    değişikliği YAPISAL bir olgudur, bkz. is_renumbered).

    NEDEN madde_no'ya HİÇ bakılmıyor (eski karar ağacında bakılıyordu):
    "bu maddenin metni değişti mi" sorusunun cevabı, numarasının kayıp
    kaymadığından TAMAMEN bağımsız olmalı -- iki soru birbirine
    karıştırılırsa (eski modelde olduğu gibi) "numarası kaymış AMA metni
    de değişmiş" durumu ya yanlış RENUMBERED'a ya da numara bilgisini
    kaybederek sade MODIFIED'a düşerdi.
    """
    similarity = char_similarity(match.old.joined_text, match.new.joined_text)
    return ChangeType.IDENTICAL if similarity >= IDENTICAL_CHAR_SIMILARITY_THRESHOLD else ChangeType.MODIFIED


def is_renumbered(match: SectionMatch) -> bool:
    """YAPISAL bayrak: madde_no değişti mi -- içerik durumundan BAĞIMSIZ."""
    return match.old.madde_no != match.new.madde_no


def is_moved(match: SectionMatch) -> bool:
    """
    YAPISAL bayrak: KISIM/BÖLÜM bağlamı DEĞİŞTİYSE ya da belgedeki sırası
    önemli ölçüde kaydıysa (bkz. config.py MOVED_MIN_POSITION_DELTA NEDEN
    notu) -- içerik durumundan VE numara değişip değişmediğinden BAĞIMSIZ.

    NEDEN heading_path[:-1] (SON eleman -- "MADDE N"/"GEÇİCİ MADDE N"
    etiketi -- HARİÇ): heading_path'in son elemanı zaten madde_no'nun
    kendisidir (aynı bilgiyi iki kez karşılaştırmamak için atılır); KISIM/
    BÖLÜM zinciri budur.
    """
    old, new = match.old, match.new
    if old.heading_path[:-1] != new.heading_path[:-1]:
        return True
    return abs(new.order_index - old.order_index) >= MOVED_MIN_POSITION_DELTA


@dataclass(frozen=True)
class ClassifiedSection:
    """
    Bir Section'ın nihai sınıflandırma sonucu -- eşleşmiş bir çift için
    old/new İKİSİ de dolu, REMOVED için sadece old, ADDED için sadece new
    doludur (üçü de aynı anda None OLAMAZ, en az biri her zaman dolu).

    change_type İÇERİK durumu, numarasi_degisti/yeri_degisti YAPISAL
    bayraklardır -- BAĞIMSIZ boyutlar, aynı satırda İKİSİ de (örn.
    change_type=MODIFIED + numarasi_degisti=True) görünebilir. REMOVED/
    ADDED satırlarında (karşılığı olmadığı için) ikisi de HER ZAMAN False'tur.
    """

    change_type: ChangeType
    old: Section | None
    new: Section | None
    numarasi_degisti: bool = False
    yeri_degisti: bool = False

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
        ClassifiedSection(
            change_type=classify_content(m),
            old=m.old,
            new=m.new,
            numarasi_degisti=is_renumbered(m),
            yeri_degisti=is_moved(m),
        )
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
