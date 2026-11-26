"""Release only an evaluated candidate; pin collection/model in the pod template."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ragops.gate import evaluate


def main() -> None:
    p = argparse.ArgumentParser()
    for name in ('baseline', 'candidate', 'thresholds'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--collection', required=True)
    p.add_argument('--model', default='nomic-embed-text')
    p.add_argument('--top-k', type=int, default=3)
    p.add_argument('--image', default='rahbar-api:a3-r2')
    args = p.parse_args()
    baseline, candidate, thresholds = [json.loads(getattr(args, k).read_text())
                                      for k in ('baseline', 'candidate', 'thresholds')]
    verdict = evaluate(baseline, candidate, thresholds)
    print(json.dumps(verdict), flush=True)
    if not verdict['pass']:
        raise SystemExit(1)
    # A results file must identify the actual evaluated collection, model and top-k.
    identity = candidate['deployment']
    if identity != {'collection': args.collection, 'model': args.model, 'top_k': args.top_k, 'image': args.image}:
        raise SystemExit('candidate identity differs from requested release')
    patch = {'spec': {'template': {'spec': {'containers': [{'name': 'api', 'image': args.image, 'env': [
        {'name': 'CHROMA_COLLECTION', 'value': args.collection},
        {'name': 'EMBED_MODEL', 'value': args.model},
        {'name': 'TOP_K', 'value': str(args.top_k)}]}]}}}}
    subprocess.run(['kubectl', '-n', 'rahbar', 'patch', 'deployment', 'api', '--type=strategic',
                    '-p', json.dumps(patch)], check=True)
    subprocess.run(['kubectl', '-n', 'rahbar', 'rollout', 'status', 'deployment/api', '--timeout=300s'], check=True)
    subprocess.run(['kubectl', '-n', 'rahbar', 'set', 'env', 'cronjob/ragops-reindex',
                    f'CHROMA_COLLECTION={args.collection}', f'EMBED_MODEL={args.model}'], check=True)


if __name__ == '__main__':
    main()
