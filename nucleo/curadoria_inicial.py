"""Curadoria inicial: descobre COM O QUE treinar a IA, lendo as conversas antigas do WhatsApp.

Passo 1 (Jev, barato): lê cada conversa até a data escolhida e responde:
  quem é a pessoa, qual o assunto, se fechou negócio, se a empresa respondeu bem,
  se precisaria de uma pessoa.
Passo 2 (motor de tarefas: Codex ou Claude Code): pega as MELHORES conversas de cada assunto e escreve um RASCUNHO do
  manual (perguntas frequentes, respostas que funcionam, erros a evitar).

Nada aqui envia mensagem. O rascunho vai para dados/curadoria/ — o líder revisa e só
então copia para a pasta empresa/.

Uso:
  python nucleo/curadoria_inicial.py --ate 2026-11-01              (todas até a data)
  python nucleo/curadoria_inicial.py --ate 2026-11-01 --limite 30  (teste com 30)
  python nucleo/curadoria_inicial.py --ate 2026-11-01 --sem-rascunho
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jev  # noqa: E402
import motores  # noqa: E402
import whatsapp  # noqa: E402
from config import DADOS, EMPRESA  # noqa: E402

PASTA = DADOS / "curadoria"
PASTA.mkdir(parents=True, exist_ok=True)
CACHE = PASTA / "cache.jsonl"

ASSUNTOS = {
    "preco": "Asked about price, payment conditions or discounts.",
    "produto": "Asked how a product/service works, what is included, details or differences.",
    "orcamento": "Wanted a custom quote that depends on measures, quantities or files they sent.",
    "agendamento": "Wanted to book, reschedule or cancel a visit, meeting, service or class.",
    "pedido_status": "Asked about an existing order/service: status, delivery, deadline.",
    "suporte": "Existing customer needing help or having a problem with what they bought.",
    "reclamacao": "Complaint, dissatisfaction, refund or cancellation.",
    "pagamento": "Sending a receipt, asking for PIX key/boleto/invoice, payment confirmation.",
    "outro": "Anything else (greeting only, spam, personal chat, supplier, job applicant).",
}

PERGUNTAS = {
    "quem": {"type": "choice", "instructions": "Who is the Cliente in this WhatsApp conversation with the company?",
             "criteria": {
                 "cliente_novo": "A prospective customer who had not bought before.",
                 "cliente_atual": "Someone who already bought/uses the company's product or service.",
                 "equipe_ou_parceiro": "Employee, supplier, partner, salesperson or job applicant.",
                 "outro": "Wrong number, spam, empty or personal chat.",
             }},
    "assunto": {"type": "choice", "instructions": "What is the MAIN topic the Cliente wanted to solve?",
                "criteria": ASSUNTOS},
    "fechou": {"type": "noul", "instructions": (
        "Did the conversation end with a closed deal (the Cliente bought, paid, booked or confirmed)?")},
    "boa_resposta": {"type": "score", "instructions": (
        "How good were the COMPANY's answers in this conversation, as a model to teach a new attendant? "
        "Judge clarity, correct information, speed, friendliness and moving the Cliente to the next step."),
        "criteria": [
            "Bad: wrong, rude, ignored the question or lost the customer by the company's fault.",
            "Weak: answered but vague, slow or without next step.",
            "Ok: correct and polite, nothing special.",
            "Good: clear, friendly, answered exactly and offered a next step.",
            "Excellent: a perfect example to copy.",
        ]},
    "precisou_humano": {"type": "noul", "instructions": (
        "Did this conversation need a human decision that an automatic attendant should not take alone "
        "(special discount, complaint, exception to rules, sensitive personal matter)?")},
}


def ler_cache() -> dict:
    out = {}
    if CACHE.exists():
        for l in CACHE.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(l)
                out[r["jid"]] = r
            except (ValueError, KeyError):
                pass
    return out


def avaliar(jid: str, msgs: list[dict], empresa: str) -> dict:
    estado = {"company": empresa, "first_message": str(msgs[0]["timestamp"])[:10],
              "conversation": whatsapp.como_texto(msgs, "Empresa")}
    r = jev.perguntar(estado, PERGUNTAS)
    a = r["answers"]
    return {"jid": jid, "ultima": str(msgs[-1]["timestamp"]), "n_msgs": len(msgs),
            "quem": a["quem"]["choice"], "assunto": a["assunto"]["choice"],
            "fechou": round(a["fechou"]["noul"], 2), "boa_resposta": round(a["boa_resposta"]["score"], 2),
            "precisou_humano": round(a["precisou_humano"]["noul"], 2),
            "tokens": (r.get("usage") or {}).get("input_tokens", 0)}


def rascunho_manual(convs: dict, notas: list[dict]) -> str:
    """Claude lê as melhores conversas de cada assunto e escreve o rascunho do manual."""
    por_assunto = defaultdict(list)
    for n in notas:
        if n["quem"] in ("cliente_novo", "cliente_atual"):
            por_assunto[n["assunto"]].append(n)
    blocos = []
    for assunto, lista in sorted(por_assunto.items(), key=lambda x: -len(x[1])):
        if assunto == "outro":
            continue
        melhores = sorted(lista, key=lambda n: (-n["boa_resposta"], -n["fechou"]))[:4]
        piores = sorted(lista, key=lambda n: n["boa_resposta"])[:2]
        for tipo, grupo in (("BOA", melhores), ("RUIM", piores)):
            for n in grupo:
                blocos.append(f"<conversa assunto=\"{assunto}\" exemplo=\"{tipo}\" fechou=\"{n['fechou']}\">\n"
                              + whatsapp.como_texto(convs[n["jid"]][-40:], "Empresa", 6000) + "\n</conversa>")
    contagem = Counter(n["assunto"] for n in notas if n["quem"] in ("cliente_novo", "cliente_atual"))
    pasta = PASTA / "rascunho"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "conversas.md").write_text("\n\n".join(blocos), encoding="utf-8")
    for velho in ("result.json", "result.ready"):
        (pasta / velho).unlink(missing_ok=True)
    instrucoes = (
        "Você ajuda uma empresa a montar o manual do seu atendente de IA no WhatsApp. Português do Brasil, simples.\n"
        f"Assuntos mais frequentes (quantidade de conversas): {dict(contagem.most_common())}\n"
        "O arquivo conversas.md nesta pasta tem conversas reais: exemplos BONS (para copiar) e RUINS (para evitar).\n"
        "Escreva rascunho-manual.md nesta pasta com as seções:\n"
        "1. ## Perguntas frequentes (por assunto; preço/prazo como [CONFIRMAR])\n2. ## Tom de voz\n"
        "3. ## Erros para evitar\n4. ## Quando passar para uma pessoa\n5. ## O que ainda falta no manual\n"
        "Não copie nomes, telefones, CPFs ou endereços de clientes.\n"
        'Ao terminar grave result.json com {"ok": true, "mensagem": "pronto"} e depois crie result.ready.')
    r = motores.rodar_tarefa(pasta, instrucoes)
    arq = pasta / "rascunho-manual.md"
    if not r.get("ok") or not arq.exists():
        raise RuntimeError(r.get("erro") or "o motor não escreveu o rascunho")
    return arq.read_text(encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ate", required=True, help="Ler conversas ANTES desta data (AAAA-MM-DD)")
    p.add_argument("--desde", default="")
    p.add_argument("--limite", type=int, default=0)
    p.add_argument("--paralelo", type=int, default=8)
    p.add_argument("--sem-rascunho", action="store_true")
    a = p.parse_args()

    sobre = EMPRESA / "sobre.md"
    empresa = sobre.read_text(encoding="utf-8")[:1500] if sobre.exists() else "A company that sells via WhatsApp."
    convs = whatsapp.conversas_1a1(ate=a.ate, desde=a.desde)
    cache = ler_cache()
    fila = [j for j in convs if j not in cache or cache[j]["ultima"] != str(convs[j][-1]["timestamp"])]
    if a.limite:
        fila = fila[:a.limite]
    print(f"{len(convs)} conversas até {a.ate}; {len(fila)} para o Jev ler agora.")

    with ThreadPoolExecutor(max_workers=a.paralelo) as ex, CACHE.open("a", encoding="utf-8") as fc:
        futs = {ex.submit(avaliar, j, convs[j], empresa): j for j in fila}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                print("erro", futs[f][:8], str(e)[:150])
                continue
            cache[r["jid"]] = r
            fc.write(json.dumps(r, ensure_ascii=False) + "\n")
            if i % 50 == 0:
                print(f"  {i}/{len(fila)}")

    notas = [cache[j] for j in convs if j in cache]
    clientes = [n for n in notas if n["quem"] in ("cliente_novo", "cliente_atual")]
    rel = {
        "ate": a.ate, "conversas": len(notas), "clientes": len(clientes),
        "quem": dict(Counter(n["quem"] for n in notas)),
        "assuntos": dict(Counter(n["assunto"] for n in clientes).most_common()),
        "fecharam": sum(1 for n in clientes if n["fechou"] >= 0.6),
        "boas_respostas": sum(1 for n in clientes if n["boa_resposta"] >= 3),
        "precisaram_humano": sum(1 for n in clientes if n["precisou_humano"] >= 0.6),
        "tokens_jev": sum(n.get("tokens", 0) for n in notas),
    }
    (PASTA / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rel, ensure_ascii=False, indent=2))

    if not a.sem_rascunho and clientes:
        print(f"Escrevendo o rascunho do manual com o motor de tarefas ({motores.MOTOR_TAREFAS})...")
        (PASTA / "rascunho-manual.md").write_text(rascunho_manual(convs, notas), encoding="utf-8")
        print(f"Pronto: {PASTA / 'rascunho-manual.md'} — revise e copie o que estiver certo para empresa/.")


if __name__ == "__main__":
    main()
