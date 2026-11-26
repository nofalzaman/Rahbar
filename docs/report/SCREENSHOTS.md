# Manual screenshot checklist

Take these yourselves in Windows Terminal/PowerShell on Nofal's laptop. Maximize the window. Show the command and its complete output; do not crop, edit, paste together or fabricate terminal output. If output needs several screens, capture labelled continuation images. Use a smaller readable font for a full trace. Screenshots are an appendix and do not count toward the report's eight main pages.

Save PNGs under **`docs/report/screenshots/`** using the names below. Then rebuild `RAHBAR_Assignment03_Report.pdf` with `python -m scripts.build_ragops_report` in an environment with ReportLab installed. The report builder appends each image on an appendix page. Do not submit the current review draft without completing the human requirements in CROSSCHECK.md.

Start here:

```powershell
Set-Location 'C:\Users\nofal\Documents\Codex\2026-11-11\i-x20\work\Rahbar'
kubectl config use-context minikube
New-Item docs/report/screenshots -ItemType Directory -Force
```

| Save as | Required evidence | Command to show |
| --- | --- | --- |
| A1-verification.png (and continuations) | All four Batch B checks, pass/fail and reasons | `kubectl logs -n rahbar job/ragops-demo-b` |
| A2-zero-chunks.png | Unchanged input shows `chunks_embedded: 0` (keep the separate verification count visible) | `kubectl logs -n rahbar job/ragops-demo-unchanged` |
| B-three-levels.png | Module, retrieval and e2e summary from actual run | `kubectl logs -n rahbar job/ragops-eval-final-candidate --tail=2` |
| C1-gate-fail.png | Bad candidate fails (recall .75 vs .85) | `python -m ragops.gate --baseline eval/results/baseline.json --candidate eval/results/bad-candidate.json --thresholds eval/thresholds.json` |
| C2-gate-pass.png | Passing candidate passes normal thresholds | `python -m ragops.gate --baseline eval/results/baseline.json --candidate eval/results/candidate.json --thresholds eval/thresholds.json` |
| D1-full-trace.png | One complete trace record | `Get-Content traces/compact-full-trace.json` |
| D2-rebuilt-prompt.png (continuations if needed) | Actual context and recorded prompt for a trace ID | `python -m ragops.traces traces/cluster.jsonl --trace-id demo-answer-20261126` |
| E1-before.png | Coverage .75, failing | `Get-Content eval/results/coverage-before.json` (or the committed coverage Job logs) |
| E2-after.png | Coverage .875, passing; same live queries | `Get-Content eval/results/coverage-after.json` |
| F1-cluster.png (continuations) | Resources, PVCs, ConfigMaps, CronJobs and Jobs | `kubectl get all,pvc,configmap,cronjob,job -n rahbar` |
| F2-ingestion-complete.png | Completed ingestion Job and its logs | `kubectl get job ragops-ingest -n rahbar; kubectl logs -n rahbar job/ragops-ingest` |
| F3-evaluation-complete.png | Completed evaluation Job and summary | `kubectl get job ragops-eval-final-candidate -n rahbar; kubectl logs -n rahbar job/ragops-eval-final-candidate --tail=2` |
| F4-configmap-fail.png | Tight threshold, failed Job and gate result | `kubectl logs -n rahbar job/ragops-gate-tight` |
| F5-configmap-pass.png | Restored threshold, passed Job and gate result; same image | `kubectl logs -n rahbar job/ragops-gate-normal` |
| F6-rollout-status.png | Actual controlled rollout command and result | Follow the safe live rerun below |
| F7-rollout-undo.png | Actual undo command and rollout status | Follow the safe live rerun below |
| F8-trace-after-undo.png | New trace shows restored collection and embedding digest | Follow the safe live rerun below |

The large JSON reports may exceed one screen. You can show each verification row with a small terminal command instead of cropping it:

```powershell
$v = Get-Content docs/evidence/ragops/demo-b.txt -Raw | ConvertFrom-Json
foreach ($d in $v.documents) {
  Write-Output "SOURCE: $($d.source) accepted=$($d.accepted)"
  $d.checks | ConvertTo-Json -Depth 5
}
```

For shorter before/after coverage images, print the actual result fields, then show uncovered topics separately:

```powershell
Get-Content eval/results/coverage-before.json -Raw | ConvertFrom-Json | Select-Object coverage,similarity_threshold,minimum_coverage,pass
Get-Content eval/results/coverage-after.json -Raw | ConvertFrom-Json | Select-Object coverage,similarity_threshold,minimum_coverage,pass
```

## Live rollout/undo screenshot rerun

Do this after reading the recorded release/rollback evidence. The deliberate bad revision is unready, so maxUnavailable=0 keeps the previous pod serving. Finish the undo; do not leave the cluster at the bad revision.

```powershell
kubectl rollout status deployment/api -n rahbar
kubectl set env deployment/api CHROMA_COLLECTION=rahbar-a3-screenshot-missing EMBED_MODEL=screenshot-invalid -n rahbar
kubectl rollout status deployment/api -n rahbar --timeout=15s
kubectl rollout undo deployment/api -n rahbar
kubectl rollout status deployment/api -n rahbar --timeout=90s
```

Then make a new request and inspect its new trace through port-forward. Keep the first terminal running:

```powershell
kubectl port-forward -n rahbar service/api 18080:8000
```

In a second terminal:

```powershell
$body = @{question='What happens to a student whose attendance falls below the required minimum in a course?'} | ConvertTo-Json
$answer = Invoke-RestMethod http://localhost:18080/api/ask -Method Post -ContentType application/json -Headers @{'X-RAGOps-Eval'='1'} -Body $body
Invoke-RestMethod "http://localhost:18080/api/traces/$($answer.request_id)" | Select-Object trace_id,collection,embedding_model,embedding_version,model_version,response | Format-List
```

Optional useful screenshots: `kubectl top pods -n rahbar`, injected-document exclusion (`traces/injection-demo.json`), changed/deleted document counts, archived-version restore, and the fresh-cluster smoke output. These support the report but are additional to the PDF's required list.

Do not substitute GitHub green-check screenshots or the old Assignment 02 Docker Hub screenshots for these Assignment 03 terminal/cluster screenshots.
