#!/usr/bin/env python3
"""
Módulo de auditoria pós-envio do sistema de alertas de tradução.

Responsabilidades:
  1. Auditar o resultado de cada execução (vagas coletadas, contatos, envio)
  2. Detectar erros, bloqueios e inconsistências automaticamente
  3. Implementar correções automáticas sem intervenção do usuário
  4. Reenviar o email corrigido quando necessário
  5. Registrar todas as ações de auditoria no Supabase

Critérios de auditoria:
  - Fontes com 0 vagas TOTAIS coletadas quando deveriam ter (erro real de scraping)
  - Erros de bloqueio 403 / IP bloqueado
  - Erros de encoding / parsing
  - Email não enviado (falha SMTP)
  - HTML gerado com tamanho anômalo (< 5 KB ou > 600 KB)

IMPORTANTE: A auditoria usa `vagas_totais` (antes da deduplicação) para detectar
erros reais de coleta, e `vagas_novas` (após deduplicação) para o reenvio.
Vagas recuperadas pelo fallback Selenium SEMPRE passam pelo filtro de deduplicação
antes de serem incluídas no reenvio — isso evita reenviar vagas já alertadas.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("auditoria")

# ─────────────────────────────────────────────────────────────────
# Limiares de auditoria
# ─────────────────────────────────────────────────────────────────

LIMIAR_HTML_MIN_KB = 5
LIMIAR_HTML_MAX_KB = 600
MAX_TENTATIVAS_SMTP = 3
BACKOFF_SMTP_SEGUNDOS = 30


# ─────────────────────────────────────────────────────────────────
# Auditoria de vagas coletadas
# ─────────────────────────────────────────────────────────────────

def auditar_coleta(
    vagas_totais: List[Dict],
    vagas_novas: List[Dict],
    erros: List[str],
    sb=None,
) -> Tuple[List[Dict], List[str], List[str]]:
    """
    Audita as vagas coletadas e tenta corrigir problemas automaticamente.

    Parâmetros:
      vagas_totais: todas as vagas coletadas (antes da deduplicação)
      vagas_novas:  vagas novas (após deduplicação, já enviadas no email)
      erros:        lista de erros da coleta
      sb:           cliente Supabase para deduplicação das vagas recuperadas

    Retorna (vagas_novas_corrigidas, erros_corrigidos, acoes_tomadas).
    As vagas retornadas já passaram pelo filtro de deduplicação.
    """
    acoes: List[str] = []

    # Usar vagas_totais para detectar erros reais de coleta (0 vagas coletadas)
    por_fonte_total = Counter(v.get("fonte", "") for v in vagas_totais)

    # ── ProZ.com: 0 vagas TOTAIS coletadas → tentar Selenium ─────
    n_proz_total = por_fonte_total.get("ProZ.com", 0)
    if n_proz_total == 0:
        logger.info("Auditoria: ProZ.com retornou 0 vagas totais — tentando Selenium como fallback...")
        try:
            from selenium_scrapers import scrape_proz_selenium
            from monitor_traducao import (
                _extrair_par_idiomas_titulo, _par_relevante, _extrair_area,
                _extrair_contagem_palavras, _extrair_formato, _extrair_preco,
                _extrair_empresa, _formatar_data, buscar_contato_empresa,
            )
            vagas_sel, erros_sel = scrape_proz_selenium(
                _extrair_par_idiomas_titulo, _par_relevante, _extrair_area,
                _extrair_contagem_palavras, _extrair_formato, _extrair_preco,
                _extrair_empresa, _formatar_data, buscar_contato_empresa,
            )
            if vagas_sel:
                # Deduplicar: só incluir vagas que ainda não foram alertadas
                vagas_sel_novas = _deduplicar(vagas_sel, sb)
                if vagas_sel_novas:
                    vagas_novas = vagas_novas + vagas_sel_novas
                    erros = [e for e in erros if "proz" not in e.lower()] + erros_sel
                    acoes.append(f"ProZ.com: Selenium recuperou {len(vagas_sel)} total, {len(vagas_sel_novas)} nova(s) após deduplicação")
                    logger.info(f"Auditoria: ProZ.com Selenium → {len(vagas_sel_novas)} nova(s)")
                else:
                    acoes.append(f"ProZ.com: Selenium recuperou {len(vagas_sel)} vaga(s), mas todas já foram alertadas antes")
                    logger.info("Auditoria: ProZ.com Selenium → 0 novas após deduplicação")
            else:
                acoes.append(f"ProZ.com: Selenium também retornou 0 vagas ({'; '.join(erros_sel) if erros_sel else 'sem erro específico'})")
                logger.warning("Auditoria: ProZ.com Selenium também retornou 0 vagas")
        except ImportError:
            acoes.append("ProZ.com: Selenium não disponível neste ambiente")
        except Exception as exc:
            acoes.append(f"ProZ.com: erro no fallback Selenium — {exc}")
            logger.error(f"Auditoria ProZ Selenium: {exc}")

    # ── Translators Café: IP de datacenter bloqueado — sem retry ─
    n_tc_total = por_fonte_total.get("Translators Café", 0)
    erros_tc = [e for e in erros if "translators" in e.lower() or "café" in e.lower()]
    tem_bloqueio_tc = any("403" in e or "bloqueado" in e.lower() for e in erros_tc)
    if n_tc_total == 0 and tem_bloqueio_tc:
        logger.info("Auditoria: TC bloqueado por IP de datacenter — retry não será tentado (comportamento esperado)")

    # ── Translation Directory: 0 vagas TOTAIS → retry imediato ──
    n_td_total = por_fonte_total.get("Translation Directory", 0)
    if n_td_total == 0:
        logger.info("Auditoria: Translation Directory retornou 0 vagas totais — tentando novamente...")
        try:
            from monitor_traducao import _scrape_translation_directory
            vagas_td_retry, erros_td_retry = _scrape_translation_directory()
            if vagas_td_retry:
                # Deduplicar: só incluir vagas que ainda não foram alertadas
                vagas_td_novas = _deduplicar(vagas_td_retry, sb)
                if vagas_td_novas:
                    vagas_novas = [v for v in vagas_novas if v.get("fonte") != "Translation Directory"] + vagas_td_novas
                    erros = [e for e in erros if "translation directory" not in e.lower()] + erros_td_retry
                    acoes.append(f"Translation Directory: retry recuperou {len(vagas_td_retry)} total, {len(vagas_td_novas)} nova(s) após deduplicação")
                    logger.info(f"Auditoria: TD retry → {len(vagas_td_novas)} nova(s)")
                else:
                    acoes.append(f"Translation Directory: retry recuperou {len(vagas_td_retry)} vaga(s), mas todas já foram alertadas antes")
            else:
                acoes.append("Translation Directory: retry também retornou 0 vagas")
        except Exception as exc:
            acoes.append(f"Translation Directory: erro no retry — {exc}")

    return vagas_novas, erros, acoes


def _deduplicar(vagas: List[Dict], sb=None) -> List[Dict]:
    """
    Filtra vagas já alertadas anteriormente.
    Usa Supabase se disponível, senão arquivo local.
    NÃO marca as vagas como vistas (isso é feito apenas no fluxo principal).
    """
    if sb is not None:
        try:
            urls_vistas = sb.get_urls_vistas()
            return [v for v in vagas if v.get("link_vaga") and v["link_vaga"] not in urls_vistas]
        except Exception:
            pass

    # Fallback: arquivo local
    try:
        import json, os
        seen_path = os.path.join(os.path.dirname(__file__), "..", "data", "traducao_seen.json")
        seen_path = os.path.normpath(seen_path)
        if os.path.exists(seen_path):
            with open(seen_path, "r", encoding="utf-8") as f:
                seen = json.load(f)
            return [v for v in vagas if v.get("link_vaga") and v["link_vaga"] not in seen]
    except Exception:
        pass

    # Se não conseguiu verificar, retornar vazio (conservador: não reenviar)
    logger.warning("Auditoria: não foi possível verificar deduplicação — vagas recuperadas descartadas por segurança")
    return []


# ─────────────────────────────────────────────────────────────────
# Auditoria do HTML gerado
# ─────────────────────────────────────────────────────────────────

def auditar_html(html: str, vagas: List[Dict], erros: List[str]) -> Tuple[str, List[str]]:
    """
    Audita o HTML gerado e corrige problemas de tamanho ou conteúdo.
    Retorna (html_corrigido, acoes_tomadas).
    """
    acoes: List[str] = []
    size_kb = len(html.encode("utf-8")) // 1024

    if size_kb < LIMIAR_HTML_MIN_KB:
        logger.warning(f"Auditoria: HTML muito pequeno ({size_kb} KB) — regenerando...")
        try:
            from email_template import gerar_html_email
            html = gerar_html_email(vagas, erros)
            novo_kb = len(html.encode("utf-8")) // 1024
            acoes.append(f"HTML regenerado: {size_kb} KB → {novo_kb} KB")
        except Exception as exc:
            acoes.append(f"Falha ao regenerar HTML: {exc}")

    elif size_kb > LIMIAR_HTML_MAX_KB:
        logger.warning(f"Auditoria: HTML muito grande ({size_kb} KB) — comprimindo...")
        # Priorizar vagas com contato descoberto
        vagas_com_contato = [
            v for v in vagas
            if v.get("contato_descoberto", {}).get("email")
            or v.get("contato_descoberto", {}).get("site")
            or v.get("tipo_contato") == "email"
        ]
        vagas_sem_contato = [v for v in vagas if v not in vagas_com_contato]

        # Reduzir progressivamente até caber
        vagas_reduzidas = vagas_com_contato[:]
        for v in vagas_sem_contato:
            vagas_reduzidas.append(v)
            try:
                from email_template import gerar_html_email
                html_teste = gerar_html_email(vagas_reduzidas, erros)
                if len(html_teste.encode("utf-8")) // 1024 <= LIMIAR_HTML_MAX_KB:
                    continue
                else:
                    vagas_reduzidas.pop()
                    break
            except Exception:
                break

        try:
            from email_template import gerar_html_email
            html = gerar_html_email(vagas_reduzidas, erros)
            novo_kb = len(html.encode("utf-8")) // 1024
            acoes.append(
                f"HTML comprimido: {size_kb} KB → {novo_kb} KB "
                f"({len(vagas_reduzidas)}/{len(vagas)} vagas mantidas)"
            )
        except Exception as exc:
            acoes.append(f"Falha ao comprimir HTML: {exc}")

    return html, acoes


# ─────────────────────────────────────────────────────────────────
# Auditoria do envio SMTP
# ─────────────────────────────────────────────────────────────────

def auditar_envio(
    assunto: str,
    html: str,
    texto_simples: str,
    enviar_smtp_fn,
    tentativas_anteriores: int = 0,
) -> Tuple[bool, List[str]]:
    """
    Tenta reenviar o email com retry automático em caso de falha SMTP.
    Retorna (enviado, acoes_tomadas).
    """
    acoes: List[str] = []

    if tentativas_anteriores >= MAX_TENTATIVAS_SMTP:
        acoes.append(f"SMTP: máximo de {MAX_TENTATIVAS_SMTP} tentativas atingido — desistindo")
        return False, acoes

    tentativas_restantes = MAX_TENTATIVAS_SMTP - tentativas_anteriores
    for tentativa in range(1, tentativas_restantes + 1):
        if tentativa > 1:
            logger.info(f"Auditoria SMTP: aguardando {BACKOFF_SMTP_SEGUNDOS}s antes da tentativa {tentativa}...")
            time.sleep(BACKOFF_SMTP_SEGUNDOS)

        logger.info(f"Auditoria SMTP: tentativa {tentativa}/{tentativas_restantes}...")
        ok = enviar_smtp_fn(assunto, html, texto_simples)
        if ok:
            acoes.append(f"SMTP: email enviado na tentativa {tentativa}")
            return True, acoes
        else:
            acoes.append(f"SMTP: falha na tentativa {tentativa}")

    return False, acoes


# ─────────────────────────────────────────────────────────────────
# Auditoria completa (orquestrador)
# ─────────────────────────────────────────────────────────────────

def executar_auditoria_completa(
    vagas_originais: List[Dict],
    erros_originais: List[str],
    html_original: str,
    email_enviado: bool,
    assunto: str,
    texto_simples: str,
    enviar_smtp_fn,
    sb=None,
    vagas_para_smtp=None,
    vagas_totais: Optional[List[Dict]] = None,
) -> Dict:
    """
    Executa a auditoria completa pós-envio e corrige problemas automaticamente.

    Parâmetros:
      vagas_originais: vagas novas já enviadas no email (após deduplicação)
      vagas_totais:    todas as vagas coletadas (antes da deduplicação) —
                       usado para detectar erros reais de coleta

    Retorna dict com:
      - vagas_finais: lista de vagas após correções
      - erros_finais: lista de erros após correções
      - html_final: HTML final enviado
      - email_enviado: bool
      - acoes: lista de todas as ações tomadas
      - reenvio_necessario: bool
    """
    resultado = {
        "vagas_finais": vagas_originais,
        "erros_finais": erros_originais,
        "html_final": html_original,
        "email_enviado": email_enviado,
        "acoes": [],
        "reenvio_necessario": False,
    }

    todas_acoes: List[str] = []
    logger.info("=== AUDITORIA PÓS-ENVIO INICIADA ===")

    # Usar vagas_totais para detectar erros reais; fallback para vagas_originais
    _vagas_totais = vagas_totais if vagas_totais is not None else vagas_originais

    # ── 1. Auditar coleta de vagas ────────────────────────────────
    vagas_corrigidas, erros_corrigidos, acoes_coleta = auditar_coleta(
        vagas_totais=_vagas_totais,
        vagas_novas=vagas_originais,
        erros=erros_originais,
        sb=sb,
    )
    todas_acoes.extend(acoes_coleta)

    novas_vagas_encontradas = len(vagas_corrigidas) > len(vagas_originais)
    if novas_vagas_encontradas:
        logger.info(
            f"Auditoria: {len(vagas_corrigidas) - len(vagas_originais)} vaga(s) adicionais recuperadas (já deduplicadas)"
        )
        resultado["reenvio_necessario"] = True
        resultado["vagas_finais"] = vagas_corrigidas
        resultado["erros_finais"] = erros_corrigidos

    # ── 2. Auditar HTML ───────────────────────────────────────────
    html_para_auditar = html_original
    if novas_vagas_encontradas:
        # Regenerar HTML com as vagas corrigidas
        try:
            from email_template import gerar_html_email
            html_para_auditar = gerar_html_email(vagas_corrigidas, erros_corrigidos)
            kb_novo = len(html_para_auditar.encode("utf-8")) // 1024
            todas_acoes.append(f"HTML regenerado com vagas corrigidas: {kb_novo} KB")
        except Exception as exc:
            todas_acoes.append(f"Falha ao regenerar HTML: {exc}")
            html_para_auditar = html_original

    html_auditado, acoes_html = auditar_html(html_para_auditar, vagas_corrigidas, erros_corrigidos)
    todas_acoes.extend(acoes_html)
    resultado["html_final"] = html_auditado

    # ── 3. Auditar envio SMTP ─────────────────────────────────────
    if not email_enviado:
        logger.info("Auditoria: email não foi enviado — tentando reenvio...")
        _vagas_reenvio = vagas_para_smtp or vagas_corrigidas
        ok_reenvio, acoes_smtp = auditar_envio(
            assunto, html_auditado, texto_simples,
            lambda a, h, t: enviar_smtp_fn(a, h, t, vagas=_vagas_reenvio)
        )
        todas_acoes.extend(acoes_smtp)
        resultado["email_enviado"] = ok_reenvio
        if ok_reenvio:
            logger.info("Auditoria: reenvio bem-sucedido!")
        else:
            logger.error("Auditoria: reenvio falhou após todas as tentativas")

    elif resultado["reenvio_necessario"]:
        # Reenviar com vagas adicionais (já deduplicadas)
        logger.info("Auditoria: reenviando email com vagas adicionais recuperadas...")
        n_adicionais = len(vagas_corrigidas) - len(vagas_originais)
        n_exibidas_originais = len(vagas_originais)
        n_exibidas_total = len(vagas_corrigidas)
        assunto_reenvio = assunto.replace(
            f"{n_exibidas_originais} nova(s)",
            f"{n_exibidas_total} nova(s) [+{n_adicionais} recuperada(s)]"
        )
        _vagas_reenvio2 = vagas_para_smtp or vagas_corrigidas
        ok_reenvio, acoes_smtp = auditar_envio(
            assunto_reenvio, html_auditado, texto_simples,
            lambda a, h, t: enviar_smtp_fn(a, h, t, vagas=_vagas_reenvio2)
        )
        todas_acoes.extend(acoes_smtp)
        resultado["email_enviado"] = ok_reenvio
        if ok_reenvio:
            logger.info("Auditoria: reenvio com vagas adicionais bem-sucedido!")
        else:
            logger.error("Auditoria: reenvio com vagas adicionais falhou")

    # ── 4. Registrar auditoria no Supabase ────────────────────────
    if todas_acoes:
        logger.info(f"Auditoria: {len(todas_acoes)} ação(ões) tomada(s):")
        for acao in todas_acoes:
            logger.info(f"  → {acao}")

        if sb:
            try:
                sb.registrar_execucao({
                    "tipo": "auditoria",
                    "acoes": "\n".join(todas_acoes),
                    "vagas_originais": len(vagas_originais),
                    "vagas_finais": len(vagas_corrigidas),
                    "email_enviado": resultado["email_enviado"],
                    "reenvio": resultado["reenvio_necessario"],
                })
            except Exception as exc:
                logger.debug(f"Falha ao registrar auditoria no Supabase: {exc}")
    else:
        logger.info("Auditoria: nenhum problema detectado — sistema operando normalmente")

    resultado["acoes"] = todas_acoes
    logger.info("=== AUDITORIA PÓS-ENVIO CONCLUÍDA ===")
    return resultado
