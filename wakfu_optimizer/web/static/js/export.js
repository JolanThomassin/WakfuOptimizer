"use strict";
// Exports du build : image PNG (et texte / JSON fournis par le serveur).

// ===================================================================== exports
const SITE_URL = "https://jolanthomassin.github.io/WakfuOptimizer/";
function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
function loadImg(src) {
  return new Promise((res) => {
    const im = new Image();
    im.crossOrigin = "anonymous";   // icônes du miroir wakassets : CORS autorisé, le canvas reste exportable
    const t = setTimeout(() => res(null), 6000);
    im.onload = () => { clearTimeout(t); res(im); };
    im.onerror = () => { clearTimeout(t); res(null); };
    im.src = src;
  });
}

// Image du build (PNG) : en-tête, stats, maîtrises / résistances, items, sublimations, aptitudes, lien du site.
async function exportPng(v) {
  toast("Création de l'image…");
  const W = 1200, P = 36, COLS = 3, CW = (W - 2 * P - (COLS - 1) * 14) / COLS, CH = 104;
  const s = v.stats;
  const aptLines = (S.meta.aptitudes || []).map((b) => {
    const pts = b.lines.filter((l) => (v.build.characteristics || {})[l.key]).map((l) => `${l.label} ${v.build.characteristics[l.key]}`);
    return pts.length ? [b.name, pts.join(" · ")] : null;
  }).filter(Boolean);
  const itemRows = Math.ceil(v.items.length / COLS);
  const H = 300 + 196 + itemRows * (CH + 14) + 70 + aptLines.length * 24 + 110;

  // images : classe, icônes de stats, items, châsses
  const srcs = new Set([`assets/classes/${v.class.key}.png`, ...v.items.map((it) => iconUrl(it.gfx))]);
  ["health_points", "action_points", "movement_points", "wakfu_points", "range", "critical_hit", "block", "damage_inflicted",
   "lock", "dodge", "melee_mastery", "distance_mastery", "critical_mastery", "rear_mastery", "berserk_mastery", "healing_mastery"].forEach((n) => srcs.add(`assets/stats/${n}.png`));
  ELEMENTS.forEach((e) => { srcs.add(`assets/stats/${e}_mastery.png`); srcs.add(`assets/stats/${e}_res.png`); srcs.add(`assets/stats/${e}_coin.png`); });
  Object.values(SHARD_FILE).forEach((c) => { srcs.add(`assets/shards/shard${c}Full.png`); srcs.add(`assets/shards/shard${c}Empty.png`); });
  v.items.forEach((it) => (it.shards || []).forEach((sh) => sh.rune && srcs.add(statIconSrc(sh.stat))));
  const imgs = {};
  await Promise.all([...srcs].map(async (src) => { imgs[src] = await loadImg(src); }));

  const scale = 2;
  const cv = document.createElement("canvas");
  cv.width = W * scale; cv.height = H * scale;
  const c = cv.getContext("2d");
  c.scale(scale, scale);
  const font = (size, weight = 400) => `${weight} ${size}px "Segoe UI", system-ui, sans-serif`;
  const rr = (x, y, w, h, r) => { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); };
  const box = (x, y, w, h, fill = "#232130", stroke = "#3a3650", r = 12) => { rr(x, y, w, h, r); c.fillStyle = fill; c.fill(); c.strokeStyle = stroke; c.lineWidth = 1; c.stroke(); };
  const text = (t, x, y, size, color = "#ece9f4", weight = 400, align = "left", maxW = 0) => {
    t = tr(String(t));
    c.font = font(size, weight); c.fillStyle = color; c.textAlign = align; c.textBaseline = "middle";
    let str = String(t);
    if (maxW) while (str.length > 1 && c.measureText(str).width > maxW) str = str.slice(0, -2) + "…";
    c.fillText(str, x, y);
    return c.measureText(str).width;
  };
  const img = (src, x, y, w, h = w) => { const im = imgs[src]; if (im) c.drawImage(im, x, y, w, h); };
  const nf = (n) => Number(n).toLocaleString("fr-FR");

  // fond
  const bg = c.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, "#1b1a25"); bg.addColorStop(1, "#13121a");
  c.fillStyle = bg; c.fillRect(0, 0, W, H);
  c.fillStyle = "#e8a93a"; c.fillRect(0, 0, W, 5);

  // en-tête
  box(P, P, 96, 96, "#2d2a3e", "#e8a93a", 18);
  img(`assets/classes/${v.class.key}.png`, P + 8, P + 8, 80);
  text(v.class.name, P + 116, P + 34, 34, "#e8a93a", 800);
  const lw = text(`Niveau ${v.level} ·`, P + 116, P + 72, 18, "#a29eb8");
  v.elements.forEach((e, i) => img(`assets/stats/${e}_coin.png`, P + 124 + lw + i * 28, P + 60, 24));
  [["Score", v.score.toFixed(1)], ["Dégâts", `×${v.damage.toFixed(2)}`], ["PV effectifs", nf(v.ehp)]].forEach(([lab, val], i) => {
    const x = W - P - (3 - i) * 160 + 10;
    box(x, P + 8, 150, 80, "#232130");
    text(lab, x + 75, P + 30, 13, "#a29eb8", 600, "center");
    text(val.replace(".", ","), x + 75, P + 62, 24, "#ece9f4", 800, "center");
  });

  // stats principales
  const main = [["health_points", nf(v.hp), "PV", "#ff7d8a"], ["action_points", s.ap, "PA", "#5cc8ff"], ["movement_points", s.mp, "PM", "#a5d94b"],
    ["wakfu_points", s.wp, "PW", "#3fd9c8"], ["range", s.range || 0, "PO", "#ece9f4"], ["critical_hit", `${s.crit_rate || 0} %`, "Critique", "#ffcf6e"],
    ["block", `${s.block || 0} %`, "Parade", "#ece9f4"], ["damage_inflicted", `${s.dmg_pct || 0} %`, "Dommages", "#7ddc7d"],
    ["lock", nf(s.lock || 0), "Tacle", "#e8a93a"], ["dodge", nf(s.dodge || 0), "Esquive", "#ece9f4"]];
  const mw = (W - 2 * P - (main.length - 1) * 10) / main.length;
  main.forEach(([ic, val, lab, col], i) => {
    const x = P + i * (mw + 10), y = 160;
    box(x, y, mw, 74);
    img(`assets/stats/${ic}.png`, x + 12, y + 14, 22);
    text(lab, x + 40, y + 25, 12, "#a29eb8", 600);
    text(val, x + 12, y + 54, 20, col, 800, "left", mw - 20);
  });

  // maîtrises / résistances
  const half = (W - 2 * P - 14) / 2, py = 254;
  box(P, py, half, 180); box(P + half + 14, py, half, 180);
  text("Maîtrises", P + 16, py + 22, 15, "#e8a93a", 800);
  text("Résistances", P + half + 30, py + 22, 15, "#e8a93a", 800);
  ELEMENTS.forEach((e, i) => {
    const y = py + 52 + i * 30;
    img(`assets/stats/${e}_mastery.png`, P + 16, y - 11, 22);
    text(EL_FR[e], P + 46, y, 15);
    text(nf(v.mastery[e]), P + half / 2 - 10, y, 16, "#ece9f4", 700, "right");
    img(`assets/stats/${e}_res.png`, P + half + 30, y - 11, 22);
    text(EL_FR[e], P + half + 60, y, 15);
    text(`${v.res_pct[e]} %`, P + 2 * half - 70, y, 16, "#ece9f4", 700, "right");
    text(`(${v.res_flat[e]})`, P + 2 * half, y, 13, "#a29eb8", 400, "right");
  });
  const secs = [["melee_mastery", "Mêlée"], ["distance_mastery", "Distance"], ["crit_mastery", "Critique", "critical_mastery"], ["rear_mastery", "Dos"],
    ["berserk_mastery", "Berserk"], ["heal_mastery", "Soin", "healing_mastery"]].filter(([k]) => s[k]);
  secs.slice(0, 4).forEach(([k, lab, ic], i) => {
    const y = py + 52 + i * 30, x = P + half / 2 + 20;
    img(`assets/stats/${ic || k}.png`, x, y - 11, 22);
    text(lab, x + 30, y, 15);
    text(nf(s[k]), P + half - 16, y, 16, s[k] < 0 ? "#ff7070" : "#ece9f4", 700, "right");
  });

  // items
  let y0 = py + 200;
  text("Équipement", P, y0 + 8, 18, "#e8a93a", 800);
  y0 += 26;
  v.items.forEach((it, i) => {
    const x = P + (i % COLS) * (CW + 14), y = y0 + Math.floor(i / COLS) * (CH + 14);
    box(x, y, CW, CH, S.forced.has(it.id) ? "#1e2a36" : "#232130", S.forced.has(it.id) ? "#5cc8ff" : "#3a3650");
    rr(x + 12, y + 12, 60, 60, 10); c.fillStyle = "#2d2a3e"; c.fill();
    img(iconUrl(it.gfx), x + 14, y + 14, 56);
    text(it.name, x + 84, y + 24, 16, it.color, 800, "left", CW - 96);
    text(`${it.slot_name} · niv. ${it.level}`, x + 84, y + 46, 13, "#a29eb8", 400, "left", CW - 96);
    const sub = [it.sub && it.sub.name, it.special && `★ ${it.special.name}`].filter(Boolean).join("   ");
    if (sub) text(sub, x + 84, y + 68, 13, "#e8a93a", 700, "left", CW - 96);
    // châsses : couleur, icône de la stat de la rune par-dessus, valeur à côté
    let rx = x + 84;
    for (const sh of it.shards || []) {
      img(`assets/shards/shard${SHARD_FILE[sh.color]}${sh.rune ? "Full" : "Empty"}.png`, rx, y + 79, 20);
      if (!sh.rune) { rx += 26; continue; }
      rr(rx + 3, y + 82, 14, 14, 3); c.fillStyle = "rgba(10, 8, 18, .72)"; c.fill();
      img(statIconSrc(sh.stat), rx + 4, y + 83, 12);
      rx += 26 + text(`+${sh.value}`, rx + 23, y + 89, 12, "#ece9f4", 600) + 6;
    }
  });
  y0 += itemRows * (CH + 14) + 6;

  // sublimations actives
  text("Sublimations", P, y0 + 10, 18, "#e8a93a", 800);
  let sx = P, sy = y0 + 40;
  for (const a of v.active) {
    const label = `${a.name} ${a.level}${a.limit ? `/${a.limit}` : ""}`;
    c.font = font(13, 600);
    const w = c.measureText(label).width + 22;
    if (sx + w > W - P) { sx = P; sy += 30; }
    rr(sx, sy - 12, w, 24, 12); c.fillStyle = "#2d2a3e"; c.fill();
    text(label, sx + 11, sy, 13, "#ece9f4", 600);
    sx += w + 8;
  }

  // aptitudes
  let ay = sy + 40;
  text("Aptitudes", P, ay, 18, "#e8a93a", 800);
  ay += 28;
  for (const [branch, line] of aptLines) {
    text(branch, P, ay, 14, "#a29eb8", 700);
    text(line, P + 120, ay, 14, "#ece9f4", 400, "left", W - 2 * P - 120);
    ay += 24;
  }

  // pied : lien du site
  const fy = Math.max(ay + 20, H - 70);
  c.fillStyle = "#3a3650"; c.fillRect(P, fy, W - 2 * P, 1);
  text("Wakfu Optimizer", P, fy + 32, 18, "#e8a93a", 800);
  text(SITE_URL, P + 168, fy + 32, 16, "#5cc8ff", 600);
  text(`${new Date().toLocaleDateString("fr-FR")} · ${$("#version").textContent}`, W - P, fy + 32, 13, "#a29eb8", 400, "right");

  const out = document.createElement("canvas");   // recadrage à la hauteur réellement utilisée
  const used = Math.min(H, fy + 64);
  out.width = W * scale; out.height = used * scale;
  out.getContext("2d").drawImage(cv, 0, 0);
  out.toBlob(async (blob) => {
    if (!blob) { toast("Impossible de créer l'image."); return; }
    download(blob, `build_${v.class.key}_${v.level}.png`);
    let copied = false;
    try { await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]); copied = true; } catch (e) { /* presse-papier refusé */ }
    toast(copied ? "Image téléchargée et copiée : collez-la directement (Ctrl+V)." : "Image téléchargée.");
    sfx("apply");
  }, "image/png");
}
