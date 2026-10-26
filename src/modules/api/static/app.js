// PPChat — front sem build: chat com streaming + mapa curricular interativo.

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const SVG_NS = "http://www.w3.org/2000/svg";
const STORE_KEY = "ppchat-conversation-v1";
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
  ask: '<svg viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
};
const THINKING_STEPS = [
  "Lendo o PPC…",
  "Consultando o grafo de pré-requisitos…",
  "Cruzando com os planos de ensino…",
  "Escrevendo a resposta…",
];
const ABORDAGEM = { teorica: "Teórica", pratica: "Prática", teorico_pratica: "Teórico-prática" };

const state = {
  curriculum: null,
  byCode: new Map(),
  sessionId: null,
  history: [], // {role: "user"|"assistant", text, usage?, stopped?}
  busy: false,
  controller: null,
  selected: null,
  showAllEdges: false,
  showCritical: false,
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
const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isMobile = () => matchMedia("(max-width: 900px)").matches;

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ───────────── Tema e abas ───────────── */
$("#theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  root.dataset.theme = current === "dark" ? "light" : "dark";
  try { localStorage.setItem("ppchat-theme", root.dataset.theme); } catch {}
  requestAnimationFrame(drawEdges);
});

function setPane(name) {
  $$(".tab").forEach((tab) => {
    const active = tab.dataset.pane === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", active);
  });
  $("#pane-chat").classList.toggle("is-visible", name === "chat");
  $("#pane-map").classList.toggle("is-visible", name === "map");
  if (name === "map") requestAnimationFrame(drawEdges);
}
$$(".tab").forEach((tab) => tab.addEventListener("click", () => setPane(tab.dataset.pane)));

/* ───────────── Currículo ───────────── */
async function loadCurriculum() {
  const response = await fetch("/curriculum");
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

  renderSuggestions();
  renderBoard();
  renderRules();
}

function renderSuggestions() {
  const { disciplinas, gargalos } = state.curriculum;
  const deepest = [...disciplinas].sort((a, b) => b.profundidade - a.profundidade || b.indice_complexidade - a.indice_complexidade)
    .find((d) => d.tipo === "obrigatoria" && !/extens/i.test(d.nome)) || disciplinas[0];
  const gate = state.byCode.get(gargalos[1] || gargalos[0]);
  const items = [
    { icon: ICON.chain, tag: "Dependências", text: `Quais são todos os pré-requisitos de ${titleCase(deepest.nome)}?` },
    { icon: ICON.route, tag: "Planejamento", text: `Reprovei em ${titleCase(gate.nome)}. Como fica o resto do meu curso?` },
    { icon: ICON.gauge, tag: "Dificuldade", text: "Quais são as disciplinas mais difíceis do curso e por quê?" },
    { icon: ICON.rules, tag: "Regras", text: "Como funcionam o estágio, o TCC e as atividades complementares?" },
  ];
  $("#suggestions").innerHTML = items.map((item, i) => `
    <button class="suggestion" style="animation-delay:${80 + i * 60}ms" data-q="${escapeHtml(item.text)}">
      <span class="s-tag">${item.icon}${item.tag}</span>
      <span class="s-text">${escapeHtml(item.text)}</span>
    </button>`).join("");
  $$(".suggestion").forEach((btn) => btn.addEventListener("click", () => ask(btn.dataset.q)));
}

function renderBoard() {
  const { disciplinas, duracao_semestres } = state.curriculum;
  const inner = $("#board-inner");
  const columns = [];
  for (let s = 1; s <= duracao_semestres; s++) {
    columns.push({ title: `${s}º semestre`, items: disciplinas.filter((d) => d.semestre === s) });
  }
  const optional = disciplinas.filter((d) => !d.semestre);
  if (optional.length) columns.push({ title: "Optativas", items: optional });

  const html = columns.map((col) => `
    <div class="column">
      <div class="col-head"><b>${col.title}</b><span>${hours(col.items.reduce((sum, d) => sum + d.carga_horaria_total, 0))}</span></div>
      ${col.items.map(cardHtml).join("")}
    </div>`).join("");
  inner.insertAdjacentHTML("beforeend", html);

  $$(".card", inner).forEach((card) => card.addEventListener("click", (event) => {
    event.stopPropagation();
    select(state.selected === card.dataset.code ? null : card.dataset.code);
  }));
  $("#board").addEventListener("click", () => select(null));
  new ResizeObserver(() => drawEdges()).observe(inner);
}

