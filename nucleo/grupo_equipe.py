"""IA no grupo da EQUIPE: qualquer pessoa do grupo pede uma tarefa em português normal
("marca a Ana na quinta 14h", "faz o orçamento desse link", "fechou a venda do João, 300 reais")
e a IA faz usando as funções, e confirma no grupo.

Como funciona (o mesmo desenho que usamos na prática):
1. Lê as mensagens novas do grupo a cada minuto (sem reprocessar o histórico na 1ª vez).
2. O Jev decide, barato e rápido, se a mensagem é um PEDIDO DE TAREFA ou só conversa.
3. Se for tarefa: avisa "já estou fazendo", chama a IA com as funções e responde o resultado.

Configuração: GI_GRUPO_EQUIPE no .env (JID do grupo, termina em @g.us) e empresa/equipe.json
(nome de cada pessoa da equipe, para a IA saber quem pediu sem ver o telefone).

Uso:  python nucleo/grupo_equipe.py            (fica rodando)
      python nucleo/grupo_equipe.py --uma-vez  (lê uma vez e sai; bom para tarefa agendada)
      python nucleo/grupo_equipe.py --listar   (mostra os grupos para achar o JID)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agente  # noqa: E402
import jev  # noqa: E402
import registro  # noqa: E402
import whatsapp  # noqa: E402
from config import DADOS, EMPRESA, GRUPO_EQUIPE  # noqa: E402

CURSOR = DADOS / "grupo_cursor.json"
CORTE_PROB, CORTE_CONF = 0.85, 0.65

PERGUNTA = {"pedido": {"type": "choice", "instructions": (
    "Read the LAST message of this company team WhatsApp group (previous messages are context). "
    "Is it asking the assistant to DO something with the company tools?"),
    "criteria": {
        "tarefa": "A clear request to do something now: book/cancel an appointment, make a quote, register a "
                  "customer, record a sale, look something up, send a notice.",
        "conversa": "Normal chat between colleagues, thanks, ok, jokes, information that needs no action.",
        "revisar": "Looks like a request but it is ambiguous or missing essential details.",
    }}}


def nomes_equipe() -> dict[str, str]:
    arq = EMPRESA / "equipe.json"
    try:
        return {k: v for k, v in json.loads(arq.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def quem(sender: str, nomes: dict) -> str:
    return nomes.get(sender.split("@")[0].split(":")[0], "colega")


def rodar_uma_vez() -> int:
    if not GRUPO_EQUIPE:
        sys.exit("Configure GI_GRUPO_EQUIPE no .env (use --listar para ver os grupos).")
    try:
        cursor = json.loads(CURSOR.read_text(encoding="utf-8"))["ts"]
    except (OSError, ValueError, KeyError):
        ult = whatsapp.mensagens_do_grupo(GRUPO_EQUIPE)
        cursor = str(ult[-1]["timestamp"]) if ult else registro.agora()
        CURSOR.write_text(json.dumps({"ts": cursor}), encoding="utf-8")
        print("Primeira vez: marquei o ponto de partida (não vou responder mensagens antigas).")
        return 0
    novas = [m for m in whatsapp.mensagens_do_grupo(GRUPO_EQUIPE, cursor) if not m["is_from_me"]]
    nomes = nomes_equipe()
    feitas = 0
    for m in novas:
        CURSOR.write_text(json.dumps({"ts": str(m["timestamp"])}), encoding="utf-8")
        texto = (m.get("content") or "").strip()
        if not texto:
            continue
        historico = whatsapp.ultimas_do_grupo(GRUPO_EQUIPE, 30)
        conversa = "\n".join(f"{'Assistente' if h['is_from_me'] else quem(h['sender'], nomes)}: {h.get('content') or ''}"
                             for h in historico)
        r = jev.perguntar({"conversation": conversa, "last_message": f"{quem(m['sender'], nomes)}: {texto}"}, PERGUNTA)
        dec = r["answers"]["pedido"]
        prob = (dec.get("probabilities") or {}).get("tarefa", 1.0 if dec["choice"] == "tarefa" else 0.0)
        if dec["choice"] != "tarefa" or prob < CORTE_PROB or dec.get("confidence", 1) < CORTE_CONF:
            continue
        pessoa = quem(m["sender"], nomes)
        whatsapp.enviar(GRUPO_EQUIPE, f"Recebido, {pessoa}! Já estou fazendo. Assim que terminar, confirmo aqui.")
        contexto = {"jid": GRUPO_EQUIPE, "nome": pessoa, "quem": pessoa, "canal": "equipe"}
        decisao = agente.decidir(conversa + f"\n{pessoa}: {texto}", contexto)
        registro.evento("tarefa_equipe", quem=pessoa, pedido=texto[:200],
                        funcoes=[f["funcao"] for f in decisao.get("funcoes_usadas", [])])
        for b in decisao["bolhas"] if decisao["responder"] else []:
            whatsapp.enviar(GRUPO_EQUIPE, b)
        feitas += 1
    return feitas


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--uma-vez", action="store_true")
    p.add_argument("--listar", action="store_true")
    a = p.parse_args()
    if a.listar:
        for g in whatsapp.grupos():
            print(f"{g['jid']}   {g['name']}")
        return
    if a.uma_vez:
        print(f"{rodar_uma_vez()} tarefas feitas.")
        return
    print("Lendo o grupo da equipe a cada minuto. Ctrl+C para parar.")
    while True:
        try:
            rodar_uma_vez()
        except Exception as e:  # noqa: BLE001
            registro.evento("erro", onde="grupo_equipe", erro=repr(e)[:300])
            print("erro:", e)
        time.sleep(60)


if __name__ == "__main__":
    main()
