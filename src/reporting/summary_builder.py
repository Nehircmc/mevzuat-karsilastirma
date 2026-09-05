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

from src.analysis.classifier import ClassifiedSection
from src.analysis.pipeline import ComparisonResult
from src.config import CHANGE_TYPE_LABELS_TR, SUMMARY_HIGHLIGHT_MAX_ITEMS_PER_CATEGORY
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
    sayilar: dict[ChangeType, int]  # İÇERİK durumu -- bkz. ComparisonResult.counts()
    yuzdeler: dict[ChangeType, float]  # 0-100 arası, virgülden sonra 1 hane
    # YAPISAL değişiklik sayıları -- {"RENUMBERED": n, "MOVED": n}. NEDEN
    # `sayilar`dan AYRI: içerik durumundan BAĞIMSIZ bir boyuttur, aynı
    # satır HEM bir içerik durumuna HEM bir yapısal bayrağa katkıda
    # bulunabilir (bkz. ComparisonResult.structural_counts() NEDEN notu)
    # -- bu yüzden `sayilar` ile TOPLANAMAZ.
    yapisal_sayilar: dict[str, int]
    # [(bölüm adı, o bölümde GERÇEKTEN bir şey değişen -- içerik VEYA
    # yapısal -- madde sayısı), ...] -- BİRDEN FAZLA bölüm AYNI (en yüksek)
    # sayıya sahipse HEPSİ listelenir (bkz. _en_cok_degisen_bolumler NEDEN
    # notu); hiç değişiklik yoksa ya da hiçbir Section'ın bölüm bilgisi
    # yoksa boş liste.
    en_cok_degisen_bolumler: list[tuple[str, int]] = field(default_factory=list)
    # Şablon tabanlı, SADECE metinsel olarak gözlemlenebilen olgulara
    # dayalı kısa cümleler (bkz. _one_cikan_degisiklikler NEDEN notu) --
    # hukuki/normatif YORUM İÇERMEZ, biçimlendiriciler (Markdown/HTML) bu
    # listeyi OLDUĞU GİBİ madde işaretli bir listeye çevirir.
    one_cikan_degisiklikler: list[str] = field(default_factory=list)


def _bolum_adi(section: Section) -> str:
    """heading_path'in SON elemanı (MADDE N/GEÇİCİ MADDE N) HARİÇ, KISIM/BÖLÜM zinciri."""
    return " > ".join(section.heading_path[:-1])


def _madde_etiketi(section: Section) -> str:
    """
    Bir maddeyi Yönetici Özeti'nde İSİMLENDİRMEK için kullanılan KISA
    etiket -- baslik VARSA doğrudan o (örn. "Veri Paylaşımı"), YOKSA
    heading_path'in SON elemanı ("MADDE 7" / "GEÇİCİ MADDE 1").

    NEDEN madde_no'dan yeniden inşa ETMİYORUZ ("MADDE {no}" gibi):
    heading_path zaten GEÇİCİ MADDE/MADDE ayrımını doğru taşır (bkz.
    structure_parser.py), aynı mantığı burada tekrar yazmak İKİ AYRI
    yerde aynı biçimlendirmeyi senkron tutma riski doğururdu.
    """
    if section.baslik:
        return section.baslik
    return section.heading_path[-1] if section.heading_path else "(başlıksız madde)"


def _hicbir_sey_degismedi(c: ClassifiedSection) -> bool:
    """content_type IDENTICAL VE ne numarası ne yeri değişmiş mi -- bkz. _en_cok_degisen_bolumler NEDEN notu."""
    return c.change_type == ChangeType.IDENTICAL and not c.numarasi_degisti and not c.yeri_degisti


