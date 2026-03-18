#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Executa o monitor_traducao.py, filtra apenas vagas NOVAS
(não alertadas antes), gera email HTML premium, converte para PDF
e envia via Gmail MCP (corpo texto + PDF anexo).

Uso:
    python3 alerta_traducao.py
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
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
HTML_PATH    = "/tmp/traducao_email.html"
PDF_PATH     = "/tmp/traducao_email.pdf"

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
# Geração do corpo de texto do email (compacto para MCP)
# ─────────────────────────────────────────────────────────────────

def gerar_corpo_texto(vagas: List[Dict], erros: List[str]) -> str:
    """Gera corpo de texto simples para o email (cabeçalho + lista de vagas)."""
    hoje = date.today().strftime("%d/%m/%Y")
    total = len(vagas)
    fontes = Counter(v["fonte"] for v in vagas)

    n_email_direto = sum(
        1 for v in vagas
        if v.get("tipo_contato") == "email" and "@" in v.get("link_contato", "")
    )
    n_descoberto = sum(
        1 for v in vagas
        if v.get("contato_descoberto", {}).get("email")
    )
    n_site = sum(
        1 for v in vagas
        if v.get("contato_descoberto", {}).get("site")
        and not v.get("contato_descoberto", {}).get("email")
    )

    linhas = [
        f"ALERTA DIÁRIO DE VAGAS DE TRADUÇÃO — {hoje}",
        f"Total: {total} vaga(s) nova(s)",
        "",
    ]
    for fonte, n in fontes.items():
        linhas.append(f"  {fonte}: {n}")
    linhas.append("")
    if n_email_direto:
        linhas.append(f"  Contato direto (email): {n_email_direto}")
    if n_descoberto:
        linhas.append(f"  Email descoberto (busca reversa): {n_descoberto}")
    if n_site:
        linhas.append(f"  Site encontrado (busca reversa): {n_site}")
    linhas.append("")
    linhas.append("O relatório completo com todos os campos, descrições e links")
    linhas.append("está no arquivo PDF anexo.")
    linhas.append("")
    linhas.append("─" * 60)
    linhas.append("LISTA DE VAGAS:")
    linhas.append("")

    for i, v in enumerate(vagas, 1):
        linhas.append(f"{i}. [{v['fonte']}] {v['titulo'][:70]}")
        linhas.append(f"   Par: {v['par_display']} | Área: {v['area']}")
        if v.get("empresa"):
            linhas.append(f"   Empresa: {v['empresa']}")
        if v.get("pais"):
            linhas.append(f"   País: {v['pais']}")
        if v.get("prazo"):
            linhas.append(f"   Prazo: {v['prazo']}")
        if v.get("preco_palavra"):
            linhas.append(f"   Preço/palavra: {v['preco_palavra']}")
        # Contato
        cd = v.get("contato_descoberto", {})
        if v.get("tipo_contato") == "email" and "@" in v.get("link_contato", ""):
            linhas.append(f"   Email: {v['link_contato']}")
        elif cd.get("email"):
            linhas.append(f"   Email (descoberto): {cd['email']}")
        elif cd.get("site"):
            linhas.append(f"   Site: {cd['site']}")
        if v.get("link_vaga"):
            linhas.append(f"   Link: {v['link_vaga']}")
        linhas.append("")

    if erros:
        linhas.append("─" * 60)
        linhas.append("AVISOS DO SISTEMA:")
        for err in erros:
            linhas.append(f"  - {err}")

    return "\n".join(linhas)


# ─────────────────────────────────────────────────────────────────
# Envio via Gmail MCP (corpo texto + PDF anexo)
# ─────────────────────────────────────────────────────────────────

def enviar_via_mcp(assunto: str, corpo: str, pdf_path: str) -> bool:
    """
    Envia o email via manus-mcp-cli.
    Usa corpo de texto simples (compacto) + PDF como anexo.
    Retorna True se enviado com sucesso.
    """
    payload = {
        "messages": [{
            "to": [RECIPIENT],
            "subject": assunto,
            "content": corpo,
            "attachments": [pdf_path] if os.path.exists(pdf_path) else [],
        }]
    }

    payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    logger.info(f"Payload MCP: {len(payload_str)} chars")

    try:
        result = subprocess.run(
            ["manus-mcp-cli", "tool", "call", "gmail_send_messages",
             "--server", "gmail", "--input", payload_str],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            logger.info("Email enviado com sucesso via Gmail MCP")
            return True
        else:
            logger.error(f"Erro no envio: {result.stderr[:500]}")
            return False
    except OSError as e:
        if "Argument list too long" in str(e):
            logger.error("Payload muito grande para o shell — tentando sem PDF...")
            # Fallback: enviar só o texto sem PDF
            payload["messages"][0]["attachments"] = []
            payload_str2 = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            result2 = subprocess.run(
                ["manus-mcp-cli", "tool", "call", "gmail_send_messages",
                 "--server", "gmail", "--input", payload_str2],
                capture_output=True, text=True, timeout=120
            )
            if result2.returncode == 0:
                logger.info("Email enviado (sem PDF) via Gmail MCP")
                return True
        logger.error(f"Erro ao executar manus-mcp-cli: {e}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao enviar email")
        return False


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

    # Assunto do email
    date_str = hoje.strftime("%d/%m/%Y")
    if novas:
        assunto = f"[Tradução] {len(novas)} nova(s) vaga(s) — {date_str}"
    else:
        assunto = f"[Tradução] Nenhuma vaga nova — {date_str}"

    # Gerar HTML premium (para o PDF)
    logger.info("Gerando HTML premium...")
    payloads = gerar_payloads_email(
        vagas=novas,
        erros=erros,
        destinatario=RECIPIENT,
        max_por_email=MAX_VAGAS_POR_EMAIL,
    )
    html = payloads[0]["messages"][0]["content"]

    # Salvar HTML
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML salvo: {len(html)} chars")

    # Converter HTML → PDF
    pdf_ok = False
    try:
        result = subprocess.run(
            ["manus-md-to-pdf", HTML_PATH, PDF_PATH],
            capture_output=True, text=True, timeout=120
        )
        if os.path.exists(PDF_PATH) and os.path.getsize(PDF_PATH) > 0:
            pdf_ok = True
            logger.info(f"PDF gerado: {os.path.getsize(PDF_PATH):,} bytes")
        else:
            logger.warning("PDF não gerado ou vazio")
    except Exception as e:
        logger.warning(f"Erro ao gerar PDF: {e}")

    # Gerar corpo de texto compacto
    corpo = gerar_corpo_texto(novas, erros)

    # Salvar payload para referência
    payload_ref = {
        "messages": [{
            "to": [RECIPIENT],
            "subject": assunto,
            "content": corpo,
            "pdf_path": PDF_PATH if pdf_ok else None,
        }]
    }
    with open(PAYLOAD_PATH, "w", encoding="utf-8") as f:
        json.dump(payload_ref, f, ensure_ascii=False, indent=2)
    with open(SUBJECT_PATH, "w", encoding="utf-8") as f:
        f.write(assunto)

    logger.info(f"Assunto: {assunto}")

    # Enviar email
    enviado = enviar_via_mcp(assunto, corpo, PDF_PATH if pdf_ok else "")
    if enviado:
        logger.info("Alerta enviado com sucesso!")
    else:
        logger.error("Falha no envio do alerta")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
