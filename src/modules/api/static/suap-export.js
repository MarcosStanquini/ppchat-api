// Roda DENTRO do SUAP, injetado pelo bookmarklet do PPChat.
// Usa a sessão que o aluno já abriu no navegador: nenhuma senha passa pelo PPChat.
// Lê só as abas acadêmicas da página do aluno, mostra o que leu e só envia se o aluno confirmar.
(() => {
  const PPCHAT = document.currentScript?.dataset.ppchat;
  if (!PPCHAT) return alert("PPChat: bookmarklet desatualizado. Pegue o botão de novo no site do PPChat.");
  if (window.__ppchatExport) return window.__ppchatExport.focus();

  // Só abas acadêmicas; dados pessoais e bancários ficam de fora
  const WANTED = [
    [/dados acad[eê]micos/i, "Dados Acadêmicos"],
    [/requisitos de conclus/i, "Requisitos de Conclusão"],
    [/hist[oó]rico/i, "Histórico"],
    [/^boletins?$/i, "Boletins"],
    [/atividades complementares/i, "Atividades Complementares"],
    [/curriculares de extens/i, "Atividades Curriculares de Extensão"],
  ];
  const MAX_ROWS = 400;

  /* ── Painel na página do SUAP ── */
  const panel = document.createElement("div");
  panel.innerHTML = `
    <style>
      #ppx{position:fixed;top:16px;right:16px;z-index:2147483647;width:360px;max-width:calc(100vw - 32px);
        font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#191b18;background:#fff;border-radius:16px;
        box-shadow:0 24px 60px -12px rgba(0,0,0,.45);border:1px solid #e5e2da;overflow:hidden}
      #ppx header{display:flex;align-items:center;gap:10px;padding:14px 16px;background:#1f8a4c;color:#fff}
      #ppx header b{font-size:15px}#ppx header button{margin-left:auto;background:none;border:0;color:#fff;font-size:20px;cursor:pointer}
      #ppx .body{padding:14px 16px}#ppx ul{margin:8px 0;padding:0;list-style:none}
      #ppx li{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px solid #f0eee8;font-size:13px}
      #ppx li span:last-child{color:#6c7068;white-space:nowrap}#ppx .muted{color:#6c7068;font-size:12.5px}
      #ppx .err{color:#b3261e}#ppx .btn{display:block;width:100%;margin-top:12px;padding:10px;border:0;border-radius:10px;
        background:#1f8a4c;color:#fff;font-weight:600;font-size:14px;cursor:pointer;text-align:center;text-decoration:none}
      #ppx .btn[disabled]{opacity:.5;cursor:default}#ppx .ghost{background:#f3f1ec;color:#191b18}
    </style>
    <div id="ppx" role="dialog" aria-label="Enviar dados para o PPChat">
      <header><b>PPChat ← SUAP</b><button type="button" data-close aria-label="Fechar">×</button></header>
      <div class="body"><div data-status>Lendo suas abas acadêmicas…</div><ul data-list></ul><div data-actions></div></div>
    </div>`;
  document.body.append(panel);
  const $ = (sel) => panel.querySelector(sel);
  const close = () => { panel.remove(); delete window.__ppchatExport; };
  $("[data-close]").addEventListener("click", close);
  window.__ppchatExport = { focus: () => panel.scrollIntoView() };
  const status = (html) => ($("[data-status]").innerHTML = html);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ── Leitura ── */
  async function getDoc(url) {
    // HX-Request: as abas do SUAP são fragmentos htmx e o servidor espera esse cabeçalho
    const response = await fetch(url, { credentials: "same-origin", headers: { "HX-Request": "true" } });
    if (/\/accounts\/login\//.test(response.url)) throw new Error("Você não está logado no SUAP. Entre e clique no favorito de novo.");
    if (!response.ok) throw new Error(`O SUAP respondeu ${response.status} em ${url}`);
    return new DOMParser().parseFromString(await response.text(), "text/html");
  }

  async function findStudent() {
    const own = location.pathname.match(/^\/edu\/aluno\/([^/]+)\//);
    if (own) return own[1];
    const doc = location.pathname === "/" ? document : await getDoc("/");
    for (const a of doc.querySelectorAll('a[href*="/edu/aluno/"]')) {
      const m = a.getAttribute("href").match(/\/edu\/aluno\/([^/?#]+)\//);
      if (m) return m[1];
    }
    throw new Error("Não achei sua página de aluno. Abra Ensino › Dados do Aluno e clique no favorito de novo.");
  }

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

  // Título de uma tabela: <caption> ou o título mais próximo acima dela
  function tableTitle(table) {
    const caption = table.querySelector("caption");
    if (caption) return clean(caption.textContent);
    let node = table;
    for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
      for (let prev = node.previousElementSibling; prev; prev = prev.previousElementSibling) {
        const heading = prev.matches("h1,h2,h3,h4,h5,legend") ? prev : prev.querySelector?.("h2,h3,h4,h5,legend");
        if (heading && clean(heading.textContent)) return clean(heading.textContent);
      }
    }
    return "";
  }

  function extractTables(doc) {
    return [...doc.querySelectorAll("table")]
      .filter((t) => !t.querySelector("table")) // só tabelas "folha", sem duplicar as aninhadas
      .slice(0, 40)
      .map((t) => ({
        titulo: tableTitle(t).slice(0, 300),
        linhas: [...t.rows].slice(0, MAX_ROWS)
          .map((tr) => [...tr.cells].map((cell) => clean(cell.textContent).slice(0, 500)))
          .filter((row) => row.some(Boolean)),
      }))
      .filter((t) => t.linhas.length);
  }

  async function collect() {
    const matricula = await findStudent();
    const base = `/edu/aluno/${encodeURIComponent(matricula)}/`;
    const page = await getDoc(base);
    // Descobre as abas pelos próprios elementos da página. No SUAP do IFSP cada aba é carregada por htmx
    // (data-tab-name + hx-get="/edu/aluno/<matrícula>/historico/"); links "?tab=" ficam como alternativa
    const candidates = [
      ...[...page.querySelectorAll("[data-tab-name][hx-get]")].map((el) => [el, el.getAttribute("hx-get")]),
      ...[...page.querySelectorAll('a[href*="tab="]')].map((el) => [el, el.getAttribute("href")]),
    ];
    const tabs = [];
    for (const [pattern, label] of WANTED) {
      const hit = candidates.find(([el]) => pattern.test(clean(el.textContent)));
      if (hit && !tabs.some((t) => t.label === label)) tabs.push({ label, url: new URL(hit[1], location.origin + base).href });
    }
    if (!tabs.length) tabs.push({ label: "Página do aluno", url: location.origin + base });

    const abas = [];
    for (const tab of tabs) {
      status(`Lendo <b>${esc(tab.label)}</b>…`);
      try {
        const doc = tab.url === location.origin + base ? page : await getDoc(tab.url);
        abas.push({ titulo: tab.label, tabelas: extractTables(doc) });
      } catch (error) {
        abas.push({ titulo: tab.label, tabelas: [], erro: error.message });
      }
    }
    return { matricula, coletado_em: new Date().toISOString(), abas };
  }

  /* ── Envio ── */
  async function send(payload) {
    const body = JSON.stringify({ ...payload, abas: payload.abas.map(({ erro, ...aba }) => aba) });
    const deadline = Date.now() + 90_000; // o plano grátis do PPChat pode estar "dormindo"
    for (;;) {
      try {
        const response = await fetch(`${PPCHAT}/aluno/importar`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
        if (response.ok) return (await response.json()).code;
        if (![502, 503, 504].includes(response.status) || Date.now() > deadline) {
          const detail = (await response.json().catch(() => null))?.detail;
          throw new Error(typeof detail === "string" ? detail : `O PPChat respondeu ${response.status}`);
        }
      } catch (error) {
        if (!(error instanceof TypeError) || Date.now() > deadline) throw error;
      }
      status("Acordando o PPChat (plano gratuito)… pode levar até 1 minuto.");
      await new Promise((r) => setTimeout(r, 3000));
    }
  }

  (async () => {
    try {
      const payload = await collect();
      const rows = (aba) => aba.tabelas.reduce((n, t) => n + t.linhas.length, 0);
      $("[data-list]").innerHTML = payload.abas.map((aba) =>
        `<li><span>${esc(aba.titulo)}</span><span${aba.erro ? ' class="err"' : ""}>${aba.erro ? "erro" : `${aba.tabelas.length} tabelas · ${rows(aba)} linhas`}</span></li>`).join("");
      status(`Matrícula <b>${esc(payload.matricula)}</b>. Isto é o que será enviado ao PPChat:
        <div class="muted">Fica guardado só no seu navegador; o servidor apaga em até 10 min.</div>`);
      $("[data-actions]").innerHTML = `<button class="btn" data-send>Enviar e abrir o PPChat</button>`;
      $("[data-send]").addEventListener("click", async (event) => {
        event.target.disabled = true;
        event.target.textContent = "Enviando…";
        try {
          const url = `${PPCHAT}/#suap=${await send(payload)}`;
          status("Pronto! Seus dados estão esperando no PPChat.");
          $("[data-actions]").innerHTML = `<a class="btn" href="${esc(url)}" target="_blank" rel="noopener">Abrir no PPChat</a>
            <button class="btn ghost" data-close2>Fechar</button>`;
          $("[data-close2]").addEventListener("click", close);
          window.open(url, "_blank", "noopener"); // se o navegador bloquear, sobra o botão acima
        } catch (error) {
          status(`<span class="err">${esc(error.message)}</span>`);
          event.target.disabled = false;
          event.target.textContent = "Tentar de novo";
        }
      });
    } catch (error) {
      status(`<span class="err">${esc(error.message)}</span>`);
    }
  })();
})();
