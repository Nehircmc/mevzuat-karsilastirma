"""sentence_splitter.py testleri: TR kısaltma duyarlılığı + offset izlenebilirliği."""

from __future__ import annotations

from src.models import TextUnit
from src.parsing.sentence_splitter import split_sentences


def _unit(text: str) -> TextUnit:
    return TextUnit(
        doc_id="t", page_no=1, block_index=0, char_start=0, char_end=len(text),
        heading_path=("İKİNCİ BÖLÜM", "MADDE 6"), text=text,
    )


class TestTemelBolme:
    def test_iki_basit_cumle_ayrilir(self):
        sentences = split_sentences(_unit("Birinci cümle. İkinci cümle."))
        assert [s.text for s in sentences] == ["Birinci cümle.", "İkinci cümle."]

    def test_nokta_olmayan_tek_cumle(self):
        sentences = split_sentences(_unit("Nokta olmayan tek cümle"))
        assert [s.text for s in sentences] == ["Nokta olmayan tek cümle"]

    def test_soru_ve_unlem_de_cumle_sonu_sayilir(self):
        sentences = split_sentences(_unit("Bu doğru mu? Evet, doğrudur!"))
        assert [s.text for s in sentences] == ["Bu doğru mu?", "Evet, doğrudur!"]


class TestKisaltmalar:
    def test_tc_kisaltmasi_bolmez(self):
        metin = "Bu Yönetmelik, T.C. Anayasasının 123 üncü maddesine dayanır."
        sentences = split_sentences(_unit(metin))
        assert len(sentences) == 1
        assert sentences[0].text == metin

    def test_vb_kisaltmasi_bolmez(self):
        sentences = split_sentences(
            _unit("Kitap, defter vb. malzemeler temin edilir. Bu esastır.")
        )
        assert len(sentences) == 2
        assert sentences[0].text == "Kitap, defter vb. malzemeler temin edilir."
        assert sentences[1].text == "Bu esastır."

    def test_tek_harf_kisaltma_bolmez(self):
        sentences = split_sentences(
            _unit("A. Bölümü ilgilendiren madde budur. Devamı aşağıdadır.")
        )
        assert len(sentences) == 2
        assert sentences[0].text == "A. Bölümü ilgilendiren madde budur."


class TestFikraListesi:
    def test_yari_noktali_virgullu_liste_tek_cumle_kalir(self):
        text = (
            "(1) Bu Yönetmelikte geçen;\n"
            "a) Açık veri: Herhangi bir kısıtlama olmaksızın erişilebilen veriyi,\n"
            "b) Kurum: İlgili genel müdürlüğü,\n"
            "ifade eder."
        )
        sentences = split_sentences(_unit(text))
        assert len(sentences) == 1
        assert sentences[0].text == text

    def test_ardisik_fikralar_ayri_cumle_olur(self):
        text = (
            "(1) Kurum verileri, ilgili birimler dışındaki kişi ve kurumlarla "
            "paylaşılamaz.\n(2) Kişisel verilerin işlenmesinde ilgili mevzuat "
            "hükümlerine uyulur."
        )
        sentences = split_sentences(_unit(text))
        assert len(sentences) == 2
        assert sentences[0].text.startswith("(1) Kurum verileri")
        assert sentences[1].text.startswith("(2) Kişisel verilerin")


class TestProvenanceVeMiras:
    def test_her_cumlenin_offseti_orijinal_metne_geri_haritalanir(self):
        text = "Birinci cümle. İkinci cümle budur."
        unit = _unit(text)
        sentences = split_sentences(unit)

        assert len(sentences) == 2
        for sentence in sentences:
            assert text[sentence.char_start : sentence.char_end] == sentence.text

    def test_heading_path_ve_kimlik_ebeveynden_miras_alinir(self):
        unit = _unit("Tek cümle burada.")
        sentences = split_sentences(unit)

        assert len(sentences) == 1
        assert sentences[0].heading_path == unit.heading_path
        assert sentences[0].doc_id == unit.doc_id
        assert sentences[0].page_no == unit.page_no
        assert sentences[0].block_index == unit.block_index
