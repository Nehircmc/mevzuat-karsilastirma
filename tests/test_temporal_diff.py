"""
src/analysis/temporal_diff.py testleri.

Buradaki dört senaryo (MADDE 2/3/5) görev geçmişinde ÖNCE sentetik
Python string'leriyle, SONRA gerçek bir PDF çifti (scratchpad'de üretildi,
depoya commit EDİLMEDİ) üzerinden gerçek ingestion/structure_parser/
section_matcher/differ.py boru hattından geçirilerek doğrulandı -- burada
AYNI metinler, differ.py::diff_section_match'in GERÇEK çıktısı üzerinden
(Section/SectionMatch nesneleri elle kurulsa da, hizalama gerçek differ.py
kodudur) birim test olarak sabitleniyor.

NEDEN eşleştirme riski (adversaryal senaryo) özellikle test ediliyor: bkz.
temporal_diff.py modül NEDEN notu -- SequenceMatcher'ın pozisyonel "replace
bloğu" eşleştirmesi, alakasız iki cümleyi (her ikisi de tesadüfen bir
tarih/süre içeriyorsa) yanlışlıkla "X -> Y değişti" diye eşleştirebilir.
TestAdversaryalEslestirme bu YANLIŞ POZİTİFİN önlendiğini kanıtlar.
"""

from __future__ import annotations

from src.analysis.differ import diff_section_match
from src.analysis.section_matcher import SectionMatch
from src.analysis.temporal_diff import diff_temporal_expressions
from src.models import Section, TextUnit
from src.parsing.temporal_expressions import TemporalExpressionKind


def _unit(text: str, *, page_no: int | None = 1) -> TextUnit:
    return TextUnit(
        doc_id="test", page_no=page_no, block_index=0,
        char_start=0, char_end=len(text), heading_path=(), text=text,
    )


def _section(text: str, *, madde_no: int, doc_id: str, page_no: int | None = 1) -> Section:
    return Section(
        doc_id=doc_id,
        heading_path=(f"MADDE {madde_no}",),
        section_type="MADDE",
        madde_no=madde_no,
        baslik=None,
        order_index=madde_no,
        units=[_unit(text, page_no=page_no)],
    )


def _match(old_text: str, new_text: str, *, madde_no: int = 1) -> SectionMatch:
    old = _section(old_text, madde_no=madde_no, doc_id="eski")
    new = _section(new_text, madde_no=madde_no, doc_id="yeni")
    return SectionMatch(old=old, new=new, method="NUMBER_AND_TITLE")


