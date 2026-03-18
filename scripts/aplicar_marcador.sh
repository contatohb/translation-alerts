#!/usr/bin/env bash
# aplicar_marcador.sh
# Após envio do email de tradução, busca a mensagem recém-enviada
# e aplica o marcador "Tradução", removendo "Empregos" e "Viagens".
#
# IDs dos marcadores:
#   Tradução : Label_6923655864710516732
#   Empregos : Label_190
#   Viagens  : Label_104

set -euo pipefail

LABEL_TRADUCAO="Label_6923655864710516732"
LABEL_EMPREGOS="Label_190"
LABEL_VIAGENS="Label_104"

echo "[marcador] Buscando emails recentes com assunto [Tradução]..."

# Buscar IDs dos emails com assunto [Tradução] enviados hoje
RESULT=$(manus-mcp-cli tool call gmail_search_messages \
  --server gmail \
  --input '{"q": "subject:[Tradução] newer_than:1d", "max_results": 10}')

# Extrair message IDs do resultado
MSG_IDS=$(echo "$RESULT" | grep -oP '"message_id":\s*"\K[^"]+' || true)

if [ -z "$MSG_IDS" ]; then
  # Tentar busca mais ampla
  RESULT2=$(manus-mcp-cli tool call gmail_search_messages \
    --server gmail \
    --input '{"q": "subject:[Tradução]", "max_results": 5}')
  MSG_IDS=$(echo "$RESULT2" | grep -oP 'Message ID: \K\S+' || true)
fi

if [ -z "$MSG_IDS" ]; then
  echo "[marcador] Nenhum email encontrado para marcar."
  exit 0
fi

# Converter para array JSON
IDS_JSON=$(echo "$MSG_IDS" | head -5 | python3 -c "
import sys, json
ids = [l.strip() for l in sys.stdin if l.strip()]
print(json.dumps(ids))
")

echo "[marcador] Aplicando marcador Tradução em: $IDS_JSON"

# Aplicar marcador Tradução
manus-mcp-cli tool call gmail_manage_labels \
  --server gmail \
  --input "{\"operation\": \"apply\", \"label_id\": \"$LABEL_TRADUCAO\", \"message_ids\": $IDS_JSON}"

# Remover marcador Empregos
manus-mcp-cli tool call gmail_manage_labels \
  --server gmail \
  --input "{\"operation\": \"remove\", \"label_id\": \"$LABEL_EMPREGOS\", \"message_ids\": $IDS_JSON}" || true

# Remover marcador Viagens
manus-mcp-cli tool call gmail_manage_labels \
  --server gmail \
  --input "{\"operation\": \"remove\", \"label_id\": \"$LABEL_VIAGENS\", \"message_ids\": $IDS_JSON}" || true

echo "[marcador] Marcadores atualizados com sucesso."
