"use strict";
// Wakfu Optimizer — interface web (vanilla JS)

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n).toLocaleString("fr-FR");
const signed = (n) => (n > 0 ? "+" : n < 0 ? "−" : "") + fmt(Math.abs(n));

const STAT_ICON = {
  hp: "health_points", hp_pct: "health_points", ap: "action_points", mp: "movement_points", wp: "wakfu_points",
  range: "range", crit_rate: "critical_hit", block: "block", crit_mastery: "critical_mastery",
  melee_mastery: "melee_mastery", distance_mastery: "distance_mastery", rear_mastery: "rear_mastery",
  berserk_mastery: "berserk_mastery", heal_mastery: "healing_mastery", dmg_pct: "damage_inflicted",
  lock: "lock", dodge: "dodge", initiative: "initiative", willpower: "force_of_will", control: "control",
  crit_res: "critical_resistance", rear_res: "rear_resistance", elem_mastery: "quadrumental_breeze",
  elem_res: "quadrumental_breeze", wisdom: "wisdom", prospecting: "prospecting", score: "quadrumental_breeze",
};
const ELEMENTS = ["fire", "water", "earth", "air"];
const EL_FR = { fire: "Feu", water: "Eau", earth: "Terre", air: "Air" };
const SHARD_FILE = { 0: "White", 1: "Red", 2: "Green", 3: "Blue" };
const SHARD_ORDER = [null, 1, 2, 3, 0];
const SHARD_SLOTS = ["HEAD", "NECK", "CHEST", "LEFT_HAND", "RIGHT_HAND", "LEGS", "BACK", "SHOULDERS", "BELT", "FIRST_WEAPON", "SECOND_WEAPON"];
const MAX_TIME = 90;

function elOf(stat) { return ELEMENTS.find((e) => stat === e || stat === `${e}_mastery` || stat === `${e}_res`); }
function icon(stat, title = "") {
  const e = elOf(stat);
  if (e) return `<span class="ic round" title="${esc(title)}"><img src="assets/stats/${e}_coin.png" alt=""></span>`;
  return `<span class="ic" title="${esc(title)}"><img src="assets/stats/${STAT_ICON[stat] || "empty_coin"}.png" alt=""></span>`;
}
function chip(stat, text, title, cls = "") {
  return `<span class="chip ${cls}" title="${esc(title)}">${icon(stat, title)}${text}</span>`;
}
// Version GitHub Pages : le moteur Python tourne dans le navigateur (static/bridge.js)
const BROWSER = window.WAKFU_BROWSER;
const iconUrl = (gfx) => BROWSER ? `https://static.ankama.com/wakfu/portal/game/item/115/${gfx}.png` : `icon/${gfx}.png`;
async function api(path, body) {
  if (BROWSER) return BROWSER.api(path, body);
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 2600);
}

// ===================================================================== état
const S = {
  meta: null, excluded: new Set(), forced: new Set(), colors: {}, job: null,
  view: null, original: null, opts: null, changed: new Set(),
};

// ===================================================================== widgets
function stepper(id, label, stat, min, max, suffix = "") {
  const d = document.createElement("div");
  d.className = "stepper";
  d.innerHTML = `<label>${stat ? `<img src="assets/stats/${STAT_ICON[stat]}.png" alt="">` : ""}${label}</label>
    <div class="ctl"><button type="button" data-d="-1" aria-label="moins">−</button>
    <input id="${id}" type="number" min="${min}" max="${max}" value="${min}"><button type="button" data-d="1" aria-label="plus">+</button></div>`;
  const inp = $("input", d);
  $$("button", d).forEach((b) => b.addEventListener("click", () => {
    inp.value = Math.max(min, Math.min(max, (+inp.value || 0) + +b.dataset.d));
    inp.dispatchEvent(new Event("change"));
  }));
  inp.addEventListener("change", () => { inp.value = Math.max(min, Math.min(max, +inp.value || 0)); });
  if (suffix) d.title = suffix;
  return d;
}
function seg(id) {
  const root = $("#" + id);
  $$("button", root).forEach((b) => b.addEventListener("click", () => setSeg(id, b.dataset.v)));
}
function setSeg(id, v) {
  $$(`#${id} button`).forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  $("#" + id).dataset.value = v;
  $("#" + id).dispatchEvent(new Event("change"));
}
const segVal = (id) => $("#" + id).dataset.value;
function toggleBtn(el, on) { el.classList.toggle("on", !!on); }
const isOn = (id) => $("#" + id).classList.contains("on");

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

  const mins = $("#mins");
  [["min_ap", "PA min", "ap", 0, 20], ["min_mp", "PM min", "mp", 0, 10], ["min_range", "PO min", "range", 0, 10],
   ["min_wp", "PW min", "wp", 0, 20], ["min_crit", "% Crit min", "crit_rate", 0, 100],
   ["min_res_pct", "% Rés. min (chaque élém.)", "elem_res", 0, 90]].forEach(([id, l, st, a, b]) => mins.appendChild(stepper(id, l, st, a, b)));
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

  seg("range"); seg("shard_mode");
  $("#shard_mode").addEventListener("change", refreshVis);
  $("#weight").addEventListener("input", refreshVis);
  $("#rear_share").addEventListener("input", refreshVis);
  cls.addEventListener("change", () => { applyClass(cls.value); refreshVis(); });
  $("#level").addEventListener("change", () => {
    const l = m.levels.find((x) => x.level === +$("#level").value);
    if (l) { $("#min_ap").value = l.min_ap; $("#min_mp").value = l.min_mp; }
    trimApt();
    renderApt();
  });
  buildAptForm();
  $("#items-btn").addEventListener("click", openPicker);
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

