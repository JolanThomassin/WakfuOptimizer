"""Qualité d'un build : règles « ce build a du sens pour cet archétype ».

Les mêmes règles servent aux tests (tests/test_build_quality.py : chaque classe × archétype habituel × niveau)
et à l'onglet Explication de l'interface (explain.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data.models import SLOT_FR, GameData, Slot
from .archetypes import ARCHETYPES, apt_profile
from .characteristics import BRANCH_FR, LINE_FR, branch_points, char_lines
from .options import Build, OptimizeOptions, default_min_ap, default_min_mp
from .shards import needs_no_secondary
from .stats import Totals

# Emplacements qu'un build complet remplit toujours (familier, monture et emblème dépendent du niveau / des filtres ;
# la seconde main peut rester vide exprès : sublimation Expert des armes légères)
CORE_SLOTS = (Slot.HEAD, Slot.NECK, Slot.CHEST, Slot.LEFT_HAND, Slot.RIGHT_HAND, Slot.LEGS, Slot.BACK,
              Slot.SHOULDERS, Slot.BELT, Slot.FIRST_WEAPON)
CRIT_MARGIN = 3        # % de critique toléré sous le palier de l'archétype
TANK_RES_PCT = 60      # % de résistance minimum (chaque élément) d'un tank
LINES_DPS_ONLY = ("strength.melee_mastery", "strength.distance_mastery", "fortune.crit_rate")


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str
    severity: str = "error"    # error : build incohérent | warn : à surveiller

    def __str__(self) -> str:
        return f"[{'OK' if self.ok else self.severity.upper()}] {self.label} : {self.detail}"


def _apt_label(key: str) -> str:
    branch, line = key.split(".", 1)
    return f"{BRANCH_FR.get(branch, branch)} · {LINE_FR.get(line, line)}"


def check_aptitudes(data: GameData, opts: OptimizeOptions, ch: dict[str, int]) -> list[Check]:
    """Aptitudes cohérentes avec l'archétype : tous les points placés, seulement des lignes du profil, et les
    incontournables (Résistance élémentaire, PA, % Critique d'un DPS, PV et Parade d'un tank, Volonté d'un débuff)."""
    out: list[Check] = []
    arch = ARCHETYPES.get(opts.archetype)
    role = arch.role if arch else "dps"
    L = opts.level

    def add(key: str, label: str, ok: bool, detail: str, severity: str = "error") -> None:
        out.append(Check(key, label, bool(ok), detail, severity))

    lines = char_lines(data.game)
    unspent = []
    for branch in data.game["characteristics"]:  # type: ignore[union-attr]
        left = branch_points(branch, L, data.game) - sum(ch.get(cl.key, 0) for cl in lines if cl.branch == branch)
        if left:
            unspent.append(f"{BRANCH_FR.get(branch, branch)} ({left})")
    add("apt_spent", "Tous les points d'aptitude placés", not unspent, "restants : " + ", ".join(unspent) if unspent else "oui")
    prof = apt_profile(opts)
    allowed = {f"{b}.{x}" for b, xs in prof.items() for x in xs}
    off = [f"{_apt_label(k)} ({n})" for k, n in ch.items() if n and k not in allowed]
    add("apt_profile", "Aptitudes cohérentes avec l'archétype", not off,
        "hors profil : " + ", ".join(off) if off else "uniquement des lignes du profil")
    if opts.apt_elem_res:
        need = min(10, branch_points("intelligence", L, data.game))
        add("apt_res", "Résistance élémentaire (Intelligence) au max", ch.get("intelligence.elem_res", 0) >= need,
            f"{ch.get('intelligence.elem_res', 0)} / {need}")
    if branch_points("major", L, data.game) >= 1:
        add("apt_major_ap", "Majeur : Point d'Action", ch.get("major.ap", 0) == 1, "pris" if ch.get("major.ap") else "absent")
    if opts.crit and opts.crit_target:
        need = min(20, branch_points("fortune", L, data.game))
        add("apt_crit", "Chance : % Coup critique au max", ch.get("fortune.crit_rate", 0) >= need,
            f"{ch.get('fortune.crit_rate', 0)} / {need}")
    if role == "tank":
        dps_lines = [f"{_apt_label(k)} ({ch[k]})" for k in LINES_DPS_ONLY if ch.get(k)]
        add("tank_apt_dps", "Tank : pas d'aptitudes de DPS", not dps_lines,
            "trouvé : " + ", ".join(dps_lines) if dps_lines else "aucune (critique, maîtrise mêlée / distance)")
        need = branch_points("strength", L, data.game)
        add("tank_apt_hp", "Tank : Force en Points de Vie", ch.get("strength.hp", 0) >= need,
            f"{ch.get('strength.hp', 0)} / {need}")
        need = min(20, branch_points("fortune", L, data.game))
        add("tank_apt_block", "Tank : % Parade au max", ch.get("fortune.block", 0) >= need, f"{ch.get('fortune.block', 0)} / {need}")
    if opts.willpower_weight >= 20:
        need = min(20, branch_points("agility", L, data.game))
        add("apt_will", "Retraits : Volonté au max", ch.get("agility.willpower", 0) >= need,
            f"{ch.get('agility.willpower', 0)} / {need}")
    return out


def check_build(data: GameData, opts: OptimizeOptions, build: Build, tot: Totals) -> list[Check]:
    """Règles qu'un build optimisé doit respecter pour avoir du sens (classe, niveau, archétype)."""
    out: list[Check] = []
    arch = ARCHETYPES.get(opts.archetype)
    role = arch.role if arch else "dps"
    s, L = tot.stats, opts.level
    # sublimation « maîtrises secondaires <= 0 » dans le build (Dénouement, Ambition…) : portée / dos / berserk à 0 exprès
    no_sec = any(needs_no_secondary(data.states.get(sid)) for sid in tot.active_states)

    def add(key: str, label: str, ok: bool, detail: str, severity: str = "error") -> None:
        out.append(Check(key, label, bool(ok), detail, severity))

    # --- équipement
    missing = [SLOT_FR[s_] for s_ in CORE_SLOTS if s_ not in build.slots]
    add("slots", "Équipement complet", not missing, "manque : " + ", ".join(missing) if missing else "tous les emplacements remplis")

    # --- PA / PM du niveau
    add("ap", "PA du niveau", s.get("ap", 0) >= default_min_ap(L), f"{s.get('ap', 0)} PA (minimum {default_min_ap(L)})")
    add("mp", "PM du niveau", s.get("mp", 0) >= default_min_mp(L), f"{s.get('mp', 0)} PM (minimum {default_min_mp(L)})")

    # --- résistances
    worst = min(tot.res_pct.values())
    if opts.res_target:
        floor = opts.res_target - opts.res_tol
        add("res", "Résistance visée", worst >= floor, f"élément le plus faible {worst} % (plancher {floor} %)")
    if role == "tank":
        need = min(TANK_RES_PCT, opts.res_target - opts.res_tol)   # bas niveau : le maximum atteignable
        add("tank_res", "Résistances de tank", worst >= need, f"élément le plus faible {worst} % (≥ {need} % attendu)")

    # --- aptitudes
    if opts.char_mode != "manual" and opts.optimize_characteristics:
        out += check_aptitudes(data, opts, build.characteristics)

    # --- dégâts
    if opts.crit and opts.crit_target:
        c = s.get("crit_rate", 0)
        add("crit", "Critique suffisant", c >= opts.crit_target - CRIT_MARGIN,
            f"{c} % (palier de l'archétype au niveau {L} : {opts.crit_target} %)")
    if role in ("dps", "heal") and opts.range in ("melee", "distance") and not no_sec:
        mine, other = ("melee_mastery", "distance_mastery") if opts.range == "melee" else ("distance_mastery", "melee_mastery")
        add("range_mastery", "Maîtrise de la bonne portée", s.get(mine, 0) > max(0, s.get(other, 0)),
            f"{LINE_FR[mine]} {s.get(mine, 0)} contre {LINE_FR[other]} {s.get(other, 0)}")
    for flag, stat, lab in (("rear", "rear_mastery", "Maîtrise Dos"), ("berserk", "berserk_mastery", "Maîtrise Berserk"),
                            ("heal", "heal_mastery", "Maîtrise Soin")):
        # hybride dégâts / soins : la Maîtrise Soin ne compte que pour les soins, s'en passer peut être le bon choix
        if getattr(opts, flag) and not no_sec and not (flag == "heal" and opts.heal_share < 100):
            add(f"{flag}_mastery", f"{lab} présente", s.get(stat, 0) > 0, f"{s.get(stat, 0)}")
    return out


def failures(checks: list[Check], severity: str = "error") -> list[Check]:
    return [c for c in checks if not c.ok and c.severity == severity]
