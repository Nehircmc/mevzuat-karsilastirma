"""
Mimari Ek 1 -- belge kimliği ve sürüm.

NEDEN ayrı bir modül (ingestion/parsing/analysis/reporting'in HİÇBİRİNE
AİT değil): bu katman bir DocumentMeta'nın GÖRÜNEN kimliğini üretir; hem
reporting hem UI katmanı buna bağımlıdır ama bu ikisi birbirine bağımlı
DEĞİLDİR (bkz. docs/ARCHITECTURE.md §1) -- bu yüzden analysis'in ÜSTÜNDE,
reporting/ui'nin ALTINDA, bağımsız bir yardımcı katman olarak duruyor.

NEDEN kronolojik sıra TESPİTİ/ONAYI burada YOK (eskiden vardı, kaldırıldı):
sistem yalnızca kullanıcının GİRDİĞİ iki tarihi birbiriyle karşılaştırıyordu,
belgenin GERÇEK içeriğini hiç doğrulamıyordu -- kullanıcı yanlış dosyayı
yanlış slota koysa bile tarihleri kendi içinde tutarlı girdiğinde hiçbir
uyarı çıkmıyordu, bu da sahte bir güvenlik hissi veriyordu. Sürüm/tarih
alanları artık SADECE bilgilendirici etiketlerdir (bkz. belge_gorunen_adi).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.models import DocumentMeta

# --------------------------------------------------------------------------
# F2 -- TARİH TAHMİNİ (dosya adı / üstveri) -- SAF, I/O'suz
# --------------------------------------------------------------------------
# NEDEN dosya AÇMA burada YOK: bu fonksiyonlar saf ve test edilebilir kalır.
# PDF/DOCX'i açıp buradaki `metadata_created` girdisini DOLDURMAK
# (pymupdf `pdf.metadata`, python-docx `core_properties.created`)
# ingestion katmanının HENÜZ yazılmamış bir sonraki adımıdır -- bkz. dosya
# başındaki görev notu ("onayım olmadan bir sonraki adıma geçme").

_FULL_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "14.11.2019", "14-11-2019", "14/11/2019"
    (re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)"), "dmy"),
    # "2019-11-14", "2019.11.14", "2019/11/14"
    (re.compile(r"(?<!\d)(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)"), "ymd"),
]
_YEAR_ONLY_PATTERN = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
_PDF_METADATA_DATE_PATTERN = re.compile(r"D:(\d{4})(\d{2})(\d{2})")


def guess_date_from_filename(filename: str) -> date | None:
    """
    Dosya adından bir tarih ADAYI çıkarır. Önce TAM tarih kalıplarını dener
    (örn. "yonetmelik_14.11.2019.pdf"), bulamazsa TEK BAŞINA bir yıla düşer
    (örn. "yonetmelik_2019.pdf" -> 1 Ocak 2019) -- bu KABACA bir öneridir,
    kesin bir yayım/yürürlük tarihi DEĞİLDİR; çağıran taraf bunu kullanıcı
    onayı olmadan kullanamaz.
    """
    for pattern, order in _FULL_DATE_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue
        try:
            if order == "dmy":
                d, m, y = match.groups()
            else:
                y, m, d = match.groups()
            return date(int(y), int(m), int(d))
        except ValueError:
            continue

    match = _YEAR_ONLY_PATTERN.search(filename)
    if match:
        return date(int(match.group(0)), 1, 1)
    return None


def guess_date_from_metadata(raw: str | date | datetime | None) -> date | None:
    """
    PDF (`/CreationDate` -> "D:20191114...") ya da DOCX (ISO 8601
    `datetime`/`date`) üstveri değerinden bir tarih ADAYI çıkarır.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        match = _PDF_METADATA_DATE_PATTERN.match(raw)
        if match:
            try:
                y, m, d = match.groups()
                return date(int(y), int(m), int(d))
            except ValueError:
                return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class DateSuggestion:
    """
    Bir tarih alanı için ÖN SEÇİM önerisi. `source` kullanıcıya HANGİ
    kaynaktan geldiğini göstermek içindir ("neden bu tarih önerildi?").
    Kesin değer DEĞİLDİR -- kullanıcı onaylamadan (F2) hiçbir analiz bunu
    kullanamaz.
    """

    suggested_date: date | None
    source: str  # "metadata" | "filename" | "none"