function applyClass(key) {
  const c = S.meta.classes.find((x) => x.key === key);
  if (!c) return;
  $$("#elements .toggle").forEach((b) => toggleBtn(b, c.elements.includes(b.dataset.el)));
  setSeg("range", c.range);
  toggleBtn($("#rear"), c.rear);
  toggleBtn($("#berserk"), c.berserk);
  toggleBtn($("#heal"), c.role === "heal");
  $("#weight").value = c.role === "tank" ? 40 : 70;
}

function refreshVis() {
  $("#class-icon").src = `assets/classes/${$("#cls").value}.png`;
  const w = +$("#weight").value;
  $("#weight-lab").textContent = `Attaque ${w} % · Défense ${100 - w} %`;
  $("#rear-lab").textContent = `${$("#rear_share").value} %`;
  $("#rear-box").classList.toggle("hidden", !isOn("rear"));
  const mode = segVal("shard_mode");
  $("#shard-steps").classList.toggle("hidden", mode !== "ideal");
  $("#my-colors").classList.toggle("hidden", mode !== "mine");
  $("#items-lab").textContent = `${S.excluded.size} exclu(s), ${S.forced.size} forcé(s)`;
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
  set("rear_share", o.rear_share); set("weight", o.offense_weight);
  $("#balance").checked = o.balance_res; $("#cond").checked = o.count_conditional;
  ["min_ap", "min_mp", "min_range", "min_wp", "min_crit", "min_res_pct", "shard_count", "max_jokers"].forEach((k) => set(k, o[k]));
  $$("#rarities .toggle").forEach((b) => toggleBtn(b, (o.allowed_rarities || []).includes(+b.dataset.r)));
  $("#lower").checked = o.lower_brackets; $("#no_relic").checked = o.exclude_relic; $("#no_epic").checked = o.exclude_epic;
  $("#no_shop").checked = o.exclude_shop; $("#pets").checked = o.include_pet_mount;
  S.excluded = new Set(o.excluded_ids || []); S.forced = new Set(o.forced_ids || []);
  setSeg("shard_mode", o.shard_mode || "ideal");
  S.apt = Object.assign({}, o.manual_chars || {});
  setSeg("char_mode", o.char_mode || "auto");
  S.colors = o.my_colors || {};
  renderShardRows();
  refreshVis();
}

function options() {
  const n = (id) => +$("#" + id).value || 0;
  const els = $$("#elements .toggle.on").map((b) => b.dataset.el);
  return {
    class_key: $("#cls").value, level: n("level"), elements: els, lang: $("#lang").value,
    range: segVal("range"), crit: isOn("crit"), rear: isOn("rear"), rear_share: n("rear_share"),
    berserk: isOn("berserk"), heal: isOn("heal"), offense_weight: n("weight"),
    balance_res: $("#balance").checked, count_conditional: $("#cond").checked,
    min_ap: n("min_ap"), min_mp: n("min_mp"), min_range: n("min_range"), min_wp: n("min_wp"),
    min_crit: n("min_crit"), min_control: 0, min_res_pct: n("min_res_pct"),
    allowed_rarities: $$("#rarities .toggle.on").map((b) => +b.dataset.r),
    lower_brackets: $("#lower").checked, exclude_relic: $("#no_relic").checked, exclude_epic: $("#no_epic").checked,
    exclude_shop: $("#no_shop").checked, include_pet_mount: $("#pets").checked, optimize_characteristics: true,
    char_mode: segVal("char_mode"), manual_chars: { ...S.apt },
    excluded_ids: [...S.excluded], forced_ids: [...S.forced],
    shard_mode: segVal("shard_mode"), shard_count: n("shard_count"), max_jokers: n("max_jokers"),
    my_colors: Object.fromEntries(SHARD_SLOTS.map((s) => [s, S.colors[s] || [1, 1, 1, 1]])),
    time_limit: MAX_TIME, alternatives: 0,
  };
}

