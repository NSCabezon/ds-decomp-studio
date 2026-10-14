"use strict";
const $ = (s, e = document) => e.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const fmt = n => Number(n || 0).toLocaleString("fr-FR");
const hex = n => "0x" + Number(n).toString(16).padStart(8, "0");
const ago = t => { if (!t) return ""; const s = Date.now() / 1000 - t; return s < 90 ? "a l'instant" : s < 5400 ? Math.round(s / 60) + " min" : s < 172800 ? Math.round(s / 3600) + " h" : Math.round(s / 86400) + " j"; };
const TABS = [["games", "Jeux"], ["game", "Travailler"], ["queue", "Queue"], ["engine", "Engine map"], ["progress", "Progression"], ["settings", "Reglages"]];
const ST = {free: "libre", claimed: "pris", expired: "expire", done: "termine", queued: "en attente", running: "en cours",
  failed: "echec", stopped: "arrete", interrupted: "interrompu", cancelled: "annule"};
let O = null, G = null, J = [], tab = location.hash.slice(1) || "games", sub = "blocks";
let fLevel = null, fState = "open", fnLevel = "", fnQuery = "", fnState = "todo", openLog = null;

async function api(path, body) {
  try {
    const r = await fetch("/api/" + path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const d = await r.json();
    if (d && d.error) toast(d.error, true);
    if (d && d.warning) toast(d.warning, true);
    return d;
  } catch (e) { toast("Serveur injoignable : " + e, true); return {error: String(e)}; }
}
function toast(msg, err) {
  const t = document.createElement("div"); t.className = "toast" + (err ? " err" : ""); t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), err ? 9000 : 4500);
}
function modal(html) { $("#modalbody").innerHTML = html; $("#modal").classList.add("on"); }
$("#modal").onclick = e => { if (e.target.id === "modal") $("#modal").classList.remove("on"); };
const closeModal = () => $("#modal").classList.remove("on");
const LV = n => O.levels[n] || {label: "?"};
const game = () => O && O.settings.active_game;
const pctBar = p => `<div class="pct"><div class="bar"><i style="width:${Math.min(p, 100)}%"></i></div><b>${p.toFixed(2)}%</b></div>`;

function tabs() {
  $("#tabs").innerHTML = TABS.map(([k, l]) => `<button class="${k === tab ? "on" : ""}" onclick="go('${k}')">${l}</button>`).join("");
}
function go(t) { tab = t; location.hash = t; tabs(); render(); }

async function loadOverview() { O = await api("overview"); }
async function loadXP() {
  const x = await api("xp"); if (!x || x.error) return;
  $("#lvl").textContent = x.level; $("#rank").textContent = x.rank;
  $("#xptxt").textContent = `${fmt(x.xp_in_level)} / ${fmt(x.xp_needed)} XP`;
  $("#xpbar").style.width = (100 * x.xp_in_level / x.xp_needed) + "%";
  window.XP = x;
}
async function selectGame(id) {
  await api("settings", {active_game: id}); O.settings.active_game = id; G = null; fLevel = null; go("game");
}

async function render() {
  if (!O) return;
  const v = $("#view");
  try {
    if (tab === "games") v.innerHTML = viewGames();
    else if (tab === "game") { v.innerHTML = await viewGame(); afterGame(); }
    else if (tab === "queue") v.innerHTML = await viewQueue();
    else if (tab === "engine") v.innerHTML = await viewEngine();
    else if (tab === "progress") v.innerHTML = viewProgress();
    else if (tab === "settings") v.innerHTML = viewSettings();
  } catch (e) { v.innerHTML = `<div class="card">Erreur d'affichage : ${esc(e)}</div>`; console.error(e); }
}

