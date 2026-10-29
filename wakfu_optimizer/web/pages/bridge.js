"use strict";
// Version GitHub Pages : remplace le serveur Python local par un Web Worker (static/worker.js).
// app.js appelle WAKFU_BROWSER.api(path, body) à la place de fetch().
(() => {
  const SETTINGS_KEY = "wakfu-optimizer:settings";
  let worker = null, ready = false, status = "Démarrage…", error = "", seq = 0, job = null;
  const pending = new Map();

  function loadSettings() {
    try { return localStorage.getItem(SETTINGS_KEY) || "{}"; } catch (e) { return "{}"; }
  }
  function saveSettings(opts) {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(opts)); } catch (e) { /* navigation privée */ }
  }

  function start() {
    ready = false;
    worker = new Worker("static/worker.js");
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.type === "status") status = m.msg;
      else if (m.type === "ready") ready = true;
      else if (m.type === "error") error = m.msg;
      else if (m.type === "progress" && job && job.id === m.job) {
        job.msg = m.msg;
        job.progress = Math.max(job.progress, m.frac);
      } else if (m.type === "result" && job && job.id === m.job) {
        Object.assign(job, { done: true, progress: 1, result: m.result });
      } else if (m.type === "reply") {
        const p = pending.get(m.id);
        pending.delete(m.id);
        if (!p) return;
        if (m.error) { p.reject(new Error(m.error)); return; }
        const out = JSON.parse(m.json);
        if (out && !Array.isArray(out) && out.error) p.reject(new Error(out.error));
        else p.resolve(out);
      }
    };
    worker.onerror = (e) => { error = `Erreur du moteur : ${e.message || e}`; };
  }

  function call(method, path, body) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      worker.postMessage({ type: "request", id, method, path, body: JSON.stringify(body ?? {}), settings: loadSettings() });
    });
  }

  function cancel() {
    if (!job || job.done) return;
    // HiGHS ne peut pas être interrompu : on arrête le Worker et on en relance un.
    worker.terminate();
    for (const p of pending.values()) p.reject(new Error("Calcul annulé"));
    pending.clear();
    Object.assign(job, { done: true, progress: 1,
      result: { status: "annulé", message: "Calcul annulé.", warnings: [], diagnostics: [] } });
    start();
  }

  async function api(path, body) {
    const method = body === undefined ? "GET" : "POST";
    const p = path.split("?")[0];
    if (p === "/api/meta" && !ready) return error ? { error } : { loading: true, msg: status };
    if (p === "/api/job") {
      if (!job) throw new Error("tâche inconnue");
      return { progress: job.progress, msg: job.done ? job.msg : (ready ? job.msg : status), done: job.done,
               elapsed: Math.round((performance.now() - job.t0) / 100) / 10, result: job.result };
    }
    if (p === "/api/optimize") {
      saveSettings(body.opts || {});
      job = { id: `j${++seq}`, progress: 0, msg: "Démarrage…", done: false, result: null, t0: performance.now() };
      worker.postMessage({ type: "optimize", job: job.id, opts: JSON.stringify(body.opts || {}) });
      return { job: job.id };
    }
    if (p === "/api/cancel") { cancel(); return { ok: true }; }
    if (p === "/api/reload") return { ok: true };
    return call(method, path, body);
  }

  start();
  window.WAKFU_BROWSER = { api };
})();
