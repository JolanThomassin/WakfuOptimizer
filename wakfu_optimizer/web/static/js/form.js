"use strict";
// Panneau de gauche : formulaire, archétypes, panneaux activables, options envoyées au calcul.

// ===================================================================== formulaire
function buildForm() {
  const m = S.meta;
  const cls = $("#cls");
  cls.innerHTML = m.classes.map((c) => `<option value="${c.key}">${esc(c.name)}</option>`).join("");
  $("#level").innerHTML = m.levels.map((l) => `<option value="${l.level}">Niveau ${l.level}</option>`).join("");
  $("#elements").innerHTML = m.elements.map((e) =>
    `<button class="toggle" data-el="${e.key}"><img src="assets/stats/${e.key}_coin.png" alt="">${e.name}</button>`).join("");
  $$("#elements .toggle").forEach((b) => b.addEventListener("click", () => b.classList.toggle("on")));
  $("#rarities").innerHTML = m.rarities.map((r) =>
    `<button class="toggle plain" data-r="${r.id}" style="--rc:${r.color}"><span style="color:${r.color}">●</span>&nbsp;${r.name}</button>`).join("");
  $$("#rarities .toggle").forEach((b) => b.addEventListener("click", () => b.classList.toggle("on")));
  ["crit", "rear", "berserk", "heal"].forEach((id) => $("#" + id).addEventListener("click", () => { $("#" + id).classList.toggle("on"); refreshVis(); }));

  const mm = $("#minmax");
  for (const [k, label, hi, st] of MINMAX) {
    mm.insertAdjacentHTML("beforeend", `<label><img src="assets/stats/${STAT_ICON[st || k]}.png" alt="">${label}</label>`);
    mm.appendChild($(".ctl", stepper(`min_${k}`, "", null, 0, hi)));
    mm.appendChild($(".ctl", stepper(`max_${k}`, "", null, 0, hi)));
    // min ≤ max : la valeur qu'on vient de changer fait bouger l'autre (max 0 = pas de limite)
    const mn = $(`#min_${k}`), mx = $(`#max_${k}`);
    mn.addEventListener("change", () => {
      if (+mx.value && +mn.value > +mx.value) { mx.value = mn.value; toast(`${label} max relevé à ${mn.value} (il était sous le min).`); }
    });
    mx.addEventListener("change", () => {
      if (+mx.value && +mx.value < +mn.value) { mn.value = mx.value; toast(`${label} min baissé à ${mx.value} (il dépassait le max).`); }
    });
  }
  const ss = $("#shard-steps");
  ss.appendChild(stepper("shard_count", "Châsses par item", null, 1, 4));
  ss.appendChild(stepper("max_jokers", "Jaunes (joker) max", null, 0, 4, "Châsses jaunes : acceptent toutes les runes"));

  const grid = document.createElement("div");
  grid.className = "shard-grid";
  for (const s of SHARD_SLOTS) {
    const name = m.slots.find((x) => x.key === s).name;
    grid.insertAdjacentHTML("beforeend", `<span>${esc(name)}</span><div class="shards" data-slot="${s}"></div>`);
  }
  $("#my-colors").appendChild(grid);
  $("#my-colors").insertAdjacentHTML("beforeend", `<p class="hint">Clic : rouge → verte → bleue → jaune (joker) → aucune. Clic droit : aucune.</p>`);

  seg("range"); seg("shard_mode"); seg("rear_share"); seg("subs-kind");
  $("#shard_mode").addEventListener("change", refreshVis);
  // double curseur : le min ne dépasse pas le max (le curseur qu'on bouge pousse l'autre)
  // résistance visée et écart max : saisie directe ou −/+ (Maj : par 5)
  const clampRes = () => {
    $("#res_target").value = Math.max(0, Math.min(90, Math.round(+$("#res_target").value || 0)));
    $("#res_tol").value = Math.max(0, Math.min(+$("#res_target").value, 30, Math.round(+$("#res_tol").value || 0)));
    refreshVis();
  };
  $$("[data-step]").forEach((bt) => bt.addEventListener("click", (e) => {
    const inp = $("#" + bt.dataset.step);
    inp.value = +inp.value + (e.shiftKey ? 5 : 1) * +bt.dataset.d;
    clampRes();
  }));
  ["#res_target", "#res_tol"].forEach((id) => $(id).addEventListener("change", clampRes));
  $("#time-btn").addEventListener("click", () => {
    const steps = [60, 180, 360];
    setTimeLimit(steps[(steps.indexOf(+$("#time_limit").value) + 1) % steps.length]);
  });
  $("#neutral").addEventListener("change", () => {
    if ($("#neutral").checked) {   // le combo impose du critique et rend dos / berserk / soin inutiles
      toggleBtn($("#crit"), true); ["rear", "berserk", "heal"].forEach((id) => toggleBtn($("#" + id), false));
      if (+$("#min_crit").value < 40) $("#min_crit").value = 40;
      if (+$("#max_crit").value && +$("#max_crit").value < 40) $("#max_crit").value = 0;
      if ($("#no_epic").checked) { $("#no_epic").checked = false; toast("Épiques autorisées : Dénouement est une sublimation épique."); }
    }
    refreshVis();
  });
  cls.addEventListener("change", () => { applyClass(cls.value); refreshVis(); });
  $("#level").addEventListener("change", () => {
    const l = m.levels.find((x) => x.level === +$("#level").value);
    const a = ARCHETYPES[$("#archetype").value];
    if (a) resetConstraints(a); else if (l) { $("#min_ap").value = l.min_ap; $("#min_mp").value = l.min_mp; }
    trimApt();
    renderApt();
  });
  buildAptForm();
  setSeg("subs-kind", "all");
  $("#subs-kind").addEventListener("change", () => subsCache && renderSubs());
  $("#subs-q").addEventListener("input", () => { clearTimeout(subsTimer); subsTimer = setTimeout(() => subsCache && renderSubs(), 150); });
  $("#subs-go").addEventListener("click", start);
  $("#subs-list").addEventListener("change", (e) => {
    const sel = e.target.closest("[data-slvl]");
    if (sel) { S.subLevels[+sel.dataset.slvl] = +sel.value; toast(`Au moins le niveau ${ROMAN[+sel.value] || sel.value} : l'optimiseur pourra monter plus haut, jamais en dessous.`); }
  });
  $("#subs-list").addEventListener("click", (e) => {
    if (e.target.closest("[data-slvl]")) return;
    const b = e.target.closest("[data-sfo],[data-sex]");
    if (b) setSubPref(+(b.dataset.sfo || b.dataset.sex), b.dataset.sfo ? "fo" : "ex");
  });
  buildItemsTab();
  ARCHETYPES = Object.fromEntries(m.archetypes.map((a) => [a.key, a]));
  $("#archetype").addEventListener("change", () => {
    applyArchetype($("#archetype").value, curClass());
    renderPresets();
    toast(`Archétype « ${ARCHETYPES[$("#archetype").value].name} » appliqué.`);
  });
  $$("[data-panel]").forEach((cb) => cb.addEventListener("change", () => {
    setPanel(cb.dataset.panel, cb.checked);
    toast(cb.checked ? "Panneau activé : vos réglages remplacent ceux de l'archétype."
      : "Panneau désactivé : l'archétype règle ces paramètres.");
  }));
  $("#go").addEventListener("click", start);
  $("#stop").addEventListener("click", () => S.job && api("/api/cancel", { job: S.job }));
  $("#reload").addEventListener("click", reloadData);
}

