"""Avalia a etapa 5: as respostas citam fontes que existem e a seção certa?

Para cada pergunta do gabarito, gera a resposta e mede:
- com citação: a resposta cita pelo menos uma fonte (ou recusa de forma explícita);
- citações válidas: nenhum número citado fica fora da lista de fontes;
- cita a seção esperada: alguma fonte citada é uma das seções do gabarito;
- recusou: respondeu "Não encontrei isso na documentação.".

A qualidade do texto em si não é medida aqui: as respostas ficam no JSON para leitura.

    uv run python -m evals.avaliar_geracao              # as 30 perguntas
    uv run python -m evals.avaliar_geracao --limite 5   # só as 5 primeiras, para testar
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from rag_laravel import banco, geracao

PASTA = Path(__file__).resolve().parent


def avaliar_pergunta(conn, p: dict, modelo: str) -> dict:
    inicio = time.perf_counter()
    fontes, partes, verificacao = [], [], {}
    for evento in geracao.responder(conn, p["pergunta"], modelo=modelo):
        if evento["tipo"] == "fontes":
            fontes = evento["fontes"]
        elif evento["tipo"] == "texto":
            partes.append(evento["texto"])
        else:
            verificacao = evento["verificacao"]
    secoes_citadas = [fontes[n - 1]["secao"] for n in verificacao["citadas"]]
    return {
        "id": p["id"],
        "tipo": p["tipo"],
        "pergunta": p["pergunta"],
        "esperado": p["esperado"],
        "fontes": [f["secao"] for f in fontes],
        "esperada_nas_fontes": any(f["secao"] in p["esperado"] for f in fontes),
        "resposta": "".join(partes),
        "citadas": secoes_citadas,
        "invalidas": verificacao["invalidas"],
        "com_citacao": not verificacao["sem_citacao"] or verificacao["recusou"],
        "recusou": verificacao["recusou"],
        "cita_esperada": any(s in p["esperado"] for s in secoes_citadas),
        "segundos": round(time.perf_counter() - inicio, 1),
    }


def relatorio(linhas: list[dict], modelo: str) -> str:
    n = len(linhas)

    def pct(chave, sub=None):
        sub = linhas if sub is None else sub
        return f"{sum(1 for x in sub if x[chave]) / len(sub):.0%}" if sub else "-"

    com_fonte_certa = [x for x in linhas if x["esperada_nas_fontes"]]
    sem_invalidas = sum(1 for x in linhas if not x["invalidas"])
    texto = [
        f"# Avaliação da geração ({modelo}, {n} perguntas)",
        "",
        "| Métrica | Resultado |",
        "|---|---|",
        f"| Respostas com citação (ou recusa explícita) | {pct('com_citacao')} |",
        f"| Respostas sem citação inválida | {sem_invalidas / n:.0%} |",
        f"| Seção esperada estava entre as fontes (busca) | {pct('esperada_nas_fontes')} |",
        f"| Cita a seção esperada (todas as perguntas) | {pct('cita_esperada')} |",
        f"| Cita a seção esperada, quando ela estava nas fontes | {pct('cita_esperada', com_fonte_certa)} |",
        f"| Recusou responder | {pct('recusou')} |",
        f"| Tempo mediano por resposta | {statistics.median(x['segundos'] for x in linhas):.1f} s |",
        "",
        "## Perguntas com problema",
        "",
    ]
    for x in linhas:
        problemas = []
        if x["invalidas"]:
            problemas.append(f"citação inválida {x['invalidas']}")
        if not x["com_citacao"]:
            problemas.append("sem citação")
        if x["esperada_nas_fontes"] and not x["cita_esperada"]:
            problemas.append("a seção certa estava nas fontes, mas não foi citada")
        if x["recusou"]:
            problemas.append("recusou")
        if problemas:
            texto.append(f"- {x['id']}. {x['pergunta']} ({'; '.join(problemas)})")
    return "\n".join(texto)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modelo", default=geracao.MODELO)
    parser.add_argument("--limite", type=int)
    args = parser.parse_args()
    perguntas = json.loads((PASTA / "perguntas.json").read_text(encoding="utf-8"))["perguntas"]
    perguntas = perguntas[: args.limite] if args.limite else perguntas
    linhas = []
    with banco.conectar() as conn:
        for p in perguntas:
            linha = avaliar_pergunta(conn, p, args.modelo)
            print(f"{p['id']:>2}. {linha['segundos']:>5.1f}s  cita esperada: {linha['cita_esperada']}", flush=True)
            linhas.append(linha)
    texto = relatorio(linhas, args.modelo)
    saida = PASTA / "resultados"
    saida.mkdir(exist_ok=True)
    base = saida / f"geracao-{datetime.now():%Y%m%d-%H%M}"
    base.with_suffix(".json").write_text(json.dumps(linhas, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(texto, encoding="utf-8")
    print()
    print(texto)


if __name__ == "__main__":
    main()
