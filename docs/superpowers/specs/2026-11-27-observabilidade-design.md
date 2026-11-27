# Observabilidade de perguntas e respostas — design

## Por quê
O dono quer saber **o que os alunos estão perguntando** e **o que estão achando das respostas**, sem
formulário de feedback. Hoje nada é guardado: a API não tem estado e as conversas vivem só no navegador.

## Objetivos
- Cada pergunta ao chat vira um registro: curso, pergunta, resposta, quem respondeu, tempo, erro.
- Opinião sem formulário: um 👍/👎 discreto embaixo de cada resposta, mais sinais automáticos do que o aluno faz.
- Página `/admin`, com senha, para o dono ver tudo no notebook ou no celular.

## Não-objetivos
- Contas de usuário ou identificar quem perguntou.
- Gráficos elaborados, exportação, alertas por e-mail.
- Classificar perguntas por assunto com IA (dá para fazer depois consultando o Neon pelo conector).

## Anti-objetivos
- O chat ficar mais lento ou parar de responder porque o banco caiu ou está acordando.
- Guardar os dados do SUAP do aluno, o IP real, ou o texto do histórico enviado pelo navegador.
- A página `/admin` acessível sem senha ou aparecendo em buscadores.

## Abordagens consideradas (escolha do usuário: A)
- **A. Página `/admin` no próprio PPChat** — escolhida: o dono olha quando quiser, sem depender de ninguém.
- B. Só gravar no Neon e consultar pelo editor SQL ou pedindo ao Claude — mais rápido de fazer, mas exige SQL
  ou intermediário. Continua possível pelo conector do Neon.
- Banco: Neon (escolha do usuário) em vez de Supabase (o grátis pausa após 7 dias sem uso) ou disco do Render
  (apaga a cada deploy).

## Decisões do usuário
- Sem formulário; com 👍/👎.
- Banco Postgres no Neon (plano grátis).
- Página `/admin` com senha.

## Desenho

**Banco.** Projeto `ppchat` no Neon, região mais perto do Brasil disponível. O servidor lê `DATABASE_URL`
(string *pooled* do Neon); sem ela (ex.: no PC do dono), nada é gravado e o site funciona igual. As tabelas são
criadas na subida do servidor com `CREATE TABLE IF NOT EXISTS` (sem ferramenta de migração).

- `perguntas`: `id` (uuid = `request_id` gerado pelo navegador), `criado_em`, `curso`, `conversa` (id
  aleatório da conversa no navegador), `turno` (posição na conversa), `pergunta`, `resposta` (até 20 mil
  caracteres), `modelo`, `status` (`ok` | `parada` | `erro`), `erro` (tipo curto, nunca o texto bruto),
  `duracao_ms`, `primeiro_texto_ms`, `tokens_saida`, `tinha_suap` (bool), `disciplinas` (quantidade em foco),
  `visitante` (hash).
- `eventos`: `id`, `pergunta_id`, `criado_em`, `tipo` (`voto` | `copiou` | `abriu_pagina`), `valor`
  (`up`/`down`/`nenhum` para voto; número da página para `abriu_pagina`).

**Gravação.** Quando a resposta termina (ok, parada pelo aluno, erro ou cliente desconectado), o servidor grava
a linha numa tarefa à parte, com tempo máximo curto; falha no banco só gera um aviso no log, sem o conteúdo da
pergunta. Vale para `/chat/stream` e `/chat`. Pergunta sem `request_id` (cliente antigo) ganha um id do servidor.

**Privacidade.** Não grava `perfil` (só `tinha_suap`), nem o histórico, nem o IP. `visitante` =
HMAC-SHA256 do IP com uma chave secreta (`LOG_SECRET`) e a data do dia: dá para contar visitantes diferentes por
dia, mas não ligar um dia ao outro nem voltar ao IP. Registros com mais de 180 dias são apagados na subida do
servidor. Rodapé fixo sob o campo de pergunta: "As perguntas e respostas são guardadas sem identificar você,
para melhorar o PPChat. Seus dados do SUAP não são guardados. Não escreva dados pessoais nas perguntas."

**Sinais.** O front manda eventos para `POST /eventos` (`{pergunta_id, tipo, valor}`), com limite por IP e só
para ids que existem:
- 👍/👎 ao lado de "Copiar": clicar marca, clicar de novo desmarca, trocar substitui. Vale o último voto. A
  escolha fica salva na conversa do navegador para os botões aparecerem marcados ao reabrir.
