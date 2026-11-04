"use strict";
// Onglet Team Builder : compléter une équipe de 3 ou 6 personnages autour de ceux choisis (engine/team.py, /api/team).

const TEAM = { size: 6, style: "balanced", picks: [], result: null, shown: 0, ready: false };
const ROLE_LABEL = { tank: "Tank", heal: "Soigneur", support: "Support", dps: "DPS" };
const TEAM_STORE = "wakfu-optimizer:team";

function saveTeam() {
  try { localStorage.setItem(TEAM_STORE, JSON.stringify({ size: TEAM.size, style: TEAM.style, picks: TEAM.picks, dup: $("#team-dup").checked })); }
  catch (e) { /* stockage indisponible */ }
}

// Premier affichage de l'onglet : réglages enregistrés, sinon le personnage du panneau de gauche.
function loadTeamTab() {
  if (TEAM.ready || !S.meta) return;
  TEAM.ready = true;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(TEAM_STORE) || "null"); } catch (e) { /* sans effet */ }
  const known = (k) => S.meta.classes.some((c) => c.key === k);
  if (saved && Array.isArray(saved.picks)) {
    TEAM.size = saved.size === 3 ? 3 : 6;
    TEAM.style = ["balanced", "offense", "defense"].includes(saved.style) ? saved.style : "balanced";
    TEAM.picks = saved.picks.filter((p) => p && known(p.class)).slice(0, TEAM.size);
    $("#team-dup").checked = !!saved.dup;
  }
  if (!TEAM.picks.length) TEAM.picks = [{ class: $("#cls").value, archetype: $("#archetype").value }];
  seg("team-size"); seg("team-style");
  setSeg("team-size", String(TEAM.size)); setSeg("team-style", TEAM.style);
  $("#team-size").addEventListener("change", () => {
    TEAM.size = +segVal("team-size");
    if (TEAM.picks.length > TEAM.size) { TEAM.picks = TEAM.picks.slice(0, TEAM.size); toast(`Équipe de ${TEAM.size} : personnages en trop retirés.`); }
    renderTeamPicks(); saveTeam();
  });
  $("#team-style").addEventListener("change", () => { TEAM.style = segVal("team-style"); saveTeam(); });
  $("#team-dup").addEventListener("change", saveTeam);
  $("#team-add").addEventListener("click", () => {
    if (TEAM.picks.length >= TEAM.size) return;
    const used = new Set(TEAM.picks.map((p) => p.class));
    const c = S.meta.classes.find((x) => !used.has(x.key)) || S.meta.classes[0];
    TEAM.picks.push({ class: c.key, archetype: "auto" });
    renderTeamPicks(); saveTeam();
  });
  $("#team-picks").addEventListener("change", (e) => {
    const row = e.target.closest("[data-pick]");
    if (!row) return;
    const p = TEAM.picks[+row.dataset.pick];
    if (e.target.dataset.f === "class") { p.class = e.target.value; p.archetype = "auto"; }
    else p.archetype = e.target.value;
    renderTeamPicks(); saveTeam();
  });
  $("#team-picks").addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]");
    if (!b) return;
    TEAM.picks.splice(+b.dataset.del, 1);
    renderTeamPicks(); saveTeam();
  });
  $("#team-go").addEventListener("click", composeTeam);
  $("#team-out").addEventListener("click", (e) => {
    const alt = e.target.closest("[data-team]");
    if (alt) { TEAM.shown = +alt.dataset.team; renderTeam(); sfx("click"); return; }
    const opt = e.target.closest("[data-opt]");
    if (opt) optimizeMember(+opt.dataset.opt);
  });
  renderTeamPicks();
}

function archOptions(c, value) {
  const recs = classArchs(c);
  const opt = (k) => `<option value="${k}"${k === value ? " selected" : ""}>${recs.includes(k) ? "★ " : ""}${esc(ARCHETYPES[k].name)}</option>`;
  return `<option value="auto"${value === "auto" ? " selected" : ""}>Auto</option>`
    + `<optgroup label="Habituels (${esc(c.name)})">${recs.filter((k) => ARCHETYPES[k]).map(opt).join("")}</optgroup>`
    + `<optgroup label="Autres archétypes">${Object.keys(ARCHETYPES).filter((k) => !recs.includes(k)).map(opt).join("")}</optgroup>`;
}

