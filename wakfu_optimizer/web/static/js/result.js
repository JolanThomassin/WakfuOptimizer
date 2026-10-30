"use strict";
// Onglet Build : résultat, détail d'une stat, cartes d'items et pastilles de stats.

// ===================================================================== résultat
function sc(stat, label, value, cls = "") {
  return `<div class="sc" data-stat="${stat}" title="Cliquer : d'où vient cette stat">${icon(stat, label)}<span class="lab">${esc(label)}</span><span class="val ${cls}">${value}</span></div>`;
}
const pn = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");

// affichage des items : grille (cartes) ou liste (une ligne par item), retenu dans le navigateur
function itemsView() {
  try { return localStorage.getItem("wakfu-optimizer:view") === "list" ? "list" : "grid"; } catch (e) { return "grid"; }
}

function archName() {
  const a = S.opts && ARCHETYPES[S.opts.archetype];
  return a ? a.name : "";
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
        <div><div class="name">${esc(v.class.name)}</div><div class="muted els">Niveau ${v.level} · ${v.elements.map((e) => icon(e, EL_FR[e])).join("")}</div>
          ${archName() ? `<div class="arch-tag" title="${esc(ARCHETYPES[S.opts.archetype].desc)}">${esc(archName())}</div>` : ""}</div>
        <div class="scores"><div title="Maîtrise utilisée par vos sorts : élémentaire (moitié l’élément joué le plus faible, moitié moyenne selon la priorité des éléments) + portée + secondaires comptées"><span class="muted">Maîtrise totale</span> <b>${fmt(v.mastery_used)}</b></div>
          <div title="Somme des résistances fixes des quatre éléments"><span class="muted">Résistance totale</span> <b>${fmt(ELEMENTS.reduce((t, e) => t + v.res_flat[e], 0))}</b></div>
          ${v.removal ? `<div title="Retraits PA / PM grâce à la Volonté (cible à 0 Volonté) : base du sort × 0,5 × ce facteur"><span class="muted">Retraits</span> <b>×${v.removal.toFixed(2)}</b></div>` : ""}</div>
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
      <div class="items-grid ${itemsView()}">${passiveCard(v)}${v.items.map(itemCard).join("")}</div>
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
  $("#copy").addEventListener("click", () => navigator.clipboard.writeText(trColumns(v.text)).then(() => toast("Build copié.")));
  $("#export-txt").addEventListener("click", () => {
    download(new Blob([trColumns(v.text)], { type: "text/plain;charset=utf-8" }), `build_${v.class.key}_${v.level}.txt`);
    toast("Build téléchargé en texte.");
  });
  $("#export-png").addEventListener("click", () => exportPng(v));
  const rv = $("#revert");
  if (rv) rv.addEventListener("click", () => { S.view = S.original; S.changed = new Set(); renderResult(); });
}

