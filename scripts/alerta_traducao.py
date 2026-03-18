#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Fluxo:
  1. Busca vagas nas três fontes (ProZ, TC, TD)
  2. Filtra apenas vagas NOVAS (não alertadas antes via seen.json)
  3. Gera HTML premium com design dark mode completo
  4. Converte HTML para PDF via Chromium headless
  5. Faz upload do PDF para o Google Drive (token via GOOGLE_DRIVE_TOKEN)
  6. Envia email via manus-mcp-cli com texto simples + link do Drive

Arquitetura de envio:
  - O Gmail MCP aceita apenas texto simples no campo 'content' (não HTML)
  - O Gmail MCP não processa caminhos de arquivo local em 'attachments'
  - A solução é: PDF → Drive → link no email (funciona para qualquer tamanho)
  - O GOOGLE_DRIVE_TOKEN está disponível como variável de ambiente no sandbox

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
PDF_PATH     = "/tmp/traducao_newsletter.pdf"

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
# Geração de PDF via Chromium headless
# ─────────────────────────────────────────────────────────────────

def gerar_pdf(html_path: str, pdf_path: str) -> bool:
    """Converte HTML para PDF usando Chromium headless."""
    try:
        result = subprocess.run(
            [
                "chromium-browser",
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                f"--print-to-pdf={pdf_path}",
                "--print-to-pdf-no-header",
                f"file://{html_path}",
            ],
            capture_output=True,
            timeout=120,
        )
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
            size_kb = os.path.getsize(pdf_path) // 1024
            logger.info(f"PDF gerado: {pdf_path} ({size_kb} KB)")
            return True
        else:
            logger.error(f"PDF não gerado ou vazio. Chromium retornou: {result.stderr[:200]}")
            return False
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {e}")
        return False


# ─────────────────────────────────────────────────────────────────
# Upload para o Google Drive
# ─────────────────────────────────────────────────────────────────

