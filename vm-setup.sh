#!/bin/bash

set -e  # Exit on any error

# System packages
sudo apt update && sudo apt install -y \
    python3 python3-pip python3-venv python3-full \
    unzip xvfb xserver-xephyr tigervnc-standalone-server \
    x11-utils gnumeric curl git

# Remove existing /app if any
sudo rm -rf /app
sudo mkdir -p /app
sudo chown "$USER":"$USER" /app

# Clone repo
git clone https://github.com/SinghYuvraj0506/wave_gologin_scripts.git /app

# Create virtual environment
cd /app
python3 -m venv .venv

# Activate venv and install requirements
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# GoLogin Orbita browser (requires root access)
export MAJOR_VERSION=135
sudo mkdir -p /root/.gologin/browser/orbita-browser-${MAJOR_VERSION}
curl -sL https://orbita-browser-linux.gologin.com/orbita-browser-latest-${MAJOR_VERSION}.tar.gz | \
    sudo tar -xz --strip-components=1 -C /root/.gologin/browser/orbita-browser-${MAJOR_VERSION}

sudo chmod -R a+rx /root/.gologin

# ChromeDriver (match the orbita version)
export CHROMEDRIVER_VERSION=135.0.7049.41
curl -sL "https://storage.googleapis.com/chrome-for-testing-public/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" -o chromedriver.zip
unzip chromedriver.zip
sudo mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver
rm -rf chromedriver.zip chromedriver-linux64