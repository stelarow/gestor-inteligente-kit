"""MODELO para criar uma função nova. Copie este arquivo com outro nome (sem o _ na frente).

Exemplos do que dá para fazer: consultar estoque, gerar 2ª via de boleto, abrir chamado,
reservar mesa, consultar status de pedido, lançar falta de funcionário...
"""
NOME = "minha_funcao"

QUANDO_USAR = """
Explique em português, para a IA, QUANDO usar esta função e o que ela faz.
Ex.: "Use quando o cliente perguntar se o pedido já saiu. Devolve o status do pedido."
"""

CAMPOS = {
    "properties": {
        "exemplo": {"type": "string", "description": "O que a IA deve preencher aqui."},
    },
}


def executar(dados: dict, contexto: dict) -> dict:
    # contexto tem: jid (quem está falando), nome, canal ("cliente" ou "equipe")
    # Faça a coisa de verdade aqui (chamar um sistema, gravar arquivo, etc.)
    return {"ok": True, "resultado": f"Recebi: {dados['exemplo']}"}
