#!/bin/bash

exec > /var/log/startup-script.log 2>&1
set -x

# Export env vars from metadata
export TASK_ID=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/TASK_ID)
export GL_API_TOKEN=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/GL_API_TOKEN)
export SOAX_USER_NAME=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/SOAX_USER_NAME)
export SOAX_PASSWORD=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/SOAX_PASSWORD)
export SOAX_HOST=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/SOAX_HOST)
export SOAX_PORT=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/SOAX_PORT)
export EVOMI_USER_NAME=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EVOMI_USER_NAME)
export EVOMI_PASSWORD=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EVOMI_PASSWORD)
export EVOMI_HOST=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EVOMI_HOST)
export EVOMI_PORT=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/EVOMI_PORT)
export PROXY_PROVIDER=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/PROXY_PROVIDER)
export WEBHOOK_URL=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/WEBHOOK_URL)
export WEBHOOK_SECRET=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/WEBHOOK_SECRET)
export HEARTBEAT_INTERVAL=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/HEARTBEAT_INTERVAL)

# Setup
cd /app
source .venv/bin/activate

echo "🚀 Starting VM initialization..."

# CRITICAL: Wait for network to be fully ready
echo "⏳ Waiting for network stack..."
sleep 5

# Wait for DNS to be ready
echo "⏳ Waiting for DNS..."
until host google.com > /dev/null 2>&1; do
    echo "   DNS not ready, waiting..."
    sleep 2
done
echo "✅ DNS ready"

# Test internet connectivity
echo "⏳ Testing internet..."
until curl -s --max-time 5 http://clients3.google.com/generate_204 > /dev/null; do
    echo "   Internet not ready, waiting..."
    sleep 2
done
echo "✅ Internet ready"

# Additional grace period
echo "⏳ Grace period (5s)..."
sleep 5

echo "✅ Network fully initialized, starting application..."

# Run your main script
python3 src/index.py

# Conditional log upload
if [[ "${SAVE_LOGS,,}" == "true" ]]; then
    BUCKET_NAME="wave-tasks-logs"
    LOG_FILE="/var/log/startup-script.log"
    LOG_DESTINATION="gs://${BUCKET_NAME}/startup-logs/${TASK_ID}.log"

    # Ensure Google Cloud SDK is installed
    if ! command -v gsutil &> /dev/null; then
        echo "Installing Google Cloud SDK tools..."
        apt-get update && apt-get install -y google-cloud-sdk
    fi

    # Upload log to GCS
    gsutil cp "$LOG_FILE" "$LOG_DESTINATION"
    UPLOAD_STATUS=$?

    sync

    if [ $UPLOAD_STATUS -eq 0 ]; then
        echo "Logs uploaded successfully to ${LOG_DESTINATION}."
    else
        echo "Log upload failed."
    fi
else
    echo "SAVE_LOGS is not set to true — skipping log upload."
fi

# Delete VM
python3 src/delete_vm.py

# Shutdown the VM
shutdown -h now
