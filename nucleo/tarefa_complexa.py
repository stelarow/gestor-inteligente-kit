"""Executa uma tarefa complexa (pedida pela função pedir_tarefa_complexa) e envia o resultado.

  python nucleo/tarefa_complexa.py <id>                 (normalmente a Central chama sozinha)
  python nucleo/tarefa_complexa.py --testar orcamento-arquivo "arte.pdf, banner 60 x 90"   (roda sem WhatsApp)
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motores  # noqa: E402
import registro  # noqa: E402
import whatsapp  # noqa: E402
from config import DADOS, EMPRESA, RAIZ  # noqa: E402

FORMATO = """
## Como entregar
Trabalhe somente dentro desta pasta (pode ler a pasta do sistema em {raiz}).
Para fórmulas e preços use a função da empresa, nunca conta de cabeça:
  python "{raiz}\\nucleo\\funcoes_cli.py" fazer_orcamento servico=... descricao=... quantidades_json='{{...}}' pecas=1
Ao terminar, grave result.json assim:
{{"ok": true, "mensagem": "texto curto para o cliente no WhatsApp (pode usar *negrito*)",
  "arquivos": ["nome-do-arquivo-nesta-pasta.png"], "observacoes_internas": "o que a equipe precisa saber"}}
Se não conseguir (link fora do ar, login, arquivo inválido), grave ok=false e explique em observacoes_internas.
Nunca invente valores. Depois de gravar result.json, crie o arquivo vazio result.ready.
"""


def montar_instrucoes(tipo: str, pedido: str) -> str:
    base = (EMPRESA / "tarefas" / f"{tipo}.md").read_text(encoding="utf-8")
    return f"{base}\n\n## Pedido do cliente\n{pedido}\n{FORMATO.format(raiz=RAIZ)}"


def executar(tid: str) -> dict:
    pasta = DADOS / "tarefas" / tid
    p = json.loads((pasta / "pedido.json").read_text(encoding="utf-8"))
    r = motores.rodar_tarefa(pasta, montar_instrucoes(p["tipo"], p["pedido"]))
    (pasta / "resultado_final.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    registro.evento("tarefa_concluida", jid=p["jid"], tipo_tarefa=p["tipo"], tarefa=tid, ok=r.get("ok"),
                    segundos=r.get("segundos"))
    if not p["jid"]:
        return r
    if r.get("ok") and r.get("mensagem"):
        arquivos = r.get("arquivos") or []
        if arquivos:
            whatsapp.enviar(p["jid"], r["mensagem"], arquivos[0])
            for a in arquivos[1:]:
                whatsapp.enviar(p["jid"], "", a)
        else:
            whatsapp.enviar(p["jid"], r["mensagem"])
    else:
        # não deixa o cliente sem resposta, e chama uma pessoa
        registro.passar_para_humano(p["jid"], f"Tarefa {p['tipo']} falhou: {r.get('erro') or r.get('observacoes_internas', '')}")
        whatsapp.enviar(p["jid"], "Tive um problema para terminar isso agora. Já pedi para uma pessoa da equipe conferir e te responder. 🙏")
    return r


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("id", nargs="?")
    a.add_argument("--testar", nargs=2, metavar=("TIPO", "PEDIDO"))
    x = a.parse_args()
    if x.testar:
        tid = "teste-" + uuid.uuid4().hex[:6]
        pasta = DADOS / "tarefas" / tid
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "pedido.json").write_text(json.dumps({"id": tid, "tipo": x.testar[0], "pedido": x.testar[1], "jid": ""}),
                                           encoding="utf-8")
        print(f"Rodando em {pasta} com o motor {motores.MOTOR_TAREFAS}...")
        print(json.dumps(executar(tid), ensure_ascii=False, indent=2))
    elif x.id:
        executar(x.id)
    else:
        a.print_help()


if __name__ == "__main__":
    main()