// ===================================================================== optimisation
async function start() {
  const o = options();
  if (!o.elements.length) { toast("Choisissez au moins un élément."); return; }
  if (!o.allowed_rarities.length) { toast("Choisissez au moins une rareté."); return; }
  S.opts = o;
  $("#go").disabled = true; $("#stop").disabled = false;
  $("#msg").innerHTML = "";
  setProgress(0, "Démarrage…", true);
  try {
    const { job } = await api("/api/optimize", { opts: o });
    S.job = job;
    poll();
  } catch (e) {
    endRun(); $("#msg").innerHTML = `<span class="err">Erreur : ${esc(e.message)}</span>`;
  }
}
function setProgress(frac, text, running) {
  $("#bar").style.width = `${Math.round(frac * 100)}%`;
  $("#ptext").textContent = text;
  $("#progress").classList.toggle("running", !!running);
}
function endRun() { $("#go").disabled = false; $("#stop").disabled = true; S.job = null; }
async function poll() {
  if (!S.job) return;
  let j;
  try { j = await api(`/api/job?id=${S.job}`); } catch (e) { setTimeout(poll, 800); return; }
  const pct = Math.round(j.progress * 100);
  setProgress(j.progress, `${pct} % — ${j.msg}  (${Math.round(j.elapsed)} s, max ${MAX_TIME} s)`, !j.done);
  if (!j.done) { setTimeout(poll, 400); return; }
  endRun();
  const r = j.result || {};
  const warn = (r.warnings || []).map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join("");
  if (!r.view) {
    const diag = (r.diagnostics || []).map((d) => `<div>• ${esc(d)}</div>`).join("");
    setProgress(1, r.status === "annulé" ? "Annulé" : "Aucun build", false);
    $("#msg").innerHTML = `<div class="err">${esc(r.message || r.status)}</div>${diag}${warn}`;
    return;
  }
  setProgress(1, `Terminé — ${r.status} en ${r.elapsed} s`, false);
  $("#msg").innerHTML = warn;
  S.original = r.view; S.view = r.view; S.changed = new Set();
  showTab("build");
  renderResult();
  $("#apt-from-build").disabled = false;
}

// ===================================================================== résultat
function sc(stat, label, value, cls = "") {
  return `<div class="sc">${icon(stat, label)}<span class="lab">${esc(label)}</span><span class="val ${cls}">${value}</span></div>`;
}
const pn = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");

