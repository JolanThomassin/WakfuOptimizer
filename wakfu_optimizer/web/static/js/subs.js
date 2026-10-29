"use strict";
// Onglet Sublimations : catalogue, imposées / exclues, tiroirs.

// ===================================================================== onglet Sublimations
const KIND_FR = { normal: "Normale", epic: "Épique", relic: "Relique" };
let subsCache = null;
let subsTimer = null;

function setSubPref(state, pref) {
  // pref : "fo" (imposer), "ex" (exclure) ; un second clic sur le même choix l'annule
  const was = pref === "fo" ? S.subForced.has(state) : S.subExcluded.has(state);
  S.subForced.delete(state); S.subExcluded.delete(state); delete S.subLevels[state];
  if (!was) (pref === "fo" ? S.subForced : S.subExcluded).add(state);
  updateSubsBadge();
  sfx("click");
  if (subsCache) renderSubs();
}
function updateSubsBadge() {
  const b = $("#subs-badge");
  const n = S.subForced.size + S.subExcluded.size;
  b.textContent = `${S.subForced.size} imposée(s) · ${S.subExcluded.size} exclue(s)`;
  b.classList.toggle("hidden", !n);
  b.classList.toggle("manual", !!n);
}

async function loadSubs() {
  $("#subs-list").innerHTML = `<div class="loading"><div class="spinner"></div>Calcul de l'intérêt de chaque sublimation…</div>`;
  try {
    subsCache = await api("/api/subs", { opts: S.opts || options(), build: S.view ? S.view.build : null });
    renderSubs();
  } catch (e) {
    $("#subs-list").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
  }
}

function subCard(f) {
  const fo = S.subForced.has(f.state), ex = S.subExcluded.has(f.state);
  const lv = f.levels.map((l) => `<span class="lv" title="${esc(l.name)}">${patternHtml(l.pattern)}<small>${esc(l.name.replace(/^.*\s/, ""))}</small></span>`).join("");
  const gain = f.gain == null ? "" : `<span class="gain ${pn(f.gain)}" title="Gain de score si on l'ajoute au build (niveau max)">${f.gain > 0 ? "+" : ""}${f.gain.toFixed(1)}</span>`;
  const tags = [
    f.kind !== "normal" ? `<span class="tag ${f.kind}">${KIND_FR[f.kind]}</span>` : "",
    f.in_build ? `<span class="tag on">Dans le build · niv. ${f.in_build}${f.limit ? `/${f.limit}` : ""}</span>` : "",
    !f.modeled ? `<span class="tag" title="L'optimiseur ne sait pas chiffrer cet effet : il ne la placera que si vous l'imposez">Non chiffrée</span>` : "",
    f.same_levels ? `<span class="tag" title="Dans les données du jeu, tous les niveaux donnent le même effet : le niveau ne sert qu'à atteindre le cumul maximum.">Niveaux identiques</span>` : "",
    f.modeled && !f.applicable ? `<span class="tag" title="Ses conditions ne correspondent pas à vos options (portée, élément, berserk…)">Incompatible</span>` : "",
  ].join("");
  return `<div class="sub-card ${fo ? "fo" : ""} ${ex ? "ex" : ""}">
    <div class="sc-head"><div class="sc-name">${esc(f.name)} ${tags}</div>${gain}</div>
    <div class="sub-desc">${esc(f.desc || "Pas de description.")}</div>
    <div class="sc-foot"><div class="lvls">${f.kind === "normal" ? lv : `<small class="muted">Se pose dans un objet ${f.kind === "epic" ? "épique" : "relique"}</small>`}</div>
      <div class="btns">${fo ? levelSelect(f) : ""}<button class="btn small ${fo ? "good" : ""}" data-sfo="${f.state}" title="L'optimiseur doit la placer">${fo ? "✓ Imposée" : "Imposer"}</button>
      <button class="btn small ${ex ? "danger" : ""}" data-sex="${f.state}" title="L'optimiseur ne l'utilisera pas">${ex ? "✕ Exclue" : "Exclure"}</button></div></div>
  </div>`;
}

// Niveau imposé : niveau cumulé minimum de l'état (ex. Neutralité III, ou IV avec deux sublimations)
const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII"];
function levelSelect(f) {
  const top = f.limit || Math.max(...f.levels.map((l) => l.level), 1);
  if (top <= 1) return "";
  const cur = S.subLevels[f.state] || 1;
  return `<label class="lvl-min" title="Niveau minimum : l'optimiseur peut monter plus haut si ça rapporte, jamais en dessous. Les niveaux de plusieurs sublimations identiques s'additionnent (ex. IV = III + I).">Niveau min.
    <select class="lvl-sel" data-slvl="${f.state}">${
    Array.from({ length: top }, (_, i) => `<option value="${i + 1}" ${i + 1 === cur ? "selected" : ""}>≥ ${ROMAN[i + 1] || i + 1}</option>`).join("")}</select></label>`;
}

function renderSubs() {
  const q = $("#subs-q").value.trim().toLowerCase();
  const kind = segVal("subs-kind") || "all";
  const list = subsCache.filter((f) => (kind === "all" || f.kind === kind)
    && (!q || `${f.name} ${f.desc}`.toLowerCase().includes(q)));
  const pinned = list.filter((f) => S.subForced.has(f.state) || S.subExcluded.has(f.state));
  const rest = list.filter((f) => !pinned.includes(f));
  const groups = [
    ["Vos choix", pinned, ""],
    ["Dans le build", rest.filter((f) => f.in_build), "Sublimations placées par l'optimiseur."],
    ["Recommandées pour ce build", rest.filter((f) => !f.in_build && f.applicable && f.gain != null && f.gain >= 0.3),
      "Elles apporteraient le plus si on les ajoutait (à la place d'une autre ou dans un objet épique / relique)."],
    ["Autres sublimations utiles", rest.filter((f) => !f.in_build && f.modeled && f.applicable && !(f.gain != null && f.gain >= 0.3)),
      S.view ? "Apport faible sur ce build (souvent : niveau max déjà atteint, ou stat déjà au plafond)." : "Lancez une optimisation pour voir leur apport chiffré."],
    ["Non chiffrées par l'optimiseur", rest.filter((f) => !f.in_build && !f.modeled),
      "Effets trop situationnels pour être chiffrés (déclenchements, dégâts de dos, armure…). Imposez celles qui vont avec votre façon de jouer."],
    ["Incompatibles avec vos options", rest.filter((f) => !f.in_build && f.modeled && !f.applicable), "Leur condition ne correspond pas à vos réglages."],
  ];
  $("#subs-count").textContent = `${list.length} sublimation(s)`;
  $("#subs-list").innerHTML = groups.filter(([, g]) => g.length).map(([title, g, hint]) => `
    <details class="sub-group" ${title.startsWith("Non chiffrées") || title.startsWith("Incompatibles") ? (q ? "open" : "") : "open"}>
      <summary><h2>${title} <span class="muted">(${g.length})</span></h2></summary>
      ${hint ? `<p class="hint">${hint}</p>` : ""}
      <div class="sub-grid">${g.map(subCard).join("")}</div></details>`).join("") || `<p class="muted pad">Aucune sublimation ne correspond.</p>`;
}

function closeDrawers() { $$(".drawer").forEach((d) => d.classList.add("hidden")); }
document.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDrawers(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawers(); });
