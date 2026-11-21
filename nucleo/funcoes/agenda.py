"""Agenda simples: mostra horários livres, marca e cancela.

Horários da empresa: empresa/funcoes/agenda.json. Marcações: dados/agenda.json.
Dá para trocar por Google Agenda ou pelo sistema da empresa (peça ao agente).
"""
import json
from datetime import date, datetime, timedelta

import registro
import whatsapp
from config import DADOS, EMPRESA, GRUPO_EQUIPE

NOME = "agenda"
ARQ = DADOS / "agenda.json"
DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

QUANDO_USAR = """
Agenda da empresa (visitas, reuniões, atendimentos, oficinas...).
acao="ver": mostra os próximos horários livres (use antes de oferecer horário).
acao="marcar": marca para o cliente (precisa de data AAAA-MM-DD, hora HH:MM e nome).
acao="cancelar": cancela a marcação deste cliente na data.
Nunca confirme um horário ao cliente sem antes marcar com sucesso.
"""

CAMPOS = {
    "properties": {
        "acao": {"type": "string", "enum": ["ver", "marcar", "cancelar"]},
        "data": {"type": "string", "description": "AAAA-MM-DD (vazio em 'ver')."},
        "hora": {"type": "string", "description": "HH:MM (vazio em 'ver' e 'cancelar')."},
        "nome": {"type": "string", "description": "Nome do cliente (vazio em 'ver')."},
        "assunto": {"type": "string", "description": "Do que se trata (vazio em 'ver')."},
    },
}


def _ler() -> list:
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _gravar(v: list) -> None:
    ARQ.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")


def _rotulo(d: date, h: str) -> str:
    return f"{DIAS[d.weekday()]} {d.strftime('%d/%m')} ({d.isoformat()}) às {h}"


def livres(dias: int = 14) -> list[str]:
    cfg = json.loads((EMPRESA / "funcoes" / "agenda.json").read_text(encoding="utf-8"))
    marc, out, hoje = _ler(), [], date.today()
    folgas = set(cfg.get("sem_atendimento", []))
    for i in range(1, dias + 1):
        d = hoje + timedelta(days=i)
        if d.isoformat() in folgas:
            continue
        for h in cfg["horarios"].get(DIAS[d.weekday()], []):
            ocupados = sum(1 for m in marc if m["data"] == d.isoformat() and m["hora"] == h)
            if ocupados < cfg.get("vagas_por_horario", 1):
                out.append(_rotulo(d, h))
    return out


def executar(dados: dict, contexto: dict) -> dict:
    jid = contexto.get("jid", "")
    if dados["acao"] == "ver":
        l = livres()[:12]
        return {"ok": True, "resultado": "Horários livres: " + ("; ".join(l) if l else "nenhum nos próximos 14 dias.")}
    try:
        d = datetime.strptime(dados["data"], "%Y-%m-%d").date()
    except ValueError:
        return {"ok": False, "resultado": "Data inválida, use AAAA-MM-DD."}
    marc = _ler()
    if dados["acao"] == "cancelar":
        resto = [m for m in marc if not (m["jid"] == jid and m["data"] == dados["data"])]
        if len(resto) == len(marc):
            return {"ok": False, "resultado": "Não achei marcação deste cliente nessa data."}
        _gravar(resto)
        registro.evento("agenda_cancelada", jid=jid, data=dados["data"])
        return {"ok": True, "resultado": "Cancelado."}
    if _rotulo(d, dados["hora"]) not in livres(60):
        return {"ok": False, "resultado": "Esse horário não está livre. Use acao='ver' e ofereça outro."}
    marc.append({"jid": jid, "nome": dados["nome"], "data": dados["data"], "hora": dados["hora"],
                 "assunto": dados["assunto"], "marcado_em": registro.agora()})
    _gravar(marc)
    registro.evento("agendado", jid=jid, data=dados["data"], hora=dados["hora"], assunto=dados["assunto"])
    if GRUPO_EQUIPE and not contexto.get("simulacao"):
        whatsapp.enviar(GRUPO_EQUIPE, f"📅 *Novo agendamento*\n{dados['nome']} — "
                                      f"{d.strftime('%d/%m')} às {dados['hora']}\n{dados['assunto']}")
    return {"ok": True, "resultado": f"Marcado: {d.strftime('%d/%m')} às {dados['hora']}."}
