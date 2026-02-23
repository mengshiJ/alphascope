#!/usr/bin/env bash
# ============================================================
#  AlphaScope — One-line Install
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/mengshiJ/alphascope/main/install.sh | bash
# ============================================================
set -e

REPO_URL="https://github.com/mengshiJ/alphascope"
RAW_URL="https://raw.githubusercontent.com/mengshiJ/alphascope/main"
INSTALL_DIR="${HOME}/.openclaw/workspace/skills/x-cookie-browser"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}▶ $*${NC}"; }
ok()    { echo -e "${GREEN}✅ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $*${NC}"; }
err()   { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        AlphaScope Installer          ║${NC}"
echo -e "${CYAN}║  KOL Alpha Monitoring for OpenClaw   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. 检查依赖 ──────────────────────────────────────────────
info "Checking dependencies..."

command -v python3 >/dev/null 2>&1 || err "python3 not found. Install it first."
command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1 || err "pip not found. Install python3-pip first."
command -v openclaw >/dev/null 2>&1 || err "openclaw not found. Install OpenClaw first: https://docs.openclaw.ai"

PIP=$(command -v pip3 || command -v pip)
ok "Dependencies OK"

# ── 2. 创建目录结构 ──────────────────────────────────────────
info "Setting up directories..."
mkdir -p "${INSTALL_DIR}/config"
mkdir -p "${INSTALL_DIR}/scripts"
mkdir -p "${INSTALL_DIR}/data/history"
mkdir -p "${HOME}/.openclaw/workspace/.secrets"
ok "Directories ready"

# ── 3. 下载文件 ──────────────────────────────────────────────
info "Downloading AlphaScope files..."

download() {
  local src="$1" dst="$2"
  curl -fsSL "${RAW_URL}/${src}" -o "${INSTALL_DIR}/${dst}"
}

# Scripts
download "scripts/list_scraper.py"      "scripts/list_scraper.py"
download "scripts/hourly_summary.py"    "scripts/hourly_summary.py"
download "scripts/digest_generator.py"  "scripts/digest_generator.py"
download "scripts/alpha_tracker.py"     "scripts/alpha_tracker.py"
download "scripts/filter_agent_v2.py"   "scripts/filter_agent_v2.py"
download "scripts/format_agent_v3.py"   "scripts/format_agent_v3.py"
download "scripts/x_fetch.py"           "scripts/x_fetch.py"
download "scripts/dex_utils.py"         "scripts/dex_utils.py"
download "scripts/cleanup_history.py"   "scripts/cleanup_history.py"

# Config template (only if user config doesn't exist yet)
download "config/system_config.example.json" "config/system_config.example.json"
if [ ! -f "${INSTALL_DIR}/config/user_profiles.json" ]; then
  download "config/user_profiles.example.json" "config/user_profiles.json"
fi

# Skill definition
download "SKILL.md"    "SKILL.md"
download "INSTALL.md"  "INSTALL.md"

ok "Files downloaded"

# ── 4. 安装 Python 依赖 ──────────────────────────────────────
info "Installing Python packages..."
$PIP install -q twikit playwright 2>&1 | tail -3
ok "Python packages installed"

# ── 5. 配置文件向导 ──────────────────────────────────────────
CONFIG_FILE="${INSTALL_DIR}/config/system_config.json"

if [ -f "${CONFIG_FILE}" ]; then
  warn "Config already exists at ${CONFIG_FILE} — skipping setup wizard."
else
  echo ""
  echo -e "${YELLOW}══════════════════════════════════════${NC}"
  echo -e "${YELLOW}  Quick Config Setup${NC}"
  echo -e "${YELLOW}══════════════════════════════════════${NC}"
  echo ""
  echo "You'll need:"
  echo "  1. X/Twitter List ID  (x.com/i/lists/<LIST_ID>)"
  echo "  2. X cookies JSON     (export from browser, see INSTALL.md)"
  echo "  3. Discord channel IDs (right-click channel → Copy ID)"
  echo ""

  read -r -p "  Enter your X List ID: " LIST_ID
  read -r -p "  Enter path to x_cookies.json [${HOME}/.openclaw/workspace/.secrets/x_cookies.json]: " COOKIES_PATH
  COOKIES_PATH="${COOKIES_PATH:-${HOME}/.openclaw/workspace/.secrets/x_cookies.json}"

  read -r -p "  Discord #x-realtime channel ID: " CH_REALTIME
  read -r -p "  Discord #x-alerts channel ID [same as realtime]: " CH_ALERTS
  CH_ALERTS="${CH_ALERTS:-${CH_REALTIME}}"
  read -r -p "  Discord #x-digest channel ID: " CH_DIGEST
  read -r -p "  Discord #alpha-weekly channel ID: " CH_WEEKLY

  cat > "${CONFIG_FILE}" <<JSON
{
  "x": {
    "list_id": "${LIST_ID}",
    "cookies_path": "${COOKIES_PATH}",
    "fetch_count": 100,
    "seen_ids_retention_days": 7
  },
  "discord": {
    "realtime_channel_id": "${CH_REALTIME}",
    "alerts_channel_id": "${CH_ALERTS}",
    "digest_channel_id": "${CH_DIGEST}",
    "alpha_weekly_channel_id": "${CH_WEEKLY}"
  },
  "data": {
    "data_dir": null
  }
}
JSON
  ok "Config saved to ${CONFIG_FILE}"
fi

# ── 6. 测试 ──────────────────────────────────────────────────
echo ""
info "Running quick test..."
if python3 "${INSTALL_DIR}/scripts/list_scraper.py" 2>&1 | tail -5; then
  ok "Scraper test passed!"
else
  warn "Scraper test had warnings — check INSTALL.md for troubleshooting."
fi

# ── 7. 完成 ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Install Complete! 🎉        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  📁 Installed to: ${INSTALL_DIR}"
echo "  📋 Config:       ${CONFIG_FILE}"
echo ""
echo "  Next steps:"
echo "  1. Make sure your X cookies file is at:"
echo "     ${COOKIES_PATH}"
echo ""
echo "  2. Customize your KOL list:"
echo "     ${INSTALL_DIR}/config/user_profiles.json"
echo ""
echo "  3. Set up cron jobs in your OpenClaw session:"
echo "     Tell your agent: 'Read INSTALL.md at ${INSTALL_DIR}/INSTALL.md'"
echo "     and ask it to set up the cron jobs."
echo ""
echo "  Full guide: ${INSTALL_DIR}/INSTALL.md"
echo "  Repo:       ${REPO_URL}"
echo ""
