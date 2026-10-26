// PPChat — front sem build: chat com disciplinas no contexto + árvore de dependências.

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const SVG_NS = "http://www.w3.org/2000/svg";
const STORE_KEY = "ppchat-conversation-v1";
const MAX_CONTEXT = 12;
const LOGO = '<svg viewBox="0 0 24 24"><path d="M6 8h12M6 12h7M6 16h9"/></svg>';
const ICON = {
  copy: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>',
  page: '<svg viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>',
  chain: '<svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
  route: '<svg viewBox="0 0 24 24"><circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h7a3.5 3.5 0 0 0 0-7H9a3.5 3.5 0 0 1 0-7h7"/></svg>',
  gauge: '<svg viewBox="0 0 24 24"><path d="M12 14l4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/></svg>',
  rules: '<svg viewBox="0 0 24 24"><path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  tree: '<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 12h4m0 0c2 0 2-6 6-6M11 12c2 0 2 6 6 6"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  back: '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
  ask: '<svg viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
};
const THINKING_STEPS = ["Lendo o PPC…", "Consultando o grafo de pré-requisitos…", "Cruzando com os planos de ensino…", "Escrevendo a resposta…"];
const ABORDAGEM = { teorica: "Teórica", pratica: "Prática", teorico_pratica: "Teórico-prática" };

const state = {
  curriculum: null,
  byCode: new Map(),
  requestId: null, // resposta em andamento, para o botão "parar"
  history: [], // {role: "user", text, disciplinas} | {role: "assistant", text, thinking?, usage?, stopped?}
  context: [], // disciplinas selecionadas para a próxima pergunta
  busy: false,
  controller: null,
  focus: null, // disciplina em foco na árvore
  focusHistory: [],
  view: "tree",
};

/* ───────────── Utilidades ───────────── */
const storage = {
  get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
  remove(key) { try { localStorage.removeItem(key); } catch {} },
};
const SMALL_WORDS = new Set(["de", "da", "do", "das", "dos", "e", "a", "o", "à", "para", "em", "na", "no"]);
function titleCase(name) {
  return name.toLowerCase().split(" ").map((word, i) =>
    i > 0 && SMALL_WORDS.has(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)
  ).join(" ");
}
const normalize = (s) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
const levelClass = (nivel) => "lvl-" + normalize(nivel);
const hours = (h) => `${Number(h).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`;
const compact = (n) => (n >= 1000 ? `${(n / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}k` : String(n));
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const disc = (code) => state.byCode.get(code);
const nameOf = (code) => titleCase(disc(code)?.nome || code);
const semesterLabel = (d) => (d.semestre ? `${d.semestre}º sem` : "Optativa");

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ───────────── Tema ───────────── */
$("#theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  root.dataset.theme = current === "dark" ? "light" : "dark";
  try { localStorage.setItem("ppchat-theme", root.dataset.theme); } catch {}
});

/* ───────────── Servidor acordando (plano grátis do Render) ───────────── */
// O plano grátis dorme após 15 min sem uso; enquanto acorda, o proxy responde 502/503 ou derruba a conexão.
// Tenta de novo por até ~90 s mostrando um aviso, em vez de falhar na primeira tentativa.
async function fetchWithWake(url, options = {}) {
  const deadline = Date.now() + 90_000;
  const banner = $("#wake");
  const showTimer = setTimeout(() => (banner.hidden = false), 1500);
  try {
    for (;;) {
      try {
        const response = await fetch(url, options);
        if (![502, 503, 504].includes(response.status) || Date.now() > deadline) return response;
      } catch (error) {
        if (error.name === "AbortError" || Date.now() > deadline) throw error;
      }
      banner.hidden = false;
      await sleep(2500);
    }
  } finally {
    clearTimeout(showTimer);
    banner.hidden = true;
  }
}

/* ───────────── Currículo ───────────── */
async function loadCurriculum() {
  const response = await fetchWithWake("/curriculum");
  if (!response.ok) throw new Error("Não foi possível carregar o currículo");
  const data = await response.json();
  state.curriculum = data;
  data.disciplinas.forEach((d) => state.byCode.set(d.codigo, d));

  $("#course-name").textContent = `${data.curso} · ${data.campus} · ${data.vigencia}`;
  $("#stats").innerHTML = [
    [data.disciplinas.length, "disciplinas"],
    [data.duracao_semestres, "semestres"],
    [hours(data.carga_horaria_total_curso), "no total"],
  ].map(([value, label]) => `<span class="stat"><b>${value}</b>${label}</span>`).join("");

  renderGrid();
  renderRules();
}

/* ───────────── Estado vazio ───────────── */
function renderEmpty(eyebrow = "Seu PPC, em conversa") {
  const { disciplinas, gargalos } = state.curriculum;
  const deepest = [...disciplinas].sort((a, b) => b.profundidade - a.profundidade || b.indice_complexidade - a.indice_complexidade)
    .find((d) => d.tipo === "obrigatoria" && !/extens/i.test(d.nome)) || disciplinas[0];
  const gate = disc(gargalos[1] || gargalos[0]);
  const pair = [gargalos[2], "SCLBDD1"].filter((c) => disc(c));
  const items = [
    { icon: ICON.chain, tag: "Dependências", text: `Quais são todos os pré-requisitos de ${titleCase(deepest.nome)}?` },
    { icon: ICON.route, tag: "Com disciplinas no contexto", text: "Em que ordem devo cursar estas disciplinas e por quê?", context: pair },
    { icon: ICON.gauge, tag: "Dificuldade", text: "Quais são as disciplinas mais difíceis do curso e por quê?" },
    { icon: ICON.rules, tag: "Planejamento", text: `Reprovei em ${titleCase(gate.nome)}. Como fica o resto do meu curso?` },
  ];
  $("#messages").innerHTML = `
    <div class="empty" id="empty">
      <p class="eyebrow">${eyebrow}</p>
      <h1>Pergunte qualquer coisa <em>sobre o seu curso.</em></h1>
      <p class="lede">Respostas baseadas no Projeto Pedagógico inteiro, com a página de cada informação.
        Digite <kbd>@</kbd> para colocar disciplinas no contexto da pergunta.</p>
      <div class="suggestions">${items.map((item, i) => `
        <button class="suggestion" style="animation-delay:${80 + i * 60}ms" data-i="${i}">
          <span class="s-tag">${item.icon}${item.tag}</span>
          <span class="s-text">${escapeHtml(item.text)}</span>
          ${item.context ? `<span class="s-chips">${item.context.map((c) => staticChip(c)).join("")}</span>` : ""}
        </button>`).join("")}
      </div>
    </div>`;
  $$(".suggestion").forEach((btn) => btn.addEventListener("click", () => {
    const item = items[btn.dataset.i];
    if (item.context) state.context = [...item.context];
    ask(item.text);
  }));
}

