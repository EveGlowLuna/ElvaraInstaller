#!/usr/bin/env bash

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Root privileges required. Restarting with sudo...${NC}"
    exec sudo bash "$0" "$@"
    exit
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed.${NC}"
    exit 1
fi

REPO_URL="https://github.com/EveGlowLuna/ElvaraInstaller.git"
BRANCH="main"
TAR_URL="https://github.com/EveGlowLuna/ElvaraInstaller/archive/refs/heads/${BRANCH}.tar.gz"

TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"
if command -v git &> /dev/null; then
    echo -e "${CYAN}Cloning repository with git...${NC}"
    git clone --depth 1 -b "$BRANCH" "$REPO_URL" repo
else
    echo -e "${YELLOW}Git not found. Falling back to curl download...${NC}"
    curl -L "$TAR_URL" -o repo.tar.gz
    tar xzf repo.tar.gz
    mv elvara-installer-* repo
fi

cd repo
echo -e "${GREEN}Starting installer...${NC}"
python3 installer_cli.py --tty

# 5. 清理
cd /
rm -rf "$TEMP_DIR"

echo -e "${GREEN}Done. You may reboot now.${NC}"