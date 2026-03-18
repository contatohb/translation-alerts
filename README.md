# Sistema de Alertas de Vagas de Tradução

Sistema automatizado de alertas diários para vagas de tradução em ProZ.com, Translators Café e Translation Directory.

## Pares de Idiomas Monitorados

| Par | Direção |
|-----|---------|
| Português ↔ Inglês | PT→EN e EN→PT |
| Português ↔ Espanhol | PT→ES e ES→PT |
| Inglês ↔ Espanhol | EN→ES e ES→EN |

## Fontes Monitoradas

| Fonte | URL | Campos Extraídos |
|-------|-----|-----------------|
| **ProZ.com** | [connect.proz.com/language-jobs](https://connect.proz.com/language-jobs) | Título, par de idiomas, área, prazo, descrição, empresa |
| **Translators Café** | [translatorscafe.com/cafe/SearchJobs.asp](https://www.translatorscafe.com/cafe/SearchJobs.asp) | Título, par de idiomas, tipo de serviço, data de publicação |
| **Translation Directory** | [translationdirectory.com](https://www.translationdirectory.com/translation_jobs/) | Título, par, área, palavras, formato, preço/palavra, prazo, empresa, país, contato |

## Estrutura do Projeto

```
translation-alerts/
├── scripts/
│   ├── monitor_traducao.py    # Scraping, filtragem e busca reversa de contatos
│   ├── email_template.py      # Template HTML premium da newsletter
│   └── alerta_traducao.py     # Orquestração e envio via Gmail MCP
├── .github/
│   └── workflows/
│       └── daily-translation-alert.yml  # Agendamento diário às 8h BRT
├── data/
│   └── traducao_seen.json     # Histórico de vagas já alertadas
├── .env.example               # Variáveis de ambiente
└── README.md
```

## Automação com GitHub Actions

O sistema executa automaticamente todos os dias às **08:00 BRT** (11:00 UTC).

Para executar manualmente:
1. Acesse a aba **Actions** do repositório
2. Selecione **Daily Translation Alert**
3. Clique em **Run workflow**

## Informações Incluídas nos Emails

Para cada vaga encontrada, o email inclui os seguintes campos (quando disponíveis):

| Campo | Fontes |
|-------|--------|
| Título da vaga | Todas |
| Par de idiomas (origem → destino) | Todas |
| Área de especialização | Todas |
| Contagem de palavras | TD, ProZ |
| Formato do arquivo | TD, ProZ |
| Preço por palavra | TD |
| País | TD |
| Empresa | TD, ProZ, TC (quando no título) |
| Pessoa de contato | TD |
| Prazo de entrega | TD, ProZ |
| Data de publicação | Todas |
| Descrição detalhada | TD, ProZ |
| Link direto para a vaga | Todas |
| Contato direto (email/site) | TD (quando disponível) |
| **Contato descoberto** (busca reversa) | TD (quando empresa conhecida) |

## Busca Reversa de Contatos

Quando uma vaga do **Translation Directory** não possui email de contato direto mas inclui o nome da empresa, o sistema tenta automaticamente:

1. Construir a URL provável do site da empresa (ex.: `www.nomeempresa.com`)
2. Visitar a homepage e extrair emails de contato
3. Localizar a página de contato e extrair emails

O resultado aparece na newsletter com destaque verde ("Contato Descoberto") e um botão de candidatura direta.

## Deduplicação

O sistema mantém o histórico em `data/traducao_seen.json`. Cada vaga é identificada pela sua URL única — nenhuma vaga é alertada mais de uma vez.

## Uso Local

```bash
# Instalar dependências
pip install requests beautifulsoup4 python-dotenv

# Executar alerta
cd scripts && python alerta_traducao.py
```

## Configuração de Email

O sistema utiliza a integração **Gmail via MCP** (Model Context Protocol) para enviar os emails, sem necessidade de senha de aplicativo.

## Parte do Sistema Intellicore

Este projeto integra o ecossistema de automações do Hudson Borges.
