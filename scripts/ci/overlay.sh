#!/usr/bin/env bash
# Writes k8s/overlays/ci: the base manifests with the stub LLM, the runner's Ollama as
# the embedding host, and the images to run. It is generated on every run and never
# committed, so the committed overlays stay exactly what a person would deploy.
#
# Needs Ollama on the existing `kind` Docker network, unless OLLAMA_HOST_IP is set.
set -euo pipefail

: "${API_IMAGE:?set API_IMAGE}"
: "${UI_IMAGE:?set UI_IMAGE}"
: "${INDEXER_IMAGE:?set INDEXER_IMAGE}"
: "${IMAGE_TAG:?set IMAGE_TAG}"
: "${EMBED_MODEL:?set EMBED_MODEL}"
: "${RELEVANCE_FLOOR:?set RELEVANCE_FLOOR}"

if [ -z "${OLLAMA_HOST_IP:-}" ]; then
  OLLAMA_HOST_IP="$(docker inspect ollama \
    -f '{{with index .NetworkSettings.Networks "kind"}}{{.IPAddress}}{{end}}')"
fi
: "${OLLAMA_HOST_IP:?Ollama must be attached to the kind network}"

dir="${OVERLAY_DIR:-k8s/overlays/ci}"
mkdir -p "$dir"

cat > "$dir/config-patch.yaml" <<PATCH
apiVersion: v1
kind: ConfigMap
metadata:
  name: rahbar-config
  namespace: rahbar
data:
  LLM_PROVIDER: "stub"
  EMBED_MODEL: "${EMBED_MODEL}"
  OLLAMA_URL: "http://${OLLAMA_HOST_IP}:11434"
  RELEVANCE_FLOOR: "${RELEVANCE_FLOOR}"
PATCH

cat > "$dir/kustomization.yaml" <<KUSTOMIZATION
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
  - ollama-networkpolicy.yaml
patches:
  - path: config-patch.yaml
images:
  - name: rahbar-api
    newName: ${API_IMAGE}
    newTag: ${IMAGE_TAG}
  - name: rahbar-ui
    newName: ${UI_IMAGE}
    newTag: ${IMAGE_TAG}
  - name: rahbar-indexer
    newName: ${INDEXER_IMAGE}
    newTag: ${IMAGE_TAG}
KUSTOMIZATION

# Recent kindnet versions enforce NetworkPolicy. The base allowlist names the
# laptop's Ollama IP, so CI must allow the actual runner-side container address.
cat > "$dir/ollama-networkpolicy.yaml" <<POLICY
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ci-ollama-egress
  namespace: rahbar
spec:
  podSelector:
    matchExpressions:
      - key: app
        operator: In
        values: [api, indexer]
  policyTypes: [Egress]
  egress:
    - to:
        - ipBlock:
            cidr: ${OLLAMA_HOST_IP}/32
      ports:
        - protocol: TCP
          port: 11434
POLICY

echo "overlay written to $dir (Ollama at ${OLLAMA_HOST_IP}:11434, floor ${RELEVANCE_FLOOR})"
