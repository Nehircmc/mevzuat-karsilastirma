"""
NEDEN otomatik yeniden üretim: document_spec.py değiştirilip de
generate_samples.py elle çalıştırılmazsa, testler ESKİ (spec ile tutarsız)
belgelere karşı YANLIŞ bir güvenle geçebilir. Bu fixture her test oturumunda
örnek belgeleri güncel spec'ten TAZE üretir.
"""

import pytest

from data.samples.generate_samples import generate_all
from src.config import SAMPLES_DIR


@pytest.fixture(scope="session", autouse=True)
def _ornek_belgeleri_uret():
    generate_all(SAMPLES_DIR)