def _en_cok_degisen_bolumler(result: ComparisonResult) -> list[tuple[str, int]]:
    """
    GERÇEKTEN bir şeyi değişen (içerik VEYA yapısal) maddeleri bölüme göre
    sayar, EN YÜKSEK sayıya sahip TÜM bölümleri döndürür (bir bölüm/bölümler
    -- birden fazla bölüm AYNI sayıda değişikliğe sahip olabilir, bu
    durumda TEK birini rastgele/dict-sıralamasına göre seçmek YANILTICI
    olurdu -- "en çok değişen bölüm buymuş" izlenimi verirken aslında
    eşit sayıda değişen başka bölümler de vardır).

    NEDEN "değişiklik" burada change_type != IDENTICAL VEYA numarasi_degisti
    VEYA yeri_degisti (SADECE change_type != IDENTICAL DEĞİL): içeriği
    AYNI kalıp SADECE numarası/yeri değişen bir madde (bkz. classifier.py
    NEDEN notu) de bu bölümde bir "olay"dır -- content_type'a göre
    filtrelemek onu YOK SAYARDI, "bu bölümde hiçbir şey olmadı" yanlış
    izlenimini verirdi.

    NEDEN sonuç listesi belgedeki İLK GÖRÜLME SIRASINA göre sıralı:
    rastgele/dict-sıralamasına bağlı bir sonuç yerine DETERMİNİSTİK (her
    çalıştırmada aynı) bir sonuç gerekir -- testler de buna karşı
    doğrulanabilsin diye.
    """
    sayac: dict[str, int] = {}
    ilk_gorulme: dict[str, int] = {}
    for sira, row in enumerate(result.rows):
        c = row.classified
        if _hicbir_sey_degismedi(c):
            continue
        section = c.old or c.new
        bolum = _bolum_adi(section)
        if not bolum:
            continue
        sayac[bolum] = sayac.get(bolum, 0) + 1
        ilk_gorulme.setdefault(bolum, sira)

    if not sayac:
        return []
    en_yuksek = max(sayac.values())
    kazananlar = [bolum for bolum in sayac if sayac[bolum] == en_yuksek]
    kazananlar.sort(key=lambda b: ilk_gorulme[b])
    return [(bolum, en_yuksek) for bolum in kazananlar]


def _kategori_ozeti(basliklar: list[str], *, tekil_sablon: str, coklu_ek_sablon: str) -> list[str]:
    """
    Bir kategorideki (MODIFIED/ADDED/REMOVED) madde etiketlerini, EN FAZLA
    SUMMARY_HIGHLIGHT_MAX_ITEMS_PER_CATEGORY tanesi TEK TEK, kalanı (varsa)
    TOPLU tek bir cümleyle özetler -- NEDEN: bkz. config.py::
    SUMMARY_HIGHLIGHT_MAX_ITEMS_PER_CATEGORY NEDEN notu (kısalık).

    `tekil_sablon` bir madde etiketi ("{}"), `coklu_ek_sablon` kalan
    sayıyı ("{}") biçimlendirir -- HER İKİSİ de SADECE ad/sayı yerleştirir,
    yorum İÇERMEZ.
    """
    sinir = SUMMARY_HIGHLIGHT_MAX_ITEMS_PER_CATEGORY
    satirlar = [tekil_sablon.format(etiket) for etiket in basliklar[:sinir]]
    kalan = len(basliklar) - sinir
    if kalan > 0:
        satirlar.append(coklu_ek_sablon.format(kalan))
    return satirlar


