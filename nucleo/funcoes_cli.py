"""Porta de entrada das funções para os agentes (OpenCode, Codex, Claude Code).

  python nucleo/funcoes_cli.py listar
  python nucleo/funcoes_cli.py agenda acao=ver
  python nucleo/funcoes_cli.py fazer_orcamento servico=impressao descricao="banner" quantidades_json='{"area_m2":0.54,"acabamentos":4}' pecas=1
  python nucleo/funcoes_cli.py agenda '{"acao": "marcar", "data": "2026-11-10", "hora": "14:00", "nome": "Ana", "assunto": "visita"}'

Quem está falando (o contexto) vem da variável GI_CONTEXTO, colocada pela Central.
A IA não escolhe o cliente: isso impede que uma conversa mexa nos dados de outra pessoa.
Resposta sempre em JSON: {"ok": true/false, "resultado": "..."}.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import funcoes  # noqa: E402
import registro  # noqa: E402


def _valor(texto: str):
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def _dados(args: list[str]) -> dict:
    if len(args) == 1 and args[0].strip().startswith("{"):
        return json.loads(args[0])
    out = {}
    for a in args:
        if "=" not in a:
            raise ValueError(f"Use nome=valor (recebi: {a})")
        k, v = a.split("=", 1)
        out[k.strip()] = _valor(v) if k.strip() not in ("quantidades_json",) else v
    return out


def _ajustar(mod, dados: dict) -> dict:
    """Completa campos que faltaram e acerta números, conforme CAMPOS da função."""
    props = mod.CAMPOS.get("properties", {})
    for nome, regra in props.items():
        tipo = regra.get("type")
        if nome not in dados:
            dados[nome] = 0 if tipo in ("integer", "number") else ""
        elif tipo == "integer":
            dados[nome] = int(float(dados[nome] or 0))
        elif tipo == "number":
            dados[nome] = float(dados[nome] or 0)
        elif tipo == "string" and not isinstance(dados[nome], str):
            dados[nome] = json.dumps(dados[nome], ensure_ascii=False)
    return dados


def main() -> None:
    mods = funcoes.carregar()
    if len(sys.argv) < 2 or sys.argv[1] == "listar":
        for m in mods.values():
            campos = ", ".join(m.CAMPOS.get("properties", {}))
            print(f"- {m.NOME}({campos}): {' '.join(m.QUANDO_USAR.split())}")
        return
    nome = sys.argv[1]
    try:
        contexto = json.loads(os.environ.get("GI_CONTEXTO") or "{}")
    except ValueError:
        contexto = {}
    try:
        dados = _dados(sys.argv[2:])
    except ValueError as e:
        print(json.dumps({"ok": False, "resultado": str(e)}, ensure_ascii=False))
        return
    if nome in mods:
        dados = _ajustar(mods[nome], dados)
    r = funcoes.executar(mods, nome, dados, contexto)
    registro.evento("funcao", jid=contexto.get("jid", ""), funcao=nome, ok=r["ok"])
    print(json.dumps(r, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
