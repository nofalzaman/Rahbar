param([string]$Raw='corpus/raw',[string]$Prepared='../rahbar-corpus-a')
$ErrorActionPreference='Stop'
function Check-Step { if ($LASTEXITCODE -ne 0) { throw 'Previous command failed; stop before continuing.' } }
minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
Check-Step
minikube addons enable ingress
minikube addons enable metrics-server
foreach ($part in @('namespace','serviceaccounts','configmap','chroma-statefulset','redis','services','networkpolicy','api','ui','ingress')) {
 kubectl apply -f "k8s/base/$part.yaml"
 Check-Step
}
python -m scripts.prepare_ragops --raw $Raw --output $Prepared
Check-Step
docker build -t rahbar-api:a3-r4 api
Check-Step
docker build -t rahbar-indexer:a3-r4 --build-context "corpus=$Raw" indexer
Check-Step
docker build -t rahbar-eval:a3-r2 -f eval/Dockerfile .
Check-Step
docker build -t rahbar-ui:a3 ui
Check-Step
minikube image load rahbar-api:a3-r4 rahbar-indexer:a3-r4 rahbar-eval:a3-r2 rahbar-ui:a3
Check-Step
kubectl apply -f k8s/ragops.yaml
Check-Step
$models=Invoke-RestMethod http://localhost:11434/api/tags
$embedding=($models.models | Where-Object name -eq 'nomic-embed-text:latest').digest
$generator=($models.models | Where-Object name -eq 'llama3.2:3b').digest
if (-not $embedding -or -not $generator) { throw 'Pull both required Ollama models before bootstrapping.' }
kubectl set env deployment/api deployment/api-candidate "EMBED_VERSION=$embedding" "LLM_VERSION=$generator" -n rahbar
Check-Step
kubectl set image deployment/ui ui=rahbar-ui:a3 -n rahbar
kubectl rollout status deployment/data-shell -n rahbar --timeout=180s
Check-Step
$dataPod=kubectl get pods -n rahbar -l app=data-shell -o jsonpath='{.items[0].metadata.name}'
kubectl exec -n rahbar $dataPod -- mkdir -p /data/corpus /data/results /data/traces
kubectl cp $Prepared "rahbar/${dataPod}:/data/corpus/active"
Check-Step
kubectl cp corpus/batch_b "rahbar/${dataPod}:/data/batch_b"
kubectl cp corpus/batch_a_demo "rahbar/${dataPod}:/data/batch_a_demo"
kubectl rollout status statefulset/chroma -n rahbar --timeout=180s
Check-Step
kubectl rollout status deployment/redis -n rahbar --timeout=180s
Check-Step
kubectl apply -f k8s/ingest-job.yaml
Check-Step
kubectl wait --for=condition=complete job/ragops-ingest -n rahbar --timeout=900s
Check-Step
kubectl rollout status deployment/api -n rahbar --timeout=180s
Check-Step
# Reuse accepted vectors for the candidate, but let only the ingestion Job write Chroma.
kubectl exec -n rahbar $dataPod -- cp /data/lake/state/rahbar-a3-baseline.json /data/lake/state/rahbar-a3-candidate.json
& "$PSScriptRoot/run_ragops.ps1" -Kind ingest -Name ragops-candidate-index -Collection rahbar-a3-candidate
kubectl wait --for=condition=complete job/ragops-candidate-index -n rahbar --timeout=900s
Check-Step
kubectl rollout status deployment/api-candidate -n rahbar --timeout=180s
kubectl apply -f k8s/ragops-cronjob.yaml
Write-Output 'Ready. Apply k8s/eval-job.yaml to run Part B. Use a fresh Job name for repeats.'
