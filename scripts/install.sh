#!/usr/bin/env bash
# Install runtime dependencies inside a Kaggle kernel (or similar Linux env).
set -euo pipefail

apt-get update -qq
apt-get install -y -qq git curl jq rsync ca-certificates

if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if ! command -v opencode >/dev/null 2>&1; then
  npm install -g opencode-ai
fi

python -m pip install -q --upgrade pip
python -m pip install -q kagglehub

echo "OK node=$(node --version) opencode=$(opencode --version 2>/dev/null || echo pending)"
