#!/usr/bin/env python3
"""
Scrapers baseados em Selenium/Chromium headless para ProZ.com e Translators Café.
Usados como fallback quando os scrapers requests são bloqueados por IP de datacenter.
"""
from __future__ import annotations

import logging
import os
import re
import time
from html import unescape
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Configuração do Selenium
# ─────────────────────────────────────────────────────────────────

def _criar_driver():
    """Cria e retorna um WebDriver Chrome headless com configurações anti-detecção.
    
    Usa chrome-for-testing (binário standalone) via selenium-manager ou webdriver-manager.
    Funciona em ambientes CI/CD restritos como GitHub Actions.
    """
    import subprocess
    import sys
    import tempfile
    import zipfile
    import urllib.request
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-default-apps")
    opts.add_argument("--disable-sync")

    # ── Estratégia 1: usar selenium-manager embutido no Selenium 4.6+ ──────────────
    # O selenium-manager baixa automaticamente o Chrome for Testing + chromedriver
    # compatíveis sem depender do Chromium do sistema (que pode ser um snap wrapper).
    try:
        logger.info("Selenium: tentando iniciar com selenium-manager (Chrome for Testing)...")
        # Não definir binary_location — deixa o selenium-manager decidir
        driver = webdriver.Chrome(options=opts)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        logger.info("Selenium: driver iniciado com sucesso via selenium-manager.")
        return driver
    except Exception as e1:
        logger.warning(f"Selenium (selenium-manager): falhou — {e1}")

    # ── Estratégia 2: webdriver-manager com Chrome for Testing ─────────────────────
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        logger.info("Selenium: tentando com webdriver-manager (ChromeDriverManager)...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        logger.info("Selenium: driver iniciado com sucesso via webdriver-manager.")
        return driver
    except Exception as e2:
        logger.warning(f"Selenium (webdriver-manager): falhou — {e2}")

    # ── Estratégia 3: Chromium do sistema (apt) ────────────────────────────────────
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType
        chromium_binary = None
        for binary in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
            if os.path.exists(binary):
                chromium_binary = binary
                break
        if chromium_binary:
            logger.info(f"Selenium: tentando com Chromium do sistema ({chromium_binary})...")
            opts.binary_location = chromium_binary
            service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
            driver = webdriver.Chrome(service=service, options=opts)
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            logger.info("Selenium: driver iniciado com sucesso via Chromium do sistema.")
            return driver
    except Exception as e3:
        logger.warning(f"Selenium (Chromium sistema): falhou — {e3}")

    raise RuntimeError("Não foi possível iniciar o WebDriver Chrome por nenhuma das estratégias disponíveis.")


def _aguardar_pagina(driver, timeout: int = 15) -> None:
    """Aguarda o carregamento completo da página."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# ProZ.com — Selenium
# ─────────────────────────────────────────────────────────────────

def scrape_proz_selenium(
    _extrair_par_idiomas_titulo,
    _par_relevante,
    _extrair_area,
    _extrair_contagem_palavras,
    _extrair_formato,
    _extrair_preco,
    _extrair_empresa,
    _formatar_data,
    buscar_contato_empresa,
) -> Tuple[List[Dict], List[str]]:
    """
    Scraper ProZ.com via RSS (para listar vagas por par de idiomas) + Selenium (para detalhes).
    
    Estratégia:
    1. Coleta IDs de vagas via RSS filtrado por par de idiomas (sem bloqueio de IP)
    2. Visita cada página de detalhe via Selenium para extrair contato/empresa
    """
    import xml.etree.ElementTree as ET
    import requests as _requests

    PROZ_LANG_PAIRS = [
        ("por", "eng"),  # PT → EN
        ("eng", "por"),  # EN → PT
        ("por", "esl"),  # PT → ES
        ("esl", "por"),  # ES → PT
        ("eng", "esl"),  # EN → ES
        ("esl", "eng"),  # ES → EN
    ]
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    vagas: List[Dict] = []
    erros: List[str] = []
    driver = None

    # ── Fase 1: Coletar IDs de vagas via RSS (não bloqueado por IP) ────────────────
    job_items: List[Dict] = []  # {job_id, titulo, descricao, pub_date, job_url, sl, tl}
    seen_ids: set = set()

    for sl, tl in PROZ_LANG_PAIRS:
        rss_url = f"https://connect.proz.com/language-jobs?sl={sl}&tl={tl}&format=rss"
        try:
            resp = _requests.get(rss_url, headers=HEADERS, timeout=20)
            if resp.status_code != 200 or "<rss" not in resp.text[:200]:
                erros.append(f"ProZ RSS {sl}→{tl}: status {resp.status_code}")
                continue
            root = ET.fromstring(resp.content)
            items = root.findall("channel/item")
            logger.info(f"ProZ RSS {sl}→{tl}: {len(items)} vaga(s)")
            for item in items:
                link = (item.findtext("link") or "").strip()
                titulo = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                m = re.search(r'translation-jobs/(\d+)', link)
                if not m:
                    continue
                job_id = m.group(1)
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                job_items.append({
                    "job_id": job_id,
                    "titulo": titulo,
                    "descricao": desc[:600],
                    "pub_date": pub_date,
                    "job_url": f"https://www.proz.com/translation-jobs/{job_id}",
                    "sl": sl,
                    "tl": tl,
                })
        except Exception as exc:
            erros.append(f"ProZ RSS {sl}→{tl}: erro — {exc}")
        time.sleep(0.5)

    logger.info(f"ProZ.com RSS: {len(job_items)} vaga(s) únicas coletadas nos 6 pares")

    if not job_items:
        return vagas, erros

    # ── Fase 2: Visitar páginas de detalhe via Selenium ────────────────────────────
    try:
        driver = _criar_driver()
    except Exception as exc:
        erros.append(f"ProZ.com Selenium: falha ao criar driver — {exc}")
        # Fallback: usar dados do RSS sem detalhes
        for item in job_items:
            sl, tl = item["sl"], item["tl"]
            lang_map = {"por": "PT", "eng": "EN", "esl": "ES"}
            origem = lang_map.get(sl, sl.upper())
            destino = lang_map.get(tl, tl.upper())
            if not _par_relevante(origem, destino):
                continue
            par_display = f"{origem} → {destino}"
            descricao = item["descricao"]
            titulo = item["titulo"]
            area = _extrair_area(descricao + " " + titulo)
            contagem_palavras = _extrair_contagem_palavras(descricao)
            formato = _extrair_formato(descricao)
            preco = _extrair_preco(descricao)
            empresa = _extrair_empresa(descricao)
            email_desc = ""
            m_email = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', descricao)
            if m_email and "HIDDEN" not in descricao[max(0, m_email.start()-5):m_email.end()+5]:
                email_desc = m_email.group(0)
            tipo_contato = "email" if email_desc else "ProZ.com"
            link_contato = email_desc if email_desc else item["job_url"]
            contato_descoberto = {}
            if empresa and not email_desc:
                contato_descoberto = buscar_contato_empresa(empresa)
            data_pub = _formatar_data(item["pub_date"])
            vagas.append({
                "titulo": titulo, "idioma_origem": origem, "idioma_destino": destino,
                "par_display": par_display, "area": area, "contagem_palavras": contagem_palavras,
                "formato": formato, "prazo": "", "tipo_contato": tipo_contato,
                "link_contato": link_contato, "link_vaga": item["job_url"], "fonte": "ProZ.com",
                "data_publicacao": data_pub, "detalhes": descricao, "contato_pessoa": "",
                "empresa": empresa, "pais": "", "preco_palavra": preco,
                "contato_descoberto": contato_descoberto,
            })
        logger.info(f"ProZ.com (fallback RSS sem Selenium): {len(vagas)} vaga(s)")
        return vagas, erros

    try:
        for item in job_items:
            job_url = item["job_url"]
            titulo = item["titulo"]
            descricao_rss = item["descricao"]
            pub_date = item["pub_date"]
            sl, tl = item["sl"], item["tl"]

            lang_map = {"por": "PT", "eng": "EN", "esl": "ES"}
            origem_rss = lang_map.get(sl, sl.upper())
            destino_rss = lang_map.get(tl, tl.upper())

            # Visitar página de detalhe via Selenium
            try:
                driver.get(job_url)
                _aguardar_pagina(driver)
                time.sleep(2)
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, "html.parser")
                full_text = soup.get_text(separator="\n", strip=True)
            except Exception as exc:
                erros.append(f"ProZ detalhe {job_url}: erro — {exc}")
                soup = BeautifulSoup("", "html.parser")
                full_text = ""

            # Extrair pares de idiomas da página de detalhe
            pares_relevantes: List[Tuple[str, str]] = []
            for span in soup.find_all("span", attrs={"data-toggle": "tooltip"}):
                title_attr = unescape(span.get("title", ""))
                text_span = span.get_text(strip=True)
                if "language pair" in text_span.lower():
                    langs = re.findall(r'<li>([^<]+)</li>', title_attr)
                    for lang_pair in langs:
                        src, tgt = _extrair_par_idiomas_titulo(lang_pair)
                        if _par_relevante(src, tgt):
                            pares_relevantes.append((src, tgt))

            # Fallback: par do RSS
            if not pares_relevantes and _par_relevante(origem_rss, destino_rss):
                pares_relevantes.append((origem_rss, destino_rss))

            # Fallback: par do título
            if not pares_relevantes:
                src, tgt = _extrair_par_idiomas_titulo(titulo)
                if _par_relevante(src, tgt):
                    pares_relevantes.append((src, tgt))

            if not pares_relevantes:
                continue

            pares_unicos = list(dict.fromkeys(pares_relevantes))
            origem, destino = pares_unicos[0]
            par_display = (
                " | ".join(f"{s}→{t}" for s, t in pares_unicos)
                if len(pares_unicos) > 1
                else f"{origem} → {destino}"
            )

            # Extrair dados da página de detalhe
            descricao = descricao_rss
            area = _extrair_area(full_text + " " + titulo)
            contagem_palavras = _extrair_contagem_palavras(full_text)
            formato = _extrair_formato(full_text)
            preco = _extrair_preco(full_text)
            prazo = ""
            m_days = re.search(r'Open\s+for\s+(\d+)\s+more\s+days?', full_text, re.IGNORECASE)
            if m_days:
                from datetime import datetime, timedelta
                prazo = (datetime.now() + timedelta(days=int(m_days.group(1)))).strftime("%d/%m/%Y")
            data_pub = _formatar_data(pub_date)

            # Empresa
            empresa = _extrair_empresa(full_text)
            if not empresa:
                empresa = _extrair_empresa(titulo)

            # Email direto na página
            email_desc = ""
            m_email = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', full_text)
            if m_email:
                cand = m_email.group(0)
                if not any(x in cand.lower() for x in ["proz.com", "example", "noreply", "support"]):
                    email_desc = cand

            # Tipo de contato
            tipo_contato = "email" if email_desc else "ProZ.com"
            link_contato = email_desc if email_desc else job_url

            # Busca reversa de contato
            contato_descoberto = {}
            if empresa and not email_desc:
                contato_descoberto = buscar_contato_empresa(empresa)

            vagas.append({
                "titulo": titulo, "idioma_origem": origem, "idioma_destino": destino,
                "par_display": par_display, "area": area, "contagem_palavras": contagem_palavras,
                "formato": formato, "prazo": prazo, "tipo_contato": tipo_contato,
                "link_contato": link_contato, "link_vaga": job_url, "fonte": "ProZ.com",
                "data_publicacao": data_pub, "detalhes": descricao, "contato_pessoa": "",
                "empresa": empresa, "pais": "", "preco_palavra": preco,
                "contato_descoberto": contato_descoberto,
            })
            time.sleep(0.8)

        logger.info(f"ProZ.com (Selenium+RSS): {len(vagas)} vaga(s) relevante(s) encontrada(s)")

    except Exception as exc:
        erros.append(f"ProZ.com (Selenium): erro — {exc}")
        logger.error(f"ProZ.com (Selenium): {exc}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return vagas, erros


# ─────────────────────────────────────────────────────────────────
# Translators Café — Selenium
# ─────────────────────────────────────────────────────────────────

TC_USERNAME = os.environ.get("TC_USERNAME", "hudsonborges")
TC_PASSWORD = os.environ.get("TC_PASSWORD", "Raios25_")
TC_COOKIE_LGN = os.environ.get("TC_COOKIE_LGN", "").strip()
TC_LOGIN_URL = "https://www.translatorscafe.com/cafe/login.asp"
TC_JOBS_URL = "https://www.translatorscafe.com/cafe/SearchJobs.asp"
TC_BASE_URL = "https://www.translatorscafe.com"


def _tc_login_selenium(driver) -> bool:
    """Realiza login no Translators Café via Selenium."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        logger.info("TC (Selenium): acessando página de login...")
        driver.get(TC_LOGIN_URL)
        _aguardar_pagina(driver)
        time.sleep(2)

        # Preencher username
        try:
            user_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "UserName"))
            )
            user_field.clear()
            user_field.send_keys(TC_USERNAME)
        except Exception:
            # Tentar por ID ou tipo
            fields = driver.find_elements("css selector", "input[type='text'], input[name*='user' i], input[id*='user' i]")
            if fields:
                fields[0].clear()
                fields[0].send_keys(TC_USERNAME)
            else:
                logger.warning("TC (Selenium): campo de username não encontrado")
                return False

        # Preencher password
        try:
            pass_field = driver.find_element("name", "Password")
            pass_field.clear()
            pass_field.send_keys(TC_PASSWORD)
        except Exception:
            fields = driver.find_elements("css selector", "input[type='password']")
            if fields:
                fields[0].clear()
                fields[0].send_keys(TC_PASSWORD)
            else:
                logger.warning("TC (Selenium): campo de password não encontrado")
                return False

        time.sleep(1)

        # Submeter formulário
        try:
            submit = driver.find_element("css selector", "input[type='submit'], button[type='submit']")
            submit.click()
        except Exception:
            pass_field.submit()

        _aguardar_pagina(driver)
        time.sleep(3)

        # Verificar login bem-sucedido
        current_url = driver.current_url
        page_text = driver.page_source
        if ("quicklook" in current_url or "Hudson" in page_text or
                "Logout" in page_text or "hudsonborges" in page_text.lower()):
            logger.info(f"TC (Selenium): login realizado com sucesso — URL: {current_url}")
            return True
        else:
            logger.warning(f"TC (Selenium): login incerto — URL: {current_url}")
            return False

    except Exception as exc:
        logger.error(f"TC (Selenium): erro no login — {exc}")
        return False