function renderShardRows() {
  for (const row of $$(".shards[data-slot]")) {
    const s = row.dataset.slot;
    const cols = S.colors[s] || [1, 1, 1, 1];
    row.innerHTML = "";
    for (let k = 0; k < 4; k++) {
      const c = k < cols.length ? cols[k] : null;
      const b = document.createElement("button");
      b.className = "shard-btn" + (c === null ? "" : " filled");
      b.innerHTML = c === null ? "" : `<img src="assets/shards/shard${SHARD_FILE[c]}Full.png" alt="">`;
      b.addEventListener("click", () => cycleShard(s, k, false));
      b.addEventListener("contextmenu", (e) => { e.preventDefault(); cycleShard(s, k, true); });
      row.appendChild(b);
    }
  }
}
function cycleShard(slot, k, clear) {
  const arr = [...(S.colors[slot] || [1, 1, 1, 1])];
  while (arr.length < 4) arr.push(null);
  arr[k] = clear ? null : SHARD_ORDER[(SHARD_ORDER.indexOf(arr[k] ?? null) + 1) % SHARD_ORDER.length];
  S.colors[slot] = arr.filter((c) => c !== null && c !== undefined);
  renderShardRows();
}

// ===================================================================== archétypes
// Définis côté Python (engine/archetypes.py, reçus par /api/meta) : priorités, contraintes, poids du calcul et
// profil d'aptitudes. Le serveur applique ceux de l'archétype pour chaque panneau désactivé.
let ARCHETYPES = {};

