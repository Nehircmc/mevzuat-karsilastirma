"""
Kurgusal "KURUMSAL VERİ YÖNETİMİ VE AÇIK VERİ YÖNETMELİĞİ" (2019 ve 2023
sürümleri) için TEK KAYNAK veri tanımı.

NEDEN tek kaynak: generate_samples.py hem PDF/DOCX belgelerini hem de
ground_truth.json'u BU modülden türetir. Eğer belgeler ve ground truth ayrı
ayrı elle yazılsaydı, aralarında sessizce tutarsızlık oluşabilir ve
Adım 3-5'teki eşleştirici/differ, gerçek hatalarını değil bu tutarsızlığı
ölçmüş olurdu. Tek kaynak sayesinde karşılaştırma sonucu OBJEKTİF olarak
(ground truth'a karşı) skorlanabilir.

Her ArticleSpec bilinçli olarak TEK bir değişim tipini test etmek için
tasarlandı; hangi maddenin hangi zorluğu temsil ettiği `aciklama` alanında
açıklanır.
"""

from __future__ import annotations

from dataclasses import dataclass

REGULATION_TITLE = "KURUMSAL VERİ YÖNETİMİ VE AÇIK VERİ YÖNETMELİĞİ"

# NEDEN gerçek olmayan bir kurum adı: Belgenin tamamen kurgusal olduğunu
# (herhangi bir gerçek kurumla ilgisi olmadığını) açık tutmak için.
KURUM_ADI = "Ulusal Veri ve İstatistik Genel Müdürlüğü"


@dataclass(frozen=True)
class ArticleSpec:
    """
    Tek bir maddenin iki sürüm arasındaki durumunu tanımlar.

    NEDEN change_type src.models.ChangeType (runtime enum'u) DEĞİL, düz
    bir str: bu alan, test verisinin HANGİ senaryoyu (IDENTICAL/MODIFIED/
    ADDED/REMOVED/RENUMBERED/MOVED) temsil ettiğini betimleyen bir
    YAZAR/DOKÜMANTASYON etiketidir -- runtime'daki ChangeType ise SADECE
    İÇERİK durumunu temsil eder (Adım 9'dan sonra RENUMBERED/MOVED artık
    onun üyesi DEĞİL, bkz. src/models.py NEDEN notu). İkisini AYNI tipte
    tutmak, ground_truth.json'un betimleyici zenginliğini runtime tipinin
    kapsamına HAPSEDERDİ.
    """

    id: str
    change_type: str
    baslik: str
    madde_no_2019: int | None  # None => 2019'da yok (ADDED)
    madde_no_2023: int | None  # None => 2023'te yok (REMOVED)
    text_2019: str | None
    text_2023: str | None
    aciklama: str  # bu maddenin test ettiği zorluk (yorum amaçlı, dokümana yazılmaz)


@dataclass(frozen=True)
class BolumSpec:
    """Bir BÖLÜM'ün sıra sayısı, başlığı ve içerdiği madde id'leri (sırayla)."""

    sira_sayisi: str  # "BİRİNCİ", "İKİNCİ", ...
    baslik: str
    article_ids: list[str]


