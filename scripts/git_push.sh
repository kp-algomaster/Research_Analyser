#!/usr/bin/env zsh
# Push to GitHub using the PAT from .env
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Error: .env file not found"
  exit 1
fi

TOKEN=$(grep '^GITHUB_PAT=' .env | cut -d'=' -f2-)

if [[ -z "$TOKEN" ]]; then
  echo "Error: GITHUB_PAT not set in .env"
  exit 1
fi

REPO_URL="https://x-access-token:${TOKEN}@github.com/kp-algomaster/Research_Analyser.git"

git push "$REPO_URL" "${1:-main}"
