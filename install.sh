#!/bin/bash

# ==========================================
# Colors for output
# ==========================================
GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
NC="\033[0m"

# ==========================================
# Variables
# ==========================================
# Your exact GitHub raw URL
REPO_URL="https://raw.githubusercontent.com/Mamadhp-eng/PanelSaz/main"
WORK_DIR="/root/client_bot"
SERVICE_NAME="client_bot"
FILE_NAME="client_bot.py"

# ==========================================
# Check Root Privilege
# ==========================================
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}❌ Error: Please run this script as root (sudo -i)${NC}"
  exit 1
fi

# ==========================================
# Main Menu
# ==========================================
function show_menu() {
    clear
    echo -e "${CYAN}=================================================${NC}"
    echo -e "${GREEN}        🚀 PanelSaz Client Bot Installer 🚀      ${NC}"
    echo -e "${CYAN}=================================================${NC}"
    echo -e "  [1] 📥 Install New Bot"
    echo -e "  [2] 🔄 Update Bot (Latest Version)"
    echo -e "  [3] 🗑 Uninstall Bot Service"
    echo -e "  [0] ❌ Exit"
    echo -e "${CYAN}=================================================${NC}"
    read -p "Please select an option [0-3]: " choice

    case $choice in
        1) install_bot ;;
        2) update_bot ;;
        3) uninstall_bot ;;
        0) echo -e "${GREEN}Exiting installer. Goodbye!${NC}"; exit 0 ;;
        *) echo -e "${RED}Invalid option! Please try again.${NC}"; sleep 2; show_menu ;;
    esac
}

function install_bot() {
    clear
    echo -e "${CYAN}--- Installing Client Bot ---${NC}"
    
    mkdir -p $WORK_DIR
    cd $WORK_DIR
    
    echo -e "${YELLOW}Installing required system packages...${NC}"
    apt update -y
    apt install python3 python3-pip curl wget unzip sqlite3 -y
    
    echo -e "${YELLOW}Downloading bot files from GitHub...${NC}"
    curl -Ls "$REPO_URL/$FILE_NAME" | sed 's/\r$//' > $FILE_NAME
    
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip3 install pyTelegramBotAPI requests pyjwt cryptography --break-system-packages

    echo -e "${YELLOW}Creating background service (Systemd)...${NC}"
    cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=PanelSaz Client Bot
After=network.target

[Service]
User=root
WorkingDirectory=${WORK_DIR}
ExecStart=/usr/bin/python3 ${WORK_DIR}/${FILE_NAME}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    systemctl start ${SERVICE_NAME}
    
    echo -e "${GREEN}✅ Installation completed successfully!${NC}"
    echo -e "To view live logs, use the following command:"
    echo -e "${CYAN}journalctl -u ${SERVICE_NAME} -f${NC}"
    echo ""
    read -p "Press Enter to return to the main menu..."
    show_menu
}

function update_bot() {
    clear
    echo -e "${RED}=================================================${NC}"
    echo -e "${YELLOW}              ⚠️ CRITICAL WARNING ⚠️             ${NC}"
    echo -e "${CYAN}Please BACKUP your database and user data before updating!${NC}"
    echo -e "If your bot has a backup feature, use it now via Telegram."
    echo -e "${RED}=================================================${NC}"
    
    read -p "Have you backed up your data? Do you want to proceed with the update? (y/n): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${YELLOW}Update canceled. Returning to menu...${NC}"
        sleep 2
        show_menu
        return
    fi

    echo -e "${CYAN}--- Updating Client Bot ---${NC}"
    
    if [ -d "$WORK_DIR" ]; then
        cd $WORK_DIR
        echo -e "${YELLOW}Stopping current bot service...${NC}"
        systemctl stop ${SERVICE_NAME} 2>/dev/null
        
        echo -e "${YELLOW}Fetching latest code from GitHub...${NC}"
        curl -Ls "$REPO_URL/$FILE_NAME" | sed 's/\r$//' > $FILE_NAME
        
        echo -e "${YELLOW}Checking and installing any new Python dependencies...${NC}"
        pip3 install pyTelegramBotAPI requests pyjwt cryptography --break-system-packages

        echo -e "${YELLOW}Restarting bot service...${NC}"
        systemctl daemon-reload
        systemctl start ${SERVICE_NAME}
        
        echo -e "${GREEN}✅ Bot updated successfully to the latest version! (Your database is safe)${NC}"
    else
        echo -e "${RED}❌ Bot is not installed on this server! Please choose option [1] to install it first.${NC}"
    fi
    
    echo ""
    read -p "Press Enter to return to the main menu..."
    show_menu
}

function uninstall_bot() {
    clear
    echo -e "${RED}⚠️ Are you sure you want to UNINSTALL the bot service? (y/n): ${NC}"
    read confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        echo -e "${YELLOW}Removing system service...${NC}"
        systemctl stop ${SERVICE_NAME} 2>/dev/null
        systemctl disable ${SERVICE_NAME} 2>/dev/null
        rm -f /etc/systemd/system/${SERVICE_NAME}.service
        systemctl daemon-reload
        echo -e "${GREEN}✅ Bot service has been stopped and removed.${NC}"
        echo -e "${YELLOW}Note: Your main directory (${WORK_DIR}) and database were NOT deleted to prevent data loss.${NC}"
    else
        echo -e "${GREEN}Operation canceled.${NC}"
    fi
    echo ""
    read -p "Press Enter to return to the main menu..."
    show_menu
}

# Execute main menu
show_menu
