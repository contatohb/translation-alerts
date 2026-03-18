#!/usr/bin/env python3
"""
Template HTML premium para newsletter de vagas de tradução.
Design: dark/slate premium, cards por vaga, todos os campos do monitor.
Compatível com Gmail (inline CSS, tabelas, sem media queries).

Campos esperados por vaga (do monitor_traducao.py):
  titulo, idioma_origem, idioma_destino, par_display,
  area, contagem_palavras, formato, preco_palavra, pais,
  prazo, data_publicacao, tipo_contato, link_contato,
  link_vaga, fonte, detalhes, contato_pessoa, empresa,
  contato_descoberto (dict: site, email, fonte_busca)
"""
from __future__ import annotations
from datetime import date
from typing import Dict, List


# ─── Paleta por fonte ────────────────────────────────────────────
FONTE_ESTILOS = {
    "ProZ.com": {
        "header_bg": "#0a2540",
        "badge_bg":  "#1a5276",
        "badge_txt": "#aed6f1",
        "accent":    "#2e86c1",
        "label":     "ProZ.com",
    },
    "Translators Café": {
        "header_bg": "#0b2e1a",
        "badge_bg":  "#1e8449",
        "badge_txt": "#a9dfbf",
        "accent":    "#27ae60",
        "label":     "Translators Café",
    },
    "Translation Directory": {
        "header_bg": "#2c0b3a",
        "badge_bg":  "#7d3c98",
        "badge_txt": "#d7bde2",
        "accent":    "#9b59b6",
        "label":     "Translation Directory",
    },
}

_DEFAULT_ESTILO = {
    "header_bg": "#1a2533",
    "badge_bg":  "#2e4057",
    "badge_txt": "#b2c3d4",
    "accent":    "#4a7fa5",
    "label":     "Outros",
}

# Cores por par de idiomas
PAR_CORES = {
    "EN → PT": "#2e86c1",
    "PT → EN": "#2e86c1",
    "PT → ES": "#d4ac0d",
    "ES → PT": "#d4ac0d",
    "EN → ES": "#8e44ad",
    "ES → EN": "#8e44ad",
}


def _estilo(fonte: str) -> dict:
    return FONTE_ESTILOS.get(fonte, _DEFAULT_ESTILO)


def _cor_par(par: str) -> str:
    for k, v in PAR_CORES.items():
        if k.replace(" ", "").lower() in par.replace(" ", "").lower():
            return v
    return "#4a7fa5"


def _campo_html(label: str, valor: str, destaque: bool = False) -> str:
    """Linha de campo label: valor em tabela."""
    if not valor or valor.strip() in ("", "-", "N/A"):
        return ""
    cor_val = "#e8f0fe" if destaque else "#c5d5e8"
    return (
        f'<tr>'
        f'<td style="padding:4px 14px 4px 0;color:#7f8fa6;font-size:12px;'
        f'white-space:nowrap;vertical-align:top;font-family:Arial,sans-serif;">{label}</td>'
        f'<td style="padding:4px 0;color:{cor_val};font-size:13px;'
        f'vertical-align:top;font-family:Arial,sans-serif;">{valor}</td>'
        f'</tr>'
    )


def _bloco_contato_descoberto(contato: Dict, accent: str) -> str:
    """Gera bloco HTML destacado para contato descoberto via busca reversa."""
    if not contato:
        return ""
    email = contato.get("email", "")
    site = contato.get("site", "")
    fonte_busca = contato.get("fonte_busca", "busca reversa")

    if not email and not site:
        return ""

    linhas = []
    if email:
        mailto = f"mailto:{email}"
        linhas.append(
            f'<a href="{mailto}" style="color:#27ae60;font-size:12px;'
            f'font-family:Arial,sans-serif;text-decoration:none;">'
            f'✉ {email}</a>'
        )
    if site:
        linhas.append(
            f'<a href="{site}" style="color:#5dade2;font-size:12px;'
            f'font-family:Arial,sans-serif;text-decoration:none;">'
            f'🌐 {site[:60]}{"..." if len(site) > 60 else ""}</a>'
        )

    conteudo = "<br>".join(linhas)
    return f'''
    <tr>
      <td colspan="2" style="padding:8px 0 4px 0;">
        <div style="background:#0a2a1a;border-left:3px solid #27ae60;
                    padding:10px 14px;border-radius:0 6px 6px 0;">
          <div style="color:#27ae60;font-size:10px;font-weight:bold;
                      text-transform:uppercase;letter-spacing:0.5px;
                      margin-bottom:6px;font-family:Arial,sans-serif;">
            Contato Descoberto <span style="color:#4a6a8a;font-weight:normal;">
            (via {fonte_busca})</span>
          </div>
          <div>{conteudo}</div>
        </div>
      </td>
    </tr>'''