function renderResult() {
  const v = S.view, s = v.stats;
  const changed = S.changed.size
    ? `<div class="modified"><span>Build modifié à la main (${S.changed.size} changement(s)) — score ${v.score.toFixed(1)} au lieu de ${S.original.score.toFixed(1)}</span><button class="btn small" id="revert">Revenir au build optimisé</button></div>` : "";
  const masteries = ELEMENTS.map((e) => sc(e, EL_FR[e], fmt(v.mastery[e]))).join("");
  const res = ELEMENTS.map((e) => sc(e, EL_FR[e], `${v.res_pct[e]} % <small class="muted">(${v.res_flat[e]})</small>`)).join("");
  const g = (k, label, suffix = "") => sc(k, label, `${fmt(s[k] || 0)}${suffix}`, pn(s[k] || 0));
  const subs = v.active.map((a) => `<span title="${esc(a.desc)}">${esc(a.name)} <b>${a.level}</b></span>`).join("");
  $("#result").innerHTML = `
  <div class="result-grid">
    <div class="summary card">
      ${changed}
      <div class="sum-head">
        <img src="assets/classes/${v.class.key}.png" alt="">
        <div><div class="name">${esc(v.class.name)}</div><div class="muted">Niveau ${v.level} · ${v.elements.map((e) => EL_FR[e]).join(", ")}</div></div>
        <div class="scores"><div><span class="muted">Score</span> <b>${v.score.toFixed(1)}</b></div>
          <div><span class="muted">Dégâts</span> <b>×${v.damage.toFixed(2)}</b></div>
          <div><span class="muted">PV effectifs</span> <b>${fmt(v.ehp)}</b></div></div>
      </div>
      <div class="big4">
        <div class="sc col">${icon("hp", "PV")}<span class="val" style="color:#ff7d8a">${fmt(v.hp)}</span></div>
        <div class="sc col">${icon("ap", "PA")}<span class="val" style="color:#5cc8ff">${s.ap} PA</span></div>
        <div class="sc col">${icon("mp", "PM")}<span class="val" style="color:#a5d94b">${s.mp} PM</span></div>
        <div class="sc col">${icon("wp", "PW")}<span class="val" style="color:#3fd9c8">${s.wp} PW</span></div>
      </div>
      <div class="sec-title">Maîtrises</div><div class="stat-grid">${masteries}</div>
      <div class="sec-title">Résistances</div><div class="stat-grid">${res}</div>
      <div class="sec-title">Combat</div>
      <div class="stat-grid">${g("dmg_pct", "% Dommages infligés", " %")}${g("crit_rate", "% Critique", " %")}${g("block", "% Parade", " %")}${g("range", "Portée")}
        ${g("initiative", "Initiative")}${g("willpower", "Volonté")}${g("dodge", "Esquive")}${g("lock", "Tacle")}${g("control", "Contrôle")}</div>
      <div class="sec-title">Secondaire</div>
      <div class="stat-grid">${g("crit_mastery", "Maîtrise critique")}${g("crit_res", "Résistance critique")}${g("rear_mastery", "Maîtrise dos")}${g("rear_res", "Résistance dos")}
        ${g("melee_mastery", "Maîtrise mêlée")}${g("distance_mastery", "Maîtrise distance")}${g("heal_mastery", "Maîtrise soin")}${g("berserk_mastery", "Maîtrise berserk")}</div>
      ${subs ? `<div class="sec-title">Sublimations actives</div><div class="active-subs">${subs}</div>` : ""}
      <div class="actions"><button class="btn" id="copy">Copier le build (texte)</button><button class="btn" id="export">Exporter en JSON</button></div>
    </div>
    <div class="items-grid">${v.items.map(itemCard).join("")}</div>
  </div>`;
  $$(".item[data-slot]").forEach((c) => c.addEventListener("click", () => openSwap(c.dataset.slot)));
  $("#copy").addEventListener("click", () => navigator.clipboard.writeText(v.text).then(() => toast("Build copié.")));
  $("#export").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([v.json], { type: "application/json" }));
    a.download = `build_${v.class.key}_${v.level}.json`;
    a.click();
  });
  const rv = $("#revert");
  if (rv) rv.addEventListener("click", () => { S.view = S.original; S.changed = new Set(); renderResult(); });
}

function statChips(it, withEls = true) {
  const out = it.stats.map((x) => chip(x.stat, signed(x.value), x.label, x.value < 0 ? "neg" : ""));
  for (const r of it.rand_mastery || []) {
    if (withEls && r.els && r.els.length) r.els.forEach((e) => out.push(chip(e, `+${r.value}`, `Maîtrise ${EL_FR[e]} (élément au choix)`)));
    else out.push(chip("elem_mastery", `+${r.value} <small>×${r.n} élém.</small>`, `Maîtrise sur ${r.n} élément(s) au choix`));
  }
  for (const r of it.rand_res || []) {
    if (withEls && r.els && r.els.length) r.els.forEach((e) => out.push(chip(e, `+${r.value} <small>rés.</small>`, `Résistance ${EL_FR[e]} (élément au choix)`)));
    else out.push(chip("elem_res", `+${r.value} <small>rés. ×${r.n}</small>`, `Résistance sur ${r.n} élément(s) au choix`));
  }
  if (it.special_effect) out.push(`<span class="chip" title="Effet spécial non compté dans le score"><small>&nbsp;+ effet spécial</small></span>`);
  return out.join("");
}

