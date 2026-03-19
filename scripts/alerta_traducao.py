#!/usr/bin/env python3
"""
Alerta diário de novas vagas de tradução.

Fluxo:
  1. Busca vagas nas três fontes (ProZ, TC, TD)
  2. Filtra apenas vagas NOVAS via Supabase (tabela traducao.vagas_vistas)
  3. Gera HTML premium com design dark mode completo
  4. Envia o HTML completo via SMTP (Gmail App Password) — sem limite de tamanho
  5. Registra a execução em traducao.log_execucoes

Arquitetura de envio (sem dependências do Manus):
  - Deduplicação: Supabase Postgres (tabela traducao.vagas_vistas)
  - Envio: SMTP Gmail com App Password (smtplib nativo do Python)
  - Credenciais: variáveis de ambiente (SUPABASE_URL, SUPABASE_KEY, GMAIL_APP_PASSWORD)
    ou fallback para tabela traducao.configuracoes no Supabase

Variáveis de ambiente necessárias (GitHub Actions Secrets):
  SUPABASE_URL          — ex: https://wuadkgmggkmyglxpxeyh.supabase.co
  SUPABASE_KEY          — service_role key do projeto Intellicore
  GMAIL_USER            — huddsong@gmail.com
  GMAIL_APP_PASSWORD    — App Password de 16 caracteres (sem espaços)
  GMAIL_RECIPIENT       — huddsong@gmail.com (pode ser igual ao GMAIL_USER)

Uso:
    python3 alerta_traducao.py
"""
from __future__ import annotations

import subprocess
import sys

# ── Auto-instalação de dependências ausentes ─────────────────────
_DEPS = ["httpx[http2]", "selenium", "lxml", "webdriver-manager"]
for _dep in _DEPS:
    try:
        __import__(_dep.split("[")[0].replace("-", "_"))
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", _dep],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

import json
import logging
import os
import smtplib
import time
from collections import Counter
from datetime import date, datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

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


# ─────────────────────────────────────────────────────────────────
# Configuração via variáveis de ambiente
# ─────────────────────────────────────────────────────────────────

SUPABASE_URL      = os.getenv("SUPABASE_URL", "https://wuadkgmggkmyglxpxeyh.supabase.co").strip()
SUPABASE_KEY      = os.getenv("SUPABASE_KEY", "").strip()
GMAIL_USER        = os.getenv("GMAIL_USER", "huddsong@gmail.com").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
GMAIL_RECIPIENT   = os.getenv("GMAIL_RECIPIENT", "huddsong@gmail.com").strip()

# Fallback: arquivo local (compatibilidade com execuções sem Supabase)
SEEN_PATH = os.path.join(_PROJECT_DIR, "data", "traducao_seen.json")


# ─────────────────────────────────────────────────────────────────
# Cliente Supabase (REST API — sem dependência de biblioteca externa)
# ─────────────────────────────────────────────────────────────────

class SupabaseClient:
    """Cliente minimalista para a API REST do Supabase."""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
            # Tabelas no schema public com prefixo traducao_
        }

    def _get(self, path: str, params: dict = None) -> Optional[list]:
        try:
            import requests
            r = requests.get(
                f"{self.url}/rest/v1/{path}",
                headers={**self._headers, "Prefer": "return=representation"},
                params=params or {},
                timeout=15,
            )
            if r.status_code == 200:
                return r.json()
            logger.warning(f"Supabase GET {path}: {r.status_code} — {r.text[:200]}")
            return None
        except Exception as e:
            logger.warning(f"Supabase GET erro: {e}")
            return None

    def _post(self, path: str, data: dict | list) -> bool:
        try:
            import requests
            r = requests.post(
                f"{self.url}/rest/v1/{path}",
                headers=self._headers,
                json=data,
                timeout=15,
            )
            return r.status_code in (200, 201, 204)
        except Exception as e:
            logger.warning(f"Supabase POST erro: {e}")
            return False

    def _rpc(self, func: str, params: dict = None) -> Optional[dict]:
        try:
            import requests
            r = requests.post(
                f"{self.url}/rest/v1/rpc/{func}",
                headers={**self._headers, "Prefer": "return=representation"},
                json=params or {},
                timeout=15,
            )
            if r.status_code == 200:
                return r.json()
            logger.warning(f"Supabase RPC {func}: {r.status_code} — {r.text[:200]}")
            return None
        except Exception as e:
            logger.warning(f"Supabase RPC erro: {e}")
            return None

    def get_urls_vistas(self) -> set:
        """Retorna o conjunto de URLs já alertadas. Lança RuntimeError se o Supabase falhar."""
        rows = self._get("traducao_vagas_vistas", {"select": "url"})
        if rows is None:
            raise RuntimeError("Supabase inacessível — get_urls_vistas retornou None")
        return {r["url"] for r in rows}

    def marcar_vistas(self, vagas: List[Dict]) -> bool:
        """Registra as novas vagas como vistas."""
        if not vagas:
            return True
        rows = [
            {
                "url": v.get("link_vaga", ""),
                "fonte": v.get("fonte", ""),
                "titulo": v.get("titulo", "")[:500],
                "primeira_vez_vista": datetime.now(timezone.utc).isoformat(),
                "ultima_vez_vista": datetime.now(timezone.utc).isoformat(),
            }
            for v in vagas
            if v.get("link_vaga")
        ]
        return self._post(
            "traducao_vagas_vistas?on_conflict=url",
            rows,
        )

    def registrar_execucao(self, dados: dict) -> bool:
        """Registra o log da execução diária."""
        return self._post("traducao_log_execucoes", dados)

    def get_config(self, chave: str) -> Optional[str]:
        """Lê um valor da tabela de configurações."""
        rows = self._get(
            "traducao_configuracoes",
            {"select": "valor", "chave": f"eq.{chave}"},
        )
        if rows:
            return rows[0].get("valor")
        return None


