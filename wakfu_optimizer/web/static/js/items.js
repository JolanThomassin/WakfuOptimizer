"use strict";
// Onglet Items et fenêtre des items forcés / exclus.

// ===================================================================== onglet Items (forcés / exclus)
const IT = { slot: "HEAD", rars: new Set(), timer: null, cache: {} };
const SLOT_TABS = ["HEAD", "NECK", "CHEST", "LEFT_HAND", "LEGS", "BACK", "SHOULDERS", "BELT", "FIRST_WEAPON", "SECOND_WEAPON", "ACCESSORY", "PET", "MOUNT"];

function buildItemsTab() {
  const names = Object.fromEntries(S.meta.slots.map((s) => [s.key, s.name]));
  $("#it-slots").innerHTML = SLOT_TABS.filter((k) => names[k]).map((k) =>
    `<button type="button" data-itslot="${k}">${esc(k === "LEFT_HAND" ? "Anneaux" : names[k])}</button>`).join("");
  $("#it-rars").innerHTML = S.meta.rarities.filter((r) => r.id > 0).map((r) =>
    `<button class="toggle plain small" data-itrar="${r.id}"><span style="color:${r.color}">●</span>&nbsp;${esc(r.name)}</button>`).join("");
  $("#it-slots").addEventListener("click", (e) => {
    const b = e.target.closest("[data-itslot]");
    if (!b) return;
    IT.slot = IT.slot === b.dataset.itslot && $("#it-q").value.trim().length >= 2 ? "" : b.dataset.itslot;
    loadItemsTab();
  });
  $("#it-rars").addEventListener("click", (e) => {
    const b = e.target.closest("[data-itrar]");
    if (!b) return;
    const r = +b.dataset.itrar;
    IT.rars.has(r) ? IT.rars.delete(r) : IT.rars.add(r);
    loadItemsTab();
  });
  $("#it-bracket").addEventListener("change", loadItemsTab);
  $("#it-q").addEventListener("input", () => { clearTimeout(IT.timer); IT.timer = setTimeout(loadItemsTab, 250); });
  // forcer / exclure / retirer, depuis la liste ou les colonnes de droite
  $("#tab-items").addEventListener("click", (e) => {
    const b = e.target.closest("[data-itfo],[data-itex],[data-itrm]");
    if (!b) return;
    const id = +(b.dataset.itfo || b.dataset.itex || b.dataset.itrm);
    const wasFo = S.forced.has(id), wasEx = S.excluded.has(id);
    S.forced.delete(id); S.excluded.delete(id);
    if (b.dataset.itfo && !wasFo) S.forced.add(id);
    if (b.dataset.itex && !wasEx) S.excluded.add(id);
    sfx("click");
    refreshVis();
    renderItemRows();
    renderPicked();
    if (S.view) renderResult();
  });
}

function updateItemsBadge() {
  const b = $("#items-badge");
  if (!b) return;
  b.textContent = `${S.forced.size} forcé(s) · ${S.excluded.size} exclu(s)`;
  b.classList.toggle("hidden", !(S.forced.size + S.excluded.size));
  b.classList.toggle("manual", !!(S.forced.size + S.excluded.size));
}

async function loadItemsTab() {
  const q = $("#it-q").value.trim();
  $$("#it-slots [data-itslot]").forEach((b) => b.classList.toggle("on", b.dataset.itslot === IT.slot));
  $$("#it-rars [data-itrar]").forEach((b) => b.classList.toggle("on", IT.rars.has(+b.dataset.itrar)));
  if (q.length < 2 && !IT.slot) { IT.slot = "HEAD"; return loadItemsTab(); }
  const params = new URLSearchParams({ q, slot: q.length >= 2 ? "" : IT.slot, level: $("#level").value, lang: $("#lang").value,
    rarity: [...IT.rars].join(","), bracket: $("#it-bracket").checked ? "1" : "0", limit: "150" });
  $("#it-results").innerHTML = `<div class="loading"><div class="spinner"></div>Chargement des items…</div>`;
  try {
    IT.list = await api(`/api/items?${params}`);
    IT.list.forEach((it) => { IT.cache[it.id] = it; });
    $("#it-count").textContent = IT.list.length >= 150 ? "150 premiers items : affinez la recherche." : `${IT.list.length} item(s)`;
    renderItemRows();
  } catch (e) {
    $("#it-results").innerHTML = `<p class="err pad">Erreur : ${esc(e.message)}</p>`;
  }
}

function itemRow(it, compact = false) {
  const fo = S.forced.has(it.id), ex = S.excluded.has(it.id);
  const btns = compact
    ? `<button class="btn small" data-itrm="${it.id}" title="Retirer de la liste">✕</button>`
    : `<button class="btn small ${fo ? "on-fo" : ""}" data-itfo="${it.id}" title="Toujours garder cet item">${fo ? "✓ Forcé" : "Forcer"}</button>
       <button class="btn small ${ex ? "on-ex" : ""}" data-itex="${it.id}" title="Ne jamais utiliser cet item">${ex ? "✕ Exclu" : "Exclure"}</button>`;
  return `<div class="it-row ${fo ? "fo" : ""} ${ex ? "ex" : ""}" style="--rc:${it.color}">
    <span class="it-iconbox"><img class="it-icon" src="${iconUrl(it.gfx)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'"></span>
    <div class="it-names"><div class="it-name">${esc(it.name)}</div>
      <div class="it-sub">${esc(it.slot_name || it.type)} · niv. ${it.level} · <span class="rar">${esc(it.rarity_name)}</span></div></div>
    ${compact ? "" : `<div class="chip-row">${statChips(it, false)}</div>`}
    <div class="btns">${btns}</div></div>`;
}
function renderItemRows() {
  if (!IT.list) return;
  $("#it-results").innerHTML = IT.list.map((it) => itemRow(it)).join("") || `<p class="muted pad">Aucun item ne correspond.</p>`;
}
async function renderPicked() {
  updateItemsBadge();
  const ids = [...S.forced, ...S.excluded].filter((i) => !IT.cache[i]);
  if (ids.length) {
    try { (await api(`/api/items?ids=${ids.join(",")}&level=${$("#level").value}&lang=${$("#lang").value}`)).forEach((it) => { IT.cache[it.id] = it; }); }
    catch (e) { /* sans effet */ }
  }
  const list = (set) => [...set].filter((i) => IT.cache[i]).map((i) => itemRow(IT.cache[i], true)).join("");
  $("#it-fo").innerHTML = list(S.forced) || `<p class="muted">Aucun item forcé.</p>`;
  $("#it-ex").innerHTML = list(S.excluded) || `<p class="muted">Aucun item exclu.</p>`;
  $("#it-fo-n").textContent = S.forced.size ? `(${S.forced.size})` : "";
  $("#it-ex-n").textContent = S.excluded.size ? `(${S.excluded.size})` : "";
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
