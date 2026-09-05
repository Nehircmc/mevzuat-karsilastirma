"""
Merkezi yapılandırma. Tüm sihirli sayılar, regex'ler ve renkler burada durur;
NEDEN: eşikleri tek yerden kalibre edebilmek (Adım 4'te L2 eşleşme eşiği,
Adım 5'te ChangeType sınırları değişecek) ve testlerde gerçek değerlere karşı
değil bu sabitlere karşı doğrulama yapabilmek için.
"""

from __future__ import annotations

import re
from pathlib import Path

# --------------------------------------------------------------------------
# YOLLAR
# --------------------------------------------------------------------------
# NEDEN: Path'leri buradan türetiyoruz ki src/ herhangi bir çalışma dizininden
# (pytest, streamlit run, script) tutarlı davransın.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = DATA_DIR / "samples"
CACHE_DIR = DATA_DIR / "cache"
ASSETS_DIR = BASE_DIR / "assets"

# --------------------------------------------------------------------------
# DESTEKLENEN GİRDİ FORMATLARI
# --------------------------------------------------------------------------
# NEDEN: OCR/taranmış PDF bilinçli olarak kapsam dışı (Onaylanmış Karar #1);
# bu küme dışına çıkan uzantılar factory.py'de açıkça reddedilir.
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

# --------------------------------------------------------------------------
# METİN KATMANI DOĞRULAMA EŞİKLERİ (taranmış/OCR'siz PDF tespiti)
# --------------------------------------------------------------------------
# NEDEN: "Sessizce boş dönme" ilkesi (Onaylanmış Karar #1) somut bir eşiğe
# ihtiyaç duyar; bir sayfa gerçekten boşsa bile TÜM belge boşsa bu bir metin
# katmanı sorunudur, tek bir boş sayfa değildir. Bu yüzden ORAN bazlı bakıyoruz.
MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER = 5
MIN_PAGE_RATIO_WITH_TEXT_LAYER = 0.5  # sayfaların en az yarısı metin içermeli

# NEDEN DOCX için ayrı bir eşik: DOCX'te "sayfa" kavramı yok, bu yüzden
# oran değil TOPLAM karakter sayısı üzerinden karar veriyoruz.
MIN_TOTAL_CHARS_FOR_DOCX_TEXT_LAYER = 20

# --------------------------------------------------------------------------
# ÜSTBİLGİ / ALTBİLGİ TESPİTİ (PDF)
# --------------------------------------------------------------------------
# NEDEN: Üstbilgi/altbilgi konumu (sayfanın üst/alt bandı) TEK BAŞINA yeterli
# değil -- gövde metni de sayfa kenarına yakın başlayabilir. Bu yüzden hem
# KONUM BANDI hem de SAYFALAR ARASI TEKRAR ORANI birlikte aranıyor: bir blok
# ancak ilgili bantta VE çoğu sayfada (normalize edilmiş olarak) tekrar
# ediyorsa üstbilgi/altbilgi sayılır.
HEADER_BAND_RATIO = 0.08  # sayfa yüksekliğinin üstten %8'i
FOOTER_BAND_RATIO = 0.08  # sayfa yüksekliğinin alttan %8'i
HEADER_FOOTER_MIN_REPETITION_RATIO = 0.6  # normalize metnin sayfaların en az %60'ında tekrarı

# "Sayfa N", "Sayfa N / M", "N/M" gibi altbilgi sayfa numarası kalıpları.
# NEDEN: Bunlar HEADER_FOOTER_MIN_REPETITION_RATIO testinden kaçabilir çünkü
# metin her sayfada FARKLIDIR (sayı değişir); bu yüzden ayrı bir regex ile
# yakalanıp normalize edildikten (sayı -> "N") sonra tekrar sayılır.
PAGE_NUMBER_FOOTER_PATTERN = re.compile(
    r"^\s*Sayfa\s+\d+(\s*/\s*\d+)?\s*$", re.IGNORECASE
)

# --------------------------------------------------------------------------
# TÜRKÇE MEVZUAT YAPISI REGEX'LERİ
# --------------------------------------------------------------------------
# NEDEN: L1 (yapısal) eşleme madde/bölüm numarasına dayanır (Mimari İlke B).
# Regex'ler ayrı sabitler olarak tutulur ki structure_parser.py test edilirken
# "hangi desenin eşleşmediği" satır satır izlenebilsin.

