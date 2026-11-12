"""Interface web local para testar a busca, sem dependências além da biblioteca padrão.

    uv run python -m rag_laravel.web            # abre em http://127.0.0.1:8470
    uv run python -m rag_laravel.web --porta 9000

Rotas:
    GET /                                         página de busca
    GET /api/buscar?q=...&estrategia=...&k=5      resultados em JSON
    GET /api/perguntar?q=...                      resposta com citação, em NDJSON (um evento por linha)
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rag_laravel import banco, busca, geracao

PAGINA = Path(__file__).resolve().parent / "web" / "index.html"
TAMANHO_TRECHO = 700

# Nome, rótulo e função de cada estratégia exposta na interface.
ESTRATEGIAS = {
    "hibrida-bge-t0.2": ("Híbrida, bge-m3 (trigramas 0,2)", lambda c, q, k: busca.hibrida(c, q, "bge", k, peso_trigramas=0.2)),
    "vetorial-bge": ("Vetorial, bge-m3", lambda c, q, k: busca.vetorial(c, q, "bge", k)),
    "trigramas": ("Trigramas (pg_trgm)", lambda c, q, k: busca.trigramas(c, q, k)),
    "vetorial-nomic": ("Vetorial, nomic-embed-text", lambda c, q, k: busca.vetorial(c, q, "nomic", k)),
    "hibrida-bge": ("Híbrida, bge-m3 (pesos iguais)", lambda c, q, k: busca.hibrida(c, q, "bge", k)),
}


def resumir(texto: str, limite: int = TAMANHO_TRECHO) -> str:
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    corte = texto.rfind(" ", 0, limite)
    return texto[: corte if corte > 0 else limite].rstrip() + " …"


def buscar(pergunta: str, estrategia: str, k: int) -> dict:
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"estratégia desconhecida: {estrategia}")
    pergunta = pergunta.strip()
    if not pergunta:
        raise ValueError("pergunta vazia")
    k = max(1, min(k, 20))
    with banco.conectar() as conn:
        inicio = time.perf_counter()
        resultados = ESTRATEGIAS[estrategia][1](conn, pergunta, k)
        ms = (time.perf_counter() - inicio) * 1000
        textos = dict(
            conn.execute(
                "SELECT id, texto FROM trechos WHERE id = ANY(%s)", ([r.id for r in resultados],)
            ).fetchall()
        )
    return {
        "estrategia": estrategia,
        "rotulo": ESTRATEGIAS[estrategia][0],
        "ms": round(ms),
        "resultados": [
            {
                "secao": r.secao,
                "caminho": r.caminho,
                "url": r.url,
                "pontuacao": r.pontuacao,
                "trecho": resumir(textos.get(r.id, "")),
            }
            for r in resultados
        ],
    }


class Manipulador(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (nome exigido pelo http.server)
        url = urlparse(self.path)
        if url.path == "/":
            self._enviar(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/estrategias":
            dados = [{"id": k, "rotulo": v[0]} for k, v in ESTRATEGIAS.items()]
            self._json(200, dados)
        elif url.path == "/api/buscar":
            params = parse_qs(url.query)
            try:
                dados = buscar(
                    params.get("q", [""])[0],
                    params.get("estrategia", ["hibrida-bge-t0.2"])[0],
                    int(params.get("k", ["5"])[0]),
                )
            except ValueError as erro:
                self._json(400, {"erro": str(erro)})
                return
            except Exception as erro:  # banco ou Ollama fora do ar
                self._json(503, {"erro": f"{type(erro).__name__}: {erro}"})
                return
            self._json(200, dados)
        elif url.path == "/api/perguntar":
            self._perguntar(parse_qs(url.query).get("q", [""])[0].strip())
        else:
            self._json(404, {"erro": "rota não encontrada"})

    def _perguntar(self, pergunta: str) -> None:
        """Manda os eventos da geração conforme chegam: fontes, pedaços de texto e a verificação."""
        if not pergunta:
            self._json(400, {"erro": "pergunta vazia"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def enviar(evento: dict) -> None:
            self.wfile.write((json.dumps(evento, ensure_ascii=False) + "\n").encode())
            self.wfile.flush()

        try:
            with banco.conectar() as conn:
                for evento in geracao.responder(conn, pergunta):
                    enviar(evento)
        except (BrokenPipeError, ConnectionResetError):
            pass  # quem pediu fechou a página
        except Exception as erro:  # banco ou Ollama fora do ar, modelo não baixado
            enviar({"tipo": "erro", "erro": f"{type(erro).__name__}: {erro}"})

    def _json(self, status: int, dados) -> None:
        self._enviar(status, json.dumps(dados, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _enviar(self, status: int, corpo: bytes, tipo: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, formato: str, *args) -> None:
        print(f"{self.address_string()} {formato % args}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--porta", type=int, default=8470)
    args = parser.parse_args()
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), Manipulador)
    print(f"Interface em http://127.0.0.1:{args.porta} (Ctrl+C para sair)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
