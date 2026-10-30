"use strict";
// Onglet Build sombre (mode debug) : combos de sublimations sur le build affiché, items inchangés (engine/combos.py).

const FORGE = { params: null, res: null, sel: 0, busy: false, families: null, famKey: "", buildKey: "", timer: 0 };
const FORGE_DEFAULT = { mode: "colors", objective: "score", epic: true, relic: true, pivot: 0, intensity: "normal",
  diversity: 3, top: 6, keep_minimums: true, conditional: true, confirmed_only: false };
const INTENSITY = { fast: { beam: 8, time_limit: 4 }, normal: { beam: 16, time_limit: 10 }, deep: { beam: 32, time_limit: 25 } };
const FG_MODE_HINT = {
  colors: "Chaque sublimation doit tenir dans les couleurs actuelles des châsses (le jaune sert de joker). Le combo se pose tel quel sur le build.",
  recolor: "N'importe quel item à 3 châsses peut porter n'importe quelle sublimation : à l'application, les châsses sont recolorées et les runes replacées (score exact recalculé).",
  dream: "Théorique : aucune contrainte de couleur, une épique et une relique même sans item pour les porter. Pour voir jusqu'où les sublimations peuvent aller.",
};
const FG_OBJ_HINT = {
  score: "Le score de l'archétype : dégâts, survie, PA / PM et objectifs (résistance, critique visés).",
  damage: "Dégâts seuls, quitte à sacrifier la survie et les objectifs de l'archétype (seuls les garde-fous PA / PM restent).",
  survival: "PV effectifs seuls (PV, résistances, parade), quitte à sacrifier les dégâts.",
};
// Rôle d'une famille dans un combo (engine/combos.py, Forge._analyse) : classe CSS et explication
const FG_ROLE = {
  Pilier: ["r-pillar", "Celle qui rapporte le plus dans ce combo."],
  Catalyseur: ["r-cata", "Vaut plus dans le combo que seule : elle fait monter une stat qui profite aux autres."],
  Déclenchée: ["r-trig", "Sa condition est remplie grâce aux autres sublimations : elle vaut plus dans le combo que seule."],
  Sacrifice: ["r-sacr", "Coûte seule (malus), mais rapporte dans ce combo."],
  "Garde-fou": ["r-guard", "Sans elle, le combo passe sous les PA / PM minimums (elle compense le malus d'une autre)."],
  Plafonnée: ["r-cap", "Rapporte peu ici : sa stat est déjà haute ou nourrie par une autre (rendement décroissant)."],
  Appoint: ["r-extra", "Apport simple, sans interaction notable."],
};
const FG_PHASES = [[0, "Solo : chaque sublimation seule…"], [0.06, "Duos : recherche des synergies…"],
  [0.16, "Faisceau : assemblage des combos…"], [0.7, "Descente : derniers ajustements…"], [0.9, "Analyse : anatomie des combos…"]];
const FG_SIGIL = `<svg class="fg-sigil" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="46"/><circle cx="50" cy="50" r="38"/>
  <path d="M50 12 L83 69 L17 69 Z"/><path d="M50 88 L17 31 L83 31 Z"/><circle cx="50" cy="50" r="9"/>
  ${Array.from({ length: 12 }, (_, i) => { const a = (i * Math.PI) / 6; return `<circle class="dot" cx="${50 + 42 * Math.cos(a)}" cy="${50 + 42 * Math.sin(a)}" r="1.6"/>`; }).join("")}</svg>`;

const f1 = (v) => (+v).toFixed(1).replace(".", ",");
function fgGain(g, signedTxt = true) {   // gain dans l'unité de l'objectif : points de score, ou % de dégâts / PV effectifs
  const obj = FORGE.res ? FORGE.res.params.objective : "score";
  const s = signedTxt && g > 0 ? "+" : g < 0 ? "−" : "";
  if (obj === "score") return `${s}${f1(Math.abs(g))} pts`;
  return `${s}${f1(Math.abs((Math.exp(g / 100) - 1) * 100))} % ${obj === "damage" ? "dégâts" : "PV eff."}`;
}