/* ───────────── Chips de disciplina ───────────── */
function staticChip(code) {
  const d = disc(code);
  if (!d) return "";
  return `<span class="dchip is-static" data-tree="${code}" title="Ver árvore de ${escapeHtml(nameOf(code))}">
    <i class="dot ${levelClass(d.nivel_estimado)}"></i><span class="dchip-name">${escapeHtml(nameOf(code))}</span></span>`;
}

function renderContext() {
  const box = $("#context");
  box.hidden = !state.context.length;
  box.innerHTML = state.context.length ? `<span class="context-label">No contexto</span>` + state.context.map((code) => {
    const d = disc(code);
    return `<span class="dchip" data-code="${code}">
      <i class="dot ${levelClass(d.nivel_estimado)}"></i>
      <span class="dchip-name">${escapeHtml(nameOf(code))}</span>
      <button type="button" data-tree="${code}" title="Ver árvore" aria-label="Ver árvore de ${escapeHtml(nameOf(code))}">${ICON.tree}</button>
      <button type="button" data-remove="${code}" title="Remover" aria-label="Remover ${escapeHtml(nameOf(code))}">${ICON.close}</button>
    </span>`;
  }).join("") : "";
  $$(".node, .card").forEach((el) => el.classList.toggle("in-context", state.context.includes(el.dataset.code)));
  updateSendState();
}

function toggleContext(code, { force } = {}) {
  const has = state.context.includes(code);
  const add = force ?? !has;
  if (add && !has) {
    if (state.context.length >= MAX_CONTEXT) return toast(`Até ${MAX_CONTEXT} disciplinas por pergunta.`);
    state.context.push(code);
  } else if (!add && has) {
    state.context = state.context.filter((c) => c !== code);
  }
  renderContext();
  if (state.focus) renderInfo(state.focus);
}

$("#context").addEventListener("click", (event) => {
  const target = event.target.closest("[data-tree], [data-remove]");
  if (!target) return;
  if (target.dataset.remove) toggleContext(target.dataset.remove, { force: false });
  else openDrawer("tree", target.dataset.tree);
});

// Chips estáticos (sugestões, bolhas do usuário) abrem a árvore
document.addEventListener("click", (event) => {
  const chip = event.target.closest(".dchip.is-static[data-tree]");
  if (chip && !chip.closest(".suggestion")) openDrawer("tree", chip.dataset.tree);
});

/* ───────────── Seletor de disciplinas (@) ───────────── */
const input = $("#input");
const picker = { open: false, start: -1, items: [], active: 0 };

function mentionQuery() {
  if (picker.start < 0) return "";
  return input.value.slice(picker.start + 1, input.selectionStart);
}

function openPicker(start) {
  picker.open = true;
  picker.start = start;
  picker.active = 0;
  $("#picker").hidden = false;
  $("#add-discipline").setAttribute("aria-expanded", "true");
  renderPicker();
}

function closePicker() {
  picker.open = false;
  picker.start = -1;
  $("#picker").hidden = true;
  $("#add-discipline").setAttribute("aria-expanded", "false");
}

function highlight(text, query) {
  if (!query) return escapeHtml(text);
  const i = normalize(text).indexOf(normalize(query));
  if (i < 0) return escapeHtml(text);
  return escapeHtml(text.slice(0, i)) + `<mark>${escapeHtml(text.slice(i, i + query.length))}</mark>` + escapeHtml(text.slice(i + query.length));
}

function renderPicker() {
  const query = mentionQuery().trim();
  const q = normalize(query);
  const list = state.curriculum.disciplinas.filter((d) => !q || normalize(`${d.nome} ${d.codigo}`).includes(q));
  picker.items = list.map((d) => d.codigo);
  picker.active = Math.min(picker.active, Math.max(0, list.length - 1));

  let html = "", lastGroup = null, index = 0;
  for (const d of list) {
    const group = d.semestre ? `${d.semestre}º semestre` : "Optativas";
    if (!q && group !== lastGroup) { html += `<div class="picker-group">${group}</div>`; lastGroup = group; }
    const selected = state.context.includes(d.codigo);
    html += `<button type="button" class="picker-item ${index === picker.active ? "is-active" : ""} ${selected ? "is-selected" : ""}"
        data-code="${d.codigo}" data-index="${index}" role="option" aria-selected="${selected}">
      <i class="dot ${levelClass(d.nivel_estimado)}"></i>
      <span class="p-code">${d.codigo}</span>
      <span class="p-name">${highlight(titleCase(d.nome), query)}</span>
      <span class="p-meta">${q ? semesterLabel(d) : hours(d.carga_horaria_total)}</span>
      <svg class="p-check" viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>
    </button>`;
    index++;
  }
  $("#picker-list").innerHTML = html || `<div class="picker-empty">Nenhuma disciplina encontrada para “${escapeHtml(query)}”.</div>`;
  $(".picker-item.is-active")?.scrollIntoView({ block: "nearest" });
}

function choosePicker(code) {
  // Remove o "@consulta" digitado e coloca a disciplina no contexto
  let end = input.selectionStart;
  if (picker.start >= 0) {
    if (input.value[picker.start - 1] === " " && input.value[end] === " ") end++; // evita espaço duplo
    input.value = input.value.slice(0, picker.start) + input.value.slice(end);
  }
  const caret = Math.max(0, picker.start);
  closePicker();
  toggleContext(code);
  input.focus();
  input.setSelectionRange(caret, caret);
  autosize();
}

function syncPicker() {
  const caret = input.selectionStart;
  const before = input.value.slice(0, caret);
  const at = before.lastIndexOf("@");
  const valid = at >= 0 && (at === 0 || /\s/.test(before[at - 1])) && !/[\n@]/.test(before.slice(at + 1)) && caret - at <= 40;
  if (valid) {
    if (!picker.open || picker.start !== at) openPicker(at);
    else renderPicker();
  } else if (picker.open) {
    closePicker();
  }
}

$("#add-discipline").addEventListener("click", () => {
  if (picker.open) { closePicker(); input.focus(); return; }
  // Insere "@" no cursor: o mesmo fluxo de digitar
  const pos = input.selectionStart ?? input.value.length;
  const needsSpace = pos > 0 && !/\s/.test(input.value[pos - 1]);
  input.value = input.value.slice(0, pos) + (needsSpace ? " @" : "@") + input.value.slice(pos);
  const caret = pos + (needsSpace ? 2 : 1);
  input.focus();
  input.setSelectionRange(caret, caret);
  syncPicker();
});
$("#picker-list").addEventListener("mousedown", (event) => event.preventDefault()); // não tira o foco do textarea
$("#picker-list").addEventListener("click", (event) => {
  const item = event.target.closest(".picker-item");
  if (item) choosePicker(item.dataset.code);
});
document.addEventListener("click", (event) => {
  if (picker.open && !event.target.closest(".composer-box")) closePicker();
});

