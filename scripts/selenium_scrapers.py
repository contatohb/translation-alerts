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
    """Cria e retorna um WebDriver Chromium headless com configurações anti-detecção.
    
    Usa webdriver-manager para instalar automaticamente o chromedriver compatível
    com a versão do Chrome/Chromium instalada no sistema.
    """
    import subprocess
    import sys
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    # Auto-instalar webdriver-manager se necessário
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "webdriver-manager"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType

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

    # Localizar o binário do Chromium e instalar chromedriver compatível
    chromium_binary = None
    for binary in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
        if os.path.exists(binary):
            chromium_binary = binary
            break

    if chromium_binary:
        opts.binary_location = chromium_binary
        try:
            # Tentar com ChromeType.CHROMIUM para obter o driver correto
            service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        except Exception:
            # Fallback: sem especificar o tipo (usa Chrome padrão)
            try:
                service = Service(ChromeDriverManager().install())
            except Exception:
                service = Service()  # Usa o chromedriver do PATH
    else:
        try:
            service = Service(ChromeDriverManager().install())
        except Exception:
            service = Service()

    driver = webdriver.Chrome(service=service, options=opts)
    # Remover flag webdriver do navigator
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


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
    Scraper ProZ.com usando Selenium headless.
    Recebe as funções auxiliares do monitor_traducao.py como parâmetros.
    """
    from datetime import datetime, timedelta

    vagas: List[Dict] = []
    erros: List[str] = []
    driver = None

    try:
        driver = _criar_driver()
        url = "https://connect.proz.com/language-jobs"
        logger.info("ProZ.com (Selenium): acessando página de vagas...")
        driver.get(url)
        _aguardar_pagina(driver)
        time.sleep(3)  # Aguardar renderização JavaScript

        # Verificar se a página carregou vagas
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        seen_urls: set = set()
        job_links = soup.find_all("a", class_="job_title_link", href=True)
        logger.info(f"ProZ.com (Selenium): {len(job_links)} link(s) de vagas encontrado(s)")

        if not job_links:
            # Tentar padrão alternativo
            job_links = [a for a in soup.find_all("a", href=True)
                         if re.search(r'proz\.com/translation-jobs/\d+', a.get("href", ""))]
            logger.info(f"ProZ.com (Selenium) fallback: {len(job_links)} link(s)")

        for a in job_links:
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

            # Descrição via data-content
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

            pares_relevantes: List[Tuple[str, str]] = []
            area = ""
            contagem_palavras = ""
            formato = ""
            data_pub = ""
            prazo = ""

            if result_wrap:
                full_text = result_wrap.get_text(separator="\n", strip=True)
                m_wc = re.search(r'Word count:\s*([\d,\.]+)', full_text, re.IGNORECASE)
                if m_wc:
                    contagem_palavras = m_wc.group(1).replace(",", ".")
                m_fmt = re.search(r'Format:\s*([^\n]+)', full_text, re.IGNORECASE)
                if m_fmt:
                    formato = m_fmt.group(1).strip()
                m_posted = re.search(
                    r'Posted\s+((?:January|February|March|April|May|June|July|August|'
                    r'September|October|November|December)\s+\d{1,2})',
                    full_text, re.IGNORECASE
                )
                if m_posted:
                    data_pub = _formatar_data(m_posted.group(1).strip())
                delivery_el = result_wrap.find(attrs={"data-title": "Delivery date"})
                if delivery_el:
                    parent_el = delivery_el.parent
                    if parent_el:
                        prazo_text = parent_el.get_text(strip=True)
                        prazo = _formatar_data(prazo_text)
                if not prazo:
                    m_days = re.search(r'Open\s+for\s+(\d+)\s+more\s+days?', full_text, re.IGNORECASE)
                    if m_days:
                        prazo = (datetime.now() + timedelta(days=int(m_days.group(1)))).strftime("%d/%m/%Y")
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
                for li in result_wrap.find_all("li"):
                    if not li.find("span"):
                        text_li = li.get_text(strip=True)
                        src, tgt = _extrair_par_idiomas_titulo(text_li)
                        if _par_relevante(src, tgt):
                            pares_relevantes.append((src, tgt))

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

            pares_unicos = list(dict.fromkeys(pares_relevantes))
            origem, destino = pares_unicos[0]
            par_display = (
                " | ".join(f"{s}→{t}" for s, t in pares_unicos)
                if len(pares_unicos) > 1
                else f"{origem} → {destino}"
            )
            if not area:
                area = _extrair_area(descricao + " " + titulo)
            if not contagem_palavras:
                contagem_palavras = _extrair_contagem_palavras(descricao)
            if not formato:
                formato = _extrair_formato(descricao)
            preco = _extrair_preco(descricao)
            empresa = _extrair_empresa(descricao)
            email_desc = ""
            m_email = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', descricao)
            if m_email and "HIDDEN" not in descricao[max(0, m_email.start() - 5):m_email.end() + 5]:
                email_desc = m_email.group(0)
            tipo_contato = "email" if email_desc else "ProZ.com"
            link_contato = email_desc if email_desc else job_url
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
                "pais": "",
                "preco_palavra": preco,
                "contato_descoberto": contato_descoberto,
            })

        logger.info(f"ProZ.com (Selenium): {len(vagas)} vaga(s) relevante(s) encontrada(s)")

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

        # Login
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