// ---------------- Jeux ----------------
function viewGames() {
  const gs = O.games, tot = gs.reduce((a, g) => a + g.functions, 0), got = gs.reduce((a, g) => a + g.matched, 0);
  const live = O.queue.filter(c => !c.expired).length;
  let h = `<div class="kpis"><div class="kpi"><b>${gs.length}</b><span>jeux</span></div>
    <div class="kpi"><b>${fmt(got)}</b><span>fonctions matchees / ${fmt(tot)}</span></div>
    <div class="kpi"><b>${gs.filter(g => g.remote).length}</b><span>sur GitHub</span></div>
    <div class="kpi"><b>${live}</b><span>blocs en cours</span></div></div>`;
  const behind = gs.filter(g => g.tools_behind && g.tools_behind.length).length;
  h += `<div class="card"><h3>Mes jeux</h3><p class="hint">Clique sur un jeu pour travailler dessus. "Retirer" le range dans projets/_archive (rien n'est supprime).</p>
  ${behind ? `<div class="btns" style="margin-bottom:8px"><span class="tag ko">${behind} jeux ont des outils en retard sur rayman-rr (auto_match...)</span>
    <button class="btn small" onclick="api('run',{id:'sync_all'}).then(r=>r.n&&toast('Mise a jour des outils lancee (onglet Queue)'))">Tout mettre a jour</button></div>` : ""}
  <table><tr><th>Jeu</th><th>Studio</th><th>Etat ROM</th><th class="num">Fonctions</th><th>Code matche</th><th>GitHub</th><th></th></tr>`;
  for (const g of [...gs].sort((a, b) => b.pct_code - a.pct_code || a.title.localeCompare(b.title))) {
    h += `<tr class="click" onclick="selectGame('${g.id}')"><td><b>${esc(g.title)}</b> ${g.id === game() ? '<span class="tag ok">actif</span>' : ""}<div class="hint">${esc(g.id)} &middot; ${esc(g.code)} ${esc(g.version || "")}</div></td>
      <td class="hint">${esc(g.studio)}</td>
      <td>${g.rom.ok ? '<span class="tag ok">ROM OK</span>' : `<span class="tag ko" title="${esc(g.rom.note)}">${esc(g.rom.note || "KO")}</span>`}</td>
      <td class="num">${fmt(g.matched)} / ${fmt(g.functions)}</td><td>${pctBar(g.pct_code)}</td>
      <td>${g.remote ? `<a class="tag gh" href="${esc(g.remote.replace(/\.git$/, ""))}" target="_blank" onclick="event.stopPropagation()">GitHub</a>` : '<span class="hint">local</span>'}</td>
      <td onclick="event.stopPropagation()"><button class="btn small sec" onclick="archiveGame('${g.id}')">Retirer</button></td></tr>`;
  }
  h += `</table></div><div class="split"><div class="card"><h3>Ajouter un jeu (depuis une ROM)</h3>
    <p class="hint">Mets la ROM (.nds, dumpee de ta cartouche) dans <code>decomp ds/roms/</code>, puis clique sur Charger.</p>
    <button class="btn sec" onclick="loadRoms()">Charger les ROMs sans projet</button><div id="roms"></div></div>
    <div class="card"><h3>Prendre un jeu publie sur GitHub</h3>
    <p class="hint">Clone le repo d'un jeu (le tien ou celui d'un ami) dans projets/. Il faut ensuite la ROM.</p>
    <div class="btns"><input id="cloneurl" placeholder="https://github.com/proprietaire/jeu-decomp" style="flex:1;min-width:240px"><button class="btn" onclick="cloneGame()">Cloner</button></div>
    <button class="btn sec small" style="margin-top:8px" onclick="loadGithub()">Voir les jeux publies (topic ds-decomp-studio)</button><div id="ghlist"></div>
    ${O.archived.length ? `<h3 style="margin-top:14px">Archives</h3>` + O.archived.map(a => `<div class="btns" style="margin:4px 0"><span>${esc(a)}</span><button class="btn small sec" onclick="restoreGame('${esc(a)}')">Remettre</button></div>`).join("") : ""}
    </div></div>`;
  return h;
}
async function archiveGame(id) {
  if (!confirm(`Retirer ${id} du studio ? Le dossier est deplace dans projets/_archive (recuperable).`)) return;
  const r = await api("archive", {game: id}); if (r.ok) { toast("Jeu archive"); await loadOverview(); render(); }
}
async function restoreGame(n) { const r = await api("restore", {name: n}); if (r.ok) { toast("Jeu remis"); await loadOverview(); render(); } }
async function loadRoms() {
  $("#roms").innerHTML = '<p class="hint">Lecture des ROMs...</p>';
  const r = await api("roms");
  $("#roms").innerHTML = !r.roms || !r.roms.length ? '<p class="hint">Aucune ROM sans projet.</p>' :
    `<table>${r.roms.map(x => `<tr><td>${esc(x.rom)}<div class="hint">${esc(x.code)} &middot; ${x.mb} Mo</div></td><td><input value="${esc(x.slug)}" id="slug-${esc(x.code)}" size="18"></td>
      <td><button class="btn small" onclick="addGame('${esc(x.code)}', ${JSON.stringify(x.rom).replace(/"/g, "&quot;")})">Ajouter</button></td></tr>`).join("")}</table>`;
}
async function addGame(code, rom) {
  const slug = $("#slug-" + code).value.trim();
  const r = await api("run", {id: "new_project", params: {slug, rom}});
  if (r.n) toast(`Creation de ${slug} lancee (onglet Queue pour suivre)`);
}
async function cloneGame() {
  const r = await api("clone", {url: $("#cloneurl").value});
  if (r.ok) { toast(`${r.game} clone. ${r.next}`); await loadOverview(); render(); }
}
async function loadGithub() {
  $("#ghlist").innerHTML = '<p class="hint">Recherche...</p>';
  const r = await api("github");
  $("#ghlist").innerHTML = (r.repos || []).map(x => `<div class="btns" style="margin:4px 0"><a href="${esc(x.url)}" target="_blank">${esc(x.fullName)}</a>
    <button class="btn small sec" onclick="$('#cloneurl').value='${esc(x.url)}'">choisir</button></div>`).join("") || '<p class="hint">Aucun repo trouve.</p>';
}

