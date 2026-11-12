"""Etapa 5: responde em português usando só os trechos encontrados, citando a fonte.

O modelo recebe os trechos numerados ([1], [2], ...) e deve citar o número depois de cada
afirmação. O código confere as citações: número que não existe entre as fontes é marcado como
inválido, e resposta sem nenhuma citação é sinalizada. Quem lê vê o link de cada fonte citada.

    uv run python -m rag_laravel.geracao "Como evitar o problema de N+1 consultas?"
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import requests

from rag_laravel import banco, busca
from rag_laravel.embeddings import OLLAMA_URL

MODELO = os.environ.get("RAG_MODELO_GERACAO", "qwen2.5:7b")
LIMITE_FONTE = 2500  # caracteres por trecho no prompt, para caber no contexto
RECUSA = "Não encontrei isso na documentação."

INSTRUCOES = f"""Você responde dúvidas sobre o framework Laravel (versão 13.x) usando SOMENTE as fontes \
fornecidas, que são trechos da documentação oficial em inglês.

Regras:
1. Responda em português do Brasil, de forma direta: no máximo 3 parágrafos curtos.
2. Depois de cada afirmação, cite a fonte usada com o número entre colchetes, por exemplo [2]. \
Use só números de fontes que existem na lista.
3. Nomes de método, classes e código ficam como estão na fonte. Se ajudar, inclua um exemplo \
de código curto copiado das fontes, em bloco de código.
4. Não use conhecimento de fora das fontes. Se as fontes não respondem a pergunta, responda \
apenas: "{RECUSA}"
"""


# Repetido no fim da mensagem: na primeira avaliação, 23% das respostas vieram sem citação nenhuma
# quando a regra estava só nas instruções de sistema (o modelo "esquece" depois de 5 fontes longas).
LEMBRETE = (
    "Responda em português, em no máximo 3 parágrafos curtos, e coloque o número da fonte entre "
    "colchetes logo depois de cada frase que usa essa fonte, por exemplo: \"Use o método with() [2].\""
)


@dataclass
class Fonte:
    numero: int
    secao: str
    caminho: str
    url: str
    texto: str


@dataclass
class Verificacao:
    citadas: list[int]  # números válidos, na ordem em que aparecem
    invalidas: list[int]  # números que não existem entre as fontes
    sem_citacao: bool
    recusou: bool

    @property
    def ok(self) -> bool:
        return self.recusou or (not self.invalidas and not self.sem_citacao)


def buscar_fontes(conn, pergunta: str, k: int = 5) -> list[Fonte]:
    """Busca híbrida (bge-m3, trigramas com peso 0,2), a melhor na avaliação da etapa 4."""
    resultados = busca.hibrida(conn, pergunta, "bge", k, peso_trigramas=0.2)
    textos = dict(
        conn.execute(
            "SELECT id, texto FROM trechos WHERE id = ANY(%s)", ([r.id for r in resultados],)
        ).fetchall()
    )
    return [
        Fonte(i, r.secao, r.caminho, r.url, textos.get(r.id, "")[:LIMITE_FONTE])
        for i, r in enumerate(resultados, start=1)
    ]


def montar_mensagens(pergunta: str, fontes: list[Fonte]) -> list[dict]:
    blocos = [f"[{f.numero}] {f.caminho}\n{f.texto.strip()}" for f in fontes]
    conteudo = (
        "Fontes:\n\n" + "\n\n---\n\n".join(blocos) + f"\n\nPergunta: {pergunta.strip()}\n\n" + LEMBRETE
    )
    return [
        {"role": "system", "content": INSTRUCOES},
        {"role": "user", "content": conteudo},
    ]


_CODIGO = re.compile(r"```.*?(```|$)|`[^`\n]*`", re.DOTALL)
_CITACAO = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def extrair_citacoes(texto: str) -> list[int]:
    """Números citados como [n] ou [n, m], fora de blocos de código (onde $lista[0] não é citação)."""
    sem_codigo = _CODIGO.sub(" ", texto)
    numeros: list[int] = []
    for grupo in _CITACAO.findall(sem_codigo):
        for n in grupo.split(","):
            numero = int(n)
            if numero not in numeros:
                numeros.append(numero)
    return numeros


def verificar(texto: str, fontes: list[Fonte]) -> Verificacao:
    validos = {f.numero for f in fontes}
    numeros = extrair_citacoes(texto)
    return Verificacao(
        citadas=[n for n in numeros if n in validos],
        invalidas=[n for n in numeros if n not in validos],
        sem_citacao=not numeros,
        # Só conta como recusa se a resposta COMEÇA pela frase: o modelo às vezes responde certo e
        # cola a frase no final, e isso não é recusa.
        recusou=texto.strip().lower().startswith(RECUSA.rstrip(".").lower()),
    )


def gerar(mensagens: list[dict], modelo: str = MODELO) -> Iterator[str]:
    """Pedaços de texto conforme o modelo gera (/api/chat com stream)."""
    with requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": modelo,
            "messages": mensagens,
            "stream": True,
            "options": {"temperature": 0.1, "num_ctx": 8192},
        },
        stream=True,
        timeout=600,
    ) as resposta:
        resposta.raise_for_status()
        for linha in resposta.iter_lines():
            if not linha:
                continue
            dados = json.loads(linha)
            if "error" in dados:
                raise RuntimeError(dados["error"])
            pedaco = dados.get("message", {}).get("content", "")
            if pedaco:
                yield pedaco


def responder(conn, pergunta: str, k: int = 5, modelo: str = MODELO) -> Iterator[dict]:
    """Eventos da resposta: 'fontes', vários 'texto' e um 'fim' com a verificação das citações."""
    fontes = buscar_fontes(conn, pergunta, k)
    yield {"tipo": "fontes", "fontes": [asdict(f) for f in fontes]}
    partes: list[str] = []
    for pedaco in gerar(montar_mensagens(pergunta, fontes), modelo):
        partes.append(pedaco)
        yield {"tipo": "texto", "texto": pedaco}
    verificacao = verificar("".join(partes), fontes)
    yield {"tipo": "fim", "modelo": modelo, "verificacao": asdict(verificacao) | {"ok": verificacao.ok}}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('uso: python -m rag_laravel.geracao "sua pergunta"')
    fontes: list[dict] = []
    with banco.conectar() as conn:
        for evento in responder(conn, " ".join(sys.argv[1:])):
            if evento["tipo"] == "fontes":
                fontes = evento["fontes"]
            elif evento["tipo"] == "texto":
                print(evento["texto"], end="", flush=True)
            else:
                v = evento["verificacao"]
                print("\n\nFontes citadas:")
                for n in v["citadas"]:
                    print(f"  [{n}] {fontes[n - 1]['caminho']}  {fontes[n - 1]['url']}")
                if v["invalidas"]:
                    print(f"  ATENÇÃO: citações que não existem entre as fontes: {v['invalidas']}")
                if v["sem_citacao"] and not v["recusou"]:
                    print("  ATENÇÃO: a resposta não cita nenhuma fonte.")


if __name__ == "__main__":
    main()
