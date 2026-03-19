#!/usr/bin/env python3
"""
Template HTML premium para newsletter de vagas de tradução.

Design: fundo branco, CSS 100% inline (resistente ao truncamento do Gmail),
layout limpo e legível, separadores visuais por fonte, agrupamento por empresa.

Regras de negócio:
  - Vagas do Translation Directory SEM contato descoberto são OMITIDAS.
  - Vagas agrupadas por empresa/anunciante dentro de cada fonte.
  - Dentro de cada fonte, empresas em ordem alfabética.
  - Separadores visuais claros entre fontes.

Campos esperados por vaga (do monitor_traducao.py):
  titulo, idioma_origem, idioma_destino, par_display,
  area, contagem_palavras, formato, preco_palavra, pais,
  prazo, data_publicacao, tipo_contato, link_contato,
  link_vaga, fonte, detalhes, contato_pessoa, empresa,
  contato_descoberto (dict: site, email, fonte_busca)
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional


# ─── Paleta por fonte ────────────────────────────────────────────────────────
FONTE_ESTILOS = {
    "ProZ.com": {
        "accent":     "#1a73e8",
        "badge_bg":   "#e8f0fe",
        "badge_txt":  "#1a73e8",
        "header_bg":  "#e8f0fe",
        "border":     "#1a73e8",
        "label":      "ProZ.com",
    },
    "Translators Café": {
        "accent":     "#0f9d58",
        "badge_bg":   "#e6f4ea",
        "badge_txt":  "#0f9d58",
        "header_bg":  "#e6f4ea",
        "border":     "#0f9d58",
        "label":      "Translators Café",
    },
    "Translation Directory": {
        "accent":     "#7b1fa2",
        "badge_bg":   "#f3e5f5",
        "badge_txt":  "#7b1fa2",
        "header_bg":  "#f3e5f5",
        "border":     "#7b1fa2",
        "label":      "Translation Directory",
    },
}

_DEFAULT_ESTILO = {
    "accent":     "#546e7a",
    "badge_bg":   "#eceff1",
    "badge_txt":  "#546e7a",
    "header_bg":  "#eceff1",
    "border":     "#546e7a",
    "label":      "Outros",
}

PAR_CORES = {
    "EN → PT": "#1a73e8",
    "PT → EN": "#1a73e8",
    "PT → ES": "#e65100",
    "ES → PT": "#e65100",
    "EN → ES": "#7b1fa2",
    "ES → EN": "#7b1fa2",
}


def _estilo(fonte: str) -> dict:
    return FONTE_ESTILOS.get(fonte, _DEFAULT_ESTILO)


def _cor_par(par: str) -> str:
    for k, v in PAR_CORES.items():
        if k.replace(" ", "").lower() in par.replace(" ", "").lower():
            return v
    return "#546e7a"


def _tem_contato(v: Dict) -> bool:
    """Verifica se a vaga tem algum contato descoberto (email ou site)."""
    cd = v.get("contato_descoberto", {})
    if not cd:
        return False
    if cd.get("aviso"):
        return False
    return bool(cd.get("email") or cd.get("site"))


def _nome_empresa(v: Dict) -> str:
    """Retorna o nome da empresa/anunciante para agrupamento e ordenação."""
    empresa = v.get("empresa", "").strip()
    if empresa and empresa.lower() not in ("", "-", "n/a", "we are"):
        return empresa
    # Tenta extrair do título
    titulo = v.get("titulo", "").strip()
    if titulo:
        return titulo[:60]
    return "Sem identificação"


def _filtrar_vagas_td(vagas: List[Dict]) -> List[Dict]:
    """Remove vagas do Translation Directory sem contato descoberto."""
    resultado = []
    for v in vagas:
        if v.get("fonte") == "Translation Directory":
            if _tem_contato(v):
                resultado.append(v)
            # else: omite silenciosamente
        else:
            resultado.append(v)
    return resultado


def _agrupar_por_empresa(vagas: List[Dict]) -> Dict[str, List[Dict]]:
    """Agrupa vagas por empresa, retornando dict ordenado alfabeticamente."""
    grupos: Dict[str, List[Dict]] = defaultdict(list)
    for v in vagas:
        key = _nome_empresa(v)
        grupos[key].append(v)
    # Ordena alfabeticamente (case-insensitive)
    return dict(sorted(grupos.items(), key=lambda x: x[0].lower()))


# ─── Estilos inline base ─────────────────────────────────────────────────────
# Todos os estilos são inline para garantir compatibilidade com Gmail
# mesmo quando o email é truncado e o <style> do <head> é perdido.

_FONT = "font-family:Arial,Helvetica,sans-serif;"
_RESET = "margin:0;padding:0;border:0;"


def _s(**kwargs) -> str:
    """Monta string de style inline a partir de kwargs."""
    return ";".join(f"{k.replace('_', '-')}:{v}" for k, v in kwargs.items()) + ";"


def _campo_row(label: str, valor: str, cor_val: str = "#333333") -> str:
    """Linha de campo label: valor."""
    if not valor or str(valor).strip() in ("", "-", "N/A"):
        return ""
    return (
        f'<tr>'
        f'<td style="{_FONT}font-size:12px;color:#888888;padding:3px 12px 3px 0;'
        f'white-space:nowrap;vertical-align:top;">{label}</td>'
        f'<td style="{_FONT}font-size:13px;color:{cor_val};padding:3px 0;'
        f'vertical-align:top;">{valor}</td>'
        f'</tr>'
    )


def _bloco_contato(cd: Dict, accent: str) -> str:
    """Gera bloco de contato descoberto (somente quando há email ou site)."""
    if not cd or cd.get("aviso") or not (cd.get("email") or cd.get("site")):
        return ""
    fonte_busca = cd.get("fonte_busca", "busca reversa")
    linhas = []
    if cd.get("email"):
        linhas.append(
            f'<a href="mailto:{cd["email"]}" style="{_FONT}color:{accent};'
            f'font-size:12px;text-decoration:none;">&#9993;&nbsp;{cd["email"]}</a>'
        )
    if cd.get("site"):
        site = cd["site"]
        site_txt = site[:70] + ("..." if len(site) > 70 else "")
        linhas.append(
            f'<a href="{site}" style="{_FONT}color:{accent};'
            f'font-size:12px;text-decoration:none;">&#127760;&nbsp;{site_txt}</a>'
        )
    conteudo = "<br>".join(linhas)
    return (
        f'<div style="margin-top:8px;padding:8px 12px;background:#f0faf4;'
        f'border-left:3px solid {accent};border-radius:0 4px 4px 0;">'
        f'<div style="{_FONT}font-size:10px;font-weight:bold;color:{accent};'
        f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">'
        f'Contato descoberto <span style="font-weight:normal;color:#666;">'
        f'(via {fonte_busca})</span></div>'
        f'{conteudo}</div>'
    )


def _card_vaga(v: Dict, accent: str) -> str:
    """Gera HTML de um card de vaga individual."""
    titulo = v.get("titulo", "Sem título")
    par = v.get("par_display", v.get("idioma_origem", "") + " → " + v.get("idioma_destino", ""))
    cor_par = _cor_par(par)
    link_vaga = v.get("link_vaga", "#")
    cd = v.get("contato_descoberto", {})
    tipo_contato = v.get("tipo_contato", "")
    link_contato = v.get("link_contato", "")

    # Badge par de idiomas
    badge_par = (
        f'<span style="{_FONT}display:inline-block;padding:2px 10px;'
        f'background:{cor_par}18;color:{cor_par};border:1px solid {cor_par}44;'
        f'border-radius:10px;font-size:12px;font-weight:bold;">{par}</span>'
    )

    # Campos
    campos = ""
    campos += _campo_row("Par de idiomas", badge_par, cor_val="#333")
    campos += _campo_row("Área / Tipo", v.get("area", ""))
    if v.get("contagem_palavras"):
        campos += _campo_row("Palavras", v.get("contagem_palavras", ""))
    if v.get("formato"):
        campos += _campo_row("Formato", v.get("formato", ""))
    if v.get("preco_palavra"):
        campos += _campo_row("Preço / palavra", v.get("preco_palavra", ""), cor_val="#1a6b2e")
    if v.get("pais"):
        campos += _campo_row("País", v.get("pais", ""))
    if v.get("prazo"):
        campos += _campo_row("Prazo", v.get("prazo", ""), cor_val="#c62828")
    if v.get("data_publicacao"):
        campos += _campo_row("Publicado em", v.get("data_publicacao", ""))

    # Descrição (limitada a 400 chars para controle de tamanho)
    desc_html = ""
    det = v.get("detalhes", "")
    if det:
        det_esc = det.replace("<", "&lt;").replace(">", "&gt;")
        if len(det_esc) > 400:
            det_esc = det_esc[:400] + "…"
        desc_html = (
            f'<div style="margin-top:8px;padding:8px 12px;background:#f8f9fa;'
            f'border-left:3px solid #dee2e6;border-radius:0 4px 4px 0;">'
            f'<div style="{_FONT}font-size:10px;font-weight:bold;color:#888;'
            f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">Descrição</div>'
            f'<div style="{_FONT}font-size:12px;color:#555;line-height:1.6;">{det_esc}</div>'
            f'</div>'
        )

    # Bloco contato descoberto
    contato_html = _bloco_contato(cd, accent)

    # Botão de ação
    btn_url = link_vaga
    btn_label = "Ver vaga &#8594;"
    if tipo_contato == "email" and link_contato and "@" in link_contato:
        btn_url = f"mailto:{link_contato}?subject=Candidatura%20-%20{titulo[:40].replace(' ', '%20')}"
        btn_label = "Enviar candidatura &#8594;"
    elif cd.get("email"):
        btn_url = f"mailto:{cd['email']}?subject=Candidatura%20-%20{titulo[:40].replace(' ', '%20')}"
        btn_label = "Contato direto &#8594;"
    elif tipo_contato == "URL" and link_contato and link_contato != link_vaga:
        btn_url = link_contato
        btn_label = "Acessar formulário &#8594;"

    return (
        f'<div style="margin-bottom:10px;padding:12px 14px;background:#ffffff;'
        f'border:1px solid #e0e0e0;border-radius:6px;">'
        f'<a href="{link_vaga}" style="{_FONT}font-size:13px;font-weight:bold;'
        f'color:{accent};text-decoration:none;line-height:1.4;">{titulo}</a>'
        f'<table cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;width:100%;">'
        f'{campos}'
        f'</table>'
        f'{desc_html}'
        f'{contato_html}'
        f'<div style="margin-top:10px;">'
        f'<a href="{btn_url}" style="{_FONT}display:inline-block;padding:6px 16px;'
        f'background:{accent};color:#ffffff;font-size:12px;font-weight:bold;'
        f'text-decoration:none;border-radius:4px;">{btn_label}</a>'
        f'</div>'
        f'</div>'
    )


def _secao_empresa(nome: str, vagas: List[Dict], accent: str) -> str:
    """Gera bloco de uma empresa com todas as suas vagas."""
    cards = "".join(_card_vaga(v, accent) for v in vagas)
    n = len(vagas)
    plural = "vagas" if n != 1 else "vaga"
    return (
        f'<div style="margin-bottom:16px;">'
        f'<div style="padding:8px 12px;background:#f5f5f5;border-radius:4px 4px 0 0;'
        f'border-left:4px solid {accent};margin-bottom:4px;">'
        f'<span style="{_FONT}font-size:13px;font-weight:bold;color:#333;">{nome}</span>'
        f'<span style="{_FONT}font-size:11px;color:#888;margin-left:8px;">'
        f'{n}&nbsp;{plural}</span>'
        f'</div>'
        f'{cards}'
        f'</div>'
    )


def _secao_fonte(fonte: str, vagas: List[Dict]) -> str:
    """Gera seção completa de uma fonte com agrupamento por empresa."""
    if not vagas:
        return ""
    e = _estilo(fonte)
    accent = e["accent"]
    grupos = _agrupar_por_empresa(vagas)
    n_total = len(vagas)
    n_empresas = len(grupos)

    blocos = "".join(
        _secao_empresa(nome, lst, accent)
        for nome, lst in grupos.items()
    )

    plural_v = "vagas" if n_total != 1 else "vaga"
    plural_e = "anunciantes" if n_empresas != 1 else "anunciante"

    return (
        # Separador visual de fonte
        f'<div style="margin:28px 0 16px 0;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr>'
        f'<td style="border-top:2px solid {accent};padding-top:0;"></td>'
        f'</tr>'
        f'</table>'
        f'<div style="margin-top:10px;padding:10px 16px;background:{e["header_bg"]};'
        f'border-radius:6px;border-left:5px solid {accent};">'
        f'<span style="{_FONT}font-size:16px;font-weight:bold;color:{accent};">{fonte}</span>'
        f'<span style="{_FONT}font-size:12px;color:#666;margin-left:10px;">'
        f'{n_total}&nbsp;{plural_v} &middot; {n_empresas}&nbsp;{plural_e}</span>'
        f'</div>'
        f'</div>'
        f'{blocos}'
    )


def gerar_html_email(
    vagas: List[Dict],
    erros: List[str],
    parte: int = 1,
    total_partes: int = 1,
) -> str:
    """
    Gera o HTML completo do email de alerta.

    Aplica as regras:
    - Omite vagas do TD sem contato descoberto.
    - Agrupa por empresa dentro de cada fonte.
    - Ordena empresas alfabeticamente.
    - CSS 100% inline para resistência ao truncamento do Gmail.
    """
    hoje = date.today().strftime("%d/%m/%Y")

    # Filtrar vagas TD sem contato
    vagas_filtradas = _filtrar_vagas_td(vagas)
    total = len(vagas_filtradas)
    omitidas = len(vagas) - total

    # Agrupar por fonte
    fontes_ordem = ["ProZ.com", "Translators Café", "Translation Directory"]
    por_fonte: Dict[str, List[Dict]] = {f: [] for f in fontes_ordem}
    for v in vagas_filtradas:
        f = v.get("fonte", "Outros")
        if f not in por_fonte:
            por_fonte[f] = []
        por_fonte[f].append(v)

    # Seções de vagas
    secoes_html = "".join(
        _secao_fonte(f, por_fonte.get(f, []))
        for f in fontes_ordem
        if por_fonte.get(f)
    )

    # Sumário
    resumo_rows = ""
    for f in fontes_ordem:
        lst = por_fonte.get(f, [])
        if lst:
            e = _estilo(f)
            resumo_rows += (
                f'<tr>'
                f'<td style="{_FONT}font-size:12px;color:#333;padding:5px 12px;">'
                f'<span style="display:inline-block;padding:2px 8px;'
                f'background:{e["badge_bg"]};color:{e["badge_txt"]};'
                f'border-radius:3px;font-size:11px;font-weight:bold;">{e["label"]}</span>'
                f'</td>'
                f'<td style="{_FONT}font-size:12px;color:{e["accent"]};'
                f'font-weight:bold;padding:5px 12px;text-align:right;">{len(lst)}</td>'
                f'</tr>'
            )

    n_contato = sum(
        1 for v in vagas_filtradas
        if _tem_contato(v)
    )
    if n_contato > 0:
        resumo_rows += (
            f'<tr style="border-top:1px solid #e0e0e0;">'
            f'<td style="{_FONT}font-size:12px;color:#0f9d58;padding:5px 12px;">'
            f'&#9989;&nbsp;Com contato descoberto</td>'
            f'<td style="{_FONT}font-size:12px;color:#0f9d58;font-weight:bold;'
            f'padding:5px 12px;text-align:right;">{n_contato}</td>'
            f'</tr>'
        )

    if omitidas > 0:
        resumo_rows += (
            f'<tr>'
            f'<td style="{_FONT}font-size:11px;color:#999;padding:4px 12px;">'
            f'&#128274;&nbsp;Omitidas (TD sem contato)</td>'
            f'<td style="{_FONT}font-size:11px;color:#999;'
            f'padding:4px 12px;text-align:right;">{omitidas}</td>'
            f'</tr>'
        )

    # Bloco de avisos — separar informativos (TC bloqueado) de erros reais
    erros_html = ""
    if erros:
        # Avisos informativos: TC bloqueado por IP de datacenter (comportamento esperado)
        erros_info = [e for e in erros if "bloqueado" in e.lower() and "403" in e]
        erros_reais = [e for e in erros if e not in erros_info]

        partes_html = []

        if erros_info:
            items_info = "".join(
                f'<li style="{_FONT}font-size:12px;color:#5a6a7a;margin-bottom:3px;">{err}</li>'
                for err in erros_info
            )
            partes_html.append(
                f'<div style="margin-top:12px;padding:10px 14px;background:#f0f4f8;'
                f'border:1px solid #c8d6e5;border-radius:6px;">'
                f'<div style="{_FONT}font-size:11px;font-weight:bold;color:#5a6a7a;'
                f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:5px;">'
                f'Fontes indisponíveis neste ambiente</div>'
                f'<ul style="margin:0;padding-left:16px;">{items_info}</ul>'
                f'</div>'
            )

        if erros_reais:
            items_reais = "".join(
                f'<li style="{_FONT}font-size:12px;color:#856404;margin-bottom:3px;">{err}</li>'
                for err in erros_reais
            )
            partes_html.append(
                f'<div style="margin-top:12px;padding:12px 16px;background:#fff3cd;'
                f'border:1px solid #ffc107;border-radius:6px;">'
                f'<div style="{_FONT}font-size:11px;font-weight:bold;color:#856404;'
                f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">'
                f'Avisos do sistema</div>'
                f'<ul style="margin:0;padding-left:16px;">{items_reais}</ul>'
                f'</div>'
            )

        if partes_html:
            erros_html = f'<div style="margin-top:20px;">{" ".join(partes_html)}</div>'

    # Indicador de parte
    parte_html = ""
    if total_partes > 1:
        parte_html = (
            f'<div style="{_FONT}text-align:center;color:#888;font-size:12px;'
            f'margin-bottom:16px;">Parte {parte} de {total_partes}</div>'
        )

    # Corpo principal
    if not vagas_filtradas:
        corpo = (
            f'<div style="text-align:center;padding:48px 24px;">'
            f'<div style="{_FONT}font-size:15px;font-weight:bold;color:#555;margin-bottom:8px;">'
            f'Nenhuma vaga nova com contato disponível hoje</div>'
            f'<div style="{_FONT}font-size:12px;color:#888;">'
            f'Pares monitorados: PT &#8596; EN &nbsp;&#183;&nbsp; PT &#8596; ES &nbsp;&#183;&nbsp; EN &#8596; ES</div>'
            f'</div>'
        )
    else:
        corpo = (
            # Sumário
            f'<div style="margin-bottom:20px;background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;">'
            f'<div style="padding:8px 12px 6px 12px;border-bottom:1px solid #e0e0e0;">'
            f'<span style="{_FONT}font-size:10px;font-weight:bold;color:#888;'
            f'text-transform:uppercase;letter-spacing:1px;">Resumo por fonte</span>'
            f'</div>'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'{resumo_rows}'
            f'<tr style="border-top:2px solid #e0e0e0;">'
            f'<td style="{_FONT}font-size:13px;font-weight:bold;color:#333;padding:8px 12px;">'
            f'Total de vagas exibidas</td>'
            f'<td style="{_FONT}font-size:15px;font-weight:bold;color:#333;'
            f'padding:8px 12px;text-align:right;">{total}</td>'
            f'</tr>'
            f'</table>'
            f'</div>'
            f'{parte_html}'
            f'{secoes_html}'
            f'{erros_html}'
        )

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Alerta de Vagas de Tradução — {hoje}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;{_FONT}">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#f4f4f4;padding:24px 0;">
    <tr>
      <td align="center">
        <table width="640" cellpadding="0" cellspacing="0" border="0"
               style="max-width:640px;width:100%;">

          <!-- HEADER -->
          <tr>
            <td style="background:#1a1a2e;border-radius:8px 8px 0 0;padding:24px 28px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <div style="{_FONT}color:#a0b4c8;font-size:10px;font-weight:bold;
                         letter-spacing:2px;text-transform:uppercase;margin-bottom:4px;">
                      ALERTA DIÁRIO &middot; TRADUÇÃO</div>
                    <div style="{_FONT}color:#ffffff;font-size:22px;font-weight:bold;
                         line-height:1.2;">Vagas de Tradução</div>
                    <div style="{_FONT}color:#7090a8;font-size:12px;margin-top:4px;">
                      PT &middot; EN &middot; ES &mdash; {hoje}</div>
                  </td>
                  <td align="right" valign="middle">
                    <div style="background:#0d2540;border:2px solid #1a73e8;
                         border-radius:8px;padding:10px 16px;text-align:center;
                         min-width:60px;">
                      <div style="{_FONT}color:#1a73e8;font-size:26px;font-weight:900;
                           line-height:1;">{total}</div>
                      <div style="{_FONT}color:#5a7a9a;font-size:10px;
                           text-transform:uppercase;letter-spacing:0.5px;">
                           nova{"s" if total != 1 else ""}</div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- CORPO -->
          <tr>
            <td style="background:#ffffff;padding:24px 28px;
                 border-left:1px solid #e0e0e0;border-right:1px solid #e0e0e0;">
              {corpo}
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td style="background:#f8f8f8;border-radius:0 0 8px 8px;padding:16px 28px;
                 border:1px solid #e0e0e0;border-top:none;">
              <div style="{_FONT}font-size:11px;color:#999;line-height:1.7;">
                <strong style="color:#555;">Hudson Borges</strong>
                &nbsp;&middot;&nbsp; Sistema de Alertas de Tradução<br>
                Fontes: ProZ.com &nbsp;&middot;&nbsp; Translators Café
                &nbsp;&middot;&nbsp; Translation Directory<br>
                Pares: PT &#8596; EN &nbsp;&middot;&nbsp; PT &#8596; ES
                &nbsp;&middot;&nbsp; EN &#8596; ES<br>
                <span style="color:#0f9d58;">&#9989; Contatos diretos descobertos
                automaticamente via busca reversa</span>
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>'''


def gerar_payloads_email(
    vagas: List[Dict],
    erros: List[str],
    destinatario: str,
    max_por_email: int = 200,
) -> List[Dict]:
    """
    Gera lista de payloads para o Gmail MCP.
    CSS 100% inline: HTML por vaga ~1.5 KB → 100 vagas ≈ 150 KB.
    Divide em partes se necessário para respeitar o limite do Gmail (102 KB).
    """
    hoje = date.today().strftime("%d/%m/%Y")

    # Filtrar antes de dividir
    vagas_filtradas = _filtrar_vagas_td(vagas)
    total = len(vagas_filtradas)

    if total == 0:
        assunto = f"[Tradução] Nenhuma vaga nova — {hoje}"
        html = gerar_html_email([], erros)
        return [{"messages": [{"to": [destinatario], "subject": assunto, "content": html}]}]

    lotes = [vagas_filtradas[i:i + max_por_email] for i in range(0, total, max_por_email)]
    total_partes = len(lotes)
    payloads = []

    for idx, lote in enumerate(lotes, 1):
        if total_partes == 1:
            assunto = f"[Tradução] {total} nova(s) vaga(s) — {hoje}"
        else:
            assunto = f"[Tradução] {total} nova(s) vaga(s) — {hoje} ({idx}/{total_partes})"

        html = gerar_html_email(lote, erros if idx == 1 else [], parte=idx, total_partes=total_partes)
        payloads.append({"messages": [{"to": [destinatario], "subject": assunto, "content": html}]})

    return payloads


if __name__ == "__main__":
    # Gera preview HTML com dados de teste
    vagas_teste = [
        {
            "titulo": "English to Brazilian Portuguese Freelance Translators Needed",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN → PT",
            "area": "Technical, IT",
            "contagem_palavras": "5.000",
            "formato": "Microsoft Word",
            "preco_palavra": "0.22 EUR per word",
            "pais": "UK",
            "empresa": "GlobalTV Translations Ltd.",
            "prazo": "31/12/2026",
            "data_publicacao": "17/03/2026",
            "tipo_contato": "Translation Directory",
            "link_contato": "https://www.translationdirectory.com/job_00078905.php",
            "link_vaga": "https://www.translationdirectory.com/job_00078905.php",
            "fonte": "Translation Directory",
            "detalhes": "Our company, a world leader in translations, specialising in TV programme information. We are currently recruiting freelance translators. Native speakers only.",
            "contato_pessoa": "John Smith",
            "contato_descoberto": {
                "email": "info@globaltv-translations.com",
                "site": "https://www.globaltv-translations.com",
                "fonte_busca": "página de contato",
            },
        },
        {
            "titulo": "GlobalTV — Ongoing EN→PT Projects (European Portuguese)",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN → PT",
            "area": "Media, IT",
            "contagem_palavras": "",
            "formato": "",
            "preco_palavra": "0.27 EUR per word",
            "pais": "UK",
            "empresa": "GlobalTV Translations Ltd.",
            "prazo": "31/12/2026",
            "data_publicacao": "18/03/2026",
            "tipo_contato": "Translation Directory",
            "link_contato": "https://www.translationdirectory.com/job_00078733.php",
            "link_vaga": "https://www.translationdirectory.com/job_00078733.php",
            "fonte": "Translation Directory",
            "detalhes": "Professional Brazilian Portuguese and European Portuguese translators needed for ongoing projects.",
            "contato_pessoa": "",
            "contato_descoberto": {
                "email": "info@globaltv-translations.com",
                "site": "https://www.globaltv-translations.com",
                "fonte_busca": "página de contato",
            },
        },
        {
            "titulo": "Vaga sem contato — deve ser omitida",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN → PT",
            "area": "IT",
            "preco_palavra": "0.10 EUR per word",
            "pais": "India",
            "empresa": "",
            "prazo": "28/02/2026",
            "fonte": "Translation Directory",
            "link_vaga": "https://www.translationdirectory.com/job_00078609.php",
            "detalhes": "Esta vaga não tem contato e deve ser omitida.",
            "contato_descoberto": {"aviso": "requer cadastro pago"},
        },
        {
            "titulo": "Simultaneous Interpreters Needed EN/PT/ES",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN → PT",
            "area": "Legal",
            "preco_palavra": "0.18 USD per word",
            "pais": "Brazil",
            "empresa": "Skrivanek Brasil",
            "prazo": "15/04/2026",
            "data_publicacao": "18/03/2026",
            "tipo_contato": "email",
            "link_contato": "info@skrivanek.com",
            "link_vaga": "https://www.translatorscafe.com/cafe/SelectedJob.asp?Job=374422",
            "fonte": "Translators Café",
            "detalhes": "We need experienced simultaneous interpreters for a legal conference.",
            "contato_pessoa": "Maria Silva",
            "contato_descoberto": {},
        },
        {
            "titulo": "Voice Over Directors and Transcreators based in Canada",
            "idioma_origem": "EN", "idioma_destino": "ES",
            "par_display": "EN → ES",
            "area": "Government / Politics",
            "preco_palavra": "",
            "pais": "",
            "empresa": "Acme Translations",
            "prazo": "01/04/2026",
            "data_publicacao": "18/03/2026",
            "tipo_contato": "URL",
            "link_contato": "https://www.proz.com/translation-jobs/2231906",
            "link_vaga": "https://www.proz.com/translation-jobs/2231906",
            "fonte": "ProZ.com",
            "detalhes": "We are looking for voice over directors and transcreators based in Canada.",
            "contato_pessoa": "",
            "contato_descoberto": {
                "site": "https://www.acmetranslations.com",
                "fonte_busca": "homepage",
            },
        },
    ]
    html = gerar_html_email(vagas_teste, ["ProZ.com: 0 vagas (encoding issue)", "Translators Café: IP bloqueado"])
    with open("/tmp/email_preview_v3.html", "w", encoding="utf-8") as f:
        f.write(html)
    size = len(html.encode("utf-8"))
    print(f"Preview gerado: /tmp/email_preview_v3.html ({size//1024} KB)")
    print(f"Vagas teste: 5 total, 1 omitida (TD sem contato) → 4 exibidas")
