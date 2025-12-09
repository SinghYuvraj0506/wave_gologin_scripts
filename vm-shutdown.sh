#!/bin/bash

# 1. Force logs to appear in Google Cloud Logging (Serial Console)
exec 1> >(logger -s -t $(basename $0)) 2>&1

echo "⚠️ Shutdown script initiated. Checking status..."

# 2. Retry Logic for Metadata (Crucial during shutdown instability)
get_metadata() {
  curl -s --retry 3 --retry-delay 1 --max-time 2 -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"
}

TASK_ID=$(get_metadata TASK_ID)
WEBHOOK_URL=$(get_metadata WEBHOOK_URL)
WEBHOOK_SECRET=$(get_metadata WEBHOOK_SECRET)

FLAG_FILE="/tmp/script_executed.flag"

# 3. Check for the flag, but log clearly if found
if [[ -f "$FLAG_FILE" ]]; then
  echo "✅ Success flag found ($FLAG_FILE). Assuming task completed normally. Exiting."
  exit 0
else
  echo "❌ No success flag found. This is a PREEMPTION or FAILURE."
fi

# 4. Validate Variables
if [[ -z "$WEBHOOK_URL" ]]; then
  echo "🔥 CRITICAL: Webhook URL is empty. Cannot send notification."
  exit 1
fi

# Construct payload
PAYLOAD="{\"task_id\":\"$TASK_ID\",\"event\":\"vm_shutdown\",\"payload\":{}}"

# Create signature
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

echo "Attempting to send webhook to $WEBHOOK_URL..."

# 5. Verbose Curl with detailed error logging
# --fail: Returns error code on 400/500 errors
# --connect-timeout: Don't wait forever, you only have 30s
RESPONSE=$(curl -v --fail --connect-timeout 5 --max-time 10 -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD" 2>&1)

if [[ $? -eq 0 ]]; then
  echo "📡 Shutdown webhook sent successfully."
else
  echo "🔥 Webhook FAILED. Curl Output:"
  echo "$RESPONSE"
fi