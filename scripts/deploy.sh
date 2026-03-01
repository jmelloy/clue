#!/usr/bin/env bash
#
# deploy.sh — Build, push, and deploy the Clue app to Kubernetes.
#
# Usage:
#   ./scripts/deploy.sh                          # defaults: registry=ghcr.io/<git-owner>/clue, tag=latest
#   ./scripts/deploy.sh -r ghcr.io/myorg/clue -t v1.2.3
#   ./scripts/deploy.sh -t $(git rev-parse --short HEAD)
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
TAG="${TAG:-latest}"
NAMESPACE="clue"
SKIP_BUILD=false

# ── Parse flags ───────────────────────────────────────────────────────────────
usage() {
  echo "Usage: $0 [-r REGISTRY] [-t TAG] [-n NAMESPACE] [--skip-build]"
  echo ""
  echo "  -r REGISTRY   Container registry prefix (default: $DEFAULT_REGISTRY)"
  echo "  -t TAG         Image tag (default: latest)"
  echo "  -n NAMESPACE   Kubernetes namespace (default: clue)"
  echo "  --skip-build   Skip Docker build/push, only apply manifests"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -r) REGISTRY="$2"; shift 2 ;;
    -t) TAG="$2"; shift 2 ;;
    -n) NAMESPACE="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

BACKEND_IMAGE="$REGISTRY-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY-frontend:$TAG"

echo "==> Configuration"
echo "    Registry:  $REGISTRY"
echo "    Tag:       $TAG"
echo "    Namespace: $NAMESPACE"
echo "    Backend:   $BACKEND_IMAGE"
echo "    Frontend:  $FRONTEND_IMAGE"
echo ""

# ── Build & push ──────────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  echo "==> Building backend image..."
  docker build -t "$BACKEND_IMAGE" "$ROOT_DIR/backend"

  echo "==> Building frontend image..."
  docker build -t "$FRONTEND_IMAGE" "$ROOT_DIR/frontend"

  echo "==> Pushing images..."
  docker push "$BACKEND_IMAGE"
  docker push "$FRONTEND_IMAGE"
else
  echo "==> Skipping build (--skip-build)"
fi

# ── Deploy to Kubernetes ──────────────────────────────────────────────────────
echo "==> Creating namespace '$NAMESPACE' (if needed)..."
kubectl apply -f "$ROOT_DIR/k8s/namespace.yaml"

echo "==> Deploying Redis..."
kubectl apply -n "$NAMESPACE" -f "$ROOT_DIR/k8s/redis.yaml"

echo "==> Deploying backend..."
kubectl apply -n "$NAMESPACE" -f "$ROOT_DIR/k8s/backend.yaml"
kubectl set image -n "$NAMESPACE" deployment/backend backend="$BACKEND_IMAGE"

echo "==> Deploying frontend..."
kubectl apply -n "$NAMESPACE" -f "$ROOT_DIR/k8s/frontend.yaml"
kubectl set image -n "$NAMESPACE" deployment/frontend frontend="$FRONTEND_IMAGE"

echo "==> Applying ingress..."
kubectl apply -n "$NAMESPACE" -f "$ROOT_DIR/k8s/ingress.yaml"

echo "==> Waiting for rollouts..."
kubectl rollout status -n "$NAMESPACE" deployment/redis --timeout=120s
kubectl rollout status -n "$NAMESPACE" deployment/backend --timeout=120s
kubectl rollout status -n "$NAMESPACE" deployment/frontend --timeout=120s

echo ""
echo "==> Deployment complete!"
kubectl get pods -n "$NAMESPACE"
