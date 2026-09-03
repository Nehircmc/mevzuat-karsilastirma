"""
Madde/bölüm hiyerarşisi çıkarımı.

Adım 1'in bıraktığı iki tespit burada çözülüyor:
1) Bir PDF bloğu hem başlık hem MADDE satırını birlikte içerebilir
   ("Amaç\\nMADDE 1- ..."); bu yüzden sınıflandırma BLOK değil SATIR
   düzeyinde yapılır.
2) Bir madde sayfa sınırında bölünebilir (farklı bloklara/sayfalara
   yayılabilir); bu yüzden bir madde'nin gövdesi TEK bir TextUnit değil,
   birden fazla orijinal bloktan toplanan bir DİZİ olabilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import BOLUM_PATTERN, GECICI_MADDE_PATTERN, KISIM_PATTERN, MADDE_PATTERN
from src.models import Document, Section, TextUnit


@dataclass(frozen=True)
class _Line:
    """Bir TextUnit'in içindeki tek bir (boş olmayan, kırpılmış) satır."""

    unit: TextUnit
    start: int  # unit.text içindeki başlangıç ofseti (kırpılmış sınıra göre)
    end: int
    text: str  # kırpılmış satır metni


def _split_into_lines(unit: TextUnit) -> list[_Line]:
    """
    Bir birimin metnini, boş satırları atlayarak, offset'i koruyarak satırlara böler.

    NEDEN offset'i baştan-sona takip ediyoruz: bu satırlardan üretilecek
    gövde parçaları (bkz. _merge_spans) TextUnit sözleşmesi gereği kendi
    ebeveyn bloğuna göre DOĞRU char_start/char_end taşımalı.
    """
    lines: list[_Line] = []
    offset = 0
    for raw_line in unit.text.split("\n"):
        line_start = offset
        line_end = offset + len(raw_line)
        offset = line_end + 1  # atlanan "\n" karakteri için +1

        lstrip_count = len(raw_line) - len(raw_line.lstrip())
        rstrip_count = len(raw_line) - len(raw_line.rstrip())
        real_start = line_start + lstrip_count
        real_end = line_end - rstrip_count
        if real_start >= real_end:
            continue  # tamamen boş satır

        lines.append(_Line(unit=unit, start=real_start, end=real_end, text=unit.text[real_start:real_end]))
    return lines


def _merge_spans(
    spans: list[tuple[TextUnit, int, int]], heading_path: tuple[str, ...]
) -> list[TextUnit]:
    """
    Aynı ebeveyn bloktan gelen BİTİŞİK (start, end) aralıklarını TEK bir
    TextUnit'e birleştirir.

    NEDEN gerekli: bir madde tek bir blok içinde birden çok satıra
    yayılabilir (örn. fıkra (1)/(2)/(3)); bunları satır satır ayrı
    TextUnit'ler olarak tutmak yerine, aynı bloktan gelen bitişik parçaları
    TEK parça hâlinde saklamak hem daha az parçalanma hem de orijinal
    metindeki boşluk/satır yapısını (fıkralar arası \\n dahil) KORUR.
    """
    if not spans:
        return []

    def _make(unit: TextUnit, start: int, end: int) -> TextUnit:
        return TextUnit(
            doc_id=unit.doc_id,
            page_no=unit.page_no,
            block_index=unit.block_index,
            char_start=start,
            char_end=end,
            heading_path=heading_path,
            text=unit.text[start:end],
        )

    merged: list[TextUnit] = []
    cur_unit, cur_start, cur_end = spans[0]
    for unit, start, end in spans[1:]:
        if unit is cur_unit and start == cur_end:
            cur_end = end  # bitişik -- birleştir
        else:
            merged.append(_make(cur_unit, cur_start, cur_end))
            cur_unit, cur_start, cur_end = unit, start, end
    merged.append(_make(cur_unit, cur_start, cur_end))
    return merged


