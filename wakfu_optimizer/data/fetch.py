"""Téléchargement des données de jeu depuis le CDN Ankama, avec cache versionné.

Organisation du cache :
    data/cache/<version>/<type>.json
    data/cache/<version>/manifest.json   (écrit en dernier : sa présence = version complète)

Utilisation en ligne de commande :
    python -m wakfu_optimizer.data.fetch            # télécharge si nouvelle version
    python -m wakfu_optimizer.data.fetch --force    # retélécharge la version courante
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

CDN_BASE = "https://wakfu.cdn.ankama.com/gamedata"
CONFIG_URL = f"{CDN_BASE}/config.json"

# Types demandés. Ceux qui n'existent pas (404) sont ignorés et notés dans le manifeste.
DATA_TYPES: tuple[str, ...] = (
    "items",
    "actions",
    "equipmentItemTypes",
    "itemProperties",
    "states",
    "jobsItems",
    "recipes",
    "recipeCategories",
    "recipeResults",
    "recipeIngredients",
)
# Types indispensables : sans eux, le cache est inutilisable.
REQUIRED_TYPES: frozenset[str] = frozenset({"items", "actions", "equipmentItemTypes"})

MANIFEST = "manifest.json"
USER_AGENT = "wakfu-optimizer/0.1 (+outil communautaire non officiel)"

DEFAULT_CACHE_ROOT = Path(
    os.environ.get("WAKFU_OPTIMIZER_CACHE", Path(__file__).resolve().parents[2] / "data" / "cache")
)


class NotFoundError(Exception):
    """La ressource n'existe pas sur le CDN (HTTP 404)."""


class NetworkError(Exception):
    """Erreur réseau persistante (hors ligne, timeout, 5xx...)."""


class DataUnavailableError(Exception):
    """Aucune donnée exploitable : ni réseau, ni cache complet."""


# Signature d'une fonction de téléchargement : (url, timeout_s) -> contenu brut.
Opener = Callable[[str, float], bytes]


