-- Idempotente: roda em toda subida do servidor
create table if not exists perguntas (
  id uuid primary key,
  criado_em timestamptz not null default now(),  -- quando a resposta terminou
  curso text not null,
  conversa uuid,
  turno int not null,
  pergunta text not null,
  pergunta_norm text not null,
  resposta text not null,
  modelo text not null,
  status text not null,
  erro text,
  duracao_ms int not null,
  primeiro_texto_ms int,
  tokens_saida int,
  tinha_suap boolean not null,
  disciplinas int not null,
  visitante text not null
);
create index if not exists perguntas_criado_em on perguntas (criado_em);
create index if not exists perguntas_conversa_turno on perguntas (conversa, turno);

create table if not exists eventos (
  id bigint generated always as identity primary key,
  pergunta_id uuid not null references perguntas (id) on delete cascade,
  criado_em timestamptz not null default now(),
  tipo text not null,
  valor text not null default ''
);
create index if not exists eventos_pergunta on eventos (pergunta_id, criado_em);

-- Saldo que o dono viu no Console da Anthropic e quando (uma linha só): base do saldo estimado no /admin
create table if not exists saldo_referencia (
  id int primary key default 1 check (id = 1),
  valor_usd numeric(12, 2) not null,
  em timestamptz not null default now()
);
