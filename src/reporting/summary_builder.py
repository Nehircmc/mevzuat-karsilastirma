"""
Adım 7: Yönetici Özeti -- TAMAMEN ŞABLON TABANLI, sayısal verilere dayalı.

NEDEN "serbest metin" ÜRETİLMİYOR (Mimari İlke C, bkz. models.py::ChangeType
NEDEN notu): analiz katmanı kapalı bir ChangeType sözlüğünün DIŞINA
çıkamıyorsa, bu sözlüğün SAYIMLARINDAN türetilen özet de aynı disiplinle
üretilmeli -- "madde X önemli ölçüde değişti" gibi YORUM içeren bir cümle
ASLA üretilmez (bu bir LLM/NLP yorumu olurdu, hangi metnin "önemli" olduğuna
dair GİZLİ bir karar verir ve doğrulanamaz). Bu modülün ürettiği HER cümle,
SABİT bir şablona ham sayıları (adet, yüzde, ChangeType Türkçe etiketi)
yerleştirir -- iki farklı çalıştırma AYNI ComparisonResult'tan HER ZAMAN
BİREBİR aynı özeti üretir (deterministik, test edilebilir).

İki ayrı formatlayıcı (bkz. render_summary_markdown burada, render_summary_
html html_renderer.py'de) AYNI SummaryStats'ı tüketir -- "hangi sayılar
gösterilecek" (burada) ile "nasıl biçimlendirilecek" (Markdown/HTML) ayrı
kaygılardır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.pipeline import ComparisonResult
from src.config import CHANGE_TYPE_LABELS_TR
from src.models import ChangeType, Section


@dataclass(frozen=True)
class SummaryStats:
    """
    Yönetici Özeti'nin dayandığı TÜM sayısal veriler -- metin/HTML
    formatlayıcılardan (render_summary_markdown, html_renderer.render_summary_
    html) AYRI tutulur ki her biri kendi biçimlendirme kaygısına
    odaklanabilsin, sayı hesaplama mantığı TEK yerde (bu modülde) kalsın.
    """

    toplam_karsilastirma: int
    eski_toplam_madde: int
    yeni_toplam_madde: int
    sayilar: dict[ChangeType, int]
    yuzdeler: dict[ChangeType, float]  # 0-100 arası, virgülden sonra 1 hane
    # (bölüm adı, o bölümdeki IDENTICAL-olmayan madde sayısı) -- hiç
    # değişiklik yoksa ya da hiçbir Section'ın bölüm bilgisi yoksa None.
    en_cok_degisen_bolum: tuple[str, int] | None = field(default=None)


def _bolum_adi(section: Section) -> str:
    """heading_path'in SON elemanı (MADDE N/GEÇİCİ MADDE N) HARİÇ, KISIM/BÖLÜM zinciri."""
    return " > ".join(section.heading_path[:-1])


def _en_cok_degisen_bolum(result: ComparisonResult) -> tuple[str, int] | None:
    """
    IDENTICAL OLMAYAN maddeleri bölüme göre sayar, en çok sayıya sahip
    bölümü döndürür.

    NEDEN eşitlikte belgedeki İLK GÖRÜLME SIRASI belirleyici: birden fazla
    bölüm AYNI sayıda değişikliğe sahipse, rastgele/dict-sıralamasına bağlı
    bir sonuç yerine DETERMİNİSTİK (her çalıştırmada aynı) bir sonuç
    gerekir -- testler de buna karşı doğrulanabilsin diye.
    """
    sayac: dict[str, int] = {}
    ilk_gorulme: dict[str, int] = {}
    for sira, row in enumerate(result.rows):
        if row.classified.change_type == ChangeType.IDENTICAL:
            continue
        section = row.classified.old or row.classified.new
        bolum = _bolum_adi(section)
        if not bolum:
            continue
        sayac[bolum] = sayac.get(bolum, 0) + 1
        ilk_gorulme.setdefault(bolum, sira)

    if not sayac:
        return None
    en_iyi = min(sayac, key=lambda b: (-sayac[b], ilk_gorulme[b]))
    return en_iyi, sayac[en_iyi]


def build_summary_stats(result: ComparisonResult) -> SummaryStats:
    """ComparisonResult'tan Yönetici Özeti'nin ihtiyaç duyduğu TÜM sayıları hesaplar."""
    sayilar = result.counts()
    toplam = sum(sayilar.values())
    yuzdeler = {
        change_type: (round(count / toplam * 100, 1) if toplam else 0.0)
        for change_type, count in sayilar.items()
    }
    eski_toplam = sum(1 for row in result.rows if row.classified.old is not None)
    yeni_toplam = sum(1 for row in result.rows if row.classified.new is not None)

    return SummaryStats(
        toplam_karsilastirma=toplam,
        eski_toplam_madde=eski_toplam,
        yeni_toplam_madde=yeni_toplam,
        sayilar=sayilar,
        yuzdeler=yuzdeler,
        en_cok_degisen_bolum=_en_cok_degisen_bolum(result),
    )


def render_summary_markdown(stats: SummaryStats) -> str:
    """
    SummaryStats'ı Streamlit'in st.markdown() ile göstereceği bir Markdown
    metnine çevirir -- SABİT şablon + sayı yerleştirme, serbest metin YOK.
    """
    lines = [
        "## Yönetici Özeti",
        "",
        (
            f"Eski belgede **{stats.eski_toplam_madde}**, yeni belgede "
            f"**{stats.yeni_toplam_madde}** madde bulundu; toplam "
            f"**{stats.toplam_karsilastirma}** karşılaştırma birimi sınıflandırıldı."
        ),
        "",
    ]
    for change_type in ChangeType:
        count = stats.sayilar[change_type]
        pct = stats.yuzdeler[change_type]
        label = CHANGE_TYPE_LABELS_TR[change_type.value]
        lines.append(f"- **{label}**: {count} madde (%{pct})")

    if stats.en_cok_degisen_bolum is not None:
        bolum, sayi = stats.en_cok_degisen_bolum
        lines.append("")
        lines.append(f"En çok değişiklik **{bolum}** bölümünde görüldü ({sayi} madde).")

    return "\n".join(lines)