ARTICLES: list[ArticleSpec] = [
    ArticleSpec(
        id="amac",
        change_type="IDENTICAL",
        baslik="Amaç",
        madde_no_2019=1,
        madde_no_2023=1,
        text_2019=(
            "(1) Bu Yönetmeliğin amacı, kurum bünyesinde üretilen ve işlenen "
            "verilerin güvenli, tutarlı ve birlikte çalışabilir biçimde "
            "yönetilmesine; kamuya açık verilerin şeffaflık ve hesap "
            "verebilirlik ilkeleri çerçevesinde paylaşılmasına ilişkin usul "
            "ve esasları düzenlemektir."
        ),
        text_2023=None,  # generate_samples.py text_2019 ile aynı kabul eder
        aciklama="IDENTICAL: basit, kısaltma/sayı içermeyen değişmeyen madde.",
    ),
    ArticleSpec(
        id="kapsam",
        change_type="IDENTICAL",
        baslik="Kapsam",
        madde_no_2019=2,
        madde_no_2023=2,
        text_2019=(
            "(1) Bu Yönetmelik, Kurumun merkez ve taşra teşkilatında "
            "üretilen, işlenen veya saklanan tüm kurumsal verileri ve bu "
            "verilerin açık veri olarak yayımlanmasına ilişkin süreçleri "
            "kapsar."
        ),
        text_2023=None,
        aciklama="IDENTICAL: basit değişmeyen madde.",
    ),
    ArticleSpec(
        id="dayanak",
        change_type="IDENTICAL",
        baslik="Dayanak",
        madde_no_2019=3,
        madde_no_2023=3,
        text_2019=(
            "(1) Bu Yönetmelik, T.C. Anayasasının 123 üncü maddesi, 5018 "
            "sayılı Kamu Mali Yönetimi ve Kontrol Kanununun 9 uncu maddesi "
            "ile 1 sayılı Cumhurbaşkanlığı Teşkilatı Hakkında "
            "Cumhurbaşkanlığı Kararnamesinin 19 uncu maddesine "
            "dayanılarak hazırlanmıştır."
        ),
        text_2023=None,
        aciklama=(
            "IDENTICAL: içinde 'T.C.' kısaltması ve '5018 sayılı' gibi "
            "sayılar geçiyor -- normalizer/sentence_splitter'ın bunları "
            "yanlışlıkla cümle sonu sanmaması test edilir."
        ),
    ),
    ArticleSpec(
        id="tanimlar",
        change_type="MODIFIED",
        baslik="Tanımlar",
        madde_no_2019=4,
        madde_no_2023=4,
        text_2019=(
            "(1) Bu Yönetmelikte geçen;\n"
            "a) Açık veri: Herhangi bir kısıtlama olmaksızın herkesin "
            "erişimine, kullanımına ve paylaşımına açık olan veriyi,\n"
            f"b) Kurum: {KURUM_ADI}nü,\n"
            "c) Kurumsal veri: Kurumun görevleri kapsamında ürettiği veya "
            "edindiği her türlü veriyi,\n"
            "ifade eder."
        ),
        text_2023=(
            "(1) Bu Yönetmelikte geçen;\n"
            "a) Açık veri: Herhangi bir kısıtlama olmaksızın herkesin "
            "erişimine, kullanımına ve paylaşımına açık olan veriyi,\n"
            f"b) Kurum: {KURUM_ADI}nü,\n"
            "c) Kurumsal veri: Kurumun görevleri kapsamında ürettiği veya "
            "edindiği her türlü veriyi,\n"
            "ç) Veri Yönetişim Kurulu: Bu Yönetmelik kapsamındaki veri "
            "yönetimi politikalarını belirlemekle görevli kurulu,\n"
            "ifade eder."
        ),
        aciklama="MODIFIED (ek filler): yeni bir tanım bendi (ç) eklenmiş.",
    ),
    ArticleSpec(
        id="veri_sorumlulugu",
        change_type="IDENTICAL",
        baslik="Veri Sorumluluğu",
        madde_no_2019=5,
        madde_no_2023=5,
        text_2019=(
            "(1) Kurum, sorumluluğundaki verilerin doğruluğundan, "
            "güncelliğinden ve güvenliğinden sorumludur.\n"
            "(2) Veri sorumluluğu, ilgili birim amirleri tarafından "
            "yürütülür."
        ),
        text_2023=None,
        aciklama="IDENTICAL: numarası değişmeyen, metni aynı kalan filler madde.",
    ),
    ArticleSpec(
        id="veri_paylasimi",
        change_type="MODIFIED",
        baslik="Veri Paylaşımı",
        madde_no_2019=6,
        madde_no_2023=6,
        text_2019=(
            "(1) Kurum verileri, ilgili birimler dışındaki kişi ve "
            "kurumlarla paylaşılamaz.\n"
            "(2) Kişisel verilerin işlenmesinde ilgili mevzuat "
            "hükümlerine uyulur."
        ),
        text_2023=(
            "(1) Kurum verileri, Veri Yönetişim Kurulunun onayı alınması "
            "kaydıyla, ilgili birimler dışındaki kişi ve kurumlarla "
            "paylaşılabilir.\n"
            "(2) Kişisel verilerin işlenmesinde ilgili mevzuat "
            "hükümlerine uyulur."
        ),
        aciklama=(
            "MODIFIED (kritik test): fıkra (1) hem cümle içi ekleme "
            "('Veri Yönetişim Kurulunun onayı alınması kaydıyla,') HEM DE "
            "anlamın tersine dönmesi ('paylaşılamaz' -> 'paylaşılabilir') "
            "içeriyor; fıkra (2) ise birebir aynı kalıyor -- differ'ın "
            "TÜM maddeyi değil sadece fıkra (1)'i değişmiş sayması gerekir."
        ),
    ),
    ArticleSpec(
        id="veri_kalitesi",
        change_type="MODIFIED",
        baslik="Veri Kalitesi ve Güvenliği",
        madde_no_2019=7,
        madde_no_2023=7,
        text_2019=(
            "(1) Kurumsal veriler, doğruluk, tutarlılık, güncellik ve "
            "eksiksizlik ilkelerine uygun olarak yönetilir.\n"
            "(2) Veri kalitesinin sağlanmasından ilgili birim sorumludur.\n"
            "(3) Verilerin güvenliği, ilgili mevzuatta belirtilen bilgi "
            "güvenliği standartlarına uygun olarak sağlanır."
        ),
        text_2023=(
            "(1) Kurumsal veriler, doğruluk, tutarlılık, güncellik ve "
            "eksiksizlik ilkelerine uygun olarak yönetilir.\n"
            "(2) Veri kalitesinin sağlanmasından ilgili birim sorumludur.\n"
            "(3) Verilerin güvenliği, ilgili mevzuatta belirtilen bilgi "
            "güvenliği standartlarına uygun olarak sağlanır.\n"
            "(4) Veri kalitesi ölçütleri, Veri Yönetişim Kurulu tarafından "
            "yılda en az bir kez gözden geçirilir."
        ),
        aciklama=(
            "MODIFIED (kritik test): UZUN madde, fıkra (1)-(3) birebir "
            "aynı, sadece fıkra (4) eklenmiş -- differ tüm maddeyi "
            "değişmiş saymamalı, sadece eklenen fıkrayı işaretlemeli."
        ),
    ),
    ArticleSpec(
        id="arsivleme",
        change_type="REMOVED",
        baslik="Arşivleme Esasları",
        madde_no_2019=8,
        madde_no_2023=None,
        text_2019=(
            "(1) Kurumsal veriler, ilgili mevzuatta öngörülen sürelerle "
            "sınırlı olmak kaydıyla arşivlenir.\n"
            "(2) Arşivleme süresi dolan veriler, ilgili mevzuat "
            "hükümlerine göre imha edilir."
        ),
        text_2023=None,
        aciklama="REMOVED: 2023'te karşılığı yok; sonraki maddelerin numara kaymasına sebep olur.",
    ),
    ArticleSpec(
        id="birim_sorumluluklari",
        change_type="MODIFIED",
        baslik="Birim Sorumlulukları",
        madde_no_2019=9,
        madde_no_2023=8,  # Arşivleme (8) kaldırıldığı için 9 -> 8 kaydı
        text_2019=(
            "(1) İlgili birimler, sorumluluklarındaki verilerin "
            "toplanması, güncellenmesi ve doğruluğunun sağlanmasından "
            "sorumludur.\n"
            "(2) Birimler, veri güvenliği ihlallerini derhal ilgili "
            "birime bildirmekle yükümlüdür."
        ),
        text_2023=(
            "(1) İlgili birimler, sorumluluklarındaki verilerin "
            "toplanması, güncellenmesi, doğruluğunun sağlanmasından ve "
            "Veri Yönetişim Kurulu tarafından belirlenen standartlara "
            "uygunluğundan sorumludur.\n"
            "(2) Birimler, veri güvenliği ihlallerini derhal Veri "
            "Yönetişim Kuruluna bildirmekle yükümlüdür."
        ),
        aciklama=(
            "MODIFIED + numara kayması (en sık karıştırılan durum): hem "
            "numarası (9->8) DEĞİŞMİŞ hem metni değişmiş -- eşleştirici "
            "bunu sadece numaraya bakarak DEĞİL, içerik benzerliğiyle "
            "bulmalı; RENUMBERED değil MODIFIED olarak sınıflandırılmalı "
            "çünkü metin de değişti."
        ),
    ),
    ArticleSpec(
        id="ust_yonetim_sorumlulugu",
        change_type="RENUMBERED",
        baslik="Üst Yönetim Sorumluluğu",
        madde_no_2019=10,
        madde_no_2023=9,  # Arşivleme kaldırıldığı için 10 -> 9 kaydı
        text_2019=(
            "(1) Üst yönetim, bu Yönetmelik kapsamındaki veri yönetimi "
            "politikalarının uygulanmasını gözetir."
        ),
        text_2023=None,
        aciklama=(
            "RENUMBERED (ek örnek): metin birebir aynı, sadece numara "
            "kaymış -- Yürürlük/Yürütme dışında, 'kısa olmayan' bir "
            "maddede de bu deseni test eder."
        ),
    ),
    ArticleSpec(
        id="veri_yonetisim_kurulu",
        change_type="ADDED",
        baslik="Veri Yönetişim Kurulu",
        madde_no_2019=None,
        madde_no_2023=10,
        text_2019=None,
        text_2023=(
            "(1) Kurum bünyesinde, veri yönetimi politikalarını "
            "belirlemek ve uygulamayı izlemek üzere Veri Yönetişim "
            "Kurulu oluşturulur.\n"
            "(2) Kurulun teşkili, görev ve çalışma usul ve esasları "
            "Kurum tarafından çıkarılan yönerge ile belirlenir."
        ),
        aciklama="ADDED: 2019'da hiç karşılığı yok, tamamen yeni madde.",
    ),
    ArticleSpec(
        id="acik_veri_portali",
        change_type="ADDED",
        baslik="Açık Veri Portalı",
        madde_no_2019=None,
        madde_no_2023=11,
        text_2019=None,
        text_2023=(
            "(1) Kurum, açık veri niteliğindeki verilerini, kamuya açık "
            "ve makine tarafından okunabilir formatlarda, Açık Veri "
            "Portalı üzerinden yayımlar.\n"
            "(2) Açık Veri Portalında yayımlanan verilerin güncellenme "
            "sıklığı, ilgili birimler tarafından belirlenir."
        ),
        aciklama="ADDED: ikinci yeni madde.",
    ),
    ArticleSpec(
        id="yururlukten_kaldirilan",
        change_type="RENUMBERED",
        baslik="Yürürlükten Kaldırılan Mevzuat",
        madde_no_2019=11,
        madde_no_2023=12,
        text_2019=(
            "(1) 3/2/2011 tarihli ve 27835 sayılı Resmî Gazetede "
            "yayımlanan Kurumsal Veri Yönetimi Yönergesi yürürlükten "
            "kaldırılmıştır."
        ),
        text_2023=None,
        aciklama="RENUMBERED: metin aynı, numara 11->12 kaymış (madde eklenmesi nedeniyle).",
    ),
    ArticleSpec(
        id="yururluk",
        change_type="RENUMBERED",
        baslik="Yürürlük",
        madde_no_2019=12,
        madde_no_2023=13,
        text_2019="(1) Bu Yönetmelik yayımı tarihinde yürürlüğe girer.",
        text_2023=None,
        aciklama=(
            "RENUMBERED (zorunlu örnek): KISA madde, metin birebir aynı, "
            "sadece numara kaymış -- MODIFIED sanılması en sık yapılan "
            "hatadır."
        ),
    ),
    ArticleSpec(
        id="yurutme",
        change_type="RENUMBERED",
        baslik="Yürütme",
        madde_no_2019=13,
        madde_no_2023=14,
        text_2019=f"(1) Bu Yönetmelik hükümlerini {KURUM_ADI} yürütür.",
        text_2023=None,
        aciklama=(
            "RENUMBERED (zorunlu örnek): KISA madde, metin birebir aynı, "
            "sadece numara kaymış."
        ),
    ),
]

