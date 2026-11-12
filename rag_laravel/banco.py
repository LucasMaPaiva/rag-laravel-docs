"""Esquema e acesso ao PostgreSQL (pgvector para vetores, pg_trgm para trigramas)."""

from __future__ import annotations

import os

import psycopg

DSN = os.environ.get("RAG_DSN", "postgresql://rag:rag@127.0.0.1:5470/rag")

# Um modelo de embedding por coluna: dá para comparar modelos no mesmo banco.
MODELOS = {
    "nomic": {"ollama": "nomic-embed-text", "dimensao": 768},
    "bge": {"ollama": "bge-m3", "dimensao": 1024},
}

ESQUEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS trechos (
    id          text PRIMARY KEY,
    pagina      text NOT NULL,
    caminho     text NOT NULL,
    ancora      text,
    url         text NOT NULL,
    texto       text NOT NULL,
    emb_nomic   vector({MODELOS["nomic"]["dimensao"]}),
    emb_bge     vector({MODELOS["bge"]["dimensao"]})
);

-- Busca por trigramas no texto com o caminho de títulos (nomes de método, termos exatos).
CREATE INDEX IF NOT EXISTS trechos_trgm_idx
    ON trechos USING gin ((caminho || ' ' || texto) gin_trgm_ops);
"""

# HNSW por coluna de vetor, criado depois da carga (mais rápido do que manter durante os INSERTs).
INDICES_VETORIAIS = """
CREATE INDEX IF NOT EXISTS trechos_emb_nomic_idx ON trechos USING hnsw (emb_nomic vector_cosine_ops);
CREATE INDEX IF NOT EXISTS trechos_emb_bge_idx ON trechos USING hnsw (emb_bge vector_cosine_ops);
"""


def conectar() -> psycopg.Connection:
    return psycopg.connect(DSN, autocommit=True)


def criar_esquema(conn: psycopg.Connection) -> None:
    conn.execute(ESQUEMA)


def vetor_sql(vetor: list[float]) -> str:
    """Formato de texto do pgvector: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.6f}" for v in vetor) + "]"
