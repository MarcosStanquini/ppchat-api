# PPChat — chat sobre o Projeto Pedagógico de Curso

Assistente que responde perguntas sobre o PPC do Bacharelado em Engenharia de Software do IFSP São Carlos:
disciplinas, ementas, cargas horárias, pré-requisitos, estágio, TCC, extensão e regras do curso. Também
monta sequências de matrícula e estima a dificuldade de cada disciplina.

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

1. **Ingestão** (`python main.py ingest`, roda uma vez por versão do PDF)
   - `PdfLoader` + `TextCleaner`: extraem o texto, removem o cabeçalho repetido e mantêm as quebras de linha das tabelas.
   - `CurriculumExtractor`: o Claude lê o PPC e devolve, por saída estruturada, todas as disciplinas com código,
     semestre, carga horária, abordagem, laboratório, pré-requisitos (por código), tópicos e página do plano de
     ensino, além dos requisitos gerais (estágio, TCC, ACs, extensão).
   - Saída em `src/data/processed/` (`ppc.md`, `curriculo.json`, `manifest.json`). Se o hash do PDF não mudou, a etapa é pulada.
2. **Grafo** (`CurriculumGraph`, sem custo de API): pré-requisitos diretos e indiretos, o que cada disciplina
   libera, o que uma reprovação trava, cadeia crítica do curso, disciplinas-gargalo e um **índice de
   complexidade estimada** (0–10), que combina profundidade na cadeia (35%), base acumulada (25%), semestre (25%) e carga horária (15%).
3. **Chat** (`ChatSession`): o system prompt leva as instruções, o currículo com o grafo e o PPC completo.
   O bloco grande tem cache de 1 h; o histórico também é cacheado a cada turno. O modelo cita `[Página N]`
   e separa o que está no PPC do que é inferência (dificuldade, por exemplo).

### Modelo e custo

- Padrão: **Claude Opus 5.5** (`claude-opus-5-5`) pela API da Anthropic, com esforço `medium` no chat e `high` na extração.
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
python main.py ingest                 # processa o PDF (use --force para refazer)
python main.py chat                   # chat interativo no terminal
python main.py ask "Quais os pré-requisitos de Arquitetura de Software?"
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
- **Estrutura curricular** (botão no topo, em painel lateral):
  - **Árvore:** a disciplina em foco fica no centro, o que vem antes ramifica para a esquerda (azul, em camadas
    "logo antes", "2 etapas antes"…) e o que ela libera ramifica para a direita (laranja). Clicar num nó
    centraliza a árvore nele; o painel ao lado traz detalhes, "Adicionar ao chat" e atalhos de pergunta.
  - **Grade:** todas as disciplinas por semestre; clicar abre a árvore.
  - Busca e o modal "Regras do curso".
- **Detalhes:** botão para parar a resposta, conversa salva no navegador e tema claro/escuro.

### API

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| GET | `/health` | — | status e número de disciplinas |
| GET | `/curriculum` | — | currículo estruturado com a análise do grafo (usado pelo mapa) |
| GET | `/pdf` | — | o PPC em PDF (aceita `#page=N`) |
| POST | `/chat` | `{"question", "history", "disciplinas", "request_id"}` (só `question` é obrigatório) | `{"answer", "usage"}` |
| POST | `/chat/stream` | igual ao `/chat` | NDJSON: `thinking`, `text`, e por fim `done` (com `usage`) ou `error` |
| POST | `/chat/cancel/{request_id}` | — | 204; interrompe a resposta em andamento |

A API **não guarda conversas**: para continuar uma, mande em `history` as trocas anteriores
(`[{"role": "user", "text": "...", "disciplinas": []}, {"role": "assistant", "text": "..."}]`, até 30 mensagens).
O front faz isso sozinho com a conversa salva no navegador. Perguntas acima do limite por IP ou do teto global
recebem 429.

## Deploy no Render (plano gratuito)

O `render.yaml` já descreve o serviço. A base processada (`src/data/processed/`) está no repositório, então o
deploy não roda a ingestão nem gasta API.

1. Faça push do repositório para o GitHub.
2. No Render: **New → Blueprint**, escolha o repositório e confirme.
3. Quando ele pedir, cole a `ANTHROPIC_API_KEY`.
4. Defina um **limite de gastos** no console da Anthropic: o site é público e não tem login.

O plano gratuito dorme após 15 min sem uso; o primeiro acesso depois disso leva até 1 minuto, e o front mostra
"Acordando o servidor…". Se mudar o PDF, rode `python main.py ingest --force` localmente e commite a base nova.

## Configuração (`.env`)

| Variável | Padrão | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | chave da API da Anthropic |
| `LLM_MODEL` | `claude-opus-5-5` | modelo do chat |
| `EXTRACTION_MODEL` | igual ao `LLM_MODEL` | modelo da extração do currículo (roda uma vez por PDF) |
| `FALLBACK_MODEL` | `claude-opus-4-8` | usado só se o principal recusar |
| `CHAT_EFFORT` / `EXTRACTION_EFFORT` | `medium` / `high` | profundidade de raciocínio (`low` a `max`) |
| `RATE_LIMIT_PER_HOUR` / `GLOBAL_RATE_LIMIT_PER_HOUR` | `30` / `400` | perguntas por IP e teto do site inteiro por hora (`0` desliga) |

## Estrutura

```
src/modules/
├── ingestion/   # PDF → texto limpo; extração do currículo estruturado
├── knowledge/   # grafo de pré-requisitos e montagem do contexto
├── response/    # prompt do sistema e sessão de chat
├── api/         # FastAPI + interface web (static/)
└── shared/      # configurações e cliente da API da Anthropic
```
