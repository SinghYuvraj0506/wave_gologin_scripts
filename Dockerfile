# syntax=docker/dockerfile:1.4
FROM --platform=linux/amd64 python:3.11-slim as base

ENV DEBIAN_FRONTEND=noninteractive
ARG MAJOR_VERSION=135
ARG CHROMEDRIVER_VERSION=135.0.7049.41

# Update and install system dependencies for Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl unzip gnupg ca-certificates fonts-liberation \
    libnss3 libxss1 libappindicator3-1 libasound2 libatk-bridge2.0-0 \
    libgtk-3-0 libdrm2 libgbm1 libxcomposite1 libxdamage1 libxrandr2 libu2f-udev \
    libgl1 libx11-xcb1 libxshmfence1 libxext6 libxfixes3 libcurl3-gnutls libvulkan1 mesa-utils libgl1-mesa-dri fonts-liberation \
    xvfb xserver-xephyr tigervnc-standalone-server x11-utils gnumeric \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Download and extract Orbita browser
RUN mkdir -p /root/.gologin/browser/orbita-browser-${MAJOR_VERSION} && \
    curl -sL https://orbita-browser-linux.gologin.com/orbita-browser-latest-${MAJOR_VERSION}.tar.gz | \
    tar -xz --strip-components=1 -C /root/.gologin/browser/orbita-browser-${MAJOR_VERSION}

# Add Orbita to PATH
ENV ORBITA_PATH=/root/.gologin/browser/orbita-browser-${MAJOR_VERSION}
ENV PATH="${ORBITA_PATH}:${PATH}"

# Install ChromeDriver matching Orbita version
RUN curl -sL "https://storage.googleapis.com/chrome-for-testing-public/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" -o chromedriver.zip \
    && unzip chromedriver.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf chromedriver.zip chromedriver-linux64

# Copy Python source code
COPY requirements.txt .
# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt

COPY src /src

# Entrypoint
CMD ["python", "/src/index.py"]