function forgeParams() {
  if (!FORGE.params) {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem("wakfu-optimizer:forge") || "{}"); } catch (e) { /* stockage indisponible */ }
    FORGE.params = { ...FORGE_DEFAULT, ...saved };
  }
  return FORGE.params;
}
function saveForgeParams() {
  try { localStorage.setItem("wakfu-optimizer:forge", JSON.stringify(FORGE.params)); } catch (e) { /* sans effet */ }
}

// ===================================================================== page
function forgeShell() {
  return `<div class="forge">
    <div class="fg-bg" aria-hidden="true"><i></i><i></i><i></i></div>
    <header class="fg-head card">${FG_SIGIL}
      <div><h2>Build sombre <span class="fg-sub">forge de combos de sublimations</span></h2>
        <p class="hint">Les items, runes et aptitudes ne bougent pas : seules les sublimations changent. La forge cherche les sublimations
          qui valent plus <b>ensemble</b> que séparément (Dénouement et le critique qui le déclenche, Mesure et la parade…), celles qu'un
          choix une par une ne trouve pas.</p></div></header>
    <div class="fg-layout">
      <aside class="card fg-params">
        <h3>Emplacements</h3>
        <div class="seg three" id="fg-mode"><button data-v="colors">Couleurs actuelles</button><button data-v="recolor">Recolorer</button><button data-v="dream">Rêve</button></div>
        <p class="hint" id="fg-mode-hint"></p>
        <h3>Objectif</h3>
        <div class="seg three" id="fg-objective"><button data-v="score">Score</button><button data-v="damage">Dégâts</button><button data-v="survival">Survie</button></div>
        <p class="hint" id="fg-obj-hint"></p>
        <h3>Pivot</h3>
        <select id="fg-pivot"><option value="0">Aucun : la forge choisit</option></select>
        <p class="hint">Sublimation présente dans chaque combo : la forge construit autour.</p>
        <h3>Sublimations spéciales</h3>
        <div class="chips"><button class="toggle plain" id="fg-epic" type="button">★ Épique</button><button class="toggle plain" id="fg-relic" type="button">★ Relique</button></div>
        <h3>Intensité</h3>
        <div class="seg three" id="fg-intensity"><button data-v="fast" title="Faisceau de 8 combos, 4 s max">Rapide</button><button data-v="normal" title="Faisceau de 16 combos, 10 s max">Normale</button><button data-v="deep" title="Faisceau de 32 combos, 25 s max">Profonde</button></div>
        <h3>Combos proposés</h3>
        <div class="seg three" id="fg-diversity"><button data-v="2" title="Au moins 2 familles différentes entre deux combos">Variantes</button><button data-v="3" title="Au moins 3 familles différentes entre deux combos">Différents</button><button data-v="4" title="Au moins 4 familles différentes entre deux combos">Très différents</button></div>
        <div id="fg-top-box"></div>
        <h3>Garde-fous</h3>
        <label class="check"><input type="checkbox" id="fg-keepmin"><span>PA / PM jamais sous les minimums</span></label>
        <label class="check"><input type="checkbox" id="fg-cond"><span>Compter les conditions « PV &gt; 90 % » et « sans armure »</span></label>
        <label class="check"><input type="checkbox" id="fg-confirmed"><span>Seulement les sublimations confirmées</span></label>
        <p class="hint">Les sublimations exclues dans l'onglet Sublimations ne sont jamais utilisées.</p>
        <button class="btn fg-go" id="fg-go" type="button">Invoquer les combos</button>
      </aside>
      <section class="fg-out" id="fg-out"></section>
    </div></div>`;
}

