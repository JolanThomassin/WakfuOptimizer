"""Team Builder : compléter une équipe de 3 ou 6 personnages autour de ceux que le joueur a choisis.

Le joueur donne un ou plusieurs personnages (classe + archétype, ou archétype « auto » : le meilleur de la classe pour
l'équipe) ; on cherche les membres manquants parmi les archétypes habituels de chaque classe (game.yaml, `archetypes`).

Score d'une équipe (en points, plus haut = mieux) :
- rôles : chaque archétype couvre un ou plusieurs rôles (TEAM_ROLES, ex. Soigneur tank = 0,8 soin + 0,5 tank) ; chaque
  rôle rapporte selon le nombre de membres qui le couvrent, avec des rendements décroissants (ROLE_VALUES : le premier
  soigneur compte beaucoup, le deuxième peu, un troisième tank coûte) ;
- apports d'équipe : ce que la classe (game.yaml, `team`) ou l'archétype apporte (placement, retrait PA…), le premier
  compte plein, le second à moitié ;
- éléments : éléments différents frappés par les membres qui font des dégâts (contre les résistances des ennemis) ;
- portée : au moins un membre au contact et un à distance ;
- classe : un archétype habituel de la classe (le plus joué d'abord) plutôt qu'un archétype rare.

Recherche : faisceau (beam search) membre par membre, puis les meilleures équipes différentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..data.models import ELEMENTS, GameData
from .archetypes import ARCHETYPES, class_archetypes

ROLES = ("tank", "heal", "support", "dps")
EL_FR = {"fire": "Feu", "water": "Eau", "earth": "Terre", "air": "Air"}
ROLE_FR = {"tank": "Tank", "heal": "Soigneur", "support": "Support", "dps": "DPS"}

# Part de chaque rôle couverte par un archétype (défaut : 1 dans le rôle de l'archétype)
TEAM_ROLES: dict[str, dict[str, float]] = {
    "berserk": {"dps": 1.0, "tank": 0.2},
    "heal_tank": {"heal": 0.8, "tank": 0.5},
    "dps_heal": {"dps": 0.55, "heal": 0.6},
    "support_heal": {"support": 0.6, "heal": 0.6},
}

# Valeur du 1er, 2e, 3e… membre de chaque rôle, par taille d'équipe et style (au-delà : dernière valeur)
ROLE_VALUES: dict[int, dict[str, dict[str, list[float]]]] = {
    3: {
        "balanced": {"tank": [10, -4], "heal": [12, -2], "support": [4, -2], "dps": [9, 6, 1]},
        "offense": {"tank": [5, -5], "heal": [11, -3], "support": [3, -2], "dps": [10, 9, 6]},
        "defense": {"tank": [12, 1], "heal": [13, 2], "support": [5, -1], "dps": [8, 3, -1]},
    },
    6: {
        "balanced": {"tank": [10, 2, -4], "heal": [12, 4, -3], "support": [7, 2, -2], "dps": [9, 8, 6, 3, 0]},
        "offense": {"tank": [7, -2], "heal": [11, 2, -3], "support": [6, 1, -2], "dps": [10, 9, 8, 6, 3]},
        "defense": {"tank": [12, 5, -2], "heal": [13, 6, -1], "support": [8, 3, -1], "dps": [8, 6, 3, 0]},
    },
}
STYLES = ("balanced", "offense", "defense")

# Apports d'équipe : (libellé, valeur du premier ; le second vaut la moitié, les suivants rien)
TRAITS: dict[str, tuple[str, float]] = {
    "placement": ("Placement", 3.0),
    "ap_removal": ("Retrait PA", 2.5),
    "mp_removal": ("Retrait PM", 2.0),
    "armor": ("Armure", 2.5),
    "boost": ("Boosts", 2.5),
    "heal": ("Soins d'appoint", 1.5),
    "protect": ("Protection", 1.5),
    "revive": ("Résurrection", 1.0),
}
# Apports d'un archétype, en plus de ceux de la classe
ARCH_TRAITS: dict[str, tuple[str, ...]] = {
    "support_debuff": ("ap_removal", "mp_removal"),
    "support_buff": ("boost",),
    "support_heal": ("boost", "heal"),
    "tank": ("protect",),
    "heal_tank": ("protect",),
}
ELEMENT_VALUE = 1.5          # par élément différent frappé par l'équipe
RANGE_MIX_VALUE = 2.0        # au moins un membre au contact et un à distance (équipe de 6 : un peu plus)
CLASS_RANK_BONUS = (2.5, 1.5, 0.8, 0.5)   # archétype habituel de la classe, le plus joué d'abord
CLASS_ROLE_BONUS = 1.5       # archétype dans le rôle principal de la classe (game.yaml, `role`)
CLASS_TRAITS_OFF_ROLE = 0.5  # part des apports de la classe avec un archétype qu'elle joue peu (3e et suivants)
RARE_ARCH_PENALTY = 3.0      # archétype que la classe ne joue pas d'habitude (seulement s'il est imposé)
DUPLICATE_CLASS_PENALTY = 6.0
BEAM = 250


@dataclass(frozen=True)
class Member:
    class_key: str
    archetype: str
    fixed: bool = False          # choisi par le joueur (classe et archétype)
    chosen_class: bool = False   # classe choisie par le joueur (archétype « auto » ou imposé)


def _roles(arch: str) -> dict[str, float]:
    a = ARCHETYPES[arch]
    return TEAM_ROLES.get(arch, {a.role: 1.0})


class TeamScorer:
    def __init__(self, data: GameData, size: int, style: str):
        self.data = data
        self.size = size
        self.values = ROLE_VALUES[6 if size > 3 else 3][style if style in STYLES else "balanced"]
        self.spec: dict[str, Any] = data.game.get("classes") or {}  # type: ignore[assignment]

    def class_traits(self, cls: str) -> tuple[str, ...]:
        return tuple(t for t in (self.spec.get(cls, {}).get("team") or []) if t in TRAITS)

    def trait_weights(self, m: Member) -> dict[str, float]:
        """Apports du membre et leur part : ceux de la classe comptent à moitié si l'archétype est peu joué par la classe
        (un Zobal tank place moins ses alliés qu'un Zobal support)."""
        usual = class_archetypes(self.data, m.class_key)
        w = 1.0 if m.archetype in usual[:2] else CLASS_TRAITS_OFF_ROLE
        out = {t: w for t in self.class_traits(m.class_key)}
        out.update({t: 1.0 for t in ARCH_TRAITS.get(m.archetype, ())})
        return out

    def traits(self, m: Member) -> set[str]:
        return set(self.trait_weights(m))

    def melee(self, m: Member) -> tuple[bool, bool]:
        """(au contact, à distance) pour ce membre."""
        a = ARCHETYPES[m.archetype]
        cls = self.data.classes.get(m.class_key)
        rng = a.range or (cls.range if cls else "melee")
        if a.role == "tank":
            return True, False
        return rng in ("melee", "mixed", "best"), rng in ("distance", "mixed", "best", "none")

    def role_cover(self, team: list[Member]) -> dict[str, float]:
        cover = {r: 0.0 for r in ROLES}
        for m in team:
            for r, x in _roles(m.archetype).items():
                cover[r] += x
        return cover

    def role_points(self, cover: dict[str, float]) -> float:
        total = 0.0
        for r, x in cover.items():
            vals = self.values[r]
            i = 0
            while x > 1e-9:
                part = min(1.0, x)
                total += part * vals[min(i, len(vals) - 1)]
                x -= part
                i += 1
        return total

    def elements(self, team: list[Member]) -> set[str]:
        out: set[str] = set()
        for m in team:
            a = ARCHETYPES[m.archetype]
            if a.hide_elements or a.offense <= 0:
                continue
            cls = self.data.classes.get(m.class_key)
            out |= set(cls.elements if cls else ())
        return out

    def class_points(self, m: Member) -> float:
        usual = class_archetypes(self.data, m.class_key)
        if m.archetype in usual:
            i = usual.index(m.archetype)
            cls = self.data.classes.get(m.class_key)
            main = CLASS_ROLE_BONUS if cls and cls.role == ARCHETYPES[m.archetype].role else 0.0
            return CLASS_RANK_BONUS[min(i, len(CLASS_RANK_BONUS) - 1)] + main
        return -RARE_ARCH_PENALTY

    def parts(self, team: list[Member]) -> dict[str, float]:
        weights: dict[str, list[float]] = {}
        for m in team:
            for t, w in self.trait_weights(m).items():
                weights.setdefault(t, []).append(w)
        traits = 0.0
        for t, ws in weights.items():   # le premier plein, le second à moitié, les suivants rien
            ws.sort(reverse=True)
            traits += TRAITS[t][1] * (ws[0] + 0.5 * (ws[1] if len(ws) > 1 else 0.0))
        melee = any(self.melee(m)[0] for m in team)
        dist = any(self.melee(m)[1] for m in team)
        classes = [m.class_key for m in team]
        dup = len(classes) - len(set(classes))
        return {
            "roles": self.role_points(self.role_cover(team)),
            "traits": traits,
            "elements": ELEMENT_VALUE * len(self.elements(team)),
            "range": (RANGE_MIX_VALUE * (1.5 if self.size > 3 else 1.0)) if melee and dist else 0.0,
            "classes": sum(self.class_points(m) for m in team),
            "duplicates": -DUPLICATE_CLASS_PENALTY * dup,
        }

    def score(self, team: list[Member]) -> float:
        return sum(self.parts(team).values())


def _options(data: GameData, cls: str) -> list[str]:
    return [a for a in class_archetypes(data, cls) if a in ARCHETYPES]


def compose(data: GameData, picks: list[dict[str, Any]], size: int = 6, style: str = "balanced",
            alternatives: int = 3, allow_duplicates: bool = False) -> list[list[Member]]:
    """Meilleures équipes de `size` membres contenant les personnages choisis.
    `picks` : [{"class": "iop", "archetype": "dps_melee" | "auto"}…] (au plus `size`)."""
    size = 6 if size > 3 else 3
    scorer = TeamScorer(data, size, style)
    fixed: list[Member] = []
    slots: list[list[Member]] = []   # domaines des places à remplir, dans l'ordre
    for p in picks[:size]:
        cls = p.get("class")
        if cls not in data.classes:
            continue
        arch = p.get("archetype") or "auto"
        if arch in ARCHETYPES:
            fixed.append(Member(cls, arch, fixed=True, chosen_class=True))
        else:
            slots.append([Member(cls, a, chosen_class=True) for a in _options(data, cls)])
    free = size - len(fixed) - len(slots)
    chosen = {m.class_key for m in fixed} | {d[0].class_key for d in slots if d}
    pool = [Member(c, a) for c in sorted(data.classes) for a in _options(data, c)
            if allow_duplicates or c not in chosen]
    slots += [pool] * free

    beam: list[tuple[float, tuple[Member, ...]]] = [(scorer.score(fixed), ())]
    for domain in slots:
        nxt: dict[frozenset[Member], tuple[float, tuple[Member, ...]]] = {}
        for _, added in beam:
            used = {m.class_key for m in added}
            for m in domain:
                if not m.chosen_class and not allow_duplicates and m.class_key in used:
                    continue
                team = added + (m,)
                key = frozenset(team)
                if key in nxt:
                    continue
                nxt[key] = (scorer.score(fixed + list(team)), team)
        beam = sorted(nxt.values(), key=lambda x: -x[0])[:BEAM]
        if not beam:
            break

    # alternatives : assez de classes proposées différentes de chaque équipe déjà retenue (2 en équipe de 6, 1 en
    # équipe de 3) ; s'il n'y en a pas assez dans le faisceau, on se contente d'une classe différente
    teams = [fixed + list(added) for _, added in beam]
    proposed = [{m.class_key for m in tm if not m.chosen_class} for tm in teams]
    out: list[list[Member]] = []
    seen: list[set[str]] = []
    for need in ((2, 1) if size > 3 else (1,)):
        for cand, classes in zip(teams, proposed):
            if len(out) >= max(1, alternatives):
                return out
            if cand in out or any(len(classes - s) < need for s in seen):
                continue
            seen.append(classes)
            out.append(cand)
    return out


# =====================================================================  vue pour l'interface
def _reason(scorer: TeamScorer, team: list[Member], i: int) -> list[str]:
    """Ce qu'apporte le membre i à l'équipe (comparée à l'équipe sans lui)."""
    m = team[i]
    rest = team[:i] + team[i + 1:]
    out: list[str] = []
    before, after = scorer.role_cover(rest), scorer.role_cover(team)
    for r in ROLES:
        if after[r] - before[r] > 0.3:
            out.append(f"Rôle {ROLE_FR[r]}" if before[r] < 0.5 else f"{ROLE_FR[r]} en renfort")
    have = set().union(*(scorer.traits(x) for x in rest)) if rest else set()
    new_traits = [TRAITS[t][0] for t in TRAITS if t in scorer.traits(m) and t not in have]
    if new_traits:
        out.append("Apporte : " + ", ".join(new_traits))
    new_el = [e for e in ELEMENTS if e in scorer.elements(team) - scorer.elements(rest)]
    if new_el:
        out.append("Éléments : " + ", ".join(EL_FR[e] for e in new_el))
    return out



def team_view(data: GameData, body: dict[str, Any]) -> dict[str, Any]:
    size = int(body.get("size") or 6)
    style = str(body.get("style") or "balanced")
    picks = [p for p in (body.get("picks") or []) if isinstance(p, dict)]
    teams = compose(data, picks, size, style, alternatives=int(body.get("alternatives") or 3),
                    allow_duplicates=bool(body.get("duplicates")))
    scorer = TeamScorer(data, 6 if size > 3 else 3, style)
    best = scorer.score(teams[0]) if teams else 0.0
    out = []
    for team in teams:
        cover = scorer.role_cover(team)
        traits = set().union(*(scorer.traits(m) for m in team)) if team else set()
        els = scorer.elements(team)
        warnings = []
        if cover["heal"] < 0.5:
            warnings.append("Pas de soigneur : l'équipe dépend des potions et des soins d'appoint.")
        if cover["tank"] < 0.4 and style != "offense":
            warnings.append("Pas de tank : personne pour encaisser et retenir les ennemis.")
        if cover["tank"] >= 2.2:
            warnings.append("Beaucoup de tanks : l'équipe manquera de dégâts.")
        if cover["dps"] < 0.9:
            warnings.append("Peu de dégâts : les combats seront longs.")
        if len(els) < 3:
            warnings.append("Peu d'éléments : les ennemis résistants à ceux-là seront difficiles.")
        members = []
        for i, m in enumerate(team):
            cls = data.classes[m.class_key]
            a = ARCHETYPES[m.archetype]
            members.append({
                "class": m.class_key, "class_name": cls.name, "archetype": m.archetype, "arch_name": a.name,
                "roles": {r: round(x, 2) for r, x in _roles(m.archetype).items()},
                "role": a.role, "picked": m.fixed or m.chosen_class, "auto_arch": m.chosen_class and not m.fixed,
                "traits": [TRAITS[t][0] for t in TRAITS if t in scorer.traits(m)],
                "elements": list(cls.elements) if not a.hide_elements and a.offense > 0 else [],
                "reasons": _reason(scorer, team, i),
                "usual": m.archetype in class_archetypes(data, m.class_key),
            })
        order = {"tank": 0, "heal": 1, "support": 2, "dps": 3}
        members.sort(key=lambda x: (not x["picked"], order.get(str(x["role"]), 9)))
        score = scorer.score(team)
        out.append({
            "members": members, "score": round(score, 1), "rel": round(100 * score / best) if best > 0 else 100,
            "parts": {k: round(v, 1) for k, v in scorer.parts(team).items()},
            "roles": {r: round(cover[r], 1) for r in ROLES},
            "traits": [{"key": t, "name": TRAITS[t][0], "on": t in traits} for t in TRAITS],
            "elements": [e for e in ELEMENTS if e in els],
            "warnings": warnings,
        })
    return {"teams": out, "size": 6 if size > 3 else 3, "style": style}