function itemCard(it) {
  const runes = (it.shards || []).map((sh) =>
    `<img src="assets/shards/shard${SHARD_FILE[sh.color]}${sh.rune ? "Full" : "Empty"}.png" alt="" title="${sh.rune ? esc(`${sh.rune} niv. ${sh.level} : +${sh.value} ${sh.label}`) : "Châsse vide"}">`).join("");
  const runeTxt = summarizeRunes(it.shards || []);
  return `<div class="item ${S.changed.has(it.slot) ? "changed" : ""}" data-slot="${it.slot}" title="Cliquer pour voir les autres items possibles">
    <div class="it-head"><img class="it-icon" src="${iconUrl(it.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div class="it-names"><div class="it-name" style="color:${it.color}">${esc(it.name)}</div>
      <div class="it-sub">${esc(it.slot_name)} · niv. ${it.level} · ${esc(it.rarity_name)}</div></div>
      <span class="it-swap">Changer ⇄</span></div>
    <div class="chip-row">${statChips(it)}</div>
    ${runes ? `<div class="runes">${runes}<span>${esc(runeTxt)}</span></div>` : ""}
    ${it.sub ? `<div class="sub" title="${esc(it.sub.desc)}">${esc(it.sub.name)}</div>` : ""}
    ${it.special ? `<div class="sub special" title="${esc(it.special.desc)}">${esc(it.special.name)}</div>` : ""}
  </div>`;
}
function summarizeRunes(shards) {
  const acc = {};
  for (const s of shards) if (s.rune) acc[s.label] = (acc[s.label] || 0) + s.value;
  return Object.entries(acc).map(([k, v]) => `+${v} ${k}`).join(" · ");
}

// ===================================================================== remplacement d'un item
async function openSwap(slot) {
  const cur = S.view.items.find((i) => i.slot === slot);
  $("#dr-title").textContent = `Remplacer : ${cur.slot_name}`;
  $("#dr-current").innerHTML = `<div class="cmp-head"><img class="it-icon" src="${iconUrl(cur.gfx)}" alt="">
    <div style="flex:1"><div class="it-name" style="color:${cur.color}">${esc(cur.name)}</div><div class="it-sub">Item actuel · niv. ${cur.level} · ${esc(cur.rarity_name)}</div>
    <div class="chip-row" style="margin-top:4px">${statChips(cur)}</div></div>
    <div class="btns"><button class="btn small" id="dr-ex" title="Ne plus proposer cet item aux prochaines optimisations">Exclure</button>
    <button class="btn small" id="dr-fo" title="Garder cet item aux prochaines optimisations">Forcer</button></div></div>`;
  $("#dr-ex").addEventListener("click", () => { S.forced.delete(cur.id); S.excluded.add(cur.id); refreshVis(); toast("Item exclu pour les prochaines optimisations."); });
  $("#dr-fo").addEventListener("click", () => { S.excluded.delete(cur.id); S.forced.add(cur.id); refreshVis(); toast("Item forcé pour les prochaines optimisations."); });
  $("#dr-list").innerHTML = `<div class="loading"><div class="spinner"></div>Recherche des items qui conviennent…</div>`;
  $("#dr-compare").innerHTML = `<p class="muted pad">Choisissez un item à gauche pour voir ce que vous gagnez et perdez.</p>`;
  $("#drawer").classList.remove("hidden");
  try {
    const r = await api("/api/alternatives", { opts: S.opts, build: S.view.build, slot });
    if (!r.items.length) { $("#dr-list").innerHTML = `<p class="muted pad">Aucun autre item possible pour cet emplacement.</p>`; return; }
    $("#dr-list").innerHTML = r.items.map((a, k) => `<div class="alt" data-k="${k}">
      <img class="it-icon" src="${iconUrl(a.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div><div class="it-name" style="color:${a.color}">${esc(a.name)}</div><div class="it-sub">niv. ${a.level} · ${esc(a.rarity_name)}</div>
      <div class="chip-row">${statChips(a, false)}</div></div>
      <div class="delta ${pn(a.delta)}">${a.delta > 0 ? "+" : ""}${a.delta.toFixed(1)}<small>score</small></div></div>`).join("");
    $$("#dr-list .alt").forEach((el) => el.addEventListener("click", () => {
      $$("#dr-list .alt").forEach((x) => x.classList.remove("sel"));
      el.classList.add("sel");
      showCompare(slot, cur, r.items[+el.dataset.k]);
    }));
  } catch (e) {
    $("#dr-list").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
  }
}