function bindForge() {
  const p = forgeParams();
  $("#fg-top-box").appendChild(stepper("fg-top", "Nombre de combos", null, 3, 10));
  ["fg-mode", "fg-objective", "fg-intensity", "fg-diversity"].forEach(seg);
  const map = { "fg-mode": "mode", "fg-objective": "objective", "fg-intensity": "intensity", "fg-diversity": "diversity" };
  for (const [id, key] of Object.entries(map)) {
    $("#" + id).addEventListener("change", () => {
      p[key] = key === "diversity" ? +segVal(id) : segVal(id);
      saveForgeParams();
      forgeHints();
    });
  }
  ["epic", "relic"].forEach((k) => $("#fg-" + k).addEventListener("click", () => {
    p[k] = !p[k]; toggleBtn($("#fg-" + k), p[k]); saveForgeParams(); sfx("click");
  }));
  const checks = { "fg-keepmin": "keep_minimums", "fg-cond": "conditional", "fg-confirmed": "confirmed_only" };
  for (const [id, key] of Object.entries(checks)) $("#" + id).addEventListener("change", (e) => { p[key] = e.target.checked; saveForgeParams(); });
  $("#fg-top").addEventListener("change", () => { p.top = +$("#fg-top").value; saveForgeParams(); });
  $("#fg-pivot").addEventListener("change", () => { p.pivot = +$("#fg-pivot").value; saveForgeParams(); });
  $("#fg-go").addEventListener("click", runForge);
  $("#fg-out").addEventListener("click", forgeClick);
}

function syncForgeParams() {
  const p = forgeParams();
  setSeg("fg-mode", p.mode); setSeg("fg-objective", p.objective); setSeg("fg-intensity", p.intensity); setSeg("fg-diversity", String(p.diversity));
  toggleBtn($("#fg-epic"), p.epic); toggleBtn($("#fg-relic"), p.relic);
  $("#fg-keepmin").checked = p.keep_minimums; $("#fg-cond").checked = p.conditional; $("#fg-confirmed").checked = p.confirmed_only;
  $("#fg-top").value = p.top;
  forgeHints();
}
function forgeHints() {
  const p = forgeParams();
  $("#fg-mode-hint").textContent = FG_MODE_HINT[p.mode];
  $("#fg-obj-hint").textContent = FG_OBJ_HINT[p.objective];
  $("#fg-go").disabled = FORGE.busy || !S.view;
}

// Familles possibles comme pivot : celles dont l'effet est chiffré (catalogue de l'onglet Sublimations, sans build)
async function loadForgeFamilies() {
  const o = S.opts || options();
  const key = `${o.class_key}|${o.level}|${(o.elements || []).join(",")}|${o.range}`;
  if (FORGE.families && FORGE.famKey === key) return fillPivot();
  try {
    FORGE.families = (await api("/api/subs", { opts: o, build: null })).filter((f) => f.modeled && f.applicable);
    FORGE.famKey = key;
    fillPivot();
  } catch (e) { /* le pivot reste « Aucun » */ }
}
function fillPivot() {
  const p = forgeParams(), sel = $("#fg-pivot");
  const groups = [["normal", "Normales"], ["epic", "Épiques"], ["relic", "Reliques"]];
  sel.innerHTML = `<option value="0">Aucun : la forge choisit</option>` + groups.map(([k, label]) => {
    const fs = FORGE.families.filter((f) => f.kind === k).sort((a, b) => a.name.localeCompare(b.name));
    return fs.length ? `<optgroup label="${label}">${fs.map((f) => `<option value="${f.state}">${esc(f.name)}</option>`).join("")}</optgroup>` : "";
  }).join("");
  if (!FORGE.families.some((f) => f.state === p.pivot)) p.pivot = 0;
  sel.value = String(p.pivot);
}

function renderForge() {
  const page = $("#tab-forge");
  if (!page.dataset.ready) { page.innerHTML = forgeShell(); bindForge(); page.dataset.ready = "1"; }
  syncForgeParams();
  loadForgeFamilies();
  if (!FORGE.busy) renderForgeOut();
}

