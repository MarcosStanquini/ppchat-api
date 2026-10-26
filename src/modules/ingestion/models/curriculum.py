from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PageText(BaseModel):
    page_number: int  # número da página no arquivo PDF (1-based)
    text: str


class Disciplina(BaseModel):
    codigo: str = Field(description="Código do componente, ex.: SCLRQSW")
    nome: str = Field(description="Nome oficial em maiúsculas, como aparece no PPC")
    semestre: Optional[int] = Field(description="Semestre em que é ofertada; null se optativa sem semestre fixo")
    tipo: Literal["obrigatoria", "optativa", "eletiva"]
    aulas_semanais: int
    total_aulas: int
    carga_horaria_ensino: float
    carga_horaria_extensao: float
    carga_horaria_total: float
    abordagem: Literal["teorica", "pratica", "teorico_pratica"] = Field(
        description="Campo 'Abordagem metodológica' do plano de ensino: T, P ou T/P"
    )
    usa_laboratorio: bool
    pre_requisitos: List[str] = Field(description="CÓDIGOS das disciplinas pré-requisito (vazio se não houver)")
    grupos_conhecimento: List[str] = Field(description="Grupos de conhecimentos essenciais do plano de ensino")
    topicos_principais: List[str] = Field(description="Até 8 tópicos curtos do conteúdo programático")
    pagina_plano_ensino: Optional[int] = Field(description="Página do PDF ([Página N]) onde começa o plano de ensino")


class RequisitoGeral(BaseModel):
    item: str = Field(description="Ex.: Estágio Supervisionado, TCC, Atividades Complementares, Extensão")
    descricao: str = Field(description="Regra objetiva: carga horária mínima, quando pode começar, condições")
    pagina: Optional[int]


class Curriculo(BaseModel):
    curso: str
    campus: str
    vigencia: str
    duracao_semestres: int
    carga_horaria_total_curso: float
    disciplinas: List[Disciplina]
    requisitos_gerais: List[RequisitoGeral]
