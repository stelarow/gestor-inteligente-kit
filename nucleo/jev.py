"""Jev (TypeSafe): IA rápida e barata que dá NOTAS e ESCOLHAS sobre um texto.

Bom para: ler milhares de conversas antigas, dar nota de interesse, decidir se uma
mensagem do grupo é um pedido de tarefa. A resposta vem em números (0 a 1), não em texto,
então o código consegue usar direto.

Chave: variável TYPESAFE_API_KEY (no .env ou no Windows).

Tipos de pergunta:
  noul   -> sim/não com probabilidade        {"type": "noul", "instructions": "..."}
  choice -> escolhe uma opção                {"type": "choice", "instructions": "...", "criteria": {"a": "...", "b": "..."}}
  score  -> nota em níveis (0..n-1)          {"type": "score", "instructions": "...", "criteria": ["nível 0", "nível 1", ...]}
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from config import JEV_MODELO, env

URL = "https://api.typesafe.ai/v1/systemone"


def chave() -> str:
    return env("TYPESAFE_API_KEY")


def perguntar(estado: dict, perguntas: dict, modelo: str = JEV_MODELO) -> dict:
    """estado = o que o Jev deve ler (ex.: a conversa). perguntas = o que ele deve julgar."""
    if not chave():
        raise RuntimeError("Falta a chave TYPESAFE_API_KEY no arquivo .env")
    corpo = json.dumps({"model": modelo, "state": estado, "questions": perguntas}, ensure_ascii=False).encode()
    espera = 2.0
    for tentativa in range(6):
        req = urllib.request.Request(URL, data=corpo, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + chave()})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504, 529) or tentativa == 5:
                raise RuntimeError(f"Jev respondeu HTTP {e.code}: {e.read()[:300]!r}") from None
            espera = float(e.headers.get("retry-after") or espera * 2)
        except (urllib.error.URLError, TimeoutError):
            if tentativa == 5:
                raise
            espera *= 2
        time.sleep(min(espera, 60))
    raise RuntimeError("Jev sem resposta")
