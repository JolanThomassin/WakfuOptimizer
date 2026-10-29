# Vérification des hypothèses (données CDN 1.93.1.62, 28/10/2026)

Légende : ✅ vérifié dans les données · 🔶 vérifié par une source tierce (formule de jeu) · ❓ non vérifiable, à confirmer en jeu

## Données du CDN

| Hypothèse | Résultat |
|---|---|
| `config.json` donne la version | ✅ `{"version": "1.93.1.62"}` |
| Les 10 types demandés existent | ✅ tous en 200. `items.json` fait **15,5 Mo** (pas 20). Existent aussi : `itemTypes`, `blueprints`, `resources`, `resourceTypes`, `harvestLoots`, `collectibleResources`. |
| Structure d'un item | ✅ `definition.item.{id, level, baseParameters{itemTypeId, rarity, minimumShardSlotNumber, maximumShardSlotNumber}, graphicParameters{gfxId}, properties[]}`, `definition.equipEffects[].effect.definition{actionId, params}`, `title{fr,en,es,pt}` (4 langues). |
| `equipmentItemTypes` → slots | ✅ `equipmentPositions` / `equipmentDisabledPositions`. Toutes les armes 2 mains (101, 111, 114, 117, 223, 253, 519) désactivent `SECOND_WEAPON`. Types en plus de la liste attendue : 219 Poing, 480 Torche, 537 Outil (slot ACCESSORY), 647 Costume (slot COSTUME), 849 Porte-bonheur (slot PET). |
| Valeur = base + par niveau × niveau | ✅ mais `params[1] = 0` pour tous les équipements normaux : valeur = `params[0]`. Exceptions : familiers/montures (niveau 1-50) et 15 armes « Makabra » de niveau 0-1 (suivent le niveau du personnage). |
| Malus sur des actionId distincts | ✅ 25 actionId « Perte/Deboost », valeur brute positive → signe −1 dans la table. |
| « Maîtrise/Résistance sur X éléments » | ✅ actionId 1068 / 1069, `params = [valeur, 0, nb_éléments, 0]`. |
| Raretés 0-7 | ✅ 0 Commun (567), 1 Inhabituel (113), 2 Rare (1643), 3 Mythique (3087), 4 Légendaire (2201), 5 Relique (99), 6 Souvenir (104), 7 Épique (115). |
| Items boutique | ✅ propriété 7 `SHOP_ITEM` (21 équipements). Propriété 24 = exclu de l'encyclopédie (604). |
| Icônes | ✅ `https://static.ankama.com/wakfu/portal/game/item/115/{gfxId}.png` (aussi `/64/`). |
| Tranches de niveau | ✅ les niveaux d'items se concentrent sur 20, 35, 50, …, 230, 245 : tranches 1-20, 21-35, …, 231-245 correctes. Niveau max d'item : 245. |

## Règles d'équipement

| Hypothèse | Résultat |
|---|---|
| Max 1 Relique, 1 Épique | ✅ portée par les **propriétés**, pas la rareté : 8 = `EXCLUSIVE_EQUIPMENT_ITEM` (99 items, toutes les reliques), 12 = `EXCLUSIVE_EQUIPMENT_ITEM_2` (117 items : les 115 épiques + 2 items « anciens » de rareté 0). Le solveur contraint donc par propriété. |
| Autres limites (Souvenir, uniques) | ✅ aucune propriété d'exclusivité sur les Souvenirs → pas de limite. Seule autre règle : deux anneaux différents. |
| Résistances plafonnées à 90 % | 🔶 plafond 90 % depuis la 1.68 ; la résistance fixe n'est pas plafonnée. |
| Contrôle minimum | ⚠ **aucun équipement ne donne de Contrôle** dans cette version (pas d'actionId correspondant) : la contrainte ne peut venir que des passifs/caractéristiques (phase 2). |
| Mono/Zone | ⚠ **aucun équipement ne donne de Maîtrise Monocible ni Zone** (et les runes Monocible/Zone existent mais leur effet est vide, actionId 400) : en phase 1, le choix Mono/Zone n'a pas d'effet ; il viendra des points de caractéristiques (phase 2). |

## Runes (châsses)

✅ Les runes sont dans `items.json` (17 items de type 811 avec `shardsParameters`) : rien à saisir à la main sauf la courbe de valeurs.

| Rune | Couleur | Doublée sur |
|---|---|---|
| Maîtrise Mêlée | Rouge | Casque, Cape |
| Maîtrise Distance | Rouge | Ceinture, Arme |
| Maîtrise Berserk | Rouge | Amulette, Cape |
| Résistance Terre | Rouge | Plastron, Bottes |
| Maîtrise Critique | Verte | Épaulettes, Arme |
| Maîtrise Dos | Verte | Ceinture, Bottes |
| Initiative | Verte | Amulette, Cape |
| Esquive | Verte | Anneaux |
| Résistance Feu | Verte | Plastron, Ceinture |
| Maîtrise Élémentaire | Bleue | Plastron, Cape |
| Maîtrise Soin | Bleue | Épaulettes, Amulette |
| Vie | Bleue | Arme, Casque |
| Tacle | Bleue | Anneaux |
| Résistance Eau | Bleue | Épaulettes, Plastron |
| Résistance Air | Bleue | Plastron, Cape |
| (Maîtrise Monocible, Zone) | Rouge | effet vide : obsolètes |

- Codes : couleur 1 = rouge, 2 = verte, 3 = bleue, 0 = blanche. Positions : 0 Casque, 3 Épaulettes, 4 Amulette, 5 Plastron, 7/8 Anneaux, 10 Ceinture, 12 Bottes, 13 Cape, 15 Arme.
- 11 niveaux de rune ; niveau d'item requis : 0, 36, 51, 66, 81, 96, 126, 141, 171, 186, 216 (✅ `shardLevelRequirement`).
- Valeurs : l'effet est une courbe par morceaux (4 segments `[base, par_niveau]`). Les bornes des segments ne sont pas dans le JSON ; en prenant niveaux 1 | 2-5 | 6-9 | 10-11 (troncature à l'entier), on retrouve exactement les tables de WakForge (vérifiées en jeu par leur auteur) : Maîtrises secondaires 1, 3, 4, 6, 7, 10, 15, 19, 24, 30, 33 ; Maîtrise Élémentaire 1-22 ; Résistances 2 puis 2,5 × niveau (max 27) ; Vie 4-88 ; Tacle/Esquive 3-66 ; Initiative 2-44. 🔶
- Nombre de châsses : `minimumShardSlotNumber`-`maximumShardSlotNumber` = 1-4 pour toutes les armures/armes (7031 items), 0 pour familiers, montures, emblèmes, costumes (898). Le nombre réel est aléatoire : réglable dans l'outil.

