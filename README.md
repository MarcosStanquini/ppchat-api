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
- **Citações clicáveis:** `[Página N]` vira um chip que abre o PDF naquela página; códigos como `SCLPROO`
  viram chips que destacam a disciplina no mapa.
- **Mapa curricular interativo:** grade por semestre com nível de complexidade estimada. Ao clicar numa
  disciplina, aparecem setas para os pré-requisitos (azul) e para o que ela libera (laranja), além de um painel
  com detalhes e atalhos de pergunta. Há busca, destaque da cadeia crítica e o modal "Regras do curso".
- **Detalhes:** botão para parar a resposta, conversa salva no navegador, tema claro/escuro e layout com abas no celular.

### API

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| GET | `/health` | — | status e número de disciplinas |
| GET | `/curriculum` | — | currículo estruturado com a análise do grafo (usado pelo mapa) |
| GET | `/pdf` | — | o PPC em PDF (aceita `#page=N`) |
| POST | `/chat` | `{"question": "...", "session_id": null}` | `{"session_id", "answer", "usage"}` |
| POST | `/chat/stream` | igual ao `/chat` | NDJSON: `thinking`, `text`, e por fim `done` (com `usage`) ou `error`; `session_id` no header `X-Session-Id` |
| POST | `/chat/{session_id}/cancel` | — | 204; interrompe a resposta em andamento e descarta a pergunta |

Mande o `session_id` recebido nas próximas perguntas para continuar a conversa. As sessões ficam em memória
no processo da API. Uma sessão responde uma pergunta por vez; enquanto responde, outra pergunta recebe 409.

## Configuração (`.env`)

| Variável | Padrão | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | chave da API da Anthropic |
| `LLM_MODEL` | `claude-opus-5-5` | modelo do chat |
| `EXTRACTION_MODEL` | igual ao `LLM_MODEL` | modelo da extração do currículo (roda uma vez por PDF) |
| `FALLBACK_MODEL` | `claude-opus-4-8` | usado só se o principal recusar |
| `CHAT_EFFORT` / `EXTRACTION_EFFORT` | `medium` / `high` | profundidade de raciocínio (`low` a `max`) |

## Estrutura

```
src/modules/
├── ingestion/   # PDF → texto limpo; extração do currículo estruturado
├── knowledge/   # grafo de pré-requisitos e montagem do contexto
├── response/    # prompt do sistema e sessão de chat
├── api/         # FastAPI + interface web (static/)
└── shared/      # configurações e cliente da API da Anthropic
```