def _get_supabase() -> Optional[SupabaseClient]:
    """Retorna um cliente Supabase configurado, ou None se não disponível."""
    key = SUPABASE_KEY
    if not key:
        # Tentar ler do arquivo de configuração local
        try:
            cfg_path = os.path.join(_PROJECT_DIR, ".env")
            if os.path.exists(cfg_path):
                with open(cfg_path) as f:
                    for line in f:
                        if line.startswith("SUPABASE_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"\'')
                            break
        except Exception:
            pass
    if not key:
        logger.warning("SUPABASE_KEY não configurada — usando fallback local (seen.json)")
        return None
    return SupabaseClient(SUPABASE_URL, key)


# ─────────────────────────────────────────────────────────────────
# Deduplicação (Supabase com fallback para arquivo local)
# ─────────────────────────────────────────────────────────────────

def _load_seen_local(path: str) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_seen_local(seen: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def filtrar_e_registrar_novas(
    vagas: List[Dict],
    sb: Optional[SupabaseClient],
) -> Tuple[List[Dict], bool]:
    """
    Filtra vagas novas e registra as novas no Supabase (ou arquivo local).
    Retorna (vagas_novas, usou_supabase).
    """
    if sb is not None:
        try:
            urls_vistas = sb.get_urls_vistas()
            novas = [v for v in vagas if v.get("link_vaga") and v["link_vaga"] not in urls_vistas]
            if novas:
                ok = sb.marcar_vistas(novas)
                if not ok:
                    logger.warning("Falha ao marcar vagas no Supabase — usando fallback local")
                    raise RuntimeError("marcar_vistas falhou")
            logger.info(f"Deduplicação via Supabase: {len(urls_vistas)} vistas, {len(novas)} novas")
            return novas, True
        except Exception as e:
            logger.warning(f"Supabase indisponível ({e}) — usando fallback local")

    # Fallback: arquivo local
    seen = _load_seen_local(SEEN_PATH)
    novas = [v for v in vagas if v.get("link_vaga") and v["link_vaga"] not in seen]
    seen_atualizado = {**seen, **{v["link_vaga"]: True for v in novas if v.get("link_vaga")}}
    _save_seen_local(seen_atualizado, SEEN_PATH)
    logger.info(f"Deduplicação via arquivo local: {len(seen)} vistas, {len(novas)} novas")
    return novas, False


# ─────────────────────────────────────────────────────────────────
# Envio via SMTP (Gmail App Password)
# ─────────────────────────────────────────────────────────────────

def _get_gmail_credentials() -> Tuple[str, str]:
    """
    Retorna (gmail_user, gmail_password).
    Prioridade: variáveis de ambiente > Supabase > erro.
    """
    user = GMAIL_USER
    password = GMAIL_APP_PASSWORD

    if not password:
        # Tentar ler do Supabase
        sb = _get_supabase()
        if sb:
            password = sb.get_config("gmail_app_password") or ""
            user = sb.get_config("gmail_user") or user

    if not password:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD não configurada. "
            "Defina a variável de ambiente ou armazene em traducao.configuracoes."
        )

    return user, password.replace(" ", "")


# Limite do Gmail para exibição inline sem truncamento
_GMAIL_INLINE_LIMIT_KB = 95  # margem de segurança abaixo dos 102 KB do Gmail


def _gerar_pdf_do_html(html: str, nome_arquivo: str = "vagas_traducao.pdf") -> Optional[bytes]:
    """
    Converte o HTML premium em PDF usando weasyprint.
    Retorna os bytes do PDF ou None em caso de erro.
    """
    try:
        from weasyprint import HTML as WeasyprintHTML
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name
        WeasyprintHTML(string=html).write_pdf(tmp_path)
        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()
        os.unlink(tmp_path)
        size_kb = len(pdf_bytes) // 1024
        logger.info(f"PDF gerado: {size_kb} KB ({nome_arquivo})")
        return pdf_bytes
    except Exception as exc:
        logger.error(f"Erro ao gerar PDF: {exc}")
        return None


