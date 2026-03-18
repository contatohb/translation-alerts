#!/usr/bin/env python3
"""
Monitor de vagas de tradução em ProZ.com e Translators Café.

Combinações de idiomas monitoradas:
  - Português ↔ Inglês  (PT/EN, EN/PT)
  - Português ↔ Espanhol (PT/ES, ES/PT)
  - Inglês    ↔ Espanhol (EN/ES, ES/EN)

Cada vaga retornada contém:
  titulo, idioma_origem, idioma_destino, area, contagem_palavras,
  formato, localizacao, prazo, tipo_contato, link_contato,
  link_vaga, fonte, data_publicacao
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

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
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
TIMEOUT = 25
SLEEP = 0.6

# ─────────────────────────────────────────────────────────────────
# Credenciais do Translators Café (login por cookie)
# ─────────────────────────────────────────────────────────────────
# O cookie LGN é gerado no login e persiste por longa duração.
# Para renovar: fazer login em translatorscafe.com e copiar o cookie LGN.
TC_USERNAME = "hudsonborges"
TC_PASSWORD = "Raios25_"

TC_LOGIN_URL = "https://www.translatorscafe.com/cafe/login.asp"
TC_JOBS_URL  = "https://www.translatorscafe.com/cafe/SearchJobs.asp"

# ─────────────────────────────────────────────────────────────────
# Mapeamento de idiomas
# ─────────────────────────────────────────────────────────────────

LANGUAGE_MAP: Dict[str, str] = {
    # Português — correspondência exata ou prefixo claro
    "portuguese": "PT",
    "português": "PT",
    "portugues": "PT",
    # Inglês
    "english": "EN",
    # Espanhol — apenas termos inequívocos
    "spanish": "ES",
    "español": "ES",
    "espanol": "ES",
    "latin american spanish": "ES",
    "castilian": "ES",
}

# Pares aceitos (bidirecional)
ACCEPTED_PAIRS = {
    ("PT", "EN"), ("EN", "PT"),
    ("PT", "ES"), ("ES", "PT"),
    ("EN", "ES"), ("ES", "EN"),
}

# Abreviações aceitas (apenas exatas, para evitar falsos positivos)
_ABBREV_MAP: Dict[str, str] = {
    "pt": "PT", "pt-br": "PT", "pt-pt": "PT",
    "en": "EN", "en-us": "EN", "en-gb": "EN",
    "es": "ES", "es-la": "ES", "es(la)": "ES",
}


def _normalizar_idioma(texto: str) -> str:
    """Converte nome de idioma para código de 2 letras (PT, EN, ES)."""
    if not texto:
        return ""
    t = texto.lower().strip()

    # 1. Correspondência exata por nome completo
    for chave, codigo in LANGUAGE_MAP.items():
        if t == chave or t.startswith(chave):
            return codigo

    # 2. Abreviação exata (2-5 chars)
    if len(t) <= 5:
        if t in _ABBREV_MAP:
            return _ABBREV_MAP[t]

    return ""


def _extrair_par_idiomas_titulo(texto: str) -> Tuple[str, str]:
    """
    Extrai par de idiomas de um texto de título usando múltiplas estratégias.
    Retorna (origem, destino) ou ("", "") se não encontrar.
    """
    if not texto:
        return "", ""

    t_lower = texto.lower()

    # Estratégia 1: Abreviações "EN-PT", "EN PT", "EN>PT"
    m = re.search(r'\b(en|pt|es)\s*[-–>]\s*(en|pt|es)\b', t_lower)
    if m:
        src = _normalizar_idioma(m.group(1))
        tgt = _normalizar_idioma(m.group(2))
        if src and tgt and src != tgt:
            return src, tgt

    # Estratégia 2: "English to Spanish", "English > Spanish"
    m = re.search(
        r'(\w+(?:\s+\w+)?)\s+(?:to|into|→|>)\s+(\w+(?:\s+\w+)?)',
        texto, re.IGNORECASE
    )
    if m:
        src = _normalizar_idioma(m.group(1))
        tgt = _normalizar_idioma(m.group(2))
        if src and tgt and src != tgt:
            return src, tgt

    # Estratégia 3: "English <> Spanish" (bidirecional)
    m = re.search(
        r'(\w+(?:\s+\w+)?)\s*<>\s*(\w+(?:\s+\w+)?)',
        texto, re.IGNORECASE
    )
    if m:
        src = _normalizar_idioma(m.group(1))
        tgt = _normalizar_idioma(m.group(2))
        if src and tgt and src != tgt:
            return src, tgt

    # Estratégia 4: "from English" + "into/to Spanish"
    m_from = re.search(r'from\s+(\w+)', t_lower)
    m_into = re.search(r'(?:into|to)\s+(\w+)', t_lower)
    if m_from and m_into:
        src = _normalizar_idioma(m_from.group(1))
        tgt = _normalizar_idioma(m_into.group(1))
        if src and tgt and src != tgt:
            return src, tgt

    return "", ""


def _parse_par_tc(lang_text: str) -> Tuple[str, str]:
    """
    Analisa par de idiomas no formato do Translators Café: 'English>Spanish'.
    Retorna (origem, destino) ou ("", "").
    """
    m = re.match(r'^(.+?)>(.+)$', lang_text.strip())
    if m:
        src = _normalizar_idioma(m.group(1).strip())
        tgt = _normalizar_idioma(m.group(2).strip())
        return src, tgt
    return "", ""


def _par_relevante(origem: str, destino: str) -> bool:
    """Retorna True se o par de idiomas está entre os aceitos."""
    if not origem or not destino:
        return False
    return (origem, destino) in ACCEPTED_PAIRS


# ─────────────────────────────────────────────────────────────────
# Scraping do ProZ.com
# ─────────────────────────────────────────────────────────────────

def _scrape_proz() -> Tuple[List[Dict], List[str]]:
    """
    Faz scraping da página pública de vagas do ProZ.com.
    Retorna (lista_vagas, lista_erros).
    """
    vagas: List[Dict] = []
    erros: List[str] = []
    url = "https://connect.proz.com/language-jobs"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        erros.append(f"ProZ.com: erro de acesso — {exc}")
        return vagas, erros

    soup = BeautifulSoup(resp.content, "html.parser")
    all_links = soup.find_all("a")
    seen_urls: set = set()

    for link in all_links:
        titulo = link.get_text(strip=True)
        href = link.get("href", "")

        if not titulo or len(titulo) < 8:
            continue
        if not re.search(r'(translation-jobs|language-jobs)/\d+', href):
            continue

        # Monta URL completa
        if href.startswith("http"):
            job_url = href
        else:
            job_url = f"https://www.proz.com{href}"

        if job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        # Extrai par de idiomas do título
        origem, destino = _extrair_par_idiomas_titulo(titulo)
        if not _par_relevante(origem, destino):
            continue

        # Extrai contexto da vaga (elemento pai)
        pai = link.find_parent()
        contexto = pai.get_text(separator=" ", strip=True) if pai else ""

        contagem_palavras = _extrair_contagem_palavras(contexto)
        formato = _extrair_formato(contexto)
        prazo = _extrair_prazo(contexto)
        area = _extrair_area(contexto)
        tipo_contato, link_contato = _extrair_contato(contexto, job_url)
        data_pub = _extrair_data_publicacao(contexto)

        vagas.append({
            "titulo": titulo,
            "idioma_origem": origem,
            "idioma_destino": destino,
            "area": area,
            "contagem_palavras": contagem_palavras,
            "formato": formato,
            "prazo": prazo,
            "tipo_contato": tipo_contato,
            "link_contato": link_contato,
            "link_vaga": job_url,
            "fonte": "ProZ.com",
            "data_publicacao": data_pub,
        })

    logger.info(f"ProZ.com: {len(vagas)} vaga(s) relevante(s) encontrada(s)")
    return vagas, erros


# ─────────────────────────────────────────────────────────────────
# Scraping do Translators Café (com login por sessão)
# ─────────────────────────────────────────────────────────────────

def _tc_fazer_login(session: requests.Session) -> bool:
    """
    Faz login no Translators Café usando a sessão fornecida.
    Retorna True se o login foi bem-sucedido.
    """
    try:
        # Passo 1: GET para obter cookies de sessão e o campo RedirectionString
        resp = session.get(
            TC_LOGIN_URL,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 403:
            logger.warning("Translators Café: acesso negado (403) na página de login")
            return False
        resp.raise_for_status()

        from bs4 import BeautifulSoup as _BS
        soup = _BS(resp.content, "html.parser")
        redir_input = soup.find("input", {"name": "RedirectionString"})
        redir_val = redir_input["value"] if redir_input else "https://www.translatorscafe.com/cafe/"

        # Passo 2: POST com todos os campos do formulário
        login_data = {
            "RedirectionString": redir_val,
            "Flag": "Login",
            "UserName": TC_USERNAME,
            "Password": TC_PASSWORD,
            "AutoLogin": "on",
        }
        time.sleep(1.5)  # Pausa para simular comportamento humano
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

        # Verifica se o login foi bem-sucedido
        if "Hudson Borges" in resp2.text or "quicklook" in resp2.url or "My Caf" in resp2.text or "Logout" in resp2.text:
            logger.info("Translators Café: login realizado com sucesso")
            return True
        elif resp2.status_code == 403:
            logger.warning("Translators Café: acesso negado (403) após POST de login")
            return False
        else:
            logger.warning("Translators Café: login pode ter falhado — verificar credenciais")
            return False

    except Exception as exc:
        logger.error(f"Translators Café: erro no login — {exc}")
        return False


def _scrape_translators_cafe() -> Tuple[List[Dict], List[str]]:
    """
    Faz scraping das vagas do Translators Café com login autenticado.
    Extrai o par de idiomas diretamente da coluna da tabela (formato 'English>Spanish').
    Retorna (lista_vagas, lista_erros).
    """
    vagas: List[Dict] = []
    erros: List[str] = []

    session = requests.Session()

    # Fazer login
    logado = _tc_fazer_login(session)
    if not logado:
        erros.append("Translators Café: falha no login — tentando acesso público")
        # Tenta mesmo assim com dados públicos (sem login)

    seen_ids: set = set()

    # Com login, o TC mostra vagas filtradas pelas combinações do perfil (PT/EN/ES)
    # Varrer todas as páginas disponíveis (normalmente 3 com login)
    for page in range(1, 6):
        if page == 1:
            url = TC_JOBS_URL
        else:
            url = f"{TC_JOBS_URL}?Mode=Selected&Page={page}"

        try:
            resp = session.get(url, headers={**HEADERS, "Referer": TC_JOBS_URL}, timeout=TIMEOUT)
            if resp.status_code == 403:
                erros.append(f"Translators Café página {page}: acesso bloqueado (403) — IP do servidor pode estar na lista de bloqueio do TC")
                break
            resp.raise_for_status()
        except Exception as exc:
            erros.append(f"Translators Café página {page}: erro — {exc}")
            break

        soup = BeautifulSoup(resp.content, "html.parser")

        # Detectar se há mais páginas
        job_links = [a for a in soup.find_all("a", href=True) if 'SelectedJob.asp' in a.get('href', '')]

        if not job_links:
            break  # Sem mais vagas

        for a in job_links:
            titulo = a.get_text(strip=True)
            href = a['href']
            m = re.search(r'Job=(\d+)', href)
            job_id = m.group(1) if m else None

            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            # URL limpa da vaga (sem parâmetro Jobs= que muda)
            url_vaga = f"https://www.translatorscafe.com/cafe/SelectedJob.asp?Job={job_id}"

            # Par de idiomas está na célula 1 da mesma linha da tabela
            td = a.find_parent('td')
            tr = td.find_parent('tr') if td else None

            pares_relevantes: List[Tuple[str, str]] = []
            data_pub = ""

            if tr:
                cells = tr.find_all('td')
                if len(cells) >= 2:
                    # Célula 1 pode conter múltiplos pares (um por linha)
                    lang_cell = cells[1]
                    for line in lang_cell.get_text(separator='\n').split('\n'):
                        line = line.strip()
                        if '>' in line and len(line) < 80:
                            src, tgt = _parse_par_tc(line)
                            if _par_relevante(src, tgt):
                                pares_relevantes.append((src, tgt))

                # Data de publicação está na linha anterior (cabeçalho do bloco)
                prev_tr = tr.find_previous_sibling('tr')
                if prev_tr:
                    prev_text = prev_tr.get_text(strip=True)
                    m_date = re.search(
                        r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M\s+GMT)',
                        prev_text
                    )
                    if m_date:
                        data_pub = m_date.group(1)

            if not pares_relevantes:
                # Fallback: tentar extrair do título
                src, tgt = _extrair_par_idiomas_titulo(titulo)
                if _par_relevante(src, tgt):
                    pares_relevantes.append((src, tgt))

            if not pares_relevantes:
                continue

            # Usar o primeiro par relevante como principal
            origem, destino = pares_relevantes[0]
            todos_pares_str = " | ".join(f"{s}→{t}" for s, t in pares_relevantes)

            # Contexto para extração de campos adicionais
            contexto = tr.get_text(separator=" ", strip=True) if tr else titulo

            vagas.append({
                "titulo": titulo,
                "idioma_origem": origem,
                "idioma_destino": destino,
                "pares_adicionais": todos_pares_str,
                "area": _extrair_area_tc(soup, tr),
                "contagem_palavras": _extrair_contagem_palavras(contexto),
                "formato": _extrair_formato(contexto),
                "prazo": _extrair_prazo(contexto),
                "tipo_contato": "Translators Café",
                "link_contato": url_vaga,
                "link_vaga": url_vaga,
                "fonte": "Translators Café",
                "data_publicacao": data_pub,
            })

        time.sleep(SLEEP)

    logger.info(f"Translators Café: {len(vagas)} vaga(s) relevante(s) encontrada(s)")
    return vagas, erros


def _extrair_area_tc(soup: BeautifulSoup, tr) -> str:
    """Extrai a área/tipo de serviço da vaga no Translators Café."""
    if tr:
        cells = tr.find_all('td')
        if cells:
            cell_text = cells[0].get_text(separator='\n', strip=True)
            lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
            # A segunda linha costuma ser o tipo (Translation, Interpreting, etc.)
            if len(lines) >= 2:
                return lines[-1]
    return ""


# ─────────────────────────────────────────────────────────────────
# Extratores de campos adicionais
# ─────────────────────────────────────────────────────────────────

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
        r'(?:open for|deadline|prazo|até|until|by)\s+([^\n\.]{3,40})',
        texto, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2})', texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extrair_area(texto: str) -> str:
    areas_conhecidas = [
        "Legal", "Medical", "Technical", "Financial", "Literary",
        "Marketing", "IT", "Science", "General", "Law", "Patents",
        "Business", "Engineering", "Tourism", "Education",
        "Jurídico", "Médico", "Técnico", "Financeiro", "Literário",
    ]
    t = texto.lower()
    encontradas = [a for a in areas_conhecidas if a.lower() in t]
    return ", ".join(encontradas[:3]) if encontradas else ""


def _extrair_contato(texto: str, url_vaga: str) -> Tuple[str, str]:
    """Retorna (tipo_contato, link_contato)."""
    m = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', texto)
    if m:
        return "email", m.group(0)

    m = re.search(r'https?://[^\s<>"]+', texto)
    if m and m.group(0) != url_vaga:
        return "URL", m.group(0)

    if "proz.com" in url_vaga:
        return "ProZ.com", url_vaga

    if "translatorscafe.com" in url_vaga:
        return "Translators Café", url_vaga

    return "link direto", url_vaga


def _extrair_data_publicacao(texto: str) -> str:
    m = re.search(
        r'(?:posted|publicad[ao])\s+([^\n\.]{3,30})',
        texto, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    return ""


# ─────────────────────────────────────────────────────────────────
# Deduplicação
# ─────────────────────────────────────────────────────────────────

def filtrar_novas_vagas(
    vagas: List[Dict],
    seen: Dict[str, str],
) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Filtra apenas vagas não vistas antes.
    Retorna (novas_vagas, seen_atualizado).
    A chave do seen é o link_vaga (URL única da vaga).
    """
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
# Formatação do email
# ─────────────────────────────────────────────────────────────────

