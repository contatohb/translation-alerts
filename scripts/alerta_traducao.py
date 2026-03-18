#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Fluxo:
  1. Busca vagas nas três fontes (ProZ, TC, TD)
  2. Filtra apenas vagas NOVAS (não alertadas antes via seen.json)
  3. Gera HTML premium com design dark mode
  4. Converte HTML → PDF via Chromium headless
  5. Faz upload do PDF para o Google Drive (link público)
  6. Envia email via Gmail MCP: corpo texto compacto + link do Drive

O link do Drive é permanente e funciona tanto no agendamento diário
quanto em execuções manuais. O token OAuth do Drive é injetado pelo
ambiente do Manus Schedule via GOOGLE_DRIVE_TOKEN.

Uso:
    python3 alerta_traducao.py
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
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
PDF_PATH     = "/tmp/traducao_email.pdf"
PAYLOAD_PATH = "/tmp/traducao_email_payload.json"
SUBJECT_PATH = "/tmp/traducao_email_subject.txt"

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
# Geração do PDF via Chromium headless
# ─────────────────────────────────────────────────────────────────

def gerar_pdf_chromium(html_path: str, pdf_path: str) -> bool:
    """
    Converte HTML → PDF usando Chromium headless.
    Renderiza o design completo (dark mode, CSS, etc.).
    Retorna True se o PDF foi gerado com sucesso.
    """
    try:
        result = subprocess.run(
            [
                "chromium-browser",
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                f"--print-to-pdf={pdf_path}",
                "--print-to-pdf-no-header",
                f"file://{html_path}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            logger.info(f"PDF gerado: {os.path.getsize(pdf_path):,} bytes")
            return True
        else:
            logger.warning(f"Chromium falhou: {result.stderr[-300:]}")
            return False
    except Exception as e:
        logger.warning(f"Erro ao gerar PDF com Chromium: {e}")
        return False


# ─────────────────────────────────────────────────────────────────
# Upload para o Google Drive
# ─────────────────────────────────────────────────────────────────

def upload_para_drive(pdf_path: str, nome_arquivo: str) -> Optional[str]:
    """
    Faz upload do PDF para o Google Drive e retorna o link público.
    Usa o token OAuth injetado pelo ambiente (GOOGLE_DRIVE_TOKEN).
    Retorna None se falhar.
    """
    try:
        import requests as req
    except ImportError:
        logger.error("requests não instalado")
        return None

    token = os.environ.get("GOOGLE_DRIVE_TOKEN") or os.environ.get("GOOGLE_WORKSPACE_CLI_TOKEN")
    if not token:
        logger.warning("Token do Google Drive não encontrado — pulando upload")
        return None

    logger.info("Fazendo upload do PDF para o Google Drive...")

    # Metadados do arquivo
    metadata = {"name": nome_arquivo, "mimeType": "application/pdf"}

    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    # Upload multipart
    boundary = "-------314159265358979323846"
    delimiter = f"\r\n--{boundary}\r\n"
    close_delim = f"\r\n--{boundary}--"

    body = (
        delimiter
        + "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(metadata)
        + delimiter
        + "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + pdf_data + close_delim.encode("utf-8")

    try:
        resp = req.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f'multipart/related; boundary="{boundary}"',
            },
            data=body,
            timeout=120,
        )
    except Exception as e:
        logger.error(f"Erro no upload para o Drive: {e}")
        return None

    if resp.status_code != 200:
        logger.error(f"Upload falhou ({resp.status_code}): {resp.text[:200]}")
        return None

    file_id = resp.json().get("id")
    if not file_id:
        logger.error("File ID não retornado pelo Drive")
        return None

    logger.info(f"File ID: {file_id}")

    # Tornar o arquivo público (qualquer pessoa com o link pode visualizar)
    try:
        perm_resp = req.post(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"role": "reader", "type": "anyone"},
            timeout=30,
        )
        if perm_resp.status_code not in (200, 201):
            logger.warning(f"Não foi possível tornar o arquivo público: {perm_resp.status_code}")
    except Exception as e:
        logger.warning(f"Erro ao definir permissão: {e}")

    link = f"https://drive.google.com/file/d/{file_id}/view"
    logger.info(f"Link do Drive: {link}")
    return link


# ─────────────────────────────────────────────────────────────────
# Geração do corpo de texto do email (compacto para MCP)
# ─────────────────────────────────────────────────────────────────

def gerar_corpo_texto(vagas: List[Dict], erros: List[str], pdf_link: Optional[str]) -> str:
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

    if pdf_link:
        linhas.append("RELATÓRIO COMPLETO (design premium, todos os campos, links de candidatura):")
        linhas.append(pdf_link)
        linhas.append("")

    linhas.append("-" * 60)
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
        linhas.append("-" * 60)
        linhas.append("AVISOS DO SISTEMA:")
        for err in erros:
            linhas.append(f"  - {err}")

    return "\n".join(linhas)


# ─────────────────────────────────────────────────────────────────
# Envio via Gmail MCP
# ─────────────────────────────────────────────────────────────────

def enviar_via_mcp(assunto: str, corpo: str) -> bool:
    """
    Envia o email via manus-mcp-cli (Gmail MCP).
    O corpo de texto é compacto (<20KB) para não exceder o limite do shell.
    Retorna True se enviado com sucesso.
    """
    payload = {
        "messages": [{
            "to": [RECIPIENT],
            "subject": assunto,
            "content": corpo,
        }]
    }

    payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    logger.info(f"Payload MCP: {len(payload_str.encode('utf-8'))//1024} KB")

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
        logger.info("Nenhuma vaga nova — email não enviado")
        return 0

    # Gerar HTML premium
    logger.info("Gerando HTML premium...")
    payloads = gerar_payloads_email(
        vagas=novas,
        erros=erros,
        destinatario=RECIPIENT,
        max_por_email=MAX_VAGAS_POR_EMAIL,
    )
    html = payloads[0]["messages"][0]["content"]

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML salvo: {len(html):,} chars")

    # Converter HTML → PDF via Chromium headless
    pdf_ok = gerar_pdf_chromium(HTML_PATH, PDF_PATH)

    # Upload do PDF para o Google Drive
    pdf_link = None
    if pdf_ok:
        nome_pdf = f"Vagas_Traducao_{hoje.strftime('%d-%m-%Y')}.pdf"
        pdf_link = upload_para_drive(PDF_PATH, nome_pdf)

    # Gerar corpo de texto compacto
    corpo = gerar_corpo_texto(novas, erros, pdf_link)

    # Salvar payload para referência
    with open(PAYLOAD_PATH, "w", encoding="utf-8") as f:
        json.dump({"subject": assunto, "pdf_link": pdf_link, "vagas": len(novas)}, f, ensure_ascii=False, indent=2)
    with open(SUBJECT_PATH, "w", encoding="utf-8") as f:
        f.write(assunto)

    logger.info(f"Assunto: {assunto}")

    # Enviar email via Gmail MCP
    enviado = enviar_via_mcp(assunto, corpo)
    if enviado:
        logger.info("Alerta enviado com sucesso!")
    else:
        logger.error("Falha no envio do alerta")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
