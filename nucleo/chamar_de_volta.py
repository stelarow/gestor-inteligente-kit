"""Chamar de volta quem sumiu (remarketing), com mensagem escrita NO DIA para cada pessoa.

Regras (aprendidas na prática):
- A mensagem é escrita na hora do envio, lendo a conversa como está AGORA.
  Nunca deixe mensagens prontas de dias antes: a conversa pode ter mudado.
- Não chama quem pediu para parar, quem já é cliente ou quem quer algo que a empresa não tem
  (empresa/produtos.json, campo "tem").
- Limite por dia, um envio por vez, com intervalo. Nunca rode dois envios ao mesmo tempo.

Uso:
  python nucleo/chamar_de_volta.py                 (SIMULA: mostra quem seria chamado e a mensagem)
  python nucleo/chamar_de_volta.py --enviar        (envia de verdade)
  python nucleo/chamar_de_volta.py --limite 10 --faixa quente
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agente  # noqa: E402
import motores  # noqa: E402
import registro  # noqa: E402
import whatsapp  # noqa: E402
from config import DADOS, EMPRESA  # noqa: E402

CHAMADOS = DADOS / "chamados.jsonl"
TRAVA = DADOS / "chamar_de_volta.lock"

def ja_chamados(dias: int) -> set[str]:
    limite = (datetime.now() - timedelta(days=dias)).isoformat()
    out = set()
    if CHAMADOS.exists():
        for l in CHAMADOS.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(l)
            except ValueError:
                continue
            if c["ts"] >= limite:
                out.add(c["jid"])
    return out


def escrever(jid: str, contato: dict) -> dict:
    """A mensagem é escrita AGORA, lendo a conversa como está hoje (motor de respostas: OpenCode)."""
    msgs = whatsapp.conversa(jid, 120)
    pedido = (
        "Você escreve UMA mensagem de WhatsApp para retomar contato com alguém que conversou com a empresa e "
        "parou de responder. Leia a conversa inteira. Seja pessoal, curto (até 3 frases), lembre do que a "
        "pessoa queria e dê um motivo real para responder (novidade, condição, horário que abriu), usando SÓ "
        "informações dos arquivos da empresa. Não use funções. Se a conversa mostrar que não faz sentido chamar "
        "(já comprou, pediu para parar, a empresa não tem o que ela quer, foi chamada há pouco), devolva chamar=false.\n\n"
        f"## Arquivos da empresa\n{agente.manual()}\n\n"
        f"Hoje: {date.today().strftime('%d/%m/%Y')}. Nota do contato: {contato['nota']} ({contato['faixa']}), "
        f"interesse: {contato['produto'] or 'não identificado'}, o que travou: {contato['trava']}\n\n"
        f"<conversa>\n{whatsapp.como_texto(msgs, 'Empresa')}\n</conversa>\n\n"
        'Responda somente com este JSON: {"chamar": true, "mensagem": "...", "motivo": "..."}')
    r = motores.opencode_json(pedido, "gi-atendimento", {"jid": jid, "canal": "cliente"})
    return {"chamar": bool(r.get("chamar")), "mensagem": str(r.get("mensagem", "")).strip(),
            "motivo": str(r.get("motivo", ""))}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--enviar", action="store_true")
    p.add_argument("--limite", type=int, default=20)
    p.add_argument("--faixa", choices=["quente", "morno", "todos"], default="todos")
    p.add_argument("--dias-sem-falar", type=int, default=7, help="Só quem está quieto há pelo menos N dias")
    p.add_argument("--nao-repetir-dias", type=int, default=30)
    a = p.parse_args()

    if a.enviar:
        try:
            fd = os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            sys.exit(f"Já existe um envio rodando (arquivo {TRAVA}). Se tem certeza que não, apague o arquivo.")
    try:
        _rodar(a)
    finally:
        if a.enviar and TRAVA.exists():
            TRAVA.unlink()


def _rodar(a) -> None:
    notas = json.loads((DADOS / "notas_contatos.json").read_text(encoding="utf-8"))
    nao_temos = {pr["nome"] for pr in json.loads((EMPRESA / "produtos.json").read_text(encoding="utf-8"))
                 if not pr.get("tem", True)}
    recentes = ja_chamados(a.nao_repetir_dias)
    corte = (date.today() - timedelta(days=a.dias_sem_falar)).isoformat()
    candidatos = [c for c in notas
                  if c["faixa"] in (("quente", "morno") if a.faixa == "todos" else (a.faixa,))
                  and not c["pediu_parar"] and c["produto"] not in nao_temos
                  and c["jid"] not in recentes and c["ultima"] <= corte
                  and not registro.esta_com_humano(c["jid"])]
    print(f"{len(candidatos)} candidatos; vou olhar até {a.limite}. Modo: {'ENVIAR' if a.enviar else 'SIMULAR'}")
    enviados = 0
    for c in candidatos:
        if enviados >= a.limite:
            break
        # revalida na hora: se a pessoa escreveu depois da nota, a nota está velha
        msgs = whatsapp.conversa(c["jid"], 5)
        if msgs and str(msgs[-1]["timestamp"])[:10] > c["ultima"]:
            print(f"- {c['nome']}: conversa mudou desde a nota, pulei")
            continue
        r = escrever(c["jid"], c)
        if not r["chamar"] or not r["mensagem"]:
            print(f"- {c['nome']}: não chamar ({r['motivo']})")
            continue
        print(f"+ {c['nome']} ({c['nota']}): {r['mensagem']}")
        if a.enviar:
            if whatsapp.enviar(c["jid"], r["mensagem"]):
                with CHAMADOS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": registro.agora(), "jid": c["jid"], "mensagem": r["mensagem"]},
                                       ensure_ascii=False) + "\n")
                registro.evento("chamado_de_volta", jid=c["jid"], nota=c["nota"])
                time.sleep(random.uniform(60, 150))  # intervalo para não parecer robô
            else:
                print("  falhou o envio — parei para conferir a conexão")
                break
        enviados += 1
    print(f"Fim: {enviados} {'enviados' if a.enviar else 'simulados'}.")


if __name__ == "__main__":
    main()
