"""Exploration des actionId utilisés par les équipements.

Produit un rapport Markdown (reports/actions_<version>.md) qui liste, pour chaque
actionId présent dans les equipEffects d'un équipement :
  - le libellé FR de actions.json,
  - le nombre d'occurrences,
  - le nombre d'effets dont la valeur dépend du niveau (params[1] != 0),
  - un exemple (item + params),
  - la stat associée dans static/actions_map.yaml (ou « NON MAPPÉ »).

Code de sortie 2 si un actionId n'est pas mappé : à lancer après chaque patch.

    python -m wakfu_optimizer.data.explore [--cache DOSSIER] [--version X]
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .actions_map import ActionMapping, load_actions_map
from .fetch import DEFAULT_CACHE_ROOT, DataBundle, GameDataFetcher

log = logging.getLogger(__name__)

# Types levelables (la valeur dépend du niveau du familier/de la monture).
LEVELABLE_TYPES = frozenset({582, 611})
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


@dataclass
class ActionUsage:
    action_id: int
    effect: str = ""
    description_fr: str = ""
    count: int = 0
    per_level_count: int = 0       # params[1] != 0 hors familiers/montures
    max_params: int = 0
    example: tuple[int, str, list[Any]] | None = None
    items: set[int] = field(default_factory=set)


def collect_usage(items: list[dict[str, Any]], equipment_types: list[dict[str, Any]],
                  actions: list[dict[str, Any]], lang: str = "fr") -> dict[int, ActionUsage]:
    """Agrège les actionId des equipEffects de tous les items équipables."""
    eq_type_ids = {t["definition"]["id"] for t in equipment_types}
    action_info = {a["definition"]["id"]: a for a in actions}
    usage: dict[int, ActionUsage] = {}
    for entry in items:
        item = entry["definition"]["item"]
        type_id = item["baseParameters"]["itemTypeId"]
        if type_id not in eq_type_ids:
            continue
        name = entry.get("title", {}).get(lang, f"#{item['id']}")
        for eff in entry["definition"].get("equipEffects", []):
            d = eff["effect"]["definition"]
            aid = int(d["actionId"])
            params: list[Any] = list(d.get("params", []))
            u = usage.get(aid)
            if u is None:
                info = action_info.get(aid, {})
                u = usage[aid] = ActionUsage(
                    aid,
                    effect=info.get("definition", {}).get("effect", "?"),
                    description_fr=(info.get("description") or {}).get(lang, "") or "",
                )
            u.count += 1
            u.items.add(item["id"])
            u.max_params = max(u.max_params, len(params))
            if len(params) > 1 and params[1] and type_id not in LEVELABLE_TYPES:
                u.per_level_count += 1
            if u.example is None:
                u.example = (item["id"], name, params)
    return usage


def render_report(version: str, usage: dict[int, ActionUsage], mapping: dict[int, ActionMapping]) -> str:
    unmapped = sorted(set(usage) - set(mapping))
    unused = sorted(set(mapping) - set(usage))
    lines = [
        f"# actionId des équipements — données {version}",
        "",
        f"{len(usage)} actionId distincts, {sum(u.count for u in usage.values())} effets.",
        f"Non mappés : {', '.join(map(str, unmapped)) or 'aucun'}.",
        f"Mappés mais absents de cette version : {', '.join(map(str, unused)) or 'aucun'}.",
        "",
        "| actionId | Effet (actions.json) | Stat interne | Signe | Occurrences | Dépend du niveau | Exemple |",
        "|---:|---|---|:-:|---:|---:|---|",
    ]
    for aid in sorted(usage):
        u = usage[aid]
        m = mapping.get(aid)
        stat = "**NON MAPPÉ**" if m is None else (m.stat if m.kind.value == "flat" else f"{m.stat} ({m.kind.value})")
        if m is not None and m.todo:
            stat += " ⚠"
        sign = "" if m is None or m.kind.value == "ignore" else ("+" if m.sign > 0 else "−")
        ex = f"{u.example[1]} ({u.example[0]}) {u.example[2]}" if u.example else ""
        lines.append(f"| {aid} | {u.effect} | {stat} | {sign} | {u.count} | {u.per_level_count} | {ex} |")
    todos = [m for m in mapping.values() if m.todo and m.action_id in usage]
    if todos:
        lines += ["", "## Hypothèses à confirmer", ""]
        lines += [f"- actionId {m.action_id} : {m.todo}" for m in todos]
    return "\n".join(lines) + "\n"


def explore(bundle: DataBundle, mapping: dict[int, ActionMapping], out_dir: Path = REPORTS_DIR) -> tuple[Path, list[int]]:
    usage = collect_usage(
        bundle.load("items"),  # type: ignore[arg-type]
        bundle.load("equipmentItemTypes"),  # type: ignore[arg-type]
        bundle.load("actions"),  # type: ignore[arg-type]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"actions_{bundle.version}.md"
    report.write_text(render_report(bundle.version, usage, mapping), encoding="utf-8")
    return report, sorted(set(usage) - set(mapping))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Liste les actionId des équipements.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--version", help="version en cache (défaut : la plus récente)")
    parser.add_argument("--out", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    fetcher = GameDataFetcher(cache_root=args.cache)
    versions = fetcher.cached_versions()
    if not versions:
        log.error("Aucune donnée en cache : lancez d'abord  python -m wakfu_optimizer.data.fetch")
        return 1
    version = args.version or versions[0]
    if version not in versions:
        log.error("Version %s absente du cache (disponibles : %s)", version, ", ".join(versions))
        return 1
    bundle = DataBundle(version, args.cache / version, offline=True)
    report, unmapped = explore(bundle, load_actions_map(), args.out)
    log.info("Rapport écrit : %s", report)
    if unmapped:
        log.warning("actionId non mappés (à ajouter dans static/actions_map.yaml) : %s", unmapped)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