# "MADDE 5", "Madde 5 -", "MADDE 5." gibi normal madde başlıkları.
MADDE_PATTERN = re.compile(
    r"^\s*MADDE\s+(\d+)\s*[-–—.]?\s*(.*)$", re.IGNORECASE
)

# "GEÇİCİ MADDE 1" -- yürürlükten kaldırılan/geçiş hükümleri farklı numara
# uzayında yaşar, normal MADDE numaralarıyla karıştırılmamalı.
GECICI_MADDE_PATTERN = re.compile(
    r"^\s*GEÇİCİ\s+MADDE\s+(\d+)\s*[-–—.]?\s*(.*)$", re.IGNORECASE
)

# Türkçe sıra sayıları -- BÖLÜM/KISIM başlıklarında kullanılıyor.
# NEDEN: Liste halinde tutmak, regex'i okunur kılıyor ve yeni bir sıra sayısı
# gerektiğinde (örn. "ON BİRİNCİ") tek satırda genişletilebiliyor.
ORDINAL_WORDS_TR = [
    "BİRİNCİ", "İKİNCİ", "ÜÇÜNCÜ", "DÖRDÜNCÜ", "BEŞİNCİ",
    "ALTINCI", "YEDİNCİ", "SEKİZİNCİ", "DOKUZUNCU", "ONUNCU",
    "ON BİRİNCİ", "ON İKİNCİ", "ON ÜÇÜNCÜ", "ON DÖRDÜNCÜ", "ON BEŞİNCİ",
]
_ORDINAL_ALTERNATION = "|".join(ORDINAL_WORDS_TR)

# "BİRİNCİ BÖLÜM", "İKİNCİ BÖLÜM" ...
BOLUM_PATTERN = re.compile(
    rf"^\s*({_ORDINAL_ALTERNATION})\s+BÖLÜM\b\s*[-–—:]?\s*(.*)$", re.IGNORECASE
)

# "BİRİNCİ KISIM", "İKİNCİ KISIM" ... (BÖLÜM'den daha üst seviye hiyerarşi)
KISIM_PATTERN = re.compile(
    rf"^\s*({_ORDINAL_ALTERNATION})\s+KISIM\b\s*[-–—:]?\s*(.*)$", re.IGNORECASE
)

# "EK-1", "EK 1" gibi ekler.
EK_PATTERN = re.compile(r"^\s*EK[- ]?(\d+)\b\s*(.*)$", re.IGNORECASE)

# NEDEN: "Yürürlük" ve "Yürütme" maddeleri neredeyse her yönetmelikte son iki
# madde olur ve numaraları yeni madde eklendiğinde KAYAR ama METİN DEĞİŞMEZ.
# Bu, "numarası değişti" yapısal bayrağının (bkz. classifier.py::is_renumbered)
# en sık karşılaşılan gerçek örneğidir -- classifier.py bu başlıkları özel
# olarak biliyor OLMAMALI (kapalı sözlük ilkesi ihlali olur); bunun yerine
# metin+numara benzerliğiyle genel kural çalışır. Bu sabit sadece test
# verisi üretiminde referans olarak kullanılır.
YURURLUK_YURUTME_BASLIKLARI = ["Yürürlük", "Yürütme"]

# --------------------------------------------------------------------------
# TÜRKÇE CÜMLE BÖLME -- KISALTMA LİSTESİ
# --------------------------------------------------------------------------
# NEDEN: difflib/sentence-splitter noktayı cümle sonu sayarsa "Dr." veya
# "T.C." gibi kısaltmalar yanlışlıkla cümleyi böler; bu da L3 diff'te
# gereksiz parçalanmaya yol açar.
TR_ABBREVIATIONS = [
    "Dr.", "Prof.", "Doç.", "Yrd.", "Av.", "Sn.",
    "vb.", "vs.", "bkz.", "krş.", "örn.", "mad.",
    "Sk.", "Cad.", "No.", "s.", "T.C.", "A.Ş.", "Ltd.", "Şti.",
    "Alm.", "İng.", "Fr.",
]

