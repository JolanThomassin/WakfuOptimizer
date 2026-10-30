"use strict";
// Langue du site (drapeaux de l'en-tête) : noms des données Ankama et textes de l'interface.
// Le code et le serveur écrivent en français. Chaque texte affiché (nœud de texte, title, placeholder) est traduit à la
// volée depuis I18N (i18n_dict.js), dont la clé est le texte français, nombres remplacés par {0}, {1}… Un texte sans
// traduction entière est traduit morceau par morceau (séparateurs « · », « : », « ; »…, nombres et parenthèses autour).
// Mode debug : les textes encore sans traduction s'accumulent dans UI.miss (console : [...UI.miss]).

const LANGS = {
  fr: { name: "Français", flag: `<rect width="1" height="2" fill="#0055a4"/><rect x="1" width="1" height="2" fill="#fff"/><rect x="2" width="1" height="2" fill="#ef4135"/>` },
  en: { name: "English", flag: `<rect width="3" height="2" fill="#012169"/><path d="M0,0L3,2M3,0L0,2" stroke="#fff" stroke-width=".4"/>
    <path d="M0,0L3,2M3,0L0,2" stroke="#c8102e" stroke-width=".14"/><path d="M1.5,0V2M0,1H3" stroke="#fff" stroke-width=".6"/>
    <path d="M1.5,0V2M0,1H3" stroke="#c8102e" stroke-width=".34"/>` },
  es: { name: "Español", flag: `<rect width="3" height="2" fill="#aa151b"/><rect y=".5" width="3" height="1" fill="#f1bf00"/>` },
  pt: { name: "Português", flag: `<rect width="3" height="2" fill="#da291c"/><rect width="1.2" height="2" fill="#046a38"/>
    <circle cx="1.2" cy="1" r=".42" fill="#ffe900"/><circle cx="1.2" cy="1" r=".24" fill="#da291c"/>` },
};
const LANG_COL = { en: 0, es: 1, pt: 2 };   // colonne de I18N
const UI = { lang: "fr", miss: new Set() };

// ===================================================================== traduction d'un texte
const NUM_RE = /\d+(?:[  ]\d{3})*(?:[.,]\d+)?/g;
const SEP_RE = /( · | — | : | ; | \/ )/;
const SEP_TR = { " · ": " · ", " — ": " — ", " : ": ": ", " ; ": " ; ", " / ": " / " };
const WORDS = [[/\bniv\. /g, { en: "lvl ", es: "niv. ", pt: "nív. " }], [/\bniveau /g, { en: "level ", es: "nivel ", pt: "nível " }]];
const LETTER = "A-Za-zÀ-ÿ";
const PREFIX_RE = new RegExp(`^([^${LETTER}(«]+)([${LETTER}(«].*)$`);   // « +12 », « 3. », « ✗ » devant le texte
const PCT_PREFIX_RE = new RegExp(`^([^${LETTER}(«%]+)(%.*)$`);   // « ✗ » devant « % Points de Vie »
const SUFFIX_RE = new RegExp(`^(.*[${LETTER})»])([^${LETTER})»]+)$`);   // « 245 », « ·  » après le texte
function trKey(s) {   // texte exact (sans espaces autour) -> traduction, ou null
  const nums = [];
  const key = s.replace(NUM_RE, (m) => { nums.push(m); return `{${nums.length - 1}}`; }).replace(/\s+/g, " ");
  const row = I18N[key];
  const out = row && row[LANG_COL[UI.lang]];
  return out == null ? null : out.replace(/\{(\d+)\}/g, (m, i) => nums[+i] ?? m);
}
const hasWords = (s) => new RegExp(`[${LETTER}]{2}`).test(s);
// Morceau sans séparateur : clé exacte, sinon on retire ce qui l'entoure (nombres, symboles, parenthèse) ou on traduit
// une liste « a, b » élément par élément. null : rien de traduit (nom d'item, de sublimation…).
function trPart(p) {
  if (!hasWords(p)) return p;
  const k = trKey(p);
  if (k != null) return k;
  let m = PREFIX_RE.exec(p);
  const pre = m && trPart(m[2]);
  if (pre != null) return m[1] + pre;
  m = PCT_PREFIX_RE.exec(p);
  const pct = m && trKey(m[2]);
  if (pct != null) return m[1] + pct;
  m = SUFFIX_RE.exec(p);
  const suf = m && trPart(m[1]);
  if (suf != null) return suf + m[2];
  m = /^(.*?)(\s*)\(([^()]*)\)$/.exec(p);
  if (m) {
    const a = m[1] ? trPart(m[1]) : "", b = trPart(m[3]);
    return a == null && b == null ? null : `${a ?? m[1]}${m[2]}(${b ?? m[3]})`;
  }
  if (p.includes(", ")) {
    const parts = p.split(", ").map(trPart);
    if (parts.every((x) => x != null)) return parts.join(", ");
  }
  let out = p;
  for (const [re, w] of WORDS) out = out.replace(re, w[UI.lang]);
  return out !== p ? out : null;
}
// `lines` : infobulle (title) dont chaque ligne se traduit à part ; ailleurs un retour à la ligne n'est qu'un espace.
function tr(s, lines = false) {   // texte français -> langue choisie (inchangé s'il n'a pas de traduction)
  if (UI.lang === "fr" || !hasWords(s)) return s;
  if (lines && s.trim().includes("\n")) return s.split("\n").map((l) => tr(l)).join("\n");
  const m = s.match(/^(\s*)([\s\S]*?)(\s*)$/);
  let out = trKey(m[2]);
  const pm = out == null && /^(.*\S)(\s+)\(([^()]*)\)$/.exec(m[2]);   // phrase connue suivie d'une parenthèse
  if (pm && trKey(pm[1]) != null) out = `${trKey(pm[1])}${pm[2]}(${trPart(pm[3]) ?? pm[3]})`;
  const px = out == null && PREFIX_RE.exec(m[2]);   // phrase connue précédée d'un symbole (« — », « ✓ »…)
  if (px && trKey(px[2]) != null) out = px[1] + trKey(px[2]);
  if (out == null) {
    let lost = false;
    const one = (p) => { const r = trPart(p); if (r == null) lost = true; return r ?? p; };
    const parts = m[2].split(SEP_RE);
    out = parts.length > 1 ? parts.map((p, i) => (i % 2 ? SEP_TR[p] : one(p))).join("") : one(m[2]);
    if (lost) miss(m[2]);
  }
  return m[1] + out + m[3];
}
// Texte brut en colonnes (export .txt) : chaque morceau entre deux espaces ou plus est traduit à part.
const trColumns = (text) => text.split("\n").map((l) => l.split(/(\s{2,})/).map((p) => tr(p)).join("")).join("\n");
function miss(s) {   // mode debug : clé à ajouter au dictionnaire
  let i = 0;
  if (DEBUG) UI.miss.add(s.replace(NUM_RE, () => `{${i++}}`).replace(/\s+/g, " "));
  return s;
}

