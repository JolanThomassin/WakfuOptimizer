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

# {"recipes": {id d'item: {"job": id du métier, "level": niveau, "ingredients": [[id d'ingrédient, quantité], ...]}},
#  "names": {id d'ingrédient: {langue: nom}}, "jobs": {id du métier: {langue: nom}}} (clés en texte, comme en JSON)
Crafts = dict[str, dict[str, Any]]


def _titles(entry: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in (entry.get("title") or {}).items() if v}


def compute_crafts(bundle: DataBundle) -> Crafts:
    recipes = {int(r["id"]): r for r in bundle.load("recipes")}  # type: ignore[union-attr]
    jobs = {str(c["definition"]["id"]): _titles(c) for c in bundle.load("recipeCategories")}  # type: ignore[union-attr]
    names: dict[str, dict[str, str]] = {}
    for t in ("items", "jobsItems"):
        for e in bundle.load(t):  # type: ignore[union-attr]
            d = e["definition"]
            names[str((d.get("item") or d)["id"])] = _titles(e)
    ingredients: dict[int, list[tuple[int, int, int]]] = {}
    for g in bundle.load("recipeIngredients"):  # type: ignore[union-attr]
        ingredients.setdefault(int(g["recipeId"]), []).append((int(g.get("ingredientOrder", 0)), int(g["itemId"]), int(g["quantity"])))
    out: dict[str, Any] = {}
    for res in bundle.load("recipeResults"):  # type: ignore[union-attr]
        iid, rid = str(res["productedItemId"]), int(res["recipeId"])
        r = recipes.get(rid)
        if r is None or iid in out:
            continue
        out[iid] = {"job": str(r["categoryId"]), "level": int(r.get("level", 0)),
                    "ingredients": [[i, q] for _, i, q in sorted(ingredients.get(rid, []))]}
    return {"recipes": out, "names": names, "jobs": jobs}


def load_crafts(bundle: DataBundle, keep: set[int] | None = None) -> Crafts:
    """Recettes : fichier précalculé s'il existe (site), sinon calculées depuis le cache."""
    try:
        if bundle.path(SOURCES_FILE).is_file():
            crafts: Any = bundle.load(SOURCES_FILE)
            if "recipes" in crafts:   # ancien format (noms en français seulement) : on recalcule
                return crafts  # type: ignore[no-any-return]
        crafts = compute_crafts(bundle)
    except (OSError, ValueError, KeyError) as exc:
        log.warning("Recettes indisponibles : %s", exc)
        return {}
    recipes = {k: v for k, v in crafts["recipes"].items() if keep is None or int(k) in keep}
    used = {str(i) for r in recipes.values() for i, _ in r["ingredients"]}
    return {"recipes": recipes, "names": {k: v for k, v in crafts["names"].items() if k in used},
            "jobs": {k: v for k, v in crafts["jobs"].items() if any(r["job"] == k for r in recipes.values())}}


def craft_of(crafts: Crafts, item_id: int, lang: str) -> dict[str, Any] | None:
    """Recette d'un item dans la langue voulue : {"job", "level", "ingredients": [[nom, quantité], ...]}."""
    r = (crafts.get("recipes") or {}).get(str(item_id))
    if r is None:
        return None
    pick = lambda t, fb: t.get(lang) or t.get("fr") or fb  # noqa: E731
    names = crafts.get("names") or {}
    return {"job": pick((crafts.get("jobs") or {}).get(r["job"], {}), "Artisanat"), "level": r["level"],
            "ingredients": [[pick(names.get(str(i), {}), f"#{i}"), q] for i, q in r["ingredients"]]}


def wiki_url(names: dict[str, str]) -> str:
    """Le wiki est en anglais ; la recherche redirige directement vers la page de l'item."""
    return WIKI_SEARCH + quote_plus(names.get("en") or names.get("fr") or "")


def dump_crafts(crafts: Crafts) -> str:
    return json.dumps(crafts, ensure_ascii=False, separators=(",", ":"))