function showCompare(slot, cur, a) {
  const rows = a.compare.map((r) => {
    const better = r.diff > 0;
    return `<tr><td>${esc(r.label)}</td><td class="num muted">${fmt(r.old)}</td><td class="num">${fmt(r.new)}</td>
      <td class="num d ${better ? "pos" : "neg"}">${r.diff > 0 ? "+" : ""}${fmt(r.diff)}</td></tr>`;
  }).join("");
  const gains = a.compare.filter((r) => r.diff > 0 && r.stat !== "score").length;
  const losses = a.compare.filter((r) => r.diff < 0 && r.stat !== "score").length;
  $("#dr-compare").innerHTML = `
    <div class="cmp-head"><img class="it-icon" src="${iconUrl(a.gfx)}" alt="">
      <div><div class="it-name" style="color:${a.color}">${esc(a.name)}</div><div class="it-sub">à la place de ${esc(cur.name)}</div></div></div>
    <div class="muted" style="font-size:12px">${gains} stat(s) en hausse, ${losses} en baisse. Les châsses et la sublimation de l'emplacement sont conservées.</div>
    ${a.dropped.length ? `<div class="note">⚠ Retire aussi : ${esc(a.dropped.join(", "))} (une seule relique / épique, ou arme à deux mains).</div>` : ""}
    <table class="cmp-table"><tr><td></td><td class="num muted">Actuel</td><td class="num muted">Nouveau</td><td class="num muted">Écart</td></tr>${rows || `<tr><td colspan="4" class="muted">Aucune différence</td></tr>`}</table>
    <button class="btn good" id="apply" style="width:100%">Valider le changement</button>`;
  $("#apply").addEventListener("click", async () => {
    try {
      const v = await api("/api/view", { opts: S.opts, build: a.build });
      S.view = v;
      S.changed.add(slot);
      a.dropped.length && toast(`Retiré : ${a.dropped.join(", ")}`);
      closeDrawers();
      renderResult();
    } catch (e) { toast("Erreur : " + e.message); }
  });
}

function closeDrawers() { $$(".drawer").forEach((d) => d.classList.add("hidden")); }
document.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDrawers(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawers(); });

// ===================================================================== aptitudes
const APT_ICON = {
  hp_pct: "health_points", elem_res: "quadrumental_breeze", barrier: "armor", heals_received_pct: "heals_performed",
  armor_hp_pct: "armor", elem_mastery: "elemental_damage", melee_mastery: "melee_mastery", distance_mastery: "distance_mastery",
  hp: "health_points", lock: "lock", dodge: "dodge", initiative: "initiative", lock_dodge: "lock", willpower: "force_of_will",
  crit_rate: "critical_hit", block: "block", crit_mastery: "critical_mastery", rear_mastery: "rear_mastery",
  berserk_mastery: "berserk_mastery", heal_mastery: "healing_mastery", rear_res: "rear_resistance", crit_res: "critical_resistance",
  ap: "action_points", mp: "movement_points", range: "range", wp: "wakfu_points", armor_given_pct: "armor_given",
  dmg_pct: "damage_inflicted", heal_pct: "heals_performed", indirect_pct: "indirect_damage",
};
const PRESET_ICON = { distance: "distance_mastery", melee: "melee_mastery", elemental: "elemental_damage", tank: "quadrumental_breeze", heal: "healing_mastery" };
const BRANCH_COLOR = { intelligence: "#6b2730", strength: "#2c5530", agility: "#4a2e66", fortune: "#1f4a5e", major: "#5a4a35" };
S.apt = {};
let presetSel = null;

function branchPoints(b, level) {
  if (b.branch === "major") return Math.max(0, Math.min(Math.floor((level + 25) / 50), 4));
  return Math.max(0, Math.floor((level + b.offset) / 4));
}
const lvl = () => +$("#level").value || 245;
const used = (b) => b.lines.reduce((t, l) => t + (S.apt[l.key] || 0), 0);

