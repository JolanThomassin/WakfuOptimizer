"use strict";
// Onglet Explication (outil de débogage du calcul).

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
  const weights = (x.weights || []).map((w) => `<div class="xw ${w.boosted ? "boost" : ""}" title="${esc(w.unit)}">${icon(w.stat, w.label)}
      <span>${esc(w.label)}</span><b class="${w.pts < 0 ? "neg" : ""}">${w.pts > 0 ? "" : ""}${String(+w.pts.toFixed(2)).replace(".", ",")} pt${Math.abs(w.pts) > 1 ? "s" : ""}</b></div>`).join("");
  const settings = x.settings.map((r) => `<tr><td>${esc(r.label)}</td><td>${esc(r.value)}</td><td>${src(r.src)}</td></tr>`).join("");
  const maxM = Math.max(0.01, ...x.marginals.map((m) => Math.abs(m.points)));
  const marg = [...x.marginals].filter((m) => m.points).sort((a, b) => b.points - a.points).map((m) =>
    `<div class="xbar"><span class="xl">${esc(m.label)} <small class="muted">${esc(m.unit)}</small></span>
      <span class="xt"><span class="xf ${m.points < 0 ? "neg" : ""}" style="width:${(100 * Math.abs(m.points) / maxM).toFixed(1)}%"></span></span>
      <b class="${m.points < 0 ? "neg" : ""}">${m.points > 0 ? "+" : ""}${m.points.toFixed(2)}</b></div>`).join("")
    || `<p class="muted">Aucune stat ne fait plus progresser le score.</p>`;
  const score = x.score.map((r) => `<tr><td>${esc(r.label)}</td><td class="num ${r.points < 0 ? "neg" : ""}">${r.points.toFixed(2)}</td></tr>`).join("");
  const apt = x.aptitudes.map((b) => `<div class="xbranch" style="--bc:${BRANCH_COLOR[b.branch] || "#333"}"><div class="xbh">${esc(b.name)} <span class="muted">${b.total} pt</span></div>`
    + b.lines.map((l, i) => `<div class="xline ${l.points ? "" : "zero"} ${l.in_profile ? "" : "off"}" title="${l.in_profile ? "" : "Ligne non utilisée par l'archétype"}">
        <span class="ic"><img src="assets/aptitudes/${l.line}.png" alt="" onerror="this.src='assets/stats/empty_coin.png'"></span>
        <span class="xll">${l.in_profile ? `${i + 1}.` : "✗"} ${esc(l.label)}${l.forced ? ` <small class="muted" title="Mise au maximum d'office, comme le font les joueurs">· max d'office</small>` : ""}</span>
        <span class="xg ${l.gain > 0 ? "pos" : l.gain < 0 ? "neg" : "muted"}" title="Points de score pour 1 point de plus dans cette ligne${l.full ? " (ligne déjà au maximum)" : ""}">${l.full ? "max" : `${l.gain > 0 ? "+" : ""}${String(l.gain).replace(".", ",")} pt`}</span>
        <b>${l.points}</b></div>`).join("")
    + `</div>`).join("");
  const checks = x.checks.map((c) => `<li class="${c.ok ? "ok" : c.severity}"><span class="ck">${c.ok ? "✓" : c.severity === "warn" ? "!" : "✗"}</span>
      <span><b>${esc(c.label)}</b> <span class="muted">— ${esc(c.detail)}</span></span></li>`).join("");
  page.innerHTML = `
  <div class="explain">
    <section class="card xhead">
      <div><h2>${esc(x.archetype.name)} ${x.archetype.recommended ? '<span class="src-tag rec">★ habituel pour la classe</span>' : '<span class="src-tag warnt">peu joué avec cette classe</span>'}</h2>
        <p class="muted">${esc(x.class)} niveau ${x.level} · ${esc(x.elements.join(", "))}</p>
        <div class="xfocus"><span class="muted">Priorité :</span>${(x.archetype.focus || []).map((f, i) =>
          `${i ? `<span class="muted">›</span>` : ""}<span class="xw boost">${icon(f.stat, f.label)}<span>${esc(f.label)}</span></span>`).join("")}</div></div>
      <div class="xpanels">${panels}</div>
    </section>
    <section class="card"><h2>Poids de chaque stat dans le calcul</h2>
      <div class="xweights">${weights}</div>
      <p class="hint">Points de score par unité (survol : unité) ; 1 point ≈ 1 % de valeur globale. En vert : poids propre à l'archétype.</p></section>
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
      <section class="card xwide"><h2>Aptitudes ${x.manual_apt ? "(les vôtres)" : "(profil de l'archétype)"}</h2>
        <p class="hint">Toutes les lignes, avec ce que rapporte 1 point de plus au build final (points de score). Numérotées : lignes de
          l'archétype, dans l'ordre de remplissage ; « max d'office » : toujours au maximum ; ✗ : lignes que l'archétype n'utilise pas.</p>
        <div class="xapt">${apt}</div></section>
    </div>
  </div>`;
}
