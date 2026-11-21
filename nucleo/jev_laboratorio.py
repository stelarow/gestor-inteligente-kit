"""Laboratório do Jev (Encontro 3): aprender o Jev testando, com exemplos e com as SUAS conversas.

Exercícios prontos:
  python nucleo/jev_laboratorio.py sim-nao        -> pergunta de sim/não (noul)
  python nucleo/jev_laboratorio.py escolha        -> escolher uma opção (choice)
  python nucleo/jev_laboratorio.py nota           -> nota em níveis (score)
  python nucleo/jev_laboratorio.py confianca      -> mesma pergunta, textos claros x ambíguos
  python nucleo/jev_laboratorio.py juntas         -> várias perguntas de uma vez sobre o mesmo texto

Com as suas conversas do WhatsApp (só leitura, nada é enviado):
  python nucleo/jev_laboratorio.py minhas --pergunta laboratorio/minha_pergunta.json --quantas 10

O arquivo de pergunta é um JSON com as perguntas, no mesmo formato dos exemplos abaixo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jev  # noqa: E402

FRASES = [
    "Oi, quanto custa? Queria fechar ainda hoje, aceita PIX?",
    "Vou pensar e te aviso, obrigado.",
    "Não quero mais receber mensagens, por favor.",
    "kkkk",
    "Pode ser semana que vem, talvez, não sei ainda",
]

EXEMPLOS = {
    "sim-nao": {"pronto_para_comprar": {
        "type": "noul",
        "instructions": "Is the customer ready to buy right now (wants to close, asks how to pay)?"}},
    "escolha": {"intencao": {
        "type": "choice",
        "instructions": "What does the customer want with this message?",
        "criteria": {
            "comprar": "Wants to buy or close now.",
            "pensar": "Is undecided or will think about it.",
            "parar": "Asks to stop receiving messages.",
            "nada": "No clear intention (laugh, emoji, greeting).",
        }}},
    "nota": {"interesse": {
        "type": "score",
        "instructions": "How interested in buying is the customer, judging only by this message?",
        "criteria": [
            "No interest at all, or asked to stop.",
            "Little interest, polite but distant.",
            "Some interest, undecided.",
            "High interest, asks details.",
            "Ready to buy now.",
        ]}},
}


def mostrar(texto: str, resposta: dict) -> None:
    print(f"\n💬 \"{texto}\"")
    for nome, r in resposta["answers"].items():
        if r["type"] == "noul":
            p = r["noul"]
            leitura = "SIM" if p >= 0.7 else "NÃO" if p <= 0.3 else "INCERTO"
            print(f"   {nome}: probabilidade de sim = {p:.2f}  → {leitura}")
        elif r["type"] == "choice":
            dist = ", ".join(f"{k} {v:.2f}" for k, v in sorted(r["probabilities"].items(), key=lambda x: -x[1]))
            print(f"   {nome}: escolheu '{r['choice']}' (confiança {r['confidence']:.2f})  [{dist}]")
        elif r["type"] == "score":
            print(f"   {nome}: nota {r['score']:.2f} de 0 a {len(r['probabilities']) - 1} "
                  f"(confiança {r['confidence']:.2f})")
    print(f"   tokens lidos: {resposta.get('usage', {}).get('input_tokens', '?')}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("exercicio", choices=["sim-nao", "escolha", "nota", "confianca", "juntas", "minhas"])
    p.add_argument("--pergunta", help="JSON com perguntas (exercício 'minhas')")
    p.add_argument("--quantas", type=int, default=10)
    a = p.parse_args()

    if a.exercicio in EXEMPLOS:
        print("Perguntas enviadas ao Jev:\n" + json.dumps(EXEMPLOS[a.exercicio], ensure_ascii=False, indent=2))
        for f in FRASES:
            mostrar(f, jev.perguntar({"customer_message": f}, EXEMPLOS[a.exercicio]))
    elif a.exercicio == "confianca":
        q = EXEMPLOS["escolha"]
        for f in ["Quero fechar agora, me passa o PIX", "hmm talvez, vamos ver né", "ok"]:
            mostrar(f, jev.perguntar({"customer_message": f}, q))
        print("\n👉 Repare: texto claro = confiança alta; ambíguo = probabilidade espalhada e confiança baixa.")
    elif a.exercicio == "juntas":
        todas = {**EXEMPLOS["sim-nao"], **EXEMPLOS["escolha"], **EXEMPLOS["nota"]}
        for f in FRASES[:3]:
            mostrar(f, jev.perguntar({"customer_message": f}, todas))
        print("\n👉 Várias perguntas no mesmo pedido rodam juntas e uma não vê a resposta da outra.")
    else:
        import whatsapp
        if not a.pergunta:
            sys.exit("Use --pergunta arquivo.json")
        qs = json.loads(Path(a.pergunta).read_text(encoding="utf-8"))
        convs = list(whatsapp.conversas_1a1().items())[-a.quantas:]
        for jid, msgs in convs:
            txt = whatsapp.como_texto(msgs, "Empresa", 20000)
            r = jev.perguntar({"conversation": txt}, qs)
            ultima = next(((m.get("content") or "") for m in reversed(msgs) if not m["is_from_me"]), "")
            mostrar(f"{jid.split('@')[0][-4:]}… última do cliente: {ultima[:80]}", r)


if __name__ == "__main__":
    main()
