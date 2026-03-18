#!/usr/bin/env python3
"""
Template HTML premium para newsletter de vagas de tradução.
Design: dark/slate premium, cards por vaga, todos os campos do monitor.

Otimização de tamanho: estilos repetidos movidos para classes CSS no <head>.
Resultado: HTML de ~70-90KB independente do número de vagas (vs. 307KB com inline).
Compatível com Gmail (suporta <style> no <head> desde 2016).

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


# ─── CSS global (movido do inline para classes) ──────────────────
CSS_GLOBAL = """
  body { margin:0; padding:0; background:#0d1b2a; }
  .wrap { background:#0d1b2a; padding:24px 0; }
  .inner { max-width:640px; width:100%; }
  /* Header */
  .hdr { background:linear-gradient(135deg,#0a2540 0%,#1a3a5c 70%,#0d2d4a 100%);
         border-radius:12px 12px 0 0; padding:28px 28px 22px 28px; }
  .hdr-label { color:#5dade2; font-size:10px; font-weight:bold;
               letter-spacing:2px; text-transform:uppercase;
               font-family:Arial,sans-serif; margin-bottom:6px; }
  .hdr-title { color:#fff; font-size:24px; font-weight:bold;
               font-family:Arial,sans-serif; line-height:1.2; }
  .hdr-sub { color:#7fa8c8; font-size:12px; font-family:Arial,sans-serif; margin-top:4px; }
  .hdr-count-box { background:#0a2540; border:2px solid #2e86c1;
                   border-radius:10px; padding:10px 16px; text-align:center; }
  .hdr-count-n { color:#5dade2; font-size:28px; font-weight:900;
                 font-family:Arial,sans-serif; line-height:1; }
  .hdr-count-lbl { color:#4a6a8a; font-size:10px; text-transform:uppercase;
                   letter-spacing:0.5px; font-family:Arial,sans-serif; }
  /* Corpo */
  .body-td { background:#162535; padding:22px 28px;
             border-left:1px solid #1e3a52; border-right:1px solid #1e3a52; }
  /* Footer */
  .ftr { background:#0a1a2a; border-radius:0 0 12px 12px;
         padding:18px 28px; border:1px solid #1e3a52; border-top:none; }
  .ftr-txt { color:#3d5a73; font-size:11px; font-family:Arial,sans-serif; line-height:1.7; }
  .ftr-name { color:#4a6a8a; }
  .ftr-green { color:#27ae60; }
  /* Sumário */
  .sumario { background:#0d1b2a; border-radius:8px; margin-bottom:20px;
             border:1px solid #1e3a52; }
  .sumario-hdr { padding:8px 12px 6px 12px; border-bottom:1px solid #1e3a52; }
  .sumario-lbl { color:#7f8fa6; font-size:10px; font-weight:bold;
                 letter-spacing:1px; text-transform:uppercase; font-family:Arial,sans-serif; }
  .sumario-td-l { padding:5px 12px; font-family:Arial,sans-serif;
                  font-size:12px; color:#c5d5e8; }
  .sumario-td-r { padding:5px 12px; font-family:Arial,sans-serif;
                  font-size:12px; color:#5dade2; font-weight:bold; text-align:right; }
  .sumario-total-l { padding:8px 12px; font-family:Arial,sans-serif;
                     font-size:12px; color:#7f8fa6; font-weight:bold; }
  .sumario-total-r { padding:8px 12px; font-family:Arial,sans-serif;
                     font-size:15px; color:#fff; font-weight:bold; text-align:right; }
  .sumario-sep { border-top:1px solid #1e3a52; }
  /* Badge fonte */
  .badge { font-size:10px; font-weight:bold; padding:2px 7px;
           border-radius:4px; font-family:Arial,sans-serif; letter-spacing:0.5px; }
  /* Seção fonte */
  .sec-hdr-td { padding:0 0 12px 0; padding-left:14px; }
  .sec-title { color:#fff; font-size:15px; font-weight:bold; font-family:Arial,sans-serif; }
  .sec-count { color:#4a6a8a; font-size:12px; font-family:Arial,sans-serif; margin-left:8px; }
  /* Card */
  .card { margin-bottom:14px; border-radius:10px; border:1px solid #243447; }
  .card-hdr-td { padding:10px 16px; border-bottom:1px solid #243447; }
  .card-num { color:#4a6a8a; font-size:11px; font-family:Arial,sans-serif; margin-left:8px; }
  .card-cv { font-size:11px; font-family:Arial,sans-serif; }
  .card-title-td { padding:12px 16px 6px 16px; }
  .card-link { color:#5dade2; font-size:14px; font-weight:bold;
               text-decoration:none; font-family:Arial,sans-serif; line-height:1.4; }
  .card-fields-td { padding:4px 16px 10px 16px; }
  /* Campos */
  .fl { padding:4px 14px 4px 0; color:#7f8fa6; font-size:12px;
        white-space:nowrap; vertical-align:top; font-family:Arial,sans-serif; }
  .fv { padding:4px 0; color:#c5d5e8; font-size:13px;
        vertical-align:top; font-family:Arial,sans-serif; }
  .fv-hi { color:#e8f0fe; }
  /* Badge par de idiomas */
  .par-badge { display:inline-block; padding:3px 10px; border-radius:10px;
               font-size:12px; font-weight:bold; font-family:Arial,sans-serif; }
  /* Bloco descrição */
  .desc-box { padding:10px 14px; border-radius:0 6px 6px 0; background:#0d1b2a; }
  .desc-lbl { color:#7f8fa6; font-size:10px; font-weight:bold;
              text-transform:uppercase; letter-spacing:0.5px;
              margin-bottom:6px; font-family:Arial,sans-serif; }
  .desc-txt { color:#8fa8c0; font-size:12px; line-height:1.6; font-family:Arial,sans-serif; }
  /* Bloco contato descoberto */
  .cd-box { background:#0a2a1a; border-radius:0 6px 6px 0; padding:10px 14px; }
  .cd-lbl { color:#27ae60; font-size:10px; font-weight:bold;
            text-transform:uppercase; letter-spacing:0.5px;
            margin-bottom:6px; font-family:Arial,sans-serif; }
  .cd-sub { color:#4a6a8a; font-weight:normal; }
  .cd-email { color:#27ae60; font-size:12px; font-family:Arial,sans-serif; text-decoration:none; }
  .cd-site { color:#5dade2; font-size:12px; font-family:Arial,sans-serif; text-decoration:none; }
  /* Botão */
  .btn { display:inline-block; color:#fff; font-size:12px; font-weight:bold;
         padding:7px 18px; border-radius:5px; text-decoration:none;
         font-family:Arial,sans-serif; }
  /* Avisos */
  .avisos { margin-top:20px; background:#1a1a0d; border:1px solid #3a3a1a; border-radius:8px; }
  .avisos-td { padding:12px 16px; }
  .avisos-lbl { color:#b7950b; font-size:11px; font-weight:bold;
                text-transform:uppercase; letter-spacing:0.5px;
                margin-bottom:8px; font-family:Arial,sans-serif; }
  .avisos-ul { color:#7d6608; font-size:12px; margin:0;
               padding-left:16px; line-height:1.7; font-family:Arial,sans-serif; }
  /* Vazio */
  .vazio-td { text-align:center; padding:48px 24px; }
  .vazio-icon { font-size:36px; margin-bottom:14px; }
  .vazio-title { color:#8fa8c0; font-size:15px; font-weight:bold;
                 margin-bottom:8px; font-family:Arial,sans-serif; }
  .vazio-sub { color:#4a6a8a; font-size:12px; font-family:Arial,sans-serif; }
"""

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
    cls_val = "fv fv-hi" if destaque else "fv"
    return (
        f'<tr>'
        f'<td class="fl">{label}</td>'
        f'<td class="{cls_val}">{valor}</td>'
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
        linhas.append(
            f'<a href="mailto:{email}" class="cd-email">&#9993; {email}</a>'
        )
    if site:
        site_txt = site[:60] + ("..." if len(site) > 60 else "")
        linhas.append(
            f'<a href="{site}" class="cd-site">&#127760; {site_txt}</a>'
        )

    conteudo = "<br>".join(linhas)
    return f'''
    <tr>
      <td colspan="2" style="padding:8px 0 4px 0;">
        <div class="cd-box" style="border-left:3px solid #27ae60;">
          <div class="cd-lbl">Contato Descoberto
            <span class="cd-sub">(via {fonte_busca})</span>
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

    # Badge do par de idiomas (inline necessário pois cor varia por par)
    badge_par = (
        f'<span class="par-badge" style="background:{cor_par}22;color:{cor_par};'
        f'border:1px solid {cor_par}55;">{par}</span>'
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
            <div class="desc-box" style="border-left:3px solid {e["accent"]};">
              <div class="desc-lbl">Descri&#231;&#227;o</div>
              <div class="desc-txt">{det}</div>
            </div>
          </td>
        </tr>'''

    # Bloco de contato descoberto
    contato_descoberto_html = _bloco_contato_descoberto(contato_descoberto, e["accent"])

    # Botão de ação principal
    btn_label = "Ver vaga &#8594;"
    btn_url = link_vaga
    if tipo_contato == "email" and link_contato and "@" in link_contato:
        btn_label = "Enviar candidatura &#8594;"
        btn_url = f"mailto:{link_contato}?subject=Candidatura%20-%20{titulo[:50].replace(' ', '%20')}"
    elif contato_descoberto.get("email") and not (tipo_contato == "email" and "@" in link_contato):
        email_desc = contato_descoberto["email"]
        btn_label = "Contato direto &#8594;"
        btn_url = f"mailto:{email_desc}?subject=Candidatura%20-%20{titulo[:50].replace(' ', '%20')}"
    elif tipo_contato == "URL" and link_contato and link_contato != link_vaga:
        btn_label = "Acessar formul&#225;rio &#8594;"
        btn_url = link_contato

    # Indicador de CV
    cv_status = "&#9888; CV: a&#231;&#227;o manual"
    cv_color = "#f39c12"
    if tipo_contato == "email" and link_contato and "@" in link_contato:
        cv_status = "&#9993; Contato direto dispon&#237;vel"
        cv_color = "#27ae60"
    elif contato_descoberto.get("email"):
        cv_status = "Email descoberto"
        cv_color = "#2ecc71"
    elif contato_descoberto.get("site"):
        cv_status = "Site encontrado"
        cv_color = "#3498db"

    return f'''
    <table width="100%" cellpadding="0" cellspacing="0" border="0" class="card"
           style="background:#1a2b3c;">
      <tr>
        <td class="card-hdr-td" style="background:{e["header_bg"]};">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td>
                <span class="badge" style="background:{e["badge_bg"]};color:{e["badge_txt"]};">{e["label"]}</span>
                <span class="card-num">#{idx}/{total}</span>
              </td>
              <td align="right">
                <span class="card-cv" style="color:{cv_color};">{cv_status}</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td class="card-title-td">
          <a href="{link_vaga}" class="card-link">{titulo}</a>
        </td>
      </tr>
      <tr>
        <td class="card-fields-td">
          <table cellpadding="0" cellspacing="0" border="0" width="100%">
            {campos}
            {descricao_html}
            {contato_descoberto_html}
            <tr>
              <td colspan="2" style="padding-top:12px;">
                <a href="{btn_url}" class="btn" style="background:{e["accent"]};">{btn_label}</a>
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
    n = len(vagas)
    return f'''
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="margin-bottom:24px;">
      <tr>
        <td class="sec-hdr-td" style="border-left:4px solid {e["accent"]};">
          <span class="sec-title">{fonte}</span>
          <span class="sec-count">{n} vaga{"s" if n != 1 else ""}</span>
        </td>
      </tr>
      <tr><td>{cards}</td></tr>
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

    # Agrupar por fonte
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

    # Contadores de contato
    n_email_direto = sum(
        1 for v in vagas
        if v.get("tipo_contato") == "email" and "@" in v.get("link_contato", "")
    )
    n_contato_descoberto = sum(
        1 for v in vagas
        if v.get("contato_descoberto", {}).get("email") or v.get("contato_descoberto", {}).get("site")
    )

    # Sumário por fonte
    resumo_rows = ""
    for f in fontes_ordem:
        lst = por_fonte.get(f, [])
        if lst:
            e = _estilo(f)
            resumo_rows += f'''
            <tr>
              <td class="sumario-td-l">
                <span class="badge" style="background:{e["badge_bg"]};color:{e["badge_txt"]};margin-right:8px;">{e["label"]}</span>
              </td>
              <td class="sumario-td-r">{len(lst)}</td>
            </tr>'''

    if n_email_direto > 0 or n_contato_descoberto > 0:
        resumo_rows += f'''
        <tr class="sumario-sep">
          <td class="sumario-td-l"><span style="color:#27ae60;font-size:11px;">&#9993; Email direto dispon&#237;vel</span></td>
          <td class="sumario-td-r" style="color:#27ae60;">{n_email_direto}</td>
        </tr>'''
        if n_contato_descoberto > 0:
            resumo_rows += f'''
            <tr>
              <td class="sumario-td-l"><span style="color:#2ecc71;font-size:11px;">Contato descoberto</span></td>
              <td class="sumario-td-r" style="color:#2ecc71;">{n_contato_descoberto}</td>
            </tr>'''

    # Bloco de erros
    erros_html = ""
    if erros:
        items = "".join(f'<li style="margin-bottom:3px;">{err}</li>' for err in erros)
        erros_html = f'''
        <table width="100%" cellpadding="0" cellspacing="0" border="0" class="avisos">
          <tr>
            <td class="avisos-td">
              <div class="avisos-lbl">Avisos do sistema</div>
              <ul class="avisos-ul">{items}</ul>
            </td>
          </tr>
        </table>'''

    # Indicador de parte
    parte_html = ""
    if total_partes > 1:
        parte_html = f'<div style="text-align:center;color:#4a6a8a;font-size:12px;margin-bottom:16px;font-family:Arial,sans-serif;">Parte {parte} de {total_partes}</div>'

    # Corpo
    if not vagas:
        corpo = '''
        <td class="vazio-td">
          <div class="vazio-icon">&#128269;</div>
          <div class="vazio-title">Nenhuma vaga nova hoje</div>
          <div class="vazio-sub">Pares monitorados: PT &#8596; EN &nbsp;&#183;&nbsp; PT &#8596; ES &nbsp;&#183;&nbsp; EN &#8596; ES</div>
        </td>'''
    else:
        corpo = f'''
        <td class="body-td">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" class="sumario">
            <tr><td colspan="2" class="sumario-hdr">
              <span class="sumario-lbl">Resumo por fonte</span>
            </td></tr>
            {resumo_rows}
            <tr class="sumario-sep">
              <td class="sumario-total-l">Total de vagas novas</td>
              <td class="sumario-total-r">{total}</td>
            </tr>
          </table>
          {parte_html}
          {secoes_html}
          {erros_html}
        </td>'''

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Alerta de Vagas de Tradu&#231;&#227;o &#8212; {hoje}</title>
  <style>{CSS_GLOBAL}</style>
</head>
<body>
  <table width="100%" cellpadding="0" cellspacing="0" border="0" class="wrap">
    <tr>
      <td align="center">
        <table width="640" cellpadding="0" cellspacing="0" border="0" class="inner">

          <!-- HEADER -->
          <tr>
            <td class="hdr">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <div class="hdr-label">ALERTA DI&#193;RIO &middot; TRADU&#199;&#195;O</div>
                    <div class="hdr-title">Vagas de Tradu&#231;&#227;o</div>
                    <div class="hdr-sub">PT &middot; EN &middot; ES &#8212; {hoje}</div>
                  </td>
                  <td align="right" valign="top">
                    <div class="hdr-count-box">
                      <div class="hdr-count-n">{total}</div>
                      <div class="hdr-count-lbl">nova{"s" if total != 1 else ""}</div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- CORPO -->
          <tr>{corpo}</tr>

          <!-- FOOTER -->
          <tr>
            <td class="ftr">
              <div class="ftr-txt">
                <strong class="ftr-name">Hudson Borges</strong>
                &nbsp;&middot;&nbsp; Sistema de Alertas de Tradu&#231;&#227;o<br>
                Fontes: ProZ.com &nbsp;&middot;&nbsp; Translators Caf&#233;
                &nbsp;&middot;&nbsp; Translation Directory<br>
                Pares: PT &#8596; EN &nbsp;&middot;&nbsp; PT &#8596; ES &nbsp;&middot;&nbsp; EN &#8596; ES<br>
                <span class="ftr-green">&#9993; Contatos diretos descobertos automaticamente via busca reversa</span>
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
    Com o template otimizado (CSS em classes), o HTML de 63 vagas fica ~80KB,
    dentro do limite do manus-mcp-cli. Não é mais necessário dividir em partes.
    """
    hoje = date.today().strftime("%d/%m/%Y")
    total = len(vagas)

    if total == 0:
        assunto = f"[Tradu\u00e7\u00e3o] Nenhuma vaga nova \u2014 {hoje}"
        html = gerar_html_email([], erros)
        return [{"messages": [{"to": [destinatario], "subject": assunto, "content": html}]}]

    lotes = [vagas[i:i + max_por_email] for i in range(0, total, max_por_email)]
    total_partes = len(lotes)
    payloads = []

    for idx, lote in enumerate(lotes, 1):
        if total_partes == 1:
            assunto = f"[Tradu\u00e7\u00e3o] {total} nova(s) vaga(s) \u2014 {hoje}"
        else:
            assunto = f"[Tradu\u00e7\u00e3o] {total} nova(s) vaga(s) \u2014 {hoje} ({idx}/{total_partes})"

        html = gerar_html_email(lote, erros if idx == 1 else [], parte=idx, total_partes=total_partes)
        payloads.append({"messages": [{"to": [destinatario], "subject": assunto, "content": html}]})

    return payloads


if __name__ == "__main__":
    # Gera preview HTML com dados de teste
    vagas_teste = [
        {
            "titulo": "English to Brazilian Portuguese Freelance Translators Needed",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN \u2192 PT",
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
                "fonte_busca": "p\u00e1gina de contato",
            },
        },
        {
            "titulo": "Simultaneous Interpreters Needed EN/PT/ES",
            "idioma_origem": "EN", "idioma_destino": "PT",
            "par_display": "EN \u2192 PT",
            "area": "Legal",
            "contagem_palavras": "",
            "formato": "",
            "preco_palavra": "0.18 USD per word",
            "pais": "Brazil",
            "empresa": "Skrivanek Brasil",
            "prazo": "15/04/2026",
            "data_publicacao": "18/03/2026",
            "tipo_contato": "email",
            "link_contato": "info@skrivanek.com",
            "link_vaga": "https://www.translatorscafe.com/cafe/SelectedJob.asp?Job=374422",
            "fonte": "Translators Caf\u00e9",
            "detalhes": "We need experienced simultaneous interpreters for a legal conference.",
            "contato_pessoa": "Maria Silva",
            "contato_descoberto": {},
        },
        {
            "titulo": "Voice Over Directors and Transcreators based in Canada",
            "idioma_origem": "EN", "idioma_destino": "ES",
            "par_display": "EN \u2192 ES",
            "area": "Government / Politics",
            "contagem_palavras": "",
            "formato": "",
            "preco_palavra": "",
            "pais": "",
            "empresa": "",
            "prazo": "01/04/2026",
            "data_publicacao": "18/03/2026",
            "tipo_contato": "URL",
            "link_contato": "https://www.proz.com/translation-jobs/2231906",
            "link_vaga": "https://www.proz.com/translation-jobs/2231906",
            "fonte": "ProZ.com",
            "detalhes": "We are looking for voice over directors and transcreators based in Canada.",
            "contato_pessoa": "",
            "contato_descoberto": {
                "site": "https://www.proz.com",
                "fonte_busca": "homepage",
            },
        },
    ]
    html = gerar_html_email(vagas_teste, [])
    with open("/tmp/email_preview_v2.html", "w", encoding="utf-8") as f:
        f.write(html)
    size = len(html.encode("utf-8"))
    print(f"Preview gerado: /tmp/email_preview_v2.html ({size//1024} KB)")
    print(f"Redução estimada para 63 vagas: de ~307KB para ~{size * 21 // 1024}KB")
