"use strict";
// Démarrage : chargement des données (/api/meta) et premier affichage. Chargé en dernier.

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
    else applyArchetype(o.archetype, curClass());   // archétype enregistré (ou celui de la classe s'il n'existe plus)
    ["priorities", "constraints", "subs"].forEach((k) => setPanel(k, false));
    renderPresets();
    renderExplain();
    refreshVis();
  }
}
$("#go").disabled = true;
if (BROWSER) $("#reload").classList.add("hidden");
$$("#picker [data-close]");
$("#pk-search").addEventListener("input", () => { clearTimeout(pkTimer); pkTimer = setTimeout(searchItems, 250); });
waitMeta();
