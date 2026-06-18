#!/usr/bin/env bash
#
#  cine-cli installer
#  Usage: curl -fsSL https://raw.githubusercontent.com/4shil/cine-cli/main/install.sh | bash
#

set -euo pipefail

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── helpers ─────────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}ℹ${RESET}  $*"; }
ok()      { echo -e "${GREEN}✔${RESET}  $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
err()     { echo -e "${RED}✘${RESET}  $*"; }
header()  { echo -e "\n${BOLD}${PURPLE}$*${RESET}\n"; }

# ── animation ───────────────────────────────────────────────────────────────
spinner() {
    local pid=$1
    local msg="${2:-Working...}"
    local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r${CYAN}%s${RESET} %s" "${frames[$i]}" "$msg"
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.08
    done
    printf "\r%-${#msg}s\r" ""          # clear line
}

run_with_spinner() {
    local msg="$1"; shift
    "$@" &>/dev/null &
    local pid=$!
    spinner "$pid" "$msg"
    wait "$pid"
}

# ── banner ──────────────────────────────────────────────────────────────────
clear 2>/dev/null || true
echo -e "${BOLD}${PURPLE}"
echo "   ██████╗██╗███╗   ██╗███████╗     ██████╗██╗     ██╗"
echo "  ██╔════╝██║████╗  ██║██╔════╝    ██╔════╝██║     ██║"
echo "  ██║     ██║██╔██╗ ██║█████╗      ██║     ██║     ██║"
echo "  ██║     ██║██║╚██╗██║██╔══╝      ██║     ██║     ██║"
echo "  ╚██████╗██║██║ ╚████║███████╗    ╚██████╗███████╗██║"
echo "   ╚═════╝╚═╝╚═╝  ╚═══╝╚══════╝     ╚═════╝╚══════╝╚═╝"
echo -e "${RESET}"
echo -e "  ${BOLD}Watch everything from your terminal.${RESET}"
echo -e "  ${CYAN}github.com/4shil/cine-cli${RESET}\n"

# ── pre-flight checks ──────────────────────────────────────────────────────
header "Checking requirements"

HAVE_PYTHON=false
HAVE_PIPX=false
HAVE_GIT=false

if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    ok "Python ${PY_VER} found"
    HAVE_PYTHON=true
else
    err "Python 3 not found"
fi

if command -v pipx &>/dev/null; then
    ok "pipx found"
    HAVE_PIPX=true
else
    warn "pipx not found"
fi

if command -v git &>/dev/null; then
    ok "git found"
    HAVE_GIT=true
else
    warn "git not found"
fi

if command -v mpv &>/dev/null; then
    ok "mpv found ($(mpv --version 2>&1 | head -1))"
else
    warn "mpv not found — you'll need it to play media"
fi

if ! $HAVE_PYTHON; then
    err "Python 3 is required. Install it and re-run this script."
    exit 1
fi

# ── install missing tools ───────────────────────────────────────────────────
if ! $HAVE_GIT; then
    info "Installing git..."
    if command -v pacman &>/dev/null; then
        run_with_spinner "Installing git..." sudo pacman -S --noconfirm git
    elif command -v apt &>/dev/null; then
        run_with_spinner "Installing git..." sudo apt install -y git
    else
        err "Cannot install git automatically. Please install git manually."
        exit 1
    fi
    HAVE_GIT=true
fi

if ! $HAVE_PIPX; then
    info "Installing pipx..."
    if command -v pacman &>/dev/null; then
        run_with_spinner "Installing pipx..." sudo pacman -S --noconfirm python-pipx
    elif command -v apt &>/dev/null; then
        run_with_spinner "Installing pipx..." sudo apt install -y pipx
    else
        python3 -m pip install --user pipx 2>/dev/null || true
    fi
    export PATH="$HOME/.local/bin:$PATH"
    HAVE_PIPX=true
fi

# ── clone repo ──────────────────────────────────────────────────────────────
header "Cloning cine-cli"

REPO_DIR="$HOME/Coding/cine-cli"

if [ -d "$REPO_DIR/.git" ]; then
    info "cine-cli already cloned at ${REPO_DIR}, updating..."
    cd "$REPO_DIR"
    run_with_spinner "Pulling latest changes..." git pull --rebase
else
    run_with_spinner "Cloning cine-cli..." git clone https://github.com/4shil/cine-cli.git "$REPO_DIR"
    cd "$REPO_DIR"
fi
ok "Repository ready at ${REPO_DIR}"

# ── install cine-cli ────────────────────────────────────────────────────────
header "Installing cine-cli"

if command -v pipx &>/dev/null || [ -f "$HOME/.local/bin/pipx" ]; then
    export PATH="$HOME/.local/bin:$PATH"
    run_with_spinner "Installing cine-cli via pipx..." pipx install "$REPO_DIR"
    ok "cine-cli installed"
else
    # fallback: uv pip install into a venv
    warn "pipx not available, using uv venv"
    if ! command -v uv &>/dev/null; then
        run_with_spinner "Installing uv..." curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
    run_with_spinner "Setting up venv..." uv venv "$REPO_DIR/.venv"
    run_with_spinner "Installing cine-cli..." uv pip install -e "$REPO_DIR"
    ok "cine-cli installed in ${REPO_DIR}/.venv"
fi

# ── config ──────────────────────────────────────────────────────────────────
header "Configuration"

CONFIG_DIR="$HOME/.config/cine-cli"
CONFIG_FILE="$CONFIG_DIR/config.toml"

mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" <<'EOF'
# cine-cli configuration
# https://github.com/4shil/cine-cli/wiki/Configuration

[cine-cli]
version = 1
debug = false
player = "mpv"
quality = "auto"
skip_update_checker = false
auto_try_next_scraper = true
hide_ip = true

[cine-cli.ui]
preview = true
watch_options = false
display_quality = false

[cine-cli.plugins]
tmdb = "cine-cli"

[cine-cli.scrapers]
default = "tmdb"

[cine-cli.http]
timeout = 30
EOF
    ok "Default config written to ${CONFIG_FILE}"
else
    info "Config already exists at ${CONFIG_FILE}, skipping"
fi

# ── verify ──────────────────────────────────────────────────────────────────
header "Verification"

export PATH="$HOME/.local/bin:$PATH"

if command -v cine-cli &>/dev/null; then
    CINE_VER=$(cine-cli --version 2>&1 | grep -oP '[\d.]+$' || echo "unknown")
    ok "cine-cli v${CINE_VER} is ready!"
else
    warn "cine-cli not in PATH yet. Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── done ────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}${GREEN}Installation complete!${RESET}\n"
echo -e "  Start watching:  ${CYAN}cine-cli \"Inception\"${RESET}"
echo -e "  List scrapers:  ${CYAN}cine-cli --list-plugins${RESET}"
echo -e "  Edit config:    ${CYAN}cine-cli -e${RESET}"
echo -e "  Get help:       ${CYAN}cine-cli --help${RESET}"
echo ""
