# Developing RAHBAR on Windows

The starter `Makefile` assumes bash and a Linux-style virtual environment. On Windows we use
PowerShell. Every command below is run from the repository root unless it says otherwise.

## Prerequisites

| Tool | Install | Who |
| --- | --- | --- |
| Git | `winget install Git.Git` | both |
| Python 3.12 | `winget install Python.Python.3.12` | both |
| VS Code | `winget install Microsoft.VisualStudioCode` | both |
| Docker Desktop (WSL 2 backend) | `winget install Docker.DockerDesktop` | Nofal |
| minikube | `winget install Kubernetes.minikube` | Nofal |
| kubectl | `winget install Kubernetes.kubectl` | Nofal |
| Ollama | `winget install Ollama.Ollama` | Nofal |

Check versions: `git --version`, `py -3.12 --version`, `docker version`, `minikube version`, `kubectl version --client`.

## Python environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r api/requirements-dev.txt -r indexer/requirements-dev.txt
```

## Everyday commands

| Purpose | Command |
| --- | --- |
| Test the api | `Set-Location api; ..\.venv\Scripts\pytest -q; Set-Location ..` |
| Test the indexer | `Set-Location indexer; ..\.venv\Scripts\pytest -q; Set-Location ..` |
| Lint | `.\.venv\Scripts\ruff check api indexer eval corpus` |
| Type-check the api | `Set-Location api; ..\.venv\Scripts\mypy app; Set-Location ..` |
| Type-check the indexer | `Set-Location indexer; ..\.venv\Scripts\mypy pipeline; Set-Location ..` |
| Run the api with stubs (chat UI at http://localhost:8000) | `Set-Location api; $env:SERVE_UI_DIR="../ui"; $env:RETRIEVER="stub"; $env:LLM_PROVIDER="stub"; ..\.venv\Scripts\uvicorn app.main:app --reload --port 8000` |
| Download the corpus | `.\.venv\Scripts\python corpus/fetch.py` |
| Submission checker | `python scripts/check_submission.py` |

## Cluster (Nofal's machine)

Docker Desktop must be running.

```powershell
minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
minikube addons enable metrics-server
minikube addons enable ingress
kubectl get nodes
```

Use `--memory=4096` if the machine has less than 16 GB of RAM. Calico is required: without it
NetworkPolicy manifests are accepted and silently ignored.

With the Docker driver on Windows the minikube IP is not reachable. Keep this running in a
separate PowerShell window while testing the Ingress, and use `127.0.0.1` as the address:

```powershell
minikube tunnel
```

Build and load images (minikube cannot see images built by your own Docker):

```powershell
docker build -t rahbar-api:dev api
docker build -f indexer/Dockerfile -t rahbar-indexer:dev .
# With the real corpus baked in (local only, never push this image):
# docker build -f indexer/Dockerfile --build-arg CORPUS_SRC=corpus/raw -t rahbar-indexer:dev .
docker build -t rahbar-ui:dev ui
minikube image load rahbar-api:dev
minikube image load rahbar-indexer:dev
minikube image load rahbar-ui:dev
```

Apply and watch:

```powershell
kubectl apply -k k8s/overlays/dev
kubectl get pods -n rahbar -w
```

Ask a question through the Ingress (tunnel running):

```powershell
$body = @{ question = "What CGPA puts a student on academic warning?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1/api/ask -Headers @{ Host = "rahbar.local" } -ContentType "application/json" -Body $body
```

## Ollama on the host (embeddings)

The cluster reaches Ollama at `host.minikube.internal:11434`, so Ollama must listen on all
interfaces:

```powershell
setx OLLAMA_HOST 0.0.0.0
```

Quit Ollama from the tray icon, start it again, then:

```powershell
ollama pull nomic-embed-text
minikube ssh "curl -s http://host.minikube.internal:11434/api/tags"
```

The last command must print JSON that lists `nomic-embed-text`. If it cannot connect, allow
inbound TCP port 11434 in Windows Firewall.

## Creating the LLM secret (never from a file)

```powershell
$env:LLM_API_KEY = "<paste the key in the terminal only>"
kubectl create secret generic rahbar-secret -n rahbar --from-literal=LLM_API_KEY="$env:LLM_API_KEY"
```

## Diagnosing a broken pod, in this order

```powershell
kubectl get pods -n rahbar
kubectl describe pod <name> -n rahbar
kubectl logs <name> -n rahbar
kubectl logs <name> -n rahbar --previous
```

Status first, then Events, then application output.