// portée imposée par la classe (Roublard : la meilleure des deux maîtrises compte)
function classRange() {
  const c = S.meta && S.meta.classes.find((x) => x.key === $("#cls").value);
  return c ? c.range : "";
}
const curClass = () => S.meta && S.meta.classes.find((x) => x.key === $("#cls").value);
const classArchs = (c) => (c && c.archetypes && c.archetypes.length ? c.archetypes : ["dps_melee"]);

// Liste des archétypes : ceux habituellement joués par la classe en tête (en couleur), puis les autres.
function renderArchetypes(c, value) {
  const recs = classArchs(c);
  const opt = (k, rec) => `<option value="${k}" class="${rec ? "rec" : "other"}">${rec ? "★ " : ""}${esc(ARCHETYPES[k].name)}</option>`;
  const others = Object.keys(ARCHETYPES).filter((k) => !recs.includes(k));
  $("#archetype").innerHTML = `<optgroup label="Habituels pour ${esc(c ? c.name : "la classe")}">${recs.map((k) => opt(k, true)).join("")}</optgroup>`
    + `<optgroup label="Autres archétypes">${others.map((k) => opt(k, false)).join("")}</optgroup>`;
  $("#archetype").value = ARCHETYPES[value] ? value : recs[0];
  $("#archetype").classList.toggle("rec", recs.includes($("#archetype").value));
}

function applyArchetype(key, cls) {
  const a = ARCHETYPES[key] || ARCHETYPES[classArchs(cls)[0]];
  renderArchetypes(cls, a.key);
  $("#arch-hint").textContent = a.desc + (classArchs(cls).includes(a.key) ? "" : " (peu joué avec cette classe)");
  setSeg("range", a.range || (cls && cls.range) || segVal("range") || "distance");
  toggleBtn($("#crit"), a.crit); toggleBtn($("#rear"), a.rear); toggleBtn($("#berserk"), a.berserk); toggleBtn($("#heal"), a.heal);
  setSeg("rear_share", String(a.rear_share >= 70 ? 80 : a.rear_share <= 35 ? 25 : 50));
  $("#res_target").value = a.res[0]; $("#res_tol").value = a.res[1];
  $("#cond").checked = !!a.count_conditional;
  resetConstraints(a);
  refreshVis();
}

// Contraintes de l'archétype (panneau Contraintes désactivé : c'est ce que le serveur utilisera)
function resetConstraints(a) {
  const lv = S.meta.levels.find((x) => x.level === +$("#level").value);
  $("#min_ap").value = Math.max(lv ? lv.min_ap : 0, (a.mins && a.mins.ap) || 0);
  $("#min_mp").value = Math.max(lv ? lv.min_mp : 0, (a.mins && a.mins.mp) || 0);
  $("#min_wp").value = (a.mins && a.mins.wp) || 0;
  if (isPanelOn("constraints")) return;   // le reste est à vous quand le panneau est activé
  ["min_range", "min_crit", "min_block", "max_ap", "max_mp", "max_range", "max_wp", "max_crit", "max_block"].forEach((k) => { $("#" + k).value = 0; });
  $$("#rarities .toggle").forEach((b) => toggleBtn(b, true));
  $("#lower").checked = false; $("#no_relic").checked = false; $("#no_epic").checked = false;
  $("#no_shop").checked = true; $("#pets").checked = true;
}
function resetSubsPanel() {
  setSeg("shard_mode", "ideal"); $("#shard_count").value = 4; $("#max_jokers").value = 1; $("#no_subs").checked = true;
}

