"""Os motores de IA do sistema (o mesmo desenho que usamos na prática):

1. RESPOSTAS  -> OpenCode (modelo rápido e barato, ex.: DeepSeek Flash). Lê a conversa + manual,
                 chama as funções e devolve a resposta em JSON.
2. TAREFAS    -> Codex ou Claude Code. Para trabalho demorado e complexo no computador
                 (ex.: abrir o arquivo do cliente, medir e orçar). Roda numa pasta própria e entrega
                 result.json + result.ready.
3. DECISÕES   -> Jev (jev.py). Notas e escolhas em números, em massa e barato.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from config import DADOS, RAIZ, env

MODELO_RESPOSTAS = env("GI_MODELO_RESPOSTAS", "opencode-go/deepseek-v4.1-flash")
MOTOR_TAREFAS = env("GI_MOTOR_TAREFAS", "codex")          # codex | claude
MODELO_TAREFAS = env("GI_MODELO_TAREFAS", "")              # vazio = padrão do motor
TEMPO_RESPOSTA = int(env("GI_TEMPO_RESPOSTA", "240"))
TEMPO_TAREFA = int(env("GI_TEMPO_TAREFA", "1800"))


class MotorFalhou(RuntimeError):
    pass


def _exe(nome: str) -> str:
    achado = shutil.which(nome)
    if not achado:
        raise MotorFalhou(f"Não achei o programa '{nome}'. Instale e faça login (veja guia/encontro-2.md).")
    return achado


def _json_do_texto(texto: str) -> dict | None:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        v = json.loads(texto)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini >= 0 and fim > ini:
        try:
            v = json.loads(texto[ini:fim + 1])
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    return None


def _ler_eventos_opencode(saida: str) -> tuple[dict | None, dict]:
    """`opencode run --format json` solta uma linha JSON por evento; a resposta é o último texto."""
    textos, info = [], {"custo": None, "erros": []}
    for linha in saida.splitlines():
        try:
            ev = json.loads(linha)
        except ValueError:
            continue
        if ev.get("type") == "text":
            t = str((ev.get("part") or {}).get("text") or "").strip()
            if t:
                textos.append(t)
        elif ev.get("type") == "step_finish":
            info["custo"] = (ev.get("part") or {}).get("cost", info["custo"])
        elif ev.get("type") == "error":
            erro = ev.get("error") or {}
            info["erros"].append(str((erro.get("data") or {}).get("message") or erro.get("message") or erro)[:300])
    for t in reversed(textos):
        v = _json_do_texto(t)
        if v is not None:
            return v, info
    return None, info


def opencode_json(prompt: str, agente: str, contexto: dict | None = None, tentativas: int = 2) -> dict:
    """Roda o agente do OpenCode (.opencode/agents/<agente>.md) e devolve o JSON da resposta.

    O contexto (quem está falando) vai por variável de ambiente para as funções:
    a IA não consegue trocar o cliente de uma função para outro número.
    """
    DADOS.mkdir(parents=True, exist_ok=True)
    fd, caminho = tempfile.mkstemp(prefix="pedido_", suffix=".txt", dir=str(DADOS))
    os.close(fd)
    arq = Path(caminho)
    arq.write_text(prompt, encoding="utf-8")
    ambiente = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                "GI_CONTEXTO": json.dumps(contexto or {}, ensure_ascii=False)}
    cmd = [_exe("opencode"), "run",
           "Leia integralmente o arquivo anexado e responda somente com o JSON final pedido nele.",
           "--pure", "--model", MODELO_RESPOSTAS, "--agent", agente, "--format", "json",
           "--dir", str(RAIZ), "--auto", "--file", str(arq)]
    ultimo_erro = ""
    try:
        for _ in range(max(1, tentativas)):
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=TEMPO_RESPOSTA, cwd=str(RAIZ), env=ambiente, check=False)
            except subprocess.TimeoutExpired:
                ultimo_erro = f"OpenCode demorou mais de {TEMPO_RESPOSTA}s"
                continue
            v, info = _ler_eventos_opencode(p.stdout or "")
            if v is not None:
                v["_custo"] = info["custo"]
                return v
            ultimo_erro = "; ".join(info["erros"]) or (p.stderr or "")[-300:] or "OpenCode não devolveu JSON"
        raise MotorFalhou(ultimo_erro)
    finally:
        arq.unlink(missing_ok=True)


def rodar_tarefa(pasta: Path, instrucoes: str, motor: str = "") -> dict:
    """Roda Codex ou Claude Code na pasta da tarefa e espera result.json + result.ready."""
    motor = (motor or MOTOR_TAREFAS).lower()
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "request.txt").write_text(instrucoes, encoding="utf-8")
    pedido = ("Leia request.txt nesta pasta e execute a tarefa completa. Ao terminar, grave result.json "
              "no formato pedido e só depois crie o arquivo vazio result.ready.")
    if motor == "claude":
        cmd = [_exe("claude"), "-p", pedido, "--output-format", "json", "--dangerously-skip-permissions",
               "--add-dir", str(RAIZ)]
        if MODELO_TAREFAS:
            cmd += ["--model", MODELO_TAREFAS]
    else:
        cmd = [_exe("codex"), "exec", pedido, "--cd", str(pasta), "--skip-git-repo-check",
               "--dangerously-bypass-approvals-and-sandbox", "-o", str(pasta / "ultima_mensagem.txt")]
        if MODELO_TAREFAS:
            cmd += ["--model", MODELO_TAREFAS]
    inicio = time.time()
    with (pasta / "motor.log").open("w", encoding="utf-8") as log:
        try:
            subprocess.run(cmd, cwd=str(pasta), stdout=log, stderr=subprocess.STDOUT, timeout=TEMPO_TAREFA,
                           env={**os.environ, "PYTHONUTF8": "1", "GI_RAIZ": str(RAIZ)}, check=False)
        except subprocess.TimeoutExpired:
            return {"ok": False, "mensagem": "", "erro": f"A tarefa passou de {TEMPO_TAREFA // 60} minutos."}
    if not (pasta / "result.ready").exists() or not (pasta / "result.json").exists():
        return {"ok": False, "mensagem": "", "erro": "O motor terminou sem entregar o resultado (veja motor.log)."}
    try:
        r = json.loads((pasta / "result.json").read_text(encoding="utf-8"))
    except ValueError:
        return {"ok": False, "mensagem": "", "erro": "result.json inválido."}
    r.setdefault("ok", True)
    r["segundos"] = round(time.time() - inicio)
    # só envia arquivos que estão DENTRO da pasta da tarefa
    r["arquivos"] = [str((pasta / a).resolve()) for a in r.get("arquivos", [])
                     if (pasta / a).resolve().is_relative_to(pasta.resolve()) and (pasta / a).exists()]
    return r