function buildAptForm() {
  const col = { intelligence: 1, strength: 1, agility: 1, fortune: 2, major: 2 };
  for (const b of S.meta.aptitudes) {
    const el = document.createElement("div");
    el.className = "branch";
    el.style.setProperty("--bc", BRANCH_COLOR[b.branch] || "#333");
    el.innerHTML = `<div class="branch-head"><span>${esc(b.name)}</span><span class="avail" data-avail="${b.branch}"></span></div>` +
      b.lines.map((l) => `<div class="apt-line" data-key="${l.key}">
        <span class="ic"><img src="assets/stats/${APT_ICON[l.line] || "empty_coin"}.png" alt=""></span>
        <span class="lab">${esc(l.label)}${l.max > 1 ? ` <small>(max ${l.max})</small>` : ""}</span>
        <span class="apt-ctl"><button data-d="-1" aria-label="moins">−</button><input type="number" min="0" value="0"><button data-d="1" aria-label="plus">+</button></span></div>`).join("");
    $(`#apt-col${col[b.branch] || 2}`).appendChild(el);
    for (const l of b.lines) {
      const row = $(`.apt-line[data-key="${l.key}"]`, el);
      const set = (v) => {
        const free = branchPoints(b, lvl()) - used(b) + (S.apt[l.key] || 0);
        v = Math.max(0, Math.min(v, free, l.max ?? Infinity));
        if (v) S.apt[l.key] = v; else delete S.apt[l.key];
        aptChanged();
      };
      $$("button", row).forEach((bt) => bt.addEventListener("click", (e) => {
        set((S.apt[l.key] || 0) + (e.shiftKey ? 10 : 1) * +bt.dataset.d);
      }));
      $("input", row).addEventListener("change", (e) => set(+e.target.value || 0));
    }
  }
  $("#apt-presets").innerHTML = S.meta.presets.map((p) =>
    `<button class="preset" data-p="${p.key}"><span class="ic"><img src="assets/stats/${PRESET_ICON[p.key] || "empty_coin"}.png" alt=""></span>${esc(p.name)}</button>`).join("");
  $$("#apt-presets .preset").forEach((b) => b.addEventListener("click", () => selectPreset(b.dataset.p)));
  $("#apt-apply").addEventListener("click", applyPreset);
  $("#apt-reset").addEventListener("click", () => { S.apt = {}; aptChanged(); });
  $("#apt-from-build").addEventListener("click", () => {
    if (!S.view) return;
    S.apt = { ...(S.view.build.characteristics || {}) };
    aptChanged();
    toast("Aptitudes du build reprises.");
  });
  seg("char_mode");
  $("#char_mode").addEventListener("change", () => { renderApt(); liveUpdate(); });
  $$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
}

function showTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  $("#tab-apt").classList.toggle("hidden", name !== "apt");
  $("#result").classList.toggle("hidden", name !== "build");
}

// Niveau baissé : on retire les points en trop en partant du bas de chaque branche.
function trimApt() {
  for (const b of S.meta.aptitudes) {
    let over = used(b) - branchPoints(b, lvl());
    for (const l of [...b.lines].reverse()) {
      if (over <= 0) break;
      const n = S.apt[l.key] || 0, cut = Math.min(n, over);
      if (cut) { S.apt[l.key] = n - cut; if (!S.apt[l.key]) delete S.apt[l.key]; over -= cut; }
    }
  }
}

function renderApt() {
  if (!S.meta || !S.meta.aptitudes || !$(".apt-line")) return;
  for (const b of S.meta.aptitudes) {
    const tot = branchPoints(b, lvl()), left = tot - used(b);
    const av = $(`[data-avail="${b.branch}"]`);
    av.innerHTML = `Disponible : <b>${left}</b> <span class="muted">/ ${tot}</span>`;
    av.className = "avail" + (left < 0 ? " over" : left > 0 ? " left" : "");
    for (const l of b.lines) {
      const row = $(`.apt-line[data-key="${l.key}"]`);
      const n = S.apt[l.key] || 0;
      $("input", row).value = n;
      row.classList.toggle("zero", !n);
      const [minus, plus] = $$("button", row);
      minus.disabled = !n;
      plus.disabled = left <= 0 || (l.max != null && n >= l.max);
    }
  }
  const manual = segVal("char_mode") === "manual";
  const badge = $("#apt-badge");
  badge.textContent = manual ? "les miennes" : "auto";
  badge.classList.toggle("manual", manual);
  const free = S.meta.aptitudes.reduce((t, b) => t + Math.max(0, branchPoints(b, lvl()) - used(b)), 0);
  $("#apt-mode-hint").textContent = manual
    ? `L'optimisation utilisera exactement ces aptitudes.${free ? ` Il reste ${free} point(s) non attribué(s).` : ""}`
    : "L'optimiseur répartit lui-même les points. Modifiez une aptitude ou appliquez un preset pour imposer les vôtres.";
}

function aptChanged() {
  if (segVal("char_mode") !== "manual") setSeg("char_mode", "manual");
  renderApt();
  liveUpdate();
}

// Recalcule les stats du build affiché avec les aptitudes choisies.
let liveTimer = null;
function liveUpdate() {
  if (!S.view || !S.opts) return;
  clearTimeout(liveTimer);
  liveTimer = setTimeout(async () => {
    const chars = segVal("char_mode") === "manual" ? { ...S.apt } : (S.original.build.characteristics || {});
    const build = { ...S.view.build, characteristics: chars };
    try { S.view = await api("/api/view", { opts: S.opts, build }); renderResult(); } catch (e) { /* sans effet */ }
  }, 250);
}

