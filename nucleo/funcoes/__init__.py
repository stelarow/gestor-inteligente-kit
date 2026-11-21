"""Funções do agente.

Cada função é um arquivo nesta pasta com:
  NOME        nome curto, sem espaço (vira o nome da ferramenta da IA)
  QUANDO_USAR texto explicando para a IA quando usar
  CAMPOS      o que a IA precisa preencher (formato JSON Schema)
  executar(dados, contexto) -> dict com pelo menos {"ok": bool, "resultado": str}

Para ligar ou desligar uma função, edite empresa/funcoes.json.
Para criar uma função nova, copie _modelo.py e peça ao seu agente para adaptar.

Regra principal: a função faz a coisa DE VERDADE e devolve o que aconteceu.
A IA só diz "feito" para o cliente depois que a função devolveu ok=True.
"""
from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path

from config import EMPRESA


def _ligadas() -> list[str] | None:
    arq = EMPRESA / "funcoes.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8")).get("ligadas")
    except (OSError, ValueError):
        return None


def carregar(somente: list[str] | None = None) -> dict:
    ligadas = somente if somente is not None else _ligadas()
    mods = {}
    for info in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"funcoes.{info.name}")
        if not hasattr(mod, "NOME"):
            continue
        if ligadas is None or mod.NOME in ligadas:
            mods[mod.NOME] = mod
    return mods


def ferramentas(mods: dict) -> list[dict]:
    """Formato de ferramenta da API do Claude."""
    out = []
    for mod in mods.values():
        schema = {"type": "object", "additionalProperties": False, **mod.CAMPOS}
        schema.setdefault("required", list(mod.CAMPOS.get("properties", {}).keys()))
        out.append({"name": mod.NOME, "description": mod.QUANDO_USAR.strip(),
                    "strict": True, "input_schema": schema})
    return out


def executar(mods: dict, nome: str, dados: dict, contexto: dict) -> dict:
    mod = mods.get(nome)
    if not mod:
        return {"ok": False, "resultado": f"Função '{nome}' não existe ou está desligada."}
    try:
        r = mod.executar(dados, contexto)
    except Exception as e:  # noqa: BLE001 — a IA precisa saber que falhou
        return {"ok": False, "resultado": f"Erro ao executar: {e}"}
    r.setdefault("ok", False)
    r.setdefault("resultado", "")
    return r
