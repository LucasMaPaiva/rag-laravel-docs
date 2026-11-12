from pathlib import Path

from rag_laravel.chunker import quebrar_pagina

FIXTURE = Path(__file__).parent / "fixtures" / "pagination.md"


def trechos():
    return quebrar_pagina(FIXTURE.read_text(encoding="utf-8"), "pagination")


def test_titulo_da_pagina_e_indice_nao_viram_trecho():
    textos = "\n".join(t.texto for t in trechos())
    assert "- [Introduction](#introduction)" not in textos
    assert trechos()[0].titulo_pagina == "Database: Pagination"


def test_secao_guarda_caminho_ancora_e_url():
    por_ancora = {t.ancora: t for t in trechos()}
    t = por_ancora["paginating-query-builder-results"]
    assert t.secoes == ["Basic Usage", "Paginating Query Builder Results"]
    assert t.caminho == "Database: Pagination > Basic Usage > Paginating Query Builder Results"
    assert t.url == "https://laravel.com/docs/13.x/pagination#paginating-query-builder-results"


def test_subsecao_de_nivel_4_fica_abaixo_da_secao_certa():
    por_ancora = {t.ancora: t for t in trechos()}
    assert por_ancora["tailwind"].secoes == ["Introduction", "Tailwind"]


def test_secao_sem_texto_proprio_nao_gera_trecho_vazio():
    assert all(t.texto.strip() for t in trechos())
    assert "basic-usage" not in {t.ancora for t in trechos()}


def test_bloco_de_codigo_fica_inteiro():
    for t in trechos():
        assert t.texto.count("```") % 2 == 0, t.id


def test_texto_para_embedding_comeca_pelo_caminho():
    t = trechos()[0]
    assert t.texto_para_embedding().startswith(t.caminho)


def test_divide_secao_longa_sem_cortar_codigo():
    secao = "<a name=\"x\"></a>\n## X\n\n" + "\n\n".join(["texto " * 60] * 5)
    secao += "\n\n```php\n" + "linha();\n" * 50 + "```\n"
    partes = quebrar_pagina("# P\n\n" + secao, "p", limite=500)
    assert len(partes) > 1
    assert all(p.texto.count("```") % 2 == 0 for p in partes)
    assert [p.indice for p in partes] == list(range(len(partes)))
