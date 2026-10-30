"use strict";
// Onglet Aptitudes : aptitudes rapides, saisie manuelle, mise à jour en direct.

// ===================================================================== aptitudes
const PRESET_ICON = { dps_distance: "distance_mastery", dps_melee: "melee_mastery", dps_mixed: "elemental_damage", dps_rear: "rear_mastery",
  berserk: "berserk_mastery", tank: "elemental_resistance", heal: "healing_mastery", support_buff: "action_points", support_debuff: "force_of_will" };
// Aptitudes rapides : la répartition type de chaque archétype ; ceux de la classe en tête, l'archétype choisi mis en avant.
function renderPresets() {
  if (!$("#apt-presets") || !S.meta || !Object.keys(ARCHETYPES).length) return;
  const recs = classArchs(curClass()), cur = $("#archetype").value;
  const keys = [...recs, ...Object.keys(ARCHETYPES).filter((k) => !recs.includes(k))];
  $("#apt-presets").innerHTML = keys.map((k) =>
    `<button class="preset${recs.includes(k) ? " rec" : ""}${k === cur ? " cur" : ""}" data-p="${k}" title="${recs.includes(k) ? "Habituel pour cette classe" : "Peu joué avec cette classe"}">`
    + `<span class="ic"><img src="assets/stats/${PRESET_ICON[k] || "empty_coin"}.png" alt=""></span>${esc(ARCHETYPES[k].name)}${k === cur ? " <small>· archétype choisi</small>" : ""}</button>`).join("");
  $$("#apt-presets .preset").forEach((b) => b.addEventListener("click", () => selectPreset(b.dataset.p)));
  if (presetSel) $$("#apt-presets .preset").forEach((b) => b.classList.toggle("sel", b.dataset.p === presetSel.key));
}
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
  renderPresets();
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
  $("#tab-items").classList.toggle("hidden", name !== "items");
  $("#tab-explain").classList.toggle("hidden", name !== "explain");
  $("#tab-weights").classList.toggle("hidden", name !== "weights");
  if (name === "weights") loadWeights();
  if (name === "items") { loadItemsTab(); renderPicked(); }
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
  const r = await api(`/api/preset?name=${key}&level=${lvl()}&cls=${$("#cls").value}`);
  const pts = r.points;
  presetSel = { key, pts };
  const labels = Object.fromEntries(S.meta.aptitudes.flatMap((b) => b.lines.map((l) => [l.key, `${b.name} · ${l.label}`])));
  $("#apt-detail").innerHTML = `<div><b>${esc(ARCHETYPES[key].name)}</b> — ${esc(r.desc)}</div><ul class="preset-detail">` +
    Object.entries(pts).map(([k, v]) => `<li><span>${esc(labels[k] || k)}</span><b>${v}</b></li>`).join("") + "</ul>";
  $("#apt-apply").disabled = false;
}
function applyPreset() {
  if (!presetSel) return;
  S.apt = { ...presetSel.pts };
  aptChanged();
  toast(`Preset appliqué (niveau ${lvl()}).`);
}
