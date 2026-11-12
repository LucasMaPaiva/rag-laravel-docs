# RAG local sobre a documentação do Laravel

Perguntas em português sobre a documentação oficial do Laravel (em inglês), respondidas a
partir dos trechos certos e com o link da seção. Tudo roda localmente e de graça: PostgreSQL
com **pgvector** e **pg_trgm**, embeddings e modelo de linguagem pelo **Ollama**.

O foco do projeto é medir: cada etapa tem avaliação com perguntas de resposta conhecida.

## Etapas

| Etapa | O que faz | Situação |
|---|---|---|
| 1. Chunking | Quebra cada página por seção (`##`, `###`, `####`), guarda o caminho de títulos, a âncora e a URL, e nunca corta bloco de código | ✅ feito, com testes |
| 2. Embeddings | Gera vetores dos trechos com modelos do Ollama e grava no pgvector | a fazer |
| 3. Busca | Vetorial, por trigramas (pg_trgm) e híbrida (as duas combinadas) | a fazer |
| 4. Avaliação da busca | ~30 perguntas em português com a seção esperada; mede se ela aparece entre os 5 primeiros (recall@5) e a posição (MRR) | a fazer |
| 5. Geração | Responde só com os trechos encontrados e cita a seção; o código confere se a citação existe | depois |

Perguntas que a avaliação quer responder:

- Pergunta em português sobre texto em inglês: quanto um modelo de embedding multilíngue ganha de um modelo só em inglês?
- Nomes de método (`simplePaginate`, `Queue::failing`): a busca por trigramas acerta onde a vetorial erra?
- A busca híbrida vale a complexidade a mais?

## Desenvolvimento

```bash
uv sync
uv run ruff check .
uv run pytest
```

## Créditos

O conteúdo indexado é a [documentação do Laravel](https://github.com/laravel/docs)
(licença MIT, © Taylor Otwell). O arquivo `tests/fixtures/pagination.md` é um trecho dela,
usado só nos testes.
