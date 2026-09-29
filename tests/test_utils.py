"""
Testes dos helpers puros de utils.py.
"""

import pytest

from utils import detect_response_type


BASE = "https://www.bet365.bet.br"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{BASE}/virtualsportscontentapi/splash?lid=33&pd=%23AVR%23B144%23", "splash"),
        (f"{BASE}/contentdata/virtualsportscontentapi/coupon?pd=%23AVR%23B146%23", "coupon"),
        # Endpoints ainda desconhecidos (ex.: aba Resultados) viram o próprio nome.
        (f"{BASE}/contentdata/virtualsportscontentapi/results?pd=x", "results"),
        (f"{BASE}/VirtualSportsContentApi/ResultsPage/?pd=x", "resultspage"),
        (f"{BASE}/virtualsportscontentapi/race-results?pd=x", "race_results"),
        (f"{BASE}/virtualsportscontentapi/", "other"),
        (f"{BASE}/virtualsportscontentapi", "other"),
        # Fora da API: não é capturado.
        (f"{BASE}/contentdata/sportsbook/coupon?pd=x", None),
        (f"{BASE}/?q=virtualsportscontentapi", None),
    ],
)
def test_detect_response_type(url, expected):
    assert detect_response_type(url) == expected
