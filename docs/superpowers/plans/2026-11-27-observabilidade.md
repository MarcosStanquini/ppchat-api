# Observabilidade de perguntas e respostas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gravar cada pergunta/resposta do chat no Neon com 👍/👎 e sinais automáticos, e mostrar tudo numa página `/admin` com senha.

**Architecture:** Um módulo novo `src/modules/observability/` com uma interface de armazenamento (`Store`), uma versão em memória (testes e sem banco) e uma em Postgres (`psycopg` async + pool). A API grava em segundo plano no fim de cada resposta e recebe eventos em `POST /eventos`; o `/admin` é uma página estática que consulta `GET /admin/api/*` com token.

**Tech Stack:** Python 3.13, FastAPI, `psycopg[binary]` + `psycopg_pool` (novos), pytest + pytest-asyncio (novos, dev), JS puro.

**Spec:** `docs/superpowers/specs/2026-11-27-observabilidade-design.md`

## Global Constraints

- Nunca gravar `perfil`, histórico ou IP; só `tinha_suap` e `visitante` = HMAC-SHA256(`LOG_SECRET`, `ip + data do dia UTC`) em hex.
- Gravar nunca pode atrasar nem quebrar o chat: tarefa à parte, timeout de 3 s, erro vira `logger.warning` sem o texto da pergunta.
- Sem `DATABASE_URL`: nada é gravado, `/eventos` responde 204 sem fazer nada, site igual.
- Sem `ADMIN_TOKEN`: `/admin` e `/admin/api/*` respondem 404. Token comparado com `hmac.compare_digest`.
- Retenção: apagar `perguntas` com mais de 180 dias na subida e a cada 24 h; `eventos` em cascata.
- `resposta` até 20 000 caracteres; em `parada`/`erro` guarda o texto parcial.
- Rodapé, texto exato: "As perguntas e respostas são guardadas sem identificar você, para melhorar o PPChat. Seus dados do SUAP não são guardados. Não escreva dados pessoais nas perguntas."
- Commits sem trailer de co-autoria. Não dar push nem deploy sem o dono pedir.

## Review Focus

1. Cliente desconecta ou aperta "parar" → a linha ainda é gravada com `status="parada"` e o texto parcial (a gravação fica no `finally`, não depois do loop). Teste na Task 3.
2. Banco fora do ar ou acordando (Neon frio) → a resposta chega normal e no mesmo tempo. Teste na Task 3.
3. `/admin/api/*` sem token ou com token errado → 401, sem dados; tentativas além do limite → 429. Teste na Task 4.
4. Texto do aluno com `%`, aspas, `'; drop table` na busca do admin → só parâmetros SQL, nunca f-string com valor. Teste na Task 2.
5. Pergunta com `request_id` repetido ou não-UUID → não quebra (`ON CONFLICT DO NOTHING` / id do servidor). Teste na Task 3.

---

### Task 1: Interface de armazenamento, registro e versão em memória

**Files:**
- Create: `src/modules/observability/__init__.py`, `src/modules/observability/records.py`, `src/modules/observability/store.py`
- Create: `requirements-dev.txt` (`pytest`, `pytest-asyncio`), `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`), `tests/__init__.py`, `tests/test_records.py`

**Interfaces:**
- Produces:
  - `@dataclass QuestionRecord(id: UUID, curso: str, conversa: UUID | None, turno: int, pergunta: str, resposta: str, modelo: str, status: Literal["ok","parada","erro"], erro: str | None, duracao_ms: int, primeiro_texto_ms: int | None, tokens_saida: int | None, tinha_suap: bool, disciplinas: int, visitante: str)`; `pergunta_norm` é property.
  - `def normalize_question(text: str) -> str` — minúsculas, sem acentos (`unicodedata` NFKD), espaços colapsados, sem `?!.` no fim.
  - `def visitor_hash(ip: str, secret: str, day: date) -> str`
  - `EventType = Literal["voto", "copiou", "abriu_pagina"]`; `def valid_event(tipo: str, valor: str) -> bool` — `voto` ∈ {up, down, nenhum}; `abriu_pagina` = inteiro 1–2000; `copiou` = "".
  - `class Store(Protocol)`: `async def save_question(r: QuestionRecord) -> None`; `async def save_event(pergunta_id: UUID, tipo: EventType, valor: str) -> bool` (False se a pergunta não existe); `async def purge(days: int = 180) -> None`; `async def close() -> None`
  - `class MemoryStore(Store)` com `questions: dict[UUID, QuestionRecord]` e `events: list[tuple]` (para os testes)
  - `class NullStore(Store)` — não faz nada; `save_event` devolve True

- [ ] **Step 1: Write the failing tests**

