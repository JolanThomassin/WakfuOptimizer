"""Comment obtenir un item : recettes d'artisanat (données Ankama) et lien vers le wiki.

Les butins de monstres ne sont pas dans les données du CDN : on renvoie vers la page « Obtainment »
de wakfu.wiki.gg (monstres, taux, coffres, succès).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote_plus

from .fetch import DataBundle

log = logging.getLogger(__name__)

SOURCES_FILE = "sources"   # version précalculée livrée avec le site (tools/build_site.py)
WIKI_SEARCH = "https://wakfu.wiki.gg/index.php?search="

Crafts = dict[int, dict[str, Any]]


def _title(entry: dict[str, Any], lang: str = "fr") -> str:
    t = entry.get("title") or {}
    return str(t.get(lang) or t.get("fr") or "")


def compute_crafts(bundle: DataBundle) -> Crafts:
    """item_id -> {"job": nom du métier, "level": niveau, "ingredients": [[nom, quantité], ...]}."""
    recipes = {int(r["id"]): r for r in bundle.load("recipes")}  # type: ignore[union-attr]
    jobs = {int(c["definition"]["id"]): _title(c) for c in bundle.load("recipeCategories")}  # type: ignore[union-attr]
    names: dict[int, str] = {}
    for t in ("items", "jobsItems"):
        for e in bundle.load(t):  # type: ignore[union-attr]
            d = e["definition"]
            names[int((d.get("item") or d)["id"])] = _title(e)
    ingredients: dict[int, list[tuple[int, str, int]]] = {}
    for g in bundle.load("recipeIngredients"):  # type: ignore[union-attr]
        ingredients.setdefault(int(g["recipeId"]), []).append(
            (int(g.get("ingredientOrder", 0)), names.get(int(g["itemId"]), f"#{g['itemId']}"), int(g["quantity"])))
    out: Crafts = {}
    for res in bundle.load("recipeResults"):  # type: ignore[union-attr]
        iid, rid = int(res["productedItemId"]), int(res["recipeId"])
        r = recipes.get(rid)
        if r is None or iid in out:
            continue
        out[iid] = {"job": jobs.get(int(r["categoryId"]), "Artisanat"), "level": int(r.get("level", 0)),
                    "ingredients": [[n, q] for _, n, q in sorted(ingredients.get(rid, []))]}
    return out


def load_crafts(bundle: DataBundle, keep: set[int] | None = None) -> Crafts:
    """Recettes : fichier précalculé s'il existe (site), sinon calculées depuis le cache."""
    try:
        if bundle.path(SOURCES_FILE).is_file():
            return {int(k): v for k, v in bundle.load(SOURCES_FILE).items()}  # type: ignore[union-attr]
        crafts = compute_crafts(bundle)
    except (OSError, ValueError, KeyError) as exc:
        log.warning("Recettes indisponibles : %s", exc)
        return {}
    return {k: v for k, v in crafts.items() if keep is None or k in keep}


def wiki_url(names: dict[str, str]) -> str:
    """Le wiki est en anglais ; la recherche redirige directement vers la page de l'item."""
    return WIKI_SEARCH + quote_plus(names.get("en") or names.get("fr") or "")


def dump_crafts(crafts: Crafts) -> str:
    return json.dumps({str(k): v for k, v in crafts.items()}, ensure_ascii=False, separators=(",", ":"))
