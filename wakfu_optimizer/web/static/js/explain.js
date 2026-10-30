"use strict";
// Onglet Explication (outil de débogage du calcul).

// ===================================================================== objectifs du niveau
// Résistance visée à ce niveau (par élément), maîtrise de portée ajoutée à chaque élément, palier de critique.
const pctFr = (n) => `${String(n).replace(".", ",")} %`;
function renderTargets(x) {
  const t = x.targets;
  if (!t) return "";
  const r = t.res, arch = esc(x.archetype.name);
  let resWhy;
  if (r.mine) resWhy = "Votre réglage (panneau Priorités activé).";
  else if (r.lowered) resWhy = `L'archétype vise ${r.wanted} % à ce niveau, impossible ici : visée abaissée au maximum atteignable.`;
  else if (r.free) resWhy = `Un ${arch} vise ${r.full} % à tout niveau, et la résistance compte encore au-delà.`;
  else if (r.scaled && x.level < r.full_level) resWhy = `Les dégâts reçus montent avec le niveau : un ${arch} vise ${r.target} % au niveau ${x.level}, `
    + `${r.full} % à partir du niveau ${r.full_level}.`;
  else resWhy = `Un ${arch} vise ${r.target} % à partir du niveau ${r.full_level}.`;
  const resTiles = r.elements.map((e) => `<div class="xtile ${e.ok ? "ok" : "bad"}" style="--ec:var(--${e.key})" title="${fmt(e.flat)} de résistance fixe">
      ${icon(`${e.key}_res`, `Résistance ${e.name}`)}<span class="xtn">${esc(e.name)}</span><b>${pctFr(e.pct)}</b>
      <span class="xtbar"><span style="width:${Math.min(100, (100 * e.pct) / Math.max(1, r.target)).toFixed(0)}%"></span></span>
      <small class="muted">${e.ok ? "✓" : `✗ ${r.floor - e.pct} % manquant${r.floor - e.pct > 1 ? "s" : ""}`}</small></div>`).join("");
  const res = r.target ? `<div class="xtarget">
      <h3>${icon("elem_res", "Résistances")} Résistances : au moins ${pctFr(r.floor)} sur chaque élément <span class="muted">(${pctFr(r.target)} visé, ± ${r.tol})</span></h3>
      <p class="hint">${resWhy} Sous ${pctFr(r.floor)}, chaque point de résistance manquant coûte au score ; entre ${pctFr(r.floor)} et ${pctFr(r.target)}, aucun malus${r.free ? "."
        : ` ; au-delà de ${pctFr(r.floor)}, la résistance ne rapporte plus rien : le reste part dans les autres stats${x.weights.some((w) => w.stat === "dmg_pct" && w.pts >= 0.95) ? " (ici, les maîtrises)" : ""}.`}</p>
      <div class="xtiles">${resTiles}</div></div>`
    : `<div class="xtarget"><h3>${icon("elem_res", "Résistances")} Résistances : aucune visée</h3></div>`;

  let mast = "";
  const m = t.mastery;
  if (m) {
    const rngTxt = m.range === "mixed" ? `Moitié mêlée, moitié distance : (${fmt(m.parts[0].value)} + ${fmt(m.parts[1].value)}) / 2 = ${fmt(m.range_value)}.`
      : m.range === "best" ? `La meilleure des deux compte (passif de classe) : ${fmt(m.range_value)}.` : "";
    const extra = m.extra.filter((e) => e.value).map((e) => ` + ${icon(e.stat, e.label)} ${fmt(e.value)}`).join("");
    const parts = m.parts.map((p) => `${icon(p.stat, p.label)} ${esc(p.label)} <b>${fmt(p.value)}</b>`).join(" · ");
    const tiles = m.elements.map((e) => `<div class="xtile ${e.played ? "" : "unplayed"} ${e.weakest ? "used" : ""}" style="--ec:var(--${e.key})"
        title="${e.played ? `Élément joué, priorité ${e.rank}${e.weakest && m.multi ? " ; le plus faible : il compte pour moitié" : ""}` : "Élément non joué"}">
      ${icon(`${e.key}_mastery`, `Maîtrise ${e.name}`)}<span class="xtn">${esc(e.name)}</span><b>${fmt(e.total)}</b>
      <small class="muted">${fmt(e.elem)} + ${fmt(m.range_value)}${extra ? " + …" : ""}</small>
      <small class="${e.rank === 1 ? "rec" : "muted"}">${!e.played ? "non jouée" : m.multi ? `priorité ${e.rank}${e.weakest ? " · la plus faible" : ""}` : "★ utilisée"}</small></div>`).join("");
    mast = `<div class="xtarget">
      <h3>${icon(m.range === "melee" ? "melee_mastery" : "distance_mastery", "Maîtrise de portée")} Maîtrise de portée : +${fmt(m.range_value)} dans chaque élément</h3>
      <p class="hint">${parts}. Elle s'ajoute à tous vos sorts${m.range === "melee" ? " au corps-à-corps" : m.range === "distance" ? " à distance" : ""},
        quel que soit leur élément : le calcul la compte comme autant de maîtrise dans chacun des éléments. ${rngTxt}</p>
      <div class="xtiles">${tiles}</div>
      <p class="hint">Maîtrise utilisée par le calcul : <b>${fmt(m.used)}</b> = ${m.multi ? "moitié l'élément joué le plus faible, moitié la moyenne des éléments joués selon leur priorité (poids 3, 2, 1…)" : "élément joué"} + portée${extra}.</p></div>`;
  }
  const c = t.crit;
  const crit = c ? `<div class="xtarget"><h3>${icon("crit_rate", "Critique")} Critique : palier de ${pctFr(c.target)} au niveau ${x.level}
      <span class="${c.value >= c.target ? "rec" : "neg"}">(vous : ${pctFr(c.value)})</span></h3>
      <p class="hint">Ce que les joueurs atteignent à ce niveau ; chaque % manquant coûte au score.</p></div>` : "";
  return `<section class="card xwide"><h2>Objectifs au niveau ${x.level}</h2>${res}${mast}${crit}</section>`;
}

