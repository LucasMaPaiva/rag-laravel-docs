from rag_laravel.busca import Resultado, fundir_rrf


def r(id_):
    return Resultado(id=id_, pagina="p", ancora=id_, caminho="c", url="u", pontuacao=0.0)


def test_rrf_premia_quem_aparece_bem_nas_duas_listas():
    vetorial = [r("a"), r("b"), r("c")]
    trigramas = [r("c"), r("a"), r("d")]
    ordem = [x.id for x in fundir_rrf([vetorial, trigramas], k=4)]
    assert ordem[0] == "a"
    assert set(ordem) == {"a", "b", "c", "d"}


def test_rrf_respeita_k():
    assert len(fundir_rrf([[r("a"), r("b"), r("c")]], k=2)) == 2


def test_rrf_com_peso_menor_a_lista_fraca_perde_o_empate():
    forte = [r("a"), r("b")]
    fraca = [r("b"), r("a")]
    assert [x.id for x in fundir_rrf([forte, fraca], k=2)] in (["a", "b"], ["b", "a"])
    assert [x.id for x in fundir_rrf([forte, fraca], k=2, pesos=[1.0, 0.3])] == ["a", "b"]


def test_rrf_exige_um_peso_por_lista():
    import pytest

    with pytest.raises(ValueError):
        fundir_rrf([[r("a")], [r("b")]], pesos=[1.0])