/* ───────────── Painel: árvore e grade ───────────── */
const drawer = $("#drawer");

function openDrawer(view = state.view, code) {
  closePicker();
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
  setView(view);
  // Com código, foca na disciplina; sem código, reabre no que estava (reaproveitando o desenho)
  if (view === "tree" && code && code !== state.focus) focusTree(code, { push: true });
}
function closeDrawer() {
  drawer.classList.remove("is-open");
  drawer.setAttribute("aria-hidden", "true");
  $("#search-results").hidden = true;
}
function setView(view) {
  state.view = view;
  $$(".seg").forEach((seg) => {
    const active = seg.dataset.view === view;
    seg.classList.toggle("is-active", active);
    seg.setAttribute("aria-selected", active);
  });
  $("#view-tree").classList.toggle("is-visible", view === "tree");
  $("#view-grid").classList.toggle("is-visible", view === "grid");
  if (view === "tree" && !$(".node", $("#tree-inner"))) showTree(state.focus); // primeiro desenho
}

$("#open-structure").addEventListener("click", () => openDrawer());
$("#close-drawer").addEventListener("click", closeDrawer);
$$(".seg").forEach((seg) => seg.addEventListener("click", () => setView(seg.dataset.view)));
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || rulesModal.open) return;
  if (picker.open) return closePicker();
  if (drawer.classList.contains("is-open")) closeDrawer();
});

/* Busca no painel */
const search = $("#search");
search.addEventListener("input", () => {
  const q = normalize(search.value.trim());
  const results = $("#search-results");
  $("#board").classList.toggle("is-filtering", !!q);
  $$(".card").forEach((card) => card.classList.toggle("is-match", !!q && normalize(`${disc(card.dataset.code).nome} ${card.dataset.code}`).includes(q)));
  if (!q) { results.hidden = true; return; }
  const list = state.curriculum.disciplinas.filter((d) => normalize(`${d.nome} ${d.codigo}`).includes(q)).slice(0, 8);
  results.innerHTML = list.length ? list.map((d, i) => `
    <button type="button" class="picker-item ${i === 0 ? "is-active" : ""}" data-code="${d.codigo}">
      <i class="dot ${levelClass(d.nivel_estimado)}"></i>
      <span class="p-name">${highlight(titleCase(d.nome), search.value.trim())}</span>
      <span class="p-meta">${semesterLabel(d)}</span>
    </button>`).join("") : '<div class="picker-empty">Nada encontrado.</div>';
  results.hidden = false;
});
search.addEventListener("keydown", (event) => {
  if (event.key === "Enter") $("#search-results .picker-item")?.click();
  if (event.key === "Escape") { search.value = ""; search.dispatchEvent(new Event("input")); event.stopPropagation(); }
});
$("#search-results").addEventListener("click", (event) => {
  const item = event.target.closest(".picker-item");
  if (!item) return;
  search.value = "";
  search.dispatchEvent(new Event("input"));
  setView("tree");
  focusTree(item.dataset.code, { push: true });
});

/* Árvore de dependências: "curso inteiro" (state.focus = null) ou centrada numa disciplina */
const TREE_WIDE = { nodeW: 214, focusW: 250, gapX: 86, gapY: 14, padX: 40, padTop: 58, padBottom: 70 };
const TREE_COURSE = { nodeW: 178, focusW: 178, gapX: 56, gapY: 10, padX: 28, padTop: 54, padBottom: 40 };
const TREE_NARROW = { nodeW: 150, focusW: 168, gapX: 40, gapY: 10, padX: 16, padTop: 54, padBottom: 72 };
let TREE = TREE_WIDE;

const isConnected = (d) => d.pre_requisitos.length > 0 || d.libera_diretamente.length > 0;

// Reordena cada coluna pela posição média dos vizinhos (heurística do baricentro): menos cruzamentos
function orderColumns(columns, level, edges, downLevels, upLevels) {
  const pos = (c) => columns.get(level.get(c)).indexOf(c) / Math.max(1, columns.get(level.get(c)).length - 1);
  const reorder = (l, neighbors) => {
    const score = (c) => { const n = neighbors(c); return n.length ? n.reduce((s, x) => s + pos(x), 0) / n.length : pos(c); };
    columns.set(l, columns.get(l).map((c) => [c, score(c)]).sort((a, b) => a[1] - b[1]).map(([c]) => c));
  };
  for (let pass = 0; pass < 2; pass++) {
    for (const l of downLevels) reorder(l, (c) => edges.filter((e) => e.to === c).map((e) => e.from));
    for (const l of upLevels) reorder(l, (c) => edges.filter((e) => e.from === c).map((e) => e.to));
  }
}

function makeColumns(level) {
  const levels = [...new Set(level.values())].sort((a, b) => a - b);
  const columns = new Map(levels.map((l) => [l, [...level.keys()].filter((c) => level.get(c) === l)
    .sort((a, b) => (disc(a).semestre || 99) - (disc(b).semestre || 99) || disc(a).nome.localeCompare(disc(b).nome))]));
  return { levels, columns };
}

// Curso inteiro: todas as disciplinas, uma coluna por semestre (optativas no fim)
function buildCourseGraph() {
  const { disciplinas, duracao_semestres } = state.curriculum;
  const level = new Map(disciplinas.map((d) => [d.codigo, d.semestre || duracao_semestres + 1]));
  const edges = [];
  for (const c of level.keys()) for (const p of disc(c).pre_requisitos) if (level.has(p)) edges.push({ from: p, to: c, side: "all" });
  const { levels, columns } = makeColumns(level);
  orderColumns(columns, level, edges, levels.slice(1), levels.slice(0, -1).reverse());
  // As sem ligação ficam no fim da coluna, para não cruzar as setas das outras
  for (const l of levels) {
    const col = columns.get(l);
    columns.set(l, [...col.filter((c) => isConnected(disc(c))), ...col.filter((c) => !isConnected(disc(c)))]);
  }
  return {
    levels, columns, edges, level,
    label: (l) => [l > duracao_semestres ? "Optativas" : `${l}º semestre`, ""],
    side: () => "",
  };
}

