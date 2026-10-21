#!/usr/bin/env bash
#
# Instala o macosvm no Linux, no seu usuário, sem precisar de root.
#
#   ./install.sh                 instala o macosvm
#   ./install.sh --system-deps   instala também os pacotes do sistema (precisa de sudo)
#   ./install.sh --setup         instala e depois prepara o computador (compila o reims-vgpu)
#   ./install.sh --uninstall    desinstala
#
# O macosvm é um gerenciador de VMs macOS. As dependências dele — o reims-vgpu
# e o reims-util — são software livre e são compilados pelo `macosvm setup`.

set -euo pipefail

APP="macosvm"
REPO_URL="https://github.com/Axelthebat/macos-vm-manager"

PREFIX="${HOME}/.local"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
BIN_DIR="${XDG_BIN_HOME:-${HOME}/.local/bin}"
VENV_DIR="${DATA_HOME}/${APP}/venv"

WITH_SYSTEM_DEPS=0
WITH_SETUP=0
UNINSTALL=0

# ----------------------------------------------------------------- saída

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_HEAD=$'\033[1m'; C_OFF=$'\033[0m'
else
    C_OK=""; C_WARN=""; C_ERR=""; C_HEAD=""; C_OFF=""
fi

step() { printf '%s==>%s %s\n' "$C_HEAD" "$C_OFF" "$1"; }
ok()   { printf '%sok  %s %s\n' "$C_OK" "$C_OFF" "$1"; }
warn() { printf '%swarn%s %s\n' "$C_WARN" "$C_OFF" "$1"; }
die()  { printf '%serr %s %s\n' "$C_ERR" "$C_OFF" "$1" >&2; exit 1; }

usage() {
    sed -n '/^# Instala o macosvm/,/^$/p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

# --------------------------------------------------------------- argumentos

while [ $# -gt 0 ]; do
    case "$1" in
        --system-deps) WITH_SYSTEM_DEPS=1 ;;
        --setup)       WITH_SETUP=1 ;;
        --uninstall)   UNINSTALL=1 ;;
        --prefix)      PREFIX="$2"; BIN_DIR="${PREFIX}/bin"; VENV_DIR="${PREFIX}/share/${APP}/venv"; shift ;;
        -h|--help)     usage ;;
        *)             die "opção desconhecida: $1 (tente --help)" ;;
    esac
    shift
done

# ------------------------------------------------------------ desinstalar

if [ "$UNINSTALL" -eq 1 ]; then
    step "removendo o ${APP}"
    if [ -e "${BIN_DIR}/${APP}" ] || [ -L "${BIN_DIR}/${APP}" ]; then
        rm -f "${BIN_DIR}/${APP}"
        ok "o comando ${APP} saiu do PATH"
    fi
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
        ok "o ambiente foi removido (${VENV_DIR})"
    fi
    ok "pronto. As VMs, os backups e os logs continuam onde estavam."
    exit 0
fi

# -------------------------------------------------------------- o python

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
                command -v "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
    die "precisa do Python 3.11 ou mais novo. No Arch: sudo pacman -S python; no Debian/Ubuntu: sudo apt install python3 python3-venv"
fi
ok "python: $("$PYTHON" --version) ($PYTHON)"

# ------------------------------------------------------ pacotes do sistema

install_system_deps() {
    step "pacotes do sistema"

    local packages=()
    local manager=""
    if command -v pacman >/dev/null 2>&1; then
        packages=(base-devel git meson ninja cmake pkg-config glib2 pixman libvulkan vulkan-tools edk2-ovmf)
        manager="pacman -S --needed --noconfirm"
    elif command -v apt-get >/dev/null 2>&1; then
        packages=(build-essential git meson ninja-build cmake pkg-config libglib2.0-dev libpixman-1-dev libvulkan-dev vulkan-tools ovmf qemu-utils)
        manager="apt-get install -y"
    elif command -v dnf >/dev/null 2>&1; then
        packages=(gcc-c++ make git meson ninja-build cmake pkgconf-pkg-config glib2-devel pixman-devel vulkan-devel vulkan-tools edk2-ovmf)
        manager="dnf install -y"
    else
        warn "distribuição não reconhecida; os pacotes do sistema não foram instalados"
        return 0
    fi

    if [ "$(id -u)" -eq 0 ]; then
        sudo $manager "${packages[@]}"
    elif command -v sudo >/dev/null 2>&1; then
        sudo $manager "${packages[@]}"
    else
        die "estes pacotes precisam de root e não há sudo aqui: sudo $manager ${packages[*]}"
    fi
    ok "${#packages[@]} pacotes instalados"
}

if [ "$WITH_SYSTEM_DEPS" -eq 1 ]; then
    install_system_deps
fi

# -------------------------------------------------------------- o macosvm

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

install_with_pipx() {
    step "instalando com o pipx"
    pipx install --force "$HERE"
}

install_with_venv() {
    step "criando o ambiente em ${VENV_DIR}"
    "$PYTHON" -m venv "$VENV_DIR" || die "o módulo venv do Python não está instalado (no Debian/Ubuntu: sudo apt install python3-venv)"

    step "instalando o macosvm"
    "${VENV_DIR}/bin/pip" install --upgrade pip --quiet
    "${VENV_DIR}/bin/pip" install --upgrade "$HERE"

    mkdir -p "$BIN_DIR"
    ln -sf "${VENV_DIR}/bin/${APP}" "${BIN_DIR}/${APP}"
    ok "o comando está em ${BIN_DIR}/${APP}"
}

if command -v pipx >/dev/null 2>&1; then
    install_with_pipx
else
    install_with_venv
fi

# ----------------------------------------------------------------- o PATH

case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *)
        warn "${BIN_DIR} não está no PATH"
        printf '     %s\n' "export PATH=\"${BIN_DIR}:\$PATH\"   # põe no ~/.bashrc ou no ~/.zshrc"
        ;;
esac

# ----------------------------------------------------------------- o setup

if [ "$WITH_SETUP" -eq 1 ]; then
    step "preparando o computador (compila o reims-vgpu; leva um tempo)"
    "${BIN_DIR}/${APP}" setup || die "o setup falhou. Rode '${APP} doctor' para ver o que ficou para trás."
fi

printf '\n'
ok "instalado"
"${BIN_DIR}/${APP}" --version 2>/dev/null || true
printf '\n'
printf 'Próximos passos:\n'
printf '  %s doctor        # o que falta no computador\n' "${APP}"
printf '  %s setup         # compila o reims-vgpu e instala o reims-util\n' "${APP}"
printf '  %s create mac    # a primeira VM\n\n' "${APP}"
printf 'Repositório: %s\n' "$REPO_URL"