// ---------------- Travailler (jeu actif) ----------------
async function viewGame() {
  if (!game()) return `<div class="card empty">Choisis d'abord un jeu dans l'onglet <a href="#games" onclick="go('games')">Jeux</a>.</div>`;
  G = await api("game?id=" + encodeURIComponent(game()));
  if (G.error) return `<div class="card">${esc(G.error)}</div>`;
  const g = G.game, opts = O.games.map(x => `<option value="${x.id}" ${x.id === g.id ? "selected" : ""}>${esc(x.title)}</option>`).join("");
  let h = `<div class="card"><div class="btns" style="justify-content:space-between">
    <div><h2 style="margin:0"><select style="font-size:17px;font-weight:700" onchange="selectGame(this.value)">${opts}</select></h2>
    <span class="hint">${esc(g.id)} &middot; ${esc(g.code)} ${esc(g.version)} &middot; ${esc(g.studio)} &middot;
    ${g.rom.ok ? '<span class="tag ok">ROM OK</span>' : `<span class="tag ko">${esc(g.rom.note)}</span>`}
    ${g.remote ? `<a class="tag gh" target="_blank" href="${esc(g.remote.replace(/\.git$/, ""))}">GitHub</a>` : '<span class="tag">local</span>'}</span></div>
    <div style="min-width:260px">${pctBar(g.pct_code)}<div class="hint" style="text-align:right">${fmt(g.matched)} / ${fmt(g.functions)} fonctions</div></div></div>
    <h3 style="margin-top:12px">Taches machine sur ce jeu</h3><div class="btns">
    ${["moulinette", "auto", "verify", "culprits", "build", "dis", "status", "permute"].map(k => `<button class="btn small ${k === "moulinette" ? "" : "sec"}" title="${esc(O.jobdefs[k].desc)}" onclick="runJob('${k}')">${esc(O.jobdefs[k].label)}</button>`).join("")}
    ${g.tools_behind && g.tools_behind.length ? `<button class="btn small" style="background:#b45309" title="${esc(g.tools_behind.join(", "))}" onclick="runJob('sync_tools',{})">Mettre a jour les outils (${g.tools_behind.length} en retard)</button>` : '<span class="tag ok">outils a jour</span>'}
    ${g.remote ? "" : `<button class="btn small green" onclick="publishGame()">Publier sur GitHub</button>`}
    </div></div>`;
  h += `<div class="levels">` + O.levels.map(l => {
    const p = G.per_level[l.n] || {blocks: 0, free: 0, claimed: 0, done: 0, left: 0};
    return `<div class="level L${l.n} ${fLevel === l.n ? "on" : ""}" onclick="setLevel(${l.n})"><b class="c${l.n}">${esc(l.label)}</b>
      <div class="n">${fmt(p.left)}</div><div class="hint">fonctions restantes &middot; ${p.free} blocs libres, ${p.claimed} pris</div>
      <div class="hint">${esc(l.hint)}</div></div>`;
  }).join("") + `</div>`;
  h += `<nav style="margin-bottom:12px">${[["blocks", "Blocs de 50"], ["functions", "Fonctions par difficulte"], ["map", "Carte memoire"]].map(([k, l]) =>
    `<button class="${sub === k ? "on" : ""}" onclick="sub='${k}';render()">${l}</button>`).join("")}</nav><div id="sub"></div>`;
  return h;
}
function afterGame() { if (!G || G.error) return; if (sub === "blocks") subBlocks(); else if (sub === "functions") subFunctions(); else subMap(); }
function setLevel(n) { fLevel = fLevel === n ? null : n; fnLevel = fLevel === null ? "" : String(fLevel); render(); }