# --------------------------------------------------------------------------
# EMBEDDING MODELİ
# --------------------------------------------------------------------------
# NEDEN: Belgeler Türkçe + İngilizce karışık olabildiği için tek dilli bir
# model (örn. sadece İngilizce) anlamsal eşlemeyi bozar (Onaylanmış Karar #3).
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_CACHE_DIR = CACHE_DIR / "embeddings"

# --------------------------------------------------------------------------
# EŞLEŞME EŞİKLERİ (L2 -- semantik eşleme, Hungarian atama)
# --------------------------------------------------------------------------
# NEDEN: Bu eşiğin altında kalan bir atama "eşleşme" değil "rastgele en
# yakın komşu" anlamına gelir (Mimari İlke B) -- böyle çiftler ADDED/REMOVED
# olarak bırakılmalı, zorla MODIFIED'a eşlenmemeli.
#
# NEDEN 0.50 DEĞİL 0.65 (Adım 4 kalibrasyonu, EMBEDDING_MODEL_NAME ile
# ÖLÇÜLDÜ): data/samples ground_truth.json'daki gerçek bir YANLIŞ POZİTİF
# -- 2019 MADDE 8 "Arşivleme Esasları" (REMOVED) ile 2023 MADDE 11 "Açık
# Veri Portalı" (ADDED) tamamen farklı konular olduğu hâlde, ikisi de kısa
# ve ortak mevzuat kelime dağarcığı (örn. "veri", "ilgili", "Kurum")
# paylaşan iki fıkralı maddeler olduğundan kosinüs benzerlikleri ~0.56'dır
# -- eski eşik (0.50) bunu YANLIŞLIKLA eşleştirirdi. 0.65, bu ölçülen yanlış
# pozitiften güvenli bir marj bırakır (bkz.
# tests/test_matcher.py::TestGercekEmbedderEntegrasyonu). NOT: bu kalibrasyon
# şu an SADECE bu negatif örneğe dayanıyor -- ground_truth.json'da L2'nin
# GERÇEKTEN çözmesi gereken (hem numarası HEM başlığı değişmiş) bir POZİTİF
# örnek YOK; gerçek belgelerle kullanılmaya başlandığında bu değer yeniden
# gözden geçirilmeli.
SECTION_MATCH_MIN_COSINE_SIMILARITY = 0.65

# NEDEN: Normalize edilmiş metinler TAM AYNI değilse bile çok yüksek kosinüs
# benzerliği + yüksek karakter benzerliği "pratikte aynı" (IDENTICAL) demektir;
# aksi halde her belgede olağan noktalama/boşluk farkları bile MODIFIED
# sayılır ve özet anlamsızlaşır.
IDENTICAL_COSINE_SIMILARITY_THRESHOLD = 0.995
IDENTICAL_CHAR_SIMILARITY_THRESHOLD = 0.98  # difflib SequenceMatcher.ratio()

# NEDEN "Taşınmış" (yeri değişti) sinyali İÇERİK BENZERLİĞİNDEN BAĞIMSIZ:
# bir maddenin KISIM/BÖLÜM bağlamı ya da belge içindeki sırası, İÇERİĞİ
# değişse de değişmese de kayabilir -- bu yüzden "yeri değişti" bir metin
# benzerliği eşiği DEĞİL, saf bir KONUM sinyalidir (bkz.
# src/analysis/classifier.py::is_moved).
MOVED_MIN_POSITION_DELTA = 3  # sıra numarasındaki minimum kayma

# --------------------------------------------------------------------------
# YÖNETİCİ ÖZETİ -- "ÖNE ÇIKAN DEĞİŞİKLİKLER"
# --------------------------------------------------------------------------
# NEDEN bir ÜST SINIR gerekli: "Öne Çıkan Değişiklikler" KISA bir liste
# olmalı (bkz. summary_builder.py NEDEN notu) -- MODIFIED/ADDED/REMOVED
# kategorilerinin HER BİRİ onlarca madde içerebilir; hepsini tek tek
# maddelemek özeti bir yönetici için OKUNAMAZ hale getirir. Bu sayı
# AŞILDIĞINDA kalan kısım tek bir toplu cümleyle özetlenir (bkz.
# summary_builder.py::_one_cikan_bolum_maddeleri).
SUMMARY_HIGHLIGHT_MAX_ITEMS_PER_CATEGORY = 5