// Disciplina em foco: o que vem antes à esquerda (pelo caminho mais longo até ela), o que libera à direita
function buildFocusGraph(code) {
  const d = disc(code);
  const anc = new Set(d.pre_requisitos_transitivos);
  const desc = new Set(d.libera_transitivamente);
  const level = new Map([[code, 0]]);
  const longest = (start, next, members) => {
    const memo = new Map();
    const dist = (c) => {
      if (c === code) return 0;
      if (!memo.has(c)) memo.set(c, Math.max(1, ...next(c).filter((n) => n === code || members.has(n)).map((n) => dist(n) + 1)));
      return memo.get(c);
    };
    return dist(start);
  };
  anc.forEach((c) => level.set(c, -longest(c, (x) => disc(x).libera_diretamente, anc)));
  desc.forEach((c) => level.set(c, longest(c, (x) => disc(x).pre_requisitos, desc)));

  const edges = [];
  for (const c of [code, ...anc]) for (const p of disc(c).pre_requisitos) if (anc.has(p)) edges.push({ from: p, to: c, side: "anc" });
  for (const c of desc) for (const p of disc(c).pre_requisitos) if (p === code || desc.has(p)) edges.push({ from: p, to: c, side: "desc" });

  const { levels, columns } = makeColumns(level);
  orderColumns(columns, level, edges, levels.filter((l) => l > 0), levels.filter((l) => l < 0).reverse());
  return {
    levels, columns, edges, level, focus: code,
    directs: new Set([...d.pre_requisitos, ...d.libera_diretamente]),
    label: (l) => (l === 0 ? ["Foco", "focus"] : l < 0 ? [l === -1 ? "Logo antes" : `${-l} etapas antes`, "anc"] : [l === 1 ? "Libera" : `${l} etapas depois`, "desc"]),
    side: (l) => (l < 0 ? "anc" : l > 0 ? "desc" : ""),
  };
}

function nodeHtml(code, { side = "", focus = false, direct = false }) {
  const d = disc(code);
  const blocks = d.libera_transitivamente.length;
  const inCtx = state.context.includes(code);
  const solo = !isConnected(d); // sem pré-requisitos nem dependentes: borda tracejada
  return `
    <button class="node ${side} ${focus ? "is-focus" : ""} ${direct ? "direct" : ""} ${inCtx ? "in-context" : ""} ${solo ? "is-solo" : ""}"
        data-code="${code}" title="${focus ? "" : "Centralizar a árvore nesta disciplina"}">
      <span class="node-top"><span class="node-code">${code}</span>
        ${inCtx ? '<span class="ctx-badge">no chat</span>' : `<i class="dot ${levelClass(d.nivel_estimado)}"></i>`}</span>
      <span class="node-name">${escapeHtml(titleCase(d.nome))}</span>
      <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
      <span class="node-meta"><span>${semesterLabel(d)} · ${hours(d.carga_horaria_total)}</span>
        ${blocks >= 3 && side !== "anc" ? `<span>trava ${blocks}</span>` : ""}</span>
    </button>`;
}

// Troca o que a árvore mostra: um código foca na disciplina, null mostra o curso inteiro
function showTree(code) {
  state.focus = code && disc(code) ? code : null;
  renderTree();
  renderCrumbs();
  renderInfo(state.focus);
  $("#tree-info").classList.remove("is-mobile-open");
}
function focusTree(code, { push = false } = {}) {
  if (code && !disc(code)) return;
  if (push && state.focus !== code) state.focusHistory.push(state.focus);
  showTree(code);
}
function showCourse() {
  state.focusHistory = [];
  showTree(null);
}

function renderCrumbs() {
  const crumbs = $("#tree-crumbs");
  crumbs.innerHTML = state.focus
    ? `<button class="crumb" data-crumb="course">${ICON.back}Curso inteiro</button>
       <span class="crumb-sep">›</span><span class="crumb is-current">${escapeHtml(nameOf(state.focus))}</span>`
    : `<span class="crumb is-current">Curso inteiro</span>
       <span class="crumb-hint">Passe o mouse para ver a cadeia de uma disciplina · clique para focar nela</span>`;
}
$("#tree-crumbs").addEventListener("click", (event) => {
  if (event.target.closest("[data-crumb=course]")) showCourse();
});

// Painel de detalhes ao lado da árvore: pode ser fechado para a árvore ocupar a tela toda
const INFO_KEY = "ppchat-tree-info";
const PANEL_ICON = '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/></svg>';
function setInfoVisible(visible) {
  $("#view-tree").classList.toggle("info-hidden", !visible);
  const toggle = $("#toggle-info");
  toggle.setAttribute("aria-pressed", visible);
  toggle.innerHTML = `${PANEL_ICON}${visible ? "Ocultar painel" : "Mostrar painel"}`;
  storage.set(INFO_KEY, visible);
}
setInfoVisible(storage.get(INFO_KEY) ?? true);
$("#toggle-info").addEventListener("click", () => setInfoVisible($("#view-tree").classList.contains("info-hidden")));
$("#open-info").addEventListener("click", () => setInfoVisible(true));

let lastTreeSize = "";

