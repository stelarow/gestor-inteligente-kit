"""Registra uma venda fechada. É o número mais importante do painel do líder."""
import registro

NOME = "registrar_venda"

QUANDO_USAR = """
Use SOMENTE quando a venda estiver confirmada de verdade: pagamento recebido/comprovante
conferido, ou o líder/equipe disse que fechou. "Vou pensar" ou "quero" sem pagar NÃO é venda.
"""

CAMPOS = {
    "properties": {
        "produto": {"type": "string"},
        "valor": {"type": "number", "description": "Valor em reais (0 se não souber)."},
        "como_confirmou": {"type": "string", "description": "Ex.: comprovante PIX conferido; líder confirmou."},
    },
}


def executar(dados: dict, contexto: dict) -> dict:
    registro.evento("venda", jid=contexto.get("jid", ""), produto=dados["produto"],
                    valor=float(dados["valor"] or 0), como=dados["como_confirmou"],
                    quem=contexto.get("quem", ""))
    return {"ok": True, "resultado": "Venda registrada no painel."}