```python
def test_normalize_question():
    assert normalize_question("  Como FUNCIONA o TCC?? ") == normalize_question("como funciona o tcc") == "como funciona o tcc"
    assert normalize_question("Estágio é obrigatório?") == "estagio e obrigatorio"

def test_visitor_hash_changes_by_day_and_hides_ip():
    a = visitor_hash("1.2.3.4", "s", date(2026, 11, 27)); b = visitor_hash("1.2.3.4", "s", date(2026, 11, 28))
    assert a != b and "1.2.3.4" not in a and len(a) == 64

def test_valid_event():
    assert valid_event("voto", "up") and valid_event("voto", "nenhum") and valid_event("abriu_pagina", "12")
    assert not valid_event("voto", "x") and not valid_event("abriu_pagina", "-1") and not valid_event("outro", "")

async def test_memory_store_event_needs_existing_question(record):
    s = MemoryStore()
    assert not await s.save_event(record.id, "voto", "up")
    await s.save_question(record)
    assert await s.save_event(record.id, "voto", "up")
```

(`record` é fixture em `tests/conftest.py` que monta um `QuestionRecord` válido.)

- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests -q` → FAIL (módulo não existe).
- [ ] **Step 3: Implement** records.py e store.py.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: registro de perguntas e interface de armazenamento`

### Task 2: Store em Postgres (Neon)

**Files:**
- Create: `src/modules/observability/postgres_store.py`, `src/modules/observability/schema.sql`
- Modify: `requirements.txt` (+ `psycopg[binary]`, `psycopg-pool`, versões fixas atuais)
- Test: `tests/test_postgres_store.py` (pula tudo com `pytest.mark.skipif` se não houver `TEST_DATABASE_URL`)

**Interfaces:**
- Consumes: `QuestionRecord`, `Store`, `EventType` (Task 1)
- Produces:
  - `class PostgresStore(Store)`: `@classmethod async def open(url: str) -> PostgresStore` (cria pool `min_size=0, max_size=4`, roda `schema.sql`)
  - Consultas do admin, todas com `dias: int` e `curso: str | None`:
    - `async def summary(dias, curso) -> dict` — `{perguntas, visitantes, votadas, positivas, paradas, reformuladas, erros}`
    - `async def top_questions(dias, curso, limit=20) -> list[dict]` — `{pergunta, vezes}` agrupado por `pergunta_norm` (mostra a versão mais recente do texto)
    - `async def negatives(dias, curso, limit=50) -> list[dict]` — perguntas cujo último voto é `down`, com `resposta`
    - `async def questions(dias, curso, busca: str | None, pagina: int, por_pagina=30) -> dict` — `{itens: [...], total}`; cada item com `voto` (último), `copiou`, `abriu_pagina`, `reformulou`, `abandonou`, `status`
- Schema (`schema.sql`, idempotente): tabelas da spec + `pergunta_norm text`; `eventos.pergunta_id uuid references perguntas(id) on delete cascade`; índices em `perguntas(criado_em)`, `perguntas(conversa, turno)`, `eventos(pergunta_id, criado_em)`.
- Derivados em SQL: último voto = `distinct on (pergunta_id) ... order by criado_em desc`; **reformulou** = existe pergunta na mesma `conversa` com `turno + 1` e `criado_em` até 2 min depois de `criado_em + duracao_ms`, e o último voto da atual não é `up`; **abandonou** = não existe `turno + 1` na conversa, sem voto final e sem cópia.

- [ ] **Step 1: Write the failing tests**

```python
async def test_roundtrip_and_cascade(pg, record):
    await pg.save_question(record); await pg.save_question(record)  # repetido não quebra
    assert await pg.save_event(record.id, "voto", "down")
    assert (await pg.negatives(7, None))[0]["pergunta"] == record.pergunta
    await pg.purge(days=-1)
    assert (await pg.summary(7, None))["perguntas"] == 0

async def test_last_vote_wins(pg, record):
    await pg.save_question(record)
    for v in ("up", "down", "nenhum"): await pg.save_event(record.id, "voto", v)
    s = await pg.summary(7, None); assert s["votadas"] == 0

async def test_reformulou(pg, make_record):
    conv = uuid4(); a = make_record(conversa=conv, turno=0); b = make_record(conversa=conv, turno=1)
    await pg.save_question(a); await pg.save_question(b)
    assert (await pg.summary(7, None))["reformuladas"] == 1

async def test_search_is_parameterized(pg, make_record):
    await pg.save_question(make_record(pergunta="100% do curso? ' drop table perguntas; --"))
    assert (await pg.questions(7, None, "100%", 1))["total"] == 1
    assert (await pg.questions(7, None, "'; drop", 1))["total"] == 1
```

(`pg` fixture: `PostgresStore.open(TEST_DATABASE_URL)` e `truncate perguntas cascade` antes de cada teste.)

