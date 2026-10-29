"""Tests du téléchargement et du cache versionné (sans réseau : opener simulé)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wakfu_optimizer.data.fetch import (
    CDN_BASE,
    CONFIG_URL,
    DataUnavailableError,
    GameDataFetcher,
    NetworkError,
    NotFoundError,
)

TYPES = ("items", "actions", "equipmentItemTypes", "recipes")


class FakeCDN:
    """Simule le CDN : dictionnaire url -> contenu, compte les appels."""

    def __init__(self, version: str = "1.93.1.62", online: bool = True) -> None:
        self.version = version
        self.online = online
        self.calls: list[str] = []
        self.files: dict[str, bytes] = {
            t: json.dumps([{"type": t}]).encode() for t in ("items", "actions", "equipmentItemTypes")
        }  # recipes absent -> 404

    def __call__(self, url: str, timeout: float) -> bytes:
        self.calls.append(url)
        if not self.online:
            raise NetworkError("hors ligne")
        if url == CONFIG_URL:
            return json.dumps({"version": self.version}).encode()
        prefix = f"{CDN_BASE}/{self.version}/"
        name = url.removeprefix(prefix).removesuffix(".json")
        if url.startswith(prefix) and name in self.files:
            return self.files[name]
        raise NotFoundError(url)


def make(tmp_path: Path, cdn: FakeCDN) -> GameDataFetcher:
    return GameDataFetcher(cache_root=tmp_path, opener=cdn, retries=2, backoff=0.0, types=TYPES)


def test_premier_telechargement_et_manifeste(tmp_path: Path) -> None:
    cdn = FakeCDN()
    bundle = make(tmp_path, cdn).ensure()
    assert bundle.version == "1.93.1.62" and not bundle.offline
    assert bundle.available == {"items", "actions", "equipmentItemTypes"}
    manifest = json.loads((tmp_path / "1.93.1.62" / "manifest.json").read_text())
    assert manifest["missing"] == ["recipes"]  # type absent ignoré proprement
    assert bundle.load("items") == [{"type": "items"}]
    assert not list((tmp_path / "1.93.1.62").glob("*.part"))


def test_pas_de_retelechargement_si_meme_version(tmp_path: Path) -> None:
    cdn = FakeCDN()
    make(tmp_path, cdn).ensure()
    cdn.calls.clear()
    make(tmp_path, cdn).ensure()
    assert cdn.calls == [CONFIG_URL]  # seule la version est relue


def test_force_retelecharge(tmp_path: Path) -> None:
    cdn = FakeCDN()
    make(tmp_path, cdn).ensure()
    cdn.calls.clear()
    make(tmp_path, cdn).ensure(force=True)
    assert len(cdn.calls) == 1 + len(TYPES)


def test_nouvelle_version_telechargee_a_cote(tmp_path: Path) -> None:
    cdn = FakeCDN("1.93.1.62")
    make(tmp_path, cdn).ensure()
    cdn.version = "1.94.0.1"
    bundle = make(tmp_path, cdn).ensure()
    assert bundle.version == "1.94.0.1"
    assert make(tmp_path, cdn).cached_versions() == ["1.94.0.1", "1.93.1.62"]


def test_hors_ligne_utilise_le_dernier_cache(tmp_path: Path) -> None:
    cdn = FakeCDN()
    make(tmp_path, cdn).ensure()
    cdn.online = False
    bundle = make(tmp_path, cdn).ensure()
    assert bundle.offline and bundle.version == "1.93.1.62"


def test_hors_ligne_sans_cache_message_clair(tmp_path: Path) -> None:
    with pytest.raises(DataUnavailableError, match="aucun cache"):
        make(tmp_path, FakeCDN(online=False)).ensure()


def test_retry_puis_succes(tmp_path: Path) -> None:
    cdn = FakeCDN()
    failures = {"n": 0}

    def flaky(url: str, timeout: float) -> bytes:
        if url == CONFIG_URL and failures["n"] == 0:
            failures["n"] += 1
            raise NetworkError("timeout")
        return cdn(url, timeout)

    bundle = GameDataFetcher(tmp_path, opener=flaky, retries=2, backoff=0.0, types=TYPES).ensure()
    assert bundle.version == "1.93.1.62"


def test_type_obligatoire_absent_et_contenu_tronque(tmp_path: Path) -> None:
    cdn = FakeCDN()
    del cdn.files["items"]
    with pytest.raises(DataUnavailableError):
        make(tmp_path, cdn).ensure()
    cdn = FakeCDN()
    cdn.files["actions"] = b'[{"tronqu'
    with pytest.raises(DataUnavailableError):
        make(tmp_path, cdn).ensure()
    assert not (tmp_path / "1.93.1.62" / "manifest.json").exists()  # version incomplète


def test_telechargement_rate_revient_a_l_ancien_cache(tmp_path: Path) -> None:
    cdn = FakeCDN("1.93.1.62")
    make(tmp_path, cdn).ensure()
    cdn.version = "1.94.0.1"
    cdn.files["items"] = b"{coupe"
    bundle = make(tmp_path, cdn).ensure()
    assert bundle.offline and bundle.version == "1.93.1.62"


def test_version_malveillante_refusee(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make(tmp_path, FakeCDN("../../etc")).ensure()


def test_urllib_opener_vrai_http(tmp_path: Path) -> None:
    """Opener réel contre un petit serveur HTTP local : 200, 404 et refus de connexion."""
    import http.server
    import threading

    from wakfu_optimizer.data.fetch import urllib_opener

    (tmp_path / "ok.json").write_text('{"version": "x"}')

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a: object, **k: object) -> None:
            super().__init__(*a, directory=str(tmp_path), **k)  # type: ignore[arg-type]

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert json.loads(urllib_opener(f"{base}/ok.json", 5)) == {"version": "x"}
        with pytest.raises(NotFoundError):
            urllib_opener(f"{base}/absent.json", 5)
    finally:
        server.shutdown()
    with pytest.raises(NetworkError):
        urllib_opener(f"{base}/ok.json", 2)  # serveur arrêté