_ARTICLES_BY_ID: dict[str, ArticleSpec] = {a.id: a for a in ARTICLES}


def get_article(article_id: str) -> ArticleSpec:
    return _ARTICLES_BY_ID[article_id]


def resolved_text(article: ArticleSpec, year: int) -> str | None:
    """
    Bir maddenin verilen yıldaki METNİNİ döndürür.

    NEDEN gerekli: Değişmeyen (IDENTICAL/RENUMBERED) maddelerde text_2023
    tekrar yazılmamış (DRY) -- None ise text_2019 ile aynı kabul edilir.
    Bu, "aynı metni iki yerde elle yazınca birinde yazım hatası olursa
    testler yanlışlıkla MODIFIED görür" riskini ortadan kaldırır.
    """
    if year == 2019:
        return article.text_2019
    if year == 2023:
        return article.text_2023 if article.text_2023 is not None else article.text_2019
    raise ValueError(f"Desteklenmeyen yıl: {year}")


BOLUMLER_2019: list[BolumSpec] = [
    BolumSpec(
        sira_sayisi="BİRİNCİ",
        baslik="Amaç, Kapsam, Dayanak ve Tanımlar",
        article_ids=["amac", "kapsam", "dayanak", "tanimlar"],
    ),
    BolumSpec(
        sira_sayisi="İKİNCİ",
        baslik="Genel Esaslar",
        article_ids=["veri_sorumlulugu", "veri_paylasimi", "veri_kalitesi", "arsivleme"],
    ),
    BolumSpec(
        sira_sayisi="ÜÇÜNCÜ",
        baslik="Görev ve Sorumluluklar",
        article_ids=["birim_sorumluluklari", "ust_yonetim_sorumlulugu"],
    ),
    BolumSpec(
        sira_sayisi="DÖRDÜNCÜ",
        baslik="Çeşitli ve Son Hükümler",
        article_ids=["yururlukten_kaldirilan", "yururluk", "yurutme"],
    ),
]

