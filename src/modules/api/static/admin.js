// Página /admin. Todo texto vindo do banco entra por textContent (nunca innerHTML).
const $ = (sel) => document.querySelector(sel);
const TOKEN_KEY = "ppchat-admin-token";
const state = { dias: 7, curso: "", busca: "", pagina: 1, total: 0 };
const PER_PAGE = 30;
const siglas = {}; // slug → sigla, para a linha de cada pergunta

const session = {
  get() { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set(v) { try { sessionStorage.setItem(TOKEN_KEY, v); } catch {} },
  clear() { try { sessionStorage.removeItem(TOKEN_KEY); } catch {} },
};
let token = session.get();

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

async function api(path, params = {}, body = undefined) {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
  const init = { headers: { Authorization: `Bearer ${token}` } };
  if (body !== undefined) {
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(`/admin/api/${path}?${query}`, init);
  if (response.status === 401 || response.status === 429) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.detail || "Senha incorreta.");
    error.auth = true;
    throw error;
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Erro ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

const pct = (part, whole) => (whole ? `${Math.round((part / whole) * 100)}%` : "—");
const when = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const filters = () => ({ dias: state.dias, curso: state.curso });

function renderStats(s) {
  const items = [
    [s.perguntas, "perguntas"],
    [s.visitantes, "visitantes (por dia)"],
    [pct(s.positivas, s.votadas), `de 👍 entre ${s.votadas} votadas`],
    [pct(s.paradas, s.perguntas), "paradas no meio"],
    [pct(s.reformuladas, s.perguntas), "reformuladas"],
    [s.erros, "erros"],
  ];
  $("#stats").replaceChildren(...items.map(([value, label]) => el("div", { class: "admin-stat" }, el("b", {}, String(value)), el("span", {}, label))));
}

function renderTop(rows) {
  const list = $("#top");
  if (!rows.length) return list.replaceChildren(el("p", { class: "admin-empty" }, "Nenhuma pergunta no período."));
  list.replaceChildren(...rows.map((r) => el("li", {}, r.pergunta, el("span", { class: "count" }, `${r.vezes}×`))));
}

function signalTags(q) {
  const tags = [];
  if (q.voto === "up") tags.push(el("span", { class: "tag good" }, "👍"));
  if (q.voto === "down") tags.push(el("span", { class: "tag bad" }, "👎"));
  if (q.status === "parada") tags.push(el("span", { class: "tag bad" }, "parada"));
  if (q.status === "erro") tags.push(el("span", { class: "tag bad" }, `erro${q.erro ? ` · ${q.erro}` : ""}`));
  if (q.reformulou) tags.push(el("span", { class: "tag bad" }, "reformulou"));
  if (q.abandonou) tags.push(el("span", { class: "tag" }, "saiu depois"));
  if (q.copiou) tags.push(el("span", { class: "tag good" }, "copiou"));
  if (q.abriu_pagina) tags.push(el("span", { class: "tag good" }, "abriu página"));
  if (q.tinha_suap) tags.push(el("span", { class: "tag" }, "com SUAP"));
  return tags;
}

function questionItem(q) {
  const facts = [when(q.criado_em), siglas[q.curso] || q.curso, `${(q.duracao_ms / 1000).toFixed(1)}s`];
  const meta = el("div", { class: "q-meta" }, el("span", {}, facts.join(" · ")), ...signalTags(q));
  return el("details", { class: "admin-q" },
    el("summary", {}, el("div", { class: "q-text" }, q.pergunta), meta),
    el("div", { class: "q-answer" }, q.resposta || (q.tinha_suap ? "(resposta não guardada: o aluno usou os dados do SUAP)" : "(sem resposta)")));
}

function renderQuestions(container, rows, empty) {
  if (!rows.length) return container.replaceChildren(el("p", { class: "admin-empty" }, empty));
  container.replaceChildren(...rows.map(questionItem));
}

function renderPager() {
  const pages = Math.max(1, Math.ceil(state.total / PER_PAGE));
  $("#page-info").textContent = `${state.total} perguntas · página ${state.pagina} de ${pages}`;
  $("#prev").disabled = state.pagina <= 1;
  $("#next").disabled = state.pagina >= pages;
}

async function loadList() {
  const page = await api("perguntas", { ...filters(), busca: state.busca, pagina: state.pagina });
  state.total = page.total;
  renderQuestions($("#list"), page.itens, state.busca ? "Nada encontrado." : "Nenhuma pergunta no período.");
  renderPager();
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const money = (v) => usd.format(v);
const shortDay = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7);

function renderCosts(c) {
  const box = $("#costs");
  $("#saldo-form").hidden = !c.configurado;
  if (!c.configurado) {
    $("#costs-note").textContent = "";
    return box.replaceChildren(el("p", { class: "admin-empty" },
      "Não configurado: falta a variável ANTHROPIC_ADMIN_KEY (chave de administração) no servidor."));
  }
  $("#costs-note").textContent = c.dados_ate ? `dados até ${when(c.dados_ate)}` : "";
  const saldo = c.saldo
    ? el("div", { class: "admin-stat" }, el("b", {}, money(c.saldo.estimado_usd)), el("span", {}, "saldo estimado"),
        el("div", { class: "cost-sub" },
          `${money(c.saldo.informado_usd)} informado em ${when(c.saldo.em)}, menos ${money(c.saldo.gasto_desde_usd)} gastos desde então`))
    : el("div", { class: "admin-stat" }, el("b", {}, "—"), el("span", {}, "saldo estimado"),
        el("div", { class: "cost-sub" }, "Informe o saldo do Console abaixo para estimar."));
  const top = el("div", { class: "cost-top" },
    el("div", { class: "admin-stat" }, el("b", {}, money(c.total_usd)), el("span", {}, `gastos nos últimos ${state.dias} dias`)),
    saldo);

  const max = Math.max(...c.por_dia.map((d) => d.usd), 0);
  const bars = el("div", { class: "cost-bars", role: "img", "aria-label": "Gasto por dia" },
    ...c.por_dia.map((d) => {
      const bar = el("i", { title: `${shortDay(d.dia)}: ${money(d.usd)}` });
      bar.style.height = `${max ? Math.max(2, (d.usd / max) * 100) : 2}%`;
      return bar;
    }));
  const days = c.por_dia.length
    ? el("div", {}, bars, el("div", { class: "cost-axis" }, el("span", {}, shortDay(c.por_dia[0].dia)),
        el("span", {}, shortDay(c.por_dia.at(-1).dia))))
    : el("p", { class: "admin-empty" }, "Nenhum gasto no período.");
  const models = el("ul", { class: "cost-models" },
    ...c.por_modelo.map((m) => el("li", {}, el("span", {}, m.modelo), el("b", {}, money(m.usd)))));
  box.replaceChildren(top, el("div", { class: "cost-cols" }, days, models));
}

async function loadCosts() {
  try {
    renderCosts(await api("custos", { dias: state.dias }));
  } catch (error) {
    if (error.auth) return showLogin(error.message);
    $("#saldo-form").hidden = true;
    $("#costs").replaceChildren(el("p", { class: "admin-error" }, error.message));
  }
}

async function loadAll() {
  loadCosts(); // independente: se a Anthropic falhar, o resto do painel aparece igual
  $("#panel-error").hidden = true;
  try {
    const [stats, top, negatives] = await Promise.all([
      api("resumo", filters()), api("mais-feitas", filters()), api("negativas", filters()),
    ]);
    renderStats(stats);
    renderTop(top);
    renderQuestions($("#negatives"), negatives, "Nenhum 👎 no período.");
    await loadList();
  } catch (error) {
    if (error.auth) return showLogin(error.message);
    $("#panel-error").textContent = error.message;
    $("#panel-error").hidden = false;
  }
}

function showLogin(message) {
  token = null;
  session.clear();
  $("#panel").hidden = true;
  $("#login").hidden = false;
  $("#login-error").textContent = message || "";
  $("#login-error").hidden = !message;
  $("#token").focus();
}

async function showPanel() {
  $("#login").hidden = true;
  $("#panel").hidden = false;
  try {
    const cursos = await api("cursos");
    for (const c of cursos) siglas[c.slug] = c.sigla;
    $("#curso").replaceChildren(el("option", { value: "" }, "Todos os cursos"),
      ...cursos.map((c) => el("option", { value: c.slug }, `${c.sigla} · ${c.nome}`)));
  } catch (error) {
    if (error.auth) return showLogin(error.message);
  }
  loadAll();
}

$("#login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  token = $("#token").value.trim();
  if (!token) return;
  session.set(token);
  $("#token").value = "";
  showPanel();
});
$("#logout").addEventListener("click", () => showLogin());

$("#saldo-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = $("#saldo-error");
  error.hidden = true;
  try {
    await api("saldo", {}, { valor_usd: $("#saldo").value });
    $("#saldo").value = "";
    loadCosts();
  } catch (err) {
    if (err.auth) return showLogin(err.message);
    error.textContent = "Valor inválido: use um número entre 0 e 100000.";
    error.hidden = false;
  }
});

for (const button of document.querySelectorAll("[data-dias]")) {
  button.addEventListener("click", () => {
    state.dias = Number(button.dataset.dias);
    state.pagina = 1;
    for (const b of document.querySelectorAll("[data-dias]")) b.setAttribute("aria-pressed", String(b === button));
    loadAll();
  });
}
$("#curso").addEventListener("change", (event) => { state.curso = event.target.value; state.pagina = 1; loadAll(); });

let searchTimer = 0;
$("#busca").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.busca = event.target.value.trim(); state.pagina = 1; loadList().catch(() => {}); }, 300);
});
$("#prev").addEventListener("click", () => { state.pagina -= 1; loadList(); });
$("#next").addEventListener("click", () => { state.pagina += 1; loadList(); });

token ? showPanel() : showLogin();