def urllib_opener(url: str, timeout: float) -> bytes:
    """Téléchargement HTTP(S) simple avec la bibliothèque standard."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: bytes = resp.read()
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFoundError(url) from exc
        raise NetworkError(f"HTTP {exc.code} sur {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NetworkError(f"{type(exc).__name__}: {exc} ({url})") from exc


@dataclass(frozen=True)
class DataBundle:
    """Jeu de données disponible localement."""

    version: str
    directory: Path
    offline: bool  # True si on utilise un cache faute de réseau
    available: frozenset[str] = field(default_factory=frozenset)

    def path(self, data_type: str) -> Path:
        return self.directory / f"{data_type}.json"

    def load(self, data_type: str) -> object:
        """Charge un type de données (lève FileNotFoundError s'il est absent)."""
        with self.path(data_type).open(encoding="utf-8") as fh:
            return json.load(fh)


class GameDataFetcher:
    """Gère la version courante du CDN et le cache local."""

    def __init__(
        self,
        cache_root: Path = DEFAULT_CACHE_ROOT,
        opener: Opener = urllib_opener,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.5,
        types: Sequence[str] = DATA_TYPES,
    ) -> None:
        self.cache_root = Path(cache_root)
        self._open = opener
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.types = tuple(types)

    # ------------------------------------------------------------------ réseau
    def _get(self, url: str, timeout: float | None = None) -> bytes:
        """GET avec retry exponentiel. Un 404 n'est jamais retenté."""
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._open(url, timeout or self.timeout)
            except NotFoundError:
                raise
            except NetworkError as exc:
                last = exc
                log.warning("Échec %d/%d : %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    time.sleep(self.backoff ** (attempt - 1))
        raise NetworkError(str(last))

    def remote_version(self) -> str:
        """Lit config.json sur le CDN et renvoie la version courante."""
        raw = self._get(CONFIG_URL, timeout=min(self.timeout, 15.0))
        try:
            version = json.loads(raw)["version"]
        except (ValueError, KeyError, TypeError) as exc:
            raise NetworkError(f"config.json illisible : {raw[:200]!r}") from exc
        if not isinstance(version, str) or not version:
            raise NetworkError(f"Version invalide dans config.json : {version!r}")
        return version

    # ------------------------------------------------------------------- cache
    def _version_dir(self, version: str) -> Path:
        # La version sert de nom de dossier : on refuse tout séparateur de chemin.
        if any(c in version for c in "/\\") or version in {".", ".."}:
            raise ValueError(f"Version suspecte : {version!r}")
        return self.cache_root / version

    def is_complete(self, version: str) -> bool:
        return (self._version_dir(version) / MANIFEST).is_file()

    def cached_versions(self) -> list[str]:
        """Versions complètes en cache, de la plus récente à la plus ancienne."""
        if not self.cache_root.is_dir():
            return []
        found = [p.name for p in self.cache_root.iterdir() if (p / MANIFEST).is_file()]
        return sorted(found, key=_version_key, reverse=True)

    def _bundle(self, version: str, offline: bool) -> DataBundle:
        directory = self._version_dir(version)
        manifest = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
        available = frozenset(manifest.get("files", {}))
        return DataBundle(version, directory, offline, available)

    def download(self, version: str) -> DataBundle:
        """Télécharge tous les types pour `version` puis écrit le manifeste."""
        directory = self._version_dir(version)
        directory.mkdir(parents=True, exist_ok=True)
        files: dict[str, dict[str, object]] = {}
        missing: list[str] = []
        for data_type in self.types:
            url = f"{CDN_BASE}/{version}/{data_type}.json"
            log.info("Téléchargement de %s.json ...", data_type)
            try:
                raw = self._get(url)
            except NotFoundError:
                if data_type in REQUIRED_TYPES:
                    raise NetworkError(f"Type obligatoire absent du CDN : {data_type}") from None
                log.info("  %s.json n'existe pas pour cette version, ignoré.", data_type)
                missing.append(data_type)
                continue
            json.loads(raw)  # validation : lève ValueError si le contenu est tronqué
            tmp = directory / f"{data_type}.json.part"
            tmp.write_bytes(raw)
            tmp.replace(directory / f"{data_type}.json")  # écriture atomique
            files[data_type] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            log.info("  %s.json : %.1f Mo", data_type, len(raw) / 1e6)
        manifest = {
            "version": version,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": CDN_BASE,
            "files": files,
            "missing": missing,
        }
        (directory / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return DataBundle(version, directory, offline=False, available=frozenset(files))

    # ------------------------------------------------------------ point d'entrée
    def ensure(self, force: bool = False) -> DataBundle:
        """Renvoie des données utilisables.

        - Réseau OK : télécharge uniquement si la version a changé (ou si `force`).
        - Hors ligne : se rabat sur la version complète la plus récente du cache.
        """
        try:
            version = self.remote_version()
        except NetworkError as exc:
            cached = self.cached_versions()
            if not cached:
                raise DataUnavailableError(
                    "Impossible de joindre le CDN Ankama et aucun cache local n'existe. "
                    "Vérifiez votre connexion puis relancez la mise à jour des données."
                ) from exc
            log.warning("CDN injoignable (%s) : utilisation du cache %s.", exc, cached[0])
            return self._bundle(cached[0], offline=True)

        if self.is_complete(version) and not force:
            log.info("Données à jour (version %s).", version)
            return self._bundle(version, offline=False)
        log.info("Nouvelle version %s : téléchargement.", version)
        try:
            return self.download(version)
        except (NetworkError, ValueError) as exc:
            cached = [v for v in self.cached_versions() if v != version]
            if not cached:
                raise DataUnavailableError(f"Téléchargement de la version {version} impossible : {exc}") from exc
            log.error("Téléchargement interrompu (%s) : retour au cache %s.", exc, cached[0])
            return self._bundle(cached[0], offline=True)


def _version_key(version: str) -> tuple[int | str, ...]:
    """Clé de tri « 1.93.1.62 » -> (1, 93, 1, 62) ; tolère les suffixes non numériques."""
    return tuple(int(p) if p.isdigit() else p for p in version.split("."))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Met à jour le cache des données Wakfu.")
    parser.add_argument("--force", action="store_true", help="retélécharger même si la version est en cache")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_ROOT, help="dossier du cache")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        bundle = GameDataFetcher(cache_root=args.cache).ensure(force=args.force)
    except DataUnavailableError as exc:
        log.error("%s", exc)
        return 1
    state = "hors ligne (cache)" if bundle.offline else "en ligne"
    log.info("Version %s prête dans %s [%s]", bundle.version, bundle.directory, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