// ===================================================================== calcul
async function runForge() {
  if (FORGE.busy || !S.view) return;
  const p = forgeParams();
  const params = { mode: p.mode, objective: p.objective, epic: p.epic, relic: p.relic, pivot: p.pivot, top: p.top,
    diversity: p.diversity, keep_minimums: p.keep_minimums, conditional: p.conditional, confirmed_only: p.confirmed_only,
    ...INTENSITY[p.intensity] };
  FORGE.busy = true;
  forgeHints();
  sfx("start");
  const t0 = performance.now(), limit = params.time_limit * 1000;
  $("#fg-out").innerHTML = `<div class="card fg-loading">${FG_SIGIL}<div class="fg-phase" id="fg-phase">${FG_PHASES[0][1]}</div>
    <div class="fg-pbar"><span id="fg-pfill"></span></div><small class="muted">${params.time_limit} s au plus</small></div>`;
  clearInterval(FORGE.timer);
  FORGE.timer = setInterval(() => {
    const x = Math.min(0.97, (performance.now() - t0) / limit);
    const fill = $("#fg-pfill"), ph = $("#fg-phase");
    if (fill) fill.style.width = `${(100 * x).toFixed(1)}%`;
    if (ph) ph.textContent = [...FG_PHASES].reverse().find(([at]) => x >= at)[1];
  }, 120);
  const build = S.view.build;
  try {
    FORGE.res = await api("/api/forge", { opts: S.opts || options(), build, params });
    FORGE.sel = 0;
    FORGE.buildKey = JSON.stringify(build);
    sfx(FORGE.res.combos.length ? "done" : "fail");
  } catch (e) {
    FORGE.res = null;
    toast("Erreur : " + e.message);
    sfx("fail");
  } finally {
    clearInterval(FORGE.timer);
    FORGE.busy = false;
    forgeHints();
    renderForgeOut();
    updateForgeBadge();
  }
}
function updateForgeBadge() {
  const b = $("#forge-badge"), r = FORGE.res;
  const best = r && r.combos[0];
  b.classList.toggle("hidden", !best);
  if (best) { b.textContent = best.vs_current > 0.05 ? `+${f1(best.vs_current)}` : "="; b.className = `badge ${best.vs_current > 0.05 ? "okb" : ""}`; }
}

// ===================================================================== résultats
function renderForgeOut() {
  const out = $("#fg-out"), r = FORGE.res;
  if (!S.view) {
    out.innerHTML = `<div class="card fg-empty">${FG_SIGIL}<p>Lancez d'abord une optimisation : le build sombre garde ses items et ne joue que sur les sublimations.</p></div>`;
    return;
  }
  if (!r) {
    out.innerHTML = `<div class="card fg-empty">${FG_SIGIL}<p>Réglez le rituel, puis <b>Invoquer les combos</b>.</p>
      <ol class="fg-steps"><li><b>Solo</b> — chaque sublimation seule sur le build nu.</li>
        <li><b>Duos</b> — chaque paire de familles : ce qu'elles valent ensemble, moins ce qu'elles valent seules = leur synergie.</li>
        <li><b>Faisceau</b> — les combos grandissent une sublimation à la fois ; les meilleurs survivent à chaque étape.</li>
        <li><b>Descente</b> — on retire, ajoute ou échange une sublimation tant que ça rapporte, puis on enlève le poids mort.</li></ol></div>`;
    return;
  }
  const stale = FORGE.buildKey !== JSON.stringify(S.view.build)
    ? `<div class="note fg-note">Le build a changé depuis ce calcul : relancez pour des combos à jour.</div>` : "";
  const msgs = r.messages.map((m) => `<div class="note fg-note">${esc(m)}</div>`).join("");
  if (!r.combos.length) {
    out.innerHTML = `${stale}${msgs}<div class="card fg-empty">${FG_SIGIL}<p>Aucun combo ne rapporte sur ce build avec ces réglages.</p></div>${forgeSearch(r)}`;
    return;
  }
  const best = r.combos[0], cb = r.combos[FORGE.sel] || best;
  out.innerHTML = `${stale}${msgs}
    <div class="fg-tiles">
      <div class="fg-tile"><span class="muted">Build actuel</span><b>${fgGain(r.current - r.bare)}</b><small class="muted">sublimations de l'optimiseur, face au build nu</small></div>
      <div class="fg-tile hot"><span class="muted">Meilleur combo</span><b>${fgGain(best.value - r.bare)}</b><small class="muted">face au build nu</small></div>
      <div class="fg-tile ${best.vs_current > 0.05 ? "win" : best.vs_current < -0.05 ? "lose" : ""}"><span class="muted">Face au build actuel</span>
        <b>${fgGain(best.vs_current)}</b><small class="muted">${best.vs_current > 0.05 ? "la forge fait mieux" : best.vs_current < -0.05 ? "l'optimiseur fait mieux" : "à égalité"}</small></div>
    </div>
    ${forgeHero(cb, r)}
    <div class="fg-grid">
      <section class="card"><h2>Classement</h2>${forgeRanking(r)}</section>
      <section class="card"><h2>Constellation des synergies</h2>${forgeMatrix(r)}</section>
      <section class="card"><h2>Duos</h2>${forgeDuos(r)}</section>
      <section class="card"><h2>Valeur seule</h2>${forgeSolo(r)}</section>
    </div>
    ${forgeSearch(r)}`;
}

