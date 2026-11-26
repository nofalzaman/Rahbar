param([Parameter(Mandatory=$true)][string]$Name,[string]$Collection='rahbar-a3-candidate',
 [string]$BatchDir='corpus/batch_b',[string]$BaseCorpus='/data/corpus/active',
 [string]$Destination='/data/corpus/with-b',[switch]$PrepareOnly)
$ErrorActionPreference='Stop'
if (-not (Test-Path "$BatchDir/_index.json")) { throw 'The incoming batch needs an _index.json manifest with actual document metadata.' }
$dataPod=kubectl get pods -n rahbar -l app=data-shell -o jsonpath='{.items[0].metadata.name}'
$incoming="/data/incoming/$Name"
kubectl exec -n rahbar $dataPod -- mkdir -p $incoming
kubectl cp "$BatchDir/." "rahbar/${dataPod}:$incoming"
if($LASTEXITCODE -ne 0) { throw 'Batch B copy failed' }
$combine=@'
import json,shutil,sys
from pathlib import Path
root=Path(sys.argv[3]);root.mkdir(parents=True,exist_ok=True)
entries={}
for folder in (Path(sys.argv[1]),Path(sys.argv[2])):
 for entry in json.loads((folder/'_index.json').read_text()): entries[entry['file']]=entry
 for p in folder.iterdir():
  if p.is_file() and p.name!='_index.json' and p.resolve()!=(root/p.name).resolve(): shutil.copy2(p,root/p.name)
(root/'_index.json').write_text(json.dumps(list(entries.values())))
print(json.dumps({'prepared_documents':len(entries),'destination':str(root)}))
'@
kubectl exec -n rahbar $dataPod -- python -c $combine $BaseCorpus $incoming $Destination
if($LASTEXITCODE -ne 0) { throw 'Manifest composition failed' }
if($PrepareOnly) { return }
& "$PSScriptRoot/run_ragops.ps1" -Kind ingest -Name $Name -Collection $Collection -Corpus $Destination
kubectl wait --for=condition=complete "job/$Name" -n rahbar --timeout=600s
if($LASTEXITCODE -ne 0) { kubectl logs -n rahbar "job/$Name"; throw 'Drift ingestion failed' }
kubectl logs -n rahbar "job/$Name" | Tee-Object "docs/evidence/ragops/$Name.txt"
Write-Output 'Now rerun the evaluation suite against the same API/top-k/model as the saved pre-B candidate. Repeated ingestion is expected to embed zero chunks.'