function subBlocks() {
  const bl = G.blocks.filter(b => (fLevel === null || b.level === fLevel) &&
    (fState === "all" || (fState === "open" ? b.state !== "done" : fState === "mine" ? b.claim && b.claim.who === O.settings.who : b.state === fState)));
  let h = `<div class="card"><div class="btns" style="margin-bottom:10px">
    <select onchange="fState=this.value;subBlocks()">${[["open", "Non termines"], ["free", "Libres"], ["claimed", "Pris"], ["mine", "Les miens"], ["done", "Termines"], ["all", "Tous"]].map(([k, l]) => `<option value="${k}" ${fState === k ? "selected" : ""}>${l}</option>`).join("")}</select>
    <span class="hint">${bl.length} blocs ${fLevel !== null ? "niveau " + esc(LV(fLevel).label) : ""} &middot; generation ${G.generation}</span>
    <span style="flex:1"></span>
    <button class="btn" onclick="claimNext()">Prendre le prochain bloc ${fLevel !== null ? esc(LV(fLevel).label) : "le plus facile"}</button>
    <button class="btn sec" onclick="qwenDialog(null)">Agents Qwen sur plusieurs blocs</button>
    <button class="btn sec" onclick="rebuildBlocks()" title="Refait les blocs avec les fonctions restantes. Les blocs pris ne bougent pas.">Recalculer les blocs</button></div>
    <div class="blocks">`;
  for (const b of bl) {
    const c = b.claim, mine = c && c.who === O.settings.who;
    h += `<div class="block L${b.level} ${b.state}"><div class="top"><span class="id">${b.id}</span><span class="state ${b.state}">${ST[b.state]}</span></div>
      <div><b class="c${b.level}">${esc(LV(b.level).label)}</b> &middot; ${b.left}/${b.count} restantes &middot; ${fmt(b.left_bytes)} octets</div>
      <div class="bar"><i style="width:${100 * (b.count - b.left) / Math.max(b.count, 1)}%"></i></div>
      <div class="hint">${hex(b.addr[0])} - ${hex(b.addr[1])}</div>
      ${c ? `<div class="hint">${esc(c.who)} (${esc(O.kinds[c.kind] || c.kind)}) &middot; ${ago(c.touched)}${c.note ? " &middot; " + esc(c.note) : ""}</div>` : ""}
      <div class="btns">
        <button class="btn small sec" onclick="openBlock('${b.id}')">Voir / brief</button>
        ${b.state === "free" || b.state === "expired" ? `<button class="btn small" onclick="claimBlock('${b.id}','human')">Prendre</button>
          <button class="btn small sec" onclick="qwenBlock('${b.id}')" title="Qwen (Ollama local) travaille sur ce bloc">Qwen</button>` : ""}
        ${mine || (c && c.kind !== "human") ? `<button class="btn small green" onclick="releaseBlock('${b.id}',true)">Termine</button>
          <button class="btn small sec" onclick="releaseBlock('${b.id}',false)">Rendre</button>` : ""}
      </div></div>`;
  }
  $("#sub").innerHTML = h + `</div>${bl.length ? "" : '<div class="empty">Aucun bloc ici.</div>'}</div>`;
}
async function claimNext() {
  const r = await api("claim", {game: game(), block: "next", level: fLevel, kind: "human"});
  if (r.ok) { toast(`Bloc ${r.block} pris`); render(); openBlock(r.block); }
}
async function claimBlock(id, kind) { const r = await api("claim", {game: game(), block: id, kind}); if (r.ok) { toast(`Bloc ${id} pris`); render(); } }
async function releaseBlock(id, fin) {
  if (fin && !confirm(`Marquer ${id} comme termine ? (les fonctions non matchees retourneront dans un futur bloc au prochain recalcul)`)) return;
  const r = await api("release", {game: game(), block: id, finished: fin}); if (r.ok) { toast(fin ? "Bloc termine, bravo !" : "Bloc rendu a la queue"); render(); }
}
async function rebuildBlocks() {
  if (!confirm("Recalculer les blocs libres avec les fonctions restantes ?")) return;
  const r = await api("rebuild", {game: game()}); if (r.ok) { toast(`${r.blocks} blocs`); render(); }
}
function qwenBlock(id) { qwenDialog([id]); }
function qwenDialog(ids) {
  window.QWEN_IDS = ids;
  const s = O.settings, free = G.blocks.filter(b => (b.state === "free" || b.state === "expired") && (fLevel === null || b.level === fLevel)).length;
  modal(`<h2>Agents Qwen ${ids ? "sur " + esc(ids.join(", ")) : "sur plusieurs blocs"}</h2>
    <p class="hint">Chaque agent travaille sur une fonction a la fois. Les matches sont verifies par lots (verify complet) puis commites.
    Pour que les agents tournent vraiment en meme temps, Ollama doit etre lance avec <code>OLLAMA_NUM_PARALLEL</code> au moins egal au nombre d'agents (voir Reglages).</p>
    <table>${ids ? "" : `<tr><td>Niveau</td><td><select data-k="level"><option value="">le plus facile d'abord</option>${O.levels.map(l => `<option value="${l.n}" ${fLevel === l.n ? "selected" : ""}>${esc(l.label)}</option>`).join("")}</select></td></tr>
      ${optField(["count", `Nombre de blocs a donner a Qwen (${free} libres ici)`, "number", Math.min(4, Math.max(free, 1))])}`}
      ${optField(["agents", "Agents en parallele", "number", s.qwen_agents])}
      ${optField(["minutes", "Minutes max par fonction", "number", s.qwen_minutes])}
      ${optField(["max", "Nombre max de fonctions (0 = toutes)", "number", 0])}
      ${optField(["batch", "Matches verifies ensemble", "number", 10])}
      <tr><td>Modele</td><td><input data-k="model" value="${esc(s.qwen_model)}"></td></tr></table>
    <div class="btns" style="margin-top:12px"><button class="btn" onclick="launchQwen()">Lancer les agents</button>
    <button class="btn sec" onclick="closeModal()">Annuler</button></div>`);
}
async function launchQwen() {
  const o = readFields(); closeModal();
  if (o.level === "" || o.level === undefined) o.level = null; else o.level = +o.level;
  const r = await api("qwen_swarm", {game: game(), blocks: window.QWEN_IDS, ...o});
  if (r.n) toast(`Qwen : ${o.agents} agent(s) sur ${r.blocks.join(", ")} (onglet Queue)`);
  render();
}
async function openBlock(id) {
  modal('<p class="hint">Chargement...</p>');
  const d = await api(`block?game=${encodeURIComponent(game())}&id=${encodeURIComponent(id)}`);
  if (d.error) return closeModal();
  window.BRIEF = d.brief;
  modal(`<div class="btns" style="justify-content:space-between"><h2 style="margin:0">Bloc ${esc(id)}</h2>
    <div class="btns"><button class="btn small" onclick="navigator.clipboard.writeText(BRIEF);toast('Brief copie : colle-le a Claude ou a une autre IA')">Copier le brief pour une IA</button>
    <button class="btn small sec" onclick="closeModal()">Fermer</button></div></div>
    <table style="margin-top:10px"><tr><th>Fonction</th><th>Adresse</th><th class="num">Taille</th><th>Niveau</th><th>auto_match</th><th>Note</th></tr>
    ${d.functions.map(f => `<tr class="click" onclick="showAsm('${esc(f.name)}')"><td>${f.done ? "&#10004; " : ""}<b>${esc(f.name)}</b></td><td class="hint">${hex(f.addr)}</td>
      <td class="num">${f.size}</td><td>${f.done ? '<span class="hint">matchee</span>' : `<span class="c${f.level}">${esc(LV(f.level).label)}</span>`}</td>
      <td class="hint">${esc(f.auto || "")}</td><td class="hint">${f.port ? "copier depuis " + esc(f.port.game) + " " + esc(f.port.file) : f.shared >= 2 ? "SDK (" + f.shared + " jeux)" : ""}</td></tr>`).join("")}</table>
    <div id="asm"></div><h3 style="margin-top:14px">Brief (pour une personne ou une IA)</h3><pre>${esc(d.brief)}</pre>`);
}
async function showAsm(name) {
  const d = await api(`asm?game=${encodeURIComponent(game())}&name=${encodeURIComponent(name)}`);
  $("#asm").innerHTML = `<h3 style="margin-top:12px">${esc(name)}</h3><pre>${esc(d.asm)}</pre>`;
  $("#asm").scrollIntoView({behavior: "smooth"});
}

