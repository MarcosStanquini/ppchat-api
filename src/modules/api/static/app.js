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
  aluno: null, // dados importados do SUAP: {matricula, coletado_em, status: {codigo: situação}, contexto}
  settings: { grades: false, progress: true, showDenied: false }, // preferências de exibição (salvas no navegador)
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

  $("#course-name").textContent = "Engenharia de Software · IFSP São Carlos";
  $("#stats").innerHTML = [
    [data.disciplinas.length, "disciplinas"],
    [data.duracao_semestres, "semestres"],
    [hours(data.carga_horaria_total_curso), "no total"],
  ].map(([value, label]) => `<span class="stat"><b>${value}</b>${label}</span>`).join("");

  renderGrid();
  renderRules();
}

/* ───────────── Estado vazio ───────────── */
function renderEmpty(eyebrow = "PPC · IFSP Câmpus São Carlos") {
  const { disciplinas, gargalos } = state.curriculum;
  const deepest = [...disciplinas].sort((a, b) => b.profundidade - a.profundidade || b.indice_complexidade - a.indice_complexidade)
    .find((d) => d.tipo === "obrigatoria" && !/extens/i.test(d.nome)) || disciplinas[0];
  const gate = disc(gargalos[1] || gargalos[0]);
  const pair = [gargalos[2], "SCLBDD1"].filter((c) => disc(c));
  const items = state.aluno ? [
    // Com o SUAP importado, as sugestões falam do percurso do próprio aluno
    { icon: ICON.route, tag: "Meu percurso", text: "Quais disciplinas eu já posso cursar no próximo semestre?" },
    { icon: ICON.rules, tag: "Meu percurso", text: "Quanto falta para eu me formar, incluindo as atividades complementares?" },
    { icon: ICON.gauge, tag: "Dificuldade", text: "Das disciplinas que ainda faltam, quais devem ser as mais difíceis para mim?" },
    { icon: ICON.chain, tag: "Planejamento", text: "Monte um plano semestre a semestre para eu me formar no menor tempo." },
  ] : [
    { icon: ICON.chain, tag: "Dependências", text: `Quais são todos os pré-requisitos de ${titleCase(deepest.nome)}?` },
    { icon: ICON.route, tag: "Com disciplinas no contexto", text: "Em que ordem devo cursar estas disciplinas e por quê?", context: pair },
    { icon: ICON.gauge, tag: "Dificuldade", text: "Quais são as disciplinas mais difíceis do curso e por quê?" },
    { icon: ICON.rules, tag: "Planejamento", text: `Reprovei em ${titleCase(gate.nome)}. Como fica o resto do meu curso?` },
  ];
  $("#messages").innerHTML = `
    <div class="empty" id="empty">
      <p class="eyebrow">${eyebrow}</p>
      <h1>Pergunte qualquer coisa sobre <em>Engenharia de Software no IFSP.</em></h1>
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
  $("#view-me").classList.toggle("is-visible", view === "me");
  $(".drawer-actions").hidden = view === "me"; // busca e regras são da árvore e da grade
  if (view === "me") renderMe();
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
const TREE_COURSE = { nodeW: 178, focusW: 178, gapX: 30, gapY: 8, padX: 20, padTop: 46, padBottom: 50 };
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

// Curso inteiro: uma coluna por semestre; optativas sem semestre fixo (LIBRAS) ficam só na Grade
function buildCourseGraph() {
  const { disciplinas, duracao_semestres } = state.curriculum;
  const level = new Map(disciplinas.filter((d) => d.semestre).map((d) => [d.codigo, d.semestre]));
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

// compact: no curso inteiro a coluna já diz o semestre, então o card mostra só a carga horária
function nodeHtml(code, { side = "", focus = false, direct = false, compact = false }) {
  const d = disc(code);
  const blocks = d.libera_transitivamente.length;
  const inCtx = state.context.includes(code);
  const solo = !isConnected(d); // sem pré-requisitos nem dependentes: borda tracejada
  const st = state.settings.progress ? studentStatus(code) : null; // com o SUAP importado: feita, cursando, liberada...
  const badge = inCtx ? '<span class="ctx-badge">no chat</span>'
    : st ? `<span class="st-badge st-${st}">${STATUS_LABEL[st]}</span>`
    : `<i class="dot ${levelClass(d.nivel_estimado)}"></i>`;
  return `
    <button class="node ${side} ${focus ? "is-focus" : ""} ${direct ? "direct" : ""} ${inCtx ? "in-context" : ""} ${solo ? "is-solo" : ""} ${st ? `st-${st}` : ""}"
        data-code="${code}" title="${focus ? "" : "Centralizar a árvore nesta disciplina"}">
      <span class="node-top"><span class="node-code">${code}</span>${badge}</span>
      <span class="node-name">${escapeHtml(titleCase(d.nome))}</span>
      <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
      <span class="node-meta"><span>${compact ? "" : `${semesterLabel(d)} · `}${hours(d.carga_horaria_total)}</span>
        ${gradeTag(code) || (blocks >= 3 && side !== "anc" ? `<span>trava ${blocks}</span>` : "")}</span>
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
  // Redesenha já na largura nova, sem esperar o ResizeObserver (que só roda quando a página pinta)
  if (state.view === "tree" && $(".node", $("#tree-inner"))) renderTree({ animate: false });
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
  if (!state.focus && canvas.clientWidth >= 640) {
    // Curso inteiro: as colunas dividem a largura disponível, sem rolagem lateral em telas comuns
    const reserved = $("#view-tree").classList.contains("info-hidden") ? 40 : 0; // aba "Painel" na borda
    const available = canvas.clientWidth - 2 * TREE.padX - reserved - (levels.length - 1) * TREE.gapX;
    const nodeW = Math.max(124, Math.min(210, Math.floor(available / levels.length)));
    TREE = { ...TREE, nodeW, focusW: nodeW };
  }
  const widthOf = (l) => (graph.focus && l === 0 ? TREE.focusW : TREE.nodeW);
  const inner = $("#tree-inner");
  inner.classList.toggle("no-anim", !animate);
  inner.classList.toggle("is-course", !state.focus);
  inner.classList.remove("is-hovering");

  // O SVG vem primeiro para as setas ficarem atrás dos cards
  inner.innerHTML = `<svg class="tree-edges" id="tree-edges"></svg>` + levels.map((l) => {
    const [label, cls] = graph.label(l);
    return `<span class="col-label ${cls}" data-level="${l}">${label}</span>` +
      columns.get(l).map((c) => nodeHtml(c, { side: graph.side(l), focus: c === graph.focus, direct: graph.directs?.has(c), compact: !graph.focus })).join("");
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
  const isolated = disciplinas.filter((d) => d.semestre && !isConnected(d));
  const optional = disciplinas.filter((d) => !d.semestre);
  $("#tree-info").innerHTML = `${INFO_CLOSE}
    <span class="info-code">VISÃO GERAL</span>
    <h3>Curso inteiro</h3>
    <div class="pills">
      <span class="pill">${duracao_semestres} semestres</span>
      <span class="pill">${disciplinas.length} disciplinas</span>
      <span class="pill">${hours(state.curriculum.carga_horaria_total_curso)}</span>
    </div>
    ${state.aluno ? progressHtml() : ""}
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
      ${optional.length ? `<p class="small-note">Optativas sem semestre fixo (${optional.map((d) => escapeHtml(nameOf(d.codigo))).join(", ")}) ficam na Grade.</p>` : ""}
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
    ${studentStatus(code) ? `<p class="st-line st-${studentStatus(code)}">${STATUS_TEXT[studentStatus(code)]}</p>` : ""}
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
        const st = state.settings.progress ? studentStatus(d.codigo) : null;
        return `<button class="card ${st ? `st-${st}` : ""}" data-code="${d.codigo}">
          <span class="card-top"><span class="card-code">${d.codigo}</span>
            ${st ? `<span class="st-badge st-${st}">${STATUS_LABEL[st]}</span>` : `<i class="dot ${levelClass(d.nivel_estimado)}"></i>`}</span>
          <span class="card-name">${escapeHtml(titleCase(d.nome))}</span>
          <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
          <span class="card-meta"><span>${hours(d.carga_horaria_total)}</span>
            ${gradeTag(d.codigo) || (blocks >= 4 ? `<span class="badge-gate">trava ${blocks}</span>` : "")}</span>
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
    body: JSON.stringify({
      question, disciplinas, history: historyPayload(), request_id: state.requestId,
      perfil: state.aluno?.contexto || null, // dados do SUAP, guardados só neste navegador
    }),
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

/* ───────────── Dados do SUAP (bookmarklet) ───────────── */
// O bookmarklet roda dentro do SUAP com a sessão do próprio aluno, envia as tabelas acadêmicas ao
// servidor e abre o PPChat com #suap=<código de uso único>. Aqui o código vira dados, que ficam só
// neste navegador (localStorage) e seguem, resumidos, junto de cada pergunta.
const ALUNO_KEY = "ppchat-aluno-v1";
const PERFIL_MAX = 28_000; // a API aceita até 30 mil caracteres
const STATUS_LABEL = { concluida: "✓ feita", cursando: "cursando", reprovada: "reprovou", liberada: "liberada" };
const STATUS_TEXT = {
  concluida: "Você já concluiu esta disciplina.",
  cursando: "Você está cursando esta disciplina agora.",
  reprovada: "Você reprovou e ainda não concluiu esta disciplina.",
  liberada: "Pré-requisitos cumpridos: você já pode cursar.",
};
const SITUACOES = [
  [/aprovad|dispensad|aproveit|cumprid|conclu[ií]d/i, "concluida"], // SUAP: "Aproveit. Disciplina"
  [/cursando|matriculad|em curso/i, "cursando"],
  [/reprovad/i, "reprovada"],
];
const RANK = { concluida: 3, cursando: 2, reprovada: 1 };
const CONTEXT_TABS = /dados acad|requisitos|complementares|extens|boletins?/i;

// Situação de uma disciplina para o aluno; "liberada" = todos os pré-requisitos já concluídos
function studentStatus(code) {
  if (!state.aluno) return null;
  const st = state.aluno.status[code];
  if (st) return st;
  const d = disc(code);
  return d && d.pre_requisitos.every((p) => state.aluno.status[p] === "concluida") ? "liberada" : null;
}

// Nomes do currículo do mais longo ao mais curto, para "Banco de Dados 1" não casar dentro de outro nome
let namesByLength = null;
function codesInRow(text) {
  const codes = [...new Set(text.match(/\bSCL[A-Z0-9]{4,5}\b/g) || [])].filter(disc);
  if (codes.length) return codes;
  namesByLength ||= state.curriculum.disciplinas.map((d) => [normalize(d.nome), d.codigo]).sort((a, b) => b[0].length - a[0].length);
  const norm = normalize(text);
  const hit = namesByLength.find(([name]) => norm.includes(name));
  return hit ? [hit[1]] : [];
}

const parseHours = (s) => {
  const m = (s || "").replace(/\./g, "").replace(",", ".").match(/\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : null;
};

// "C.H. Prevista:" | "640,00 hora(s)" → 640 (rótulo e valor na mesma célula ou na seguinte)
function findHours(tables, label) {
  for (const t of tables) for (const row of t.linhas) {
    for (let i = 0; i < row.length; i++) {
      if (!label.test(row[i])) continue;
      const inline = parseHours(row[i].replace(label, ""));
      return inline ?? parseHours(row[i + 1]);
    }
  }
  return null;
}

const mdTable = (t, maxRows = 40) =>
  (t.titulo ? `**${t.titulo}**\n` : "") + t.linhas.slice(0, maxRows).map((r) => `| ${r.join(" | ")} |`).join("\n");

// Lê uma tabela pelo cabeçalho (1ª linha). Desde a versão 2 do bookmarklet as colunas mescladas vêm
// repetidas, então o índice do cabeçalho bate com o das células
function records(t) {
  const [head = [], ...rows] = t.linhas;
  const keys = head.map(normalize);
  return { rows, col: (re) => keys.findIndex((k) => re.test(k)) };
}
const tablesOf = (data, re) => data.abas.filter((a) => re.test(a.titulo)).flatMap((a) => a.tabelas);
const hasDigit = (s) => /\d/.test(s || "");

// "I.R.A." | "8,20" → "8,20" (rótulo numa célula, valor na seguinte)
function findValue(tables, label) {
  for (const t of tables) for (const row of t.linhas) {
    const i = row.findIndex((cell) => label.test(cell));
    if (i >= 0 && row[i + 1]) return row[i + 1];
  }
  return null;
}

// Nota final, frequência e período de cada disciplina (Histórico + Boletim do período atual)
function readGrades(data) {
  const notas = {};
  for (const t of tablesOf(data, /hist[oó]rico|boletins?/i)) {
    const r = records(t);
    const iSit = r.col(/situa/);
    if (iSit < 0) continue;
    const iNota = [/^mfd/, /^nota/, /^media$/].map((re) => r.col(re)).find((i) => i >= 0) ?? -1;
    const iFreq = r.col(/freq/);
    const iPer = r.col(/^ano letivo|^ano\/periodo/);
    for (const row of r.rows) {
      const codes = codesInRow(row.join(" | "));
      if (!codes.length) continue;
      const status = SITUACOES.find(([re]) => re.test(row[iSit]))?.[1] || null;
      const entry = {
        situacao: row[iSit] || null,
        status,
        nota: iNota >= 0 && hasDigit(row[iNota]) ? row[iNota] : null,
        freq: iFreq >= 0 && hasDigit(row[iFreq]) ? row[iFreq] : null,
        periodo: iPer >= 0 && hasDigit(row[iPer]) ? row[iPer] : null,
      };
      for (const code of codes) {
        const prev = notas[code];
        // Fica a linha de situação mais avançada (ex.: aprovado depois de uma reprovação), sem perder dados
        if (prev && (RANK[status] || 0) < (RANK[prev.status] || 0)) continue;
        notas[code] = { ...prev, ...Object.fromEntries(Object.entries(entry).filter(([, v]) => v != null)) };
      }
    }
  }
  return notas;
}

function readComplementares(data) {
  const tables = tablesOf(data, /complementares/i);
  const acc = {
    prevista: findHours(tables, /C\.?\s*H\.?\s*Prevista:?/i),
    cumprida: findHours(tables, /C\.?\s*H\.?\s*Cumprida:?/i),
    cadastrada: findHours(tables, /C\.?\s*H\.?\s*Cadastrada:?/i),
    tipos: [],
    lancamentos: [],
  };
  for (const t of tables) {
    const r = records(t);
    const iTipo = r.col(/^tipo$/), iMax = r.col(/max\.? curso/), iCad = r.col(/cadastrada/), iCont = r.col(/contabilizada/);
    if (iTipo >= 0 && iCont >= 0) {
      acc.tipos = r.rows.filter((row) => row[iTipo]).map((row) => ({
        tipo: row[iTipo], max: parseHours(row[iMax]), cadastrada: parseHours(row[iCad]), contabilizada: parseHours(row[iCont]) ?? 0,
      }));
    }
    const iAtv = r.col(/atividade/), iDef = r.col(/deferida/);
    if (iAtv >= 0 && iDef >= 0) {
      const iPer = r.col(/ano\/periodo/), iTipoCh = r.col(/tipo\/carga/), iRaz = r.col(/razao/);
      acc.lancamentos = r.rows.filter((row) => row[iAtv]).map((row) => ({
        periodo: row[iPer] || "", tipo: row[iTipoCh] || "", atividade: row[iAtv], deferida: row[iDef] || "", razao: row[iRaz] && row[iRaz] !== "-" ? row[iRaz] : "",
      }));
    }
  }
  return acc;
}

function readRequisitos(data) {
  for (const t of tablesOf(data, /requisitos/i)) {
    const r = records(t);
    const iNome = r.col(/requisito/), iSit = r.col(/situa/), iPrev = r.col(/prevista/), iCump = r.col(/cumprid/), iPend = r.col(/pendente/);
    if (iNome < 0 || iPrev < 0) continue;
    return r.rows.filter((row) => row[iNome]).map((row) => ({
      nome: row[iNome], situacao: row[iSit] || "", prevista: parseHours(row[iPrev]), cumprida: parseHours(row[iCump]), pendente: parseHours(row[iPend]),
    }));
  }
  return [];
}

function readExtensao(data) {
  for (const t of tablesOf(data, /extens/i)) {
    const r = records(t);
    const iPrev = r.col(/prevista/), iCump = r.col(/cumprida/);
    if (iPrev < 0) continue;
    return r.rows.map((row) => ({ prevista: parseHours(row[iPrev]), cumprida: parseHours(row[iCump]) }))
      .filter((x) => x.prevista != null)
      .reduce((sum, x) => ({ prevista: sum.prevista + x.prevista, cumprida: sum.cumprida + (x.cumprida || 0) }), { prevista: 0, cumprida: 0 });
  }
  return null;
}

function buildAluno(data) {
  const status = {};
  for (const aba of data.abas) for (const t of aba.tabelas) for (const row of t.linhas) {
    const text = row.join(" | ");
    const situacao = SITUACOES.find(([re]) => re.test(text))?.[1];
    if (!situacao) continue;
    for (const code of codesInRow(text)) {
      if (!status[code] || RANK[situacao] > RANK[status[code]]) status[code] = situacao;
    }
  }
  const aluno = {
    versao: data.versao || 1,
    matricula: data.matricula,
    coletado_em: data.coletado_em,
    status,
    // Notas e tabelas lidas pelo cabeçalho só são confiáveis com as colunas mescladas expandidas (versão 2)
    notas: data.versao >= 2 ? readGrades(data) : {},
    acc: readComplementares(data),
    requisitos: data.versao >= 2 ? readRequisitos(data) : [],
    extensao: data.versao >= 2 ? readExtensao(data) : null,
    ira: findValue(tablesOf(data, /dados acad/i), /^I\.?\s?R\.?\s?A\.?$/i),
    diag: data.abas.map((a) => ({ titulo: a.titulo, tabelas: a.tabelas.length, linhas: a.tabelas.reduce((n, t) => n + t.linhas.length, 0) })),
  };
  // Tabelas que ajudam a responder (requisitos, horas, boletim atual), como markdown
  aluno.tabelas = data.abas.filter((a) => CONTEXT_TABS.test(a.titulo))
    .map((a) => `### ${a.titulo}\n` + a.tabelas.map((t) => mdTable(t)).join("\n\n")).join("\n\n");
  return aluno;
}

// Resumo que vai junto das perguntas (o modelo recebe as listas já calculadas com o grafo)
function alunoContext(aluno) {
  const all = state.curriculum.disciplinas.filter((d) => d.semestre);
  const by = (st) => all.filter((d) => aluno.status[d.codigo] === st);
  const names = (list) => list.map((d) => {
    const n = aluno.notas?.[d.codigo];
    return `${titleCase(d.nome)} (${d.codigo}${n?.nota ? `, nota ${n.nota}` : ""}${n?.periodo ? `, ${n.periodo}` : ""})`;
  }).join("; ") || "nenhuma";
  const done = (c) => aluno.status[c] === "concluida";
  const pending = all.filter((d) => !["concluida", "cursando"].includes(aluno.status[d.codigo]));
  const free = pending.filter((d) => d.pre_requisitos.every(done));
  const afterNow = pending.filter((d) => !d.pre_requisitos.every(done) &&
    d.pre_requisitos.every((p) => done(p) || aluno.status[p] === "cursando"));
  const lines = [
    `Matrícula ${aluno.matricula} · dados do SUAP de ${new Date(aluno.coletado_em).toLocaleDateString("pt-BR")}`,
    `Concluídas (${by("concluida").length} de ${all.length}): ${names(by("concluida"))}`,
    `Cursando agora: ${names(by("cursando"))}`,
    `Reprovadas e ainda não concluídas: ${names(by("reprovada"))}`,
    `Liberadas para cursar já (todos os pré-requisitos concluídos): ${names(free)}`,
    `Liberadas se for aprovado no semestre atual: ${names(afterNow)}`,
    `Ainda não liberadas: ${names(pending.filter((d) => !free.includes(d) && !afterNow.includes(d)))}`,
    aluno.ira ? `I.R.A. (índice de rendimento acadêmico): ${aluno.ira}` : "",
    aluno.acc.prevista ? `Atividades complementares: ${aluno.acc.cumprida ?? "?"} h cumpridas de ${aluno.acc.prevista} h exigidas.` : "",
    aluno.acc.tipos?.length ? `Horas por tipo de atividade complementar (contabilizada/máximo no curso): ${aluno.acc.tipos.map((t) => `${t.tipo}: ${t.contabilizada}/${t.max ?? "?"} h`).join("; ")}` : "",
    aluno.extensao ? `Carga horária de extensão curricular (disciplinas Atividades de Extensão 1 a 4; não são atividades complementares): ${aluno.extensao.cumprida} h de ${aluno.extensao.prevista} h.` : "",
    "",
    "Tabelas copiadas do SUAP:",
    aluno.tabelas,
  ];
  return lines.filter((l) => l !== "").join("\n").slice(0, PERFIL_MAX);
}

function setAluno(aluno) {
  state.aluno = aluno;
  if (aluno) aluno.contexto = alunoContext(aluno);
  aluno ? storage.set(ALUNO_KEY, aluno) : storage.remove(ALUNO_KEY);
  const label = $("#suap-btn-label");
  label.textContent = aluno ? "SUAP conectado" : "Conectar SUAP";
  $("#suap-btn").classList.toggle("is-connected", !!aluno);
  if ($(".node", $("#tree-inner"))) { renderTree({ animate: false }); renderInfo(state.focus); }
  if ($("#empty")) renderEmpty();
  renderGrid();
  renderSettings();
  if (state.view === "me") renderMe();
}

function progressHtml() {
  const all = state.curriculum.disciplinas.filter((d) => d.semestre);
  const count = (st) => all.filter((d) => studentStatus(d.codigo) === st).length;
  const done = count("concluida");
  const { prevista, cumprida } = state.aluno.acc;
  const free = all.filter((d) => studentStatus(d.codigo) === "liberada").map((d) => d.codigo);
  return `
    <div class="info-section progress">
      <h4>Seu progresso · SUAP</h4>
      <div class="progress-row"><span><b>${done}</b> de ${all.length} disciplinas</span><span>${Math.round((done / all.length) * 100)}%</span></div>
      <div class="meter big"><i class="lvl-introdutoria" style="width:${(done / all.length) * 100}%"></i></div>
      <div class="progress-pills">
        <span class="st-badge st-cursando">${count("cursando")} cursando</span>
        <span class="st-badge st-liberada">${free.length} liberadas</span>
        ${count("reprovada") ? `<span class="st-badge st-reprovada">${count("reprovada")} a refazer</span>` : ""}
      </div>
      ${prevista ? `<div class="progress-row" style="margin-top:12px"><span>Atividades complementares</span><span>${cumprida ?? "?"} / ${prevista} h</span></div>
        <div class="meter big"><i class="lvl-intermediaria" style="width:${Math.min(100, ((cumprida || 0) / prevista) * 100)}%"></i></div>` : ""}
      ${free.length ? `<h4 style="margin-top:14px">Já pode cursar</h4>${goChips(free)}` : ""}
    </div>`;
}

/* Engrenagem: configurações de exibição da árvore e da grade */
const SETTINGS_KEY = "ppchat-tree-settings";
Object.assign(state.settings, storage.get(SETTINGS_KEY) || {});

// Engrenagem do cabeçalho: cada opção é um interruptor ligado a uma chave de state.settings
const SETTING_INPUTS = { grades: "#opt-grades", progress: "#opt-progress", showDenied: "#opt-denied" };

function renderSettings() {
  const connected = !!state.aluno;
  for (const [key, sel] of Object.entries(SETTING_INPUTS)) {
    $(sel).checked = !!state.settings[key];
    $(sel).disabled = !connected;
  }
  $("#settings-note").hidden = connected;
}
function setSetting(key, value) {
  state.settings[key] = value;
  storage.set(SETTINGS_KEY, state.settings);
  if ($(".node", $("#tree-inner"))) renderTree({ animate: false });
  renderGrid();
  if (state.view === "me") renderMe();
}
$("#tree-settings-btn").addEventListener("click", (event) => {
  event.stopPropagation();
  const pop = $("#tree-settings");
  pop.hidden = !pop.hidden;
  event.currentTarget.setAttribute("aria-expanded", !pop.hidden);
  renderSettings();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".settings")) $("#tree-settings").hidden = true;
});
for (const [key, sel] of Object.entries(SETTING_INPUTS)) {
  $(sel).addEventListener("change", (event) => setSetting(key, event.target.checked));
}

const gradeValue = (nota) => Number(String(nota).replace(",", "."));
const gradeClass = (nota) => {
  const v = gradeValue(nota);
  return Number.isNaN(v) ? "g-mid" : v >= 8 ? "g-high" : v >= 6 ? "g-mid" : "g-low";
};
// Nota final no card (só com a opção ligada e a disciplina já feita)
function gradeTag(code) {
  if (!state.settings.grades || !state.aluno) return "";
  const n = state.aluno.notas?.[code];
  if (!n?.nota || state.aluno.status[code] !== "concluida") return "";
  return `<span class="grade ${gradeClass(n.nota)}" title="Nota final">${escapeHtml(n.nota)}</span>`;
}

/* ───────────── Aba "Meu percurso" ───────────── */
function ring(pct) {
  const r = 52, c = 2 * Math.PI * r;
  return `<svg class="ring" viewBox="0 0 120 120" aria-hidden="true">
    <circle cx="60" cy="60" r="${r}" class="ring-bg"/>
    <circle cx="60" cy="60" r="${r}" class="ring-fg" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct)}"/>
    <text x="60" y="58" class="ring-pct">${Math.round(pct * 100)}%</text><text x="60" y="78" class="ring-sub">do curso</text></svg>`;
}

const bar = (value, max, cls = "") =>
  `<div class="me-bar ${cls}"><i style="width:${max ? Math.min(100, (value / max) * 100) : 0}%"></i></div>`;
const fmtH = (h) => (h == null ? "?" : `${Number(h).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`);

function renderMe() {
  const box = $("#me");
  const a = state.aluno;
  if (!a) {
    box.innerHTML = `
      <div class="me-empty">
        <p class="eyebrow">Meu percurso</p>
        <h3>Veja seu curso do seu jeito</h3>
        <p class="muted">Conecte o SUAP para ver suas notas, o que falta para se formar e sugestões para completar as atividades complementares.</p>
        <button class="btn btn-primary" data-me="connect">Conectar SUAP</button>
      </div>`;
    return;
  }
  const all = state.curriculum.disciplinas.filter((d) => d.semestre);
  const statusOf = (c) => studentStatus(c);
  const done = all.filter((d) => statusOf(d.codigo) === "concluida");
  const doing = all.filter((d) => statusOf(d.codigo) === "cursando");
  const free = all.filter((d) => statusOf(d.codigo) === "liberada");
  const blocked = all.filter((d) => !statusOf(d.codigo) || statusOf(d.codigo) === "reprovada");
  const graded = done.map((d) => gradeValue(a.notas?.[d.codigo]?.nota)).filter((v) => !Number.isNaN(v));
  const media = graded.length ? (graded.reduce((s, v) => s + v, 0) / graded.length).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) : null;
  const acc = a.acc || {};
  const accLeft = acc.prevista != null ? Math.max(0, acc.prevista - (acc.cumprida || 0)) : null;

  // Linha do tempo: disciplinas agrupadas pelo semestre letivo em que foram cursadas
  const periods = new Map();
  for (const d of [...done, ...doing]) {
    const n = a.notas?.[d.codigo] || {};
    const key = statusOf(d.codigo) === "cursando" ? "Agora" : n.periodo || "Sem período";
    if (!periods.has(key)) periods.set(key, []);
    periods.get(key).push(d);
  }
  const order = [...periods.keys()].sort((x, y) => (x === "Agora") - (y === "Agora") || x.localeCompare(y));
  const course = (d) => {
    const n = a.notas?.[d.codigo] || {};
    const st = statusOf(d.codigo);
    return `<button class="me-course st-${st}" data-goto="${d.codigo}" title="Ver na árvore">
      <span class="me-course-main"><b>${escapeHtml(titleCase(d.nome))}</b><small>${d.codigo}${n.freq ? ` · ${escapeHtml(n.freq)} freq.` : ""}</small></span>
      ${st === "cursando" ? '<span class="st-badge st-cursando">cursando</span>'
        : n.nota ? `<span class="grade big ${gradeClass(n.nota)}">${escapeHtml(n.nota)}</span>`
        : `<span class="st-badge st-concluida">${/aproveit/i.test(n.situacao || "") ? "aproveitada" : "✓ feita"}</span>`}
    </button>`;
  };

  const tipos = (acc.tipos || []).filter((t) => t.max).map((t) => ({ ...t, folga: Math.max(0, t.max - (t.contabilizada || 0)) }));
  // Indeferidas ficam ocultas por padrão (opção "Mostrar indeferidas")
  const isDenied = (l) => /n[aã]o/i.test(l.deferida);
  const denied = (acc.lancamentos || []).filter(isDenied);
  const shownLogs = (acc.lancamentos || []).filter((l) => state.settings.showDenied || !isDenied(l));
  // O SUAP traz uma linha "TOTAL:" na tabela de requisitos: vira o resumo do card
  const reqs = (a.requisitos || []).filter((r) => !/^total/i.test(r.nome));
  const reqTotal = (a.requisitos || []).find((r) => /^total/i.test(r.nome));

  box.innerHTML = `
    <section class="me-hero">
      ${ring(done.length / all.length)}
      <div class="me-hero-text">
        <p class="eyebrow">Meu percurso · Engenharia de Software · IFSP São Carlos</p>
        <h3>${done.length} de ${all.length} disciplinas concluídas</h3>
        <p class="muted">Matrícula ${escapeHtml(a.matricula)} · dados do SUAP de
          ${new Date(a.coletado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</p>
        <div class="me-actions">
          <button class="btn btn-primary btn-sm" data-me="ask">${ICON.ask}Perguntar sobre meu percurso</button>
          <button class="btn btn-sm" data-me="update">Atualizar do SUAP</button>
        </div>
      </div>
      <div class="me-kpis">
        ${a.ira ? `<div class="kpi"><b>${escapeHtml(a.ira)}</b><span>I.R.A.</span></div>` : ""}
        ${media ? `<div class="kpi"><b>${media}</b><span>média das notas</span></div>` : ""}
        <div class="kpi kpi-anc"><b>${doing.length}</b><span>cursando agora</span></div>
        <div class="kpi kpi-accent"><b>${free.length}</b><span>já liberadas</span></div>
        ${acc.prevista ? `<div class="kpi kpi-desc"><b>${fmtH(acc.cumprida)}</b><span>de ${fmtH(acc.prevista)} complementares</span></div>` : ""}
        ${a.extensao ? `<div class="kpi"><b>${fmtH(a.extensao.cumprida)}</b><span>de ${fmtH(a.extensao.prevista)} de extensão curricular</span></div>` : ""}
      </div>
    </section>

    ${(a.versao || 1) < 2 ? `<div class="me-banner">Clique de novo no favorito <b>PPChat ← SUAP</b> com o SUAP aberto para trazer
      as notas, os requisitos de conclusão e o detalhe das atividades complementares.</div>` : ""}

    <div class="me-grid">
      <div class="me-col">
        ${reqs.length ? `
        <article class="me-card">
          <header><h4>Para se formar</h4><span class="muted">${reqTotal?.prevista ? `${fmtH(reqTotal.cumprida)} de ${fmtH(reqTotal.prevista)} no total` : "requisitos do SUAP"}</span></header>
          ${reqTotal?.prevista ? bar(reqTotal.cumprida || 0, reqTotal.prevista, "ok") : ""}
          <ul class="req-list">${reqs.map((r) => {
            const ok = /cumprid|conclu|ok\b/i.test(r.situacao) && !/n[aã]o|pendente/i.test(r.situacao);
            return `<li class="${ok ? "is-ok" : ""}">
              <div class="req-top"><span class="req-check">${ok ? ICON.check : ""}</span><b>${escapeHtml(r.nome)}</b>
                <span class="req-sit">${escapeHtml(r.situacao || "")}</span></div>
              ${r.prevista ? `${bar(r.cumprida || 0, r.prevista, ok ? "ok" : "")}
                <div class="req-meta"><span>${fmtH(r.cumprida)} de ${fmtH(r.prevista)}</span>${r.pendente ? `<span>faltam ${fmtH(r.pendente)}</span>` : ""}</div>` : ""}
            </li>`;
          }).join("")}</ul>
        </article>` : ""}

        <article class="me-card">
          <header><h4>Minhas disciplinas</h4><span class="muted">${done.length} feitas · ${doing.length} cursando</span></header>
          <div class="timeline">${order.map((key) => {
            const list = periods.get(key);
            const nums = list.map((d) => gradeValue(a.notas?.[d.codigo]?.nota)).filter((v) => !Number.isNaN(v));
            const avg = nums.length ? (nums.reduce((s, v) => s + v, 0) / nums.length).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) : null;
            return `<section class="tl-period ${key === "Agora" ? "is-now" : ""}">
              <div class="tl-head"><span class="tl-dot"></span><b>${key === "Agora" ? "Cursando agora" : escapeHtml(key)}</b>
                ${avg ? `<span class="muted">média ${avg}</span>` : ""}</div>
              <div class="tl-courses">${list.map(course).join("")}</div>
            </section>`;
          }).join("")}</div>
          <div class="me-pending">
            <h5>Já pode cursar (${free.length})</h5>
            ${free.length ? goChips(free.map((d) => d.codigo)) : '<p class="muted small-note">Nada liberado no momento.</p>'}
            <h5>Ainda bloqueadas (${blocked.length})</h5>
            ${blocked.length ? goChips(blocked.map((d) => d.codigo)) : '<p class="muted small-note">Nenhuma.</p>'}
          </div>
        </article>
      </div>

      <div class="me-col">
        ${acc.prevista ? `
        <article class="me-card">
          <header><h4>Atividades complementares</h4><span class="muted">${fmtH(acc.cumprida)} de ${fmtH(acc.prevista)}</span></header>
          <div class="acc-total">
            <div><b>${fmtH(acc.cumprida)}</b><span>contabilizadas</span></div>
            <div><b>${fmtH(accLeft)}</b><span>faltam</span></div>
            ${acc.cadastrada && acc.cumprida != null && acc.cadastrada > acc.cumprida ? `<div><b>${fmtH(acc.cadastrada - acc.cumprida)}</b><span>enviadas sem contar</span></div>` : ""}
          </div>
          ${bar(acc.cumprida || 0, acc.prevista, "acc")}
          ${tipos.length ? `<h5>Por tipo</h5><ul class="acc-types">${tipos.map((t) => `
            <li><div class="acc-type-top"><span>${escapeHtml(t.tipo)}</span><span>${fmtH(t.contabilizada)} / ${fmtH(t.max)}</span></div>
              ${bar(t.contabilizada || 0, t.max, t.folga === 0 ? "full" : "acc")}</li>`).join("")}</ul>` : ""}
          ${shownLogs.length || denied.length ? `<div class="acc-log-head"><h5>Lançamentos</h5>
            ${denied.length && !state.settings.showDenied ? `<span class="muted small-note">${denied.length} indeferida(s) oculta(s) · ⚙ no topo</span>` : ""}</div>
            <ul class="acc-log">${shownLogs.map((l) => `
            <li class="${/n[aã]o/i.test(l.deferida) ? "is-denied" : ""}">
              <div><b>${escapeHtml(l.atividade)}</b><small>${escapeHtml(l.tipo)}${l.periodo ? ` · ${escapeHtml(l.periodo)}` : ""}</small>
                ${l.razao ? `<p class="acc-reason">${escapeHtml(l.razao)}</p>` : ""}</div>
              <span class="st-badge ${/n[aã]o/i.test(l.deferida) ? "st-reprovada" : /sim/i.test(l.deferida) ? "st-concluida" : "st-cursando"}">
                ${/n[aã]o/i.test(l.deferida) ? "indeferida" : /sim/i.test(l.deferida) ? "deferida" : "em análise"}</span>
            </li>`).join("")}</ul>` : ""}
        </article>` : ""}
      </div>
    </div>`;
}

$("#me").addEventListener("click", (event) => {
  const goto = event.target.closest("[data-goto]");
  if (goto) { setView("tree"); return focusTree(goto.dataset.goto, { push: true }); }
  const act = event.target.closest("[data-me]")?.dataset.me;
  if (act === "connect" || act === "update") { renderSuapModal(); suapModal.showModal(); }
  else if (act === "ask") { closeDrawer(); ask("Faça um resumo do meu percurso no curso: o que já fiz, como estou indo e o que devo priorizar agora."); }
});

/* Modal */
const suapModal = $("#suap-modal");
const bookmarkletHref = () =>
  `javascript:(()=>{var s=document.createElement('script');s.src='${location.origin}/static/suap-export.js?v='+Date.now();` +
  `s.dataset.ppchat='${location.origin}';document.body.appendChild(s);})();`;

function suapStepsHtml() {
  return `
    <ol class="steps">
      <li><b>Arraste este botão para a barra de favoritos</b> do navegador
        <a class="bookmarklet" href="${bookmarkletHref()}" title="Arraste para a barra de favoritos">PPChat ← SUAP</a>
        <span class="small-note">Barra escondida? <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>B</kbd>. Ou
        <button class="link" data-act="copy-bookmarklet">copie o código</button> e crie um favorito com ele.</span></li>
      <li>Entre no <a href="https://suap.ifsp.edu.br" target="_blank" rel="noopener">SUAP</a> como sempre. <b>O PPChat nunca vê sua senha.</b></li>
      <li>Com o SUAP aberto, clique no favorito <b>PPChat ← SUAP</b>, confira o que será enviado e clique em <b>Enviar</b>.</li>
    </ol>`;
}

function renderSuapModal() {
  const a = state.aluno;
  $("#suap-title").textContent = a ? "Seus dados do SUAP" : "Conectar ao SUAP";
  if (!a) {
    $("#suap-body").innerHTML = `
      <p>Importe seu histórico do SUAP para o PPChat responder sobre <b>o seu</b> percurso e marcar na árvore o que você já fez.</p>
      ${suapStepsHtml()}
      <p class="small-note">Lemos só as abas acadêmicas: dados acadêmicos, histórico, boletins, requisitos de conclusão e atividades
        complementares. Os dados ficam guardados <b>só neste navegador</b>; o servidor só repassa e apaga assim que o PPChat abre.
        Projeto independente, sem vínculo oficial com o IFSP.</p>`;
    return;
  }
  // Conectado: o progresso fica na aba "Meu percurso"; aqui só atualizar, conferir e remover
  const recognized = Object.keys(a.status).length;
  $("#suap-title").textContent = "Atualizar dados do SUAP";
  $("#suap-body").innerHTML = `
    <p class="small-note" style="margin-top:0">Matrícula <b>${escapeHtml(a.matricula)}</b> · última importação em
      ${new Date(a.coletado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
      · ${Object.values(a.status).filter((s) => s === "concluida").length} disciplinas concluídas</p>
    ${recognized ? "" : `<div class="error-box">Li ${a.diag.reduce((n, d) => n + d.linhas, 0)} linhas, mas não reconheci
      nenhuma disciplina. O formato do SUAP pode ser diferente do esperado; mande um print da aba Histórico para ajustarmos.</div>`}
    ${suapStepsHtml()}
    <details class="diag"><summary>O que foi lido do SUAP</summary>
      <ul class="diag-list">${a.diag.map((d) => `<li><span>${escapeHtml(d.titulo)}</span><span>${d.tabelas} tabelas · ${d.linhas} linhas</span></li>`).join("")}</ul>
    </details>
    <div class="info-actions"><button class="btn" data-act="remove-aluno">Remover meus dados deste navegador</button></div>`;
}

// Conectado: o botão leva ao "Meu percurso"; sem dados, abre as instruções do bookmarklet
$("#suap-btn").addEventListener("click", () => {
  if (state.aluno) return openDrawer("me");
  renderSuapModal();
  suapModal.showModal();
});
suapModal.addEventListener("click", async (event) => {
  if (event.target === suapModal || event.target.closest("[data-close]")) return suapModal.close();
  if (event.target.closest(".bookmarklet")) {
    event.preventDefault(); // aqui no PPChat ele não faz nada: só funciona dentro do SUAP
    return toast("Arraste o botão para a barra de favoritos e clique nele com o SUAP aberto.");
  }
  if (event.target.closest("[data-goto]")) {
    suapModal.close();
    return openDrawer("tree", event.target.closest("[data-goto]").dataset.goto);
  }
  const act = event.target.closest("[data-act]")?.dataset.act;
  if (act === "copy-bookmarklet") {
    try { await navigator.clipboard.writeText(bookmarkletHref()); toast("Código copiado. Cole como endereço de um novo favorito."); }
    catch { toast("Não foi possível copiar."); }
  } else if (act === "remove-aluno") {
    setAluno(null);
    renderSuapModal();
    toast("Seus dados do SUAP foram apagados deste navegador.");
  }
});

// Chegada do bookmarklet: #suap=<código>. O código some da URL na hora e só vale uma vez.
async function importFromHash() {
  const match = location.hash.match(/^#suap=([\w-]{16,64})$/);
  if (!match) return;
  history.replaceState(null, "", location.pathname + location.search);
  try {
    const response = await fetchWithWake(`/aluno/importar/${match[1]}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Erro ${response.status}`);
    setAluno(buildAluno(data));
    // Recém-importado: mostra direto o "Meu percurso"
    openDrawer("me");
    toast("Dados do SUAP importados.");
  } catch (error) {
    toast(`Não consegui importar do SUAP: ${error.message}`);
  }
}

/* ───────────── Início ───────────── */
marked.use({ gfm: true, breaks: false });
updateSendState();
loadCurriculum()
  .then(() => {
    const saved = storage.get(ALUNO_KEY);
    if (saved?.status) setAluno(saved);
    if (!restoreConversation()) renderEmpty();
    importFromHash();
  })
  .catch((error) => toast(error.message));

// O painel da estrutura abre logo abaixo do cabeçalho (que guarda a engrenagem e o botão do SUAP)
new ResizeObserver(([entry]) => {
  document.documentElement.style.setProperty("--topbar-h", `${entry.target.offsetHeight}px`);
}).observe($(".topbar"));
