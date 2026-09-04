"""
Adım 6: renkli diff görünümü için CSS.

NEDEN iki parçalı (assets/styles.css + generate_color_css()): DÜZEN
(kenarlık, boşluk, kart yapısı) statik bir dosyada elle yazılır çünkü
sık değişmez ve renkten bağımsızdır; RENK ise TEK KAYNAK olan
src/config.py::COLOR_PALETTE'ten PROGRAMATİK olarak üretilir -- aksi halde
renkler iki yerde (config.py VE bir .css dosyasında) elle senkron
tutulmaya çalışılır ve er ya da geç birbirinden sessizce sapar.
"""

from __future__ import annotations

from src.config import ASSETS_DIR, COLOR_PALETTE

_STATIC_CSS_PATH = ASSETS_DIR / "styles.css"


def _css_key(change_type_value: str) -> str:
    """ChangeType.value ("ADDED" gibi) -> CSS sınıf soneki ("added")."""
    return change_type_value.lower()


def generate_color_css() -> str:
    """
    COLOR_PALETTE'teki HER ChangeType için `.mk-diff-<key>` (cümle/kelime
    düzeyinde vurgulama, bkz. src/reporting/html_renderer.py) ve
    `.mk-badge-<key>` (Section düzeyinde rozet) CSS kurallarını üretir.
    """
    lines: list[str] = []
    for change_type_value, colors in COLOR_PALETTE.items():
        css_key = _css_key(change_type_value)
        declaration = f"color: {colors['text']}; background-color: {colors['background']};"
        lines.append(f".mk-diff-{css_key} {{ {declaration} }}")
        lines.append(f".mk-badge-{css_key} {{ {declaration} }}")
    return "\n".join(lines)


def load_static_css() -> str:
    """assets/styles.css içindeki (renk İÇERMEYEN) düzen CSS'ini okur."""
    if not _STATIC_CSS_PATH.exists():
        return ""
    return _STATIC_CSS_PATH.read_text(encoding="utf-8")


def build_full_css() -> str:
    """Statik düzen CSS'i ile config.py'den üretilen renk CSS'ini birleştirir."""
    return f"{load_static_css()}\n\n{generate_color_css()}"


def inject() -> None:
    """TAM CSS'i (düzen + renk) geçerli Streamlit sayfasına enjekte eder."""
    import streamlit as st

    st.markdown(f"<style>{build_full_css()}</style>", unsafe_allow_html=True)
