"""
Tarih ve süre ifadelerinin metin içinde YAKALANMASI -- saf, TextUnit/Section'dan
BAĞIMSIZ (bkz. sentence_splitter.py::find_sentence_spans ile AYNI desen).

NEDEN ayrı bir modül (src/temporal.py'ye EKLENMEDİ): src/temporal.py belge
KİMLİĞİ/sürümüne (DocumentMeta, dosya adı/üstveri tahmini) aittir, belge
GÖVDE METNİNİ hiç okumaz (bkz. o modülün NEDEN notu). Bu modül tam tersini
yapar -- gövde metni İÇİNDE geçen tarih/süre ifadelerini bulur -- birbirine
KARIŞTIRILMAMASI için ayrı dosyada, ayrı dizinde (parsing/, temporal.py'nin
bulunduğu kökten farklı) tutulur.

NEDEN kapsam yine de SINIRLI (serbest biçimli/deyimsel tarih ifadeleri
kapsam dışı, ama yazıyla süre miktarları ARTIK destekleniyor -- bkz.
_sayi_kelimelerini_coz): tam doğal dil ayrıştırması genel bir regex
kümesiyle GÜVENİLİR yapılamaz. Kapsam dışı kalan ifadeler sessizce YOK
SAYILIR, YANLIŞ bir değer ÜRETİLMEZ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from src.config import (
    TEMPORAL_SURE_BIRIMLERI_TR,
    TEMPORAL_TR_AY_ADLARI,
    TEMPORAL_TR_SAYI_KELIMELERI,
)


class TemporalExpressionKind(str, Enum):
    """Kapalı sözlük (Mimari İlke C ile aynı ilke) -- SADECE iki tür."""

    DATE = "DATE"
    DURATION = "DURATION"


@dataclass(frozen=True)
class TemporalExpression:
    """
    Metin içinde bulunan TEK bir tarih/süre ifadesi.

    `normalized_value` KARŞILAŞTIRMA anahtarıdır (bkz. differ.py::
    _normalized_key ile AYNI ilke) -- "14/11/2019" ve "14 Kasım 2019" AYNI
    normalized_value'yu üretir ki iki belgede FARKLI biçimde yazılmış AYNI
    tarih yanlışlıkla "değişti" sayılmasın. Görüntülenen METİN (`text`)
    HER ZAMAN orijinal, normalize EDİLMEMİŞ hâldir.
    """

    text: str
    kind: TemporalExpressionKind
    start: int
    end: int
    normalized_value: str


# NEDEN TEK bir birleşik regex (dört ayrı `finditer` çağrısı DEĞİL): tek bir
# `finditer` geçişi, aynı karakter aralığının BİRDEN FAZLA alt-desenle
# (örn. bir yıl hem "yıl" süre biriminin hem "yılı" tarih son ekinin bir
# parçası gibi) ÇAKIŞARAK eşleşmesini regex motorunun kendisi ENGELLER --
# soldan sağa, en erken başlayan/en uzun eşleşme kazanır, elle çakışma
# çözümü YAZMAYA gerek KALMAZ.
_AY_ALTERNATION = "|".join(TEMPORAL_TR_AY_ADLARI.keys())
_BIRIM_ALTERNATION = "|".join(TEMPORAL_SURE_BIRIMLERI_TR)
_SAYI_KELIME_ALTERNATION = "|".join(TEMPORAL_TR_SAYI_KELIMELERI.keys())

_TEMPORAL_RE = re.compile(
    r"(?P<num_date>\b(?P<nd_d>\d{1,2})[./](?P<nd_m>\d{1,2})[./](?P<nd_y>\d{4})\b)"
    rf"|(?P<tr_date>\b(?P<td_d>\d{{1,2}})\s+(?P<td_ay>{_AY_ALTERNATION})\s+(?P<td_y>\d{{4}})\b)"
    r"|(?P<year_only>\b(?P<yo_y>\d{4})\s+yılı(?:nda|nın|ndan)?\b)"
    rf"|(?P<duration>\b(?P<dur_amt>\d+)\s+(?P<dur_birim>{_BIRIM_ALTERNATION})\b)"
    rf"|(?P<duration_word>\b(?P<dw_sayi>(?:(?:{_SAYI_KELIME_ALTERNATION})\s+)*(?:{_SAYI_KELIME_ALTERNATION}))"
    rf"\s+(?P<dw_birim>{_BIRIM_ALTERNATION})\b)"
)


def _sayi_kelimelerini_coz(kelimeler: list[str]) -> int:
    """
    Türkçe yazıyla yazılmış bir tam sayıyı (örn. "kırk beş" -> 45, "iki
    yüz kırk beş" -> 245) TOPLAMSAL/basamaklı biçimde çözer.

    NEDEN "yüz"/"bin" ÇARPAN, diğerleri TOPLAMA olarak işleniyor: Türkçe
    sayı adlandırması BASAMAKLIDIR ("iki yüz" = 2*100, ama "kırk beş" =
    40+5 -- "kırk" bir çarpan DEĞİL, kendi basamağının değeridir). `current`
    aktif basamak grubunu, `total` tamamlanmış (bin ile kapatılmış)
    grupları biriktirir -- standart "kelimeden sayıya" çevirme algoritması.
    """
    total = 0
    current = 0
    for kelime in kelimeler:
        deger = TEMPORAL_TR_SAYI_KELIMELERI[kelime]
        if deger == 1000:
            current = (current or 1) * 1000
            total += current
            current = 0
        elif deger == 100:
            current = (current or 1) * 100
        else:
            current += deger
    return total + current


def find_temporal_expressions(text: str) -> list[TemporalExpression]:
    """
    Bir metindeki TÜM tarih/süre ifadelerini, GEÇTİKLERİ SIRAYLA döndürür.

    Geçersiz bir tarih (örn. "32.13.2019") sessizce ATLANIR -- yakalanan
    RAKAM diziSİ bir tarih İFADESİ gibi görünse de gerçek bir takvim
    tarihi değilse, bunu bir TemporalExpression olarak ÜRETMEK yanlış bir
    normalized_value (ve dolayısıyla yanlış bir "değişti" kararı) üretirdi.
    """
    results: list[TemporalExpression] = []
    for m in _TEMPORAL_RE.finditer(text):
        if m.group("num_date"):
            d, mo, y = int(m.group("nd_d")), int(m.group("nd_m")), int(m.group("nd_y"))
            try:
                iso = date(y, mo, d).isoformat()
            except ValueError:
                continue
            results.append(
                TemporalExpression(
                    text=m.group(0), kind=TemporalExpressionKind.DATE,
                    start=m.start(), end=m.end(), normalized_value=iso,
                )
            )
        elif m.group("tr_date"):
            d, y = int(m.group("td_d")), int(m.group("td_y"))
            mo = TEMPORAL_TR_AY_ADLARI[m.group("td_ay")]
            try:
                iso = date(y, mo, d).isoformat()
            except ValueError:
                continue
            results.append(
                TemporalExpression(
                    text=m.group(0), kind=TemporalExpressionKind.DATE,
                    start=m.start(), end=m.end(), normalized_value=iso,
                )
            )
        elif m.group("year_only"):
            results.append(
                TemporalExpression(
                    text=m.group(0), kind=TemporalExpressionKind.DATE,
                    start=m.start(), end=m.end(),
                    normalized_value=f"{m.group('yo_y')}-YIL",
                )
            )
        elif m.group("duration"):
            results.append(
                TemporalExpression(
                    text=m.group(0), kind=TemporalExpressionKind.DURATION,
                    start=m.start(), end=m.end(),
                    normalized_value=f"{m.group('dur_amt')} {m.group('dur_birim')}",
                )
            )
        elif m.group("duration_word"):
            miktar = _sayi_kelimelerini_coz(m.group("dw_sayi").split())
            # NEDEN normalized_value RAKAMLI biçimle AYNI kalıpta ("45 gün",
            # "kırk beş gün" DEĞİL): "otuz gün" -> "45 gün" gibi bir
            # DEĞİŞİKLİKTE eski/yeni ifadeler yazım biçimlerinden BAĞIMSIZ
            # karşılaştırılabilsin (bkz. TemporalExpression NEDEN notu --
            # "14/11/2019" ile "14 Kasım 2019" İLE AYNI ilke).
            results.append(
                TemporalExpression(
                    text=m.group(0), kind=TemporalExpressionKind.DURATION,
                    start=m.start(), end=m.end(),
                    normalized_value=f"{miktar} {m.group('dw_birim')}",
                )
            )
    return results