async function selectPreset(key) {
  $$("#apt-presets .preset").forEach((b) => b.classList.toggle("sel", b.dataset.p === key));
  const p = S.meta.presets.find((x) => x.key === key);
  const pts = await api(`/api/preset?name=${key}&level=${lvl()}`);
  presetSel = { key, pts };
  const labels = Object.fromEntries(S.meta.aptitudes.flatMap((b) => b.lines.map((l) => [l.key, `${b.name} · ${l.label}`])));
  $("#apt-detail").innerHTML = `<div>${esc(p.desc)}</div><ul class="preset-detail">` +
    Object.entries(pts).map(([k, v]) => `<li><span>${esc(labels[k] || k)}</span><b>${v}</b></li>`).join("") + "</ul>";
  $("#apt-apply").disabled = false;
}
function applyPreset() {
  if (!presetSel) return;
  S.apt = { ...presetSel.pts };
  aptChanged();
  toast(`Preset appliqué (niveau ${lvl()}).`);
}

// ===================================================================== exclus / forcés
let pkTimer = null;
function openPicker() {
  $("#picker").classList.remove("hidden");
  $("#pk-search").focus();
  renderPickerLists();
}
function pkRow(it, actions) {
  return `<div class="pk-item"><img src="${iconUrl(it.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
    <div><span style="color:${it.color}">${esc(it.name)}</span> <span class="muted">niv. ${it.level} · ${esc(it.slot_name || it.type)}</span></div>
    <div class="btns">${actions}</div></div>`;
}
async function searchItems() {
  const q = $("#pk-search").value.trim();
  if (q.length < 2) { $("#pk-results").innerHTML = ""; return; }
  const list = await api(`/api/items?q=${encodeURIComponent(q)}&level=${$("#level").value}&lang=${$("#lang").value}`);
  $("#pk-results").innerHTML = list.map((it) => pkRow(it,
    `<button class="btn small" data-ex="${it.id}">Exclure</button><button class="btn small" data-fo="${it.id}">Forcer</button>`)).join("") || `<p class="muted">Aucun item.</p>`;
}
async function renderPickerLists() {
  const ids = [...S.excluded, ...S.forced];
  const list = ids.length ? await api(`/api/items?ids=${ids.join(",")}&level=${$("#level").value}&lang=${$("#lang").value}`) : [];
  const by = Object.fromEntries(list.map((i) => [i.id, i]));
  const rm = (id) => `<button class="btn small" data-rm="${id}">Retirer</button>`;
  $("#pk-ex").innerHTML = [...S.excluded].filter((i) => by[i]).map((i) => pkRow(by[i], rm(i))).join("") || `<p class="muted">Aucun</p>`;
  $("#pk-fo").innerHTML = [...S.forced].filter((i) => by[i]).map((i) => pkRow(by[i], rm(i))).join("") || `<p class="muted">Aucun</p>`;
  refreshVis();
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ex],[data-fo],[data-rm]");
  if (!b) return;
  const id = +(b.dataset.ex || b.dataset.fo || b.dataset.rm);
  S.excluded.delete(id); S.forced.delete(id);
  if (b.dataset.ex) S.excluded.add(id);
  if (b.dataset.fo) S.forced.add(id);
  renderPickerLists();
});

// ===================================================================== démarrage
async function reloadData() {
  await api("/api/reload", {});
  S.meta = null;
  $("#version").textContent = "Mise à jour des données…";
  waitMeta(false);
}
async function waitMeta(first = true) {
  let m;
  try { m = await api("/api/meta"); } catch (e) { setTimeout(() => waitMeta(first), 1000); return; }
  if (m.error) { setProgress(0, m.error, false); $("#version").textContent = m.error; return; }
  if (m.loading || !m.classes) { setProgress(0, m.msg || "Chargement des données Ankama…", true); $("#go").disabled = true; setTimeout(() => waitMeta(first), 700); return; }
  S.meta = m;
  $("#version").textContent = `Données ${m.version} · ${fmt(m.items)} items`;
  setProgress(0, "Prêt", false);
  $("#go").disabled = false;
  if (first) {
    buildForm();
    const o = Object.assign({}, m.defaults, m.settings || {});
    if (!m.settings || !m.settings.class_key) { o.class_key = "iop"; }
    applyOptions(o);
    if (!m.settings || !m.settings.class_key) applyClass(o.class_key);
    refreshVis();
  }
}
$("#go").disabled = true;
if (BROWSER) $("#reload").classList.add("hidden");
$$("#picker [data-close]");
$("#pk-search").addEventListener("input", () => { clearTimeout(pkTimer); pkTimer = setTimeout(searchItems, 250); });
waitMeta();
