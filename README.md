# PPChat — chat sobre o Projeto Pedagógico de Curso

Assistente que responde perguntas sobre os PPCs dos 6 cursos de graduação do IFSP São Carlos
(Engenharia de Software, Engenharia Aeronáutica, Administração, ADS, Processos Gerenciais e Manutenção de
Aeronaves): disciplinas, ementas, cargas horárias, pré-requisitos, estágio, TCC, extensão e regras do curso.
Também monta sequências de matrícula e estima a dificuldade de cada disciplina.

Sem o SUAP importado, o site abre na tela **Explorar cursos**. Importando o SUAP, o PPChat lê o curso na aba
"Dados Acadêmicos" e abre direto nele (**Meu curso**); dá para explorar os outros cursos a qualquer momento.
Cada curso tem endereço próprio (`/analise-e-desenvolvimento-de-sistemas`, `/administracao`...).

## Como funciona

O PPC tem cerca de 140 mil tokens (somando o currículo estruturado), o que cabe inteiro no contexto do Claude (1M tokens). Por isso o projeto
não usa busca vetorial: o modelo lê o documento todo a cada pergunta, e o prompt caching faz isso sair barato.
Com top-k de trechos, perguntas sobre dependências ("o que eu preciso antes de Arquitetura de Software?")
falhavam, porque a resposta fica espalhada pelo quadro de pré-requisitos, pela grade e pelos planos de ensino.

```
PDF ──► texto limpo com [Página N] ──────────────────────────────┐
   └──► Claude extrai o currículo (JSON validado com Pydantic)   │
              └──► grafo de pré-requisitos (cálculo local) ──────┤
                                                                 ▼
                        system prompt = instruções + currículo/grafo + PPC completo (cache de 1 h)
                                                                 ▼
                                               chat multi-turno com streaming
```

1. **Ingestão** (`python main.py ingest --curso <slug>|all`, roda uma vez por versão do PDF)
   - `PdfLoader` + `TextCleaner`: extraem o texto, removem cabeçalhos e rodapés repetidos (detectados em qualquer PPC, sem regex por curso) e mantêm as quebras de linha das tabelas.
   - `CurriculumExtractor`: o Claude lê o PPC e devolve, por saída estruturada, todas as disciplinas com código,
     semestre, carga horária, abordagem, laboratório, pré-requisitos (por código), tópicos e página do plano de
     ensino, além dos requisitos gerais (estágio, TCC, ACs, extensão).
   - Cada curso tem uma pasta em `src/data/courses/<slug>/` (`ppc.pdf`, `ppc.md`, `curriculo.json`, `manifest.json` e
     `notas.md` opcional com instruções específicas do curso para o prompt). O registro dos cursos fica em
     `src/data/courses/courses.json`. Se o hash do PDF não mudou, a etapa é pulada; `--sem-extracao` gera só o texto.
2. **Grafo** (`CurriculumGraph`, sem custo de API): pré-requisitos diretos e indiretos, o que cada disciplina
   libera, o que uma reprovação trava, cadeia crítica do curso, disciplinas-gargalo e um **índice de
   complexidade estimada** (0–10), que combina profundidade na cadeia (35%), base acumulada (25%), semestre (25%) e carga horária (15%).
3. **Chat** (`ChatSession`): o system prompt leva as instruções, o currículo com o grafo e o PPC completo.
   O bloco grande tem cache de 1 h; o histórico também é cacheado a cada turno. O modelo cita `[Página N]`
   e separa o que está no PPC do que é inferência (dificuldade, por exemplo).

### Modelos de IA

O aluno escolhe quem responde num seletor discreto no campo de pergunta ("Gratuito ▾"):

| Opção | Quem responde e quem paga | Limite por hora |
|---|---|---|
| **Gratuito** (padrão) | as **2 primeiras perguntas do dia** de cada pessoa saem do Claude do dono; depois, Gemini Flash-Lite no nível grátis (chave do dono) | 30 por IP, 400 no total; Claude do dono: no máximo 100 por hora no site inteiro |
| **Minha chave** (GPT, Gemini, Groq ou Claude) | o aluno, com a própria chave | 60 por IP |

- **Gratuito:** a cota do Claude é por IP e por dia (horário de Brasília), em memória (zera num deploy). Se o
  Claude falhar ou a cota acabar, a pergunta vai ao Gemini antes de sair qualquer texto. Se o Gemini também
  esgotar, o aluno vê "O modelo gratuito atingiu o limite de uso agora. Tente mais tarde ou use sua própria
  chave." Perguntas sem SUAP, sem histórico e sem disciplinas em foco (como as da tela Explorar) são respondidas
  uma vez e guardadas em memória por 7 dias; as repetidas não chamam a IA nem gastam cota.