function cardHtml(d) {
  const blocks = d.libera_transitivamente.length;
  return `
    <button class="card" data-code="${d.codigo}" title="${escapeHtml(titleCase(d.nome))}">
      <span class="card-top">
        <span class="card-code">${d.codigo}</span>
        <i class="dot ${levelClass(d.nivel_estimado)}" title="Complexidade ${d.nivel_estimado}"></i>
      </span>
      <span class="card-name">${escapeHtml(d.nome)}</span>
      <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
      <span class="card-meta">
        <span>${hours(d.carga_horaria_total)} · ${ABORDAGEM[d.abordagem].split("-")[0]}</span>
        ${blocks >= 4 ? `<span class="badge-gate" title="Trava ${blocks} disciplinas se reprovada">trava ${blocks}</span>` : ""}
      </span>
    </button>`;
}

function renderRules() {
  const rules = state.curriculum.requisitos_gerais;
  $("#rules-body").innerHTML = rules.length
    ? rules.map((r) => `
      <div class="rule">
        <b>${escapeHtml(r.item)}</b>
        <p>${escapeHtml(r.descricao)} ${r.pagina ? pageChip(r.pagina) : ""}</p>
      </div>`).join("")
    : '<p class="none">Nenhuma regra extraída.</p>';
}

/* ───────────── Seleção e setas ───────────── */
function select(code, { scroll = false } = {}) {
  state.selected = code;
  const d = code ? state.byCode.get(code) : null;
  const anc = new Set(d ? d.pre_requisitos_transitivos : []);
  const desc = new Set(d ? d.libera_transitivamente : []);

  $("#board").classList.toggle("has-selection", !!d);
  $$(".card").forEach((card) => {
    const c = card.dataset.code;
    card.classList.toggle("is-sel", c === code);
    card.classList.toggle("is-anc", anc.has(c));
    card.classList.toggle("is-desc", desc.has(c));
  });
  renderDetail(d);
  drawEdges({ animate: true });

  if (d) {
    const card = $(`.card[data-code="${code}"]`);
    revealCard(card, scroll);
    if (scroll) {
      card.classList.remove("is-pulse");
      void card.offsetWidth;
      card.classList.add("is-pulse");
    }
  }
}

// Mantém o card visível na faixa do mapa que o painel de detalhes não cobre
function revealCard(card, center) {
  const board = $("#board");
  const panel = $("#detail");
  const b = board.getBoundingClientRect();
  const r = card.getBoundingClientRect();
  const visibleBottom = panel.hidden ? b.bottom : panel.getBoundingClientRect().top - 12;
  const top = board.scrollTop + r.top - b.top - 44; // 44 = cabeçalho fixo da coluna
  const left = board.scrollLeft + r.left - b.left - (b.width - r.width) / 2;

  const outY = r.bottom > visibleBottom || r.top < b.top + 40;
  const outX = r.left < b.left || r.right > b.right;
  if (center || (outX && outY)) board.scrollTo({ top, left, behavior: "smooth" });
  else if (outY) board.scrollTo({ top, behavior: "smooth" });
  else if (outX) board.scrollTo({ left, behavior: "smooth" });
}

function edgeList() {
  const edges = [];
  const add = (from, to, cls) => edges.push({ from, to, cls });
  const prereqs = (c) => state.byCode.get(c)?.pre_requisitos || [];

  if (state.showAllEdges) {
    state.curriculum.disciplinas.forEach((d) => d.pre_requisitos.forEach((p) => add(p, d.codigo, "e-faint")));
  }
  if (state.showCritical) {
    const path = state.curriculum.cadeia_critica;
    for (let i = 1; i < path.length; i++) add(path[i - 1], path[i], "e-crit");
  }
  if (state.selected) {
    const d = state.byCode.get(state.selected);
    const up = new Set([...d.pre_requisitos_transitivos, d.codigo]);
    const down = new Set([...d.libera_transitivamente, d.codigo]);
    up.forEach((c) => prereqs(c).forEach((p) => up.has(p) && add(p, c, "e-anc")));
    d.libera_transitivamente.forEach((c) => prereqs(c).forEach((p) => down.has(p) && add(p, c, "e-desc")));
  }
  return edges;
}