def upload_drive(pdf_path: str, nome_arquivo: str) -> Optional[str]:
    """
    Faz upload do PDF para o Google Drive e retorna o link compartilhado.
    Usa o token OAuth do GOOGLE_DRIVE_TOKEN (disponível no ambiente do sandbox).
    """
    try:
        import requests as req
    except ImportError:
        logger.error("requests não instalado")
        return None

    token = os.getenv("GOOGLE_DRIVE_TOKEN") or os.getenv("GOOGLE_WORKSPACE_CLI_TOKEN")
    if not token:
        logger.error("GOOGLE_DRIVE_TOKEN não encontrado")
        return None

    try:
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        metadata = {"name": nome_arquivo, "mimeType": "application/pdf"}

        r = req.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "metadata": ("metadata", json.dumps(metadata), "application/json"),
                "file": ("newsletter.pdf", pdf_data, "application/pdf"),
            },
            timeout=60,
        )

        if r.status_code != 200:
            logger.error(f"Erro no upload para o Drive: {r.status_code} — {r.text[:200]}")
            return None

        file_id = r.json()["id"]
        logger.info(f"Upload para o Drive OK. File ID: {file_id}")

        # Tornar público (qualquer pessoa com o link pode visualizar)
        r2 = req.post(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"role": "reader", "type": "anyone"},
            timeout=10,
        )
        if r2.status_code not in (200, 201):
            logger.warning(f"Não foi possível tornar o arquivo público: {r2.status_code}")

        link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        logger.info(f"Link do Drive: {link}")
        return link

    except Exception as e:
        logger.error(f"Erro no upload para o Drive: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# Envio via Gmail MCP
# ─────────────────────────────────────────────────────────────────

def enviar_via_mcp(assunto: str, corpo: str) -> bool:
    """
    Envia o email via manus-mcp-cli com texto simples no corpo.

    O Gmail MCP aceita apenas plain text no campo 'content'.
    O design premium é entregue via PDF no Google Drive (link no corpo).
    O payload de texto simples é pequeno (<2KB) e não tem problemas de limite.
    """
    payload = json.dumps({
        "messages": [{
            "to": [RECIPIENT],
            "subject": assunto,
            "content": corpo,
        }]
    }, ensure_ascii=False)

    try:
        result = subprocess.run(
            ["manus-mcp-cli", "tool", "call", "gmail_send_messages",
             "--server", "gmail", "--input", payload],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # Extrair Message ID do resultado mais recente
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


# ─────────────────────────────────────────────────────────────────
# Geração do corpo do email (texto simples)
# ─────────────────────────────────────────────────────────────────

def gerar_corpo_email(
    vagas: List[Dict],
    erros: List[str],
    drive_link: Optional[str],
    date_str: str,
) -> str:
    """Gera o corpo em texto simples com resumo e link do PDF."""
    por_fonte = Counter(v.get("fonte", "") for v in vagas)
    n_contato = sum(
        1 for v in vagas
        if v.get("contato_descoberto", {}).get("email")
        or v.get("contato_descoberto", {}).get("site")
    )
    n_email = sum(
        1 for v in vagas
        if v.get("tipo_contato") == "email" and "@" in v.get("link_contato", "")
    )

    linhas = [
        f"Alerta Diário de Vagas de Tradução — {date_str}",
        "",
        f"Total de vagas novas: {len(vagas)}",
    ]
    for fonte in ["ProZ.com", "Translators Café", "Translation Directory"]:
        n = por_fonte.get(fonte, 0)
        if n:
            linhas.append(f"  • {fonte}: {n} vaga{'s' if n != 1 else ''}")

    linhas += [
        "",
        f"Contatos descobertos via busca reversa: {n_contato}",
        f"Email direto disponível: {n_email}",
    ]

    if drive_link:
        linhas += [
            "",
            "RELATÓRIO COMPLETO (PDF com design premium):",
            drive_link,
            "",
            "O PDF contém todos os campos por vaga:",
            "  par de idiomas, área, empresa, país, prazo, preço/palavra, descrição e contato.",
        ]
    else:
        linhas += [
            "",
            "NOTA: O PDF não pôde ser gerado nesta execução.",
            "Verifique os logs para mais detalhes.",
        ]

    if erros:
        linhas += ["", "Avisos do sistema:"]
        for err in erros:
            linhas.append(f"  - {err}")

    linhas += [
        "",
        "---",
        "Sistema de Alertas de Tradução — Hudson Borges",
        "Pares monitorados: PT <> EN · PT <> ES · EN <> ES",
    ]

    return "\n".join(linhas)


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
        from email_template import gerar_html_email
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

    # Gerar HTML premium
    logger.info("Gerando HTML premium...")
    html = gerar_html_email(novas, erros)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = len(html.encode("utf-8")) // 1024
    logger.info(f"HTML gerado: {size_kb} KB")

    # Gerar PDF via Chromium headless
    logger.info("Gerando PDF via Chromium headless...")
    pdf_ok = gerar_pdf(HTML_PATH, PDF_PATH)

    # Upload do PDF para o Google Drive
    drive_link = None
    if pdf_ok:
        logger.info("Fazendo upload do PDF para o Google Drive...")
        nome_pdf = f"Newsletter Vagas Tradução — {date_str.replace('/', '-')}.pdf"
        drive_link = upload_drive(PDF_PATH, nome_pdf)
        if not drive_link:
            logger.warning("Upload para o Drive falhou — email será enviado sem link do PDF")

    # Gerar corpo do email (texto simples com link do Drive)
    assunto = f"[Tradução] {len(novas)} nova(s) vaga(s) — {date_str}"
    corpo = gerar_corpo_email(novas, erros, drive_link, date_str)

    logger.info(f"Assunto: {assunto}")
    logger.info(f"Corpo: {len(corpo)} chars")

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
