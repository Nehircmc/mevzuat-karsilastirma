"""normalizer.py testleri: dönüşüm doğruluğu + offset izlenebilirliği."""

from __future__ import annotations

from src.parsing.normalizer import normalize


class TestTireleTamiri:
    def test_satir_sonu_tiresi_kaldirilir(self):
        sonuc = normalize("gerçekleş-\ntirme işlemi")
        assert sonuc.normalized == "gerçekleştirme işlemi"

    def test_parantez_sonrasi_tire_korunur(self):
        # NEDEN: bu tire kelime bölme değil, gerçek bir ayraç -- silinmemeli.
        sonuc = normalize("(1) Madde-2 hükmü")
        assert "Madde-2" in sonuc.normalized


class TestBosluklarVeNoktalama:
    def test_coklu_bosluk_tek_bosluga_indirgenir(self):
        sonuc = normalize("Kurum   verileri\tgüvenlidir")
        assert sonuc.normalized == "Kurum verileri güvenlidir"

    def test_turkce_tirnak_ve_tire_normalize_edilir(self):
        sonuc = normalize("“Açık veri” – kavramı")
        assert sonuc.normalized == '"Açık veri" - kavramı'


class TestOffsetIzlenebilirligi:
    def test_tireleme_sonrasi_span_dogru_haritalanir(self):
        orijinal = "gerçekleş-\ntirme işlemi"
        sonuc = normalize(orijinal)
        assert sonuc.normalized == "gerçekleştirme işlemi"

        # normalized'de "tirme" kelimesinin konumu:
        norm_start = sonuc.normalized.index("tirme")
        norm_end = norm_start + len("tirme")

        orig_start, orig_end = sonuc.map_span(norm_start, norm_end)
        assert orijinal[orig_start:orig_end] == "tirme"

    def test_bosluk_sikistirma_sonrasi_span_dogru_haritalanir(self):
        orijinal = "Kurum   verileri"
        sonuc = normalize(orijinal)
        norm_start = sonuc.normalized.index("verileri")
        norm_end = norm_start + len("verileri")

        orig_start, orig_end = sonuc.map_span(norm_start, norm_end)
        assert orijinal[orig_start:orig_end] == "verileri"

    def test_degismeyen_bolge_birebir_haritalanir(self):
        # Hiçbir normalizasyon tetiklenmeyen düz bir metinde, her span
        # kendi orijinal indeksine eşit olmalı.
        orijinal = "sade metin"
        sonuc = normalize(orijinal)
        assert sonuc.normalized == orijinal
        assert sonuc.map_span(0, 4) == (0, 4)

    def test_bos_span_en_yakin_konuma_haritalanir(self):
        sonuc = normalize("abc")
        assert sonuc.map_span(1, 1) == (1, 1)
