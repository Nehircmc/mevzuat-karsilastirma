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
from src.config import CHANGE_TYPE_LABELS_TR
from src.models import ChangeType

_SUMMARY_COLUMNS = ["Değişim Türü", "Sayı", "Yüzde"]
_DETAIL_COLUMNS = [
    "Değişim Türü",
    "Eski Madde No",
    "Yeni Madde No",
    "Başlık",
    "Eski Bölüm",
    "Yeni Bölüm",
    "Eski Metin",
    "Yeni Metin",
]


def build_summary_dataframe(result: ComparisonResult) -> pd.DataFrame:
    """
    Her ChangeType için bir satır (sayı + yüzde) -- kapalı kümenin TAMAMI,
    sayısı 0 olanlar DAHİL (bkz. ComparisonResult.counts NEDEN notu).
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


def build_detail_dataframe(result: ComparisonResult) -> pd.DataFrame:
    """Her karşılaştırma satırı (eşleşmiş ya da açıkta kalmış Section) için bir satır."""
    rows = []
    for row in result.rows:
        c = row.classified
        rows.append(
            {
                "Değişim Türü": CHANGE_TYPE_LABELS_TR[c.change_type.value],
                "Eski Madde No": c.old.madde_no if c.old else None,
                "Yeni Madde No": c.new.madde_no if c.new else None,
                "Başlık": (c.old.baslik if c.old else c.new.baslik) or "",
                "Eski Bölüm": " > ".join(c.old.heading_path[:-1]) if c.old else "",
                "Yeni Bölüm": " > ".join(c.new.heading_path[:-1]) if c.new else "",
                "Eski Metin": c.old.joined_text if c.old else "",
                "Yeni Metin": c.new.joined_text if c.new else "",
            }
        )
    return pd.DataFrame(rows, columns=_DETAIL_COLUMNS)
