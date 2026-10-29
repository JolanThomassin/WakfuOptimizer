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
  crit_res: "critical_resistance", rear_res: "rear_resistance", elem_mastery: "elemental_damage",
  elem_res: "elemental_resistance", wisdom: "wisdom", prospecting: "prospecting", score: "quadrumental_breeze",
};
const ELEMENTS = ["fire", "water", "earth", "air"];
const EL_FR = { fire: "Feu", water: "Eau", earth: "Terre", air: "Air" };
const SHARD_FILE = { 0: "White", 1: "Red", 2: "Green", 3: "Blue" };
const SHARD_ORDER = [null, 1, 2, 3, 0];
const SHARD_SLOTS = ["HEAD", "NECK", "CHEST", "LEFT_HAND", "RIGHT_HAND", "LEGS", "BACK", "SHOULDERS", "BELT", "FIRST_WEAPON", "SECOND_WEAPON"];


function elOf(stat) { return ELEMENTS.find((e) => stat === e || stat === `${e}_mastery` || stat === `${e}_res`); }
function icon(stat, title = "") {
  const e = elOf(stat);
  if (e && stat === e) return `<span class="ic round" title="${esc(title)}"><img src="assets/stats/${e}_coin.png" alt=""></span>`;
  if (e) return `<span class="ic" title="${esc(title)}"><img src="assets/stats/${stat}.png" alt=""></span>`;
  return `<span class="ic" title="${esc(title)}"><img src="assets/stats/${STAT_ICON[stat] || "empty_coin"}.png" alt=""></span>`;
}
function chip(stat, text, title, cls = "") {
  return `<span class="chip ${cls}" title="${esc(title)}">${icon(stat, title)}${text}</span>`;
}
// Version GitHub Pages : le moteur Python tourne dans le navigateur (static/bridge.js).
// static.ankama.com refuse les images affichées sur un autre site : miroir communautaire (wakassets).
const BROWSER = window.WAKFU_BROWSER;
const iconUrl = (gfx) => BROWSER ? `https://vertylo.github.io/wakassets/items/${gfx}.png` : `icon/${gfx}.png`;
async function api(path, body) {
  if (BROWSER) return BROWSER.api(path, body);
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
// ===================================================================== effets sonores
// Synthétisés par le navigateur (Web Audio) : aucun fichier à charger. Coupables depuis l'en-tête.
const SFX = { on: true, ctx: null };
try { SFX.on = localStorage.getItem("wakfu-optimizer:sfx") !== "off"; } catch (e) { /* stockage indisponible */ }
function audio() {
  if (!SFX.ctx) { const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return null; SFX.ctx = new AC(); }
  if (SFX.ctx.state === "suspended") SFX.ctx.resume();
  return SFX.ctx;
}
function tone(ctx, freq, at, dur, type = "sine", vol = 0.12, slideTo = 0) {
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, at);
  if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, at + dur);
  g.gain.setValueAtTime(0.0001, at);
  g.gain.exponentialRampToValueAtTime(vol, at + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(ctx.destination);
  o.start(at);
  o.stop(at + dur + 0.02);
}
function sfx(kind) {
  if (!SFX.on) return;
  try {
    const ctx = audio();
    if (!ctx) return;
    const t = ctx.currentTime + 0.01;
    if (kind === "done") {   // petit arpège montant + éclat
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(ctx, f, t + i * 0.075, 0.42, "triangle", 0.11));
      tone(ctx, 2093, t + 0.3, 0.6, "sine", 0.05);
    } else if (kind === "fail") {
      tone(ctx, 392, t, 0.22, "triangle", 0.1); tone(ctx, 277.18, t + 0.16, 0.38, "triangle", 0.1);
    } else if (kind === "apply") {
      tone(ctx, 880, t, 0.09, "sine", 0.09); tone(ctx, 1318.5, t + 0.07, 0.16, "sine", 0.08);
    } else if (kind === "start") {
      tone(ctx, 440, t, 0.18, "sine", 0.06, 880);
    } else {   // clic
      tone(ctx, 1200, t, 0.05, "square", 0.025);
    }
  } catch (e) { /* audio indisponible */ }
}
function renderSfxBtn() {
  const b = $("#sfx-btn");
  b.textContent = SFX.on ? "🔊" : "🔇";
  b.title = SFX.on ? "Sons activés (clic pour couper)" : "Sons coupés (clic pour activer)";
}
$("#sfx-btn").addEventListener("click", () => {
  SFX.on = !SFX.on;
  try { localStorage.setItem("wakfu-optimizer:sfx", SFX.on ? "on" : "off"); } catch (e) { /* sans effet */ }
  renderSfxBtn();
  sfx("click");
});
renderSfxBtn();

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
  subForced: new Set(), subExcluded: new Set(), subLevels: {},
};
const MINMAX = [["ap", "PA", 20], ["mp", "PM", 10], ["range", "PO", 10], ["wp", "PW", 20], ["crit", "% Crit", 100, "crit_rate"],
  ["block", "% Parade", 100]];

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
    if (l) { $("#min_ap").value = l.min_ap; $("#min_mp").value = l.min_mp; }
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
  setSeg("rear_share", c.rear ? "80" : "50");
  $("#res_target").value = c.role === "tank" ? 65 : c.role === "heal" ? 55 : 50;
}