// ===================================================================== onglet Explication
// Ce que l'algorithme a privilégié pour ce personnage et cet archétype (outil de débogage), mis à jour à chaque calcul.
function renderExplain() {
  const x = S.explain, page = $("#tab-explain");
  const tab = $('.tab[data-tab="explain"]'), badge = $("#explain-badge");
  tab.disabled = !x;
  if (!x) {
    page.innerHTML = `<div class="card empty-explain muted">Lancez une optimisation : cet onglet expliquera ce que le calcul a privilégié.</div>`;
    badge.classList.add("hidden");
    return;
  }
  const bad = x.checks.filter((c) => !c.ok && c.severity === "error");
  badge.textContent = bad.length ? `${bad.length} ⚠` : "✓";
  badge.className = `badge ${bad.length ? "warnb" : "okb"}`;
  const src = (v) => `<span class="src-tag ${v === "vos réglages" ? "mine" : "arch"}">${esc(v)}</span>`;
  const panels = x.panels.map((p) => `<span class="src-tag ${p.on ? "mine" : "arch"}">${esc(p.name)} : ${p.on ? "vos réglages" : "archétype"}</span>`).join("");
  const settings = x.settings.map((r) => `<tr><td>${esc(r.label)}</td><td>${esc(r.value)}</td><td>${src(r.src)}</td></tr>`).join("");
  const maxM = Math.max(0.01, ...x.marginals.map((m) => Math.abs(m.points)));
  const marg = [...x.marginals].filter((m) => m.points).sort((a, b) => b.points - a.points).map((m) =>
    `<div class="xbar"><span class="xl">${esc(m.label)} <small class="muted">${esc(m.unit)}</small></span>
      <span class="xt"><span class="xf ${m.points < 0 ? "neg" : ""}" style="width:${(100 * Math.abs(m.points) / maxM).toFixed(1)}%"></span></span>
      <b class="${m.points < 0 ? "neg" : ""}">${m.points > 0 ? "+" : ""}${m.points.toFixed(2)}</b></div>`).join("")
    || `<p class="muted">Aucune stat ne fait plus progresser le score.</p>`;
  const score = x.score.map((r) => `<tr><td>${esc(r.label)}</td><td class="num ${r.points < 0 ? "neg" : ""}">${r.points.toFixed(2)}</td></tr>`).join("");
  const checks = x.checks.map((c) => `<li class="${c.ok ? "ok" : c.severity}"><span class="ck">${c.ok ? "✓" : c.severity === "warn" ? "!" : "✗"}</span>
      <span><b>${esc(c.label)}</b> <span class="muted">— ${esc(c.detail)}</span></span></li>`).join("");
  page.innerHTML = `
  <div class="explain">
    <section class="card xhead">
      <div><h2>${esc(x.archetype.name)} ${x.archetype.recommended ? '<span class="src-tag rec">★ habituel pour la classe</span>' : '<span class="src-tag warnt">peu joué avec cette classe</span>'}</h2>
        <p class="muted els">${esc(x.class)} niveau ${x.level} · ${x.element_keys.map((e) => icon(e, EL_FR[e])).join("")}</p>
        <div class="xfocus"><span class="muted">Priorité :</span>${(x.archetype.focus || []).map((f, i) =>
          `${i ? `<span class="muted">›</span>` : ""}<span class="xw boost">${icon(f.stat, f.label)}<span>${esc(f.label)}</span></span>`).join("")}</div></div>
      <div class="xpanels">${panels}</div>
    </section>
    ${renderTargets(x)}
    <div class="xgrid">
      <section class="card"><h2>Réglages utilisés par le calcul</h2>
        <table class="xtable">${settings}</table>
        <p class="hint">« archétype » : valeur fixée par l'archétype (panneau désactivé ou poids internes) ; « vos réglages » : panneau activé.</p></section>
      <section class="card"><h2>Ce que vaut un gain, au build final</h2>
        <p class="hint">Points de score gagnés pour chaque gain (1 point ≈ 1 % de valeur globale). Plus la barre est longue, plus le calcul
          privilégie cette stat à ce stade ; une stat à 0 est déjà au plafond ou ne compte pas pour l'archétype.</p>
        ${marg}</section>
      <section class="card"><h2>Composition du score</h2>
        <table class="xtable">${score}<tr class="tot"><td>Total</td><td class="num">${x.total.toFixed(2)}</td></tr></table>
        <p class="hint">Dégâts et survie sont des logarithmes pondérés par le poids attaque / défense ; les pénalités sont négatives.</p></section>
      <section class="card"><h2>Contrôles de qualité</h2><ul class="xchecks">${checks}</ul>
        <p class="hint">Mêmes règles que les tests automatiques (tests/test_build_quality.py).</p></section>
    </div>
  </div>`;
}
