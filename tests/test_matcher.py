"""
section_matcher.py (Adım 3 -- Matcher L1) testleri.

Kritik özellik: yonetmelik_2019 -> yonetmelik_2023 gerçek örnek belge
çiftinde çıkarılan eşleşmeler, ground_truth.json'a karşı OBJEKTİF olarak
doğrulanır. ground_truth.json bilinçli olarak şu tuzakları içeriyor:
- aynı madde_no'nun İKİ FARKLI maddeye ait olması (2019 MADDE 8 "Arşivleme
  Esasları" kaldırılınca 2023 MADDE 8 "Birim Sorumlulukları" olur) --
  saf numara eşleştirmesi bunu YANLIŞ eşleştirir, L1 başlık çelişkisiyle
  bunu engellemeli.
- numarası kayan ama metni/başlığı aynı kalan maddeler (RENUMBERED) --
  L1 bunları başlık eşliğiyle yakalamalı.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.analysis.embedder import Embedder
from src.analysis.section_matcher import MatchResult, SectionMatch, match_sections
from src.config import SAMPLES_DIR, SECTION_MATCH_MIN_COSINE_SIMILARITY
from src.ingestion.docx_loader import DOCXLoader
from src.ingestion.pdf_loader import PDFLoader
from src.models import Section, TextUnit
from src.parsing.structure_parser import parse_structure

with open(SAMPLES_DIR / "ground_truth.json", encoding="utf-8") as f:
    _GROUND_TRUTH = json.load(f)


def _section(
    *,
    section_type: str = "MADDE",
    madde_no: int | None,
    baslik: str | None,
    order_index: int = 0,
    doc_id: str = "test",
) -> Section:
    heading_label = f"{'GEÇİCİ MADDE' if section_type == 'GECICI_MADDE' else 'MADDE'} {madde_no}"
    return Section(
        doc_id=doc_id,
        heading_path=(heading_label,),
        section_type=section_type,
        madde_no=madde_no,
        baslik=baslik,
        order_index=order_index,
        units=[],
    )


_LOADERS = [
    ("pdf", PDFLoader, "yonetmelik_2019.pdf", "yonetmelik_2023.pdf"),
    ("docx", DOCXLoader, "yonetmelik_2019.docx", "yonetmelik_2023.docx"),
]


def _gercek_sections(loader_cls, filename: str, doc_id: str) -> list[Section]:
    doc = loader_cls().load(SAMPLES_DIR / filename, doc_id=doc_id)
    return parse_structure(doc)


def _section_with_text(
    *,
    text: str,
    section_type: str = "MADDE",
    madde_no: int | None,
    baslik: str | None,
    order_index: int = 0,
    doc_id: str = "test",
) -> Section:
    """
    _section()'dan FARKI: L2 (embedding) testleri joined_text'i sahte
    embedder'ın anahtarı olarak kullanır -- boş units (joined_text == "")
    ile üretilen Section'lar birbirinden AYIRT EDİLEMEZ olurdu. Bu yüzden
    L2 testleri her Section'a BENZERSİZ bir gövde metni veren bu yardımcıyı
    kullanır.
    """
    heading_label = f"{'GEÇİCİ MADDE' if section_type == 'GECICI_MADDE' else 'MADDE'} {madde_no}"
    unit = TextUnit(
        doc_id=doc_id,
        page_no=1,
        block_index=0,
        char_start=0,
        char_end=len(text),
        heading_path=(heading_label,),
        text=text,
    )
    return Section(
        doc_id=doc_id,
        heading_path=(heading_label,),
        section_type=section_type,
        madde_no=madde_no,
        baslik=baslik,
        order_index=order_index,
        units=[unit],
    )


class _FakeEmbedder:
    """
    Gerçek sentence-transformers modeli yerine, elle tanımlı deterministik
    vektörler döndüren test çifti. NEDEN: L2'nin (Hungarian atama, eşik
    filtreleme, section_type ayrımı) doğruluğu, embedding modelinin
    KENDİSİNDEN bağımsız test edilebilmeli -- gerçek model testleri ağ
    erişimi + saniyeler ister, algoritma testleri BUNA muhtaç olmamalı.
    """

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = vectors

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.array([self._vectors[t] for t in texts], dtype=np.float32)


class TestGroundTruthKarsilastirmasi:
    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_eslesen_ciftler_ground_truth_ile_ayni(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        actual_pairs = {(m.old.madde_no, m.new.madde_no) for m in result.matches}
        expected_pairs = {
            (m["madde_no_2019"], m["madde_no_2023"])
            for m in _GROUND_TRUTH["maddeler"]
            if m["madde_no_2019"] is not None and m["madde_no_2023"] is not None
        }
        assert actual_pairs == expected_pairs

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_kaldirilan_madde_unmatched_old_da(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        expected_removed_no = {
            m["madde_no_2019"]
            for m in _GROUND_TRUTH["maddeler"]
            if m["madde_no_2019"] is not None and m["madde_no_2023"] is None
        }
        assert {s.madde_no for s in result.unmatched_old} == expected_removed_no

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_eklenen_madde_unmatched_new_de(self, fmt, loader_cls, dosya_2019, dosya_2023):
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        expected_added_no = {
            m["madde_no_2023"]
            for m in _GROUND_TRUTH["maddeler"]
            if m["madde_no_2023"] is not None and m["madde_no_2019"] is None
        }
        assert {s.madde_no for s in result.unmatched_new} == expected_added_no

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_renumbered_madde_title_only_ile_esleniyor(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN: "Yürürlük"/"Yürütme" gibi numarası kayan ama başlığı/metni
        # aynı kalan maddeler, NUMBER_AND_TITLE geçişinde YAKALANAMAZ (farklı
        # numara) -- TITLE_ONLY geçişiyle bulunmalı.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        renumbered_no_2019 = {
            m["madde_no_2019"]
            for m in _GROUND_TRUTH["maddeler"]
            if m["change_type"] == "RENUMBERED"
        }
        for match in result.matches:
            if match.old.madde_no in renumbered_no_2019:
                assert match.method == "TITLE_ONLY", (
                    f"MADDE {match.old.madde_no}: RENUMBERED madde TITLE_ONLY ile "
                    f"eşleşmeliydi, {match.method} ile eşleşti"
                )

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_ayni_numarali_farkli_madde_baslik_celismesiyle_engellenir(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN (kritik test): 2019 MADDE 8 "Arşivleme Esasları" kaldırılınca
        # 2023 MADDE 8 "Birim Sorumlulukları" olur -- saf numara eşleştirmesi
        # bu ikisini YANLIŞ eşleştirir. L1 bunu başlık çelişkisiyle
        # engellemeli ve gerçek karşılığı (2023 MADDE 9, aynı başlık) bulmalı.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023")

        result = match_sections(old_sections, new_sections)

        birim_match = next(m for m in result.matches if m.old.baslik == "Birim Sorumlulukları")
        assert birim_match.old.madde_no == 9
        assert birim_match.new.madde_no == 8
        assert birim_match.method == "TITLE_ONLY"

        arsivleme = next(s for s in result.unmatched_old if s.baslik == "Arşivleme Esasları")
        assert arsivleme.madde_no == 8


class TestSentetikKenarDurumlari:
    def test_ayni_numara_ayni_baslik_number_and_title_ile_esler(self):
        old = [_section(madde_no=1, baslik="Amaç", order_index=0)]
        new = [_section(madde_no=1, baslik="Amaç", order_index=0)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "NUMBER_AND_TITLE"
        assert not result.unmatched_old
        assert not result.unmatched_new

    def test_ayni_numara_farkli_baslik_eslesmez(self):
        old = [_section(madde_no=8, baslik="Arşivleme Esasları", order_index=0)]
        new = [_section(madde_no=8, baslik="Birim Sorumlulukları", order_index=0)]

        result = match_sections(old, new)

        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == new

    def test_farkli_numara_ayni_baslik_title_only_ile_esler(self):
        old = [_section(madde_no=12, baslik="Yürürlük", order_index=11)]
        new = [_section(madde_no=13, baslik="Yürürlük", order_index=12)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "TITLE_ONLY"
        assert result.matches[0].old.madde_no == 12
        assert result.matches[0].new.madde_no == 13

    def test_baslik_buyuk_kucuk_harf_ve_bosluk_farkina_duyarsiz(self):
        old = [_section(madde_no=1, baslik="  Amaç  ", order_index=0)]
        new = [_section(madde_no=2, baslik="AMAÇ", order_index=0)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "TITLE_ONLY"

    def test_baslik_yoksa_sadece_numaraya_gore_esler(self):
        old = [_section(madde_no=1, baslik=None, order_index=0)]
        new = [_section(madde_no=1, baslik=None, order_index=0)]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].method == "NUMBER_AND_TITLE"

    def test_iki_tarafta_da_tekrar_eden_baslik_belirsizse_eslesmez(self):
        # NEDEN: aynı başlık her iki tarafta da BİRDEN FAZLA kez geçiyorsa
        # hangi çiftin doğru olduğu belirsizdir -- L1 KESMEZ.
        old = [
            _section(madde_no=1, baslik="Genel Hükümler", order_index=0),
            _section(madde_no=2, baslik="Genel Hükümler", order_index=1),
        ]
        new = [
            _section(madde_no=3, baslik="Genel Hükümler", order_index=0),
            _section(madde_no=4, baslik="Genel Hükümler", order_index=1),
        ]

        result = match_sections(old, new)

        assert result.matches == []
        assert len(result.unmatched_old) == 2
        assert len(result.unmatched_new) == 2

    def test_gecici_madde_normal_madde_ile_ayni_numara_olsa_bile_karismaz(self):
        old = [
            _section(section_type="MADDE", madde_no=1, baslik="Amaç", order_index=0),
            _section(section_type="GECICI_MADDE", madde_no=1, baslik=None, order_index=1),
        ]
        new = [
            _section(section_type="GECICI_MADDE", madde_no=1, baslik=None, order_index=0),
        ]

        result = match_sections(old, new)

        assert len(result.matches) == 1
        assert result.matches[0].old.section_type == "GECICI_MADDE"
        assert result.unmatched_old == [old[0]]

    def test_bos_listeler_hersey_unmatched(self):
        old = [_section(madde_no=1, baslik="Amaç", order_index=0)]
        result = match_sections(old, [])
        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == []

    def test_sonuc_tipleri(self):
        result = match_sections([], [])
        assert isinstance(result, MatchResult)
        assert result.matches == []

    def test_matches_old_order_indexe_gore_sirali(self):
        old = [
            _section(madde_no=3, baslik="Üçüncü", order_index=2),
            _section(madde_no=1, baslik="Birinci", order_index=0),
            _section(madde_no=2, baslik="İkinci", order_index=1),
        ]
        new = [
            _section(madde_no=3, baslik="Üçüncü", order_index=2),
            _section(madde_no=1, baslik="Birinci", order_index=0),
            _section(madde_no=2, baslik="İkinci", order_index=1),
        ]

        result = match_sections(old, new)

        assert [m.old.order_index for m in result.matches] == [0, 1, 2]

    def test_section_match_dataclass_alanlari(self):
        old = _section(madde_no=1, baslik="Amaç", order_index=0)
        new = _section(madde_no=1, baslik="Amaç", order_index=0)
        m = SectionMatch(old=old, new=new, method="NUMBER_AND_TITLE")
        assert m.old is old
        assert m.new is new
        assert m.method == "NUMBER_AND_TITLE"


class TestL2EmbeddingHungarianAtama:
    """
    Sahte (deterministik) embedder ile Matcher L2'nin (embedding + Hungarian
    atama + eşik filtreleme) doğruluğunu, gerçek modelden BAĞIMSIZ test eder.
    """

    def test_embedder_none_ise_l1_ile_ayni_davranir(self):
        # NEDEN kritik: embedder verilmezse davranış Adım 3'teki L1 ile
        # BİREBİR aynı kalmalı (geriye dönük uyumluluk).
        old = [_section(madde_no=8, baslik="Arşivleme Esasları", order_index=0)]
        new = [_section(madde_no=8, baslik="Birim Sorumlulukları", order_index=0)]

        result = match_sections(old, new)

        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == new

    def test_hungarian_kuresel_optimumu_secer_satir_bazli_acgozlu_secimi_degil(self):
        # NEDEN (kritik test): A satırı en yüksek benzerliği X ile taşır
        # (0.70 > 0.62) -- satır-bazlı açgözlü bir seçim A'yı X'e kilitler.
        # Ama B, X'e ÇOK daha güçlü bağlıdır (0.95) ve Y'ye neredeyse hiç
        # benzemez (-0.42); KÜRESEL en iyi TOPLAM benzerlik A-Y + B-X'tir
        # (açgözlü A-X + B-Y toplamından KESİNLİKLE daha yüksek). Hungarian
        # bunu doğru bulmalı, açgözlü tuzağa düşmemeli.
        old = [
            _section_with_text(text="eski-A", madde_no=1, baslik="Eski Madde A", order_index=0),
            _section_with_text(text="eski-B", madde_no=2, baslik="Eski Madde B", order_index=1),
        ]
        new = [
            _section_with_text(text="yeni-X", madde_no=9, baslik="Yeni Madde X", order_index=0),
            _section_with_text(text="yeni-Y", madde_no=10, baslik="Yeni Madde Y", order_index=1),
        ]
        embedder = _FakeEmbedder(
            {
                "eski-A": [-0.42, 0.855],
                "eski-B": [0.707, 0.939],
                "yeni-X": [0.25, 0.718],
                "yeni-Y": [-0.969, 0.21],
            }
        )

        result = match_sections(old, new, embedder=embedder, min_similarity=0.5)

        assert not result.unmatched_old
        assert not result.unmatched_new
        by_old_baslik = {m.old.baslik: m.new.baslik for m in result.matches}
        assert by_old_baslik == {"Eski Madde A": "Yeni Madde Y", "Eski Madde B": "Yeni Madde X"}
        assert all(m.method == "EMBEDDING" for m in result.matches)

    def test_esik_altindaki_atama_reddedilir(self):
        # NEDEN: Hungarian tek adayı olsa bile ZORLA bir atama üretir;
        # benzerlik SECTION_MATCH_MIN_COSINE_SIMILARITY'nin altındaysa bu
        # "rastgele en yakın komşu"dur, "eşleşme" değil -- unmatched kalmalı.
        old = [_section_with_text(text="alakasiz-eski", madde_no=1, baslik="X", order_index=0)]
        new = [_section_with_text(text="alakasiz-yeni", madde_no=2, baslik="Y", order_index=0)]
        embedder = _FakeEmbedder(
            {"alakasiz-eski": [1.0, 0.0], "alakasiz-yeni": [0.0, 1.0]}  # sim = 0.0
        )

        result = match_sections(old, new, embedder=embedder, min_similarity=0.5)

        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == new

    def test_min_similarity_parametresi_esigi_degistirir(self):
        old = [_section_with_text(text="e1", madde_no=1, baslik="X", order_index=0)]
        new = [_section_with_text(text="e2", madde_no=2, baslik="Y", order_index=0)]
        # sim(e1, e2) = 0.6 (aynı yönde, farklı büyüklük değil -- dik olmayan basit vektörler)
        embedder = _FakeEmbedder({"e1": [1.0, 0.0], "e2": [0.6, 0.8]})

        dusuk_esik = match_sections(old, new, embedder=embedder, min_similarity=0.5)
        assert len(dusuk_esik.matches) == 1
        assert dusuk_esik.matches[0].method == "EMBEDDING"

        yuksek_esik = match_sections(old, new, embedder=embedder, min_similarity=0.9)
        assert yuksek_esik.matches == []
        assert yuksek_esik.unmatched_old == old
        assert yuksek_esik.unmatched_new == new

    def test_varsayilan_esik_configden_gelir(self):
        # NEDEN: min_similarity parametresi verilmezse src/config.py'deki
        # SECTION_MATCH_MIN_COSINE_SIMILARITY (0.50) kullanılmalı -- eşikler
        # tek yerden kalibre edilebilmeli (Mimari İlke, config.py NEDEN notu).
        old = [_section_with_text(text="e1", madde_no=1, baslik="X", order_index=0)]
        new = [_section_with_text(text="e2", madde_no=2, baslik="Y", order_index=0)]
        # sim tam eşiğin biraz altında -> reddedilmeli
        embedder = _FakeEmbedder(
            {"e1": [1.0, 0.0], "e2": [SECTION_MATCH_MIN_COSINE_SIMILARITY - 0.1, 0.9]}
        )

        result = match_sections(old, new, embedder=embedder)

        assert result.matches == []

    def test_gecici_madde_normal_madde_ile_embeddingde_de_karismaz(self):
        # NEDEN: L1'deki section_type ayrımı L2'de de KORUNMALI -- vektörler
        # birebir aynı olsa bile (sim=1.0) farklı numara uzaylarındaki
        # section_type'lar eşleşmemeli (bkz. config.py GECICI_MADDE_PATTERN).
        old = [
            _section_with_text(
                text="ayni-metin",
                section_type="MADDE",
                madde_no=1,
                baslik="X",
                order_index=0,
            )
        ]
        new = [
            _section_with_text(
                text="ayni-metin-2",
                section_type="GECICI_MADDE",
                madde_no=1,
                baslik=None,
                order_index=0,
            )
        ]
        embedder = _FakeEmbedder({"ayni-metin": [1.0, 0.0], "ayni-metin-2": [1.0, 0.0]})

        result = match_sections(old, new, embedder=embedder, min_similarity=0.5)

        assert result.matches == []
        assert result.unmatched_old == old
        assert result.unmatched_new == new

    def test_l1_zaten_eslestirdiyse_l2ye_hic_dusmez(self):
        # NEDEN: L2, SADECE L1'in eşleştiremediği artıklar üzerinde
        # çalışmalı -- L1'in bulduğu bir eşleşme L2 tarafından tekrar
        # işlenmemeli/değiştirilmemeli (embedder'a o metin hiç sorulmamalı).
        old = [_section(madde_no=1, baslik="Amaç", order_index=0)]
        new = [_section(madde_no=1, baslik="Amaç", order_index=0)]

        class PatlayanEmbedder:
            def embed(self, texts):
                raise AssertionError("L1 zaten eşleştirdi, embedder çağrılmamalıydı")

        result = match_sections(old, new, embedder=PatlayanEmbedder())

        assert len(result.matches) == 1
        assert result.matches[0].method == "NUMBER_AND_TITLE"

    def test_l1_ve_l2_matches_birlikte_order_indexe_gore_sirali(self):
        l1_old = _section(madde_no=1, baslik="Amaç", order_index=0)
        l1_new = _section(madde_no=1, baslik="Amaç", order_index=0)
        l2_old = _section_with_text(text="l2-eski", madde_no=5, baslik="X", order_index=1)
        l2_new = _section_with_text(text="l2-yeni", madde_no=6, baslik="Y", order_index=1)
        embedder = _FakeEmbedder({"l2-eski": [1.0, 0.0], "l2-yeni": [0.9, 0.1]})

        result = match_sections(
            [l1_old, l2_old], [l1_new, l2_new], embedder=embedder, min_similarity=0.5
        )

        assert len(result.matches) == 2
        assert [m.method for m in result.matches] == ["NUMBER_AND_TITLE", "EMBEDDING"]


class TestGercekEmbedderEntegrasyonu:
    """
    src/analysis/embedder.py'nin GERÇEK sentence-transformers modeliyle
    çalıştığını doğrular. NEDEN ayrı bir sınıfta: bu testler ağ erişimi
    (ilk çalıştırmada model indirimi) ve saniyeler mertebesinde süre
    gerektirir -- algoritma doğruluğu (TestL2EmbeddingHungarianAtama)
    bundan bağımsız ve hızlı kalmalı.
    """

    def test_ayni_metin_kosinus_benzerligi_bire_yakin(self):
        embedder = Embedder()
        vecs = embedder.embed(["Bu bir test cümlesidir.", "Bu bir test cümlesidir."])
        sim = float(np.dot(vecs[0], vecs[1]) / (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[1])))
        assert sim > 0.99

    def test_alakasiz_metin_kosinus_benzerligi_belirgin_dusuk(self):
        embedder = Embedder()
        vecs = embedder.embed(
            ["Veri sorumlusu kişisel verileri korumakla yükümlüdür.", "Kedi köpekten hızlı koşar."]
        )
        sim = float(np.dot(vecs[0], vecs[1]) / (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[1])))
        assert sim < SECTION_MATCH_MIN_COSINE_SIMILARITY

    def test_disk_onbellegi_ikinci_cagriyi_modeli_calistirmadan_yanitlar(self, monkeypatch):
        embedder = Embedder()
        text = "Önbellek testi için benzersiz bir cümle -- L2 Adım 4."
        embedder.embed([text])  # ilk çağrı: model çalışır, diske yazılır

        def _patlayan_load_model():
            raise AssertionError("Önbellek varken model TEKRAR yüklenmemeliydi")

        monkeypatch.setattr(embedder, "_load_model", _patlayan_load_model)
        vecs = embedder.embed([text])  # ikinci çağrı: sadece diskten okumalı
        assert vecs.shape == (1, 384)

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_gercek_ornek_belgede_l1_eslesmeleri_l2_sonrasi_da_korunur(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN TAM EŞİTLİK değil ALT KÜME (subset) kontrolü: L2
        # (_match_by_embedding) SADECE L1'in eşleştiremediği artıklar
        # üzerinde çalışır, L1'in bulduğu eşleşmelere hiç dokunmaz -- bu
        # yüzden L1'in bulduğu HER çift, L2 sonrasında da mutlaka bulunur.
        # Ama tersi ZORUNLU DEĞİL: L2, L1'in unmatched bıraktığı GERÇEK
        # ADDED/REMOVED maddeler arasında (bu belgede: "Arşivleme Esasları"
        # ile "Açık Veri Portalı") teorik olarak yanlış bir eşleşme
        # bulabilir -- bunun engellenmesi eşik KALİBRASYONUNUN işidir, bkz.
        # test_arsivleme_acik_veri_portaliyla_yanlislikla_eslesmiyor.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_l2")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_l2")

        l1_only = match_sections(old_sections, new_sections)
        l1_l2 = match_sections(old_sections, new_sections, embedder=Embedder())

        l1_pairs = {(m.old.madde_no, m.new.madde_no) for m in l1_only.matches}
        l1_l2_pairs = {(m.old.madde_no, m.new.madde_no) for m in l1_l2.matches}
        assert l1_pairs <= l1_l2_pairs

    @pytest.mark.parametrize("fmt,loader_cls,dosya_2019,dosya_2023", _LOADERS)
    def test_arsivleme_acik_veri_portaliyla_yanlislikla_eslesmiyor(
        self, fmt, loader_cls, dosya_2019, dosya_2023
    ):
        # NEDEN bu test VAR (gerçek kalibrasyon ölçümü, Adım 4): gerçek
        # embedding modeliyle 2019 MADDE 8 "Arşivleme Esasları" (REMOVED)
        # ile 2023 MADDE 11 "Açık Veri Portalı" (ADDED) arasındaki kosinüs
        # benzerliği ~0.56'dır -- ikisi TAMAMEN farklı konular olsa da kısa,
        # ortak mevzuat kelime dağarcığı (örn. "veri", "ilgili", "Kurum")
        # paylaşan iki fıkralı maddeler. config.py'deki
        # SECTION_MATCH_MIN_COSINE_SIMILARITY BU YANLIŞ POZİTİFİ ELEYECEK
        # kadar yüksek kalibre edilmiş olmalı (bkz. config.py NEDEN notu) --
        # bu test o eşiğin gelecekte YANLIŞLIKLA düşürülmesine karşı bir
        # regresyon bekçisidir.
        old_sections = _gercek_sections(loader_cls, dosya_2019, f"{fmt}_2019_l2b")
        new_sections = _gercek_sections(loader_cls, dosya_2023, f"{fmt}_2023_l2b")

        result = match_sections(old_sections, new_sections, embedder=Embedder())

        arsivleme_eslesti_mi = any(
            m.old.baslik == "Arşivleme Esasları" for m in result.matches
        )
        assert not arsivleme_eslesti_mi, "Arşivleme Esasları YANLIŞLIKLA bir 2023 maddesiyle eşleşti"
