"""
Adım 4: metinleri embedding vektörlerine çeviren sarmalayıcı + disk önbelleği.

NEDEN disk önbelleği: sentence-transformers hem MODEL YÜKLEMESİ (ağırlıklar,
saniyeler sürer) hem de HER metin için ENCODE çağrısı bakımından pahalıdır;
aynı Section metni farklı çalıştırmalar arasında (testler, aynı belge
çiftinin tekrar analiz edilmesi) tekrar tekrar encode edilmemeli. Önbellek
anahtarı hem metnin hem MODEL ADININ hash'idir -- NEDEN model adı da
anahtara giriyor (alt dizin olarak): farklı modellerin ürettiği vektörler
UYUMSUZDUR (farklı boyut/uzay), model değişirse eski önbellek SESSİZCE
yanlış vektör döndürmemeli.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

from src.config import EMBEDDING_CACHE_DIR, EMBEDDING_MODEL_NAME


def _safe_model_dirname(model_name: str) -> str:
    """Model adını dosya sistemi için güvenli bir alt dizin adına çevirir."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", model_name)


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embedder:
    """
    sentence-transformers.SentenceTransformer etrafında ince bir sarmalayıcı.

    NEDEN model modül seviyesinde DEĞİL __init__/embed içinde tembel (lazy)
    yükleniyor: sentence-transformers/torch içe aktarımı ağırdır (saniyeler
    sürebilir); bu maliyeti sadece GERÇEKTEN bir metin encode edilirken
    ödemek istiyoruz -- section_matcher.py'yi sadece L1 katmanı için import
    eden (embedder hiç örneklenmeyen) bir çağıran bu maliyeti ÖDEMEMELİ.
    """

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        cache_dir: Path = EMBEDDING_CACHE_DIR,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = Path(cache_dir) / _safe_model_dirname(model_name)
        self._model = None  # tembel yükleme, bkz. sınıf docstring'i

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _cache_path(self, text: str) -> Path:
        return self._cache_dir / f"{_cache_key(text)}.npy"

    def embed(self, texts: list[str]) -> np.ndarray:
        """
        Verilen metinleri embedding vektörlerine çevirir; sonuç
        (len(texts), boyut) şeklinde bir numpy dizisidir, GİRDİ SIRASIYLA
        aynı sıradadır.

        Önbellekte olmayan metinler TEK bir model.encode() çağrısında toplu
        hesaplanır (NEDEN toplu: sentence-transformers'ta batch encode,
        metin başına ayrı çağırmaktan çok daha hızlıdır), ardından her biri
        diske yazılır ki bir sonraki çağrı (aynı metin + aynı model) modeli
        hiç çalıştırmadan önbellekten okusun.
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        self._cache_dir.mkdir(parents=True, exist_ok=True)

        results: list[np.ndarray] = [None] * len(texts)  # type: ignore[list-item]
        to_compute_idx: list[int] = []
        to_compute_text: list[str] = []

        for i, text in enumerate(texts):
            path = self._cache_path(text)
            if path.exists():
                results[i] = np.load(path)
            else:
                to_compute_idx.append(i)
                to_compute_text.append(text)

        if to_compute_text:
            model = self._load_model()
            computed = model.encode(to_compute_text, convert_to_numpy=True)
            for idx, text, vec in zip(to_compute_idx, to_compute_text, computed):
                vec = np.asarray(vec, dtype=np.float32)
                results[idx] = vec
                np.save(self._cache_path(text), vec)

        return np.stack(results)
