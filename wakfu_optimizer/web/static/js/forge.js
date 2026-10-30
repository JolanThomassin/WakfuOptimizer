"use strict";
// Onglet Build sombre (mode debug) : un bouton, des sublimations qui vont bien ensemble (engine/combos.ideas).
// Le premier clic explore les corps types (quelques secondes) ; les suivants montrent les combos suivants.

const FORGE = { ideas: null, pos: 0, busy: false, timer: 0 };
const FG_PER_CLICK = 3;
const FG_OBJ = { damage: "Dégâts", survival: "Survie", score: "Équilibré" };
const FG_SIGIL = `<svg class="fg-sigil" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="46"/><circle cx="50" cy="50" r="38"/>
  <path d="M50 12 L83 69 L17 69 Z"/><path d="M50 88 L17 31 L83 31 Z"/><circle cx="50" cy="50" r="9"/>
  ${Array.from({ length: 12 }, (_, i) => { const a = (i * Math.PI) / 6; return `<circle class="dot" cx="${50 + 42 * Math.cos(a)}" cy="${50 + 42 * Math.sin(a)}" r="1.6"/>`; }).join("")}</svg>`;

const f1 = (v) => (+v).toFixed(1).replace(".", ",");
function fgGain(g, obj) {   // gain dans l'unité de l'objectif : % de dégâts / PV effectifs, ou points de score
  if (obj === "score") return `+${f1(g)} pts`;
  return `+${f1((Math.exp(g / 100) - 1) * 100)} % ${obj === "damage" ? "dégâts" : "PV eff."}`;
}
const fgIcon = (gfx) => `<img src="${iconUrl(gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;

function renderForge() {
  const page = $("#tab-forge");
  if (page.dataset.ready) return;
  page.dataset.ready = "1";
  page.innerHTML = `<div class="forge">
    <div class="fg-bg" aria-hidden="true"><i></i><i></i><i></i></div>
    <section class="card fg-head">${FG_SIGIL}
      <div><h2>Build sombre</h2><p class="hint">Des sublimations qui vont bien ensemble : l'une fait monter une stat, l'autre s'en déclenche.</p></div>
      <button class="btn fg-go" id="fg-go" type="button">Générer des combos</button></section>
    <div id="fg-out" class="fg-out"></div></div>`;
  $("#fg-go").addEventListener("click", forgeNext);
  $("#fg-out").addEventListener("click", forgeClick);
}

async function forgeNext() {
  if (FORGE.busy) return;
  if (!FORGE.ideas) await forgeLoad();
  if (!FORGE.ideas || !FORGE.ideas.length) return;
  if (FORGE.pos >= FORGE.ideas.length) FORGE.pos = 0;
  const shown = FORGE.ideas.slice(FORGE.pos, FORGE.pos + FG_PER_CLICK);
  FORGE.pos += FG_PER_CLICK;
  $("#fg-out").innerHTML = `<div class="fg-cards">${shown.map(forgeCard).join("")}</div>
    <p class="hint fg-count">${Math.min(FORGE.pos, FORGE.ideas.length)} / ${FORGE.ideas.length} combos · recliquez pour les suivants</p>`;
  $("#fg-go").textContent = "Autres combos";
  sfx("done");
}

async function forgeLoad() {
  FORGE.busy = true;
  $("#fg-go").disabled = true;
  sfx("start");
  const t0 = performance.now();
  $("#fg-out").innerHTML = `<div class="card fg-loading">${FG_SIGIL}<div class="fg-phase">Recherche des combos…</div>
    <div class="fg-pbar"><span id="fg-pfill"></span></div></div>`;
  clearInterval(FORGE.timer);
  FORGE.timer = setInterval(() => {   // ~20 s en local : barre indicative
    const fill = $("#fg-pfill");
    if (fill) fill.style.width = `${(100 * (1 - Math.exp(-(performance.now() - t0) / 9000))).toFixed(1)}%`;
  }, 150);
  try {
    FORGE.ideas = (await api("/api/ideas", { opts: S.opts || options() })).ideas;
    FORGE.pos = 0;
    if (!FORGE.ideas.length) $("#fg-out").innerHTML = `<div class="card fg-loading"><p>Aucun combo trouvé.</p></div>`;
  } catch (e) {
    $("#fg-out").innerHTML = "";
    toast("Erreur : " + e.message);
    sfx("fail");
  } finally {
    clearInterval(FORGE.timer);
    FORGE.busy = false;
    $("#fg-go").disabled = false;
  }
}

function forgeCard(x, k) {
  const i = FORGE.ideas.indexOf(x);
  const subs = x.parts.map((p) => `<li title="${esc(p.desc)}"><span class="fg-ic">${fgIcon(p.gfx)}</span>
      <span class="fg-sn"><b>${esc(p.sub)}</b>${p.kind !== "normal" ? ` <span class="tag ${p.kind}">${p.kind === "epic" ? "Épique" : "Relique"}</span>` : ""}
        <small>${esc(p.desc)}</small></span>
      ${p.pattern.length ? `<span class="fg-pat" title="Couleurs de châsses">${patternHtml(p.pattern)}</span>` : ""}</li>`).join("");
  return `<article class="card fg-card" style="animation-delay:${k * 0.08}s">
    <div class="fg-ch"><h3>${esc(x.name)}</h3>
      <span class="tag">${esc(FG_OBJ[x.objective])}</span>${x.power ? `<span class="tag on">Deck le plus fort</span>` : ""}</div>
    <div class="fg-gain"><b>${fgGain(x.gain, x.objective)}</b>${x.synergy > 0.3
      ? `<small title="Ce que le combo rapporte en plus de la somme de ses sublimations prises une à une">synergie : ${fgGain(x.synergy, x.objective)}</small>` : ""}</div>
    <ul class="fg-subs">${subs}</ul>
    <div class="fg-why">${x.why.map((w) => `<p>${esc(w)}</p>`).join("")}</div>
    <p class="hint fg-body">${esc(x.body)}</p>
    <div class="fg-actions"><button class="btn small" data-fgimpose="${i}" title="Impose ces sublimations à la prochaine optimisation, à la place des sublimations imposées actuelles">Imposer à l'optimiseur</button>
      <button class="btn small" data-fgcopy="${i}">📋 Copier</button></div>
  </article>`;
}

function forgeClick(e) {
  const imp = e.target.closest("[data-fgimpose]"), cp = e.target.closest("[data-fgcopy]");
  if (imp) {
    const x = FORGE.ideas[+imp.dataset.fgimpose];
    S.subForced = new Set(Object.keys(x.forced).map(Number));
    S.subLevels = {};
    for (const [s, lvl] of Object.entries(x.forced)) { S.subExcluded.delete(+s); if (lvl > 1) S.subLevels[+s] = lvl; }
    updateSubsBadge();
    if (subsCache) renderSubs();
    sfx("apply");
    toast(`${S.subForced.size} sublimation(s) imposée(s) à la place des précédentes : relancez l'optimisation.`);
  }
  if (cp) {
    const x = FORGE.ideas[+cp.dataset.fgcopy];
    const text = [`${x.name} (${fgGain(x.gain, x.objective)})`, ...x.parts.map((p) => `- ${p.sub}`), ...x.why].join("\n");
    navigator.clipboard.writeText(text).then(() => toast("Combo copié."));
  }
}
