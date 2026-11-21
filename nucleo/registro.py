"""Tudo o que acontece vira uma linha em dados/eventos.jsonl.

É daí que saem os números do painel (o "BI" do líder).
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime

from config import DADOS

EVENTOS = DADOS / "eventos.jsonl"
FILA = DADOS / "fila.json"
HUMANO = DADOS / "com_humano.json"
_trava = threading.Lock()


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def evento(tipo: str, **dados) -> dict:
    linha = {"ts": agora(), "tipo": tipo, **dados}
    with _trava, EVENTOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


def eventos(desde: str = "") -> list[dict]:
    if not EVENTOS.exists():
        return []
    out = []
    for l in EVENTOS.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("ts", "") >= desde:
            out.append(e)
    return out


def _ler(arq, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar(arq, valor) -> None:
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(valor, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(arq)


# ---------- fila de respostas esperando aprovação ----------
def fila() -> list[dict]:
    return _ler(FILA, [])


def na_fila(item: dict) -> dict:
    with _trava:
        itens = [i for i in _ler(FILA, []) if i["jid"] != item["jid"]]  # 1 rascunho por conversa
        item = {"id": uuid.uuid4().hex[:10], "criado": agora(), **item}
        itens.append(item)
        _gravar(FILA, itens)
    return item


def tirar_da_fila(item_id: str) -> dict | None:
    with _trava:
        itens = _ler(FILA, [])
        achado = next((i for i in itens if i["id"] == item_id), None)
        _gravar(FILA, [i for i in itens if i["id"] != item_id])
    return achado


# ---------- conversas que estão com um humano ----------
def com_humano() -> dict:
    return _ler(HUMANO, {})


def passar_para_humano(jid: str, motivo: str) -> None:
    with _trava:
        d = _ler(HUMANO, {})
        d[jid] = {"desde": agora(), "motivo": motivo}
        _gravar(HUMANO, d)


def devolver_para_ia(jid: str) -> None:
    with _trava:
        d = _ler(HUMANO, {})
        d.pop(jid, None)
        _gravar(HUMANO, d)


def esta_com_humano(jid: str) -> bool:
    return jid in _ler(HUMANO, {})


def hoje() -> str:
    return time.strftime("%Y-%m-%d")
