"""
Configuração compartilhada pelos scripts de src/365-fv.

Todos os caminhos são relativos: os scripts devem ser
executados a partir da raiz do repositório.
"""

from pathlib import Path


# ============================================================
# SITE
# ============================================================

BASE_URL = "https://www.bet365.bet.br/"

# Coupons com este marcador não trazem mercados/odds.
EMPTY_COUPON_MARKER = "EV;ID=EMB;"


# ============================================================
# DIRETÓRIOS
# ============================================================

DATA_DIR = Path("data")

RAW_DIR = DATA_DIR / "raw"

PARSED_DIR = DATA_DIR / "parsed"

NORMALIZED_DIR = DATA_DIR / "normalized"

DIAGNOSTICS_DIR = DATA_DIR / "diagnostics"