def _tc_extrair_detalhes_selenium(driver, job_id: str, url_vaga: str) -> Dict[str, str]:
    """Visita a página de detalhes de uma vaga do TC via Selenium e extrai campos."""
    campos = {
        "pais": "", "empresa": "", "url_empresa": "", "email_contato": "",
        "site_contato": "", "area": "", "tipo_servico": "", "idiomas": "",
        "descricao": "", "data_publicacao": "",
    }
    try:
        driver.get(url_vaga)
        _aguardar_pagina(driver)
        time.sleep(1.5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 1. Data de publicação
        job_header = soup.find(string=re.compile(r'Job #\d+'))
        if job_header:
            parent_text = job_header.parent.get_text(strip=True)
            m_date = re.search(r'posted on\s*(\d+/\d+/\d+)', parent_text, re.IGNORECASE)
            if m_date:
                from monitor_traducao import _formatar_data
                campos["data_publicacao"] = _formatar_data(m_date.group(1))

        # 2. País
        country_img = soup.find("img", alt=re.compile(r'^[A-Z]{2}$'))
        if country_img:
            parent = country_img.parent
            country_text = parent.get_text(strip=True)
            country_clean = re.sub(r'^[A-Z]{2}\s*', '', country_text).strip()
            if country_clean:
                campos["pais"] = country_clean

        # 3. Empresa
        co_el = soup.find(class_=lambda c: c and "sjCo" in c)
        if co_el:
            company_link = co_el.find("a")
            if company_link:
                campos["empresa"] = company_link.get_text(strip=True)
                campos["url_empresa"] = company_link.get("href", "")

        # 4. Email/site de contato
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
                    domain = text.strip()
                    if "." in domain and not domain.startswith("http"):
                        campos["site_contato"] = f"https://{domain}"

        # 5. Campos sjParam
        for el in soup.find_all(class_="sjParam"):
            text = el.get_text(separator=" ", strip=True)
            if "Job type:" in text:
                campos["tipo_servico"] = re.sub(r'\s+', ' ', text.replace("Job type:", "").strip()).strip(", ")
            elif "Languages:" in text:
                campos["idiomas"] = text.replace("Languages:", "").strip()
            elif "Specialization:" in text:
                campos["area"] = text.replace("Specialization:", "").strip()

        # 6. Descrição
        desc_parent = None
        for el in soup.find_all(class_="sjParam"):
            text = el.get_text(separator=" ", strip=True)
            if "Job description:" in text:
                desc_parent = el.parent
                break
        if desc_parent:
            desc_text = desc_parent.get_text(separator=" ", strip=True)
            m_desc = re.search(
                r'Job description:\s*(.+?)(?:\s*Job #|\s*Before accepting|$)',
                desc_text, re.IGNORECASE | re.DOTALL
            )
            if m_desc:
                campos["descricao"] = m_desc.group(1).strip()[:600]

    except Exception as exc:
        logger.debug(f"TC (Selenium) detalhe {job_id}: erro — {exc}")

    return campos


def scrape_translators_cafe_selenium(
    _parse_par_tc,
    _extrair_par_idiomas_titulo,
    _par_relevante,
    _extrair_area,
    _extrair_contagem_palavras,
    _extrair_formato,
    _extrair_preco,
    _extrair_prazo,
    _formatar_data,
    buscar_contato_empresa,
) -> Tuple[List[Dict], List[str]]:
    """
    Scraper Translators Café usando Selenium headless com login autenticado.
    Recebe as funções auxiliares do monitor_traducao.py como parâmetros.
    """
    vagas: List[Dict] = []
    erros: List[str] = []
    driver = None

    try:
        driver = _criar_driver()

        # Estratégia 1: injetar cookie LGN persistente (não requer formulário de login)
        logado = False
        if TC_COOKIE_LGN:
            try:
                # Precisa navegar para o domínio antes de injetar cookies
                driver.get(TC_BASE_URL)
                _aguardar_pagina(driver)
                time.sleep(2)
                driver.add_cookie({
                    "name": "LGN",
                    "value": TC_COOKIE_LGN,
                    "domain": "www.translatorscafe.com",
                    "path": "/",
                    "secure": False,
                })
                driver.add_cookie({
                    "name": "LNG",
                    "value": "UILng=en",
                    "domain": "www.translatorscafe.com",
                    "path": "/",
                })
                logger.info("TC (Selenium): cookie LGN injetado com sucesso")
                logado = True
            except Exception as e_cookie:
                logger.warning(f"TC (Selenium): falha ao injetar cookie LGN — {e_cookie}")

        # Estratégia 2: login via formulário (fallback)
        if not logado:
            logado = _tc_login_selenium(driver)
        if not logado:
            erros.append("Translators Café (Selenium): falha no login")
            logger.warning("TC (Selenium): continuando sem login (acesso público)")

        seen_ids: set = set()

        for page in range(1, 6):
            url = TC_JOBS_URL if page == 1 else f"{TC_JOBS_URL}?Page={page}"
            logger.info(f"TC (Selenium): acessando página {page}...")
            driver.get(url)
            _aguardar_pagina(driver)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            job_links = [a for a in soup.find_all("a", href=True) if "SelectedJob.asp" in a.get("href", "")]

            if not job_links:
                logger.info(f"TC (Selenium): página {page} sem vagas — parando")
                break

            logger.info(f"TC (Selenium): página {page} — {len(job_links)} vaga(s)")

            for a in job_links:
                titulo = a.get_text(strip=True)
                href = a["href"]
                m = re.search(r'Job=(\d+)', href)
                job_id = m.group(1) if m else None
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                url_vaga = f"{TC_BASE_URL}/cafe/SelectedJob.asp?Job={job_id}"

                # Extrair par de idiomas da lista
                td = a.find_parent("td")
                tr = td.find_parent("tr") if td else None
                pares_relevantes: List[Tuple[str, str]] = []
                area_lista = ""
                data_pub_lista = ""

                if tr:
                    cells = tr.find_all("td")
                    if len(cells) >= 2:
                        lang_cell = cells[1]
                        for line in lang_cell.get_text(separator="\n").split("\n"):
                            line = line.strip()
                            if ">" in line and len(line) < 80:
                                src, tgt = _parse_par_tc(line)
                                if _par_relevante(src, tgt):
                                    pares_relevantes.append((src, tgt))
                        cell0_lines = [l.strip() for l in cells[0].get_text(separator="\n").split("\n") if l.strip()]
                        if len(cell0_lines) >= 2:
                            area_lista = cell0_lines[-1]
                    prev_tr = tr.find_previous_sibling("tr")
                    if prev_tr:
                        prev_text = prev_tr.get_text(strip=True)
                        m_date = re.search(
                            r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M\s+GMT)',
                            prev_text
                        )
                        if m_date:
                            data_pub_lista = _formatar_data(m_date.group(1))

                if not pares_relevantes:
                    src, tgt = _extrair_par_idiomas_titulo(titulo)
                    if _par_relevante(src, tgt):
                        pares_relevantes.append((src, tgt))
                if not pares_relevantes:
                    continue

                pares_unicos = list(dict.fromkeys(pares_relevantes))
                origem, destino = pares_unicos[0]
                par_display = (
                    " | ".join(f"{s}→{t}" for s, t in pares_unicos)
                    if len(pares_unicos) > 1
                    else f"{origem} → {destino}"
                )

                # Visitar página de detalhes
                detalhes = _tc_extrair_detalhes_selenium(driver, job_id, url_vaga)

                pais_final = detalhes.get("pais", "")
                empresa_final = detalhes.get("empresa", "")
                url_empresa = detalhes.get("url_empresa", "")
                email_contato = detalhes.get("email_contato", "")
                site_contato = detalhes.get("site_contato", "")
                area_final = detalhes.get("area", "") or area_lista or _extrair_area(titulo)
                descricao_final = detalhes.get("descricao", "")
                data_pub_final = detalhes.get("data_publicacao", "") or data_pub_lista
                tipo_servico = detalhes.get("tipo_servico", "") or area_lista

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
                    "titulo": titulo,
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

                # Voltar para a lista de vagas
                driver.back()
                _aguardar_pagina(driver)
                time.sleep(1)

            time.sleep(1.5)

        logger.info(f"Translators Café (Selenium): {len(vagas)} vaga(s) relevante(s) encontrada(s)")

    except Exception as exc:
        erros.append(f"Translators Café (Selenium): erro — {exc}")
        logger.error(f"Translators Café (Selenium): {exc}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return vagas, erros
