"""O cérebro: monta o pedido (regras + manual da empresa + funções + conversa) e manda
para o motor de RESPOSTAS (OpenCode). O agente do OpenCode chama as funções sozinho e
devolve a resposta em JSON.

Princípio (aprendido na prática): quando a IA erra, melhore o MANUAL (pasta empresa/),
não crie "gambiarras" no código que filtram palavras ou reescrevem a resposta.
O código só cuida de: fila, segurança, envio e as funções que fazem coisas de verdade.
"""
from __future__ import annotations

import json
from datetime import datetime

import funcoes
import motores
import registro
from config import DADOS, EMPRESA

FEEDBACK = DADOS / "feedback.jsonl"
ASSUNTOS = ["venda", "orcamento", "agendamento", "suporte", "equipe", "outro"]
INTERESSES = ["quente", "morno", "frio", "nao_se_aplica"]

FORMATO = f"""
## Formato da resposta (somente este JSON, nada fora dele)
{{
  "responder": true,                  // false quando não há nada a dizer (ok, figurinha, conversa encerrada)
  "bolhas": ["mensagem 1", "mensagem 2"],  // 1 a 3 mensagens curtas, como gente escreve no WhatsApp
  "motivo": "para o líder: por que respondeu assim, em 1 ou 2 frases",
  "assunto": "{'|'.join(ASSUNTOS)}",
  "interesse": "{'|'.join(INTERESSES)}",
  "funcoes_usadas": [{{"funcao": "nome", "ok": true, "resultado": "o que a função devolveu"}}]
}}
"""


def manual(canal: str = "cliente") -> str:
    """Junta os arquivos .md da pasta empresa/ (o 'manual' que a IA segue)."""
    partes = []
    for arq in sorted(EMPRESA.glob("*.md")):
        if arq.name.upper().startswith("LEIA"):
            continue
        if arq.name.lower() == "equipe.md" and canal != "equipe":
            continue
        partes.append(f"<arquivo nome=\"{arq.name}\">\n{arq.read_text(encoding='utf-8').strip()}\n</arquivo>")
    return "\n\n".join(partes)


def lista_funcoes() -> str:
    linhas = []
    for m in funcoes.carregar().values():
        campos = ", ".join(f"{k} ({v.get('type')}{': ' + v['description'] if v.get('description') else ''})"
                           for k, v in m.CAMPOS.get("properties", {}).items())
        linhas.append(f"### {m.NOME}\n{' '.join(m.QUANDO_USAR.split())}\nCampos: {campos}")
    return "\n\n".join(linhas)


def regras(canal: str) -> str:
    papel = ("Você atende os CLIENTES da empresa pelo WhatsApp." if canal == "cliente" else
             "Você é o assistente da EQUIPE da empresa num grupo de WhatsApp: ajuda o líder e os colegas "
             "a fazer tarefas usando as funções.")
    return f"""{papel}

## Como trabalhar
- Leia a conversa INTEIRA antes de responder. Responda o que a pessoa perguntou por último,
  sem repetir o que já foi dito.
- Use SOMENTE as informações dos arquivos da empresa e o resultado das funções.
  Não invente preço, prazo, horário, vaga ou regra. Se não souber, use passar_para_humano.
- Escreva como uma pessoa da equipe no WhatsApp: frases curtas, no tom do arquivo de tom de voz,
  no máximo 3 bolhas.
- Contas de preço: use a função de orçamento. Nunca calcule de cabeça.
- Só diga "marcado", "cadastrado", "feito" depois que a função devolveu "ok": true.
- Trabalho demorado (ex.: orçamento que exige abrir e medir o arquivo que o cliente mandou): use pedir_tarefa_complexa e diga
  que já está trabalhando nisso.
- Se uma função falhar, diga com honestidade que vai verificar e passe para uma pessoa.

## Como usar as funções
Rode no terminal: python nucleo/funcoes_cli.py <funcao> campo=valor campo="valor com espaço"
Exemplo: python nucleo/funcoes_cli.py agenda acao=ver

{lista_funcoes()}
"""


def feedbacks_recentes(n: int = 8) -> str:
    if not FEEDBACK.exists():
        return ""
    itens = []
    for l in FEEDBACK.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            f = json.loads(l)
        except ValueError:
            continue
        sinal = "👍 GOSTOU" if f.get("nota") == "bom" else "👎 NÃO GOSTOU"
        itens.append(f"- {sinal}: {f.get('comentario', '')} (resposta: {f.get('resposta', '')[:200]})")
    return "## Comentários recentes do líder sobre suas respostas (siga)\n" + "\n".join(itens) if itens else ""


def salvar_feedback(nota: str, comentario: str, resposta: str, jid: str = "") -> None:
    with FEEDBACK.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": registro.agora(), "nota": nota, "comentario": comentario,
                            "resposta": resposta, "jid": jid}, ensure_ascii=False) + "\n")


def montar_pedido(conversa_txt: str, contexto: dict, imagens: list[str] | None = None) -> str:
    canal = contexto.get("canal", "cliente")
    fotos = ""
    if imagens:
        fotos = "\n## Imagens que o cliente mandou (abra e olhe)\n" + "\n".join(f"- {c}" for c in imagens)
    return f"""{regras(canal)}

## Arquivos da empresa
{manual(canal)}

{feedbacks_recentes()}

## Agora
{datetime.now().strftime('%A %d/%m/%Y %H:%M')} — contato: {contexto.get('nome') or 'sem nome'}
{fotos}

## Conversa
<conversa>
{conversa_txt}
</conversa>
{FORMATO}"""


def _normalizar(r: dict) -> dict:
    bolhas = r.get("bolhas") or []
    if isinstance(bolhas, str):
        bolhas = [bolhas]
    return {
        "responder": bool(r.get("responder")) and bool(bolhas),
        "bolhas": [str(b).strip() for b in bolhas if str(b).strip()][:3],
        "motivo": str(r.get("motivo", "")),
        "assunto": r.get("assunto") if r.get("assunto") in ASSUNTOS else "outro",
        "interesse": r.get("interesse") if r.get("interesse") in INTERESSES else "nao_se_aplica",
        "funcoes_usadas": r.get("funcoes_usadas") if isinstance(r.get("funcoes_usadas"), list) else [],
        "custo": r.get("_custo"),
    }


def decidir(conversa_txt: str, contexto: dict, imagens: list[str] | None = None, motor=None) -> dict:
    """Devolve {"responder", "bolhas", "motivo", "assunto", "interesse", "funcoes_usadas"}."""
    agente = "gi-equipe" if contexto.get("canal") == "equipe" else "gi-atendimento"
    chamar = motor or motores.opencode_json
    try:
        r = chamar(montar_pedido(conversa_txt, contexto, imagens), agente, contexto)
    except motores.MotorFalhou as e:
        registro.evento("erro", jid=contexto.get("jid", ""), erro=f"motor de respostas: {e}"[:300])
        return {"responder": False, "bolhas": [], "motivo": f"Falha ao escrever a resposta: {e}",
                "assunto": "outro", "interesse": "nao_se_aplica", "funcoes_usadas": [], "falhou": True}
    return _normalizar(r)
