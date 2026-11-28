param([ValidateSet('ingest','eval')][string]$Kind,[Parameter(Mandatory=$true)][string]$Name,[string]$Collection='rahbar-a3-baseline',[string]$Corpus='/data/corpus/active',[string]$Api='http://api:8000',[string]$Label='baseline',[string]$Baseline='', [switch]$SkipNoise)
$ErrorActionPreference='Stop'
if ($Kind -eq 'ingest') {
 $writers = kubectl get jobs -n rahbar -o json | ConvertFrom-Json
 if (@($writers.items | Where-Object { $_.status.active -gt 0 -and $_.spec.template.metadata.labels.app -eq 'ragops-ingest' }).Count -gt 0) { throw 'Wait for the active ingestion Job to finish before creating another writer.' }
}
if ($Kind -eq 'ingest') { $template='k8s/ingest-job.yaml' } else { $template='k8s/eval-job.yaml' }
$job = kubectl create --dry-run=client -f $template -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Unable to load Job template' }
$job.metadata.name=$Name
$container=$job.spec.template.spec.containers[0]
if ($Kind -eq 'ingest') {
 foreach ($entry in $container.env) {
  if ($entry.name -eq 'CHROMA_COLLECTION') { $entry.value=$Collection }
  if ($entry.name -eq 'CORPUS_DIR') { $entry.value=$Corpus }
 }
} else {
 $container.args=@('--api',$Api,'--output','/data/results','--label',$Label,'--gate','/thresholds/thresholds.json')
 if ($Baseline) { $container.args+=@('--baseline',$Baseline) }
 if ($SkipNoise) { $container.args+='--skip-noise' }
}
$job | ConvertTo-Json -Depth 50 | kubectl apply -f -
if ($LASTEXITCODE -ne 0) { throw 'Job creation failed' }
Write-Output "Created $Kind Job $Name. Follow with: kubectl logs -n rahbar -f job/$Name"

