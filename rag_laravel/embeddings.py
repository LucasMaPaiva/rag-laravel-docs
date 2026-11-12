"""Embeddings pelo Ollama (/api/embed), em lotes."""

from __future__ import annotations

import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11440")

# O nomic-embed-text foi treinado com prefixos de tarefa; o bge-m3 não usa prefixo.
PREFIXOS = {
    "nomic-embed-text": {"documento": "search_document: ", "pergunta": "search_query: "},
}


def com_prefixo(modelo: str, textos: list[str], tipo: str) -> list[str]:
    prefixo = PREFIXOS.get(modelo, {}).get(tipo, "")
    return [prefixo + t for t in textos]


def gerar(modelo: str, textos: list[str], tipo: str = "documento", timeout: int = 600) -> list[list[float]]:
    """Gera embeddings; ``tipo`` é 'documento' (trecho indexado) ou 'pergunta'."""
    resposta = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": modelo, "input": com_prefixo(modelo, textos, tipo), "truncate": True},
        timeout=timeout,
    )
    resposta.raise_for_status()
    vetores = resposta.json()["embeddings"]
    if len(vetores) != len(textos):
        raise ValueError(f"esperava {len(textos)} vetores, vieram {len(vetores)}")
    return vetores
