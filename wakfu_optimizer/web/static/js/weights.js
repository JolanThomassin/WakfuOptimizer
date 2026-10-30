"use strict";
// Onglet Poids : poids du calcul de l'archétype, modifiables (S.weights = poids saisis, voir engine/weights.py).

// S.weights : { "offense_weight": 30, "utility.ap": [8, 14], … } — seulement ce qui diffère de l'archétype
let wData = null;   // réponse de /api/weights (valeurs de l'archétype)

const num = (v, d = 2) => String(+(+v).toFixed(d)).replace(".", ",");
const ptsTxt = (v) => `${num(v)} pt${Math.abs(v) >= 2 ? "s" : ""}`;

async function loadWeights() {
  $("#tab-weights").innerHTML = `<div class="loading"><div class="spinner"></div>Lecture des poids de l'archétype…</div>`;
  try {
    wData = await api("/api/weights", { opts: { ...options(), custom_weights: {} } });
    renderWeights();
  } catch (e) {
    $("#tab-weights").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
  }
}

function updateWeightsBadge() {
  const n = Object.keys(S.weights).length;
  const b = $("#weights-badge");
  b.textContent = n ? `${n} modifié${n > 1 ? "s" : ""}` : "archétype";
  b.classList.toggle("manual", !!n);
}

// Valeur utilisée : la vôtre si modifiée, sinon celle de l'archétype
const wVal = (key, def) => (key in S.weights ? S.weights[key] : def);

function setWeight(key, value, def) {
  if (JSON.stringify(value) === JSON.stringify(def)) delete S.weights[key];
  else S.weights[key] = value;
  updateWeightsBadge();
  renderWeights();
}

function resetBtn(key) {
  return key in S.weights ? `<button class="w-reset" data-wreset="${key}" title="Revenir à la valeur de l'archétype">↺</button>` : "";
}

function wInput(attrs, value, step, min, max) {
  return `<input class="w-in" type="number" ${attrs} value="${value}" step="${step}" min="${min}"${max != null ? ` max="${max}"` : ""}>`;
}

