#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f state/semantic_cache.pid ]]; then
  kill "$(cat state/semantic_cache.pid)" || true
  rm -f state/semantic_cache.pid
fi
if [[ -f state/litellm.pid ]]; then
  kill "$(cat state/litellm.pid)" 2>/dev/null || true
  rm -f state/litellm.pid
fi
if [[ -f state/redis.pid ]]; then
  kill "$(cat state/redis.pid)" 2>/dev/null || true
  rm -f state/redis.pid
fi
if [[ -f docker-compose.runtime.yml ]]; then
  sg docker -c 'docker compose -f docker-compose.runtime.yml down' || true
fi
