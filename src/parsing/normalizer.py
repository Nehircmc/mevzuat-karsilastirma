"""
Metin normalizasyonu -- satır sonu tireleme tamiri, boşluk/tırnak/tire
normalizasyonu.

ÖNEMLİ: Bu modül normalizasyonu OFFSET İZLENEBİLİRLİĞİNİ KORUYARAK yapar.
NEDEN: differ.py (Adım 5) normalize edilmiş metin üzerinde çalışacak ama
sonuçta üretilen her fark, TextUnit'in char_start/char_end'ine (yani
ORİJİNAL, normalize edilmemiş metne) geri izlenebilir olmalı (Mimari İlke A).
Normalizasyon uzunluk değiştiren bir işlemdir (tireleme birleştirme metni
kısaltır, boşluk sıkıştırma da öyle) -- bu yüzden basit bir "orijinal
uzunluk == normalize uzunluk" varsayımı YAPAMAYIZ; her çıktı karakteri için
kaynağın hangi orijinal indeksten geldiğini açıkça kaydediyoruz.
"""

from __future__ import annotations

from dataclasses import dataclass

# Türkçe metinlerde sık görülen "akıllı" tırnak ve tire varyantlarını
# standart ASCII karşılıklarına indirger. NEDEN: embedding modeli ve
# difflib için "aynı anlama gelen ama farklı bayt" varyantları gürültüdür.
_QUOTE_DASH_MAP: dict[str, str] = {
    "“": '"',  # “
    "”": '"',  # ”
    "„": '"',  # „
    "«": '"',  # «
    "»": '"',  # »
    "‘": "'",  # ‘
    "’": "'",  # ’
    "–": "-",  # – (en dash)
    "—": "-",  # — (em dash)
    "−": "-",  # − (minus sign)
}


@dataclass(frozen=True)
class NormalizedText:
    """
    Normalizasyon sonucu + orijinale geri haritalama tablosu.

    normalized_to_original[k]: normalize edilmiş metindeki k. karakterin,
    ORİJİNAL metindeki hangi indeksten türediğini tutar. Bu sayede normalize
    metin üzerinde bulunan herhangi bir [start, end) aralığı, map_span ile
    orijinal metindeki karşılığına çevrilebilir.
    """

    original: str
    normalized: str
    normalized_to_original: tuple[int, ...]

    def map_span(self, norm_start: int, norm_end: int) -> tuple[int, int]:
        """Normalize metindeki [norm_start, norm_end) aralığını orijinale çevirir."""
        if norm_start >= norm_end:
            pos = (
                self.normalized_to_original[norm_start]
                if norm_start < len(self.normalized_to_original)
                else len(self.original)
            )
            return pos, pos

        orig_start = self.normalized_to_original[norm_start]
        orig_end = self.normalized_to_original[norm_end - 1] + 1
        return orig_start, orig_end


def normalize(text: str) -> NormalizedText:
    """Orijinal metni normalize eder ve offset haritasını üretir."""
    output_chars: list[str] = []
    mapping: list[int] = []
    last_was_space_output = False

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # 1) Satır sonu tireleme tamiri: "gerçek-\nleştirme" -> "gerçekleştirme".
        # NEDEN sadece harf-harf arasında: sayı/parantez gibi bağlamlarda
        # tire kelime bölme değil gerçek bir ayraçtır, birleştirilmemeli.
        if (
            ch == "-"
            and i > 0
            and text[i - 1].isalpha()
            and i + 1 < n
            and text[i + 1] == "\n"
            and i + 2 < n
            and text[i + 2].isalpha()
        ):
            i += 2  # '-' ve '\n' çıktıya YAZILMAZ; kelimenin iki yarısı birleşir
            last_was_space_output = False
            continue

        # 2) Türkçe tırnak / tire normalizasyonu
        replacement = _QUOTE_DASH_MAP.get(ch)
        if replacement is not None:
            output_chars.append(replacement)
            mapping.append(i)
            last_was_space_output = False
            i += 1
            continue

        # 3) Çoklu boşluk sıkıştırma (satır sonu dahil tüm boşluk türleri)
        if ch.isspace():
            if not last_was_space_output:
                output_chars.append(" ")
                mapping.append(i)
                last_was_space_output = True
            i += 1
            continue

        output_chars.append(ch)
        mapping.append(i)
        last_was_space_output = False
        i += 1

    return NormalizedText(
        original=text,
        normalized="".join(output_chars),
        normalized_to_original=tuple(mapping),
    )
