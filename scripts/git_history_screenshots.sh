#!/usr/bin/env bash
#
# git_history_screenshots.sh
#
# Walks through git history, checking out every Nth commit,
# rebuilding docker containers, creating a Clue game + a Hold'em game,
# and taking screenshots of each. Screenshots go into screenshots/history/.
#
# Usage:
#   ./scripts/git_history_screenshots.sh [--step N] [--start COMMIT] [--games clue,holdem]
#
# Options:
#   --step N         Check out every Nth commit (default: 20)
#   --start COMMIT   Start from this commit (default: first commit)
#   --games LIST     Comma-separated game types to screenshot (default: clue,holdem)
#   --timeout SECS   Max seconds to wait for containers (default: 120)
#   --dry-run        Just list commits, don't run anything
#
# Requirements: docker, node/npx, playwright browsers installed

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

STEP=20
START_COMMIT=""
GAMES="clue,holdem"
THEMES=""
TIMEOUT=120
DRY_RUN=false
SCREENSHOT_DIR="$REPO_ROOT/screenshots/history"

while [[ $# -gt 0 ]]; do
    case $1 in
        --step) STEP="$2"; shift 2 ;;
        --start) START_COMMIT="$2"; shift 2 ;;
        --games) GAMES="$2"; shift 2 ;;
        --themes) THEMES="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Get list of commits (oldest first)
if [[ -n "$START_COMMIT" ]]; then
    ALL_COMMITS=($(git log --reverse --format="%h" "$START_COMMIT"..HEAD))
    # Prepend the start commit itself
    ALL_COMMITS=("$START_COMMIT" "${ALL_COMMITS[@]}")
else
    ALL_COMMITS=($(git log --reverse --format="%h"))
fi

TOTAL=${#ALL_COMMITS[@]}
echo "Total commits: $TOTAL, stepping by $STEP"

# Select every Nth commit + always include the last
SELECTED=()
for ((i = 0; i < TOTAL; i += STEP)); do
    SELECTED+=("${ALL_COMMITS[$i]}")
done
# Always include the latest commit
LAST="${ALL_COMMITS[$((TOTAL - 1))]}"
NUM_SELECTED=${#SELECTED[@]}
if [[ "${SELECTED[$((NUM_SELECTED - 1))]}" != "$LAST" ]]; then
    SELECTED+=("$LAST")
fi

echo "Selected ${#SELECTED[@]} commits to screenshot"
echo ""

# Save current branch to restore later
ORIGINAL_REF=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse HEAD)

mkdir -p "$SCREENSHOT_DIR"

# List mode
if $DRY_RUN; then
    for ((idx = 0; idx < ${#SELECTED[@]}; idx++)); do
        COMMIT="${SELECTED[$idx]}"
        DATE=$(git log -1 --format="%ai" "$COMMIT" | cut -d' ' -f1)
        SUBJECT=$(git log -1 --format="%s" "$COMMIT")
        SEQ=$(printf "%03d" $idx)
        echo "$SEQ  $COMMIT  $DATE  $SUBJECT"
    done
    exit 0
fi

# Copy worker script and install playwright in /tmp so it survives git checkout
WORKER_DIR="/tmp/git_history_screenshots_$$"
mkdir -p "$WORKER_DIR"
cp "$SCRIPT_DIR/git_history_screenshot_worker.js" "$WORKER_DIR/worker.js"
WORKER_SCRIPT="$WORKER_DIR/worker.js"

# Install playwright in the temp dir
echo "Installing playwright in $WORKER_DIR..."
(cd "$WORKER_DIR" && npm init -y --silent && npm install --silent playwright 2>&1 | tail -1)
echo ""

cleanup() {
    echo ""
    echo "Cleaning up..."
    docker compose down --remove-orphans 2>/dev/null || true
    git checkout "$ORIGINAL_REF" 2>/dev/null || true
    rm -rf "$WORKER_DIR"
    echo "Restored to $ORIGINAL_REF"
}
trap cleanup EXIT

wait_for_backend() {
    local elapsed=0
    while [[ $elapsed -lt $TIMEOUT ]]; do
        # Accept any HTTP response (even 404) — it means the server is up
        if curl -so /dev/null -w '%{http_code}' http://localhost:8000/ 2>/dev/null | grep -qE '^[2-5]'; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

wait_for_frontend() {
    local elapsed=0
    while [[ $elapsed -lt $TIMEOUT ]]; do
        if curl -so /dev/null -w '%{http_code}' http://localhost:5173/ 2>/dev/null | grep -qE '^[2-5]'; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

take_screenshot_for_commit() {
    local COMMIT="$1"
    local SEQ="$2"
    local DATE="$3"
    local LABEL="${SEQ}_${DATE}_${COMMIT}"

    echo "--- [$SEQ] Commit $COMMIT ($DATE) ---"

    # Check out the commit (force to handle file changes)
    git checkout --force "$COMMIT" --quiet 2>/dev/null || true

    # Check if docker-compose.yml exists at this commit
    if [[ ! -f "docker-compose.yml" ]] && [[ ! -f "docker-compose.yaml" ]]; then
        echo "  SKIP: no docker-compose.yml at this commit"
        return 0
    fi

    # Stop previous containers
    docker compose down --remove-orphans 2>/dev/null || true

    # Rebuild and start (suppress most output)
    echo "  Building and starting containers..."
    if ! docker compose build --quiet 2>/dev/null; then
        echo "  SKIP: docker compose build failed"
        return 0
    fi

    if ! docker compose up -d 2>/dev/null; then
        echo "  SKIP: docker compose up failed"
        return 0
    fi

    # Early commits used volume-mounted frontend without npm install
    # Run npm install inside the frontend container if it exists
    docker compose exec -T frontend npm install 2>/dev/null || true

    # Wait for services
    echo "  Waiting for backend..."
    if ! wait_for_backend; then
        echo "  SKIP: backend didn't start within ${TIMEOUT}s"
        docker compose logs backend 2>/dev/null | tail -5
        return 0
    fi

    echo "  Waiting for frontend..."
    if ! wait_for_frontend; then
        echo "  SKIP: frontend didn't start within ${TIMEOUT}s"
        return 0
    fi

    # Extra settle time for frontend to fully load
    sleep 3

    # Run the screenshot node script (from /tmp copy)
    echo "  Taking screenshots..."
    node "$WORKER_SCRIPT" \
        "$LABEL" "$SCREENSHOT_DIR" "$GAMES" "$THEMES" \
        2>&1 | sed 's/^/  /' || echo "  WARNING: screenshot script had errors"

    echo "  Done with $LABEL"
    echo ""
}

# Main loop
for ((idx = 0; idx < ${#SELECTED[@]}; idx++)); do
    COMMIT="${SELECTED[$idx]}"
    DATE=$(git log -1 --format="%ai" "$COMMIT" | cut -d' ' -f1)
    SEQ=$(printf "%03d" $idx)
    take_screenshot_for_commit "$COMMIT" "$SEQ" "$DATE"
done

echo ""
echo "All screenshots saved to $SCREENSHOT_DIR"
echo "Total: $(ls -1 "$SCREENSHOT_DIR"/*.png 2>/dev/null | wc -l) images"