function levelPips(level, limit) {
  const top = Math.max(limit || level, level);
  if (top <= 1) return "";
  return `<span class="fg-pips" title="Niveau cumulé ${level} / ${top}">${Array.from({ length: top }, (_, i) => `<i class="${i < level ? "on" : ""}"></i>`).join("")}</span>`;
}
function subIcon(gfx, cls = "fg-ic") {
  return `<img class="${cls}" src="${iconUrl(gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
}

function forgeHero(cb, r) {
  const scale = Math.max(0.01, ...cb.parts.map((p) => Math.max(Math.abs(p.solo), Math.abs(p.marginal))));
  const w = (v) => `${(100 * Math.abs(v) / scale).toFixed(1)}%`;
  const parts = cb.parts.map((p) => {
    const [cls, why] = FG_ROLE[p.role] || ["r-extra", ""];
    const places = p.subs.map((s) => `<span class="fg-place ${s.recolored ? "recol" : ""}" title="${esc(s.name)}${s.recolored ? " — châsses recolorées" : ""}">
        ${s.host.gfx ? subIcon(s.host.gfx, "fg-it") : `<span class="fg-it ghost">?</span>`}<span>${esc(s.host.slot_name)}</span>
        ${s.pattern.length ? `<span class="fg-pat">${patternHtml(s.pattern)}</span><small>${esc((s.name.match(/\s([IVX]+)$/) || ["", ""])[1])}</small>` : ""}</span>`).join("");
    const conds = p.conditions.map((c) => `<span class="fg-cond ${c.ok ? "ok" : "ko"}" title="Valeur dans le combo : ${c.value}">${c.ok ? "✓" : "✗"} ${esc(c.label)}
        <small>${c.value} · marge ${c.margin >= 0 ? "+" : ""}${c.margin}</small></span>`).join("");
    return `<div class="fg-part ${cls}">
      <div class="fg-icbox">${subIcon(p.gfx)}${p.kind !== "normal" ? `<span class="fg-kind ${p.kind}" title="${p.kind === "epic" ? "Épique" : "Relique"}">★</span>` : ""}</div>
      <div class="fg-pmain">
        <div class="fg-pname"><b title="${esc(p.desc)}">${esc(p.name)}</b>${levelPips(p.level, p.limit)}<span class="fg-role" title="${esc(why)}">${esc(p.role)}</span>
          ${p.confirmed ? "" : `<span class="tag" title="Pas encore confirmée : description, niveaux et effets à vérifier">non confirmée</span>`}</div>
        <div class="fg-places">${places}</div>${conds ? `<div class="fg-conds">${conds}</div>` : ""}
      </div>
      <div class="fg-bars" title="Seule : ce qu'elle rapporte sur le build nu. Dans le combo : ce que coûte son retrait.">
        <div class="fg-bar"><span class="solo ${p.solo < 0 ? "neg" : ""}" style="width:${w(p.solo)}"></span></div>
        <div class="fg-bar"><span class="marg" style="width:${w(p.marginal)}"></span></div>
        <small><span class="muted">seule</span> ${fgGain(p.solo)} · <span class="muted">dans le combo</span> <b>${fgGain(p.marginal)}</b></small>
      </div></div>`;
  }).join("");
  const s = cb.stats;
  const keyStats = [["ap", "PA", s.ap], ["mp", "PM", s.mp], ["crit_rate", "% Critique", `${s.crit_rate} %`], ["dmg_pct", "% Dommages infligés", `${s.dmg_pct} %`],
    ["block", "% Parade", `${s.block} %`], ["elem_mastery", "Maîtrise utilisée", fmt(cb.mastery_used)], ["hp", "PV", fmt(cb.hp)], ["willpower", "Volonté", s.willpower]]
    .map(([k, l, v]) => `<span class="fg-ks">${icon(k, l)}<b>${v}</b><small>${esc(l)}</small></span>`).join("");
  const syn = cb.synergy;
  const runes = cb.runes_changed.length ? `<details class="fg-det"><summary>Runes replacées (${cb.runes_changed.length} item(s))</summary>
      ${cb.runes_changed.map((x) => `<div class="fg-rune"><b>${esc(x.slot_name)}</b> <span class="muted">${esc(x.before || "aucune")}</span> → ${esc(x.after || "aucune")}</div>`).join("")}</details>` : "";
  const rank = r.combos.indexOf(cb) + 1;
  return `<section class="card fg-hero">
    <div class="fg-hero-head"><span class="fg-rank">#${rank}</span>
      <div class="fg-title"><h2>${esc(cb.name)}</h2>
        <div class="fg-tags"><span class="tag">${cb.parts.length} familles · ${cb.parts.reduce((t, p) => t + p.subs.length, 0)} sublimations</span>
          <span class="tag ${syn > 0.05 ? "syn-pos" : syn < -0.05 ? "syn-neg" : ""}" title="Gain du combo moins la somme des gains de chaque famille seule. Négatif : plusieurs sublimations nourrissent la même stat (rendement décroissant) ; positif : elles se renforcent.">synergie ${syn > 0 ? "+" : ""}${f1(syn)}</span>
          ${cb.build ? `<span class="tag on">applicable</span>` : `<span class="tag">théorique</span>`}
          ${cb.recolored.length ? `<span class="tag" title="${esc(cb.recolored.join(", "))}">${cb.recolored.length} item(s) recoloré(s)</span>` : ""}
          ${Math.abs(cb.estimate - cb.value) > 0.05 ? `<span class="tag" title="Valeur estimée par la recherche, avant de replacer les runes">estimé : ${fgGain(cb.estimate - r.bare)}</span>` : ""}</div></div>
      <div class="fg-big"><b>${fgGain(cb.value - r.bare)}</b><small>${fgGain(cb.vs_current)} face au build actuel</small></div></div>
    <div class="fg-legend"><span><i class="solo"></i>seule</span><span><i class="marg"></i>dans le combo</span>
      ${Object.entries(FG_ROLE).map(([k, [c, why]]) => `<span class="fg-role ${c}" title="${esc(why)}">${esc(k)}</span>`).join("")}</div>
    <div class="fg-anat">${parts}</div>
    <div class="fg-keys">${keyStats}<span class="fg-ks">${icon("score", "Dégâts")}<b>×${f1(cb.damage)}</b><small>Dégâts</small></span></div>
    ${runes}
    <details class="fg-det"><summary>Ce que le combo apporte (face au build sans sublimation)</summary>
      <table class="cmp-table">${CMP_HEAD.replace("Actuel", "Sans subli.").replace("Nouveau", "Combo")}${cmpRows(cb.compare)}</table></details>
    <div class="fg-actions">
      <button class="btn good" data-fg="apply" ${cb.build ? "" : "disabled title=\"Mode Rêve : le combo n'a pas d'emplacement réel sur ce build\""}>Appliquer au build</button>
      <button class="btn" data-fg="impose" title="Impose ces sublimations (et leurs niveaux) à la prochaine optimisation, à la place des sublimations imposées actuelles">Imposer à l'optimiseur</button>
      <button class="btn" data-fg="copy" title="Copier le combo en texte">📋 Copier</button></div>
  </section>`;
}

function forgeRanking(r) {
  const best = Math.max(0.01, ...r.combos.map((c) => c.value - r.bare));
  return `<div class="fg-rankl">${r.combos.map((c, i) => `<button class="fg-row ${i === FORGE.sel ? "on" : ""}" data-fgsel="${i}" type="button">
      <span class="fg-n">${i + 1}</span>
      <span class="fg-rn"><b>${esc(c.name)}</b><span class="fg-icons">${c.parts.map((p) => `<span title="${esc(p.name)} ${p.level}">${subIcon(p.gfx, "fg-mini")}</span>`).join("")}</span></span>
      <span class="fg-rv"><span class="fg-bar"><span class="marg" style="width:${(100 * Math.max(0, c.value - r.bare) / best).toFixed(1)}%"></span></span>
        <small>${fgGain(c.value - r.bare)} · <span class="${pn(c.vs_current)}">${fgGain(c.vs_current)}</span></small></span></button>`).join("")}</div>
    <p class="hint">Gain face au build nu · écart avec le build actuel. Cliquez un combo pour l'afficher en grand.</p>`;
}

