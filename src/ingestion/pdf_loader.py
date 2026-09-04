"""
PyMuPDF tabanlı PDF loader.

NEDEN `import pymupdf` (ve `import fitz` DEĞİL): `fitz` ismi PyMuPDF'in eski/
deprecated import yoludur; güncel paket kendi adıyla (`pymupdf`) import
edilmeyi önerir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from src.config import (
    FOOTER_BAND_RATIO,
    HEADER_BAND_RATIO,
    HEADER_FOOTER_MIN_REPETITION_RATIO,
    MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER,
    MIN_PAGE_RATIO_WITH_TEXT_LAYER,
    PAGE_NUMBER_FOOTER_PATTERN,
)
from src.ingestion.base import CorruptDocumentError, DocumentLoader, NoTextLayerError
from src.models import Document, DocumentMeta, TextUnit

_WHITESPACE_RE = re.compile(r"\s+")
_DIGIT_RE = re.compile(r"\d+")


def _normalize_for_repetition(text: str) -> str:
    """
    Üstbilgi/altbilgi TEKRAR tespiti için anahtar üretir.

    NEDEN rakamları "#" ile değiştiriyoruz: "Sayfa 1", "Sayfa 2" gibi altbilgiler
    sayfa başına FARKLI metindir ama YAPISAL olarak aynı kalıptır; rakam
    normalizasyonu olmadan repetition-ratio bunları asla yakalayamaz.
    """
    collapsed = _WHITESPACE_RE.sub(" ", text).strip()
    return _DIGIT_RE.sub("#", collapsed)


class PDFLoader(DocumentLoader):
    """PDF -> provenance'lı TextUnit listesi. Blok bazlı çıkarım kullanır."""

    def load(self, path: str | Path, doc_id: str) -> Document:
        path = Path(path)
        try:
            pdf = pymupdf.open(path)
        except pymupdf.FileDataError as exc:
            # NEDEN pymupdf.FileDataError yakalanıyor: PyMuPDF'in KENDİ
            # istisnası, uzantısı .pdf olan ama içeriği bozuk/boş/geçersiz
            # bir dosyada fırlatılır (EmptyFileError bunun bir alt sınıfıdır,
            # ayrıca yakalamaya gerek yok). Bu, çağıranın (UI) PyMuPDF'e özgü
            # bir istisna türü BİLMESİNİ gerektirmemesi için CorruptDocumentError'a
            # (bkz. ingestion/base.py NEDEN notu) çevrilir.
            raise CorruptDocumentError(
                f"'{path}' bir PDF olarak açılamadı; dosya bozuk, boş ya da geçersiz olabilir."
            ) from exc
        try:
            self._assert_text_layer_present(pdf, path)

            page_blocks = self._extract_body_blocks_per_page(pdf)

            units: list[TextUnit] = []
            block_index = 0
            for page_no, blocks in page_blocks:
                for text in blocks:
                    units.append(
                        TextUnit(
                            doc_id=doc_id,
                            page_no=page_no,
                            block_index=block_index,
                            char_start=0,
                            char_end=len(text),
                            heading_path=(),
                            text=text,
                        )
                    )
                    block_index += 1

            meta = DocumentMeta(
                doc_id=doc_id,
                source_path=str(path),
                file_type="pdf",
                title=path.stem,
                page_count=pdf.page_count,
            )
            return Document(meta=meta, units=units)
        finally:
            pdf.close()

    def _assert_text_layer_present(self, pdf: pymupdf.Document, path: Path) -> None:
        """
        Metin katmanı doğrulaması.

        NEDEN sayfa ORANINA bakıyoruz, tek sayfaya değil: gerçek belgelerde
        boş bir sayfa (örn. "Bu sayfa bilinçli olarak boş bırakılmıştır")
        normaldir; asıl sorun belgenin GENELİNİN taranmış/OCR'siz olmasıdır.
        """
        if pdf.page_count == 0:
            raise NoTextLayerError(f"PDF hiç sayfa içermiyor: {path}")

        pages_with_text = 0
        for page in pdf:
            if len(page.get_text().strip()) >= MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER:
                pages_with_text += 1

        ratio = pages_with_text / pdf.page_count
        if ratio < MIN_PAGE_RATIO_WITH_TEXT_LAYER:
            raise NoTextLayerError(
                f"'{path}' dosyasında yeterli metin katmanı bulunamadı "
                f"(sayfaların yalnızca %{ratio * 100:.0f}'inde metin var). "
                "Taranmış/OCR'siz PDF bu sistemin kapsamı dışındadır."
            )

    def _extract_body_blocks_per_page(
        self, pdf: pymupdf.Document
    ) -> list[tuple[int, list[str]]]:
        """
        Üstbilgi/altbilgi ayıklanmış gövde bloklarını sayfa sayfa döndürür.

        NEDEN iki geçişli: tekrar oranı hesaplamak için ÖNCE tüm belgeyi
        taramamız (Geçiş 1), SONRA hangi bloğun gerçekten üstbilgi/altbilgi
        olduğuna karar vermemiz (Geçiş 2) gerekir -- tek geçişte sayfa 1'i
        işlerken sayfa 50'deki tekrarı bilemeyiz.
        """
        total_pages = pdf.page_count
        raw_pages: list[dict] = []  # page_no, height, blocks(list of dict)

        # Geçiş 1: bant sınıflandırması + tekrar sayaçları
        repetition_pages: dict[tuple[str, str], set[int]] = {}
        for page_index, page in enumerate(pdf):
            page_no = page_index + 1
            height = page.rect.height
            header_limit = height * HEADER_BAND_RATIO
            footer_limit = height * (1 - FOOTER_BAND_RATIO)

            page_blocks = []
            for block in page.get_text("blocks", sort=True):
                x0, y0, x1, y1, text, _block_no, block_type = block
                if block_type != 0:  # 0 = metin bloğu, 1 = görüntü
                    continue
                text = text.strip("\n")
                if not text.strip():
                    continue

                mid_y = (y0 + y1) / 2
                if mid_y <= header_limit:
                    band = "header"
                elif mid_y >= footer_limit:
                    band = "footer"
                else:
                    band = "body"

                page_blocks.append({"text": text, "band": band})

                if band in ("header", "footer"):
                    key = (band, _normalize_for_repetition(text))
                    repetition_pages.setdefault(key, set()).add(page_no)

            raw_pages.append({"page_no": page_no, "blocks": page_blocks})

        # Geçiş 2: tekrar oranına göre üstbilgi/altbilgi olarak işaretle, gövdeyi ayıkla
        result: list[tuple[int, list[str]]] = []
        for page_info in raw_pages:
            body_texts: list[str] = []
            for block in page_info["blocks"]:
                text = block["text"]
                band = block["band"]

                if band == "body":
                    body_texts.append(text)
                    continue

                key = (band, _normalize_for_repetition(text))
                ratio = len(repetition_pages.get(key, set())) / total_pages
                is_repeating_header_footer = ratio >= HEADER_FOOTER_MIN_REPETITION_RATIO
                # NEDEN ek regex kontrolü: kısa belgelerde (örn. 2 sayfa) tekrar
                # oranı istatistiksel olarak güçlü olmayabilir; "Sayfa N" gibi
                # bilinen kalıplar ayrıca doğrudan tanınır.
                is_known_page_number_pattern = band == "footer" and bool(
                    PAGE_NUMBER_FOOTER_PATTERN.match(text)
                )

                if is_repeating_header_footer or is_known_page_number_pattern:
                    continue  # üstbilgi/altbilgi -- gövdeye sızdırma

                # Bantta konumlanmış ama tekrar ETMEYEN blok: gerçek gövde metnidir.
                body_texts.append(text)

            result.append((page_info["page_no"], body_texts))

        return result