class TestGercekDegisiklikPaired:
    """MADDE 2 senaryosu: aynı cümle, sadece süre miktarı değişmiş -- YÜKSEK
    kelime benzerliği (0.80) -> eşleştirilmiş (paired) rapor edilmeli."""

    def test_sure_degisikligi_eslestirilir(self):
        match = _match(
            "Başvurular 30 gün içinde değerlendirilir.",
            "Başvurular 45 gün içinde değerlendirilir.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 1
        c = changes[0]
        assert c.paired is True
        assert c.old.kind == TemporalExpressionKind.DURATION
        assert c.old.text == "30 gün"
        assert c.new.text == "45 gün"

    def test_yaziyla_sureden_rakamla_sureye_degisiklik_eslestirilir(self):
        # NEDEN: "otuz gün" -> "45 gün" YAZIM biçimi değişse bile bu
        # GERÇEK bir değer değişikliğidir (30 -> 45) -- normalized_value
        # rakamlı/yazılı biçimden BAĞIMSIZ olduğu için (bkz.
        # temporal_expressions.py) old_keys != new_keys doğru tespit
        # edilir, kelime benzerliği yüksek olduğu için eşleştirilir.
        match = _match(
            "Başvurular otuz gün içinde değerlendirilir.",
            "Başvurular 45 gün içinde değerlendirilir.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 1
        assert changes[0].paired is True
        assert changes[0].old.text == "otuz gün"
        assert changes[0].new.text == "45 gün"

    def test_tarih_degisikligi_eslestirilir(self):
        match = _match(
            "Yönetmelik 14.11.2019 tarihinde yürürlüğe girer.",
            "Yönetmelik 5.3.2023 tarihinde yürürlüğe girer.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 1
        assert changes[0].paired is True
        assert changes[0].old.normalized_value == "2019-11-14"
        assert changes[0].new.normalized_value == "2023-03-05"


class TestAdversaryalEslestirme:
    """
    MADDE 3 senaryosu: madde BÜYÜK ÖLÇÜDE yeniden yazılmış, eski/yeni
    cümleler ALAKASIZ ama HER İKİSİ DE tesadüfen bir tarih/süre içeriyor.
    Kelime benzerliği DÜŞÜK (0.00/0.22) -> eşleştirme İDDİA EDİLMEMELİ,
    ifadeler BAĞIMSIZ iki olgu (kaldırıldı + eklendi) olarak raporlanmalı.
    """

    def test_alakasiz_tarihler_eslestirilmez(self):
        match = _match(
            "Sözleşme 1 Ocak 2018 tarihinde imzalanmıştır.",
            "Bu maddenin yürürlük tarihi 5 Mart 2023 olarak belirlenmiştir.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 2
        assert all(not c.paired for c in changes)
        kaldirilan = next(c for c in changes if c.old is not None)
        eklenen = next(c for c in changes if c.new is not None)
        assert kaldirilan.old.text == "1 Ocak 2018"
        assert eklenen.new.text == "5 Mart 2023"

    def test_alakasiz_sureler_eslestirilmez(self):
        match = _match(
            "Fesih bildirimi 90 gün önce yapılmalıdır.",
            "İtiraz süresi 15 gün olarak düzenlenmiştir.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 2
        assert all(not c.paired for c in changes)


class TestSadeceEklenenIfade:
    """MADDE 5 senaryosu: yeni bir cümle (dolayısıyla yeni bir tarih)
    eklenmiş -- eşleştirme iddiası OLMAMALI, sadece "eklendi"."""

    def test_yeni_cumledeki_tarih_eklendi_sayilir(self):
        match = _match(
            "Kurul, gerekli gördüğü hallerde toplanır.",
            "Kurul, gerekli gördüğü hallerde toplanır. Kurul ilk toplantısını 14 Kasım 2019 tarihinde yapar.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 1
        assert changes[0].paired is False
        assert changes[0].old is None
        assert changes[0].new.text == "14 Kasım 2019"


class TestSinirDurumAgirYenidenYazim:
    """
    Sentetik sınır durum (gerçek PDF'te doğrulanamadı, bkz. görev geçmişi --
    QA PDF üreticisindeki bir metin-ayrıştırma artefaktı MADDE 4'ü eşleşme
    dışı bıraktı): AYNI hükmün ağır yeniden yazımla değiştiği ama kelime
    benzerliğinin eşiğin (0.5) ALTINA düştüğü durum -- BİLİNÇLİ ödünleşim,
    eşleştirme iddia edilmez, ifadeler ayrı olgu olarak raporlanır.
    """

    def test_agir_yeniden_yazim_esik_altinda_ayri_olgu_olarak_raporlanir(self):
        match = _match(
            "Başvurular 30 gün içinde değerlendirilir ve sonuçlandırılır.",
            "Başvurular 45 gün içinde incelenerek karara bağlanır.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))

        assert len(changes) == 2
        assert all(not c.paired for c in changes)


class TestDegismeyenIfadeler:
    def test_ayni_cumlede_farkli_kisim_degisirse_ifade_degismemis_sayilir(self):
        match = _match(
            "Başvurular 30 gün içinde değerlendirilir ve karara bağlanır.",
            "Başvurular 30 gün içinde incelenir ve karara bağlanır.",
        )
        changes = diff_temporal_expressions(diff_section_match(match))
        assert changes == []

    def test_hicbir_tarih_sure_yoksa_bos_liste(self):
        match = _match("Bu maddenin amacı düzenleme yapmaktır.", "Bu maddenin amacı iş süreçlerini düzenlemektir.")
        changes = diff_temporal_expressions(diff_section_match(match))
        assert changes == []
