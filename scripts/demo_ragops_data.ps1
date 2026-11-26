param([ValidatePattern('^[a-z0-9][a-z0-9-]{0,25}$')][string]$Prefix=('demo-'+(Get-Date -Format 'yyyyMMddHHmmss')))
$ErrorActionPreference='Stop'
if ((kubectl config current-context) -ne 'minikube') { throw 'Select the minikube context before running this demo.' }
$dataPod=kubectl get pods -n rahbar -l app=data-shell -o jsonpath='{.items[0].metadata.name}'
$root="/data/$Prefix"
$collection="rahbar-$Prefix"
kubectl exec -n rahbar $dataPod -- mkdir -p $root
kubectl cp corpus/batch_a_demo "rahbar/${dataPod}:$root/a"
if ($LASTEXITCODE -ne 0) { throw 'Batch A copy failed' }
kubectl cp corpus/batch_b "rahbar/${dataPod}:$root/b"
if ($LASTEXITCODE -ne 0) { throw 'Batch B copy failed' }
function Run-Ingestion([string]$Step,[string]$Corpus) {
 $name="$Prefix-$Step"
 & "$PSScriptRoot/run_ragops.ps1" -Kind ingest -Name $name -Collection $collection -Corpus $Corpus
 kubectl wait --for=condition=complete "job/$name" -n rahbar --timeout=300s
 if ($LASTEXITCODE -ne 0) { kubectl logs -n rahbar "job/$name"; throw "Job $name failed" }
 kubectl logs -n rahbar "job/$name" | Tee-Object "docs/evidence/ragops/$name.txt"
}
Run-Ingestion 'a' "$root/a"
$combine=@'
import json,shutil,sys
from pathlib import Path
root=Path(sys.argv[1]); combined=root/'combined'; combined.mkdir(exist_ok=True)
entries=[]
for folder in (root/'a',root/'b'):
 entries+=json.loads((folder/'_index.json').read_text())
 for p in folder.glob('*.md'): shutil.copy2(p,combined/p.name)
(combined/'_index.json').write_text(json.dumps(entries))
'@
kubectl exec -n rahbar $dataPod -- python -c $combine $root
Run-Ingestion 'b' "$root/combined"
Run-Ingestion 'unchanged' "$root/combined"
$change=@'
import sys
from pathlib import Path
p=Path(sys.argv[1])/'combined/library-new.md'
p.write_text(p.read_text()+'\nThe synthetic library also offers a reading room.\n')
'@
kubectl exec -n rahbar $dataPod -- python -c $change $root
Run-Ingestion 'changed' "$root/combined"
$delete=@'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])/'combined/_index.json'
p.write_text(json.dumps([e for e in json.loads(p.read_text()) if e['file']!='lab.md']))
'@
kubectl exec -n rahbar $dataPod -- python -c $delete $root
Run-Ingestion 'deleted' "$root/combined"
$digest=(Get-FileHash corpus/batch_a_demo/library-old.md -Algorithm SHA256).Hash.ToLowerInvariant()
$job=kubectl create --dry-run=client -f k8s/ingest-job.yaml -o json | ConvertFrom-Json
$job.metadata.name="$Prefix-restore"
$container=$job.spec.template.spec.containers[0]
foreach($entry in $container.env) {
 if($entry.name -eq 'CHROMA_COLLECTION') { $entry.value=$collection }
 if($entry.name -eq 'CORPUS_DIR') { $entry.value="$root/combined" }
}
$container | Add-Member -NotePropertyName args -NotePropertyValue @('--restore','library-old.md',$digest) -Force
$job | ConvertTo-Json -Depth 50 | kubectl apply -f -
kubectl wait --for=condition=complete "job/$Prefix-restore" -n rahbar --timeout=60s
if ($LASTEXITCODE -ne 0) { throw 'Restore Job failed' }
kubectl logs -n rahbar "job/$Prefix-restore" | Tee-Object "docs/evidence/ragops/$Prefix-restore.txt"
Write-Output "Completed Part A in isolated collection $collection; live API collection was not changed."
