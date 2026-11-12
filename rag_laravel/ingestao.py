"""Carrega os trechos no banco e gera os embeddings de um modelo.

    python -m rag_laravel.ingestao trechos              # quebra a documentação e grava os textos
    python -m rag_laravel.ingestao embeddings nomic     # preenche emb_nomic
    python -m rag_laravel.ingestao embeddings bge       # preenche emb_bge
    python -m rag_laravel.ingestao indices              # cria os índices HNSW
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from rag_laravel import banco, embeddings
from rag_laravel.chunker import quebrar_diretorio

PASTA_DOCS = Path(__file__).resolve().parent.parent / "data" / "docs"


def carregar_trechos(conn) -> int:
    trechos = quebrar_diretorio(PASTA_DOCS)
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO trechos (id, pagina, caminho, ancora, url, texto)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET caminho = EXCLUDED.caminho, ancora = EXCLUDED.ancora,
                   url = EXCLUDED.url, texto = EXCLUDED.texto""",
            [(t.id, t.pagina, t.caminho, t.ancora, t.url, t.texto) for t in trechos],
        )
    return len(trechos)


def gerar_embeddings(conn, chave: str, lote: int = 32) -> None:
    modelo = banco.MODELOS[chave]["ollama"]
    coluna = f"emb_{chave}"
    pendentes = conn.execute(
        f"SELECT id, caminho, texto FROM trechos WHERE {coluna} IS NULL ORDER BY id"
    ).fetchall()
    print(f"{len(pendentes)} trechos sem {coluna}")
    inicio = time.perf_counter()
    for i in range(0, len(pendentes), lote):
        parte = pendentes[i : i + lote]
        vetores = embeddings.gerar(modelo, [f"{c}\n\n{t}" for _, c, t in parte])
        with conn.cursor() as cur:
            cur.executemany(
                f"UPDATE trechos SET {coluna} = %s::vector WHERE id = %s",
                [(banco.vetor_sql(v), id_) for (id_, _, _), v in zip(parte, vetores, strict=True)],
            )
        feitos = i + len(parte)
        decorrido = time.perf_counter() - inicio
        print(f"  {feitos}/{len(pendentes)}  {decorrido:.0f}s", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("acao", choices=["trechos", "embeddings", "indices"])
    parser.add_argument("modelo", nargs="?", choices=sorted(banco.MODELOS))
    args = parser.parse_args()
    with banco.conectar() as conn:
        banco.criar_esquema(conn)
        if args.acao == "trechos":
            print(f"{carregar_trechos(conn)} trechos gravados")
        elif args.acao == "embeddings":
            if not args.modelo:
                parser.error("informe o modelo: nomic ou bge")
            gerar_embeddings(conn, args.modelo)
        else:
            conn.execute(banco.INDICES_VETORIAIS)
            print("índices HNSW criados")


if __name__ == "__main__":
    main()