// ===================================================================== panneaux activables
// Désactivés à chaque arrivée sur le site : classe, niveau et archétype suffisent pour un build optimisé.
// Activés, ils remplacent les réglages de l'archétype par les vôtres.
const isPanelOn = (k) => { const cb = $(`[data-panel="${k}"]`); return !!(cb && cb.checked); };
function setPanel(k, on) {
  const cb = $(`[data-panel="${k}"]`);
  cb.checked = on;
  cb.closest(".card").classList.toggle("panel-off", !on);
  if (on && k === "subs") $("#no_subs").checked = false;   // activé : sublimations utilisées
  if (!on) {   // retour aux valeurs de l'archétype, pour que l'affichage dise ce qui sera utilisé
    const a = ARCHETYPES[$("#archetype").value];
    if (k === "priorities" && a) applyArchetype(a.key, curClass());
    if (k === "constraints" && a) resetConstraints(a);
    if (k === "subs") resetSubsPanel();
  }
  refreshVis();
}

function applyClass(key) {
  const c = S.meta.classes.find((x) => x.key === key);
  if (!c) return;
  $$("#elements .toggle").forEach((b) => toggleBtn(b, c.elements.includes(b.dataset.el)));
  setSeg("range", c.range);
  applyArchetype(classArchs(c)[0], c);
  renderPresets();
}

function refreshVis() {
  $("#class-icon").src = `assets/classes/${$("#cls").value}.png`;
  const rt = +$("#res_target").value, tol = +$("#res_tol").value;
  $("#res-hint").textContent = rt
    ? `Chaque élément entre ${Math.max(0, rt - tol)} et ${rt} % : aucun malus dans cet écart, le reste part dans les stats.`
    : "Pas de résistance visée : tout part dans les stats.";
  const arch = ARCHETYPES[$("#archetype").value];
  const best = classRange() === "best";
  $("#range-box").classList.toggle("hidden", !!(arch && arch.hide_range) || best);
  $("#range-note").classList.toggle("hidden", !best);
  const neutral = $("#neutral").checked;
  $("#rear-box").classList.toggle("hidden", !isOn("rear") || neutral);
  ["rear", "berserk", "heal"].forEach((id) => { $("#" + id).disabled = neutral; $("#" + id).classList.toggle("off", neutral); });
  const mode = segVal("shard_mode");
  $("#shard-steps").classList.toggle("hidden", mode !== "ideal");
  $("#my-colors").classList.toggle("hidden", mode !== "mine");
  updateItemsBadge();
  renderApt();
}