async function subFunctions() {
  const q = `functions?game=${encodeURIComponent(game())}&level=${fnLevel}&q=${encodeURIComponent(fnQuery)}&state=${fnState}&limit=400`;
  $("#sub").innerHTML = `<div class="card"><div class="btns" style="margin-bottom:10px">
    <select onchange="fnState=this.value;subFunctions()"><option value="todo" ${fnState === "todo" ? "selected" : ""}>A faire (triees par difficulte)</option><option value="done" ${fnState === "done" ? "selected" : ""}>Deja matchees</option></select>
    <select onchange="fnLevel=this.value;fLevel=this.value===''?null:+this.value;subFunctions()"><option value="">Tous niveaux</option>${O.levels.map(l => `<option value="${l.n}" ${fnLevel === String(l.n) ? "selected" : ""}>${esc(l.label)}</option>`).join("")}</select>
    <input placeholder="nom..." value="${esc(fnQuery)}" onchange="fnQuery=this.value;subFunctions()"><span class="hint" id="fncount"></span></div><div id="fntable" class="hint">Chargement...</div><div id="asm"></div></div>`;
  const d = await api(q);
  if (d.error) return;
  $("#fncount").textContent = `${fmt(d.total)} fonctions${d.total > d.rows.length ? " (400 premieres)" : ""}`;
  $("#fntable").innerHTML = `<table><tr><th>Fonction</th><th>Adresse</th><th class="num">Taille</th><th>Mode</th><th>Niveau</th><th>auto_match</th><th>Bloc</th><th>Note</th></tr>
    ${d.rows.map(f => `<tr class="click" onclick="showAsm('${esc(f.name)}')"><td><b>${esc(f.name)}</b></td><td class="hint">${hex(f.addr)}</td><td class="num">${f.size}</td>
    <td class="hint">${f.mode}</td><td>${f.done ? (esc(f.file || "")) : `<span class="c${f.level}">${esc(LV(f.level).label)}</span>`}</td><td class="hint">${esc(f.auto || "")}</td>
    <td class="hint">${esc(f.block || "")}</td><td class="hint">${f.port ? "copier depuis " + esc(f.port.game) : f.shared >= 2 ? "SDK (" + f.shared + ")" : ""}</td></tr>`).join("")}</table>`;
}