function renderTree({ animate = true } = {}) {
  const canvas = $("#tree-canvas");
  const graph = state.focus ? buildFocusGraph(state.focus) : buildCourseGraph();
  const { levels, columns, edges, level } = graph;
  TREE = canvas.clientWidth < 640 ? TREE_NARROW : state.focus ? TREE_WIDE : TREE_COURSE;
  const widthOf = (l) => (graph.focus && l === 0 ? TREE.focusW : TREE.nodeW);
  const inner = $("#tree-inner");
  inner.classList.toggle("no-anim", !animate);
  inner.classList.toggle("is-course", !state.focus);
  inner.classList.remove("is-hovering");

  // O SVG vem primeiro para as setas ficarem atrás dos cards
  inner.innerHTML = `<svg class="tree-edges" id="tree-edges"></svg>` + levels.map((l) => {
    const [label, cls] = graph.label(l);
    return `<span class="col-label ${cls}" data-level="${l}">${label}</span>` +
      columns.get(l).map((c) => nodeHtml(c, { side: graph.side(l), focus: c === graph.focus, direct: graph.directs?.has(c) })).join("");
  }).join("") +
    (graph.focus && levels.length === 1 ? `<p class="tree-empty">Esta disciplina não exige nem libera nenhuma outra: dá para cursá-la a qualquer momento do seu semestre.</p>` : "");

  // Posiciona: mede as alturas reais e centraliza cada coluna
  const nodes = new Map($$(".node", inner).map((el) => [el.dataset.code, el]));
  nodes.forEach((el, c) => el.style.setProperty("--node-w", `${widthOf(level.get(c))}px`));
  const colX = new Map();
  let x = TREE.padX;
  for (const l of levels) {
    colX.set(l, x);
    x += widthOf(l) + TREE.gapX;
  }
  const width = x - TREE.gapX + TREE.padX;
  const heights = new Map(levels.map((l) => [l, columns.get(l).reduce((s, c) => s + nodes.get(c).offsetHeight, 0) + TREE.gapY * (columns.get(l).length - 1)]));
  const height = Math.max(Math.max(...heights.values()) + TREE.padTop + TREE.padBottom, canvas.clientHeight);
  const offset = Math.max(0, (canvas.clientWidth - width) / 2); // centraliza quando sobra espaço
  const boxes = new Map();
  for (const l of levels) {
    let y = TREE.padTop + (height - TREE.padTop - TREE.padBottom - heights.get(l)) / 2;
    const w = widthOf(l);
    const left = colX.get(l) + offset;
    for (const c of columns.get(l)) {
      const el = nodes.get(c);
      const h = el.offsetHeight;
      el.style.left = `${left}px`;
      el.style.top = `${y}px`;
      const step = graph.focus ? Math.abs(l) : levels.indexOf(l);
      el.style.setProperty("--delay", `${step * 0.04}s`);
      el.style.setProperty("--from", `${(graph.focus ? Math.sign(l) : 1) * 14}px`);
      boxes.set(c, { x: left, y, w, h });
      y += h + TREE.gapY;
    }
    $(`.col-label[data-level="${l}"]`, inner).style.left = `${left + w / 2}px`;
  }
  inner.style.width = `${Math.max(width, canvas.clientWidth)}px`;
  inner.style.height = `${height}px`;

  // Setas
  const svg = $("#tree-edges");
  svg.setAttribute("width", inner.offsetWidth);
  svg.setAttribute("height", height);
  const step = (c) => (graph.focus ? Math.abs(level.get(c)) : levels.indexOf(level.get(c)));
  for (const e of edges) {
    const a = boxes.get(e.from), b = boxes.get(e.to);
    const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
    const bend = Math.max(40, (x2 - x1) * 0.5);
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`);
    path.setAttribute("class", `e-${e.side} e-anim`);
    path.dataset.from = e.from;
    path.dataset.to = e.to;
    svg.append(path);
    if (animate) {
      path.style.setProperty("--len", Math.ceil(path.getTotalLength()));
      path.style.setProperty("--delay", `${0.06 + Math.max(step(e.from), step(e.to)) * 0.04}s`);
    }
    const dot = document.createElementNS(SVG_NS, "circle");
    dot.setAttribute("cx", x2); dot.setAttribute("cy", y2); dot.setAttribute("r", 3.5);
    dot.setAttribute("class", `e-${e.side}`);
    dot.dataset.from = e.from;
    dot.dataset.to = e.to;
    svg.append(dot);
  }

  // Foco: centraliza a disciplina; curso inteiro: começa do 1º semestre
  if (graph.focus) {
    const f = boxes.get(graph.focus);
    canvas.scrollTo({ left: f.x + f.w / 2 - canvas.clientWidth / 2, top: f.y + f.h / 2 - canvas.clientHeight / 2 });
  } else {
    canvas.scrollTo({ left: 0, top: 0 }); // do topo, para os títulos dos semestres aparecerem
  }
  lastTreeSize = `${canvas.clientWidth}x${canvas.clientHeight}`;
}

$("#tree-inner").addEventListener("click", (event) => {
  const node = event.target.closest(".node");
  if (!node) return;
  if (node.dataset.code === state.focus) $("#tree-info").classList.toggle("is-mobile-open");
  else focusTree(node.dataset.code, { push: true });
});
$("#info-fab").addEventListener("click", () => $("#tree-info").classList.toggle("is-mobile-open"));

// Hover: no foco destaca as setas da disciplina; no curso inteiro destaca a cadeia completa dela
$("#tree-inner").addEventListener("mouseover", (event) => {
  const node = event.target.closest(".node");
  const inner = $("#tree-inner");
  const svg = $("#tree-edges");
  if (!svg) return;
  const code = node?.dataset.code;
  const marks = $$("path, circle", svg);
  if (!code) {
    inner.classList.remove("is-hovering");
    svg.classList.remove("has-hover");
    return;
  }
  if (state.focus) {
    svg.classList.add("has-hover");
    marks.forEach((el) => el.classList.toggle("is-hot", el.dataset.from === code || el.dataset.to === code));
    return;
  }
  const d = disc(code);
  const up = new Set([code, ...d.pre_requisitos_transitivos]);
  const down = new Set([code, ...d.libera_transitivamente]);
  inner.classList.add("is-hovering");
  $$(".node", inner).forEach((el) => el.classList.toggle("is-dim", !up.has(el.dataset.code) && !down.has(el.dataset.code)));
  marks.forEach((el) => {
    const anc = up.has(el.dataset.from) && up.has(el.dataset.to);
    const desc = down.has(el.dataset.from) && down.has(el.dataset.to);
    el.classList.toggle("is-anc-hot", anc);
    el.classList.toggle("is-desc-hot", desc && !anc);
  });
});
$("#tree-inner").addEventListener("mouseleave", () => {
  $("#tree-inner").classList.remove("is-hovering");
  $("#tree-edges")?.classList.remove("has-hover");
});

// Só redesenha quando o tamanho realmente muda (janela redimensionada), e sem repetir as animações
let resizeTimer = 0;
new ResizeObserver(([entry]) => {
  if (!entry.contentRect.width || state.view !== "tree" || !$(".node", $("#tree-inner"))) return;
  if (`${$("#tree-canvas").clientWidth}x${$("#tree-canvas").clientHeight}` === lastTreeSize) return;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => renderTree({ animate: false }), 120);
}).observe($("#tree-canvas"));

const INFO_CLOSE = `<button class="icon-btn info-close" data-act="hide-info" title="Fechar painel" aria-label="Fechar painel">${ICON.close}</button>`;
const goChips = (codes, extra = () => "") =>
  `<div class="chips">${codes.map((c) => `<button class="chip-go" data-goto="${c}"><i class="dot ${levelClass(disc(c).nivel_estimado)}"></i>${escapeHtml(nameOf(c))}${extra(c)}</button>`).join("")}</div>`;

function renderCourseInfo() {
  const { disciplinas, cadeia_critica, gargalos, duracao_semestres } = state.curriculum;
  const connected = disciplinas.filter(isConnected);
  const isolated = disciplinas.filter((d) => !isConnected(d));
  $("#tree-info").innerHTML = `${INFO_CLOSE}
    <span class="info-code">VISÃO GERAL</span>
    <h3>Curso inteiro</h3>
    <div class="pills">
      <span class="pill">${duracao_semestres} semestres</span>
      <span class="pill">${disciplinas.length} disciplinas</span>
      <span class="pill">${hours(state.curriculum.carga_horaria_total_curso)}</span>
    </div>
    <div class="info-section">
      <div class="stat-grid">
        <div class="stat-card anc"><b>${connected.length}</b><span>com pré-requisitos ou dependentes</span></div>
        <div class="stat-card desc"><b>${cadeia_critica.length}</b><span>etapas na cadeia mais longa</span></div>
      </div>
    </div>
    <div class="info-section">
      <h4>Cadeia mais longa</h4>
      <ol class="chain">${cadeia_critica.map((c) => `<li><button class="link" data-goto="${c}">${escapeHtml(nameOf(c))}</button></li>`).join("")}</ol>
    </div>
    <div class="info-section">
      <h4>Mais travam o curso se reprovadas</h4>
      ${goChips(gargalos.slice(0, 6), (c) => ` <b>${disc(c).libera_transitivamente.length}</b>`)}
    </div>
    ${isolated.length ? `<div class="info-section">
      <p class="small-note">${isolated.length} disciplinas não exigem nem liberam nenhuma outra: aparecem com
        <b>borda tracejada</b> no fim de cada semestre e podem ser cursadas sem travar nada.</p>
    </div>` : ""}`;
}

function renderInfo(code) {
  if (!code) return renderCourseInfo();
  const d = disc(code);
  const inCtx = state.context.includes(code);
  const name = titleCase(d.nome);
  const back = state.focusHistory.at(-1);
  $("#tree-info").innerHTML = `${INFO_CLOSE}
    ${state.focusHistory.length ? `<button class="btn btn-sm back-btn" data-act="back">${ICON.back}<span>Voltar para ${back ? escapeHtml(nameOf(back)) : "o curso inteiro"}</span></button>` : ""}
    <span class="info-code">${d.codigo}</span>
    <h3>${escapeHtml(name)}</h3>
    <div class="pills">
      <span class="pill">${d.semestre ? `${d.semestre}º semestre` : "Optativa"}</span>
      <span class="pill">${hours(d.carga_horaria_total)}</span>
      <span class="pill">${d.aulas_semanais} aulas/semana</span>
      <span class="pill">${ABORDAGEM[d.abordagem]}</span>
      ${d.usa_laboratorio ? '<span class="pill">Laboratório</span>' : ""}
    </div>
    <div class="info-actions">
      <button class="btn ${inCtx ? "" : "btn-primary"}" data-act="context">${inCtx ? `${ICON.check}No contexto do chat · remover` : `${ICON.plus}Adicionar ao chat`}</button>
      <div class="row">
        <button class="btn btn-sm" data-ask="O que eu vou aprender em ${escapeHtml(name)}? Resuma a ementa e os objetivos.">${ICON.ask}O que aprendo?</button>
        <button class="btn btn-sm" data-ask="O que acontece com o meu curso se eu reprovar em ${escapeHtml(name)}?">E se reprovar?</button>
      </div>
    </div>
    <div class="info-section">
      <div class="stat-grid">
        <div class="stat-card anc"><b>${d.pre_requisitos_transitivos.length}</b><span>vêm antes (${d.pre_requisitos.length} direto${d.pre_requisitos.length === 1 ? "" : "s"})</span></div>
        <div class="stat-card desc"><b>${d.libera_transitivamente.length}</b><span>dependem dela</span></div>
      </div>
    </div>
    <div class="info-section">
      <h4>Complexidade estimada</h4>
      <div class="complexity">
        <span class="score">${d.indice_complexidade.toLocaleString("pt-BR")}</span>
        <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
      </div>
      <p class="small-note">${d.nivel_estimado} · ${d.profundidade} etapa(s) de pré-requisito até ela. Estimativa, não é dado oficial do PPC.</p>
    </div>
    ${d.topicos_principais.length ? `<div class="info-section"><h4>Tópicos</h4><ul class="topics">${d.topicos_principais.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul></div>` : ""}
    ${d.pagina_plano_ensino ? `<div class="info-section"><a class="btn btn-sm" href="/pdf#page=${d.pagina_plano_ensino}" target="_blank" rel="noopener">${ICON.page}Plano de ensino · p. ${d.pagina_plano_ensino}</a></div>` : ""}`;
}

$("#tree-info").addEventListener("click", (event) => {
  const target = event.target.closest("[data-act], [data-ask], [data-goto]");
  if (!target) return;
  if (target.dataset.goto) focusTree(target.dataset.goto, { push: true });
  else if (target.dataset.act === "hide-info") {
    // No celular o painel é uma camada por cima da árvore; no desktop, fecha a coluna lateral
    if (matchMedia("(max-width: 900px)").matches) $("#tree-info").classList.remove("is-mobile-open");
    else setInfoVisible(false);
  }
  else if (target.dataset.act === "context") toggleContext(state.focus);
  else if (target.dataset.act === "back") showTree(state.focusHistory.pop() ?? null);
  else if (target.dataset.ask) {
    toggleContext(state.focus, { force: true });
    closeDrawer();
    ask(target.dataset.ask);
  }
});

/* Grade por semestre */
function renderGrid() {
  const { disciplinas, duracao_semestres } = state.curriculum;
  const columns = [];
  for (let s = 1; s <= duracao_semestres; s++) columns.push({ title: `${s}º semestre`, items: disciplinas.filter((d) => d.semestre === s) });
  const optional = disciplinas.filter((d) => !d.semestre);
  if (optional.length) columns.push({ title: "Optativas", items: optional });

  $("#board-inner").innerHTML = columns.map((col) => `
    <div class="column">
      <div class="col-head"><b>${col.title}</b><span>${hours(col.items.reduce((sum, d) => sum + d.carga_horaria_total, 0))}</span></div>
      ${col.items.map((d) => {
        const blocks = d.libera_transitivamente.length;
        return `<button class="card" data-code="${d.codigo}">
          <span class="card-top"><span class="card-code">${d.codigo}</span><i class="dot ${levelClass(d.nivel_estimado)}"></i></span>
          <span class="card-name">${escapeHtml(titleCase(d.nome))}</span>
          <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
          <span class="card-meta"><span>${hours(d.carga_horaria_total)}</span>
            ${blocks >= 4 ? `<span class="badge-gate">trava ${blocks}</span>` : ""}</span>
        </button>`;
      }).join("")}
    </div>`).join("");
}
$("#board-inner").addEventListener("click", (event) => {
  const card = event.target.closest(".card");
  if (!card) return;
  setView("tree");
  focusTree(card.dataset.code, { push: true });
});

function renderRules() {
  const rules = state.curriculum.requisitos_gerais;
  $("#rules-body").innerHTML = rules.length
    ? rules.map((r) => `<div class="rule"><b>${escapeHtml(r.item)}</b><p>${escapeHtml(r.descricao)} ${r.pagina ? pageChip(r.pagina) : ""}</p></div>`).join("")
    : '<p class="muted">Nenhuma regra extraída.</p>';
}
const rulesModal = $("#rules-modal");
$("#open-rules").addEventListener("click", () => rulesModal.showModal());
rulesModal.addEventListener("click", (event) => {
  if (event.target === rulesModal || event.target.closest("[data-close]")) rulesModal.close();
});

/* ───────────── Respostas: markdown + chips ───────────── */
const pageChip = (from, to) =>
  `<a class="page-ref" href="/pdf#page=${from}" target="_blank" rel="noopener" title="Abrir o PPC na página ${from}">${ICON.page}p. ${from}${to ? `–${to}` : ""}</a>`;
const REF_PATTERN = /\[(?:Páginas?|p\.)\s*(\d+)(?:\s*[–-]\s*(\d+))?\]|\b(SCL[A-Z0-9]{4,5})\b/g;

function enhance(root) {
  $$("table", root).forEach((table) => {
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    table.replaceWith(wrap);
    wrap.append(table);
  });
  $$("a", root).forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => node.parentElement.closest("a, code, pre") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  const nodes = [];
  while (walker.nextNode()) {
    REF_PATTERN.lastIndex = 0; // regex com /g guarda estado entre chamadas de test()
    if (REF_PATTERN.test(walker.currentNode.data)) nodes.push(walker.currentNode);
  }
  for (const node of nodes) {
    REF_PATTERN.lastIndex = 0;
    const html = escapeHtml(node.data).replace(REF_PATTERN, (match, from, to, code) => {
      if (from) return pageChip(from, to);
      return disc(code) ? `<button class="code-ref" data-code="${code}" title="${escapeHtml(nameOf(code))} — ver árvore">${code}</button>` : match;
    });
    const span = document.createElement("span");
    span.innerHTML = html;
    node.replaceWith(...span.childNodes);
  }
}

function renderMarkdown(el, text, { streaming = false } = {}) {
  el.innerHTML = DOMPurify.sanitize(marked.parse(text, { gfm: true }));
  enhance(el);
  if (streaming) {
    const last = el.lastElementChild || el;
    const target = last.matches("ul, ol, .table-wrap") ? (last.querySelector("li:last-child, td:last-child") || last) : last;
    target.classList.add("caret");
  }
}

$("#messages").addEventListener("click", (event) => {
  const chip = event.target.closest(".code-ref");
  if (chip) openDrawer("tree", chip.dataset.code);
});

/* ───────────── Chat ───────────── */
const messagesEl = $("#messages");
const composer = $("#composer");

function scrollToBottom(force = false) {
  const nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 140;
  if (force || nearBottom) messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addUserMessage(text, disciplinas = []) {
  $("#empty")?.remove();
  messagesEl.insertAdjacentHTML("beforeend", `
    <div class="msg msg-user"><div class="bubble-wrap">
      ${disciplinas.length ? `<div class="bubble-chips">${disciplinas.map(staticChip).join("")}</div>` : ""}
      <div class="bubble">${escapeHtml(text)}</div>
    </div></div>`);
}

function addBotMessage() {
  $("#empty")?.remove();
  messagesEl.insertAdjacentHTML("beforeend", `
    <div class="msg msg-bot">
      <div class="avatar">${LOGO}</div>
      <div class="body">
        <details class="reasoning" hidden>
          <summary><span class="orb"></span><span class="reasoning-label">Raciocinando…</span><span class="reasoning-preview"></span></summary>
          <div class="reasoning-body"></div>
        </details>
        <div class="answer"></div>
        <div class="msg-footer"></div>
      </div>
    </div>`);
  const msg = messagesEl.lastElementChild;
  return {
    answer: $(".answer", msg), footer: $(".msg-footer", msg), reasoning: $(".reasoning", msg),
    reasoningBody: $(".reasoning-body", msg), reasoningLabel: $(".reasoning-label", msg), reasoningPreview: $(".reasoning-preview", msg),
  };
}

// Raciocínio recolhido: ao vivo mostra só a última frase; quando a resposta começa, vira "Raciocinou por Xs"
function renderReasoning(ui, entry, { live }) {
  if (!entry.thinking) return;
  ui.reasoning.hidden = false;
  ui.reasoning.classList.toggle("is-live", live);
  ui.reasoningBody.innerHTML = DOMPurify.sanitize(marked.parse(entry.thinking));
  if (live) {
    const sentences = entry.thinking.replace(/[*_#`]/g, "").trim().split(/(?<=[.!?:])\s+/);
    ui.reasoningLabel.textContent = "Raciocinando…";
    ui.reasoningPreview.textContent = sentences.at(-1).length > 12 ? sentences.at(-1) : sentences.at(-2) || "";
  } else {
    ui.reasoningPreview.textContent = "";
    ui.reasoningLabel.textContent = entry.thinkingSeconds ? `Raciocinou por ${entry.thinkingSeconds}s` : "Raciocínio";
  }
}

