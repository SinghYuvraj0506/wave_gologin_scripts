#!/bin/bash

exec > /var/log/startup-script.log 2>&1
set -x

# Export env vars from metadata
export TASK_ID=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/TASK_ID)
export GL_API_TOKEN=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/GL_API_TOKEN)
export SOAX_USER_NAME=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/SOAX_USER_NAME)
export SOAX_PASSWORD=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/SOAX_PASSWORD)
export WEBHOOK_URL=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/WEBHOOK_URL)
export WEBHOOK_SECRET=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/WEBHOOK_SECRET)

# Setup
cd /app
source .venv/bin/activate

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

# Shutdown the VM
shutdown -h now
