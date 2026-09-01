#!/usr/bin/env bash
set -e
apt-get update -qq && apt-get install -y -qq git curl jq rsync
if ! command -v node >/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi
npm install -g opencode-ai
echo "OK $(node --version) $(opencode --version)"
