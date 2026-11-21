"""Configuração do Gestor Inteligente: lê o arquivo .env e define as pastas."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Windows: deixa aparecer acentos e emojis no terminal
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

RAIZ = Path(os.environ.get("GI_RAIZ", Path(__file__).resolve().parents[1])).resolve()
EMPRESA = RAIZ / "empresa"


def _carregar_env() -> None:
    arq = RAIZ / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()

DADOS = Path(os.environ.get("GI_DADOS", RAIZ / "dados")).resolve()
DADOS.mkdir(parents=True, exist_ok=True)


def env(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome, padrao).strip()


def lista(nome: str) -> list[str]:
    return [x.strip() for x in env(nome).split(",") if x.strip()]


# WhatsApp (bridge)
BRIDGE_URL = env("GI_BRIDGE_URL", "http://127.0.0.1:8080")
MENSAGENS_DB = Path(env("GI_MENSAGENS_DB", str(RAIZ / "bridge" / "store" / "messages.db")))
PORTA_PAINEL = int(env("GI_PORTA", "8791"))
# 127.0.0.1 = painel só neste computador. Para abrir no celular da rede, use 0.0.0.0 (sem senha!)
ESCUTAR = env("GI_ESCUTAR", "127.0.0.1")

# IA
ESPERA_SEGUNDOS = int(env("GI_ESPERA_SEGUNDOS", "60"))  # junta mensagens picadas
JEV_MODELO = env("GI_JEV_MODELO", "jev-1.14.0")

# Segurança: começa sempre no modo "aprovar"
# aprovar  = a IA escreve, o líder aprova no painel
# teste    = envia sozinho só para os números de teste
# liberado = envia sozinho para todos
MODO = env("GI_MODO", "aprovar")
NUMEROS_TESTE = lista("GI_NUMEROS_TESTE")
NUMERO_LIDER = env("GI_NUMERO_LIDER")           # quem recebe os avisos de "passar para humano"
GRUPO_EQUIPE = env("GI_GRUPO_EQUIPE")            # JID do grupo da equipe (termina em @g.us)

ESTADO = DADOS / "estado.json"


def ler_estado() -> dict:
    """Estado que o painel muda sem reiniciar (pausar, modo)."""
    base = {"pausado": False, "modo": MODO}
    try:
        base.update(json.loads(ESTADO.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return base


def salvar_estado(estado: dict) -> None:
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ESTADO)
