"""Três jeitos de buscar trechos para uma pergunta.

- vetorial: similaridade de cosseno entre o embedding da pergunta e o dos trechos (pgvector);
- trigramas: semelhança de trigramas entre a pergunta e o texto (pg_trgm), que favorece
  termos exatos como nomes de método (``simplePaginate``, ``Cache::lock``);
- híbrida: junta as duas listas por Reciprocal Rank Fusion (RRF), que só olha a posição
  em cada lista e dispensa calibrar escalas diferentes de pontuação.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag_laravel import banco, embeddings


@dataclass
class Resultado:
    id: str
    pagina: str
    ancora: str | None
    caminho: str
    url: str
    pontuacao: float

    @property
    def secao(self) -> str:
        return f"{self.pagina}#{self.ancora or ''}"


COLUNAS = "id, pagina, ancora, caminho, url"


def vetorial(conn, pergunta: str, modelo: str = "bge", k: int = 10) -> list[Resultado]:
    nome = banco.MODELOS[modelo]["ollama"]
    (vetor,) = embeddings.gerar(nome, [pergunta], tipo="pergunta")
    linhas = conn.execute(
        f"""SELECT {COLUNAS}, 1 - (emb_{modelo} <=> %s::vector) AS pontuacao
            FROM trechos WHERE emb_{modelo} IS NOT NULL
            ORDER BY emb_{modelo} <=> %s::vector LIMIT %s""",
        (banco.vetor_sql(vetor), banco.vetor_sql(vetor), k),
    ).fetchall()
    return [Resultado(*linha) for linha in linhas]


def trigramas(conn, pergunta: str, k: int = 10) -> list[Resultado]:
    linhas = conn.execute(
        f"""SELECT {COLUNAS}, word_similarity(%s, caminho || ' ' || texto) AS pontuacao
            FROM trechos ORDER BY pontuacao DESC LIMIT %s""",
        (pergunta, k),
    ).fetchall()
    return [Resultado(*linha) for linha in linhas]


def fundir_rrf(
    listas: list[list[Resultado]], k: int = 10, constante: int = 60, pesos: list[float] | None = None
) -> list[Resultado]:
    """Reciprocal Rank Fusion: soma peso / (constante + posição) de cada lista.

    Sem ``pesos``, todas as listas valem o mesmo (RRF clássico).
    """
    pesos = pesos or [1.0] * len(listas)
    if len(pesos) != len(listas):
        raise ValueError("informe um peso para cada lista")
    pontos: dict[str, float] = {}
    por_id: dict[str, Resultado] = {}
    for lista, peso in zip(listas, pesos, strict=True):
        for posicao, r in enumerate(lista, start=1):
            pontos[r.id] = pontos.get(r.id, 0.0) + peso / (constante + posicao)
            por_id.setdefault(r.id, r)
    ordem = sorted(pontos, key=pontos.get, reverse=True)[:k]
    return [Resultado(**{**por_id[i].__dict__, "pontuacao": pontos[i]}) for i in ordem]


def hibrida(
    conn, pergunta: str, modelo: str = "bge", k: int = 10, profundidade: int = 50, peso_trigramas: float = 1.0
) -> list[Resultado]:
    """Busca vetorial e por trigramas fundidas por RRF; ``peso_trigramas`` < 1 dá menos voz aos trigramas."""
    return fundir_rrf(
        [vetorial(conn, pergunta, modelo, profundidade), trigramas(conn, pergunta, profundidade)],
        k=k,
        pesos=[1.0, peso_trigramas],
    )