function forgeMatrix(r) {
  const m = r.matrix, n = m.states.length;
  if (n < 2) return `<p class="muted">Pas assez de familles pour comparer.</p>`;
  const vals = m.cells.flat().filter((v) => v != null);
  const mx = Math.max(0.5, ...vals.map(Math.abs));
  const cell = (v, a, b) => {
    if (a === b) return `<span class="fg-cell self"></span>`;
    if (v == null) return `<span class="fg-cell none" title="${esc(m.states[a].name)} + ${esc(m.states[b].name)} : impossibles ensemble"></span>`;
    const x = Math.min(1, Math.abs(v) / mx);
    return `<span class="fg-cell ${v >= 0 ? "pos" : "neg"}" style="--x:${(0.12 + 0.88 * x).toFixed(2)}"
      title="${esc(m.states[a].name)} + ${esc(m.states[b].name)} : synergie ${v > 0 ? "+" : ""}${f1(v)}"></span>`;
  };
  const head = `<span></span>` + m.states.map((s) => `<span class="fg-mh" title="${esc(s.name)}">${subIcon(s.gfx, "fg-mini")}</span>`).join("");
  const rows = m.states.map((s, a) => `<span class="fg-ml" title="${esc(s.desc)}">${subIcon(s.gfx, "fg-mini")}<span>${esc(s.name)}</span></span>`
    + m.cells[a].map((v, b) => cell(v, a, b)).join("")).join("");
  return `<div class="fg-matrix" style="grid-template-columns: minmax(70px, 160px) repeat(${n}, minmax(0, 1fr))">${head}${rows}</div>
    <p class="hint"><span class="fg-sw pos"></span> se renforcent · <span class="fg-sw neg"></span> se marchent dessus (même stat, rendement décroissant)
      · <span class="fg-sw none"></span> impossibles ensemble. Duo = les deux au plus haut niveau d'une sublimation.</p>`;
}

