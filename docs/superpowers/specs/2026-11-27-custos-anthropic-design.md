# Custos da Anthropic no /admin — design curto

## Por quê
O dono quer ver no `/admin` quanto está gastando com a Anthropic e quanto ainda tem de saldo, sem abrir o Console.

## Objetivos
- Mostrar o gasto real (o mesmo da fatura) no período escolhido (7, 30, 90 dias), por dia e por modelo.
- Mostrar um saldo estimado.

## Não-objetivos
- Saldo exato em tempo real: a API da Anthropic não expõe o crédito restante.
- Alertas de saldo baixo, custo por pergunta.

## Anti-objetivos
- A chave de administração chegar ao navegador, aparecer em log ou ser usada para algo além de ler custos.
- O `/admin` ficar lento ou quebrar se a Anthropic demorar ou falhar.

## Abordagens (escolha do usuário: 1)
1. **Custo real pela API de administração + saldo estimado** — escolhida. Bate com a fatura (com 4 a 24 h de
   atraso); exige uma chave `sk-ant-admin` no Render.
2. Estimar pelos tokens gravados no banco × tabela de preços — sem chave poderosa, em tempo real, mas
   aproximado e só cobre o uso do chat.

## Desenho
- **Fonte:** `client.beta.organization.analytics.cost.list(...)` do SDK `anthropic` já instalado (2.3.0),
  agrupado por modelo, em buckets de 1 dia. Valores vêm em centavos (string decimal); somados com `Decimal`.
  Mostra também "dados até <data_refreshed_at>".
- **Chave:** nova variável `ANTHROPIC_ADMIN_KEY` (secreta, `sync: false`). Usada só no servidor, num cliente
  separado do chat. Sem ela, o cartão de custos mostra "não configurado" e o resto do admin funciona igual.
- **Saldo estimado:** no `/admin` há um campo "Saldo que aparece no Console agora (US$)". Ao salvar, o servidor
  grava esse valor e a hora numa tabela `saldo_referencia` no Neon. Saldo estimado = valor informado − gasto
  desde aquela hora. Ao recarregar crédito, basta informar o saldo novo do Console. Sem referência, mostra só o
  gasto.
- **Desempenho:** a resposta da Anthropic fica em memória por 30 min (a API pede consultas espaçadas e os dados
  só mudam algumas vezes ao dia). Tempo máximo de 10 s; se falhar, o cartão mostra "não foi possível carregar
  os custos agora" e o log registra só o tipo do erro.
- **API do admin:** `GET /admin/api/custos?dias=` e `POST /admin/api/saldo` (`{valor_usd}` entre 0 e 100 mil),
  ambas atrás da mesma senha e bloqueio de tentativas do admin.
- **Tela:** cartão "Custos da Anthropic" com: gasto do período, saldo estimado (e desde quando), barras por dia
  e lista por modelo. O filtro de curso não se aplica a esse cartão.

## Decisões minhas (podem ser corrigidas)
- Saldo por "ponto de referência" digitado no admin, em vez de variável no Render (não precisa reimplantar).
- Cache de 30 min; tempo máximo de 10 s.
- Valores mostrados em US$ com 2 casas.

## Para quem implementar decidir
Visual exato do cartão e das barras.