- **SUAP:** vai normalmente ao Claude do dono e à chave do aluno. Para o Gemini grátis (que pode usar os dados),
  só com o aceite do aluno (`consentimento_gratis`), pedido uma vez no navegador; sem aceite, o servidor tira os
  dados do SUAP da pergunta que vai ao Gemini.
- **Chave do aluno:** passa pelo servidor só naquela pergunta; não vai para log, banco nem mensagem de erro. No
  navegador fica só na aba, ou no `localStorage` se o aluno marcar "lembrar neste navegador".
- **Contexto:** o PPC inteiro (72 a 141 mil tokens, conforme o curso) vai em todas as opções. Os modelos estáveis
  do Groq aceitam no máximo 131 mil tokens, por isso o padrão do Groq é o `minimaxai/minimax-m2.7` (prévia, 196
  mil); troque com `GROQ_MODEL` se ele sair do ar.
- **Chave do dono para o Gemini:** `GEMINI_API_KEY` em <https://aistudio.google.com> (Get API key; sem cartão).
  As cotas grátis por modelo aparecem em <https://aistudio.google.com/rate-limit>; como cada pergunta manda o PPC
  inteiro, o limite de tokens por minuto costuma ser o primeiro a acabar. `OPENROUTER_API_KEY` (opcional) acrescenta
  o roteador grátis do OpenRouter como última reserva.
- Num teste com 8 perguntas reais, o Gemini Flash-Lite respondeu todas em 2 a 3 s até a primeira palavra, com
  qualidade parecida com a do Claude Haiku; o Gemini Flash demorou de 5 a 55 s e falhou 3 vezes, por isso ficou de fora.

### Claude: modelo e custo

- Padrão do Claude (2 perguntas por dia no gratuito): **Claude Opus 5.5** (`claude-opus-5-5`) pela API da Anthropic, com esforço `medium` no chat e `high` na extração.
- Se o modelo recusar uma pergunta, o middleware do SDK repete a requisição no `FALLBACK_MODEL` (Opus 4.8).
- Custo aproximado (Opus 5.5: US$ 4 / 1M tokens de entrada, US$ 20 / 1M de saída, US$ 0,20 / 1M lidos do cache):
  cada pergunta lê ~140 mil tokens do cache (~US$ 0,03) mais a resposta. A primeira pergunta de cada hora grava o
  cache de 1 h (2× o preço de entrada, ~US$ 1,10). Confira os valores atuais em <https://www.anthropic.com/pricing>.
- O chat mostra no terminal quantos tokens vieram do cache, para você conferir; a API devolve o mesmo em `usage` no `/chat`.
- Para gastar menos, use os modelos do `.env-example` (Haiku 5.5 no chat): em teste, cerca de 1 centavo de dólar por pergunta.

