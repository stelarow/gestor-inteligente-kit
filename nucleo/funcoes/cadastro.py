"""Cadastra o cliente num sistema (plataforma, CRM, planilha...).

Configuração: empresa/funcoes/cadastro.json
- Sem "url_api": grava em dados/cadastros.csv (bom para começar).
- Com "url_api": envia os dados por POST para o sistema da empresa.
  Peça ao seu agente para adaptar ao seu sistema (cada plataforma é diferente).
"""
import csv
import json
import urllib.request

import registro
from config import DADOS, EMPRESA

NOME = "cadastrar_cliente"

QUANDO_USAR = """
Use quando o cliente fechou (ou precisa de cadastro) e já passou TODOS os dados pedidos
em empresa/funcoes/cadastro.json. Se faltar dado, peça antes. Devolve se o cadastro deu certo.
"""

CAMPOS = {
    "properties": {
        "nome": {"type": "string"},
        "telefone": {"type": "string"},
        "email": {"type": "string", "description": "Vazio se o cliente não informou."},
        "documento": {"type": "string", "description": "CPF/CNPJ se a empresa pede; senão vazio."},
        "produto": {"type": "string", "description": "O que o cliente contratou/comprou."},
        "observacao": {"type": "string"},
    },
}


def executar(dados: dict, contexto: dict) -> dict:
    cfg = json.loads((EMPRESA / "funcoes" / "cadastro.json").read_text(encoding="utf-8"))
    faltando = [c for c in cfg.get("obrigatorios", []) if not str(dados.get(c, "")).strip()]
    if faltando:
        return {"ok": False, "resultado": f"Faltam: {', '.join(faltando)}. Peça ao cliente."}
    linha = {**dados, "jid": contexto.get("jid", ""), "quando": registro.agora()}
    if cfg.get("url_api"):
        req = urllib.request.Request(cfg["url_api"], data=json.dumps(linha).encode(), headers={
            "Content-Type": "application/json", **cfg.get("cabecalhos", {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if not 200 <= r.status < 300:
                    return {"ok": False, "resultado": "O sistema recusou o cadastro. Passe para uma pessoa."}
        except OSError as e:
            return {"ok": False, "resultado": f"O sistema não respondeu ({e}). Passe para uma pessoa."}
    else:
        arq = DADOS / "cadastros.csv"
        novo = not arq.exists()
        with arq.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linha))
            if novo:
                w.writeheader()
            w.writerow(linha)
    registro.evento("cadastro", jid=contexto.get("jid", ""), produto=dados["produto"])
    return {"ok": True, "resultado": f"Cliente {dados['nome']} cadastrado."}
