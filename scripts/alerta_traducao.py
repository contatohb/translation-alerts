#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Executa o monitor_traducao.py, filtra apenas vagas NOVAS
(não alertadas antes), salva o email em arquivo JSON para
envio posterior via Gmail MCP diretamente pelo shell.

Uso:
    python3 alerta_traducao.py
    # O email será salvo em /tmp/traducao_email_payload.json
    # e o assunto em /tmp/traducao_email_subject.txt
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("alerta_traducao")

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPTS_DIR)

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_PROJECT_DIR, ".env"))
except Exception:
    pass

RECIPIENT    = os.getenv("MONITOR_RECIPIENT", "huddsong@gmail.com")
SEEN_PATH    = os.path.join(_PROJECT_DIR, "data", "traducao_seen.json")
PAYLOAD_PATH = "/tmp/traducao_email_payload.json"
SUBJECT_PATH = "/tmp/traducao_email_subject.txt"


# ─────────────────────────────────────────────────────────────────
# Histórico de vagas já alertadas
# ─────────────────────────────────────────────────────────────────

def load_seen(path: str) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_seen(seen: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────
# Principal
# ─────────────────────────────────────────────────────────────────

def main():
    import warnings
    warnings.filterwarnings("ignore")

    hoje = date.today()
    logger.info(f"Alerta de vagas de tradução — {hoje.isoformat()}")

    # Importar módulo de monitoramento
    try:
        from monitor_traducao import (
            buscar_vagas,
            filtrar_novas_vagas,
            formatar_email_traducao,
        )
    except ImportError as e:
        logger.error(f"Erro ao importar monitor_traducao: {e}")
        return 1

    # Buscar vagas
    logger.info("Buscando vagas de tradução (PT/EN/ES)...")
    vagas, erros = buscar_vagas()
    logger.info(f"Vagas encontradas: {len(vagas)}")

    # Carregar histórico e filtrar novas
    seen = load_seen(SEEN_PATH)
    novas, seen_atualizado = filtrar_novas_vagas(vagas, seen)
    logger.info(f"Vagas novas (não alertadas antes): {len(novas)}")

    # Salvar histórico atualizado
    save_seen(seen_atualizado, SEEN_PATH)

    # Limitar a 50 vagas por email para evitar payloads muito grandes
    MAX_VAGAS_POR_EMAIL = 50
    lotes = [novas[i:i+MAX_VAGAS_POR_EMAIL] for i in range(0, max(len(novas), 1), MAX_VAGAS_POR_EMAIL)]
    if not lotes:
        lotes = [[]]
    total_lotes = len(lotes)

    messages = []
    for idx, lote in enumerate(lotes, 1):
        # Gerar corpo do email
        corpo = formatar_email_traducao(lote, erros if idx == 1 else [])
        if idx == 1:
            print(corpo[:2000])  # Preview do primeiro lote

        # Definir assunto
        if novas:
            if total_lotes > 1:
                assunto = (
                    f"[Tradução] {len(novas)} nova(s) vaga(s) — "
                    f"{hoje.strftime('%d/%m/%Y')} (parte {idx}/{total_lotes})"
                )
            else:
                assunto = (
                    f"[Tradução] {len(novas)} nova(s) vaga(s) — "
                    f"{hoje.strftime('%d/%m/%Y')}"
                )
        else:
            assunto = f"[Tradução] Nenhuma vaga nova — {hoje.strftime('%d/%m/%Y')}"

        messages.append({
            "subject": assunto,
            "to": [RECIPIENT],
            "content": corpo,
        })

    # Salvar payload do email em arquivo para envio via Gmail MCP
    payload = {"messages": messages}
    with open(PAYLOAD_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    with open(SUBJECT_PATH, "w", encoding="utf-8") as f:
        f.write(messages[0]["subject"])

    logger.info(f"Payload do email salvo em: {PAYLOAD_PATH} ({total_lotes} mensagem(ns))")
    logger.info(f"Assunto: {messages[0]['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