function refreshVis() {
  $("#class-icon").src = `assets/classes/${$("#cls").value}.png`;
  const rt = +$("#res_target").value, tol = +$("#res_tol").value;
  $("#res-hint").textContent = rt
    ? `Chaque élément entre ${Math.max(0, rt - tol)} et ${rt} % : aucun malus dans cet écart, le reste part dans les stats.`
    : "Pas de résistance visée : tout part dans les stats.";
  const neutral = $("#neutral").checked;
  $("#rear-box").classList.toggle("hidden", !isOn("rear") || neutral);
  ["rear", "berserk", "heal"].forEach((id) => { $("#" + id).disabled = neutral; $("#" + id).classList.toggle("off", neutral); });
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
    range: segVal("range"), crit: isOn("crit"), rear: isOn("rear"), rear_share: +segVal("rear_share") || 50,
    berserk: isOn("berserk"), heal: isOn("heal"), offense_weight: 85, res_target: n("res_target"), res_tol: n("res_tol"),
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

// ===================================================================== optimisation
async function start() {
  const o = options();
  if (!o.elements.length) { toast("Choisissez au moins un élément."); return; }
  if (!o.allowed_rarities.length) { toast("Choisissez au moins une rareté."); return; }
  S.opts = o;
  $("#go").disabled = true; $("#stop").disabled = false;
  $("#msg").innerHTML = "";
  progressStart("Démarrage…");
  sfx("start");
  try {
    const { job } = await api("/api/optimize", { opts: o });
    S.job = job;
    poll();
  } catch (e) {
    endRun(); progressEnd(false, "Erreur"); $("#msg").innerHTML = `<span class="err">Erreur : ${esc(e.message)}</span>`;
  }
}
function setTimeLimit(sec) {
  $("#time_limit").value = sec;
  $("#time-btn").textContent = `⏱ ${sec / 60} min`;
}

// ===================================================================== barre de progression
// Ce qu'affiche la barre avance tout seul, en douceur, vers l'étape suivante (jamais d'arrêt visible),
// démarre vite et accélère franchement à la fin : le calcul paraît plus rapide qu'il n'est.
const P = { shown: 0, target: 0, since: 0, t0: 0, running: false, raf: 0, last: 0, finishFrom: 0, finishAt: 0 };
const PHASES = [
  [/candidats/, "Tri des items"], [/modèle/, "Préparation"], [/premier build/, "Premier build"],
  [/passe (\d+)/, (m) => `Affinage du build · étape ${m[1]}`], [/Terminé/, "Finitions"],
];
function phaseLabel(msg) {
  for (const [re, lab] of PHASES) {
    const m = re.exec(msg || "");
    if (m) return typeof lab === "function" ? lab(m) : lab;
  }
  return msg || "";
}
function fmtSec(ms) { return `${(ms / 1000).toFixed(1).replace(".", ",")} s`; }
function progressFrame(now) {
  const dt = Math.min(0.1, (now - P.last) / 1000);
  P.last = now;
  let goal;
  if (P.finishAt) {   // fin : sprint jusqu'à 100 % (ease-out)
    const k = Math.min(1, (now - P.finishAt) / 450);
    goal = P.finishFrom + (1 - P.finishFrom) * (1 - (1 - k) ** 3);
    P.shown = goal;
  } else {
    // avance lente vers « étape actuelle + 14 % » : la barre bouge toujours, sans dépasser 96 %
    const ceil = Math.min(0.96, P.target + 0.14);
    goal = P.target + (ceil - P.target) * (1 - Math.exp(-(now - P.since) / 9000));
    P.shown += (Math.max(P.shown, goal) - P.shown) * Math.min(1, dt * 4);
  }
  $("#bar").style.width = `${(P.shown * 100).toFixed(2)}%`;
  $("#progress").style.setProperty("--speed", `${Math.max(0.35, 1.2 - P.shown)}s`);
  if (P.running) $("#ptime").textContent = fmtSec(now - P.t0);
  if (!P.running && !(P.finishAt && now - P.finishAt < 460)) { clearInterval(P.raf); P.raf = 0; }
}
// minuterie à 30 images/s : contrairement aux images d'animation du navigateur, elle tourne aussi onglet caché
function progressTick() {
  clearInterval(P.raf);
  P.raf = setInterval(() => progressFrame(performance.now()), 33);
}
function progressStart(text) {
  Object.assign(P, { shown: 0, target: 0.04, since: performance.now(), t0: performance.now(), running: true,
                     last: performance.now(), finishAt: 0 });
  $("#progress").className = "progress running";
  $("#ptext").textContent = text;
  progressTick();
}
function progressUpdate(frac, msg) {
  if (frac > P.target + 0.001) { P.target = frac; P.since = performance.now(); }
  $("#ptext").textContent = phaseLabel(msg);
}
function progressEnd(ok, text, elapsedSec) {
  if (text !== "Annulé") sfx(ok ? "done" : "fail");
  P.running = false;
  P.finishFrom = P.shown;
  P.finishAt = performance.now();
  progressTick();
  $("#progress").className = `progress ${ok ? "done" : "failed"}`;
  $("#ptext").textContent = text;
  $("#ptime").textContent = elapsedSec != null ? `${String(elapsedSec).replace(".", ",")} s` : "";
}
// états simples (chargement des données, prêt, erreur)
function setProgress(frac, text, running) {
  clearInterval(P.raf);
  P.running = false; P.finishAt = 0; P.shown = frac;
  $("#bar").style.width = `${Math.round(frac * 100)}%`;
  $("#ptext").textContent = text;
  $("#ptime").textContent = "";
  $("#progress").className = `progress ${running ? "running loading" : ""}`;
}
function endRun() { $("#go").disabled = false; $("#stop").disabled = true; S.job = null; }
async function poll() {
  if (!S.job) return;
  let j;
  try { j = await api(`/api/job?id=${S.job}`); } catch (e) { setTimeout(poll, 800); return; }
  if (!j.done) { progressUpdate(j.progress, j.msg); setTimeout(poll, 300); return; }
  endRun();
  const r = j.result || {};
  const warn = (r.warnings || []).map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join("");
  if (!r.view) {
    const diag = (r.diagnostics || []).map((d) => `<div>• ${esc(d)}</div>`).join("");
    progressEnd(false, r.status === "annulé" ? "Annulé" : "Aucun build trouvé", r.elapsed);
    $("#msg").innerHTML = `<div class="err">${esc(r.message || r.status)}</div>${diag}${warn}`;
    return;
  }
  progressEnd(true, `✓ Build trouvé${r.status === "optimal" ? " (optimal)" : r.status.includes("durée max") ? " (durée max atteinte)" : ""}`, r.elapsed);
  $("#msg").innerHTML = warn;
  S.original = r.view; S.view = r.view; S.changed = new Set();
  subsCache = null;
  showTab("build");
  renderResult();
  $("#apt-from-build").disabled = false;
  renderApt();   // en mode auto, l'onglet Aptitudes montre ceux choisis par l'optimiseur
}

// ===================================================================== résultat
function sc(stat, label, value, cls = "") {
  return `<div class="sc" data-stat="${stat}" title="Cliquer : d'où vient cette stat">${icon(stat, label)}<span class="lab">${esc(label)}</span><span class="val ${cls}">${value}</span></div>`;
}
const pn = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");

// affichage des items : grille (cartes) ou liste (une ligne par item), retenu dans le navigateur
function itemsView() {
  try { return localStorage.getItem("wakfu-optimizer:view") === "list" ? "list" : "grid"; } catch (e) { return "grid"; }
}

function renderResult() {
  const v = S.view, s = v.stats;
  const changed = S.changed.size
    ? `<div class="modified"><span>Build modifié à la main (${S.changed.size} changement(s)) — score ${v.score.toFixed(1)} au lieu de ${S.original.score.toFixed(1)}</span><button class="btn small" id="revert">Revenir au build optimisé</button></div>` : "";
  const masteries = ELEMENTS.map((e) => sc(`${e}_mastery`, EL_FR[e], fmt(v.mastery[e]))).join("");
  const res = ELEMENTS.map((e) => sc(`${e}_res`, EL_FR[e], `${v.res_pct[e]} % <small class="muted">(${v.res_flat[e]})</small>`)).join("");
  const g = (k, label, suffix = "") => sc(k, label, `${fmt(s[k] || 0)}${suffix}`, pn(s[k] || 0));
  const subs = v.active.map((a) => {
    const over = a.limit && a.raw > a.limit;
    const tip = `${a.desc}${a.limit ? `\nNiveau max : ${a.limit}` : ""}${over ? `\n⚠ ${a.raw - a.limit} niveau(x) perdu(s) : au-delà du maximum` : ""}${a.modeled ? "" : "\nEffet non chiffré par l'optimiseur"}`;
    return `<span class="${over ? "over" : ""}" title="${esc(tip)}">${esc(a.name)} <b>${a.level}${a.limit ? `/${a.limit}` : ""}</b>${over ? " ⚠" : ""}</span>`;
  }).join("");
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
        <div class="sc col" data-stat="hp" title="Cliquer : d'où vient cette stat">${icon("hp", "PV")}<span class="val" style="color:#ff7d8a">${fmt(v.hp)}</span></div>
        <div class="sc col" data-stat="ap" title="Cliquer : d'où vient cette stat">${icon("ap", "PA")}<span class="val" style="color:#5cc8ff">${s.ap} PA</span></div>
        <div class="sc col" data-stat="mp" title="Cliquer : d'où vient cette stat">${icon("mp", "PM")}<span class="val" style="color:#a5d94b">${s.mp} PM</span></div>
        <div class="sc col" data-stat="wp" title="Cliquer : d'où vient cette stat">${icon("wp", "PW")}<span class="val" style="color:#3fd9c8">${s.wp} PW</span></div>
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
      <div class="actions three"><button class="btn" id="copy" title="Copier le build en texte (Discord, forum…)">📋 Copier</button>
        <button class="btn" id="export-txt" title="Télécharger le build en texte lisible">📄 Texte (.txt)</button>
        <button class="btn" id="export-png" title="Télécharger une image du build, avec le lien du site">🖼️ Image (.png)</button></div>
    </div>
    <div class="items-wrap">
      <div class="items-bar"><span class="muted">${v.items.length} items</span>
        <div class="seg view-seg" id="items-view"><button data-v="grid" title="Cartes en grille">▦ Grille</button><button data-v="list" title="Une ligne par item">☰ Liste</button></div></div>
      <div class="items-grid ${itemsView()}">${v.items.map(itemCard).join("")}</div>
    </div>
  </div>`;
  $$("#items-view button").forEach((b) => {
    b.classList.toggle("on", b.dataset.v === itemsView());
    b.addEventListener("click", () => {
      try { localStorage.setItem("wakfu-optimizer:view", b.dataset.v); } catch (e) { /* sans effet */ }
      $(".items-grid").className = `items-grid ${b.dataset.v}`;
      $$("#items-view button").forEach((x) => x.classList.toggle("on", x === b));
    });
  });
  $$(".item[data-slot]").forEach((c) => c.addEventListener("click", () => openSwap(c.dataset.slot)));
  $$("#result .sc[data-stat]").forEach((el) => el.addEventListener("click", (e) => { e.stopPropagation(); showStatPop(el); }));
  $$(".item [data-subslot]").forEach((el) => el.addEventListener("click", (e) => {
    e.stopPropagation();
    openSubSwap(el.dataset.subslot, el.dataset.special === "1");
  }));
  $("#copy").addEventListener("click", () => navigator.clipboard.writeText(v.text).then(() => toast("Build copié.")));
  $("#export-txt").addEventListener("click", () => {
    download(new Blob([v.text], { type: "text/plain;charset=utf-8" }), `build_${v.class.key}_${v.level}.txt`);
    toast("Build téléchargé en texte.");
  });
  $("#export-png").addEventListener("click", () => exportPng(v));
  const rv = $("#revert");
  if (rv) rv.addEventListener("click", () => { S.view = S.original; S.changed = new Set(); renderResult(); });
}

// ===================================================================== détail d'une stat
const KIND_LABEL = { base: "Base", item: "Items", random: "Items (au choix)", rune: "Runes", apt: "Aptitudes", sub: "Sublimations", pct: "% PV" };
function srcIcon(x) {
  const img = (src, cls = "") => `<img class="sp-ic ${cls}" src="${src}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
  switch (x.kind) {
    case "item": case "random": return img(iconUrl(x.ref), "it");
    case "rune": return img(`assets/shards/shard${SHARD_FILE[x.ref] || "White"}Full.png`);
    case "apt": return img(`assets/aptitudes/${x.ref}.png`);
    case "base": return img(`assets/classes/${S.view.class.key}.png`, "it");
    case "pct": return img("assets/stats/health_points.png");
    default: return `<span class="sp-ic sub">✦</span>`;
  }
}
function showStatPop(el) {
  const b = S.view.breakdown && S.view.breakdown[el.dataset.stat];
  const pop = $("#stat-pop");
  if (!b) { pop.classList.add("hidden"); return; }
  const sum = b.lines.reduce((t, x) => t + x.value, 0);
  const max = Math.max(1, ...b.lines.map((x) => Math.abs(x.value)));
  const kinds = {};
  for (const x of b.lines) { const k = x.kind === "random" ? "item" : x.kind; kinds[k] = (kinds[k] || 0) + x.value; }
  pop.innerHTML = `<div class="sp-head">${icon(el.dataset.stat, b.label)}<b>${esc(b.label)}</b><span class="sp-total">${fmt(b.total)}</span>
      <button class="sp-close" data-spclose aria-label="Fermer">✕</button></div>
    ${b.note ? `<div class="muted sp-note">${esc(b.note)}</div>` : ""}
    ${sum !== b.total ? `<div class="note">Total brut ${fmt(sum)}, plafonné à ${fmt(b.total)}.</div>` : ""}
    <div class="sp-kinds">${Object.entries(kinds).sort((a, c) => c[1] - a[1]).map(([k, v]) =>
      `<span class="sp-k k-${k}">${KIND_LABEL[k] || k} <b>${signed(v)}</b></span>`).join("")}</div>
    <div class="sp-lines">${b.lines.length ? b.lines.map((x) => `<div class="sp-line k-${x.kind}">
      ${srcIcon(x)}<span class="sp-src" title="${esc(x.src)}">${esc(x.src)}</span>
      <span class="sp-barbox"><span class="sp-bar ${x.value < 0 ? "neg" : ""}" style="width:${Math.max(4, Math.round(100 * Math.abs(x.value) / max))}%"></span></span>
      <span class="sp-val ${x.value < 0 ? "neg" : ""}">${signed(x.value)}</span></div>`).join("") : `<p class="muted">Rien dans ce build.</p>`}</div>`;
  pop.classList.remove("hidden");
  const r = el.getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight;
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`;
  pop.style.top = `${r.bottom + 6 + h > innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6}px`;
}
document.addEventListener("click", (e) => {
  const pop = $("#stat-pop");
  if (pop && !pop.classList.contains("hidden") && (e.target.closest("[data-spclose]") || !e.target.closest("#stat-pop"))) pop.classList.add("hidden");
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#stat-pop").classList.add("hidden"); });
document.addEventListener("scroll", () => $("#stat-pop").classList.add("hidden"), true);

// ===================================================================== exports
const SITE_URL = "https://jolanthomassin.github.io/WakfuOptimizer/";
function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
function loadImg(src) {
  return new Promise((res) => {
    const im = new Image();
    im.crossOrigin = "anonymous";   // icônes du miroir wakassets : CORS autorisé, le canvas reste exportable
    const t = setTimeout(() => res(null), 6000);
    im.onload = () => { clearTimeout(t); res(im); };
    im.onerror = () => { clearTimeout(t); res(null); };
    im.src = src;
  });
}

// Image du build (PNG) : en-tête, stats, maîtrises / résistances, items, sublimations, aptitudes, lien du site.
async function exportPng(v) {
  toast("Création de l'image…");
  const W = 1200, P = 36, COLS = 3, CW = (W - 2 * P - (COLS - 1) * 14) / COLS, CH = 104;
  const s = v.stats;
  const aptLines = (S.meta.aptitudes || []).map((b) => {
    const pts = b.lines.filter((l) => (v.build.characteristics || {})[l.key]).map((l) => `${l.label} ${v.build.characteristics[l.key]}`);
    return pts.length ? [b.name, pts.join(" · ")] : null;
  }).filter(Boolean);
  const itemRows = Math.ceil(v.items.length / COLS);
  const H = 300 + 196 + itemRows * (CH + 14) + 70 + aptLines.length * 24 + 110;

  // images : classe, icônes de stats, items, châsses
  const srcs = new Set([`assets/classes/${v.class.key}.png`, ...v.items.map((it) => iconUrl(it.gfx))]);
  ["health_points", "action_points", "movement_points", "wakfu_points", "range", "critical_hit", "block", "damage_inflicted",
   "melee_mastery", "distance_mastery", "critical_mastery", "rear_mastery", "berserk_mastery", "healing_mastery"].forEach((n) => srcs.add(`assets/stats/${n}.png`));
  ELEMENTS.forEach((e) => { srcs.add(`assets/stats/${e}_mastery.png`); srcs.add(`assets/stats/${e}_res.png`); });
  Object.values(SHARD_FILE).forEach((c) => { srcs.add(`assets/shards/shard${c}Full.png`); srcs.add(`assets/shards/shard${c}Empty.png`); });
  const imgs = {};
  await Promise.all([...srcs].map(async (src) => { imgs[src] = await loadImg(src); }));

  const scale = 2;
  const cv = document.createElement("canvas");
  cv.width = W * scale; cv.height = H * scale;
  const c = cv.getContext("2d");
  c.scale(scale, scale);
  const font = (size, weight = 400) => `${weight} ${size}px "Segoe UI", system-ui, sans-serif`;
  const rr = (x, y, w, h, r) => { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); };
  const box = (x, y, w, h, fill = "#232130", stroke = "#3a3650", r = 12) => { rr(x, y, w, h, r); c.fillStyle = fill; c.fill(); c.strokeStyle = stroke; c.lineWidth = 1; c.stroke(); };
  const text = (t, x, y, size, color = "#ece9f4", weight = 400, align = "left", maxW = 0) => {
    c.font = font(size, weight); c.fillStyle = color; c.textAlign = align; c.textBaseline = "middle";
    let str = String(t);
    if (maxW) while (str.length > 1 && c.measureText(str).width > maxW) str = str.slice(0, -2) + "…";
    c.fillText(str, x, y);
    return c.measureText(str).width;
  };
  const img = (src, x, y, w, h = w) => { const im = imgs[src]; if (im) c.drawImage(im, x, y, w, h); };
  const nf = (n) => Number(n).toLocaleString("fr-FR");

  // fond
  const bg = c.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, "#1b1a25"); bg.addColorStop(1, "#13121a");
  c.fillStyle = bg; c.fillRect(0, 0, W, H);
  c.fillStyle = "#e8a93a"; c.fillRect(0, 0, W, 5);

  // en-tête
  box(P, P, 96, 96, "#2d2a3e", "#e8a93a", 18);
  img(`assets/classes/${v.class.key}.png`, P + 8, P + 8, 80);
  text(v.class.name, P + 116, P + 34, 34, "#e8a93a", 800);
  text(`Niveau ${v.level} · ${v.elements.map((e) => EL_FR[e]).join(", ")}`, P + 116, P + 72, 18, "#a29eb8");
  [["Score", v.score.toFixed(1)], ["Dégâts", `×${v.damage.toFixed(2)}`], ["PV effectifs", nf(v.ehp)]].forEach(([lab, val], i) => {
    const x = W - P - (3 - i) * 160 + 10;
    box(x, P + 8, 150, 80, "#232130");
    text(lab, x + 75, P + 30, 13, "#a29eb8", 600, "center");
    text(val.replace(".", ","), x + 75, P + 62, 24, "#ece9f4", 800, "center");
  });

  // stats principales
  const main = [["health_points", nf(v.hp), "PV", "#ff7d8a"], ["action_points", s.ap, "PA", "#5cc8ff"], ["movement_points", s.mp, "PM", "#a5d94b"],
    ["wakfu_points", s.wp, "PW", "#3fd9c8"], ["range", s.range || 0, "PO", "#ece9f4"], ["critical_hit", `${s.crit_rate || 0} %`, "Critique", "#ffcf6e"],
    ["block", `${s.block || 0} %`, "Parade", "#ece9f4"], ["damage_inflicted", `${s.dmg_pct || 0} %`, "Dommages", "#7ddc7d"]];
  const mw = (W - 2 * P - 7 * 10) / 8;
  main.forEach(([ic, val, lab, col], i) => {
    const x = P + i * (mw + 10), y = 160;
    box(x, y, mw, 74);
    img(`assets/stats/${ic}.png`, x + 12, y + 14, 22);
    text(lab, x + 40, y + 25, 12, "#a29eb8", 600);
    text(val, x + 12, y + 54, 20, col, 800, "left", mw - 20);
  });

  // maîtrises / résistances
  const half = (W - 2 * P - 14) / 2, py = 254;
  box(P, py, half, 180); box(P + half + 14, py, half, 180);
  text("Maîtrises", P + 16, py + 22, 15, "#e8a93a", 800);
  text("Résistances", P + half + 30, py + 22, 15, "#e8a93a", 800);
  ELEMENTS.forEach((e, i) => {
    const y = py + 52 + i * 30;
    img(`assets/stats/${e}_mastery.png`, P + 16, y - 11, 22);
    text(EL_FR[e], P + 46, y, 15);
    text(nf(v.mastery[e]), P + half / 2 - 10, y, 16, "#ece9f4", 700, "right");
    img(`assets/stats/${e}_res.png`, P + half + 30, y - 11, 22);
    text(EL_FR[e], P + half + 60, y, 15);
    text(`${v.res_pct[e]} %`, P + 2 * half - 70, y, 16, "#ece9f4", 700, "right");
    text(`(${v.res_flat[e]})`, P + 2 * half, y, 13, "#a29eb8", 400, "right");
  });
  const secs = [["melee_mastery", "Mêlée"], ["distance_mastery", "Distance"], ["crit_mastery", "Critique", "critical_mastery"], ["rear_mastery", "Dos"],
    ["berserk_mastery", "Berserk"], ["heal_mastery", "Soin", "healing_mastery"]].filter(([k]) => s[k]);
  secs.slice(0, 4).forEach(([k, lab, ic], i) => {
    const y = py + 52 + i * 30, x = P + half / 2 + 20;
    img(`assets/stats/${ic || k}.png`, x, y - 11, 22);
    text(lab, x + 30, y, 15);
    text(nf(s[k]), P + half - 16, y, 16, s[k] < 0 ? "#ff7070" : "#ece9f4", 700, "right");
  });

  // items
  let y0 = py + 200;
  text("Équipement", P, y0 + 8, 18, "#e8a93a", 800);
  y0 += 26;
  v.items.forEach((it, i) => {
    const x = P + (i % COLS) * (CW + 14), y = y0 + Math.floor(i / COLS) * (CH + 14);
    box(x, y, CW, CH, S.forced.has(it.id) ? "#1e2a36" : "#232130", S.forced.has(it.id) ? "#5cc8ff" : "#3a3650");
    rr(x + 12, y + 12, 60, 60, 10); c.fillStyle = "#2d2a3e"; c.fill();
    img(iconUrl(it.gfx), x + 14, y + 14, 56);
    text(it.name, x + 84, y + 24, 16, it.color, 800, "left", CW - 96);
    text(`${it.slot_name} · niv. ${it.level}`, x + 84, y + 46, 13, "#a29eb8", 400, "left", CW - 96);
    const sub = [it.sub && it.sub.name, it.special && `★ ${it.special.name}`].filter(Boolean).join("   ");
    if (sub) text(sub, x + 84, y + 68, 13, "#e8a93a", 700, "left", CW - 96);
    (it.shards || []).forEach((sh, k) => img(`assets/shards/shard${SHARD_FILE[sh.color]}${sh.rune ? "Full" : "Empty"}.png`, x + 84 + k * 22, y + 80, 18));
  });
  y0 += itemRows * (CH + 14) + 6;

  // sublimations actives
  text("Sublimations", P, y0 + 10, 18, "#e8a93a", 800);
  let sx = P, sy = y0 + 40;
  for (const a of v.active) {
    const label = `${a.name} ${a.level}${a.limit ? `/${a.limit}` : ""}`;
    c.font = font(13, 600);
    const w = c.measureText(label).width + 22;
    if (sx + w > W - P) { sx = P; sy += 30; }
    rr(sx, sy - 12, w, 24, 12); c.fillStyle = "#2d2a3e"; c.fill();
    text(label, sx + 11, sy, 13, "#ece9f4", 600);
    sx += w + 8;
  }

  // aptitudes
  let ay = sy + 40;
  text("Aptitudes", P, ay, 18, "#e8a93a", 800);
  ay += 28;
  for (const [branch, line] of aptLines) {
    text(branch, P, ay, 14, "#a29eb8", 700);
    text(line, P + 120, ay, 14, "#ece9f4", 400, "left", W - 2 * P - 120);
    ay += 24;
  }

  // pied : lien du site
  const fy = Math.max(ay + 20, H - 70);
  c.fillStyle = "#3a3650"; c.fillRect(P, fy, W - 2 * P, 1);
  text("Wakfu Optimizer", P, fy + 32, 18, "#e8a93a", 800);
  text(SITE_URL, P + 168, fy + 32, 16, "#5cc8ff", 600);
  text(`${new Date().toLocaleDateString("fr-FR")} · ${$("#version").textContent}`, W - P, fy + 32, 13, "#a29eb8", 400, "right");

  const out = document.createElement("canvas");   // recadrage à la hauteur réellement utilisée
  const used = Math.min(H, fy + 64);
  out.width = W * scale; out.height = used * scale;
  out.getContext("2d").drawImage(cv, 0, 0);
  out.toBlob(async (blob) => {
    if (!blob) { toast("Impossible de créer l'image."); return; }
    download(blob, `build_${v.class.key}_${v.level}.png`);
    let copied = false;
    try { await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]); copied = true; } catch (e) { /* presse-papier refusé */ }
    toast(copied ? "Image téléchargée et copiée : collez-la directement (Ctrl+V)." : "Image téléchargée.");
    sfx("apply");
  }, "image/png");
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

// Comment obtenir l'item : recette (données Ankama) + lien wiki (butins de monstres, coffres, succès)
function obtain(it) {
  const parts = [];
  if (it.craft) {
    const ing = it.craft.ingredients.map(([n, q]) => `${q} × ${n}`).join("\n");
    parts.push(`<span class="craft" title="${esc(`Recette (${it.craft.job} niv. ${it.craft.level}) :\n${ing}`)}">⚒ ${esc(it.craft.job)} niv. ${it.craft.level}</span>`);
  } else {
    parts.push(`<span title="Aucune recette : butin, coffre, succès, boutique…">Pas de recette</span>`);
  }
  if (it.shop) parts.push(`<span class="shop">Boutique</span>`);
  if (it.wiki) parts.push(`<a href="${esc(it.wiki)}" target="_blank" rel="noopener" onclick="event.stopPropagation()"
    title="Monstres et taux de butin, coffres, succès (wakfu.wiki.gg, en anglais)">Où l'obtenir ↗</a>`);
  return `<div class="obtain">${parts.join("")}</div>`;
}

function itemCard(it) {
  const runes = (it.shards || []).map((sh) =>
    `<img src="assets/shards/shard${SHARD_FILE[sh.color]}${sh.rune ? "Full" : "Empty"}.png" alt="" title="${sh.rune ? esc(`${sh.rune} niv. ${sh.level} : +${sh.value} ${sh.label}`) : "Châsse vide"}">`).join("");
  const runeTxt = summarizeRunes(it.shards || []);
  const forced = S.forced.has(it.id);
  return `<div class="item ${S.changed.has(it.slot) ? "changed" : ""} ${forced ? "forced-item" : ""}" data-slot="${it.slot}" title="Cliquer pour voir les autres items possibles">
    ${forced ? `<span class="forced-tag" title="Item forcé : gardé à chaque optimisation (retirer : clic sur l'item puis « Forcer », ou Items exclus / forcés)">📌 Forcé</span>` : ""}
    <div class="it-head"><img class="it-icon" src="${iconUrl(it.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div class="it-names"><div class="it-name" style="color:${it.color}">${esc(it.name)}</div>
      <div class="it-sub">${esc(it.slot_name)} · niv. ${it.level} · ${esc(it.rarity_name)}</div></div>
      <span class="it-swap">Changer ⇄</span></div>
    <div class="chip-row">${statChips(it)}</div>
    ${runes ? `<div class="runes">${runes}<span>${esc(runeTxt)}</span></div>` : ""}
    ${subLine(it, false)}${subLine(it, true)}
    ${obtain(it)}
  </div>`;
}
// Sublimation d'un item : cliquable pour en changer (comme un item)
function subLine(it, special) {
  const s = special ? it.special : it.sub;
  if (!s && (special ? !it.can_special : !(it.shards || []).length)) return "";
  const txt = s ? esc(s.name) : `+ ${special ? "sublimation épique / relique" : "sublimation"}`;
  const tip = s ? `${s.desc}${s.modeled ? "" : "\n(effet non chiffré)"}\n\nCliquer pour changer de sublimation` : "Cliquer pour choisir une sublimation";
  return `<div class="sub ${special ? "special" : ""} ${s ? "" : "empty"}" data-subslot="${it.slot}" data-special="${special ? 1 : 0}" title="${esc(tip)}">${txt} <span class="sub-swap">⇄</span></div>`;
}
function patternHtml(pattern) {
  return pattern.map((c) => `<img class="pat" src="assets/shards/shard${SHARD_FILE[c]}Full.png" alt="">`).join("");
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
    <div class="chip-row" style="margin-top:4px">${statChips(cur)}</div>${obtain(cur)}</div>
    <div class="btns"><button class="btn small" id="dr-ex" title="Ne plus proposer cet item aux prochaines optimisations">Exclure</button>
    <button class="btn small" id="dr-fo" title="Garder cet item aux prochaines optimisations">Forcer</button></div></div>`;
  $("#dr-ex").addEventListener("click", () => { S.forced.delete(cur.id); S.excluded.add(cur.id); refreshVis(); renderResult(); sfx("click"); toast("Item exclu pour les prochaines optimisations."); });
  $("#dr-fo").addEventListener("click", () => { S.excluded.delete(cur.id); S.forced.add(cur.id); refreshVis(); renderResult(); sfx("click"); toast("Item forcé pour les prochaines optimisations."); });
  $("#dr-list").innerHTML = `<div class="loading"><div class="spinner"></div>Recherche des items qui conviennent…</div>`;
  $("#dr-compare").innerHTML = `<p class="muted pad">Choisissez un item à gauche pour voir ce que vous gagnez et perdez.</p>`;
  $("#drawer").classList.remove("hidden");
  try {
    const r = await api("/api/alternatives", { opts: S.opts, build: S.view.build, slot });
    if (!r.items.length) { $("#dr-list").innerHTML = `<p class="muted pad">Aucun autre item possible pour cet emplacement.</p>`; return; }
    $("#dr-list").innerHTML = r.items.map((a, k) => `<div class="alt" data-k="${k}">
      <img class="it-icon" src="${iconUrl(a.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div><div class="it-name" style="color:${a.color}">${esc(a.name)}</div><div class="it-sub">niv. ${a.level} · ${esc(a.rarity_name)}</div>
      <div class="chip-row">${statChips(a, false)}</div>${obtain(a)}</div>
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
      <div><div class="it-name" style="color:${a.color}">${esc(a.name)}</div><div class="it-sub">à la place de ${esc(cur.name)}</div>${obtain(a)}</div></div>
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
      sfx("apply");
    } catch (e) { toast("Erreur : " + e.message); }
  });
}

