#!/bin/bash

# ==========================================
# GitHub Auto-Installer Script
# ==========================================
BINARY_URL="https://raw.githubusercontent.com/mamadhp-eng/PanelSaz/main/client_bot"

VERSION="1.0.16"
CREATOR="t.me/muhammad_hosein_pour"
SERVICE_NAME="pasargad_bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
BOT_DIR="/root/pasargad_panel"
BOT_FILE="client_bot"

function show_banner() {
    clear
    echo -e "\e[1;36m====================================================\e[0m"
    echo -e "\e[1;32m      Pasargad Panel Bot Ultimate Installer         \e[0m"
    echo -e "\e[1;33m      Version: $VERSION                             \e[0m"
    echo -e "\e[1;35m      Creator: $CREATOR                             \e[0m"
    echo -e "\e[1;36m====================================================\e[0m"
    echo ""
}

function print_msg() { echo -e "\e[1;32m[+] $1\e[0m"; }
function print_err() { echo -e "\e[1;31m[-] $1\e[0m"; }

function install_bot() {
    show_banner
    print_msg "Starting Installation..."
    
    mkdir -p $BOT_DIR
    cd $BOT_DIR
    
    print_msg "Downloading Bot Core..."
    # دانلود فایل و ذخیره آن
    wget -qO $BOT_FILE $BINARY_URL
    
    # بررسی اینکه آیا فایل واقعا دانلود شده و یک فایل متنی/HTML نیست
    if grep -q "404: Not Found" $BOT_FILE; then
        print_err "Error: Binary file not found on GitHub! Check the BINARY_URL."
        exit 1
    fi

    chmod +x $BOT_FILE
    
    while true; do
        read -p "Enter your Telegram Bot Token (e.g. 123456:ABC-DEF): " BOT_TOKEN
        if [[ $BOT_TOKEN =~ ^[0-9]+:[a-zA-Z0-9_-]+$ ]]; then break; else print_err "Invalid Token!"; fi
    done

    while true; do
        read -p "Enter your Numeric Telegram Admin ID (e.g. 123456789): " ADMIN_ID
        if [[ $ADMIN_ID =~ ^[0-9]+$ ]]; then break; else print_err "Invalid ID!"; fi
    done

    print_msg "Generating config.json..."
    cat <<EOF > config.json
{
    "bot_token": "$BOT_TOKEN",
    "super_admin": $ADMIN_ID,
    "panel_url": "",
    "marzban_admin_username": "",
    "marzban_admin_password": "",
    "card_number": "",
    "card_holder": "",
    "auto_backup_hours": 0,
    "license_key": ""
}
EOF

    print_msg "Creating background service..."
    sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Pasargad Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/$BOT_FILE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    sudo systemctl start $SERVICE_NAME

    print_msg "Installation Complete! Go to your bot and send /start"
    echo -e "\e[1;33m⚠️ Note: The bot will ask for a License Key upon first interaction.\e[0m"
}

install_bot
