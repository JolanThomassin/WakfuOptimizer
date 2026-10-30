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
#                no_secondary (maîtrises secondaires <= 0 : imposé par le solveur s'il place la sublimation)
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
    7257: [(1, "num_0", ["range"], "flat", "none"), (2, "num_0", ["dmg_pct"], "flat", "distance")],  # Sentinelle (PO toujours)
    8380: [(0, "num_0", ["elem_res"], "flat", "no_armor")],                 # Aplomb naturel
    7870: [(1, "num_0", ["dmg_pct"], "flat", "no_armor")],                  # Pétillance
}

# Effets à valeur fixe, conditionnés à une stat (épiques « au lancement du combat ») : ajoutés tels quels.
STAT_CONDITIONAL: dict[int, list[tuple[str, int, str]]] = {
    5073: [("dmg_pct", 15, "stat_le:ap:10"), ("willpower", 10, "stat_le:ap:10")],          # Inflexible
    5074: [("dmg_pct", 20, "stat_le:crit_rate:10"), ("crit_res", 50, "stat_le:crit_rate:10")],  # Constant
    5075: [("crit_rate", 10, "stat_ge:block:40")],                                         # Mesure
    5370: [("willpower", 10, "stat_ge:wp:8"), ("block", 15, "stat_ge:wp:8")],              # Pacte Wakfu
    6707: [("hp_pct", 30, "stat_ge:block:50")],                                            # Pilier
    # Dénouement : conversion de la Maîtrise Critique (model._crit_conversion) ; >= 40 % critique et, choix du
    # projet, maîtrises secondaires <= 0
    5077: [("crit_to_elem", 100, "stat_ge:crit_rate:40&no_secondary")],
}

# Sublimations confirmées (description, niveaux, effets et contraintes vérifiés avec l'utilisateur) : les autres
# sont grisées dans l'interface.
CONFIRMED = {5077, 7115, 6026, 7861, 7722}   # Dénouement, Ambition, Influence, Force vitale, Conservation

# Valeurs officielles par niveau (encyclopédie Ankama, /fr/linker/state?id=X&level=k), vérifiées en jeu
# (Visibilité I : -300 Tacle, II : -150). L'encyclopédie affiche le niveau k-1 et s'arrête au niveau max - 1 :
# le dernier niveau est donc prolongé avec le même pas (-450, -300, -150). WakForge a le même défaut.
# id d'état -> (niveau max, valeurs par niveau de chaque effet, dans l'ordre des effets) ; remplace les valeurs WakForge.
OFFICIAL_LEVELS: dict[int, tuple[int, list[list[int]]]] = {
    5073: (1, [[15], [10]]),  # Inflexible
    5074: (1, [[20], [50]]),  # Constant
    5075: (1, [[10]]),  # Mesure
    5158: (1, [[-2], [2]]),  # Maniement : Deux mains
    5370: (1, [[10], [15]]),  # Pacte Wakfu
    5444: (1, [[50], [-200]]),  # Science du placement
    5981: (3, [[1, 1, 1], [-30, -20, -10]]),  # Dévastation
    5982: (4, [[5, 10, 15, 20], [3, 6, 9, 12]]),  # Ravage
    5983: (6, [[15, 30, 45, 60, 75, 90]]),  # Carnage
    5984: (6, [[5, 10, 15, 20, 25, 30]]),  # Cicatrisation
    5985: (6, [[2, 4, 6, 8, 10, 12]]),  # Embuscade
    6000: (2, [[50, 100], [-50, -50]]),  # Théorie de la matière
    6005: (2, [[1, 1], [-20, -10]]),  # Vélocité
    6008: (2, [[1, 1], [-150, -75]]),  # Vivacité
    6009: (6, [[5, 10, 15, 20, 25, 30]]),  # Critique Berserk
    6010: (2, [[1, 1], [-300, -150], [-300, -150]]),  # Visibilité
    6013: (6, [[1, 3, 4, 6, 7, 9], [1, 3, 4, 6, 7, 9], [1, 3, 4, 6, 7, 9]]),  # Ravage secondaire
    6024: (6, [[5, 10, 15, 20, 25, 30]]),  # Parade Berserk
    6026: (6, [[3, 6, 9, 12, 15, 18]]),  # Influence
    6036: (6, [[2, 4, 6, 8, 10, 12]]),  # Longueur
    6707: (1, [[30]]),  # Pilier
    6821: (6, [[25, 50, 75, 100, 125, 150]]),  # Expert des armes légères
    6931: (4, [[8, 16, 24, 32]]),  # Neutralité
    6933: (6, [[5, 10, 15, 20, 25, 30]]),  # Prétention
    7075: (2, [[-1, -1], [50, 100], [50, 100]]),  # Combat rapproché
    7076: (2, [[-2, -1], [75, 75]]),  # Carapace
    7077: (2, [[-1, -1], [5, 10]]),  # Armure lourde
    7115: (6, [[5, 10, 15, 20, 25, 30]]),  # Ambition
    7257: (1, [[3], [15]]),  # Sentinelle
    7722: (4, [[10, 20, 30, 40]]),  # Conservation
    7859: (6, [[3, 6, 9, 12, 15, 18]]),  # Force légère
    7860: (2, [[1, 1]]),  # Agilité vitale
    7861: (2, [[1, 1]]),  # Force vitale
    7862: (6, [[4, 8, 12, 16, 20, 24]]),  # Influence vitale
    7864: (6, [[50, 100, 150, 200, 250, 300]]),  # Evasion
    7865: (6, [[50, 100, 150, 200, 250, 300]]),  # Interception
    7870: (1, [[20]]),  # Pétillance
    8380: (0, [[50, 50, 50, 50, 50]]),  # Aplomb naturel
    8388: (6, [[2, 4, 6, 8, 10, 12]]),  # Acribie
    8390: (6, [[3, 6, 9, 12, 15, 18]]),  # Dérobade continue
    8391: (6, [[5, 10, 15, 20, 25, 30]]),  # Bouclier critique
    8393: (6, [[5, 10, 15, 20, 25, 30]]),  # Bouclier dorsal
    8518: (4, [[4, 8, 12, 16]]),  # Brûlure
    8519: (4, [[4, 8, 12, 16]]),  # Gel
    8520: (4, [[4, 8, 12, 16]]),  # Tellurisme
    8521: (4, [[4, 8, 12, 16]]),  # Ventilation
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
        for stat, v, cond in STAT_CONDITIONAL.get(sid, []):
            effects.append({"stat": stat, "values": [v] * 5, "mode": "flat", "condition": cond})
        if sid in OFFICIAL_LEVELS:
            lim, vals = OFFICIAL_LEVELS[sid]
            for eff, v in zip(effects, vals):
                eff["values"] = v
            if lim:
                entry["limit"] = lim
        if sid in CONFIRMED:
            entry["confirmed"] = True
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
