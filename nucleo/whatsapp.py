"""Conversa com o WhatsApp através da bridge (bridge/bridge.exe).

- Ler conversas: direto no banco messages.db da bridge (somente leitura).
- Enviar: POST /api/send da bridge.
- Baixar mídia: POST /api/download da bridge.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.request
from contextlib import closing
from pathlib import Path

from config import BRIDGE_URL, MENSAGENS_DB

WHATSAPP_DB = MENSAGENS_DB.with_name("whatsapp.db")


def _ler(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _post(caminho: str, corpo: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        BRIDGE_URL + caminho,
        data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def enviar(destino: str, texto: str = "", arquivo: str = "") -> bool:
    """destino = telefone (5500000000000) ou JID (…@s.whatsapp.net, …@lid, …@g.us)."""
    corpo = {"recipient": destino, "message": texto}
    if arquivo:
        corpo["media_path"] = str(Path(arquivo).resolve())
    try:
        return bool(_post("/api/send", corpo).get("success"))
    except OSError:
        return False


def digitando(destino: str, ligado: bool = True) -> None:
    try:
        _post("/api/typing", {"recipient": destino, "state": "composing" if ligado else "paused"}, 10)
    except OSError:
        pass


def baixar_midia(message_id: str, chat_jid: str) -> str:
    """Devolve o caminho do arquivo baixado ou '' se não deu."""
    try:
        r = _post("/api/download", {"message_id": message_id, "chat_jid": chat_jid}, 120)
        return r.get("path", "") if r.get("success") else ""
    except OSError:
        return ""


def bridge_no_ar() -> bool:
    try:
        with urllib.request.urlopen(BRIDGE_URL + "/health", timeout=5):
            return True
    except OSError:
        return False


def jids_da_mesma_pessoa(chat_jid: str) -> list[str]:
    """O WhatsApp pode guardar a MESMA pessoa em dois endereços (número e 'lid').

    Lição real: ler só um deles faz a IA perder metade da conversa.
    """
    jids = {chat_jid}
    usuario = chat_jid.split("@")[0]
    if WHATSAPP_DB.exists():
        try:
            with closing(_ler(WHATSAPP_DB)) as w:
                for lid, pn in w.execute(
                        "select lid, pn from whatsmeow_lid_map where lid=? or pn=?", (usuario, usuario)):
                    jids.add(f"{pn}@s.whatsapp.net")
                    jids.add(f"{lid}@lid")
        except sqlite3.Error:
            pass
    return sorted(jids)


def conversa(chat_jid: str, limite: int = 80) -> list[dict]:
    """Últimas mensagens da conversa, juntando todos os endereços da pessoa."""
    jids = jids_da_mesma_pessoa(chat_jid)
    marcas = ",".join("?" * len(jids))
    with closing(_ler(MENSAGENS_DB)) as m:
        linhas = m.execute(
            f"select id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename "
            f"from messages where chat_jid in ({marcas}) order by timestamp desc limit ?",
            (*jids, limite)).fetchall()
    msgs = [dict(l) for l in reversed(linhas)]
    vistos, unicas = set(), []
    for msg in msgs:
        if msg["id"] in vistos:
            continue
        vistos.add(msg["id"])
        unicas.append(msg)
    return unicas


def nome_do_contato(chat_jid: str) -> str:
    try:
        with closing(_ler(MENSAGENS_DB)) as m:
            r = m.execute("select name from chats where jid=?", (chat_jid,)).fetchone()
            return (r["name"] if r else "") or ""
    except sqlite3.Error:
        return ""


def como_texto(msgs: list[dict], nome_empresa: str = "Empresa", max_chars: int = 60000) -> str:
    """Transforma a conversa em texto para a IA ler."""
    linhas = []
    for m in msgs:
        quem = nome_empresa if m["is_from_me"] else "Cliente"
        texto = (m.get("content") or "").strip()
        if m.get("media_type"):
            texto = f"[{m['media_type']}{': ' + m['filename'] if m.get('filename') else ''}] {texto}".strip()
        if texto:
            linhas.append(f"[{str(m['timestamp'])[:16]}] {quem}: {texto[:1500]}")
    txt = "\n".join(linhas)
    if len(txt) <= max_chars:
        return txt
    # começo (como chegou) + final (como está agora)
    inicio, fim, n = linhas[:15], [], sum(len(l) + 1 for l in linhas[:15])
    for l in reversed(linhas[15:]):
        if n + len(l) > max_chars - 200:
            break
        fim.append(l)
        n += len(l) + 1
    return "\n".join(inicio) + "\n[... mensagens do meio omitidas ...]\n" + "\n".join(reversed(fim))


def conversas_1a1(ate: str = "", desde: str = "") -> dict[str, list[dict]]:
    """Todas as conversas individuais (sem grupos), opcionalmente num período (AAAA-MM-DD)."""
    filtro, args = "", []
    if desde:
        filtro += " and timestamp >= ?"
        args.append(desde)
    if ate:
        filtro += " and timestamp < ?"
        args.append(ate)
    out: dict[str, list[dict]] = {}
    with closing(_ler(MENSAGENS_DB)) as m:
        for l in m.execute(
                "select id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename from messages "
                "where chat_jid not like '%@g.us' and chat_jid not like '%broadcast%' "
                f"and chat_jid not like '%@newsletter' {filtro} order by chat_jid, timestamp", args):
            out.setdefault(l["chat_jid"], []).append(dict(l))
    # só conversas em que o cliente falou alguma coisa
    return {j: ms for j, ms in out.items() if any(not x["is_from_me"] for x in ms)}


def mensagens_do_grupo(grupo_jid: str, depois_de: str = "", limite: int = 200) -> list[dict]:
    with closing(_ler(MENSAGENS_DB)) as m:
        linhas = m.execute(
            "select id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename from messages "
            "where chat_jid=? and timestamp > ? order by timestamp limit ?",
            (grupo_jid, depois_de or "0", limite)).fetchall()
    return [dict(l) for l in linhas]


def ultimas_do_grupo(grupo_jid: str, n: int = 30) -> list[dict]:
    with closing(_ler(MENSAGENS_DB)) as m:
        linhas = m.execute(
            "select id, chat_jid, sender, content, timestamp, is_from_me from messages "
            "where chat_jid=? order by timestamp desc limit ?", (grupo_jid, n)).fetchall()
    return [dict(l) for l in reversed(linhas)]


def grupos() -> list[dict]:
    with closing(_ler(MENSAGENS_DB)) as m:
        return [dict(r) for r in m.execute(
            "select jid, name, last_message_time from chats where jid like '%@g.us' order by last_message_time desc")]