function renderFooter(footer, entry) {
  const usage = entry.usage;
  footer.innerHTML = `
    <button class="tool" data-copy>${ICON.copy}<span>Copiar</span></button>
    ${entry.stopped ? '<span class="tag-stopped">Resposta interrompida</span>' : ""}
    ${usage ? `<span class="usage" title="Tokens desta resposta">
      ${usage.cache_read_input_tokens ? `<span class="bolt">⚡ ${compact(usage.cache_read_input_tokens)}</span> do cache ·` : ""}
      ${compact(usage.output_tokens)} gerados · ${usage.model}</span>` : ""}`;
  $("[data-copy]", footer).addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    try {
      await navigator.clipboard.writeText(entry.text);
      btn.innerHTML = `${ICON.check}<span>Copiado</span>`;
      setTimeout(() => (btn.innerHTML = `${ICON.copy}<span>Copiar</span>`), 1600);
    } catch { toast("Não foi possível copiar"); }
  });
}

function startThinking(answer) {
  answer.innerHTML = `<div class="thinking"><span class="orb"></span><span class="status">${THINKING_STEPS[0]}</span></div>`;
  let step = 0;
  return setInterval(() => {
    const status = $(".status", answer);
    if (!status) return;
    step = Math.min(step + 1, THINKING_STEPS.length - 1);
    status.outerHTML = `<span class="status">${THINKING_STEPS[step]}</span>`;
  }, 2200);
}

