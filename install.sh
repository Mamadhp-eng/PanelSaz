#!/bin/bash

# ==========================================
# Colors
# ==========================================
GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
NC="\033[0m"

# ==========================================
# Variables
# ==========================================
VERSION="1.0.16"
REPO_URL="https://raw.githubusercontent.com/Mamadhp-eng/PanelSaz/main"
WORK_DIR="/root/client_bot"
SERVICE_NAME="client_bot"
FILE_NAME="client_bot"

# ==========================================
# Check Root
# ==========================================
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}❌ Error: Please run this script as root (sudo -i)${NC}"
  exit 1
fi

# ==========================================
# Header
# ==========================================
function print_header() {
    clear
    echo -e "${CYAN}=================================================${NC}"
    echo -e "${GREEN}      🚀 PanelSaz Client Bot Installer 🚀      ${NC}"
    echo -e "${YELLOW}               Version: ${VERSION}               ${NC}"
    echo -e "${CYAN}=================================================${NC}"
    echo -e " 👨‍💻 Creator: Muhammad Hoseinpour"
    echo -e " ✈️ Telegram: t.me/muhammad_hoseinpour"
    echo -e " 🔗 GitHub: github.com/Mamadhp-eng/PanelSaz"
    echo -e "${CYAN}=================================================${NC}"
}

# ==========================================
# Main Menu
# ==========================================
function show_menu() {
    print_header
    echo -e "  [1] 📥 Install New Bot"
    echo -e "  [2] 🔄 Update Bot (Latest Version)"
    echo -e "  [3] ⏹️ Stop Bot Service"
    echo -e "  [4] ▶️ Restart Bot Service"
    echo -e "  [5] 🗑 Uninstall Bot Service"
    echo -e "  [0] ❌ Exit"
    echo -e "${CYAN}=================================================${NC}"
    read -p "Please select an option [0-5]: " choice

    case $choice in
        1) install_bot ;;
        2) update_bot ;;
        3) stop_bot ;;
        4) restart_bot ;;
        5) uninstall_bot ;;
        0) echo -e "${GREEN}Exiting installer. Goodbye!${NC}"; exit 0 ;;
        *) echo -e "${RED}Invalid option! Please try again.${NC}"; sleep 2; show_menu ;;
    esac
}

