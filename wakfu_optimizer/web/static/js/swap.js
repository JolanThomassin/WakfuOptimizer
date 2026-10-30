"use strict";
// Remplacement d'un item ou d'une sublimation sur le build, avec comparaison.

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
    const norm = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    $("#dr-list").innerHTML = `<input class="search dr-search" id="dr-search" type="search" placeholder="Filtrer les ${r.items.length} items par nom…">`
      + r.items.map((a, k) => `<div class="alt" data-k="${k}">
      <img class="it-icon" src="${iconUrl(a.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div><div class="it-name" style="color:${a.color}">${esc(a.name)}</div><div class="it-sub">niv. ${a.level} · ${esc(a.rarity_name)}</div>
      <div class="chip-row">${statChips(a, false)}</div>${obtain(a)}</div>
      <div class="delta ${pn(a.delta)}">${a.delta > 0 ? "+" : ""}${a.delta.toFixed(1)}<small>score</small></div></div>`).join("");
    $$("#dr-list .alt").forEach((el) => el.addEventListener("click", () => {
      $$("#dr-list .alt").forEach((x) => x.classList.remove("sel"));
      el.classList.add("sel");
      showCompare(slot, cur, r.items[+el.dataset.k]);
    }));
    $("#dr-search").addEventListener("input", (e) => {
      const q = norm(e.target.value.trim());
      $$("#dr-list .alt").forEach((el) => el.classList.toggle("hidden", !!q && !norm(r.items[+el.dataset.k].name).includes(q)));
    });
  } catch (e) {
    $("#dr-list").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
  }
}

// Lignes de comparaison : valeurs, écart, et ce que l'écart de cette stat seule change au score
// (0 = la stat ne compte pas pour ces réglages, ex. Maîtrise critique sur un tank).
const CMP_HEAD = `<tr><td></td><td class="num muted">Actuel</td><td class="num muted">Nouveau</td><td class="num muted">Écart</td>
  <td class="num muted" title="Écart de score dû à cette ligne seule (les autres stats inchangées)">Score</td></tr>`;
function cmpRows(list) {
  return list.map((r) => {
    const sc = r.stat === "score" ? r.diff : r.score;
    const scTxt = sc == null ? "" : `${sc > 0 ? "+" : ""}${sc.toFixed(1).replace(".", ",")}`;
    return `<tr class="${r.stat === "score" ? "cmp-total" : ""}"><td>${esc(r.label)}</td><td class="num muted">${fmt(r.old)}</td><td class="num">${fmt(r.new)}</td>
      <td class="num d ${r.diff > 0 ? "pos" : "neg"}">${r.diff > 0 ? "+" : ""}${fmt(r.diff)}</td>
      <td class="num d ${sc == null ? "" : pn(sc) || "muted"}">${scTxt}</td></tr>`;
  }).join("");
}

function showCompare(slot, cur, a) {
  const rows = cmpRows(a.compare);
  const gains = a.compare.filter((r) => r.diff > 0 && r.stat !== "score").length;
  const losses = a.compare.filter((r) => r.diff < 0 && r.stat !== "score").length;
  $("#dr-compare").innerHTML = `
    <div class="cmp-head"><img class="it-icon" src="${iconUrl(a.gfx)}" alt="">
      <div><div class="it-name" style="color:${a.color}">${esc(a.name)}</div><div class="it-sub">à la place de ${esc(cur.name)}</div>${obtain(a)}</div></div>
    <div class="muted" style="font-size:12px">${gains} stat(s) en hausse, ${losses} en baisse. Les châsses et la sublimation de l'emplacement sont conservées.</div>
    ${a.dropped.length ? `<div class="note">⚠ Retire aussi : ${esc(a.dropped.join(", "))} (une seule relique / épique, ou arme à deux mains).</div>` : ""}
    <table class="cmp-table">${CMP_HEAD}${rows || `<tr><td colspan="5" class="muted">Aucune différence</td></tr>`}</table>
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
    const norm = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    $("#dr-list").innerHTML = `<input class="search dr-search" id="dr-search" type="search" placeholder="Filtrer les ${r.items.length} items par nom…">`
      + r.items.map((a, k) => `<div class="alt" data-k="${k}">
      <div class="pat-box">${a.id ? patternHtml(a.pattern) : "∅"}</div>
      <div><div class="it-name">${esc(a.name)}${a.id && !a.modeled ? ` <small class="muted">(non chiffrée)</small>` : ""}${a.inactive ? ` <small class="neg-txt" title="Sa condition n'est pas remplie avec ce build : elle ne ferait rien">(condition non remplie)</small>` : ""}</div>
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
  const rows = cmpRows(a.compare);
  $("#dr-compare").innerHTML = `
    <div class="cmp-head"><div class="pat-box">${a.id ? patternHtml(a.pattern) : "∅"}</div>
      <div><div class="it-name">${esc(a.name)}</div><div class="it-sub">à la place de ${cur ? esc(cur.name) : "aucune"}</div></div></div>
    ${a.desc ? `<div class="sub-desc">${esc(a.desc)}</div>` : ""}
    ${a.id && !a.modeled ? `<div class="note">Effet non chiffré par l'optimiseur : le score ne reflète pas son intérêt réel.</div>` : ""}
    <table class="cmp-table">${CMP_HEAD}${rows || `<tr><td colspan="5" class="muted">Aucune différence chiffrée</td></tr>`}</table>
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