function forgeDuos(r) {
  const pos = r.duos.filter((d) => d.synergy > 0), neg = r.duos.filter((d) => d.synergy < 0);
  const line = (d) => `<div class="fg-duo ${d.synergy > 0 ? "pos" : "neg"}">${subIcon(d.a.gfx, "fg-mini")}<span>${esc(d.a.name)}</span><span class="muted">+</span>
    ${subIcon(d.b.gfx, "fg-mini")}<span>${esc(d.b.name)}</span><b>${d.synergy > 0 ? "+" : ""}${f1(d.synergy)}</b></div>`;
  return `<h3>Complices</h3>${pos.map(line).join("") || `<p class="muted">Aucune paire ne vaut plus que la somme de ses parts sur ce build.</p>`}
    <h3>Rivales</h3>${neg.map(line).join("") || `<p class="muted">Aucune.</p>`}
    <p class="hint">Synergie d'un duo = gain des deux ensemble − gain de chacune seule.</p>`;
}

function forgeSolo(r) {
  const mx = Math.max(0.01, ...r.solo.map((s) => Math.abs(s.gain)));
  return r.solo.map((s) => `<div class="fg-solo" title="${esc(s.desc)}">${subIcon(s.gfx, "fg-mini")}<span>${esc(s.name)}</span>
      <span class="fg-bar"><span class="solo ${s.gain < 0 ? "neg" : ""}" style="width:${(100 * Math.abs(s.gain) / mx).toFixed(1)}%"></span></span>
      <b class="${pn(s.gain)}">${fgGain(s.gain)}</b></div>`).join("")
    + `<p class="hint">Chaque famille seule sur le build nu, à son meilleur niveau d'une sublimation.</p>`;
}

