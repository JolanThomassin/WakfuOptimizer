"use strict";
// Lancement d'un calcul, barre de progression, suivi de la tâche (/api/job).

// ===================================================================== optimisation
async function start() {
  const o = options();
  const arch = ARCHETYPES[o.archetype];
  if (!o.elements.length && !(arch && arch.hide_elements)) { toast("Choisissez au moins un élément."); return; }   // tank : aucun
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
  S.explain = r.explain || null;
  renderExplain();
  subsCache = null;
  showTab("build");
  renderResult();
  $("#apt-from-build").disabled = false;
  renderApt();   // en mode auto, l'onglet Aptitudes montre ceux choisis par l'optimiseur
}