function utilityCard(r) {
  const [pts, cap] = wVal(r.key, [r.def_pts, r.def_cap]);
  const mod = r.key in S.weights;
  const per = r.unit === 100 ? "pour 100" : r.decaying ? "pour le 1er point" : "par point";
  return `<div class="w-card ${mod ? "mod" : ""} ${pts ? "" : "zero"}">
    <div class="w-head">${icon(r.stat, r.label)}<span class="w-name">${esc(r.label)}</span>${mod ? `<span class="w-pill">modifié</span>` : ""}${resetBtn(r.key)}</div>
    <p class="w-desc">${esc(r.desc)}</p>
    <div class="w-fields">
      <label>Poids<span class="w-unit">${per}</span>${wInput(`data-wu="${r.key}" data-part="0"`, pts, r.unit === 100 ? 0.1 : 0.5, 0)}</label>
      <label>Jusqu'à<span class="w-unit">${r.unit === 100 ? "points" : esc(r.label)}</span>${wInput(`data-wu="${r.key}" data-part="1"`, cap, r.unit === 100 ? 50 : 1, 0)}</label>
    </div>
    <div class="w-def">Archétype : ${r.def_pts ? `${ptsTxt(r.def_pts)} ${per}, jusqu'à ${r.def_cap}` : "ne compte pas"}</div>
  </div>`;
}

function scalarCard(key, stat, label, desc, value, def, unitTxt, defTxt, disabled = false) {
  const mod = key in S.weights;
  return `<div class="w-card ${mod ? "mod" : ""} ${value ? "" : "zero"} ${disabled ? "off" : ""}">
    <div class="w-head">${icon(stat, label)}<span class="w-name">${esc(label)}</span>${mod ? `<span class="w-pill">modifié</span>` : ""}${resetBtn(key)}</div>
    <p class="w-desc">${desc}</p>
    <div class="w-fields one"><label>${unitTxt}${wInput(`data-ws="${key}" ${disabled ? "disabled" : ""}`, value, 1, 0, 100)}</label></div>
    <div class="w-def">Archétype : ${defTxt}</div>
  </div>`;
}

function renderWeights() {
  const w = wData, page = $("#tab-weights");
  if (!w) return;
  const off = wVal("offense_weight", w.offense.default), def = 100 - off;
  const offMod = "offense_weight" in S.weights;
  const derived = [
    ["dmg_pct", "Dégâts", off / 100, "par % de dégâts en plus"],
    ["hp", "PV", def / 100, "par % de PV en plus"],
    ["elem_res", "Résistances", def / 100, "par % de dégâts subis en moins"],
    ["block", "Parade", (def / 100) * w.block_reduction, `par % de Parade (coup paré : −${Math.round(100 * w.block_reduction)} % de dégâts)`],
  ].map(([stat, label, pts, unit]) => `<div class="w-tile ${pts ? "" : "zero"}" title="${esc(unit)}">${icon(stat, label)}
      <div><div class="w-tl">${esc(label)}</div><div class="w-tu">${esc(unit)}</div></div><b>${ptsTxt(pts)}</b></div>`).join("");
  const will = w.will, crit = w.crit;
  const willW = wVal("willpower_weight", will.def_weight), willMin = wVal("will_min", will.def_min);
  const critT = wVal("crit_target", crit.def_target);
  const n = Object.keys(S.weights).length;
  const apt = S.explain ? aptHtml(S.explain) : `<p class="muted">Lancez une optimisation : vous verrez ici ce que rapporte un point de plus dans chaque ligne d'aptitude.</p>`;
  page.innerHTML = `
  <div class="weights">
    <section class="card w-top">
      <div><h2>Poids du calcul · ${esc(w.archetype)}</h2>
        <p class="hint">Ce que chaque stat rapporte au score (1 point ≈ 1 % de valeur globale). Ce sont les poids de l'archétype :
          modifiez-en un pour le remplacer, ↺ pour revenir à sa valeur. Ils servent au prochain calcul.</p></div>
      <button class="btn small ${n ? "danger" : ""}" id="w-reset-all" ${n ? "" : "disabled"}>Tout réinitialiser${n ? ` (${n})` : ""}</button>
    </section>

    <section class="card">
      <div class="w-sec-h"><h2>Attaque et défense</h2>${offMod ? `<span class="w-pill">modifié</span>` : ""}${resetBtn("offense_weight")}</div>
      <div class="w-balance">
        <span class="w-side">${icon("dmg_pct", "Attaque")} Attaque <b>${off} %</b></span>
        <input type="range" id="w-offense" min="0" max="100" step="5" value="${off}">
        <span class="w-side right">Défense <b>${def} %</b> ${icon("elem_res", "Défense")}</span>
      </div>
      <p class="hint">Archétype : ${w.offense.default} % attaque. Les poids ci-dessous en découlent.</p>
      <div class="w-tiles">${derived}</div>
    </section>

    <section class="card">
      <h2>Stats utiles au-delà des minimums</h2>
      <p class="hint">Chaque point compte jusqu'au maximum indiqué ; au-delà, il ne rapporte plus rien. Poids à 0 : la stat ne compte pas.</p>
      <div class="w-grid">${w.utility.map(utilityCard).join("")}</div>
    </section>

    <section class="card">
      <h2>Volonté et critique</h2>
      <div class="w-grid">
        ${scalarCard("willpower_weight", "willpower", "Volonté (retraits infligés)",
          "Retraits de PA / PM sur les ennemis : environ poids / 100 point de score par point de Volonté.",
          willW, will.def_weight, "Poids", will.def_weight ? `${will.def_weight}` : "ne compte pas")}
        ${scalarCard("will_min", "willpower", "Volonté minimum",
          `Sous ce seuil, malus de ${num(will.penalty)} pt par point manquant (retraits PA / PM subis). 0 : pas de minimum.`,
          willMin, will.def_min, "Minimum", will.def_min ? `${will.def_min}` : "aucun")}
        ${scalarCard("crit_target", "crit_rate", "Critique visé",
          crit.enabled ? `Malus de ${num(crit.penalty)} pt par % de critique manquant sous ce palier. 0 : pas de palier.`
            : "Le critique ne compte pas pour ces réglages (priorités).",
          critT, crit.def_target, "Palier (%)", crit.def_target ? `${crit.def_target} %` : "aucun", !crit.enabled)}
      </div>
    </section>

    <section class="card">
      <h2>Pénalités fixes</h2>
      <div class="w-tiles">${w.fixed.map((f) => `<div class="w-tile" title="${esc(f.unit)}">${icon(f.stat, f.label)}
        <div><div class="w-tl">${esc(f.label)}</div><div class="w-tu">${esc(f.unit)}</div></div><b class="neg">${ptsTxt(f.pts)}</b></div>`).join("")}</div>
    </section>

    <section class="card">
      <h2>Aptitudes ${S.explain && S.explain.manual_apt ? "(les vôtres)" : "(profil de l'archétype)"}</h2>
      <p class="hint">Au build affiché : ce que rapporte 1 point de plus dans chaque ligne (points de score). Numérotées : lignes de
        l'archétype, dans l'ordre de remplissage ; « max d'office » : toujours au maximum ; ✗ : lignes que l'archétype n'utilise pas.</p>
      <div class="xapt">${apt}</div>
    </section>
  </div>`;
  bindWeights();
}

