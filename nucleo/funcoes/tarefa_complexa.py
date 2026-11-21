"""Pede um trabalho demorado ao motor de TAREFAS (Codex ou Claude Code).

Exemplo: orçamento a partir de um arquivo enviado. O agente no computador abre o arquivo,
mede de verdade e calcula o preço pela função da empresa.

Os tipos de tarefa ficam em empresa/tarefas/<tipo>.md (as instruções para o motor).
A tarefa roda em segundo plano; quando termina, o resultado é enviado na mesma conversa.
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import registro
from config import DADOS, EMPRESA

NOME = "pedir_tarefa_complexa"
PASTA_TIPOS = EMPRESA / "tarefas"


def tipos() -> list[str]:
    return sorted(p.stem for p in PASTA_TIPOS.glob("*.md")) if PASTA_TIPOS.exists() else []


QUANDO_USAR = f"""
Use para trabalho demorado que precisa de um agente no computador (minutos, não segundos).
Tipos disponíveis: {", ".join(tipos()) or "nenhum"}.
Depois de pedir, diga ao cliente que já está trabalhando e que manda o resultado aqui na conversa.
Não invente o resultado: ele chega sozinho quando ficar pronto.
"""

CAMPOS = {
    "properties": {
        "tipo": {"type": "string", "description": "Um dos tipos disponíveis."},
        "pedido": {"type": "string", "description": "O que o cliente pediu, com links, quantidades e detalhes."},
    },
}


def executar(dados: dict, contexto: dict) -> dict:
    if dados["tipo"] not in tipos():
        return {"ok": False, "resultado": f"Tipo desconhecido. Use um destes: {', '.join(tipos())}"}
    tid = uuid.uuid4().hex[:8]
    pasta = DADOS / "tarefas" / tid
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "pedido.json").write_text(json.dumps({
        "id": tid, "tipo": dados["tipo"], "pedido": dados["pedido"], "jid": contexto.get("jid", ""),
        "nome": contexto.get("nome", ""), "criado": registro.agora()}, ensure_ascii=False, indent=2), encoding="utf-8")
    registro.evento("tarefa_pedida", jid=contexto.get("jid", ""), tipo_tarefa=dados["tipo"], tarefa=tid)
    if not contexto.get("simulacao"):
        executor = Path(__file__).resolve().parents[1] / "tarefa_complexa.py"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([sys.executable, "-X", "utf8", str(executor), tid], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return {"ok": True, "resultado": f"Tarefa {tid} iniciada. O resultado será enviado nesta conversa em alguns minutos."}
