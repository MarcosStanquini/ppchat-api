# PPChat com várias IAs — design

## Por quê
Hoje toda pergunta usa o Claude pela chave da API do dono, que paga por cada pergunta. O objetivo é
**cortar custos** e **dar liberdade** ao aluno: por padrão um modelo gratuito, o Claude do dono disponível
para teste, e a opção de o aluno usar a própria chave (GPT, Gemini ou Groq).

## Objetivos
- Modelo padrão **gratuito**, sem o aluno escolher nada: Gemini Flash (Google AI Studio, chave do dono,
  nível grátis). Quando a cota do Flash acabar, revezamento: Gemini Flash-Lite (cota própria) e depois um modelo
  grátis do OpenRouter com contexto longo.
- **Respostas guardadas**: pergunta ao gratuito sem dados do SUAP e sem histórico (ex.: as perguntas prontas da
  tela Explorar) é respondida uma vez e guardada por curso + pergunta normalizada; as próximas iguais saem do
  cache, sem chamar a IA.
- **Claude (teste)**: o Claude atual com a chave do dono, com limite de uso mais apertado.
- **Chave do aluno** (opcional): GPT, Gemini ou Groq, escolhendo o provedor e colando a chave. Sem Claude por
  enquanto, porque o Claude (teste) do dono já está disponível.
- O PPC inteiro continua indo no contexto (mesma qualidade de resposta e citações [Página N]).

## Não-objetivos
- Chave do aluno para o Claude (por enquanto).
- PPC enxuto e histórico encurtado para o gratuito (ficaram de fora desta versão).
- Busca por trechos (RAG); contas de usuário; guardar chaves no servidor.
- Trocar a ingestão (extração do currículo continua com Claude, rodada pelo dono).

## Anti-objetivos
- Chave do aluno gravada em disco, banco ou log do servidor.
- Aluno mandando o histórico do SUAP para um serviço gratuito sem saber que os dados podem ser usados.
- O site parar de responder quando a cota grátis acabar, sem explicar o que aconteceu.

## Abordagens consideradas (escolha do usuário: A)
- **A. Chave passa pelo servidor, sem ser guardada** — escolhida. A montagem da pergunta (PPC, currículo,
  perfil do SUAP, disciplinas em foco) fica num lugar só; cada provedor é um adaptador.
- B. Navegador fala direto com a IA — a chave nunca sai do navegador, mas duplica a montagem da pergunta e o
  tratamento do streaming em Python e JavaScript.

## Decisões do usuário
- Liberdade de escolha + corte de custos; o padrão é gratuito e não exige escolha.
- O Claude do dono fica disponível para teste.
- Chaves do aluno: GPT, Gemini e Groq, sem aviso sobre limites do nível grátis do Groq; sem Claude por enquanto.
- Otimizações do gratuito: respostas guardadas e revezamento entre modelos do Gemini.
- Abordagem A.
- **Gratuito esgotado** (Gemini e OpenRouter): só a mensagem "o gratuito atingiu o limite agora, tente mais
  tarde ou use sua chave". Nunca cai automaticamente no Claude do dono.
- **SUAP no gratuito: aceite uma vez.** Na primeira pergunta ao gratuito com o SUAP importado, o aviso oferece
  "Entendi, usar meus dados" ou "Perguntar sem meus dados"; o navegador lembra a escolha. Sem aceite, o front não
  manda o `perfil` e o servidor também o descarta para as opções gratuitas se a requisição não trouxer
  `consentimento_gratis: true`.

## Desenho
**Provedores (backend).** `ChatSession` deixa de chamar o SDK da Anthropic direto e passa a usar um
`ChatProvider` com uma única operação: transmitir a resposta (eventos `thinking`/`text`) a partir do mesmo
system prompt e histórico, e informar o uso de tokens no fim. Dois adaptadores:
- `AnthropicProvider`: o código atual (cache de 1 h, raciocínio resumido, fallback de recusa).
- `OpenAICompatibleProvider`: um só adaptador, com o SDK `openai`, para **OpenAI**, **Gemini** (endpoint
  compatível com OpenAI do Google), **Groq** e **OpenRouter** — muda só a URL base, a chave e o modelo. Dependência nova:
  `openai`. Nesses provedores não há resumo de raciocínio na tela.

