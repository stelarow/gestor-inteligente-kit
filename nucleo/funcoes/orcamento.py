"""Orçamento automático com a fórmula da empresa (empresa/funcoes/orcamento.json).

A IA descobre na conversa as quantidades; ESTA função faz a conta.
Nunca deixe a IA fazer conta de preço "de cabeça".
"""
import json

import registro
from config import EMPRESA

NOME = "fazer_orcamento"

QUANDO_USAR = """
Use quando o cliente pedir preço/orçamento de algo que depende de medidas ou quantidades.
Preencha as quantidades com o que o cliente disse. Se faltar alguma informação essencial,
NÃO chame: pergunte antes ao cliente. Devolve o valor calculado pela fórmula da empresa.
"""

CAMPOS = {
    "properties": {
        "servico": {"type": "string", "description": "Nome do serviço, igual ao de empresa/funcoes/orcamento.json."},
        "descricao": {"type": "string", "description": "O que o cliente quer, em uma frase."},
        "quantidades_json": {"type": "string", "description": (
            'Quantidades em JSON, com os nomes das variáveis do serviço. Ex.: {"area_m2": 0.54, "acabamentos": 4}')},
        "pecas": {"type": "integer", "description": "Quantas unidades o cliente quer."},
    },
}


def config() -> dict:
    return json.loads((EMPRESA / "funcoes" / "orcamento.json").read_text(encoding="utf-8"))


def calcular(serv: dict, quantidades: dict, pecas: int) -> dict:
    custo, linhas = 0.0, []
    for nome, var in serv["variaveis"].items():
        qtd = float(quantidades.get(nome, 0) or 0)
        valor = qtd * float(var["preco_por_unidade"])
        custo += valor
        linhas.append(f"{var.get('rotulo', nome)}: {qtd:g} {var.get('unidade', '')} = R$ {valor:.2f}")
    custo += float(serv.get("custo_fixo", 0))
    pecas = max(1, int(pecas or 1))
    custo_total = custo * pecas
    venda = max(custo_total * float(serv.get("multiplicador", 1)), float(serv.get("minimo", 0)))
    reserva = float(serv.get("reserva_percentual", 0))
    return {"custo": round(custo_total, 2), "venda": round(venda, 2),
            "venda_com_reserva": round(venda * (1 + reserva / 100), 2) if reserva else None,
            "detalhe": linhas, "pecas": pecas}


def executar(dados: dict, contexto: dict) -> dict:
    cfg = config()
    serv = cfg["servicos"].get(dados["servico"])
    if not serv:
        return {"ok": False, "resultado": f"Serviço não cadastrado. Opções: {', '.join(cfg['servicos'])}"}
    try:
        qtds = json.loads(dados["quantidades_json"] or "{}")
    except ValueError:
        return {"ok": False, "resultado": "quantidades_json inválido."}
    faltando = [n for n in serv["variaveis"] if n not in qtds]
    if faltando:
        return {"ok": False, "resultado": f"Faltam informações: {', '.join(faltando)}. Pergunte ao cliente."}
    r = calcular(serv, qtds, dados["pecas"])
    registro.evento("orcamento", jid=contexto.get("jid", ""), servico=dados["servico"],
                    descricao=dados["descricao"], valor=r["venda"])
    texto = (f"PREÇO PARA O CLIENTE de {dados['descricao']} ({r['pecas']} un.): R$ {r['venda']:.2f}."
             + (f" (Valor alternativo com reserva para imprevistos, só se o líder pedir: R$ {r['venda_com_reserva']:.2f}.)"
                if r["venda_com_reserva"] else "")
             + f" Prazo: {serv.get('prazo', 'a combinar')}."
             + f" (Custo interno R$ {r['custo']:.2f} — NÃO conte ao cliente.)")
    return {"ok": True, "resultado": texto, **r}