- [ ] **Step 2: Run** com `TEST_DATABASE_URL` do branch `dev` → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS (e sem a variável, tudo `skipped`).
- [ ] **Step 5: Commit** — `feat: armazenamento das perguntas e consultas do admin no Postgres`

### Task 3: API grava perguntas e recebe eventos

**Files:**
- Modify: `src/modules/shared/services/settings.py` (+ `database_url: Optional[str]`, `admin_token: Optional[str]`, `log_secret: Optional[str]`, `log_retention_days: int = 180`)
- Modify: `src/modules/api/app.py` (`ChatRequest.conversa: Optional[UUID]`, lifespan abre o store e agenda o `purge`, `_stream_answer` e `/chat` gravam, novo `POST /eventos`)
- Create: `src/modules/observability/recorder.py`
- Test: `tests/test_api_observability.py`

**Interfaces:**
- Consumes: `Store`, `MemoryStore`, `NullStore`, `QuestionRecord`, `visitor_hash`, `valid_event` (Task 1); `PostgresStore.open` (Task 2)
- Produces:
  - `def get_store() -> Store` / `def set_store(store: Store) -> None` (os testes trocam por `MemoryStore`)
  - `def record_in_background(record: QuestionRecord) -> None` — `asyncio.create_task` com `wait_for(..., 3)`, guarda a referência da task num `set` até terminar
  - `POST /eventos` body `{pergunta_id: UUID, tipo: str, valor: str = ""}` → 204; 400 se `valid_event` falhar; 404 se a pergunta não existe; limite `RateLimiter(per_ip=120, global_limit=5000)`
  - `request_id` que não é UUID → o servidor usa `uuid4()` para o registro (o cancelamento continua pelo id original)
  - Ingredientes do registro: `turno = len(history) // 2`, `modelo = settings.llm_model`, `tokens_saida` de `_usage`, `primeiro_texto_ms` = tempo até o primeiro evento `text`, `erro` = nome da classe da exceção (nunca `str(error)`), `tinha_suap = bool(perfil)`, `disciplinas = len(disciplinas)`
  - Se `LOG_SECRET` estiver vazio com `DATABASE_URL` definido, o servidor não sobe (erro claro na subida)

- [ ] **Step 1: Write the failing tests** (TestClient; `ChatSession.stream_events` trocado por um gerador falso)

```python
def test_stream_records_ok(client, store, fake_answer):
    fake_answer(["Olá", " mundo"])
    client.post("/chat/stream", json={"question": "Q?", "curso": "analise-e-desenvolvimento-de-sistemas", "request_id": str(rid), "perfil": "DADOS"}).read()
    r = wait_for_record(store, rid)
    assert r.status == "ok" and r.resposta == "Olá mundo" and r.tinha_suap and "DADOS" not in repr(r)

def test_stopped_answer_is_recorded_with_partial_text(client, store, fake_answer): ...  # gerador levanta CancelledError depois de "Ol" → status "parada", resposta "Ol"
def test_error_records_class_name_not_message(client, store, fake_answer): ...  # RuntimeError("sk-segredo") → erro == "RuntimeError"
def test_db_failure_does_not_break_chat(client, failing_store, fake_answer): ...  # resposta 200 completa
def test_non_uuid_request_id_still_recorded(client, store, fake_answer): ...
def test_event_unknown_question_404_and_bad_value_400(client, store): ...
def test_no_database_means_events_204(client_null_store): ...
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (gravação no `finally` do `produce`, com o status decidido pelo que aconteceu). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: chat grava perguntas e respostas em segundo plano, e recebe 👍/👎`

### Task 4: Página /admin

**Files:**
- Create: `src/modules/api/admin.py` (`APIRouter`), `src/modules/api/static/admin.html`, `src/modules/api/static/admin.js`, `src/modules/api/static/admin.css` (reusa variáveis de cor de `styles.css`)
- Modify: `src/modules/api/app.py` (incluir o router **antes** do catch-all `/{slug}`)
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: `get_store()` (Task 3); `summary`, `top_questions`, `negatives`, `questions` (Task 2)
- Produces:
  - `GET /admin` → `admin.html` com `X-Robots-Tag: noindex` e `<meta name="robots" content="noindex">`; 404 sem `ADMIN_TOKEN`
  - `GET /admin/api/resumo|mais-feitas|negativas|perguntas` com `dias ∈ {7, 30, 90}` (padrão 7), `curso` opcional (só slugs do registro), `pagina ≥ 1`, `busca ≤ 200` chars; `Authorization: Bearer <token>`; 401 sem/errado; limite de 10 erros de token por IP por hora → 429
  - Com `NullStore` (sem banco): as rotas respondem 503 "Banco não configurado"
  - Front do admin: pede a senha, guarda em `sessionStorage` (`try/catch`), cartões de números, listas "Mais feitas", "👎 recentes" (resposta em `<details>`), "Todas" com busca e paginação; sinais como etiquetas pequenas; filtro de período e curso no topo; funciona a 375 px. Todo texto vindo do banco entra via `textContent` (nunca `innerHTML`); respostas em markdown passam por `DOMPurify` como no chat.

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_404_without_token_configured(client_no_admin): assert client_no_admin.get("/admin").status_code == 404
def test_admin_api_requires_token(client): assert client.get("/admin/api/resumo").status_code == 401
def test_admin_api_wrong_token_rate_limited(client):
    codes = [client.get("/admin/api/resumo", headers={"Authorization": "Bearer x"}).status_code for _ in range(11)]
    assert codes[-1] == 429