- "Copiar" e clique em [p. N] da resposta.
- Derivados na própria consulta do `/admin`, sem evento: **parada** (status), **reformulou** (nova pergunta na
  mesma conversa até 2 min depois do fim da anterior, sem 👍 na anterior), **abandonou** (última pergunta da
  conversa, sem voto nem cópia).
- Respostas de conversas antigas (sem id) não mostram 👍/👎.

**Página `/admin`.** HTML próprio (mesmo visual do site), `noindex`. Pede a senha uma vez e guarda na aba
(`sessionStorage`); os dados vêm de `GET /admin/api/...` com `Authorization: Bearer <ADMIN_TOKEN>`, comparado em
tempo constante; tentativas erradas têm limite por IP. Sem `ADMIN_TOKEN` configurado, `/admin` responde 404.
Conteúdo, com filtro de período (7, 30, 90 dias) e de curso:
- Números: perguntas, visitantes, % de 👍 entre as votadas, % paradas, % reformuladas, erros.
- Perguntas mais feitas (texto normalizado: minúsculas, sem acento e pontuação final), com contagem.
- 👎 recentes, com a resposta ao abrir.
- Todas as perguntas, mais novas primeiro, paginadas, com busca por texto e os sinais de cada uma.

**Configuração.** Novas variáveis no Render: `DATABASE_URL`, `ADMIN_TOKEN`, `LOG_SECRET` (secretas,
`sync: false` no `render.yaml`); documentadas no `.env-example`. Dependência nova: driver Postgres assíncrono
(`psycopg[binary]` com pool).

**Relação com o multi-IA** (pausado em `feat/multi-ia`). `modelo` guarda hoje o `settings.llm_model`; quando o
multi-IA entrar, passa a guardar o rótulo de quem respondeu ("Gratuito · Gemini" etc.).

## Decisões do design (podem ser corrigidas pelo usuário)
- **Ids.** O navegador já gera um `request_id` novo (UUID) a cada envio; o servidor só aceita UUID válido
  (senão gera um) e grava com `ON CONFLICT DO NOTHING`. `ChatRequest` ganha `conversa` (UUID opcional): o front
  passa a criar o id da conversa antes da primeira pergunta. `turno` = `len(history) // 2`, calculado no
  servidor (com histórico cortado em 30 mensagens, é a posição dentro do que foi enviado).
- **IP.** `visitante` e os limites de `/eventos` e da senha usam o mesmo `client_ip` do limite atual; contagem
  de visitantes é aproximada (dá para forjar o cabeçalho), aceitável para esse uso. A senha forte é a proteção real.
- **Votos e eventos.** Linhas acumulam; desmarcar grava `voto=nenhum`; vale o último voto por pergunta.
  % 👍 = 👍 / (👍 + 👎) entre perguntas com voto final. Cópias e cliques em página contam perguntas com pelo menos
  um (não cliques). `/eventos` só aceita ids de perguntas existentes.
- **Retenção.** Apaga registros com mais de 180 dias na subida e a cada 24 h; `eventos.pergunta_id` com
  `ON DELETE CASCADE`.
- **Normalização** da pergunta feita em Python na gravação, em uma coluna `pergunta_norm` (sem extensão no Neon).
- **API do admin:** `GET /admin/api/resumo`, `/admin/api/mais-feitas`, `/admin/api/negativas`,
  `/admin/api/perguntas?pagina=&busca=`, todas com `dias` (7/30/90) e `curso` opcionais; os sinais derivados
  saem de SQL.
- **Texto do aluno.** `pergunta` já é limitada a 4 mil caracteres pela API; sem redação automática. O rodapé
  ganha "Não escreva dados pessoais nas perguntas."
- **Falhas.** Em `parada` e `erro`, `resposta` guarda o texto parcial; `primeiro_texto_ms`, `tokens_saida` e
  `erro` podem ser nulos.
- **Testes.** pytest (novo no projeto). A gravação fica atrás de uma interface com versão em memória para os
  testes da API; os testes de SQL rodam contra um branch `dev` do Neon (`TEST_DATABASE_URL`) e são pulados sem ele.

## Para quem implementar decidir
Visual exato da página `/admin` e dos botões 👍/👎, tamanho das páginas da lista, limites de `/eventos` e de
tentativas de senha, nomes dos índices.