def enviar_smtp(
    assunto: str,
    html: str,
    texto_simples: str = "",
) -> bool:
    """
    Envia o email via SMTP SSL (Gmail App Password).

    Estratégia de envio:
    - Se o HTML <= 95 KB: envia o HTML diretamente no corpo do email.
    - Se o HTML > 95 KB: gera um PDF com o conteúdo completo e envia como
      anexo, com corpo simples informando que o conteúdo está no PDF.
      Isso evita o truncamento do Gmail (limite de ~102 KB).
    """
    try:
        gmail_user, gmail_password = _get_gmail_credentials()
    except RuntimeError as e:
        logger.error(str(e))
        return False

    size_kb = len(html.encode("utf-8")) // 1024
    usar_pdf = size_kb > _GMAIL_INLINE_LIMIT_KB

    if usar_pdf:
        logger.info(
            f"HTML com {size_kb} KB > {_GMAIL_INLINE_LIMIT_KB} KB — "
            f"convertendo para PDF para evitar truncamento do Gmail"
        )
        pdf_bytes = _gerar_pdf_do_html(html)
        if pdf_bytes is None:
            logger.warning("Falha ao gerar PDF — enviando HTML mesmo assim")
            usar_pdf = False

    if usar_pdf:
        # Email com PDF anexado e corpo simples
        msg = MIMEMultipart("mixed")
        msg["Subject"] = assunto
        msg["From"] = f"Sistema de Alertas de Tradução <{gmail_user}>"
        msg["To"] = GMAIL_RECIPIENT

        n_vagas = assunto.split("]")[1].strip().split(" ")[0] if "]" in assunto else "?"
        corpo_html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#222;padding:24px;">
        <h2 style="color:#1a3a5c;">Alerta Diário de Vagas de Tradução</h2>
        <p>Foram encontradas <strong>{n_vagas} nova(s) vaga(s)</strong> hoje.</p>
        <p>O conteúdo completo está no arquivo PDF em anexo
        (<em>vagas_traducao.pdf</em>).</p>
        <p style="color:#888;font-size:12px;">O PDF foi gerado automaticamente porque
        o volume de vagas de hoje excede o limite de exibição inline do Gmail
        ({_GMAIL_INLINE_LIMIT_KB} KB). Abra o anexo para ver todas as vagas com
        design premium completo.</p>
        </body></html>
        """
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        # Anexar o PDF
        from datetime import date as _date
        nome_pdf = f"vagas_traducao_{_date.today().strftime('%Y-%m-%d')}.pdf"
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{nome_pdf}"')
        msg.attach(part)

        logger.info(f"Enviando email com PDF anexado ({len(pdf_bytes)//1024} KB)...")
    else:
        # Email com HTML inline (comportamento padrão)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"Sistema de Alertas de Tradução <{gmail_user}>"
        msg["To"] = GMAIL_RECIPIENT

        if not texto_simples:
            texto_simples = f"Alerta de vagas de tradução — {assunto}"
        msg.attach(MIMEText(texto_simples, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        inicio = time.time()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, GMAIL_RECIPIENT, msg.as_string())
        duracao = time.time() - inicio
        if usar_pdf:
            logger.info(f"Email com PDF enviado via SMTP em {duracao:.1f}s")
        else:
            logger.info(f"Email enviado via SMTP em {duracao:.1f}s — HTML: {size_kb} KB")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Falha de autenticação SMTP. Verifique o App Password do Gmail. "
            "Gere um novo em: https://myaccount.google.com/apppasswords"
        )
        return False
    except smtplib.SMTPException as e:
        logger.error(f"Erro SMTP: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao enviar email: {e}")
        return False


# ─────────────────────────────────────────────────────────────────
# Geração do texto simples (fallback para clientes sem HTML)
# ─────────────────────────────────────────────────────────────────

def gerar_texto_simples(vagas: List[Dict], erros: List[str], date_str: str) -> str:
    """Gera o corpo em texto simples com resumo das vagas."""
    por_fonte = Counter(v.get("fonte", "") for v in vagas)
    n_contato = sum(
        1 for v in vagas
        if v.get("contato_descoberto", {}).get("email")
        or v.get("contato_descoberto", {}).get("site")
    )

    linhas = [
        f"Alerta Diário de Vagas de Tradução — {date_str}",
        "=" * 50,
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
        "",
        "Este email contém o design premium completo em HTML.",
        "Se estiver vendo este texto, seu cliente de email não suporta HTML.",
        "",
    ]

    for i, v in enumerate(vagas, 1):
        linhas += [
            f"[{i}] {v.get('titulo', 'Sem título')}",
            f"    Fonte: {v.get('fonte', '')}",
            f"    Idiomas: {v.get('par_idiomas', '')}",
            f"    Empresa: {v.get('empresa', '')}",
            f"    Link: {v.get('link_vaga', '')}",
            "",
        ]

    if erros:
        linhas += ["Avisos do sistema:"]
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

    inicio_total = time.time()
    hoje = date.today()
    date_str = hoje.strftime("%d/%m/%Y")
    logger.info(f"Alerta de vagas de tradução — {hoje.isoformat()}")

    # Importar módulos
    try:
        from monitor_traducao import buscar_vagas
        from email_template import gerar_html_email
    except ImportError as e:
        logger.error(f"Erro ao importar módulos: {e}")
        return 1

    # Conectar ao Supabase
    sb = _get_supabase()
    if sb:
        logger.info("Supabase conectado — deduplicação via banco de dados")
    else:
        logger.info("Supabase indisponível — deduplicação via arquivo local")

    # Buscar vagas
    logger.info("Buscando vagas de tradução (PT/EN/ES)...")
    vagas, erros = buscar_vagas()
    logger.info(f"Vagas encontradas: {len(vagas)}")
    if erros:
        for err in erros:
            logger.warning(f"Aviso: {err}")

    # Filtrar novas e registrar no Supabase
    novas, usou_supabase = filtrar_e_registrar_novas(vagas, sb)
    logger.info(f"Vagas novas (não alertadas antes): {len(novas)}")

    por_fonte = Counter(v.get("fonte", "") for v in novas)

    if not novas:
        logger.info("Nenhuma vaga nova — email não enviado")
        if sb:
            sb.registrar_execucao({
                "vagas_novas": 0,
                "vagas_proz": 0,
                "vagas_tc": 0,
                "vagas_td": 0,
                "contatos_descobertos": 0,
                "email_enviado": False,
                "duracao_segundos": round(time.time() - inicio_total, 1),
            })
        return 0

    # Gerar HTML premium completo
    logger.info("Gerando HTML premium...")
    html = gerar_html_email(novas, erros)
    size_kb = len(html.encode("utf-8")) // 1024
    logger.info(f"HTML gerado: {size_kb} KB")

    # Gerar texto simples (fallback)
    texto_simples = gerar_texto_simples(novas, erros, date_str)

    # Montar assunto
    assunto = f"[Tradução] {len(novas)} nova(s) vaga(s) — {date_str}"

    # Enviar via SMTP (HTML completo, sem limite de tamanho)
    logger.info(f"Enviando email via SMTP para {GMAIL_RECIPIENT}...")
    enviado = enviar_smtp(assunto, html, texto_simples)

    duracao = round(time.time() - inicio_total, 1)
    n_contato = sum(
        1 for v in novas
        if v.get("contato_descoberto", {}).get("email")
        or v.get("contato_descoberto", {}).get("site")
    )

    if enviado:
        logger.info(f"Alerta enviado com sucesso em {duracao}s!")
    else:
        logger.error("Falha no envio do alerta")

    # ── Auditoria pós-envio com autocorreção automática ───────────
    try:
        from auditoria import executar_auditoria_completa
        resultado_auditoria = executar_auditoria_completa(
            vagas_originais=novas,
            erros_originais=erros,
            html_original=html,
            email_enviado=enviado,
            assunto=assunto,
            texto_simples=texto_simples,
            enviar_smtp_fn=enviar_smtp,
            sb=sb,
        )
        novas = resultado_auditoria["vagas_finais"]
        erros = resultado_auditoria["erros_finais"]
        html = resultado_auditoria["html_final"]
        enviado = resultado_auditoria["email_enviado"]
    except ImportError:
        logger.warning("Módulo de auditoria não encontrado — pulando auditoria")
    except Exception as exc:
        logger.error(f"Erro na auditoria pós-envio: {exc}")

    # Registrar execução no Supabase
    por_fonte_final = Counter(v.get("fonte", "") for v in novas)
    n_contato_final = sum(
        1 for v in novas
        if v.get("contato_descoberto", {}).get("email")
        or v.get("contato_descoberto", {}).get("site")
    )
    if sb:
        sb.registrar_execucao({
            "vagas_novas": len(novas),
            "vagas_proz": por_fonte_final.get("ProZ.com", 0),
            "vagas_tc": por_fonte_final.get("Translators Café", 0),
            "vagas_td": por_fonte_final.get("Translation Directory", 0),
            "contatos_descobertos": n_contato_final,
            "email_enviado": enviado,
            "erro": "\n".join(erros) if erros else None,
            "duracao_segundos": round(time.time() - inicio_total, 1),
        })

    return 0 if enviado else 1


if __name__ == "__main__":
    sys.exit(main())
