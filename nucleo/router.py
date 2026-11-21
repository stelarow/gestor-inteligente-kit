"""Central do Gestor Inteligente.

Recebe as mensagens da bridge, espera a pessoa terminar de escrever, chama a IA
e envia (ou deixa na fila para o líder aprovar). Também serve o painel do líder.

Iniciar:  python nucleo/router.py      Painel:  http://127.0.0.1:8791/
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agente  # noqa: E402
import audio  # noqa: E402
import registro  # noqa: E402
import whatsapp  # noqa: E402
from config import (DADOS, ESCUTAR, ESPERA_SEGUNDOS, NUMEROS_TESTE, PORTA_PAINEL,  # noqa: E402
                    ler_estado, salvar_estado)

AQUI = Path(__file__).resolve().parent
NOME_EMPRESA = "Empresa"
_timers: dict[str, threading.Timer] = {}
_travas: dict[str, threading.Lock] = {}
_ultimo_humano: dict[str, float] = {}
_t = threading.Lock()


def _telefone(jid: str) -> str:
    return jid.split("@")[0].split(":")[0]


def pode_enviar_sozinho(jid: str) -> bool:
    modo = ler_estado()["modo"]
    if modo == "liberado":
        return True
    if modo == "teste":
        tel = _telefone(jid)
        return any(tel == n or jid == n for n in NUMEROS_TESTE)
    return False


def enviar_bolhas(jid: str, bolhas: list[str]) -> bool:
    ok = True
    for i, b in enumerate(bolhas):
        whatsapp.digitando(jid, True)
        time.sleep(min(1.5 + len(b) / 60, 6))  # parece gente digitando
        ok = whatsapp.enviar(jid, b) and ok
        if i < len(bolhas) - 1:
            time.sleep(1)
    whatsapp.digitando(jid, False)
    return ok


# ---------------- processar uma conversa ----------------
def processar(jid: str) -> None:
    with _t:
        trava = _travas.setdefault(jid, threading.Lock())
    if not trava.acquire(blocking=False):
        agendar(jid)  # já tem um processamento desta conversa rodando: tenta de novo depois
        return
    try:
        _processar(jid)
    except Exception as e:  # noqa: BLE001
        registro.evento("erro", jid=jid, erro=repr(e)[:300])
        traceback.print_exc()
    finally:
        trava.release()


def _processar(jid: str) -> None:
    estado = ler_estado()
    if estado["pausado"]:
        registro.evento("pausado", jid=jid)
        return
    if registro.esta_com_humano(jid):
        return
    msgs = whatsapp.conversa(jid)
    if not msgs or msgs[-1]["is_from_me"]:
        return  # a última mensagem já é nossa
    inicio = time.time()

    # mídias que chegaram depois da nossa última resposta
    novas = []
    for m in reversed(msgs):
        if m["is_from_me"]:
            break
        novas.append(m)
    imagens = []
    for m in novas:
        tipo = (m.get("media_type") or "").lower()
        if tipo == "image":
            c = whatsapp.baixar_midia(m["id"], m["chat_jid"])
            if c:
                imagens.append(c)
        elif tipo in ("audio", "ptt") and audio.disponivel():
            c = whatsapp.baixar_midia(m["id"], m["chat_jid"])
            if c:
                m["content"] = f"(áudio transcrito) {audio.transcrever(c)}"

    nome = whatsapp.nome_do_contato(jid)
    contexto = {"jid": jid, "nome": nome, "canal": "cliente"}
    decisao = agente.decidir(whatsapp.como_texto(msgs, NOME_EMPRESA), contexto, imagens)
    registro.evento("resposta_gerada", jid=jid, assunto=decisao["assunto"], interesse=decisao["interesse"],
                    responder=decisao["responder"], motivo=decisao["motivo"],
                    funcoes=[f["funcao"] for f in decisao.get("funcoes_usadas", [])])
    if not decisao["responder"] or not decisao["bolhas"]:
        return

    # Lição real: se uma pessoa da equipe respondeu pelo celular enquanto a IA pensava, a IA fica quieta.
    if _ultimo_humano.get(jid, 0) > inicio:
        registro.evento("descartada", jid=jid, motivo="uma pessoa respondeu enquanto a IA pensava")
        return

    item = {"jid": jid, "nome": nome, "bolhas": decisao["bolhas"], "motivo": decisao["motivo"],
            "assunto": decisao["assunto"], "interesse": decisao["interesse"],
            "funcoes": decisao.get("funcoes_usadas", []),
            "ultima_do_cliente": (novas[0].get("content") or "")[:300] if novas else ""}
    if pode_enviar_sozinho(jid):
        ok = enviar_bolhas(jid, decisao["bolhas"])
        registro.evento("resposta_enviada" if ok else "erro", jid=jid, como="automatico",
                        bolhas=decisao["bolhas"], motivo=decisao["motivo"])
    else:
        registro.na_fila(item)
        registro.evento("na_fila", jid=jid)


def agendar(jid: str) -> None:
    """Espera a pessoa parar de mandar mensagens picadas antes de responder."""
    with _t:
        if jid in _timers:
            _timers[jid].cancel()
        t = threading.Timer(ESPERA_SEGUNDOS, processar, args=(jid,))
        t.daemon = True
        _timers[jid] = t
        t.start()


# ---------------- números do painel ----------------
def resumo(dias: int = 0) -> dict:
    inicio = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d") if dias else registro.hoje()
    ev = registro.eventos(inicio)
    conta = lambda t: sum(1 for e in ev if e["tipo"] == t)  # noqa: E731
    interesse: dict[str, str] = {}
    for e in ev:
        if e["tipo"] == "resposta_gerada":
            interesse[e["jid"]] = e.get("interesse", "")
    vendas = [e for e in ev if e["tipo"] == "venda"]
    orc = [e for e in ev if e["tipo"] == "orcamento"]
    por_pessoa: dict[str, dict] = {}
    for e in vendas:
        p = por_pessoa.setdefault(e.get("quem") or "IA no atendimento", {"vendas": 0, "valor": 0.0})
        p["vendas"] += 1
        p["valor"] += float(e.get("valor") or 0)
    for e in ev:
        if e["tipo"] == "tarefa_equipe":
            p = por_pessoa.setdefault(e.get("quem") or "?", {"vendas": 0, "valor": 0.0})
            p["tarefas"] = p.get("tarefas", 0) + 1
    return {
        "desde": inicio,
        "conversas": len({e["jid"] for e in ev if e["tipo"] == "mensagem_recebida"}),
        "mensagens": conta("mensagem_recebida"),
        "respostas_enviadas": conta("resposta_enviada"),
        "aprovadas": sum(1 for e in ev if e["tipo"] == "resposta_enviada" and e.get("como") == "aprovada"),
        "na_fila": len(registro.fila()),
        "com_humano": len(registro.com_humano()),
        "passadas_para_humano": conta("humano"),
        "orcamentos": len(orc), "valor_orcado": round(sum(float(e.get("valor") or 0) for e in orc), 2),
        "agendamentos": conta("agendado"),
        "vendas": len(vendas), "valor_vendido": round(sum(float(e.get("valor") or 0) for e in vendas), 2),
        "quentes": sum(1 for v in interesse.values() if v == "quente"),
        "mornos": sum(1 for v in interesse.values() if v == "morno"),
        "frios": sum(1 for v in interesse.values() if v == "frio"),
        "erros": conta("erro"),
        "por_pessoa": por_pessoa,
        "assuntos": {a: sum(1 for e in ev if e["tipo"] == "resposta_gerada" and e.get("assunto") == a)
                     for a in ("venda", "orcamento", "agendamento", "suporte", "equipe", "outro")},
    }


def saude() -> dict:
    ev = registro.eventos(registro.hoje())
    erros = [e for e in ev if e["tipo"] == "erro"][-3:]
    bridge = whatsapp.bridge_no_ar()
    return {"whatsapp": bridge, "central": True, "pausado": ler_estado()["pausado"],
            "modo": ler_estado()["modo"], "erros_hoje": erros,
            "conclusao": ("🚨 WhatsApp desconectado" if not bridge else
                          "⚠️ Agente pausado" if ler_estado()["pausado"] else
                          "⚠️ Houve erros hoje" if erros else "✅ Tudo funcionando")}


# ---------------- servidor HTTP ----------------
class Central(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso
        pass

    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados, ensure_ascii=False, default=str).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):  # noqa: N802
        rota = self.path.split("?")[0]
        if rota in ("/", "/painel"):
            corpo = (AQUI / "painel.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif rota == "/api/resumo":
            q = dict(p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p)
            self._json(resumo(int(q.get("dias", 0) or 0)))
        elif rota == "/api/fila":
            self._json(registro.fila())
        elif rota == "/api/humano":
            self._json(registro.com_humano())
        elif rota == "/api/saude":
            self._json(saude())
        elif rota == "/api/contatos":
            arq = DADOS / "notas_contatos.json"
            self._json(json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else [])
        elif rota == "/health":
            self._json({"ok": True})
        else:
            self._json({"erro": "não encontrado"}, 404)

    def do_POST(self):  # noqa: N802
        rota, d = self.path.split("?")[0], self._corpo()
        if rota == "/incoming":
            self._json({"ok": True})
            receber(d)
        elif rota == "/api/aprovar":
            item = registro.tirar_da_fila(d.get("id", ""))
            if not item:
                return self._json({"ok": False, "erro": "Já foi enviado ou descartado."})
            bolhas = d.get("bolhas") or item["bolhas"]
            editada = bolhas != item["bolhas"]
            ok = enviar_bolhas(item["jid"], bolhas)
            registro.evento("resposta_enviada" if ok else "erro", jid=item["jid"], como="aprovada",
                            editada=editada, bolhas=bolhas)
            if editada:
                agente.salvar_feedback("ruim", "O líder corrigiu a resposta. Prefira o jeito corrigido: "
                                       + " / ".join(bolhas), " / ".join(item["bolhas"]), item["jid"])
            self._json({"ok": ok})
        elif rota == "/api/descartar":
            item = registro.tirar_da_fila(d.get("id", ""))
            if item:
                registro.evento("descartada", jid=item["jid"], motivo="líder descartou")
            self._json({"ok": bool(item)})
        elif rota == "/api/feedback":
            agente.salvar_feedback(d.get("nota", "bom"), d.get("comentario", ""), d.get("resposta", ""), d.get("jid", ""))
            self._json({"ok": True})
        elif rota == "/api/estado":
            est = ler_estado()
            if "pausado" in d:
                est["pausado"] = bool(d["pausado"])
            if d.get("modo") in ("aprovar", "teste", "liberado"):
                est["modo"] = d["modo"]
            salvar_estado(est)
            registro.evento("estado", **est)
            self._json(est)
        elif rota == "/api/devolver":
            registro.devolver_para_ia(d.get("jid", ""))
            self._json({"ok": True})
        else:
            self._json({"erro": "não encontrado"}, 404)


def receber(d: dict) -> None:
    jid = d.get("chat_jid", "")
    if not jid or d.get("is_group") or jid.endswith("@g.us"):
        return  # grupos são lidos pelo grupo_equipe.py
    if d.get("is_from_me"):
        # Mensagem que uma PESSOA mandou pelo celular: a IA não atropela.
        _ultimo_humano[jid] = time.time()
        with _t:
            if jid in _timers:
                _timers[jid].cancel()
        for item in registro.fila():
            if item["jid"] == jid:
                registro.tirar_da_fila(item["id"])
        registro.evento("humano_respondeu", jid=jid)
        return
    registro.evento("mensagem_recebida", jid=jid, tipo_midia=d.get("media_type", ""))
    agendar(jid)


def main() -> None:
    srv = ThreadingHTTPServer((ESCUTAR, PORTA_PAINEL), Central)
    print(f"Central no ar: http://127.0.0.1:{PORTA_PAINEL}/   (modo: {ler_estado()['modo']})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
