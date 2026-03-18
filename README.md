# Sistema de Alertas de Vagas de Tradução

Sistema automatizado de alertas diários para vagas de tradução em ProZ.com e Translators Café.

## Pares de Idiomas Monitorados

| Par | Direção |
|-----|---------|
| Português ↔ Inglês | PT→EN e EN→PT |
| Português ↔ Espanhol | PT→ES e ES→PT |
| Inglês ↔ Espanhol | EN→ES e ES→EN |

## Fontes Monitoradas

- **ProZ.com** — [connect.proz.com/language-jobs](https://connect.proz.com/language-jobs)
- **Translators Café** — [translatorscafe.com/cafe/SearchJobs.asp](https://www.translatorscafe.com/cafe/SearchJobs.asp)

## Estrutura do Projeto

```
translation-alerts/
├── scripts/
│   ├── monitor_traducao.py    # Scraping e filtragem das vagas
│   └── alerta_traducao.py     # Envio de email via Gmail MCP
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

Para cada vaga encontrada, o email inclui:

- Título da vaga
- Par de idiomas (origem → destino)
- Área de especialização
- Contagem de palavras (quando disponível)
- Formato do arquivo (quando disponível)
- Prazo de entrega (quando disponível)
- Data de publicação
- Fonte (ProZ.com ou Translators Café)
- Link direto para a vaga
- Contato (email, URL ou via plataforma)
- Status do envio do CV

## Deduplicação

O sistema mantém o histórico em `data/traducao_seen.json`. Cada vaga é identificada pela sua URL única — nenhuma vaga é alertada mais de uma vez.

## Uso Local

```bash
# Instalar dependências
pip install requests beautifulsoup4 python-dotenv

# Executar alerta
cd scripts && python alerta_traducao.py

# Forçar envio mesmo sem novidades
cd scripts && python alerta_traducao.py --force-send
```

## Configuração de Email

O sistema utiliza a integração **Gmail via MCP** (Model Context Protocol) para enviar os emails, sem necessidade de senha de aplicativo.

## Parte do Sistema Intellicore

Este projeto integra o ecossistema de automações do Hudson Borges.
