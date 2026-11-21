"""Passa a conversa para uma pessoa da equipe e avisa o líder no WhatsApp."""
import registro
import whatsapp
from config import NUMERO_LIDER

NOME = "passar_para_humano"

QUANDO_USAR = """
Use quando: o cliente pedir para falar com uma pessoa; reclamar ou estiver irritado;
pedir algo que não está nas informações da empresa; envolver dinheiro fora do padrão
(desconto especial, reembolso, cancelamento); ou quando você não tiver certeza.
Depois de usar, a IA para de responder esta conversa até o líder devolver no painel.
"""

CAMPOS = {
    "properties": {
        "motivo": {"type": "string", "description": "Por que precisa de uma pessoa, em uma frase."},
        "resumo": {"type": "string", "description": "Resumo curto da conversa para quem vai assumir."},
    },
}


def executar(dados: dict, contexto: dict) -> dict:
    jid = contexto.get("jid", "")
    registro.passar_para_humano(jid, dados["motivo"])
    registro.evento("humano", jid=jid, motivo=dados["motivo"])
    avisou = False
    if NUMERO_LIDER and not contexto.get("simulacao"):
        nome = contexto.get("nome") or jid.split("@")[0]
        avisou = whatsapp.enviar(NUMERO_LIDER, (
            f"🙋 *Conversa para uma pessoa assumir*\n*Contato:* {nome}\n"
            f"*Motivo:* {dados['motivo']}\n*Resumo:* {dados['resumo']}"))
    return {"ok": True, "resultado": "Conversa marcada para uma pessoa assumir."
            + (" O líder foi avisado." if avisou else "")}