# --------------------------------------------------------------------------
# KAYNAK BAĞLANTISI ("Belgede görüntüle · Sayfa N")
# --------------------------------------------------------------------------
# NEDEN bir TOPLAM bayt BÜTÇESİ (tek dosyanın boyutu DEĞİL): bir PDF'in
# base64 payload'ı (tarayıcıda `blob:` URL'e çevrilip ilgili sayfada
# açılır, bkz. src/ui/components.py::build_pdf_source_payload NEDEN
# notu), HER satırın kendi bağlantısında AYNEN TEKRARLANIR -- sunucuda
# YENİ bir erişim yüzeyi açmadığı için (bkz. o fonksiyonun NEDEN notu)
# BİLİNÇLİ tercih edilir, ama bunun bedeli HER satırda TEKRARLANMASIDIR.
# Tek başına küçük bir PDF bile, YÜZLERCE madde içeren bir belgede
# sayfayı ŞİŞİRİR -- bütçe = dosya boyutu (bayt) × o taraftaki (eski/
# yeni) satır sayısı. Bu bütçe AŞILDIĞINDA tıklanabilir bağlantı YERİNE
# düz "Sayfa N" metni gösterilir (bkz. render_source_link) -- özellik
# ZORLA uygulanmaz.
SOURCE_LINK_MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MB

# --------------------------------------------------------------------------
# DIFF RENK PALETİ (HTML side-by-side görünüm için)
# --------------------------------------------------------------------------
# NEDEN: Renkler burada sabitlenir ki html_renderer.py ve styles.py aynı
# paletten okusun; iki yerde renk tanımlanırsa tutarsızlık riski oluşur.
#
# NEDEN "MOVED"/"RENUMBERED" anahtarları hâlâ burada (ChangeType'ta ARTIK
# YOK olsalar bile): bu ikisi artık İÇERİK durumu değil YAPISAL bayrak
# (bkz. models.py::ChangeType NEDEN notu, classifier.py::ClassifiedSection)
# ama rozet/renk ihtiyaçları AYNI -- bu sözlük anahtar olarak ChangeType.value
# YERİNE düz string alır, bu yüzden yapısal bayraklar için de KULLANILABİLİR.
COLOR_PALETTE = {
    "IDENTICAL": {"text": "#374151", "background": "#FFFFFF"},
    "MODIFIED": {"text": "#8A6D00", "background": "#FFF4CE"},
    "ADDED": {"text": "#1B7F3A", "background": "#E6F4EA"},
    "REMOVED": {"text": "#B3261E", "background": "#FCE8E6"},
    "MOVED": {"text": "#1A56DB", "background": "#E8F0FE"},
    "RENUMBERED": {"text": "#6B21A8", "background": "#F3E8FF"},
}

# --------------------------------------------------------------------------
# TÜRKÇE ETİKETLER (ChangeType İÇERİK durumları + YAPISAL bayraklar)
# --------------------------------------------------------------------------
# NEDEN: models.py'deki ChangeType enum'u İngilizce sabit isimler taşır
# (kod içi tutarlılık için); ama UI ve şablon tabanlı özet Türkçe olmalı.
# Bu sözlük enum ADI (name) -> Türkçe etiket eşlemesidir; enum burada değil
# models.py'de tanımlı çünkü config.py'nin models.py'ye bağımlı OLMAMASI
# gerekir (dairesel bağımlılık riski). "MOVED"/"RENUMBERED" anahtarları
# COLOR_PALETTE'teki gerekçeyle AYNI nedenle burada duruyor -- YAPISAL
# bayrakların rozet etiketi. NEDEN "MOVED" -> "Bölümü Değişti" (anahtar
# adı hâlâ "MOVED"/is_moved, sadece GÖRÜNEN etiket): "Yeri Değişti"
# kullanıcı testinde "Numarası Değişti" ile karıştırılıyordu -- "Bölümü
# Değişti" bunun KISIM/BÖLÜM bağlamının (is_moved'ın asıl kontrol ettiği
# şey, bkz. classifier.py::is_moved) değiştiğini daha AÇIK anlatıyor.
CHANGE_TYPE_LABELS_TR = {
    "IDENTICAL": "Değişmedi",
    "MODIFIED": "Değişti",
    "ADDED": "Yeni Eklendi",
    "REMOVED": "Kaldırıldı",
    "MOVED": "Bölümü Değişti",
    "RENUMBERED": "Numarası Değişti",
}
