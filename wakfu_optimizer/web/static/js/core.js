"use strict";
// Outils communs : DOM, icônes de stats, appels /api, effets sonores, menu, état global S, widgets.

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

// ===================================================================== menu de gauche repliable
function setSide(collapsed) {
  document.body.classList.toggle("side-collapsed", collapsed);
  $("#side-btn").classList.toggle("on", !collapsed);
  $("#side-btn").title = collapsed ? "Afficher les réglages" : "Masquer les réglages";
}
$("#side-btn").addEventListener("click", () => setSide(!document.body.classList.contains("side-collapsed")));

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
  subForced: new Set(), subExcluded: new Set(), subLevels: {}, elOrder: [],
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