def formatar_email_traducao(vagas: List[Dict], erros: List[str]) -> str:
    """Formata o corpo do email com as vagas encontradas."""
    from datetime import date
    hoje = date.today().strftime("%d/%m/%Y")

    linhas: List[str] = []
    linhas.append(f"ALERTA DE VAGAS DE TRADUÇÃO — {hoje}")
    linhas.append("=" * 70)

    if not vagas:
        linhas.append("")
        linhas.append("Nenhuma vaga nova encontrada hoje para os pares:")
        linhas.append("  PT↔EN  |  PT↔ES  |  EN↔ES")
    else:
        linhas.append(f"Total de vagas novas: {len(vagas)}")
        linhas.append("")

        for i, v in enumerate(vagas, 1):
            par = f"{v.get('idioma_origem','?')} → {v.get('idioma_destino','?')}"
            # Se houver pares adicionais, mostrar todos
            pares_add = v.get("pares_adicionais", "")
            if pares_add and pares_add != par.replace(" → ", "→"):
                par_display = pares_add
            else:
                par_display = par

            linhas.append(f"{'─' * 70}")
            linhas.append(f"[{i}/{len(vagas)}]  {v.get('titulo', 'Sem título')}")
            linhas.append(f"{'─' * 70}")
            linhas.append(f"  Par de idiomas : {par_display}")
            if v.get("area"):
                linhas.append(f"  Área/Tipo      : {v['area']}")
            if v.get("contagem_palavras"):
                linhas.append(f"  Palavras       : {v['contagem_palavras']}")
            if v.get("formato"):
                linhas.append(f"  Formato        : {v['formato']}")
            if v.get("prazo"):
                linhas.append(f"  Prazo          : {v['prazo']}")
            if v.get("data_publicacao"):
                linhas.append(f"  Publicado em   : {v['data_publicacao']}")
            linhas.append(f"  Fonte          : {v.get('fonte', 'N/A')}")
            linhas.append(f"  Link da vaga   : {v.get('link_vaga', 'N/A')}")
            tipo_c = v.get("tipo_contato", "")
            link_c = v.get("link_contato", "")
            if tipo_c and link_c and link_c != v.get("link_vaga"):
                linhas.append(f"  Contato        : {link_c}")
            linhas.append(f"  CV enviado     : ⚠️  Requer ação manual")
            linhas.append("")

    # Erros de scraping
    if erros:
        linhas.append("─" * 70)
        linhas.append("AVISOS DO SISTEMA:")
        for e in erros:
            linhas.append(f"  • {e}")
        linhas.append("")

    linhas.append("=" * 70)
    linhas.append("Sistema de alertas de tradução — Hudson Borges")
    linhas.append("Pares monitorados: PT↔EN | PT↔ES | EN↔ES")
    linhas.append("Fontes: ProZ.com | Translators Café")

    return "\n".join(linhas)


# ─────────────────────────────────────────────────────────────────
# Ponto de entrada
# ─────────────────────────────────────────────────────────────────

def buscar_vagas() -> Tuple[List[Dict], List[str]]:
    """Busca vagas em todas as fontes e retorna (vagas, erros)."""
    todas_vagas: List[Dict] = []
    todos_erros: List[str] = []

    # ProZ.com
    vagas_proz, erros_proz = _scrape_proz()
    todas_vagas.extend(vagas_proz)
    todos_erros.extend(erros_proz)

    # Translators Café
    vagas_tc, erros_tc = _scrape_translators_cafe()
    todas_vagas.extend(vagas_tc)
    todos_erros.extend(erros_tc)

    logger.info(f"Total geral: {len(todas_vagas)} vaga(s) | {len(todos_erros)} erro(s)")
    return todas_vagas, todos_erros