// ===================================================================== détail d'une stat
const KIND_LABEL = { passive: "Passif de classe", base: "Base", item: "Items", random: "Items (au choix)", rune: "Runes", apt: "Aptitudes", sub: "Sublimations", pct: "% PV" };
function srcIcon(x) {
  const img = (src, cls = "") => `<img class="sp-ic ${cls}" src="${src}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
  switch (x.kind) {
    case "item": case "random": return img(iconUrl(x.ref), "it");
    case "rune": return img(`assets/shards/shard${SHARD_FILE[x.ref] || "White"}Full.png`);
    case "apt": return img(`assets/aptitudes/${x.ref}.png`);
    case "base": case "passive": return img(`assets/classes/${S.view.class.key}.png`, "it");
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
// la page défile : la fenêtre ne suit pas, on la ferme ; défiler dans la fenêtre elle-même la laisse ouverte
document.addEventListener("scroll", (e) => {
  const pop = $("#stat-pop");
  if (!pop.contains(e.target)) pop.classList.add("hidden");
}, true);

// Libellés courts des stats (affichés en mode liste)
const SHORT = {
  ap: "PA", mp: "PM", wp: "PW", range: "Portée", hp: "PV", hp_pct: "% PV", crit_rate: "% Crit.", block: "% Parade",
  elem_mastery: "Maîtrise élém.", melee_mastery: "M. mêlée", distance_mastery: "M. distance", crit_mastery: "M. critique",
  rear_mastery: "M. dos", berserk_mastery: "M. berserk", heal_mastery: "M. soin", dmg_pct: "% Dommages",
  elem_res: "Rés. élém.", lock: "Tacle", dodge: "Esquive", initiative: "Initiative", willpower: "Volonté", control: "Contrôle",
  crit_res: "Rés. critique", rear_res: "Rés. dos", wisdom: "Sagesse", prospecting: "Prospection",
};
const lbl = (k) => (SHORT[k] ? ` <span class="lb">${SHORT[k]}</span>` : "");

// Stats d'un item : les maîtrises (et résistances) d'élément de même valeur sont regroupées sur une seule
// pastille avec les icônes des éléments côte à côte, au lieu d'une ligne par élément.
function statChips(it, withEls = true) {
  const groups = { mastery: new Map(), res: new Map() };   // valeur -> [éléments]
  const others = [];
  const add = (kind, v, e) => { const m = groups[kind]; if (!m.has(v)) m.set(v, []); if (!m.get(v).includes(e)) m.get(v).push(e); };
  for (const x of it.stats) {
    const m = /^(fire|water|earth|air)_(mastery|res)$/.exec(x.stat);
    if (m) add(m[2] === "res" ? "res" : "mastery", x.value, m[1]);
    else others.push(x);
  }
  const out = others.map((x) => chip(x.stat, `<b>${signed(x.value)}</b>${lbl(x.stat)}`, x.label, x.value < 0 ? "neg" : ""));
  const randLabel = [];
  for (const [kind, list] of [["mastery", it.rand_mastery], ["res", it.rand_res]]) {
    for (const r of list || []) {
      if (withEls && r.els && r.els.length) r.els.forEach((e) => add(kind, r.value, e));
      else randLabel.push(chip(kind === "res" ? "elem_res" : "elem_mastery", `+${r.value} <small>×${r.n}</small>`,
        `${kind === "res" ? "Résistance" : "Maîtrise"} sur ${r.n} élément(s) au choix`));
    }
  }
  for (const kind of ["mastery", "res"]) {
    for (const [v, els] of groups[kind]) {
      const order = ELEMENTS.filter((e) => els.includes(e));
      const what = kind === "res" ? "Résistance" : "Maîtrise";
      const tip = `${what} (${order.map((e) => EL_FR[e]).join(", ")}) : ${signed(v)}`;
      const icons = order.map((e) => `<img src="assets/stats/${e}_${kind === "res" ? "res" : "mastery"}.png" alt="">`).join("");
      out.push(`<span class="chip els ${v < 0 ? "neg" : ""}" title="${esc(tip)}"><span class="el-icons">${icons}</span><b>${signed(v)}</b>`
        + ` <span class="lb">${kind === "res" ? "Rés." : "Maîtrise"}</span></span>`);
    }
  }
  out.push(...randLabel);
  if (it.special_effect) out.push(`<span class="chip" title="Effet spécial non compté dans le score"><small>&nbsp;+ effet spécial</small></span>`);
  return out.join("");
}

// Comment obtenir l'item : recette (données Ankama) + lien wiki (butins de monstres, coffres, succès)
function obtain(it) {
  const parts = [];
  if (it.craft) {
    const ing = it.craft.ingredients.map(([n, q]) => `${q} × ${n}`).join("\n");
    parts.push(`<span class="craft" title="${esc(`Recette : ${it.craft.job} niv. ${it.craft.level}\n${ing}`)}">⚒ ${it.craft.level}</span>`);
  }
  if (it.shop) parts.push(`<span class="shop" title="Item boutique">€</span>`);
  if (it.wiki) parts.push(`<a href="${esc(it.wiki)}" target="_blank" rel="noopener" onclick="event.stopPropagation()"
    title="Où l'obtenir : monstres et taux de butin, coffres, succès (wakfu.wiki.gg)">↗</a>`);
  return `<div class="obtain">${parts.join("")}</div>`;
}

// Passif inné de la classe : toujours actif, en tête des items
// Case « passif de classe » en tête des items, seulement s'il donne des stats (description au survol)
function passiveCard(v) {
  const p = v.passive;
  if (!p || !p.stats.length) return "";
  const tiles = p.stats.map((x) => `<div class="pv-tile ${x.value < 0 ? "neg" : ""}">${icon(x.stat, x.label)}
      <b>${signed(x.value)}</b><span>${esc(x.label)}</span></div>`).join("");
  return `<div class="item passive-item" style="--rc:#e8a93a" title="${esc(`${p.name} : ${p.desc}`)}">
    <span class="passive-ribbon">Passif</span>
    <div class="it-head">
      <span class="it-iconbox"><img class="it-icon" src="assets/classes/${v.class.key}.png" alt=""></span>
      <div class="it-names"><div class="it-name">${esc(p.name)}</div><div class="it-sub">Passif de classe · ${esc(v.class.name)}</div></div>
    </div>
    <div class="pv-tiles">${tiles}</div>
    <div class="it-foot passive-foot"><span>Toujours actif</span><span class="muted">survol : détail</span></div>
  </div>`;
}

function itemCard(it) {
  const runes = (it.shards || []).map(runeBadge).join("");
  const forced = S.forced.has(it.id);
  return `<div class="item ${S.changed.has(it.slot) ? "changed" : ""} ${forced ? "forced-item" : ""}" data-slot="${it.slot}" style="--rc:${it.color}"
      title="Cliquer pour voir les autres items possibles">
    ${forced ? `<span class="forced-tag" title="Item forcé : gardé à chaque optimisation">Forcé</span>` : ""}
    <div class="it-head">
      <span class="it-iconbox"><img class="it-icon" src="${iconUrl(it.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'"></span>
      <div class="it-names"><div class="it-name" title="${esc(it.name)}">${esc(it.name)}</div>
        <div class="it-sub">${forced ? `<span class="forced-pill" title="Item forcé : gardé à chaque optimisation">Forcé</span>` : ""}${esc(it.slot_name)} · niv. ${it.level} · <span class="rar">${esc(it.rarity_name)}</span></div></div>
      <span class="it-swap" title="Changer d'item">⇄</span>
    </div>
    <div class="chip-row">${statChips(it)}</div>
    <div class="it-foot">
      ${runes ? `<div class="runes" title="${esc(summarizeRunes(it.shards || []))}">${runes}</div>` : ""}
      <div class="it-subs">${subLine(it, false)}${subLine(it, true)}</div>
      ${obtain(it)}
    </div>
  </div>`;
}
// Sublimation d'un item : pastille cliquable pour en changer (comme un item) ; « + » discret si vide
function subLine(it, special) {
  const s = special ? it.special : it.sub;
  if (!s && (special ? !it.can_special : !(it.shards || []).length)) return "";
  const tip = s ? `${s.desc}${s.modeled ? "" : "\n(effet non chiffré)"}\n\nCliquer pour changer de sublimation`
    : `Ajouter une sublimation${special ? " épique / relique" : ""}`;
  const txt = s ? `${special ? "★" : "✦"} ${esc(s.name)}` : `+ ${special ? "épique" : "subli"}`;
  return `<span class="sub ${special ? "special" : ""} ${s ? "" : "empty"}" data-subslot="${it.slot}" data-special="${special ? 1 : 0}" title="${esc(tip)}">${txt}</span>`;
}
function patternHtml(pattern) {
  return pattern.map((c) => `<img class="pat" src="assets/shards/shard${SHARD_FILE[c]}Full.png" alt="">`).join("");
}

// Une châsse : la couleur en fond, l'icône de la stat de la rune par-dessus et sa valeur à côté
function runeBadge(sh) {
  const shard = `<img class="rn-shard" src="assets/shards/shard${SHARD_FILE[sh.color]}${sh.rune ? "Full" : "Empty"}.png" alt="">`;
  if (!sh.rune) return `<span class="rn empty" title="Châsse vide">${shard}</span>`;
  const tip = `${sh.rune} niv. ${sh.level} : +${sh.value} ${sh.label}`;
  return `<span class="rn" title="${esc(tip)}"><span class="rn-gem">${shard}${icon(sh.stat, tip)}</span><b>+${sh.value}</b></span>`;
}

function summarizeRunes(shards) {
  const acc = {};
  for (const s of shards) if (s.rune) acc[s.label] = (acc[s.label] || 0) + s.value;
  return Object.entries(acc).map(([k, v]) => `+${v} ${k}`).join(" · ");
}
