"use strict";
// Web Worker : Python (Pyodide) + moteur Wakfu Optimizer, hors du fil de l'interface.
importScripts("https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.js");

const status = (msg) => postMessage({ type: "status", msg });
let mod = null;

async function getBytes(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} : HTTP ${r.status}`);
  return new Uint8Array(await r.arrayBuffer());
}

const ready = (async () => {
  try {
    const build = await (await fetch("../build.json", { cache: "no-store" })).json();
    status("Chargement de Python dans le navigateur…");
    const py = await loadPyodide();
    status("Chargement du solveur…");
    await py.loadPackage(["numpy", "pyyaml", "highspy"]);
    status("Chargement des données Ankama…");
    const [zip, ...files] = await Promise.all([getBytes(`../${build.py}`),
      ...build.files.map((f) => getBytes(`../${build.data}${f}`))]);
    py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide" });
    py.FS.mkdirTree("/data");
    build.files.forEach((f, i) => py.FS.writeFile(`/data/${f}`, files[i]));
    status("Lecture des items…");
    mod = py.pyimport("wakfu_optimizer.web.browser");
    mod.init("/data", build.version);
    postMessage({ type: "ready" });
  } catch (e) {
    postMessage({ type: "error", msg: `Le moteur n'a pas pu démarrer : ${e.message || e}` });
    throw e;
  }
})();

onmessage = async (e) => {
  const m = e.data;
  try {
    await ready;
    if (m.type === "optimize") {
      const progress = (msg, frac) => postMessage({ type: "progress", job: m.job, msg, frac });
      postMessage({ type: "result", job: m.job, result: JSON.parse(mod.optimize(m.opts, progress)) });
    } else {
      postMessage({ type: "reply", id: m.id, json: mod.request(m.method, m.path, m.body, m.settings) });
    }
  } catch (err) {
    const msg = String(err.message || err).split("\n").filter(Boolean).pop();
    if (m.type === "optimize") {
      postMessage({ type: "result", job: m.job, result: { status: "erreur", message: `Erreur : ${msg}`, warnings: [], diagnostics: [] } });
    } else {
      postMessage({ type: "reply", id: m.id, error: msg });
    }
  }
};