def test_admin_page_noindex(client): assert client.get("/admin").headers["x-robots-tag"] == "noindex"
def test_admin_api_ok_with_token(client, pg_or_fake): ...  # 200 e chaves do resumo
def test_admin_not_shadowed_by_course_route(client): assert client.get("/admin").status_code != 404
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; abrir `/admin` no navegador local com o branch `dev` e conferir no notebook e a 375 px.
- [ ] **Step 5: Commit** — `feat: página /admin com perguntas, 👍/👎 e sinais`

### Task 5: Front do chat — 👍/👎, sinais e rodapé

**Files:**
- Modify: `src/modules/api/static/app.js` (`streamAnswer`, `ask`, `persist`, `renderFooter`, criação da conversa, clique em `.page-ref`)
- Modify: `src/modules/api/static/index.html` (rodapé sob o `.hint`), `src/modules/api/static/styles.css`

**Interfaces:**
- Consumes: `ChatRequest.conversa`, `POST /eventos` (Task 3)
- Produces:
  - `state.convId` passa a existir antes da primeira pergunta: `ask` cria `newConvId()` se nulo; `persist` usa esse id em vez de criar outro. `newConvId()` deve gerar UUID (`crypto.randomUUID`; sem ele, a conversa vai sem `conversa`).
  - Cada `entry` do assistente ganha `id` (= `request_id` daquela resposta) e `voto` (`"up" | "down" | undefined`), salvos na conversa.
  - `function sendEvent(id, tipo, valor = "")` — `fetch` com `keepalive: true`, erros ignorados; não manda nada se `id` não existir.
  - `renderFooter`: botões 👍 e 👎 (com `aria-pressed` e `title` "Boa resposta" / "Resposta ruim") ao lado de "Copiar", só quando `entry.id` existe; clicar marca/troca/desmarca e chama `sendEvent(id, "voto", up|down|nenhum)` + `persist()`. "Copiar" também chama `sendEvent(id, "copiou")`.
  - Clique em `.page-ref` dentro de uma resposta → `sendEvent(id, "abriu_pagina", página)` (delegação no `.msg-bot`, lendo o id do `entry`).
  - Rodapé com o texto exato das Global Constraints, pequeno, sob o `.hint`.

- [ ] **Step 1: Verificação manual** (sem testes de front no projeto), servidor local apontando para o branch `dev`: votar, trocar, desmarcar, copiar, abrir página, reabrir a conversa (voto continua marcado), conversa antiga sem `id` (sem botões), celular 375 px; conferir cada evento no `/admin` e com `select` no Neon. Prints em `prints/10-observabilidade/`.
- [ ] **Step 2: Commit** — `feat: 👍/👎 nas respostas, sinais de uso e aviso de privacidade`

### Task 6: Neon, configuração e verificação final

**Files:**
- Modify: `.env-example`, `render.yaml` (`DATABASE_URL`, `ADMIN_TOKEN`, `LOG_SECRET` com `sync: false`), `README.md` (seção "Observabilidade": o que é guardado, o que não é, como abrir o `/admin`)

- [ ] **Step 1:** No Neon (conector): projeto `ppchat`, região mais próxima do Brasil disponível, branch `dev` para testes; pegar as strings *pooled* de `main` e `dev`. Gravar a de `dev` só no `.env` local (`TEST_DATABASE_URL` e `DATABASE_URL`), nunca em arquivo versionado.
- [ ] **Step 2:** `venv/Scripts/python.exe -m pytest -q` → tudo PASS (incluindo os testes de Postgres contra `dev`); `ruff check` sem avisos novos nos arquivos tocados; rodar os 5 quality gates.
- [ ] **Step 3: Commit** — `docs: observabilidade no README e variáveis do Render`
- [ ] **Step 4:** Entregar ao dono os valores a colocar no Render (`DATABASE_URL` de `main`, `ADMIN_TOKEN` e `LOG_SECRET` gerados com `secrets.token_urlsafe(32)`), sem push até ele pedir.