def _card_vaga(v: Dict, idx: int, total: int) -> str:
    """Gera HTML de um card de vaga com todos os campos disponíveis."""
    fonte = v.get("fonte", "")
    e = _estilo(fonte)
    titulo = v.get("titulo", "Sem título")
    par = v.get("par_display", f"{v.get('idioma_origem','?')} → {v.get('idioma_destino','?')}")
    cor_par = _cor_par(par)
    link_vaga = v.get("link_vaga", "#")
    link_contato = v.get("link_contato", "")
    tipo_contato = v.get("tipo_contato", "")
    contato_descoberto = v.get("contato_descoberto", {})

    # Badge do par de idiomas
    badge_par = (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:10px;'
        f'background:{cor_par}22;color:{cor_par};font-size:12px;font-weight:bold;'
        f'border:1px solid {cor_par}55;font-family:Arial,sans-serif;">{par}</span>'
    )

    # Campos da vaga
    campos = ""
    campos += _campo_html("Par de idiomas", badge_par, destaque=True)
    campos += _campo_html("Área / Tipo", v.get("area", ""))
    campos += _campo_html("Palavras", v.get("contagem_palavras", ""))
    campos += _campo_html("Formato", v.get("formato", ""))
    campos += _campo_html("Preço / palavra", v.get("preco_palavra", ""))
    campos += _campo_html("País", v.get("pais", ""))
    campos += _campo_html("Empresa", v.get("empresa", ""))
    campos += _campo_html("Contato", v.get("contato_pessoa", ""))
    campos += _campo_html("Prazo", v.get("prazo", ""), destaque=True)
    campos += _campo_html("Publicado em", v.get("data_publicacao", ""))

    # Bloco de descrição
    descricao_html = ""
    if v.get("detalhes"):
        det = v["detalhes"].replace("<", "&lt;").replace(">", "&gt;")
        descricao_html = f'''
        <tr>
          <td colspan="2" style="padding:10px 0 4px 0;">
            <div style="background:#0d1b2a;border-left:3px solid {e["accent"]};
                        padding:10px 14px;border-radius:0 6px 6px 0;">
              <div style="color:#7f8fa6;font-size:10px;font-weight:bold;
                          text-transform:uppercase;letter-spacing:0.5px;
                          margin-bottom:6px;font-family:Arial,sans-serif;">Descrição</div>
              <div style="color:#8fa8c0;font-size:12px;line-height:1.6;
                          font-family:Arial,sans-serif;">{det}</div>
            </div>
          </td>
        </tr>'''

    # Bloco de contato descoberto (busca reversa)
    contato_descoberto_html = _bloco_contato_descoberto(contato_descoberto, e["accent"])

    # Botão de ação principal
    btn_label = "Ver vaga →"
    btn_url = link_vaga

    # Se há email direto na vaga
    if tipo_contato == "email" and link_contato and "@" in link_contato:
        btn_label = "Enviar candidatura →"
        btn_url = f"mailto:{link_contato}?subject=Candidatura%20-%20{titulo[:50].replace(' ', '%20')}"
    # Se há email descoberto via busca reversa
    elif contato_descoberto.get("email") and not (tipo_contato == "email" and "@" in link_contato):
        email_desc = contato_descoberto["email"]
        btn_label = "Contato direto →"
        btn_url = f"mailto:{email_desc}?subject=Candidatura%20-%20{titulo[:50].replace(' ', '%20')}"
    elif tipo_contato == "URL" and link_contato and link_contato != link_vaga:
        btn_label = "Acessar formulário →"
        btn_url = link_contato

    # Indicador de CV
    cv_status = "⚠ CV: ação manual"
    cv_color = "#f39c12"
    if tipo_contato == "email" and link_contato and "@" in link_contato:
        cv_status = "✉ Contato direto disponível"
        cv_color = "#27ae60"
    elif contato_descoberto.get("email"):
        cv_status = "🔍 Email descoberto"
        cv_color = "#2ecc71"
    elif contato_descoberto.get("site"):
        cv_status = "🌐 Site encontrado"
        cv_color = "#3498db"

    return f'''
    <!-- CARD #{idx} -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="margin-bottom:14px;border-radius:10px;overflow:hidden;
                  background:#1a2b3c;border:1px solid #243447;">
      <!-- Header do card -->
      <tr>
        <td style="background:{e["header_bg"]};padding:10px 16px;
                   border-bottom:1px solid #243447;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td>
                <span style="background:{e["badge_bg"]};color:{e["badge_txt"]};
                             font-size:10px;font-weight:bold;padding:2px 8px;
                             border-radius:4px;font-family:Arial,sans-serif;
                             letter-spacing:0.5px;">{e["label"]}</span>
                <span style="color:#4a6a8a;font-size:11px;
                             font-family:Arial,sans-serif;margin-left:8px;">
                  #{idx}/{total}
                </span>
              </td>
              <td align="right">
                <span style="color:{cv_color};font-size:11px;
                             font-family:Arial,sans-serif;">
                  {cv_status}
                </span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <!-- Título -->
      <tr>
        <td style="padding:12px 16px 6px 16px;">
          <a href="{link_vaga}"
             style="color:#5dade2;font-size:14px;font-weight:bold;
                    text-decoration:none;font-family:Arial,sans-serif;
                    line-height:1.4;">{titulo}</a>
        </td>
      </tr>
      <!-- Campos -->
      <tr>
        <td style="padding:4px 16px 10px 16px;">
          <table cellpadding="0" cellspacing="0" border="0" width="100%">
            {campos}
            {descricao_html}
            {contato_descoberto_html}
            <tr>
              <td colspan="2" style="padding-top:12px;">
                <a href="{btn_url}"
                   style="display:inline-block;background:{e["accent"]};
                          color:#ffffff;font-size:12px;font-weight:bold;
                          padding:7px 18px;border-radius:5px;
                          text-decoration:none;font-family:Arial,sans-serif;">
                  {btn_label}
                </a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>'''