function bindWeights() {
  const w = wData;
  $("#w-offense").addEventListener("input", (e) => {   // aperçu pendant le glissement, enregistré au relâchement
    const off = +e.target.value;
    $$(".w-balance b")[0].textContent = `${off} %`; $$(".w-balance b")[1].textContent = `${100 - off} %`;
  });
  $("#w-offense").addEventListener("change", (e) => setWeight("offense_weight", +e.target.value, w.offense.default));
  $$("#tab-weights [data-wu]").forEach((inp) => inp.addEventListener("change", () => {
    const r = w.utility.find((x) => x.key === inp.dataset.wu);
    const cur = [...wVal(r.key, [r.def_pts, r.def_cap])];
    cur[+inp.dataset.part] = Math.max(0, +inp.value || 0);
    setWeight(r.key, cur, [r.def_pts, r.def_cap]);
  }));
  const defs = { willpower_weight: w.will.def_weight, will_min: w.will.def_min, crit_target: w.crit.def_target };
  $$("#tab-weights [data-ws]").forEach((inp) => inp.addEventListener("change", () =>
    setWeight(inp.dataset.ws, Math.max(0, Math.min(100, Math.round(+inp.value || 0))), defs[inp.dataset.ws])));
  $$("#tab-weights [data-wreset]").forEach((b) => b.addEventListener("click", () => {
    delete S.weights[b.dataset.wreset];
    updateWeightsBadge(); renderWeights(); sfx("click");
  }));
  $("#w-reset-all").addEventListener("click", () => {
    S.weights = {};
    updateWeightsBadge(); renderWeights(); sfx("click");
    toast("Poids de l'archétype rétablis.");
  });
}

// Aptitudes : ce que rapporte un point de plus, au build affiché (données de l'onglet Explication)
function aptHtml(x) {
  return x.aptitudes.map((b) => `<div class="xbranch" style="--bc:${BRANCH_COLOR[b.branch] || "#333"}"><div class="xbh">${esc(b.name)} <span class="muted">${b.total} pt</span></div>`
    + b.lines.map((l, i) => `<div class="xline ${l.points ? "" : "zero"} ${l.in_profile ? "" : "off"}" title="${l.in_profile ? "" : "Ligne non utilisée par l'archétype"}">
        <span class="ic"><img src="assets/aptitudes/${l.line}.png" alt="" onerror="this.src='assets/stats/empty_coin.png'"></span>
        <span class="xll">${l.in_profile ? `${i + 1}.` : "✗"} ${esc(l.label)}${l.forced ? ` <small class="muted" title="Mise au maximum d'office, comme le font les joueurs">· max d'office</small>` : ""}</span>
        <span class="xg ${l.gain > 0 ? "pos" : l.gain < 0 ? "neg" : "muted"}" title="Points de score pour 1 point de plus dans cette ligne${l.full ? " (ligne déjà au maximum)" : ""}">${l.full ? "max" : `${l.gain > 0 ? "+" : ""}${String(l.gain).replace(".", ",")} pt`}</span>
        <b>${l.points}</b></div>`).join("")
    + `</div>`).join("");
}
