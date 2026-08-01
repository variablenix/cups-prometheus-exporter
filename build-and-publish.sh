#!/usr/bin/env bash
# Build and publish the exporter image to GitHub Container Registry.
#
# Usage:
#   ./build-and-publish.sh          # publish latest
#   ./build-and-publish.sh 1.0.0    # publish latest and 1.0.0
#
# Environment overrides:
#   GHCR_USER=variablenix
#   GHCR_IMAGE=ghcr.io/variablenix/cups-prometheus-exporter
#   DOCKER_PLATFORM=linux/amd64,linux/arm64

set -euo pipefail

readonly GHCR_USER="${GHCR_USER:-${GITHUB_ACTOR:-variablenix}}"
readonly IMAGE="${GHCR_IMAGE:-ghcr.io/${GHCR_USER}/cups-prometheus-exporter}"
readonly LATEST_TAG="${IMAGE}:latest"
readonly VERSION_INPUT="${1:-}"
readonly VERSION="${VERSION_INPUT#v}"

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [version]" >&2
  exit 2
fi

if [[ -n "${VERSION}" && ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "Version must be a semantic version such as 1.0.0 or 1.0.0-rc.1" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
if ! docker buildx version >/dev/null 2>&1; then
  echo "docker buildx is required" >&2
  exit 1
fi

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  printf '%s\n' "${GITHUB_TOKEN}" | docker login ghcr.io --username "${GHCR_USER}" --password-stdin
elif command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh auth token | docker login ghcr.io --username "${GHCR_USER}" --password-stdin
else
  echo "GHCR authentication is required. Set GITHUB_TOKEN or run 'gh auth login'." >&2
  exit 1
fi

tags=(--tag "${LATEST_TAG}")
if [[ -n "${VERSION}" ]]; then
  tags+=(--tag "${IMAGE}:${VERSION}")
fi

labels=(
  --label "org.opencontainers.image.source=https://github.com/variablenix/cups-prometheus-exporter"
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
)

platform_args=()
if [[ -n "${DOCKER_PLATFORM:-}" ]]; then
  platform_args+=(--platform "${DOCKER_PLATFORM}")
fi

docker buildx build \
  --pull \
  "${platform_args[@]}" \
  "${tags[@]}" \
  "${labels[@]}" \
  --provenance=true \
  --sbom=true \
  --push \
  .

echo "Published ${LATEST_TAG}"
if [[ -n "${VERSION}" ]]; then
  echo "Published ${IMAGE}:${VERSION}"
fi
