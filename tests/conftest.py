"""Options pytest du projet.

    pytest                      # tests unitaires + tests de qualité rapides (scénarios clés)
    pytest --quality=full       # + matrice complète : chaque classe × archétype habituel × niveau (long)
    pytest --quality=off        # sans lancer le solveur sur les vraies données
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--quality", choices=("off", "quick", "full"), default=os.environ.get("WAKFU_QUALITY", "quick"),
                     help="tests de qualité des builds sur les vraies données (défaut : quick)")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "quality: optimisation complète sur les vraies données (solveur)")
    config.addinivalue_line("markers", "quality_full: matrice complète des tests de qualité (--quality=full)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mode = config.getoption("--quality")
    skip_full = pytest.mark.skip(reason="matrice complète : pytest --quality=full")
    skip_all = pytest.mark.skip(reason="tests de qualité désactivés (--quality=off)")
    for item in items:
        if mode == "off" and ("quality" in item.keywords or "quality_full" in item.keywords):
            item.add_marker(skip_all)
        elif mode != "full" and "quality_full" in item.keywords:
            item.add_marker(skip_full)
