#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Executa o monitor_traducao.py, filtra apenas vagas NOVAS
(não alertadas antes), gera email HTML premium e salva
o payload JSON para envio via Gmail MCP pelo shell.

Uso:
    python3 alerta_traducao.py
    # O payload será salvo em /tmp/traducao_email_payload.json
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

MAX_VAGAS_POR_EMAIL = 50


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
    date_str = hoje.strftime("%d/%m/%Y")
    logger.info(f"Alerta de vagas de tradução — {hoje.isoformat()}")

    # Importar módulos
    try:
        from monitor_traducao import buscar_vagas, filtrar_novas_vagas
        from email_template import gerar_payloads_email
    except ImportError as e:
        logger.error(f"Erro ao importar módulos: {e}")
        return 1

    # Buscar vagas
    logger.info("Buscando vagas de tradução (PT/EN/ES)...")
    vagas, erros = buscar_vagas()
    logger.info(f"Vagas encontradas: {len(vagas)}")
    if erros:
        for err in erros:
            logger.warning(f"Aviso: {err}")

    # Carregar histórico e filtrar novas
    seen = load_seen(SEEN_PATH)
    novas, seen_atualizado = filtrar_novas_vagas(vagas, seen)
    logger.info(f"Vagas novas (não alertadas antes): {len(novas)}")

    # Salvar histórico atualizado
    save_seen(seen_atualizado, SEEN_PATH)

    # Gerar payloads usando o template premium
    payloads = gerar_payloads_email(
        vagas=novas,
        erros=erros,
        destinatario=RECIPIENT,
        max_por_email=MAX_VAGAS_POR_EMAIL,
    )

    # Salvar payload para envio via Gmail MCP
    # Formato: {"messages": [...]} com todos os emails em uma lista única
    all_messages = []
    for p in payloads:
        all_messages.extend(p["messages"])

    payload_final = {"messages": all_messages}

    with open(PAYLOAD_PATH, "w", encoding="utf-8") as f:
        json.dump(payload_final, f, ensure_ascii=False)

    with open(SUBJECT_PATH, "w", encoding="utf-8") as f:
        f.write(all_messages[0]["subject"])

    logger.info(f"Payload salvo em: {PAYLOAD_PATH} ({len(all_messages)} mensagem(ns))")
    logger.info(f"Assunto: {all_messages[0]['subject']}")
    logger.info(f"Tamanho do payload: {os.path.getsize(PAYLOAD_PATH):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
