"""Uzantıya göre doğru loader'ı seçer."""

from __future__ import annotations

from pathlib import Path

from src.config import SUPPORTED_EXTENSIONS
from src.ingestion.base import DocumentLoader
from src.ingestion.docx_loader import DOCXLoader
from src.ingestion.pdf_loader import PDFLoader

_LOADERS: dict[str, type[DocumentLoader]] = {
    ".pdf": PDFLoader,
    ".docx": DOCXLoader,
}


def get_loader(path: str | Path) -> DocumentLoader:
    """
    Dosya uzantısına göre uygun DocumentLoader örneğini döndürür.

    NEDEN uzantı kontrolü burada MERKEZİ: desteklenmeyen bir format (örn.
    taranmış .pdf içeren OCR gerektiren akışlar ya da .doc) sisteme sessizce
    girmesin; hata mesajı SUPPORTED_EXTENSIONS'ı referans göstererek net olsun.
    """
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Desteklenmeyen dosya uzantısı: '{suffix}'. "
            f"Desteklenen uzantılar: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return _LOADERS[suffix]()