function applyOptions(o) {
  const set = (id, v) => { if (v !== undefined && $("#" + id)) $("#" + id).value = v; };
  set("cls", o.class_key);
  const lv = S.meta.levels.map((l) => l.level).filter((l) => l >= o.level).pop() ?? S.meta.levels[0].level;
  set("level", lv);
  set("lang", o.lang);
  $$("#elements .toggle").forEach((b) => toggleBtn(b, (o.elements || []).includes(b.dataset.el)));
  setSeg("range", o.range || "melee");
  toggleBtn($("#crit"), o.crit); toggleBtn($("#rear"), o.rear); toggleBtn($("#berserk"), o.berserk); toggleBtn($("#heal"), o.heal);
  const rs = +o.rear_share || 50;
  setSeg("rear_share", rs >= 70 ? "80" : rs <= 35 ? "25" : "50");
  set("res_target", o.res_target ?? 50);
  set("res_tol", o.res_tol ?? 5);
  $("#cond").checked = o.count_conditional;
  $("#neutral").checked = !!o.neutral_combo;
  setTimeLimit(180);   // toujours 3 min à l'ouverture de la page
  ["min_ap", "min_mp", "min_range", "min_wp", "min_crit", "min_block", "max_ap", "max_mp", "max_range", "max_wp", "max_crit", "max_block",
   "shard_count", "max_jokers"].forEach((k) => set(k, o[k] ?? 0));
  S.subForced = new Set(o.forced_subs || []); S.subExcluded = new Set(o.excluded_subs || []);
  S.subLevels = Object.fromEntries(Object.entries(o.forced_sub_levels || {}).map(([k, v]) => [+k, +v]));
  $("#no_subs").checked = !!o.no_subs;
  $$("#rarities .toggle").forEach((b) => toggleBtn(b, (o.allowed_rarities || []).includes(+b.dataset.r)));
  $("#lower").checked = o.lower_brackets; $("#no_relic").checked = o.exclude_relic; $("#no_epic").checked = o.exclude_epic;
  $("#no_shop").checked = o.exclude_shop; $("#pets").checked = o.include_pet_mount;
  S.excluded = new Set(o.excluded_ids || []); S.forced = new Set(o.forced_ids || []);
  setSeg("shard_mode", o.shard_mode || "ideal");
  S.apt = Object.assign({}, o.manual_chars || {});
  $("#apt_elem_res").checked = o.apt_elem_res ?? true;
  setSeg("char_mode", o.char_mode || "auto");
  S.colors = o.my_colors || {};
  updateSubsBadge();
  renderShardRows();
  refreshVis();
}

function options() {
  const n = (id) => +$("#" + id).value || 0;
  const els = $$("#elements .toggle.on").map((b) => b.dataset.el);
  return {
    class_key: $("#cls").value, level: n("level"), elements: els, lang: $("#lang").value,
    range: classRange() === "best" ? "best" : segVal("range"), crit: isOn("crit"), rear: isOn("rear"), rear_share: +segVal("rear_share") || 50,
    berserk: isOn("berserk"), heal: isOn("heal"), archetype: $("#archetype").value,
    panels: { priorities: isPanelOn("priorities"), constraints: isPanelOn("constraints"), subs: isPanelOn("subs") },
    res_target: n("res_target"), res_tol: n("res_tol"),
    count_conditional: $("#cond").checked,
    min_ap: n("min_ap"), min_mp: n("min_mp"), min_range: n("min_range"), min_wp: n("min_wp"),
    min_crit: n("min_crit"), min_control: 0, min_res_pct: 0,
    max_ap: n("max_ap"), max_mp: n("max_mp"), max_range: n("max_range"), max_wp: n("max_wp"), max_crit: n("max_crit"),
    min_block: n("min_block"), max_block: n("max_block"), apt_elem_res: $("#apt_elem_res").checked,
    forced_subs: [...S.subForced], excluded_subs: [...S.subExcluded], no_subs: $("#no_subs").checked,
    forced_sub_levels: Object.fromEntries([...S.subForced].filter((s) => S.subLevels[s] > 1).map((s) => [s, S.subLevels[s]])),
    allowed_rarities: $$("#rarities .toggle.on").map((b) => +b.dataset.r),
    lower_brackets: $("#lower").checked, exclude_relic: $("#no_relic").checked, exclude_epic: $("#no_epic").checked,
    exclude_shop: $("#no_shop").checked, include_pet_mount: $("#pets").checked, optimize_characteristics: true,
    char_mode: segVal("char_mode"), manual_chars: { ...S.apt },
    excluded_ids: [...S.excluded], forced_ids: [...S.forced],
    shard_mode: segVal("shard_mode"), shard_count: n("shard_count"), max_jokers: n("max_jokers"),
    my_colors: Object.fromEntries(SHARD_SLOTS.map((s) => [s, S.colors[s] || [1, 1, 1, 1]])),
    time_limit: n("time_limit") || 180, alternatives: 0, neutral_combo: $("#neutral").checked,
  };
}