async function subMap() {
  $("#sub").innerHTML = `<div class="card"><h3>Carte memoire du module ARM9</h3><p class="hint">Chaque trait = une fonction, a sa place dans la memoire. Gris = matchee, couleur = difficulte. Survole pour le nom, clique pour l'assembleur.</p>
    <canvas id="map" height="260"></canvas><div class="legend"><span><i style="background:var(--done)"></i>matchee</span>${O.levels.map(l => `<span><i style="background:var(--l${l.n})"></i>${esc(l.label)}</span>`).join("")}</div>
    <div class="hint" id="maptip">&nbsp;</div><div id="asm"></div></div>`;
  const d = await api("map?game=" + encodeURIComponent(game()));
  if (d.error) return;
  const cv = $("#map"), ctx = cv.getContext("2d"), W = cv.clientWidth, rows = 8, H = 260;
  cv.width = W * devicePixelRatio; cv.height = H * devicePixelRatio; ctx.scale(devicePixelRatio, devicePixelRatio);
  const css = getComputedStyle(document.documentElement), col = l => css.getPropertyValue(l < 0 ? "--done" : "--l" + l).trim();
  const span = Math.max(d.end - d.start, 1), per = span / rows, rh = H / rows;
  const pos = a => { const o = a - d.start, r = Math.min(Math.floor(o / per), rows - 1); return [((o - r * per) / per) * W, r * rh]; };
  for (const [a, s, l] of d.functions) {
    const [x, y] = pos(a); ctx.fillStyle = col(l); ctx.fillRect(x, y + 2, Math.max(W * s / per, 1.2), rh - 4);
  }
  cv.onmousemove = e => {
    const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, row = Math.floor(y / rh);
    const a = d.start + row * per + (x / W) * per, f = d.functions.find(f => f[0] <= a && a < f[0] + Math.max(f[1], per / W * 2));
    $("#maptip").textContent = f ? `${hex(f[0])} - ${f[1]} octets - ${f[2] < 0 ? "matchee" : LV(f[2]).label}` : hex(a);
    cv._f = f;
  };
  cv.onclick = async () => { if (cv._f) { const fs = await api(`functions?game=${encodeURIComponent(game())}&state=todo&limit=100000`); const m = (fs.rows || []).find(r => r.addr === cv._f[0]); if (m) showAsm(m.name); } };
}

const JOB_OPTS = {
  auto: [["jobs", "Coeurs utilises (-j)", "number", 16], ["permute", "Permuter sur N near misses (0 = non)", "number", 0],
    ["minutes", "Minutes de permuter par fonction", "number", 2], ["fresh", "Tout refaire (ignorer le cache des echecs)", "check", false],
    ["dry_run", "Essai a blanc (ne change rien)", "check", false],
    ["cached_only", "Seulement integrer les matches deja trouves (reprise rapide)", "check", false], ["force", "Relancer meme si l'auto-match est marque termine", "check", false]],
  permute: [["permute", "Nombre de near misses", "number", 10], ["minutes", "Minutes par fonction", "number", 2], ["jobs", "Coeurs (-j)", "number", 16],
    ["force", "Relancer meme si marque termine", "check", false]],
  culprits: [["fix", "Retirer les fichiers fautifs (non commites) et reconstruire", "check", true],
    ["any", "Autoriser aussi les fichiers deja commites (prudence)", "check", false]],
  moulinette: [["push", "Pousser sur GitHub si la verification passe", "check", true], ["permute_near", "Permuter sur N near misses (0 = non)", "number", 0],
    ["near_minutes", "Minutes de permuter par near miss", "number", 5], ["restart", "Oublier les echecs deja essayes", "select", ["", "all", "auto", "permuter", "qwen"]],
    ["no_drafts", "Sans brouillons m2c", "check", false], ["no_auto", "Sans auto-match", "check", false], ["no_commit", "Verifier seulement (pas de commit)", "check", false]],
};
function optField([k, label, type, def]) {
  if (type === "check") return `<tr><td>${esc(label)}</td><td><input type="checkbox" data-k="${k}" ${def ? "checked" : ""}></td></tr>`;
  if (type === "select") return `<tr><td>${esc(label)}</td><td><select data-k="${k}">${def.map(v => `<option value="${v}">${v || "non"}</option>`).join("")}</select></td></tr>`;
  return `<tr><td>${esc(label)}</td><td><input type="number" data-k="${k}" value="${def}" style="width:90px"></td></tr>`;
}
function readFields() {
  const o = {};
  document.querySelectorAll("#modalbody [data-k]").forEach(e => { o[e.dataset.k] = e.type === "checkbox" ? e.checked : e.type === "number" ? +e.value : e.value; });
  return o;
}
async function runJob(id, params) {
  if (JOB_OPTS[id] && !params) {
    const opts = JOB_OPTS[id].map(o => o[0] === "push" ? [o[0], o[1], o[2], !!G.game.remote] : o);
    modal(`<h2>${esc(O.jobdefs[id].label)}</h2><p class="hint">${esc(O.jobdefs[id].desc)}</p><table>${opts.map(optField).join("")}</table>
      <div class="btns" style="margin-top:12px"><button class="btn" onclick="closeModal();runJob('${id}',readFields())">Lancer</button>
      <button class="btn sec" onclick="closeModal()">Annuler</button></div>`);
    return;
  }
  params = params || {};
  let r = await api("run", {id, game: game(), params});
  if (r.error && r.error.includes("forcer") && confirm("Auto-match deja termine sur ce jeu. Relancer quand meme ?")) r = await api("run", {id, game: game(), params: {...params, force: true}});
  if (r.n) toast(`Tache #${r.n} ajoutee a la queue`);
}
async function publishGame() {
  if (!confirm(`Publier ${G.game.title} sur GitHub en PUBLIC ?\nLa ROM et les fichiers du jeu ne sont jamais envoyes (verifie avant l'envoi).`)) return;
  const r = await api("run", {id: "publish", game: game()}); if (r.n) toast("Publication lancee (onglet Queue)");
}