function setBusy(busy) {
  state.busy = busy;
  composer.classList.toggle("is-busy", busy);
  $("#send").setAttribute("aria-label", busy ? "Parar resposta" : "Enviar");
  updateSendState();
}
function updateSendState() { $("#send").disabled = !state.busy && !input.value.trim(); }
const persist = () => storage.set(STORE_KEY, { history: state.history });
const MAX_HISTORY = 30; // igual ao limite da API

// O servidor não guarda conversas: cada pergunta leva as últimas trocas completas
function historyPayload() {
  return state.history.slice(-MAX_HISTORY).map(({ role, text, disciplinas }) =>
    role === "user" ? { role, text, disciplinas: disciplinas || [] } : { role, text: text.slice(0, 20000) });
}

function stopAnswer() {
  if (!state.busy) return;
  // Avisa o servidor explicitamente: abortar o fetch nem sempre derruba a conexão (proxies, keep-alive)
  if (state.requestId) fetch(`/chat/cancel/${state.requestId}`, { method: "POST" }).catch(() => {});
  state.controller?.abort();
}

function errorMessage(status, body) {
  if (Array.isArray(body?.detail)) return "Pergunta inválida (texto ou histórico grande demais).";
  if (body?.detail) return body.detail;
  if (status >= 502) return "O servidor está iniciando. Tente de novo em alguns segundos.";
  return `Erro ${status}`;
}