function forgeSearch(r) {
  const s = r.search, total = Math.max(0.01, s.phases.reduce((t, p) => t + p.time, 0));
  return `<div class="fg-search card"><div class="fg-timeline">${s.phases.map((p) => `<span style="flex:${Math.max(0.02, p.time / total)}"
      title="${esc(p.name)} : ${f1(p.time)} s · ${fmt(p.evals)} évaluations">${esc(p.name)}</span>`).join("")}</div>
    <p class="muted">${fmt(s.evals)} combinaisons évaluées en ${f1(s.elapsed)} s${s.timed_out ? " (durée max atteinte)" : ""} · ${s.pieces} sublimations candidates
      · ${s.hosts} items à châsses · ${s.specials} emplacement(s) épique ou relique</p></div>`;
}

// ===================================================================== actions
function forgeClick(e) {
  const sel = e.target.closest("[data-fgsel]");
  if (sel) { FORGE.sel = +sel.dataset.fgsel; sfx("click"); renderForgeOut(); $(".fg-hero").scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  const act = e.target.closest("[data-fg]");
  if (!act || act.disabled) return;
  const cb = FORGE.res.combos[FORGE.sel];
  if (act.dataset.fg === "apply") forgeApply(cb);
  if (act.dataset.fg === "impose") forgeImpose(cb);
  if (act.dataset.fg === "copy") {
    const lines = [`Build sombre — ${cb.name} (${fgGain(cb.value - FORGE.res.bare)})`].concat(cb.parts.map((p) =>
      `- ${p.name} ${p.level}${p.limit ? `/${p.limit}` : ""} : ${p.subs.map((s) => `${s.name} (${s.host.slot_name})`).join(", ")}`));
    navigator.clipboard.writeText(lines.join("\n")).then(() => toast("Combo copié."));
  }
}

async function forgeApply(cb) {
  try {
    const v = await api("/api/view", { opts: S.opts, build: cb.build });
    const before = S.view.build.slots;
    for (const [slot, ch] of Object.entries(v.build.slots)) {
      const b = before[slot];
      if (!b || b.sublimation_id !== ch.sublimation_id || b.special_sublimation_id !== ch.special_sublimation_id
        || JSON.stringify(b.shards) !== JSON.stringify(ch.shards)) S.changed.add(slot);
    }
    S.view = v;
    renderResult();
    showTab("build");
    sfx("apply");
    toast("Combo appliqué au build (« Revenir au build optimisé » pour l'annuler).");
  } catch (e) { toast("Erreur : " + e.message); }
}

function forgeImpose(cb) {
  S.subForced = new Set(Object.keys(cb.forced).map(Number));
  S.subLevels = {};
  for (const [s, lvl] of Object.entries(cb.forced)) {
    S.subExcluded.delete(+s);
    if (lvl > 1) S.subLevels[+s] = lvl;
  }
  updateSubsBadge();
  if (subsCache) renderSubs();
  sfx("apply");
  toast(`${S.subForced.size} sublimation(s) imposée(s) à la place des précédentes : relancez l'optimisation.`);
}
