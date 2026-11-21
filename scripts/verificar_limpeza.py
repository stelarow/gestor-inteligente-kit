"""Procura dados pessoais ou internos que não deveriam estar no kit antes de compartilhar.

Uso:  python scripts/verificar_limpeza.py                  (procura telefones, CPF, e-mails, chaves)
      python scripts/verificar_limpeza.py --palavras "NomeDaEmpresa,NomeDoFuncionario"
"""
import argparse
import io
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parents[1]
PULAR = {".git", "dados", "store", "__pycache__", "node_modules"}
PADROES = {
    "telefone": re.compile(r"(?<!\d)55\d{10,11}(?!\d)"),
    "cpf": re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"),
    "e-mail": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "chave": re.compile(r"(sk-ant-[\w-]{10,}|tsk_[\w]{10,}|Bearer [\w-]{20,})"),
    "grupo/lid": re.compile(r"\d{12,}@(g\.us|lid)"),
}
PERMITIDOS = re.compile(r"55000000000\d|noreply@|exemplo|example\.com|@s\.whatsapp\.net|@lid\b|@g\.us")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--palavras", default="")
    a = p.parse_args()
    palavras = [x.strip() for x in a.palavras.split(",") if x.strip()]
    achados = 0
    for arq in RAIZ.rglob("*"):
        if arq.is_dir() or PULAR & set(arq.relative_to(RAIZ).parts) or arq.suffix in (".exe", ".sum") \
                or arq.name in ("verificar_limpeza.py", ".env"):
            continue
        try:
            texto = arq.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            for nome, rx in PADROES.items():
                for m in rx.finditer(linha):
                    if not PERMITIDOS.search(m.group(0)):
                        achados += 1
                        print(f"⚠️ {nome}: {arq.relative_to(RAIZ)}:{n}: {m.group(0)}")
            for pal in palavras:
                if pal.lower() in linha.lower():
                    achados += 1
                    print(f"⚠️ palavra '{pal}': {arq.relative_to(RAIZ)}:{n}")
    print("✅ Nada encontrado." if not achados else f"🚨 {achados} itens para revisar.")
    sys.exit(1 if achados else 0)


if __name__ == "__main__":
    main()