async function streamAnswer(question, disciplinas, ui) {
  state.controller = new AbortController();
  state.requestId = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const response = await fetchWithWake("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, disciplinas, history: historyPayload(), request_id: state.requestId }),
    signal: state.controller.signal,
  });
  if (!response.ok) {
    const error = new Error(errorMessage(response.status, await response.json().catch(() => null)));
    error.status = response.status;
    throw error;
  }

  const entry = { role: "assistant", text: "", thinking: "" };
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const startedAt = performance.now();
  let buffer = "", frame = 0, thinkingTimer = ui.thinkingTimer;
  const stopIndicator = () => {
    if (!thinkingTimer) return;
    clearInterval(thinkingTimer);
    thinkingTimer = null;
    ui.answer.innerHTML = "";
  };
  const paint = () => {
    frame = 0;
    if (entry.text) renderMarkdown(ui.answer, entry.text, { streaming: true });
    else renderReasoning(ui, entry, { live: true });
    scrollToBottom();
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "thinking") {
          stopIndicator();
          entry.thinking += event.text;
          frame ||= requestAnimationFrame(paint);
        } else if (event.type === "text") {
          stopIndicator();
          if (!entry.text && entry.thinking) {
            entry.thinkingSeconds = Math.max(1, Math.round((performance.now() - startedAt) / 1000));
            renderReasoning(ui, entry, { live: false });
            ui.reasoning.open = false;
          }
          entry.text += event.text;
          frame ||= requestAnimationFrame(paint);
        } else if (event.type === "done") {
          entry.usage = event.usage;
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      }
    }
  } catch (error) {
    if (error.name === "AbortError") entry.stopped = true;
    else { error.partial = entry; throw error; }
  } finally {
    clearInterval(thinkingTimer);
    cancelAnimationFrame(frame);
  }
  return entry;
}

async function ask(question) {
  question = question.trim();
  if (!question || state.busy) return;
  const disciplinas = [...state.context];
  state.context = [];
  renderContext();
  closePicker();
  input.value = "";
  autosize();

  addUserMessage(question, disciplinas);
  const ui = addBotMessage();
  ui.thinkingTimer = startThinking(ui.answer);
  scrollToBottom(true);
  setBusy(true);

  try {
    const entry = await streamAnswer(question, disciplinas, ui);
    renderMarkdown(ui.answer, entry.text || (entry.stopped ? "" : "_Sem resposta._"));
    renderReasoning(ui, entry, { live: false });
    renderFooter(ui.footer, entry);
    if (!entry.stopped && entry.text) { // a API rejeita mensagens vazias no histórico
      state.history.push({ role: "user", text: question, disciplinas }, entry);
      persist();
    }
  } catch (error) {
    clearInterval(ui.thinkingTimer);
    const partial = error.partial?.text ? DOMPurify.sanitize(marked.parse(error.partial.text)) : "";
    ui.answer.innerHTML = `${partial}<div class="error-box">${
      error.status === 429 ? escapeHtml(error.message) : `Não consegui responder: ${escapeHtml(error.message)}`}</div>`;
  } finally {
    state.controller = null;
    state.requestId = null;
    setBusy(false);
    scrollToBottom();
    if (matchMedia("(pointer: fine)").matches) input.focus();
  }
}

function restoreConversation() {
  const saved = storage.get(STORE_KEY);
  if (!saved?.history?.length) return false;
  state.history = saved.history;
  messagesEl.innerHTML = "";
  for (const entry of state.history) {
    if (entry.role === "user") addUserMessage(entry.text, entry.disciplinas || []);
    else {
      const ui = addBotMessage();
      renderMarkdown(ui.answer, entry.text);
      renderReasoning(ui, entry, { live: false });
      renderFooter(ui.footer, entry);
    }
  }
  scrollToBottom(true);
  return true;
}

$("#new-chat").addEventListener("click", () => {
  stopAnswer();
  state.history = [];
  state.context = [];
  storage.remove(STORE_KEY);
  renderContext();
  renderEmpty("Nova conversa");
  input.focus();
});

/* Composer */
function autosize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  input.style.overflowY = input.scrollHeight > 180 ? "auto" : "hidden";
  updateSendState();
}
input.addEventListener("input", () => { autosize(); syncPicker(); });
input.addEventListener("click", syncPicker);
input.addEventListener("keydown", (event) => {
  if (picker.open && picker.items.length) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      picker.active = (picker.active + delta + picker.items.length) % picker.items.length;
      renderPicker();
      return;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      choosePicker(picker.items[picker.active]);
      return;
    }
  }
  if (picker.open && event.key === "Escape") { event.preventDefault(); closePicker(); return; }
  if (event.key === "Backspace" && !input.value && state.context.length) {
    toggleContext(state.context.at(-1), { force: false }); // apaga o último chip, como em campos de tags
    return;
  }
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!state.busy) ask(input.value);
  }
});
composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.busy) stopAnswer();
  else ask(input.value);
});

/* ───────────── Início ───────────── */
marked.use({ gfm: true, breaks: false });
updateSendState();
loadCurriculum()
  .then(() => { if (!restoreConversation()) renderEmpty(); })
  .catch((error) => toast(error.message));