// ===================================================================== changement de sublimation sur un item
async function openSubSwap(slot, special) {
  const cur = S.view.items.find((i) => i.slot === slot);
  const s = special ? cur.special : cur.sub;
  $("#dr-title").textContent = `${special ? "Sublimation épique / relique" : "Sublimation"} : ${cur.name}`;
  $("#dr-current").innerHTML = `<div class="cmp-head"><img class="it-icon" src="${iconUrl(cur.gfx)}" alt="">
    <div style="flex:1"><div class="it-name">${s ? esc(s.name) : "Aucune sublimation"}</div>
    <div class="it-sub">${special ? "Emplacement épique / relique de l'item" : `Châsses : ${patternHtml(cur.shards.map((x) => x.color))}`}</div>
    ${s ? `<div class="sub-desc">${esc(s.desc)}</div>` : ""}</div>
    ${s ? `<div class="btns"><button class="btn small" id="dr-sex" title="Ne plus utiliser cette sublimation aux prochaines optimisations">Exclure</button>
    <button class="btn small" id="dr-sfo" title="L'imposer aux prochaines optimisations">Imposer</button></div>` : ""}</div>`;
  if (s) {
    $("#dr-sex").addEventListener("click", () => { setSubPref(s.state, "ex"); toast("Sublimation exclue pour les prochaines optimisations."); });
    $("#dr-sfo").addEventListener("click", () => { setSubPref(s.state, "fo"); toast("Sublimation imposée pour les prochaines optimisations."); });
  }
  $("#dr-list").innerHTML = `<div class="loading"><div class="spinner"></div>Recherche des sublimations qui vont sur cet item…</div>`;
  $("#dr-compare").innerHTML = `<p class="muted pad">Choisissez une sublimation à gauche pour voir ce que vous gagnez et perdez.</p>`;
  $("#drawer").classList.remove("hidden");
  try {
    const r = await api("/api/sub_alternatives", { opts: S.opts, build: S.view.build, slot, special });
    const note = !special && r.other_colors
      ? `<p class="hint pad">${r.other_colors} autre(s) demandent d'autres couleurs de châsses : imposez-les dans l'onglet Sublimations et relancez.</p>` : "";
    if (!r.items.length) { $("#dr-list").innerHTML = `<p class="muted pad">Aucune sublimation possible ici.</p>${note}`; return; }
    $("#dr-list").innerHTML = r.items.map((a, k) => `<div class="alt" data-k="${k}">
      <div class="pat-box">${a.id ? patternHtml(a.pattern) : "∅"}</div>
      <div><div class="it-name">${esc(a.name)}${a.id && !a.modeled ? ` <small class="muted">(non chiffrée)</small>` : ""}</div>
      <div class="sub-desc">${esc(a.desc)}</div></div>
      <div class="delta ${pn(a.delta)}">${a.delta > 0 ? "+" : ""}${a.delta.toFixed(1)}<small>score</small></div></div>`).join("") + note;
    $$("#dr-list .alt").forEach((el) => el.addEventListener("click", () => {
      $$("#dr-list .alt").forEach((x) => x.classList.remove("sel"));
      el.classList.add("sel");
      showSubCompare(slot, s, r.items[+el.dataset.k]);
    }));
  } catch (e) {
    $("#dr-list").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
  }
}