def suggest_publication_date(
    source_path: str, metadata_created: str | date | datetime | None = None
) -> DateSuggestion:
    """
    Yayım tarihi için bir ÖN SEÇİM üretir. Öncelik üstveri > dosya adıdır --
    NEDEN: üstveri (PDF /CreationDate, DOCX core_properties.created)
    dosyanın KENDİSİNDEN gelir; dosya adı kullanıcının seçtiği serbest bir
    etikettir ve yanıltıcı olabilir (örn. "yonetmelik_son_hali.pdf" gibi
    tarihsiz de adlandırılmış olabilir).
    """
    from_metadata = guess_date_from_metadata(metadata_created)
    if from_metadata is not None:
        return DateSuggestion(from_metadata, "metadata")

    from_filename = guess_date_from_filename(Path(source_path).name)
    if from_filename is not None:
        return DateSuggestion(from_filename, "filename")

    return DateSuggestion(None, "none")


# --------------------------------------------------------------------------
# F3 -- GÖRÜNEN AD (TEK fonksiyon, kademeli düşüş)
# --------------------------------------------------------------------------


def _format_date_tr(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def belge_gorunen_adi(meta: DocumentMeta) -> str:
    """
    F3: belge görünen adını üreten TEK fonksiyon -- hiçbir modül kendi
    dizesini kurmasın (bkz. src/reporting/summary_builder.py'deki AYNI
    ilke: SABİT şablon, serbest metin yok).

    Kademeli düşüş:
      1. version_label varsa    : "Belge A (2019 sürümü)"
      2. yalnızca tarih varsa   : "Belge A (14.11.2019)"
      3. hiçbiri yoksa          : "Belge A (yonetmelik_v1.pdf)"

    NEDEN kademe 2'de effective_date > publication_date: kullanıcı bir
    sürümü AYIRT EDERKEN asıl sorduğu soru "bu belge HANGİ DÖNEMDE
    yürürlükteydi"dir -- yayım tarihi sadece belgenin ne zaman KAMUYA
    açıklandığını gösterir, hangi dönemi YÖNETTİĞİNİ değil (bkz.
    src/models.py::DocumentMeta NEDEN notu).
    """
    etiket = f"Belge {meta.slot}" if meta.slot else "Belge"

    if meta.version_label:
        return f"{etiket} ({meta.version_label})"
    if meta.effective_date is not None:
        return f"{etiket} ({_format_date_tr(meta.effective_date)})"
    if meta.publication_date is not None:
        return f"{etiket} ({_format_date_tr(meta.publication_date)})"
    return f"{etiket} ({Path(meta.source_path).name})"


# --------------------------------------------------------------------------
# F7 -- KAYNAK GÖSTERİMİ (TEK üretim noktası)
# --------------------------------------------------------------------------


def kaynak_atifi(meta: DocumentMeta, bolum_etiketi: str, sayfa_no: int | None = None) -> str:
    """
    F7: atıf dizesi -- belge kimliği + sürüm + konum. F3'ün görünen ad
    fonksiyonunu KULLANIR (iki ayrı yerde iki farklı biçim OLUŞMASIN).

    örn. kaynak_atifi(belge_b_meta, "MADDE 5", 3)
         -> "Belge B (2023 sürümü), MADDE 5, s. 3"
    """
    ad = belge_gorunen_adi(meta)
    if sayfa_no is not None:
        return f"{ad}, {bolum_etiketi}, s. {sayfa_no}"
    return f"{ad}, {bolum_etiketi}"
