"""Transforma áudio do WhatsApp em texto, no próprio computador (opcional).

Precisa de: pip install faster-whisper
Sem isso, a IA só fica sabendo que chegou um áudio e pede para a pessoa escrever.
"""
from __future__ import annotations

_modelo = None


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcrever(caminho: str) -> str:
    global _modelo
    from faster_whisper import WhisperModel
    if _modelo is None:
        try:
            _modelo = WhisperModel("small", device="cuda", compute_type="float16")
        except Exception:  # noqa: BLE001 — sem placa de vídeo, usa o processador
            _modelo = WhisperModel("small", device="cpu", compute_type="int8")
    partes, _ = _modelo.transcribe(caminho, language="pt", vad_filter=True)
    return " ".join(p.text.strip() for p in partes).strip()
