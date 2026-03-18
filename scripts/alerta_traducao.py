#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Executa o monitor_traducao.py, filtra apenas vagas NOVAS
(não alertadas antes) e envia email detalhado via Gmail MCP.

Uso:
    python3 alerta_traducao.py [--force-send]
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
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

RECIPIENT = os.getenv("MONITOR_RECIPIENT", "huddsong@gmail.com")
SEEN_PATH = os.path.join(_PROJECT_DIR, "data", "traducao_seen.json")


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
# Envio de email via Gmail MCP
# ─────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, recipient: str) -> bool:
    payload = {
        "messages": [{
            "subject": subject,
            "to": [recipient],
            "content": body,
        }]
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(payload, tmp, ensure_ascii=False)
    tmp.flush()
    tmp.close()
    try:
        with open(tmp.name, "r", encoding="utf-8") as f:
            input_str = f.read()
        result = subprocess.run(
            ["manus-mcp-cli", "tool", "call", "gmail_send_messages",
             "--server", "gmail", "--input", input_str],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            logger.info(f"Email enviado para {recipient}")
            return True
        else:
            logger.error(f"Erro ao enviar email: {result.stderr[:300]}")
            return False
    except Exception as exc:
        logger.error(f"Gmail MCP: {exc}")
        return False
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)


# ─────────────────────────────────────────────────────────────────
# Principal
# ─────────────────────────────────────────────────────────────────

def main():
    import warnings
    warnings.filterwarnings("ignore")

    force_send = "--force-send" in sys.argv

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

    # Gerar corpo do email
    corpo = formatar_email_traducao(novas, erros)
    print(corpo)

    # Definir assunto
    if novas:
        assunto = (
            f"[Tradução] {len(novas)} nova(s) vaga(s) — "
            f"{hoje.strftime('%d/%m/%Y')}"
        )
    else:
        assunto = f"[Tradução] Nenhuma vaga nova — {hoje.strftime('%d/%m/%Y')}"

    # Enviar email se há novidades ou se forçado
    if novas or force_send:
        ok = send_email(assunto, corpo, RECIPIENT)
        return 0 if ok else 1
    else:
        logger.info("Sem novidades — email não enviado (use --force-send para forçar)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
