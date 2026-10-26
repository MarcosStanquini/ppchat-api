from functools import cached_property
from typing import Dict, List, Optional, Set

from pydantic import BaseModel

from src.modules.ingestion.models.curriculum import Curriculo, Disciplina

# Pesos do índice de complexidade estimada (0-10). Não é dado oficial do PPC:
# combina sinais objetivos do próprio currículo para o modelo raciocinar de forma consistente.
COMPLEXITY_WEIGHTS = {"profundidade": 0.35, "base_acumulada": 0.25, "semestre": 0.25, "carga": 0.15}


class DisciplinaAnalise(BaseModel):
    codigo: str
    profundidade: int  # elos de pré-requisito até ela (0 = não exige nada)
    cadeia_mais_longa: List[str]  # códigos, da raiz até a disciplina
    pre_requisitos_transitivos: List[str]
    libera_diretamente: List[str]
    libera_transitivamente: List[str]
    indice_complexidade: float
    nivel_estimado: str


class CurriculumGraph:
    def __init__(self, curriculo: Curriculo):
        self.curriculo = curriculo
        self.by_code: Dict[str, Disciplina] = {d.codigo: d for d in curriculo.disciplinas}
        self.dependents: Dict[str, List[str]] = {code: [] for code in self.by_code}
        for disciplina in curriculo.disciplinas:
            for required in disciplina.pre_requisitos:
                self.dependents[required].append(disciplina.codigo)

    def _sort(self, codes) -> List[str]:
        # Ordem estável (semestre, código) para o texto gerado nunca mudar entre execuções
        return sorted(codes, key=lambda c: (self.by_code[c].semestre or 99, c))

    def _closure(self, code: str, edges: Dict[str, List[str]], seen: Optional[Set[str]] = None) -> Set[str]:
        seen = set() if seen is None else seen
        for neighbor in edges[code]:
            if neighbor not in seen:
                seen.add(neighbor)
                self._closure(neighbor, edges, seen)
        return seen

    @cached_property
    def _prerequisites(self) -> Dict[str, List[str]]:
        return {code: d.pre_requisitos for code, d in self.by_code.items()}

    @cached_property
    def longest_chains(self) -> Dict[str, List[str]]:
        chains: Dict[str, List[str]] = {}

        def chain(code: str, visiting: Set[str]) -> List[str]:
            if code in chains:
                return chains[code]
            if code in visiting:  # ciclo no PPC: interrompe em vez de recursão infinita
                return [code]
            visiting.add(code)
            best: List[str] = []
            for required in self._sort(self._prerequisites[code]):
                candidate = chain(required, visiting)
                if len(candidate) > len(best):
                    best = candidate
            visiting.discard(code)
            chains[code] = best + [code]
            return chains[code]

        for code in self.by_code:
            chain(code, set())
        return chains

    @cached_property
    def analysis(self) -> Dict[str, DisciplinaAnalise]:
        ancestors = {c: self._closure(c, self._prerequisites) for c in self.by_code}
        descendants = {c: self._closure(c, self.dependents) for c in self.by_code}
        depth = {c: len(chain) - 1 for c, chain in self.longest_chains.items()}

        max_depth = max(depth.values(), default=0) or 1
        max_ancestors = max((len(a) for a in ancestors.values()), default=0) or 1
        semesters = [d.semestre for d in self.by_code.values() if d.semestre]
        max_semester = max(semesters, default=1)
        max_hours = max((d.carga_horaria_total for d in self.by_code.values()), default=0) or 1

        result = {}
        for code, disciplina in self.by_code.items():
            semester_score = (
                (disciplina.semestre - 1) / max(max_semester - 1, 1) if disciplina.semestre else 0.5
            )
            score = 10 * (
                COMPLEXITY_WEIGHTS["profundidade"] * depth[code] / max_depth
                + COMPLEXITY_WEIGHTS["base_acumulada"] * len(ancestors[code]) / max_ancestors
                + COMPLEXITY_WEIGHTS["semestre"] * semester_score
                + COMPLEXITY_WEIGHTS["carga"] * disciplina.carga_horaria_total / max_hours
            )
            result[code] = DisciplinaAnalise(
                codigo=code,
                profundidade=depth[code],
                cadeia_mais_longa=self.longest_chains[code],
                pre_requisitos_transitivos=self._sort(ancestors[code]),
                libera_diretamente=self._sort(self.dependents[code]),
                libera_transitivamente=self._sort(descendants[code]),
                indice_complexidade=round(score, 1),
                nivel_estimado="introdutória" if score < 3.5 else "intermediária" if score < 6.5 else "avançada",
            )
        return result

    @cached_property
    def critical_path(self) -> List[str]:
        return max(self.longest_chains.values(), key=len, default=[])

    def bottlenecks(self, top: int = 8) -> List[str]:
        """Disciplinas que mais travam o curso se o aluno reprovar."""
        ranked = sorted(self.by_code, key=lambda c: (-len(self.analysis[c].libera_transitivamente), c))
        return [c for c in ranked if self.analysis[c].libera_transitivamente][:top]
