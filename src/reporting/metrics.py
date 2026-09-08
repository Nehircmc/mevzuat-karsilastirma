"""
Adım 7: karşılaştırma sonucundaki sayısal göstergeleri pandas.DataFrame'e
çevirir -- Excel/CSV dışa aktarımın (exporter.py) VE UI'daki metrik
tablolarının ORTAK veri kaynağı.

NEDEN sabit kolon listeleri (_SUMMARY_COLUMNS/_DETAIL_COLUMNS) ile:
pd.DataFrame(rows) girdi listesi BOŞSA (örn. hiç madde bulunamayan bir
belge çifti) kolon adlarını dict anahtarlarından ÇIKARAMAZ ve 0x0 boş bir
DataFrame döner -- bu, dışa aktarılan Excel/CSV'nin BAŞLIK SATIRINI bile
kaybetmesi demektir. columns= parametresi bu durumda bile doğru başlıkları
garanti eder.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.pipeline import ComparisonResult
from src.config import CHANGE_TYPE_LABELS_TR, TEMPORAL_EXPRESSION_KIND_LABELS_TR
from src.models import ChangeType, Section, TextUnit

_SUMMARY_COLUMNS = ["Değişim Türü", "Sayı", "Yüzde"]
_STRUCTURAL_COLUMNS = ["Yapısal Değişiklik", "Sayı"]
_SECTION_BREAKDOWN_COLUMNS = ["Bölüm"] + [CHANGE_TYPE_LABELS_TR[ct.value] for ct in ChangeType]
_TEMPORAL_CHANGES_COLUMNS = ["Madde", "Tür", "Eski Değer", "Yeni Değer", "Sayfa"]
# NEDEN "—" (em dash, boş string DEĞİL): bir tablo hücresinin boş mu yoksa
# "bu alan bu satırda İLGİLİ DEĞİL" mi olduğu görsel olarak AYIRT edilsin
# -- örn. "eklendi" bir değişiklikte "Eski Değer" hücresi hiç yoktu, "boş
# unutulmuş" gibi görünmemeli.
_TEMPORAL_BOS_DEGER = "—"
# NEDEN ayrı bir sabit (özel karakter/boşluk İÇERMEYEN): heading_path'i
# olmayan (KISIM/BÖLÜM tespit edilemeyen) bir Section'ı SESSİZCE tablodan
# DÜŞÜRMEK yerine ayrı bir kovaya toplar -- aksi halde bölüm başına
# sayılan toplam, result.counts() toplamından daha AZ çıkar ve bu fark
# nereye gittiği belirsiz kalırdı (bkz. build_section_breakdown NEDEN
# notu). components.py bu SABİTİ, seçilen bölüme göre filtrelerken AYNI
# etiketi kullanmak için İÇE AKTARIR (public, alt çizgisiz).
BOLUMSUZ_ETIKETI = "(Bölüm Bilgisi Yok)"
_DETAIL_COLUMNS = [
    "Değişim Türü",
    "Numarası Değişti",
    CHANGE_TYPE_LABELS_TR["MOVED"],
    "Eski Madde No",
    "Yeni Madde No",
    "Başlık",
    "Eski Bölüm",
    "Yeni Bölüm",
    "Eski Metin",
    "Yeni Metin",
]

# NEDEN: Excel/LibreOffice/Google Sheets, bir hücre "=", "+", "-" ya da "@"
# ile BAŞLIYORSA bunu (dosya CSV olarak açıldığında ya da bazı akışlarda
# .xlsx'te bile) bir FORMÜL sanabilir ("CSV/Formula Injection", CWE-1236).
# Bu sütunlardaki metin KULLANICININ YÜKLEDİĞİ belgeden gelir -- bir madde
# metni gayet doğal biçimde "- İlgili birim..." gibi bir liste öğesiyle
# BAŞLAYABİLİR; bu tesadüfi içerik bile kötü niyetli bir formül gibi
# yorumlanabilir. Kaçırılması gereken sütunlar SADECE belge içeriğinden
# gelenlerdir -- "Değişim Türü" bizim ÜRETTİĞİMİZ sabit bir etikettir,
# madde numaraları int/None'dır, bu yüzden ikisi de bu riski TAŞIMAZ.
_FORMULA_INJECTION_TRIGGER_CHARS = ("=", "+", "-", "@")
_SPREADSHEET_INJECTION_RISK_COLUMNS = (
    "Başlık",
    "Eski Bölüm",
    "Yeni Bölüm",
    "Eski Metin",
    "Yeni Metin",
)


def _neutralize_formula_prefix(value: str) -> str:
    """
    Formül enjeksiyonuna karşı savunma: metin bir formül tetikleyici
    karakterle başlıyorsa başına bir tek tırnak (') eklenir -- bu, Excel/
    LibreOffice'i hücreyi DÜZ METİN olarak yorumlamaya zorlar; görünen
    İÇERİĞİ (tek tırnak dışında) DEĞİŞTİRMEZ.
    """
    if value and value[0] in _FORMULA_INJECTION_TRIGGER_CHARS:
        return f"'{value}"
    return value


def build_summary_dataframe(result: ComparisonResult) -> pd.DataFrame:
    """
    İÇERİK DURUMU: her ChangeType için bir satır (sayı + yüzde) -- kapalı
    kümenin TAMAMI, sayısı 0 olanlar DAHİL (bkz. ComparisonResult.counts
    NEDEN notu). YAPISAL değişiklikler için bkz. build_structural_dataframe
    -- BAĞIMSIZ bir boyut olduğu için AYRI bir tabloda tutulur, bu ikisi
    TEK bir tabloda birleştirilseydi "toplam" satırı yanıltıcı olurdu.
    """
    counts = result.counts()
    total = sum(counts.values())
    rows = []
    for change_type in ChangeType:
        count = counts[change_type]
        pct = round(count / total * 100, 1) if total else 0.0
        rows.append(
            {
                "Değişim Türü": CHANGE_TYPE_LABELS_TR[change_type.value],
                "Sayı": count,
                "Yüzde": pct,
            }
        )
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)


def build_structural_dataframe(result: ComparisonResult) -> pd.DataFrame:
    """
    YAPISAL DEĞİŞİKLİKLER: Numarası Değişti / Bölümü Değişti sayıları --
    İÇERİK durumundan BAĞIMSIZ (bkz. ComparisonResult.structural_counts
    NEDEN notu), bu yüzden YÜZDE sütunu YOK -- iki satır birbirini
    dışlamadığı için "toplamın yüzdesi" kavramı burada anlamsızdır.
    """
    structural = result.structural_counts()
    rows = [
        {"Yapısal Değişiklik": CHANGE_TYPE_LABELS_TR["RENUMBERED"], "Sayı": structural["RENUMBERED"]},
        {"Yapısal Değişiklik": CHANGE_TYPE_LABELS_TR["MOVED"], "Sayı": structural["MOVED"]},
    ]
    return pd.DataFrame(rows, columns=_STRUCTURAL_COLUMNS)


def _bolum_adi(section: Section) -> str:
    """heading_path'in SON elemanı (MADDE N/GEÇİCİ MADDE N) HARİÇ, KISIM/BÖLÜM zinciri."""
    return " > ".join(section.heading_path[:-1])


def build_section_breakdown(result: ComparisonResult) -> pd.DataFrame:
    """
    Her KISIM/BÖLÜM için İÇERİK DURUMU sayımı (Değişmedi/Değişti/Yeni
    Eklendi/Kaldırıldı) -- kullanıcının "hangi bölümde daha fazla
    değişiklik var" sorusuna, madde madde değil BÖLÜM düzeyinde cevap
    verir.

    NEDEN YAPISAL bayraklar (numarasi_degisti/yeri_degisti) BU TABLODA
    YOK: build_summary_dataframe/build_structural_dataframe'deki AYNI
    gerekçeyle (bkz. o modülün NEDEN notu) -- içerik durumu ile yapısal
    bayraklar BAĞIMSIZ boyutlardır, TEK bir tabloda karıştırılırsa
    "toplam" satırı yanıltıcı olur. Bölüm bazında "en çok değişen bölüm"
    HANGİSİ sorusunun cevabı (içerik+yapısal birleşik) hâlâ
    SummaryStats.en_cok_degisen_bolumler'dadır (bkz. summary_builder.py)
    -- burası SADECE içerik durumu dökümüdür.

    NEDEN heading_path'i olmayan Section'lar BOLUMSUZ_ETIKETI altında
    toplanır, SESSİZCE atlanmaz: aksi halde bu tablodaki sayıların toplamı
    result.counts() toplamından daha AZ çıkar, "nereye kayboldu" sorusu
    cevapsız kalırdı.

    NEDEN satır sırası belgedeki İLK GÖRÜLME SIRASINA göre (alfabetik
    DEĞİL): "BİRİNCİ BÖLÜM" < "İKİNCİ BÖLÜM" < ... < "ONUNCU BÖLÜM"
    alfabetik sıralamada YANLIŞ sıraya girer (örn. "İKİNCİ" harf olarak
    "BİRİNCİ"den önce gelmez ama alfabetik olarak da doğru sırayı
    GARANTİ ETMEZ) -- belge sırası HER ZAMAN doğru okuma sırasıdır.
    """
    sayac: dict[str, dict[ChangeType, int]] = {}
    ilk_gorulme: dict[str, int] = {}
    for sira, row in enumerate(result.rows):
        c = row.classified
        section = c.old or c.new
        bolum = _bolum_adi(section) or BOLUMSUZ_ETIKETI
        sayac.setdefault(bolum, dict.fromkeys(ChangeType, 0))
        sayac[bolum][c.change_type] += 1
        ilk_gorulme.setdefault(bolum, sira)

    bolumler = sorted(sayac, key=lambda b: ilk_gorulme[b])
    rows = []
    for bolum in bolumler:
        row_dict: dict[str, object] = {"Bölüm": bolum}
        for change_type in ChangeType:
            row_dict[CHANGE_TYPE_LABELS_TR[change_type.value]] = sayac[bolum][change_type]
        rows.append(row_dict)
    return pd.DataFrame(rows, columns=_SECTION_BREAKDOWN_COLUMNS)


def _ilk_sayfa_no(units: list[TextUnit]) -> int | None:
    """
    render_source_link'teki (src/ui/components.py) AYNI ilk-dolu-sayfa
    deseni -- DOCX'te (sayfa kavramı YOK, bkz. o modülün NEDEN notu) veya
    provenance eksikse None döner.
    """
    return next((u.page_no for u in units if u.page_no is not None), None)


def build_temporal_changes_table(result: ComparisonResult) -> pd.DataFrame:
    """
    Mimari Ek 2 -- tarihsel/sayısal değişiklik dökümü: her TemporalChange
    (bkz. pipeline.py::ComparisonResult.temporal_changes) için bir satır.

    NEDEN "paired" olmayan (sadece kaldırılan VEYA sadece eklenen)
    değişiklikler de AYNI tabloda, ayrı bir tabloya BÖLÜNMEDEN: her ikisi
    de kullanıcının "bu maddede tarih/süre ile ilgili ne değişti" sorusuna
    cevaptır -- eşleştirilmiş olup olmadığı "Eski Değer"/"Yeni Değer"
    sütunlarından (biri "—" ise eşleştirilmemiş) zaten ANLAŞILIR, ayrı bir
    tablo kullanıcıya aynı bilgiyi iki yerde aratırdı.

    NEDEN sayfa numarası OLD/NEW sırasıyla düşer (biri yoksa diğerine):
    "hangi sayfada geçiyor" sorusunun en doğal cevabı DEĞİŞİKLİĞİN
    KAYNAĞI olan cümledir -- kaldırılan bir ifade için bu HER ZAMAN eski
    belgedeki sayfadır, eklenen için yeni belgedeki sayfadır; eşleştirilmiş
    (paired) bir değişiklikte önce eski belge tercih edilir (kullanıcı
    genelde "nereden değişti" sorusunu sorar).
    """
    rows = []
    for change in result.temporal_changes:
        madde_eski = change.match.old.madde_no
        madde_yeni = change.match.new.madde_no
        madde_etiketi = f"MADDE {madde_eski}" if madde_eski == madde_yeni else f"MADDE {madde_eski} → {madde_yeni}"

        kind = change.old.kind if change.old is not None else change.new.kind
        sayfa = None
        if change.old_sentence is not None:
            sayfa = _ilk_sayfa_no(change.old_sentence.units)
        if sayfa is None and change.new_sentence is not None:
            sayfa = _ilk_sayfa_no(change.new_sentence.units)

        rows.append(
            {
                "Madde": madde_etiketi,
                "Tür": TEMPORAL_EXPRESSION_KIND_LABELS_TR[kind.value],
                "Eski Değer": change.old.text if change.old is not None else _TEMPORAL_BOS_DEGER,
                "Yeni Değer": change.new.text if change.new is not None else _TEMPORAL_BOS_DEGER,
                "Sayfa": sayfa if sayfa is not None else _TEMPORAL_BOS_DEGER,
            }
        )
    return pd.DataFrame(rows, columns=_TEMPORAL_CHANGES_COLUMNS)


def build_detail_dataframe(result: ComparisonResult) -> pd.DataFrame:
    """
    Her karşılaştırma satırı (eşleşmiş ya da açıkta kalmış Section) için bir
    satır -- "Değişim Türü" İÇERİK durumu, "Numarası Değişti"/"Yeri
    Değişti" BAĞIMSIZ yapısal bayraklardır (bkz. classifier.py NEDEN notu;
    bir satırda İKİSİ de "Evet" olabilir, örn. ground_truth.json/
    birim_sorumlulukları). Belge içeriğinden gelen sütunlar (bkz.
    _SPREADSHEET_INJECTION_RISK_COLUMNS) formül enjeksiyonuna karşı
    kaçırılır (_neutralize_formula_prefix).
    """
    rows = []
    for row in result.rows:
        c = row.classified
        rows.append(
            {
                "Değişim Türü": CHANGE_TYPE_LABELS_TR[c.change_type.value],
                "Numarası Değişti": "Evet" if c.numarasi_degisti else "Hayır",
                CHANGE_TYPE_LABELS_TR["MOVED"]: "Evet" if c.yeri_degisti else "Hayır",
                "Eski Madde No": c.old.madde_no if c.old else None,
                "Yeni Madde No": c.new.madde_no if c.new else None,
                "Başlık": (c.old.baslik if c.old else c.new.baslik) or "",
                "Eski Bölüm": " > ".join(c.old.heading_path[:-1]) if c.old else "",
                "Yeni Bölüm": " > ".join(c.new.heading_path[:-1]) if c.new else "",
                "Eski Metin": c.old.joined_text if c.old else "",
                "Yeni Metin": c.new.joined_text if c.new else "",
            }
        )
    df = pd.DataFrame(rows, columns=_DETAIL_COLUMNS)
    for col in _SPREADSHEET_INJECTION_RISK_COLUMNS:
        df[col] = df[col].map(_neutralize_formula_prefix)
    return df
