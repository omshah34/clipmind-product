#!/usr/bin/env bash
if ! grep -q "sha256:" requirements.txt; then
  echo "❌ requirements.txt is missing hash pins. Run: pip-compile --generate-hashes"
  exit 1
fi
echo "✅ Hash pins verified"