## Instalação

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp .env-example .env           # preencha ANTHROPIC_API_KEY
```

A chave é criada em <https://platform.claude.com/settings/keys>.

## Uso

```bash
python main.py ingest --curso all     # processa os PDFs (use --force para refazer)
python main.py chat --curso administracao   # chat interativo no terminal
python main.py ask --curso engenharia-de-software "Quais os pré-requisitos de Arquitetura de Software?"
python main.py serve --port 8000      # API + interface web em http://localhost:8000
```

### Interface web

Ao rodar `serve`, abra <http://localhost:8000>. Não há build nem login: é HTML, CSS e JS puros em
`src/modules/api/static/`.

- **Chat com streaming:** respostas em markdown com tabelas; enquanto o modelo pensa, aparece uma
  linha com o resumo do raciocínio, que vira "Raciocinou por Xs" e pode ser expandida. O resumo vem em inglês.
- **Disciplinas no contexto:** digite `@` (ou use o botão do livro) para escolher disciplinas. Elas viram chips
  acima do campo, e a ficha completa de cada uma (pré-requisitos, o que libera, tópicos, complexidade) vai
  junto da pergunta.
- **Citações clicáveis:** `[Página N]` vira um chip que abre o PDF naquela página; códigos como `SCLPROO`
  abrem a árvore da disciplina.
- **Estrutura curricular** (botões Fluxograma e Meu percurso no topo, em tela cheia):
  - **Fluxograma**, em dois modos:
    - **Conexões:** a disciplina em foco fica no centro, o que vem antes ramifica para a esquerda (azul, em camadas
      "logo antes", "2 etapas antes"…) e o que ela libera ramifica para a direita (laranja). Clicar num nó
      centraliza nele; o painel ao lado traz detalhes, "Adicionar ao chat" e atalhos de pergunta.
    - **Grade:** todas as disciplinas por semestre; clicar abre as conexões.
  - **Meu percurso** (com o SUAP conectado): trilha em serpente com os semestres já cursados, o atual e uma previsão
    até a formatura (pelos pré-requisitos e pelo semestre de oferta na matriz). Clicar num semestre mostra as
    disciplinas, notas e frequência; a formatura mostra os requisitos e as atividades complementares.
  - Busca e o modal "Regras do curso".
- **Conversas:** lista lateral com as conversas salvas só no navegador (título automático pela primeira pergunta,
  renomear e apagar); com a marca e o "Novo chat" no topo, como a do ChatGPT. Fechada, o cabeçalho mostra o botão de abrir, a marca e o novo chat; no celular ela abre por cima.
- **Detalhes:** botão para parar a resposta e menu Ajustes (tema claro/escuro/sistema, opções de exibição e o PDF do PPC).

### API

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| GET | `/health` | — | status e número de disciplinas |
| GET | `/curriculum` | — | currículo estruturado com a análise do grafo (usado pelo mapa) |
| GET | `/pdf` | — | o PPC em PDF (aceita `#page=N`) |
| GET | `/models` | — | opções de IA do seletor (`id`, `label`, `own_key`) |
| POST | `/chat` | `{"question", "history", "disciplinas", "request_id", "modelo", "chave", "consentimento_gratis"}` (só `question` é obrigatório; sem `modelo` = `gratis`) | `{"answer", "usage", "modelo", "provedor", "cache"}` |
| POST | `/chat/stream` | igual ao `/chat` | NDJSON: `thinking`, `text`, e por fim `done` (com `usage`, `modelo`, `provedor`, `cache`) ou `error` |
| POST | `/chat/cancel/{request_id}` | — | 204; interrompe a resposta em andamento |

A API **não guarda conversas**: para continuar uma, mande em `history` as trocas anteriores
(`[{"role": "user", "text": "...", "disciplinas": []}, {"role": "assistant", "text": "..."}]`, até 30 mensagens).
O front faz isso sozinho com a conversa salva no navegador. Perguntas acima do limite por IP ou do teto global
recebem 429.

## Dados do aluno via SUAP (bookmarklet)

O SUAP do IFSP não oferece, na API, as notas e o histórico do aluno, e o login da página web tem reCAPTCHA. Por
isso o PPChat **não pede senha**: o aluno arrasta o favorito "PPChat ← SUAP" (botão **Conectar SUAP** no topo) e o
clica com o SUAP já aberto.

1. O script (`static/suap-export.js`) roda dentro do SUAP com a sessão do próprio aluno e lê só as abas acadêmicas
   (dados acadêmicos, requisitos de conclusão, histórico, boletins e atividades complementares e de extensão).
   Dados pessoais e bancários ficam de fora. Antes de enviar, mostra o que leu.
2. Envia as tabelas para `POST /aluno/importar` (CORS liberado só para `SUAP_ORIGINS`) e recebe um código de uso
   único que expira em 1 hora. O servidor guarda os dados só em memória.
3. Abre o PPChat com `#suap=<código>`. O front troca o código pelos dados (`GET /aluno/importar/{código}`), apaga o
   código da URL e guarda tudo **só no navegador**. Dá para remover a qualquer momento no mesmo botão.
4. A situação de cada disciplina (feita, cursando, reprovada) vem do código `SCL…` ou do nome na tabela. As
   "liberadas" são calculadas pelo grafo de pré-requisitos. Um resumo vai junto de cada pergunta (`perfil`), e a
   árvore vira um mapa de progresso.

O leitor é genérico (descobre as abas pelos links e extrai todas as tabelas), mas se o SUAP mudar muito, ajuste os
padrões em `suap-export.js` (abas) e em `buildAluno` no `app.js` (situações).

## Observabilidade (página `/admin`)

Cada pergunta ao chat vira um registro num Postgres (Neon, plano grátis): curso, pergunta, resposta, modelo,
tempo, desfecho (`ok`, `parada` ou `erro`) e os sinais do aluno: 👍/👎 embaixo da resposta, cópia e clique em
[p. N]. Reformulou (nova pergunta na mesma conversa até 2 min depois) e saiu depois são calculados na consulta.

- **Não é guardado:** os dados do SUAP (só "tinha SUAP: sim/não"; a resposta de quem importou o SUAP também
  não é guardada, porque costuma repetir notas e matrícula), o histórico enviado pelo navegador e o IP. O
  visitante vira um código que muda a cada dia (HMAC do IP com `LOG_SECRET`). Registros com mais de 180 dias são
  apagados. O rodapé do chat avisa o aluno.
