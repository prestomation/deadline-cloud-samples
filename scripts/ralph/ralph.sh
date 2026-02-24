#!/bin/bash
# Ralph - Autonomous AI agent loop using kiro-cli
# Based on: https://github.com/snarktank/ralph
#
# IMPORTANT: Run this script from the PROJECT ROOT, not from scripts/ralph/
# Usage: ./scripts/ralph/ralph.sh [--trust-all-tools] [max_iterations]
# Default: 25 iterations

set -e

# Parse arguments
TRUST_ALL_TOOLS=""
MAX_ITERATIONS=25

while [[ $# -gt 0 ]]; do
  case $1 in
    --trust-all-tools)
      TRUST_ALL_TOOLS="--trust-all-tools"
      shift
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      fi
      shift
      ;;
  esac
done

# SCRIPT_DIR is where ralph files live (prd.json, progress.txt, prompt.md)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PROJECT_ROOT is where kiro-cli should run from (to access AGENTS.md, source code, etc.)
# Use git root if available, otherwise use parent of scripts/ralph (assumes scripts/ralph/ structure)
if git rev-parse --show-toplevel &>/dev/null; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel)"
else
  # Assume script is in scripts/ralph/, so go up two levels
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

# Prerequisite checks
if ! command -v kiro-cli &>/dev/null; then
  echo "Error: kiro-cli not found. Install it first." >&2
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "Error: jq not found. Install with: brew install jq" >&2
  exit 1
fi

if [ ! -f "$PRD_FILE" ]; then
  echo "Error: PRD file not found: $PRD_FILE" >&2
  echo "Create prd.json with your task list. See ralph-loop skill for format." >&2
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/prompt.md" ]; then
  echo "Error: prompt.md not found in $SCRIPT_DIR" >&2
  exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Archive previous run if branch changed
if [ -f "$PRD_FILE" ] && [ -f "$LAST_BRANCH_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  LAST_BRANCH=$(cat "$LAST_BRANCH_FILE" 2>/dev/null || echo "")

  if [ -n "$CURRENT_BRANCH" ] && [ -n "$LAST_BRANCH" ] && [ "$CURRENT_BRANCH" != "$LAST_BRANCH" ]; then
    DATE=$(date +%Y-%m-%d)
    FOLDER_NAME=$(echo "$LAST_BRANCH" | sed 's|^ralph/||')
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"

    echo -e "${YELLOW}Archiving previous run: $LAST_BRANCH${NC}"
    mkdir -p "$ARCHIVE_FOLDER"
    [ -f "$PRD_FILE" ] && cp "$PRD_FILE" "$ARCHIVE_FOLDER/"
    [ -f "$PROGRESS_FILE" ] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    echo "   Archived to: $ARCHIVE_FOLDER"

    # Reset progress file
    echo "# Ralph Progress Log" > "$PROGRESS_FILE"
    echo "Started: $(date)" >> "$PROGRESS_FILE"
    echo "---" >> "$PROGRESS_FILE"
  fi
fi

# Track current branch
if [ -f "$PRD_FILE" ]; then
  CURRENT_BRANCH=$(jq -r '.branchName // empty' "$PRD_FILE" 2>/dev/null || echo "")
  if [ -n "$CURRENT_BRANCH" ]; then
    echo "$CURRENT_BRANCH" > "$LAST_BRANCH_FILE"
  fi
fi

# Initialize progress file if needed
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Progress Log" > "$PROGRESS_FILE"
  echo "Started: $(date)" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

echo -e "${BLUE}Starting Ralph - Max iterations: $MAX_ITERATIONS${NC}"
echo -e "${BLUE}  Project root: $PROJECT_ROOT${NC}"
echo -e "${BLUE}  Ralph files:  $SCRIPT_DIR${NC}"
if [ -n "$TRUST_ALL_TOOLS" ]; then
  echo -e "${YELLOW}Running with --trust-all-tools (fully autonomous)${NC}"
fi
echo ""

# Create a fake 'less' so Makeself .run installers don't hijack the terminal
FAKELESS_DIR=$(mktemp -d)
printf '#!/bin/sh\ncat > /dev/null\n' > "$FAKELESS_DIR/less"
chmod +x "$FAKELESS_DIR/less"
export PATH="$FAKELESS_DIR:$PATH"

# Change to project root so agent can access AGENTS.md, README.md, source code
cd "$PROJECT_ROOT"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}  Ralph Iteration $i of $MAX_ITERATIONS${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
  echo ""

  # Run kiro-cli from PROJECT_ROOT with instructions from SCRIPT_DIR
  OUTPUT=$(cat "$SCRIPT_DIR/prompt.md" | kiro-cli chat --no-interactive $TRUST_ALL_TOOLS 2>&1 | tee /dev/stderr) || true

  # Check for completion signal
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Ralph completed all tasks!${NC}"
    echo -e "${GREEN}  Completed at iteration $i of $MAX_ITERATIONS${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
    exit 0
  fi

  echo ""
  echo "Iteration $i complete. Continuing in 2 seconds..."
  sleep 2
done

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Ralph reached max iterations ($MAX_ITERATIONS) without completing.${NC}"
echo -e "${YELLOW}  Check progress.txt for status.${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════════${NC}"
exit 1
