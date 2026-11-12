import pytest

from rag_laravel.web import buscar, resumir


def test_resumir_mantem_texto_curto():
    assert resumir("abc", limite=10) == "abc"


def test_resumir_corta_em_palavra():
    assert resumir("um dois tres quatro", limite=9) == "um dois …"


@pytest.mark.parametrize(("pergunta", "estrategia"), [("  ", "vetorial-bge"), ("oi", "nao-existe")])
def test_buscar_rejeita_entrada_invalida_antes_de_ir_ao_banco(pergunta, estrategia):
    with pytest.raises(ValueError):
        buscar(pergunta, estrategia, 5)
