#!/usr/bin/env bash
set -euo pipefail

if ! /usr/bin/curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/health/ready >/dev/null; then
  /usr/bin/systemctl restart medagent-backend.service
  exit 1
fi
