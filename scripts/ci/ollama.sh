#!/usr/bin/env bash
# Starts Ollama in a container on the CI runner and pulls the embedding model, so the
# indexer and the api embed with the same pinned model as on a laptop (section 4.4).
set -euo pipefail

: "${OLLAMA_IMAGE:?set OLLAMA_IMAGE}"
: "${EMBED_MODEL:?set EMBED_MODEL}"

mkdir -p "$HOME/.ollama"
docker run -d --name ollama -p 11434:11434 -v "$HOME/.ollama:/root/.ollama" "$OLLAMA_IMAGE"

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null

docker exec ollama ollama pull "$EMBED_MODEL"
