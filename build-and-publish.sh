#!/usr/bin/env bash
# build-and-publish.sh — Build and push cups-prometheus-exporter to GHCR
#
# Usage:
#   bash build-and-publish.sh          # build + push latest
#   bash build-and-publish.sh 1.0.0    # build + push with version tag
#
# Requirements:
#   - git, docker
#   - One of: gh CLI (preferred) or GITHUB_TOKEN env var with write:packages scope
#     GHCR login is handled automatically by this script
#
# Location: cups-prometheus-exporter/build-and-publish.sh

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
GHCR_USER="variablenix"
IMAGE="ghcr.io/${GHCR_USER}/cups-prometheus-exporter"
TAG="latest"

# ─────────────────────────────────────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
DIM="\033[2m"

# ─────────────────────────────────────────────────────────────────────────────
# Parse args — optional version tag
# ─────────────────────────────────────────────────────────────────────────────
if [[ "${1:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  VERSION="${1}"
else
  VERSION=""
fi

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   cups-prometheus-exporter — Build & Push    ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo -e "${DIM}  Image   : ${IMAGE}:${TAG}${RESET}"
[[ -n "${VERSION}" ]] && echo -e "${DIM}  Version : ${IMAGE}:${VERSION}${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Preflight — verify GHCR auth before doing any work
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}  Preflight checks${RESET}"

if command -v gh &>/dev/null; then
  if ! gh auth status &>/dev/null; then
    echo -e "  ${RED}✗ gh CLI is not authenticated${RESET}"
    echo -e "  ${DIM}  Run: gh auth login${RESET}"
    echo -e "  ${DIM}  Then re-run this script${RESET}"
    exit 1
  fi
elif [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo -e "  ${RED}✗ No GHCR auth available${RESET}"
  echo -e "  ${DIM}  Install gh CLI and run: gh auth login${RESET}"
  echo -e "  ${DIM}  Or: export GITHUB_TOKEN=<token with write:packages>${RESET}"
  exit 1
fi

echo -e "  ${GREEN}✓${RESET} Auth available"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Authenticate to GHCR
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}  1. Authenticating to GHCR${RESET}"
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
  echo -e "  ${GREEN}✓${RESET} Logged in via GITHUB_TOKEN env"
elif command -v gh &>/dev/null; then
  gh auth token | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
  echo -e "  ${GREEN}✓${RESET} Logged in via gh CLI"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Build Docker image
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}  2. Building Docker image${RESET}"
echo -e "${DIM}  This may take a minute on first build${RESET}"
echo ""

if [[ -n "${VERSION}" ]]; then
  docker build \
    --no-cache \
    -t "${IMAGE}:${TAG}" \
    -t "${IMAGE}:${VERSION}" \
    .
else
  docker build \
    --no-cache \
    -t "${IMAGE}:${TAG}" \
    .
fi

echo ""
echo -e "  ${GREEN}✓${RESET} Image built"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Push to GHCR
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}  3. Pushing to GHCR${RESET}"
docker push "${IMAGE}:${TAG}"
echo -e "  ${GREEN}✓${RESET} Pushed ${IMAGE}:${TAG}"

if [[ -n "${VERSION}" ]]; then
  docker push "${IMAGE}:${VERSION}"
  echo -e "  ${GREEN}✓${RESET} Pushed ${IMAGE}:${VERSION}"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Verify image is public
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}  4. Verifying package is publicly accessible${RESET}"
if docker manifest inspect "${IMAGE}:${TAG}" &>/dev/null; then
  echo -e "  ${GREEN}✓${RESET} Image is publicly accessible"
else
  echo -e "  ${YELLOW}⚠${RESET} Image may be private — make it public at:"
  echo -e "    ${DIM}https://github.com/users/variablenix/packages/container/cups-prometheus-exporter/settings${RESET}"
  echo -e "    ${DIM}Danger Zone → Change package visibility → Public${RESET}"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}  Summary${RESET}"
echo -e "${DIM}  ────────────────────────────────────────────${RESET}"
echo -e "  ${GREEN}✓${RESET} Image pushed: ${IMAGE}:${TAG}"
[[ -n "${VERSION}" ]] && echo -e "  ${GREEN}✓${RESET} Image pushed: ${IMAGE}:${VERSION}"
echo ""
echo -e "${DIM}  To update the running container on moonlab:${RESET}"
echo -e "${DIM}    bash deploy.sh cups${RESET}"
echo ""
