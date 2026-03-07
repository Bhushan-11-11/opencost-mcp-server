#!/usr/bin/env bash
set -euo pipefail

violations=$(git ls-files | grep -E '(^|/)\.env($|\.)' | grep -vE '\.env\.example$|\.env-example$' || true)
if [[ -n "${violations}" ]]; then
  echo "Refusing commit: tracked .env-style files detected"
  echo "${violations}"
  exit 1
fi

echo "No tracked .env secret files detected."