**Opções de IA.** Registro fixo no servidor (`/models` devolve a lista para o front):
| id | rótulo | chave | limite |
|---|---|---|---|
| `gratis` | Gratuito | dono (`GEMINI_API_KEY`): Flash → Flash-Lite; reserva OpenRouter (`OPENROUTER_API_KEY`) | limite atual por IP/global; respostas guardadas não contam |
| `claude-teste` | Claude (teste) | dono (`ANTHROPIC_API_KEY`) | mais apertado por IP (ex.: 10/h) |
| `openai` / `gemini` / `groq` | Minha chave · GPT/Gemini/Groq | do aluno | só um limite leve por IP para proteger o servidor |
Modelos de cada opção vêm de variáveis de ambiente, com padrões no código.

**Pergunta.** `/chat` e `/chat/stream` ganham `modelo` (id da opção, padrão `gratis`) e `chave` (só para as
opções do aluno). A chave é usada naquela requisição e descartada: não vai para log, nem para mensagens de
erro, nem fica em memória depois da resposta. Clientes antigos sem `modelo` caem em `gratis`.

**Reserva do gratuito.** Se o Gemini Flash responder cota esgotada (429), a mesma pergunta vai para o Gemini
Flash-Lite e, se também esgotar, para o OpenRouter grátis. Se os dois falharem, o aluno vê uma mensagem clara: "O modelo gratuito atingiu o limite de uso agora.
Tente mais tarde ou use sua própria chave."

**Erros da chave do aluno.** Chave inválida (401/403) → "Sua chave do <provedor> foi recusada"; sem crédito/cota
(429/402) → mensagem própria. Nunca devolver o texto bruto do provedor (pode conter partes da chave).

**Front.** Um seletor discreto no campo de pergunta: "Gratuito ▾", com as opções e "Usar minha chave…". O
diálogo de chave pede provedor + chave, com "lembrar neste navegador" (localStorage; sem marcar, só na aba).
Aviso de privacidade ao usar o gratuito com o SUAP importado: o nível grátis pode usar os dados para melhorar os
produtos do provedor. Conversas salvas lembram qual IA respondeu (rótulo pequeno na resposta).

**Contexto e custo.** O PPC inteiro vai em todas as opções. Gemini e OpenAI reaproveitam a entrada repetida
automaticamente; a Anthropic mantém o cache explícito.

## Decisões do design (podem ser corrigidas pelo usuário)
- **Limites separados por opção**, cada uma com contador por IP e global próprios, para ninguém gastar o crédito
  do dono trocando de opção: `gratis` mantém 30/h por IP e 400/h no total; `claude-teste` 10/h por IP e 100/h
  no total (é a única que custa dinheiro ao dono); chave do aluno 60/h por IP, sem teto global.
- **Reserva do OpenRouter só antes do primeiro token**: 429, 5xx ou timeout do Gemini ao abrir a resposta. Se
  a falha vier no meio da resposta, ela termina com uma mensagem de erro (o protocolo NDJSON não muda).
- **Rótulo da resposta = quem de fato respondeu** ("Gratuito · Gemini", "Gratuito · OpenRouter",
  "Claude (teste)", "Minha chave · GPT"). O evento `done` leva `modelo` (opção) e `provedor` (quem respondeu);
  os campos de cache do `Usage` passam a ser opcionais (só o terminal e a resposta do `/chat` os usam).

## Para quem implementar decidir
Nomes exatos dos modelos padrão (verificar a lista atual de cada provedor na hora), visual do seletor e do
diálogo, texto final dos avisos, valor do limite do Claude (teste).
