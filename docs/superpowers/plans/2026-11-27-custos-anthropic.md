# Custos da Anthropic no /admin — plano

> Execução inline (executing-plans), TDD em cada tarefa.

**Goal:** cartão no `/admin` com gasto real da Anthropic no período e saldo estimado.
**Architecture:** `observability/costs.py` busca o relatório de custos com o `AsyncAnthropic` (chave de admin),
em janelas de até 31 dias, com cache de 30 min; o Postgres guarda um ponto de referência do saldo; `admin.py`
expõe `GET /admin/api/custos` e `POST /admin/api/saldo`; `admin.js` desenha o cartão.
**Tech stack:** FastAPI, `anthropic` 2.3.0 (`client.beta.organization.analytics.cost.list`), psycopg, JS puro.
**Spec:** `docs/superpowers/specs/2026-11-27-custos-anthropic-design.md`

## Global Constraints
- A chave `ANTHROPIC_ADMIN_KEY` nunca vai ao navegador nem ao log; erro loga só o nome da classe.
- A API aceita no máximo 31 dias por consulta: 90 dias = várias janelas.
- Valores vêm em centavos (string decimal) → `Decimal(amount) / 100`.
- Cache 30 min; tempo máximo 10 s; falha não é guardada no cache.
- Saldo informado: 0 a 100 000 US$.

## Review Focus
- Período maior que 31 dias somado corretamente (janelas sem sobreposição).
- Várias páginas de resultado (has_next_page).
- Anthropic lenta ou com erro → 502 com aviso, admin continua funcionando.
- Sem chave → `{"configurado": false}`, sem chamar a Anthropic.
- Saldo sem referência → só gasto; com referência → valor − gasto desde a hora informada.

### Task 1: `costs.py`
Files: create `src/modules/observability/costs.py`, `tests/test_costs.py`.
Produces: `CostService(list_costs, now=..., ttl=1800)`, `await report(dias) -> dict`
(`total_usd`, `por_dia[{dia, usd}]`, `por_modelo[{modelo, usd}]`, `dados_ate`),
`await spent_since(when) -> tuple[Decimal, datetime|None]`, `windows(start, end) -> list[tuple]`,
`get_service()/set_service()`.
Tests: janelas de 90 dias = 3 sem sobreposição; soma por dia/modelo e conversão de centavos; paginação;
cache (segunda chamada não consulta) e erro não cacheado.

### Task 2: saldo no Postgres
Files: `schema.sql` (tabela `saldo_referencia`, uma linha), `postgres_store.py` (`set_balance`, `get_balance`),
`store.py` (`AdminQueries`), `tests/conftest.py` (truncate), `tests/test_postgres_store.py`.
Test: gravar duas vezes guarda só o último valor com a hora.

### Task 3: rotas
Files: `admin.py`, `settings.py` (`anthropic_admin_key`), `tests/test_admin.py`.
Tests: sem chave → configurado false; com serviço falso → total e saldo estimado; erro → 502;
POST saldo valida faixa e exige senha.

### Task 4: tela + config
Files: `admin.html`, `admin.css`, `admin.js`, `README.md`, `.env-example`, `render.yaml`.
Verificação: prints em `prints/11-custos/`.
