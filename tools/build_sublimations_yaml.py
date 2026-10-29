"""Génère wakfu_optimizer/data/static/sublimations.yaml.

Le CDN Ankama ne fournit que le NOM des états appliqués par les sublimations.
Les descriptions chiffrées par niveau et les niveaux de cumul max proviennent
de WakForge (https://github.com/Tmktahu/WakForge, licence MIT).
Les effets « modélisés » (utilisés par le solveur) sont choisis à la main
ci-dessous (CURATED) : seuls les effets permanents ou à condition simple.

    python tools/build_sublimations_yaml.py CHEMIN/VERS/WakForge
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

# state_id -> liste de (index de ligne de description, clé num, [stats], mode, condition)
#   mode : flat (valeur brute) | pct_level (% du niveau du personnage) | const:<v> (valeur fixe)
#   le signe est lu dans le texte (« -{num_0} » => négatif)
#   conditions : none, melee, distance, berserk, hp_high, no_armor, two_handed,
#                light_weapons, element:fire|water|earth|air,
#                no_secondary (maîtrises secondaires <= 0 : option « combo Neutralité + Dénouement »)
CURATED: dict[int, list[tuple[int, str, list[str], str, str]]] = {
    5982: [(1, "num_0", ["all_mastery"], "pct_level", "none"), (2, "num_0", ["elem_res"], "flat", "none")],  # Ravage
    5984: [(0, "num_0", ["hp_pct"], "flat", "none")],                       # Cicatrisation
    6026: [(0, "num_0", ["crit_rate"], "flat", "none")],                    # Influence
    6008: [(0, "num_0", ["ap"], "flat", "none"), (1, "num_0", ["elem_res"], "flat", "none")],  # Vivacité
    6005: [(0, "num_0", ["mp"], "flat", "none"), (1, "num_0", ["dmg_pct"], "flat", "none")],   # Vélocité
    6010: [(0, "num_0", ["range"], "flat", "none"), (1, "num_0", ["lock"], "flat", "none"),
           (2, "num_0", ["dodge"], "flat", "none")],                       # Visibilité
    5981: [(0, "num_0", ["wp"], "flat", "none"), (1, "num_0", ["willpower"], "flat", "none")],  # Dévastation
    6000: [(0, "num_0", ["crit_rate"], "flat", "none"), (1, "num_0", ["dmg_pct"], "flat", "none")],  # Théorie de la matière
    6013: [(1, "num_0", ["crit_rate"], "flat", "none"), (1, "num_1", ["block"], "flat", "none"),
           (1, "num_2", ["willpower"], "flat", "none")],  # Ravage secondaire
    7077: [(0, "num_0", ["mp"], "flat", "none"), (1, "num_0", ["dmg_pct"], "flat", "none")],   # Armure lourde
    7076: [(0, "num_0", ["ap"], "flat", "none"), (1, "num_0", ["elem_res"], "flat", "none")],  # Carapace
    7075: [(0, "num_0", ["range"], "flat", "none"), (1, "num_0", ["lock", "dodge"], "pct_level", "none")],  # Combat rapproché
    7864: [(1, "num_0", ["dodge"], "pct_level", "none")],                   # Evasion
    7865: [(1, "num_0", ["lock"], "pct_level", "none")],                    # Interception
    8390: [(0, "num_0", ["block"], "flat", "none")],                        # Dérobade continue
    8391: [(0, "num_0", ["crit_res"], "flat", "none")],                     # Bouclier critique
    8393: [(0, "num_0", ["rear_res"], "flat", "none")],                     # Bouclier dorsal
    8518: [(0, "num_0", ["dmg_pct"], "flat", "element:fire")],              # Brûlure
    8519: [(0, "num_0", ["dmg_pct"], "flat", "element:water")],             # Gel
    8520: [(0, "num_0", ["dmg_pct"], "flat", "element:earth")],             # Tellurisme
    8521: [(0, "num_0", ["dmg_pct"], "flat", "element:air")],               # Ventilation
    5985: [(0, "num_0", ["dmg_pct"], "flat", "melee")],                     # Embuscade (cibles au contact)
    6036: [(0, "num_0", ["dmg_pct"], "flat", "distance")],                  # Longueur
    8388: [(0, "num_0", ["dmg_pct"], "flat", "distance")],                  # Acribie (5 cases et +)
    5983: [(1, "num_0", ["elem_mastery"], "pct_level", "hp_high")],         # Carnage
    7862: [(1, "num_0", ["crit_rate"], "flat", "hp_high")],                 # Influence vitale
    7722: [(1, "num_0", ["block"], "flat", "hp_high")],                     # Conservation
    7861: [(1, "num_0", ["ap"], "flat", "hp_high")],                        # Force vitale
    7860: [(1, "num_0", ["mp"], "flat", "hp_high")],                        # Agilité vitale
    6009: [(1, "num_0", ["crit_rate"], "flat", "berserk")],                 # Critique Berserk
    6024: [(1, "num_0", ["block"], "flat", "berserk")],                     # Parade Berserk
    7859: [(1, "num_0", ["dmg_pct"], "flat", "no_armor")],                  # Force légère
    6821: [(1, "num_0", ["elem_mastery"], "pct_level", "light_weapons")],   # Expert des armes légères
    6931: [(1, "num_0", ["dmg_pct"], "flat", "no_secondary")],              # Neutralité
    6933: [(1, "num_0", ["block"], "flat", "no_secondary")],                # Prétention
    7115: [(1, "num_0", ["crit_rate"], "flat", "no_secondary")],            # Ambition
    # --- épiques
    5158: [(1, "num_0", ["mp"], "flat", "two_handed"), (2, "num_0", ["ap"], "flat", "two_handed")],  # Maniement : Deux mains
    5444: [(0, "num_0", ["elem_res"], "flat", "none"), (0, "num_1", ["rear_res"], "flat", "none")],  # Science du placement
    # --- reliques
    7257: [(1, "num_0", ["range"], "flat", "distance"), (2, "num_0", ["dmg_pct"], "flat", "distance")],  # Sentinelle
    8380: [(0, "num_0", ["elem_res"], "flat", "no_armor")],                 # Aplomb naturel
    7870: [(1, "num_0", ["dmg_pct"], "flat", "no_armor")],                  # Pétillance
}

# Valeurs à forcer quand le texte WakForge n'a pas de nombre exploitable
CONST_FIXES: dict[tuple[int, int, str], list[int]] = {}


def render(text: str, data: dict[str, object]) -> str:
    """Remplace {num_k} par « v1/v2/... » (valeurs par niveau, dédoublonnées)."""
    for key, val in data.items():
        if not key.startswith("num_") or not isinstance(val, dict):
            continue
        vals = [val[f"level_{i}"] for i in range(1, 7) if f"level_{i}" in val]
        uniq = list(dict.fromkeys(vals))
        text = text.replace("{" + key + "}", "/".join(str(v) for v in uniq))
    text = re.sub(r"\{img_\w+\}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def main(wakforge: Path) -> None:
    fr = json.loads((wakforge / "src/plugins/i18n/statesTranslations/fr_states.json").read_text(encoding="utf-8"))
    states = {int(s["id"]): s for s in json.loads((wakforge / "src/models/state_data.json").read_text(encoding="utf-8"))}
    consts = (wakforge / "src/models/useConstants.js").read_text(encoding="utf-8")
    block = consts.split("STATE_LEVEL_LIMITS = {", 1)[1].split("};", 1)[0]
    limits = {int(k): int(v) for k, v in re.findall(r"(\d+):\s*(\d+)", block)}

    out: dict[int, dict[str, object]] = {}
    for sid, st in sorted(states.items()):
        lines = st.get("descriptionData", [])
        desc = " ; ".join(t for t in (render(fr.get(d.get("text", ""), "") or "", d) for d in lines) if t)
        entry: dict[str, object] = {"name": fr.get(f"{sid}_name") or fr.get(st.get("name", ""), ""), "desc": desc}
        if sid in limits:
            entry["limit"] = limits[sid]
        effects = []
        for line_idx, num, stats, mode, cond in CURATED.get(sid, []):
            d = lines[line_idx]
            raw_text = fr.get(d.get("text", ""), "") or ""
            sign = -1 if re.search(r"-\s*\{" + num + r"\}", raw_text) else 1
            fixed = CONST_FIXES.get((sid, line_idx, num))
            if fixed is not None:
                values, sign = fixed, 1
            else:
                nums = d.get(num)
                if not isinstance(nums, dict):
                    raise SystemExit(f"état {sid} ligne {line_idx} : pas de {num}")
                values = [int(nums[f"level_{i}"]) for i in range(1, 7) if f"level_{i}" in nums]
            for stat in stats:
                effects.append({"stat": stat, "values": [sign * v for v in values], "mode": mode, "condition": cond})
        if effects:
            entry["effects"] = effects
        out[sid] = entry
    missing = sorted(set(CURATED) - set(out))
    if missing:
        raise SystemExit(f"états modélisés absents de WakForge : {missing}")
    header = (
        "# Sublimations : description et effets des ÉTATS appliqués (clé = id d'état).\n"
        "# Fichier généré par tools/build_sublimations_yaml.py à partir de WakForge (MIT) :\n"
        "# descriptions FR par niveau et niveaux de cumul max (limit).\n"
        "# Les couleurs, niveaux et raretés des sublimations viennent de items.json (CDN).\n"
        "# 'effects' = effets pris en compte par le solveur (choisis à la main) :\n"
        "#   stat, values (par niveau d'état 1..N), mode (flat | pct_level = % du niveau),\n"
        "#   condition (none, melee, distance, berserk, hp_high, no_armor, two_handed,\n"
        "#   light_weapons, element:<élément>).\n"
        "# Après un patch : ajouter ici les nouveaux états (sinon : affichés, mais non optimisés).\n"
    )
    target = Path(__file__).resolve().parents[1] / "wakfu_optimizer/data/static/sublimations.yaml"
    target.write_text(header + yaml.safe_dump({"states": out}, allow_unicode=True, sort_keys=False, width=200, default_flow_style=None), encoding="utf-8")
    print(f"{len(out)} états, {sum(1 for e in out.values() if 'effects' in e)} modélisés -> {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
