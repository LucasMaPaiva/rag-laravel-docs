"""Avalia a busca com perguntas de resposta conhecida.

Para cada pergunta, a busca acerta se uma das seções esperadas aparece entre os k primeiros
resultados (recall@k). O MRR (média de 1/posição do primeiro acerto) mostra também se a
seção certa vem no topo ou lá embaixo.

    python -m evals.avaliar_busca --estrategias vetorial-nomic vetorial-bge trigramas hibrida-bge
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from rag_laravel import banco, busca

PASTA = Path(__file__).resolve().parent
ESTRATEGIAS = {
    "vetorial-nomic": lambda c, p, k: busca.vetorial(c, p, "nomic", k),
    "vetorial-bge": lambda c, p, k: busca.vetorial(c, p, "bge", k),
    "trigramas": lambda c, p, k: busca.trigramas(c, p, k),
    "hibrida-nomic": lambda c, p, k: busca.hibrida(c, p, "nomic", k),
    "hibrida-bge": lambda c, p, k: busca.hibrida(c, p, "bge", k),
}


def posicao_do_acerto(resultados, esperado: list[str]) -> int | None:
    for i, r in enumerate(resultados, start=1):
        if r.secao in esperado:
            return i
    return None


def avaliar(conn, estrategia: str, perguntas: list[dict], k: int) -> dict:
    linhas = []
    for p in perguntas:
        inicio = time.perf_counter()
        resultados = ESTRATEGIAS[estrategia](conn, p["pergunta"], k)
        segundos = time.perf_counter() - inicio
        pos = posicao_do_acerto(resultados, p["esperado"])
        linhas.append({
            "id": p["id"], "tipo": p["tipo"], "pergunta": p["pergunta"], "esperado": p["esperado"],
            "posicao": pos, "top3": [r.secao for r in resultados[:3]], "segundos": round(segundos, 3),
        })

    def resumo(sub):
        if not sub:
            return None
        acertos = sum(1 for linha in sub if linha["posicao"])
        mrr = statistics.mean(1 / linha["posicao"] if linha["posicao"] else 0 for linha in sub)
        return {"n": len(sub), "recall": acertos / len(sub), "mrr": mrr}

    return {
        "estrategia": estrategia,
        "geral": resumo(linhas),
        "conceito": resumo([x for x in linhas if x["tipo"] == "conceito"]),
        "metodo": resumo([x for x in linhas if x["tipo"] == "metodo"]),
        "latencia_mediana_s": statistics.median(x["segundos"] for x in linhas),
        "perguntas": linhas,
    }


def relatorio(resultados: list[dict], k: int) -> str:
    def pct(r):
        return f"{r['recall']:.0%}" if r else "-"

    linhas = [
        f"# Avaliação da busca (recall@{k} e MRR)", "",
        f"| Estratégia | Recall@{k} geral | Conceito | Nome de método | MRR | Latência mediana |",
        "|---|---|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r['estrategia']} | {pct(r['geral'])} | {pct(r['conceito'])} | {pct(r['metodo'])} "
            f"| {r['geral']['mrr']:.2f} | {r['latencia_mediana_s'] * 1000:.0f} ms |"
        )
    linhas += ["", "## Perguntas que cada estratégia errou", ""]
    for r in resultados:
        erros = [x for x in r["perguntas"] if not x["posicao"]]
        linhas.append(f"### {r['estrategia']} ({len(erros)} erros)")
        for x in erros:
            linhas.append(f"- {x['id']}. {x['pergunta']} (esperado {x['esperado'][0]}; veio {x['top3'][:1]})")
        linhas.append("")
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--estrategias", nargs="+", default=list(ESTRATEGIAS), choices=list(ESTRATEGIAS))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    perguntas = json.loads((PASTA / "perguntas.json").read_text(encoding="utf-8"))["perguntas"]
    with banco.conectar() as conn:
        resultados = [avaliar(conn, e, perguntas, args.k) for e in args.estrategias]
    texto = relatorio(resultados, args.k)
    saida = PASTA / "resultados"
    saida.mkdir(exist_ok=True)
    base = saida / f"busca-{datetime.now():%Y%m%d-%H%M}"
    base.with_suffix(".json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
