"""DocumentLoader soyut arayüzü -- tüm format-özel loader'lar bunu uygular."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.models import Document


class NoTextLayerError(Exception):
    """
    Belgede yeterli metin katmanı bulunamadığında fırlatılır.

    NEDEN: Onaylanmış Karar #1 gereği OCR/taranmış PDF kapsam dışıdır VE
    sistem bu durumda SESSİZCE boş sonuç dönemez -- kullanıcı "karşılaştırma
    yapıldı ama hiçbir şey bulunamadı" yanılgısına düşmemeli. Bu istisna
    açıkça yakalanıp UI'da (Adım 6) kullanıcıya gösterilmek üzere tasarlandı.
    """


class CorruptDocumentError(Exception):
    """
    Dosya uzantısı doğru (.pdf/.docx) ama İÇERİK bozuk/okunamaz olduğunda
    fırlatılır (örn. PyMuPDF'in FileDataError'ı, python-docx'in
    PackageNotFoundError'ı).

    NEDEN format-özel kütüphane istisnaları (pymupdf.FileDataError,
    docx.opc.exceptions.PackageNotFoundError) burada SARILIYOR: app.py
    (Mimari İlke D) format/kütüphane bilgisi TAŞIMAMALI -- SADECE
    src/ingestion/base.py'nin tanımladığı kapalı istisna kümesini (bu ve
    NoTextLayerError) yakalayabilmeli. Loader'lar DEĞİŞTİĞİNDE (örn.
    PyMuPDF yerine başka bir kütüphane) UI kodunun DEĞİŞMESİ GEREKMEMELİ.
    """


class DocumentLoader(ABC):
    """
    Format-özel loader'ların uyması gereken sözleşme.

    NEDEN soyut: app.py ve factory.py somut formatı (PDF/DOCX) bilmeden
    `loader.load(...)` çağırabilmeli (Mimari İlke D -- orkestrasyon
    katmanında iş mantığı/format bilgisi olmamalı).
    """

    @abstractmethod
    def load(self, path: str | Path, doc_id: str) -> Document:
        """
        Verilen dosyayı okuyup provenance'lı bir Document döndürür.

        Raises:
            NoTextLayerError: Belgede kullanılabilir metin katmanı yoksa.
        """
        raise NotImplementedError