- **Gravação fora do caminho da resposta:** em segundo plano, com limite de 3 s; banco fora do ar só gera aviso
  no log e o chat segue igual. Sem `DATABASE_URL`, nada é gravado.
- **Ver:** abra `/admin` e entre com o `ADMIN_TOKEN` (fica só na aba). Sem `ADMIN_TOKEN` configurado, `/admin`
  responde 404. Mostra números do período (7/30/90 dias), perguntas mais feitas, 👎 recentes e todas as
  perguntas com busca.
- **Custos da Anthropic:** com `ANTHROPIC_ADMIN_KEY` (chave de administração, criada no Console em Settings →
  Admin keys), o `/admin` mostra o gasto real do período, por dia e por modelo (com 4 a 24 h de atraso; guardado
  em memória por 30 min). A API não informa o saldo: digite no `/admin` o saldo que o Console mostra e o painel
  passa a mostrar esse valor menos o gasto desde então. A chave fica só no servidor e só lê custos.
- **Testes:** `pip install -r requirements-dev.txt` e `pytest`. Os testes de Postgres usam `TEST_DATABASE_URL`
  (um branch separado do Neon) e são pulados sem ela; eles apagam as tabelas desse banco a cada teste.

## Deploy no Render (plano gratuito)

O `render.yaml` já descreve o serviço. A base processada (`src/data/courses/`) está no repositório, então o
deploy não roda a ingestão nem gasta API.

1. Faça push do repositório para o GitHub.
2. No Render: **New → Blueprint**, escolha o repositório e confirme.
3. Quando ele pedir, cole a `ANTHROPIC_API_KEY` e a `GEMINI_API_KEY`.
4. Defina um **limite de gastos** no console da Anthropic: o site é público e não tem login.

O plano gratuito dorme após 15 min sem uso; o primeiro acesso depois disso leva até 1 minuto, e o front mostra
"Acordando o servidor…". Se mudar o PDF, rode `python main.py ingest --curso <slug> --force` localmente e commite a base nova.

## Configuração (`.env`)

| Variável | Padrão | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | chave da API da Anthropic |
| `LLM_MODEL` | `claude-opus-5-5` | modelo do chat |
| `EXTRACTION_MODEL` | igual ao `LLM_MODEL` | modelo da extração do currículo (roda uma vez por PDF) |
| `FALLBACK_MODEL` | `claude-opus-4-8` | usado só se o principal recusar |
| `CHAT_EFFORT` / `EXTRACTION_EFFORT` | `medium` / `high` | profundidade de raciocínio (`low` a `max`) |
| `RATE_LIMIT_PER_HOUR` / `GLOBAL_RATE_LIMIT_PER_HOUR` | `30` / `400` | limite do gratuito: perguntas por IP e teto do site inteiro por hora (`0` desliga) |
| `GEMINI_API_KEY` | — | chave do dono no Google AI Studio, para o gratuito |
| `GEMINI_MODELS` | `["gemini-3.5-flash-lite"]` | modelos do Gemini no gratuito, tentados em ordem |
| `CLAUDE_FREE_PER_DAY` / `CLAUDE_FREE_GLOBAL_PER_HOUR` | `2` / `100` | perguntas do Claude do dono no gratuito, por pessoa por dia e no site por hora (`0` desliga) |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | — / `openrouter/free` | reserva do gratuito (opcional) |
| `OPENAI_MODEL` / `GEMINI_BYOK_MODEL` / `GROQ_MODEL` / `CLAUDE_BYOK_MODEL` | `gpt-6-luna` / `gemini-3.5-flash-lite` / `minimaxai/minimax-m2.7` / igual ao `LLM_MODEL` | modelos usados com a chave do aluno |
| `DATABASE_URL` | — | Postgres das perguntas (string *pooled* do Neon); vazio = não grava |
| `ADMIN_TOKEN` | — | senha da página `/admin`; vazio = `/admin` não existe |
| `LOG_SECRET` | — | chave do código diário de visitante; obrigatória com `DATABASE_URL` |
| `ANTHROPIC_ADMIN_KEY` | — | chave de administração da Anthropic, só para os custos no `/admin`; vazio = cartão "não configurado" |
| `LOG_RETENTION_DAYS` | `180` | dias até os registros serem apagados |

## Estrutura

```
src/modules/
├── ingestion/   # PDF → texto limpo; extração do currículo estruturado
├── knowledge/   # grafo de pré-requisitos e montagem do contexto
├── response/    # prompt do sistema e sessão de chat
├── api/         # FastAPI + interface web (static/)
└── shared/      # configurações e cliente da API da Anthropic
```
