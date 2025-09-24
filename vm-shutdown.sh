#!/bin/bash

TASK_ID=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/TASK_ID)
WEBHOOK_URL=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/WEBHOOK_URL)
WEBHOOK_SECRET=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/WEBHOOK_SECRET)

FLAG_FILE="/tmp/script_executed.flag"

if [[ -f "$FLAG_FILE" ]]; then
  echo "✅ Main script executed, skipping shutdown webhook."
  exit 0
fi

# Construct payload
PAYLOAD="{\"task_id\":\"$TASK_ID\",\"event\":\"vm_shutdown\",\"payload\":{}}"

# Create signature (HMAC SHA256)
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

# Send webhook
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD"

echo "📡 Shutdown webhook sent for task_id=$TASK_ID"