function showSubCompare(slot, cur, a) {
  const rows = a.compare.map((r) => `<tr><td>${esc(r.label)}</td><td class="num muted">${fmt(r.old)}</td><td class="num">${fmt(r.new)}</td>
      <td class="num d ${r.diff > 0 ? "pos" : "neg"}">${r.diff > 0 ? "+" : ""}${fmt(r.diff)}</td></tr>`).join("");
  $("#dr-compare").innerHTML = `
    <div class="cmp-head"><div class="pat-box">${a.id ? patternHtml(a.pattern) : "∅"}</div>
      <div><div class="it-name">${esc(a.name)}</div><div class="it-sub">à la place de ${cur ? esc(cur.name) : "aucune"}</div></div></div>
    ${a.desc ? `<div class="sub-desc">${esc(a.desc)}</div>` : ""}
    ${a.id && !a.modeled ? `<div class="note">Effet non chiffré par l'optimiseur : le score ne reflète pas son intérêt réel.</div>` : ""}
    <table class="cmp-table"><tr><td></td><td class="num muted">Actuel</td><td class="num muted">Nouveau</td><td class="num muted">Écart</td></tr>${rows || `<tr><td colspan="4" class="muted">Aucune différence chiffrée</td></tr>`}</table>
    <button class="btn good" id="apply" style="width:100%">Valider le changement</button>`;
  $("#apply").addEventListener("click", async () => {
    try {
      S.view = await api("/api/view", { opts: S.opts, build: a.build });
      S.changed.add(slot);
      closeDrawers();
      renderResult();
      sfx("apply");
    } catch (e) { toast("Erreur : " + e.message); }
  });
}

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

// ===================================================================== aptitudes
const PRESET_ICON = { distance: "distance_mastery", melee: "melee_mastery", elemental: "elemental_damage", tank: "elemental_resistance", heal: "healing_mastery" };
const BRANCH_COLOR = { intelligence: "#6b2730", strength: "#2c5530", agility: "#4a2e66", fortune: "#1f4a5e", major: "#5a4a35" };
S.apt = {};
let presetSel = null;

function branchPoints(b, level) {
  if (b.branch === "major") return Math.max(0, Math.min(Math.floor((level + 25) / 50), 4));
  return Math.max(0, Math.floor((level + b.offset) / 4));
}
const lvl = () => +$("#level").value || 245;
const manualApt = () => segVal("char_mode") === "manual";
// Points affichés : les miens en manuel ; en auto, ceux que l'optimiseur a choisis pour le build affiché.
const aptPts = () => (manualApt() ? S.apt : (S.view && S.view.build.characteristics) || {});
const used = (b) => b.lines.reduce((t, l) => t + (aptPts()[l.key] || 0), 0);

function buildAptForm() {
  const col = { intelligence: 1, strength: 1, agility: 1, fortune: 2, major: 2 };
  for (const b of S.meta.aptitudes) {
    const el = document.createElement("div");
    el.className = "branch";
    el.style.setProperty("--bc", BRANCH_COLOR[b.branch] || "#333");
    el.innerHTML = `<div class="branch-head"><span>${esc(b.name)}</span><span class="avail" data-avail="${b.branch}"></span></div>` +
      b.lines.map((l) => `<div class="apt-line" data-key="${l.key}">
        <span class="ic"><img src="assets/aptitudes/${l.line}.png" alt="" onerror="this.src='assets/stats/empty_coin.png'"></span>
        <span class="lab">${esc(l.label)}${l.max > 1 ? ` <small>(max ${l.max})</small>` : ""}</span>
        <span class="apt-ctl"><button data-d="-1" aria-label="moins">−</button><input type="number" min="0" value="0"><button data-d="1" aria-label="plus">+</button></span></div>`).join("");
    $(`#apt-col${col[b.branch] || 2}`).appendChild(el);
    for (const l of b.lines) {
      const row = $(`.apt-line[data-key="${l.key}"]`, el);
      const set = (v) => {
        if (!manualApt()) { S.apt = { ...aptPts() }; S.aptMode = "manual"; }   // on part des aptitudes du build
        setSeg("char_mode", "manual");
        const free = branchPoints(b, lvl()) - used(b) + (S.apt[l.key] || 0);
        v = Math.max(0, Math.min(v, free, l.max ?? Infinity));
        if (v) S.apt[l.key] = v; else delete S.apt[l.key];
        aptChanged();
      };
      $$("button", row).forEach((bt) => bt.addEventListener("click", (e) => {
        set((aptPts()[l.key] || 0) + (e.shiftKey ? 10 : 1) * +bt.dataset.d);
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
  // passage en manuel : on part des points affichés (ceux du build), pas d'anciens points oubliés
  S.aptMode = segVal("char_mode");
  $("#char_mode").addEventListener("change", () => {
    const mode = segVal("char_mode");
    if (mode === "manual" && S.aptMode !== "manual" && S.view) S.apt = { ...(S.view.build.characteristics || {}) };
    S.aptMode = mode;
    renderApt(); liveUpdate();
  });
  $$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
}

function showTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  $("#tab-apt").classList.toggle("hidden", name !== "apt");
  $("#tab-subs").classList.toggle("hidden", name !== "subs");
  $("#result").classList.toggle("hidden", name !== "build");
  if (name === "subs") loadSubs();
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
      const n = aptPts()[l.key] || 0;
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
    : S.view ? "Aptitudes choisies par l'optimiseur pour ce build. Modifiez-en une (ou appliquez un preset) pour imposer les vôtres."
      : "L'optimiseur répartit lui-même les points : ils s'afficheront ici après le calcul.";
  $("#apt-res-box").classList.toggle("hidden", manual);
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