// ===================================================================== traduction de la page
// Pour chaque nœud on garde le texte français et le texte affiché : si le code change le texte, le nouveau est le français.
const TR_ATTRS = ["title", "placeholder", "aria-label", "label"];
const trText = new WeakMap(), trAttr = new WeakMap();
function trTextNode(n) {
  const r = trText.get(n);
  const fr = r && n.data === r.shown ? r.fr : n.data;
  const shown = tr(fr);
  if (shown !== n.data) n.data = shown;
  trText.set(n, { fr, shown });
}
function trAttrs(el) {
  let rs = trAttr.get(el);
  for (const a of TR_ATTRS) {
    const v = el.getAttribute(a);
    if (v == null) continue;
    if (!rs) trAttr.set(el, rs = {});
    const r = rs[a];
    const fr = r && v === r.shown ? r.fr : v;
    const shown = tr(fr, true);
    if (shown !== v) el.setAttribute(a, shown);
    rs[a] = { fr, shown };
  }
}
function trTree(root) {
  if (root.nodeType === 3) { trTextNode(root); return; }
  if (root.nodeType !== 1 || root.closest("script, style, .notranslate")) return;
  trAttrs(root);
  const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.nodeType === 1 && (n.tagName === "SCRIPT" || n.tagName === "STYLE" || n.classList.contains("notranslate"))
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  for (let n = w.nextNode(); n; n = w.nextNode()) (n.nodeType === 3 ? trTextNode(n) : trAttrs(n));
}
// En français, rien à faire : un texte vu avant un retour au français est repris tel que le code l'a laissé.
new MutationObserver((muts) => {
  if (UI.lang === "fr") return;
  for (const m of muts) {
    if (m.type === "childList") m.addedNodes.forEach(trTree);
    else if (m.type === "characterData") trTextNode(m.target);
    else if (m.target.nodeType === 1 && !m.target.closest(".notranslate")) trAttrs(m.target);
  }
}).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: TR_ATTRS });

// ===================================================================== drapeaux de l'en-tête
const flagSvg = (l) => `<svg class="flag" viewBox="0 0 3 2" aria-hidden="true">${LANGS[l].flag}</svg>`;
function savedLang() {
  try { const l = localStorage.getItem("wakfu-optimizer:lang"); return LANGS[l] ? l : null; } catch (e) { return null; }
}
// Langue de l'interface (sans recharger les données) : appelée au démarrage et par setLang.
function useLang(l) {
  l = LANGS[l] ? l : "fr";
  $("#lang").value = l;
  UI.lang = l;
  document.documentElement.lang = l;
  document.body.dataset.lang = l;
  $("#lang-btn").innerHTML = flagSvg(l);
  $("#lang-btn").title = `${LANGS[l].name} (clic pour changer de langue)`;
  $("#lang-menu").innerHTML = Object.keys(LANGS).map((k) =>
    `<button type="button" data-lang="${k}" class="${k === l ? "on" : ""}">${flagSvg(k)}<span>${LANGS[k].name}</span></button>`).join("");
  trTree(document.body);
}
async function setLang(l) {
  $("#lang-menu").classList.add("hidden");
  if (l === UI.lang) return;
  try { localStorage.setItem("wakfu-optimizer:lang", l); } catch (e) { /* sans effet */ }
  useLang(l);
  sfx("click");
  // noms des données déjà affichés : on les redemande dans la nouvelle langue
  IT.cache = {}; subsCache = null;
  if (S.opts) S.opts.lang = l;
  if (S.view && S.opts) {
    try {
      const same = S.original === S.view;
      S.view = await api("/api/view", { opts: S.opts, build: S.view.build });
      if (same) S.original = S.view;
      else if (S.original) S.original = await api("/api/view", { opts: S.opts, build: S.original.build });
      renderResult();
    } catch (e) { /* sans effet */ }
  }
  if (!$("#tab-items").classList.contains("hidden")) { loadItemsTab(); renderPicked(); }
  if (!$("#tab-subs").classList.contains("hidden")) loadSubs();
}
$("#lang-btn").addEventListener("click", (e) => { e.stopPropagation(); $("#lang-menu").classList.toggle("hidden"); });
$("#lang-menu").addEventListener("click", (e) => { const b = e.target.closest("[data-lang]"); if (b) setLang(b.dataset.lang); });
document.addEventListener("click", (e) => { if (!e.target.closest(".lang-pick")) $("#lang-menu").classList.add("hidden"); });
useLang(savedLang() || "fr");