// ---------------- Queue ----------------
async function viewQueue() {
  await loadOverview();
  const d = await api("jobs"); J = d.jobs || [];
  let h = `<div class="split"><div class="card"><h3>Qui travaille sur quoi (tous les jeux)</h3>
    <p class="hint">Les blocs pris par des personnes ou des IA. Un bloc non touche depuis 48 h retourne dans la queue.</p>`;
  h += O.queue.length ? `<table><tr><th>Jeu</th><th>Bloc</th><th>Qui</th><th>Depuis</th><th></th></tr>${O.queue.map(c => `<tr><td>${esc(c.title)}</td><td><b>${esc(c.block)}</b></td>
    <td>${esc(c.who)}<div class="hint">${esc(O.kinds[c.kind] || c.kind)}${c.note ? " &middot; " + esc(c.note) : ""}</div></td><td class="hint">${ago(c.touched)} ${c.expired ? '<span class="state expired">expire</span>' : ""}</td>
    <td><button class="btn small sec" onclick="selectGame('${c.game}')">Ouvrir</button></td></tr>`).join("")}</table>` : '<div class="empty">Personne ne travaille sur un bloc pour l\'instant.</div>';
  h += `</div><div class="card"><h3>Comment rejoindre (personnes et IA)</h3>
    <p>Une personne ou une IA prend un bloc, travaille, puis le marque termine. Les prises sont enregistrees dans le repo GitHub du jeu (<code>.studio/claims/</code>), donc tout le monde voit la meme queue.</p>
    <pre>python studio/studio.py blocks &lt;jeu&gt; --free
python studio/studio.py claim &lt;jeu&gt; next --who NOM --kind claude
python studio/studio.py brief &lt;jeu&gt; &lt;bloc&gt;     (fiche de travail)
python studio/studio.py done &lt;jeu&gt; &lt;bloc&gt;</pre>
    <p class="hint">Les taches machine (a droite / en bas) passent une par une par jeu, et au maximum ${O.settings.max_parallel_jobs} en meme temps (Reglages).</p></div></div>`;
  h += `<div class="card"><h3>Taches machine</h3>${J.length ? `<table><tr><th>#</th><th>Tache</th><th>Jeu</th><th>Etat</th><th>Avancement</th><th>Duree</th><th></th></tr>
    ${J.map(j => `<tr><td class="hint">${j.n}</td><td>${esc(j.label)}${j.params && j.params.block ? " " + esc(j.params.block) : ""}</td><td class="hint">${esc(j.game || "-")}</td>
    <td><span class="state ${j.state}">${ST[j.state] || j.state}</span></td><td style="min-width:140px"><div class="bar"><i style="width:${j.pct}%"></i></div></td>
    <td class="hint">${Math.floor(j.elapsed / 60)} min ${j.elapsed % 60} s</td>
    <td class="btns"><button class="btn small sec" onclick="showLog(${j.n})">Log</button>
    ${j.state === "running" || j.state === "queued" ? `<button class="btn small red" onclick="cancelJob(${j.n})">Stop</button>` : ""}
    ${j.id === "qwen" && j.state === "running" ? `<button class="btn small sec" onclick="api('qwen_stop',{game:'${j.game}'}).then(()=>toast('Qwen s\\'arretera apres la fonction en cours'))">Finir apres la fonction</button>` : ""}</td></tr>`).join("")}</table>` : '<div class="empty">Aucune tache.</div>'}
    <div id="logbox"></div></div>`;
  return h;
}
async function cancelJob(n) { await api("cancel", {n}); toast("Tache arretee"); render(); }
async function showLog(n) {
  openLog = n; const d = await api("log?n=" + n);
  const box = $("#logbox"); if (box) { box.innerHTML = `<h3 style="margin-top:12px">Log de la tache #${n}</h3><pre id="logpre">${esc(d.log)}</pre>`; const p = $("#logpre"); p.scrollTop = p.scrollHeight; }
}