def _secao_fonte(fonte: str, vagas: List[Dict], idx_inicio: int, total_geral: int) -> str:
    """Gera seção HTML de uma fonte com todos os seus cards."""
    if not vagas:
        return ""
    e = _estilo(fonte)
    cards = "".join(
        _card_vaga(v, idx_inicio + i, total_geral)
        for i, v in enumerate(vagas)
    )
    return f'''
    <!-- SEÇÃO: {fonte} -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="margin-bottom:24px;">
      <tr>
        <td style="padding:0 0 12px 0;border-left:4px solid {e["accent"]};
                   padding-left:14px;">
          <span style="color:#ffffff;font-size:15px;font-weight:bold;
                       font-family:Arial,sans-serif;">{fonte}</span>
          <span style="color:#4a6a8a;font-size:12px;
                       font-family:Arial,sans-serif;margin-left:8px;">
            {len(vagas)} vaga{"s" if len(vagas) != 1 else ""}
          </span>
        </td>
      </tr>
      <tr>
        <td>{cards}</td>
      </tr>
    </table>'''


def gerar_html_email(
    vagas: List[Dict],
    erros: List[str],
    parte: int = 1,
    total_partes: int = 1,
) -> str:
    """Gera o HTML completo do email de alerta."""
    hoje = date.today().strftime("%d/%m/%Y")
    total = len(vagas)

    # Agrupar por fonte (ordem fixa)
    fontes_ordem = ["ProZ.com", "Translators Café", "Translation Directory"]
    por_fonte: Dict[str, List[Dict]] = {f: [] for f in fontes_ordem}
    for v in vagas:
        f = v.get("fonte", "Outros")
        if f not in por_fonte:
            por_fonte[f] = []
        por_fonte[f].append(v)

    # Seções de vagas
    secoes_html = ""
    idx_atual = 1
    for f in fontes_ordem:
        lst = por_fonte.get(f, [])
        if lst:
            secoes_html += _secao_fonte(f, lst, idx_atual, total)
            idx_atual += len(lst)

    # Contar vagas com contato descoberto
    n_contato_descoberto = sum(
        1 for v in vagas
        if v.get("contato_descoberto", {}).get("email") or v.get("contato_descoberto", {}).get("site")
    )
    n_email_direto = sum(
        1 for v in vagas
        if v.get("tipo_contato") == "email" and "@" in v.get("link_contato", "")
    )

    # Sumário por fonte
    resumo_rows = ""
    for f in fontes_ordem:
        lst = por_fonte.get(f, [])
        if lst:
            e = _estilo(f)
            resumo_rows += f'''
            <tr>
              <td style="padding:5px 12px;font-family:Arial,sans-serif;
                         font-size:12px;color:#c5d5e8;">
                <span style="background:{e["badge_bg"]};color:{e["badge_txt"]};
                             font-size:10px;font-weight:bold;padding:2px 7px;
                             border-radius:4px;margin-right:8px;">{e["label"]}</span>
              </td>
              <td style="padding:5px 12px;font-family:Arial,sans-serif;
                         font-size:12px;color:#5dade2;font-weight:bold;
                         text-align:right;">{len(lst)}</td>
            </tr>'''

    # Linha de contatos descobertos no sumário
    if n_email_direto > 0 or n_contato_descoberto > 0:
        resumo_rows += f'''
        <tr style="border-top:1px solid #1e3a52;">
          <td style="padding:5px 12px;font-family:Arial,sans-serif;
                     font-size:12px;color:#c5d5e8;">
            <span style="color:#27ae60;font-size:11px;">✉ Email direto disponível</span>
          </td>
          <td style="padding:5px 12px;font-family:Arial,sans-serif;
                     font-size:12px;color:#27ae60;font-weight:bold;
                     text-align:right;">{n_email_direto}</td>
        </tr>'''
        if n_contato_descoberto > 0:
            resumo_rows += f'''
            <tr>
              <td style="padding:5px 12px;font-family:Arial,sans-serif;
                         font-size:12px;color:#c5d5e8;">
                <span style="color:#2ecc71;font-size:11px;">🔍 Contato descoberto</span>
              </td>
              <td style="padding:5px 12px;font-family:Arial,sans-serif;
                         font-size:12px;color:#2ecc71;font-weight:bold;
                         text-align:right;">{n_contato_descoberto}</td>
            </tr>'''

    # Bloco de erros
    erros_html = ""
    if erros:
        items = "".join(
            f'<li style="margin-bottom:3px;">{err}</li>'
            for err in erros
        )
        erros_html = f'''
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="margin-top:20px;background:#1a1a0d;border:1px solid #3a3a1a;
                      border-radius:8px;">
          <tr>
            <td style="padding:12px 16px;">
              <div style="color:#b7950b;font-size:11px;font-weight:bold;
                          text-transform:uppercase;letter-spacing:0.5px;
                          margin-bottom:8px;font-family:Arial,sans-serif;">
                Avisos do sistema
              </div>
              <ul style="color:#7d6608;font-size:12px;margin:0;
                         padding-left:16px;line-height:1.7;
                         font-family:Arial,sans-serif;">
                {items}
              </ul>
            </td>
          </tr>
        </table>'''

    # Indicador de parte
    parte_html = ""
    if total_partes > 1:
        parte_html = f'''
        <div style="text-align:center;color:#4a6a8a;font-size:12px;
                    margin-bottom:16px;font-family:Arial,sans-serif;">
          Parte {parte} de {total_partes}
        </div>'''

    # Conteúdo quando não há vagas
    if not vagas:
        corpo = '''
        <div style="text-align:center;padding:48px 24px;">
          <div style="font-size:36px;margin-bottom:14px;">🔍</div>
          <div style="color:#8fa8c0;font-size:15px;font-weight:bold;
                      margin-bottom:8px;font-family:Arial,sans-serif;">
            Nenhuma vaga nova hoje
          </div>
          <div style="color:#4a6a8a;font-size:12px;font-family:Arial,sans-serif;">
            Pares monitorados: PT ↔ EN &nbsp;·&nbsp; PT ↔ ES &nbsp;·&nbsp; EN ↔ ES
          </div>
        </div>'''
    else:
        corpo = f'''
        <!-- SUMÁRIO -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:#0d1b2a;border-radius:8px;margin-bottom:20px;
                      overflow:hidden;border:1px solid #1e3a52;">
          <tr>
            <td colspan="2" style="padding:8px 12px 6px 12px;
                                   border-bottom:1px solid #1e3a52;">
              <span style="color:#7f8fa6;font-size:10px;font-weight:bold;
                           letter-spacing:1px;text-transform:uppercase;
                           font-family:Arial,sans-serif;">Resumo por fonte</span>
            </td>
          </tr>
          {resumo_rows}
          <tr style="border-top:1px solid #1e3a52;">
            <td style="padding:8px 12px;font-family:Arial,sans-serif;
                       font-size:12px;color:#7f8fa6;font-weight:bold;">
              Total de vagas novas
            </td>
            <td style="padding:8px 12px;font-family:Arial,sans-serif;
                       font-size:15px;color:#ffffff;font-weight:bold;
                       text-align:right;">{total}</td>
          </tr>
        </table>
        {parte_html}
        <!-- VAGAS -->
        {secoes_html}
        {erros_html}'''

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Alerta de Vagas de Tradução — {hoje}</title>
</head>
<body style="margin:0;padding:0;background-color:#0d1b2a;">

  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#0d1b2a;padding:24px 0;">
    <tr>
      <td align="center">
        <table width="640" cellpadding="0" cellspacing="0" border="0"
               style="max-width:640px;width:100%;">

          <!-- HEADER -->
          <tr>
            <td style="background:linear-gradient(135deg,#0a2540 0%,#1a3a5c 70%,#0d2d4a 100%);
                       border-radius:12px 12px 0 0;padding:28px 28px 22px 28px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <div style="color:#5dade2;font-size:10px;font-weight:bold;
                                letter-spacing:2px;text-transform:uppercase;
                                font-family:Arial,sans-serif;margin-bottom:6px;">
                      ALERTA DIÁRIO · TRADUÇÃO
                    </div>
                    <div style="color:#ffffff;font-size:24px;font-weight:bold;
                                font-family:Arial,sans-serif;line-height:1.2;">
                      Vagas de Tradução
                    </div>
                    <div style="color:#7fa8c8;font-size:12px;
                                font-family:Arial,sans-serif;margin-top:4px;">
                      PT · EN · ES — {hoje}
                    </div>
                  </td>
                  <td align="right" valign="top">
                    <div style="background:#0a2540;border:2px solid #2e86c1;
                                border-radius:10px;padding:10px 16px;text-align:center;">
                      <div style="color:#5dade2;font-size:28px;font-weight:900;
                                  font-family:Arial,sans-serif;line-height:1;">
                        {total}
                      </div>
                      <div style="color:#4a6a8a;font-size:10px;
                                  text-transform:uppercase;letter-spacing:0.5px;
                                  font-family:Arial,sans-serif;">
                        nova{"s" if total != 1 else ""}
                      </div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- CORPO -->
          <tr>
            <td style="background:#162535;padding:22px 28px;
                       border-left:1px solid #1e3a52;border-right:1px solid #1e3a52;">
              {corpo}
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td style="background:#0a1a2a;border-radius:0 0 12px 12px;
                       padding:18px 28px;border:1px solid #1e3a52;border-top:none;">
              <div style="color:#3d5a73;font-size:11px;
                          font-family:Arial,sans-serif;line-height:1.7;">
                <strong style="color:#4a6a8a;">Hudson Borges</strong>
                &nbsp;·&nbsp; Sistema de Alertas de Tradução<br>
                Fontes: ProZ.com &nbsp;·&nbsp; Translators Café
                &nbsp;·&nbsp; Translation Directory<br>
                Pares: PT ↔ EN &nbsp;·&nbsp; PT ↔ ES &nbsp;·&nbsp; EN ↔ ES<br>
                <span style="color:#27ae60;">✉ Contatos diretos descobertos automaticamente via busca reversa</span>
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
    max_por_email: int = 50,
) -> List[Dict]:
    """
    Gera lista de payloads para o Gmail MCP.
    Divide em múltiplos emails se houver mais de max_por_email vagas.
    """
    hoje = date.today().strftime("%d/%m/%Y")
    total = len(vagas)

    if total == 0:
        assunto = f"[Tradução] Nenhuma vaga nova — {hoje}"
        html = gerar_html_email([], erros)
        return [{"messages": [{"to": destinatario, "subject": assunto,
                               "content": html, "content_type": "html"}]}]

    lotes = [vagas[i:i + max_por_email] for i in range(0, total, max_por_email)]
    total_partes = len(lotes)
    payloads = []

    for idx, lote in enumerate(lotes, 1):
        if total_partes == 1:
            assunto = f"[Tradução] {total} nova(s) vaga(s) — {hoje}"
        else:
            assunto = f"[Tradução] {total} nova(s) vaga(s) — {hoje} ({idx}/{total_partes})"

        html = gerar_html_email(
            lote,
            erros if idx == 1 else [],
            parte=idx,
            total_partes=total_partes,
        )
        payloads.append({"messages": [{"to": destinatario, "subject": assunto,
                                       "content": html, "content_type": "html"}]})

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
            "detalhes": "Our company, a world leader in translations, specialising in TV programme information. We are currently recruiting freelance translators. Native speakers only. Flexible working conditions.",
            "contato_pessoa": "John Smith",
            "contato_descoberto": {
                "email": "info@globaltv-translations.com",
                "site": "https://www.globaltv-translations.com",
                "fonte_busca": "página de contato",
            },
        },
        {
            "titulo": "Simultaneous Interpreters Needed EN/PT/ES – Rio de Janeiro",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN → PT | PT → ES",
            "area": "General",
            "contagem_palavras": "",
            "formato": "",
            "preco_palavra": "",
            "pais": "Brazil",
            "empresa": "Skrivanek",
            "prazo": "30/03/2026",
            "data_publicacao": "18/03/2026",
            "tipo_contato": "Translators Café",
            "link_contato": "https://www.translatorscafe.com/cafe/SelectedJob.asp?Job=123456",
            "link_vaga": "https://www.translatorscafe.com/cafe/SelectedJob.asp?Job=123456",
            "fonte": "Translators Café",
            "detalhes": "We are looking for experienced simultaneous interpreters for a 3-day international conference in Rio de Janeiro.",
            "contato_pessoa": "",
            "contato_descoberto": {
                "email": "info@skrivanek.com",
                "site": "https://skrivanek.com",
                "fonte_busca": "homepage",
            },
        },
        {
            "titulo": "Spanish to English Legal Document Translation – Urgent",
            "idioma_origem": "ES", "idioma_destino": "EN",
            "par_display": "ES → EN",
            "area": "Legal",
            "contagem_palavras": "12.000",
            "formato": "PDF",
            "preco_palavra": "0.10 USD per word",
            "pais": "USA",
            "empresa": "LegalDocs Inc.",
            "prazo": "25/03/2026",
            "data_publicacao": "16/03/2026",
            "tipo_contato": "email",
            "link_contato": "jobs@legaldocs.com",
            "link_vaga": "https://www.proz.com/translation-jobs/9999999",
            "fonte": "ProZ.com",
            "detalhes": "Legal contracts and agreements. Certified translation required. Urgent delivery.",
            "contato_pessoa": "Maria Garcia",
            "contato_descoberto": {},
        },
    ]
    erros_teste = ["Translators Café: acesso bloqueado (403) — IP do servidor bloqueado pelo TC"]

    html = gerar_html_email(vagas_teste, erros_teste)
    with open("/tmp/email_preview.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Preview salvo em /tmp/email_preview.html")
