"""
src/parsing/temporal_expressions.py testleri -- saf regex/normalizasyon
davranışı, Section/SectionMatch'ten bağımsız.
"""

from __future__ import annotations

from src.parsing.temporal_expressions import TemporalExpressionKind, find_temporal_expressions


class TestTarihIfadeleri:
    def test_nokta_ayracli_tarih(self):
        exprs = find_temporal_expressions("Yönetmelik 14.11.2019 tarihinde yürürlüğe girer.")
        assert len(exprs) == 1
        assert exprs[0].kind == TemporalExpressionKind.DATE
        assert exprs[0].text == "14.11.2019"
        assert exprs[0].normalized_value == "2019-11-14"

    def test_slash_ayracli_tarih(self):
        exprs = find_temporal_expressions("14/11/2019 tarihli belge.")
        assert exprs[0].normalized_value == "2019-11-14"

    def test_tr_ay_adiyla_tarih(self):
        exprs = find_temporal_expressions("Sözleşme 1 Ocak 2018 tarihinde imzalanmıştır.")
        assert len(exprs) == 1
        assert exprs[0].text == "1 Ocak 2018"
        assert exprs[0].normalized_value == "2018-01-01"

    def test_farkli_bicimde_yazilan_ayni_tarih_ayni_normalized_value_uretir(self):
        a = find_temporal_expressions("14.11.2019")[0]
        b = find_temporal_expressions("14 Kasım 2019")[0]
        assert a.normalized_value == b.normalized_value == "2019-11-14"

    def test_sadece_yil_ifadesi(self):
        exprs = find_temporal_expressions("Komisyon 2020 yılında ilk toplantısını yapar.")
        assert len(exprs) == 1
        assert exprs[0].kind == TemporalExpressionKind.DATE
        assert exprs[0].normalized_value == "2020-YIL"

    def test_sadece_yil_tam_tarihle_karismaz(self):
        # NEDEN: "2020-YIL" ile "2020-01-01" FARKLI normalized_value'lardır --
        # "2020 yılında" ifadesi, o yılın 1 Ocak'ıyla AYNI ANLAMA gelmez.
        yil = find_temporal_expressions("2020 yılında")[0]
        tam = find_temporal_expressions("1 Ocak 2020")[0]
        assert yil.normalized_value != tam.normalized_value

    def test_gecersiz_tarih_atlanir(self):
        assert find_temporal_expressions("Geçersiz: 32.13.2019 burada.") == []

    def test_madde_numarasi_tarih_sanilmaz(self):
        assert find_temporal_expressions("MADDE 14 uyarınca işlem yapılır.") == []


class TestSureIfadeleri:
    def test_gun_birimi(self):
        exprs = find_temporal_expressions("Başvurular 30 gün içinde değerlendirilir.")
        assert len(exprs) == 1
        assert exprs[0].kind == TemporalExpressionKind.DURATION
        assert exprs[0].text == "30 gün"
        assert exprs[0].normalized_value == "30 gün"

    def test_diger_birimler(self):
        for text, beklenen in [
            ("2 hafta içinde", "2 hafta"),
            ("6 ay içinde", "6 ay"),
            ("3 yıl süreyle", "3 yıl"),
        ]:
            exprs = find_temporal_expressions(text)
            assert len(exprs) == 1
            assert exprs[0].normalized_value == beklenen

    def test_yaziyla_yazilan_basit_sure(self):
        exprs = find_temporal_expressions("Başvurular otuz gün içinde değerlendirilir.")
        assert len(exprs) == 1
        assert exprs[0].text == "otuz gün"
        assert exprs[0].normalized_value == "30 gün"

    def test_yaziyla_bilesik_sure(self):
        exprs = find_temporal_expressions("Başvurular kırk beş gün içinde değerlendirilir.")
        assert exprs[0].normalized_value == "45 gün"

    def test_yaziyla_yuzler_ve_binler(self):
        assert find_temporal_expressions("Süre iki yüz kırk beş gün olarak belirlenmiştir.")[0].normalized_value == "245 gün"
        assert find_temporal_expressions("Toplam üç bin yüz on iki gün sürmüştür.")[0].normalized_value == "3112 gün"

    def test_yaziyla_ve_rakamla_ayni_sure_ayni_normalized_value_uretir(self):
        yaziyla = find_temporal_expressions("otuz gün")[0]
        rakamla = find_temporal_expressions("30 gün")[0]
        assert yaziyla.normalized_value == rakamla.normalized_value == "30 gün"

    def test_sayi_kelimesi_birim_olmadan_yakalanmaz(self):
        # NEDEN: "otuz kişi" bir süre DEĞİLDİR -- birim kelimesi (gün/hafta/
        # ay/yıl) yoksa sayı kelimesi TEK BAŞINA anlamsızdır, yakalanmamalı.
        assert find_temporal_expressions("Toplantıya otuz kişi katıldı.") == []

    def test_yil_suresi_yil_tarihiyle_karismaz(self):
        # "2 yıl" (süre) ile "2023 yılında" (tarih) FARKLI kalıplardır.
        sure = find_temporal_expressions("En az 2 yıl süreyle geçerlidir.")
        assert len(sure) == 1
        assert sure[0].kind == TemporalExpressionKind.DURATION


class TestKarisikMetin:
    def test_birden_fazla_ifade_sirayla_dondurulur(self):
        text = "Sözleşme 1 Ocak 2018 tarihinde imzalanır, fesih bildirimi 90 gün önce yapılır."
        exprs = find_temporal_expressions(text)
        assert [e.kind for e in exprs] == [
            TemporalExpressionKind.DATE,
            TemporalExpressionKind.DURATION,
        ]
        assert exprs[0].start < exprs[1].start

    def test_tarih_veya_sure_yoksa_bos_liste(self):
        assert find_temporal_expressions("Bu maddenin amacı düzenleme yapmaktır.") == []