function renderTeamPicks() {
  $("#team-picks").innerHTML = TEAM.picks.map((p, i) => {
    const c = S.meta.classes.find((x) => x.key === p.class) || S.meta.classes[0];
    return `<div class="team-pick" data-pick="${i}">
      <img class="class-icon" src="assets/classes/${c.key}.png" alt="">
      <div class="team-pick-sel">
        <select data-f="class">${S.meta.classes.map((x) => `<option value="${x.key}"${x.key === c.key ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
        <select data-f="arch">${archOptions(c, ARCHETYPES[p.archetype] ? p.archetype : "auto")}</select>
      </div>
      <button class="btn ghost small" type="button" data-del="${i}" title="Retirer ce personnage">✕</button>
    </div>`;
  }).join("") || `<p class="hint">Aucun personnage : l'équipe entière sera proposée.</p>`;
  $("#team-n").textContent = `${TEAM.picks.length} / ${TEAM.size}`;
  $("#team-add").disabled = TEAM.picks.length >= TEAM.size;
}

async function composeTeam() {
  $("#team-out").innerHTML = `<div class="loading"><div class="spinner"></div>Composition de l'équipe…</div>`;
  try {
    TEAM.result = await api("/api/team", { picks: TEAM.picks, size: TEAM.size, style: TEAM.style, duplicates: $("#team-dup").checked });
    TEAM.shown = 0;
    renderTeam();
    sfx("done");
  } catch (e) {
    $("#team-out").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
    sfx("fail");
  }
}

function roleBadges(roles) {
  return Object.entries(roles).sort((a, b) => b[1] - a[1])
    .map(([r, x]) => `<span class="role-badge r-${r}" title="${x < 1 ? `${ROLE_LABEL[r]} à ${Math.round(x * 100)} %` : ROLE_LABEL[r]}">${ROLE_LABEL[r]}</span>`).join("");
}

function renderTeam() {
  const r = TEAM.result;
  if (!r || !r.teams.length) { $("#team-out").innerHTML = `<p class="muted pad">Aucune équipe trouvée.</p>`; return; }
  const t = r.teams[TEAM.shown] || r.teams[0];
  const tabs = r.teams.length > 1 ? `<div class="seg team-alts" style="grid-template-columns:repeat(${r.teams.length},1fr)">${r.teams.map((x, i) =>
    `<button type="button" data-team="${i}" class="${i === TEAM.shown ? "on" : ""}">${i ? `Alternative ${i}` : "Meilleure équipe"}<small>${x.rel} %</small></button>`).join("")}</div>` : "";
  const members = t.members.map((m, i) => `<div class="card team-member${m.picked ? " picked" : ""}">
      <div class="tm-head">
        <img class="tm-icon" src="assets/classes/${m.class}.png" alt="">
        <div class="tm-name"><b>${esc(m.class_name)}</b><span>${esc(m.arch_name)}${m.usual ? "" : ` <small class="muted">(peu joué)</small>`}</span></div>
        ${m.picked ? `<span class="badge manual" title="${m.auto_arch ? "Votre personnage (archétype choisi pour l'équipe)" : "Votre personnage"}">${m.auto_arch ? "Vous · auto" : "Vous"}</span>` : `<span class="badge">Proposé</span>`}
      </div>
      <div class="tm-roles">${roleBadges(m.roles)}${m.elements.map((e) => `<img class="tm-el" src="assets/stats/${e}_coin.png" alt="" title="${EL_FR[e]}">`).join("")}</div>
      ${m.traits.length ? `<div class="tm-traits">${m.traits.map((x) => `<span class="chip plain">${esc(x)}</span>`).join("")}</div>` : ""}
      ${m.reasons.length ? `<ul class="tm-why">${m.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <button class="btn small" type="button" data-opt="${i}" title="Charge cette classe et cet archétype dans le panneau de gauche et lance l'optimisation">Optimiser ce perso</button>
    </div>`).join("");
  const roles = ["tank", "heal", "support", "dps"].map((k) =>
    `<div class="tm-sum-role"><span class="role-badge r-${k}">${ROLE_LABEL[k]}</span><b>${fmt(t.roles[k])}</b></div>`).join("");
  const traits = t.traits.map((x) => `<span class="tm-trait ${x.on ? "on" : "off"}">${x.on ? "✓" : "✗"} ${esc(x.name)}</span>`).join("");
  const els = ELEMENTS.map((e) => `<img class="tm-el${t.elements.includes(e) ? "" : " off"}" src="assets/stats/${e}_coin.png" alt="" title="${EL_FR[e]}">`).join("");
  $("#team-out").innerHTML = `${tabs}
    <section class="card team-sum">
      <div class="tm-sum-row"><span class="muted">Rôles</span>${roles}</div>
      <div class="tm-sum-row"><span class="muted">Éléments</span>${els}</div>
      <div class="tm-sum-row wrap"><span class="muted">Apports</span>${traits}</div>
      ${t.warnings.map((w) => `<p class="tm-warn">⚠ ${esc(w)}</p>`).join("")}
    </section>
    <div class="team-grid">${members}</div>`;
}

// Charge le membre dans le panneau de gauche (classe, archétype) et lance son optimisation.
function optimizeMember(i) {
  const t = TEAM.result && (TEAM.result.teams[TEAM.shown] || TEAM.result.teams[0]);
  const m = t && t.members[i];
  if (!m) return;
  if ($("#go").disabled) { toast("Un calcul est déjà en cours."); return; }
  $("#cls").value = m.class;
  applyClass(m.class);
  if (Object.keys(S.weights).length) { S.weights = {}; updateWeightsBadge(); }
  applyArchetype(m.archetype, curClass());
  renderPresets();
  refreshVis();
  showTab("build");
  toast(`${m.class_name} · ${m.arch_name} : optimisation lancée.`);
  start();
}
