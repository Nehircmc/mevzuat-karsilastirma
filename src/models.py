"""
Provenance sözleşmesi burada tanımlanır (Mimari İlke A). Bu modüldeki
dataclass'lar tüm boru hattının (ingestion -> parsing -> analysis ->
reporting) ORTAK dili; hiçbir katman "düz string" ile çalışmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChangeType(str, Enum):
    """
    Kapalı etiket sözlüğü (Mimari İlke C). Analiz katmanı bu kümenin
    DIŞINDA bir değer üretemez -- "yorum yok" ilkesi tip sistemiyle
    zorlanır, iyi niyetle değil. str'den türetilmesinin nedeni: pandas/
    Excel/JSON dışa aktarımda enum'un doğrudan okunabilir string olarak
    serileşmesini sağlamak (ekstra .value çağrısı gerektirmeden).
    """

    IDENTICAL = "IDENTICAL"
    MODIFIED = "MODIFIED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MOVED = "MOVED"
    RENUMBERED = "RENUMBERED"


@dataclass(frozen=True)
class TextUnit:
    """
    Boru hattındaki EN KÜÇÜK provenance birimi.

    Koordinat sözleşmesi: char_start/char_end, bu birimin AİT OLDUĞU bir üst
    seviye kaynağın (Adım 1'de: loader'ın çıkardığı ham blok/paragraf metni;
    Adım 2'den itibaren: cümle bölme sonrası ebeveyn bloğun ham metni)
    içindeki ofsettir -- belge genelinde global bir ofset DEĞİLDİR. NEDEN:
    global ofset, normalizasyon (Adım 1.8) sonrası kaymalara karşı kırılgan
    olurdu; blok-yerel ofset her katmanda yeniden hesaplanabilir ve
    normalizer'ın "orijinal metne geri haritalama" yükümlülüğü sadece kendi
    bloğu için offset üretmesini gerektirir.

    heading_path: kökten bu birime kadar olan başlık zinciri, örn.
    ["İKİNCİ BÖLÜM", "MADDE 7"]. Boş tuple olabilir (henüz hiçbir başlık
    tespit edilmemiş gövde metni -- örn. belge başlığından önceki metin).

    page_no: DOCX'te sayfa kavramı yoktur (akış tabanlı biçimdir), bu yüzden
    None olabilir. Bu durumu tolere ETMEMEK ingestion/docx_loader.py'yi
    yapay sayfa numaraları uydurmaya zorlardı -- bu da provenance'ı
    YANLIŞ bir kesinlik izlenimiyle kirletir.
    """

    doc_id: str
    page_no: int | None
    block_index: int
    char_start: int
    char_end: int
    heading_path: tuple[str, ...]
    text: str

    def __post_init__(self) -> None:
        # NEDEN: char_start/char_end ile text'in uzunluğu tutarsızsa bu
        # birimin provenance'ı yalandır -- ileride "kaynağa geri git" dediğimizde
        # yanlış karaktere işaret eder. Sessizce kabul etmek yerine hemen patlar.
        if self.char_end < self.char_start:
            raise ValueError(
                f"TextUnit: char_end ({self.char_end}) < char_start ({self.char_start})"
            )
        if self.char_end - self.char_start != len(self.text):
            raise ValueError(
                "TextUnit: (char_end - char_start) metnin uzunluğuyla eşleşmiyor; "
                f"beklenen {self.char_end - self.char_start}, gerçek {len(self.text)}"
            )
        if self.page_no is not None and self.page_no < 1:
            raise ValueError(f"TextUnit: page_no 1'den küçük olamaz: {self.page_no}")
        if self.block_index < 0:
            raise ValueError(f"TextUnit: block_index negatif olamaz: {self.block_index}")


@dataclass(frozen=True)
class DocumentMeta:
    """Belge düzeyinde kimlik/köken bilgisi -- TextUnit.doc_id bu meta'ya işaret eder."""

    doc_id: str
    source_path: str
    file_type: str  # "pdf" | "docx" -- factory.py'nin ürettiği kanonik değer
    title: str | None = None
    # NEDEN: DOCX akış tabanlı olduğundan sayfa sayısı loader tarafından
    # GÜVENİLİR şekilde bilinemez (render motoruna bağlıdır); bu yüzden
    # opsiyonel tutuluyor, uydurulmuyor.
    page_count: int | None = None


@dataclass
class Document:
    """Bir kaynak dosyanın tüm boru hattı boyunca taşınan temsili."""

    meta: DocumentMeta
    units: list[TextUnit] = field(default_factory=list)
    # NEDEN TextUnit'in İÇİNDE değil: Mimari İlke A'daki provenance alan kümesi
    # sabittir ("ihlal edilemez") ve tüm katmanların ortak dilidir. Başlık
    # STİLİ ise sadece DOCX loader'a özgü, Adım 2'nin structure_parser'ı için
    # bir İPUCUDUR (PDF'te bu ipucun karşılığı punto/kalınlıktır, o da
    # TextUnit'e girmez). Bu yüzden Document seviyesinde, block_index'e göre
    # anahtarlanmış AYRI bir sözlükte tutulur.
    heading_style_hints: dict[int, str] = field(default_factory=dict)


@dataclass
class Section:
    """
    Bir madde/geçici madde düzeyinde hiyerarşik gruplama -- Adım 3-5'teki
    eşleştirme ve diff işlemlerinin ÇALIŞTIĞI birim budur (tek tek TextUnit
    değil). structure_parser.parse_structure() üretir.

    NEDEN TextUnit'ten AYRI bir sınıf: TextUnit sabit provenance sözleşmesini
    taşır (Mimari İlke A); Section ise bunun ÜZERİNE kurulu, birden fazla
    TextUnit'i (bir madde sayfa sınırında bölünmüşse birden fazla bloktan
    gelen parçaları) tek bir mantıksal madde altında toplayan bir gruplamadır.
    units listesi HER ZAMAN geçerli, kendi orijinal ebeveynine ait offset'ler
    taşıyan TextUnit'lerden oluşur -- birleştirme sırasında offset'ler asla
    "uydurulmaz".
    """

    doc_id: str
    heading_path: tuple[str, ...]  # örn. ("İKİNCİ BÖLÜM", "MADDE 7")
    section_type: str  # "MADDE" | "GECICI_MADDE" -- kapalı küme
    madde_no: int | None
    baslik: str | None  # kısa madde başlığı (örn. "Amaç"); tespit edilemezse None
    order_index: int  # belgedeki sıralı konum -- Adım 4'te MOVED tespiti için
    units: list[TextUnit] = field(default_factory=list)

    @property
    def joined_text(self) -> str:
        """Section'a ait tüm TextUnit'lerin metnini sırayla birleştirir (ham, normalize edilmemiş)."""
        return " ".join(u.text for u in self.units)
