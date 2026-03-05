#!/usr/bin/env bash
#
# deploy.sh — Build, push, and deploy the Clue app to Kubernetes.
#
# Usage:
#   ./scripts/deploy.sh                          # defaults: registry=ghcr.io/<git-owner>/clue, tag=<short sha>
#   ./scripts/deploy.sh -r ghcr.io/myorg/clue -t v1.2.3
#   ./scripts/deploy.sh -t latest
#
# Prerequisites:
#   - docker (logged in to your registry)
#   - kubectl (configured for the target cluster)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
# Try to detect the registry from the git remote
DEFAULT_OWNER=$(git -C "$ROOT_DIR" remote get-url origin 2>/dev/null \
  | sed -n 's#.*github\.com[:/]\([^/]*\)/.*#\1#p' \
  | tr '[:upper:]' '[:lower:]')
DEFAULT_REGISTRY="ghcr.io/${DEFAULT_OWNER:-clue}/clue"

REGISTRY="${REGISTRY:-$DEFAULT_REGISTRY}"
TAG="${TAG:-}"
TAG_SET=false
NAMESPACE="clue"
SKIP_BUILD=false
SSH_TARGET="${SSH_TARGET:-}"
WITH_CERT_MANAGER=false

# ── Parse flags ───────────────────────────────────────────────────────────────
usage() {
  echo "Usage: $0 [-r REGISTRY] [-t TAG] [-n NAMESPACE] [--skip-build] [--ssh user@host] [--cert-manager]"
  echo ""
  echo "  -r REGISTRY   Container registry prefix (default: $DEFAULT_REGISTRY)"
  echo "  -t TAG         Image tag (default: git short SHA)"
  echo "  -n NAMESPACE   Kubernetes namespace (default: clue)"
  echo "  --skip-build   Skip Docker build/push, only apply manifests"
  echo "  --ssh TARGET   Run kubectl on remote host over SSH (e.g. ubuntu@k8s-box)"
  echo "  --cert-manager Apply cert-manager ClusterIssuer before ingress"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -r) REGISTRY="$2"; shift 2 ;;
    -t) TAG="$2"; TAG_SET=true; shift 2 ;;
    -n) NAMESPACE="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --ssh) SSH_TARGET="$2"; shift 2 ;;
    --cert-manager) WITH_CERT_MANAGER=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# Default TAG to git short SHA for builds; require explicit -t with --skip-build
if [ -z "$TAG" ]; then
  if [ "$SKIP_BUILD" = true ]; then
    echo "Error: --skip-build requires an explicit tag (-t TAG)" >&2
    exit 1
  fi
  TAG="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
fi

BACKEND_IMAGE="$REGISTRY-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY-frontend:$TAG"

echo "==> Configuration"
echo "    Registry:  $REGISTRY"
echo "    Tag:       $TAG"
echo "    Namespace: $NAMESPACE"
echo "    Backend:   $BACKEND_IMAGE"
echo "    Frontend:  $FRONTEND_IMAGE"
echo "    SSH:       ${SSH_TARGET:-local kubectl context}"
echo "    CertMgr:   $WITH_CERT_MANAGER"
echo ""

kubectl_cmd() {
  if [ -n "$SSH_TARGET" ]; then
    local quoted_args=""
    local arg
    for arg in "$@"; do
      quoted_args+=" $(printf '%q' "$arg")"
    done
    ssh "$SSH_TARGET" "kubectl${quoted_args}"
  else
    kubectl "$@"
  fi
}

apply_manifest() {
  local namespace="$1"
  local manifest_path="$2"

  if [ -n "$SSH_TARGET" ]; then
    if [ -n "$namespace" ]; then
      kubectl_cmd apply -n "$namespace" -f - < "$manifest_path"
    else
      kubectl_cmd apply -f - < "$manifest_path"
    fi
  else
    if [ -n "$namespace" ]; then
      kubectl_cmd apply -n "$namespace" -f "$manifest_path"
    else
      kubectl_cmd apply -f "$manifest_path"
    fi
  fi
}

# ── Build & push ──────────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  echo "==> Logging in to ghcr.io..."
  echo "${GITHUB_TOKEN:-$(gh auth token)}" | docker login ghcr.io -u "${GITHUB_ACTOR:-$(gh api user -q .login)}" --password-stdin

  echo "==> Building backend image (linux/amd64)..."
  docker buildx build --platform linux/amd64 -t "$BACKEND_IMAGE" -f "$ROOT_DIR/backend/Dockerfile" --push "$ROOT_DIR"
else
  echo "==> Skipping build (--skip-build)"
fi

# ── Deploy to Kubernetes ──────────────────────────────────────────────────────
echo "==> Creating namespace '$NAMESPACE' (if needed)..."
apply_manifest "" "$ROOT_DIR/k8s/namespace.yaml"

echo "==> Deploying Redis..."
apply_manifest "$NAMESPACE" "$ROOT_DIR/k8s/redis.yaml"

echo "==> Deploying backend..."
# Substitute the correct image before applying so the manifest always
# carries the pinned SHA tag and doesn't trigger a spurious rollout.
sed "s|image: clue-backend:.*|image: $BACKEND_IMAGE|" "$ROOT_DIR/k8s/backend.yaml" \
  | kubectl_cmd apply -n "$NAMESPACE" -f -

echo "==> Deploying agent-runner..."
# Agent runner uses the backend image with a different entrypoint.
sed "s|image: clue-backend:.*|image: $BACKEND_IMAGE|" "$ROOT_DIR/k8s/agent-runner.yaml" \
  | kubectl_cmd apply -n "$NAMESPACE" -f -

if [ "$WITH_CERT_MANAGER" = true ]; then
  echo "==> Applying cert-manager ClusterIssuer..."
  apply_manifest "" "$ROOT_DIR/k8s/clusterissuer.yaml"
fi

echo "==> Applying ingress..."
apply_manifest "$NAMESPACE" "$ROOT_DIR/k8s/ingress.yaml"

echo "==> Waiting for rollouts..."
kubectl_cmd rollout status -n "$NAMESPACE" deployment/redis --timeout=120s
kubectl_cmd rollout status -n "$NAMESPACE" deployment/backend --timeout=120s
kubectl_cmd rollout status -n "$NAMESPACE" deployment/agent-runner --timeout=120s

echo ""
echo "==> Deployment complete!"
kubectl_cmd get pods -n "$NAMESPACE"
