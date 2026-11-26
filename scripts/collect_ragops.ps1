param([string]$Destination='eval/results')
$ErrorActionPreference='Stop'
$dataPod=kubectl get pods -n rahbar -l app=data-shell -o jsonpath='{.items[0].metadata.name}'
New-Item $Destination -ItemType Directory -Force | Out-Null
New-Item "$Destination/verification" -ItemType Directory -Force | Out-Null
New-Item traces -ItemType Directory -Force | Out-Null
kubectl cp "rahbar/${dataPod}:/data/results/." $Destination
kubectl cp "rahbar/${dataPod}:/data/lake/reports/." "$Destination/verification"
$readLogs=@'
from pathlib import Path
import sys
for p in sorted(Path('/data/traces').glob('*.jsonl')):
 sys.stdout.write(p.read_text())
'@
kubectl exec -n rahbar $dataPod -- python -c $readLogs | Set-Content traces/cluster.jsonl -Encoding UTF8
kubectl get all,pvc,configmap,cronjob,job -n rahbar | Tee-Object docs/evidence/ragops/cluster-final.txt
kubectl top pods -n rahbar | Tee-Object docs/evidence/ragops/resources-final.txt