function install_bot() {
    print_header
    echo -e "${CYAN}--- Installing Client Bot ---${NC}"
    
    # Get Valid Bot Token
    while true; do
        read -p "👉 Enter your Bot Token (e.g., 123456:ABC-DEF): " BOT_TOKEN
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[a-zA-Z0-9_-]+$ ]]; then
            break
        else
            echo -e "${RED}❌ Invalid token format! Please enter a valid Telegram Bot Token.${NC}"
        fi
    done

    # Get Valid Admin ID
    while true; do
        read -p "👉 Enter your numeric Telegram User ID (e.g., 123456789): " ADMIN_ID
        if [[ "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
            break
        else
            echo -e "${RED}❌ Invalid ID format! Please enter numbers only.${NC}"
        fi
    done

    mkdir -p $WORK_DIR
    cd $WORK_DIR
    
    echo -e "${YELLOW}Installing required system packages...${NC}"
    apt update -y
    apt install python3 python3-pip curl wget unzip sqlite3 -y
    
    echo -e "${YELLOW}Downloading bot files from GitHub...${NC}"
    curl -Ls "$REPO_URL/$FILE_NAME" | sed 's/\r$//' > $FILE_NAME
    
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip3 install pyTelegramBotAPI requests pyjwt cryptography --break-system-packages

    echo -e "${YELLOW}Generating Initial Config...${NC}"
    cat <<EOF > config.json
{
    "bot_token": "$BOT_TOKEN",
    "super_admin": $ADMIN_ID,
    "panel_url": "",
    "panel_login_url": "",
    "marzban_admin_username": "",
    "marzban_admin_password": "",
    "card_number": "",
    "card_holder": "",
    "auto_backup_hours": 0,
    "github_url": "https://github.com/Mamadhp-eng/PanelSaz",
    "test_is_active": true,
    "test_volume_gb": 1,
    "test_days": 1,
    "test_limit_per_user": 1,
    "test_group_id": 2,
    "min_deposit": 50000,
    "payg_price_per_gb": 3000,
    "faq_text": "",
    "force_channel": "",
    "license_key": "",
    "btn_buy_panel": "🛒 خرید پنل نمایندگی 🛒",
    "btn_wallet": "👤 کیف پول",
    "btn_my_services": "🌐 سرویس‌های من",
    "btn_buy_license": "🔑 خرید لایسنس ربات",
    "btn_test_config": "🎁 دریافت کانفیگ تست",
    "btn_faq": "❓ سوالات متداول",
    "btn_support": "🎧 ارتباط با پشتیبانی"
}
EOF

    echo -e "${YELLOW}Creating background service (Systemd)...${NC}"
    cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=PanelSaz Client Bot
After=network.target

[Service]
User=root
WorkingDirectory=${WORK_DIR}
ExecStart=${WORK_DIR}/${FILE_NAME}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    systemctl start ${SERVICE_NAME}
    
    echo -e "${GREEN}✅ Installation completed successfully!${NC}"
    echo -e "Go to your bot in Telegram and send /start"
    echo ""
    read -p "Press Enter to return to the main menu..."
    show_menu
}

function update_bot() {
    print_header
    echo -e "${RED}=================================================${NC}"
    echo -e "${YELLOW}              ⚠️ CRITICAL WARNING ⚠️             ${NC}"
    echo -e "${CYAN}Please BACKUP your database from the bot menu before updating!${NC}"
    echo -e "${RED}=================================================${NC}"
    
    read -p "Have you backed up your data? Proceed with update? (y/n): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${YELLOW}Update canceled.${NC}"; sleep 2; show_menu; return
    fi

    echo -e "${CYAN}--- Updating Client Bot ---${NC}"
    if [ -d "$WORK_DIR" ]; then
        cd $WORK_DIR
        echo -e "${YELLOW}Stopping bot service...${NC}"
        systemctl stop ${SERVICE_NAME} 2>/dev/null
        
        echo -e "${YELLOW}Fetching latest code...${NC}"
        curl -Ls "$REPO_URL/$FILE_NAME" | sed 's/\r$//' > $FILE_NAME
        
        echo -e "${YELLOW}Installing new dependencies...${NC}"
        pip3 install pyTelegramBotAPI requests pyjwt cryptography --break-system-packages

        echo -e "${YELLOW}Restarting bot...${NC}"
        systemctl daemon-reload
        systemctl start ${SERVICE_NAME}
        
        echo -e "${GREEN}✅ Bot updated successfully!${NC}"
    else
        echo -e "${RED}❌ Bot is not installed!${NC}"
    fi
    echo ""; read -p "Press Enter to return to the main menu..."
    show_menu
}

function stop_bot() {
    echo -e "${CYAN}--- Stopping Client Bot ---${NC}"
    systemctl stop ${SERVICE_NAME} 2>/dev/null
    echo -e "${GREEN}✅ Bot stopped.${NC}"
    echo ""; read -p "Press Enter to return..."
    show_menu
}

function restart_bot() {
    echo -e "${CYAN}--- Restarting Client Bot ---${NC}"
    systemctl restart ${SERVICE_NAME} 2>/dev/null
    echo -e "${GREEN}✅ Bot restarted.${NC}"
    echo ""; read -p "Press Enter to return..."
    show_menu
}

function uninstall_bot() {
    print_header
    echo -e "${RED}⚠️ Are you sure you want to UNINSTALL the bot files? (y/n): ${NC}"
    read confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        echo -e "${YELLOW}Removing service and files...${NC}"
        systemctl stop ${SERVICE_NAME} 2>/dev/null
        systemctl disable ${SERVICE_NAME} 2>/dev/null
        rm -f /etc/systemd/system/${SERVICE_NAME}.service
        systemctl daemon-reload
        rm -rf $WORK_DIR
        echo -e "${GREEN}✅ Bot and all its files have been permanently deleted.${NC}"
    else
        echo -e "${GREEN}Operation canceled.${NC}"
    fi
    echo ""; read -p "Press Enter to return..."
    show_menu
}

# Execute
show_menu
