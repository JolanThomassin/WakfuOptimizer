# Wakfu Optimizer

Optimiseur de build Wakfu : à partir d'une classe, d'un niveau et de priorités, il cherche le meilleur équipement (châsses, runes et sublimations comprises) avec le solveur OR-Tools CP-SAT.

> Outil communautaire non officiel. État : **étape 1** (récupération des données + table des effets).

## Installation

Python 3.12 ou plus récent.

```bash
cd wakfu_optimizer
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS : source .venv/bin/activate)
pip install -e ".[dev]"
```

## Interface

Double-cliquez sur `Lancer Wakfu Optimizer.bat` (ou `python -m wakfu_optimizer.web`) : l'interface s'ouvre dans le navigateur.
Après un calcul, cliquez sur un item du build pour voir les autres items possibles, la comparaison gains / pertes, et valider l'échange.
Chaque item indique comment l'obtenir : recette (métier, niveau, ingrédients au survol, tirés des données Ankama) et lien
« Où l'obtenir » vers [wakfu.wiki.gg](https://wakfu.wiki.gg) pour les butins de monstres, coffres et succès (absents des données Ankama).

## Version en ligne (sans Python) — GitHub Pages

La même interface tourne entièrement dans le navigateur : le code Python est exécuté par [Pyodide](https://pyodide.org)
dans un Web Worker et OR-Tools (absent du navigateur) est remplacé par le solveur [HiGHS](https://highs.dev)
(`wakfu_optimizer/engine/milp.py`, même API que CP-SAT). Rien à installer pour l'utilisateur.

Mise en ligne :

1. Pousser le projet sur GitHub (branche `main`).
2. Dans le dépôt : *Settings > Pages > Build and deployment > Source* : **GitHub Actions**.
3. Le workflow `.github/workflows/pages.yml` construit le site (`tools/build_site.py`) et le publie sur
   `https://<utilisateur>.github.io/<dépôt>/`. Il est relancé chaque jour pour suivre les patchs du jeu.

Le CDN Ankama n'autorise pas les requêtes depuis un autre site (pas de CORS) : `build_site.py` copie donc dans le site
une version allégée de `items.json` et `equipmentItemTypes.json` (champs lus par l'optimiseur uniquement).

Tester en local : `python tools/build_site.py` puis `python -m http.server 8766 --directory _site`.
Pour tester le solveur HiGHS hors navigateur : `WAKFU_SOLVER=highs pytest`.

Le solveur maximise `85 × ln(dégâts) + 15 × ln(PV effectifs) + valeur des PA/PM/PO/PW − pénalité` par linéarisations
successives (chaque passe est un problème linéaire CP-SAT, résolu en quelques secondes). La pénalité porte sur la
**résistance visée** : 1 point de score par point de résistance fixe manquant, par élément. La cible est donc atteinte dès que
c'est possible, sans rendre le calcul impossible à bas niveau.

- **Portée** : mêlée, distance ou **mixte** (les deux maîtrises comptent à moitié : Huppermage, Eliotrope).
- **Coups de dos** : part des coups portés de dos (25 / 50 / 80 %) ; seule cette part profite de la Maîtrise Dos.
- **Contraintes** : minimum et maximum de PA, PM, PO, PW et % critique.
- **Sublimations** (onglet dédié) : apport chiffré de chacune sur le build, sublimations **imposées** (même celles dont
  l'effet n'est pas chiffré, ex. Destruction) ou **exclues** ; sur le build, clic sur une sublimation pour la changer.
- **Version navigateur (HiGHS)** : HiGHS trouve mal un premier build quand il doit aussi placer les châsses. On lui en
  construit un (items choisis sans châsses, puis châsses complétées items fixés), et chaque passe repart du build précédent.

## Utilisation (étape 1)

```bash
python -m wakfu_optimizer.data.fetch          # télécharge les données si la version a changé
python -m wakfu_optimizer.data.fetch --force  # retélécharge la version courante
python -m wakfu_optimizer.data.explore        # rapport des actionId -> reports/actions_<version>.md
pytest                                        # tests
```

Les données sont mises en cache dans `data/cache/<version>/` (variable `WAKFU_OPTIMIZER_CACHE` pour changer le dossier). Sans réseau, la dernière version complète du cache est utilisée.

## Sources de données

- Données de jeu : CDN officiel Ankama, `https://wakfu.cdn.ankama.com/gamedata/config.json` puis `/{version}/{type}.json`. Elles restent la propriété d'Ankama ; leur mise à disposition et ses conditions sont décrites sur le [forum Wakfu (JSON DATA)](https://www.wakfu.com/en/forum/332-development/236779-json-data). Ne pas redistribuer le cache.
- Icônes : `https://static.ankama.com/wakfu/portal/game/item/115/{gfxId}.png` (version locale) ; dans la version en ligne,
  et pour les icônes de stats (`gui/assets/stats`) et d'aptitudes (`gui/assets/aptitudes`), le dépôt communautaire
  [wakassets](https://github.com/Vertylo/wakassets) (images © Ankama, usage communautaire non commercial).
- Formules de combat : [wakfu.wiki.gg](https://wakfu.wiki.gg/wiki/Damage), [Wakfu Calc](https://sites.google.com/view/wakfucalc/en/guides/formulas). Valeurs de runes recoupées avec [WakForge](https://github.com/Tmktahu/WakForge) (MIT).

Le détail de chaque hypothèse vérifiée est dans [docs/verifications.md](docs/verifications.md).

## Formules utilisées

- Valeur d'un effet d'équipement : `params[0] + params[1] × niveau` (`params[1]` vaut 0 hors familiers/montures).
- Résistance : `% = floor(100 × (1 − 0,8^(rés_fixe/100)))`, plafond 90 %.
- Dégâts moyens (élément principal), `M` = maîtrises applicables, `Mc` = Maîtrise Critique, `t` = taux critique plafonné à 100 % :
  `E(M) = (1 − t) × (1 + M/100) + t × 1,25 × (1 + (M + Mc)/100)`.
  De dos (proportion `p` des frappes) : `(1 − p) × E(M) + p × 1,25 × E(M + Maîtrise Dos)`.

## Après un patch du jeu

1. `python -m wakfu_optimizer.data.fetch` (nouvelle version détectée automatiquement).
2. `python -m wakfu_optimizer.data.explore` : code de sortie 2 et liste des actionId inconnus s'il y en a.
3. Ajouter ces actionId dans `wakfu_optimizer/data/static/actions_map.yaml` (stat, signe), puis relancer `pytest`.

## Limites connues

- Aucun équipement ne donne de Contrôle ni de Maîtrise Monocible/Zone : ces stats viendront des caractéristiques (phase 2).
- Les effets « applique un état » (sublimations, effets spéciaux d'items) ne sont pas chiffrés dans le CDN ; ils doivent être saisis à la main.
- actionId 39/40 (« charac passée en paramètre ») : libellé à confirmer en jeu, exclus du score.