function drawEdges({ animate = false } = {}) {
  const svg = $("#edges");
  const inner = $("#board-inner");
  if (!state.curriculum || !inner.offsetParent) return; // mapa oculto (aba do celular)
  svg.setAttribute("width", inner.scrollWidth);
  svg.setAttribute("height", inner.scrollHeight);
  svg.replaceChildren();

  const base = inner.getBoundingClientRect();
  const box = (code) => {
    const card = $(`.card[data-code="${code}"]`, inner);
    if (!card) return null;
    const r = card.getBoundingClientRect();
    return { left: r.left - base.left, right: r.right - base.left, mid: r.top - base.top + r.height / 2 };
  };

  for (const { from, to, cls } of edgeList()) {
    const a = box(from), b = box(to);
    if (!a || !b) continue;
    const x1 = a.right, y1 = a.mid, x2 = b.left, y2 = b.mid;
    const bend = Math.max(36, Math.abs(x2 - x1) / 2);
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`);
    path.setAttribute("class", cls);
    svg.append(path);
    if (animate && (cls === "e-anc" || cls === "e-desc")) {
      path.style.setProperty("--len", path.getTotalLength());
      path.classList.add("e-anim");
    }
    if (cls !== "e-faint") {
      const dot = document.createElementNS(SVG_NS, "circle");
      dot.setAttribute("cx", x2); dot.setAttribute("cy", y2); dot.setAttribute("r", 3.2);
      dot.setAttribute("fill", getComputedStyle(path).stroke);
      svg.append(dot);
    }
  }
}

function chipList(codes, cls) {
  if (!codes.length) return '<span class="none">Nenhuma</span>';
  return `<div class="chips">${codes.map((c) => {
    const d = state.byCode.get(c);
    return `<button class="chip ${cls}" data-goto="${c}" title="${c}">${escapeHtml(d ? d.nome : c)}</button>`;
  }).join("")}</div>`;
}

function renderDetail(d) {
  const panel = $("#detail");
  const board = $("#board");
  if (!d) {
    panel.hidden = true;
    board.style.paddingBottom = "";
    return;
  }
  const name = titleCase(d.nome);
  const blocks = d.libera_transitivamente.length;
  panel.innerHTML = `
    <div class="detail-head">
      <div>
        <span class="card-code">${d.codigo}</span>
        <h3>${escapeHtml(d.nome)}</h3>
        <div class="detail-sub">
          <span class="pill">${d.semestre ? `${d.semestre}º semestre` : "Optativa"}</span>
          <span class="pill">${hours(d.carga_horaria_total)}${d.carga_horaria_extensao ? ` (extensão ${hours(d.carga_horaria_extensao)})` : ""}</span>
          <span class="pill">${d.aulas_semanais} aulas/semana</span>
          <span class="pill">${ABORDAGEM[d.abordagem]}</span>
          ${d.usa_laboratorio ? '<span class="pill">Laboratório</span>' : ""}
        </div>
      </div>
      <button class="icon-btn" data-close-detail aria-label="Fechar">${ICON.close}</button>
    </div>
    <div class="detail-grid">
      <div>
        <h4>Pré-requisitos diretos</h4>
        ${chipList(d.pre_requisitos, "anc")}
        ${d.pre_requisitos_transitivos.length > d.pre_requisitos.length
          ? `<h4 style="margin-top:12px">Base acumulada</h4>${chipList(d.pre_requisitos_transitivos.filter((c) => !d.pre_requisitos.includes(c)), "anc")}`
          : ""}
        <h4 style="margin-top:12px">Libera</h4>
        ${chipList(d.libera_diretamente, "desc")}
        ${blocks > d.libera_diretamente.length ? `<p class="trava">Se reprovada, trava ${blocks} disciplinas no total.</p>` : ""}
      </div>
      <div>
        <h4>Complexidade estimada</h4>
        <div class="complexity">
          <span class="score">${d.indice_complexidade.toLocaleString("pt-BR")}</span>
          <span class="meter"><i class="${levelClass(d.nivel_estimado)}" style="width:${d.indice_complexidade * 10}%"></i></span>
        </div>
        <p class="muted small" style="margin:4px 0 12px">${d.nivel_estimado} · profundidade ${d.profundidade} na cadeia · não é dado oficial</p>
        ${d.topicos_principais.length ? `<h4>Tópicos</h4><ul class="topics">${d.topicos_principais.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>` : ""}
      </div>
    </div>
    <div class="detail-actions">
      <button class="btn btn-sm btn-primary" data-ask="O que eu vou aprender em ${escapeHtml(name)}? Resuma a ementa e os objetivos.">${ICON.ask}O que vou aprender?</button>
      <button class="btn btn-sm" data-ask="Como devo me preparar para ${escapeHtml(name)}? Considere os pré-requisitos e o conteúdo.">Como me preparar?</button>
      <button class="btn btn-sm" data-ask="O que acontece com o meu curso se eu reprovar em ${escapeHtml(name)}?">E se eu reprovar?</button>
      ${d.pagina_plano_ensino ? `<a class="btn btn-sm" href="/pdf#page=${d.pagina_plano_ensino}" target="_blank" rel="noopener">${ICON.page}Plano de ensino · p. ${d.pagina_plano_ensino}</a>` : ""}
    </div>`;
  panel.hidden = false;
  panel.scrollTop = 0;
  board.style.paddingBottom = `${panel.offsetHeight + 24}px`;
}

$("#detail").addEventListener("click", (event) => {
  const target = event.target.closest("[data-goto], [data-ask], [data-close-detail]");
  if (!target) return;
  if (target.dataset.goto) select(target.dataset.goto, { scroll: true });
  else if (target.dataset.ask) { ask(target.dataset.ask); if (isMobile()) setPane("chat"); }
  else select(null);
});

/* Toggles, busca e modal */
function bindToggle(id, key) {
  $(id).addEventListener("click", (event) => {
    state[key] = !state[key];
    event.currentTarget.setAttribute("aria-pressed", state[key]);
    if (key === "showCritical") {
      const path = new Set(state.curriculum.cadeia_critica);
      $$(".card").forEach((card) => card.classList.toggle("is-crit", state.showCritical && path.has(card.dataset.code)));
    }
    drawEdges({ animate: true });
  });
}
bindToggle("#toggle-edges", "showAllEdges");
bindToggle("#toggle-critical", "showCritical");

$("#search").addEventListener("input", (event) => {
  const query = normalize(event.target.value.trim());
  $("#board").classList.toggle("is-filtering", !!query);
  $$(".card").forEach((card) => {
    const d = state.byCode.get(card.dataset.code);
    card.classList.toggle("is-match", !!query && normalize(`${d.nome} ${d.codigo}`).includes(query));
  });
});
$("#search").addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const match = $(".card.is-match");
  if (match) select(match.dataset.code, { scroll: true });
});

const rulesModal = $("#rules-modal");
$("#open-rules").addEventListener("click", () => rulesModal.showModal());
rulesModal.addEventListener("click", (event) => {
  if (event.target === rulesModal || event.target.closest("[data-close]")) rulesModal.close();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.selected && !rulesModal.open) select(null);
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
      const d = state.byCode.get(code);
      return d ? `<button class="code-ref" data-code="${code}" title="${escapeHtml(titleCase(d.nome))} — ver no mapa">${code}</button>` : match;
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
  if (!chip) return;
  if (isMobile()) setPane("map");
  requestAnimationFrame(() => select(chip.dataset.code, { scroll: true }));
});

/* ───────────── Chat ───────────── */
const messagesEl = $("#messages");
const input = $("#input");
const composer = $("#composer");

function scrollToBottom(force = false) {
  const nearBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 140;
  if (force || nearBottom) messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addUserMessage(text) {
  $("#empty")?.remove();
  messagesEl.insertAdjacentHTML("beforeend",
    `<div class="msg msg-user"><div class="bubble">${escapeHtml(text)}</div></div>`);
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
    answer: $(".answer", msg),
    footer: $(".msg-footer", msg),
    reasoning: $(".reasoning", msg),
    reasoningBody: $(".reasoning-body", msg),
    reasoningLabel: $(".reasoning-label", msg),
    reasoningPreview: $(".reasoning-preview", msg),
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
    ui.reasoningBody.scrollTop = ui.reasoningBody.scrollHeight;
  } else {
    ui.reasoningPreview.textContent = "";
    ui.reasoningLabel.textContent = entry.thinkingSeconds
      ? `Raciocinou por ${entry.thinkingSeconds}s` : "Raciocínio";
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
const updateSendState = () => { $("#send").disabled = !state.busy && !input.value.trim(); };

function stopAnswer() {
  if (!state.busy) return;
  // Avisa o servidor explicitamente: abortar o fetch nem sempre derruba a conexão (proxies, keep-alive)
  if (state.sessionId) fetch(`/chat/${state.sessionId}/cancel`, { method: "POST" }).catch(() => {});
  state.controller?.abort();
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function streamWithRetry(question, ui) {
  for (let attempt = 0; ; attempt++) {
    try {
      return await streamAnswer(question, ui);
    } catch (error) {
      // 409: a resposta interrompida ainda está encerrando no servidor; costuma levar 1-2 s
      if (error.status !== 409 || attempt >= 10) throw error;
      await sleep(600);
    }
  }
}

function persist() {
  storage.set(STORE_KEY, { sessionId: state.sessionId, history: state.history });
}

async function streamAnswer(question, ui) {
  state.controller = new AbortController();
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: state.sessionId }),
    signal: state.controller.signal,
  });
  if (!response.ok) {
    const error = new Error((await response.json().catch(() => ({}))).detail || `Erro ${response.status}`);
    error.status = response.status;
    throw error;
  }
  state.sessionId = response.headers.get("X-Session-Id");

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
  if (isMobile()) setPane("chat");
  input.value = "";
  autosize();

  addUserMessage(question);
  const ui = addBotMessage();
  ui.thinkingTimer = startThinking(ui.answer);
  scrollToBottom(true);
  setBusy(true);

  let entry;
  try {
    try {
      entry = await streamWithRetry(question, ui);
    } catch (error) {
      if (error.status !== 404) throw error;
      // O servidor reiniciou e perdeu a sessão: continua numa nova
      state.sessionId = null;
      toast("A conversa anterior expirou no servidor. Continuei numa nova sessão.");
      entry = await streamWithRetry(question, ui);
    }
    renderMarkdown(ui.answer, entry.text || (entry.stopped ? "" : "_Sem resposta._"));
    renderReasoning(ui, entry, { live: false });
    renderFooter(ui.footer, entry);
    if (!entry.stopped) {
      state.history.push({ role: "user", text: question }, entry);
      persist();
    }
  } catch (error) {
    clearInterval(ui.thinkingTimer);
    const partial = error.partial?.text ? DOMPurify.sanitize(marked.parse(error.partial.text)) : "";
    ui.answer.innerHTML = `${partial}<div class="error-box">${
      error.status === 409 ? "Ainda estou terminando a resposta anterior. Tente de novo em instantes."
        : `Não consegui responder: ${escapeHtml(error.message)}`}</div>`;
  } finally {
    state.controller = null;
    setBusy(false);
    scrollToBottom();
    if (!isMobile()) input.focus();
  }
}

function restoreConversation() {
  const saved = storage.get(STORE_KEY);
  if (!saved?.history?.length) return;
  state.sessionId = saved.sessionId;
  state.history = saved.history;
  for (const entry of state.history) {
    if (entry.role === "user") addUserMessage(entry.text);
    else {
      const ui = addBotMessage();
      renderMarkdown(ui.answer, entry.text);
      renderReasoning(ui, entry, { live: false });
      renderFooter(ui.footer, entry);
    }
  }
  scrollToBottom(true);
}

$("#new-chat").addEventListener("click", () => {
  stopAnswer();
  state.sessionId = null;
  state.history = [];
  storage.remove(STORE_KEY);
  messagesEl.innerHTML = `
    <div class="empty" id="empty">
      <p class="eyebrow">Nova conversa</p>
      <h1>Pergunte qualquer coisa<br><em>sobre o seu curso.</em></h1>
      <p class="lede">Respostas baseadas no Projeto Pedagógico inteiro, com a página de cada informação
        e o grafo de pré-requisitos já calculado.</p>
      <div class="suggestions" id="suggestions"></div>
    </div>`;
  if (state.curriculum) renderSuggestions();
  setPane("chat");
  input.focus();
});

/* Composer */
function autosize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  input.style.overflowY = input.scrollHeight > 180 ? "auto" : "hidden";
  updateSendState();
}
input.addEventListener("input", autosize);
input.addEventListener("keydown", (event) => {
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
  .then(() => {
    restoreConversation();
    document.fonts?.ready.then(() => drawEdges());
  })
  .catch((error) => toast(error.message));
window.addEventListener("resize", () => drawEdges());
