# PPChat multi-curso (IFSP São Carlos) — design

## Por quê
O PPChat responde só sobre o PPC de Engenharia de Software. A ideia é atender os 6 cursos de graduação do
IFSP São Carlos: o aluno tem o "seu" curso (vindo do SUAP) e pode explorar os outros.

## Objetivos
- 6 cursos: Eng. Software, Eng. Aeronáutica, Administração (bacharelados); ADS, Processos Gerenciais,
  Manutenção de Aeronaves (tecnologias; este último em extinção).
- Tela **Explorar cursos**: primeira tela de quem não importou o SUAP; funciona no celular.
- **Meu curso**: detectado na aba "Dados Acadêmicos" do SUAP; o PPChat passa a abrir nele.
- Cabeçalho sempre mostra o curso aberto, com troca rápida. Endereço por curso (`/analise-e-desenvolvimento-de-sistemas`).
- Conversas salvas ficam marcadas com o curso.

## Não-objetivos
- Outros campi; Supabase ou qualquer banco; versões antigas dos PPCs (ingressantes antes da reformulação).

## Anti-objetivos
- Responder com o PPC errado sem o aluno perceber.
- Aumentar o custo por pergunta (cada curso continua com seu próprio cache de prompt, que só é pago quando alguém pergunta sobre ele).

## Abordagens consideradas (escolha do usuário: identificar pelo SUAP + explorar)
- A. Aluno escolhe e SUAP confirma — preterida pelo usuário.
- B. Só SUAP — escolhida como fonte do "meu curso"; sem SUAP o aluno explora qualquer curso.
- C. Claude deduz pela pergunta — descartada (erra e gasta tokens).

## Decisões do usuário
- Só os 6 cursos de São Carlos, arquivos no repositório, sem Supabase.
- Duas telas: explorar cursos e "meu curso".
- Extração dos currículos feita nesta sessão (plano do Claude), não pela API.

## Desenho
**Dados**: `src/data/courses/courses.json` (registro: slug, nome, sigla, tipo, status, fonte do PDF) e uma
pasta por curso `src/data/courses/<slug>/` com `ppc.pdf`, `ppc.md`, `curriculo.json`, `manifest.json` e
`notas.md` opcional (instruções específicas do curso para o prompt, ex.: os dois sentidos de "extensão" em ES).
Eng. Software usa o PPC atualizado (Parecer 37/2025). `src/data/processed/` e o PDF antigo saem.

**Ingestão**: `python main.py ingest --curso <slug>|all [--force] [--sem-extracao]`. Texto sai localmente
(PyMuPDF); o limpador remove cabeçalhos/rodapés repetidos de forma genérica (linhas que aparecem em muitas
páginas) em vez do regex fixo de ES. `--sem-extracao` gera só o `ppc.md`.

**Backend**: `get_knowledge_base(slug)` com cache por curso; as 6 bases (~2 MB) são carregadas ao subir o servidor, para um curso quebrado falhar o deploy e não a visita de um aluno. Slug validado contra o
registro (404 se desconhecido). Prompt com nome do curso + `notas.md`. Endpoints: `GET /courses` (lista com
números: semestres, carga, nº de disciplinas), `GET /curriculum?curso=`, `GET /pdf?curso=`, `curso` no corpo
de `/chat` e `/chat/stream` (padrão `engenharia-de-software` para clientes antigos). Rotas `/<slug>` (slug completo do curso) servem o
front. CLI `chat`/`ask` ganham `--curso`.

**Front**: `state.course` (curso aberto) separado de `state.aluno.curso` (curso do SUAP).
Sem curso na URL: abre no curso do SUAP; sem SUAP, na tela Explorar. Trocar de curso recarrega currículo,
fluxograma e PDF e começa conversa nova. "Meu percurso" só aparece no próprio curso. O histórico do SUAP vai
ao chat mesmo em outro curso (permite "se eu mudar para ADS, o que aproveito?"). SUAP com curso fora dos 6:
aviso e tela Explorar. Textos fixos "Engenharia de Software" viram o nome do curso aberto.

## Para quem implementar decidir
Layout exato dos cards; nome da rota do explorar; como o seletor do cabeçalho se comporta no celular.
