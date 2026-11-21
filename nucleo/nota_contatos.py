"""Nota de cada contato (quente / morno / frio), feita pelo Jev lendo a conversa inteira.

Resultado em dados/notas_contatos.json — aparece na aba "Contatos" do painel.
Só reavalia conversas que mudaram desde a última vez.

Uso:  python nucleo/nota_contatos.py            (todas)
      python nucleo/nota_contatos.py --limite 20
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import jev  # noqa: E402
import whatsapp  # noqa: E402
from config import DADOS, EMPRESA  # noqa: E402

CACHE = DADOS / "notas_cache.jsonl"
SAIDA = DADOS / "notas_contatos.json"


def produtos() -> list[dict]:
    return json.loads((EMPRESA / "produtos.json").read_text(encoding="utf-8"))


def perguntas(lista: list[dict]) -> dict:
    opc = {p["id"]: f"{p['nome']}: {p.get('descricao', '')}" for p in lista}
    opc["nenhum"] = "No specific product/service can be identified."
    return {
        "ja_cliente": {"type": "noul", "instructions": (
            "Has the Cliente ALREADY bought/contracted from the company (paid, signed, receives the service)?")},
        "pessoa_da_equipe": {"type": "noul", "instructions": (
            "Is the Cliente actually an employee, supplier, partner or job applicant, not a customer?")},
        "potencial": {"type": "score", "instructions": (
            "As a NEW sale, how likely is the Cliente to buy if the company follows up now with a good offer? "
            "Existing customers, staff and suppliers belong to the lowest level."),
            "criteria": [
                "Not a new lead: already a customer, staff/supplier, wrong person, refused clearly or only said hi.",
                "Weak curiosity: one vague question or only the price, then disappeared.",
                "Real interest but blocked: stopped on price, schedule, distance or timing.",
                "Strong interest: asked details, discussed conditions, said they will come back.",
                "Ready: wanted to buy, booked, asked how to pay, but the purchase is not shown as done.",
            ]},
        "produto": {"type": "choice", "instructions": "Which product/service is the Cliente most interested in?",
                    "criteria": opc},
        "trava": {"type": "choice", "instructions": "What mainly stopped this person from buying so far?",
                  "criteria": {
                      "preco": "Price, budget, asked for discount.",
                      "horario_prazo": "Schedule, availability or deadline did not fit.",
                      "distancia": "Location or delivery.",
                      "momento": "Not now / will think / later.",
                      "concorrente": "Chose another company.",
                      "sumiu": "Stopped answering without a reason.",
                      "nada": "Nothing blocked, or not a lead.",
                  }},
        "pediu_parar": {"type": "noul", "instructions": (
            "Did the Cliente ask to stop receiving messages or say they are not interested anymore?")},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limite", type=int, default=0)
    p.add_argument("--paralelo", type=int, default=8)
    a = p.parse_args()

    lista = produtos()
    nomes = {x["id"]: x["nome"] for x in lista}
    qs = perguntas(lista)
    convs = whatsapp.conversas_1a1()
    cache = {}
    if CACHE.exists():
        for l in CACHE.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(l)
                cache[r["jid"]] = r
            except (ValueError, KeyError):
                pass
    fila = [j for j in convs if j not in cache or cache[j]["ultima"] != str(convs[j][-1]["timestamp"])]
    if a.limite:
        fila = fila[:a.limite]
    print(f"{len(convs)} conversas; {len(fila)} para avaliar.")

    def avaliar(jid: str) -> dict:
        msgs = convs[jid]
        r = jev.perguntar({"today": date.today().isoformat(), "conversation": whatsapp.como_texto(msgs, "Empresa")}, qs)
        x = r["answers"]
        return {"jid": jid, "ultima": str(msgs[-1]["timestamp"]),
                "ja_cliente": x["ja_cliente"]["noul"], "equipe": x["pessoa_da_equipe"]["noul"],
                "potencial": x["potencial"]["score"], "produto": x["produto"]["choice"],
                "trava": x["trava"]["choice"], "pediu_parar": x["pediu_parar"]["noul"]}

    with ThreadPoolExecutor(max_workers=a.paralelo) as ex, CACHE.open("a", encoding="utf-8") as fc:
        futs = {ex.submit(avaliar, j): j for j in fila}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                print("erro", futs[f][:8], str(e)[:150])
                continue
            cache[r["jid"]] = r
            fc.write(json.dumps(r, ensure_ascii=False) + "\n")

    saida = []
    for jid, msgs in convs.items():
        r = cache.get(jid)
        if not r or r["ja_cliente"] >= 0.7 or r["equipe"] >= 0.7:
            continue
        nota = round(100 * r["potencial"] / 4 * (1 - 0.9 * r["pediu_parar"]))
        tel = jid.split("@")[0] if jid.endswith("@s.whatsapp.net") else ""
        saida.append({
            "jid": jid, "nome": whatsapp.nome_do_contato(jid) or "(sem nome)", "telefone": tel,
            "link": f"https://wa.me/{tel}" if tel else "", "nota": nota,
            "faixa": "quente" if nota >= 60 else "morno" if nota >= 35 else "frio",
            "produto": nomes.get(r["produto"], ""), "trava": r["trava"],
            "pediu_parar": r["pediu_parar"] >= 0.6, "ultima": str(msgs[-1]["timestamp"])[:10],
            "ultima_do_cliente": next(((m.get("content") or "") for m in reversed(msgs) if not m["is_from_me"]), "")[:160],
        })
    saida.sort(key=lambda x: -x["nota"])
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    q = sum(1 for s in saida if s["faixa"] == "quente")
    print(f"Pronto: {len(saida)} contatos com nota ({q} quentes). Veja no painel, aba Contatos.")


if __name__ == "__main__":
    main()
