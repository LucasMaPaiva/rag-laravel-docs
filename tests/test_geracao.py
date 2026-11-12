from rag_laravel.geracao import (
    LEMBRETE,
    RECUSA,
    Fonte,
    extrair_citacoes,
    montar_mensagens,
    verificar,
)


def fontes(n=3):
    return [Fonte(i, f"p#s{i}", f"Página > Seção {i}", f"u{i}", f"texto {i}") for i in range(1, n + 1)]


def test_extrai_citacoes_simples_e_agrupadas_sem_repetir():
    assert extrair_citacoes("Use X [2]. Também Y [1, 3] e de novo [2].") == [2, 1, 3]


def test_ignora_colchetes_dentro_de_codigo():
    texto = "Acesse o item [1].\n\n```php\n$itens[0] = 'a';\n```\n\nOu `$lista[5]` inline."
    assert extrair_citacoes(texto) == [1]


def test_verificacao_marca_numero_inexistente():
    v = verificar("Isso vale [1] e aquilo [7].", fontes())
    assert v.citadas == [1]
    assert v.invalidas == [7]
    assert not v.ok


def test_verificacao_resposta_sem_citacao():
    v = verificar("O Laravel faz isso sozinho.", fontes())
    assert v.sem_citacao
    assert not v.ok


def test_recusa_explicita_e_aceita_sem_citacao():
    v = verificar(RECUSA, fontes())
    assert v.recusou
    assert v.ok


def test_mensagens_numeram_as_fontes_e_trazem_a_pergunta():
    sistema, usuario = montar_mensagens("Como paginar?", fontes(2))
    assert sistema["role"] == "system"
    assert "[1] Página > Seção 1" in usuario["content"]
    assert "[2] Página > Seção 2" in usuario["content"]
    assert "Pergunta: Como paginar?" in usuario["content"]
    assert usuario["content"].endswith(LEMBRETE)


def test_frase_de_recusa_colada_no_fim_de_uma_resposta_nao_e_recusa():
    v = verificar(f"Use as chaves read e write [1].\n\n{RECUSA}", fontes())
    assert not v.recusou
    assert v.citadas == [1]
