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


class TestRakamliTarihNoktasi:
    """
    Tarihsel/sayısal değişiklik tespiti özelliği için eklendi (görev
    geçmişi): "14.11.2019" gibi BOŞLUKSUZ rakam.rakam örüntüleri cümle
    sonu SAYILMAMALI -- aksi halde find_temporal_expressions'ın gördüğü
    her cümle parçası tarihi PARÇALANMIŞ hâlde alır ve hiçbir tarih
    ifadesi TANINAMAZ.
    """

    def test_nokta_ayracli_tam_tarih_bolunmez(self):
        metin = "Yönetmelik 14.11.2019 tarihinde yürürlüğe girer."
        sentences = split_sentences(_unit(metin))
        assert len(sentences) == 1
        assert sentences[0].text == metin

    def test_iki_ayri_tarih_iceren_metin_doğru_bolunur(self):
        metin = "Sözleşme 1.1.2018 tarihinde başlar. Bitiş 31.12.2020 olarak belirlenmiştir."
        sentences = split_sentences(_unit(metin))
        assert len(sentences) == 2
        assert sentences[0].text == "Sözleşme 1.1.2018 tarihinde başlar."
        assert sentences[1].text == "Bitiş 31.12.2020 olarak belirlenmiştir."

    def test_binlik_ayrac_da_bolunmez(self):
        # NEDEN aynı kural: "5.000" da rakam.rakam örüntüsü -- yan etki
        # olarak TR binlik ayracını da korur, bu YANLIŞ bir davranış değil.
        metin = "Toplam tutar 5.000 TL olarak belirlenmiştir. Ödeme yapılır."
        sentences = split_sentences(_unit(metin))
        assert len(sentences) == 2
        assert sentences[0].text == "Toplam tutar 5.000 TL olarak belirlenmiştir."

    def test_madde_numarasindan_sonraki_gercek_cumle_sonu_hala_bolunur(self):
        # NEDEN kritik: madde numarası ("Madde 5.") TEK taraflı bir
        # rakam-nokta durumudur -- noktadan SONRA rakam DEĞİL boşluk+büyük
        # harf gelir, bu yüzden YİNE cümle sonu sayılmalı (bkz.
        # _rakamli_tarih_noktasi_mi NEDEN notu).
        metin = "Madde 5. Başvurular değerlendirilir."
        sentences = split_sentences(_unit(metin))
        assert len(sentences) == 2
        assert sentences[0].text == "Madde 5."
        assert sentences[1].text == "Başvurular değerlendirilir."


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