## Sublimations

✅ Les sublimations sont dans `items.json` (type 812, champ `sublimationParameters{slotColorPattern, isEpic, isRelic}`) :
- 398 normales, toutes à **3 couleurs** (aucune à 4 dans cette version), niveaux I/II/III = items distincts ;
- 32 épiques et 47 reliques, **sans motif de couleur** : leur description indique qu'elles s'enchâssent **dans l'objet épique / relique**. 9 items (armes et anneaux des nations, Épée Éternelle) ont en plus les propriétés 19/20 « ajoute un slot de gemme épique/relique ».
- L'effet = actionId 304 « applique un état » (`params[0]` = id d'état, `params[2]` = niveau). `states.json` ne contient **que les noms** des états : les effets chiffrés doivent être saisis à la main (`static/sublimations.yaml`), au moins pour celles qui influencent le score.
- Châsse blanche = joker pour le motif 🔶 (règle appliquée par WakForge). Motif sur 3 châsses consécutives parmi 4 (positions 1-3 ou 2-4) 🔶.
- ❓ À confirmer en jeu : les châsses doivent-elles contenir une rune pour activer la sublimation (le solveur les remplira de toute façon).
- ❓ Cumul : certains états ont un niveau max (ex. sublimations épiques limitées au niveau 1). À reporter dans le YAML.

## Formules de combat 🔶

Sources : [wakfu.wiki.gg/wiki/Damage](https://wakfu.wiki.gg/wiki/Damage), [Wakfu Calc – Formulas](https://sites.google.com/view/wakfucalc/en/guides/formulas).

- `% résistance = floor(100 × (1 − 0.8^(rés_fixe / 100)))`, plafond 90 % (≈ 1032 fixe). ✅ conforme à l'hypothèse (avec arrondi inférieur).
- Dégâts = `base × (1 + maîtrises/100) × orientation × crit × (1 + %dégâts infligés/100) × (1 − %rés/100)`.
- Critique : **×1,25 sur la valeur de base**, la Maîtrise Critique s'ajoute aux maîtrises → la formule proposée est correcte.
- Orientation : 1 face, 1,1 côté, **1,25 dos** (et la Maîtrise Dos s'ajoute de dos).
- Berserk : actif si PV ≤ 50 %.
- PV : `(50 + 10 × niveau + PV fixes) × (1 + %PV/100)`.
- ❓ Stats de base (6 PA, 3 PM, 6 PW, 3 % crit) : valeurs courantes, à confirmer.

## Non résolu

- ❓ actionId 39/40 « charac passée en paramètre » : `params[4]` vaut 120 (123 items, ex. « Casque de puissance » +10) ou 121 (90 items, ex. familier Arakne). Le CDN ne nomme pas ces characs : il faut lire leur effet en jeu. Exclus du score en attendant.
- ❓ Effets « applique un état » (304) sur 104 équipements : effets spéciaux non chiffrés, ignorés par défaut.
