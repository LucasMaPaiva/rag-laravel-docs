"""Quebra as páginas da documentação do Laravel em trechos (chunks) por seção.

Formato de entrada (laravel/docs): título em ``#``, um índice de links, e cada seção
precedida por ``<a name="ancora"></a>`` e um título ``##``, ``###`` ou ``####``.

Cada trecho guarda o caminho de títulos (para dar contexto ao embedding), a âncora e a
URL pública, e nunca corta um bloco de código ao meio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BASE_URL = "https://laravel.com/docs/{versao}/{pagina}"
ANCORA = re.compile(r'^<a name="([^"]+)"></a>\s*$')
TITULO = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
CERCA = re.compile(r"^\s*(```|~~~)")


@dataclass
class Trecho:
    pagina: str
    titulo_pagina: str
    secoes: list[str]
    ancora: str | None
    texto: str
    versao: str = "13.x"
    indice: int = 0
    extras: dict = field(default_factory=dict)

    @property
    def caminho(self) -> str:
        return " > ".join([self.titulo_pagina, *self.secoes])

    @property
    def url(self) -> str:
        url = BASE_URL.format(versao=self.versao, pagina=self.pagina)
        return f"{url}#{self.ancora}" if self.ancora else url

    @property
    def id(self) -> str:
        return f"{self.pagina}#{self.ancora or 'inicio'}:{self.indice}"

    def texto_para_embedding(self) -> str:
        """O caminho de títulos entra no texto: ajuda a busca a saber de que trecho se trata."""
        return f"{self.caminho}\n\n{self.texto}"


def _dividir_paragrafos(texto: str, limite: int) -> list[str]:
    """Divide um texto longo em partes de até ``limite`` caracteres, sem cortar código."""
    if len(texto) <= limite:
        return [texto]
    blocos: list[str] = []
    atual: list[str] = []
    dentro_de_codigo = False
    for linha in texto.split("\n"):
        if CERCA.match(linha):
            dentro_de_codigo = not dentro_de_codigo
        atual.append(linha)
        fim_de_paragrafo = linha.strip() == "" and not dentro_de_codigo
        if fim_de_paragrafo and len("\n".join(atual)) >= limite:
            blocos.append("\n".join(atual).strip())
            atual = []
    if atual and "\n".join(atual).strip():
        blocos.append("\n".join(atual).strip())
    return blocos


def quebrar_pagina(conteudo: str, pagina: str, versao: str = "13.x", limite: int = 2000) -> list[Trecho]:
    """Transforma o markdown de uma página em trechos, um por seção (com subdivisão se longa)."""
    linhas = conteudo.splitlines()
    titulo_pagina = pagina
    pilha: list[tuple[int, str]] = []  # (nível, título) das seções abertas
    ancora_pendente: str | None = None
    ancora_atual: str | None = None
    corpo: list[str] = []
    trechos: list[Trecho] = []
    dentro_de_codigo = False
    no_indice = False

    def fechar() -> None:
        texto = "\n".join(corpo).strip()
        corpo.clear()
        if not texto:
            return
        secoes = [t for _, t in pilha]
        for i, parte in enumerate(_dividir_paragrafos(texto, limite)):
            trechos.append(
                Trecho(pagina=pagina, titulo_pagina=titulo_pagina, secoes=secoes,
                       ancora=ancora_atual, texto=parte, versao=versao, indice=i)
            )

    for linha in linhas:
        if CERCA.match(linha):
            dentro_de_codigo = not dentro_de_codigo
        if not dentro_de_codigo:
            if m := ANCORA.match(linha):
                ancora_pendente = m.group(1)
                continue
            if m := TITULO.match(linha):
                nivel, titulo = len(m.group(1)), m.group(2)
                if nivel == 1:
                    titulo_pagina = titulo
                    no_indice = True
                    continue
                fechar()
                while pilha and pilha[-1][0] >= nivel:
                    pilha.pop()
                pilha.append((nivel, titulo))
                ancora_atual, ancora_pendente = ancora_pendente, None
                no_indice = False
                continue
            if no_indice:
                # Índice de links logo depois do título da página: não é conteúdo.
                continue
        corpo.append(linha)
    fechar()
    return trechos


def quebrar_diretorio(pasta: Path, versao: str = "13.x", limite: int = 2000) -> list[Trecho]:
    trechos: list[Trecho] = []
    for arquivo in sorted(pasta.glob("*.md")):
        if arquivo.name.lower() in {"readme.md", "license.md", "documentation.md"}:
            continue
        trechos += quebrar_pagina(arquivo.read_text(encoding="utf-8"), arquivo.stem, versao, limite)
    return trechos