def _one_cikan_degisiklikler(result: ComparisonResult) -> list[str]:
    """
    "Öne Çıkan Değişiklikler" -- teknik olmayan bir okuyucu için KISA,
    SADECE metinsel olarak gözlemlenebilen olgulara dayalı cümle listesi.

    NEDEN "yorum" ÜRETİLMİYOR (bkz. modül başı NEDEN notu -- Mimari İlke
    C'nin doğal uzantısı): her cümle SABİT bir şablona ("{etiket} maddesi
    ... tespit edildi/eklendi/bulunmuyor/değişti") madde etiketi veya ham
    sayı yerleştirir -- "önemli", "riskli", "kapsamlı" gibi bir NİTELEME
    kelimesi HİÇBİR ŞABLONDA yer almaz; hangi maddenin "öne çıktığı" bir
    yargı değil, SADECE değişiklik listesinin (MODIFIED/ADDED/REMOVED/
    RENUMBERED/MOVED) ilk N öğesidir.

    NEDEN sıralama MODIFIED -> REMOVED -> ADDED -> RENUMBERED -> MOVED:
    her kategori İÇİNDE belge sırası (order_index, bkz. pipeline.py
    rows.sort) korunur; kategoriler arası sıra SABİTTİR (her çalıştırmada
    aynı) -- kullanıcı geri bildirimindeki örnekle aynı sırayı izler.
    """
    modified: list[str] = []
    removed: list[str] = []
    added: list[str] = []
    for row in result.rows:
        c = row.classified
        section = c.old or c.new
        if c.change_type == ChangeType.MODIFIED:
            modified.append(_madde_etiketi(section))
        elif c.change_type == ChangeType.REMOVED:
            removed.append(_madde_etiketi(section))
        elif c.change_type == ChangeType.ADDED:
            added.append(_madde_etiketi(section))

    satirlar: list[str] = []
    satirlar.extend(
        _kategori_ozeti(
            modified,
            tekil_sablon="{} maddesinde içerik değişikliği tespit edildi.",
            coklu_ek_sablon="İçeriği değişen {} madde daha var.",
        )
    )
    satirlar.extend(
        _kategori_ozeti(
            removed,
            tekil_sablon="{} maddesi yeni belgede bulunmuyor.",
            coklu_ek_sablon="Yeni belgede bulunmayan {} madde daha var.",
        )
    )
    satirlar.extend(
        _kategori_ozeti(
            added,
            tekil_sablon="{} maddesi yeni belgede eklendi.",
            coklu_ek_sablon="Yeni belgede eklenen {} madde daha var.",
        )
    )

    renumbered = sum(1 for row in result.rows if row.classified.numarasi_degisti)
    if renumbered > 0:
        satirlar.append(f"{renumbered} maddenin numarası değişti.")
    moved = sum(1 for row in result.rows if row.classified.yeri_degisti)
    if moved > 0:
        satirlar.append(f"{moved} maddenin bölümü değişti.")

    return satirlar


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
        yapisal_sayilar=result.structural_counts(),
        en_cok_degisen_bolumler=_en_cok_degisen_bolumler(result),
        one_cikan_degisiklikler=_one_cikan_degisiklikler(result),
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
    lines.append("### İçerik Durumu")
    for change_type in ChangeType:
        count = stats.sayilar[change_type]
        pct = stats.yuzdeler[change_type]
        label = CHANGE_TYPE_LABELS_TR[change_type.value]
        lines.append(f"- **{label}**: {count} madde (%{pct})")

    # NEDEN AYRI bir başlık altında: yapısal sayılar içerik durumundan
    # BAĞIMSIZ bir boyuttur -- aynı madde HEM içerik durumu listesinde HEM
    # burada görünebilir, bu NORMALDİR ve "toplam değişen madde" hesabına
    # dahil edilmemelidir (bkz. modül NEDEN notu).
    lines.append("")
    lines.append("### Yapısal Değişiklikler")
    lines.append(
        f"- **{CHANGE_TYPE_LABELS_TR['RENUMBERED']}**: "
        f"{stats.yapisal_sayilar['RENUMBERED']} maddede madde numarası değişikliği tespit edildi."
    )
    lines.append(
        f"- **{CHANGE_TYPE_LABELS_TR['MOVED']}**: "
        f"{stats.yapisal_sayilar['MOVED']} maddede bölümü değişikliği tespit edildi."
    )

    if stats.en_cok_degisen_bolumler:
        sayi = stats.en_cok_degisen_bolumler[0][1]
        bolumler = ", ".join(f"**{bolum}**" for bolum, _ in stats.en_cok_degisen_bolumler)
        cogul = len(stats.en_cok_degisen_bolumler) > 1
        lines.append("")
        lines.append(
            f"En çok değişiklik {bolumler} {'bölümlerinde' if cogul else 'bölümünde'} görüldü ({sayi} madde)."
        )

    if stats.one_cikan_degisiklikler:
        lines.append("")
        lines.append("### Öne Çıkan Değişiklikler")
        for madde in stats.one_cikan_degisiklikler:
            lines.append(f"- {madde}")

    return "\n".join(lines)
