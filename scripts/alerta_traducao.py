#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Fluxo:
  1. Busca vagas nas três fontes (ProZ, TC, TD)
  2. Filtra apenas vagas NOVAS (não alertadas antes via seen.json)
  3. Gera HTML premium com design dark mode completo
  4. Salva o payload JSON em arquivo temporário
  5. Envia via manus-mcp-cli com --input @arquivo (sem limite de tamanho)

A solução --input @arquivo contorna o limite de argumento do shell (~130KB),
permitindo enviar emails HTML de qualquer tamanho. Funciona tanto em
execuções manuais quanto no agendamento diário (Manus Schedule).

Uso:
    python3 alerta_traducao.py
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

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
HTML_PATH    = "/tmp/traducao_email.html"
PAYLOAD_PATH = "/tmp/traducao_email_payload.json"

MAX_VAGAS_POR_EMAIL = 200  # Todas as vagas em um único email


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
# Envio via Gmail MCP usando --input @arquivo
# ─────────────────────────────────────────────────────────────────

def enviar_via_mcp(assunto: str, html: str) -> bool:
    """
    Envia o email HTML completo via manus-mcp-cli usando --input @arquivo.

    Esta abordagem salva o payload JSON em um arquivo temporário e passa
    o caminho com o prefixo '@' para o manus-mcp-cli, contornando o limite
    de tamanho de argumento do shell (~130KB). Suporta emails de qualquer
    tamanho e funciona tanto manualmente quanto no agendamento diário.
    """
    payload = {
        "messages": [{
            "to": [RECIPIENT],
            "subject": assunto,
            "content": html,
        }]
    }

    # Salvar payload em arquivo temporário
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    size_kb = os.path.getsize(tmp_path) // 1024
    logger.info(f"Payload salvo em {tmp_path} ({size_kb} KB)")

    try:
        result = subprocess.run(
            [
                "manus-mcp-cli", "tool", "call", "gmail_send_messages",
                "--server", "gmail",
                "--input", f"@{tmp_path}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # Extrair Message ID do resultado
            try:
                result_files = sorted(
                    [f for f in os.listdir("/tmp/manus-mcp") if f.startswith("mcp_result_")],
                    key=lambda f: os.path.getmtime(f"/tmp/manus-mcp/{f}"),
                    reverse=True,
                )
                if result_files:
                    with open(f"/tmp/manus-mcp/{result_files[0]}", "r") as rf:
                        result_data = json.load(rf)
                    msgs = result_data.get("messages", [])
                    if msgs:
                        msg_id = msgs[0].get("messageId", "N/A")
                        logger.info(f"Email enviado — Message ID: {msg_id}")
            except Exception:
                pass
            logger.info("Email enviado com sucesso via Gmail MCP")
            return True
        else:
            logger.error(f"Erro no envio (código {result.returncode}): {result.stderr[:500]}")
            return False
    except OSError as e:
        logger.error(f"Erro ao executar manus-mcp-cli: {e}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao enviar email")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────
# Principal
# ─────────────────────────────────────────────────────────────────

def main():
    import warnings
    warnings.filterwarnings("ignore")

    hoje = date.today()
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

    if not novas:
        logger.info("Nenhuma vaga nova — email não enviado")
        return 0

    # Assunto do email
    date_str = hoje.strftime("%d/%m/%Y")
    assunto = f"[Tradução] {len(novas)} nova(s) vaga(s) — {date_str}"

    # Gerar HTML premium (design dark mode completo)
    logger.info("Gerando HTML premium...")
    payloads = gerar_payloads_email(
        vagas=novas,
        erros=erros,
        destinatario=RECIPIENT,
        max_por_email=MAX_VAGAS_POR_EMAIL,
    )
    html = payloads[0]["messages"][0]["content"]

    # Salvar HTML para referência
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML gerado: {len(html):,} chars ({len(html.encode('utf-8'))//1024} KB)")

    logger.info(f"Assunto: {assunto}")

    # Enviar email via Gmail MCP com --input @arquivo
    enviado = enviar_via_mcp(assunto, html)
    if enviado:
        logger.info("Alerta enviado com sucesso!")
    else:
        logger.error("Falha no envio do alerta")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
