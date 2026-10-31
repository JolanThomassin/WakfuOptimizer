"""Archétypes de jeu : ce que l'optimiseur doit privilégier pour un rôle (DPS distance, tank…).

Un archétype règle d'un coup les priorités (portée, maîtrises secondaires, résistance visée), les poids du calcul
(attaque / défense, Volonté, palier de critique), les contraintes de base (PA, PM) et le profil d'aptitudes
(lignes qui ont un sens pour ce rôle, et l'ordre dans lequel on remplit les points restants).

C'est la seule définition des archétypes : l'interface les reçoit par /api/meta, et les tests de qualité
(tests/test_build_quality.py) construisent leurs options avec `archetype_options`, exactement comme le site
quand les panneaux Priorités, Contraintes et Sublimations sont désactivés.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..data.models import GameData, Rarity
from .characteristics import BRANCH_FR, LINE_FR, branch_points, char_lines
from .options import OptimizeOptions, default_min_ap, default_min_mp
from .weights import apply_custom_weights


@dataclass(frozen=True)
class Archetype:
    key: str
    name: str
    desc: str
    role: str                         # dps | tank | heal | support
    range: str | None = None          # None : portée de la classe
    crit: bool = True
    rear: bool = False
    rear_share: int = 50
    berserk: bool = False
    heal: bool = False
    heal_share: int = 50              # % de l'attaque comptée en soins si « soin » (aussi coché à la main sur un DPS)
    res_target: int = 65             # % de résistance visé à haut niveau (plus bas avant : voir res_target)
    res_tol: int = 5
    res_free: bool = False            # la résistance compte encore au-delà de la cible (tank)
    offense: int = 85                 # poids de l'attaque (la défense prend le reste)
    will: int = 0                     # poids de la Volonté (retraits PA / PM)
    will_min: int = 0                 # Volonté minimum : malus en dessous (tank : retraits PA / PM subis)
    crit_floor: bool = False          # palier de critique selon le niveau (voir crit_target)
    crit_bonus: int = 0               # % de critique visé en plus du palier du niveau
    count_conditional: bool = True
    hide_range: bool = False          # la portée n'a pas de sens pour ce rôle (interface)
    hide_elements: bool = False       # les éléments joués n'ont pas de sens (dégâts ignorés) : pas de choix (interface)
    mins: dict[str, int] = field(default_factory=dict)   # minimums en plus de ceux du niveau (ap, mp, wp)
    mp_extra: int = 0                 # PM en plus du minimum du niveau (mêlée : on va au contact, 6 PM au niveau 200)
    min_range: int = 0                # PO minimum à distance (au plus 1 sous le niveau MIN_RANGE_LEVEL)
    utility: dict[str, tuple[float, int]] = field(default_factory=dict)   # PA/PM/PO/PW : (valeur, plafond), voir scoring.UTILITY
    # Tacle / Esquive : (valeur de « niveau » points, plafond en multiples du niveau) ; ces stats montent avec le
    # niveau, la valeur d'un point aussi (ex. (0.1, 4) au niveau 65 : jusqu'à 260 de Tacle, 0,1 % par 65 points)
    per_level: dict[str, tuple[float, float]] = field(default_factory=dict)
    # mêlée (DPS mêlée, dos, berserk) : Tacle (prioritaire) et un peu d'Esquive, moins que pour le tank
    focus: tuple[tuple[str, str], ...] = ()   # stats privilégiées (stat, libellé), affichées dans l'onglet Explication


ARCHETYPES: dict[str, Archetype] = {a.key: a for a in (
    Archetype("dps_melee", "DPS mêlée", "Dégâts au corps-à-corps : Maîtrise mêlée et critique, et de bonnes résistances "
              "(au contact, on encaisse).", "dps", range="melee", res_target=70, crit_floor=True, mp_extra=1,
              per_level={"lock": (0.02, 6), "dodge": (0.015, 6)},
              focus=(("melee_mastery", "Maîtrise mêlée"), ("crit_rate", "Critique"), ("ap", "PA"), ("elem_res", "Résistances"))),
    # attaque à 97 : une fois le plancher de résistance atteint (pénalité res_short), tout part dans les maîtrises.
    # Critique visé plus haut que les autres DPS ; PM moins utiles (on frappe de loin sans se déplacer beaucoup).
    Archetype("dps_distance", "DPS distance", "Dégâts à distance : assez de résistances pour le niveau, puis tout "
              "dans les maîtrises (distance, élémentaire), beaucoup de critique et un peu de portée ; les PM "
              "comptent moins (on joue de loin).", "dps", range="distance",
              offense=97, crit_floor=True, crit_bonus=10, min_range=2, utility={"mp": (0.012, 5)},
              focus=(("distance_mastery", "Maîtrise distance"), ("crit_rate", "Critique"), ("ap", "PA"), ("range", "Portée"))),
    Archetype("dps_mixed", "DPS mixte", "Frappe au contact comme à distance (Huppermage, Eliotrope…).",
              "dps", range="mixed", crit_floor=True,
              focus=(("elem_mastery", "Maîtrise élémentaire"), ("crit_rate", "Critique"), ("ap", "PA"))),
    Archetype("dps_rear", "DPS dos", "Coups dans le dos (Sram) : Maîtrise dos prioritaire, avec de bonnes résistances "
              "(au contact, on encaisse).", "dps", range="melee", rear=True, rear_share=80, res_target=70,
              offense=88, crit_floor=True, mp_extra=1, per_level={"lock": (0.02, 6), "dodge": (0.015, 6)},
              focus=(("rear_mastery", "Maîtrise dos"), ("melee_mastery", "Maîtrise mêlée"), ("crit_rate", "Critique"),
                     ("elem_res", "Résistances"))),
    Archetype("berserk", "Berserk", "Joue à bas PV (Sacrieur) : Maîtrise berserk, résistances un peu plus basses.",
              "dps", range="melee", berserk=True, res_target=60, offense=88, crit_floor=True, mp_extra=1,
              count_conditional=False, per_level={"lock": (0.02, 6), "dodge": (0.015, 6)}, focus=(("berserk_mastery", "Maîtrise berserk"), ("melee_mastery", "Maîtrise mêlée"),
                                              ("crit_rate", "Critique"), ("hp", "PV"))),
    Archetype("tank", "Tank", "Survie d'abord : résistances (même au-delà de la cible), PV, parade, Tacle et "
              "Esquive, PM (jusqu'à 7), un peu de Portée, résistances critique et dos (jamais négatives), Volonté d'au moins 10 ; dégâts ignorés. "
              "Aptitudes : Force en PV, Chance en parade et résistances.",
              "tank", range="melee", hide_range=True, hide_elements=True, crit=False, res_target=70, res_tol=4, res_free=True,
              # PA : plus que pour les autres (8 points chacun) ; PM : se placer, porter (jusqu'à 7) ;
              # Portée : jusqu'à 3, chaque point moins que le précédent (DECAYING) ;
              # résistances critique et dos : 0,1 et 0,15 point de score par point (dos : on se fait contourner),
              # malus sous 0 (scoring.SEC_RES_NEG_PENALTY) ; Volonté : malus sous 10 (retraits subis)
              offense=0, will_min=10,
              utility={"ap": (0.08, 14), "mp": (0.05, 7), "range": (0.03, 3), "crit_res": (0.001, 100), "rear_res": (0.0015, 150)},
              per_level={"lock": (0.05, 9),           # Tacle : retenir les ennemis au contact (≈ 2 200 au niveau 245)
                         "dodge": (0.04, 9)},          # Esquive : se dégager, un peu moins que le Tacle
              focus=(("hp", "PV"), ("lock", "Tacle"), ("mp", "PM"), ("elem_res", "Résistances"), ("block", "Parade"))),
    Archetype("heal", "Soigneur", "Soins : Maîtrise soin et critique, bonne survie.",
              "heal", heal=True, heal_share=100, offense=80, crit_floor=True, min_range=1,
              focus=(("heal_mastery", "Maîtrise soin"), ("crit_rate", "Critique"), ("ap", "PA"), ("elem_res", "Résistances"))),
    # Moitié dégâts, moitié soins (scoring.ln_offense) : maîtrises élémentaire, de portée et critique servent aux deux,
    # Maîtrise soin et % Soins réalisés aux soins, % Dommages infligés aux dégâts.
    Archetype("dps_heal", "DPS soigneur", "Dégâts et soins à parts égales (Ecaflip, Eniripsa…) : les maîtrises "
              "élémentaire, de portée et critique servent aux deux ; la Maîtrise soin et le % Soins réalisés aux soins "
              "seulement, le % Dommages infligés aux dégâts seulement.", "heal", heal=True, heal_share=50,
              crit_floor=True, min_range=1,
              focus=(("heal_mastery", "Maîtrise soin"), ("crit_mastery", "Maîtrise critique"), ("crit_rate", "Critique"),
                     ("ap", "PA"))),
    Archetype("support_buff", "Support buff", "Boosts / placement : PA, PM, PW et survie avant les dégâts. "
              "(Armure donnée non chiffrée.)", "support", crit=False, res_target=67, offense=60,
              mins={"ap": 11, "mp": 5, "wp": 8}, utility={"mp": (0.04, 6), "wp": (0.015, 14)},
              focus=(("ap", "PA"), ("mp", "PM"), ("wp", "PW"), ("elem_res", "Résistances"))),
    # Soins et boosts portés sur les alliés, au contact comme à distance : la maîtrise mêlée (cible à 2 cases au
    # plus) ou distance ne s'applique qu'à une partie des soins, d'où la portée « mixte » (moitié de chaque).
    # PA d'abord (plus de sorts de soin et de boost par tour), puis la puissance des soins (poids 45 seulement).
    Archetype("support_heal", "Support soin", "Soigneur et booster (Zobal…) : PA avant tout (plus de soins et de "
              "boosts par tour), PM, PW et survie, puis Maîtrise soin et élémentaire ; les maîtrises mêlée et "
              "distance ne comptent qu'à moitié (on soigne à toutes les distances).", "support", heal=True, heal_share=100,
              range="mixed", hide_range=True, res_target=67, offense=45, mins={"ap": 11, "mp": 5},
              utility={"ap": (0.1, 14), "mp": (0.04, 6), "wp": (0.015, 14)},
              focus=(("ap", "PA"), ("heal_mastery", "Maîtrise soin"), ("mp", "PM"), ("wp", "PW"), ("elem_res", "Résistances"))),
    Archetype("support_debuff", "Support débuff", "Retraits PA / PM : la Volonté compte beaucoup (+1 % de retrait "
              "par point, jusqu'à 100), puis PA, PM et survie.", "support", crit=False, res_target=67,
              offense=55, will=45, mins={"ap": 11, "mp": 5},
              focus=(("willpower", "Volonté"), ("ap", "PA"), ("mp", "PM"), ("elem_res", "Résistances"))),
)}

# Champs de OptimizeOptions réglés par chaque panneau de l'interface (désactivé = valeur de l'archétype)
PRIORITY_FIELDS = ("range", "crit", "rear", "rear_share", "berserk", "heal", "res_target", "res_tol")
CONSTRAINT_FIELDS = ("min_ap", "min_mp", "min_range", "min_wp", "min_crit", "min_block", "max_ap", "max_mp",
                     "max_range", "max_wp", "max_crit", "max_block", "allowed_rarities", "lower_brackets",
                     "exclude_relic", "exclude_epic", "exclude_shop", "include_pet_mount")
SUB_FIELDS = ("shard_mode", "shard_count", "max_jokers", "no_subs", "confirmed_subs_only", "count_conditional")
# Toujours ceux de l'archétype (pas réglables dans l'interface)
WEIGHT_FIELDS = ("offense_weight", "heal_share", "res_free", "willpower_weight", "will_min", "crit_target", "utility")
PANELS = {"priorities": PRIORITY_FIELDS, "constraints": CONSTRAINT_FIELDS, "subs": SUB_FIELDS}


def crit_target(level: int, bonus: int = 0) -> int:
    """% de critique visé par un DPS : ce que les joueurs atteignent à ce niveau (10 % au niveau 45, 31 % au 140,
    50 % à partir du 225), plus le bonus de l'archétype (DPS distance). En dessous, chaque % manquant coûte au
    score (voir scoring.CRIT_SHORT_PENALTY)."""
    return min(50, max(10, round(level * 2 / 9))) + bonus


# Résistance visée selon le niveau : les dégâts reçus montent avec le niveau, la résistance attendue aussi.
# Cible de l'archétype atteinte au niveau RES_FULL_LEVEL, RES_PER_LEVEL % de moins par niveau en dessous
# (DPS distance : 60 % ± 5 au niveau 140, soit au moins 55 % partout ; 65 % ± 5 à partir du 160).
RES_FULL_LEVEL = 160
RES_PER_LEVEL = 0.2
RES_MIN_TARGET = 25


def res_target(arch: Archetype, level: int) -> int:
    """% de résistance visé par l'archétype à ce niveau (le plancher est res_tol en dessous). Le tank vise sa
    cible à tout niveau (s'il ne l'atteint pas, le solveur l'abaisse au maximum possible)."""
    if arch.res_free or level >= RES_FULL_LEVEL:
        return arch.res_target
    lower = round(arch.res_target - (RES_FULL_LEVEL - level) * RES_PER_LEVEL)
    return min(arch.res_target, max(RES_MIN_TARGET, lower))


# PO minimum des archétypes à distance (min_range) : complète à partir de ce niveau, 1 PO au plus en dessous
MIN_RANGE_LEVEL = 100


def min_range(arch: Archetype, rng: str, level: int) -> int:
    """PO minimum : rien au contact ; à distance, celle de l'archétype (1 au plus sous MIN_RANGE_LEVEL)."""
    if rng == "melee" or not arch.min_range:
        return 0
    return arch.min_range if level >= MIN_RANGE_LEVEL else min(1, arch.min_range)


def class_archetypes(data: GameData, class_key: str) -> list[str]:
    """Archétypes habituels de la classe (game.yaml), le plus joué en premier."""
    spec = data.game.get("classes", {}).get(class_key, {})  # type: ignore[union-attr]
    keys = [k for k in (spec.get("archetypes") or []) if k in ARCHETYPES]
    return keys or ["dps_melee"]


def default_archetype(data: GameData, class_key: str) -> str:
    return class_archetypes(data, class_key)[0]


def archetype_values(arch: Archetype, class_range: str, level: int) -> dict[str, Any]:
    """Valeurs des champs de PANELS et WEIGHT_FIELDS pour un archétype (panneaux désactivés)."""
    base = OptimizeOptions()
    rng = "best" if class_range == "best" else arch.range or class_range or "melee"
    return {
        # priorités
        "range": rng, "crit": arch.crit, "rear": arch.rear, "rear_share": arch.rear_share, "berserk": arch.berserk,
        "heal": arch.heal, "res_target": res_target(arch, level), "res_tol": arch.res_tol,
        "count_conditional": arch.count_conditional,
        # poids
        "offense_weight": arch.offense, "heal_share": arch.heal_share, "res_free": arch.res_free, "willpower_weight": arch.will,
        "will_min": arch.will_min,
        "crit_target": crit_target(level, arch.crit_bonus) if arch.crit_floor and arch.crit else 0,
        "utility": {**{k: [v, cap] for k, (v, cap) in arch.utility.items()},
                    **{k: [v / max(1, level), round(cap * level)] for k, (v, cap) in arch.per_level.items()}},
        # contraintes
        "min_ap": max(default_min_ap(level), arch.mins.get("ap", 0)),
        "min_mp": max(default_min_mp(level) + arch.mp_extra, arch.mins.get("mp", 0)),
        "min_wp": arch.mins.get("wp", 0), "min_range": min_range(arch, rng, level), "min_crit": 0, "min_block": 0,
        "max_ap": 0, "max_mp": 0, "max_range": 0, "max_wp": 0, "max_crit": 0, "max_block": 0,
        "allowed_rarities": tuple(int(r) for r in Rarity), "lower_brackets": False, "exclude_relic": False,
        "exclude_epic": False, "exclude_shop": True, "include_pet_mount": True,
        # châsses et sublimations
        "shard_mode": "ideal", "shard_count": 4, "max_jokers": base.max_jokers,
        "no_subs": True,   # panneau désactivé : aucune sublimation (sauf celles imposées dans l'onglet Sublimations)
        "confirmed_subs_only": False,
    }


def apply_archetype(opts: OptimizeOptions, data: GameData, panels_off: tuple[str, ...] = tuple(PANELS)) -> OptimizeOptions:
    """Remet les champs des panneaux désactivés (et toujours les poids) aux valeurs de l'archétype."""
    if opts.archetype not in ARCHETYPES:
        opts.archetype = default_archetype(data, opts.class_key)
    cls = data.classes.get(opts.class_key)
    vals = archetype_values(ARCHETYPES[opts.archetype], cls.range if cls else "melee", opts.level)
    fields = list(WEIGHT_FIELDS) + [f for p in panels_off for f in PANELS.get(p, ())]
    for f in fields:
        setattr(opts, f, vals[f])
    if not opts.crit:
        opts.crit_target = 0
    apply_custom_weights(opts)   # poids modifiés dans l'onglet Poids
    if cls and cls.range == "best":   # Roublard : la meilleure maîtrise compte, quelle que soit la portée choisie
        opts.range = "best"
    return opts


def archetype_options(data: GameData, class_key: str, level: int, archetype: str | None = None,
                      **overrides: Any) -> OptimizeOptions:
    """Options d'un calcul fait avec le seul panneau Personnage (classe, niveau, archétype) : ce que le site
    envoie quand les autres panneaux sont désactivés. Base des tests de qualité."""
    cls = data.classes[class_key]
    o = OptimizeOptions(class_key=class_key, level=level, elements=tuple(cls.elements),
                        archetype=archetype or default_archetype(data, class_key))
    apply_archetype(o, data)
    for k, v in overrides.items():
        setattr(o, k, v)
    return o


# =====================================================================  profil d'aptitudes
def apt_profile(opts: OptimizeOptions) -> dict[str, list[str]]:
    """Lignes d'aptitudes qui ont un sens pour ces réglages, par branche, dans l'ordre où les joueurs les remplissent.
    Le solveur ne place des points que dans ces lignes ; les points sans effet sur le score suivent cet ordre.
    Dérivé des options (et non du seul archétype) : cocher Critique dans les priorités ouvre la ligne % Critique."""
    arch = ARCHETYPES.get(opts.archetype)
    tank = arch is not None and arch.role == "tank"
    support = arch is not None and arch.role == "support"
    rng = opts.range
    range_lines = {"melee": ["melee_mastery"], "distance": ["distance_mastery"]}.get(rng, ["melee_mastery", "distance_mastery"])
    dodge_line = {"melee": "lock", "distance": "dodge"}.get(rng, "lock_dodge")

    strength = ["hp"] if tank else range_lines + ["elem_mastery", "hp"]
    agility = ["lock", "willpower"] if tank else [dodge_line, "willpower"]
    if (opts.utility.get("dodge") or (0, 0))[0] and "dodge" not in agility:   # Esquive comptée : sa ligne, après la première
        agility.insert(1, "dodge")
    if opts.willpower_weight >= 20:   # retraits PA / PM : Volonté au maximum d'abord
        agility = ["willpower"] + [x for x in agility if x != "willpower"]

    fortune: list[str] = []
    if opts.crit:
        fortune.append("crit_rate")
    if opts.rear and not opts.heal:
        fortune.append("rear_mastery")
    if opts.berserk:
        fortune.append("berserk_mastery")
    if opts.heal:
        fortune.append("heal_mastery")
    if tank or support:
        fortune += ["block", "crit_res", "rear_res"]
    if opts.crit or not fortune or tank or support:
        fortune.append("crit_mastery")   # ligne sans plafond : reçoit le reste
    fortune = list(dict.fromkeys(fortune))

    major = ["ap", "mp"]
    if opts.heal:
        major.append("heal_pct")
    if tank:
        major.append("elem_res")
    if support:
        major.append("wp")
    major += ["dmg_pct"] + (["range"] if rng != "melee" else []) + ["wp", "range", "elem_res"]
    major = list(dict.fromkeys(major))

    return {"intelligence": ["elem_res", "hp_pct"], "strength": strength, "agility": agility,
            "fortune": fortune, "major": major}


def apt_forced(opts: OptimizeOptions) -> set[str]:
    """Lignes mises au maximum d'office (mode auto), comme le font les joueurs quel que soit le calcul : Résistance
    élémentaire (si cochée), PA en Majeur, % Critique pour un archétype à palier de critique, Parade et résistances
    critique / dos pour un tank (sinon, sans effet sur le score, ses points de Chance peuvent finir en Maîtrise
    critique), Volonté pour un débuff."""
    arch = ARCHETYPES.get(opts.archetype)
    out = {"major.ap"}
    if opts.apt_elem_res:
        out.add("intelligence.elem_res")
    if opts.crit and opts.crit_target:
        out.add("fortune.crit_rate")
    if arch is not None and arch.role == "tank":
        out |= {"fortune.block", "fortune.crit_res", "fortune.rear_res"}
    if opts.willpower_weight >= 20:
        out.add("agility.willpower")
    return out & profile_keys(opts)


def profile_keys(opts: OptimizeOptions) -> set[str]:
    return {f"{b}.{line}" for b, lines in apt_profile(opts).items() for line in lines}


def profile_points(opts: OptimizeOptions, game: dict[str, Any]) -> dict[str, int]:
    """Répartition « rapide » d'un profil : chaque ligne remplie à son maximum, dans l'ordre."""
    maxes = {cl.key: cl.max_points for cl in char_lines(game)}
    out: dict[str, int] = {}
    for branch, lines in apt_profile(opts).items():
        left = branch_points(branch, opts.level, game)
        for line in lines:
            key = f"{branch}.{line}"
            if key not in maxes or left <= 0:
                continue
            n = left if maxes[key] is None else min(left, maxes[key])  # type: ignore[type-var]
            if n > 0:
                out[key] = n
                left -= n
    return out


def profile_desc(opts: OptimizeOptions) -> str:
    """Le profil d'aptitudes en clair : « Force : Maîtrise Distance, puis Maîtrise Élémentaire… »."""
    parts = []
    for branch, lines in apt_profile(opts).items():
        parts.append(f"{BRANCH_FR.get(branch, branch)} : " + ", puis ".join(LINE_FR.get(x, x) for x in lines))
    return " ; ".join(parts) + "."


def preset(data: GameData, archetype: str, class_key: str, level: int) -> dict[str, int]:
    """Aptitudes rapides d'un archétype (onglet Aptitudes) : son profil rempli dans l'ordre."""
    return profile_points(archetype_options(data, class_key, level, archetype), data.game)


def meta_archetypes(levels: list[int]) -> list[dict[str, Any]]:
    """Archétypes pour l'interface (ordre d'affichage). `res_by_level` : résistance visée à chaque niveau proposé."""
    return [{"key": a.key, "name": a.name, "desc": a.desc, "role": a.role, "range": a.range, "crit": a.crit,
             "rear": a.rear, "rear_share": a.rear_share, "berserk": a.berserk, "heal": a.heal, "heal_share": a.heal_share,
             "res": [a.res_target, a.res_tol], "res_by_level": {lv: res_target(a, lv) for lv in levels}, "offense": a.offense, "will": a.will, "res_free": a.res_free,
             "crit_floor": a.crit_floor, "hide_range": a.hide_range,
             "hide_elements": a.hide_elements, "mins": dict(a.mins), "mp_extra": a.mp_extra, "min_range": a.min_range,
             "count_conditional": a.count_conditional} for a in ARCHETYPES.values()]
