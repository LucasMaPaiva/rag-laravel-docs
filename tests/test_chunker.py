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


def test_tabela_e_codigo_enormes_sao_cortados_no_teto_mantendo_cercas():
    tabela = "\n".join(f"| Contrato{i} | Facade{i} |" for i in range(400))
    codigo = "```php\n" + "\n".join(f"$x{i} = {i};" for i in range(800)) + "\n```"
    md = "# P\n\n<a name=\"t\"></a>\n## T\n\n" + tabela + "\n\n" + codigo + "\n"
    partes = quebrar_pagina(md, "p", limite=1000)
    assert max(len(p.texto) for p in partes) <= 3 * 1000 + 100
    assert all(p.texto.count("```") % 2 == 0 for p in partes)
    assert any(p.texto.startswith("```php") for p in partes[1:])


def test_imagem_base64_vira_marcador():
    md = "# P\n\n<a name=\"a\"></a>\n## A\n\nTela:\n\n![Tela de autorização](data:image/png;base64," + "A" * 5000 + ")\n"
    (trecho,) = quebrar_pagina(md, "p")
    assert "[imagem: Tela de autorização]" in trecho.texto
    assert "base64" not in trecho.texto


def test_ids_sao_unicos_mesmo_sem_ancora():
    md = "# P\n\n## Sem ancora 1\n\ntexto a\n\n## Sem ancora 2\n\ntexto b\n"
    partes = quebrar_pagina(md, "p")
    assert len({p.id for p in partes}) == len(partes) == 2
