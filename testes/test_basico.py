"""Testes que rodam SEM WhatsApp e SEM gastar IA (a IA é simulada).

Rodar:  python -m pytest testes -q      (ou: python testes/test_basico.py)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="gi-teste-"))
os.environ["GI_DADOS"] = str(TMP / "dados")
os.environ["GI_MENSAGENS_DB"] = str(TMP / "messages.db")
os.environ["GI_ESPERA_SEGUNDOS"] = "0"
os.environ["GI_MODO"] = "aprovar"
os.environ["GI_NUMERO_LIDER"] = ""
os.environ["GI_GRUPO_EQUIPE"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nucleo"))

DB = Path(os.environ["GI_MENSAGENS_DB"])
with sqlite3.connect(DB) as c:
    c.executescript("""
    CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP);
    CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP,
      is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT, media_key BLOB, file_sha256 BLOB,
      file_enc_sha256 BLOB, file_length INTEGER, PRIMARY KEY (id, chat_jid));
    INSERT INTO chats VALUES ('5500000000009@s.whatsapp.net', 'Cliente Teste', '2026-01-01');
    INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me) VALUES
      ('m1', '5500000000009@s.whatsapp.net', '5500000000009', 'Oi! Quanto fica um vaso de 150 g, umas 8 horas?', '2026-01-01 10:00:00', 0);
    """)

import agente  # noqa: E402
import motores  # noqa: E402
import funcoes  # noqa: E402
import registro  # noqa: E402
import router  # noqa: E402
from funcoes import agenda, orcamento  # noqa: E402


def motor_falso(pedido: str, agente_nome: str, contexto: dict) -> dict:
    """Simula o agente do OpenCode: lê o pedido, chama a função de orçamento e devolve o JSON."""
    assert agente_nome == "gi-atendimento"
    assert "fazer_orcamento" in pedido and "Gráfica Rápida Exemplo" in pedido and "<conversa>" in pedido
    r = funcoes.executar(funcoes.carregar(), "fazer_orcamento", {
        "servico": "impressao", "descricao": "banner 60 x 90 cm", "quantidades_json": '{"area_m2":0.54,"acabamentos":4}',
        "pecas": 1}, contexto)
    assert r["ok"]
    return {"responder": True, "bolhas": [f"Fica R$ {r['venda']:.2f} 🙂", "Quer que eu reserve?"],
            "motivo": "Calculei pela função de orçamento.", "assunto": "orcamento", "interesse": "quente",
            "funcoes_usadas": [{"funcao": "fazer_orcamento", "ok": True, "resultado": r["resultado"]}]}


def test_orcamento_faz_a_conta():
    serv = orcamento.config()["servicos"]["impressao"]
    r = orcamento.calcular(serv, {"area_m2": 0.54, "acabamentos": 4}, 1)
    v = serv["variaveis"]
    custo = (0.54 * v["area_m2"]["preco_por_unidade"] + 4 * v["acabamentos"]["preco_por_unidade"]
             + serv.get("custo_fixo", 0))
    venda = max(custo * serv["multiplicador"], serv["minimo"])
    assert r["custo"] == round(custo, 2)
    assert r["venda"] == round(venda, 2)
    assert r["venda_com_reserva"] == round(venda * (1 + serv["reserva_percentual"] / 100), 2)


def test_orcamento_pede_o_que_falta():
    r = orcamento.executar({"servico": "impressao", "descricao": "x", "quantidades_json": '{"area_m2": 0.5}', "pecas": 1}, {})
    assert not r["ok"] and "acabamentos" in r["resultado"]


def test_ferramentas_no_formato_do_claude():
    f = funcoes.ferramentas(funcoes.carregar())
    nomes = {x["name"] for x in f}
    assert {"passar_para_humano", "fazer_orcamento", "agenda", "cadastrar_cliente", "registrar_venda"} <= nomes
    for x in f:
        assert x["strict"] and x["input_schema"]["additionalProperties"] is False
        assert set(x["input_schema"]["required"]) == set(x["input_schema"]["properties"])


def test_agenda_marca_e_nao_deixa_lotar():
    livres = agenda.livres(14)
    assert livres, "a agenda de exemplo deveria ter horários"
    iso = livres[0].split("(")[1].split(")")[0]
    hora = livres[0].rsplit(" ", 1)[1]
    ctx = {"jid": "x@s.whatsapp.net", "simulacao": True}
    vagas = agenda.config()["vagas_por_horario"] if hasattr(agenda, "config") else 2
    for i in range(vagas):
        assert agenda.executar({"acao": "marcar", "data": iso, "hora": hora, "nome": f"P{i}", "assunto": "visita técnica"}, ctx)["ok"]
    r = agenda.executar({"acao": "marcar", "data": iso, "hora": hora, "nome": "Extra", "assunto": "visita técnica"}, ctx)
    assert not r["ok"], "quem passa das vagas do horário não cabe"


def test_manual_le_a_pasta_empresa_sem_o_leia_me():
    m = agente.manual()
    assert "Gráfica Rápida Exemplo" in m and "Pasta da empresa" not in m
    assert "Para o grupo da equipe" not in m and "Para o grupo da equipe" in agente.manual("equipe")


def test_fluxo_completo_vai_para_a_fila_no_modo_aprovar():
    original = motores.opencode_json
    motores.opencode_json = motor_falso
    try:
        router.receber({"chat_jid": "5500000000009@s.whatsapp.net", "content": "Oi", "is_from_me": False})
        for _ in range(50):
            if registro.fila():
                break
            time.sleep(0.1)
    finally:
        motores.opencode_json = original
    fila = registro.fila()
    assert len(fila) == 1 and fila[0]["bolhas"][0].startswith("Fica R$")
    assert fila[0]["funcoes"][0]["funcao"] == "fazer_orcamento" and fila[0]["funcoes"][0]["ok"]
    r = router.resumo()
    assert r["orcamentos"] == 1 and r["quentes"] == 1 and r["na_fila"] == 1


def test_funcoes_pelo_terminal_usam_o_contexto_da_central():
    import subprocess
    cli = Path(__file__).resolve().parents[1] / "nucleo" / "funcoes_cli.py"
    amb = {**os.environ, "GI_CONTEXTO": json.dumps({"jid": "5500000000007@s.whatsapp.net", "simulacao": True})}
    out = subprocess.run([sys.executable, "-X", "utf8", str(cli), "fazer_orcamento", "servico=impressao",
                          "descricao=cartao", 'quantidades_json={"area_m2":0.05,"acabamentos":1}', "pecas=2"],
                         capture_output=True, text=True, encoding="utf-8", env=amb)
    r = json.loads(out.stdout)
    assert r["ok"] and r["pecas"] == 2
    ev = [e for e in registro.eventos() if e["tipo"] == "orcamento" and e["jid"] == "5500000000007@s.whatsapp.net"]
    assert ev, "o orçamento tem que ficar no nome de quem a Central indicou"


def test_falha_do_motor_nao_responde_e_registra_erro():
    original = motores.opencode_json
    def quebra(*a, **k):
        raise motores.MotorFalhou("sem crédito")
    motores.opencode_json = quebra
    try:
        d = agente.decidir("[x] Cliente: oi", {"jid": "5500000000006@s.whatsapp.net"})
    finally:
        motores.opencode_json = original
    assert not d["responder"] and d.get("falhou")


def test_tarefa_complexa_cria_pedido_sem_rodar_motor_em_simulacao():
    from funcoes import tarefa_complexa
    assert "orcamento-arquivo" in tarefa_complexa.tipos()
    r = tarefa_complexa.executar({"tipo": "orcamento-arquivo", "pedido": "https://exemplo/arte.pdf"},
                                 {"jid": "5500000000005@s.whatsapp.net", "simulacao": True})
    assert r["ok"]
    import tarefa_complexa as executor
    texto = executor.montar_instrucoes("orcamento-arquivo", "link X")
    assert "result.ready" in texto and "funcoes_cli.py" in texto and "link X" in texto


def test_pessoa_respondeu_pelo_celular_tira_da_fila():
    if not registro.fila():
        registro.na_fila({"jid": "5500000000009@s.whatsapp.net", "bolhas": ["oi"]})
    router.receber({"chat_jid": "5500000000009@s.whatsapp.net", "content": "Oi, aqui é a Carla da equipe", "is_from_me": True})
    assert not registro.fila()


def test_modo_teste_so_envia_para_numero_de_teste():
    router.NUMEROS_TESTE[:] = ["5500000000009"]
    router.salvar_estado({"pausado": False, "modo": "teste"})
    assert router.pode_enviar_sozinho("5500000000009@s.whatsapp.net")
    assert not router.pode_enviar_sozinho("5500000000008@s.whatsapp.net")
    router.salvar_estado({"pausado": False, "modo": "aprovar"})
    assert not router.pode_enviar_sozinho("5500000000009@s.whatsapp.net")


if __name__ == "__main__":
    falhas = 0
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            try:
                fn()
                print("✅", nome)
            except Exception as e:  # noqa: BLE001
                falhas += 1
                print("❌", nome, "->", repr(e))
    sys.exit(1 if falhas else 0)