// ---------------- Engine map ----------------
async function viewEngine() {
  const d = await api("engine");
  if (d.error) return "";
  let h = `<div class="card"><h3>Studios (meme studio = souvent le meme moteur)</h3><div class="grid">${d.studios.map(s => `<div class="card" style="margin:0"><b>${esc(s.studio)}</b>
    <div class="hint">${s.games.map(g => `<a href="#game" onclick="selectGame('${g}');return false">${esc(g)}</a>`).join(", ")}</div></div>`).join("")}</div></div>`;
  h += `<div class="split"><div class="card"><h3>Jeux indexes (base d'empreintes)</h3><p class="hint">SDK = code Nintendo present dans 5 jeux ou plus. Unique = code propre au jeu.</p>
    <table><tr><th>Jeu</th><th class="num">Fonctions</th><th class="num">SDK</th><th class="num">Unique</th></tr>
    ${d.games.map(g => `<tr><td>${esc(g.title)}<div class="hint">${esc(g.studio)}</div></td><td class="num">${fmt(g.functions)}</td><td class="num">${fmt(g.sdk)}</td><td class="num">${fmt(g.unique)}</td></tr>`).join("")}</table>
    <div class="btns" style="margin-top:10px"><button class="btn small sec" onclick="api('run',{id:'scan'}).then(r=>r.n&&toast('Indexation lancee'))">Re-indexer les empreintes</button></div></div>
    <div class="card"><h3>Moteurs partages entre jeux</h3><p class="hint">Fonctions identiques entre deux jeux, hors SDK : du code moteur reutilise. Un match dans un jeu = gratuit dans l'autre (niveau "Portable").</p>
    <table><tr><th>Jeu A</th><th>Jeu B</th><th class="num">Moteur commun</th><th class="num">SDK commun</th></tr>
    ${d.pairs.slice(0, 40).map(p => `<tr><td>${esc(p.a)}</td><td>${esc(p.b)}</td><td class="num"><b>${fmt(p.engine)}</b></td><td class="num hint">${fmt(p.sdk)}</td></tr>`).join("")}</table></div></div>`;
  return h;
}

// ---------------- Progression ----------------
function viewProgress() {
  const x = window.XP; if (!x) return '<div class="empty">Chargement...</div>';
  return `<div class="kpis"><div class="kpi"><b>${x.level}</b><span>niveau (${esc(x.rank)})</span></div><div class="kpi"><b>${fmt(x.xp)}</b><span>XP total</span></div>
    <div class="kpi"><b>${fmt(x.stats.matched)}</b><span>fonctions matchees</span></div><div class="kpi"><b>${x.stats.blocks_done}</b><span>blocs termines</span></div></div>
    <div class="split"><div class="card"><h3>Butin recent</h3>${x.events.map(e => e.kind === "loot" ? `<div class="loot ${e.rarity}">+${e.xp} XP &middot; <b>${esc(e.name)}</b> (${e.size} octets) &middot; ${esc(e.game)}</div>`
    : `<div class="loot ${e.kind}">${esc(e.text)}</div>`).join("") || '<div class="empty">Rien encore.</div>'}</div>
    <div class="card"><h3>Succes</h3>${x.achievements.map(a => `<div class="ach ${a.unlocked ? "" : "off"}">${a.unlocked ? "&#127942;" : "&#128274;"} ${esc(a.label)}</div>`).join("")}</div></div>`;
}

// ---------------- Reglages ----------------
function viewSettings() {
  const s = O.settings;
  return `<div class="card" style="max-width:700px"><h3>Reglages</h3><table>
    <tr><td>Ton nom (pour prendre des blocs)</td><td><input id="s-who" value="${esc(s.who)}"></td></tr>
    <tr><td>Taches machine en parallele</td><td><input id="s-par" type="number" min="1" max="8" value="${s.max_parallel_jobs}"></td></tr>
    <tr><td>Modele Qwen (Ollama)</td><td><input id="s-model" value="${esc(s.qwen_model)}"></td></tr>
    <tr><td>Agents Qwen en parallele (par defaut)<div class="hint">Ollama doit avoir OLLAMA_NUM_PARALLEL &ge; ce nombre (variable d'environnement, puis redemarrer Ollama). Avec 16 Go de VRAM : environ 4 pour qwen9-ctx, 8 pour qwen-ctx (4b).</div></td><td><input id="s-agents" type="number" min="1" max="16" value="${s.qwen_agents}"></td></tr>
    <tr><td>Minutes max par fonction (Qwen)</td><td><input id="s-min" type="number" min="1" max="60" value="${s.qwen_minutes}"></td></tr>
    <tr><td>Publier les prises de blocs sur GitHub</td><td><input id="s-push" type="checkbox" ${s.push_claims ? "checked" : ""}></td></tr>
    <tr><td>Compte GitHub</td><td><input id="s-owner" value="${esc(s.github_owner)}" placeholder="rempli a la 1re publication"></td></tr></table>
    <div class="btns" style="margin-top:12px"><button class="btn" onclick="saveSettings()">Enregistrer</button></div></div>`;
}
async function saveSettings() {
  const r = await api("settings", {who: $("#s-who").value.trim(), max_parallel_jobs: +$("#s-par").value, qwen_model: $("#s-model").value.trim(),
    qwen_minutes: +$("#s-min").value, qwen_agents: +$("#s-agents").value, push_claims: $("#s-push").checked, github_owner: $("#s-owner").value.trim()});
  if (!r.error) { O.settings = r; toast("Reglages enregistres"); }
}

// ---------------- boucle ----------------
(async function init() {
  tabs(); await loadOverview(); render(); loadXP();
  setInterval(async () => {
    if (document.hidden || $("#modal").classList.contains("on")) return;
    if (tab === "queue") { const y = scrollY; await render(); if (openLog) showLog(openLog); scrollTo(0, y); }
  }, 4000);
  setInterval(() => { if (!document.hidden) loadXP(); }, 60000);
})();
