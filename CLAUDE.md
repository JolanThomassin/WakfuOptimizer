# Wakfu Optimizer — carte du code

Optimiseur de build Wakfu : Python (moteur + serveur local) et interface web en JS sans framework. Le même moteur
tourne dans le navigateur (GitHub Pages) via Pyodide, avec HiGHS à la place d'OR-Tools. Code, commentaires,
interface et messages de commit en français.

## Où changer quoi

| Pour… | Fichier |
|---|---|
| Une formule de jeu, la valeur d'une stat, une pénalité | `engine/scoring.py` (`score_parts`, constantes `*_PENALTY`, `UTILITY`) |
| Une variable du score (nouvelle stat qui compte) | `engine/features.py` (évaluateur + modèle côte à côte, la checklist est en tête) |
| Un archétype, ses poids, son profil d'aptitudes | `engine/archetypes.py` (`ARCHETYPES`, `archetype_values`, `apt_profile`, `apt_forced`) |
| Les poids modifiables (onglet Poids) | `engine/weights.py` (`UTILITY_ROWS`, `apply_custom_weights`) + `web/static/js/weights.js` |
| Une contrainte du modèle (min / max, règle d'équipement) | `engine/model.py` (`_build` pour les items, `_derived` pour les stats) |
| Les passes, le temps, le rattrapage de résistance, le diagnostic | `engine/solver.py` |
| L'élagage des items candidats | `engine/candidates.py` (`item_features` : à tenir à jour avec le score) |
| Le calcul exact des stats d'un build | `engine/stats.py` (`evaluate`) |
| Les contrôles « ce build a du sens » | `engine/quality.py` (tests + onglet Explication) |
| L'onglet Explication | `engine/explain.py` (Python) + `web/static/js/explain.js` |
| Une réponse JSON de l'interface | `web/views.py` ; nouvelle requête : une ligne dans `ROUTES` (marche en local et en ligne) |
| L'interface | `web/static/js/<onglet>.js`, `index.html`, `style.css` |
| Une traduction (EN / ES / PT) d'un texte affiché | `web/static/js/i18n_dict.js` ; effets de sublimations et passifs : `i18n_subs.js` |
| Les données maintenues à la main | `data/static/game.yaml` (classes, aptitudes, base), `sublimations.yaml`, `actions_map.yaml` |

## Moteur (`wakfu_optimizer/engine/`)

Flux d'un calcul (`solver.Optimizer.run`) :
`options` corrigées → `candidates.select_candidates` → `model.BuildModel` (variables + contraintes) →
passes : objectif = gradient du score (`scoring.gradient`) × variables du score (`features.model_features`),
résolution, `model.extract` → build, `stats.evaluate` → score exact, nouveau point de linéarisation →
finitions (`sublimations.fill_empty_subs`, `characteristics.fill_unspent`) → `SolveResult`.

- `options.py` : `OptimizeOptions` (tous les réglages), `Build` (résultat sérialisable).
- `backend.py` : choix du solveur (OR-Tools CP-SAT, ou `milp.py` = HiGHS avec la même API ; `WAKFU_SOLVER=highs`).
- `scoring.py` : formules pures, `FEATURES` (variables du score et pas du gradient), `score_parts`, `gradient`.
- `features.py` : chaque variable du score, calculée exactement (évaluateur) et linéairement (modèle).
- Le score est en points (≈ % de valeur globale) : `w_off × ln(dégâts) + w_def × ln(PV effectifs) + utilité − pénalités`.
- `archetypes.py` est la seule définition des archétypes (l'interface les reçoit par `/api/meta`).
- `alternatives.py`, `sublimations.py` : remplacement d'un item / d'une sublimation sur un build (onglets du site).
- `report.py` : export texte / JSON. `shards.py` : règles châsses / runes / conditions de sublimations.

## Web (`wakfu_optimizer/web/`)

- `server.py` : serveur HTTP local (fichiers, données, calculs en tâche de fond). `browser.py` : la même chose
  pour Pyodide (appelé par `pages/worker.js` ; `pages/bridge.js` remplace `fetch` dans le navigateur).
- `views.py` : toutes les réponses JSON + `ROUTES`, communes aux deux versions.
- `static/js/` : scripts classiques qui partagent la portée globale, chargés dans l'ordre de `index.html`
  (`core.js` d'abord : `$`, `api`, état `S` ; `main.js` en dernier : démarrage). Un nouveau fichier = une balise
  `<script>` dans `index.html` (`tools/build_site.py` versionne toutes les balises `static/...`).
- `static/js/i18n.js` : langue du site (drapeaux). Le code et le serveur écrivent en français ; chaque texte affiché
  est traduit à la volée par sa clé française (nombres → `{0}`). Nouveau texte : ajouter sa clé dans `i18n_dict.js`
  (mode debug, en anglais : `[...UI.miss]` dans la console liste les textes sans traduction).
- `gui/` : ancienne interface Qt (PySide6), plus utilisée par le lanceur ; seuls `gui/assets/` (icônes) servent au site.

## Vérifier un changement

- `pytest` (~4 min, dont tests de qualité sur les vraies données) ; `pytest --quality=off` pour aller vite.
- Changement du calcul (score, modèle, passes, élagage) : `python tools/bench.py --save avant.json` **avant**,
  puis `--compare avant.json` après (scores, temps, et réévaluation de l'ancien build avec le nouveau score).
- Refactor sans changement de comportement : `python tools/bench.py --model --full --save m.json` avant,
  `--compare m.json` après : les modèles CP-SAT doivent rester identiques.
- Interface : lancer `wakfu-web` (`.claude/launch.json`), faire un calcul, ouvrir chaque onglet, cliquer un item.
  Version en ligne : `python tools/build_site.py` puis `wakfu-pages`.
- `mypy` est déjà bruyant (API CamelCase d'OR-Tools) : comparer le nombre d'erreurs avant / après, pas viser zéro.