def parse_structure(document: Document) -> list[Section]:
    """
    Belgenin (blok bazlı) TextUnit listesini madde/bölüm hiyerarşisine göre
    Section'lara ayırır.

    Algoritma tüm satırları GLOBAL sırayla (blok/sayfa sınırlarını aşarak)
    tek geçişte tarar; bir BÖLÜM/KISIM/MADDE eşleşmesi mevcut section'ı
    kapatır, yapısal olmayan bir satır ise ya "sıradaki madde başlığı adayı"
    (bir sonraki satır MADDE ile eşleşiyorsa) ya da açık section'ın gövdesi
    olarak değerlendirilir.
    """
    all_lines: list[_Line] = []
    for unit in document.units:
        all_lines.extend(_split_into_lines(unit))

    sections: list[Section] = []
    current_bolum: str | None = None
    current_kisim: str | None = None
    current_section: Section | None = None
    current_spans: list[tuple[TextUnit, int, int]] = []
    pending_title: str | None = None

    def _finalize() -> None:
        nonlocal current_section, current_spans
        if current_section is not None:
            current_section.units = _merge_spans(current_spans, current_section.heading_path)
        current_section = None
        current_spans = []

    for i, line in enumerate(all_lines):
        m_bolum = BOLUM_PATTERN.match(line.text)
        m_kisim = KISIM_PATTERN.match(line.text)
        m_gecici = GECICI_MADDE_PATTERN.match(line.text)
        # NEDEN önce GEÇİCİ MADDE kontrolü: MADDE_PATTERN de teorik olarak
        # "GEÇİCİ MADDE 1"in "MADDE 1" kısmına yanlış eşleşebilir; GEÇİCİ
        # MADDE'yi önce eleyerek bunu engelliyoruz.
        m_madde = None if m_gecici else MADDE_PATTERN.match(line.text)

        if m_bolum:
            _finalize()
            current_bolum = f"{m_bolum.group(1)} BÖLÜM"
            # NEDEN current_kisim SIFIRLANMAZ: Türk mevzuat hiyerarşisinde
            # bir KISIM birden çok BÖLÜM içerir (KISIM > BÖLÜM > MADDE);
            # yeni bir BÖLÜM, içinde bulunduğu KISIM bağlamını GEÇERSİZ KILMAZ.
            pending_title = None
            continue

        if m_kisim:
            _finalize()
            current_kisim = f"{m_kisim.group(1)} KISIM"
            # NEDEN current_bolum SIFIRLANIR: yeni bir KISIM, bir önceki
            # KISIM'a ait BÖLÜM bağlamını devralamaz -- o BÖLÜM artık
            # kapsam dışıdır, yeni KISIM kendi BÖLÜM'lerini bekler.
            current_bolum = None
            pending_title = None
            continue

        if m_madde or m_gecici:
            _finalize()
            match = m_gecici or m_madde
            no = int(match.group(1))
            is_gecici = m_gecici is not None
            heading_label = f"GEÇİCİ MADDE {no}" if is_gecici else f"MADDE {no}"
            heading_path = tuple(p for p in (current_kisim, current_bolum, heading_label) if p)

            current_section = Section(
                doc_id=line.unit.doc_id,
                heading_path=heading_path,
                section_type="GECICI_MADDE" if is_gecici else "MADDE",
                madde_no=no,
                baslik=pending_title,
                order_index=len(sections),
                units=[],
            )
            sections.append(current_section)
            pending_title = None

            remainder = match.group(2)
            if remainder:
                abs_start = line.start + match.start(2)
                abs_end = line.start + match.end(2)
                current_spans.append((line.unit, abs_start, abs_end))
            continue

        # Yapısal olmayan satır: bir sonraki satır MADDE/GEÇİCİ MADDE ile
        # eşleşiyorsa bu satır o maddenin BAŞLIĞIDIR (içinde bulunduğumuz
        # section'ın gövdesi DEĞİL) -- bu yüzden mevcut section burada kapanır.
        next_is_madde = False
        if i + 1 < len(all_lines):
            next_text = all_lines[i + 1].text
            next_is_madde = bool(
                MADDE_PATTERN.match(next_text) or GECICI_MADDE_PATTERN.match(next_text)
            )

        if next_is_madde:
            _finalize()
            pending_title = line.text
            continue

        if current_section is not None:
            current_spans.append((line.unit, line.start, line.end))
        # else: bağlamsal satır (belge başlığı, bölüm alt başlığı vb.) -- atla

    _finalize()
    return sections
