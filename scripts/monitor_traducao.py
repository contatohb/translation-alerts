#!/usr/bin/env python3
"""
Monitor de vagas de tradução em ProZ.com, Translators Café e Translation Directory.

Combinações de idiomas monitoradas:
  - Português ↔ Inglês  (PT/EN, EN/PT)
  - Português ↔ Espanhol (PT/ES, ES/PT)
  - Inglês    ↔ Espanhol (EN/ES, ES/EN)

Cada vaga retornada contém (todos os campos em todas as fontes, quando disponíveis):
  titulo, idioma_origem, idioma_destino, par_display, area,
  contagem_palavras, formato, prazo, data_publicacao,
  tipo_contato, link_contato, link_vaga, fonte,
  detalhes, contato_pessoa, empresa, pais, preco_palavra,
  contato_descoberto (dict: site, email, fonte_busca)
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from html import unescape
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}
TIMEOUT = 25
SLEEP   = 0.8

# ─────────────────────────────────────────────────────────────────
# Credenciais do Translators Café
# ─────────────────────────────────────────────────────────────────
import os as _os
TC_USERNAME   = "hudsonborges"
TC_PASSWORD   = "Raios25_"
TC_LOGIN_URL  = "https://www.translatorscafe.com/cafe/login.asp"
TC_JOBS_URL   = "https://www.translatorscafe.com/cafe/SearchJobs.asp?Mode=Selected"
TC_BASE_URL   = "https://www.translatorscafe.com"
TC_RSS_URL    = "https://www.translatorscafe.com/tcUtils/EN/jobs/rss.aspx"
# Cookie LGN persistente do TC — injetado via secret TC_COOKIE_LGN no GitHub Actions
TC_COOKIE_LGN = _os.environ.get("TC_COOKIE_LGN", "").strip()

# Pares de idiomas do ProZ com filtro de idioma (sl=source, tl=target)
PROZ_LANG_PAIRS = [
    ("por", "eng"),  # PT → EN
    ("eng", "por"),  # EN → PT
    ("por", "esl"),  # PT → ES
    ("esl", "por"),  # ES → PT
    ("eng", "esl"),  # EN → ES
    ("esl", "eng"),  # ES → EN
]

# ─────────────────────────────────────────────────────────────────
# Mapeamento de idiomas
# ─────────────────────────────────────────────────────────────────
LANGUAGE_MAP: Dict[str, str] = {
    "portuguese": "PT", "português": "PT", "portugues": "PT",
    "brazilian portuguese": "PT", "portuguese (brazil)": "PT",
    "portuguese (european)": "PT", "portuguese (portugal)": "PT",
    "english": "EN",
    "spanish": "ES", "español": "ES", "espanol": "ES",
    "latin american spanish": "ES", "castilian": "ES",
}

ACCEPTED_PAIRS = {
    ("PT", "EN"), ("EN", "PT"),
    ("PT", "ES"), ("ES", "PT"),
    ("EN", "ES"), ("ES", "EN"),
}

_ABBREV_MAP: Dict[str, str] = {
    "pt": "PT", "pt-br": "PT", "pt-pt": "PT",
    "en": "EN", "en-us": "EN", "en-gb": "EN",
    "es": "ES", "es-la": "ES", "es(la)": "ES",
}

_MESES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DIAS_EN = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}

_EMAILS_IGNORAR = {
    "sentry", "example", "test", "noreply", "no-reply", "donotreply",
    "privacy", "gdpr", "w3.org", "schema.org", "google", "facebook",
    "twitter", "linkedin", "youtube", "apple", "microsoft", "amazon",
    "cloudflare", "wordpress", "jquery", "bootstrap", "fontawesome",
    "spoofing", "abuse", "spam", "phishing", "security", "postmaster",
    "webmaster", "hostmaster", "mailer-daemon", "bounce", "unsubscribe",
}


# ─────────────────────────────────────────────────────────────────
# Utilitários gerais
# ─────────────────────────────────────────────────────────────────

def _formatar_data(texto: str) -> str:
    """Converte qualquer formato de data para dd/mm/aaaa."""
    if not texto:
        return ""
    t = texto.strip()
    t_clean = re.sub(r'^(?:' + '|'.join(_DIAS_EN) + r'),?\s*', '', t, flags=re.IGNORECASE)

    # MM/DD/YYYY americano
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', t_clean)
    if m:
        mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mm > 12:
            dd, mm = mm, dd
        return f"{dd:02d}/{mm:02d}/{yyyy}"

    # "17 Mar 2026"
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', t_clean)
    if m:
        dd, mes_str, yyyy = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
        mm = _MESES_EN.get(mes_str, 0)
        if mm:
            return f"{dd:02d}/{mm:02d}/{yyyy}"

    # "March 18, 2026" ou "March 18"
    m = re.match(r'^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(?:at\s+\d+:\d+)?)?,?\s*(\d{4})?', t_clean)
    if m:
        mes_str, dd = m.group(1).lower()[:3], int(m.group(2))
        yyyy = int(m.group(3)) if m.group(3) else datetime.now().year
        mm = _MESES_EN.get(mes_str, 0)
        if mm:
            return f"{dd:02d}/{mm:02d}/{yyyy}"

    # DD/MM/YYYY já correto
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})', t_clean)
    if m:
        return t_clean[:10]

    return t


def _normalizar_idioma(texto: str) -> str:
    if not texto:
        return ""
    t = texto.lower().strip()
    for chave, codigo in LANGUAGE_MAP.items():
        if t == chave or t.startswith(chave):
            return codigo
    if len(t) <= 5 and t in _ABBREV_MAP:
        return _ABBREV_MAP[t]
    return ""


def _extrair_par_idiomas_titulo(texto: str) -> Tuple[str, str]:
    if not texto:
        return "", ""
    t_lower = texto.lower()

    m = re.search(r'\b(en|pt|es)\s*[-–>]\s*(en|pt|es)\b', t_lower)
    if m:
        src = _normalizar_idioma(m.group(1))
        tgt = _normalizar_idioma(m.group(2))
        if src and tgt and src != tgt:
            return src, tgt

    m = re.search(r'(\w+(?:\s+\w+)?)\s+(?:to|into|→|>)\s+(\w+(?:\s+\w+)?)', texto, re.IGNORECASE)
    if m:
        src = _normalizar_idioma(m.group(1))
        tgt = _normalizar_idioma(m.group(2))
        if src and tgt and src != tgt:
            return src, tgt

    m = re.search(r'(\w+(?:\s+\w+)?)\s*<>\s*(\w+(?:\s+\w+)?)', texto, re.IGNORECASE)
    if m:
        src = _normalizar_idioma(m.group(1))
        tgt = _normalizar_idioma(m.group(2))
        if src and tgt and src != tgt:
            return src, tgt

    m_from = re.search(r'from\s+(\w+)', t_lower)
    m_into = re.search(r'(?:into|to)\s+(\w+)', t_lower)
    if m_from and m_into:
        src = _normalizar_idioma(m_from.group(1))
        tgt = _normalizar_idioma(m_into.group(1))
        if src and tgt and src != tgt:
            return src, tgt

    return "", ""


def _parse_par_tc(lang_text: str) -> Tuple[str, str]:
    m = re.match(r'^(.+?)>(.+)$', lang_text.strip())
    if m:
        src = _normalizar_idioma(m.group(1).strip())
        tgt = _normalizar_idioma(m.group(2).strip())
        return src, tgt
    return "", ""


def _par_relevante(origem: str, destino: str) -> bool:
    if not origem or not destino:
        return False
    return (origem, destino) in ACCEPTED_PAIRS


def _extrair_contagem_palavras(texto: str) -> str:
    m = re.search(r'([\d,\.]+)\s*(?:word|palavra|word count|wc)', texto, re.IGNORECASE)
    if m:
        return m.group(1).replace(",", ".")
    return ""


def _extrair_formato(texto: str) -> str:
    formatos = ["Microsoft Word", "PDF", "Excel", "PowerPoint", "InDesign",
                "HTML", "XML", "XLIFF", "TMX", "TXT"]
    t = texto.lower()
    encontrados = [f for f in formatos if f.lower() in t]
    return ", ".join(encontrados) if encontrados else ""


def _extrair_prazo(texto: str) -> str:
    m = re.search(
        r'(?:delivery\s+date|deadline|prazo|até|until|by|open\s+for)\s*:?\s*([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+at\s+\d+:\d+)?(?:,?\s*\d{4})?)',
        texto, re.IGNORECASE
    )
    if m:
        return _formatar_data(m.group(1).strip())
    m = re.search(r'open\s+for\s+(\d+)\s+more\s+days?', texto, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        return (datetime.now() + timedelta(days=days)).strftime("%d/%m/%Y")
    m = re.search(r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+at\s+\d+:\d+)?)', texto, re.IGNORECASE)
    if m:
        return _formatar_data(m.group(1).strip())
    return ""


def _extrair_area(texto: str) -> str:
    areas_conhecidas = [
        "Legal", "Medical", "Technical", "Financial", "Literary",
        "Marketing", "IT", "Science", "General", "Law", "Patents",
        "Business", "Engineering", "Tourism", "Education",
        "Broadcast", "Journalism", "Pharmaceutical", "Life Sciences",
        "Automotive", "Aerospace", "Mining", "Energy", "Environment",
        "Psychology", "Social Sciences", "Well-being", "Mental Health",
    ]
    t = texto.lower()
    encontradas = [a for a in areas_conhecidas if a.lower() in t]
    return ", ".join(encontradas[:3]) if encontradas else ""


def _extrair_preco(texto: str) -> str:
    """Extrai preço/palavra do texto da descrição."""
    m = re.search(
        r'(?:rate|price|pay|budget|offer)[^.]{0,50}?(\d[\d,\.]+\s*(?:USD|EUR|GBP|BRL|CAD|AUD|CHF)?(?:\s*/?\s*word|\s*per\s*word|\s*per\s*source\s*word)?)',
        texto, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(r'(\d[\d,\.]+\s*(?:USD|EUR|GBP|BRL|CAD|AUD)\s*/?\s*word)', texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'(\d[\d,\.]+\s*(?:USD|EUR|GBP|BRL|CAD|AUD)\s+per\s+(?:word|source\s+word))', texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extrair_empresa(texto: str) -> str:
    """Extrai nome de empresa do texto da descrição."""
    m = re.search(
        r'([A-Z][A-Za-z\s&\-\.]+(?:Ltd\.?|Inc\.?|LLC|Group|Services|Solutions|Global|Worldwide|Agency|Company|Corp\.?|GmbH|S\.A\.|B\.V\.|Limited))',
        texto
    )
    if m:
        return m.group(1).strip()
    return ""


# ─────────────────────────────────────────────────────────────────
# Busca reversa de contatos
# ─────────────────────────────────────────────────────────────────

def _emails_validos(emails: List[str]) -> List[str]:
    return [
        e for e in emails
        if not any(skip in e.lower() for skip in _EMAILS_IGNORAR)
        and len(e) < 80
        and "." in e.split("@")[-1]
    ]


# Domínios suspeitos, de parking ou sem conteúdo real
_DOMINIOS_SUSPEITOS = {
    "godaddy.com", "namecheap.com", "sedo.com", "dan.com", "hugedomains.com",
    "afternic.com", "parkingcrew.net", "bodis.com", "above.com", "undeveloped.com",
    "domainmarket.com", "buydomains.com", "flippa.com", "brandbucket.com",
    "squarespace.com", "wix.com", "weebly.com", "wordpress.com",
    "blogspot.com", "tumblr.com", "medium.com",
    # Domínios de parking confirmados manualmente
    "weare.com",  # parking da First Place Internet, Inc. — sem relação com tradução
}

# Indicadores de página em branco, parking ou erro
_INDICADORES_INVALIDOS = [
    "domain for sale", "buy this domain", "this domain is for sale",
    "domain parking", "parked domain", "coming soon", "under construction",
    "website coming soon", "em construção", "em breve",
    "403 forbidden", "404 not found", "access denied",
    "this site can't be reached", "err_connection",
    "godaddy", "namecheap", "sedo.com", "dan.com",
    # Indicadores de parking identificados em weare.com e similares
    "first place internet", "motels.com", "book discount hotel",
    "this domain is parked", "this page is parked",
]


def _validar_site(url: str, timeout: int = 10) -> Dict[str, object]:
    """
    Acessa o site e verifica se é real, funcional e não suspeito.
    Retorna dict com: ok (bool), url_final (str), soup (BeautifulSoup|None),
    motivo_descarte (str|None).
    """
    resultado = {"ok": False, "url_final": url, "soup": None, "motivo_descarte": None}
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        url_final = r.url
        resultado["url_final"] = url_final

        # Verificar status HTTP
        if r.status_code in (403, 404, 410, 500, 502, 503):
            resultado["motivo_descarte"] = f"HTTP {r.status_code}"
            return resultado

        if r.status_code != 200:
            resultado["motivo_descarte"] = f"HTTP {r.status_code}"
            return resultado

        # Verificar domínio suspeito
        dominio_final = urlparse(url_final).netloc.lower().replace("www.", "")
        if any(d in dominio_final for d in _DOMINIOS_SUSPEITOS):
            resultado["motivo_descarte"] = f"domínio suspeito ({dominio_final})"
            return resultado

        # Verificar conteúdo mínimo
        texto = r.text.lower()
        if len(r.text) < 200:
            resultado["motivo_descarte"] = "página em branco ou muito curta"
            return resultado

        for indicador in _INDICADORES_INVALIDOS:
            if indicador in texto:
                resultado["motivo_descarte"] = f"conteúdo suspeito: '{indicador}'"
                return resultado

        # Site válido
        resultado["ok"] = True
        resultado["soup"] = BeautifulSoup(r.content, "html.parser")
        return resultado

    except requests.exceptions.ConnectionError:
        resultado["motivo_descarte"] = "conexão recusada"
    except requests.exceptions.Timeout:
        resultado["motivo_descarte"] = "timeout"
    except Exception as exc:
        resultado["motivo_descarte"] = f"erro: {exc}"
    return resultado


def _extrair_emails_pagina(url: str, timeout: int = 8) -> List[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return []
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r.text)
        return _emails_validos(list(set(emails)))[:3]
    except Exception:
        return []


def _encontrar_pagina_contato(base_url: str, soup: BeautifulSoup = None, timeout: int = 8) -> Optional[str]:
    try:
        if soup is None:
            r = requests.get(base_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.content, "html.parser")
        contact_kws = ['contact', 'contato', 'kontakt', 'get-in-touch', 'reach-us',
                       'reach-out', 'about', 'sobre', 'team', 'equipe']
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").lower()
            text = a.get_text(strip=True).lower()
            for kw in contact_kws:
                if kw in href or kw in text:
                    full_url = urljoin(base_url, a.get("href", ""))
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        return full_url
        return None
    except Exception:
        return None


def _construir_url_empresa(nome_empresa: str) -> Optional[str]:
    if not nome_empresa or len(nome_empresa) < 3:
        return None
    slug = re.sub(r'[^a-zA-Z0-9]', '', nome_empresa.lower())
    if len(slug) < 3:
        return None
    return f"https://www.{slug}.com"


def buscar_contato_empresa(nome_empresa: str, url_empresa: str = "", pais: str = "") -> Dict[str, str]:
    """
    Tenta encontrar email e site de contato de uma empresa.
    Valida o site antes de incluir: sites em branco, quebrados ou suspeitos são descartados.
    Retorna dict com: site (str), email (str), fonte_busca (str), valido (bool).
    Retorna {} se o site for inválido ou não encontrado.
    """
    if not nome_empresa and not url_empresa:
        return {}

    # Determinar URL a testar
    url_tentativa = url_empresa if url_empresa else _construir_url_empresa(nome_empresa)
    if not url_tentativa:
        return {}

    # Validar o site
    validacao = _validar_site(url_tentativa)
    if not validacao["ok"]:
        logger.debug(
            f"Site descartado para '{nome_empresa}' ({url_tentativa}): "
            f"{validacao['motivo_descarte']}"
        )
        return {}  # Site inválido — vaga não entra na newsletter

    soup = validacao["soup"]
    url_final = validacao["url_final"]
    resultado = {"site": url_final, "valido": True}

    # 1. Buscar emails diretamente na homepage
    emails_homepage = _emails_validos(
        re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', soup.get_text())
    )
    if emails_homepage:
        resultado["email"] = emails_homepage[0]
        resultado["fonte_busca"] = "homepage"
        return resultado

    # 2. Buscar links mailto: explícitos
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip()
            if email and "@" in email and not any(s in email.lower() for s in _EMAILS_IGNORAR):
                resultado["email"] = email
                resultado["fonte_busca"] = "mailto homepage"
                return resultado

    # 3. Buscar página de contato
    contact_url = _encontrar_pagina_contato(url_final, soup)
    if contact_url:
        emails_contato = _extrair_emails_pagina(contact_url)
        if emails_contato:
            resultado["email"] = emails_contato[0]
            resultado["fonte_busca"] = "página de contato"
            return resultado
        # Buscar mailto na página de contato
        try:
            r_c = requests.get(contact_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r_c.status_code == 200:
                soup_c = BeautifulSoup(r_c.content, "html.parser")
                for a in soup_c.find_all("a", href=True):
                    href = a.get("href", "")
                    if href.startswith("mailto:"):
                        email = href.replace("mailto:", "").split("?")[0].strip()
                        if email and "@" in email and not any(s in email.lower() for s in _EMAILS_IGNORAR):
                            resultado["email"] = email
                            resultado["fonte_busca"] = "mailto página de contato"
                            return resultado
        except Exception:
            pass

    # Site válido mas sem email encontrado
    resultado["fonte_busca"] = "site (sem email)"
    return resultado


# ─────────────────────────────────────────────────────────────────
# Scraping do ProZ.com
# ─────────────────────────────────────────────────────────────────

def _scrape_proz() -> Tuple[List[Dict], List[str]]:
    """Faz scraping das vagas do ProZ.com usando URLs filtradas por par de idiomas."""
    vagas: List[Dict] = []
    erros: List[str] = []
    seen_urls: set = set()

    for sl, tl in PROZ_LANG_PAIRS:
        url = f"https://connect.proz.com/language-jobs?sl={sl}&tl={tl}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            erros.append(f"ProZ.com ({sl}→{tl}): erro de acesso — {exc}")
            continue
        time.sleep(SLEEP)

        soup = BeautifulSoup(resp.content, "html.parser")

        for a in soup.find_all("a", class_="job_title_link", href=True):
            href = a.get("href", "")
            titulo = a.get_text(strip=True)

            if not titulo or len(titulo) < 8:
                continue
            if not re.search(r'proz\.com/translation-jobs/\d+', href):
                continue

            job_url = href if href.startswith("http") else f"https://www.proz.com{href}"
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            # Descrição completa via data-content
            descricao_raw = unescape(a.get("data-content", ""))
            descricao = re.sub(r'<[^>]+>', ' ', descricao_raw).strip()
            descricao = re.sub(r'\s+', ' ', descricao)[:600]

            # Subir para o jobs__result-wrap
            result_wrap = None
            parent = a.parent
            for _ in range(20):
                if parent and parent.get("class") and any("result-wrap" in c for c in parent.get("class", [])):
                    result_wrap = parent
                    break
                parent = parent.parent if parent else None

            # Pares de idiomas, área e palavras via tooltips
            pares_relevantes: List[Tuple[str, str]] = []
            area = ""
            contagem_palavras = ""
            formato = ""
            data_pub = ""
            prazo = ""

            if result_wrap:
                full_text = result_wrap.get_text(separator="\n", strip=True)

                # Palavras e formato do container
                m_wc = re.search(r'Word count:\s*([\d,\.]+)', full_text, re.IGNORECASE)
                if m_wc:
                    contagem_palavras = m_wc.group(1).replace(",", ".")
                m_fmt = re.search(r'Format:\s*([^\n]+)', full_text, re.IGNORECASE)
                if m_fmt:
                    formato = m_fmt.group(1).strip()

                # Data de publicação
                m_posted = re.search(r'Posted\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2})', full_text, re.IGNORECASE)
                if m_posted:
                    data_pub = _formatar_data(m_posted.group(1).strip())

                # Prazo via data-title="Delivery date"
                delivery_el = result_wrap.find(attrs={"data-title": "Delivery date"})
                if delivery_el:
                    parent_el = delivery_el.parent
                    if parent_el:
                        prazo_text = parent_el.get_text(strip=True)
                        prazo = _formatar_data(prazo_text)

                # Prazo via "Open for N more days"
                if not prazo:
                    m_days = re.search(r'Open\s+for\s+(\d+)\s+more\s+days?', full_text, re.IGNORECASE)
                    if m_days:
                        prazo = (datetime.now() + timedelta(days=int(m_days.group(1)))).strftime("%d/%m/%Y")

                # Tooltips: pares de idiomas e áreas
                for span in result_wrap.find_all("span", attrs={"data-toggle": "tooltip"}):
                    title_attr = unescape(span.get("title", ""))
                    text_span = span.get_text(strip=True)

                    if "language pair" in text_span.lower():
                        langs = re.findall(r'<li>([^<]+)</li>', title_attr)
                        for lang_pair in langs:
                            src, tgt = _extrair_par_idiomas_titulo(lang_pair)
                            if _par_relevante(src, tgt):
                                pares_relevantes.append((src, tgt))

                    elif "field" in text_span.lower():
                        fields = re.findall(r'<li>([^<]+)</li>', title_attr)
                        area = ", ".join(fields[:3])

                # Par de idiomas direto no li (sem tooltip)
                for li in result_wrap.find_all("li"):
                    if not li.find("span"):
                        text_li = li.get_text(strip=True)
                        src, tgt = _extrair_par_idiomas_titulo(text_li)
                        if _par_relevante(src, tgt):
                            pares_relevantes.append((src, tgt))

            # Fallback: par do título e descrição
            if not pares_relevantes:
                src, tgt = _extrair_par_idiomas_titulo(titulo)
                if _par_relevante(src, tgt):
                    pares_relevantes.append((src, tgt))
            if not pares_relevantes:
                src, tgt = _extrair_par_idiomas_titulo(descricao)
                if _par_relevante(src, tgt):
                    pares_relevantes.append((src, tgt))

            if not pares_relevantes:
                continue

            # Deduplicar pares
            pares_unicos = list(dict.fromkeys(pares_relevantes))
            origem, destino = pares_unicos[0]
            par_display = " | ".join(f"{s}→{t}" for s, t in pares_unicos) if len(pares_unicos) > 1 else f"{origem} → {destino}"

            # Área: fallback para descrição + título
            if not area:
                area = _extrair_area(descricao + " " + titulo)

            # Palavras: fallback para descrição
            if not contagem_palavras:
                contagem_palavras = _extrair_contagem_palavras(descricao)

            # Formato: fallback para descrição
            if not formato:
                formato = _extrair_formato(descricao)

            # Preço: extrair da descrição
            preco = _extrair_preco(descricao)

            # Empresa: extrair da descrição
            empresa = _extrair_empresa(descricao)

            # Email direto na descrição
            email_desc = ""
            m_email = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', descricao)
            if m_email and "HIDDEN" not in descricao[max(0, m_email.start()-5):m_email.end()+5]:
                email_desc = m_email.group(0)

            # Tipo de contato
            tipo_contato = "email" if email_desc else "ProZ.com"
            link_contato = email_desc if email_desc else job_url

            # Busca reversa de contato se empresa conhecida e sem email direto
            contato_descoberto = {}
            if empresa and not email_desc:
                contato_descoberto = buscar_contato_empresa(empresa)

            vagas.append({
                "titulo": titulo,
                "idioma_origem": origem,
                "idioma_destino": destino,
                "par_display": par_display,
                "area": area,
                "contagem_palavras": contagem_palavras,
                "formato": formato,
                "prazo": prazo,
                "tipo_contato": tipo_contato,
                "link_contato": link_contato,
                "link_vaga": job_url,
                "fonte": "ProZ.com",
                "data_publicacao": data_pub,
                "detalhes": descricao,
                "contato_pessoa": "",
                "empresa": empresa,
                "pais": "",  # Não disponível na lista pública do ProZ
                "preco_palavra": preco,
                "contato_descoberto": contato_descoberto,
            })

    logger.info(f"ProZ.com: {len(vagas)} vaga(s) relevante(s) encontrada(s)")
    return vagas, erros


# ─────────────────────────────────────────────────────────────────
# Scraping do Translators Café (com login + visita a páginas de detalhes)
# ─────────────────────────────────────────────────────────────────

def _tc_fazer_login(session: requests.Session) -> bool:
    try:
        resp = session.get(TC_LOGIN_URL, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 403:
            logger.warning("Translators Café: acesso negado (403) na página de login")
            return False
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "html.parser")
        redir_input = soup.find("input", {"name": "RedirectionString"})
        redir_val = redir_input["value"] if redir_input else "https://www.translatorscafe.com/cafe/"

        login_data = {
            "RedirectionString": redir_val,
            "Flag": "Login",
            "UserName": TC_USERNAME,
            "Password": TC_PASSWORD,
            "AutoLogin": "on",
        }
        time.sleep(1.5)
        resp2 = session.post(
            TC_LOGIN_URL,
            data=login_data,
            headers={
                **HEADERS,
                "Referer": TC_LOGIN_URL,
                "Origin": "https://www.translatorscafe.com",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        if "Hudson Borges" in resp2.text or "quicklook" in resp2.url or "My Caf" in resp2.text or "Logout" in resp2.text:
            logger.info("Translators Café: login realizado com sucesso")
            return True
        elif resp2.status_code == 403:
            logger.warning("Translators Café: acesso negado (403) após POST de login")
            return False
        else:
            logger.warning("Translators Café: login pode ter falhado")
            return False

    except Exception as exc:
        logger.error(f"Translators Café: erro no login — {exc}")
        return False


def _tc_extrair_detalhes(session: requests.Session, job_id: str, url_vaga: str) -> Dict[str, str]:
    """
    Visita a página de detalhes de uma vaga do TC e extrai todos os campos disponíveis:
    país, empresa, URL da empresa, email/site de contato, especialização, tipo de serviço,
    idiomas, descrição completa e data de publicação.
    """
    campos = {
        "pais": "", "empresa": "", "url_empresa": "", "email_contato": "",
        "site_contato": "", "area": "", "tipo_servico": "", "idiomas": "",
        "descricao": "", "data_publicacao": "",
    }

    try:
        time.sleep(SLEEP)
        resp = session.get(url_vaga, headers={**HEADERS, "Referer": TC_JOBS_URL}, timeout=TIMEOUT)
        if resp.status_code != 200:
            logger.debug(f"TC detalhe {job_id}: status {resp.status_code}")
            return campos

        soup = BeautifulSoup(resp.content, "html.parser")
        html = resp.text

        # 1. Data de publicação — "Job #374422posted on3/18/2026at11:21GMT"
        job_header = soup.find(string=re.compile(r'Job #\d+'))
        if job_header:
            parent_text = job_header.parent.get_text(strip=True)
            m_date = re.search(r'posted on\s*(\d+/\d+/\d+)', parent_text, re.IGNORECASE)
            if m_date:
                campos["data_publicacao"] = _formatar_data(m_date.group(1))

        # 2. País — flag img com alt de 2 letras maiúsculas seguida de texto
        country_img = soup.find("img", alt=re.compile(r'^[A-Z]{2}$'))
        if country_img:
            parent = country_img.parent
            country_text = parent.get_text(strip=True)
            # Remover o código da flag (2 letras) e pegar o nome do país
            country_clean = re.sub(r'^[A-Z]{2}\s*', '', country_text).strip()
            if country_clean:
                campos["pais"] = country_clean

        # 3. Empresa — classe sjCo
        co_el = soup.find(class_=lambda c: c and "sjCo" in c)
        if co_el:
            company_link = co_el.find("a")
            if company_link:
                campos["empresa"] = company_link.get_text(strip=True)
                campos["url_empresa"] = company_link.get("href", "")

        # 4. Email/site de contato — sjEmailInfo
        email_el = soup.find(class_="sjEmailInfo")
        if email_el:
            email_link = email_el.find("a")
            if email_link:
                href = email_link.get("href", "")
                text = email_link.get_text(strip=True)
                if "@" in text or (href and "@" in href):
                    campos["email_contato"] = text if "@" in text else href.replace("mailto:", "")
                elif href.startswith("http"):
                    campos["site_contato"] = href
                else:
                    # É um domínio sem mailto — construir URL
                    domain = text.strip()
                    if "." in domain and not domain.startswith("http"):
                        campos["site_contato"] = f"https://{domain}"
                    elif href.startswith("http"):
                        campos["site_contato"] = href

        # 5. Campos sjParam
        for el in soup.find_all(class_="sjParam"):
            text = el.get_text(separator=" ", strip=True)
            if "Job type:" in text:
                campos["tipo_servico"] = text.replace("Job type:", "").strip()
                # Limpar vírgulas e espaços extras
                campos["tipo_servico"] = re.sub(r'\s+', ' ', campos["tipo_servico"]).strip(", ")
            elif "Languages:" in text:
                campos["idiomas"] = text.replace("Languages:", "").strip()
            elif "Specialization:" in text:
                campos["area"] = text.replace("Specialization:", "").strip()

        # 6. Descrição — bloco sjParam que contém "Job description:"
        desc_parent = None
        for el in soup.find_all(class_="sjParam"):
            text = el.get_text(separator=" ", strip=True)
            if "Job description:" in text:
                desc_parent = el.parent
                break

        if desc_parent:
            desc_text = desc_parent.get_text(separator=" ", strip=True)
            m_desc = re.search(r'Job description:\s*(.+?)(?:\s*Job #|\s*Before accepting|$)', desc_text, re.IGNORECASE | re.DOTALL)
            if m_desc:
                campos["descricao"] = m_desc.group(1).strip()[:600]

        return campos

    except Exception as exc:
        logger.debug(f"TC detalhe {job_id}: erro — {exc}")
        return campos


def _scrape_translators_cafe() -> Tuple[List[Dict], List[str]]:
    """
    Faz scraping das vagas do Translators Café.

    Estratégia (em ordem de preferência):
    1. RSS público + cookie LGN para autenticar visitas a páginas de detalhes
    2. Login via requests (funciona quando o IP não está bloqueado)
    3. Acesso público sem login (fallback final)
    """
    import xml.etree.ElementTree as ET

    vagas: List[Dict] = []
    erros: List[str] = []
    seen_ids: set = set()

    # Montar sessão com cookie LGN (login persistente) se disponível
    session = requests.Session()
    if TC_COOKIE_LGN:
        session.cookies.set("LGN", TC_COOKIE_LGN, domain="www.translatorscafe.com")
        session.cookies.set("LNG", "UILng=en", domain="www.translatorscafe.com")
        logger.info("Translators Café: usando cookie LGN persistente")
    else:
        # Tentar login via requests como fallback
        logado = _tc_fazer_login(session)
        if not logado:
            erros.append("Translators Café: cookie LGN não configurado e login via requests falhou")

    # Obter lista de vagas via RSS (não bloqueado por IP)
    job_ids_relevantes: List[Tuple[str, str, str, str]] = []  # (job_id, titulo, pares_desc, pub_date)
    try:
        resp_rss = requests.get(
            TC_RSS_URL,
            headers={**HEADERS, "Cookie": f"LGN={TC_COOKIE_LGN}; LNG=UILng%3Den" if TC_COOKIE_LGN else ""},
            timeout=TIMEOUT,
        )
        if resp_rss.status_code == 200 and "<rss" in resp_rss.text[:200]:
            root = ET.fromstring(resp_rss.content)
            ns = ""
            items = root.findall(f"{ns}channel/{ns}item") or root.findall("channel/item")
            logger.info(f"Translators Café RSS: {len(items)} item(ns) encontrado(s)")
            for item in items:
                link = (item.findtext("link") or "").strip()
                titulo = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                m = re.search(r'Job=(\d+)', link)
                if not m:
                    continue
                job_id = m.group(1)
                # Filtrar por idiomas relevantes na descrição do RSS
                desc_clean = re.sub(r'<[^>]+>', ' ', desc)
                # Aceitar vagas com PT, EN ou ES na descrição
                if re.search(r'\b(Portuguese|English|Spanish|Português|Inglês|Espanhol)\b', desc_clean, re.IGNORECASE):
                    job_ids_relevantes.append((job_id, titulo, desc_clean, pub_date))
        else:
            erros.append(f"Translators Café RSS: resposta inesperada (status {resp_rss.status_code})")
            # Fallback: scraping da página de vagas
            raise ValueError("RSS indisponível")
    except Exception as exc:
        erros.append(f"Translators Café RSS: erro — {exc} — tentando scraping direto")
        # Fallback: scraping da página de vagas (método antigo)
        for page in range(1, 6):
            url = TC_JOBS_URL if page == 1 else f"{TC_JOBS_URL}&Page={page}"
            try:
                resp = session.get(url, headers={**HEADERS, "Referer": TC_JOBS_URL}, timeout=TIMEOUT)
                if resp.status_code == 403:
                    erros.append(f"Translators Café página {page}: acesso bloqueado (403)")
                    break
                resp.raise_for_status()
            except Exception as e2:
                erros.append(f"Translators Café página {page}: erro — {e2}")
                break
            soup = BeautifulSoup(resp.content, "html.parser")
            for a in soup.find_all("a", href=True):
                if 'SelectedJob.asp' not in a.get('href', ''):
                    continue
                m = re.search(r'Job=(\d+)', a['href'])
                if not m:
                    continue
                job_id = m.group(1)
                titulo = a.get_text(strip=True)
                job_ids_relevantes.append((job_id, titulo, "", ""))
            time.sleep(SLEEP)

    logger.info(f"Translators Café: {len(job_ids_relevantes)} vaga(s) candidata(s) via RSS/scraping")

    # Visitar páginas de detalhes para extrair dados completos
    for job_id, titulo_rss, desc_rss, pub_date_rss in job_ids_relevantes:
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        url_vaga = f"{TC_BASE_URL}/cafe/SelectedJob.asp?Job={job_id}"

        # Extrair pares de idiomas da descrição do RSS
        pares_relevantes: List[Tuple[str, str]] = []
        for line in re.split(r'[<>\n]', desc_rss):
            line = line.strip()
            if not line:
                continue
            src, tgt = _parse_par_tc(line) if '>' in line else _extrair_par_idiomas_titulo(line)
            if _par_relevante(src, tgt):
                pares_relevantes.append((src, tgt))

        # Visitar página de detalhes
        detalhes = _tc_extrair_detalhes(session, job_id, url_vaga)

        # Completar pares a partir dos detalhes se RSS não forneceu
        if not pares_relevantes:
            src_d = detalhes.get("idioma_origem", "")
            tgt_d = detalhes.get("idioma_destino", "")
            if src_d and tgt_d and _par_relevante(src_d, tgt_d):
                pares_relevantes.append((src_d, tgt_d))

        # Fallback: par do título
        if not pares_relevantes:
            src, tgt = _extrair_par_idiomas_titulo(titulo_rss)
            if _par_relevante(src, tgt):
                pares_relevantes.append((src, tgt))

        if not pares_relevantes:
            continue

        pares_unicos = list(dict.fromkeys(pares_relevantes))
        origem, destino = pares_unicos[0]
        par_display = " | ".join(f"{s}→{t}" for s, t in pares_unicos) if len(pares_unicos) > 1 else f"{origem} → {destino}"

        pais_final = detalhes.get("pais", "")
        empresa_final = detalhes.get("empresa", "")
        url_empresa = detalhes.get("url_empresa", "")
        email_contato = detalhes.get("email_contato", "")
        site_contato = detalhes.get("site_contato", "")
        area_final = detalhes.get("area", "") or _extrair_area(titulo_rss)
        descricao_final = detalhes.get("descricao", "")
        data_pub_final = detalhes.get("data_publicacao", "") or _formatar_data(pub_date_rss)

        contagem_palavras = _extrair_contagem_palavras(descricao_final)
        formato = _extrair_formato(descricao_final)
        preco = _extrair_preco(descricao_final)
        prazo = _extrair_prazo(descricao_final)

        if email_contato:
            tipo_contato = "email"
            link_contato = email_contato
        elif site_contato:
            tipo_contato = "URL"
            link_contato = site_contato
        else:
            tipo_contato = "Translators Café"
            link_contato = url_vaga

        contato_descoberto = {}
        if empresa_final and not email_contato:
            contato_descoberto = buscar_contato_empresa(empresa_final, url_empresa, pais_final)

        vagas.append({
            "titulo": titulo_rss,
            "idioma_origem": origem,
            "idioma_destino": destino,
            "par_display": par_display,
            "area": area_final,
            "contagem_palavras": contagem_palavras,
            "formato": formato,
            "prazo": prazo,
            "tipo_contato": tipo_contato,
            "link_contato": link_contato,
            "link_vaga": url_vaga,
            "fonte": "Translators Café",
            "data_publicacao": data_pub_final,
            "detalhes": descricao_final,
            "contato_pessoa": "",
            "empresa": empresa_final,
            "pais": pais_final,
            "preco_palavra": preco,
            "contato_descoberto": contato_descoberto,
        })
        time.sleep(SLEEP)

    logger.info(f"Translators Café: {len(vagas)} vaga(s) relevante(s) encontrada(s)")
    return vagas, erros


# ─────────────────────────────────────────────────────────────────
# Scraping do Translation Directory
# ─────────────────────────────────────────────────────────────────

TD_URLS: Dict[str, str] = {
    "EN-PT": "https://www.translationdirectory.com/translation_jobs/english_portuguese_translation_jobs.php",
    "ES-PT": "https://www.translationdirectory.com/translation_jobs/spanish_portuguese_translation_jobs.php",
    "EN-ES": "https://www.translationdirectory.com/translation_jobs/english_spanish_translation_jobs.php",
}

_TD_CAMPOS = {
    "source_lang": re.compile(r'Source language\(s\):\s*(.+?)(?=\s+Target language|\s+Details|\s+Deadline|\s+Posted|\s+Contact|\s+Country|\s+Number|\s+This|$)', re.IGNORECASE),
    "target_lang": re.compile(r'Target language\(s\):\s*(.+?)(?=\s+Source language|\s+Details|\s+Deadline|\s+Posted|\s+Contact|\s+Country|\s+Number|\s+This|$)', re.IGNORECASE),
    "detalhes":    re.compile(r'Details of the project:\s*(.+?)(?=\s+This job is:|\s+We want to pay|\s+Who can apply|\s+Deadline for applying|\s+Contact person|$)', re.IGNORECASE | re.DOTALL),
    "preco":       re.compile(r'We want to pay for this job:\s*(.+?)(?=\s+Who can apply|\s+Deadline|\s+Contact|$)', re.IGNORECASE),
    "prazo":       re.compile(r'Deadline for applying:\s*(\S+)', re.IGNORECASE),
    "contato":     re.compile(r'Contact person:\s*(.+?)(?=\s+Company name|\s+Country|\s+IP:|$)', re.IGNORECASE),
    "empresa":     re.compile(r'Company name:\s*(.+?)(?=\s+Country|\s+IP:|$)', re.IGNORECASE),
    "pais":        re.compile(r'Country:\s*(\w+)', re.IGNORECASE),
    "posted":      re.compile(r'Posted on:\s*(.+?)(?:\s+IP:|$)', re.IGNORECASE),
}


def _extrair_campos_td(bloco: str) -> Dict[str, str]:
    campos = {}
    for nome, rx in _TD_CAMPOS.items():
        m = rx.search(bloco)
        campos[nome] = m.group(1).strip() if m else ""

    if campos.get("prazo"):
        campos["prazo"] = _formatar_data(campos["prazo"])
    if campos.get("posted"):
        campos["posted"] = _formatar_data(campos["posted"])

    # Registrar se empresa/contato estão ocultos pelo TD (para exibir aviso)
    campos["contato_oculto_td"] = "1" if "[Hidden by TD]" in campos.get("contato", "") or "[Hidden by TD]" in campos.get("empresa", "") else ""
    for k in ("contato", "empresa"):
        if "[Hidden by TD]" in campos.get(k, ""):
            campos[k] = ""

    if campos.get("detalhes"):
        campos["detalhes"] = campos["detalhes"][:600].strip()

    return campos


def _td_extrair_pagina_individual(job_url: str) -> Dict[str, str]:
    """
    Visita a página individual de uma vaga do Translation Directory e extrai
    todos os campos disponíveis, incluindo empresa e contato mencionados na descrição.
    Retorna dict com: empresa, contato_pessoa, pais, detalhes, preco, prazo, posted,
                      source_lang, target_lang, email_direto, site_mencionado
    """
    resultado: Dict[str, str] = {}
    try:
        r = requests.get(job_url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return resultado
        soup = BeautifulSoup(r.content, "html.parser")

        # Remover nav, scripts, footer, ads
        for tag in soup(["script", "style", "nav", "footer", "ins"]):
            tag.decompose()

        texto_completo = soup.get_text(separator="\n", strip=True)
        linhas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
        texto_bloco = " ".join(linhas)

        # Extrair campos estruturados com regex
        campos_rx = {
            "source_lang": re.compile(r'Source language\(s\):\s*(.+?)(?=\s+Target language|\s+Details|\s+Deadline|\s+Posted|\s+Contact|\s+Country|\s+Number|\s+This|$)', re.IGNORECASE),
            "target_lang": re.compile(r'Target language\(s\):\s*(.+?)(?=\s+Source language|\s+Details|\s+Deadline|\s+Posted|\s+Contact|\s+Country|\s+Number|\s+This|$)', re.IGNORECASE),
            "detalhes":    re.compile(r'Details of the project:\s*(.+?)(?=\s+This job is:|\s+We want to pay|\s+Who can apply|\s+Deadline for applying|\s+Contact person|\s+Special requirements|$)', re.IGNORECASE | re.DOTALL),
            "preco":       re.compile(r'We want to pay for this job[:\s]+(.+?)(?=\s+Who can apply|\s+Deadline|\s+Contact|$)', re.IGNORECASE),
            "prazo":       re.compile(r'Deadline for applying:\s*(\S+)', re.IGNORECASE),
            "contato":     re.compile(r'Contact person:\s*(.+?)(?=\s+Company name|\s+Country|\s+IP:|$)', re.IGNORECASE),
            "empresa":     re.compile(r'Company name:\s*(.+?)(?=\s+Country|\s+IP:|$)', re.IGNORECASE),
            "pais":        re.compile(r'Country:\s*(\w+(?:\s+\w+)?)', re.IGNORECASE),
            "posted":      re.compile(r'Posted on(?:\s+\w+,)?\s*(\d{1,2}\s+\w+\s+\d{4})', re.IGNORECASE),
        }
        for nome, rx in campos_rx.items():
            m = rx.search(texto_bloco)
            resultado[nome] = m.group(1).strip() if m else ""

        # Limpar [Hidden by TD] e registrar ocultamento
        resultado["contato_oculto_td"] = "1" if any(
            "[Hidden by TD]" in resultado.get(k, "") for k in ("contato", "empresa")
        ) else ""
        for k in ("contato", "empresa"):
            if "[Hidden by TD]" in resultado.get(k, ""):
                resultado[k] = ""

        # Truncar detalhes
        if resultado.get("detalhes"):
            resultado["detalhes"] = resultado["detalhes"][:800].strip()

        # Formatar datas
        if resultado.get("prazo"):
            resultado["prazo"] = _formatar_data(resultado["prazo"])
        if resultado.get("posted"):
            resultado["posted"] = _formatar_data(resultado["posted"])

        # ── Extração de empresa do título da página ──────────────────
        # O título costuma ser: "NomeEmpresa is looking for..."
        titulo_pagina = ""
        title_tag = soup.find("title")
        if title_tag:
            titulo_pagina = title_tag.get_text(strip=True)
        # Tentar h1/h2
        for htag in soup.find_all(["h1", "h2", "h3"]):
            t = htag.get_text(strip=True)
            if len(t) > 10 and any(kw in t.lower() for kw in ["looking for", "seeking", "needs", "requires", "hiring", "recrut"]):
                titulo_pagina = t
                break

        # Extrair empresa do título se não encontrada nos campos estruturados
        if not resultado.get("empresa"):
            # Padrão: "NomeEmpresa is looking for / needs / seeks / requires"
            m_emp = re.search(
                r'^([A-Z][A-Za-z0-9\s&\-\.]+?)\s+(?:is\s+)?(?:looking for|seeking|needs|requires|hiring|recrut)',
                titulo_pagina, re.IGNORECASE
            )
            if m_emp:
                resultado["empresa"] = m_emp.group(1).strip()

        # Tentar extrair empresa da descrição se ainda não encontrada
        if not resultado.get("empresa") and resultado.get("detalhes"):
            # Padrão: primeira frase menciona a empresa
            m_emp2 = re.search(
                r'^([A-Z][A-Za-z0-9\s&\-\.]+?)\s+(?:is\s+)?(?:looking for|seeking|needs|requires|hiring|recrut|invit)',
                resultado["detalhes"], re.IGNORECASE
            )
            if m_emp2:
                resultado["empresa"] = m_emp2.group(1).strip()
            else:
                # Fallback: padrão genérico de empresa
                resultado["empresa"] = _extrair_empresa(resultado["detalhes"])

        # ── Extrair email direto do texto completo ────────────────────
        emails_pagina = re.findall(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', texto_bloco)
        emails_validos = _emails_validos(emails_pagina)
        resultado["email_direto"] = emails_validos[0] if emails_validos else ""

        # ── Extrair site mencionado na descrição ─────────────────────
        detalhes_texto = resultado.get("detalhes", "") + " " + texto_bloco[:500]
        m_site = re.search(
            r'(?:https?://|www\.)[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s<>"]*)?',
            detalhes_texto
        )
        if m_site:
            site_raw = m_site.group(0)
            if not any(x in site_raw.lower() for x in [
                'translationdirectory', 'google', 'facebook', 'twitter',
                'linkedin', 'forms.gle', 'addthis', 'googlesyndication',
                'pcvector', 'truechristianity', 'w3.org'
            ]):
                resultado["site_mencionado"] = site_raw if site_raw.startswith('http') else f'https://{site_raw}'

    except Exception as exc:
        logger.debug(f"TD página individual {job_url}: erro — {exc}")

    return resultado


def _scrape_translation_directory() -> Tuple[List[Dict], List[str]]:
    """
    Faz scraping das vagas do Translation Directory.
    Para cada vaga encontrada na lista, visita obrigatoriamente a página individual
    para extrair empresa, contato e descrição completa, mesmo quando ocultos pelo TD.
    """
    vagas: List[Dict] = []
    erros: List[str] = []
    seen_urls: set = set()

    for par_label, url in TD_URLS.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            erros.append(f"Translation Directory ({par_label}): erro de acesso — {exc}")
            continue

        soup = BeautifulSoup(resp.content, "html.parser")
        job_links = [a for a in soup.find_all("a", href=True)
                     if re.match(r'^/job_\d+\.php$', a.get("href", ""))]

        for a in job_links:
            href = a.get("href", "")
            job_url = f"https://www.translationdirectory.com{href}"

            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            titulo_lista = a.get_text(strip=True)
            if not titulo_lista or len(titulo_lista) < 5:
                continue

            # Visitar a página individual para extrair todos os campos
            campos = _td_extrair_pagina_individual(job_url)
            time.sleep(SLEEP)

            # Par de idiomas: usar campos da página individual, fallback para par_label
            origem_code, destino_code = "", ""
            source_lang = campos.get("source_lang", "")
            target_lang = campos.get("target_lang", "")

            if source_lang and source_lang.lower() != "all languages":
                origem_code = _normalizar_idioma(source_lang.split(",")[0].strip())
            if target_lang and target_lang.lower() != "all languages":
                for tgt_item in re.split(r'[,;]', target_lang):
                    tgt_code = _normalizar_idioma(tgt_item.strip())
                    if tgt_code:
                        destino_code = tgt_code
                        break

            if not origem_code or not destino_code:
                parts = par_label.split("-")
                if len(parts) == 2:
                    origem_code = parts[0]
                    destino_code = parts[1]

            if not _par_relevante(origem_code, destino_code):
                if _par_relevante(destino_code, origem_code):
                    origem_code, destino_code = destino_code, origem_code
                else:
                    continue

            # Título: usar o da página individual se mais descritivo
            titulo = titulo_lista

            empresa_td = campos.get("empresa", "")
            pais_td = campos.get("pais", "")
            contato_pessoa = campos.get("contato", "")
            contato_oculto = campos.get("contato_oculto_td", "")
            detalhes_td = campos.get("detalhes", "")
            data_pub_raw = campos.get("posted", "")

            # Email direto na página individual
            link_contato_email = campos.get("email_direto", "")
            tipo_contato = "email" if link_contato_email else "Translation Directory"

            # Site mencionado na descrição
            site_na_descricao = campos.get("site_mencionado", "")

            # Busca reversa: priorizar site na descrição, depois nome da empresa
            contato_descoberto = {}
            if not link_contato_email:
                if site_na_descricao:
                    contato_descoberto = buscar_contato_empresa("", site_na_descricao, pais_td)
                    if not contato_descoberto:
                        contato_descoberto = {"site": site_na_descricao, "fonte_busca": "mencionado na descrição"}
                    if contato_descoberto.get("email"):
                        tipo_contato = "email (descoberto)"
                        link_contato_email = contato_descoberto["email"]
                if not contato_descoberto.get("email") and empresa_td:
                    # Busca reversa pelo nome da empresa
                    resultado_empresa = buscar_contato_empresa(empresa_td, "", pais_td)
                    if resultado_empresa:
                        if resultado_empresa.get("email"):
                            tipo_contato = "email (descoberto)"
                            link_contato_email = resultado_empresa["email"]
                        # Mesclar: manter site_na_descricao se já encontrado
                        if not contato_descoberto.get("site"):
                            contato_descoberto = resultado_empresa
                        else:
                            contato_descoberto.update({k: v for k, v in resultado_empresa.items() if k not in contato_descoberto})
                if not contato_descoberto and contato_oculto:
                    contato_descoberto = {"aviso": "Contato oculto pelo TD (requer cadastro pago)"}

            vagas.append({
                "titulo": titulo,
                "idioma_origem": origem_code,
                "idioma_destino": destino_code,
                "par_display": f"{origem_code} → {destino_code}",
                "area": _extrair_area(detalhes_td),
                "contagem_palavras": _extrair_contagem_palavras(detalhes_td),
                "formato": _extrair_formato(detalhes_td),
                "prazo": campos.get("prazo", ""),
                "tipo_contato": tipo_contato,
                "link_contato": link_contato_email or job_url,
                "link_vaga": job_url,
                "fonte": "Translation Directory",
                "data_publicacao": data_pub_raw,
                "detalhes": detalhes_td,
                "contato_pessoa": contato_pessoa,
                "empresa": empresa_td,
                "pais": pais_td,
                "preco_palavra": campos.get("preco", ""),
                "contato_descoberto": contato_descoberto,
            })

    logger.info(f"Translation Directory: {len(vagas)} vaga(s) relevante(s) encontrada(s)")
    return vagas, erros


# ─────────────────────────────────────────────────────────────────
# Deduplicação
# ─────────────────────────────────────────────────────────────────

def filtrar_novas_vagas(
    vagas: List[Dict],
    seen: Dict[str, str],
) -> Tuple[List[Dict], Dict[str, str]]:
    novas: List[Dict] = []
    seen_novo = dict(seen)

    for vaga in vagas:
        chave = vaga.get("link_vaga", "")
        if not chave:
            continue
        if chave not in seen_novo:
            novas.append(vaga)
            seen_novo[chave] = vaga.get("titulo", "")

    return novas, seen_novo


# ─────────────────────────────────────────────────────────────────
# Ponto de entrada
# ─────────────────────────────────────────────────────────────────

def _usar_selenium_disponivel() -> bool:
    """Verifica se o Selenium e o Chromium estão disponíveis."""
    try:
        import selenium  # noqa: F401
        import os
        for binary in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
            if os.path.exists(binary):
                return True
        return False
    except ImportError:
        return False


def buscar_vagas() -> Tuple[List[Dict], List[str]]:
    """Busca vagas em todas as fontes e retorna (vagas, erros).
    
    Estratégia de fallback automático:
    - Tenta primeiro com requests (rápido, sem overhead)
    - Se retornar 0 vagas ou erro de acesso, tenta com Selenium headless
    - Selenium contorna bloqueios de IP de datacenter (GitHub Actions)
    """
    todas_vagas: List[Dict] = []
    todos_erros: List[str] = []
    selenium_ok = _usar_selenium_disponivel()

    # ── ProZ.com ──────────────────────────────────────────────────
    vagas_proz, erros_proz = _scrape_proz()
    # Fallback Selenium se requests retornou 0 vagas ou erro de bloqueio
    if selenium_ok and (len(vagas_proz) == 0 or any(
        "bloqueado" in e.lower() or "403" in e or "encoding" in e.lower() or "decode" in e.lower()
        for e in erros_proz
    )):
        logger.info("ProZ.com: tentando scraper Selenium como fallback...")
        try:
            from selenium_scrapers import scrape_proz_selenium
            vagas_proz_sel, erros_proz_sel = scrape_proz_selenium(
                _extrair_par_idiomas_titulo, _par_relevante, _extrair_area,
                _extrair_contagem_palavras, _extrair_formato, _extrair_preco,
                _extrair_empresa, _formatar_data, buscar_contato_empresa,
            )
            if len(vagas_proz_sel) > len(vagas_proz):
                vagas_proz = vagas_proz_sel
                erros_proz = erros_proz_sel
                logger.info(f"ProZ.com: Selenium retornou {len(vagas_proz)} vaga(s)")
            else:
                erros_proz.extend(erros_proz_sel)
        except Exception as exc:
            erros_proz.append(f"ProZ.com (Selenium fallback): erro — {exc}")
            logger.error(f"ProZ.com Selenium fallback: {exc}")
    todas_vagas.extend(vagas_proz)
    todos_erros.extend(erros_proz)

    # ── Translators Café ─────────────────────────────────────────
    vagas_tc, erros_tc = _scrape_translators_cafe()
    # Fallback Selenium se requests retornou 0 vagas ou erro de bloqueio
    if selenium_ok and (len(vagas_tc) == 0 or any(
        "bloqueado" in e.lower() or "403" in e or "login" in e.lower()
        for e in erros_tc
    )):
        logger.info("Translators Café: tentando scraper Selenium como fallback...")
        try:
            from selenium_scrapers import scrape_translators_cafe_selenium
            vagas_tc_sel, erros_tc_sel = scrape_translators_cafe_selenium(
                _parse_par_tc, _extrair_par_idiomas_titulo, _par_relevante,
                _extrair_area, _extrair_contagem_palavras, _extrair_formato,
                _extrair_preco, _extrair_prazo, _formatar_data, buscar_contato_empresa,
            )
            if len(vagas_tc_sel) > len(vagas_tc):
                vagas_tc = vagas_tc_sel
                erros_tc = erros_tc_sel
                logger.info(f"Translators Café: Selenium retornou {len(vagas_tc)} vaga(s)")
            else:
                erros_tc.extend(erros_tc_sel)
        except Exception as exc:
            erros_tc.append(f"Translators Café (Selenium fallback): erro — {exc}")
            logger.error(f"Translators Café Selenium fallback: {exc}")
    todas_vagas.extend(vagas_tc)
    todos_erros.extend(erros_tc)

    # ── Translation Directory ────────────────────────────────────
    vagas_td, erros_td = _scrape_translation_directory()
    todas_vagas.extend(vagas_td)
    todos_erros.extend(erros_td)

    logger.info(f"Total geral: {len(todas_vagas)} vaga(s) | {len(todos_erros)} erro(s)")
    return todas_vagas, todos_erros