BOLUMLER_2023: list[BolumSpec] = [
    BolumSpec(
        sira_sayisi="BİRİNCİ",
        baslik="Amaç, Kapsam, Dayanak ve Tanımlar",
        article_ids=["amac", "kapsam", "dayanak", "tanimlar"],
    ),
    BolumSpec(
        sira_sayisi="İKİNCİ",
        baslik="Genel Esaslar",
        # NEDEN "arsivleme" burada yok: 2023'te kaldırılmış madde.
        article_ids=["veri_sorumlulugu", "veri_paylasimi", "veri_kalitesi"],
    ),
    BolumSpec(
        sira_sayisi="ÜÇÜNCÜ",
        baslik="Görev ve Sorumluluklar",
        article_ids=[
            "birim_sorumluluklari",
            "ust_yonetim_sorumlulugu",
            "veri_yonetisim_kurulu",
            "acik_veri_portali",
        ],
    ),
    BolumSpec(
        sira_sayisi="DÖRDÜNCÜ",
        baslik="Çeşitli ve Son Hükümler",
        article_ids=["yururlukten_kaldirilan", "yururluk", "yurutme"],
    ),
]


def get_bolumler(year: int) -> list[BolumSpec]:
    if year == 2019:
        return BOLUMLER_2019
    if year == 2023:
        return BOLUMLER_2023
    raise ValueError(f"Desteklenmeyen yıl: {year}")


def get_madde_no(article: ArticleSpec, year: int) -> int | None:
    return article.madde_no_2019 if year == 2019 else article.madde_no_2023
